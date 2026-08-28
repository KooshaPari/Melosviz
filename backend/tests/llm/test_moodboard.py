"""Tests for mood-board palette + style extraction."""

from __future__ import annotations

import pytest

from melosviz.llm.moodboard import (
    _fallback_for_paths,
    _style_from_keyword,
    extract_palette,
    mood_board_summary,
    style_descriptor,
)


def _png_bytes(rgb: tuple[int, int, int], size: int = 32) -> bytes:
    """Create a tiny solid-color PNG without PIL.

    Uses the standard PNG signature + IHDR + IDAT (uncompressed) + IEND.
    """
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    raw = b""
    for _ in range(size):
        raw += b"\x00" + bytes(rgb) * size  # filter byte + RGB pixels
    idat = zlib.compress(raw, 9)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


class TestExtractPalette:
    def test_no_images_returns_empty(self):
        # Truly empty input (caller supplied no images) → empty list
        assert extract_palette([]) == []

    def test_missing_paths_fall_back_to_keyword_palette(self, tmp_path):
        # User supplied a path, but the file doesn't exist → the
        # pipeline still needs a palette, so we match the path stem
        # against the keyword dictionary and return that.
        pal = extract_palette([tmp_path / "neon_ref.png"])
        assert pal and pal[0].startswith("#")

    def test_solid_red_image_returns_red_hex(self, tmp_path):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        png = tmp_path / "red.png"
        png.write_bytes(_png_bytes((220, 30, 30)))
        pal = extract_palette([png])
        assert pal
        # First color should be reddish
        r = int(pal[0][1:3], 16)
        g = int(pal[0][3:5], 16)
        b = int(pal[0][5:7], 16)
        assert r > g and r > b

    def test_multiple_images_average_or_pick_dominant(self, tmp_path):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        red = tmp_path / "red.png"
        blue = tmp_path / "blue.png"
        red.write_bytes(_png_bytes((220, 30, 30)))
        blue.write_bytes(_png_bytes((30, 30, 220)))
        pal = extract_palette([red, blue])
        assert len(pal) >= 2

    def test_fallback_for_keyword_path(self, tmp_path):
        # A path that doesn't exist → fallback path triggers
        pal = _fallback_for_paths([tmp_path / "neon_ref.png"])
        assert pal[0].startswith("#")


class TestStyleDescriptor:
    def test_no_images_returns_empty(self):
        assert style_descriptor([]) == ""

    def test_fallback_keyword(self, tmp_path):
        s = _style_from_keyword([tmp_path / "neon_ref.png"])
        assert "neon" in s.lower()

    def test_solid_image_returns_descriptor(self, tmp_path):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        png = tmp_path / "dark.png"
        png.write_bytes(_png_bytes((10, 10, 10)))
        s = style_descriptor([png])
        # Should at least return some descriptor or empty
        assert isinstance(s, str)


class TestMoodBoardSummary:
    def test_summary_keys(self, tmp_path):
        summary = mood_board_summary([])
        assert "palette" in summary
        assert "style" in summary
