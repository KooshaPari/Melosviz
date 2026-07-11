// Pure interpolation helpers for RenderSpec keyframe data.
//
// This module is intentionally free of Three.js / React dependencies so
// it can be unit-tested in isolation (workstream D will swap lerp → spline).
//
// Workstream plug-in points (future):
//   D — replace lerpScalar with Catmull-Rom easing

import type { Keyframe } from '../renderSpec'

// ---- Exported types --------------------------------------------------------

export interface InterpolatedFrame {
  /** Camera spherical coordinates at this position. */
  camera: { distance: number; azimuth: number; elevation: number }
  /** Interpolated color palette at this position. */
  color: { primary: string; secondary: string; brightness: number }
  /** Normalised playhead position [0, 1]. */
  t: number
}

// ---- Private helpers -------------------------------------------------------

function lerpScalar(a: number, b: number, alpha: number): number {
  return a + (b - a) * alpha
}

/**
 * Convert a hex colour string (#rgb or #rrggbb) to an [r, g, b] tuple in [0, 1].
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
  return [((n >> 16) & 0xff) / 255, ((n >> 8) & 0xff) / 255, (n & 0xff) / 255]
}

function rgbToHex(r: number, g: number, b: number): string {
  const byte = (v: number) =>
    Math.round(Math.min(1, Math.max(0, v)) * 255)
      .toString(16)
      .padStart(2, '0')
  return `#${byte(r)}${byte(g)}${byte(b)}`
}

function lerpHex(hexA: string, hexB: string, alpha: number): string {
  const [ar, ag, ab] = hexToRgb(hexA)
  const [br, bg, bb] = hexToRgb(hexB)
  return rgbToHex(
    lerpScalar(ar, br, alpha),
    lerpScalar(ag, bg, alpha),
    lerpScalar(ab, bb, alpha),
  )
}

// ---- Public API ------------------------------------------------------------

/**
 * Interpolate between the two keyframes surrounding `t` and return a merged
 * `InterpolatedFrame`.
 *
 * - If `t` is before the first keyframe the first frame is returned as-is.
 * - If `t` is past the last keyframe the last frame is returned as-is.
 * - If `keyframes` is empty, a safe default frame is returned.
 *
 * @param keyframes - Array of keyframes (may be unsorted; sorted internally).
 * @param t - Normalised playhead position in [0, 1].
 */
export function lerpKeyframe(keyframes: Keyframe[], t: number): InterpolatedFrame {
  const clamped = Math.min(1, Math.max(0, t))

  if (keyframes.length === 0) {
    return {
      t: clamped,
      camera: { distance: 5, azimuth: 0, elevation: 0 },
      color: { primary: '#7c6af7', secondary: '#22d3ee', brightness: 0.8 },
    }
  }

  const sorted = [...keyframes].sort((a, b) => a.t - b.t)
  const first = sorted[0]!
  const last = sorted[sorted.length - 1]!

  // Before first keyframe
  if (clamped <= first.t) {
    return {
      t: clamped,
      camera: { ...first.camera },
      color: { ...first.color },
    }
  }

  // After last keyframe
  if (clamped >= last.t) {
    return {
      t: clamped,
      camera: { ...last.camera },
      color: { ...last.color },
    }
  }

  // Find surrounding pair
  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i]!
    const b = sorted[i + 1]!
    if (clamped >= a.t && clamped <= b.t) {
      const span = b.t - a.t
      const alpha = span < 1e-9 ? 0 : (clamped - a.t) / span

      return {
        t: clamped,
        camera: {
          distance: lerpScalar(a.camera.distance, b.camera.distance, alpha),
          azimuth: lerpScalar(a.camera.azimuth, b.camera.azimuth, alpha),
          elevation: lerpScalar(a.camera.elevation, b.camera.elevation, alpha),
        },
        color: {
          primary: lerpHex(a.color.primary, b.color.primary, alpha),
          secondary: lerpHex(a.color.secondary, b.color.secondary, alpha),
          brightness: lerpScalar(a.color.brightness, b.color.brightness, alpha),
        },
      }
    }
  }

  // Should not reach here given the guards above
  return { t: clamped, camera: { ...last.camera }, color: { ...last.color } }
}
