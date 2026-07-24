import { t, tf } from '../i18n'
import { PLAYBACK_RATE_PRESETS } from '../lib/playbackRate'
import { formatTrackTime } from '../utils/sceneSummary'

export interface PlaybackTransportProps {
  playbackT: number
  autoPlay: boolean
  durationSecs: number
  currentSceneLabel: string
  isListening: boolean
  bpm?: number
  onTogglePlay: () => void
  onSeek: (t: number) => void
  onReset: () => void
  /** When true, render volume/mute controls (paired with a hidden audio element). */
  showVolume?: boolean
  volume?: number
  muted?: boolean
  onVolumeChange?: (volume: number) => void
  onMutedToggle?: () => void
  /** Scene/audio playback speed multiplier (0.5–1.5). */
  playbackRate?: number
  onPlaybackRateChange?: (rate: number) => void
  /** When true, restart scene from 0 when playback reaches the end. */
  loopEnabled?: boolean
  onLoopToggle?: () => void
}

export function PlaybackTransport({
  playbackT,
  autoPlay,
  durationSecs,
  currentSceneLabel,
  isListening,
  bpm,
  onTogglePlay,
  onSeek,
  onReset,
  showVolume = false,
  volume = 0.8,
  muted = false,
  onVolumeChange,
  onMutedToggle,
  playbackRate = 1,
  onPlaybackRateChange,
  loopEnabled = false,
  onLoopToggle,
}: PlaybackTransportProps) {
  const duration = Math.max(0, durationSecs)
  const elapsedSecs = duration * playbackT
  const elapsed = formatTrackTime(elapsedSecs)
  const total = formatTrackTime(duration)
  const timeReadout = tf('playback.time', { elapsed, total })
  const volumePct = Math.round(Math.max(0, Math.min(1, volume)) * 100)
  const ratePct = Math.round(playbackRate * 100)

  const statusKey = autoPlay
    ? 'playback.status.playing'
    : isListening
      ? 'playback.status.listening'
      : 'playback.status.idle'

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3 rounded-lg bg-black/40 border border-white/10 px-4 py-3">
        <button
          type="button"
          onClick={onTogglePlay}
          title={autoPlay ? t('playback.pause') : t('playback.play')}
          aria-label={autoPlay ? t('playback.pause_aria') : t('playback.play_aria')}
          className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border transition-colors text-sm ${
            autoPlay
              ? 'bg-fuchsia-500/30 border-fuchsia-500/50 text-fuchsia-200'
              : 'bg-white/5 border-white/20 text-white/60 hover:bg-white/10'
          }`}
        >
          {autoPlay ? '⏸' : '▶'}
        </button>

        <div className="flex-1 flex flex-col gap-1">
          <input
            type="range"
            min={0}
            max={100}
            step={0.1}
            value={Math.round(playbackT * 1000) / 10}
            onChange={(e) => onSeek(Number(e.target.value) / 100)}
            aria-label={t('playback.seek_aria')}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(playbackT * 100)}
            aria-valuetext={timeReadout}
            className="w-full h-1.5 rounded-full appearance-none bg-white/10 accent-fuchsia-500 cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-white/30">
            <span>{currentSceneLabel}</span>
            <span aria-live="off">{timeReadout}</span>
          </div>
        </div>

        {showVolume && onVolumeChange && onMutedToggle && (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              type="button"
              onClick={onMutedToggle}
              title={muted ? t('playback.unmute') : t('playback.mute')}
              aria-label={muted ? t('playback.unmute_aria') : t('playback.mute_aria')}
              aria-pressed={muted}
              className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center border border-white/20 bg-white/5 hover:bg-white/10 text-white/60 text-xs transition-colors"
            >
              {muted ? '🔇' : '🔊'}
            </button>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={muted ? 0 : volumePct}
              onChange={(e) => {
                const next = Number(e.target.value) / 100
                onVolumeChange(next)
                if (next > 0 && muted) onMutedToggle()
              }}
              aria-label={t('playback.volume_aria')}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={muted ? 0 : volumePct}
              aria-valuetext={tf('playback.volume_valuetext', { pct: muted ? 0 : volumePct })}
              className="w-16 h-1.5 rounded-full appearance-none bg-white/10 accent-cyan-500 cursor-pointer"
            />
          </div>
        )}

        {onPlaybackRateChange && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <div className="hidden sm:flex items-center gap-0.5" role="group" aria-label={t('playback.rate_presets_aria')}>
              {PLAYBACK_RATE_PRESETS.map((preset) => {
                const active = Math.abs(playbackRate - preset) < 0.05
                return (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => onPlaybackRateChange(preset)}
                    title={tf('playback.rate_preset', { rate: preset.toFixed(1) })}
                    aria-label={tf('playback.rate_preset_aria', { rate: preset.toFixed(1) })}
                    aria-pressed={active}
                    className={`px-1 py-0.5 rounded text-[9px] font-mono border transition-colors ${
                      active
                        ? 'bg-amber-500/25 border-amber-500/50 text-amber-200'
                        : 'bg-white/5 border-white/15 text-white/40 hover:bg-white/10'
                    }`}
                  >
                    {preset.toFixed(1)}×
                  </button>
                )
              })}
            </div>
            <span className="text-[10px] text-white/35 font-mono w-7 text-right" aria-hidden="true">
              {playbackRate.toFixed(1)}×
            </span>
            <input
              type="range"
              min={50}
              max={150}
              step={10}
              value={ratePct}
              onChange={(e) => onPlaybackRateChange(Number(e.target.value) / 100)}
              title={t('playback.rate')}
              aria-label={t('playback.rate_aria')}
              aria-valuemin={50}
              aria-valuemax={150}
              aria-valuenow={ratePct}
              aria-valuetext={tf('playback.rate_valuetext', { rate: playbackRate.toFixed(1) })}
              className="w-14 h-1.5 rounded-full appearance-none bg-white/10 accent-amber-500 cursor-pointer"
            />
          </div>
        )}

        {onLoopToggle && (
          <button
            type="button"
            onClick={onLoopToggle}
            title={loopEnabled ? t('playback.loop_off') : t('playback.loop_on')}
            aria-label={loopEnabled ? t('playback.loop_off_aria') : t('playback.loop_on_aria')}
            aria-pressed={loopEnabled}
            className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border text-xs transition-colors ${
              loopEnabled
                ? 'bg-emerald-500/25 border-emerald-500/50 text-emerald-200'
                : 'border-white/20 bg-white/5 hover:bg-white/10 text-white/60'
            }`}
          >
            🔁
          </button>
        )}

        <button
          type="button"
          onClick={onReset}
          title={t('playback.reset')}
          aria-label={t('playback.reset_aria')}
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border border-white/20 bg-white/5 hover:bg-white/10 text-white/60 text-xs transition-colors"
        >
          ↺
        </button>
      </div>

      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-3">
          <div
            className={`w-2 h-2 rounded-full ${
              autoPlay
                ? 'bg-fuchsia-400 animate-pulse'
                : isListening
                  ? 'bg-cyan-400 animate-pulse'
                  : 'bg-white/20'
            }`}
          />
          <span className="text-xs text-white/40">{t(statusKey)}</span>
          <div className="hidden sm:flex items-center gap-1.5" aria-hidden="true">
            <span className="inline-flex items-center gap-1 rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-white/35 font-mono">
              <span>{t('keyboard.label.arrow_left')}</span>
              <span>{t('playback.seek_hint_back')}</span>
            </span>
            <span className="inline-flex items-center gap-1 rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-white/35 font-mono">
              <span>{t('playback.seek_hint_forward')}</span>
              <span>{t('keyboard.label.arrow_right')}</span>
            </span>
          </div>
        </div>
        <div className="text-xs text-white/30">
          {tf('playback.bpm_footer', { bpm: bpm ?? 120 })}
        </div>
      </div>
    </div>
  )
}
