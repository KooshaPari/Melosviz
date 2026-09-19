"""Windows regression: storyboard reads must not rely on the locale codec.

A ``storyboard.json`` legitimately carries non-ASCII text: accented scene
names, an em dash in a mood label, an emoji in a prompt.  Reading it with
``Path.read_text()`` and no explicit encoding uses the platform default,
which on Windows is ``cp1252`` — that either raises ``UnicodeDecodeError``
or silently mangles the payload before it reaches the Director.

The test asserts an exact round-trip, so it fails on either symptom and
passes only when the reader pins UTF-8.
"""

from __future__ import annotations

import json
from pathlib import Path

from melosviz.compose.beat_cuts import load_storyboard_for_plan

NON_ASCII = "Sc\u00e8ne \u00ab R\u00eave \u2014 caf\u00e9 \U0001f3ac"


def test_load_storyboard_for_plan_roundtrips_non_ascii(tmp_path: Path) -> None:
    payload = {"scenes": [{"index": 0, "label": NON_ASCII, "prompt": NON_ASCII}]}
    storyboard = tmp_path / "storyboard.json"
    # This is how a storyboard exists on disk in practice: UTF-8 JSON.
    storyboard.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = load_storyboard_for_plan(storyboard)

    assert loaded["scenes"][0]["label"] == NON_ASCII
    assert loaded["scenes"][0]["prompt"] == NON_ASCII
