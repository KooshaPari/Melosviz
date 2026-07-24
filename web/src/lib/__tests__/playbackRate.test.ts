import { describe, it, expect, beforeEach } from 'vitest'
import {
  DEFAULT_PLAYBACK_RATE,
  MAX_PLAYBACK_RATE,
  MIN_PLAYBACK_RATE,
  PLAYBACK_RATE_STORAGE_KEY,
  loadPlaybackRate,
  savePlaybackRate,
} from '../playbackRate'

describe('playbackRate', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns default when storage is empty', () => {
    expect(loadPlaybackRate()).toBe(DEFAULT_PLAYBACK_RATE)
  })

  it('persists rate to localStorage', () => {
    const saved = savePlaybackRate(1.25)
    expect(saved).toBe(1.25)
    expect(localStorage.getItem(PLAYBACK_RATE_STORAGE_KEY)).toBe('1.25')
    expect(loadPlaybackRate()).toBe(1.25)
  })

  it('clamps out-of-range rate', () => {
    expect(savePlaybackRate(2).toFixed(1)).toBe(String(MAX_PLAYBACK_RATE))
    expect(savePlaybackRate(0.1).toFixed(1)).toBe(String(MIN_PLAYBACK_RATE))
  })
})
