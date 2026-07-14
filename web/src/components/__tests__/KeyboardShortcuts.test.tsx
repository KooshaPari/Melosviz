/**
 * Tests for useKeyboardShortcuts hook and KeyboardHelp dialog.
 */
import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useKeyboardShortcuts, type KeyboardShortcutActions } from '../../hooks/useKeyboardShortcuts'
import { KeyboardHelp } from '../KeyboardHelp'

// ---- helpers ----------------------------------------------------------------

function makeActions(overrides: Partial<KeyboardShortcutActions> = {}): KeyboardShortcutActions {
  return {
    togglePlay: vi.fn(),
    seekBackward: vi.fn(),
    seekForward: vi.fn(),
    toggleHelp: vi.fn(),
    closeModal: vi.fn(),
    openPresetEditor: vi.fn(),
    toggleFullscreen: vi.fn(),
    toggleMute: vi.fn(),
    toggleLoop: vi.fn(),
    restartPlayback: vi.fn(),
    ...overrides,
  }
}

function fireKey(key: string, targetEl?: Element) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true })
  if (targetEl) {
    Object.defineProperty(event, 'target', { value: targetEl })
    targetEl.dispatchEvent(event)
  } else {
    window.dispatchEvent(event)
  }
}

// ---- useKeyboardShortcuts ---------------------------------------------------

describe('useKeyboardShortcuts', () => {
  it('calls togglePlay on Space', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey(' ')
    expect(actions.togglePlay).toHaveBeenCalledTimes(1)
  })

  it('calls seekBackward on ArrowLeft', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('ArrowLeft')
    expect(actions.seekBackward).toHaveBeenCalledTimes(1)
  })

  it('calls seekForward on ArrowRight', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('ArrowRight')
    expect(actions.seekForward).toHaveBeenCalledTimes(1)
  })

  it('calls toggleHelp on ? key', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('?')
    expect(actions.toggleHelp).toHaveBeenCalledTimes(1)
  })

  it('calls closeModal on Escape', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('Escape')
    expect(actions.closeModal).toHaveBeenCalledTimes(1)
  })

  it('calls openPresetEditor on p', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('p')
    expect(actions.openPresetEditor).toHaveBeenCalledTimes(1)
  })

  it('calls toggleFullscreen on f', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('f')
    expect(actions.toggleFullscreen).toHaveBeenCalledTimes(1)
  })

  it('calls toggleMute on m', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('m')
    expect(actions.toggleMute).toHaveBeenCalledTimes(1)
  })

  it('calls toggleLoop on l', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('l')
    expect(actions.toggleLoop).toHaveBeenCalledTimes(1)
  })

  it('calls restartPlayback on r', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))
    fireKey('r')
    expect(actions.restartPlayback).toHaveBeenCalledTimes(1)
  })

  it('does NOT fire Space when an input element is focused', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    const event = new KeyboardEvent('keydown', { key: ' ', bubbles: true })
    // Simulate target being the input
    Object.defineProperty(event, 'target', { value: input })
    window.dispatchEvent(event)

    expect(actions.togglePlay).not.toHaveBeenCalled()
    document.body.removeChild(input)
  })

  it('DOES fire Escape even when an input element is focused', () => {
    const actions = makeActions()
    renderHook(() => useKeyboardShortcuts(actions))

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
    Object.defineProperty(event, 'target', { value: input })
    window.dispatchEvent(event)

    expect(actions.closeModal).toHaveBeenCalledTimes(1)
    document.body.removeChild(input)
  })

  it('removes listener on unmount', () => {
    const actions = makeActions()
    const { unmount } = renderHook(() => useKeyboardShortcuts(actions))
    unmount()
    fireKey(' ')
    expect(actions.togglePlay).not.toHaveBeenCalled()
  })
})

// ---- KeyboardHelp dialog ----------------------------------------------------

describe('KeyboardHelp', () => {
  it('renders shortcut rows when open=true', () => {
    render(<KeyboardHelp open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('Keyboard Shortcuts')).toBeTruthy()
    expect(screen.getByText('Playback')).toBeTruthy()
    expect(screen.getByText('View')).toBeTruthy()
    expect(screen.getByText('Help')).toBeTruthy()
    expect(screen.getByText('Toggle play / pause')).toBeTruthy()
    expect(screen.getByText('Toggle fullscreen scene view')).toBeTruthy()
    expect(screen.getByText('Toggle track audio mute')).toBeTruthy()
    expect(screen.getByText('Toggle scene loop at end')).toBeTruthy()
  })

  it('does not render content when open=false', () => {
    render(<KeyboardHelp open={false} onOpenChange={vi.fn()} />)
    expect(screen.queryByText('Keyboard Shortcuts')).toBeNull()
  })

  it('calls onOpenChange(false) when close button is clicked', async () => {
    const onOpenChange = vi.fn()
    render(<KeyboardHelp open={true} onOpenChange={onOpenChange} />)
    const closeBtn = document.getElementById('keyboard-help-close')
    expect(closeBtn).toBeTruthy()
    fireEvent.click(closeBtn!)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('moves initial focus to the close control when opened (FOCUS.md)', async () => {
    render(<KeyboardHelp open={true} onOpenChange={vi.fn()} />)
    const closeBtn = document.getElementById('keyboard-help-close')
    await waitFor(() => {
      expect(document.activeElement).toBe(closeBtn)
    })
  })
})
