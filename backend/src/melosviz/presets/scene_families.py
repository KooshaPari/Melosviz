"""R3F scene-template families — preset-specific segment → look mapping.

Each preset selects a *family* of scene templates (geometry / camera language)
rather than only palette or motion metadata. Families are consumed by
:mod:`melosviz.compose.web_spec` when building shot keyframes for the browser
renderer and when preset ``apply()`` mutators remap ``scene_segments``.
"""

from __future__ import annotations

from typing import Any

# Canonical template ids shared with the web ``sceneTemplates`` module.
R3F_SCENE_TEMPLATES: tuple[str, ...] = (
    "wire_orb",
    "torus_flow",
    "crystal_burst",
    "ring_drift",
    "grid_depth",
    "octa_pulse",
)

# Default label → template (used when no preset family is active).
DEFAULT_LABEL_TEMPLATES: dict[str, str] = {
    "intro": "wire_orb",
    "verse": "torus_flow",
    "chorus": "crystal_burst",
    "drop": "octa_pulse",
    "bridge": "ring_drift",
    "breakdown": "ring_drift",
    "outro": "wire_orb",
    "unknown": "torus_flow",
}

# Preset families remap section labels to distinct template pools.
PRESET_SCENE_FAMILIES: dict[str, dict[str, str]] = {
    "cinematic": {
        "intro": "wire_orb",
        "verse": "grid_depth",
        "chorus": "crystal_burst",
        "drop": "octa_pulse",
        "bridge": "torus_flow",
        "breakdown": "ring_drift",
        "outro": "wire_orb",
        "unknown": "grid_depth",
    },
    "synthwave": {
        "intro": "grid_depth",
        "verse": "torus_flow",
        "chorus": "octa_pulse",
        "drop": "crystal_burst",
        "bridge": "ring_drift",
        "breakdown": "wire_orb",
        "outro": "grid_depth",
        "unknown": "torus_flow",
    },
    "lofi": {
        "intro": "ring_drift",
        "verse": "wire_orb",
        "chorus": "torus_flow",
        "drop": "torus_flow",
        "bridge": "ring_drift",
        "breakdown": "wire_orb",
        "outro": "ring_drift",
        "unknown": "wire_orb",
    },
    "minimal": {
        "intro": "wire_orb",
        "verse": "ring_drift",
        "chorus": "torus_flow",
        "drop": "crystal_burst",
        "bridge": "wire_orb",
        "breakdown": "ring_drift",
        "outro": "wire_orb",
        "unknown": "ring_drift",
    },
    "energetic": {
        "intro": "grid_depth",
        "verse": "torus_flow",
        "chorus": "octa_pulse",
        "drop": "crystal_burst",
        "bridge": "torus_flow",
        "breakdown": "ring_drift",
        "outro": "grid_depth",
        "unknown": "octa_pulse",
    },
    "ambient": {
        "intro": "ring_drift",
        "verse": "wire_orb",
        "chorus": "torus_flow",
        "drop": "crystal_burst",
        "bridge": "ring_drift",
        "breakdown": "wire_orb",
        "outro": "ring_drift",
        "unknown": "wire_orb",
    },
}

# Human-readable scene names for shot keyframes (screen reader + UI jumps).
TEMPLATE_DISPLAY_NAMES: dict[str, str] = {
    "wire_orb": "Establishing",
    "torus_flow": "Performance",
    "crystal_burst": "Anthem",
    "ring_drift": "Interlude",
    "grid_depth": "Horizon",
    "octa_pulse": "Pulse",
}


def family_for_preset(preset_name: str | None) -> dict[str, str]:
    """Return the label→template map for *preset_name*, or the default."""
    if not preset_name:
        return dict(DEFAULT_LABEL_TEMPLATES)
    key = preset_name.strip().lower()
    return dict(PRESET_SCENE_FAMILIES.get(key, DEFAULT_LABEL_TEMPLATES))


def template_for_label(label: str, family: dict[str, str]) -> str:
    """Resolve a section label to a scene template id."""
    return family.get(label, family.get("unknown", "torus_flow"))


def remap_scene_segments(
    scene_segments: list[dict[str, Any]],
    *,
    preset_name: str | None = None,
    family: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Assign ``scene_template`` to each segment; enforce adjacent uniqueness."""
    mapping = family or family_for_preset(preset_name)
    pool = list(R3F_SCENE_TEMPLATES)
    prev_template: str | None = None
    out: list[dict[str, Any]] = []

    for seg in scene_segments:
        seg_copy = dict(seg)
        label = str(seg_copy.get("label", "unknown"))
        preferred = template_for_label(label, mapping)
        template = preferred
        if prev_template is not None and template == prev_template:
            for alt in pool:
                if alt != prev_template:
                    template = alt
                    break
        seg_copy["scene_template"] = template
        seg_copy["scene"] = TEMPLATE_DISPLAY_NAMES.get(template, label.title())
        out.append(seg_copy)
        prev_template = template

    return out


__all__ = [
    "R3F_SCENE_TEMPLATES",
    "DEFAULT_LABEL_TEMPLATES",
    "PRESET_SCENE_FAMILIES",
    "TEMPLATE_DISPLAY_NAMES",
    "family_for_preset",
    "template_for_label",
    "remap_scene_segments",
]
