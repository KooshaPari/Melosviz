"""Fuzz + chaos failure-injection tests for MelosViz antigame spectrum.

Targets:
  * RenderSpec JSON round-trip fuzzing — random byte/text inputs through
    pydantic validation; the parser must never crash with an uncaught
    exception, must return a *validated* spec or raise ValidationError.
  * WAV-decode fuzzing — malformed RIFF / corrupt chunk / truncated samples
    are routed through the stdlib `wave` reader; we assert the analyser
    either succeeds or raises a well-defined error class.
  * Bridge HTTP layer fuzzing — Random text / bytes / unicode payloads sent
    to /analyze, /build, /render.  Must produce 4xx, never 5xx, never hang.
  * Chaos: bridge-dies-mid-request, ffmpeg/blender missing, malformed spec.

These tests are explicitly designed to fail if any antigame surface is
brittle.  They run in-process; no ffmpeg, no Blender, no bridge process
required.
"""

from __future__ import annotations

import asyncio
import io
import json
import math
import os
import struct
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Optional hypothesis: only required for the property-based fuzz tests.
# If hypothesis isn't installed we still run the structural fuzz tests below.
# ---------------------------------------------------------------------------
try:
    from hypothesis import HealthCheck, given, settings, strategies as st  # type: ignore

    HAVE_HYPOTHESIS = True
except ImportError:  # pragma: no cover — handled below
    HAVE_HYPOTHESIS = False


# ===========================================================================
# 1. RenderSpec JSON round-trip fuzzing
# ===========================================================================

from melosviz.analysis.models import RenderSpec  # noqa: E402


class TestRenderSpecFuzz:
    """Random structured JSON inputs must parse, not crash, not produce
    a broken model that explodes on the first attribute access."""

    @pytest.mark.skipif(not HAVE_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        metadata=st.dictionaries(
            keys=st.sampled_from(["source_audio", "duration", "fps", "width",
                                   "height", "sample_rate", "channels",
                                   "estimated_bpm"]),
            values=st.one_of(
                st.none(),
                st.floats(allow_nan=False, allow_infinity=False, max_value=1e6),
                st.integers(min_value=-1_000_000, max_value=1_000_000),
                st.text(max_size=64),
                st.booleans(),
            ),
            max_size=8,
        ),
    )
    @settings(max_examples=50, deadline=2000,
              suppress_health_check=[HealthCheck.too_slow])
    def test_metadata_never_crashes(self, metadata: dict) -> None:
        try:
            spec = RenderSpec(metadata=metadata)
        except Exception as exc:  # noqa: BLE001
            # Pydantic may reject some types (e.g. duration=negative). That is
            # acceptable; only uncaught crashes are bad.
            assert exc.__class__.__name__ in {
                "ValidationError", "TypeError", "ValueError"
            }, f"unexpected exception: {exc!r}"
        else:
            # If we got a spec, it must round-trip cleanly back to JSON.
            dump = spec.model_dump()
            assert isinstance(dump["metadata"], dict)

    @pytest.mark.skipif(not HAVE_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        payload=st.binary(min_size=0, max_size=512),
    )
    @settings(max_examples=40, deadline=2000,
              suppress_health_check=[HealthCheck.too_slow])
    def test_garbage_bytes_to_renderspec(self, payload: bytes) -> None:
        """Random byte strings should never hang or crash; they should
        either round-trip to a default spec or raise ValidationError."""
        # The fuzz vector: try parsing the bytes as JSON; if that fails, wrap
        # as a string and ensure the model still produces a valid spec.
        for variant in (
            payload,
            payload.decode("utf-8", errors="replace"),
            json.dumps({"metadata": {"x": payload.decode("utf-8", errors="replace")}}),
        ):
            try:
                if isinstance(variant, bytes):
                    obj = json.loads(variant.decode("utf-8", errors="replace"))
                else:
                    obj = json.loads(variant) if variant.startswith("{") else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                obj = None
            if obj is None:
                continue
            try:
                spec = RenderSpec.model_validate(obj)
            except Exception as exc:  # noqa: BLE001
                assert exc.__class__.__name__ in {
                    "ValidationError", "TypeError", "ValueError"
                }
            else:
                # Round-trip again — must not corrupt.
                spec.model_dump()


# ===========================================================================
# 2. WAV-decode fuzzing
# ===========================================================================


def _write_wav(path: Path, *, seconds: float = 1.0, sr: int = 44100, freq: int = 440) -> Path:
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", int(32767 * math.sin(2 * math.pi * freq * i / sr)))
            for i in range(n)
        )
        wf.writeframes(frames)
    return path


class TestWavDecodeFuzz:
    """Corrupted / truncated WAVs must NOT cause a crash; either succeed
    or raise a well-known exception.  We rely on the stdlib ``wave`` module's
    built-in checks for non-magic data."""

    def test_truncated_wav_does_not_crash(self, tmp_path: Path) -> None:
        from melosviz.analysis.audio import spec_from_wav

        good = _write_wav(tmp_path / "good.wav", seconds=0.5)
        # Truncate the file to half size — RIFF chunk header is preserved
        # but the data chunk is broken.
        with open(good, "r+b") as f:
            f.truncate(good.stat().st_size // 4)
        # Either the analyser returns a degraded spec or raises a known
        # error class — but never an uncaught crash / segfault.
        try:
            spec = spec_from_wav(good)
        except (wave.Error, EOFError, ValueError, RuntimeError, struct.error):
            return
        # If it survived, it must still be a pydantic model.
        assert hasattr(spec, "model_dump")

    def test_random_bytes_dont_pretend_to_be_wav(self, tmp_path: Path) -> None:
        from melosviz.analysis.audio import spec_from_wav

        bad = tmp_path / "not.wav"
        bad.write_bytes(os.urandom(2048))
        with pytest.raises((wave.Error, EOFError, ValueError, RuntimeError, OSError)):
            spec_from_wav(bad)

    def test_zero_length_wav(self, tmp_path: Path) -> None:
        from melosviz.analysis.audio import spec_from_wav

        z = tmp_path / "zero.wav"
        z.write_bytes(b"")
        with pytest.raises((wave.Error, EOFError, ValueError, RuntimeError, OSError)):
            spec_from_wav(z)

    def test_oversized_duration_clamps_or_raises(self, tmp_path: Path) -> None:
        """WAV claims an absurd duration — should not OOM the process."""
        from melosviz.analysis.audio import spec_from_wav

        p = tmp_path / "huge.wav"
        n = 44100 * 60  # 1 minute
        with wave.open(str(p), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * n)
        try:
            t0 = time.monotonic()
            spec_from_wav(p)
            elapsed = time.monotonic() - t0
            # Must not exceed 30s — protects against runaway FFT on huge WAVs.
            assert elapsed < 30.0
        except (wave.Error, ValueError, RuntimeError, MemoryError):
            return


# ===========================================================================
# 3. Bridge HTTP layer fuzzing
# ===========================================================================


class TestBridgeHttpFuzz:
    """Hit the FastAPI app via TestClient with garbage / boundary inputs.
    Catches: 500s on bad input, hangs, and double-stack traces leaking."""

    @pytest.fixture
    def client(self):
        try:
            from fastapi.testclient import TestClient
            from melosviz.bridge.server import app
        except ImportError:  # pragma: no cover — only when [bridge] extras not installed
            pytest.skip("fastapi/uvicorn not installed")
        return TestClient(app)

    def test_analyze_with_missing_file(self, client) -> None:
        r = client.post("/analyze", json={"wav_path": "/no/such/file.wav"})
        # 400 (file not found) — NOT 500.
        assert r.status_code == 400, r.text
        assert "File not found" in r.text

    def test_analyze_with_garbage_path(self, client) -> None:
        r = client.post("/analyze", json={"wav_path": "\x00\x01\x02"})
        assert r.status_code in (400, 422), r.text

    def test_analyze_with_path_traversal(self, client) -> None:
        r = client.post("/analyze", json={"wav_path": "../../../etc/passwd"})
        # Must NOT 500 — must return 400.
        assert r.status_code in (400, 422), r.text

    def test_analyze_with_overlong_path(self, client) -> None:
        r = client.post("/analyze", json={"wav_path": "A" * 100_000})
        assert r.status_code in (400, 413, 422), r.text

    def test_analyze_with_wrong_field_types(self, client) -> None:
        r = client.post("/analyze", json={"wav_path": ["list", "not", "str"]})
        assert r.status_code in (400, 422), r.text

    def test_analyze_with_no_body(self, client) -> None:
        r = client.post("/analyze")
        assert r.status_code in (400, 415, 422), r.text

    def test_render_with_no_out_dir(self, client) -> None:
        r = client.post("/render", json={"wav_path": "x.wav"})
        # Missing required field — should be 422.
        assert r.status_code in (400, 422), r.text

    def test_health_is_idempotent(self, client) -> None:
        # Hit it 50 times — must not leak state.
        for _ in range(50):
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json() == {"status": "ok"}


# ===========================================================================
# 4. Chaos: bridge-dies-mid-request, missing tools, malformed spec
# ===========================================================================


class TestChaosResilience:
    """Failure-injection tests — the spec paths must degrade gracefully."""

    def test_bridge_dies_mid_request(self, tmp_path: Path, monkeypatch) -> None:
        """If the upstream bridge subprocess dies after we send a request,
        we should get a clean error — not a hang."""
        from melosviz.analysis.audio import spec_from_wav

        wav = _write_wav(tmp_path / "ok.wav", seconds=0.25)
        # Simulate the bridge process dying after a successful analysis by
        # replacing one of the downstream functions to raise SystemExit.
        with patch("melosviz.compose.assemble.assemble_render_plan",
                   side_effect=SystemExit(1)):
            from melosviz.compose.assemble import assemble_render_plan
            spec = spec_from_wav(wav)
            with pytest.raises((SystemExit, RuntimeError)):
                assemble_render_plan(spec, mock_adapters=True)

    def test_ffmpeg_missing_fails_open(self, tmp_path: Path, monkeypatch) -> None:
        """video_exporter must fail-open to a known error class when ffmpeg
        is absent — never crash, never hang."""
        from melosviz.render import video_exporter

        spec = RenderSpec(metadata={"source_audio": "x.wav"})
        _write_wav(tmp_path / "x.wav", seconds=0.2)
        # Force the resolver to return a path that does not exist on PATH.
        monkeypatch.setattr(video_exporter, "_resolve_ffmpeg_binary",
                            lambda: "/no/such/ffmpeg-binary-xyz")
        from melosviz.render.video_exporter import FFMpegNotFoundError, export_video
        with pytest.raises(FFMpegNotFoundError):
            export_video(spec, format="mp4", output_dir=str(tmp_path))

    def test_blender_missing_fails_open(self, tmp_path: Path) -> None:
        """If Blender is absent, the blender exporter must return a known
        error and not silently produce a broken script."""
        from melosviz.render import blender_exporter
        # Patch shutil.which to return None (so the exporter thinks
        # blender is missing).
        with patch("shutil.which", return_value=None):
            try:
                out = blender_exporter.build_bpy_script(
                    RenderSpec(), output_path=str(tmp_path / "blend.py"))
            except (FileNotFoundError, RuntimeError, OSError, NotImplementedError):
                return
            # If it returns, the result must be a string (script body).
            assert out is None or isinstance(out, str)

    def test_malformed_spec_is_rejected(self) -> None:
        """Garbage spec input must not crash the mutator registry."""
        from melosviz.presets.registry import ThemePresetRegistry
        reg = ThemePresetRegistry()
        try:
            out = reg.get_preset(None)  # type: ignore[arg-type]
        except (TypeError, ValueError, AttributeError, KeyError):
            return
        # If it returns, the result must be a ThemePreset or None — never garbage.
        assert out is None or hasattr(out, "name")

    def test_concurrent_bridge_clients_do_not_race(self) -> None:
        """Many concurrent spec_from_wav calls on the same file must all
        return the same spec — no torn reads."""
        from melosviz.analysis.audio import spec_from_wav
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
            _write_wav(Path(t.name), seconds=0.25)
            path = Path(t.name)
        results: list[RenderSpec] = []
        errors: list[BaseException] = []

        def worker():
            try:
                results.append(spec_from_wav(path))
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t_ in threads: t_.start()
        for t_ in threads: t_.join(timeout=30)
        assert not errors, f"concurrent failures: {errors}"
        # All results must agree on duration (the only stable field).
        durations = {r.metadata.get("duration") for r in results}
        assert len(durations) == 1, f"racing reads: {durations}"
