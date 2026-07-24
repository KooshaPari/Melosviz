import { describe, it, expect, beforeEach } from 'vitest'
import {
  DEFAULT_PLAYBACK_VOLUME,
  PLAYBACK_VOLUME_STORAGE_KEY,
  loadPlaybackVolume,
  savePlaybackVolume,
} from '../playbackVolume'

describe('playbackVolume', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns defaults when storage is empty', () => {
    expect(loadPlaybackVolume()).toEqual({
      volume: DEFAULT_PLAYBACK_VOLUME,
      muted: false,
    })
  })

  it('persists volume and muted to localStorage', () => {
    const saved = savePlaybackVolume({ volume: 0.42, muted: true })
    expect(saved).toEqual({ volume: 0.42, muted: true })
    expect(JSON.parse(localStorage.getItem(PLAYBACK_VOLUME_STORAGE_KEY)!)).toEqual({
      volume: 0.42,
      muted: true,
    })
    expect(loadPlaybackVolume()).toEqual({ volume: 0.42, muted: true })
  })

  it('clamps out-of-range volume', () => {
    expect(savePlaybackVolume({ volume: 2, muted: false }).volume).toBe(1)
    expect(savePlaybackVolume({ volume: -0.5, muted: false }).volume).toBe(0)
  })
})
