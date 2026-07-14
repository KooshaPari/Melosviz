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


class TestReadyAndMetrics:
    def test_ready_returns_200(self, client: TestClient) -> None:
        """GET /ready must return HTTP 200 when the bridge is serving."""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ready"
        assert "uptime_s" in data

    def test_metrics_prometheus_text(self, client: TestClient) -> None:
        """GET /metrics must return Prometheus-text exposition."""
        client.get("/health")
        response = client.get("/metrics")
        assert response.status_code == 200
        body = response.text
        assert "melosviz_up 1" in body
        assert "melosviz_ready" in body
        assert "melosviz_http_requests_total" in body

    def test_debug_profile_disabled_by_default(self, client: TestClient) -> None:
        import os

        os.environ.pop("MELOSVIZ_PROFILE", None)
        assert client.get("/debug/profile").status_code == 404

    def test_debug_profile_enabled(self, client: TestClient) -> None:
        import os

        os.environ["MELOSVIZ_PROFILE"] = "1"
        try:
            response = client.get("/debug/profile")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data.get("mode") == "oneshot"
            assert "profile" in data
            assert "function calls" in data["profile"]
        finally:
            os.environ.pop("MELOSVIZ_PROFILE", None)

    def test_debug_profile_continuous_enabled(self, client: TestClient) -> None:
        """MELOSVIZ_PROFILE=continuous starts a sampler; GET returns latest dump."""
        import os

        from melosviz import observability as obs

        os.environ["MELOSVIZ_PROFILE"] = "continuous"
        os.environ["MELOSVIZ_PROFILE_INTERVAL_S"] = "0.2"
        try:
            obs.stop_continuous_profiler()
            obs.ensure_continuous_profiler()
            response = client.get("/debug/profile")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["mode"] == "continuous"
            assert "profile" in data
            assert "function calls" in data["profile"]
            assert "sampled_at" in data
            assert data["interval_s"] == 0.2
        finally:
            obs.stop_continuous_profiler()
            os.environ.pop("MELOSVIZ_PROFILE", None)
            os.environ.pop("MELOSVIZ_PROFILE_INTERVAL_S", None)

    def test_debug_profile_continuous_via_2(self, client: TestClient) -> None:
        """MELOSVIZ_PROFILE=2 is an alias for continuous mode."""
        import os

        from melosviz import observability as obs

        os.environ["MELOSVIZ_PROFILE"] = "2"
        try:
            obs.stop_continuous_profiler()
            obs.ensure_continuous_profiler()
            response = client.get("/debug/profile")
            assert response.status_code == 200
            assert response.json()["mode"] == "continuous"
        finally:
            obs.stop_continuous_profiler()
            os.environ.pop("MELOSVIZ_PROFILE", None)


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
        assert "problem+json" in response.headers.get("content-type", "")
        body = response.json()
        detail = str(body.get("detail", ""))
        assert "not found" in detail.lower() or "File not found" in detail
        assert body.get("status") == 400
        assert body.get("title")


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


# ---------------------------------------------------------------------------
# POST /analyze — audio_path alias
# ---------------------------------------------------------------------------


class TestAnalyzeAudioPathAlias:
    def test_audio_path_accepted(
        self,
        client: TestClient,
        minimal_wav: Path,
        mock_render_spec: dict,
    ) -> None:
        with patch(
            "melosviz.bridge.server._analyze_with_mir_or_python",
            return_value=mock_render_spec,
        ):
            response = client.post(
                "/analyze", json={"audio_path": str(minimal_wav)}
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------


class TestUploadEndpoint:
    def test_upload_returns_wav_path(
        self, client: TestClient, minimal_wav: Path
    ) -> None:
        with minimal_wav.open("rb") as fh:
            response = client.post(
                "/upload",
                files={"file": ("tone.wav", fh, "audio/wav")},
            )
        assert response.status_code == 200
        body = response.json()
        assert "wav_path" in body
        uploaded = Path(body["wav_path"])
        assert uploaded.exists()
        assert uploaded.stat().st_size > 0

    def test_uploaded_file_can_be_analyzed(
        self,
        client: TestClient,
        minimal_wav: Path,
        mock_render_spec: dict,
    ) -> None:
        with minimal_wav.open("rb") as fh:
            up = client.post(
                "/upload",
                files={"file": ("tone.wav", fh, "audio/wav")},
            )
        wav_path = up.json()["wav_path"]
        with patch(
            "melosviz.bridge.server._analyze_with_mir_or_python",
            return_value=mock_render_spec,
        ):
            response = client.post("/analyze", json={"wav_path": wav_path})
        assert response.status_code == 200
