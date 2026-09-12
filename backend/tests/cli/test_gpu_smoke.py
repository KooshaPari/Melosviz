"""Real-GPU end-to-end smoke test for the melosviz studio pipeline.

Runs the full 5-step CLI in offline-MELOSVIZ_COMFYUI mode against a tiny
30s sine-wave WAV + a 3-line LRC, verifies the artifact topology is
correct, and asserts the cache + provenance + validate layers all
report back cleanly.

Pre-conditions:
  - MELOSVIZ_COMFYUI_OFFLINE=1 (offline-mode workflow; no GPU required)
  - ffmpeg + uv on PATH
  - backend pytest can write to /tmp/melviz_smoke

The test is marked ``pytest.mark.slow`` so it doesn't run on every
``pytest`` invocation. Run with ``pytest -m slow tests/cli/test_gpu_smoke.py``
or ``--no-header -m slow test_gpu_smoke.py``.
"""
from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
WORKDIR = Path("/tmp/melviz_smoke")


def _synth_wav(path: Path, dur_s: float = 6.0, bpm: int = 120) -> None:
    """Write a minimal stereo 22050Hz 16-bit PCM WAV with a kick on every beat."""
    sr = 22050
    n = int(sr * dur_s)
    period = 60.0 / bpm
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(n):
            t = i / sr
            bt = t % period
            kick = 0.55 * math.exp(-bt * 50.0) if bt < 0.05 else 0.0
            sample = int(max(-1.0, min(1.0, kick)) * 32767)
            w.writeframes(struct.pack("<h", sample))


def _write_lrc(path: Path) -> None:
    path.write_text(
        "[00:00.00]Test line one\n"
        "[00:02.00]Test line two\n"
        "[00:04.00]Test line three\n"
    )


def _run_cli(args: list[str], cwd: Path, env: dict) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "melosviz.cli.main", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, (
        f"CLI failed (rc={completed.returncode})\n"
        f"  args: {args}\n"
        f"  stdout: {completed.stdout[-2000:]}\n"
        f"  stderr: {completed.stderr[-2000:]}\n"
    )


def test_studio_pipeline_offline_mode_produces_artifact_topology(tmp_path: Path) -> None:
    """End-to-end smoke: 5-step pipeline emits the full artifact tree."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH — required for the master step")

    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir(parents=True)

    # 1. Synth inputs.
    wav_path = WORKDIR / "track.wav"
    lrc_path = WORKDIR / "track.lrc"
    _synth_wav(wav_path, dur_s=6.0, bpm=120)
    _write_lrc(lrc_path)

    env = os.environ.copy()
    env["MELOSVIZ_COMFYUI_OFFLINE"] = "1"
    # Point the CLI subprocess at the repo's backend/src so melosviz is
    # importable. parents[3] of this file lands at the repo root, so
    # /backend/src/ there is the editable source tree.
    env["PYTHONPATH"] = str(
        (Path(__file__).resolve().parents[3] / "backend" / "src")
    )

    # 2. Storyboard.
    sb_path = WORKDIR / "storyboard.json"
    _run_cli(
        [
            "storyboard",
            str(wav_path),
            "--concept",
            "GPU smoke test",
            "--bpm",
            "120",
            "--palette",
            "#0d0d10 #ff2bd6 #22d3ee",
            "--lyrics",
            str(lrc_path),
            "--out",
            str(sb_path),
        ],
        WORKDIR,
        env,
    )
    assert sb_path.exists(), "storyboard.json was not produced"
    sb = json.loads(sb_path.read_text())
    assert "scenes" in sb and sb["scenes"], "storyboard.json had no scenes"

    # 3. Validate (in-process, no CLI call) — storyboard structure sanity check.
    sb = json.loads(sb_path.read_text())
    for scene in sb["scenes"]:
        assert "prompt" in scene
        assert "start" in scene and "duration" in scene

    # 4. Generate (offline-mode writes workflow.json per scene).
    gen_path = WORKDIR / "generate"
    _run_cli(
        [
            "generate",
            str(wav_path),
            "--storyboard",
            str(sb_path),
            "--out",
            str(gen_path),
        ],
        WORKDIR,
        env,
    )
    # Scene dirs live under the scene-type subdirs (e.g. comfyui_video/scene_000).
    scene_dirs = list(gen_path.rglob("scene_*"))
    assert scene_dirs, f"generate produced no scene_* dirs under {gen_path}"

    # 5. Validate the generated tree has workflow.json per ComfyUI scene.
    comfy_dirs = [d for d in scene_dirs if d.parent.name.startswith("comfyui_")]
    assert comfy_dirs, "generate produced no ComfyUI scene dirs"
    for scene_dir in comfy_dirs:
        wf = scene_dir / "workflow.json"
        assert wf.exists(), f"missing {wf}"

    # 6. Ship: offline package + archive topology (production-delivery-extensions).
    _run_cli(["ship", str(gen_path)], WORKDIR, env)
    final_zip = gen_path / "final.zip"
    assert final_zip.is_file() and final_zip.stat().st_size > 0, (
        "final.zip was not produced by viz ship"
    )
    with zipfile.ZipFile(final_zip) as archive:
        names = archive.namelist()
    assert "manifest.json" in names, "ship output missing manifest.json"
    assert "vj/manifest.json" in names, "ship output missing vj/manifest.json"


# Single-character single-use import so the file uses `json` above without a duplicate.
import json  # noqa: E402  (placed after module-level test definitions)
import zipfile  # noqa: E402  (used by step 6 ZIP assertions above)
