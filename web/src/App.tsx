import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { t, tf } from './i18n'
import { useLocale } from './i18n/LocaleProvider'
import { SceneView } from './r3fRenderer'
import { AudioAdapter } from './audioAdapter'
import type { RenderSpec } from './renderSpec'
import { SpecViewer } from './components/SpecViewer'
import { useAnalysis } from './hooks/useAnalysis'
import { usePlaylist } from './hooks/usePlaylist'
import type { PlaylistItem } from './hooks/usePlaylist'
import { PlaylistPanel } from './components/PlaylistPanel'
import { SplashScreen } from './components/SplashScreen'
import { LoadingOverlay } from './components/LoadingOverlay'
import { WaveformDisplay } from './components/WaveformDisplay'
import { PresetEditor } from './components/PresetEditor'
import type { NamedPreset } from './components/PresetEditor'
import { PresetQuickApply } from './components/PresetQuickApply'
import { KeyboardHelp } from './components/KeyboardHelp'
import { LocaleSwitcher } from './components/LocaleSwitcher'
import { OnboardingBanner } from './components/OnboardingBanner'
import { AudioDropzone } from './components/AudioDropzone'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useTheme } from './theme/ThemeProvider'
import { PlaybackTransport } from './components/PlaybackTransport'
import { loadPlaybackVolume, savePlaybackVolume } from './lib/playbackVolume'
import { loadPlaybackRate, savePlaybackRate } from './lib/playbackRate'
import { loadPlaybackLoop, savePlaybackLoop } from './lib/playbackLoop'

// Placeholder spec — drives the scene from the first frame.
// Workstream C (semantic multi-scene) will replace this with a server-fetched
// spec per uploaded track; workstreams A/B will populate spectral/beat fields.
const PLACEHOLDER_SPEC: RenderSpec = {
  durationSecs: 240,
  bpm: 128,
  keyframes: [
    {
      t: 0,
      scene: 'Establishing',
      camera: { distance: 8, azimuth: 0, elevation: 0.15 },
      color: { primary: '#7c6af7', secondary: '#22d3ee', brightness: 0.7 },
    },
    {
      t: 0.18,
      scene: 'Performance',
      camera: { distance: 5, azimuth: 0.4, elevation: 0.1 },
      color: { primary: '#ec4899', secondary: '#f59e0b', brightness: 0.9 },
    },
    {
      t: 0.45,
      scene: 'Anthem',
      camera: { distance: 4, azimuth: -0.3, elevation: 0.3 },
      color: { primary: '#f97316', secondary: '#a3e635', brightness: 1.0 },
    },
    {
      t: 0.72,
      scene: 'Interlude',
      camera: { distance: 7, azimuth: 0, elevation: 0.05 },
      color: { primary: '#0ea5e9', secondary: '#818cf8', brightness: 0.6 },
    },
    {
      t: 0.88,
      scene: 'Outro',
      camera: { distance: 10, azimuth: 0.2, elevation: 0.2 },
      color: { primary: '#6366f1', secondary: '#22d3ee', brightness: 0.5 },
    },
  ],
}

export default function App() {
  const adapterRef = useRef<AudioAdapter | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [audioPath, setAudioPath] = useState('')
  const [showSplash, setShowSplash] = useState(true)
  const [showHelp, setShowHelp] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const { theme, highContrast, toggle: toggleTheme, toggleHighContrast } = useTheme()
  const { locale } = useLocale()
  const { data: renderSpec, loading: analyzing, progress: analysisProgress, error: analysisError, errorKind: analysisErrorKind, analyze, cancel: cancelAnalysis, dismissError: dismissAnalysisError } = useAnalysis()

  // Playlist: wraps useAnalysis.analyze for file-based inputs
  const analyzeFile = useCallback(async (objectUrl: string): Promise<RenderSpec> => {
    await analyze(objectUrl)
    // analyze() updates state; we need a direct fetch here for the playlist
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio_path: objectUrl }),
    })
    if (!res.ok) throw new Error(`Server error: ${res.status}`)
    const raw = (await res.json()) as Record<string, unknown>
    return {
      durationSecs: (raw.durationSecs as number) ?? (raw.duration_sec as number) ?? 240,
      keyframes: (raw.keyframes as RenderSpec['keyframes']) ?? [],
      bpm: raw.bpm as number | undefined,
    }
  }, [analyze])

  const playlist = usePlaylist(analyzeFile)
  // Track which playlist item the user is actively viewing
  const [playlistViewSpec, setPlaylistViewSpec] = useState<RenderSpec | null>(null)

  const handleSelectPlaylistItem = useCallback((item: PlaylistItem) => {
    if (item.spec) setPlaylistViewSpec(item.spec)
  }, [])

  // Active spec priority: playlist-selected > analyzed > placeholder
  const activeSpec: RenderSpec = playlistViewSpec ?? renderSpec ?? PLACEHOLDER_SPEC

  // ---- Playback state ------------------------------------------------------
  const [playbackT, setPlaybackT] = useState(0)
  const [autoPlay, setAutoPlay] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playbackVolume, setPlaybackVolume] = useState(() => loadPlaybackVolume().volume)
  const [playbackMuted, setPlaybackMuted] = useState(() => loadPlaybackVolume().muted)
  const [playbackRate, setPlaybackRate] = useState(() => loadPlaybackRate())
  const [playbackLoop, setPlaybackLoop] = useState(() => loadPlaybackLoop())

  // Auto-play: advance playbackT at bpm-derived rate.
  // Each beat = 1 / totalBeats progress; totalBeats = bpm * durationSecs / 60.
  const rafRef = useRef<number | null>(null)
  const lastTickRef = useRef<number>(performance.now())
  const playbackTRef = useRef(0)
  playbackTRef.current = playbackT

  useEffect(() => {
    if (!autoPlay) {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
      return
    }

    const bpm = activeSpec.bpm ?? 120
    const totalBeats = (bpm * activeSpec.durationSecs) / 60
    // Progress per millisecond = 1 / (durationSecs * 1000)
    const progressPerMs = 1 / (activeSpec.durationSecs * 1000)

    lastTickRef.current = performance.now()

    const tick = (now: number) => {
      const dt = now - lastTickRef.current
      lastTickRef.current = now
      // Clamp totalBeats usage to avoid drift; advance by elapsed fraction
      void totalBeats // referenced for future beat-lock accuracy
      setPlaybackT((prev) => {
        const next = prev + dt * progressPerMs * playbackRate
        if (next >= 1) {
          if (playbackLoop) {
            const el = audioRef.current
            if (el) el.currentTime = 0
            return 0
          }
          setAutoPlay(false)
          return 1
        }
        return next
      })
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay, activeSpec.bpm, activeSpec.durationSecs, playbackRate, playbackLoop])

  // Reset playbackT to 0 when a new spec arrives
  useEffect(() => {
    setPlaybackT(0)
    setAutoPlay(false)
  }, [renderSpec])

  // Keep hidden audio element volume/mute/rate in sync with persisted prefs
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    el.volume = playbackVolume
    el.muted = playbackMuted
    el.playbackRate = playbackRate
  }, [playbackVolume, playbackMuted, playbackRate, audioPath])

  const handleVolumeChange = useCallback((volume: number) => {
    setPlaybackVolume(volume)
    savePlaybackVolume({ volume, muted: playbackMuted })
  }, [playbackMuted])

  const handleMutedToggle = useCallback(() => {
    setPlaybackMuted((prev) => {
      const next = !prev
      savePlaybackVolume({ volume: playbackVolume, muted: next })
      return next
    })
  }, [playbackVolume])

  const handlePlaybackRateChange = useCallback((rate: number) => {
    setPlaybackRate(rate)
    savePlaybackRate(rate)
  }, [])

  const handleLoopToggle = useCallback(() => {
    setPlaybackLoop((prev) => {
      const next = !prev
      savePlaybackLoop(next)
      return next
    })
  }, [])

  // Dispose audio on unmount
  useEffect(() => {
    return () => {
      adapterRef.current?.dispose()
    }
  }, [])

  const handleStart = async () => {
    try {
      setError(null)
      if (!adapterRef.current) {
        adapterRef.current = new AudioAdapter()
      }
      setIsPlaying(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start audio')
    }
  }

  const handleStop = () => {
    adapterRef.current?.stop()
    setIsPlaying(false)
  }

  // ---- Keyboard shortcut actions -------------------------------------------
  const shortcutActions = useMemo(() => ({
    togglePlay: () => setAutoPlay((v) => !v),
    seekBackward: () => setPlaybackT((t) => Math.max(0, t - 5 / (activeSpec.durationSecs || 240))),
    seekForward: () => setPlaybackT((t) => Math.min(1, t + 5 / (activeSpec.durationSecs || 240))),
    toggleHelp: () => setShowHelp((v) => !v),
    closeModal: () => {
      if (showHelp) setShowHelp(false)
      else if (fullscreen) setFullscreen(false)
    },
    openPresetEditor: () => { /* preset editor triggered externally */ },
    toggleFullscreen: () => setFullscreen((v) => !v),
    toggleMute: handleMutedToggle,
    toggleLoop: handleLoopToggle,
    restartPlayback: () => { setAutoPlay(false); setPlaybackT(0) },
  }), [activeSpec.durationSecs, showHelp, fullscreen, handleMutedToggle, handleLoopToggle])

  useKeyboardShortcuts(shortcutActions)

  // Scene jump: map button index → keyframe t
  const handleSceneJump = useCallback(
    (index: number) => {
      const kf = activeSpec.keyframes[index]
      if (kf) setPlaybackT(kf.t)
    },
    [activeSpec.keyframes],
  )

  const handleApplyPreset = useCallback((preset: NamedPreset) => {
    setAutoPlay(false)
    setPlaybackT(Math.min(1, Math.max(0, preset.params.energy)))
  }, [])

  const currentSceneLabel =
    (() => {
      const sorted = [...activeSpec.keyframes].sort((a, b) => a.t - b.t)
      let label = sorted[0]?.scene ?? 'Start'
      for (const kf of sorted) {
        if (playbackT >= kf.t) label = kf.scene ?? label
      }
      return label
    })()

  const showOnboarding =
    !showSplash && !renderSpec && playlist.queue.length === 0

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#080808]" data-locale={locale}>
      <a className="skip-link" href="#main">
        {t('a11y.skip_link')}
      </a>
      {showSplash && <SplashScreen onDone={() => setShowSplash(false)} />}
      <LoadingOverlay visible={analyzing} onCancel={cancelAnalysis} progressPct={analysisProgress} />
      <KeyboardHelp open={showHelp} onOpenChange={setShowHelp} />

      {/* ---- R3F Canvas -------------------------------------------------- */}
      <SceneView
        spec={activeSpec}
        playbackT={playbackT}
        currentSceneLabel={currentSceneLabel}
        className={`absolute inset-0 w-full h-full${fullscreen ? ' z-40' : ''}`}
      />

      {showOnboarding && <OnboardingBanner />}

      {/* ---- Playlist sidebar (right of left panel) --------------------- */}
      <div className="absolute top-4 left-72 z-10 flex flex-col gap-3">
        <PlaylistPanel
          playlist={playlist}
          onSelectItem={handleSelectPlaylistItem}
        />
      </div>

      {/* ---- Left panel (main landmark) ---------------------------------- */}
      <main id="main" tabIndex={-1} className="absolute top-4 left-4 z-10 flex flex-col gap-3 w-64">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight text-white/90">Melosviz</h1>
          <div className="flex items-center gap-1">
            <LocaleSwitcher />
            <button
              type="button"
              onClick={toggleHighContrast}
              title={t('theme.high_contrast')}
              className={`flex h-6 w-6 items-center justify-center rounded-full border text-[9px] font-semibold transition-colors ${
                highContrast
                  ? 'border-cyan-400/60 bg-cyan-500/20 text-cyan-200'
                  : 'border-white/20 bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80'
              }`}
              aria-label={
                highContrast
                  ? t('theme.high_contrast_disable_aria')
                  : t('theme.high_contrast_enable_aria')
              }
              aria-pressed={highContrast}
            >
              HC
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              title={theme === 'dark' ? t('theme.switch_light') : t('theme.switch_dark')}
              className="flex h-6 w-6 items-center justify-center rounded-full border border-white/20 bg-white/5 text-[10px] text-white/50 hover:bg-white/10 hover:text-white/80 transition-colors"
              aria-label={
                theme === 'dark'
                  ? t('theme.switch_light_aria')
                  : t('theme.switch_dark_aria')
              }
            >
              {theme === "dark" ? "Aa" : "A"}
            </button>
            <button
              type="button"
              onClick={() => setFullscreen((v) => !v)}
              title={fullscreen ? t('fullscreen.exit') : t('fullscreen.enter')}
              className={`flex h-6 min-w-6 items-center justify-center rounded-full border px-1 text-[9px] font-semibold transition-colors ${
                fullscreen
                  ? 'border-fuchsia-400/60 bg-fuchsia-500/20 text-fuchsia-200'
                  : 'border-white/20 bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80'
              }`}
              aria-label={
                fullscreen ? t('fullscreen.exit_aria') : t('fullscreen.enter_aria')
              }
              aria-pressed={fullscreen}
            >
              {t('fullscreen.label')}
            </button>
            <button
              type="button"
              onClick={() => setShowHelp(true)}
              title={t('keyboard.show_shortcuts_title')}
              className="flex h-6 w-6 items-center justify-center rounded-full border border-white/20 bg-white/5 text-xs text-white/50 hover:bg-white/10 hover:text-white/80 transition-colors"
              aria-label={t('keyboard.show_shortcuts')}
            >
              ?
            </button>
          </div>
        </div>

        {/* File picker + Analyze */}
        <div className="flex flex-col gap-2 rounded-lg bg-black/40 border border-white/10 p-3">
          <AudioDropzone
            value={audioPath}
            onChange={setAudioPath}
            disabled={analyzing}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => { if (audioPath) void analyze(audioPath) }}
              disabled={!audioPath || analyzing}
              className="flex-1 px-3 py-1.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-medium transition-colors border border-cyan-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {analyzing ? t('status.analyzing_short') : t('action.analyze')}
            </button>
            {analyzing && (
              <button
                type="button"
                onClick={cancelAnalysis}
                className="px-2 py-1.5 rounded text-[10px] font-medium text-white/50 hover:text-white/80 border border-white/15 hover:border-white/25 transition-colors"
              >
                {t('action.cancel')}
              </button>
            )}
          </div>
          {analysisError && (
            <div role="alert" className="rounded border border-red-500/30 bg-red-950/30 p-2 space-y-1.5">
              <p className="text-xs text-red-400">{analysisError}</p>
              {analysisErrorKind === 'bridge' && (
                <p className="text-[10px] text-white/40 leading-snug">
                  {t('error.bridge_unreachable_hint')}
                </p>
              )}
              {analysisErrorKind === 'memory_cap' && (
                <p className="text-[10px] text-white/40 leading-snug">
                  {t('error.memory_cap_hint')}
                </p>
              )}
              {audioPath && (
                <button
                  type="button"
                  onClick={() => { if (audioPath) void analyze(audioPath) }}
                  disabled={analyzing}
                  className="text-[10px] font-medium text-cyan-300/90 hover:text-cyan-200 disabled:opacity-40"
                >
                  {t('error.retry')}
                </button>
              )}
              <button
                type="button"
                onClick={dismissAnalysisError}
                aria-label={t('error.dismiss_aria')}
                className="ml-3 text-[10px] font-medium text-white/45 hover:text-white/70"
              >
                {t('error.dismiss')}
              </button>
            </div>
          )}
          {renderSpec && <SpecViewer spec={renderSpec} />}
        </div>

        {/* Audio playback + preset editor */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={isPlaying ? handleStop : handleStart}
            title={isPlaying ? t('audio.stop') : t('audio.start')}
            className="px-4 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-sm font-medium transition-colors border border-cyan-500/30"
          >
            {isPlaying ? t('audio.stop') : t('audio.start')}
          </button>
          <PresetQuickApply onApply={handleApplyPreset} />
          <PresetEditor
            spec={activeSpec}
            onPreviewChange={(t) => { setAutoPlay(false); setPlaybackT(t) }}
            onApplyPreset={handleApplyPreset}
          />
        </div>

        {error && <p className="text-sm text-red-400 max-w-xs">{error}</p>}
      </main>

      {/* ---- Right panel: scene jumps ------------------------------------- */}
      <div className="absolute top-4 right-4 z-10 flex flex-col gap-2">
        <span className="text-xs text-white/50 font-medium uppercase tracking-wider">
          {t('scene.panel_label')}
        </span>
        <div className="flex flex-col gap-1" role="group" aria-label={t('scene.panel_aria')}>
          {activeSpec.keyframes.map((kf, i) => {
            const sceneName = kf.scene ?? tf('scene.beat_fallback', { n: i + 1 })
            const active = currentSceneLabel === kf.scene
            return (
              <button
                key={kf.scene ?? i}
                type="button"
                onClick={() => handleSceneJump(i)}
                title={tf('scene.jump_aria', { name: sceneName })}
                aria-label={tf('scene.jump_aria', { name: sceneName })}
                aria-current={active ? 'true' : undefined}
                className={`px-3 py-1.5 rounded-md text-xs text-left transition-colors ${
                  active
                    ? 'bg-fuchsia-500/25 text-fuchsia-300 border border-fuchsia-500/40'
                    : 'bg-white/5 text-white/60 hover:bg-white/10 border border-white/10'
                }`}
              >
                {sceneName}
              </button>
            )
          })}
        </div>
      </div>

      {/* ---- Hidden audio for track preview volume control ---------------- */}
      {audioPath && (
        <audio ref={audioRef} src={audioPath} preload="metadata" className="sr-only" aria-hidden="true" />
      )}

      {/* ---- Waveform display (visible when an audio path is set) ---------- */}
      {audioPath && (
        <div className="absolute bottom-36 left-4 right-4 z-10">
          <WaveformDisplay audioSrc={audioPath} playbackT={playbackT} />
        </div>
      )}

      {/* ---- Bottom bar: playback controls -------------------------------- */}
      <div className="absolute bottom-4 left-4 right-4 z-10">
        <PlaybackTransport
          playbackT={playbackT}
          autoPlay={autoPlay}
          durationSecs={activeSpec.durationSecs}
          currentSceneLabel={currentSceneLabel}
          isListening={isPlaying}
          bpm={activeSpec.bpm}
          onTogglePlay={() => setAutoPlay((v) => !v)}
          onSeek={(t) => {
            setAutoPlay(false)
            setPlaybackT(t)
          }}
          onReset={() => {
            setAutoPlay(false)
            setPlaybackT(0)
          }}
          showVolume={Boolean(audioPath)}
          volume={playbackVolume}
          muted={playbackMuted}
          onVolumeChange={handleVolumeChange}
          onMutedToggle={handleMutedToggle}
          playbackRate={playbackRate}
          onPlaybackRateChange={handlePlaybackRateChange}
          loopEnabled={playbackLoop}
          onLoopToggle={handleLoopToggle}
        />
      </div>
    </div>
  )
}
