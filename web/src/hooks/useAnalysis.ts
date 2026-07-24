import { useState, useCallback } from 'react'
import type { RenderSpec } from '../renderSpec'
import { mapAnalysisToRenderSpec, type RawAnalysisSpec } from '../mapAnalysisSpec'

/** @deprecated Prefer RawAnalysisSpec from mapAnalysisSpec — kept for test imports. */
export type AnalysisRenderSpec = RawAnalysisSpec

const BLOB_PREFIX = 'blob:'
const LARGE_UPLOAD_BYTES = 10 * 1024 * 1024

function isBlobUrl(path: string): boolean {
  return path.startsWith(BLOB_PREFIX)
}

/** Turn fetch / network failures into user-facing messages. */
export function formatAnalysisError(err: unknown, status?: number): string {
  if (status === 413) {
    return 'File too large for the bridge (max 1 GiB upload). Try a shorter clip or paste a server path.'
  }
  if (err instanceof TypeError) {
    const msg = err.message.toLowerCase()
    if (
      msg.includes('failed to fetch') ||
      msg.includes('networkerror') ||
      msg.includes('load failed')
    ) {
      return 'Connection to the bridge was reset. Is the bridge running on 127.0.0.1:8765?'
    }
  }
  if (err instanceof Error) return err.message
  return 'Unknown error'
}

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* ignore non-JSON bodies */
  }
  return `${res.status} ${res.statusText}`
}

/** Upload a browser File to POST /upload; returns server-side wav_path. */
export async function uploadAudioFile(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/upload')
    xhr.responseType = 'json'

    if (onProgress && file.size > 0) {
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) {
          onProgress(Math.round((ev.loaded / ev.total) * 100))
        }
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const body = xhr.response as { wav_path?: string }
        if (body?.wav_path) {
          resolve(body.wav_path)
          return
        }
        reject(new Error('Upload response missing wav_path'))
        return
      }
      if (xhr.status === 413) {
        reject(Object.assign(new Error(formatAnalysisError(null, 413)), { status: 413 }))
        return
      }
      const detail =
        typeof xhr.response === 'object' && xhr.response?.detail
          ? String(xhr.response.detail)
          : `${xhr.status} ${xhr.statusText}`
      reject(new Error(`Upload failed: ${detail}`))
    }

    xhr.onerror = () => {
      reject(
        new TypeError(
          'Connection to the bridge was reset during upload. Is the bridge running on 127.0.0.1:8765?',
        ),
      )
    }

    const form = new FormData()
    form.append('file', file, file.name)
    xhr.send(form)
  })
}

/** Resolve a blob: URL to a server wav_path; passthrough for filesystem paths. */
export async function resolveServerAudioPath(
  audioPath: string,
  onProgress?: (percent: number) => void,
): Promise<string> {
  if (!isBlobUrl(audioPath)) return audioPath

  const blobRes = await fetch(audioPath)
  if (!blobRes.ok) {
    throw new Error(`Failed to read local audio: ${blobRes.status}`)
  }
  const blob = await blobRes.blob()
  const name =
    blob.type && blob.type !== 'application/octet-stream'
      ? `upload.${blob.type.split('/')[1] ?? 'wav'}`
      : 'upload.wav'
  const file = new File([blob], name, { type: blob.type || 'audio/wav' })
  return uploadAudioFile(file, onProgress)
}

export async function fetchAnalyze(wavPath: string): Promise<RawAnalysisSpec> {
  const res = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ wav_path: wavPath }),
  })
  if (!res.ok) {
    const detail = await readErrorDetail(res)
    throw Object.assign(new Error(`Server error: ${detail}`), { status: res.status })
  }
  return (await res.json()) as RawAnalysisSpec
}

/** Analyze a pasted path or blob: URL end-to-end. */
export async function analyzeAudioPath(
  audioPath: string,
  onProgress?: (percent: number) => void,
): Promise<RenderSpec> {
  const wavPath = await resolveServerAudioPath(audioPath, onProgress)
  const raw = await fetchAnalyze(wavPath)
  return mapAnalysisToRenderSpec(raw)
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
  /** 0–100 while uploading a blob URL; null otherwise. */
  uploadProgress: number | null
  statusHint: string | null
}

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({
    data: null,
    loading: false,
    progress: null,
    error: null,
    uploadProgress: null,
    statusHint: null,
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
    setState({
      data: null,
      loading: true,
      error: null,
      uploadProgress: null,
      statusHint: isBlobUrl(audioPath) ? 'Preparing upload…' : null,
    })
    try {
      const spec = await analyzeAudioPath(audioPath, (pct) => {
        setState((prev) => ({
          ...prev,
          uploadProgress: pct,
          statusHint: pct < 100 ? `Uploading… ${pct}%` : 'Analyzing…',
        }))
      })
      setState({
        data: spec,
        loading: false,
        error: null,
        uploadProgress: null,
        statusHint: null,
      })
    } catch (err) {
      const status =
        err && typeof err === 'object' && 'status' in err
          ? (err as { status: number }).status
          : undefined
      setState({
        data: null,
        loading: false,
        error: formatAnalysisError(err, status),
        uploadProgress: null,
        statusHint: null,
      })
    } finally {
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [])

  return { ...state, analyze, cancel, dismissError }
}

export { LARGE_UPLOAD_BYTES, isBlobUrl }
