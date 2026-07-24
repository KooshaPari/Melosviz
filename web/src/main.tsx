import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/brand.css'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { LocaleProvider } from './i18n/LocaleProvider'
import { ThemeProvider } from './theme/ThemeProvider'

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('[melosviz] mount point #root not found in index.html')
}

createRoot(rootEl).render(
  <StrictMode>
    <ThemeProvider>
      <LocaleProvider>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </LocaleProvider>
    </ThemeProvider>
  </StrictMode>,
)
