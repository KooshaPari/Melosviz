"""Property / fuzz-style RenderSpec JSON roundtrips (C07 L66/L67 + C08).

Structured Hypothesis coverage for keyframes, scene segments, camera poses,
and palette/color fields — enough property depth for C07 L66 without a slow
fuzz farm (modest ``max_examples``, ``deadline=None``).
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from melosviz.analysis.models import RenderSpec

pytest.importorskip("hypothesis")

# ---- shared strategies (keep leaf sizes small for CI speed) ---------------

_finite = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
)
_unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_hex_color = st.from_regex(r"#[0-9a-fA-F]{6}", fullmatch=True)
_easing = st.sampled_from(["linear", "ease_in", "ease_out", "ease_in_out"])
_scene_label = st.sampled_from(
    ["intro", "verse", "chorus", "drop", "bridge", "breakdown", "outro", "unknown"]
)
_camera_language = st.sampled_from(
    ["steady_cam", "slow_push", "orbit_drift", "cut_frenzy"]
)


@st.composite
def sparse_keyframes(draw: st.DrawFn) -> list[dict[str, object]]:
    """v1-style sparse keyframes (t + optional color/energy)."""
    n = draw(st.integers(min_value=0, max_value=6))
    out: list[dict[str, object]] = []
    for _i in range(n):
        kf: dict[str, object] = {
            "t": draw(
                st.floats(
                    min_value=0.0,
                    max_value=600.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            ),
            "energy": draw(_unit),
        }
        if draw(st.booleans()):
            kf["color"] = draw(_hex_color)
        if draw(st.booleans()):
            kf["easing"] = draw(_easing)
        out.append(kf)
    return out


@st.composite
def dense_keyframes(draw: st.DrawFn) -> list[dict[str, object]]:
    """v2 dense keyframes with stems (capped length)."""
    n = draw(st.integers(min_value=0, max_value=8))
    out: list[dict[str, object]] = []
    for i in range(n):
        out.append(
            {
                "t": float(i) * 0.033,
                "energy": draw(_unit),
                "brightness": draw(_unit),
                "valence": draw(_unit),
                "arousal": draw(_unit),
                "beat_strength": draw(_unit),
                "onset_strength": draw(_unit),
                "spectral_centroid": draw(
                    st.floats(
                        min_value=0.0,
                        max_value=20_000.0,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                ),
                "stems": {
                    "drums": draw(_unit),
                    "bass": draw(_unit),
                    "vocals": draw(_unit),
                    "other": draw(_unit),
                },
                "easing": draw(_easing),
            }
        )
    return out


@st.composite
def scene_segments(draw: st.DrawFn) -> list[dict[str, object]]:
    n = draw(st.integers(min_value=0, max_value=5))
    segs: list[dict[str, object]] = []
    t = 0.0
    for i in range(n):
        dur = draw(
            st.floats(
                min_value=0.1, max_value=32.0, allow_nan=False, allow_infinity=False
            )
        )
        end = t + dur
        segs.append(
            {
                "index": i,
                "label": draw(_scene_label),
                "start": t,
                "end": end,
                "energy_mean": draw(_unit),
                "brightness_mean": draw(_unit),
                "mood": {"valence": draw(_unit), "arousal": draw(_unit)},
                "dominant_stem": draw(
                    st.sampled_from(["drums", "bass", "vocals", "other"])
                ),
                "camera_language": draw(_camera_language),
            }
        )
        t = end
    return segs


@st.composite
def camera_path(draw: st.DrawFn) -> list[dict[str, object]]:
    """Procedural camera pose keyframes (scene.camera shape)."""
    n = draw(st.integers(min_value=0, max_value=6))
    path: list[dict[str, object]] = []
    for i in range(n):
        path.append(
            {
                "t": float(i) * 0.5,
                "position": [
                    draw(_finite),
                    draw(_finite),
                    draw(_finite),
                ],
                "look_at": [
                    draw(_finite),
                    draw(_finite),
                    draw(_finite),
                ],
                "fov_deg": draw(
                    st.floats(
                        min_value=10.0,
                        max_value=120.0,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                ),
                "roll_deg": draw(
                    st.floats(
                        min_value=-45.0,
                        max_value=45.0,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                ),
                "camera_language": draw(_camera_language),
            }
        )
    return path


@given(
    duration=st.floats(
        min_value=0.1, max_value=600, allow_nan=False, allow_infinity=False
    ),
    fps=st.integers(min_value=1, max_value=120),
    bpm=st.floats(
        min_value=40.0, max_value=240.0, allow_nan=False, allow_infinity=False
    ),
    palette=st.lists(_hex_color, min_size=0, max_size=8),
)
@settings(max_examples=40, deadline=None)
def test_fuzz_renderspec_json_roundtrip(
    duration: float, fps: int, bpm: float, palette: list[str]
) -> None:
    spec = RenderSpec(
        metadata={"duration": duration, "fps": fps, "bpm": bpm},
        palette=palette,
    )
    raw = spec.model_dump_json()
    data = json.loads(raw)
    again = RenderSpec.model_validate(data)
    assert again.metadata["duration"] == pytest.approx(duration)
    assert again.metadata["fps"] == fps
    assert list(again.palette) == list(palette)


@given(
    keyframes=sparse_keyframes(),
    dense=dense_keyframes(),
    scenes=scene_segments(),
    camera=camera_path(),
    palette=st.lists(_hex_color, min_size=0, max_size=6),
    bg=st.one_of(_hex_color, st.none()),
)
@settings(max_examples=50, deadline=None)
def test_fuzz_renderspec_keyframes_scenes_camera_color_roundtrip(
    keyframes: list[dict[str, object]],
    dense: list[dict[str, object]],
    scenes: list[dict[str, object]],
    camera: list[dict[str, object]],
    palette: list[str],
    bg: str | None,
) -> None:
    """Property coverage across keyframes, scenes, camera, and color fields."""
    metadata: dict[str, object] = {
        "duration": 12.0,
        "fps": 30,
        "width": 1280,
        "height": 720,
    }
    if bg is not None:
        metadata["background_color"] = bg

    layers: list[object] = []
    if camera:
        layers.append({"type": "camera", "path": camera})

    spec = RenderSpec(
        metadata=metadata,
        palette=palette,
        keyframes=keyframes,
        dense_keyframes=dense,
        scene_segments=scenes,
        layers=layers,
        timeline=[{"type": "camera_marker", "t": 0.0}] if camera else [],
    )
    encoded = spec.model_dump_json()
    again = RenderSpec.model_validate_json(encoded)
    dumped = again.model_dump()

    assert dumped["palette"] == palette
    assert dumped["keyframes"] == keyframes
    assert dumped["dense_keyframes"] == dense
    assert dumped["scene_segments"] == scenes
    assert dumped["layers"] == layers
    if bg is not None:
        assert again.metadata.get("background_color") == bg


@given(
    payload=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        _finite,
        st.text(max_size=32),
        st.lists(st.integers(), max_size=4),
        st.dictionaries(
            st.sampled_from(
                [
                    "metadata",
                    "palette",
                    "keyframes",
                    "dense_keyframes",
                    "scene_segments",
                    "layers",
                    "timeline",
                    "camera",
                    "color",
                ]
            ),
            st.one_of(
                st.none(),
                st.lists(_hex_color, max_size=3),
                st.lists(
                    st.dictionaries(
                        st.sampled_from(["t", "energy", "color", "label"]),
                        st.one_of(_unit, _hex_color, st.text(max_size=12)),
                        max_size=4,
                    ),
                    max_size=3,
                ),
            ),
            max_size=6,
        ),
    )
)
@settings(max_examples=40, deadline=None)
def test_fuzz_renderspec_malformed_payload_stable(payload: object) -> None:
    """Malformed JSON either validates into typed lists/dicts or raises cleanly."""
    from pydantic import ValidationError

    raw = json.dumps(payload)
    try:
        spec = RenderSpec.model_validate_json(raw)
    except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
        return

    dumped = spec.model_dump()
    assert isinstance(dumped["metadata"], dict)
    assert isinstance(dumped["palette"], list)
    assert isinstance(dumped["keyframes"], list)
    assert isinstance(dumped["dense_keyframes"], list)
    assert isinstance(dumped["scene_segments"], list)
