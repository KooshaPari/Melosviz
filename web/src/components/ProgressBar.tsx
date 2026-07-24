// ProgressBar — Staged progress bar with per-stage labels, gradient pulse
// animation on fill, and an error-drain-to-red state with 'we hit a snag'.
//
// Stages (in order): decoding audio… → routing frames… → muxing… → complete

export interface ProgressBarProps {
  /** Progress in [0, 1]. Drives fill width. */
  progress: number
  /** Current stage key — one of 'decoding-audio' | 'routing-frames' | 'muxing' | 'complete'. */
  stage: string
  /** Optional error message. When set, fill drains to red and a snag label replaces stage text. */
  error?: string
}

/** StageDescriptor maps a key to a human label and its normalised position on the bar. */
interface StageDescriptor {
  label: string
  position: number
}

const STAGES: Record<string, StageDescriptor> = {
  'decoding-audio': { label: 'decoding audio…', position: 0.15 },
  'routing-frames': { label: 'routing frames…', position: 0.45 },
  muxing: { label: 'muxing…', position: 0.75 },
  complete: { label: 'complete', position: 1 },
}

const STAGE_KEYS = ['decoding-audio', 'routing-frames', 'muxing', 'complete'] as const

/** Minimum fill fraction when an error occurs — the bar never fully empties. */
const ERROR_FLOOR = 0.08

/**
 * ProgressBar renders a progress track with:
 *  - A gradient bar that pulses via a shimmer keyframe.
 *  - Per-stage tick marks and labels at fixed positions.
 *  - An error state that drains the fill toward ERROR_FLOOR with a red gradient
 *    and replaces the stage label with 'we hit a snag'.
 */
export function ProgressBar({ progress, stage, error }: ProgressBarProps) {
  const currentIndex = STAGE_KEYS.indexOf(stage as (typeof STAGE_KEYS)[number])
  const isError = Boolean(error)

  // Clamp & apply error floor
  const fillWidth = isError
    ? Math.max(ERROR_FLOOR, Math.min(1, progress)) * 100
    : Math.min(1, Math.max(0, progress)) * 100

  return (
    <div className="w-full" style={{ fontFamily: 'ui-monospace, monospace' }}>
      <style>{`
        @keyframes pbar-shimmer {
          0%   { background-position: -200% center; }
          100% { background-position: 200% center; }
        }
        @keyframes pbar-drain {
          0%   { background-position: 0% center; }
          100% { opacity: 1; }
        }
        .pbar-fill {
          background-size: 200% auto;
          animation: pbar-shimmer 1.8s ease-in-out infinite;
        }
        .pbar-fill--error {
          animation: pbar-drain 0.6s ease-out forwards;
        }
      `}</style>

      {/* ---- Track ---- */}
      <div
        className="relative w-full h-2.5 rounded-full overflow-hidden"
        style={{ background: 'rgba(255,255,255,0.08)' }}
      >
        {/* Fill */}
        <div
          className={`absolute inset-y-0 left-0 rounded-full transition-[width,background] duration-500 ${
            isError ? 'pbar-fill--error' : 'pbar-fill'
          }`}
          style={{
            width: `${fillWidth}%`,
            background: isError
              ? 'linear-gradient(90deg, #ef4444 0%, #dc2626 100%)'
              : 'linear-gradient(90deg, #7c3aed 0%, #06b6d4 40%, #a78bfa 60%, #06b6d4 80%, #7c3aed 100%)',
            backgroundSize: isError ? '100% 100%' : '200% auto',
            boxShadow: isError
              ? '0 0 8px rgba(239,68,68,0.5)'
              : '0 0 8px rgba(124,58,237,0.4)',
          }}
        />

        {/* Stage tick marks */}
        {STAGE_KEYS.map((key) => {
          const s = STAGES[key]!
          const reached = currentIndex >= STAGE_KEYS.indexOf(key) && !isError
          return (
            <div
              key={key}
              className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full transition-colors duration-300"
              style={{
                left: `${s.position * 100}%`,
                marginLeft: '-3px',
                background: reached
                  ? 'rgba(255,255,255,0.9)'
                  : 'rgba(255,255,255,0.2)',
                boxShadow: reached ? '0 0 4px rgba(255,255,255,0.6)' : 'none',
              }}
            />
          )
        })}
      </div>

      {/* ---- Labels row ---- */}
      <div className="relative w-full mt-2 h-4">
        {STAGE_KEYS.map((key) => {
          const s = STAGES[key]!
          const isActive = key === stage && !isError
          const isPast = currentIndex >= STAGE_KEYS.indexOf(key) && !isError

          return (
            <span
              key={key}
              className="absolute text-[10px] leading-none whitespace-nowrap transition-all duration-300"
              style={{
                left: `${s.position * 100}%`,
                transform: 'translateX(-50%)',
                color: isActive
                  ? 'rgba(255,255,255,0.9)'
                  : isPast
                    ? 'rgba(255,255,255,0.45)'
                    : 'rgba(255,255,255,0.2)',
                fontWeight: isActive ? 600 : 400,
                letterSpacing: '0.04em',
              }}
            >
              {s.label}
            </span>
          )
        })}

        {/* Error label overlays the row when error is present */}
        {isError && (
          <span
            className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold leading-none tracking-wider"
            style={{ color: '#fca5a5', textShadow: '0 0 8px rgba(239,68,68,0.3)' }}
          >
            we hit a snag
          </span>
        )}
      </div>

      {/* ---- Optional error message ---- */}
      {isError && error && (
        <p
          className="mt-1.5 text-[10px] leading-tight text-center max-w-full truncate"
          style={{ color: 'rgba(239,68,68,0.7)' }}
        >
          {error}
        </p>
      )}

      {/* ---- Percentage ---- */}
      <p
        className="mt-1 text-[10px] font-medium text-center tabular-nums tracking-wider"
        style={{
          color: isError ? 'rgba(239,68,68,0.6)' : 'rgba(255,255,255,0.3)',
        }}
      >
        {isError ? '—' : `${Math.round(progress * 100)}%`}
      </p>
    </div>
  )
}
