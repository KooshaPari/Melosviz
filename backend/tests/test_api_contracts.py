"""API contract tests for Melosviz."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from melosviz.main import app

client = TestClient(app)


def _write_test_wav(
    path: Path,
    sample_rate: int = 22050,
    duration: float = 1.0,
    frequency: float = 440.0,
) -> None:
    total_frames = int(sample_rate * duration)
    amplitude = 0.35
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for index in range(total_frames):
            sample = int(
                amplitude
                * 32767
                * math.sin(2 * math.pi * frequency * index / sample_rate)
            )
            wav_file.writeframes(struct.pack("<h", sample))


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_endpoint_returns_analysis_contract(tmp_path: Path) -> None:
    audio_path = tmp_path / "tone.wav"
    _write_test_wav(audio_path)

    with audio_path.open("rb") as file_handle:
        response = client.post(
            "/v1/audio/analyze",
            files={"file": ("tone.wav", file_handle, "audio/wav")},
            data={"request": '{"model": "default", "analysis": "full"}'},
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    payload = response.json()
    assert payload["analysis"] == "full"
    assert payload["sample_rate"] == 22050
    assert payload["channels"] == 1
    assert payload["bpm"] is not None
    assert payload["waveform"] is not None
    assert payload["frequency"] is not None


def test_analyze_endpoint_rejects_invalid_audio_with_http_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "broken.wav"
    invalid_path.write_bytes(b"not-audio")

    with invalid_path.open("rb") as file_handle:
        response = client.post(
            "/v1/audio/analyze",
            files={"file": ("broken.wav", file_handle, "audio/wav")},
            data={"request": '{"model": "default", "analysis": "full"}'},
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 415
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    detail = response.json()["detail"]
    assert (
        "Unable to decode audio file" in detail
        or "Failed to run full analysis" in detail
        or "Error opening" in detail
    )


def test_visualize_endpoint_returns_render_contract(tmp_path: Path) -> None:
    audio_path = tmp_path / "tone.wav"
    _write_test_wav(audio_path)

    with audio_path.open("rb") as file_handle:
        response = client.post(
            "/v1/audio/visualize",
            data={
                "payload": '{"model": "default", "analysis": "full", "fps": 24, "width": 1280, "height": 720, "duration_sec": 1.0, "export_format": "json", "seed": 42}',
                "theme": "dark_street",
            },
            files={"file": ("tone.wav", file_handle, "audio/wav")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["message"] == "Visualization spec generated"
    assert payload["selected_theme"]["id"] == "dark_street"
    assert payload["frame_count"] == len(payload["render"]["keyframes"])
    assert payload["duration_sec"] == 1.0

    keyframe = payload["render"]["keyframes"][0]
    assert {
        "hue",
        "amplitude",
        "intensity",
        "bpm_sync",
        "energy",
        "color_shift",
        "frequency",
    } <= keyframe.keys()

    assert 0.0 <= keyframe["energy"] <= 1.0
    assert 0.0 <= keyframe["hue"] <= 360.0
    assert 0.0 <= keyframe["intensity"] <= 1.0
    assert isinstance(keyframe["color_shift"], str)
    assert isinstance(keyframe["amplitude"], (int, float))
    assert isinstance(keyframe["frequency"]["dominant"], list)
