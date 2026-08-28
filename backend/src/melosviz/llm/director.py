"""Director — turns MIR + concept into a beat-synced scene storyboard.

The Director is the **creative brain** of the MelosViz pipeline. It takes
the MIR summary (BPM, key, structure, energy, mood) and a free-form
*concept prompt* (e.g. *"neon-noir city at midnight, a dancer losing
themselves in the music"*) and emits a **storyboard**: one
:class:`StoryboardScene` per music segment, each with a tool choice
(``comfyui_image`` / ``comfyui_video`` / ``procedural_3d_animation`` /
``c4d_3d`` / ``unreal_cinematic`` / ``motion_graphics_beat_sync``), a
prompt, palette tweaks, camera moves, and beat-synced timing.

How the Director picks scenes
-----------------------------
The Director assigns scenes by:

1. **Segment archetype** — intro/verse/chorus/drop/bridge/breakdown/outro
   each maps to a default "house style" (e.g. intro = title card, drop =
   high-energy 3D burst, breakdown = slow motion video clip).
2. **Anti-repeat constraint** — no two adjacent scenes share the same
   ``scene_type`` (mirrors :mod:`melosviz.compose.narrator`).
3. **Beat alignment** — scene durations are quantised to whole bars
   (``bars = round(segment_dur * bpm / 60)``).
4. **LLM refinement (optional)** — when ``MELOSVIZ_LLM_ENDPOINT`` is set,
   we POST a JSON request to a cheap LLM (OpenAI-compatible) and ask it
   to rewrite the per-scene prompts in the user's concept voice. The LLM
   never invents new tools / timings — it only rewords prompts.

Without an LLM, the Director uses deterministic templates per archetype
and concept-keyword matching (color, lighting, mood keywords) — fully
offline, fully reproducible.

Configuration (env vars)
------------------------
``MELOSVIZ_LLM_ENDPOINT``    OpenAI-compatible chat-completions URL.
``MELOSVIZ_LLM_MODEL``        Model name (default ``"gpt-4o-mini"``).
``MELOSVIZ_LLM_API_KEY``      Bearer token.
``MELOSVIZ_LLM_TIMEOUT``      Per-call timeout, seconds (default 60).

Usage::

    from melosviz.llm.director import Director, DirectorRequest
    director = Director()
    req = DirectorRequest(
        concept="neon-noir city at midnight, dancer losing themselves",
        duration_s=210.0, bpm=124.0, key="F# minor",
        segments=[...],  # SceneSegment dicts from MIR
    )
    board = director.storyboard(req)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Schema version for :class:`ContinuityAnchor`. Bumped from v1 to v2 in
#: 2026-08 (WBS-2): ``reference_image`` changed from ``str = ""`` to
#: ``Path | None = None`` so the field is strongly-typed and ``None`` is
#: explicit (no more "empty string means missing" ambiguity). v2 is
#: wire-incompatible with v1 payloads that used ``""`` for absent —
#: ``from_concept`` continues to default to ``None`` for missing
#: references. Downstream consumers (ComfyUI IP-Adapter, C4D reference
#: shader) should treat ``None`` as "no reference attached".
CONTINUITY_ANCHOR_VERSION = 2

__all__ = [
    "CONTINUITY_ANCHOR_VERSION",
    "ContinuityAnchor",
    "DEFAULT_ASPECT_RATIO",
    "Director",
    "DirectorRequest",
    "StoryboardScene",
    "Storyboard",
    "DIRECTOR_SCENE_TYPES",
    "list_aspect_ratios",
    "resolve_aspect_ratio",
]


# ---------------------------------------------------------------------------
# Lazy imports to avoid a hard dep on lyrics/moodboard when only the
# basic API surface is used (e.g. in unit tests of unrelated modules).
# ---------------------------------------------------------------------------

def _lyrics_align(phrases, segments, **kw):
    from .lyrics import align_to_segments
    return align_to_segments(phrases, segments, **kw)


def _mood_board(paths):
    from .moodboard import mood_board_summary
    return mood_board_summary(paths)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LLM_ENDPOINT_ENV = "MELOSVIZ_LLM_ENDPOINT"
_LLM_MODEL_ENV = "MELOSVIZ_LLM_MODEL"
_LLM_KEY_ENV = "MELOSVIZ_LLM_API_KEY"
_LLM_TIMEOUT_ENV = "MELOSVIZ_LLM_TIMEOUT"

DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_LLM_TIMEOUT_S = 60

#: All scene types the Director may emit. Must be keys the conductor
#: registry can route (see ``melosviz.conductor.registry``).
DIRECTOR_SCENE_TYPES: tuple[str, ...] = (
    "comfyui_image",
    "comfyui_video",
    "procedural_3d_animation",
    "c4d_3d",
    "unreal_cinematic",
    "motion_graphics_beat_sync",
    "generative_asset",  # legacy alias → maps to comfyui_image
    "comfyui_audio_video_wan",        # WBS-107: Wan S2V audio-conditioned
    "comfyui_audio_video_seedance",   # WBS-107: Seedance A2V audio-conditioned
)

#: Archetype → default (scene_type, prompt suffix, camera move) palette.
#: WBS-109: ``audio_video_scene_type`` overrides ``scene_type`` when the
#: audio-conditioned pipeline is engaged (see :meth:`Director.storyboard`).
#: ``audio_video_requires_character`` gates the override — e.g. ``chorus``
#: only switches to Seedance A2V when an anchor subject token is present
#: (or the user explicitly opts in via ``--audio-conditioned-video``).
_ARCHETYPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "intro":     {"scene_type": "comfyui_image",        "camera": "slow_dolly_in",     "prompt_tail": "title card, cinematic letterbox, breathing room"},
    "verse":     {"scene_type": "comfyui_video",        "camera": "handheld_orbit",    "prompt_tail": "intimate close-ups, naturalistic light, subtle motion"},
    "chorus":    {"scene_type": "comfyui_video",        "camera": "whip_pan_burst",    "prompt_tail": "wide vista, saturated palette, hero pose, dynamic camera",
                  "audio_video_scene_type": "comfyui_audio_video_seedance", "audio_video_requires_character": True},
    "drop":      {"scene_type": "unreal_cinematic",     "camera": "impact_punch_in",   "prompt_tail": "kinetic impact frame, hyper-detailed, lens flare, pyro",
                  "audio_video_scene_type": "comfyui_audio_video_wan"},
    "bridge":    {"scene_type": "motion_graphics_beat_sync", "camera": "parallax_scroll", "prompt_tail": "type-led transition, geometry morph, beat-synced type reveal"},
    "breakdown": {"scene_type": "comfyui_video",        "camera": "slow_push_in",      "prompt_tail": "long take, soft focus, dreamlike, ambient texture"},
    "outro":     {"scene_type": "comfyui_image",        "camera": "slow_pull_back",    "prompt_tail": "fade to black, end credits plate, restrained motion"},
    "unknown":   {"scene_type": "comfyui_image",        "camera": "static_hero",       "prompt_tail": "balanced framing, neutral light"},
}

#: Concept keyword → lighting / palette bias (multiplicative on palette).
_CONCEPT_KEYWORD_BIAS: dict[str, dict[str, str]] = {
    "neon":         {"lighting": "neon noir",   "palette_suffix": "magenta+cyan"},
    "city":         {"lighting": "urban night", "palette_suffix": "amber+teal"},
    "forest":       {"lighting": "dappled",     "palette_suffix": "moss+sunbeam"},
    "underwater":   {"lighting": "caustic",     "palette_suffix": "aqua+indigo"},
    "desert":       {"lighting": "harsh sun",   "palette_suffix": "ochre+sienna"},
    "space":        {"lighting": "rim light",   "palette_suffix": "violet+gold"},
    "dance":        {"lighting": "strobe",      "palette_suffix": "magenta+white"},
    "love":         {"lighting": "soft warm",   "palette_suffix": "rose+cream"},
    "loss":         {"lighting": "cold blue",   "palette_suffix": "steel+ash"},
    "festival":     {"lighting": "festival",    "palette_suffix": "fuchsia+lime"},
}


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class ContinuityAnchor:
    """Per-storyboard "this is who we follow" tokens.

    Each storyboard has one anchor that gets threaded into every scene
    prompt + the workflow's IP-Adapter / reference-image fields so
    ComfyUI/C4D/UE can keep the same subject + environment across
    scene cuts.

    The anchor is derived from the user-supplied ``--continuity`` flag
    or, when not given, from the first non-trivial noun phrase in the
    concept prompt. Every Director call exposes ``DirectorRequest.continuity``
    so users can pin a subject manually.

    .. versionchanged:: v2 (2026-08)
        ``reference_image`` changed from ``str = ""`` (v1) to
        ``Path | None = None`` (v2). v1 callers that passed an empty
        string for "no reference" still work — ``from_concept`` defaults
        to ``None`` and downstream consumers treat ``None`` as "no
        reference attached". Existing v1 payloads that passed a
        file-path string will be coerced via :class:`pathlib.Path` and
        validated for existence.
    """
    subject_token: str = ""        # e.g. ``"a young woman with bioluminescent tattoos"``
    env_token: str = ""            # e.g. ``"underwater city, coral archways"``
    palette_token: str = ""        # e.g. ``"deep teal, magenta, bone white"``
    #: Path to an IP-Adapter / style reference image. ``None`` means
    #: "no reference attached" (v2). The path is validated for existence
    #: by :meth:`from_concept` and the orchestrator; missing files are
    #: silently dropped to ``None`` with a warning rather than aborting
    #: the render — operators can fix the path and re-render.
    reference_image: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON.

        ``reference_image`` is emitted as ``str(path)`` when set, or
        ``None`` when absent, so v2 payloads are explicit about missing
        references (v1 used ``""``, which was ambiguous).
        """
        return {
            **asdict(self),
            "reference_image": (
                str(self.reference_image) if self.reference_image else None
            ),
            "_version": CONTINUITY_ANCHOR_VERSION,
        }

    @classmethod
    def from_concept(
        cls,
        concept: str,
        *,
        reference_image: Path | None = None,
    ) -> "ContinuityAnchor":
        """Best-effort anchor derivation from a free-form concept string.

        Args:
            concept: Free-form concept text. Used for crude noun
                extraction (first 2 comma-separated chunks become
                subject + environment, palette defaults to empty).
            reference_image: Optional path to an IP-Adapter / style
                reference image (v2; was a positional ``str = ""`` arg
                in v1). When supplied, the path is validated for
                existence — missing files are dropped to ``None`` with
                a warning rather than aborting the pipeline.
        """
        c = concept.strip()
        parts = [p.strip(" .,;:") for p in c.split(",") if p.strip()] if c else []
        subject = parts[0] if parts else ""
        env = parts[1] if len(parts) > 1 else ""
        ref = cls._validate_reference(reference_image)
        return cls(
            subject_token=subject,
            env_token=env,
            palette_token="",
            reference_image=ref,
        )

    @staticmethod
    def _validate_reference(value: Path | str | None) -> Path | None:
        """Coerce + validate a reference_image candidate.

        Accepts a :class:`pathlib.Path`, a string path (legacy v1
        callers), or ``None``. When the resulting path doesn't exist
        on disk, the reference is dropped to ``None`` and a warning is
        logged — silence is preferred to a hard crash because the
        alternative path (no IP-Adapter) still produces a useful render.
        """
        if value is None or value == "":
            return None
        try:
            p = value if isinstance(value, Path) else Path(str(value))
        except (TypeError, ValueError) as exc:
            logger.warning(
                "ContinuityAnchor: could not coerce %r to Path (%s); "
                "reference_image dropped.",
                value,
                exc,
            )
            return None
        if not p.is_file():
            logger.warning(
                "ContinuityAnchor: reference_image %s does not exist "
                "(or is not a regular file); dropping to None.",
                p,
            )
            return None
        return p


@dataclass
class StoryboardScene:
    """One scene in the Director's storyboard.

    Mirrors a RenderSpec scene-segment dict but adds Director-level fields
    so the orchestrator knows which tool to dispatch and how to time it.
    """
    index: int
    label: str                    # intro / verse / chorus / drop / …
    start: float                  # seconds in source track
    end: float
    duration: float
    scene_type: str               # a DIRECTOR_SCENE_TYPES value
    prompt: str                   # full diffusion / 3-D prompt
    negative: str = ""
    camera: str = "static_hero"
    beats_in_segment: list[float] = field(default_factory=list)
    bar_count: int = 0
    palette_override: list[str] = field(default_factory=list)
    seed: int = 0
    notes: str = ""
    #: Per-scene width / height (driven by the storyboard's aspect_ratio).
    width: int = 1280
    height: int = 720
    fps: int = 24
    #: Per-scene continuity anchor — populated from the storyboard's
    #: top-level :class:`ContinuityAnchor` so ComfyUI IP-Adapter / C4D /
    #: UE can reference the same subject + environment across cuts.
    continuity: ContinuityAnchor = field(default_factory=ContinuityAnchor)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["beats_in_segment"] = list(self.beats_in_segment)
        d["continuity"] = self.continuity.to_dict()
        return d


@dataclass
class Storyboard:
    """The full output of :meth:`Director.storyboard`."""
    concept: str
    duration_s: float
    bpm: float
    key: str
    scenes: list[StoryboardScene]
    palette: list[str] = field(default_factory=list)
    seed: int = 0
    #: Delivery-target aspect ratio — one of the keys in
    #: :data:`melosviz.presets.aspect_ratios.DELIVERY_ASPECT_RATIOS`. Drives
    #: every scene's ``width`` / ``height`` / ``fps``.
    aspect_ratio: str = "youtube_1080"
    #: Subject/environment anchor threaded into every scene.
    continuity: ContinuityAnchor = field(default_factory=ContinuityAnchor)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "duration_s": self.duration_s,
            "bpm": self.bpm,
            "key": self.key,
            "palette": self.palette,
            "seed": self.seed,
            "aspect_ratio": self.aspect_ratio,
            "continuity": self.continuity.to_dict(),
            "scenes": [s.to_dict() for s in self.scenes],
        }


#: Aspect-ratio presets exposed by the CLI ``--aspect-ratio`` flag. Each
#: tuple is ``(label, width, height, fps)``. See
#: :mod:`melosviz.presets.aspect_ratios` for the full delivery-target
#: matrix and the human-readable descriptions used by ``melosviz apply``.
DEFAULT_ASPECT_RATIO = "youtube_1080"
_ASPECT_RATIOS: dict[str, tuple[str, int, int, int]] = {
    "festival_4k":      ("3840x2160 16:9 24fps — festival/VJ screen",     3840, 2160, 24),
    "youtube_1080":     ("1920x1080 16:9 24fps — YouTube / Vimeo",       1920, 1080, 24),
    "youtube_4k":       ("3840x2160 16:9 30fps — YouTube 4K",            3840, 2160, 30),
    "club_portrait":    ("1080x1920  9:16 30fps — club floor portrait",   1080, 1920, 30),
    "social_vertical":  ("1080x1920  9:16 30fps — IG Reels / TikTok",     1080, 1920, 30),
    "cinema_letterbox": ("2048x858  ~2.39:1 24fps — DCP letterbox",      2048,  858, 24),
    "square_social":    ("1080x1080  1:1 30fps — IG square / SoundCloud", 1080, 1080, 30),
}


def list_aspect_ratios() -> list[str]:
    """Return the keys of the built-in aspect-ratio preset table."""
    return sorted(_ASPECT_RATIOS.keys())


def resolve_aspect_ratio(name: str) -> tuple[str, int, int, int]:
    """Look up ``name`` and return ``(label, width, height, fps)``.

    Unknown names fall back to the default (``youtube_1080``).
    """
    return _ASPECT_RATIOS.get(name, _ASPECT_RATIOS[DEFAULT_ASPECT_RATIO])


@dataclass
class DirectorRequest:
    """Inputs to :meth:`Director.storyboard`."""
    concept: str
    duration_s: float
    bpm: float
    key: str = "C"
    segments: list[dict[str, Any]] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)
    seed: int | None = None
    #: Optional timed lyrics — list of :class:`LyricPhrase` from
    #: :mod:`melosviz.llm.lyrics`. When present, scene boundaries are
    #: snapped to lyric phrase onsets.
    lyrics: list[Any] = field(default_factory=list)
    #: Optional mood-board reference images (paths).
    mood_board: list[str] = field(default_factory=list)
    #: Delivery-target aspect ratio (festival_4k / youtube_1080 / …).
    #: See :func:`list_aspect_ratios`.
    aspect_ratio: str = DEFAULT_ASPECT_RATIO
    #: Optional explicit continuity anchor — pins the subject/environment
    #: across cuts. When omitted, :meth:`ContinuityAnchor.from_concept`
    #: derives a best-effort anchor from the concept.
    continuity: ContinuityAnchor | None = None
    # WBS-108: force audio-conditioned video routing even when no character
    # anchor is available (e.g. CLI flag ``--audio-conditioned-video``).
    audio_conditioned_video: bool = False


# ---------------------------------------------------------------------------
# Director
# ---------------------------------------------------------------------------


class Director:
    """Storyboards a track into a beat-synced scene plan."""

    def __init__(self, *, seed: int | None = None) -> None:
        self._seed = seed if seed is not None else int(time.time()) & 0xFFFFFFFF

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def storyboard(self, req: DirectorRequest) -> Storyboard:
        """Build a :class:`Storyboard` from a :class:`DirectorRequest`."""
        rng = random.Random(self._seed ^ _seed_from_str(req.concept))

        # 1. Mood-board palette/style (if reference images were supplied).
        if req.mood_board:
            mb = _mood_board(req.mood_board)
            mb_palette = mb.get("palette") or []
            mb_style = mb.get("style") or ""
            if mb_palette:
                req = DirectorRequest(
                    **{**req.__dict__, "palette": mb_palette[: len(req.palette) or 5] or req.palette}
                )

        base_palette = list(req.palette) if req.palette else [
            "#0d0d10", "#7c6af7", "#f472b6", "#22d3ee", "#c084fc", "#f0f0f8",
        ]
        palette = self._apply_concept_bias(req.concept, base_palette)

        segments = list(req.segments) or _synthetic_segments(req.duration_s, req.bpm)

        # 2. Snap to lyric phrase boundaries when lyrics are present.
        if req.lyrics:
            try:
                segments = _lyrics_align(req.lyrics, segments)
            except Exception as exc:
                logger.warning("Director: lyric alignment failed (%s) — using beat-only segments", exc)

        scenes: list[StoryboardScene] = []
        last_scene_type: str | None = None

        for i, seg in enumerate(segments):
            label = str(seg.get("label", "unknown"))
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start + 8.0))
            duration = max(0.1, end - start)

            arch = _ARCHETYPE_DEFAULTS.get(label, _ARCHETYPE_DEFAULTS["unknown"])
            scene_type = str(arch["scene_type"])
            # WBS-109: archetype-level audio-conditioned routing.
            # ``drop`` always routes to Wan S2V (any audio can drive motion);
            # ``chorus`` only routes to Seedance A2V when a character is
            # pinned (anchor has a subject_token) OR the user explicitly
            # requested audio-conditioned video via the CLI flag.
            audio_scene = arch.get("audio_video_scene_type")
            requires_char = bool(arch.get("audio_video_requires_character", False))
            if audio_scene is not None:
                if not requires_char:
                    scene_type = audio_scene
                else:
                    anchor_hint = req.continuity or ContinuityAnchor.from_concept(req.concept)
                    has_character = bool(anchor_hint.subject_token) if anchor_hint else False
                    if has_character or req.audio_conditioned_video:
                        scene_type = audio_scene
            # Anti-repeat
            if scene_type == last_scene_type and len(_ARCHETYPE_DEFAULTS) > 1:
                scene_type = _alternate_scene_type(scene_type, rng)
            last_scene_type = scene_type

            bar_count = max(1, round(duration * req.bpm / 60.0))
            beats_in_seg = [start + (b * 60.0 / max(1.0, req.bpm))
                            for b in range(bar_count + 1)]

            # Lyric overrides (when this scene was aligned to a phrase)
            lyric_text = str(seg.get("lyric_text", "")).strip()
            lyric_mood = str(seg.get("lyric_mood", ""))
            lyric_camera = str(seg.get("lyric_camera", ""))
            camera = lyric_camera or str(arch["camera"])

            prompt = self._compose_prompt(
                concept=req.concept,
                label=label,
                scene_type=scene_type,
                prompt_tail=str(arch["prompt_tail"]),
                key=req.key,
                seed=req.seed if req.seed is not None else self._seed,
                index=i,
                lyric_text=lyric_text,
                lyric_mood=lyric_mood,
                mood_board_style=mb_style if req.mood_board else "",
                continuity=req.continuity or ContinuityAnchor.from_concept(req.concept),
            )
            seed = (self._seed + i * 1009) & 0xFFFFFFFF

            notes_parts = [f"archetype={label}", f"bars={bar_count}"]
            if lyric_text:
                notes_parts.append(f"lyric={lyric_text[:80]}")
            if lyric_mood:
                notes_parts.append(f"mood={lyric_mood}")

            scenes.append(StoryboardScene(
                index=i,
                label=label,
                start=start,
                end=end,
                duration=duration,
                scene_type=scene_type,
                prompt=prompt,
                negative=_default_negative(scene_type),
                camera=camera,
                beats_in_segment=beats_in_seg,
                bar_count=bar_count,
                palette_override=palette,
                seed=seed,
                notes=", ".join(notes_parts),
            ))

        # Optional LLM refinement — never changes timing or tool choice.
        scenes = self._maybe_refine_with_llm(scenes, req)

        # Resolve the storyboard's aspect-ratio preset + continuity anchor.
        aspect_label, width, height, fps = resolve_aspect_ratio(req.aspect_ratio)
        anchor = req.continuity or ContinuityAnchor.from_concept(req.concept)
        for sc in scenes:
            sc.width = width
            sc.height = height
            sc.fps = fps
            if not sc.continuity.subject_token and not sc.continuity.env_token:
                sc.continuity = anchor
            # v2 (WBS-2): always thread the request's reference_image into
            # every scene's continuity so IP-Adapter / C4D / UE can see it,
            # even when subject/env tokens are set by other rules. A None
            # anchor.reference_image is a no-op (don't overwrite an
            # already-set scene reference).
            if anchor.reference_image is not None:
                sc.continuity.reference_image = anchor.reference_image

        return Storyboard(
            concept=req.concept,
            duration_s=req.duration_s,
            bpm=req.bpm,
            key=req.key,
            scenes=scenes,
            palette=palette,
            seed=self._seed,
            aspect_ratio=req.aspect_ratio,
            continuity=anchor,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply_concept_bias(self, concept: str, palette: list[str]) -> list[str]:
        bias = _match_bias(concept)
        if not bias:
            return palette
        # Cycle palette + bias-derived accent so each storyboard has a
        # unique mood without overwriting the user's palette.
        suffix = bias["palette_suffix"]
        accents = _accent_colors(suffix)
        return (palette + accents)[: max(6, len(palette))]

    def _compose_prompt(
        self, *, concept: str, label: str, scene_type: str,
        prompt_tail: str, key: str, seed: int, index: int,
        lyric_text: str = "", lyric_mood: str = "",
        mood_board_style: str = "",
        continuity: "ContinuityAnchor | None" = None,
    ) -> str:
        bias = _match_bias(concept)
        lighting = bias["lighting"] if bias else "cinematic"
        pieces = [
            concept.strip().rstrip(",.") or "music visual",
            f"scene {label}",
            f"lighting: {lighting}",
            f"key of {key}",
            prompt_tail,
        ]
        if mood_board_style:
            pieces.append(f"look: {mood_board_style}")
        if lyric_text:
            # Inline the lyric as the emotional seed for the prompt.
            pieces.append(f"depicts: \"{lyric_text[:120]}\"")
        if lyric_mood and lyric_mood != "neutral":
            pieces.append(f"mood: {lyric_mood}")
        if continuity is not None:
            if continuity.subject_token:
                pieces.append(f"subject: {continuity.subject_token[:120]}")
            if continuity.env_token:
                pieces.append(f"environment: {continuity.env_token[:120]}")
        if scene_type in ("comfyui_video", "unreal_cinematic"):
            pieces.append("smooth motion, no jitter")
        if scene_type == "comfyui_image":
            pieces.append("poster-quality composition, rule of thirds")
        if scene_type == "motion_graphics_beat_sync":
            pieces.append("bold type, geometric shapes, beat-driven timing")
        return ", ".join(p for p in pieces if p)

    def _maybe_refine_with_llm(
        self, scenes: list[StoryboardScene], req: DirectorRequest,
    ) -> list[StoryboardScene]:
        endpoint = os.environ.get(_LLM_ENDPOINT_ENV)
        if not endpoint:
            return scenes
        try:
            timeout = int(os.environ.get(_LLM_TIMEOUT_ENV, str(DEFAULT_LLM_TIMEOUT_S)))
        except ValueError:
            timeout = DEFAULT_LLM_TIMEOUT_S
        model = os.environ.get(_LLM_MODEL_ENV, DEFAULT_LLM_MODEL)
        api_key = os.environ.get(_LLM_KEY_ENV, "")

        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a music-video art director. Rewrite the "
                        "following scene prompts so they read as a single "
                        "cohesive visual story. Keep timing, scene_type, "
                        "camera, and palette EXACTLY. Return valid JSON: "
                        '{"rewrites": [{"index": int, "prompt": str}]}'
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "concept": req.concept,
                        "scenes": [
                            {"index": s.index, "label": s.label, "scene_type": s.scene_type,
                             "camera": s.camera, "prompt": s.prompt}
                            for s in scenes
                        ],
                    }),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }
        try:
            req_obj = urllib.request.Request(
                endpoint,
                method="POST",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
                },
            )
            with urllib.request.urlopen(req_obj, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            text = payload["choices"][0]["message"]["content"]
            rewrites = json.loads(text).get("rewrites") or []
            by_index = {int(r["index"]): str(r["prompt"]) for r in rewrites}
            for s in scenes:
                if s.index in by_index and by_index[s.index]:
                    s.prompt = by_index[s.index]
            logger.info("Director: LLM rewrote %d/%d scene prompts", len(by_index), len(scenes))
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
            logger.warning("Director: LLM refinement skipped (%s) — using template prompts.", exc)
        return scenes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_from_str(s: str) -> int:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


def _match_bias(concept: str) -> dict[str, str] | None:
    c = concept.lower()
    for kw, bias in _CONCEPT_KEYWORD_BIAS.items():
        if re.search(rf"\b{re.escape(kw)}\b", c):
            return bias
    return None


def _accent_colors(suffix: str) -> list[str]:
    table = {
        "magenta+cyan":      ["#ff2bd6", "#22d3ee"],
        "amber+teal":        ["#ffb347", "#1ec8c8"],
        "moss+sunbeam":      ["#4f7942", "#fff59d"],
        "aqua+indigo":       ["#56e1ff", "#3f37c9"],
        "ochre+sienna":      ["#d4a017", "#a0522d"],
        "violet+gold":       ["#7c3aed", "#ffd166"],
        "magenta+white":     ["#ff2bd6", "#ffffff"],
        "rose+cream":        ["#ff8fa3", "#fff1e6"],
        "steel+ash":         ["#708090", "#cfd8dc"],
        "fuchsia+lime":      ["#ff2bd6", "#b6ff5c"],
    }
    return table.get(suffix, ["#ffffff"])


def _default_negative(scene_type: str) -> str:
    base = "lowres, blurry, watermark, text artifacts, jpeg compression"
    if scene_type in ("comfyui_video", "unreal_cinematic"):
        base += ", flickering, jitter, motion blur glitches"
    return base


def _alternate_scene_type(current: str, rng: random.Random) -> str:
    pool = [s for s in DIRECTOR_SCENE_TYPES if s != current]
    return rng.choice(pool) if pool else current


def _synthetic_segments(duration_s: float, bpm: float) -> list[dict[str, Any]]:
    """Synthesize a coarse structure when MIR didn't return segments."""
    if duration_s <= 0 or bpm <= 0:
        return []
    bar_dur = 60.0 / bpm * 4.0  # 4/4
    n_bars = max(1, int(duration_s / bar_dur))
    # Coarse: intro (1 bar) + verses/chorus alternating + outro (1 bar)
    pattern = ["intro"] + (["verse", "chorus", "verse", "chorus", "bridge", "chorus"]
                          if n_bars > 24 else ["verse", "chorus", "verse"]) + ["outro"]
    segments: list[dict[str, Any]] = []
    t = 0.0
    bars_per_segment = max(2, n_bars // max(1, len(pattern)))
    for i, label in enumerate(pattern):
        start = t
        end = min(duration_s, start + bars_per_segment * bar_dur)
        segments.append({
            "index": i,
            "label": label,
            "start": start,
            "end": end,
            "energy_mean": 0.4 + 0.1 * i,
        })
        t = end
        if t >= duration_s:
            break
    if segments and segments[-1]["end"] < duration_s:
        # Extend last segment to cover the tail
        segments[-1]["end"] = duration_s
    return segments


# ---------------------------------------------------------------------------
# Multi-shot Director (3-pass planning: outline -> scenes -> shots)
# ---------------------------------------------------------------------------

@dataclass
class StoryOutline:
    """Top-level outline of a music video — act structure, emotional arc."""

    title: str
    concept: str
    acts: list[dict]            # [{name, start, end, intent}]
    emotional_arc: list[str]    # one word per scene index (joy / dread / ...)
    palette_arc: list[list[str]] # palette per scene
    total_scenes: int

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "concept": self.concept,
            "acts": list(self.acts),
            "emotional_arc": list(self.emotional_arc),
            "palette_arc": list(self.palette_arc),
            "total_scenes": self.total_scenes,
        }


@dataclass
class Shot:
    """One shot — the smallest unit of the director's plan."""

    scene_index: int
    shot_index: int             # 0-based within scene
    kind: str                    # wide | medium | closeup | insert | cutaway
    camera_motion: str
    subject_token: str | None
    duration_s: float
    prompt: str
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "scene_index": self.scene_index,
            "shot_index": self.shot_index,
            "kind": self.kind,
            "camera_motion": self.camera_motion,
            "subject_token": self.subject_token,
            "duration_s": self.duration_s,
            "prompt": self.prompt,
            "notes": self.notes,
        }


class MultiShotDirector:
    """3-pass planning: outline (acts + arc) -> scenes (1st Director pass) -> shots (2nd pass per scene).

    Pass 1 — Outline:
        Decide act structure (intro / build / drop / outro), the emotional arc
        (joy->dread->joy), and a per-scene palette arc (cold->warm->hot).
    Pass 2 — Scenes:
        Run the existing single-pass Director.storyboard() to materialize
        scenes with prompts, cameras, and scene_type routing.
    Pass 3 — Shots:
        Break each scene into 2-4 shots of varying kind (wide/medium/closeup)
        + camera motion, so the resulting video has the beat-synced variety
        of a real festival cut.

    Falls back gracefully when no LLM is configured: each pass uses a
    deterministic rule, producing the same structure every time.
    """

    def __init__(self, *, seed: int | None = None, shots_per_scene: int = 3) -> None:
        self._base = Director(seed=seed)
        self._seed = self._base._seed
        self._shots_per_scene = max(2, min(5, shots_per_scene))

    # ------------------------------------------------------------------
    # Pass 1 — outline
    # ------------------------------------------------------------------

    def plan_outline(self, req: DirectorRequest) -> StoryOutline:
        """First pass: decide the macro arc before generating scenes."""
        # 4-act template (intro / build / peak / outro). Boundaries land on
        # phrase onsets when lyrics are present, else on the structure markers.
        acts = []
        total = float(req.duration_s or 180.0)
        boundaries = [0.0, total * 0.15, total * 0.55, total * 0.85, total]
        act_names = ["intro", "build", "peak", "outro"]
        for i, name in enumerate(act_names):
            acts.append({
                "name": name,
                "start": round(boundaries[i], 2),
                "end": round(boundaries[i + 1], 2),
                "intent": _ACT_INTENT[name],
            })

        # Emotional arc: cool -> warm -> hot -> cool (cinematic classic).
        arc_names = [
            "wonder", "longing", "tension", "joy", "ecstasy",
            "release", "triumph", "awe", "stillness", "memory",
        ]
        rng = random.Random(self._seed ^ _seed_from_str(req.concept))
        n_arc = max(4, sum(1 for _ in req.segments) or 6)
        arc = [rng.choice(arc_names) for _ in range(n_arc)]
        # Force the climax to land on the peak act.
        peak_idx = next(i for i, a in enumerate(acts) if a["name"] == "peak")
        peak_scene = max(0, min(n_arc - 1, int(n_arc * (peak_idx + 1) / len(acts))))
        arc[peak_scene] = "ecstasy"

        # Palette arc: cold -> warm -> monochrome (per-act base color).
        palette_arc = []
        palette = list(req.palette) if req.palette else [
            "#0d0d10", "#7c6af7", "#f472b6", "#22d3ee", "#c084fc", "#f0f0f8",
        ]
        for i in range(n_arc):
            base = palette[i % len(palette)]
            palette_arc.append([base, palette[(i + 2) % len(palette)]])

        return StoryOutline(
            title=req.concept[:60] or "untitled music video",
            concept=req.concept,
            acts=acts,
            emotional_arc=arc,
            palette_arc=palette_arc,
            total_scenes=n_arc,
        )

    # ------------------------------------------------------------------
    # Pass 2 — scenes (delegate to the single-pass Director)
    # ------------------------------------------------------------------

    def plan_scenes(self, req: DirectorRequest, outline: StoryOutline | None = None) -> Storyboard:
        """Materialize the scenes (Pass 2). Returns a Storyboard."""
        outline = outline or self.plan_outline(req)
        sb = self._base.storyboard(req)
        # Annotate each scene with the outline's emotional_arc + palette_arc.
        for i, scene in enumerate(sb.scenes):
            if i < len(outline.emotional_arc):
                scene.notes = (scene.notes or "") + f"|mood={outline.emotional_arc[i]}"
            if i < len(outline.palette_arc):
                scene.palette = outline.palette_arc[i]
        sb.outline = outline.to_dict()
        return sb

    # ------------------------------------------------------------------
    # Pass 3 — shots (break each scene into 2-4 shots)
    # ------------------------------------------------------------------

    def plan_shots(self, sb: Storyboard) -> list[Shot]:
        """Third pass: break each scene into N shots of varied kind + camera."""
        shots: list[Shot] = []
        rng = random.Random(self._seed ^ 0x5EED)
        shot_kinds = ["wide", "medium", "closeup", "insert", "cutaway"]
        camera_motions = [
            "slow_dolly_in", "slow_pull_back", "whip_pan_burst",
            "handheld_drift", "static_locked_off", "orbit_half",
        ]
        for i, scene in enumerate(sb.scenes):
            subject = (
                scene.continuity.subject_token
                if getattr(scene, "continuity", None) is not None
                else None
            )
            # Per-scene shot breakdown: alternate wide / medium / closeup.
            chosen_kinds = ["wide", "medium"]
            for j in range(self._shots_per_scene - 2):
                chosen_kinds.append(rng.choice(shot_kinds))
            chosen_kinds = chosen_kinds[: self._shots_per_scene]
            per_shot = max(scene.duration / self._shots_per_scene, 1.5)
            for k, kind in enumerate(chosen_kinds):
                camera = scene.camera if k == 0 else rng.choice(camera_motions)
                shot_prompt = scene.prompt + f" ({kind} framing, {camera} motion)"
                shots.append(Shot(
                    scene_index=i,
                    shot_index=k,
                    kind=kind,
                    camera_motion=camera,
                    subject_token=subject,
                    duration_s=round(per_shot, 2),
                    prompt=shot_prompt,
                    notes=f"act={scene.label}",
                ))
        return shots

    # ------------------------------------------------------------------
    # Full 3-pass entry point
    # ------------------------------------------------------------------

    def plan_three_pass(self, req: DirectorRequest) -> dict:
        """Run all three passes and return (outline, storyboard, shots)."""
        outline = self.plan_outline(req)
        sb = self.plan_scenes(req, outline)
        shots = self.plan_shots(sb)
        return {
            "outline": outline.to_dict(),
            "storyboard": sb,
            "shots": [s.to_dict() for s in shots],
        }


_ACT_INTENT = {
    "intro": "establish the world and introduce the protagonist",
    "build": "develop tension, show the journey, layer the motifs",
    "peak": "climax, visual maximum, the story's central action",
    "outro": "release and resolve, hand the story back to the viewer",
}
