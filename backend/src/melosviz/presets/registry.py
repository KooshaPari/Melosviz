"""Preset registry for Melosviz themes."""

from __future__ import annotations

from typing import Dict, List

from melosviz.analysis.models import GenreTheme, ThemePreset


class ThemePresetRegistry:
    """Container for all curated presets used by the API."""

    def __init__(self) -> None:
        self._presets: Dict[GenreTheme, ThemePreset] = {
            GenreTheme.DARK_STREET: ThemePreset(
                id="dark_street",
                name="Dark Street",
                colors=["#050505", "#120022", "#1B013A", "#00F5FF"],
                glow_color="#00F5FF",
                geometry="angular",
                mood="gritty",
                notes="A moody, urban palette with deep purple shadows and cyan neon edges.",
            ),
            GenreTheme.CLASSY: ThemePreset(
                id="classy",
                name="Classy",
                colors=["#07111F", "#102A43", "#B8860B", "#F8E0A0"],
                glow_color="#C9A93B",
                geometry="curves",
                mood="elegant",
                notes="Warm champagne accents with smooth spline-like geometry and restrained motion.",
            ),
            GenreTheme.ENERGETIC: ThemePreset(
                id="energetic",
                name="Energetic",
                colors=["#040404", "#FF2D95", "#FF6B00", "#00E5FF"],
                glow_color="#FF2D95",
                geometry="pulse",
                mood="driven",
                notes="High-energy geometry and quick transitions built around hot pink and electric orange.",
            ),
            GenreTheme.AMBIENT: ThemePreset(
                id="ambient",
                name="Ambient",
                colors=["#042D31", "#05384A", "#4C2A85", "#A39BFF"],
                glow_color="#8A75FF",
                geometry="organic",
                mood="meditative",
                notes="Teal and purple gradients with slow evolving organic flow for immersive passages.",
            ),
            GenreTheme.CHILLOUT: ThemePreset(
                id="chillout",
                name="Chillout",
                colors=["#081B2F", "#233A63", "#8D84FF", "#C8D2E5"],
                glow_color="#C8D2E5",
                geometry="waves",
                mood="gentle",
                notes="Lavender, silver and soft motion curves for minimal deep-night sets.",
            ),
            GenreTheme.RETRO_DISCO: ThemePreset(
                id="retro_disco",
                name="Retro Disco",
                colors=["#26001E", "#FF4FB8", "#AFAFAF", "#00B9FF"],
                glow_color="#FFD166",
                geometry="starburst",
                mood="playful",
                notes="Deep magenta core with chrome and rainbow accents, emphasizing radial starburst motifs.",
            ),
            GenreTheme.URBAN: ThemePreset(
                id="urban",
                name="Urban",
                colors=["#101010", "#232323", "#A8FF00", "#E6FF5C"],
                glow_color="#CFFF00",
                geometry="blocky",
                mood="raw",
                notes="Charcoal and high-contrast blocks with lime and neon-yellow spikes.",
            ),
            GenreTheme.EUPHORIA: ThemePreset(
                id="euphoria",
                name="Euphoria",
                colors=["#1B0040", "#7922FF", "#FF2FD5", "#00E8FF", "#FFB347"],
                glow_color="#FF2FD5",
                geometry="explosive",
                mood="anthemic",
                notes="Bold rainbow gradients and expanding forms designed for uplifting crowd energy.",
            ),
        }

    def get_preset(self, theme: GenreTheme) -> ThemePreset:
        return self._presets[theme]

    def get_all_presets(self) -> List[ThemePreset]:
        return list(self._presets.values())
