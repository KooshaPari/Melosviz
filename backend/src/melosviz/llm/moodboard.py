"""Mood-board palette + style extraction.

Lets a user drop 1-5 reference images and have the Director extract
the dominant palette and a coarse *style descriptor* to feed into
each scene prompt. This is how real music-video art directors work
— they pull a mood board together (frames from other videos,
photographs, fabric swatches, paintings) before storyboarding.

Public API
----------

* :func:`extract_palette`  — returns a list of hex colors (dominant → accent).
* :func:`style_descriptor` — returns a short style sentence (e.g.
  *"high-saturation neon, shallow DOF, 35mm grain"*).
* :func:`mood_board_summary` — convenience: extract both from a list
  of image paths.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "extract_palette",
    "style_descriptor",
    "mood_board_summary",
    "mood_board_from_env",
]


# Fallback palette per brightness/saturation profile — used when PIL
# isn't installed so the pipeline still works offline.
_FALLBACK_PALETTES: dict[str, list[str]] = {
    "neon":        ["#ff2bd6", "#22d3ee", "#0d0d10", "#f0f0f8"],
    "sunset":      ["#ff5e5b", "#f7b733", "#2c1810", "#fff1e6"],
    "forest":      ["#4f7942", "#1e3a1e", "#fff59d", "#708238"],
    "underwater":  ["#56e1ff", "#3f37c9", "#0a0a23", "#caf0f8"],
    "monochrome":  ["#0d0d10", "#708090", "#cfd8dc", "#f0f0f8"],
    "festival":    ["#ff2bd6", "#b6ff5c", "#ffd166", "#0d0d10"],
    "warm":        ["#ff8fa3", "#fff1e6", "#d4a017", "#a0522d"],
    "cold":        ["#708090", "#cfd8dc", "#3f37c9", "#0a0a23"],
}


def _try_pil_quantize(img_path: Path, n_colors: int = 5) -> list[tuple[int, tuple[int, int, int]]]:
    """Quantize image to N colors using PIL's median-cut.

    Returns list of (count, (r, g, b)) sorted by count desc.
    Empty list if PIL isn't available or image can't be read.
    """
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return []
    try:
        with Image.open(img_path) as im:
            im = im.convert("RGB").resize((128, 128))  # downsample for speed
            q = im.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
            palette = q.getpalette() or []
            counts = q.getcolors() or []
            # counts is list of (count, palette_index)
            out: list[tuple[int, tuple[int, int, int]]] = []
            for count, idx in sorted(counts, key=lambda c: -c[0]):
                base = idx * 3
                if base + 3 > len(palette):
                    continue
                rgb = (palette[base], palette[base + 1], palette[base + 2])
                out.append((count, rgb))
            return out
    except Exception as exc:
        logger.warning("mood_board: %s failed (%s) — using fallback", img_path.name, exc)
        return []


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def extract_palette(
    image_paths: list[str | Path],
    *,
    n_colors: int = 5,
) -> list[str]:
    """Extract a dominant-color palette from a list of images.

    Uses PIL's median-cut quantizer when available. Falls back to a
    keyword-matched default palette if PIL is missing or all images
    fail to load.
    """
    image_paths = [Path(p) for p in image_paths if p]
    if not image_paths:
        return []

    counts: dict[tuple[int, int, int], int] = {}
    for p in image_paths:
        if not p.exists():
            continue
        for c, rgb in _try_pil_quantize(p, n_colors):
            # Bucket to nearest 16 so we don't get 254,253,255 = 254,253,255
            bucketed = (rgb[0] & 0xF0, rgb[1] & 0xF0, rgb[2] & 0xF0)
            counts[bucketed] = counts.get(bucketed, 0) + c

    if not counts:
        return _fallback_for_paths(image_paths)

    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    hexes = [_rgb_to_hex(rgb) for rgb, _ in ranked[:n_colors]]
    return hexes


def style_descriptor(image_paths: list[str | Path]) -> str:
    """Return a short style sentence derived from the images.

    Reads average brightness/saturation via PIL when available; falls
    back to the path-stem keyword matching if not.
    """
    image_paths = [Path(p) for p in image_paths if p and Path(p).exists()]
    if not image_paths:
        return ""
    try:
        from PIL import Image, ImageStat  # type: ignore
    except ImportError:
        return _style_from_keyword(image_paths)

    brightness_vals: list[float] = []
    sat_vals: list[float] = []
    for p in image_paths:
        try:
            with Image.open(p) as im:
                im = im.convert("RGB").resize((64, 64))
                stat = ImageStat.Stat(im)
                r, g, b = (stat.mean[i] for i in range(3))
                brightness = (r + g + b) / (3 * 255)
                mx = max(r, g, b) or 1.0
                mn = min(r, g, b)
                sat = (mx - mn) / mx
                brightness_vals.append(brightness)
                sat_vals.append(sat)
        except Exception:
            continue
    if not brightness_vals:
        return _style_from_keyword(image_paths)

    brightness = sum(brightness_vals) / len(brightness_vals)
    sat = sum(sat_vals) / len(sat_vals)

    bits: list[str] = []
    if brightness < 0.25:
        bits.append("low-key")
    elif brightness > 0.75:
        bits.append("high-key")
    if sat > 0.5:
        bits.append("high-saturation")
    elif sat < 0.2:
        bits.append("desaturated")

    grain = "35mm grain" if brightness < 0.5 else "clean digital"
    bits.append(grain)
    if sat > 0.4:
        bits.append("punchy contrast")

    if not bits:
        bits.append("naturalistic")
    return ", ".join(bits)


def mood_board_summary(image_paths: list[str | Path]) -> dict:
    """Convenience: return ``{"palette": [...], "style": "..."}``."""
    return {
        "palette": extract_palette(image_paths),
        "style": style_descriptor(image_paths),
    }


def mood_board_from_env(env_var: str = "MELOSVIZ_MOOD_BOARD") -> dict:
    """Read a comma-separated list of image paths from an env var."""
    raw = os.environ.get(env_var, "")
    if not raw:
        return {"palette": [], "style": ""}
    paths = [p.strip() for p in raw.split(",") if p.strip()]
    return mood_board_summary(paths)


# ---------------------------------------------------------------------------
# Internals (keyword fallback)
# ---------------------------------------------------------------------------


_FALLBACK_KEYWORDS: dict[str, tuple[str, list[str]]] = {
    "neon":        ("neon noir, vibrant", ["#ff2bd6", "#22d3ee", "#0d0d10"]),
    "city":        ("urban night, cinematic", ["#ffb347", "#1ec8c8", "#0d0d10"]),
    "forest":      ("dappled natural light", ["#4f7942", "#fff59d", "#1e3a1e"]),
    "underwater":  ("caustic blue, dreamy", ["#56e1ff", "#3f37c9", "#0a0a23"]),
    "desert":      ("harsh sun, ochre", ["#d4a017", "#a0522d", "#fff1e6"]),
    "space":       ("rim light, sci-fi", ["#7c3aed", "#ffd166", "#0d0d10"]),
    "festival":    ("festival strobe, fuchsia", ["#ff2bd6", "#b6ff5c", "#0d0d10"]),
    "love":        ("soft warm, intimate", ["#ff8fa3", "#fff1e6", "#a0522d"]),
    "dark":        ("low-key, moody", ["#0d0d10", "#708090", "#cfd8dc"]),
    "warm":        ("warm tones", ["#ff8fa3", "#fff1e6", "#d4a017"]),
    "cold":        ("cold tones", ["#708090", "#cfd8dc", "#3f37c9"]),
}


def _style_from_keyword(paths: list[Path]) -> str:
    blob = " ".join(p.stem.lower() for p in paths)
    for kw, (style, _) in _FALLBACK_KEYWORDS.items():
        if kw in blob:
            return style
    return ""


def _fallback_for_paths(paths: list[Path]) -> list[str]:
    blob = " ".join(p.stem.lower() for p in paths)
    for kw, (_, pal) in _FALLBACK_KEYWORDS.items():
        if kw in blob:
            return pal
    return _FALLBACK_PALETTES["neon"]
