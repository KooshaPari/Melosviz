// Basic WebGL2 3D scene renderer for melosviz.
// Renders a solid-color rotating quad at the display's native refresh rate
// (target 60fps). Vanilla WebGL2; no Three.js or other 3D dependencies.

const VERT_SRC = `#version 300 es
in vec3 aPos;
uniform mat4 uMVP;
void main() {
  gl_Position = uMVP * vec4(aPos, 1.0);
}
`

const FRAG_SRC = `#version 300 es
precision highp float;
uniform vec4 uColor;
out vec4 outColor;
void main() {
  outColor = uColor;
}
`

// --- Minimal 4x4 column-major matrix math (OpenGL convention) ---

type Mat4 = Float32Array

function mat4Identity(): Mat4 {
  const m = new Float32Array(16)
  m[0] = 1
  m[5] = 1
  m[10] = 1
  m[15] = 1
  return m
}

function mat4Multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Float32Array(16)
  for (let col = 0; col < 4; col++) {
    for (let row = 0; row < 4; row++) {
      let sum = 0
      for (let k = 0; k < 4; k++) {
        sum += a[k * 4 + row] * b[col * 4 + k]
      }
      out[col * 4 + row] = sum
    }
  }
  return out
}

function mat4Perspective(
  fovY: number,
  aspect: number,
  near: number,
  far: number,
): Mat4 {
  const f = 1 / Math.tan(fovY / 2)
  const nf = 1 / (near - far)
  const m = new Float32Array(16)
  m[0] = f / aspect
  m[5] = f
  m[10] = (far + near) * nf
  m[11] = -1
  m[14] = 2 * far * near * nf
  return m
}

function mat4Translation(x: number, y: number, z: number): Mat4 {
  const m = mat4Identity()
  m[12] = x
  m[13] = y
  m[14] = z
  return m
}

function mat4RotationX(angle: number): Mat4 {
  const c = Math.cos(angle)
  const s = Math.sin(angle)
  const m = mat4Identity()
  m[5] = c
  m[6] = s
  m[9] = -s
  m[10] = c
  return m
}

function mat4RotationY(angle: number): Mat4 {
  const c = Math.cos(angle)
  const s = Math.sin(angle)
  const m = mat4Identity()
  m[0] = c
  m[2] = -s
  m[8] = s
  m[10] = c
  return m
}

// Default target frame rate for the render loop. Declared as a typed
// const so consumers can read it without a separate export surface.
const _DEFAULT_FPS: number = 60

export class CanvasRenderer {
  readonly targetFps: number = _DEFAULT_FPS
  private gl: WebGL2RenderingContext
  private program: WebGLProgram
  private vao: WebGLVertexArrayObject
  private vbo: WebGLBuffer
  private uMVP: WebGLUniformLocation | null
  private uColor: WebGLUniformLocation | null
  private startTime: number
  private aspect: number
  private projection: Mat4
  private view: Mat4
  private model: Mat4
  private mvp: Mat4

  constructor(canvas: HTMLCanvasElement, gl: WebGL2RenderingContext) {
    this.gl = gl
    this.startTime = performance.now()
    this.aspect = canvas.width / Math.max(canvas.height, 1)
    this.projection = mat4Perspective(Math.PI / 4, this.aspect, 0.1, 100)
    this.view = mat4Translation(0, 0, -3)
    this.model = mat4Identity()
    this.mvp = mat4Identity()

    const vs = this.compileShader(gl.VERTEX_SHADER, VERT_SRC)
    const fs = this.compileShader(gl.FRAGMENT_SHADER, FRAG_SRC)
    this.program = this.linkProgram(vs, fs)

    this.uMVP = gl.getUniformLocation(this.program, 'uMVP')
    this.uColor = gl.getUniformLocation(this.program, 'uColor')

    // Two triangles forming a unit quad in the XY plane, centered at origin.
    const quad = new Float32Array([
      -0.5, -0.5, 0,
       0.5, -0.5, 0,
      -0.5,  0.5, 0,
      -0.5,  0.5, 0,
       0.5, -0.5, 0,
       0.5,  0.5, 0,
    ])

    this.vao = gl.createVertexArray()!
    gl.bindVertexArray(this.vao)

    this.vbo = gl.createBuffer()!
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo)
    gl.bufferData(gl.ARRAY_BUFFER, quad, gl.STATIC_DRAW)

    const aPos = gl.getAttribLocation(this.program, 'aPos')
    gl.enableVertexAttribArray(aPos)
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0)

    gl.bindVertexArray(null)

    gl.viewport(0, 0, canvas.width, canvas.height)
    gl.clearColor(0, 0, 0, 1)
  }

  setViewport(width: number, height: number): void {
    this.aspect = width / Math.max(height, 1)
    this.projection = mat4Perspective(Math.PI / 4, this.aspect, 0.1, 100)
    this.gl.viewport(0, 0, width, height)
  }

  render(): void {
    const gl = this.gl
    const t = (performance.now() - this.startTime) / 1000

    // Continuous model rotation so the 3D pipeline is visibly exercised
    // every frame. A consumer driving requestAnimationFrame easily hits
    // the _DEFAULT_FPS target on this single-draw workload.
    const rx = mat4RotationX(t * 0.7)
    const ry = mat4RotationY(t * 0.9)
    this.model = mat4Multiply(rx, ry)
    this.mvp = mat4Multiply(
      this.projection,
      mat4Multiply(this.view, this.model),
    )

    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.useProgram(this.program)

    gl.uniformMatrix4fv(this.uMVP, false, this.mvp)
    gl.uniform4f(
      this.uColor,
      0.4 + 0.4 * Math.sin(t),
      0.5,
      0.8 - 0.3 * Math.cos(t * 0.5),
      1.0,
    )

    gl.bindVertexArray(this.vao)
    gl.drawArrays(gl.TRIANGLES, 0, 6)
    gl.bindVertexArray(null)
  }

  dispose(): void {
    const gl = this.gl
    gl.deleteBuffer(this.vbo)
    gl.deleteVertexArray(this.vao)
    gl.deleteProgram(this.program)
  }

  private compileShader(type: number, source: string): WebGLShader {
    const gl = this.gl
    const shader = gl.createShader(type)!
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(shader) ?? 'Shader compile error'
      gl.deleteShader(shader)
      throw new Error(log)
    }
    return shader
  }

  private linkProgram(vs: WebGLShader, fs: WebGLShader): WebGLProgram {
    const gl = this.gl
    const program = gl.createProgram()!
    gl.attachShader(program, vs)
    gl.attachShader(program, fs)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const log = gl.getProgramInfoLog(program) ?? 'Program link error'
      gl.deleteProgram(program)
      throw new Error(log)
    }
    return program
  }
}
