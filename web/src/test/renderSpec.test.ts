// TDD tests for the renderSpec data-binding seam.
//
// These cover specToSceneParams, hexToRgb, and the interpolation contract
// so workstreams A/B/D can extend them without regressions.

import { describe, it, expect } from 'vitest'
import {
  specToSceneParams,
  hexToRgb,
} from '../renderSpec'
import type { RenderSpec } from '../renderSpec'

const SIMPLE_SPEC: RenderSpec = {
  durationSecs: 100,
  keyframes: [
    {
      t: 0,
      camera: { distance: 10, azimuth: 0, elevation: 0 },
      color: { primary: '#000000', secondary: '#ffffff', brightness: 0.5 },
    },
    {
      t: 1,
      camera: { distance: 20, azimuth: 1, elevation: 0.5 },
      color: { primary: '#ff0000', secondary: '#0000ff', brightness: 1.0 },
    },
  ],
}

// ---- hexToRgb -----------------------------------------------------------

describe('hexToRgb', () => {
  it('converts 6-digit hex to [r,g,b] in [0,1]', () => {
    const [r, g, b] = hexToRgb('#ff0000')
    expect(r).toBeCloseTo(1)
    expect(g).toBeCloseTo(0)
    expect(b).toBeCloseTo(0)
  })

  it('converts 3-digit hex', () => {
    const [r, g, b] = hexToRgb('#f00')
    expect(r).toBeCloseTo(1)
    expect(g).toBeCloseTo(0)
    expect(b).toBeCloseTo(0)
  })

  it('converts white correctly', () => {
    const [r, g, b] = hexToRgb('#ffffff')
    expect(r).toBeCloseTo(1)
    expect(g).toBeCloseTo(1)
    expect(b).toBeCloseTo(1)
  })

  it('converts black correctly', () => {
    const [r, g, b] = hexToRgb('#000000')
    expect(r).toBeCloseTo(0)
    expect(g).toBeCloseTo(0)
    expect(b).toBeCloseTo(0)
  })
})

// ---- specToSceneParams --------------------------------------------------

describe('specToSceneParams', () => {
  it('returns t=0 params at time 0', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 0)
    expect(p.t).toBeCloseTo(0)
    expect(p.camera.distance).toBeCloseTo(10)
    expect(p.camera.azimuth).toBeCloseTo(0)
  })

  it('returns t=1 params at durationSecs', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 100)
    expect(p.t).toBeCloseTo(1)
    expect(p.camera.distance).toBeCloseTo(20)
    expect(p.camera.azimuth).toBeCloseTo(1)
  })

  it('interpolates camera distance at t=0.5 (midpoint)', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 50)
    expect(p.t).toBeCloseTo(0.5)
    // Midpoint between distance 10 and 20 = 15
    expect(p.camera.distance).toBeCloseTo(15)
    expect(p.camera.azimuth).toBeCloseTo(0.5)
    expect(p.camera.elevation).toBeCloseTo(0.25)
  })

  it('interpolates color brightness at t=0.5', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 50)
    // Midpoint between 0.5 and 1.0 = 0.75
    expect(p.color.brightness).toBeCloseTo(0.75)
  })

  it('clamps t < 0 to first keyframe', () => {
    const p = specToSceneParams(SIMPLE_SPEC, -10)
    expect(p.t).toBeCloseTo(0)
    expect(p.camera.distance).toBeCloseTo(10)
  })

  it('clamps t > 1 to last keyframe', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 999)
    expect(p.t).toBeCloseTo(1)
    expect(p.camera.distance).toBeCloseTo(20)
  })

  it('defaults beatEnergy to 0', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 50)
    expect(p.beatEnergy).toBe(0)
  })

  it('accepts explicit beatEnergy override', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 50, 0.8)
    expect(p.beatEnergy).toBeCloseTo(0.8)
  })

  it('defaults spectral to null', () => {
    const p = specToSceneParams(SIMPLE_SPEC, 50)
    expect(p.spectral).toBeNull()
  })

  it('passes through spectral override', () => {
    const fft = new Float32Array(512)
    fft[0] = 0.9
    const p = specToSceneParams(SIMPLE_SPEC, 50, 0, fft)
    expect(p.spectral).toBe(fft)
    expect(p.spectral![0]).toBeCloseTo(0.9)
  })

  it('returns safe defaults for empty keyframe array', () => {
    const emptySpec: RenderSpec = { durationSecs: 60, keyframes: [] }
    const p = specToSceneParams(emptySpec, 30)
    expect(p.camera.distance).toBeGreaterThan(0)
    expect(p.color.primary).toMatch(/^#/)
  })

  it('handles single-keyframe spec without errors', () => {
    const singleSpec: RenderSpec = {
      durationSecs: 60,
      keyframes: [
        {
          t: 0,
          camera: { distance: 7, azimuth: 0.5, elevation: 0.1 },
          color: { primary: '#7c3aed', secondary: '#06b6d4', brightness: 0.8 },
        },
      ],
    }
    const p = specToSceneParams(singleSpec, 30)
    expect(p.camera.distance).toBeCloseTo(7)
    expect(p.camera.azimuth).toBeCloseTo(0.5)
  })

  it('interpolates color primary channel at midpoint', () => {
    // primary goes from #000000 to #ff0000 — midpoint R should be ~0.5 → ~#800000
    const p = specToSceneParams(SIMPLE_SPEC, 50)
    const [r, g, b] = hexToRgb(p.color.primary)
    expect(r).toBeCloseTo(0.5, 1)
    expect(g).toBeCloseTo(0)
    expect(b).toBeCloseTo(0)
  })

  it('multi-keyframe: picks correct segment', () => {
    const multiSpec: RenderSpec = {
      durationSecs: 100,
      keyframes: [
        { t: 0,    camera: { distance: 1, azimuth: 0, elevation: 0 }, color: { primary: '#ff0000', secondary: '#000000', brightness: 0 } },
        { t: 0.5,  camera: { distance: 5, azimuth: 0, elevation: 0 }, color: { primary: '#00ff00', secondary: '#000000', brightness: 0.5 } },
        { t: 1,    camera: { distance: 9, azimuth: 0, elevation: 0 }, color: { primary: '#0000ff', secondary: '#000000', brightness: 1 } },
      ],
    }
    // At t=0.25 (midpoint of first segment): distance should be 3
    const p25 = specToSceneParams(multiSpec, 25)
    expect(p25.camera.distance).toBeCloseTo(3)

    // At t=0.75 (midpoint of second segment): distance should be 7
    const p75 = specToSceneParams(multiSpec, 75)
    expect(p75.camera.distance).toBeCloseTo(7)
  })
})
