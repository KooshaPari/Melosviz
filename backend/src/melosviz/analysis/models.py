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


class RenderSpec(BaseModel):
    """A mutable description of a render.

    The preset mutators in :mod:`melosviz.presets` (e.g. ``cinematic.apply``)
    assign to these attributes directly, so the model is **not** frozen
    and the field types are kept loose (``dict`` / ``list``) so a preset
    can store arbitrary keyframes, timeline events, layer metadata, etc.
    """

    # Free-form renderer metadata (width / height / fps / duration / preset
    # hints). Kept as a plain dict so callers and presets can stash
    # implementation-defined keys without subclassing.
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Colour palette used to drive frame rendering, in ``#rrggbb`` form.
    palette: list[str] = Field(default_factory=list)
    # Renderer layers (shaders, particle systems, masks, etc.).
    layers: list[Any] = Field(default_factory=list)
    # Time-stamped keyframes that describe the render's motion.
    keyframes: list[Any] = Field(default_factory=list)
    # Time-stamped timeline events (sections, cues, transitions).
    timeline: list[Any] = Field(default_factory=list)

    model_config = {
        # Pydantic v2 default: extra fields are ignored. We do this so
        # downstream code that adds ad-hoc keys (e.g. ``spec.audio``)
        # doesn't blow up validation.
        "extra": "ignore",
        # RenderSpecs are mutated in place by preset mutators; we
        # therefore explicitly allow attribute assignment.
        "frozen": False,
    }
