import { describe, it, expect, vi } from 'vitest'
import { attachShortcuts } from '../shortcuts'

describe('attachShortcuts', () => {
  it('calls play when Space is pressed', () => {
    const play = vi.fn()
    const stop = vi.fn()
    const cleanup = attachShortcuts({ play, stop })

    const event = new KeyboardEvent('keydown', { code: 'Space' })
    window.dispatchEvent(event)

    expect(play).toHaveBeenCalled()
    cleanup()
  })

  it('calls stop when Escape is pressed', () => {
    const play = vi.fn()
    const stop = vi.fn()
    const cleanup = attachShortcuts({ play, stop })

    const event = new KeyboardEvent('keydown', { code: 'Escape' })
    window.dispatchEvent(event)

    expect(stop).toHaveBeenCalled()
    cleanup()
  })

  it('does not trigger when typing in input', () => {
    const play = vi.fn()
    const stop = vi.fn()
    const cleanup = attachShortcuts({ play, stop })

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    const event = new KeyboardEvent('keydown', { code: 'Space', bubbles: true })
    input.dispatchEvent(event)

    expect(play).not.toHaveBeenCalled()

    document.body.removeChild(input)
    cleanup()
  })

  it('cleans up listener', () => {
    const play = vi.fn()
    const stop = vi.fn()
    const cleanup = attachShortcuts({ play, stop })
    cleanup()

    const event = new KeyboardEvent('keydown', { code: 'Space' })
    window.dispatchEvent(event)

    expect(play).not.toHaveBeenCalled()
  })
})
