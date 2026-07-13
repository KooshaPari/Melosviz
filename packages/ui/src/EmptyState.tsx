import type { ReactNode } from "react";

export interface EmptyStateProps {
  /** Illustration or icon, typically an inline SVG mirroring the brand spectrum motif. */
  icon?: ReactNode;
  title: string;
  description?: string;
  /** Primary call-to-action, e.g. a `Button`. */
  action?: ReactNode;
  footnote?: string;
  className?: string;
}

/**
 * Branded empty/zero-data state wrapper (C10 L100 / L105). Title uses the
 * shared brand gradient token so every empty state across the app matches
 * without re-deriving the gradient per call-site.
 */
export function EmptyState({ icon, title, description, action, footnote, className = "" }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center gap-2 py-2 text-center${className ? ` ${className}` : ""}`}>
      {icon}
      <p
        className="text-xs font-medium tracking-tight"
        style={{
          background: "var(--mv-grad-brand, linear-gradient(90deg, #4c40b0, #7c6af7, #c084fc))",
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          color: "transparent",
        }}
      >
        {title}
      </p>
      {description && (
        <p className="text-[11px] text-white/40 leading-relaxed px-1">{description}</p>
      )}
      {action}
      {footnote && <p className="text-[10px] text-white/25">{footnote}</p>}
    </div>
  );
}
