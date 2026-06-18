import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { startWebVitals } from './webVitals'

// Start Web Vitals monitoring in production builds.
if (import.meta.env.PROD) {
  startWebVitals()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
