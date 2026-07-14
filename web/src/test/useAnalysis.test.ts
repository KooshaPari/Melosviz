import { describe, expect, it, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import {
  formatAnalysisError,
  parseMemoryCapDetail,
  problemDetailFromBody,
  useAnalysis,
} from '../hooks/useAnalysis'
import { setLocale } from '../i18n'

describe('parseMemoryCapDetail', () => {
  it('parses hard-cap detail from bridge problem+json', () => {
    expect(
      parseMemoryCapDetail(
        'memory cap exceeded (hard): rss=200MB > cap=100MB',
      ),
    ).toEqual({ tier: 'hard', rssMb: 200, capMb: 100 })
  })

  it('returns null for unrelated detail strings', () => {
    expect(parseMemoryCapDetail('path is outside the allowed data directory')).toBeNull()
  })
})

describe('problemDetailFromBody', () => {
  it('reads FastAPI detail field', () => {
    expect(
      problemDetailFromBody({
        detail: 'memory cap exceeded (soft): rss=150MB > cap=100MB',
      }),
    ).toBe('memory cap exceeded (soft): rss=150MB > cap=100MB')
  })
})

describe('formatAnalysisError', () => {
  beforeEach(() => {
    setLocale('en')
  })

  it('maps gateway errors to bridge unreachable', () => {
    const { message, kind } = formatAnalysisError(undefined, 502, 'Bad Gateway')
    expect(kind).toBe('bridge')
    expect(message).toBe('Analysis bridge is not reachable')
  })

  it('maps memory-cap 503 to memory_cap with RSS hints', () => {
    const { message, kind } = formatAnalysisError(
      undefined,
      503,
      'Service Unavailable',
      'memory cap exceeded (hard): rss=200MB > cap=100MB',
    )
    expect(kind).toBe('memory_cap')
    expect(message).toContain('200')
    expect(message).toContain('100')
  })

  it('maps generic 503 to server error when detail is not memory cap', () => {
    const { message, kind } = formatAnalysisError(undefined, 503, 'Service Unavailable')
    expect(kind).toBe('server')
    expect(message).toBe('Server error: 503 Service Unavailable')
  })

  it('maps fetch TypeError to bridge unreachable', () => {
    const { message, kind } = formatAnalysisError(new TypeError('Failed to fetch'))
    expect(kind).toBe('bridge')
    expect(message).toBe('Analysis bridge is not reachable')
  })

  it('maps HTTP 500 to server error with status', () => {
    const { message, kind } = formatAnalysisError(undefined, 500, 'Internal Server Error')
    expect(kind).toBe('server')
    expect(message).toBe('Server error: 500 Internal Server Error')
  })

  it('translates bridge unreachable in Spanish', () => {
    setLocale('es')
    const { message } = formatAnalysisError(new TypeError('Failed to fetch'))
    expect(message).toBe('No se puede contactar con el puente de análisis')
  })
})

describe('useAnalysis', () => {
  beforeEach(() => {
    setLocale('en')
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('cancel aborts in-flight analyze without setting error', async () => {
    let rejectFetch!: (reason?: unknown) => void
    const fetchPromise = new Promise<Response>((_, reject) => {
      rejectFetch = reject
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(() => fetchPromise),
    )

    const { result } = renderHook(() => useAnalysis())

    act(() => {
      void result.current.analyze('/tmp/track.wav')
    })
    await waitFor(() => expect(result.current.loading).toBe(true))
    expect(result.current.progress).toBe(0)

    act(() => {
      result.current.cancel()
      rejectFetch(new DOMException('Aborted', 'AbortError'))
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBeNull()
    expect(result.current.data).toBeNull()
    expect(result.current.progress).toBeNull()
  })

  it('retry after cancel ignores stale response and completes cleanly', async () => {
    let resolveFirst!: (value: Response) => void
    const firstPromise = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })
    let callCount = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(() => {
        callCount += 1
        if (callCount === 1) return firstPromise
        return Promise.resolve(
          new Response(
            JSON.stringify({ durationSecs: 90, keyframes: [], bpm: 120 }),
            { status: 200 },
          ),
        )
      }),
    )

    const { result } = renderHook(() => useAnalysis())

    act(() => {
      void result.current.analyze('/tmp/track.wav')
    })
    await waitFor(() => expect(result.current.loading).toBe(true))

    act(() => {
      result.current.cancel()
    })
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      resolveFirst(
        new Response(JSON.stringify({ durationSecs: 999 }), { status: 200 }),
      )
    })
    await waitFor(() => expect(result.current.data).toBeNull())

    await act(async () => {
      await result.current.analyze('/tmp/track.wav')
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.data?.durationSecs).toBe(90)
    expect(result.current.error).toBeNull()
  })

  it('completes analyze when fetch succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ durationSecs: 120, keyframes: [], bpm: 128 }),
            { status: 200 },
          ),
        ),
      ),
    )

    const { result } = renderHook(() => useAnalysis())

    await act(async () => {
      await result.current.analyze('/tmp/track.wav')
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.data?.durationSecs).toBe(120)
    expect(result.current.error).toBeNull()
    expect(result.current.progress).toBeNull()
  })

  it('surfaces memory-cap rejection from bridge problem+json', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              detail: 'memory cap exceeded (soft): rss=150MB > cap=100MB',
            }),
            { status: 429, statusText: 'Too Many Requests' },
          ),
        ),
      ),
    )

    const { result } = renderHook(() => useAnalysis())

    await act(async () => {
      await result.current.analyze('/tmp/huge-track.wav')
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.errorKind).toBe('memory_cap')
    expect(result.current.error).toContain('150')
    expect(result.current.error).toContain('100')
  })

  it('dismissError clears error without affecting data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(new Response('bad', { status: 500, statusText: 'Error' })),
      ),
    )

    const { result } = renderHook(() => useAnalysis())

    await act(async () => {
      await result.current.analyze('/tmp/track.wav')
    })
    expect(result.current.error).toBeTruthy()

    act(() => {
      result.current.dismissError()
    })

    expect(result.current.error).toBeNull()
    expect(result.current.errorKind).toBeNull()
    expect(result.current.data).toBeNull()
  })
})
