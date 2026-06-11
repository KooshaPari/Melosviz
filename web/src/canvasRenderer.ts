export interface AudioData {
  energy: number
  beatFlash: number
  downbeatFlash: number
  beatPhase: number
  intensity: number
  hue: number
  frequencyData: Uint8Array
}

const VERT = `
attribute vec2 aPos;
varying vec2 vUV;
void main() {
  vUV = aPos * 0.5 + 0.5;
  gl_Position = vec4(aPos, 0.0, 1.0);
}
`

const FRAG = `
precision highp float;
varying vec2 vUV;
uniform float uTime;
uniform vec2 uRes;
uniform float uEnergy;
uniform float uHue;
uniform float uIntensity;
uniform vec3 uColor0;
uniform vec3 uColor1;
uniform vec3 uColor2;
uniform int uSceneType;
uniform float uSceneAge;
uniform float uSceneLen;
uniform float uBeatFlash;
uniform float uDownbeatFlash;
uniform float uZoom;
uniform vec2 uPan;
uniform float uRotation;
uniform float uBeatPhase;
uniform float uCameraTilt;
uniform float uMotionSpeed;
uniform int uOverlayCount;
uniform float uOverlayEnergy;
uniform vec2 uLight0;
uniform vec2 uLight1;
uniform float uLightRadius;

#define TAU 6.28318530718

float ring(vec2 p, float r, float w) {
  return smoothstep(w, 0.0, abs(length(p) - r));
}

float ringSdf(vec2 p, float r, float w) {
  return abs(length(p) - r) - w;
}

float sdHex(vec2 p, float r) {
  const vec3 k = vec3(-0.8660254, 0.5, 0.5773503);
  p = abs(p);
  p -= 2.0 * min(dot(k.xy, p), 0.0) * k.xy;
  p -= vec2(clamp(p.x, -k.z * r, k.z * r), r);
  return length(p) * sign(p.y);
}

float sdBox(vec2 p, vec2 b) {
  vec2 d = abs(p) - b;
  return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}

float sdTri(vec2 p, float r) {
  const float k = 1.7320508;
  p.x = abs(p.x) - r;
  p.y = p.y + r / k;
  if (p.x + k * p.y > 0.0) p = vec2(p.x - k * p.y, -k * p.x - p.y) / 2.0;
  p.x -= clamp(p.x, -2.0 * r, 0.0);
  return -length(p) * sign(p.y);
}

vec2 toPolar(vec2 p) { return vec2(length(p), atan(p.y, p.x)); }

float hash(float n) { return fract(sin(n) * 43758.5453); }
float noise1(float x) {
  float i = floor(x), f = fract(x);
  return mix(hash(i), hash(i + 1.0), f * f * (3.0 - 2.0 * f));
}

float beatPulse(float t, float freq, float decay) {
  float p = fract(t * freq);
  return exp(-p / max(decay, 0.001)) * (1.0 - p);
}

vec2 orbit(float t, float speed, float radius, float wobble) {
  float a = t * speed;
  float w = noise1(t * speed * 0.3) * wobble;
  return vec2(cos(a) * (radius + w), sin(a) * (radius + w * 0.6));
}

vec2 camTransform(vec2 p) {
  float tilt = uCameraTilt * 0.04;
  float ca = cos(tilt), sa = sin(tilt);
  return vec2(p.x * ca - p.y * sa, p.x * sa + p.y * ca);
}

float spotlight(vec2 p, vec2 center, float radius, float softness) {
  return smoothstep(radius + softness, radius - softness, length(p - center));
}

float spotlightRing(vec2 p, vec2 center, float radius, float width) {
  return smoothstep(width, 0.0, abs(length(p - center) - radius));
}

float beatGrid(vec2 p, float t, float spacing, float rotation) {
  float s = sin(rotation), c = cos(rotation);
  vec2 rp = vec2(p.x * c - p.y * s, p.x * s + p.y * c);
  vec2 grid = abs(fract(rp * spacing - t * 0.2) - 0.5);
  float line = min(grid.x, grid.y);
  return smoothstep(0.02, 0.0, line) * 0.5;
}

vec3 hsb2rgb(vec3 c) {
  vec3 p = abs(fract(c.x + vec3(1.0, 2.0/3.0, 1.0/3.0)) * 6.0 - 3.0);
  return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

vec3 scenePlaceholder(vec2 uv, float t) {
  float beat = beatPulse(t, uBeatPhase * 2.0, 0.08) * uBeatFlash;
  float en = uEnergy;
  vec2 p = uv / uZoom;
  float r = ring(p, 0.3 + en * 0.1, 0.01);
  vec3 col = uColor0 * 0.05 + uColor1 * r * 0.4 + uColor2 * beat * 0.15;
  return col;
}

vec3 sceneEstablishing(vec2 uv, float t) {
  float beat = beatPulse(t, uBeatPhase * 2.0, 0.08) * uBeatFlash;
  float downbeat = uDownbeatFlash;
  float en = uEnergy;
  vec2 p = uv / uZoom;
  float h = sdHex(p, 0.25 + en * 0.05);
  float hex = smoothstep(0.006, 0.0, h);
  float r = ring(p, 0.35, 0.005);
  vec3 col = uColor0 * 0.05 + uColor1 * hex * 0.35 + uColor2 * r * 0.3 + uColor1 * beat * 0.2;
  return col;
}

vec3 scenePerformance(vec2 uv, float t) {
  float beat = beatPulse(t, uBeatPhase * 2.0, 0.08) * uBeatFlash;
  float downbeat = uDownbeatFlash;
  float en = uEnergy;
  float inten = uIntensity;
  vec2 p = camTransform(uv) / uZoom;
  float bars = 0.0;
  for (int i = 0; i < 8; i++) {
    float fi = float(i);
    float x = fi / 8.0 - 0.5;
    float h = abs(sin(t * 2.0 + fi * 0.7)) * (0.1 + en * 0.2);
    bars += smoothstep(0.004, 0.0, abs(sdBox(p - vec2(x, 0.0), vec2(0.02, h))));
  }
  bars *= 0.05 * (0.5 + en * 1.2 + beat * 1.5);
  float pulse = sin(t * 3.5) * 0.5 + 0.5;
  float pulse2 = sin(t * 5.8 + 1.1) * 0.5 + 0.5;
  float pulse3 = sin(t * 2.1 + 2.3) * 0.5 + 0.5;
  float r1 = ring(p, 0.38 + pulse * 0.06, 0.006);
  float r2 = ring(p, 0.26 + pulse2 * 0.04, 0.005);
  float r3 = ring(p, 0.17 + pulse3 * 0.07, 0.004);
  vec2 lightCenter = vec2(sin(t * 0.4) * 0.15, cos(t * 0.3) * 0.1);
  float spot = spotlightRing(p, lightCenter, 0.22 + beat * 0.08, 0.008 + beat * 0.006);
  float bg0 = spotlight(p, uLight0, uLightRadius, 0.22);
  float bg1 = spotlight(p, uLight1, uLightRadius * 0.9, 0.18);
  vec3 bg = uColor0 * 0.06 + uColor1 * bg0 * 0.1 + uColor2 * bg1 * 0.08;
  vec3 col = bg;
  col = mix(col, uColor1 * 0.4, r1 * 0.9);
  col = mix(col, uColor1 * 0.3, r2 * 0.8);
  col = mix(col, uColor1 * 0.25, r3 * 0.7);
  col += uColor1 * bars * (1.0 + beat * 0.8);
  col += uColor2 * spot * (0.5 + beat * 1.5);
  col += uColor0 * downbeat * 0.2;
  col += uColor2 * beat * 0.12;
  return col;
}

vec3 sceneAnthem(vec2 uv, float t) {
  float beat = beatPulse(t, uBeatPhase * 2.0, 0.08) * uBeatFlash;
  float downbeat = uDownbeatFlash;
  float en = uEnergy;
  float inten = uIntensity;
  float tilt = uCameraTilt * 0.04;
  float ca = cos(tilt), sa = sin(tilt);
  vec2 p = vec2(uv.x * ca - uv.y * sa, uv.x * sa + uv.y * ca) / uZoom;
  vec2 pol = toPolar(p);
  float kSides = 8.0 + floor(en * 4.0);
  float kaleAngle = mod(pol.y, TAU / kSides) - TAU / kSides * 0.5;
  vec2 kUv = vec2(pol.x * cos(kaleAngle), pol.x * sin(kaleAngle));
  float grid = beatGrid(kUv, t, 8.0 + en * 6.0, kSides * 2.0);
  float hexBurst = 0.0;
  for (int i = 0; i < 5; i++) {
    float fi = float(i);
    float phase = fract(fi / 5.0 + t * 0.5 + uBeatPhase * fi * 0.2);
    float radius = phase * (0.45 + inten * 0.2);
    float w = 0.004 + (1.0 - phase) * 0.008;
    float hv = smoothstep(w, 0.0, abs(sdHex(kUv, radius)));
    float fade = smoothstep(0.0, 0.12, phase) * smoothstep(1.0, 0.6, phase);
    hexBurst += hv * fade * (1.0 + beat * 2.0);
  }
  vec2 lightCenter = vec2(sin(t * 0.6) * 0.12, cos(t * 0.45) * 0.09);
  float spot = spotlight(p, lightCenter, 0.2 + beat * 0.15, 0.06);
  float spotRing = spotlightRing(p, lightCenter, 0.2 + beat * 0.15, 0.005 + beat * 0.004);
  float bg0 = spotlight(p, uLight0, uLightRadius * 1.5, 0.28);
  float bg1 = spotlight(p, uLight1, uLightRadius * 1.2, 0.22);
  vec3 bg = uColor0 * 0.09 + uColor1 * bg0 * 0.12 + uColor2 * bg1 * 0.1;
  vec3 col = bg;
  col = mix(col, uColor1 * 0.6, grid * (0.5 + beat * 1.2));
  col += uColor2 * hexBurst * 0.8;
  col += uColor0 * spot * (0.3 + beat * 0.7);
  col += uColor2 * spotRing * (0.6 + beat * 1.4);
  col += uColor1 * downbeat * 0.35;
  col += uColor0 * beat * 0.2;
  col += uColor2 * beat * 0.15;
  return col;
}

vec3 sceneInterlude(vec2 uv, float t) {
  float beat = beatPulse(t, uBeatPhase * 0.5, 0.25) * uBeatFlash;
  float en = uEnergy;
  float inten = uIntensity;
  vec2 p = uv / uZoom;
  float tri1 = smoothstep(0.006, 0.0, sdTri(p - vec2(sin(t * 0.2) * 0.15, cos(t * 0.15) * 0.1), 0.1 + inten * 0.05));
  float tri2 = smoothstep(0.006, 0.0, sdTri(p - vec2(cos(t * 0.18 + 2.0) * 0.18, sin(t * 0.13 + 1.0) * 0.12), 0.07 + en * 0.03));
  float bg0 = spotlight(p, uLight0, uLightRadius * 0.8, 0.35);
  float bg1 = spotlight(p, uLight1, uLightRadius * 0.6, 0.28);
  vec3 bg = uColor0 * 0.12 + uColor1 * bg0 * 0.08 + uColor2 * bg1 * 0.06;
  vec3 col = bg;
  col += uColor2 * tri1 * 0.5;
  col += uColor1 * tri2 * 0.4;
  col += uColor0 * beat * 0.15;
  return col;
}

vec3 sceneOutro(vec2 uv, float t) {
  float beat = beatPulse(t, uBeatPhase * 0.5, 0.25) * uBeatFlash;
  float en = uEnergy;
  vec2 p = uv / uZoom;
  float r = ring(p, 0.2 + en * 0.05, 0.008);
  float fade = smoothstep(0.0, 1.0, t * 0.5);
  vec3 bg = uColor0 * 0.02 + uColor1 * 0.02 + uColor2 * 0.02;
  vec3 col = bg + uColor1 * r * 0.5 * fade;
  col += uColor2 * beat * 0.1 * fade;
  return col;
}

void main() {
  vec2 uv = (vUV - 0.5) * 2.0;
  uv.x *= uRes.x / uRes.y;
  uv += uPan;
  float t = uTime * uMotionSpeed;
  vec3 col;
  if (uSceneType == 0) col = scenePlaceholder(uv, t);
  else if (uSceneType == 1) col = sceneEstablishing(uv, t);
  else if (uSceneType == 2) col = scenePerformance(uv, t);
  else if (uSceneType == 3) col = sceneAnthem(uv, t);
  else if (uSceneType == 4) col = sceneInterlude(uv, t);
  else col = sceneOutro(uv, t);
  col = pow(col, vec3(0.4545));
  gl_FragColor = vec4(col, 1.0);
}
`

export class CanvasRenderer {
  private gl: WebGLRenderingContext
  private program: WebGLProgram
  private uniforms: Record<string, WebGLUniformLocation | null>
  private startTime: number
  private scene = 0
  private audioData: AudioData = {
    energy: 0,
    beatFlash: 0,
    downbeatFlash: 0,
    beatPhase: 0,
    intensity: 0,
    hue: 0,
    frequencyData: new Uint8Array(0),
  }
  private dpr: number

  constructor(private canvas: HTMLCanvasElement) {
    this.dpr = Math.min(window.devicePixelRatio || 1, 2)
    const gl = canvas.getContext('webgl', {
      alpha: false,
      antialias: false,
      premultipliedAlpha: false,
    })
    if (!gl) throw new Error('WebGL not supported')
    this.gl = gl

    this.program = this.createProgram(VERT, FRAG)
    this.uniforms = {
      uTime: this.getUniform('uTime'),
      uRes: this.getUniform('uRes'),
      uEnergy: this.getUniform('uEnergy'),
      uHue: this.getUniform('uHue'),
      uIntensity: this.getUniform('uIntensity'),
      uColor0: this.getUniform('uColor0'),
      uColor1: this.getUniform('uColor1'),
      uColor2: this.getUniform('uColor2'),
      uSceneType: this.getUniform('uSceneType'),
      uSceneAge: this.getUniform('uSceneAge'),
      uSceneLen: this.getUniform('uSceneLen'),
      uBeatFlash: this.getUniform('uBeatFlash'),
      uDownbeatFlash: this.getUniform('uDownbeatFlash'),
      uZoom: this.getUniform('uZoom'),
      uPan: this.getUniform('uPan'),
      uRotation: this.getUniform('uRotation'),
      uBeatPhase: this.getUniform('uBeatPhase'),
      uCameraTilt: this.getUniform('uCameraTilt'),
      uMotionSpeed: this.getUniform('uMotionSpeed'),
      uOverlayCount: this.getUniform('uOverlayCount'),
      uOverlayEnergy: this.getUniform('uOverlayEnergy'),
      uLight0: this.getUniform('uLight0'),
      uLight1: this.getUniform('uLight1'),
      uLightRadius: this.getUniform('uLightRadius'),
    }

    this.startTime = performance.now()
    this.setupGeometry()
    this.resize()
    window.addEventListener('resize', this.resize)
  }

  setScene(s: number) {
    this.scene = s
  }

  updateAudioData(data: AudioData) {
    this.audioData = data
  }

  render() {
    const gl = this.gl
    const t = (performance.now() - this.startTime) / 1000

    gl.viewport(0, 0, this.canvas.width, this.canvas.height)
    gl.clearColor(0, 0, 0, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.useProgram(this.program)

    const hue = this.audioData.hue / 360
    const c0 = this.hslToRgb(hue, 0.7, 0.05)
    const c1 = this.hslToRgb(hue + 0.05, 0.85, 0.55)
    const c2 = this.hslToRgb(hue + 0.15, 0.75, 0.45)

    gl.uniform1f(this.uniforms.uTime, t)
    gl.uniform2f(this.uniforms.uRes, this.canvas.width, this.canvas.height)
    gl.uniform1f(this.uniforms.uEnergy, this.audioData.energy)
    gl.uniform1f(this.uniforms.uHue, this.audioData.hue)
    gl.uniform1f(this.uniforms.uIntensity, this.audioData.intensity)
    gl.uniform3f(this.uniforms.uColor0, c0[0], c0[1], c0[2])
    gl.uniform3f(this.uniforms.uColor1, c1[0], c1[1], c1[2])
    gl.uniform3f(this.uniforms.uColor2, c2[0], c2[1], c2[2])
    gl.uniform1i(this.uniforms.uSceneType, this.scene)
    gl.uniform1f(this.uniforms.uSceneAge, t)
    gl.uniform1f(this.uniforms.uSceneLen, 60)
    gl.uniform1f(this.uniforms.uBeatFlash, this.audioData.beatFlash)
    gl.uniform1f(this.uniforms.uDownbeatFlash, this.audioData.downbeatFlash)
    gl.uniform1f(this.uniforms.uZoom, 1.0 + this.audioData.energy * 0.2)
    gl.uniform2f(this.uniforms.uPan, 0, 0)
    gl.uniform1f(this.uniforms.uRotation, 0)
    gl.uniform1f(this.uniforms.uBeatPhase, this.audioData.beatPhase)
    gl.uniform1f(this.uniforms.uCameraTilt, this.audioData.energy * 0.5)
    gl.uniform1f(this.uniforms.uMotionSpeed, 1.0)
    gl.uniform1i(this.uniforms.uOverlayCount, 0)
    gl.uniform1f(this.uniforms.uOverlayEnergy, 0)
    gl.uniform2f(this.uniforms.uLight0, Math.sin(t * 0.3) * 0.2, Math.cos(t * 0.25) * 0.15)
    gl.uniform2f(this.uniforms.uLight1, Math.cos(t * 0.2) * 0.25, Math.sin(t * 0.35) * 0.18)
    gl.uniform1f(this.uniforms.uLightRadius, 0.3 + this.audioData.energy * 0.1)

    gl.drawArrays(gl.TRIANGLES, 0, 6)
  }

  resize = () => {
    const rect = this.canvas.getBoundingClientRect()
    this.canvas.width = rect.width * this.dpr
    this.canvas.height = rect.height * this.dpr
  }

  dispose() {
    window.removeEventListener('resize', this.resize)
    this.gl.deleteProgram(this.program)
  }

  private createShader(type: number, source: string): WebGLShader {
    const gl = this.gl
    const shader = gl.createShader(type)!
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) || 'Shader compile error')
    }
    return shader
  }

  private createProgram(vs: string, fs: string): WebGLProgram {
    const gl = this.gl
    const program = gl.createProgram()!
    gl.attachShader(program, this.createShader(gl.VERTEX_SHADER, vs))
    gl.attachShader(program, this.createShader(gl.FRAGMENT_SHADER, fs))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || 'Program link error')
    }
    return program
  }

  private getUniform(name: string): WebGLUniformLocation | null {
    return this.gl.getUniformLocation(this.program, name)
  }

  private setupGeometry() {
    const gl = this.gl
    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, -1, 1, 1, -1, 1]),
      gl.STATIC_DRAW,
    )
    const aPos = gl.getAttribLocation(this.program, 'aPos')
    gl.enableVertexAttribArray(aPos)
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0)
  }

  private hslToRgb(h: number, s: number, l: number): [number, number, number] {
    const k = (n: number) => (n + h * 12) % 12
    const a = s * Math.min(l, 1 - l)
    const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
    return [f(0), f(8), f(4)]
  }
}
