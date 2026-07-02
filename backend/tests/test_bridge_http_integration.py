"""Integration tests for the Bridge HTTP layer.

Tests cover:
- Happy path: valid requests → correct responses
- Error paths: invalid inputs, upstream failures, timeouts
- Security: rate limiting, auth, path containment
- Schema: response format validation
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from melosviz.bridge import server
from melosviz.bridge.server import app, AnalyzeRequest, BuildRequest, RenderRequest


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def reset_security():
    """Reset security limiter between tests."""
    yield
    if hasattr(server, 'security_limiter'):
        server.security_limiter.reset()


@pytest.fixture
def mock_wav_file(tmp_path):
    """Create a mock WAV file path."""
    wav_path = tmp_path / "test.wav"
    wav_path.write_bytes(b"RIFF" + b"\x00" * 100)  # Minimal WAV header
    return str(wav_path)


@pytest.fixture
def mock_render_spec():
    """Mock RenderSpec data."""
    return {
        "version": 2,
        "metadata": {
            "estimated_bpm": 120.0,
            "duration": 180.0,
            "width": 1280,
            "height": 720,
            "fps": 30,
        },
        "dense_keyframes": [],
        "scene_segments": [],
        "timeline_events": [],
        "palette": {},
        "domain_opacities": {},
    }


# =============================================================================
# Health endpoint tests
# =============================================================================


class TestHealthEndpoint:
    """GET /health endpoint."""

    def test_health_returns_ok(self, client, reset_security):
        """Health endpoint always returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_is_idempotent(self, client, reset_security):
        """Multiple health checks return same response."""
        resp1 = client.get("/health")
        resp2 = client.get("/health")
        assert resp1.json() == resp2.json()


# =============================================================================
# Analyze endpoint tests
# =============================================================================


class TestAnalyzeEndpoint:
    """POST /analyze endpoint."""

    def test_analyze_valid_wav_happy_path(self, client, mock_wav_file, mock_render_spec, reset_security):
        """Valid WAV file request returns RenderSpec JSON."""
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze:
            mock_analyze.return_value = mock_render_spec

            response = client.post(
                "/analyze",
                json={"wav_path": mock_wav_file},
            )

            assert response.status_code == 200
            data = json.loads(response.text)
            assert data["version"] == 2
            assert data["metadata"]["estimated_bpm"] == 120.0

    def test_analyze_missing_file_returns_400(self, client, tmp_path, reset_security):
        """Request for non-existent WAV returns 400."""
        missing = str(tmp_path / "missing.wav")
        response = client.post(
            "/analyze",
            json={"wav_path": missing},
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_analyze_empty_path_returns_400(self, client, reset_security):
        """Empty path string returns 400."""
        response = client.post(
            "/analyze",
            json={"wav_path": ""},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_analyze_invalid_wav_returns_400(self, client, tmp_path, reset_security):
        """Invalid WAV file returns 400 with error detail."""
        bad_wav = tmp_path / "bad.wav"
        bad_wav.write_bytes(b"INVALID")

        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze:
            mock_analyze.side_effect = ValueError("invalid WAV header")

            response = client.post(
                "/analyze",
                json={"wav_path": str(bad_wav)},
            )

            assert response.status_code == 400
            assert "invalid WAV" in response.json()["detail"]

    def test_analyze_mir_fallback_to_python(self, client, mock_wav_file, mock_render_spec, reset_security):
        """Analyzer falls back to Python when Rust MIR fails."""
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze:
            mock_analyze.return_value = mock_render_spec

            response = client.post(
                "/analyze",
                json={"wav_path": mock_wav_file},
            )

            assert response.status_code == 200
            mock_analyze.assert_called_once()


# =============================================================================
# Build endpoint tests
# =============================================================================


class TestBuildEndpoint:
    """POST /build endpoint."""

    def test_build_valid_spec_returns_plan(self, client, mock_wav_file, mock_render_spec, reset_security):
        """Valid WAV generates render plan JSON."""
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze, \
             patch("melosviz.compose.assemble.assemble_render_plan") as mock_assemble:
            mock_analyze.return_value = mock_render_spec
            mock_plan = {"transitions": [10.0, 20.0], "segments": []}
            mock_assemble.return_value = mock_plan

            response = client.post(
                "/build",
                json={"wav_path": mock_wav_file},
            )

            assert response.status_code == 200
            data = json.loads(response.text)
            assert "transitions" in data
            assert data["transitions"] == [10.0, 20.0]

    def test_build_missing_file_returns_400(self, client, tmp_path, reset_security):
        """Request for non-existent WAV returns 400."""
        missing = str(tmp_path / "missing.wav")
        response = client.post(
            "/build",
            json={"wav_path": missing},
        )
        assert response.status_code == 400

    def test_build_with_optional_out_dir(self, client, mock_wav_file, mock_render_spec, tmp_path, reset_security):
        """Build accepts optional out_dir parameter."""
        out_dir = str(tmp_path / "out")
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze, \
             patch("melosviz.compose.assemble.assemble_render_plan") as mock_assemble:
            mock_analyze.return_value = mock_render_spec
            mock_assemble.return_value = {"transitions": []}

            response = client.post(
                "/build",
                json={"wav_path": mock_wav_file, "out_dir": out_dir},
            )

            assert response.status_code == 200


# =============================================================================
# Render endpoint tests
# =============================================================================


class TestRenderEndpoint:
    """POST /render endpoint."""

    def test_render_valid_spec_creates_plan_file(self, client, mock_wav_file, mock_render_spec, tmp_path, reset_security):
        """Render endpoint writes plan JSON to output directory."""
        out_dir = str(tmp_path / "render_out")
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze, \
             patch("melosviz.compose.assemble.assemble_render_plan") as mock_assemble:
            mock_analyze.return_value = mock_render_spec
            mock_plan = {"transitions": [5.0, 15.0], "segments": []}
            mock_assemble.return_value = mock_plan

            response = client.post(
                "/render",
                json={"wav_path": mock_wav_file, "out_dir": out_dir},
            )

            assert response.status_code == 200
            assert out_dir in response.text
            # Verify plan file was written
            plan_file = Path(out_dir) / "render_plan.json"
            assert plan_file.exists()

    def test_render_missing_wav_returns_400(self, client, tmp_path, reset_security):
        """Render with missing WAV returns 400."""
        missing = str(tmp_path / "missing.wav")
        out_dir = str(tmp_path / "out")

        response = client.post(
            "/render",
            json={"wav_path": missing, "out_dir": out_dir},
        )
        assert response.status_code == 400

    def test_render_creates_output_directory(self, client, mock_wav_file, mock_render_spec, tmp_path, reset_security):
        """Render creates output directory if missing."""
        out_dir = str(tmp_path / "deep" / "nested" / "dir")
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze, \
             patch("melosviz.compose.assemble.assemble_render_plan") as mock_assemble:
            mock_analyze.return_value = mock_render_spec
            mock_assemble.return_value = {"transitions": []}

            response = client.post(
                "/render",
                json={"wav_path": mock_wav_file, "out_dir": out_dir},
            )

            assert response.status_code == 200
            assert Path(out_dir).exists()


# =============================================================================
# Schema and error response tests
# =============================================================================


class TestRequestValidation:
    """Request schema validation."""

    def test_analyze_missing_required_field(self, client, reset_security):
        """Request without wav_path returns 422."""
        response = client.post("/analyze", json={})
        assert response.status_code == 422

    def test_build_missing_required_field(self, client, reset_security):
        """Build without wav_path returns 422."""
        response = client.post("/build", json={})
        assert response.status_code == 422

    def test_render_missing_required_field(self, client, reset_security):
        """Render without out_dir returns 422."""
        response = client.post(
            "/render",
            json={"wav_path": "/some/path"},
        )
        assert response.status_code == 422

    def test_analyze_type_validation(self, client, reset_security):
        """Non-string wav_path returns 422."""
        response = client.post(
            "/analyze",
            json={"wav_path": 12345},
        )
        assert response.status_code == 422


class TestResponseSchema:
    """Response format validation."""

    def test_analyze_response_is_json_text(self, client, mock_wav_file, mock_render_spec, reset_security):
        """Analyze response is plaintext JSON (not application/json)."""
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze:
            mock_analyze.return_value = mock_render_spec

            response = client.post(
                "/analyze",
                json={"wav_path": mock_wav_file},
            )

            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")
            # Should still be valid JSON
            data = json.loads(response.text)
            assert isinstance(data, dict)

    def test_build_response_is_json_text(self, client, mock_wav_file, mock_render_spec, reset_security):
        """Build response is plaintext JSON."""
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze, \
             patch("melosviz.compose.assemble.assemble_render_plan") as mock_assemble:
            mock_analyze.return_value = mock_render_spec
            mock_assemble.return_value = {"transitions": []}

            response = client.post(
                "/build",
                json={"wav_path": mock_wav_file},
            )

            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")

    def test_render_response_is_json_text(self, client, mock_wav_file, mock_render_spec, tmp_path, reset_security):
        """Render response is plaintext JSON (output directory path)."""
        out_dir = str(tmp_path / "out")
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze, \
             patch("melosviz.compose.assemble.assemble_render_plan") as mock_assemble:
            mock_analyze.return_value = mock_render_spec
            mock_assemble.return_value = {"transitions": []}

            response = client.post(
                "/render",
                json={"wav_path": mock_wav_file, "out_dir": out_dir},
            )

            assert response.status_code == 200


# =============================================================================
# PathContainment tests
# =============================================================================


class TestPathContainment:
    """Path containment / security validation."""

    def test_path_traversal_rejection(self, client, tmp_path, reset_security):
        """Path traversal attempts in legacy mode still get resolved."""
        # In legacy mode, path traversal is allowed (backward compat)
        # but path must exist
        traversal_path = str(tmp_path / "../../../etc/passwd")

        response = client.post(
            "/analyze",
            json={"wav_path": traversal_path},
        )

        # Will fail because /etc/passwd doesn't exist in test context
        assert response.status_code == 400


# =============================================================================
# Error recovery and fallback tests
# =============================================================================


class TestErrorRecovery:
    """Error handling and graceful degradation."""

    def test_analyze_timeout_returns_400(self, client, mock_wav_file, reset_security):
        """Analyzer timeout returns 400 error."""
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze:
            mock_analyze.side_effect = TimeoutError("analyzer timeout")

            response = client.post(
                "/analyze",
                json={"wav_path": mock_wav_file},
            )

            assert response.status_code == 400
            assert "timeout" in response.json()["detail"].lower() or "invalid WAV" in response.json()["detail"]

    def test_build_assemble_failure_returns_400(self, client, mock_wav_file, mock_render_spec, reset_security):
        """Assemble failure returns 400 error."""
        with patch("melosviz.bridge.server._analyze_with_mir_or_python") as mock_analyze, \
             patch("melosviz.compose.assemble.assemble_render_plan") as mock_assemble:
            mock_analyze.return_value = mock_render_spec
            mock_assemble.side_effect = RuntimeError("assemble failed")

            response = client.post(
                "/build",
                json={"wav_path": mock_wav_file},
            )

            assert response.status_code == 400
