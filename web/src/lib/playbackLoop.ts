export const PLAYBACK_LOOP_STORAGE_KEY = "mv_playback_loop";

export function loadPlaybackLoop(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.localStorage.getItem(PLAYBACK_LOOP_STORAGE_KEY);
  if (raw === null) return false;
  return raw === "1" || raw === "true";
}

export function savePlaybackLoop(enabled: boolean): boolean {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(PLAYBACK_LOOP_STORAGE_KEY, enabled ? "1" : "0");
  }
  return enabled;
}
