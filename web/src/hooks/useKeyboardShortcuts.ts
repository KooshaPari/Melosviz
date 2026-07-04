import { useEffect } from 'react'

export interface ShortcutDef {
  key: string
  label: string
  description: string
}

export const SHORTCUT_DEFS: ShortcutDef[] = [
  { key: 'Space', label: 'Space', description: 'Toggle play / pause' },
  { key: '←', label: '← Arrow', description: 'Seek back 5 s' },
  { key: '→', label: '→ Arrow', description: 'Seek forward 5 s' },
  { key: '?', label: '?', description: 'Open keyboard shortcut help' },
  { key: 'Escape', label: 'Esc', description: 'Close modal / reset focus' },
  { key: 'p', label: 'P', description: 'Open preset editor' },
  { key: 'f', label: 'F', description: 'Toggle fullscreen scene view' },
  { key: 'r', label: 'R', description: 'Restart playback from beginning' },
]

export interface KeyboardShortcutActions {
  togglePlay: () => void
  seekBackward: () => void
  seekForward: () => void
  toggleHelp: () => void
  closeModal: () => void
  openPresetEditor: () => void
  toggleFullscreen: () => void
  restartPlayback: () => void
}

/** Returns true when the event originates from a text input / textarea / contenteditable */
function isInputFocused(e: KeyboardEvent): boolean {
  const target = e.target
  if (!target || !(target instanceof Element)) return false
  const tag = (target as Element).tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if ((target as HTMLElement).isContentEditable) return true
  return false
}

export function useKeyboardShortcuts(actions: KeyboardShortcutActions): void {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Never fire shortcuts while the user is typing in an input, EXCEPT Escape
      if (isInputFocused(e) && e.key !== 'Escape') return

      switch (e.key) {
        case ' ':
          e.preventDefault()
          actions.togglePlay()
          break
        case 'ArrowLeft':
          e.preventDefault()
          actions.seekBackward()
          break
        case 'ArrowRight':
          e.preventDefault()
          actions.seekForward()
          break
        case '?':
          actions.toggleHelp()
          break
        case 'Escape':
          actions.closeModal()
          break
        case 'p':
        case 'P':
          actions.openPresetEditor()
          break
        case 'f':
        case 'F':
          actions.toggleFullscreen()
          break
        case 'r':
        case 'R':
          actions.restartPlayback()
          break
        default:
          break
      }
    }

    window.addEventListener('keydown', handler)
    return () => {
      window.removeEventListener('keydown', handler)
    }
  }, [actions])
}
