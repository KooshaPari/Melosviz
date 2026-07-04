import type { RenderSpec } from '../renderSpec'

interface SpecViewerProps {
  spec: RenderSpec
}

export function SpecViewer({ spec }: SpecViewerProps) {
  const summary = {
    bpm: spec.bpm ?? '—',
    durationSecs: spec.durationSecs,
    keyframes: spec.keyframes.length,
  }

  return (
    <div className="mt-3 rounded-lg bg-white/5 border border-white/10 p-3">
      <p className="text-xs text-white/50 font-medium uppercase tracking-wider mb-2">
        RenderSpec
      </p>
      <pre className="text-xs text-cyan-300 whitespace-pre-wrap font-mono leading-relaxed">
        {JSON.stringify(summary, null, 2)}
      </pre>
    </div>
  )
}
