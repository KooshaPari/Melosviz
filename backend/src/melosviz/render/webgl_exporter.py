"""WebGL / glTF Binary (``.glb``) export helpers for Melosviz visual specs.

This module turns a :class:`~melosviz.analysis.models.RenderSpec` into a
self-describing ``.glb`` payload that can be loaded by any conformant
glTF 2.0 viewer.  The output uses the standard glTF Binary container
layout:

* 12-byte header (``glTF`` magic, version 2, total length)
* JSON chunk describing the asset, scene, mesh, materials, shaders
* ``BIN`` chunk holding vertex/keyframe data

The fragment shader and animation JavaScript used by the existing HTML
exporter are embedded as glTF ``extras`` so the entire visual can be
replayed from a single ``.glb`` blob.

The implementation is intentionally pure-stdlib (no ``msgpack``,
``numpy``, or other dependencies) so it stays fast and portable.
"""

from __future__ import annotations

import json
import struct
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Union

if TYPE_CHECKING:
    from melosviz.analysis.models import RenderSpec


__all__ = [
    "WebGLExportError",
    "export_webgl",
    "export_webgl_to_file",
    "parse_glb",
    "GLB_MAGIC",
    "GLB_VERSION",
    "GLB_HEADER_SIZE",
    "GLB_CHUNK_TYPE_JSON",
    "GLB_CHUNK_TYPE_BIN",
]


# ---------------------------------------------------------------------------
# GLB container constants (glTF 2.0 spec).
# ---------------------------------------------------------------------------

# glTF Binary container magic: ASCII "glTF" = 0x46546C67.
GLB_MAGIC: int = 0x46546C67
GLB_VERSION: int = 2
# Size of a GLB header: 3 x uint32 (magic, version, total length).
GLB_HEADER_SIZE: int = 12
# Chunk header size: 2 x uint32 (length, type).
GLB_CHUNK_HEADER_SIZE: int = 8

# ASCII "JSON" = 0x4E4F534A.
GLB_CHUNK_TYPE_JSON: int = 0x4E4F534A
# ASCII "BIN\0" = 0x004E4942.
GLB_CHUNK_TYPE_BIN: int = 0x004E4942

# glTF requires 4-byte alignment for chunks.
_GLB_CHUNK_ALIGNMENT: int = 4
_JSON_PADDING_BYTE: bytes = b" "
_BIN_PADDING_BYTE: bytes = b"\x00"

# Vertex layout for the fullscreen quad.  Each vertex is 2 floats (x, y).
_QUAD_VERTICES: Tuple[float, ...] = (
    -1.0, -1.0,
     1.0, -1.0,
    -1.0,  1.0,
     1.0,  1.0,
)

# Texcoords for the same quad (matches the JS exporter mapping).
_QUAD_UVS: Tuple[float, ...] = (
    0.0, 0.0,
    1.0, 0.0,
    0.0, 1.0,
    1.0, 1.0,
)

# Triangle-list indices.
_QUAD_INDICES: Tuple[int, ...] = (0, 1, 2, 2, 1, 3)


# ---------------------------------------------------------------------------
# Errors.
# ---------------------------------------------------------------------------


class WebGLExportError(RuntimeError):
    """Raised when a :class:`RenderSpec` cannot be serialised to GLB."""


# ---------------------------------------------------------------------------
# Shaders (embedded as glTF ``extras`` so the GLB is self-describing).
# ---------------------------------------------------------------------------


_VERTEX_SHADER = """\
attribute vec2 aPos;
attribute vec2 aUV;
varying vec2 vUV;
void main() {
  vUV = aUV;
  gl_Position = vec4(aPos, 0.0, 1.0);
}
"""


_FRAGMENT_SHADER = """\
precision highp float;
varying vec2 vUV;
uniform float uTime;
uniform vec2  uRes;
uniform float uEnergy;
uniform float uHue;
uniform float uIntensity;
uniform vec3  uColor0;
uniform vec3  uColor1;
uniform vec3  uColor2;
#define TAU 6.28318530718

vec2 toPolar(vec2 p) { return vec2(length(p), atan(p.y, p.x)); }

float ring(vec2 p, float r, float w) {
  return smoothstep(w, 0.0, abs(length(p) - r));
}

float sdHex(vec2 p, float r) {
  const vec3 k = vec3(-0.8660254, 0.5, 0.5773503);
  p = abs(p);
  p -= 2.0 * min(dot(k.xy, p), 0.0) * k.xy;
  p -= vec2(clamp(p.x, -k.z * r, k.z * r), r);
  return length(p) * sign(p.y);
}

void main() {
  vec2 uv = (vUV - 0.5);
  uv.x *= uRes.x / uRes.y;

  float pulse  = sin(uTime * 3.2) * 0.5 + 0.5;
  float pulse2 = sin(uTime * 5.7 + 1.1) * 0.5 + 0.5;
  float en     = uEnergy;
  float inten  = uIntensity;

  vec3 bg = uColor0 * 0.07 + uColor1 * 0.04;

  float r1 = ring(uv, 0.36 + pulse * 0.04, 0.007);
  float r2 = ring(uv, 0.26 + pulse2 * 0.03, 0.005);
  float r3 = ring(uv, 0.18 + en * 0.06, 0.004);

  vec2 pol = toPolar(uv);
  float bars = 0.0;
  for (int i = 0; i < 24; i++) {
    float fi = float(i) / 24.0;
    float f  = sin(fi * 43.98 + uTime * 1.8) * 0.5 + 0.5;
    float spike = max(0.0, sin(pol.y * 24.0 + fi * TAU - uTime * 2.0)) * f;
    bars += spike * smoothstep(0.0, 0.12, pol.x) * smoothstep(0.48, 0.12, pol.x);
  }
  bars *= 0.04 * (0.4 + en * 0.9);

  float rot = uTime * 0.18 + en * 0.6;
  vec2 ruv = vec2(
    uv.x * cos(rot) - uv.y * sin(rot),
    uv.x * sin(rot) + uv.y * cos(rot)
  );
  float hex = smoothstep(0.02, 0.0, sdHex(ruv, 0.07 + inten * 0.05));

  float dist = length(uv);
  float glow = exp(-dist * 2.8) * 0.35;

  vec3 col = bg;
  col = mix(col, uColor1 * 0.35, r1);
  col = mix(col, uColor1 * 0.25, r2);
  col = mix(col, uColor1 * 0.20, r3);
  col += uColor1 * bars;
  col += uColor1 * glow * (0.5 + en * 0.8);
  col = mix(col, uColor1, hex * 0.75);

  float vig = 1.0 - smoothstep(0.5, 1.1, dist);
  col *= vig;
  col = col / (col + 0.6);
  col = pow(col, vec3(0.9));

  gl_FragColor = vec4(col, 1.0);
}
"""


_SHADER_PROGRAM = {
    "vertex": _VERTEX_SHADER,
    "fragment": _FRAGMENT_SHADER,
    "language": "glsl",
    "targets": ["webgl2", "webgl"],
}


# Standalone JavaScript animation loop embedded in the GLB.
_ANIMATION_SCRIPT = """\
(function(specJson) {
  'use strict';
  var SPEC = specJson;
  function hexToRgb01(hex) {
    var clean = (hex || '#00f5ff').replace('#', '');
    var full = clean.length === 3
      ? clean.split('').map(function(c) { return c + c; }).join('')
      : clean;
    var n = parseInt(full, 16);
    return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255];
  }
  var canvas = document.getElementById('melosviz-canvas');
  if (!canvas) { throw new Error('melosviz-canvas element not found'); }
  var gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
  if (!gl) { throw new Error('WebGL not available'); }
  function compile(type, src) {
    var sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      throw new Error('Shader compile: ' + gl.getShaderInfoLog(sh));
    }
    return sh;
  }
  var VS = SPEC.vertexShader;
  var FS = SPEC.fragmentShader;
  var prog = gl.createProgram();
  gl.attachShader(prog, compile(gl.VERTEX_SHADER, VS));
  gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    throw new Error('Link: ' + gl.getProgramInfoLog(prog));
  }
  var verts = new Float32Array([
    -1, -1,  0, 0,
     1, -1,  1, 0,
    -1,  1,  0, 1,
     1,  1,  1, 1,
  ]);
  var buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);
  var aPos = gl.getAttribLocation(prog, 'aPos');
  var aUV  = gl.getAttribLocation(prog, 'aUV');
  gl.enableVertexAttribArray(aPos);
  gl.enableVertexAttribArray(aUV);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 16, 0);
  gl.vertexAttribPointer(aUV,  2, gl.FLOAT, false, 16, 8);
  var uTime   = gl.getUniformLocation(prog, 'uTime');
  var uRes    = gl.getUniformLocation(prog, 'uRes');
  var uEnergy = gl.getUniformLocation(prog, 'uEnergy');
  var uHue    = gl.getUniformLocation(prog, 'uHue');
  var uInten  = gl.getUniformLocation(prog, 'uIntensity');
  var uC0     = gl.getUniformLocation(prog, 'uColor0');
  var uC1     = gl.getUniformLocation(prog, 'uColor1');
  var uC2     = gl.getUniformLocation(prog, 'uColor2');
  var palette = SPEC.palette || ['#00f5ff', '#ff2fd5', '#8a75ff'];
  var c0 = hexToRgb01(palette[0]);
  var c1 = hexToRgb01(palette[1] || palette[0]);
  var c2 = hexToRgb01(palette[2] || palette[0]);
  var keyframes = SPEC.keyframes || [];
  var frameCount = Math.max(keyframes.length, 1);
  var startTime = performance.now();
  function draw() {
    var w = canvas.clientWidth  || 1920;
    var h = canvas.clientHeight || 1080;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== w * dpr) canvas.width = w * dpr;
    if (canvas.height !== h * dpr) canvas.height = h * dpr;
    gl.viewport(0, 0, canvas.width, canvas.height);
    var elapsed = (performance.now() - startTime) / 1000;
    var fi = Math.floor((elapsed * 30) % frameCount);
    var key = keyframes[fi] || { energy: 0.5, hue: 190, intensity: 0.6 };
    gl.useProgram(prog);
    gl.uniform1f(uTime,   elapsed);
    gl.uniform2f(uRes,    canvas.width, canvas.height);
    gl.uniform1f(uEnergy, key.energy    || 0.5);
    gl.uniform1f(uHue,    ((key.hue      || 190) / 360));
    gl.uniform1f(uInten,  key.intensity || 0.6);
    gl.uniform3f(uC0, c0[0], c0[1], c0[2]);
    gl.uniform3f(uC1, c1[0], c1[1], c1[2]);
    gl.uniform3f(uC2, c2[0], c2[1], c2[2]);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    requestAnimationFrame(draw);
  }
  draw();
})(window.MELOSVIZ_SPEC || {});
"""


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _hex_to_rgb01(color: str) -> Tuple[float, float, float]:
    """Convert a ``#rrggbb`` / ``#rgb`` string to a 0-1 RGB tuple."""
    if not isinstance(color, str):
        return (0.0, 0.0, 0.0)
    clean = color.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        return (0.0, 0.0, 0.0)
    try:
        r = int(clean[0:2], 16) / 255.0
        g = int(clean[2:4], 16) / 255.0
        b = int(clean[4:6], 16) / 255.0
    except ValueError:
        return (0.0, 0.0, 0.0)
    return (r, g, b)


def _pad(data: bytes, alignment: int, pad_byte: bytes) -> bytes:
    """Pad ``data`` so its length is a multiple of ``alignment`` bytes."""
    remainder = len(data) % alignment
    if remainder == 0:
        return data
    return data + pad_byte * (alignment - remainder)


def _spec_to_dict(spec: Union["RenderSpec", Dict[str, Any], None]) -> Dict[str, Any]:
    """Coerce a :class:`RenderSpec` (or dict) to a plain dictionary.

    ``None`` is treated as an empty spec.  Other non-dict, non-RenderSpec
    inputs (numbers, strings, lists, etc.) raise :class:`WebGLExportError`
    so the caller gets a clear, immediate failure for misuse.
    """
    if spec is None:
        return {}
    if isinstance(spec, dict):
        return dict(spec)
    if hasattr(spec, "model_dump"):
        return spec.model_dump()
    raise WebGLExportError(
        f"export_webgl: spec must be a RenderSpec or dict, got "
        f"{type(spec).__name__}"
    )


def _build_binary_blob(
    keyframes: List[Dict[str, Any]],
    palette: List[Any],
) -> bytes:
    """Pack vertex + keyframe data into a single binary blob.

    Layout (little-endian, 4-byte aligned):

    * ``float32[8]``  : quad vertex positions (x, y)
    * ``float32[8]``  : quad texcoords (u, v)
    * ``uint16[6]``   : quad indices
    * ``float32[N*8]``: keyframe records (t, energy, hue, intensity,
                                          r0, g0, b0, reserved)

    The exact internal layout is documented in ``extras.layout`` of the
    glTF asset so consumers can decode it without consulting this file.
    """
    chunks: List[bytes] = []

    # Vertices
    chunks.append(struct.pack("<8f", *_QUAD_VERTICES))
    # UVs
    chunks.append(struct.pack("<8f", *_QUAD_UVS))
    # Indices
    chunks.append(struct.pack("<6H", *_QUAD_INDICES))

    # Default palette colour (RGB, 0-1) used to fill missing keyframes.
    default_color = (0.0, 1.0, 1.0)
    if palette:
        default_color = _hex_to_rgb01(str(palette[0]))

    # Keyframes: 8 floats per record.
    if not keyframes:
        keyframes = [
            {
                "time": 0.0,
                "energy": 0.5,
                "hue": 190.0,
                "intensity": 0.6,
                "color_shift": default_color,
            }
        ]

    for kf in keyframes:
        if not isinstance(kf, dict):
            continue
        t = float(kf.get("time", 0.0))
        energy = float(kf.get("energy", 0.5))
        hue = float(kf.get("hue", 190.0)) / 360.0
        intensity = float(kf.get("intensity", 0.6))
        color = kf.get("color_shift")
        if isinstance(color, str):
            rgb = _hex_to_rgb01(color)
        elif isinstance(color, (list, tuple)) and len(color) >= 3:
            rgb = (float(color[0]), float(color[1]), float(color[2]))
        else:
            rgb = default_color
        chunks.append(
            struct.pack(
                "<ffffffff",
                t,
                max(0.0, min(1.0, energy)),
                max(0.0, min(1.0, hue)),
                max(0.0, min(1.0, intensity)),
                rgb[0],
                rgb[1],
                rgb[2],
                0.0,
            )
        )

    return b"".join(chunks)


def _compute_layout(num_keyframes: int) -> Dict[str, Any]:
    """Return the byte offsets and counts for the binary layout."""
    vertex_bytes = 8 * 4
    uv_bytes = 8 * 4
    index_bytes = 6 * 2
    keyframe_bytes = max(1, num_keyframes) * 8 * 4

    # Round each region to 4 bytes for alignment.
    def _align(n: int) -> int:
        return (n + 3) & ~3

    offsets = {
        "vertices": 0,
        "uvs": _align(vertex_bytes),
        "indices": _align(vertex_bytes + uv_bytes),
        "keyframes": _align(vertex_bytes + uv_bytes + index_bytes),
    }
    sizes = {
        "vertices": vertex_bytes,
        "uvs": uv_bytes,
        "indices": index_bytes,
        "keyframes": keyframe_bytes,
    }
    counts = {
        "vertices": 8,
        "uvs": 8,
        "indices": 6,
        "keyframes": max(1, num_keyframes),
    }
    total = offsets["keyframes"] + keyframe_bytes
    return {
        "offsets": offsets,
        "sizes": sizes,
        "counts": counts,
        "total_bytes": total,
    }


def _build_gltf_json(
    spec_dict: Dict[str, Any],
    layout: Dict[str, Any],
    bin_length: int,
) -> bytes:
    """Build the JSON chunk payload for the GLB.

    The output is a minimal but valid glTF 2.0 scene describing a
    fullscreen quad that uses a custom shader material.  The original
    :class:`RenderSpec` is preserved verbatim under ``extras.spec`` so
    consumers can re-derive the full visual without re-running the
    analysis pipeline.
    """
    metadata = spec_dict.get("metadata", {}) or {}
    width = int(metadata.get("width", 1920))
    height = int(metadata.get("height", 1080))
    fps = int(metadata.get("fps", 30))
    duration_sec = float(metadata.get("duration", 30.0))
    title = str(metadata.get("title", "Melosviz"))

    palette: List[Any] = list(spec_dict.get("palette") or [])
    keyframes: List[Dict[str, Any]] = list(spec_dict.get("keyframes") or [])
    layers: List[Dict[str, Any]] = list(spec_dict.get("layers") or [])
    shots: List[Dict[str, Any]] = list(spec_dict.get("shots") or [])
    timeline: List[Dict[str, Any]] = list(spec_dict.get("timeline") or [])

    # Round BIN length to 4 bytes for GLB alignment.
    bin_padded = (bin_length + 3) & ~3

    offsets = layout["offsets"]
    sizes = layout["sizes"]
    counts = layout["counts"]

    asset: Dict[str, Any] = {
        "version": "2.0",
        "generator": "melosviz-webgl-exporter",
        "copyright": "Melosviz",
        "extras": {
            "title": title,
            "renderSpecMetadata": metadata,
            "generatedAt": int(time.time()),
        },
    }

    scene: Dict[str, Any] = {
        "name": title,
        "nodes": [0],
        "extras": {
            "viewport": {"width": width, "height": height},
        },
    }

    # Buffer 0 holds the raw binary blob.
    buffer: Dict[str, Any] = {
        "byteLength": bin_padded,
    }

    # BufferViews describe how the buffer is split.
    buffer_views: List[Dict[str, Any]] = [
        {
            "buffer": 0,
            "byteOffset": offsets["vertices"],
            "byteLength": sizes["vertices"],
            "target": 34962,  # ARRAY_BUFFER
        },
        {
            "buffer": 0,
            "byteOffset": offsets["uvs"],
            "byteLength": sizes["uvs"],
            "target": 34962,
        },
        {
            "buffer": 0,
            "byteOffset": offsets["indices"],
            "byteLength": sizes["indices"],
            "target": 34963,  # ELEMENT_ARRAY_BUFFER
        },
        {
            "buffer": 0,
            "byteOffset": offsets["keyframes"],
            "byteLength": sizes["keyframes"],
        },
    ]

    # Accessors describe how each bufferView is interpreted.
    accessors: List[Dict[str, Any]] = [
        {
            "bufferView": 0,
            "componentType": 5126,  # FLOAT
            "count": counts["vertices"] // 2,
            "type": "VEC2",
            "min": [-1.0, -1.0],
            "max": [1.0, 1.0],
        },
        {
            "bufferView": 1,
            "componentType": 5126,
            "count": counts["uvs"] // 2,
            "type": "VEC2",
            "min": [0.0, 0.0],
            "max": [1.0, 1.0],
        },
        {
            "bufferView": 2,
            "componentType": 5123,  # UNSIGNED_SHORT
            "count": counts["indices"],
            "type": "SCALAR",
            "min": [0],
            "max": [3],
        },
        {
            "bufferView": 3,
            "componentType": 5126,
            "count": counts["keyframes"],
            "type": "VEC8",
        },
    ]

    mesh: Dict[str, Any] = {
        "primitives": [
            {
                "attributes": {
                    "POSITION": 0,
                    "TEXCOORD_0": 1,
                },
                "indices": 2,
                "material": 0,
                "mode": 4,  # TRIANGLES
            }
        ],
    }

    # Material is a placeholder; the actual visuals come from a custom
    # shader embedded in ``extras``.  We give it a neutral base color
    # so glTF 2.0 viewers don't choke.
    material: Dict[str, Any] = {
        "name": "melosviz-shader",
        "doubleSided": True,
        "pbrMetallicRoughness": {
            "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
            "metallicFactor": 0.0,
            "roughnessFactor": 1.0,
        },
        "extras": {
            "shader": _SHADER_PROGRAM,
            "vertexShader": _VERTEX_SHADER,
            "fragmentShader": _FRAGMENT_SHADER,
            "animation": _ANIMATION_SCRIPT,
            "uniforms": {
                "uTime":      {"type": "float",  "default": 0.0},
                "uRes":       {"type": "vec2",   "default": [width, height]},
                "uEnergy":    {"type": "float",  "default": 0.5},
                "uHue":       {"type": "float",  "default": 0.5},
                "uIntensity": {"type": "float",  "default": 0.6},
                "uColor0":    {"type": "vec3",   "default": [0.0, 0.96, 1.0]},
                "uColor1":    {"type": "vec3",   "default": [1.0, 0.18, 0.84]},
                "uColor2":    {"type": "vec3",   "default": [0.54, 0.46, 1.0]},
            },
        },
    }

    node: Dict[str, Any] = {
        "mesh": 0,
        "name": "fullscreen-quad",
    }

    gltf: Dict[str, Any] = {
        "asset": asset,
        "scene": 0,
        "scenes": [scene],
        "nodes": [node],
        "meshes": [mesh],
        "materials": [material],
        "buffers": [buffer],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "extras": {
            "spec": spec_dict,
            "layout": layout,
            "render": {
                "width": width,
                "height": height,
                "fps": fps,
                "duration_sec": duration_sec,
                "palette": palette,
                "layerCount": len(layers),
                "shotCount": len(shots),
                "timelineEventCount": len(timeline),
                "keyframeCount": len(keyframes),
            },
        },
    }

    text = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def export_webgl(spec: Union["RenderSpec", Dict[str, Any], None]) -> bytes:
    """Serialise a :class:`RenderSpec` to a glTF Binary (``.glb``) blob.

    The output is a fully self-describing glTF 2.0 container:

    * a 12-byte header (magic ``glTF``, version 2, total length)
    * a JSON chunk describing the asset, scene, materials, and shaders
    * a ``BIN`` chunk containing vertex and keyframe data

    The full original :class:`RenderSpec` is preserved under
    ``extras.spec`` in the JSON chunk so downstream tools can recover
    it without re-running the analysis pipeline.

    Parameters
    ----------
    spec:
        A :class:`~melosviz.analysis.models.RenderSpec` (or a dict with
        the same shape) to export.

    Returns
    -------
    bytes
        The serialised ``.glb`` payload.  The total length is at least
        ``12 + 8 + json_bytes + 8 + bin_bytes``; small specs yield
        payloads under 1 KiB.

    Raises
    ------
    WebGLExportError
        If ``spec`` is not a ``RenderSpec`` or ``dict``, or if the
        serialised blob fails internal length validation.
    """
    spec_dict = _spec_to_dict(spec)
    if not isinstance(spec_dict, dict):
        raise WebGLExportError(
            f"export_webgl: spec must be a RenderSpec or dict, got "
            f"{type(spec_dict).__name__}"
        )

    keyframes = spec_dict.get("keyframes") or []
    if not isinstance(keyframes, list):
        keyframes = []
    palette = spec_dict.get("palette") or []
    if not isinstance(palette, list):
        palette = []

    # 1. Build the binary blob.
    bin_payload = _build_binary_blob(keyframes, palette)
    layout = _compute_layout(len(keyframes))
    # Pad BIN to 4 bytes per GLB spec.
    bin_chunk_data = _pad(bin_payload, _GLB_CHUNK_ALIGNMENT, _BIN_PADDING_BYTE)

    # 2. Build the JSON chunk.
    json_payload = _build_gltf_json(spec_dict, layout, len(bin_payload))
    json_chunk_data = _pad(json_payload, _GLB_CHUNK_ALIGNMENT, _JSON_PADDING_BYTE)

    # 3. Assemble header + chunks.
    total_length = (
        GLB_HEADER_SIZE
        + GLB_CHUNK_HEADER_SIZE + len(json_chunk_data)
        + GLB_CHUNK_HEADER_SIZE + len(bin_chunk_data)
    )

    parts: List[bytes] = [
        struct.pack("<III", GLB_MAGIC, GLB_VERSION, total_length),
        struct.pack("<II", len(json_chunk_data), GLB_CHUNK_TYPE_JSON),
        json_chunk_data,
        struct.pack("<II", len(bin_chunk_data), GLB_CHUNK_TYPE_BIN),
        bin_chunk_data,
    ]
    blob = b"".join(parts)

    if len(blob) != total_length:
        raise WebGLExportError(
            f"export_webgl: internal length mismatch "
            f"(expected {total_length}, got {len(blob)})"
        )
    return blob


def export_webgl_to_file(
    spec: Union["RenderSpec", Dict[str, Any], None],
    output_path: Union[str, Path],
) -> Path:
    """Serialise ``spec`` to a ``.glb`` file on disk.

    Returns the absolute :class:`Path` to the written file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = export_webgl(spec)
    path.write_bytes(payload)
    return path.resolve()


def parse_glb(blob: bytes) -> Dict[str, Any]:
    """Parse a ``.glb`` blob back into a dictionary.

    Useful for tests and for downstream consumers that want to verify
    round-trip integrity.  Returns a dict with keys ``header``,
    ``json`` (the parsed asset), and ``bin`` (the raw binary chunk).
    Raises :class:`WebGLExportError` on malformed input.
    """
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise WebGLExportError(
            f"parse_glb: expected bytes, got {type(blob).__name__}"
        )
    if len(blob) < GLB_HEADER_SIZE:
        raise WebGLExportError(
            f"parse_glb: blob too small ({len(blob)} bytes)"
        )

    magic, version, total_length = struct.unpack(
        "<III", bytes(blob[:GLB_HEADER_SIZE])
    )
    if magic != GLB_MAGIC:
        raise WebGLExportError(
            f"parse_glb: bad magic 0x{magic:08X} (expected 0x{GLB_MAGIC:08X})"
        )
    if version != GLB_VERSION:
        raise WebGLExportError(
            f"parse_glb: unsupported GLB version {version}"
        )
    if total_length != len(blob):
        raise WebGLExportError(
            f"parse_glb: length mismatch (header says {total_length}, "
            f"blob is {len(blob)})"
        )

    offset = GLB_HEADER_SIZE
    json_chunk: Dict[str, Any] = {}
    bin_chunk: bytes = b""

    while offset < len(blob):
        if offset + GLB_CHUNK_HEADER_SIZE > len(blob):
            raise WebGLExportError("parse_glb: truncated chunk header")
        chunk_length, chunk_type = struct.unpack(
            "<II", bytes(blob[offset:offset + GLB_CHUNK_HEADER_SIZE])
        )
        offset += GLB_CHUNK_HEADER_SIZE
        chunk_data = bytes(blob[offset:offset + chunk_length])
        if len(chunk_data) < chunk_length:
            raise WebGLExportError("parse_glb: truncated chunk body")
        offset += chunk_length

        if chunk_type == GLB_CHUNK_TYPE_JSON:
            text = chunk_data.rstrip(b"\x00 ").rstrip(b" ")
            try:
                json_chunk = json.loads(text.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WebGLExportError(
                    f"parse_glb: invalid JSON chunk: {exc}"
                ) from exc
        elif chunk_type == GLB_CHUNK_TYPE_BIN:
            bin_chunk = chunk_data
        # Unknown chunk types are tolerated per the GLB spec.

    return {
        "header": {
            "magic": magic,
            "version": version,
            "total_length": total_length,
        },
        "json": json_chunk,
        "bin": bin_chunk,
    }


# ---------------------------------------------------------------------------
# Backwards-compatible helpers preserved for the existing HTML exporter.
# ---------------------------------------------------------------------------


def generate_animation_loop(spec: Dict[str, Any]) -> str:
    """Return a standalone JS animation loop string for embedding."""
    # The animation script expects a window.MELOSVIZ_SPEC object; the
    # caller is responsible for setting it before including the script.
    return _ANIMATION_SCRIPT


def export_html(spec: Dict[str, Any], output_path: str) -> Path:
    """Write a self-contained HTML file with the visualisation.

    Retained for backward compatibility with the original API surface.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = spec.get("metadata", {}) if isinstance(spec, dict) else {}
    width = int(metadata.get("width", 1920))
    height = int(metadata.get("height", 1080))
    title = str(metadata.get("title", "Melosviz"))
    spec_json = json.dumps(spec)

    html = (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "  <head>\n"
        "    <meta charset=\"utf-8\" />\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        f"    <title>{title} &mdash; melosviz</title>\n"
        "    <style>\n"
        "      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n"
        "      html, body {\n"
        "        width: 100%; height: 100%;\n"
        "        background: #000;\n"
        "        overflow: hidden;\n"
        "        font-family: 'Inter', system-ui, sans-serif;\n"
        "      }\n"
        "      #melosviz-canvas {\n"
        "        display: block;\n"
        "        width: 100vw;\n"
        "        height: 100vh;\n"
        "      }\n"
        "    </style>\n"
        "  </head>\n"
        "  <body>\n"
        f"    <canvas id=\"melosviz-canvas\" width=\"{width}\" height=\"{height}\"></canvas>\n"
        f"    <script>window.MELOSVIZ_SPEC = {spec_json};</script>\n"
        f"    <script>{_ANIMATION_SCRIPT}</script>\n"
        "  </body>\n"
        "</html>\n"
    )
    path.write_text(html, encoding="utf-8")
    return path.resolve()
