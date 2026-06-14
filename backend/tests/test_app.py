"""Backend API integration tests using FastAPI TestClient.

WP-18: Test: backend API integration
Exercises all public endpoints defined in ``melosviz.main`` with the
TestClient so no live server is needed.
"""

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
    """Write a minimal sine-wave WAV file for upload tests."""
    total_frames = int(sample_rate * duration)
    amplitude = 0.35
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(total_frames):
            sample = int(
                amplitude * 32767 * math.sin(2 * math.pi * frequency * i / sample_rate)
            )
            wav_file.writeframes(struct.pack("<h", sample))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_endpoint() -> None:
    """GET /v1/health returns 200 and a status payload."""
    response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_healthz_alias_not_found() -> None:
    """GET /healthz is not defined in this app."""
    response = client.get("/healthz")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def test_presets_list() -> None:
    """GET /v1/presets returns a list of theme presets."""
    response = client.get("/v1/presets")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Every preset has a readable name and an ID
    for preset in data:
        assert "id" in preset
        assert "name" in preset


# ---------------------------------------------------------------------------
# Audio Analysis
# ---------------------------------------------------------------------------

def test_analyze_post_with_valid_audio(tmp_path: Path) -> None:
    """POST /v1/audio/analyze with a valid WAV file."""
    audio_path = tmp_path / "tone.wav"
    _write_test_wav(audio_path)

    import json
    request_payload = {
        "model": "default",
        "analysis": "full",
        "include_waveform": True,
        "include_spectrum": True,
        "include_bpm": True,
        "genre": "dark_street",
        "window_ms": 2000,
        "fft_size": 2048,
        "hop_size": 512,
    }

    with audio_path.open("rb") as file_handle:
        response = client.post(
            "/v1/audio/analyze",
            files={"file": ("tone.wav", file_handle, "audio/wav")},
            data={"request": json.dumps(request_payload)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["sample_rate"] == 22050
    assert body["channels"] == 1
    assert body["analysis"] == "full"
    assert "bpm" in body
    assert "waveform" in body
    assert "frequency" in body


def test_analyze_post_rejects_invalid_audio() -> None:
    """POST /v1/audio/analyze with a non-audio file yields 415."""
    import json
    bad_audio = b"not-an-audio-file"
    response = client.post(
        "/v1/audio/analyze",
        files={"file": ("bad.wav", bad_audio, "audio/wav")},
        data={"request": json.dumps({"analysis": "full"})},
    )
    assert response.status_code == 415


def test_analyze_post_missing_file() -> None:
    """POST /v1/audio/analyze without a file yields 422."""
    response = client.post(
        "/v1/audio/analyze",
        data={"request": "{}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Audio Visualization
# ---------------------------------------------------------------------------

def test_visualize_post_with_valid_audio(tmp_path: Path) -> None:
    """POST /v1/audio/visualize with a valid WAV file."""
    audio_path = tmp_path / "tone.wav"
    _write_test_wav(audio_path)

    import json
    payload = {
        "analysis": "full",
        "style": {},
        "fps": 24,
        "width": 1280,
        "height": 720,
        "duration_sec": 1.0,
        "export_format": "json",
        "seed": 42,
    }

    with audio_path.open("rb") as file_handle:
        response = client.post(
            "/v1/audio/visualize",
            files={"file": ("tone.wav", file_handle, "audio/wav")},
            data={
                "payload": json.dumps(payload),
                "theme": "dark_street",
                "analysis": "full",
                "fps": 24,
                "width": 1280,
                "height": 720,
                "duration_sec": 1.0,
                "export_format": "json",
                "seed": 42,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Visualization spec generated"
    assert "selected_theme" in body
    assert "render" in body
    assert "keyframes" in body["render"]
    assert len(body["render"]["keyframes"]) > 0


def test_visualize_post_rejects_bad_export_format() -> None:
    """POST /v1/audio/visualize with an invalid export_format yields 422."""
    import json
    payload = {
        "analysis": "full",
        "style": {},
        "fps": 24,
        "width": 1280,
        "height": 720,
        "duration_sec": 1.0,
        "export_format": "bad_format",
        "seed": 0,
    }

    response = client.post(
        "/v1/audio/visualize",
        data={
            "payload": json.dumps(payload),
            "theme": "dark_street",
            "analysis": "full",
            "fps": 24,
            "width": 1280,
            "height": 720,
            "duration_sec": 1.0,
            "export_format": "bad_format",
            "seed": 0,
        },
    )

    assert response.status_code == 422


def test_visualize_post_missing_file() -> None:
    """POST /v1/audio/visualize without a file yields 422."""
    response = client.post(
        "/v1/audio/visualize",
        data={"payload": "{}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Non-existent endpoints (task-specified)
# ---------------------------------------------------------------------------

def test_api_v1_jobs_not_found() -> None:
    """GET /api/v1/jobs is not defined in this app."""
    response = client.get("/api/v1/jobs")
    assert response.status_code == 404


def test_api_v1_jobs_post_not_found() -> None:
    """POST /api/v1/jobs is not defined in this app."""
    response = client.post("/api/v1/jobs", json={"name": "test"})
    assert response.status_code == 404


def test_api_v1_healthz_not_found() -> None:
    """GET /api/v1/healthz is not defined in this app."""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 404
