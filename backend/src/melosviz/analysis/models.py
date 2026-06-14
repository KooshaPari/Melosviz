"""Pydantic models used by Melosviz."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class AudioFormat(str, Enum):
    """Supported audio formats for analysis input."""

    WAV = "wav"
    MP3 = "mp3"
    FLAC = "flac"
    OGG = "ogg"
    M4A = "m4a"
    AAC = "aac"


class AnalysisType(str, Enum):
    """Analysis output modes supported by the engine."""

    BPM = "bpm"
    WAVEFORM = "waveform"
    FREQUENCY = "frequency"
    FULL = "full"


class GenreTheme(str, Enum):
    """Visual preset theme names."""

    DARK_STREET = "dark_street"
    CLASSY = "classy"
    ENERGETIC = "energetic"
    AMBIENT = "ambient"
    CHILLOUT = "chillout"
    RETRO_DISCO = "retro_disco"
    URBAN = "urban"
    EUPHORIA = "euphoria"


class AnalyzeRequest(BaseModel):
    """Input payload controlling analysis behavior."""

    model: str = Field(default="default", description="Model selector used by the API.")
    analysis: AnalysisType = Field(default=AnalysisType.FULL)
    include_waveform: bool = Field(default=True)
    include_spectrum: bool = Field(default=True)
    include_bpm: bool = Field(default=True)
    genre: GenreTheme = Field(default=GenreTheme.DARK_STREET)
    theme: Optional[GenreTheme] = Field(default=None)
    window_ms: int = Field(default=2000, ge=0, le=60000)
    fft_size: int = Field(default=2048, ge=256, le=16384)
    hop_size: int = Field(default=512, ge=128, le=8192)

    @model_validator(mode="after")
    def _validate_fft(self) -> "AnalyzeRequest":
        if self.hop_size >= self.fft_size:
            raise ValueError("hop_size must be smaller than fft_size for spectral analysis")
        return self


class BPMResult(BaseModel):
    """Result from tempo and beat extraction."""

    bpm: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1.0)
    beat_positions: List[float] = Field(default_factory=list)
    downbeat_positions: List[float] = Field(default_factory=list)
    onset_positions: List[float] = Field(default_factory=list)
    stability: float = Field(default=0.0)
    method: str = Field(default="librosa.beat.beat_track")


class TimelineEvent(BaseModel):
    """A single timed event in the visual timeline."""

    time: float = Field(default=0.0, ge=0, description="Time in seconds from start of track")
    type: str = Field(description="Event type: section, shot_change, overlay, camera_move, etc.")
    data: Dict[str, Any] = Field(default_factory=dict, description="Typed payload for the event")


class WaveformResult(BaseModel):
    """Summary data of normalized waveform peaks."""

    samples: List[float] = Field(default_factory=list)
    peak_amplitude: float = Field(ge=0)
    rms_db: float
    duration: float = Field(gt=0)
    sample_rate: int = Field(gt=0)


class FrequencyResult(BaseModel):
    """Frequency-domain analysis summary."""

    peak_frequency_hz: float = Field(ge=0)
    spectral_centroid: float = Field(default=0.0)
    spectral_rolloff: float = Field(default=0.0)
    spectral_flatness: float = Field(default=0.0)
    dominant_bins: Dict[str, float] = Field(default_factory=dict)
    spectrogram: Optional[List[List[float]]] = Field(default=None)


class AnalysisResult(BaseModel):
    """Aggregate analysis result for one audio input."""

    duration_seconds: float = Field(ge=0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    analysis: AnalysisType
    bpm: Optional[BPMResult] = Field(default=None)
    waveform: Optional[WaveformResult] = Field(default=None)
    frequency: Optional[FrequencyResult] = Field(default=None)


class Note(BaseModel):
    """A single MIDI note extracted from a track.

    Times are stored in seconds. The ``pitch`` field follows the MIDI
    convention (0-127) where 60 is middle C. ``velocity`` uses the MIDI
    convention (1-127 for audible notes; 0 typically indicates a note-off).
    """

    pitch: int = Field(ge=0, le=127, description="MIDI note number (0-127)")
    start: float = Field(ge=0, description="Onset time in seconds from start of track")
    duration: float = Field(ge=0, description="Note length in seconds")
    velocity: int = Field(
        default=80,
        ge=0,
        le=127,
        description="MIDI velocity (0-127); 0 is treated as note-off by convention",
    )


class NoteStream(BaseModel):
    """A flat sequence of :class:`Note` objects extracted from a MIDI file.

    Tracks are merged in file order. Notes are sorted by ``(start, pitch)``
    for deterministic downstream rendering.
    """

    notes: List[Note] = Field(default_factory=list, description="All notes in the stream")
    source_path: Optional[str] = Field(
        default=None, description="Origin MIDI file path, if known"
    )
    ticks_per_beat: int = Field(
        default=480, ge=1, description="PPQ resolution from the source file header"
    )

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.notes)

    def __iter__(self):  # pragma: no cover - trivial
        return iter(self.notes)


class CameraState(BaseModel):
    """Camera transform used by shots and keyframes."""

    zoom: float = Field(default=0.0, ge=0)
    pan_x: float = Field(default=0.0)
    pan_y: float = Field(default=0.0)
    rotation: float = Field(default=0.0)


class ShotSpec(BaseModel):
    """Camera and visual spec for a single shot or scene."""

    id: str
    section: str = Field(default="")
    start_time: float = Field(default=0.0, ge=0)
    end_time: float = Field(default=0.0, ge=0)
    camera: CameraState = Field(default_factory=lambda: CameraState(zoom=1.0))
    transition_in: Dict[str, Any] = Field(default_factory=dict, description="How this shot transitions in")
    transition_out: Dict[str, Any] = Field(default_factory=dict, description="How this shot transitions out")
    overlay: List[Dict[str, Any]] = Field(default_factory=list, description="Overlay tracks: text, sprites, etc.")
    palette_shift: str = Field(default="", description="Color/shift over time")
    shot_type: str = Field(
        default="",
        description="Visual shot archetype (establishing, performance, anthem, etc.)",
    )
    motif: str = Field(default="", description="Scene motif key used by the renderer")
    beat_anchor: float = Field(default=0.0, ge=0, description="Beat-phase anchor [0,1) for this shot")
    energy_profile: List[float] = Field(
        default_factory=list,
        description="Energy samples (start, mid, end) clamped to [0, 1]",
    )
    movement: Dict[str, Any] = Field(
        default_factory=dict,
        description="Camera-movement descriptor (type, speed, pattern, beat_lock)",
    )
    cut_style: str = Field(default="", description="Canonical cut name for transitions")


class ThemePreset(BaseModel):
    """Metadata describing a render preset."""

    id: str
    name: str = Field(default="")
    colors: List[str] = Field(default_factory=list)
    glow_color: str = Field(default="")
    geometry: str = Field(default="")
    mood: str = Field(default="")
    notes: str = Field(default="")


class RenderStyle(BaseModel):
    """A rendering style descriptor from clients or presets."""

    template: str = Field(default="modern")
    colors: List[str] = Field(default_factory=list)
    motion: str = Field(default="balanced")
    contrast: str = Field(default="high")
    glass: bool = Field(default=True)
    xform: str = Field(default="dynamic")


class VisualizeRequest(BaseModel):
    """Input payload controlling visualization generation."""

    model: str = Field(default="default")
    source_file: str = Field(default="")
    analysis: AnalysisType = Field(default=AnalysisType.FULL)
    style: RenderStyle = Field(default_factory=RenderStyle)
    fps: int = Field(default=30, ge=1, le=120)
    width: int = Field(default=1920, ge=1)
    height: int = Field(default=1080, ge=1)
    duration_sec: float = Field(default=30.0, gt=0.0)
    export_format: str = Field(default="html")
    seed: int = Field(default=0)

    @field_validator("export_format", mode="before")
    @classmethod
    def _validate_export_format(cls, value: str, info: ValidationInfo) -> str:
        valid = frozenset({"webgl", "json", "html"})
        if value.lower() not in valid:
            raise ValueError(f"export_format must be one of {sorted(valid)}")
        return value


class RenderSpec(BaseModel):
    """Normalized render payload shared by API, UI, and exports."""

    metadata: Dict[str, Any] = Field(default_factory=dict)
    palette: List[str] = Field(default_factory=list)
    layers: List[Dict[str, Any]] = Field(default_factory=list)
    shots: List[ShotSpec] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    keyframes: List[Dict[str, Any]] = Field(default_factory=list)


class VisualizeResponse(BaseModel):
    """Structured visualization result used by both API and SDK clients."""

    status: str
    message: str
    analysis: AnalysisResult
    selected_theme: ThemePreset
    render: RenderSpec
    artifact_url: Optional[str] = Field(default=None)
    frame_count: int = Field(default=0, ge=0)
    duration_sec: float = Field(default=0.0)
