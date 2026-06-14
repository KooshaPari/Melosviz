import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { History, type RenderJob } from '../history'

describe('History', () => {
  const jobs: RenderJob[] = [
    { id: '1', title: 'Jazz Jam', createdAt: '2024-01-01T00:00:00Z', status: 'completed', duration: 30 },
    { id: '2', title: 'EDM Drop', createdAt: '2024-01-02T00:00:00Z', status: 'running' },
    { id: '3', title: 'Classical', createdAt: '2024-01-03T00:00:00Z', status: 'failed' },
  ]

  it('renders empty state', () => {
    render(<History jobs={[]} onReplay={vi.fn()} />)
    expect(screen.getByText('No past renders yet')).toBeInTheDocument()
  })

  it('renders job list', () => {
    render(<History jobs={jobs} onReplay={vi.fn()} />)
    expect(screen.getByText('Jazz Jam')).toBeInTheDocument()
    expect(screen.getByText('EDM Drop')).toBeInTheDocument()
    expect(screen.getByText('Classical')).toBeInTheDocument()
  })

  it('calls onReplay when replay clicked', () => {
    const onReplay = vi.fn()
    render(<History jobs={jobs} onReplay={onReplay} />)
    const replayButtons = screen.getAllByText('Replay')
    fireEvent.click(replayButtons[0])
    expect(onReplay).toHaveBeenCalledWith('1')
  })

  it('shows only last 20 jobs', () => {
    const manyJobs = Array.from({ length: 25 }, (_, i) => ({
      id: String(i),
      title: `Job ${i}`,
      createdAt: '2024-01-01T00:00:00Z',
      status: 'completed' as const,
    }))
    render(<History jobs={manyJobs} onReplay={vi.fn()} />)
    expect(screen.getByText('History (20)')).toBeInTheDocument()
  })
})
