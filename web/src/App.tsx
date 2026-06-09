import { useEffect, useRef, useState } from 'react'
import { CanvasRenderer } from './canvasRenderer'
import { AudioAdapter } from './audioAdapter'

export default function App() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rendererRef = useRef<CanvasRenderer | null>(null)
  const adapterRef = useRef<AudioAdapter | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [scene, setScene] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const renderer = new CanvasRenderer(canvas)
    rendererRef.current = renderer

    const adapter = new AudioAdapter((data) => {
      renderer.updateAudioData(data)
    })
    adapterRef.current = adapter

    let raf: number
    const loop = () => {
      renderer.render()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      renderer.dispose()
      adapter.dispose()
    }
  }, [])

  const handleStart = async () => {
    try {
      setError(null)
      await adapterRef.current?.start()
      setIsPlaying(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start audio')
    }
  }

  const handleStop = () => {
    adapterRef.current?.stop()
    setIsPlaying(false)
  }

  const handleSceneChange = (s: number) => {
    setScene(s)
    rendererRef.current?.setScene(s)
  }

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
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
      />
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
          Web Audio API / WebGL
        </div>
      </div>
    </div>
  )
}
