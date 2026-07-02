"""Unit tests for B7 MIR analyzer error paths in melosviz.bridge.server.

Covers fallback scenarios when Rust MIR binary is missing, fails, or both
analyzers are unavailable. Ensures graceful degradation and clear error
messages.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from melosviz.bridge.server import _analyze_with_mir_or_python


class TestAnalyzeWithMirOrPythonErrorPaths:
    """Error path coverage for MIR analyzer with Python fallback."""

    def test_mir_binary_missing_fallback_to_python(self):
        """When MIR binary doesn't exist, Python analyzer is invoked."""
        with patch.object(Path, "exists", return_value=False):
            with patch("melosviz.analysis.audio.spec_from_wav") as mock_spec:
                mock_spec.return_value = Mock(
                    model_dump=Mock(return_value={"frames": 100, "tempo": 120})
                )

                wav_path = Path("/tmp/test.wav")
                result = _analyze_with_mir_or_python(wav_path)

                assert result == {"frames": 100, "tempo": 120}
                mock_spec.assert_called_once_with(wav_path)

    def test_mir_subprocess_error_fallback_to_python(self):
        """When MIR subprocess fails, Python fallback is triggered."""
        with patch.object(Path, "exists", return_value=True):
            with patch("melosviz.bridge.server.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(1, "melosviz-mir")

                with patch("melosviz.analysis.audio.spec_from_wav") as mock_spec:
                    mock_spec.return_value = Mock(
                        model_dump=Mock(return_value={"frames": 200, "tempo": 130})
                    )

                    wav_path = Path("/tmp/test.wav")
                    result = _analyze_with_mir_or_python(wav_path)

                    assert result == {"frames": 200, "tempo": 130}
                    mock_spec.assert_called_once_with(wav_path)

    def test_mir_timeout_fallback_to_python(self):
        """When MIR subprocess times out, Python fallback is triggered."""
        with patch.object(Path, "exists", return_value=True):
            with patch("melosviz.bridge.server.subprocess.run") as mock_run:
                mock_run.side_effect = TimeoutError("MIR analyzer exceeded 120s")

                with patch("melosviz.analysis.audio.spec_from_wav") as mock_spec:
                    mock_spec.return_value = Mock(
                        model_dump=Mock(return_value={"frames": 150, "tempo": 125})
                    )

                    wav_path = Path("/tmp/test.wav")
                    result = _analyze_with_mir_or_python(wav_path)

                    assert result == {"frames": 150, "tempo": 125}

    def test_mir_json_decode_error_fallback_to_python(self):
        """When MIR output is malformed JSON, Python fallback is triggered."""
        with patch.object(Path, "exists", return_value=True):
            with patch("melosviz.bridge.server.subprocess.run"):
                with patch("builtins.open", create=True):
                    with patch("json.load") as mock_json_load:
                        mock_json_load.side_effect = json.JSONDecodeError(
                            "Expecting", "doc", 0
                        )

                        with patch("melosviz.analysis.audio.spec_from_wav") as mock_spec:
                            mock_spec.return_value = Mock(
                                model_dump=Mock(return_value={"fallback": True})
                            )

                            wav_path = Path("/tmp/test.wav")
                            result = _analyze_with_mir_or_python(wav_path)

                            assert result == {"fallback": True}

    def test_malformed_wav_input_python_error(self):
        """When input WAV is malformed, Python analyzer raises appropriate error."""
        with patch.object(Path, "exists", return_value=False):
            with patch("melosviz.analysis.audio.spec_from_wav") as mock_spec:
                mock_spec.side_effect = Exception(
                    "Invalid WAV file: missing RIFF header"
                )

                wav_path = Path("/tmp/corrupted.wav")
                with pytest.raises(Exception, match="Invalid WAV file"):
                    _analyze_with_mir_or_python(wav_path)

    def test_mir_success_returns_parsed_json(self):
        """When MIR succeeds, parsed JSON spec is returned."""
        expected_spec = {
            "frames": 4410,
            "sample_rate": 22050,
            "channels": 2,
            "tempo": 120.5,
            "onset_times": [0.0, 0.5, 1.0],
        }

        with patch.object(Path, "exists", return_value=True):
            with patch("melosviz.bridge.server.subprocess.run") as mock_run:
                with patch("builtins.open", create=True):
                    with patch("json.load") as mock_json_load:
                        mock_json_load.return_value = expected_spec

                        wav_path = Path("/tmp/test.wav")
                        result = _analyze_with_mir_or_python(wav_path)

                        assert result == expected_spec
                        mock_run.assert_called_once()

    def test_python_spec_model_dump_conversion(self):
        """When Python analyzer returns Pydantic model, model_dump is called."""
        with patch.object(Path, "exists", return_value=False):
            mock_spec_obj = Mock()
            mock_spec_obj.model_dump = Mock(
                return_value={"duration": 10.5, "peaks": []}
            )

            with patch("melosviz.analysis.audio.spec_from_wav") as mock_spec:
                mock_spec.return_value = mock_spec_obj

                wav_path = Path("/tmp/test.wav")
                result = _analyze_with_mir_or_python(wav_path)

                assert result == {"duration": 10.5, "peaks": []}
                mock_spec_obj.model_dump.assert_called_once()

    def test_python_dict_fallback_conversion(self):
        """When Python analyzer returns dict (no model_dump), use it directly."""
        expected_result = {"duration": 5.0, "tempo": 100}

        with patch.object(Path, "exists", return_value=False):
            with patch("melosviz.analysis.audio.spec_from_wav") as mock_spec:
                mock_spec.return_value = expected_result

                wav_path = Path("/tmp/test.wav")
                result = _analyze_with_mir_or_python(wav_path)

                assert result == expected_result
