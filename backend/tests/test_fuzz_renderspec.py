"""Property / fuzz-style RenderSpec JSON roundtrips (C07 L67 seed + C08)."""

from __future__ import annotations

import json

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st

from melosviz.analysis.models import RenderSpec


@given(
    duration=st.floats(min_value=0.1, max_value=600, allow_nan=False, allow_infinity=False),
    fps=st.integers(min_value=1, max_value=120),
    bpm=st.floats(min_value=40.0, max_value=240.0, allow_nan=False, allow_infinity=False),
    palette=st.lists(
        st.from_regex(r"#[0-9a-fA-F]{6}", fullmatch=True),
        min_size=0,
        max_size=8,
    ),
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
