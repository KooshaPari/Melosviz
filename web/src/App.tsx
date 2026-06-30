import { useCallback, useEffect, useRef, useState } from 'react'
import { SceneView } from './r3fRenderer'
import { AudioAdapter } from './audioAdapter'
import { specToSceneParams } from './renderSpec'
import type { RenderSpec, SceneParams } from './renderSpec'

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

const DEFAULT_PARAMS: SceneParams = specToSceneParams(PLACEHOLDER_SPEC, 0)

export default function App() {
  const adapterRef = useRef<AudioAdapter | null>(null)
  const startTimeRef = useRef<number>(performance.now())
  const [isPlaying, setIsPlaying] = useState(false)
  const [scene, setScene] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useState<SceneParams>(DEFAULT_PARAMS)

  // Advance the render spec playhead every animation frame
  useEffect(() => {
    let raf: number
    const tick = () => {
      const elapsed = (performance.now() - startTimeRef.current) / 1000
      setParams(specToSceneParams(PLACEHOLDER_SPEC, elapsed))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
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

  // Scene override: jump the playhead to the matching keyframe's t position
  const handleSceneChange = useCallback((s: number) => {
    setScene(s)
    // Index 0 = "Placeholder" (t=0), indices 1–5 map to keyframes 0–4
    const kfIndex = Math.max(0, s - 1)
    const kf = PLACEHOLDER_SPEC.keyframes[kfIndex]
    if (kf) {
      startTimeRef.current =
        performance.now() - kf.t * PLACEHOLDER_SPEC.durationSecs * 1000
    }
  }, [])

  const scenes = [
    'Placeholder',
    'Establishing',
    'Performance',
    'Anthem',
    'Interlude',
    'Outro',
  ]

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#080808]">
      <SceneView params={params} className="absolute inset-0 w-full h-full" />
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-3">
        <h1 className="text-xl font-bold tracking-tight text-white/90">
          Melosviz
        </h1>
        <div className="flex items-center gap-2">
          <button
            onClick={isPlaying ? handleStop : handleStart}
            className="px-4 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-sm font-medium transition-colors border border-cyan-500/30"
          >
            {isPlaying ? 'Stop Audio' : 'Start Audio'}
          </button>
        </div>
        {error && (
          <p className="text-sm text-red-400 max-w-xs">{error}</p>
        )}
      </div>
      <div className="absolute top-4 right-4 z-10 flex flex-col gap-2">
        <label className="text-xs text-white/50 font-medium uppercase tracking-wider">
          Scene
        </label>
        <div className="flex flex-col gap-1">
          {scenes.map((name, i) => (
            <button
              key={name}
              onClick={() => handleSceneChange(i)}
              className={`px-3 py-1.5 rounded-md text-xs text-left transition-colors ${
                scene === i
                  ? 'bg-fuchsia-500/25 text-fuchsia-300 border border-fuchsia-500/40'
                  : 'bg-white/5 text-white/60 hover:bg-white/10 border border-white/10'
              }`}
            >
              {name}
            </button>
          ))}
        </div>
      </div>
      <div className="absolute bottom-4 left-4 right-4 z-10 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-xs text-white/40">
            {isPlaying ? 'Listening' : 'Idle'}
          </span>
        </div>
        <div className="text-xs text-white/30">
          Three.js / R3F
        </div>
      </div>
    </div>
  )
}
