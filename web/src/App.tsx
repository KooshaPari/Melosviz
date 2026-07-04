import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { KeyboardHelp } from './components/KeyboardHelp'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'

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
      color: { primary: '#7c3aed', secondary: '#06b6d4', brightness: 0.7 },
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
  const { data: renderSpec, loading: analyzing, error: analysisError, analyze } = useAnalysis()

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
        const next = prev + dt * progressPerMs
        if (next >= 1) {
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
  }, [autoPlay, activeSpec.bpm, activeSpec.durationSecs])

  // Reset playbackT to 0 when a new spec arrives
  useEffect(() => {
    setPlaybackT(0)
    setAutoPlay(false)
  }, [renderSpec])

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
    closeModal: () => setShowHelp(false),
    openPresetEditor: () => { /* preset editor triggered externally */ },
    toggleFullscreen: () => setFullscreen((v) => !v),
    restartPlayback: () => { setAutoPlay(false); setPlaybackT(0) },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [activeSpec.durationSecs])

  useKeyboardShortcuts(shortcutActions)

  // Scene jump: map button index → keyframe t
  const handleSceneJump = useCallback(
    (index: number) => {
      const kf = activeSpec.keyframes[index]
      if (kf) setPlaybackT(kf.t)
    },
    [activeSpec.keyframes],
  )

  const currentSceneLabel =
    (() => {
      const sorted = [...activeSpec.keyframes].sort((a, b) => a.t - b.t)
      let label = sorted[0]?.scene ?? 'Start'
      for (const kf of sorted) {
        if (playbackT >= kf.t) label = kf.scene ?? label
      }
      return label
    })()

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#080808]">
      {showSplash && <SplashScreen onDone={() => setShowSplash(false)} />}
      <LoadingOverlay visible={analyzing} />
      <KeyboardHelp open={showHelp} onOpenChange={setShowHelp} />

      {/* ---- R3F Canvas -------------------------------------------------- */}
      <SceneView
        spec={activeSpec}
        playbackT={playbackT}
        className={`absolute inset-0 w-full h-full${fullscreen ? ' z-40' : ''}`}
      />

      {/* ---- Playlist sidebar (right of left panel) --------------------- */}
      <div className="absolute top-4 left-72 z-10 flex flex-col gap-3">
        <PlaylistPanel
          playlist={playlist}
          onSelectItem={handleSelectPlaylistItem}
        />
      </div>

      {/* ---- Left panel -------------------------------------------------- */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-3 w-64">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight text-white/90">Melosviz</h1>
          <button
            onClick={() => setShowHelp(true)}
            title="Keyboard shortcuts (?)"
            className="flex h-6 w-6 items-center justify-center rounded-full border border-white/20 bg-white/5 text-xs text-white/50 hover:bg-white/10 hover:text-white/80 transition-colors"
            aria-label="Show keyboard shortcuts"
          >
            ?
          </button>
        </div>

        {/* File picker + Analyze */}
        <div className="flex flex-col gap-2 rounded-lg bg-black/40 border border-white/10 p-3">
          <label className="text-xs text-white/50 font-medium uppercase tracking-wider">
            Audio File Path
          </label>
          <input
            type="text"
            value={audioPath}
            onChange={(e) => setAudioPath(e.target.value)}
            placeholder="/path/to/track.mp3"
            className="px-2 py-1.5 rounded bg-white/5 border border-white/10 text-xs text-white/80 placeholder:text-white/30 focus:outline-none focus:border-cyan-500/50"
          />
          <button
            onClick={() => { if (audioPath) void analyze(audioPath) }}
            disabled={!audioPath || analyzing}
            className="px-3 py-1.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-medium transition-colors border border-cyan-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {analyzing ? 'Analyzing…' : 'Analyze'}
          </button>
          {analysisError && <p className="text-xs text-red-400">{analysisError}</p>}
          {renderSpec && <SpecViewer spec={renderSpec} />}
        </div>

        {/* Audio playback + preset editor */}
        <div className="flex items-center gap-2">
          <button
            onClick={isPlaying ? handleStop : handleStart}
            className="px-4 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-sm font-medium transition-colors border border-cyan-500/30"
          >
            {isPlaying ? 'Stop Audio' : 'Start Audio'}
          </button>
          <PresetEditor
            spec={activeSpec}
            onPreviewChange={(t) => { setAutoPlay(false); setPlaybackT(t) }}
          />
        </div>

        {error && <p className="text-sm text-red-400 max-w-xs">{error}</p>}
      </div>

      {/* ---- Right panel: scene jumps ------------------------------------- */}
      <div className="absolute top-4 right-4 z-10 flex flex-col gap-2">
        <label className="text-xs text-white/50 font-medium uppercase tracking-wider">
          Scene
        </label>
        <div className="flex flex-col gap-1">
          {activeSpec.keyframes.map((kf, i) => (
            <button
              key={kf.scene ?? i}
              onClick={() => handleSceneJump(i)}
              className={`px-3 py-1.5 rounded-md text-xs text-left transition-colors ${
                currentSceneLabel === kf.scene
                  ? 'bg-fuchsia-500/25 text-fuchsia-300 border border-fuchsia-500/40'
                  : 'bg-white/5 text-white/60 hover:bg-white/10 border border-white/10'
              }`}
            >
              {kf.scene ?? `Beat ${i + 1}`}
            </button>
          ))}
        </div>
      </div>

      {/* ---- Waveform display (visible when an audio path is set) ---------- */}
      {audioPath && (
        <div className="absolute bottom-36 left-4 right-4 z-10">
          <WaveformDisplay audioSrc={audioPath} playbackT={playbackT} />
        </div>
      )}

      {/* ---- Bottom bar: playback controls -------------------------------- */}
      <div className="absolute bottom-4 left-4 right-4 z-10 flex flex-col gap-2">
        {/* Slider + auto-play */}
        <div className="flex items-center gap-3 rounded-lg bg-black/40 border border-white/10 px-4 py-3">
          {/* Auto-play toggle */}
          <button
            onClick={() => setAutoPlay((v) => !v)}
            title={autoPlay ? 'Pause auto-play' : 'Start auto-play'}
            className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border transition-colors text-sm ${
              autoPlay
                ? 'bg-fuchsia-500/30 border-fuchsia-500/50 text-fuchsia-200'
                : 'bg-white/5 border-white/20 text-white/60 hover:bg-white/10'
            }`}
          >
            {autoPlay ? '⏸' : '▶'}
          </button>

          {/* Playback position slider (0–100%) */}
          <div className="flex-1 flex flex-col gap-1">
            <input
              type="range"
              min={0}
              max={100}
              step={0.1}
              value={Math.round(playbackT * 1000) / 10}
              onChange={(e) => {
                setAutoPlay(false)
                setPlaybackT(Number(e.target.value) / 100)
              }}
              className="w-full h-1.5 rounded-full appearance-none bg-white/10 accent-fuchsia-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-white/30">
              <span>{currentSceneLabel}</span>
              <span>{Math.round(playbackT * 100)}%</span>
            </div>
          </div>

          {/* Reset button */}
          <button
            onClick={() => { setAutoPlay(false); setPlaybackT(0) }}
            title="Reset to start"
            className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border border-white/20 bg-white/5 hover:bg-white/10 text-white/60 text-xs transition-colors"
          >
            ↺
          </button>
        </div>

        {/* Status row */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-3">
            <div className={`w-2 h-2 rounded-full ${autoPlay ? 'bg-fuchsia-400 animate-pulse' : isPlaying ? 'bg-cyan-400 animate-pulse' : 'bg-white/20'}`} />
            <span className="text-xs text-white/40">
              {autoPlay ? 'Playing' : isPlaying ? 'Listening' : 'Idle'}
            </span>
          </div>
          <div className="text-xs text-white/30">
            {activeSpec.bpm ?? 120} BPM · Three.js / R3F
          </div>
        </div>
      </div>
    </div>
  )
}
