// Control panel for melosviz — play / pause / preset buttons.
// Styled with Tailwind CSS to match the dark HUD aesthetic.

import { useCallback } from 'react'

export type Preset =
  | 'jazz'
  | 'classical'
  | 'edm'
  | 'ambient'
  | 'rock'

export const PRESETS: { id: Preset; label: string }[] = [
  { id: 'jazz', label: 'Jazz' },
  { id: 'classical', label: 'Classical' },
  { id: 'edm', label: 'EDM' },
  { id: 'ambient', label: 'Ambient' },
  { id: 'rock', label: 'Rock' },
]

export interface ControlPanelProps {
  isPlaying: boolean
  activePreset: Preset | null
  onPlay: () => void
  onPause: () => void
  onStop: () => void
  onPreset: (preset: Preset) => void
  disabled?: boolean
}

export function ControlPanel({
  isPlaying,
  activePreset,
  onPlay,
  onPause,
  onStop,
  onPreset,
  disabled = false,
}: ControlPanelProps) {
  const handlePlayPause = useCallback(() => {
    if (isPlaying) {
      onPause()
    } else {
      onPlay()
    }
  }, [isPlaying, onPlay, onPause])

  return (
    <div className="flex flex-col gap-4">
      {/* Playback controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={handlePlayPause}
          disabled={disabled}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-colors border backdrop-blur-sm disabled:opacity-40 disabled:cursor-not-allowed
            bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border-cyan-500/30"
        >
          {isPlaying ? 'Pause' : 'Play'}
        </button>
        <button
          onClick={onStop}
          disabled={disabled}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-colors border backdrop-blur-sm disabled:opacity-40 disabled:cursor-not-allowed
            bg-white/5 hover:bg-white/10 text-white/70 border-white/10"
        >
          Stop
        </button>
      </div>

      {/* Preset selector */}
      <div className="flex flex-col gap-1">
        <span className="text-[10px] text-white/40 font-medium uppercase tracking-wider">
          Preset
        </span>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              onClick={() => onPreset(p.id)}
              disabled={disabled}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors border disabled:opacity-40 disabled:cursor-not-allowed
                ${
                  activePreset === p.id
                    ? 'bg-fuchsia-500/25 text-fuchsia-300 border-fuchsia-500/40'
                    : 'bg-white/5 text-white/60 hover:bg-white/10 border-white/10'
                }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
