"""Aspect-ratio / delivery-target presets.

The MelosViz pipeline can deliver the same storyboard at any of these
ratios by simply re-running :func:`melosviz.llm.director.Director.storyboard`
with a different ``--aspect-ratio`` flag. Each preset encodes:

- a human-readable label (used by ``melosviz apply`` and the desktop UI)
- the canvas size (width × height, in pixels)
- the playback frame-rate
- a short note explaining when to use it

The same table is mirrored inside
:mod:`melosviz.llm.director` so the Director can set per-scene
``width`` / ``height`` / ``fps`` without importing the full preset
package (avoids circular imports in tests).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AspectRatioPreset:
    name: str
    label: str
    width: int
    height: int
    fps: int
    notes: str


DELIVERY_ASPECT_RATIOS: tuple[AspectRatioPreset, ...] = (
    AspectRatioPreset(
        name="festival_4k",
        label="3840×2160 16:9 24fps — festival/VJ screen",
        width=3840, height=2160, fps=24,
        notes="Use for festival main-stage IMAG, VJ booths, broadcast.",
    ),
    AspectRatioPreset(
        name="youtube_4k",
        label="3840×2160 16:9 30fps — YouTube 4K",
        width=3840, height=2160, fps=30,
        notes="Maximum-clarity YouTube premiere.",
    ),
    AspectRatioPreset(
        name="youtube_1080",
        label="1920×1080 16:9 24fps — YouTube / Vimeo",
        width=1920, height=1080, fps=24,
        notes="Default for the web release; cinema-like 24fps.",
    ),
    AspectRatioPreset(
        name="club_portrait",
        label="1080×1920 9:16 30fps — club floor portrait",
        width=1080, height=1920, fps=30,
        notes="DJ booth / club pillar / vertical LED stack.",
    ),
    AspectRatioPreset(
        name="social_vertical",
        label="1080×1920 9:16 30fps — IG Reels / TikTok / YT Shorts",
        width=1080, height=1920, fps=30,
        notes="Punchy hook in the first 3 seconds; safe-zone aware.",
    ),
    AspectRatioPreset(
        name="cinema_letterbox",
        label="2048×858 ~2.39:1 24fps — DCP letterbox",
        width=2048, height=858, fps=24,
        notes="DCI-compliant letterbox for festival film programs.",
    ),
    AspectRatioPreset(
        name="square_social",
        label="1080×1080 1:1 30fps — IG square / SoundCloud",
        width=1080, height=1080, fps=30,
        notes="Album-art-led square format; static-camera friendly.",
    ),
)


def aspect_ratio_by_name(name: str) -> AspectRatioPreset:
    """Look up an aspect-ratio preset by name (case-insensitive)."""
    key = name.strip().lower()
    for p in DELIVERY_ASPECT_RATIOS:
        if p.name == key:
            return p
    # Fallback to the default (youtube_1080).
    for p in DELIVERY_ASPECT_RATIOS:
        if p.name == "youtube_1080":
            return p
    raise RuntimeError("youtube_1080 default missing from DELIVERY_ASPECT_RATIOS")


def list_aspect_ratio_names() -> list[str]:
    return [p.name for p in DELIVERY_ASPECT_RATIOS]


__all__ = [
    "AspectRatioPreset",
    "DELIVERY_ASPECT_RATIOS",
    "aspect_ratio_by_name",
    "list_aspect_ratio_names",
]
