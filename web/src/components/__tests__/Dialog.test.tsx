import { describe, it, expect, vi, afterEach } from 'vitest'
import { render } from '@testing-library/react'
import { DialogOverlay } from '../Dialog'
import { Dialog } from '../Dialog'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Dialog motion', () => {
  it('omits animate-in classes when prefers-reduced-motion is set', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    const { container } = render(
      <Dialog.Root open>
        <Dialog.Portal>
          <DialogOverlay data-testid="overlay" />
        </Dialog.Portal>
      </Dialog.Root>,
    )

    const overlay = container.querySelector('[data-testid="overlay"]')
    expect(overlay?.className).not.toMatch(/animate-in/)
  })
})
