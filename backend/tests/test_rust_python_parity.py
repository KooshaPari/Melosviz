"""Rust melosviz-mir ↔ Python spec_from_wav parity (C08 L75).

Compares schema presence and core metadata on a deterministic sine WAV.
Skips when the Rust binary is absent (local without cargo build).
CI builds ``melosviz-mir`` before running this module.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_wav(path: Path, duration_s: float = 1.0, freq: float = 440.0, sr: int = 44100) -> Path:
    n = int(duration_s * sr)
    samples = [int(32767 * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{n}h", *samples))
    return path


def _find_mir_bin() -> Path | None:
    env = os.environ.get("MELOSVIZ_MIR_BIN")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    candidates = [
        REPO_ROOT / "target" / "release" / "melosviz-mir",
        REPO_ROOT / "target" / "release" / "melosviz-mir.exe",
        REPO_ROOT / "target" / "debug" / "melosviz-mir",
        REPO_ROOT / "target" / "debug" / "melosviz-mir.exe",
    ]
    which = shutil.which("melosviz-mir")
    if which:
        candidates.insert(0, Path(which))
    for c in candidates:
        if c.is_file():
            return c
    return None


def _run_rust(mir: Path, wav: Path, out: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(mir), "--wav", str(wav), "--fps", "15", "--out", str(out)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, f"melosviz-mir failed:\n{proc.stderr}\n{proc.stdout}"
    return json.loads(out.read_text(encoding="utf-8"))


REQUIRED_TOP = {
    "metadata",
    "dense_keyframes",
    "timeline_events",
    "scene_segments",
    "stem_channels",
    "mir",
}
REQUIRED_META = {"sample_rate", "channels", "duration", "fps"}


@pytest.fixture(scope="module")
def mir_bin() -> Path:
    bin_path = _find_mir_bin()
    if bin_path is None:
        pytest.skip("melosviz-mir binary not found; build with cargo build -p melosviz-mir")
    return bin_path


def test_rust_python_metadata_parity(mir_bin: Path, tmp_path: Path) -> None:
    from melosviz.analysis.audio import spec_from_wav

    wav = _make_wav(tmp_path / "parity_440.wav", duration_s=1.0, freq=440.0)
    rust = _run_rust(mir_bin, wav, tmp_path / "rust.json")
    py = spec_from_wav(wav)
    py_dump = py.model_dump() if hasattr(py, "model_dump") else dict(py)

    assert REQUIRED_TOP.issubset(rust.keys())
    assert REQUIRED_META.issubset(set(rust["metadata"].keys()))
    assert REQUIRED_META.issubset(set(py_dump["metadata"].keys()))

    assert int(rust["metadata"]["sample_rate"]) == int(py_dump["metadata"]["sample_rate"]) == 44100
    assert int(rust["metadata"]["channels"]) == 1
    assert int(py_dump["metadata"]["channels"]) == 1
    assert abs(float(rust["metadata"]["duration"]) - 1.0) < 0.05
    assert abs(float(py_dump["metadata"]["duration"]) - 1.0) < 0.05
    # Both surfaces agree on duration within 50 ms.
    assert abs(float(rust["metadata"]["duration"]) - float(py_dump["metadata"]["duration"])) < 0.05


def test_rust_spec_validates_as_python_renderspec(mir_bin: Path, tmp_path: Path) -> None:
    from melosviz.analysis.models import RenderSpec

    wav = _make_wav(tmp_path / "parity_220.wav", duration_s=2.0, freq=220.0)
    rust = _run_rust(mir_bin, wav, tmp_path / "rust2.json")
    # Extra Rust-only nested fields should still parse into RenderSpec (extra=ignore default).
    spec = RenderSpec.model_validate(rust)
    assert float(spec.metadata["duration"]) > 1.5
    assert int(spec.metadata["sample_rate"]) == 44100


def test_rust_dense_keyframes_nonempty(mir_bin: Path, tmp_path: Path) -> None:
    wav = _make_wav(tmp_path / "parity_dense.wav", duration_s=1.0, freq=440.0)
    rust = _run_rust(mir_bin, wav, tmp_path / "dense.json")
    assert len(rust["dense_keyframes"]) >= 10
    assert isinstance(rust["mir"], dict)
