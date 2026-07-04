interface LoadingOverlayProps {
  visible: boolean
}

export function LoadingOverlay({ visible }: LoadingOverlayProps) {
  if (!visible) return null

  return (
    <div
      className="fixed inset-0 z-40 flex flex-col items-center justify-center"
      style={{ background: 'rgba(15,15,26,0.85)', backdropFilter: 'blur(4px)' }}
    >
      <style>{`
        @keyframes mv-freq {
          0%, 100% { transform: scaleY(0.2); }
          50%       { transform: scaleY(1.0); }
        }
        .mv-freq-bar {
          transform-origin: bottom;
          animation: mv-freq var(--dur, 0.6s) ease-in-out infinite;
        }
      `}</style>

      <div className="flex items-end gap-1 h-10 mb-4">
        {[0.5, 0.8, 1.0, 0.7, 0.9, 0.6, 1.0, 0.8, 0.5].map((_, i) => (
          <div
            key={i}
            className="mv-freq-bar w-1.5 rounded-sm"
            style={{
              height: '100%',
              background: `linear-gradient(to top, #7c3aed, #06b6d4)`,
              // @ts-expect-error CSS custom property
              '--dur': `${0.4 + i * 0.07}s`,
              animationDelay: `${i * 0.06}s`,
            }}
          />
        ))}
      </div>

      <p className="text-sm font-medium tracking-widest uppercase" style={{ color: 'rgba(255,255,255,0.6)' }}>
        Analyzing audio…
      </p>
    </div>
  )
}
