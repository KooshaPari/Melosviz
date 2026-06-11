"""Tests for melosviz pydantic models."""

from melosviz.analysis.models import (
    AnalyzeRequest,
    BPMResult,
    GenreTheme,
    VisualizeRequest,
)


def test_enum_values_are_valid() -> None:
    assert GenreTheme.DARK_STREET.value == "dark_street"
    assert GenreTheme.CLASSY.value == "classy"
    assert GenreTheme.ENERGETIC.value == "energetic"
    assert GenreTheme.AMBIENT.value == "ambient"
    assert GenreTheme.CHILLOUT.value == "chillout"
    assert GenreTheme.RETRO_DISCO.value == "retro_disco"
    assert GenreTheme.URBAN.value == "urban"
    assert GenreTheme.EUPHORIA.value == "euphoria"


def test_analyze_request_validation() -> None:
    request = AnalyzeRequest(window_ms=250, fft_size=2048, hop_size=512)
    assert request.window_ms == 250
    assert request.analysis.value == "full"


def test_bpm_result_confidence_bounds() -> None:
    result = BPMResult(
        bpm=124.0,
        confidence=0.72,
        beat_positions=[0.1, 0.5, 0.9],
        stability=0.86,
    )
    assert 0.0 <= result.confidence <= 1.0
    assert 0.0 <= result.stability <= 1.0


def test_visualize_request_defaults() -> None:
    request = VisualizeRequest(source_file="audio.wav")
    assert request.model == "default"
    assert request.fps == 30
    assert request.width == 1920
    assert request.height == 1080
