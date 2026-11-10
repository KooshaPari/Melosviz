"""Mounted M-E02 smoke: real CLI/bridge, real FFmpeg, no adapter mocks.

This does NOT grade artistic quality. It proves the repaired product spine can:
- dispatch two scenes sharing one backend as two work identities;
- emit two independently decodable scene artifacts;
- feed those artifacts to a decodable final assembly;
- return the same structured scene truth through /api/studio/generate.

The independent recovery oracle remains a separate acceptance boundary.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from melosviz.bridge.server import app


def _write_wav(path: Path, seconds: float = 1.0, sr: int = 8000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(seconds * sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(frames):
            # deterministic, non-silent saw wave
            sample = ((i % 80) - 40) * 300
            w.writeframesraw(struct.pack("<h", sample))


def _storyboard(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "concept": "M-E02 mounted fixture",
                "seed": 7,
                "scenes": [
                    {
                        "index": 0,
                        "name": "s0",
                        "label": "intro",
                        "start": 0.0,
                        "end": 0.5,
                        "scene_type": "video_export",
                        "prompt": "fixture scene zero",
                        "palette": ["#ff0000"],
                    },
                    {
                        "index": 1,
                        "name": "s1",
                        "label": "outro",
                        "start": 0.5,
                        "end": 1.0,
                        "scene_type": "video_export",
                        "prompt": "fixture scene one",
                        "palette": ["#0000ff"],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _probe(path: Path) -> None:
    assert path.is_file() and path.stat().st_size > 0, path
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    streams = payload.get("streams") or []
    assert len(streams) == 1 and streams[0].get("codec_type") == "video", payload


def _run_cli(wav: Path, sb: Path, out: Path, *, only_scenes: str | None = None) -> dict:
    env = os.environ.copy()
    env.pop("MELOSVIZ_COMFYUI_OFFLINE", None)
    cmd = [
        sys.executable,
        "-m",
        "melosviz.cli.main",
        "generate",
        str(wav),
        "--storyboard",
        str(sb),
        "--out",
        str(out),
        "--job-id",
        "m-e02-mounted",
    ]
    if only_scenes is not None:
        cmd += ["--only-scenes", only_scenes]
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    return json.loads(proc.stdout)


@pytest.mark.skipif(
    subprocess.run(["sh", "-c", "command -v ffmpeg && command -v ffprobe"], capture_output=True).returncode != 0,
    reason="ffmpeg/ffprobe required for mounted media smoke",
)
def test_mounted_cli_two_same_backend_scenes_feed_real_assembly(tmp_path: Path) -> None:
    wav = tmp_path / "track.wav"
    sb = tmp_path / "storyboard.json"
    out = tmp_path / "cli-out"
    _write_wav(wav)
    _storyboard(sb)

    manifest = _run_cli(wav, sb, out)
    assert manifest["dispatched_scenes"] == [0, 1], manifest
    assert manifest["assembly_state"] == "produced_unverified", manifest
    scenes = manifest["scenes"]
    assert [s["scene_index"] for s in scenes] == [0, 1], scenes
    assert [s["scene_type"] for s in scenes] == ["video_export", "video_export"]
    assert [s["outcome"] for s in scenes] == ["render", "render"]

    paths = [Path(s["artifact_path"]) for s in scenes]
    assert len({p.resolve() for p in paths}) == 2, paths
    assert "dispatch_000" in paths[0].parts
    assert "dispatch_001" in paths[1].parts
    for p in paths:
        _probe(p)

    assembled = out / "assembly" / "melosviz-assembled.mp4"
    _probe(assembled)


@pytest.mark.skipif(
    subprocess.run(["sh", "-c", "command -v ffmpeg && command -v ffprobe"], capture_output=True).returncode != 0,
    reason="ffmpeg/ffprobe required for mounted media smoke",
)
def test_mounted_bridge_generate_returns_real_structured_scene_results(tmp_path: Path) -> None:
    wav = tmp_path / "track.wav"
    sb = tmp_path / "storyboard.json"
    out = tmp_path / "bridge-out"
    _write_wav(wav)
    _storyboard(sb)

    with TestClient(app) as client:
        response = client.post(
            "/api/studio/generate",
            json={
                "wav_path": str(wav),
                "storyboard_path": str(sb),
                "out_dir": str(out),
                "offline": False,
                "job_id": "m-e02-bridge-mounted",
            },
        )

    assert response.status_code == 200, response.text
    manifest = response.json()
    scenes = manifest.get("scenes") or []
    assert [s.get("scene_index") for s in scenes] == [0, 1], manifest
    assert [s.get("outcome") for s in scenes] == ["render", "render"], manifest
    for scene in scenes:
        _probe(Path(scene["artifact_path"]))
    _probe(out / "assembly" / "melosviz-assembled.mp4")


def _duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return float(proc.stdout.strip())


@pytest.mark.skipif(
    subprocess.run(["sh", "-c", "command -v ffmpeg && command -v ffprobe"], capture_output=True).returncode != 0,
    reason="ffmpeg/ffprobe required for mounted media smoke",
)
def test_mounted_r2_selective_render_reuses_r1_evidence_for_complete_assembly(
    tmp_path: Path,
) -> None:
    wav = tmp_path / "track.wav"
    sb = tmp_path / "storyboard.json"
    out = tmp_path / "r2-out"
    _write_wav(wav)
    _storyboard(sb)

    r1 = _run_cli(wav, sb, out)
    assert r1["dispatched_scenes"] == [0, 1]
    assembled = out / "assembly" / "melosviz-assembled.mp4"
    _probe(assembled)
    r1_duration = _duration(assembled)
    assert r1_duration > 1.5, r1_duration

    payload = json.loads(sb.read_text(encoding="utf-8"))
    r1_digest = __import__("hashlib").sha256(assembled.read_bytes()).hexdigest()
    s0_path = Path(r1["scenes"][0]["artifact_path"])
    s0_digest = __import__("hashlib").sha256(s0_path.read_bytes()).hexdigest()
    payload["scenes"][1]["prompt"] = "fixture scene one revised"
    payload["scenes"][1]["palette"] = ["#00ff00"]
    sb.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    r2 = _run_cli(wav, sb, out, only_scenes="1")
    assert r2["dispatched_scenes"] == [1], r2
    assert r2["only_scenes"] == [1], r2
    assert r2["assembly_state"] == "produced_unverified", r2
    _probe(assembled)
    r2_duration = _duration(assembled)
    # A selected-only assembly would be ~1 second. Reuse of unchanged S0 must
    # keep the complete two-scene timeline.
    assert r2_duration > 1.5, r2_duration
    r2_digest = __import__("hashlib").sha256(assembled.read_bytes()).hexdigest()
    assert r2_digest != r1_digest
    assert __import__("hashlib").sha256(s0_path.read_bytes()).hexdigest() == s0_digest
    repeat = _run_cli(wav, sb, out, only_scenes="1")
    assert len(repeat["scenes"]) == 1 and repeat["scenes"][0]["scene_index"] == 1
    assert repeat["scenes"][0]["from_cache"] is True, repeat
    assert __import__("hashlib").sha256(assembled.read_bytes()).hexdigest() == r2_digest
