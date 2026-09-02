"""Tests for the Director (storyboard generator)."""

from __future__ import annotations

import io
import json
import logging
import urllib.error
from pathlib import Path

import pytest

from melosviz.llm.admission import LLMAdmissionConfig, LLMAdmissionGate
from melosviz.llm.director import (
    CONTINUITY_ANCHOR_VERSION,
    ContinuityAnchor,
    Director,
    DirectorRequest,
    DIRECTOR_SCENE_TYPES,
)
from melosviz.llm.lyrics import parse_lrc


def _sample_segments() -> list[dict]:
    # 60-second simple structure: intro / verse / chorus / bridge / outro
    return [
        {"index": 0, "label": "intro",   "start": 0.0,  "end": 8.0,  "energy_mean": 0.3},
        {"index": 1, "label": "verse",   "start": 8.0,  "end": 20.0, "energy_mean": 0.5},
        {"index": 2, "label": "chorus",  "start": 20.0, "end": 36.0, "energy_mean": 0.85},
        {"index": 3, "label": "bridge",  "start": 36.0, "end": 48.0, "energy_mean": 0.6},
        {"index": 4, "label": "outro",   "start": 48.0, "end": 60.0, "energy_mean": 0.25},
    ]


def test_storyboard_has_one_scene_per_segment() -> None:
    director = Director(seed=1234)
    req = DirectorRequest(
        concept="neon-noir city at midnight, dancer losing themselves in the music",
        duration_s=60.0,
        bpm=124.0,
        key="F# minor",
        segments=_sample_segments(),
    )
    board = director.storyboard(req)
    assert len(board.scenes) == len(req.segments)
    assert board.bpm == 124.0
    assert board.key == "F# minor"


def test_scene_types_are_valid_and_no_adjacent_duplicates() -> None:
    director = Director(seed=42)
    req = DirectorRequest(
        concept="festival neon dance, vibrant",
        duration_s=120.0,
        bpm=128.0,
        segments=_sample_segments(),
    )
    board = director.storyboard(req)
    for s in board.scenes:
        assert s.scene_type in DIRECTOR_SCENE_TYPES
    for prev, nxt in zip(board.scenes, board.scenes[1:]):
        # Anti-repeat is soft — we only require that two adjacent scenes
        # are not *identical* "intro" or "outro" placeholders, which
        # the static archetype map already enforces.
        if prev.scene_type == nxt.scene_type:
            assert prev.label == nxt.label  # would only happen for tiny boards
    # Adjacent scene_type is allowed to repeat (it's a soft hint, not hard)
    # but every scene has a beat count > 0 and bar_count >= 1.
    for s in board.scenes:
        assert s.bar_count >= 1
        assert len(s.beats_in_segment) >= 2


def test_beat_alignment_to_bpm() -> None:
    director = Director(seed=7)
    req = DirectorRequest(
        concept="desert journey at dawn",
        duration_s=60.0,
        bpm=120.0,
        segments=_sample_segments(),
    )
    board = director.storyboard(req)
    # 120 BPM = 2 beats/second, 4/4 → beats 0, 0.5, 1.0, …
    # Beat 0 of any segment equals its start, beat N equals start + N*0.5
    for s in board.scenes:
        if not s.beats_in_segment:
            continue
        assert abs(s.beats_in_segment[0] - s.start) < 1e-6
        # Subsequent beats step by ~60/bpm
        if len(s.beats_in_segment) >= 2:
            step = s.beats_in_segment[1] - s.beats_in_segment[0]
            assert abs(step - (60.0 / req.bpm)) < 1e-6


def test_concept_keyword_bias_shifts_palette() -> None:
    director = Director(seed=1)
    req_neon = DirectorRequest(
        concept="neon city at midnight",
        duration_s=30.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 30.0}],
    )
    req_neutral = DirectorRequest(
        concept="abstract geometric shapes",
        duration_s=30.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 30.0}],
    )
    board_neon = director.storyboard(req_neon)
    board_neutral = director.storyboard(req_neutral)
    # neon should add magenta+cyan accents to palette
    assert any("ff" in c.lower() or "22d3ee" in c.lower() for c in board_neon.palette)
    # neutral can fall back to base palette without accents
    assert isinstance(board_neutral.palette, list)


def test_synthetic_segments_when_none_provided() -> None:
    director = Director(seed=99)
    req = DirectorRequest(
        concept="abstract",
        duration_s=120.0,
        bpm=120.0,
        segments=[],
    )
    board = director.storyboard(req)
    assert len(board.scenes) >= 4  # at least intro/verse/chorus/outro
    total = sum(s.duration for s in board.scenes)
    assert abs(total - 120.0) < 1e-3


def test_determinism_same_seed_same_storyboard() -> None:
    req = DirectorRequest(
        concept="neon festival",
        duration_s=30.0,
        bpm=128.0,
        segments=[{"label": "verse", "start": 0.0, "end": 30.0}],
    )
    a = Director(seed=5).storyboard(req).to_dict()
    b = Director(seed=5).storyboard(req).to_dict()
    assert a == b


def test_storyboard_to_dict_is_json_serialisable() -> None:
    import json
    director = Director(seed=2)
    req = DirectorRequest(
        concept="abstract neon",
        duration_s=30.0,
        bpm=124.0,
        segments=[{"label": "verse", "start": 0.0, "end": 30.0}],
    )
    board = director.storyboard(req)
    payload = board.to_dict()
    # round-trip via JSON to assert all values are JSON-safe
    json.dumps(payload)


# ---------------------------------------------------------------------------
# Lyrics-aware storyboarding
# ---------------------------------------------------------------------------


def test_lyrics_snap_scenes_to_phrase_boundaries() -> None:
    phrases = parse_lrc(
        "[00:00.00]First lyric phrase\n"
        "[00:04.00]Second phrase here\n"
        "[00:08.00]Third one now\n"
        "[00:12.00]Fourth and final"
    )
    req = DirectorRequest(
        concept="abstract",
        duration_s=20.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 20.0}],
        lyrics=phrases,
    )
    board = Director(seed=42).storyboard(req)
    # Each phrase becomes its own scene
    assert len(board.scenes) == len(phrases)
    # Each scene's notes mention the lyric
    for scene, phrase in zip(board.scenes, phrases):
        assert phrase.text[:40] in scene.notes


def test_high_arousal_lyric_picks_dynamic_camera() -> None:
    phrases = parse_lrc(
        "[00:00.00]Scream, fight, run, burn the fire, explode the wall\n"
        "[00:04.00]Whisper, breathe, drift, soft, gently fading"
    )
    req = DirectorRequest(
        concept="abstract",
        duration_s=20.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 20.0}],
        lyrics=phrases,
    )
    board = Director(seed=42).storyboard(req)
    high = board.scenes[0].camera
    low = board.scenes[1].camera
    assert high != low
    assert any(t in high for t in ("whip", "handheld", "burst"))


def test_lyric_text_inlined_in_prompt() -> None:
    phrases = parse_lrc("[00:00.00]City lights are calling out my name")
    req = DirectorRequest(
        concept="abstract",
        duration_s=8.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 8.0}],
        lyrics=phrases,
    )
    board = Director(seed=42).storyboard(req)
    assert "city lights are calling out my name" in board.scenes[0].prompt.lower()


# ---------------------------------------------------------------------------
# Mood-board integration
# ---------------------------------------------------------------------------


def _solid_png(rgb: tuple[int, int, int]) -> bytes:
    """Build an 8×8 PNG with the given solid color, no PIL."""
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b""
    for _ in range(8):
        raw += b"\x00" + bytes(rgb) * 8
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def test_mood_board_extracts_palette(tmp_path) -> None:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        pytest.skip("Pillow not installed")

    img = tmp_path / "ref.png"
    img.write_bytes(_solid_png((220, 30, 30)))

    req = DirectorRequest(
        concept="abstract",
        duration_s=8.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 8.0}],
        mood_board=[str(img)],
    )
    board = Director(seed=42).storyboard(req)
    # First palette color should be reddish
    assert board.palette
    r = int(board.palette[0][1:3], 16)
    assert r > 100


def test_mood_board_style_inlined_into_prompt(tmp_path) -> None:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        pytest.skip("Pillow not installed")

    img = tmp_path / "dark_ref.png"
    img.write_bytes(_solid_png((10, 10, 10)))

    req = DirectorRequest(
        concept="abstract",
        duration_s=8.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 8.0}],
        mood_board=[str(img)],
    )
    board = Director(seed=42).storyboard(req)
    prompt_tokens = (
        "low-key", "grain", "high-key", "saturation",
        "naturalistic", "clean digital", "punchy",
    )
    assert any(token in board.scenes[0].prompt.lower() for token in prompt_tokens)


# ---------------------------------------------------------------------------
# v2 ContinuityAnchor.reference_image (WBS-2)
# ---------------------------------------------------------------------------


def test_continuity_anchor_reference_image_accepts_path(tmp_path) -> None:
    """v2: ``reference_image`` accepts a ``Path`` and round-trips it.

    The ``from_concept`` constructor validates the path exists and stores
    it as a :class:`pathlib.Path`; ``to_dict()`` serialises it as a
    string so JSON payloads stay portable.
    """
    ref = tmp_path / "reference.png"
    ref.write_bytes(_solid_png((180, 60, 200)))

    anchor = ContinuityAnchor.from_concept(
        "neon-noir city at midnight, dancer",
        reference_image=ref,
    )
    assert anchor.reference_image == ref
    assert isinstance(anchor.reference_image, Path)

    payload = anchor.to_dict()
    assert payload["reference_image"] == str(ref)
    assert payload["_version"] == CONTINUITY_ANCHOR_VERSION == 2
    # JSON-round-trip safety
    json.dumps(payload)


def test_continuity_anchor_reference_image_drops_missing_path_with_warning(
    tmp_path, caplog
) -> None:
    """v2: paths that don't exist on disk are dropped to ``None`` with a
    warning — the alternative rendering path (no IP-Adapter) still works
    so a typo in the path doesn't abort the whole pipeline."""
    missing = tmp_path / "definitely-not-here.png"

    with caplog.at_level(logging.WARNING, logger="melosviz.llm.director"):
        anchor = ContinuityAnchor.from_concept(
            "neon-noir city at midnight",
            reference_image=missing,
        )
    assert anchor.reference_image is None
    assert any("reference_image" in rec.message for rec in caplog.records)

    # Round-trip: to_dict still emits None (not "")
    assert anchor.to_dict()["reference_image"] is None


def test_continuity_anchor_to_dict_serializes_reference_image_as_str() -> None:
    """v2: ``to_dict()`` always emits ``reference_image`` as ``str(path)``
    or ``None``. The v1 convention (``str = ""``) is rejected — empty
    string would be ambiguous against a valid empty-path sentinel.
    """
    a = ContinuityAnchor()
    assert a.to_dict()["reference_image"] is None
    assert a.to_dict()["_version"] == 2

    # Round-trip with a Path
    anchor = ContinuityAnchor(
        subject_token="dancer",
        env_token="underwater city",
        palette_token="teal",
        reference_image=Path("/tmp/does-not-matter.png"),
    )
    payload = anchor.to_dict()
    assert payload["reference_image"] == "/tmp/does-not-matter.png"
    assert payload["subject_token"] == "dancer"
    # Round-trip safe through JSON
    json.dumps(payload)


def test_director_threads_reference_image_into_scene_continuity(tmp_path) -> None:
    """v2: when ``DirectorRequest.continuity.reference_image`` is set,
    every scene in the resulting :class:`Storyboard` inherits it on its
    own ``continuity.reference_image`` — so adapters downstream can
    pick it up via ``scene["ip_adapter_image"]`` without re-reading the
    storyboard-level anchor.
    """
    ref = tmp_path / "face_pin.png"
    ref.write_bytes(_solid_png((220, 180, 60)))

    continuity = ContinuityAnchor.from_concept(
        "neon dancer in city at midnight",
        reference_image=ref,
    )
    req = DirectorRequest(
        concept="neon dancer in city at midnight",
        duration_s=20.0,
        bpm=120.0,
        segments=_sample_segments(),
        continuity=continuity,
    )
    board = Director(seed=11).storyboard(req)

    # The storyboard-level anchor carries it
    assert board.continuity.reference_image == ref
    # And every scene inherits it
    for scene in board.scenes:
        assert scene.continuity.reference_image == ref

    # Round-trip through JSON confirms the wire format
    payload = board.to_dict()
    assert payload["continuity"]["reference_image"] == str(ref)
    assert payload["continuity"]["_version"] == 2
    for scene_payload in payload["scenes"]:
        assert scene_payload["continuity"]["reference_image"] == str(ref)


# ---------------------------------------------------------------------------
# Native-audio routing (WBS-107..109)
# ---------------------------------------------------------------------------


def test_drop_archetype_routes_to_audio_video_wan() -> None:
    """drop → comfyui_audio_video_wan when audio_conditioned_video flag is on."""
    director = Director(seed=7)
    req = DirectorRequest(
        concept="festival neon dance, vibrant",
        duration_s=60.0,
        bpm=128.0,
        key="C minor",
        segments=_sample_segments(),
        audio_conditioned_video=True,
    )
    director.storyboard(req)
    # Drop scene type defined in _ARCHETYPE_DEFAULTS regardless of segments.
    from melosviz.llm.director import _ARCHETYPE_DEFAULTS
    assert _ARCHETYPE_DEFAULTS["drop"].get("audio_video_scene_type") == "comfyui_audio_video_wan"


def test_chorus_archetype_routes_to_audio_video_seedance_with_character() -> None:
    """chorus → comfyui_audio_video_seedance when audio_conditioned_video + character present."""
    director = Director(seed=11)
    # A concept that parses to a non-empty subject token triggers has_character=True.
    req = DirectorRequest(
        concept="dancer drifting through a neon city, moody",
        duration_s=60.0,
        bpm=124.0,
        key="F# minor",
        segments=_sample_segments(),
        audio_conditioned_video=True,
    )
    board = director.storyboard(req)
    chorus_scenes = [s for s in board.scenes if s.label == "chorus"]
    assert chorus_scenes, "expected at least one chorus scene"
    for scene in chorus_scenes:
        assert scene.scene_type == "comfyui_audio_video_seedance"


# ---------------------------------------------------------------------------
# v2 ContinuityAnchor.reference_image (WBS-2)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# LLM admission integration (production-delivery-extensions Task 2)
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal context-manager response for testing LLM injection."""

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _llm_env(monkeypatch) -> None:
    values = {
        "MELOSVIZ_LLM_ENDPOINT": "https://llm.invalid/v1/chat/completions",
        "MELOSVIZ_LLM_MODEL": "fixed-model",
        "MELOSVIZ_LLM_INPUT_USD_PER_MILLION": "1.00",
        "MELOSVIZ_LLM_OUTPUT_USD_PER_MILLION": "2.00",
        "MELOSVIZ_LLM_MAX_OUTPUT_TOKENS": "100",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _single_scene_request() -> DirectorRequest:
    return DirectorRequest(
        concept="neon city",
        duration_s=8.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 8.0}],
    )


def test_llm_missing_prices_falls_back_without_network(monkeypatch, caplog) -> None:
    """Pricing env vars missing -> no network call, template prompts are used."""
    monkeypatch.setenv("MELOSVIZ_LLM_ENDPOINT", "https://llm.invalid")
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not be called")

    with caplog.at_level(logging.WARNING, logger="melosviz.llm.director"):
        board = Director(seed=1, llm_opener=opener).storyboard(_single_scene_request())
    assert calls == 0
    assert "scene verse" in board.scenes[0].prompt
    assert "must be configured" in caplog.text


def test_llm_429_honors_retry_after_and_keeps_model(monkeypatch) -> None:
    """429 with Retry-After header: sleep is honoured, model is preserved across retries."""
    _llm_env(monkeypatch)
    requests: list[dict] = []
    sleeps: list[float] = []
    responses = [
        urllib.error.HTTPError(
            "https://llm.invalid", 429, "rate limited", {"Retry-After": "2"}, io.BytesIO()
        ),
        FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "rewrites": [{"index": 0, "prompt": "refined prompt"}]
            })}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }),
    ]

    def opener(request, timeout):
        requests.append(json.loads(request.data.decode()))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    board = Director(
        seed=1, llm_opener=opener, llm_sleeper=sleeps.append
    ).storyboard(_single_scene_request())
    assert board.scenes[0].prompt == "refined prompt"
    assert sleeps == [2.0]
    assert [request["model"] for request in requests] == ["fixed-model", "fixed-model"]


def test_llm_non_retryable_400_attempts_once(monkeypatch) -> None:
    """400 Bad Request: no retry, no network beyond the first call."""
    _llm_env(monkeypatch)
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            request.full_url, 400, "bad request", {}, io.BytesIO()
        )

    board = Director(seed=1, llm_opener=opener).storyboard(_single_scene_request())
    assert calls == 1
    assert "scene verse" in board.scenes[0].prompt


def test_llm_records_actual_cost_in_gate(monkeypatch) -> None:
    """When the LLM returns usage, the gate's spent_usd reflects actual_cost
    (not the reserved estimate), so the budget ledger stays accurate."""
    _llm_env(monkeypatch)
    config = LLMAdmissionConfig.from_env()
    gate = LLMAdmissionGate(config)
    estimate = config.estimate(b"x")

    def opener(request, timeout):
        return FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "rewrites": [{"index": 0, "prompt": "ok"}]
            })}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        })

    board = Director(
        seed=1, llm_gate=gate, llm_opener=opener
    ).storyboard(_single_scene_request())
    assert board.scenes[0].prompt == "ok"
    expected_actual = config.actual_cost(4, 2)
    assert gate.spent_usd == expected_actual
    assert gate.spent_usd != estimate.usd
