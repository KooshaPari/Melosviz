import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react'
import App from '../App'
import { LocaleProvider } from '../i18n/LocaleProvider'
import { ThemeProvider } from '../theme/ThemeProvider'
import { setLocale } from '../i18n'

vi.mock('../r3fRenderer', () => ({
  SceneView: () => <div data-testid="scene-view" />,
}))

vi.mock('../components/SplashScreen', () => ({
  SplashScreen: ({ onDone }: { onDone: () => void }) => {
    queueMicrotask(() => onDone())
    return null
  },
}))

function renderApp() {
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <App />
      </LocaleProvider>
    </ThemeProvider>,
  )
}

describe('App skip link and main landmark', () => {
  beforeEach(() => {
    localStorage.clear()
    setLocale('en')
  })

  it('renders skip link targeting #main', async () => {
    renderApp()
    await act(async () => {})
    const skip = screen.getByRole('link', { name: /skip to main content/i })
    expect(skip).toHaveAttribute('href', '#main')
    expect(skip).toHaveClass('skip-link')
  })

  it('renders main landmark with id main and tabIndex -1', async () => {
    renderApp()
    await waitFor(() => {
      expect(document.getElementById('main')).toBeTruthy()
    })
    const main = document.getElementById('main')
    expect(main?.tagName).toBe('MAIN')
    expect(main).toHaveAttribute('tabindex', '-1')
  })

  it('localizes skip link in Spanish', async () => {
    setLocale('es')
    renderApp()
    await act(async () => {})
    expect(
      screen.getByRole('link', { name: /saltar al contenido principal/i }),
    ).toBeInTheDocument()
  })

  it('fullscreen toggle exposes aria-pressed and Escape exits', async () => {
    renderApp()
    await waitFor(() => {
      expect(document.getElementById('main')).toBeTruthy()
    })
    const fsBtn = screen.getByRole('button', { name: /enter fullscreen scene view/i })
    expect(fsBtn).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(fsBtn)
    expect(fsBtn).toHaveAttribute('aria-pressed', 'true')
    expect(fsBtn).toHaveAccessibleName(/exit fullscreen scene view/i)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(
      screen.getByRole('button', { name: /enter fullscreen scene view/i }),
    ).toHaveAttribute('aria-pressed', 'false')
  })

  it('playback transport exposes i18n aria-labels and time readout', async () => {
    renderApp()
    await waitFor(() => {
      expect(document.getElementById('main')).toBeTruthy()
    })
    expect(screen.getByRole('button', { name: /start playback/i })).toBeInTheDocument()
    expect(screen.getByRole('slider', { name: /seek playback position/i })).toBeInTheDocument()
    expect(screen.getByText('0:00 / 4:00')).toBeInTheDocument()
  })

  it('localizes scene jump panel in Spanish', async () => {
    setLocale('es')
    renderApp()
    await waitFor(() => {
      expect(document.getElementById('main')).toBeTruthy()
    })
    expect(screen.getByText('Escena')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /saltar a escena establishing/i }),
    ).toBeInTheDocument()
  })
})
