import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import {
  HIGH_CONTRAST_STORAGE_KEY,
  ThemeProvider,
  applyDocumentTheme,
  useTheme,
} from '../ThemeProvider'

function ThemeProbe() {
  const { theme, highContrast, toggle, toggleHighContrast } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="hc">{highContrast ? 'on' : 'off'}</span>
      <button type="button" onClick={toggle}>
        toggle theme
      </button>
      <button type="button" onClick={toggleHighContrast}>
        toggle hc
      </button>
    </div>
  )
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.removeAttribute('data-high-contrast')
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.removeAttribute('data-high-contrast')
  })

  it('persists theme and high-contrast preference to localStorage', () => {
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'toggle theme' }))
    fireEvent.click(screen.getByRole('button', { name: 'toggle hc' }))

    expect(localStorage.getItem('melosviz-theme')).toBe('light')
    expect(localStorage.getItem(HIGH_CONTRAST_STORAGE_KEY)).toBe('true')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.dataset.highContrast).toBe('true')
  })

  it('restores high-contrast from localStorage on mount', () => {
    localStorage.setItem(HIGH_CONTRAST_STORAGE_KEY, 'true')

    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('hc').textContent).toBe('on')
    expect(document.documentElement.dataset.highContrast).toBe('true')
  })

  it('applyDocumentTheme clears high-contrast dataset when disabled', () => {
    applyDocumentTheme('dark', true)
    expect(document.documentElement.dataset.highContrast).toBe('true')

    applyDocumentTheme('dark', false)
    expect(document.documentElement.dataset.highContrast).toBeUndefined()
  })
})
