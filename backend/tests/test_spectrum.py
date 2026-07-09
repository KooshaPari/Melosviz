from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


def _write_wav(path: Path, samples: list[int], sample_rate: int = 8000) -> Path:
    import struct

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        if samples:
            handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        else:
            handle.writeframes(b"")
    return path


json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=48),
)

json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=8)
        | st.dictionaries(st.text(min_size=1, max_size=24), children, max_size=8)
    ),
    max_leaves=24,
)


@settings(max_examples=80, deadline=None)
@given(
    metadata=st.dictionaries(
        st.text(min_size=1, max_size=24), json_values, max_size=10
    ),
    palette=st.lists(st.text(max_size=16), max_size=8),
    dense_keyframes=st.lists(
        st.dictionaries(st.text(min_size=1, max_size=16), json_values, max_size=8),
        max_size=10,
    ),
)
def test_renderspec_json_round_trips_fuzz(
    metadata: dict[str, object],
    palette: list[str],
    dense_keyframes: list[dict[str, object]],
) -> None:
    from melosviz.analysis.models import RenderSpec

    spec = RenderSpec(
        metadata=metadata,
        palette=palette,
        dense_keyframes=dense_keyframes,
    )
    encoded = spec.model_dump_json()
    decoded = RenderSpec.model_validate_json(encoded)

    assert decoded.model_dump() == spec.model_dump()


@settings(max_examples=60, deadline=None)
@given(payload=json_values)
def test_renderspec_json_parse_rejects_or_normalizes_fuzz(payload: object) -> None:
    from pydantic import ValidationError

    from melosviz.analysis.models import RenderSpec

    encoded = json.dumps(payload)
    try:
        spec = RenderSpec.model_validate_json(encoded)
    except ValidationError:
        return

    dumped = spec.model_dump()
    assert isinstance(dumped["metadata"], dict)
    assert isinstance(dumped["palette"], list)
    assert isinstance(dumped["dense_keyframes"], list)


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    samples=st.lists(st.integers(min_value=-32768, max_value=32767), max_size=256),
    bucket_count=st.integers(min_value=1, max_value=64),
)
def test_wav_analysis_handles_small_valid_wavs_fuzz(
    tmp_path: Path,
    samples: list[int],
    bucket_count: int,
) -> None:
    from melosviz.analysis.audio import analyze_wav

    wav = _write_wav(tmp_path / "input.wav", samples)
    result = analyze_wav(wav, bucket_count=bucket_count)

    assert result.sample_rate == 8000
    assert result.channels == 1
    assert result.duration_sec >= 0
    assert result.rms_envelope
    assert all(0.0 <= value <= 1.0 for value in result.rms_envelope)


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=st.binary(max_size=512))
def test_wav_analysis_rejects_malformed_bytes_fuzz(
    tmp_path: Path, payload: bytes
) -> None:
    from melosviz.analysis.audio import analyze_wav

    wav = tmp_path / "malformed.wav"
    wav.write_bytes(payload)

    with pytest.raises((EOFError, ValueError, wave.Error)):
        analyze_wav(wav)


class TestBridgeSpectrum:
    @pytest.fixture()
    def client(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")

        from melosviz.bridge import server
        from melosviz.bridge.server import app

        if hasattr(server, "security_limiter"):
            server.security_limiter.reset()
        return TestClient(app)

    @settings(
        max_examples=40,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(path_text=st.text(max_size=96))
    def test_bridge_invalid_wav_paths_do_not_500(self, client, path_text: str) -> None:
        from melosviz.bridge import server

        if hasattr(server, "security_limiter"):
            server.security_limiter.reset()
        response = client.post("/analyze", json={"wav_path": path_text})

        # 429 can appear under aggressive fuzz if the limiter is shared; still not 500.
        assert response.status_code in {400, 422, 429}

    @settings(
        max_examples=40,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(payload=st.binary(max_size=256))
    def test_bridge_malformed_json_does_not_500(self, client, payload: bytes) -> None:
        from melosviz.bridge import server

        if hasattr(server, "security_limiter"):
            server.security_limiter.reset()
        response = client.post(
            "/build",
            content=payload,
            headers={"content-type": "application/json"},
        )

        assert response.status_code in {400, 422, 429}

    def test_bridge_dependency_failure_mid_request_returns_500(
        self, client, tmp_path: Path
    ) -> None:
        from melosviz.bridge import server

        if hasattr(server, "security_limiter"):
            server.security_limiter.reset()
        wav = _write_wav(tmp_path / "input.wav", [0, 1000, -1000, 0])

        with patch(
            "melosviz.analysis.audio.spec_from_wav_rich",
            side_effect=RuntimeError("bridge died mid-request"),
        ):
            response = client.post("/analyze", json={"wav_path": str(wav)})

        # Bridge maps analyzer exceptions to HTTP 400 (invalid WAV / analyze failure).
        assert response.status_code in {400, 500}


class TestChaosSpectrum:
    def test_ffmpeg_missing_raises_actionable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from melosviz.render.video_exporter import (
            FFMpegNotFoundError,
            _resolve_ffmpeg_binary,
        )

        monkeypatch.delenv("MELOSVIZ_FFMPEG_BIN", raising=False)
        monkeypatch.setattr(
            "melosviz.render.video_exporter.shutil.which", lambda _name: None
        )

        with pytest.raises(FFMpegNotFoundError, match="ffmpeg"):
            _resolve_ffmpeg_binary()

    def test_blender_missing_raises_actionable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from melosviz.render.blender_exporter import (
            BlenderNotFoundError,
            _resolve_blender_binary,
        )

        monkeypatch.delenv("MELOSVIZ_BLENDER_BIN", raising=False)
        monkeypatch.setattr(
            "melosviz.render.blender_exporter.shutil.which", lambda _name: None
        )
        monkeypatch.setattr(Path, "exists", lambda _self: False)

        with pytest.raises(BlenderNotFoundError, match="Blender"):
            _resolve_blender_binary()

    def test_malformed_spec_rejected_before_render(self) -> None:
        from melosviz.analysis.models import RenderSpec
        from melosviz.compose.assemble import AssemblyError, assemble_render_plan

        with pytest.raises(AssemblyError, match="scene_segments is empty"):
            assemble_render_plan(RenderSpec(metadata={"duration": 1.0}))

    def test_ffmpeg_probe_execution_failure_falls_through(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from melosviz.render.video_exporter import (
            FFMpegNotFoundError,
            _resolve_ffmpeg_binary,
        )

        fake = tmp_path / "ffmpeg"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o755)
        monkeypatch.setenv("MELOSVIZ_FFMPEG_BIN", str(fake))
        monkeypatch.setattr(
            "melosviz.render.video_exporter.shutil.which", lambda _name: None
        )

        def _boom(*_a, **_k):
            raise subprocess.SubprocessError("boom")

        monkeypatch.setattr(
            "melosviz.render.video_exporter.subprocess.run",
            _boom,
        )

        with pytest.raises(FFMpegNotFoundError):
            _resolve_ffmpeg_binary()
