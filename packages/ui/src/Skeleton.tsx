import type { CSSProperties } from "react";

/** Content-shaped loading skeleton primitive (C10 L99). */
export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={`mv-skeleton ${className}`}
      style={style}
      aria-hidden="true"
    />
  );
}

/** Stacked skeleton block used by loading overlays (C10 L99). */
export function SkeletonBlock() {
  return (
    <div className="flex w-full max-w-md flex-col gap-3 p-4" role="status" aria-label="Loading">
      <style>{`
        .mv-skeleton {
          background: linear-gradient(
            90deg,
            var(--mv-surface) 0%,
            rgba(124, 106, 247, 0.25) 50%,
            var(--mv-surface) 100%
          );
          background-size: 200% 100%;
          animation: mv-skel 1.2s ease-in-out infinite;
          border-radius: 8px;
        }
        @keyframes mv-skel {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          .mv-skeleton { animation: none; }
        }
      `}</style>
      <Skeleton style={{ height: 18, width: "40%" }} />
      <Skeleton style={{ height: 12, width: "100%" }} />
      <Skeleton style={{ height: 12, width: "85%" }} />
      <Skeleton style={{ height: 120, width: "100%" }} />
    </div>
  );
}
