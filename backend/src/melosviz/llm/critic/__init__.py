"""Auto-critic loop: vision-LLM feedback on rendered scenes.

The critic takes a rendered scene (PNG/MP4 reference + the storyboard scene
description) and returns a structured critique:

  {
    "score": 0..10,
    "verdict": "approve" | "revise" | "reject",
    "issues": [{"category": "...", "severity": "...", "note": "..."}],
    "suggested_prompt_patch": "...",   # optional
  }

The loop runs at most `max_rounds` revisions per scene and stops when the
verdict is "approve" or the score is >= `approve_threshold`.

LLM providers (in priority order):
  1. OpenAI gpt-4o (when MELOSVIZ_CRITIC_API_KEY + MELOSVIZ_CRITIC_PROVIDER=openai)
  2. Anthropic claude-3-5-sonnet (when MELOSVIZ_CRITIC_API_KEY + MELOSVIZ_CRITIC_PROVIDER=anthropic)
  3. Google gemini-1.5-pro (when MELOSVIZ_CRITIC_API_KEY + MELOSVIZ_CRITIC_PROVIDER=google)
  4. Deterministic heuristic (no LLM key set)

The deterministic fallback scores the scene on the 5 dimensions below and
returns issues when any of them is below threshold.

Designed to plug into the orchestrator after each scene render: the
critic's verdict drives whether to re-render that scene with the
suggested prompt patch.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


class CritiqueVerdict(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class CritiqueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CritiqueIssue:
    category: str            # composition | palette | mood | continuity | quality
    severity: str            # low | medium | high | critical
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CritiqueResult:
    score: float                          # 0..10
    verdict: str                          # approve | revise | reject
    issues: list[CritiqueIssue]
    suggested_prompt_patch: str | None
    model_used: str
    latency_ms: int
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["issues"] = [i.to_dict() for i in self.issues]
        return d


@dataclass
class CriticRound:
    round_index: int
    result: CritiqueResult
    accepted: bool

    def to_dict(self) -> dict:
        return {
            "round_index": self.round_index,
            "result": self.result.to_dict(),
            "accepted": self.accepted,
        }


@dataclass
class AutoCriticReport:
    scene_index: int
    scene_name: str
    rounds: list[CritiqueRound] = field(default_factory=list)
    final_score: float = 0.0
    final_verdict: str = "reject"
    final_prompt: str = ""
    accepted: bool = False

    def to_dict(self) -> dict:
        return {
            "scene_index": self.scene_index,
            "scene_name": self.scene_name,
            "rounds": [r.to_dict() for r in self.rounds],
            "final_score": self.final_score,
            "final_verdict": self.final_verdict,
            "final_prompt": self.final_prompt,
            "accepted": self.accepted,
        }


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


_CRITIC_PROVIDERS = ("openai", "anthropic", "google", "deterministic")


def detect_provider() -> str:
    """Pick the highest-priority provider the current env supports."""
    explicit = os.environ.get("MELOSVIZ_CRITIC_PROVIDER", "").lower().strip()
    if explicit in _CRITIC_PROVIDERS:
        return explicit
    api_key = os.environ.get("MELOSVIZ_CRITIC_API_KEY", "").strip()
    if not api_key:
        return "deterministic"
    # Default by env-var naming convention.
    if api_key.startswith("sk-ant-"):
        return "anthropic"
    if api_key.startswith("sk-"):
        return "openai"
    if api_key.startswith("AIza"):
        return "google"
    return "openai"


# ---------------------------------------------------------------------------
# Deterministic heuristic (the offline fallback)
# ---------------------------------------------------------------------------


_KEYWORDS_QUALITY = ("blurry", "low-quality", "warped", "artifact", "deformed",
                      "extra fingers", "uncanny", "lowres")
_KEYWORDS_PALETTE = ("off-palette", "wrong colors", "too bright", "washed out")
_KEYWORDS_CONTINUITY = ("character drift", "wardrobe change", "env mismatch")
_KEYWORDS_MOOD = ("doesn't match mood", "wrong tone", "feels static")


def _heuristic_critique(image_path: Path | None, prompt: str) -> CritiqueResult:
    """Score the scene on 5 dimensions using prompt-side heuristics.

    Without a vision model we can only check the prompt-side description;
    the rendered frame is acknowledged (path recorded) but not actually
    read. The heuristic returns a *suggested_prompt_patch* with concrete
    prompt-level corrections so the orchestrator's `viz direct --replace-prompt`
    loop can iterate.
    """
    issues: list[CritiqueIssue] = []
    score = 8.0
    pl = prompt.lower()

    if any(kw in pl for kw in _KEYWORDS_QUALITY):
        issues.append(CritiqueIssue(
            category="quality",
            severity=CritiqueSeverity.HIGH.value,
            note="Prompt mentions quality concerns; re-render with stricter negatives.",
        ))
        score -= 1.5

    if any(kw in pl for kw in _KEYWORDS_PALETTE):
        issues.append(CritiqueIssue(
            category="palette",
            severity=CritiqueSeverity.MEDIUM.value,
            note="Prompt mentions palette drift; re-pin to the storyboard palette.",
        ))
        score -= 1.0

    if any(kw in pl for kw in _KEYWORDS_CONTINUITY):
        issues.append(CritiqueIssue(
            category="continuity",
            severity=CritiqueSeverity.CRITICAL.value,
            note="Prompt mentions character/wardrobe/env drift; lock continuity anchors.",
        ))
        score -= 2.0

    if any(kw in pl for kw in _KEYWORDS_MOOD):
        issues.append(CritiqueIssue(
            category="mood",
            severity=CritiqueSeverity.MEDIUM.value,
            note="Prompt mentions mood mismatch; align with outline's emotional_arc.",
        ))
        score -= 1.0

    # Image presence check (file exists, > 1 KB).
    if image_path is not None and image_path.exists():
        size = image_path.stat().st_size
        if size < 1024:
            issues.append(CritiqueIssue(
                category="quality",
                severity=CritiqueSeverity.CRITICAL.value,
                note=f"Rendered frame is suspiciously small ({size} bytes); likely empty.",
            ))
            score -= 2.0
    else:
        issues.append(CritiqueIssue(
            category="quality",
            severity=CritiqueSeverity.HIGH.value,
            note="No rendered frame on disk; orchestrator likely skipped or failed.",
        ))
        score -= 1.5

    score = max(0.0, min(10.0, round(score, 2)))

    if score >= 7.5:
        verdict = CritiqueVerdict.APPROVE.value
    elif score >= 5.0:
        verdict = CritiqueVerdict.REVISE.value
    else:
        verdict = CritiqueVerdict.REJECT.value

    # Suggest a concrete prompt patch when revisions are needed.
    suggested = None
    if verdict != CritiqueVerdict.APPROVE.value:
        suggested = _suggest_prompt_patch(prompt, issues)

    return CritiqueResult(
        score=score,
        verdict=verdict,
        issues=issues,
        suggested_prompt_patch=suggested,
        model_used="deterministic-heuristic",
        latency_ms=2,
    )


def _suggest_prompt_patch(prompt: str, issues: Sequence[CritiqueIssue]) -> str:
    """Build a revised prompt that targets the most-severe issue."""
    cats = {i.category for i in issues}
    suffixes: list[str] = []
    if "quality" in cats:
        suffixes.append("35mm film grain, sharp focus, no artifacts, no extra fingers, "
                        "physically plausible anatomy")
    if "palette" in cats:
        suffixes.append("strictly within the storyboard palette, no off-hue colors, "
                        "balanced contrast, no clipping")
    if "continuity" in cats:
        suffixes.append("character continuity locked: same face, same wardrobe, "
                        "same environment as previous scenes")
    if "mood" in cats:
        suffixes.append("mood matches the current scene's emotional_arc label, "
                        "controlled lighting, no jarring tonal shifts")
    if not suffixes:
        return prompt
    return f"{prompt.rstrip('. ')}. " + " ; ".join(suffixes)


# ---------------------------------------------------------------------------
# Vision-LLM providers (best-effort; only kick in when an API key is set)
# ---------------------------------------------------------------------------


def _openai_critique(image_path: Path, prompt: str) -> CritiqueResult:
    api_key = os.environ["MELOSVIZ_CRITIC_API_KEY"]
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    body = {
        "model": os.environ.get("MELOSVIZ_CRITIC_MODEL", "gpt-4o"),
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": f"Critique this rendered scene for a music video.\n"
                         f"Scene prompt: {prompt}\n\n"
                         f"Respond ONLY with JSON matching this schema:\n"
                         f"{{\"score\": 0-10, \"verdict\": \"approve|revise|reject\", "
                         f"\"issues\": [{{\"category\": \"...\", \"severity\": \"...\", \"note\": \"...\"}}], "
                         f"\"suggested_prompt_patch\": \"...\" or null}}"},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        }],
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    latency_ms = int((time.time() - t0) * 1000)
    content = payload["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return _dict_to_critique(parsed, model_used=body["model"], latency_ms=latency_ms,
                            cost_usd=_openai_cost(payload))


def _openai_cost(payload: dict) -> float:
    usage = payload.get("usage", {})
    return float(usage.get("prompt_tokens", 0)) / 1000.0 * 0.005 + \
           float(usage.get("completion_tokens", 0)) / 1000.0 * 0.015


def _anthropic_critique(image_path: Path, prompt: str) -> CritiqueResult:
    api_key = os.environ["MELOSVIZ_CRITIC_API_KEY"]
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    body = {
        "model": os.environ.get("MELOSVIZ_CRITIC_MODEL", "claude-3-5-sonnet-20240620"),
        "max_tokens": 600,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                {"type": "text",
                 "text": f"Scene prompt: {prompt}\n\n"
                         f"Critique as JSON: {{score 0-10, verdict, issues, suggested_prompt_patch}}"},
            ],
        }],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    latency_ms = int((time.time() - t0) * 1000)
    content = "".join(b.get("text", "")
                       for b in payload.get("content", []) if b.get("type") == "text")
    return _dict_to_critique(_extract_json(content), model_used=body["model"],
                            latency_ms=latency_ms, cost_usd=_anthropic_cost(payload))


def _anthropic_cost(payload: dict) -> float:
    usage = payload.get("usage", {})
    return float(usage.get("input_tokens", 0)) / 1000.0 * 0.003 + \
           float(usage.get("output_tokens", 0)) / 1000.0 * 0.015


def _google_critique(image_path: Path, prompt: str) -> CritiqueResult:
    api_key = os.environ["MELOSVIZ_CRITIC_API_KEY"]
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    model = os.environ.get("MELOSVIZ_CRITIC_MODEL", "gemini-1.5-pro")
    body = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                {"text": f"Critique this scene.\nPrompt: {prompt}\n\n"
                         f"Respond with JSON only: {{score, verdict, issues, suggested_prompt_patch}}"},
            ],
        }],
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    latency_ms = int((time.time() - t0) * 1000)
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    return _dict_to_critique(_extract_json(text), model_used=model,
                            latency_ms=latency_ms, cost_usd=0.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM response, even when wrapped."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON object in LLM response: {text[:200]!r}")
    return json.loads(m.group(0))


def _dict_to_critique(d: dict, *, model_used: str, latency_ms: int,
                      cost_usd: float) -> CritiqueResult:
    return CritiqueResult(
        score=float(d.get("score", 0.0)),
        verdict=str(d.get("verdict", "reject")),
        issues=[CritiqueIssue(
            category=str(i.get("category", "quality")),
            severity=str(i.get("severity", "low")),
            note=str(i.get("note", "")),
        ) for i in d.get("issues", [])],
        suggested_prompt_patch=d.get("suggested_prompt_patch"),
        model_used=model_used,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )


def critique_scene(image_path: Path, prompt: str,
                   provider: str | None = None) -> CritiqueResult:
    """One-shot critique of one rendered scene.

    Tries the requested `provider` first; falls back to heuristic if the
    provider raises (network error, missing key, model 4xx).
    """
    chosen = (provider or detect_provider()).lower()
    if chosen in ("openai", "anthropic", "google") and image_path.exists():
        try:
            if chosen == "openai":
                return _openai_critique(image_path, prompt)
            if chosen == "anthropic":
                return _anthropic_critique(image_path, prompt)
            if chosen == "google":
                return _google_critique(image_path, prompt)
        except (KeyError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            LOG.warning("Vision LLM %s failed (%s); falling back to heuristic.", chosen, exc)
    return _heuristic_critique(image_path if image_path.exists() else None, prompt)


def auto_critic_loop(
    image_path: Path,
    prompt: str,
    *,
    scene_index: int,
    scene_name: str,
    max_rounds: int = 3,
    approve_threshold: float = 7.5,
    provider: str | None = None,
) -> AutoCriticReport:
    """Iterate the critic up to `max_rounds` times; stop on APPROVE.

    The current prompt is patched using the critic's `suggested_prompt_patch`
    between rounds. The final report contains every round + the final
    accepted prompt.
    """
    report = AutoCriticReport(scene_index=scene_index, scene_name=scene_name,
                              final_prompt=prompt)
    current = prompt
    for i in range(max_rounds):
        result = critique_scene(image_path, current, provider=provider)
        accepted = result.verdict == CritiqueVerdict.APPROVE.value \
                  or result.score >= approve_threshold
        report.rounds.append(CriticRound(round_index=i, result=result,
                                         accepted=accepted))
        if accepted:
            break
        if result.suggested_prompt_patch:
            current = result.suggested_prompt_patch
        else:
            # No patch suggested; break to avoid an infinite loop.
            break
    report.final_score = report.rounds[-1].result.score
    report.final_verdict = report.rounds[-1].result.verdict
    report.final_prompt = current
    report.accepted = report.rounds[-1].accepted
    return report


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Auto-critic for one music-video scene")
    parser.add_argument("image", type=Path, help="Rendered scene frame (PNG/JPG)")
    parser.add_argument("prompt", type=str, help="Scene prompt")
    parser.add_argument("--scene-index", type=int, default=0)
    parser.add_argument("--scene-name", type=str, default="")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--approve-threshold", type=float, default=7.5)
    parser.add_argument("--provider", type=str, default=None,
                        choices=_CRITIC_PROVIDERS)
    parser.add_argument("--out", type=Path, default=None,
                        help="Write the AutoCriticReport JSON here")
    args = parser.parse_args(argv)

    report = auto_critic_loop(
        image_path=args.image,
        prompt=args.prompt,
        scene_index=args.scene_index,
        scene_name=args.scene_name,
        max_rounds=args.max_rounds,
        approve_threshold=args.approve_threshold,
        provider=args.provider,
    )
    payload = report.to_dict()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0 if report.accepted else 2


__all__ = [
    "CritiqueVerdict",
    "CritiqueSeverity",
    "CritiqueIssue",
    "CritiqueResult",
    "CriticRound",
    "AutoCriticReport",
    "detect_provider",
    "critique_scene",
    "auto_critic_loop",
    "main",
]