// History view for melosviz — lists past renders with replay button.
// Styled with Tailwind CSS to match the dark HUD aesthetic.

import { useCallback } from 'react'

export interface RenderJob {
  id: string
  title: string
  createdAt: string
  status: 'completed' | 'failed' | 'running'
  duration?: number
}

export interface HistoryProps {
  jobs: RenderJob[]
  onReplay: (jobId: string) => void
  onDelete?: (jobId: string) => void
  disabled?: boolean
}

export function History({ jobs, onReplay, onDelete, disabled = false }: HistoryProps) {
  const displayJobs = jobs.slice(0, 20)

  const formatDate = useCallback((iso: string) => {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }, [])

  const statusIcon = (status: RenderJob['status']) => {
    switch (status) {
      case 'completed':
        return (
          <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        )
      case 'failed':
        return (
          <svg className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        )
      case 'running':
        return (
          <svg className="w-4 h-4 text-cyan-400 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        )
    }
  }

  if (displayJobs.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-white/40">
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className="text-sm">No past renders yet</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-[10px] text-white/40 font-medium uppercase tracking-wider">
        History ({displayJobs.length})
      </span>
      <div className="flex flex-col gap-1 max-h-64 overflow-y-auto pr-1">
        {displayJobs.map((job) => (
          <div
            key={job.id}
            className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 transition-colors"
          >
            {statusIcon(job.status)}
            <div className="flex-1 min-w-0">
              <div className="text-sm text-white/80 truncate">{job.title}</div>
              <div className="text-xs text-white/40">
                {formatDate(job.createdAt)}
                {job.duration !== undefined && ` · ${job.duration}s`}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => onReplay(job.id)}
                disabled={disabled || job.status === 'running'}
                className="px-2 py-1 rounded-md text-xs font-medium transition-colors border border-white/10 bg-white/5 hover:bg-white/10 text-white/70 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Replay
              </button>
              {onDelete && (
                <button
                  onClick={() => onDelete(job.id)}
                  disabled={disabled}
                  className="px-2 py-1 rounded-md text-xs font-medium transition-colors border border-red-500/20 bg-red-500/10 hover:bg-red-500/20 text-red-300 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
