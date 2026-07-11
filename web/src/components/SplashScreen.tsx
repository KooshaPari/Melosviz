import { useEffect, useState } from 'react'

interface SplashScreenProps {
  onDone: () => void
}

export function SplashScreen({ onDone }: SplashScreenProps) {
  const [fading, setFading] = useState(false)

  useEffect(() => {
    const fadeTimer = setTimeout(() => setFading(true), 1600)
    const doneTimer = setTimeout(() => onDone(), 2200)
    return () => {
      clearTimeout(fadeTimer)
      clearTimeout(doneTimer)
    }
  }, [onDone])

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center"
      style={{
        background: 'var(--mv-bg)',
        transition: 'opacity 0.6s ease-out',
        opacity: fading ? 0 : 1,
        pointerEvents: fading ? 'none' : 'all',
      }}
    >
      <style>{`
        @keyframes mv-shimmer {
          0%   { background-position: -200% center; }
          100% { background-position: 200% center; }
        }
        @keyframes mv-wave {
          0%, 100% { transform: scaleY(0.4); }
          50%       { transform: scaleY(1.0); }
        }
        .mv-title {
          background: linear-gradient(
            90deg,
            #7c3aed 0%,
            #06b6d4 30%,
            #a78bfa 50%,
            #06b6d4 70%,
            #7c3aed 100%
          );
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          animation: mv-shimmer 2.4s linear infinite;
        }
        .mv-bar {
          animation: mv-wave var(--delay, 0.4s) ease-in-out infinite;
          transform-origin: bottom;
        }
        @media (prefers-reduced-motion: reduce) {
          .mv-title, .mv-bar { animation: none !important; }
        }
      `}</style>

      {/* Waveform SVG */}
      <div className="flex items-end gap-1 mb-6 h-12">
        {[0.3, 0.6, 1.0, 0.8, 0.5, 0.9, 0.4, 0.7, 1.0, 0.6, 0.3].map((h, i) => (
          <div
            key={i}
            className="mv-bar rounded-full w-1.5"
            style={{
              height: `${h * 100}%`,
              background: `linear-gradient(to top, var(--mv-primary), var(--mv-secondary))`,
              // @ts-expect-error CSS custom property
              '--delay': `${0.2 + i * 0.08}s`,
              animationDelay: `${i * 0.07}s`,
            }}
          />
        ))}
      </div>

      <h1 className="mv-title text-5xl font-black tracking-tight mb-2">MelosViz</h1>
      <p className="text-sm font-medium tracking-[0.3em] uppercase" style={{ color: 'rgba(255,255,255,0.4)' }}>
        Music · Vision · Render
      </p>
    </div>
  )
}
