"""Golden RenderSpec corpus (C08 L71/L77).

Deterministic synthetic WAVs → normalized RenderSpec JSON under
``eval/golden/expected/``. Set ``UPDATE_GOLDEN=1`` to regenerate fixtures.

Cases cover pure tones plus multi-genre *character* synthetics (kick pulse,
chord stack, noise burst) — copyright-free stand-ins for real-track diversity.
"""

from __future__ import annotations

import json
import math
import os
import random
import struct
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "eval" / "golden"
EXPECTED_DIR = GOLDEN_DIR / "expected"
WAV_DIR = GOLDEN_DIR / "wav"

SampleGen = Callable[[int, int], list[int]]


def _tone(freq_hz: float) -> SampleGen:
    def gen(n: int, sample_rate: int) -> list[int]:
        if freq_hz <= 0:
            return [0] * n
        return [
            int(32767 * 0.8 * math.sin(2 * math.pi * freq_hz * i / sample_rate))
            for i in range(n)
        ]

    return gen


def _kick_pattern() -> SampleGen:
    """Electronic/EDM-like: 2 Hz low sine pulses with exponential decay."""

    def gen(n: int, sample_rate: int) -> list[int]:
        out = [0] * n
        pulse_hz = 2.0
        pulse_len = int(0.08 * sample_rate)
        for i in range(n):
            phase = (i / sample_rate) * pulse_hz
            if (phase % 1.0) < (pulse_len / sample_rate) * pulse_hz:
                local = int((phase % 1.0) * sample_rate / pulse_hz)
                env = math.exp(-local / (0.03 * sample_rate))
                out[i] = int(
                    32767
                    * 0.9
                    * env
                    * math.sin(2 * math.pi * 55.0 * local / sample_rate)
                )
        return out

    return gen


def _chord_cmaj() -> SampleGen:
    """Harmonic/pop-like: C major triad (C4/E4/G4) mix."""

    freqs = (261.63, 329.63, 392.00)

    def gen(n: int, sample_rate: int) -> list[int]:
        out: list[int] = []
        for i in range(n):
            s = sum(math.sin(2 * math.pi * f * i / sample_rate) for f in freqs) / len(
                freqs
            )
            out.append(int(32767 * 0.7 * s))
        return out

    return gen


def _noise_burst() -> SampleGen:
    """Ambient/texture-like: seeded white noise (deterministic)."""

    def gen(n: int, sample_rate: int) -> list[int]:
        del sample_rate  # rate unused; length is n
        rng = random.Random(0x4D453130)  # "ME10"
        return [int(rng.uniform(-0.35, 0.35) * 32767) for _ in range(n)]

    return gen


# name, duration_s, generator
CASES: tuple[tuple[str, float, SampleGen], ...] = (
    ("sine_440hz_1s", 1.0, _tone(440)),
    ("sine_220hz_2s", 2.0, _tone(220)),
    ("silence_1s", 1.0, _tone(0)),
    ("kick_pattern_2s", 2.0, _kick_pattern()),
    ("chord_cmaj_1s", 1.0, _chord_cmaj()),
    ("noise_burst_1s", 1.0, _noise_burst()),
)


def _write_wav(
    path: Path, duration_s: float, gen: SampleGen, sample_rate: int = 44100
) -> Path:
    n = int(duration_s * sample_rate)
    samples = gen(n, sample_rate)
    assert len(samples) == n
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n}h", *samples))
    return path


def _normalize(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Drop path-dependent fields; round floats for cross-platform stability."""
    meta = dict(spec_dict.get("metadata") or {})
    meta.pop("source_audio", None)

    def _round_num(v: Any) -> Any:
        if isinstance(v, float):
            return round(v, 6)
        if isinstance(v, list):
            return [_round_num(x) for x in v]
        return v

    for key in (
        "duration",
        "analysis_peak_rms",
        "estimated_bpm",
        "amplitude_envelope",
        "onset_times",
    ):
        if key in meta:
            meta[key] = _round_num(meta[key])

    timeline = spec_dict.get("timeline") or []
    norm_timeline = []
    for ev in timeline:
        item = dict(ev)
        if "time" in item and isinstance(item["time"], float):
            item["time"] = round(item["time"], 6)
        norm_timeline.append(item)

    return {
        "metadata": {
            "sample_rate": meta.get("sample_rate"),
            "channels": meta.get("channels"),
            "duration": meta.get("duration"),
            "fps": meta.get("fps"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "analysis_peak_rms": meta.get("analysis_peak_rms"),
            "estimated_bpm": meta.get("estimated_bpm"),
            "amplitude_envelope": meta.get("amplitude_envelope"),
            "onset_times": meta.get("onset_times"),
            "chord": meta.get("chord"),
            "scale": meta.get("scale"),
            "harmonic_notes": meta.get("harmonic_notes"),
        },
        "timeline": norm_timeline,
        "palette": spec_dict.get("palette") or [],
    }


def _dump(spec: Any) -> dict[str, Any]:
    if hasattr(spec, "model_dump"):
        return spec.model_dump()
    return dict(spec)


@pytest.mark.parametrize("name,duration,gen", CASES, ids=[c[0] for c in CASES])
def test_golden_renderspec(
    name: str, duration: float, gen: SampleGen, tmp_path: Path
) -> None:
    from melosviz.analysis.audio import spec_from_wav

    wav = _write_wav(WAV_DIR / f"{name}.wav", duration, gen)
    local = _write_wav(tmp_path / f"{name}.wav", duration, gen)
    assert wav.stat().st_size > 44
    spec = spec_from_wav(local)
    got = _normalize(_dump(spec))

    expected_path = EXPECTED_DIR / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN") in ("1", "true", "True"):
        EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
        expected_path.write_text(
            json.dumps(got, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pytest.skip(f"updated golden {expected_path.relative_to(REPO_ROOT)}")

    assert expected_path.is_file(), (
        f"missing golden {expected_path}; run with UPDATE_GOLDEN=1 to create"
    )
    want = json.loads(expected_path.read_text(encoding="utf-8"))
    assert got["metadata"]["sample_rate"] == want["metadata"]["sample_rate"] == 44100
    assert got["metadata"]["channels"] == want["metadata"]["channels"] == 1
    assert abs(float(got["metadata"]["duration"]) - duration) < 0.05
    assert len(got["metadata"]["amplitude_envelope"] or []) == len(
        want["metadata"]["amplitude_envelope"] or []
    )
    assert got == want


def test_golden_manifest_lists_all_cases() -> None:
    manifest = GOLDEN_DIR / "MANIFEST.md"
    assert manifest.is_file()
    text = manifest.read_text(encoding="utf-8")
    for name, _, _ in CASES:
        assert name in text
