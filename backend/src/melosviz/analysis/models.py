"""Core analysis data models.

This module is intentionally small: it only contains the dataclass-style
models that the rest of the package re-uses — most prominently
:class:`RenderSpec`, the mutable spec consumed by the preset mutators in
:mod:`melosviz.presets` and by the FFmpeg-backed exporter in
:mod:`melosviz.render.video_exporter`.

The rest of the upstream analysis pipeline (audio decoding, BPM
detection, frequency/waveform features, note extraction) lives in
separate, optional modules that are deliberately not imported here so
this file stays usable in minimal environments (CI smoke tests, the
FFmpeg wrapper, etc.) that don't pull in numpy / scipy / librosa.

RenderSpec v2 — shared renderer-agnostic contract
--------------------------------------------------
v2 extends v1 with rich audio-semantic fields consumed by every downstream
renderer (Blender, After Effects, Unreal, TouchDesigner, the built-in
FFmpeg exporter). All v2 fields default to empty/None so existing callers
that only set v1 fields continue to work unchanged.

JSON schema overview (renderer-agnostic contract)::

    {
      "metadata": {
        "source_audio": "/path/to/track.wav",
        "duration": 210.5,
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "sample_rate": 44100,
        "channels": 2,
        "estimated_bpm": 128.0,
        "analysis_peak_rms": 0.87,
        "amplitude_envelope": [0.1, 0.4, ...]   // 120-bucket legacy
      },
      "palette": ["#00f5ff", "#ff2fd5", "#8a75ff"],
      "layers": [...],
      "keyframes": [...],   // v1 sparse; v2 dense_keyframes preferred
      "timeline": [...],

      // --- RenderSpec v2 additions ---

      "dense_keyframes": [
        {
          "t": 0.033,
          "energy": 0.72,
          "brightness": 0.55,
          "valence": 0.6,
          "arousal": 0.8,
          "beat_strength": 0.0,
          "onset_strength": 0.3,
          "spectral_centroid": 3200.0,
          "stems": {
            "drums": 0.9,
            "bass": 0.6,
            "vocals": 0.2,
            "other": 0.3
          },
          "easing": "ease_in_out"
        },
        ...
      ],

      "timeline_events": [
        {"t": 0.0,    "type": "beat",      "strength": 0.8},
        {"t": 0.0,    "type": "downbeat",  "bar": 1},
        {"t": 1.024,  "type": "onset",     "strength": 0.6},
        {"t": 32.0,   "type": "section",   "label": "drop",
         "segment_index": 1, "confidence": 0.9}
      ],

      "scene_segments": [
        {
          "index": 0,
          "label": "intro",
          "start": 0.0,
          "end": 32.0,
          "energy_mean": 0.3,
          "brightness_mean": 0.4,
          "mood": {"valence": 0.5, "arousal": 0.4},
          "dominant_stem": "other"
        },
        ...
      ],

      "stem_channels": {
        "drums":  [0.9, 0.1, 0.8, ...],  // per-frame energy, len=total_frames
        "bass":   [...],
        "vocals": [...],
        "other":  [...]
      },

      "mir": {
        "tempo_bpm": 128.0,
        "tempo_curve": [128.0, 128.5, ...],   // per-beat
        "danceability": 0.85,
        "energy_trajectory": [0.3, 0.5, ...], // per-second
        "brightness_trajectory": [0.4, 0.6, ...],
        "valence_trajectory": [0.5, 0.6, ...],
        "arousal_trajectory": [0.7, 0.8, ...],
        "key": "C",
        "mode": "major",
        "chord_sequence": [
          {"t": 0.0, "chord": "Cmaj", "confidence": 0.9},
          ...
        ]
      }
    }
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GenreTheme(str, Enum):
    """Coarse visual style buckets used by the legacy theme registry."""

    DARK_STREET = "dark_street"
    CLASSY = "classy"
    ENERGETIC = "energetic"
    AMBIENT = "ambient"
    CHILLOUT = "chillout"
    RETRO_DISCO = "retro_disco"
    URBAN = "urban"
    EUPHORIA = "euphoria"


class ThemePreset(BaseModel):
    """A curated, read-only visual preset (colour palette + motion hints)."""

    id: str
    name: str
    colors: list[str]
    glow_color: str
    geometry: str
    mood: str
    notes: str = ""


# ---------------------------------------------------------------------------
# RenderSpec v2 sub-models — used as typed helpers but stored as plain dicts
# in RenderSpec for maximum renderer compatibility (JSON round-trips cleanly,
# Blender/AE/Unreal/TD can deserialise without the Python classes).
# ---------------------------------------------------------------------------


class StemFrame(BaseModel):
    """Per-stem energy values at a single dense-keyframe time step."""

    drums: float = 0.0
    bass: float = 0.0
    vocals: float = 0.0
    other: float = 0.0


class DenseKeyframe(BaseModel):
    """Rich, renderer-agnostic keyframe at time ``t`` (seconds).

    Generated at 10–30 Hz so downstream animators (Blender NLA, AE
    graph editor, Unreal Sequencer, TD CHOP) can drive parameters
    directly from the sampled values without re-interpolating.

    Fields
    ------
    t:
        Time offset in seconds from the start of the track.
    energy:
        Normalised RMS energy [0, 1].
    brightness:
        Spectral centroid proxy, normalised [0, 1].
    valence:
        Estimated valence (positive/negative sentiment) [0, 1].
    arousal:
        Estimated arousal (calm/excited) [0, 1].
    beat_strength:
        Beat confidence at this frame [0, 1].  Non-zero only on beat frames.
    onset_strength:
        Onset detection function value, normalised [0, 1].
    spectral_centroid:
        Raw spectral centroid in Hz (useful for freq-mapped visuals).
    stems:
        Per-stem energy channel values [0, 1].
    easing:
        Suggested easing hint for the *following* keyframe interval.
        Consumers are free to ignore; defaults to ``"linear"``.
    """

    t: float
    energy: float = 0.0
    brightness: float = 0.0
    valence: float = 0.5
    arousal: float = 0.5
    beat_strength: float = 0.0
    onset_strength: float = 0.0
    spectral_centroid: float = 0.0
    stems: StemFrame = Field(default_factory=StemFrame)
    easing: str = "linear"


class TimelineEvent(BaseModel):
    """A discrete musical event on the shared timeline.

    ``type`` is one of ``"beat"``, ``"downbeat"``, ``"onset"``,
    ``"section"``, ``"drop"``, ``"bridge"``.
    Extra fields (e.g. ``bar``, ``segment_index``, ``label``) are allowed
    via ``extra="allow"`` so callers can annotate without subclassing.
    """

    t: float
    type: str
    strength: float = 1.0

    model_config = {"extra": "allow", "frozen": False}


class MoodVector(BaseModel):
    """Valence + arousal at a segment level."""

    valence: float = 0.5
    arousal: float = 0.5


class SceneSegment(BaseModel):
    """A semantically-classified scene segment (not a fixed time %).

    ``label`` is one of ``"intro"``, ``"verse"``, ``"chorus"``,
    ``"drop"``, ``"bridge"``, ``"breakdown"``, ``"outro"``, ``"unknown"``.
    The label is derived from real audio novelty / structural features,
    NOT from fixed time ratios.
    """

    index: int
    label: str
    start: float
    end: float
    energy_mean: float = 0.0
    brightness_mean: float = 0.0
    mood: MoodVector = Field(default_factory=MoodVector)
    dominant_stem: str = "other"

    model_config = {"extra": "allow", "frozen": False}


class MIRSummary(BaseModel):
    """Music-information-retrieval semantic summary for the full track.

    All trajectory lists are per-second unless noted.
    """

    tempo_bpm: float | None = None
    # Per-beat tempo estimates (useful for rubato / tempo-mapped visuals).
    tempo_curve: list[float] = Field(default_factory=list)
    danceability: float | None = None
    # Per-second trajectories — index i = second i of the track.
    energy_trajectory: list[float] = Field(default_factory=list)
    brightness_trajectory: list[float] = Field(default_factory=list)
    valence_trajectory: list[float] = Field(default_factory=list)
    arousal_trajectory: list[float] = Field(default_factory=list)
    key: str | None = None
    mode: str | None = None
    # Chord sequence: [{"t": float, "chord": str, "confidence": float}]
    chord_sequence: list[dict[str, Any]] = Field(default_factory=list)


class RenderSpec(BaseModel):
    """A mutable, renderer-agnostic render description.

    v1 fields (``metadata``, ``palette``, ``layers``, ``keyframes``,
    ``timeline``) are unchanged — all existing callers and preset mutators
    continue to work.

    v2 fields add rich audio semantics: dense keyframes (10–30 Hz),
    structured timeline events, semantically-classified scene segments,
    per-stem energy channels, and a full MIR summary.  All v2 fields
    default to empty/None so the upgrade is fully backward-compatible.

    The model serialises to/from JSON cleanly (via ``.model_dump()`` /
    ``.model_validate()``), making it consumable by Blender bpy scripts,
    AE/nexrender JSON pipelines, Unreal Python/Sequencer, and
    TouchDesigner Python callbacks without importing this module.
    """

    # ---- v1 fields (unchanged) ----------------------------------------
    metadata: dict[str, Any] = Field(default_factory=dict)
    palette: list[str] = Field(default_factory=list)
    layers: list[Any] = Field(default_factory=list)
    keyframes: list[Any] = Field(default_factory=list)
    timeline: list[Any] = Field(default_factory=list)

    # ---- v2 fields -------------------------------------------------------
    # Dense keyframes at 10–30 Hz; stored as plain dicts for JSON compat.
    # Use DenseKeyframe.model_validate(kf) to get a typed view.
    dense_keyframes: list[dict[str, Any]] = Field(default_factory=list)
    # Structured timeline events (beats, downbeats, onsets, sections).
    timeline_events: list[dict[str, Any]] = Field(default_factory=list)
    # Semantically-classified scene segments.
    scene_segments: list[dict[str, Any]] = Field(default_factory=list)
    # Per-stem energy channels: {"drums": [f, ...], "bass": [...], ...}
    # Each list has one float per dense keyframe (aligned with dense_keyframes).
    stem_channels: dict[str, list[float]] = Field(default_factory=dict)
    # Full-track MIR summary; stored as a dict for JSON compat.
    # Use MIRSummary.model_validate(spec.mir) to get a typed view.
    mir: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "ignore",
        "frozen": False,
    }
