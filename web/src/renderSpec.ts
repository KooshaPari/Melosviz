// Typed interface for the render spec data-binding seam.
//
// The backend's spec_builder.py emits a RenderSpec with shot-level keyframes;
// this module defines the canonical TS shape and helpers to translate keyframes
// into per-frame SceneParams consumed by the R3F renderer.
//
// Workstream plug-in points (future):
//   A — spectral textures: extend SpectralFrame, pass into SceneParams.spectral
//   B — beat particles: beat_anchor events → SceneParams.beatEnergy
//   D — dense spline morphing: replace lerp below with Catmull-Rom easing

// ---- Source types (from backend JSON) -----------------------------------

export interface KeyframeCamera {
  /** Camera Z distance from origin (depth / zoom). */
  distance: number
  /** Camera azimuth in radians. */
  azimuth: number
  /** Camera elevation in radians. */
  elevation: number
}

export interface KeyframeColor {
  /** Hex string, e.g. "#7c3aed". */
  primary: string
  /** Hex string for secondary accent. */
  secondary: string
  /** Overall scene brightness [0, 1]. */
  brightness: number
}

export interface Keyframe {
  /** Normalised position in [0, 1] representing time within the track. */
  t: number
  camera: KeyframeCamera
  color: KeyframeColor
  /** Name of the scene / shot label (e.g. "Establishing", "Anthem"). */
  scene?: string
}

export interface RenderSpec {
  /** Track duration in seconds (used to map absolute time → t). */
  durationSecs: number
  keyframes: Keyframe[]
  /** Optional BPM for beat-locked downstream workstreams. */
  bpm?: number
}

// ---- Runtime types consumed by the R3F scene-graph ----------------------

/** SceneParams is the per-frame data contract between spec and renderer. */
export interface SceneParams {
  camera: KeyframeCamera
  color: KeyframeColor
  /** Normalised playhead position [0, 1]. */
  t: number
  /** Beat energy [0, 1] — 0 until workstream B wires in beat events. */
  beatEnergy: number
  /** Spectral data placeholder — null until workstream A wires in FFT. */
  spectral: Float32Array | null
}

// ---- Helpers -------------------------------------------------------------

/**
 * Linear-interpolate a single scalar.
 * Workstream D will replace this with Catmull-Rom / easing curves.
 */
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

/**
 * Parse a hex color string to an [r, g, b] tuple in [0, 1].
 * Handles 3- and 6-digit forms.
 */
export function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '')
  const expanded =
    clean.length === 3
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean
  const n = parseInt(expanded, 16)
  return [
    ((n >> 16) & 0xff) / 255,
    ((n >> 8) & 0xff) / 255,
    (n & 0xff) / 255,
  ]
}

/**
 * Interpolate between two adjacent keyframes, returning a merged
 * KeyframeCamera and KeyframeColor.
 */
function interpKeyframes(a: Keyframe, b: Keyframe, alpha: number): Omit<SceneParams, 't' | 'beatEnergy' | 'spectral'> {
  const camera: KeyframeCamera = {
    distance: lerp(a.camera.distance, b.camera.distance, alpha),
    azimuth: lerp(a.camera.azimuth, b.camera.azimuth, alpha),
    elevation: lerp(a.camera.elevation, b.camera.elevation, alpha),
  }

  // Interpolate each RGB channel independently
  const [ar, ag, ab] = hexToRgb(a.color.primary)
  const [br, bg, bb] = hexToRgb(b.color.primary)
  const [ar2, ag2, ab2] = hexToRgb(a.color.secondary)
  const [br2, bg2, bb2] = hexToRgb(b.color.secondary)

  const toHex = (r: number, g: number, bl: number): string => {
    const byte = (v: number) =>
      Math.round(Math.min(1, Math.max(0, v)) * 255)
        .toString(16)
        .padStart(2, '0')
    return `#${byte(r)}${byte(g)}${byte(bl)}`
  }

  const color: KeyframeColor = {
    primary: toHex(lerp(ar, br, alpha), lerp(ag, bg, alpha), lerp(ab, bb, alpha)),
    secondary: toHex(
      lerp(ar2, br2, alpha),
      lerp(ag2, bg2, alpha),
      lerp(ab2, bb2, alpha),
    ),
    brightness: lerp(a.color.brightness, b.color.brightness, alpha),
  }

  return { camera, color }
}

/**
 * Convert an absolute playhead time (seconds) and a RenderSpec into a
 * SceneParams object for the current frame.
 *
 * Beat energy and spectral data default to 0/null; downstream workstreams
 * (B, A) overlay those values before passing to the renderer.
 */
export function specToSceneParams(
  spec: RenderSpec,
  currentTimeSecs: number,
  beatEnergy = 0,
  spectral: Float32Array | null = null,
): SceneParams {
  const { keyframes, durationSecs } = spec
  const t = Math.min(1, Math.max(0, currentTimeSecs / Math.max(durationSecs, 0.001)))

  if (keyframes.length === 0) {
    return {
      t,
      beatEnergy,
      spectral,
      camera: { distance: 5, azimuth: 0, elevation: 0 },
      color: { primary: '#7c3aed', secondary: '#06b6d4', brightness: 0.8 },
    }
  }

  // Find the surrounding pair
  const sorted = [...keyframes].sort((a, b) => a.t - b.t)
  const last = sorted[sorted.length - 1]!

  if (t <= sorted[0]!.t) {
    return { t, beatEnergy, spectral, ...interpKeyframes(sorted[0]!, sorted[0]!, 0) }
  }
  if (t >= last.t) {
    return { t, beatEnergy, spectral, ...interpKeyframes(last, last, 0) }
  }

  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i]!
    const b = sorted[i + 1]!
    if (t >= a.t && t <= b.t) {
      const span = b.t - a.t
      const alpha = span < 1e-9 ? 0 : (t - a.t) / span
      return { t, beatEnergy, spectral, ...interpKeyframes(a, b, alpha) }
    }
  }

  // Fallback — should not reach here
  return { t, beatEnergy, spectral, ...interpKeyframes(last, last, 0) }
}
