"""Tests for :mod:`melosviz.llm.critic`.

Coverage target: 90%+ line coverage so the per-module QGate floor is met.

Module surface under test::

    CritiqueVerdict       (approve | revise | reject)
    CritiqueSeverity      (low | medium | high | critical)
    CritiqueIssue         (dataclass + to_dict)
    CritiqueResult        (dataclass + to_dict)
    CriticRound           (dataclass + to_dict)
    AutoCriticReport      (dataclass + to_dict)
    detect_provider       (env-var + API-key-prefix dispatch)
    critique_scene        (provider dispatch + heuristic fallback)
    auto_critic_loop      (iterate until approve / cap)
    _suggest_prompt_patch (build patch from issue categories)
    _extract_json         (JSON extraction from LLM chatter)
    _dict_to_critique     (normalize raw dict to CritiqueResult)
    _heuristic_critique   (offline fallback)
    main                  (CLI entrypoint)

Network-dependent paths (``_openai_critique`` / ``_anthropic_critique`` /
``_google_critique``) are exercised with ``urllib.request.urlopen``
patched so the tests run fully offline.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from melosviz.llm import critic as critic_mod
from melosviz.llm.critic import (
    AutoCriticReport,
    CriticRound,
    CritiqueIssue,
    CritiqueResult,
    CritiqueSeverity,
    CritiqueVerdict,
    _anthropic_cost,
    _dict_to_critique,
    _extract_json,
    _heuristic_critique,
    _openai_cost,
    _suggest_prompt_patch,
    auto_critic_loop,
    critique_scene,
    detect_provider,
    main,
)

# ---------------------------------------------------------------------------
# Enum & dataclass shapes
# ---------------------------------------------------------------------------


def test_critique_verdict_string_values() -> None:
    assert {v.value for v in CritiqueVerdict} == {"approve", "revise", "reject"}


def test_critique_severity_string_values() -> None:
    assert {v.value for v in CritiqueSeverity} == {"low", "medium", "high", "critical"}


def test_critique_issue_to_dict_roundtrip() -> None:
    issue = CritiqueIssue(category="palette", severity="medium", note="too bright")
    assert issue.to_dict() == {"category": "palette", "severity": "medium", "note": "too bright"}


def test_critique_result_to_dict_includes_serialized_issues() -> None:
    issue = CritiqueIssue(category="quality", severity="low", note="blurry")
    result = CritiqueResult(
        score=6.5,
        verdict="revise",
        issues=[issue],
        suggested_prompt_patch="sharper",
        model_used="test",
        latency_ms=10,
        cost_usd=0.001,
    )
    d = result.to_dict()
    assert d["score"] == 6.5
    assert d["verdict"] == "revise"
    assert d["issues"] == [{"category": "quality", "severity": "low", "note": "blurry"}]
    assert d["suggested_prompt_patch"] == "sharper"
    assert d["cost_usd"] == 0.001


def test_critic_round_to_dict_round_trip() -> None:
    result = CritiqueResult(
        score=9.0,
        verdict="approve",
        issues=[],
        suggested_prompt_patch=None,
        model_used="deterministic-heuristic",
        latency_ms=2,
    )
    round_ = CriticRound(round_index=0, result=result, accepted=True)
    d = round_.to_dict()
    assert d == {
        "round_index": 0,
        "accepted": True,
        "result": result.to_dict(),
    }


def test_auto_critic_report_defaults_and_to_dict() -> None:
    report = AutoCriticReport(scene_index=2, scene_name="intro")
    assert report.rounds == []
    assert report.final_score == 0.0
    assert report.final_verdict == "reject"
    assert report.accepted is False
    d = report.to_dict()
    assert d == {
        "scene_index": 2,
        "scene_name": "intro",
        "rounds": [],
        "final_score": 0.0,
        "final_verdict": "reject",
        "final_prompt": "",
        "accepted": False,
    }


# ---------------------------------------------------------------------------
# detect_provider
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_critic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MELOSVIZ_CRITIC_PROVIDER", raising=False)
    monkeypatch.delenv("MELOSVIZ_CRITIC_API_KEY", raising=False)
    # _anthropic_critique reads this with a default, so an ambient value would
    # silently change the model name the provider tests assert on.
    monkeypatch.delenv("MELOSVIZ_CRITIC_MODEL", raising=False)


def test_detect_provider_explicit_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MELOSVIZ_CRITIC_PROVIDER", "openai")
    monkeypatch.delenv("MELOSVIZ_CRITIC_API_KEY", raising=False)
    assert detect_provider() == "openai"


def test_detect_provider_explicit_anthropic_google_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for explicit, expected in (
        ("anthropic", "anthropic"),
        ("google", "google"),
        ("deterministic", "deterministic"),
    ):
        monkeypatch.setenv("MELOSVIZ_CRITIC_PROVIDER", explicit)
        assert detect_provider() == expected


def test_detect_provider_no_key_returns_deterministic(clean_critic_env: None) -> None:
    assert detect_provider() == "deterministic"


def test_detect_provider_anthropic_key_prefix(
    monkeypatch: pytest.MonkeyPatch,
    clean_critic_env: None,
) -> None:
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-ant-fakefake")
    assert detect_provider() == "anthropic"


def test_detect_provider_openai_key_prefix(
    monkeypatch: pytest.MonkeyPatch,
    clean_critic_env: None,
) -> None:
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-fakefakefake")
    assert detect_provider() == "openai"


def test_detect_provider_google_key_prefix(
    monkeypatch: pytest.MonkeyPatch,
    clean_critic_env: None,
) -> None:
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "AIzaFakeKey")
    assert detect_provider() == "google"


def test_detect_provider_unknown_prefix_defaults_to_openai(
    monkeypatch: pytest.MonkeyPatch,
    clean_critic_env: None,
) -> None:
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "totally-unrecognised")
    assert detect_provider() == "openai"


def test_detect_provider_explicit_trumps_key_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "AIzaFakeKey")
    monkeypatch.setenv("MELOSVIZ_CRITIC_PROVIDER", "anthropic")
    assert detect_provider() == "anthropic"


def test_detect_provider_invalid_explicit_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MELOSVIZ_CRITIC_PROVIDER", "nonsense-provider")
    monkeypatch.delenv("MELOSVIZ_CRITIC_API_KEY", raising=False)
    assert detect_provider() == "deterministic"


# ---------------------------------------------------------------------------
# _heuristic_critique
# ---------------------------------------------------------------------------


def _critique(image: Path, prompt: str) -> CritiqueResult:
    """Helper: route through critique_scene with explicit deterministic provider."""
    return critique_scene(image, prompt, provider="deterministic")


def test_heuristic_clean_prompt_with_render_approves(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"\x89PNG" + b"x" * 4096)
    result = _critique(image, "A neon noir rooftop at midnight, slow camera push-in")
    assert result.model_used == "deterministic-heuristic"
    assert result.verdict == CritiqueVerdict.APPROVE.value
    assert result.score >= 7.5
    assert result.issues == []
    assert result.suggested_prompt_patch is None


def test_heuristic_quality_keyword_lowers_score(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    result = _critique(image, "A warped, blurry portrait with extra fingers")
    assert any(i.category == "quality" for i in result.issues)


def test_heuristic_palette_keyword_lowers_score(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    result = _critique(image, "Too bright, washed out colors everywhere")
    assert any(i.category == "palette" for i in result.issues)


def test_heuristic_continuity_keyword_lowers_score(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    result = _critique(image, "Character drift, wardrobe change throughout")
    assert any(i.category == "continuity" for i in result.issues)


def test_heuristic_mood_keyword_lowers_score(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    result = _critique(image, "Feels static, wrong tone for the arc")
    assert any(i.category == "mood" for i in result.issues)


def test_heuristic_tiny_image_is_critical(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x")  # 1 byte < 1024 threshold
    result = _critique(image, "Clean prompt")
    crit_issue = next(i for i in result.issues if "small" in i.note)
    assert crit_issue.severity == "critical"


def test_heuristic_no_image_on_disk_lowers_score(tmp_path: Path) -> None:
    """image_path.exists() is False -> the helper routes via heuristic-with-None."""
    result = _heuristic_critique(None, "Clean prompt")
    assert any("No rendered frame" in i.note for i in result.issues)


def test_heuristic_multiple_issues_drive_verdict_to_revise_or_reject(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    prompt = "Warp, blurry, extra fingers, washed out, character drift, wrong tone"
    result = _critique(image, prompt)
    assert result.verdict in {"revise", "reject"}
    assert len(result.issues) >= 3


def test_heuristic_score_is_clamped_to_0_10(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    result = _critique(
        image,
        "everything blurry warped wrong tone washed out character drift extra fingers warped",
    )
    assert 0.0 <= result.score <= 10.0


# ---------------------------------------------------------------------------
# _suggest_prompt_patch
# ---------------------------------------------------------------------------


def test_suggest_prompt_patch_with_no_issues_returns_original() -> None:
    """Edge case: ``_suggest_prompt_patch`` short-circuits when there are no issues."""
    patched = _suggest_prompt_patch("A clean prompt with no problems.", [])
    assert patched == "A clean prompt with no problems."


def test_suggest_prompt_patch_quality_only() -> None:
    issues = [CritiqueIssue(category="quality", severity="high", note="blurry")]
    patched = _suggest_prompt_patch("base prompt", issues)
    assert "base prompt" in patched
    assert "35mm film grain" in patched


def test_suggest_prompt_patch_palette_only() -> None:
    issues = [CritiqueIssue(category="palette", severity="medium", note="washed")]
    patched = _suggest_prompt_patch("base prompt", issues)
    assert "strictly within the storyboard palette" in patched


def test_suggest_prompt_patch_continuity_only() -> None:
    issues = [CritiqueIssue(category="continuity", severity="critical", note="drift")]
    patched = _suggest_prompt_patch("base prompt", issues)
    assert "character continuity locked" in patched


def test_suggest_prompt_patch_mood_only() -> None:
    issues = [CritiqueIssue(category="mood", severity="medium", note="static")]
    patched = _suggest_prompt_patch("base prompt", issues)
    assert "mood matches" in patched


def test_suggest_prompt_patch_combines_multiple_categories() -> None:
    issues = [
        CritiqueIssue(category="quality", severity="high", note="x"),
        CritiqueIssue(category="mood", severity="medium", note="y"),
    ]
    patched = _suggest_prompt_patch("base prompt", issues)
    # Both suffixes appear, joined by ' ; '.
    assert "35mm film grain" in patched
    assert "mood matches" in patched


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


def test_extract_json_pure_json() -> None:
    assert _extract_json('{"score": 9}') == {"score": 9}


def test_extract_json_with_surrounding_text() -> None:
    text = 'Sure! Here you go: {"score": 7, "verdict": "approve"} thanks.'
    assert _extract_json(text) == {"score": 7, "verdict": "approve"}


def test_extract_json_missing_raises_value_error() -> None:
    with pytest.raises(ValueError, match="No JSON"):
        _extract_json("no braces here")


# ---------------------------------------------------------------------------
# _dict_to_critique
# ---------------------------------------------------------------------------


def test_dict_to_critique_normalizes_missing_fields() -> None:
    d = {
        "score": "8.0",
        "verdict": 42,
        "issues": [{"category": 99, "severity": None, "note": b"bytes"}],
        "suggested_prompt_patch": "patch",
    }
    crit = _dict_to_critique(d, model_used="m", latency_ms=5, cost_usd=0.1)
    assert crit.score == 8.0
    assert crit.verdict == "42"
    assert crit.issues[0].category == "99"
    assert crit.issues[0].severity == "None"
    assert crit.issues[0].note == "b'bytes'"


# ---------------------------------------------------------------------------
# auto_critic_loop
# ---------------------------------------------------------------------------


def _approve_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_heuristic(image, prompt):
        return CritiqueResult(
            score=10.0,
            verdict=CritiqueVerdict.APPROVE.value,
            issues=[],
            suggested_prompt_patch=None,
            model_used="deterministic-heuristic",
            latency_ms=1,
        )

    monkeypatch.setattr(critic_mod, "_heuristic_critique", _fake_heuristic)


def test_auto_critic_loop_exits_on_approve_immediately(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    monkeypatch_obj = pytest.MonkeyPatch()
    try:
        _approve_heuristic(monkeypatch_obj)
        report = auto_critic_loop(
            image_path=image,
            prompt="anything",
            scene_index=0,
            scene_name="intro",
            max_rounds=3,
            approve_threshold=7.5,
            provider="deterministic",
        )
    finally:
        monkeypatch_obj.undo()
    assert report.accepted is True
    assert len(report.rounds) == 1
    assert report.final_score == 10.0


def test_auto_critic_loop_caps_at_max_rounds_when_always_rejecting(
    tmp_path: Path,
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    seen: list[str] = []

    def _record(image, prompt):
        seen.append(prompt)
        return CritiqueResult(
            score=2.0,
            verdict=CritiqueVerdict.REJECT.value,
            issues=[CritiqueIssue(category="quality", severity="high", note="bad")],
            suggested_prompt_patch=f"{prompt} (patched v2)",
            model_used="deterministic-heuristic",
            latency_ms=1,
        )

    monkeypatch_obj = pytest.MonkeyPatch()
    try:
        monkeypatch_obj.setattr(critic_mod, "_heuristic_critique", _record)
        report = auto_critic_loop(
            image_path=image,
            prompt="p0",
            scene_index=1,
            scene_name="verse",
            max_rounds=3,
            approve_threshold=7.5,
            provider="deterministic",
        )
    finally:
        monkeypatch_obj.undo()
    assert len(report.rounds) == 3
    assert report.accepted is False
    assert report.final_verdict == "reject"
    # Each round must critique the previous round's patch, not the original
    # prompt. Without this the loop could keep re-criticing "p0" forever.
    assert seen == ["p0", "p0 (patched v2)", "p0 (patched v2) (patched v2)"]
    # The loop applies the last round's patch after recording the round, so the
    # final prompt is one patch ahead of the last critiqued prompt.
    assert report.final_prompt == "p0 (patched v2) (patched v2) (patched v2)"


def test_auto_critic_loop_halts_when_no_patch_suggested(tmp_path: Path) -> None:
    """A round that rejects with no patch must not loop forever."""
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)

    def _reject_no_patch(image, prompt):
        return CritiqueResult(
            score=4.0,
            verdict=CritiqueVerdict.REJECT.value,
            issues=[CritiqueIssue(category="quality", severity="high", note="bad")],
            suggested_prompt_patch=None,
            model_used="deterministic-heuristic",
            latency_ms=1,
        )

    monkeypatch_obj = pytest.MonkeyPatch()
    try:
        monkeypatch_obj.setattr(critic_mod, "_heuristic_critique", _reject_no_patch)
        report = auto_critic_loop(
            image_path=image,
            prompt="p0",
            scene_index=0,
            scene_name="verse",
            max_rounds=10,
            approve_threshold=7.5,
            provider="deterministic",
        )
    finally:
        monkeypatch_obj.undo()
    assert len(report.rounds) == 1
    assert report.accepted is False


def test_auto_critic_loop_score_threshold_path(tmp_path: Path) -> None:
    """A 'revise' verdict that nonetheless exceeds approve_threshold accepts."""
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)

    def _revise_high_score(image, prompt):
        # Score above threshold even though verdict is "revise" -> accepted.
        return CritiqueResult(
            score=8.0,
            verdict=CritiqueVerdict.REVISE.value,
            issues=[],
            suggested_prompt_patch=None,
            model_used="deterministic-heuristic",
            latency_ms=1,
        )

    monkeypatch_obj = pytest.MonkeyPatch()
    try:
        monkeypatch_obj.setattr(critic_mod, "_heuristic_critique", _revise_high_score)
        report = auto_critic_loop(
            image_path=image,
            prompt="p",
            scene_index=0,
            scene_name="verse",
            max_rounds=3,
            approve_threshold=7.5,
            provider="deterministic",
        )
    finally:
        monkeypatch_obj.undo()
    assert report.accepted is True
    assert len(report.rounds) == 1


# ---------------------------------------------------------------------------
# Mocked HTTP paths
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


def _fake_urlopen_response(payload: dict[str, Any]) -> _FakeResponse:
    return _FakeResponse(json.dumps(payload).encode("utf-8"))


def test_openai_critique_parses_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"fake-png")
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-test")

    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "score": 9.1,
                            "verdict": "approve",
                            "issues": [],
                            "suggested_prompt_patch": None,
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
    }

    captured: dict[str, Any] = {}

    def _fake_urlopen(req: urllib.request.Request, timeout: int | None = None) -> _FakeResponse:
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _fake_urlopen_response(payload)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    result = critic_mod._openai_critique(image, "scene prompt")

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    # Assert the request actually carries the image, prompt, model, and JSON
    # response mode. Without these, dropping any of them from the body would
    # leave this test green.
    assert captured["body"]["model"] == "gpt-4o"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    content = captured["body"]["messages"][0]["content"]
    assert "scene prompt" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert result.verdict == "approve"
    assert result.score == 9.1
    # 1000/1000*0.005 + 200/1000*0.015 = 0.005 + 0.003 = 0.008
    assert result.cost_usd == pytest.approx(0.008)


def test_openai_cost_uses_openai_pricing() -> None:
    payload = {"usage": {"prompt_tokens": 2000, "completion_tokens": 500}}
    # 2000/1000*0.005 + 500/1000*0.015
    assert _openai_cost(payload) == pytest.approx(0.0175)


def test_anthropic_cost_uses_anthropic_pricing() -> None:
    payload = {"usage": {"input_tokens": 1000, "output_tokens": 500}}
    # 1000/1000*0.003 + 500/1000*0.015
    assert _anthropic_cost(payload) == pytest.approx(0.0105)


def test_anthropic_critique_handles_text_block_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clean_critic_env: None,
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"fake-png")
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-ant-test")

    payload = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"score": 7.0, "verdict": "approve", "issues": []}),
            }
        ],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=None: _fake_urlopen_response(payload),
    )
    result = critic_mod._anthropic_critique(image, "scene prompt")
    assert result.score == 7.0
    assert result.verdict == "approve"
    assert result.model_used == "claude-3-5-sonnet-20240620"


def test_anthropic_critique_skips_non_text_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"fake-png")
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-ant-test")

    payload = {
        "content": [
            {"type": "image", "source": {}},
            {"type": "text", "text": json.dumps({"score": 5, "verdict": "revise", "issues": []})},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=None: _fake_urlopen_response(payload),
    )
    result = critic_mod._anthropic_critique(image, "p")
    assert result.score == 5


def test_google_critique_handles_candidates_parts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"fake-png")
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "AIzaFake")

    body = json.dumps({"score": 8.0, "verdict": "approve", "issues": []})
    payload = {"candidates": [{"content": {"parts": [{"text": body}]}}]}

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=None: _fake_urlopen_response(payload),
    )
    result = critic_mod._google_critique(image, "scene prompt")
    assert result.score == 8.0
    assert result.verdict == "approve"


# ---------------------------------------------------------------------------
# critique_scene: dispatch + fallback
# ---------------------------------------------------------------------------


def test_critique_scene_falls_back_when_provider_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-fake")

    def _boom(req, timeout=None):
        raise urllib.error.URLError("network is down")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    result = critic_mod.critique_scene(image, "clean prompt", provider="openai")
    assert result.model_used == "deterministic-heuristic"


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(urllib.error.URLError("network is down"), id="urlerror"),
        pytest.param(
            urllib.error.HTTPError("https://api.openai.com", 500, "server error", None, None),
            id="httperror",
        ),
        pytest.param(json.JSONDecodeError("not json", "{", 0), id="malformed_json"),
    ],
)
def test_critique_scene_falls_back_on_each_provider_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    """critique_scene catches URLError, HTTPError, and JSONDecodeError.

    Each is a distinct failure mode from the provider, and a regression that
    dropped one from the except clause would let a real request error escape
    instead of falling back to the deterministic heuristic.
    """
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-fake")

    def _raise(req, timeout=None):
        raise failure

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    result = critic_mod.critique_scene(image, "clean prompt", provider="openai")
    assert result.model_used == "deterministic-heuristic"


def test_critique_scene_anthropic_dispatch_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When provider=anthropic, the anthropic branch is dispatched."""
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-ant-fake")

    captured: dict[str, Any] = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _fake_urlopen_response(
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"score": 9, "verdict": "approve", "issues": []}),
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    result = critic_mod.critique_scene(image, "p", provider="anthropic")
    # Assert on the parsed hostname, not a substring: a substring check would
    # also pass for "https://evil.test/?x=api.anthropic.com", and it trips the
    # CodeQL incomplete-URL-substring-sanitization check.
    assert urllib.parse.urlparse(captured["url"]).hostname == "api.anthropic.com"
    assert result.score == 9


def test_critique_scene_google_dispatch_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "AIzaFake")

    captured: dict[str, Any] = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _fake_urlopen_response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {"score": 8, "verdict": "approve", "issues": []}
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    result = critic_mod.critique_scene(image, "p", provider="google")
    # Parsed-hostname assertion, for the reason given in the Anthropic test.
    assert urllib.parse.urlparse(captured["url"]).hostname == "generativelanguage.googleapis.com"
    assert result.score == 8


def test_critique_scene_with_missing_image_routes_to_heuristic_with_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """critique_scene(image=missing, provider=openai) -> falls back to heuristic."""
    monkeypatch.setenv("MELOSVIZ_CRITIC_API_KEY", "sk-fake")
    result = critic_mod.critique_scene(tmp_path / "no_such_file.png", "p", provider="openai")
    # image.exists() is False so we skip HTTP and go straight to heuristic.
    assert result.model_used == "deterministic-heuristic"


# ---------------------------------------------------------------------------
# main: CLI entrypoint
# ---------------------------------------------------------------------------


def test_main_approve_returns_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)
    out = tmp_path / "report.json"

    def _approve(image, prompt):
        return CritiqueResult(
            score=10.0,
            verdict=CritiqueVerdict.APPROVE.value,
            issues=[],
            suggested_prompt_patch=None,
            model_used="deterministic-heuristic",
            latency_ms=1,
        )

    monkeypatch.setattr(critic_mod, "_heuristic_critique", _approve)
    rc = main(
        [
            str(image),
            "clean",
            "--scene-index",
            "0",
            "--scene-name",
            "intro",
            "--max-rounds",
            "3",
            "--approve-threshold",
            "7.5",
            "--provider",
            "deterministic",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["accepted"] is True


def test_main_reject_returns_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x" * 4096)

    def _reject(image, prompt):
        return CritiqueResult(
            score=2.0,
            verdict=CritiqueVerdict.REJECT.value,
            issues=[CritiqueIssue(category="quality", severity="high", note="bad")],
            suggested_prompt_patch=f"{prompt} v2",
            model_used="deterministic-heuristic",
            latency_ms=1,
        )

    monkeypatch.setattr(critic_mod, "_heuristic_critique", _reject)
    rc = main(
        [
            str(image),
            "p",
            "--provider",
            "deterministic",
            "--max-rounds",
            "1",
        ]
    )
    assert rc == 2
