import { Component, type ErrorInfo, type ReactNode } from 'react'
import { recordDecision } from './InspectabilityPanel'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ErrorBoundaryProps {
  children: ReactNode
  /**
   * Optional custom fallback UI.
   * When omitted, the built-in friendly error container is rendered.
   */
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorId: string
}

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Generate a short, human-readable error ID for traceability. */
function generateErrorId(): string {
  const ts = Date.now().toString(36)
  const rand = Math.random().toString(36).slice(2, 8)
  return `ERR-${ts}-${rand}`
}

/** Copy a string to the system clipboard, swallowing permission errors silently. */
async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard access may be denied; fail silently.
  }
}

// ── Component ──────────────────────────────────────────────────────────────────

/**
 * ErrorBoundary catches React render errors, records a `journey_abandoned`
 * decision via InspectabilityPanel, and displays a friendly fallback UI.
 *
 * The built-in fallback includes:
 * - A warning icon and human-readable error message
 * - An error ID label + "Copy ID" action for debugging
 * - A "Refresh" button that resets error state
 *
 * @example
 * ```tsx
 * <ErrorBoundary>
 *   <MyApp />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, errorId: '' }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error, errorId: generateErrorId() }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    recordDecision({
      type: 'journey_abandoned',
      error: error.message,
      errorName: error.name,
      componentStack: errorInfo.componentStack ?? null,
      errorId: this.state.errorId || generateErrorId(),
      timestamp: new Date().toISOString(),
    })
  }

  // ── Handlers ─────────────────────────────────────────────────────────────

  private handleRefresh = (): void => {
    this.setState({ hasError: false, error: null, errorId: '' })
  }

  private handleCopyErrorId = (): void => {
    if (this.state.errorId) {
      void copyToClipboard(this.state.errorId)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children
    }

    // Allow consumers to supply their own fallback
    if (this.props.fallback) {
      return this.props.fallback
    }

    return (
      <div className="flex items-center justify-center w-full h-full min-h-[240px]">
        <div className="mx-auto max-w-md rounded-xl border border-red-500/20 bg-[var(--mv-surface,#111118)] p-6 shadow-2xl">
          {/* ── Icon ─────────────────────────────────────────────────────── */}
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10">
            <span
              className="text-xl select-none"
              role="img"
              aria-label="error"
            >
              ⚠
            </span>
          </div>

          {/* ── Heading ─────────────────────────────────────────────────── */}
          <h2 className="mb-2 text-center text-sm font-semibold text-white/90">
            Something went wrong
          </h2>

          {/* ── Error message ────────────────────────────────────────────── */}
          <p className="mb-4 text-center text-xs leading-relaxed text-white/50">
            {this.state.error?.message ||
              'An unexpected render error occurred.'}
          </p>

          {/* ── Error ID + Copy ─────────────────────────────────────────── */}
          <div className="mb-5 flex items-center justify-center gap-2">
            <code className="rounded bg-white/5 px-2 py-1 text-[11px] font-mono text-white/40 select-all">
              {this.state.errorId}
            </code>
            <button
              onClick={this.handleCopyErrorId}
              className="rounded bg-white/5 px-2 py-1 text-[11px] text-white/50 transition-colors hover:bg-white/10 hover:text-white/80"
              title="Copy error ID to clipboard"
            >
              Copy ID
            </button>
          </div>

          {/* ── Refresh ─────────────────────────────────────────────────── */}
          <button
            onClick={this.handleRefresh}
            className="w-full rounded-lg bg-fuchsia-500/25 py-2 text-sm font-medium text-fuchsia-200 transition-colors hover:bg-fuchsia-500/35 border border-fuchsia-500/40"
          >
            Refresh
          </button>
        </div>
      </div>
    )
  }
}
