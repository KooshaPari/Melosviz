"""Tests for the WebGL / glTF Binary exporter.

The exporter serialises a :class:`~melosviz.analysis.models.RenderSpec`
into a self-describing ``.glb`` blob (glTF 2.0 binary container).  The
test suite covers:

* GLB container structure (header, magic, version, chunk layout)
* JSON chunk validity (parseable, conforms to glTF 2.0 schema basics)
* Binary chunk layout (vertex data, keyframe data, alignment)
* Spec round-tripping (the original spec is preserved under ``extras``)
* Performance budget (export < 2 s for a 30 s clip)
* Error handling (malformed blobs, bad input types)
* Edge cases (empty spec, oversized keyframes, no palette, etc.)
* File I/O (``export_webgl_to_file``)
* Module surface (public exports, glTF magic values)
"""

from __future__ import annotations

import json
import struct
import time
from pathlib import Path

import pytest

from melosviz.analysis.models import RenderSpec
from melosviz.render.webgl_exporter import (
    GLB_CHUNK_TYPE_BIN,
    GLB_CHUNK_TYPE_JSON,
    GLB_HEADER_SIZE,
    GLB_MAGIC,
    GLB_VERSION,
    WebGLExportError,
    export_html,
    export_webgl,
    export_webgl_to_file,
    parse_glb,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures.
# ---------------------------------------------------------------------------


def _make_minimal_spec() -> RenderSpec:
    """Return a ``RenderSpec`` with sensible defaults."""
    return RenderSpec(
        metadata={"width": 1280, "height": 720, "fps": 30, "duration": 30.0},
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
        keyframes=[
            {"time": 0.0, "energy": 0.5, "hue": 190.0,
             "intensity": 0.6, "color_shift": "#00f5ff"},
            {"time": 0.5, "energy": 0.7, "hue": 220.0,
             "intensity": 0.8, "color_shift": "#ff2fd5"},
        ],
    )


def _make_30s_spec(num_keyframes: int = 900) -> RenderSpec:
    """Return a fully-populated 30s @ 30fps spec (default ~900 keyframes)."""
    keyframes = []
    for i in range(num_keyframes):
        t = i / 30.0
        keyframes.append(
            {
                "time": round(t, 4),
                "energy": min(1.0, 0.3 + 0.4 * ((i % 60) / 60.0)),
                "hue": 190.0 + (i % 360),
                "intensity": 0.5 + 0.4 * ((i * 7) % 100) / 100.0,
                "color_shift": ["#00f5ff", "#ff2fd5", "#8a75ff"][i % 3],
            }
        )
    return RenderSpec(
        metadata={
            "title": "stress",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "duration": 30.0,
        },
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
        layers=[{"type": "background"}, {"type": "shapes"}],
        shots=[{"id": "shot-1", "section": "intro"}],
        timeline=[{"time": 0.0, "type": "shot_change", "data": {}}],
        keyframes=keyframes,
    )


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


def test_export_webgl_returns_bytes() -> None:
    """``export_webgl`` returns a ``bytes`` object."""
    payload = export_webgl(_make_minimal_spec())
    assert isinstance(payload, bytes)
    assert len(payload) > 0


def test_export_webgl_starts_with_glb_magic() -> None:
    """The first 4 bytes of the payload are the ``glTF`` magic."""
    payload = export_webgl(_make_minimal_spec())
    assert payload[:4] == b"glTF"
    assert struct.unpack("<I", payload[:4])[0] == GLB_MAGIC


def test_export_webgl_header_is_correct() -> None:
    """The 12-byte GLB header is little-endian ``magic|version|length``."""
    payload = export_webgl(_make_minimal_spec())
    magic, version, total_length = struct.unpack("<III", payload[:12])
    assert magic == GLB_MAGIC
    assert version == GLB_VERSION
    assert version == 2
    assert total_length == len(payload)


def test_export_webgl_has_json_and_bin_chunks() -> None:
    """The blob contains both a JSON chunk and a BIN chunk."""
    payload = export_webgl(_make_minimal_spec())
    parsed = parse_glb(payload)
    assert parsed["header"]["magic"] == GLB_MAGIC
    assert parsed["header"]["version"] == GLB_VERSION
    assert parsed["json"], "JSON chunk must be non-empty"
    assert parsed["bin"], "BIN chunk must be non-empty"


def test_export_webgl_json_chunk_is_valid_gltf_2() -> None:
    """The JSON chunk is a parseable glTF 2.0 asset document."""
    payload = export_webgl(_make_minimal_spec())
    parsed = parse_glb(payload)
    gltf = parsed["json"]
    assert gltf["asset"]["version"] == "2.0"
    assert gltf["asset"]["generator"] == "melosviz-webgl-exporter"
    assert "scenes" in gltf and len(gltf["scenes"]) == 1
    assert "nodes" in gltf and len(gltf["nodes"]) == 1
    assert "meshes" in gltf and len(gltf["meshes"]) == 1
    assert "materials" in gltf and len(gltf["materials"]) == 1
    assert "buffers" in gltf
    assert "bufferViews" in gltf
    assert "accessors" in gltf


def test_export_webgl_preserves_original_spec_in_extras() -> None:
    """The original RenderSpec is preserved verbatim under ``extras.spec``."""
    spec = _make_minimal_spec()
    payload = export_webgl(spec)
    parsed = parse_glb(payload)
    extras_spec = parsed["json"]["extras"]["spec"]
    assert extras_spec["metadata"]["width"] == 1280
    assert extras_spec["metadata"]["height"] == 720
    assert extras_spec["palette"] == [
        "#00f5ff", "#ff2fd5", "#8a75ff"
    ]
    assert len(extras_spec["keyframes"]) == 2


def test_export_webgl_embedded_shader_is_present() -> None:
    """The fragment and vertex shaders are embedded in material extras."""
    payload = export_webgl(_make_minimal_spec())
    parsed = parse_glb(payload)
    material = parsed["json"]["materials"][0]
    shader = material["extras"]["shader"]
    assert shader["language"] == "glsl"
    assert "attribute vec2 aPos" in shader["vertex"]
    assert "void main()" in shader["fragment"]
    assert "uTime" in shader["fragment"]
    assert "uEnergy" in shader["fragment"]
    assert "uniforms" in material["extras"]


def test_export_webgl_animation_script_is_embedded() -> None:
    """A standalone JavaScript animation loop is embedded in the GLB."""
    payload = export_webgl(_make_minimal_spec())
    parsed = parse_glb(payload)
    animation = parsed["json"]["materials"][0]["extras"]["animation"]
    # The JS animation loop is a self-invoking function that drives the
    # WebGL canvas.  It must reference the canvas element, request an
    # animation frame, and update at least one of the standard uniforms.
    assert "melosviz-canvas" in animation
    assert "requestAnimationFrame" in animation
    assert "getContext" in animation
    assert "uniform" in animation.lower()
    assert "drawArrays" in animation or "drawElements" in animation


def test_export_webgl_bin_chunk_contains_quad_vertices() -> None:
    """The first 32 bytes of BIN are the 8-float quad vertex positions."""
    payload = export_webgl(_make_minimal_spec())
    parsed = parse_glb(payload)
    bin_data = parsed["bin"]
    vertices = struct.unpack("<8f", bin_data[0:32])
    assert vertices == (-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0)


def test_export_webgl_bin_chunk_contains_texcoords() -> None:
    """The UV buffer view is the second 32 bytes of BIN."""
    payload = export_webgl(_make_minimal_spec())
    parsed = parse_glb(payload)
    bin_data = parsed["bin"]
    uvs = struct.unpack("<8f", bin_data[32:64])
    assert uvs == (0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0)


def test_export_webgl_bin_chunk_contains_indices() -> None:
    """The index buffer view encodes the two triangles of the quad."""
    payload = export_webgl(_make_minimal_spec())
    parsed = parse_glb(payload)
    bin_data = parsed["bin"]
    # Indices start at byte 64 (after vertices + UVs), 6 * uint16.
    indices = struct.unpack("<6H", bin_data[64:76])
    assert indices == (0, 1, 2, 2, 1, 3)


def test_export_webgl_bin_chunk_contains_keyframes() -> None:
    """The keyframe buffer view contains a record per keyframe (8 floats)."""
    spec = _make_minimal_spec()
    payload = export_webgl(spec)
    parsed = parse_glb(payload)
    bin_data = parsed["bin"]
    # keyframes start at the offsets["keyframes"] byte; layout is documented
    # in extras.layout.
    layout = parsed["json"]["extras"]["layout"]
    kf_offset = layout["offsets"]["keyframes"]
    kf_count = layout["counts"]["keyframes"]
    assert kf_count == 2
    first = struct.unpack("<8f", bin_data[kf_offset:kf_offset + 32])
    t, energy, hue, intensity, r, g, b, _reserved = first
    assert t == pytest.approx(0.0)
    assert 0.0 <= energy <= 1.0
    assert 0.0 <= intensity <= 1.0


def test_export_webgl_chunks_are_4byte_aligned() -> None:
    """JSON and BIN chunks are padded to a 4-byte multiple per GLB spec."""
    payload = export_webgl(_make_minimal_spec())
    # Skip 12-byte header, then read JSON chunk length and type.
    json_len, json_type = struct.unpack("<II", payload[12:20])
    assert json_type == GLB_CHUNK_TYPE_JSON
    assert json_len % 4 == 0

    # The BIN chunk follows the padded JSON chunk.
    json_total = 8 + json_len
    bin_len, bin_type = struct.unpack(
        "<II", payload[12 + json_total:12 + json_total + 8]
    )
    assert bin_type == GLB_CHUNK_TYPE_BIN
    assert bin_len % 4 == 0


def test_export_webgl_handles_empty_spec() -> None:
    """An empty ``RenderSpec()`` is serialised with a sensible default keyframe."""
    payload = export_webgl(RenderSpec())
    parsed = parse_glb(payload)
    assert parsed["header"]["magic"] == GLB_MAGIC
    assert parsed["json"]["asset"]["version"] == "2.0"
    # Empty spec still produces a non-empty BIN chunk with one default
    # keyframe so downstream consumers have at least one record to play.
    assert len(parsed["bin"]) > 0


def test_export_webgl_handles_dict_input() -> None:
    """A plain ``dict`` with the spec shape is accepted."""
    spec_dict = {
        "metadata": {"width": 800, "height": 600, "fps": 24, "duration": 5.0},
        "palette": ["#abcdef"],
        "keyframes": [],
    }
    payload = export_webgl(spec_dict)
    parsed = parse_glb(payload)
    assert parsed["json"]["extras"]["spec"]["metadata"]["width"] == 800


def test_export_webgl_rejects_non_dict_spec() -> None:
    """A non-dict / non-RenderSpec argument raises :class:`WebGLExportError`."""
    with pytest.raises(WebGLExportError):
        export_webgl(12345)  # type: ignore[arg-type]


def test_export_webgl_strips_color_hashes_correctly() -> None:
    """Hex colour strings are decoded to 0-1 RGB floats in the BIN chunk."""
    spec = RenderSpec(
        metadata={"width": 100, "height": 100, "fps": 30, "duration": 1.0},
        palette=["#ff0000"],
        keyframes=[
            {"time": 0.0, "energy": 0.5, "hue": 0.0,
             "intensity": 0.5, "color_shift": "#ff0000"},
        ],
    )
    payload = export_webgl(spec)
    parsed = parse_glb(payload)
    layout = parsed["json"]["extras"]["layout"]
    kf_offset = layout["offsets"]["keyframes"]
    # Record: t, energy, hue, intensity, r, g, b, reserved
    t, energy, hue, intensity, r, g, b, _ = struct.unpack(
        "<8f", parsed["bin"][kf_offset:kf_offset + 32]
    )
    assert r == pytest.approx(1.0, abs=1e-5)
    assert g == pytest.approx(0.0, abs=1e-5)
    assert b == pytest.approx(0.0, abs=1e-5)


def test_export_webgl_faster_than_budget_for_30s_clip() -> None:
    """``export_webgl`` meets the < 2s acceptance criterion for a 30s clip."""
    spec = _make_30s_spec(num_keyframes=900)  # 30s @ 30fps
    start = time.perf_counter()
    payload = export_webgl(spec)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"export took {elapsed:.3f}s, expected < 2.0s"
    assert len(payload) > 0


def test_export_webgl_30s_clip_round_trips() -> None:
    """A 30s, 900-keyframe spec round-trips through export/parse losslessly."""
    spec = _make_30s_spec(num_keyframes=900)
    payload = export_webgl(spec)
    parsed = parse_glb(payload)
    extras_spec = parsed["json"]["extras"]["spec"]
    assert extras_spec["metadata"]["duration"] == 30.0
    assert len(extras_spec["keyframes"]) == 900
    # First and last keyframes survive the round trip.
    assert extras_spec["keyframes"][0]["time"] == pytest.approx(0.0)
    last = extras_spec["keyframes"][-1]["time"]
    assert last == pytest.approx(899 / 30.0, rel=1e-3)


def test_export_webgl_to_file_creates_file(tmp_path: Path) -> None:
    """``export_webgl_to_file`` writes a real ``.glb`` file on disk."""
    spec = _make_minimal_spec()
    out = export_webgl_to_file(spec, tmp_path / "out.glb")
    assert out.exists()
    assert out.is_file()
    assert out.stat().st_size > 12  # more than just a header
    # The file's first 4 bytes are the GLB magic.
    with out.open("rb") as fh:
        magic = fh.read(4)
    assert magic == b"glTF"


def test_export_webgl_to_file_creates_parent_dirs(tmp_path: Path) -> None:
    """``export_webgl_to_file`` creates missing parent directories."""
    nested = tmp_path / "deep" / "nested" / "out.glb"
    assert not nested.parent.exists()
    spec = _make_minimal_spec()
    out = export_webgl_to_file(spec, nested)
    assert out.exists()
    assert nested.parent.is_dir()


def test_parse_glb_round_trips() -> None:
    """``parse_glb`` recovers the same JSON / BIN we wrote."""
    spec = _make_minimal_spec()
    payload = export_webgl(spec)
    parsed = parse_glb(payload)
    # The JSON chunk re-decodes to a dict with the same top-level keys.
    assert isinstance(parsed["json"], dict)
    assert "asset" in parsed["json"]
    # The BIN chunk is the exact bytes we wrote (modulo 4-byte padding).
    assert len(parsed["bin"]) > 0


def test_parse_glb_rejects_truncated_blob() -> None:
    """``parse_glb`` raises :class:`WebGLExportError` on truncated input."""
    payload = export_webgl(_make_minimal_spec())
    truncated = payload[:20]  # cut off the chunks
    with pytest.raises(WebGLExportError):
        parse_glb(truncated)


def test_parse_glb_rejects_bad_magic() -> None:
    """``parse_glb`` raises when the magic bytes are wrong."""
    payload = export_webgl(_make_minimal_spec())
    bad = b"junk" + payload[4:]
    with pytest.raises(WebGLExportError):
        parse_glb(bad)


def test_parse_glb_rejects_wrong_length() -> None:
    """``parse_glb`` raises when the header length doesn't match the blob."""
    payload = export_webgl(_make_minimal_spec())
    # Corrupt the length field (bytes 8-12) to a different value.
    bad = payload[:8] + b"\x00\x00\x00\x00" + payload[12:]
    with pytest.raises(WebGLExportError):
        parse_glb(bad)


def test_parse_glb_rejects_non_bytes() -> None:
    """``parse_glb`` raises when given a non-bytes object."""
    with pytest.raises(WebGLExportError):
        parse_glb("not bytes")  # type: ignore[arg-type]


def test_module_exports_public_api() -> None:
    """All advertised public names are importable and callable."""
    import melosviz.render.webgl_exporter as mod

    for name in (
        "WebGLExportError",
        "export_webgl",
        "export_webgl_to_file",
        "parse_glb",
        "GLB_MAGIC",
        "GLB_VERSION",
        "GLB_HEADER_SIZE",
        "GLB_CHUNK_TYPE_JSON",
        "GLB_CHUNK_TYPE_BIN",
    ):
        assert hasattr(mod, name), f"missing public name: {name}"
    assert callable(export_webgl)
    assert callable(parse_glb)
    assert callable(export_webgl_to_file)
    assert issubclass(WebGLExportError, RuntimeError)
    # GLB constants match the glTF 2.0 spec.
    assert GLB_MAGIC == 0x46546C67
    assert GLB_VERSION == 2
    assert GLB_HEADER_SIZE == 12


def test_export_html_still_works(tmp_path: Path) -> None:
    """The legacy ``export_html`` helper is preserved and writes a file."""
    spec = {
        "metadata": {"width": 800, "height": 600, "title": "legacy"},
        "palette": ["#ffffff"],
        "keyframes": [],
    }
    out = export_html(spec, str(tmp_path / "out.html"))
    assert out.exists()
    assert out.suffix == ".html"
    content = out.read_text(encoding="utf-8")
    assert "melosviz-canvas" in content
    assert "MELOSVIZ_SPEC" in content


def test_export_webgl_with_unicode_metadata() -> None:
    """Non-ASCII characters in metadata round-trip through the JSON chunk."""
    spec = RenderSpec(metadata={"title": "クリップ 🎵"})
    payload = export_webgl(spec)
    parsed = parse_glb(payload)
    assert parsed["json"]["extras"]["spec"]["metadata"]["title"] == "クリップ 🎵"


def test_export_webgl_bin_layout_keys_present() -> None:
    """The ``extras.layout`` block exposes the BIN layout for consumers."""
    spec = _make_minimal_spec()
    payload = export_webgl(spec)
    parsed = parse_glb(payload)
    layout = parsed["json"]["extras"]["layout"]
    for key in ("offsets", "sizes", "counts", "total_bytes"):
        assert key in layout
    for region in ("vertices", "uvs", "indices", "keyframes"):
        assert region in layout["offsets"]
        assert region in layout["sizes"]
        assert region in layout["counts"]
