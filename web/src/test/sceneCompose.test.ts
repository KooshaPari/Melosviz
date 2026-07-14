import { describe, it, expect } from 'vitest'
import { resolveSceneBlend } from '../utils/sceneBlend'
import type { RenderSpec } from '../renderSpec'
import { applyPresetToSpec, mapAnalysisToRenderSpec } from '../mapAnalysisSpec'

const MULTI_SCENE_SPEC: RenderSpec = {
  durationSecs: 100,
  transitionFraction: 0.12,
  keyframes: [
    {
      t: 0,
      scene: 'Establishing',
      scene_template: 'wire_orb',
      transition_secs: 3,
      camera: { distance: 9, azimuth: 0, elevation: 0.2 },
      color: { primary: '#111111', secondary: '#222222', brightness: 0.5 },
    },
    {
      t: 0.5,
      scene: 'Anthem',
      scene_template: 'crystal_burst',
      transition_secs: 3,
      camera: { distance: 4, azimuth: 0.3, elevation: 0.3 },
      color: { primary: '#ff0000', secondary: '#00ff00', brightness: 0.9 },
    },
    {
      t: 1,
      scene: 'Anthem',
      scene_template: 'crystal_burst',
      camera: { distance: 4, azimuth: 0.3, elevation: 0.3 },
      color: { primary: '#ff0000', secondary: '#00ff00', brightness: 0.9 },
    },
  ],
  sceneSegments: [
    { index: 0, label: 'intro', start: 0, end: 50, scene_template: 'wire_orb' },
    { index: 1, label: 'chorus', start: 50, end: 100, scene_template: 'crystal_burst' },
  ],
}

describe('resolveSceneBlend', () => {
  it('returns single template when far from boundary', () => {
    const state = resolveSceneBlend(MULTI_SCENE_SPEC, 0.1)
    expect(state.fromTemplate).toBe('wire_orb')
    expect(state.blend).toBeCloseTo(0)
  })

  it('crossfades near segment boundary', () => {
    const state = resolveSceneBlend(MULTI_SCENE_SPEC, 0.48)
    expect(state.fromTemplate).toBe('wire_orb')
    expect(state.toTemplate).toBe('crystal_burst')
    expect(state.blend).toBeGreaterThan(0)
    expect(state.blend).toBeLessThanOrEqual(1)
  })
})

describe('mapAnalysisToRenderSpec', () => {
  it('maps v2 backend fields', () => {
    const spec = mapAnalysisToRenderSpec({
      metadata: { duration: 180 },
      duration_sec: 180,
      bpm: 128,
      keyframes: [{ t: 0, camera: { distance: 5, azimuth: 0, elevation: 0 }, color: { primary: '#fff', secondary: '#000', brightness: 0.5 } }],
      scene_segments: [{ index: 0, label: 'intro', start: 0, end: 180, scene_template: 'wire_orb' }],
    })
    expect(spec.durationSecs).toBe(180)
    expect(spec.sceneSegments?.length).toBe(1)
    expect(spec.keyframes.length).toBe(1)
  })
})

describe('applyPresetToSpec', () => {
  it('remaps segment templates for energetic preset', () => {
    const remapped = applyPresetToSpec(MULTI_SCENE_SPEC, 'energetic')
    const templates = remapped.sceneSegments?.map((s) => s.scene_template) ?? []
    expect(templates.length).toBeGreaterThan(0)
    expect(new Set(templates).size).toBeGreaterThan(1)
  })
})
