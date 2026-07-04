import { useState, useCallback } from 'react'
import type { RenderSpec, Keyframe } from '../renderSpec'

/** Raw shape returned by the /api/analyze endpoint. */
export interface AnalysisRenderSpec {
  title?: string
  bpm?: number
  key?: string
  duration_sec?: number
  durationSecs?: number
  keyframes?: Keyframe[]
  color_palette?: string[]
  [key: string]: unknown
}

/** Map the loose backend response to the canonical RenderSpec contract. */
function toRenderSpec(raw: AnalysisRenderSpec): RenderSpec {
  return {
    durationSecs: raw.durationSecs ?? raw.duration_sec ?? 240,
    keyframes: raw.keyframes ?? [],
    bpm: raw.bpm,
  }
}

interface AnalysisState {
  data: RenderSpec | null
  loading: boolean
  error: string | null
}

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({
    data: null,
    loading: false,
    error: null,
  })

  const analyze = useCallback(async (audioPath: string) => {
    setState({ data: null, loading: true, error: null })
    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_path: audioPath }),
      })
      if (!res.ok) {
        throw new Error(`Server error: ${res.status} ${res.statusText}`)
      }
      const raw = (await res.json()) as AnalysisRenderSpec
      setState({ data: toRenderSpec(raw), loading: false, error: null })
    } catch (err) {
      setState({
        data: null,
        loading: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  }, [])

  return { ...state, analyze }
}
