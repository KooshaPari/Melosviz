import { useState, useCallback } from 'react'

export interface AnalysisRenderSpec {
  title?: string
  bpm?: number
  key?: string
  duration_sec?: number
  color_palette?: string[]
  [key: string]: unknown
}

interface AnalysisState {
  data: AnalysisRenderSpec | null
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
      const data = (await res.json()) as AnalysisRenderSpec
      setState({ data, loading: false, error: null })
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
