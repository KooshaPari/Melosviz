export const PLAYBACK_VOLUME_STORAGE_KEY = "mv_playback_volume";

export const DEFAULT_PLAYBACK_VOLUME = 0.8;

export interface PlaybackVolumeState {
  volume: number;
  muted: boolean;
}

function clampVolume(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_PLAYBACK_VOLUME;
  return Math.max(0, Math.min(1, value));
}

function parseStored(raw: string | null): PlaybackVolumeState {
  if (!raw) return { volume: DEFAULT_PLAYBACK_VOLUME, muted: false };
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") {
      return { volume: DEFAULT_PLAYBACK_VOLUME, muted: false };
    }
    const volume = clampVolume(Number((parsed as PlaybackVolumeState).volume));
    const muted = Boolean((parsed as PlaybackVolumeState).muted);
    return { volume, muted };
  } catch {
    return { volume: DEFAULT_PLAYBACK_VOLUME, muted: false };
  }
}

export function loadPlaybackVolume(): PlaybackVolumeState {
  if (typeof window === "undefined") {
    return { volume: DEFAULT_PLAYBACK_VOLUME, muted: false };
  }
  return parseStored(window.localStorage.getItem(PLAYBACK_VOLUME_STORAGE_KEY));
}

export function savePlaybackVolume(
  state: PlaybackVolumeState,
): PlaybackVolumeState {
  const next = {
    volume: clampVolume(state.volume),
    muted: Boolean(state.muted),
  };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(
      PLAYBACK_VOLUME_STORAGE_KEY,
      JSON.stringify(next),
    );
  }
  return next;
}
