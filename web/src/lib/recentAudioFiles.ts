export const RECENT_AUDIO_STORAGE_KEY = 'mv_recent_audio_files'
export const RECENT_AUDIO_MAX = 8

export type RecentAudioKind = 'path' | 'file'

/** Persisted shape — blob URLs are never stored (session-only). */
export interface RecentAudioEntry {
  name: string
  size: number
  lastUsed: number
  kind: RecentAudioKind
  /** Filesystem or server path; only present for kind === 'path'. */
  path?: string
}

function entryKey(entry: Pick<RecentAudioEntry, 'name' | 'size' | 'kind' | 'path'>): string {
  return `${entry.kind}:${entry.path ?? ''}:${entry.name}:${entry.size}`
}

function parseStored(raw: string | null): RecentAudioEntry[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (item): item is RecentAudioEntry =>
          !!item &&
          typeof item === 'object' &&
          typeof (item as RecentAudioEntry).name === 'string' &&
          typeof (item as RecentAudioEntry).size === 'number' &&
          typeof (item as RecentAudioEntry).lastUsed === 'number' &&
          ((item as RecentAudioEntry).kind === 'path' ||
            (item as RecentAudioEntry).kind === 'file'),
      )
      .map((item) => ({
        name: item.name,
        size: item.size,
        lastUsed: item.lastUsed,
        kind: item.kind,
        ...(item.kind === 'path' && typeof item.path === 'string' ? { path: item.path } : {}),
      }))
  } catch {
    return []
  }
}

export function loadRecentAudioFiles(): RecentAudioEntry[] {
  if (typeof window === 'undefined') return []
  return parseStored(window.localStorage.getItem(RECENT_AUDIO_STORAGE_KEY)).sort(
    (a, b) => b.lastUsed - a.lastUsed,
  )
}

function persist(entries: RecentAudioEntry[]): RecentAudioEntry[] {
  const sorted = [...entries].sort((a, b) => b.lastUsed - a.lastUsed).slice(0, RECENT_AUDIO_MAX)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(RECENT_AUDIO_STORAGE_KEY, JSON.stringify(sorted))
  }
  return sorted
}

/** Insert or bump a recent entry; returns the updated list (newest first). */
export function pushRecentAudioFile(
  entry: Omit<RecentAudioEntry, 'lastUsed'> & { lastUsed?: number },
): RecentAudioEntry[] {
  const now = entry.lastUsed ?? Date.now()
  const next: RecentAudioEntry = {
    name: entry.name,
    size: entry.size,
    lastUsed: now,
    kind: entry.kind,
    ...(entry.kind === 'path' && entry.path ? { path: entry.path } : {}),
  }
  const key = entryKey(next)
  const existing = loadRecentAudioFiles().filter((e) => entryKey(e) !== key)
  return persist([next, ...existing])
}

/** Remove all persisted recent entries; returns an empty list. */
export function clearRecentAudioFiles(): RecentAudioEntry[] {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(RECENT_AUDIO_STORAGE_KEY)
  }
  return []
}

export function formatRecentSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
