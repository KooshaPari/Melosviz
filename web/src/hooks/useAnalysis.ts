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

interface AnalysisState {
  data: RenderSpec | null
  loading: boolean
  error: string | null
  /** 0–100 while uploading a blob URL; null otherwise. */
  uploadProgress: number | null
  statusHint: string | null
}

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({
    data: null,
    loading: false,
    error: null,
    uploadProgress: null,
    statusHint: null,
  })

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
    }
  }, [])

  return { ...state, analyze }
}

export { LARGE_UPLOAD_BYTES, isBlobUrl }
