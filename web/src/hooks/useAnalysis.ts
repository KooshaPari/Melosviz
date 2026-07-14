import { useState, useCallback, useRef } from 'react'
import type { RenderSpec, Keyframe } from '../renderSpec'
import { t, tf } from '../i18n'

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

export type AnalysisErrorKind = 'bridge' | 'server' | 'memory_cap' | 'unknown'

export interface MemoryCapDetails {
  tier: 'soft' | 'hard'
  rssMb: number
  capMb: number
}

/** Parse bridge MemoryCapExceeded detail strings from problem+json bodies. */
export function parseMemoryCapDetail(detail: string): MemoryCapDetails | null {
  const match = detail.match(
    /memory cap exceeded \((soft|hard)\): rss=(\d+)MB > cap=(\d+)MB/i,
  )
  if (!match) return null
  return {
    tier: match[1] as 'soft' | 'hard',
    rssMb: Number(match[2]),
    capMb: Number(match[3]),
  }
}

/** Extract a string detail from a FastAPI / problem+json error body. */
export function problemDetailFromBody(body: unknown): string | undefined {
  if (typeof body === 'string') return body
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return undefined
}

/** Classify fetch / HTTP failures into user-facing bridge vs server messages. */
export function formatAnalysisError(
  err: unknown,
  status?: number,
  statusText = '',
  detail?: string,
): { message: string; kind: AnalysisErrorKind } {
  if (status !== undefined) {
    const memory = detail ? parseMemoryCapDetail(detail) : null
    if (memory) {
      const key =
        memory.tier === 'soft' ? 'error.memory_cap_soft' : 'error.memory_cap_hard'
      return {
        message: tf(key, { rssMb: memory.rssMb, capMb: memory.capMb }),
        kind: 'memory_cap',
      }
    }
    if (status === 502 || status === 504) {
      return { message: t('error.bridge_unreachable'), kind: 'bridge' }
    }
    return {
      message: tf('error.analysis_server', { status, statusText }),
      kind: 'server',
    }
  }

  if (err instanceof TypeError) {
    const msg = err.message.toLowerCase()
    if (
      msg.includes('fetch') ||
      msg.includes('network') ||
      msg.includes('load failed') ||
      msg.includes('failed to fetch')
    ) {
      return { message: t('error.bridge_unreachable'), kind: 'bridge' }
    }
  }

  if (err instanceof Error && err.message) {
    return { message: err.message, kind: 'unknown' }
  }

  return { message: t('error.analysis_unknown'), kind: 'unknown' }
}

interface AnalysisState {
  data: RenderSpec | null
  loading: boolean
  /** Simulated 0–100 progress while loading; null when idle. */
  progress: number | null
  error: string | null
  errorKind: AnalysisErrorKind | null
}

function clearProgressTimer(timerRef: { current: ReturnType<typeof setInterval> | null }) {
  if (timerRef.current !== null) {
    clearInterval(timerRef.current)
    timerRef.current = null
  }
}

/** Asymptotic ramp — stays below 95% until the fetch resolves. */
function simulatedProgressPct(elapsedMs: number): number {
  return Math.min(95, Math.round(95 * (1 - Math.exp(-elapsedMs / 4000))))
}

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({
    data: null,
    loading: false,
    progress: null,
    error: null,
    errorKind: null,
  })
  const abortRef = useRef<AbortController | null>(null)
  const generationRef = useRef(0)
  const progressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const progressStartRef = useRef(0)

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    generationRef.current += 1
    clearProgressTimer(progressTimerRef)
    setState((prev) => ({
      ...prev,
      loading: false,
      progress: null,
      error: null,
      errorKind: null,
    }))
  }, [])

  const dismissError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null, errorKind: null }))
  }, [])

  const analyze = useCallback(async (audioPath: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const generation = ++generationRef.current

    const isStale = () => generation !== generationRef.current

    clearProgressTimer(progressTimerRef)
    progressStartRef.current = Date.now()
    setState({ data: null, loading: true, progress: 0, error: null, errorKind: null })
    progressTimerRef.current = setInterval(() => {
      const elapsed = Date.now() - progressStartRef.current
      const pct = simulatedProgressPct(elapsed)
      setState((prev) => (prev.loading ? { ...prev, progress: pct } : prev))
    }, 250)
    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_path: audioPath }),
        signal: controller.signal,
      })
      if (isStale() || controller.signal.aborted) return
      if (!res.ok) {
        let detail: string | undefined
        try {
          detail = problemDetailFromBody(await res.json())
        } catch {
          detail = undefined
        }
        const { message, kind } = formatAnalysisError(
          undefined,
          res.status,
          res.statusText,
          detail,
        )
        throw Object.assign(new Error(message), { analysisKind: kind })
      }
      const raw = (await res.json()) as AnalysisRenderSpec
      if (isStale() || controller.signal.aborted) return
      clearProgressTimer(progressTimerRef)
      setState({ data: toRenderSpec(raw), loading: false, progress: null, error: null, errorKind: null })
    } catch (err) {
      if (isStale() || controller.signal.aborted) return
      if (err instanceof DOMException && err.name === 'AbortError') return
      const kind =
        (err as { analysisKind?: AnalysisErrorKind }).analysisKind ??
        formatAnalysisError(err).kind
      const message =
        err instanceof Error ? err.message : formatAnalysisError(err).message
      clearProgressTimer(progressTimerRef)
      setState({
        data: null,
        loading: false,
        progress: null,
        error: message,
        errorKind: kind,
      })
    } finally {
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [])

  return { ...state, analyze, cancel, dismissError }
}
