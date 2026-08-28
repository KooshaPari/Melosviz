"""Character sheet + registry primitives for character-consistent rendering.

A :class:`CharacterSheet` is the canonical, file-format-agnostic
description of a single recurring character in a music-video story
(dancer, vocalist, mascot, etc.). It carries both human-readable
metadata (name, description, prompts) and machine-actionable
references — one image per canonical reference slot (front,
three-quarter, profile, full-body, style).

A :class:`CharacterRegistry` is the in-memory collection of sheets
that the orchestrator threads through every render dispatch so the
adapter can swap in character-aware workflows (IP-Adapter-FaceID
or PuLID) wherever the user tagged a scene with a character name.

This module is intentionally engine-agnostic: it describes *what*
must be rendered and *which image* to use as the reference, but
the actual diffusion-graph wiring lives in
``melosviz.render.comfyui_adapter`` and the workflow JSON files
under ``backend/workflows/``.
"""

from __future__ import annotations

from melosviz.character.registry_io import (
    DEFAULT_IMAGE_EXTENSIONS,
    CharacterIOError,
    ENGINE_WORKFLOWS,
    load_registry,
    save_registry,
    save_sheet,
    workflow_for_engine,
)
from melosviz.character.sheet import (
    CHARACTER_IPADAPTER,
    CHARACTER_PULID,
    ENGINE_IPADAPTER,
    ENGINE_PULID,
    REFERENCE_FULL_BODY,
    REFERENCE_FRONT,
    REFERENCE_PROFILE,
    REFERENCE_SLOTS,
    REFERENCE_STYLE,
    REFERENCE_THREE_QUARTER,
    SUPPORTED_ENGINES,
    CharacterRegistry,
    CharacterSheet,
)

__all__ = [
    "CHARACTER_IPADAPTER",
    "CHARACTER_PULID",
    "DEFAULT_IMAGE_EXTENSIONS",
    "ENGINE_IPADAPTER",
    "ENGINE_PULID",
    "ENGINE_WORKFLOWS",
    "REFERENCE_FULL_BODY",
    "REFERENCE_FRONT",
    "REFERENCE_PROFILE",
    "REFERENCE_SLOTS",
    "REFERENCE_STYLE",
    "REFERENCE_THREE_QUARTER",
    "SUPPORTED_ENGINES",
    "CharacterIOError",
    "CharacterRegistry",
    "CharacterSheet",
    "load_registry",
    "save_registry",
    "save_sheet",
    "workflow_for_engine",
]