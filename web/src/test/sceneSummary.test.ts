import { describe, it, expect } from 'vitest'
import { buildSceneSummary, formatTrackTime } from '../utils/sceneSummary'
import type { RenderSpec } from '../renderSpec'

const FIXTURE_SPEC: RenderSpec = {
  durationSecs: 240,
  bpm: 128,
  key: 'C major',
  beatTimes: [0.5, 1.0, 1.5],
  keyframes: [
    {
      t: 0,
      scene: 'Anthem (fixture)',
      camera: { distance: 4, azimuth: -0.3, elevation: 0.3 },
      color: { primary: '#f97316', secondary: '#a3e635', brightness: 1.0 },
    },
    {
      t: 0.5,
      scene: 'Bridge',
      camera: { distance: 6, azimuth: 0.5, elevation: 0.1 },
      color: { primary: '#7c6af7', secondary: '#22d3ee', brightness: 0.5 },
    },
  ],
}

describe('formatTrackTime', () => {
  it('formats minutes and zero-padded seconds', () => {
    expect(formatTrackTime(0)).toBe('0:00')
    expect(formatTrackTime(65)).toBe('1:05')
    expect(formatTrackTime(240)).toBe('4:00')
  })
})

describe('buildSceneSummary', () => {
  it('is deterministic for fixed spec + playbackT', () => {
    const a = buildSceneSummary({
      spec: FIXTURE_SPEC,
      playbackT: 0,
      sceneLabel: 'Anthem (fixture)',
    })
    const b = buildSceneSummary({
      spec: FIXTURE_SPEC,
      playbackT: 0,
      sceneLabel: 'Anthem (fixture)',
    })
    expect(a).toEqual(b)
    expect(a.imgLabel).toContain('Anthem (fixture)')
    expect(a.imgLabel).toContain('0% through track')
    expect(a.detailText).toContain('Tempo 128 beats per minute')
    expect(a.detailText).toContain('Key C major')
    expect(a.detailText).toContain('3 beat markers')
    expect(a.detailText).toContain('#f97316')
    expect(a.liveAnnouncement).toContain('Anthem (fixture). Playback')
    expect(a.liveKey).toBe('Anthem (fixture)|0')
  })

  it('interpolates camera and color at mid-track playbackT', () => {
    const summary = buildSceneSummary({
      spec: FIXTURE_SPEC,
      playbackT: 0.25,
      sceneLabel: 'Anthem (fixture)',
    })
    expect(summary.detailText).toContain('25%')
    expect(summary.detailText).toContain('1:00 of 4:00')
    expect(summary.detailText).toContain('Camera distance 5.0')
  })

  it('falls back when scene label is empty', () => {
    const summary = buildSceneSummary({
      spec: FIXTURE_SPEC,
      playbackT: 0,
      sceneLabel: '   ',
    })
    expect(summary.imgLabel).toContain('Scene')
    expect(summary.liveAnnouncement).toContain('Scene. Playback')
  })
})
