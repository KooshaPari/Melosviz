// Keyboard shortcuts for melosviz — space=play, esc=stop.
// Thin wrapper around browser keyboard events with automatic cleanup.

export interface ShortcutsMap {
  /** Space — toggles play / pause. */
  play: () => void
  /** Escape — stops playback. */
  stop: () => void
}

/**
 * Attach global keyboard shortcuts for melosviz.
 * Returns a cleanup function that removes the listener.
 *
 * @example
 * ```ts
 * const cleanup = attachShortcuts({
 *   play: () => setPlaying((p) => !p),
 *   stop: () => setPlaying(false),
 * });
 * // later…
 * cleanup();
 * ```
 */
export function attachShortcuts(map: ShortcutsMap): () => void {
  const handler = (e: KeyboardEvent) => {
    // Ignore when user is typing in an input.
    const target = e.target as HTMLElement
    if (
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable
    ) {
      return
    }

    switch (e.code) {
      case 'Space':
        e.preventDefault()
        map.play()
        break
      case 'Escape':
        e.preventDefault()
        map.stop()
        break
    }
  }

  window.addEventListener('keydown', handler)
  return () => window.removeEventListener('keydown', handler)
}

/**
 * React hook that attaches shortcuts and cleans up on unmount.
 * Safe to call inside a component body.
 */
export function useShortcuts(map: ShortcutsMap): () => void {
  if (typeof window !== 'undefined') {
    return attachShortcuts(map)
  }
  return () => {}
}
