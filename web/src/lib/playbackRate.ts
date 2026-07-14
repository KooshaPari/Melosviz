export const PLAYBACK_RATE_STORAGE_KEY = 'mv_playback_rate'

export const DEFAULT_PLAYBACK_RATE = 1

export const MIN_PLAYBACK_RATE = 0.5

export const MAX_PLAYBACK_RATE = 1.5

export const PLAYBACK_RATE_PRESETS = [0.5, 1, 1.5] as const

function clampRate(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_PLAYBACK_RATE
  return Math.max(MIN_PLAYBACK_RATE, Math.min(MAX_PLAYBACK_RATE, value))
}

export function loadPlaybackRate(): number {
  if (typeof window === 'undefined') return DEFAULT_PLAYBACK_RATE
  const raw = window.localStorage.getItem(PLAYBACK_RATE_STORAGE_KEY)
  if (!raw) return DEFAULT_PLAYBACK_RATE
  const parsed = Number(raw)
  return clampRate(parsed)
}

export function savePlaybackRate(rate: number): number {
  const next = clampRate(rate)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(PLAYBACK_RATE_STORAGE_KEY, String(next))
  }
  return next
}
