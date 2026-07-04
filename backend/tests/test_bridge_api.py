"""FastAPI bridge endpoint tests.

Covers the /health and /analyze endpoints using FastAPI's TestClient
(backed by httpx).  The Rust MIR binary is never present in CI, so all
analyze tests monkeypatch ``_analyze_with_mir_or_python`` to avoid the
subprocess call while still exercising the full HTTP layer.
"""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from melosviz.bridge import server
from melosviz.bridge.server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Return a synchronous TestClient for the bridge app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_security():
    """Reset rate-limiter state between tests so they are independent."""
    yield
    if hasattr(server, "security_limiter"):
        server.security_limiter.reset()


@pytest.fixture
def minimal_wav(tmp_path: Path) -> Path:
    """Write a valid, minimal (0.1 s, mono, 44100 Hz) WAV to *tmp_path*."""
    wav_path = tmp_path / "test_tone.wav"
    n_frames = 4410  # 0.1 s at 44100 Hz
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(44100)
        # Silent frames (all zeros)
        wf.writeframes(struct.pack("<" + "h" * n_frames, *([0] * n_frames)))
    return wav_path


@pytest.fixture
def mock_render_spec() -> dict:
    """Minimal RenderSpec v2 dict returned by the mocked analyzer."""
    return {
        "metadata": {
            "source_audio": "/tmp/test.wav",
            "duration": 0.1,
            "fps": 30,
            "width": 1920,
            "height": 1080,
            "sample_rate": 44100,
            "channels": 1,
            "estimated_bpm": 120.0,
            "analysis_peak_rms": 0.0,
            "amplitude_envelope": [],
        },
        "palette": ["#00f5ff", "#ff2fd5"],
        "layers": [],
        "keyframes": [],
        "timeline": [],
        "dense_keyframes": [
            {
                "t": 0.0,
                "energy": 0.0,
                "brightness": 0.0,
                "valence": 0.5,
                "arousal": 0.5,
                "beat_strength": 0.0,
                "onset_strength": 0.0,
                "spectral_centroid": 0.0,
                "stems": {"drums": 0.0, "bass": 0.0, "vocals": 0.0, "other": 0.0},
                "easing": "linear",
            }
        ],
        "timeline_events": [],
        "scene_segments": [
            {
                "index": 0,
                "label": "intro",
                "start": 0.0,
                "end": 0.1,
                "energy_mean": 0.0,
                "brightness_mean": 0.0,
                "mood": {"valence": 0.5, "arousal": 0.5},
                "dominant_stem": "other",
            }
        ],
        "stem_channels": {"drums": [], "bass": [], "vocals": [], "other": []},
        "mir": {
            "tempo_bpm": 120.0,
            "tempo_curve": [],
            "danceability": None,
            "energy_trajectory": [],
            "brightness_trajectory": [],
            "valence_trajectory": [],
            "arousal_trajectory": [],
            "key": "C",
            "mode": "major",
            "chord_sequence": [],
        },
    }


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient) -> None:
        """GET /health must return HTTP 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_body_has_status_ok(self, client: TestClient) -> None:
        """GET /health body must include {"status": "ok"}."""
        data = client.get("/health").json()
        assert data.get("status") == "ok"


# ---------------------------------------------------------------------------
# POST /analyze — validation errors
# ---------------------------------------------------------------------------


class TestAnalyzeValidation:
    def test_missing_wav_path_returns_422(self, client: TestClient) -> None:
        """POST /analyze without wav_path must return 422 (Pydantic validation)."""
        response = client.post("/analyze", json={})
        assert response.status_code == 422

    def test_nonexistent_file_returns_400(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """POST /analyze with a path that does not exist must return 400."""
        missing = str(tmp_path / "ghost.wav")
        response = client.post("/analyze", json={"wav_path": missing})
        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "not found" in detail.lower() or "File not found" in detail


# ---------------------------------------------------------------------------
# POST /analyze — happy path
# ---------------------------------------------------------------------------


class TestAnalyzeHappyPath:
    def test_valid_wav_returns_200(
        self,
        client: TestClient,
        minimal_wav: Path,
        mock_render_spec: dict,
    ) -> None:
        """POST /analyze with a real WAV file returns HTTP 200."""
        with patch(
            "melosviz.bridge.server._analyze_with_mir_or_python",
            return_value=mock_render_spec,
        ):
            response = client.post("/analyze", json={"wav_path": str(minimal_wav)})
        assert response.status_code == 200

    def test_valid_wav_returns_json_with_required_fields(
        self,
        client: TestClient,
        minimal_wav: Path,
        mock_render_spec: dict,
    ) -> None:
        """RenderSpec response must contain metadata, keyframes, and mir keys."""
        with patch(
            "melosviz.bridge.server._analyze_with_mir_or_python",
            return_value=mock_render_spec,
        ):
            response = client.post("/analyze", json={"wav_path": str(minimal_wav)})

        data = json.loads(response.text)
        for field in ("metadata", "keyframes", "dense_keyframes", "mir"):
            assert field in data, f"RenderSpec missing required field: {field}"

    def test_render_spec_field_types(
        self,
        client: TestClient,
        minimal_wav: Path,
        mock_render_spec: dict,
    ) -> None:
        """RenderSpec fields must have correct Python types."""
        with patch(
            "melosviz.bridge.server._analyze_with_mir_or_python",
            return_value=mock_render_spec,
        ):
            response = client.post("/analyze", json={"wav_path": str(minimal_wav)})

        data = json.loads(response.text)
        meta = data["metadata"]
        assert isinstance(meta.get("estimated_bpm"), (int, float)), (
            "estimated_bpm must be numeric"
        )
        assert isinstance(data.get("keyframes"), list), "keyframes must be a list"
        assert isinstance(data.get("dense_keyframes"), list), (
            "dense_keyframes must be a list"
        )
        assert isinstance(data.get("palette"), list), "palette must be a list"
        assert isinstance(data.get("mir"), dict), "mir must be a dict"

    def test_mir_tempo_bpm_is_numeric(
        self,
        client: TestClient,
        minimal_wav: Path,
        mock_render_spec: dict,
    ) -> None:
        """mir.tempo_bpm must be numeric when present."""
        with patch(
            "melosviz.bridge.server._analyze_with_mir_or_python",
            return_value=mock_render_spec,
        ):
            response = client.post("/analyze", json={"wav_path": str(minimal_wav)})

        data = json.loads(response.text)
        tempo = data["mir"].get("tempo_bpm")
        assert tempo is None or isinstance(tempo, (int, float)), (
            f"mir.tempo_bpm must be numeric or null, got {type(tempo)}"
        )
