"""WebGL HTML export helpers for melosviz visual specs."""

from __future__ import annotations

import json
from pathlib import Path

_FRAG_HEADER = """
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
"""

_FRAG_UTILS = """
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
"""

_FRAG_MAIN = """
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

_FRAGMENT_SOURCE = _FRAG_HEADER + _FRAG_UTILS + _FRAG_MAIN


def _build_js(spec: dict) -> str:
    """Return the full inlined JS string that initialises and runs the WebGL canvas."""
    spec_json = json.dumps(spec)
    return f"""
(function() {{
  'use strict';
  const SPEC = {spec_json};

  /* ---------- helpers ---------- */
  function hexToRgb01(hex) {{
    const clean = (hex || '#00f5ff').replace('#', '');
    const full = clean.length === 3
      ? clean.split('').map(function(c) {{ return c + c; }}).join('')
      : clean;
    const n = parseInt(full, 16);
    return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255];
  }}

  /* ---------- WebGL init ---------- */
  var canvas = document.getElementById('melosviz-canvas');
  if (!canvas) {{ throw new Error('melosviz-canvas element not found'); }}

  var gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
  if (!gl) {{ throw new Error('WebGL not available in this browser.'); }}

  /* Shader sources — fragment drives the full visual */
  var VERT_SRC =
    'attribute vec2 aPos;' +
    'varying vec2 vUV;' +
    'void main() {{' +
    '  vUV = aPos * 0.5 + 0.5;' +
    '  gl_Position = vec4(aPos, 0.0, 1.0);' +
    '}}';

  var FRAG_SRC = {json.dumps(_FRAGMENT_SOURCE)};

  function compileShader(type, src) {{
    var sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {{
      throw new Error('Shader compile error: ' + (gl.getShaderInfoLog(sh) || '?'));
    }}
    return sh;
  }}

  var prog = gl.createProgram();
  gl.attachShader(prog, compileShader(gl.VERTEX_SHADER, VERT_SRC));
  gl.attachShader(prog, compileShader(gl.FRAGMENT_SHADER, FRAG_SRC));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {{
    throw new Error('Program link error: ' + (gl.getProgramInfoLog(prog) || '?'));
  }}

  /* Fullscreen quad buffer */
  var quadBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
  var aPos = gl.getAttribLocation(prog, 'aPos');
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

  /* Uniform locations */
  var uTime   = gl.getUniformLocation(prog, 'uTime');
  var uRes    = gl.getUniformLocation(prog, 'uRes');
  var uEnergy = gl.getUniformLocation(prog, 'uEnergy');
  var uHue    = gl.getUniformLocation(prog, 'uHue');
  var uInten  = gl.getUniformLocation(prog, 'uIntensity');
  var uC0     = gl.getUniformLocation(prog, 'uColor0');
  var uC1     = gl.getUniformLocation(prog, 'uColor1');
  var uC2     = gl.getUniformLocation(prog, 'uColor2');

  /* Palette from spec */
  var palette = SPEC.palette || ['#00f5ff', '#ff2fd5', '#8a75ff'];
  var c0 = hexToRgb01(palette[0]);
  var c1 = hexToRgb01(palette[1] || palette[0]);
  var c2 = hexToRgb01(palette[2] || palette[0]);

  /* Keyframe data */
  var keyframes = SPEC.keyframes || [];
  var frameCount = Math.max(keyframes.length, 1);
  var startTime = performance.now();

  /* Resize handling */
  function resize() {{
    var w = canvas.clientWidth  || 1920;
    var h = canvas.clientHeight || 1080;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {{
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
    }}
    gl.viewport(0, 0, canvas.width, canvas.height);
    return [canvas.width, canvas.height];
  }}

  /* Animation loop */
  var rafId = 0;
  function draw() {{
    var res = resize();
    var elapsed = (performance.now() - startTime) / 1000;
    var fi = Math.floor((elapsed * 30) % frameCount);
    var key = keyframes[fi] || {{ energy: 0.5, hue: 190, intensity: 0.6 }};

    gl.useProgram(prog);
    gl.uniform1f(uTime,   elapsed);
    gl.uniform2f(uRes,    res[0], res[1]);
    gl.uniform1f(uEnergy, key.energy    || 0.5);
    gl.uniform1f(uHue,    ((key.hue      || 190) / 360));
    gl.uniform1f(uInten,  key.intensity || 0.6);
    gl.uniform3f(uC0, c0[0], c0[1], c0[2]);
    gl.uniform3f(uC1, c1[0], c1[1], c1[2]);
    gl.uniform3f(uC2, c2[0], c2[1], c2[2]);

    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    rafId = requestAnimationFrame(draw);
  }}

  /* Start */
  resize();
  draw();

  /* ResizeObserver polyfill via rAF so IE11 compat is not needed (modern browsers only) */
  if (window.ResizeObserver) {{
    new ResizeObserver(draw).observe(canvas.parentElement || canvas);
  }}
}})();
"""


def generate_animation_loop(spec: dict) -> str:
    """Return a standalone JS animation loop string for embedding."""
    return _build_js(spec)


def export_html(spec: dict, output_path: str) -> Path:
    """Write a self-contained HTML file with the visualisation."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = spec.get("metadata", {})
    width = int(metadata.get("width", 1920))
    height = int(metadata.get("height", 1080))
    fps = int(metadata.get("fps", 30))
    title = str(metadata.get("title", "Melosviz"))
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title} — melosviz</title>
    <style>
      *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
      html, body {{
        width: 100%; height: 100%;
        background: #000;
        overflow: hidden;
        font-family: 'Inter', system-ui, sans-serif;
      }}
      #melosviz-canvas {{
        display: block;
        width: 100vw;
        height: 100vh;
      }}
      /* Overlay title card */
      #overlay {{
        position: fixed;
        bottom: 24px;
        left: 28px;
        pointer-events: none;
        user-select: none;
      }}
      #overlay p {{
        font-size: 11px;
        letter-spacing: 0.32em;
        text-transform: uppercase;
        color: rgba(255,255,255,0.28);
      }}
      #overlay h1 {{
        font-size: 18px;
        font-weight: 900;
        letter-spacing: 0.06em;
        color: rgba(255,255,255,0.55);
        text-shadow: 0 0 18px rgba(0,245,255,0.5);
      }}
    </style>
  </head>
  <body>
    <canvas id="melosviz-canvas" width="{width}" height="{height}"></canvas>
    <div id="overlay">
      <p>melosviz</p>
      <h1>{title}</h1>
    </div>
    <script>{_build_js(spec)}</script>
  </body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path.resolve()
