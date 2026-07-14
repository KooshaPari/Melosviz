import { useState, useCallback } from 'react'
import type { RenderSpec } from '../renderSpec'
import { mapAnalysisToRenderSpec, type RawAnalysisSpec } from '../mapAnalysisSpec'

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
      const raw = (await res.json()) as RawAnalysisSpec
      setState({ data: mapAnalysisToRenderSpec(raw), loading: false, error: null })
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
