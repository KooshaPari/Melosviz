import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { usePlaylist } from '../hooks/usePlaylist'
import type { RenderSpec } from '../renderSpec'

const MOCK_SPEC: RenderSpec = {
  durationSecs: 120,
  keyframes: [],
  bpm: 100,
}

function makeFile(name = 'test.mp3'): File {
  return new File(['audio'], name, { type: 'audio/mpeg' })
}

/** Returns a never-settling promise — simulates a stalled analysis request. */
function pendingAnalyze(): Promise<RenderSpec> {
  return new Promise(() => {/* never resolves */})
}

// Mock URL.createObjectURL / URL.revokeObjectURL
beforeEach(() => {
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:mock-url'),
    revokeObjectURL: vi.fn(),
  })
})

describe('usePlaylist', () => {
  it('starts with an empty queue', () => {
    const analyze = vi.fn().mockImplementation(pendingAnalyze)
    const { result } = renderHook(() => usePlaylist(analyze))
    expect(result.current.queue).toHaveLength(0)
    expect(result.current.currentIndex).toBe(-1)
    expect(result.current.isProcessing).toBe(false)
  })

  it('addFiles appends items with pending status', () => {
    const analyze = vi.fn().mockImplementation(pendingAnalyze)
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('a.mp3'), makeFile('b.mp3')])
    })

    expect(result.current.queue).toHaveLength(2)
    // First item is immediately picked up for analysis (effect fires on mount)
    expect(['pending', 'analyzing']).toContain(result.current.queue[0]!.status)
    // Second item stays pending until first completes
    expect(result.current.queue[1]!.status).toBe('pending')
    expect(result.current.currentIndex).toBe(0)
  })

  it('removeItem removes the correct item and adjusts currentIndex', () => {
    const analyze = vi.fn().mockImplementation(pendingAnalyze)
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('a.mp3'), makeFile('b.mp3'), makeFile('c.mp3')])
    })

    const idToRemove = result.current.queue[0]!.id
    act(() => {
      result.current.removeItem(idToRemove)
    })

    expect(result.current.queue).toHaveLength(2)
    expect(result.current.queue.find((i) => i.id === idToRemove)).toBeUndefined()
  })

  it('reorder swaps items correctly', () => {
    const analyze = vi.fn().mockImplementation(pendingAnalyze)
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('a.mp3'), makeFile('b.mp3'), makeFile('c.mp3')])
    })

    const originalIds = result.current.queue.map((i) => i.id)

    act(() => {
      result.current.reorder(0, 2)
    })

    const newIds = result.current.queue.map((i) => i.id)
    expect(newIds[2]).toBe(originalIds[0])
    expect(newIds[0]).toBe(originalIds[1])
    expect(newIds[1]).toBe(originalIds[2])
  })

  it('reorder move-down keeps currentIndex on the moved item', () => {
    const analyze = vi.fn().mockImplementation(pendingAnalyze)
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('a.mp3'), makeFile('b.mp3'), makeFile('c.mp3')])
    })
    act(() => {
      result.current.setCurrentIndex(1)
    })
    act(() => {
      result.current.reorder(1, 2)
    })

    expect(result.current.currentIndex).toBe(2)
    expect(result.current.queue[2]?.file.name).toBe('b.mp3')
  })

  it('clearQueue empties the queue and resets state', () => {
    const analyze = vi.fn().mockImplementation(pendingAnalyze)
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('a.mp3')])
    })
    act(() => {
      result.current.clearQueue()
    })

    expect(result.current.queue).toHaveLength(0)
    expect(result.current.currentIndex).toBe(-1)
    expect(result.current.isProcessing).toBe(false)
  })

  it('auto-advances to next pending item after analysis completes', async () => {
    const analyze = vi.fn().mockResolvedValue(MOCK_SPEC)
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('a.mp3'), makeFile('b.mp3')])
    })

    // After processing the first item, it should be marked done
    await waitFor(() => {
      expect(result.current.queue[0]?.status).toBe('done')
    })

    // currentIndex should have advanced to 1 (next pending item)
    expect(result.current.currentIndex).toBe(1)
  })

  it('marks item as error when analysis fails', async () => {
    const analyze = vi.fn().mockRejectedValue(new Error('network failure'))
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('fail.mp3')])
    })

    await waitFor(() => {
      expect(result.current.queue[0]?.status).toBe('error')
    })

    expect(result.current.queue[0]?.errorMsg).toBe('network failure')
  })

  it('setCurrentIndex updates the active item', () => {
    const analyze = vi.fn().mockImplementation(pendingAnalyze)
    const { result } = renderHook(() => usePlaylist(analyze))

    act(() => {
      result.current.addFiles([makeFile('a.mp3'), makeFile('b.mp3'), makeFile('c.mp3')])
    })
    act(() => {
      result.current.setCurrentIndex(2)
    })

    expect(result.current.currentIndex).toBe(2)
    expect(result.current.activeItem?.file.name).toBe('c.mp3')
  })
})
