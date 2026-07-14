import { useEffect } from 'react'

export type ShortcutGroup = 'playback' | 'view' | 'help'

export interface ShortcutDef {
  key: string
  labelKey: string
  description: string
  group: ShortcutGroup
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = ['playback', 'view', 'help']

export const SHORTCUT_DEFS: ShortcutDef[] = [
  { key: 'Space', labelKey: 'keyboard.label.space', description: 'keyboard.shortcut.play_pause', group: 'playback' },
  { key: '←', labelKey: 'keyboard.label.arrow_left', description: 'keyboard.shortcut.seek_back', group: 'playback' },
  { key: '→', labelKey: 'keyboard.label.arrow_right', description: 'keyboard.shortcut.seek_forward', group: 'playback' },
  { key: 'm', labelKey: 'keyboard.label.m', description: 'keyboard.shortcut.toggle_mute', group: 'playback' },
  { key: 'l', labelKey: 'keyboard.label.l', description: 'keyboard.shortcut.toggle_loop', group: 'playback' },
  { key: 'r', labelKey: 'keyboard.label.r', description: 'keyboard.shortcut.restart', group: 'playback' },
  { key: 'p', labelKey: 'keyboard.label.p', description: 'keyboard.shortcut.open_preset', group: 'view' },
  { key: 'f', labelKey: 'keyboard.label.f', description: 'keyboard.shortcut.toggle_fullscreen', group: 'view' },
  { key: '?', labelKey: 'keyboard.label.question', description: 'keyboard.shortcut.open_help', group: 'help' },
  { key: 'Escape', labelKey: 'keyboard.label.escape', description: 'keyboard.shortcut.close_modal', group: 'help' },
]

export interface KeyboardShortcutActions {
  togglePlay: () => void
  seekBackward: () => void
  seekForward: () => void
  toggleHelp: () => void
  closeModal: () => void
  openPresetEditor: () => void
  toggleFullscreen: () => void
  toggleMute: () => void
  toggleLoop: () => void
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
        case 'm':
        case 'M':
          actions.toggleMute()
          break
        case 'l':
        case 'L':
          actions.toggleLoop()
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
