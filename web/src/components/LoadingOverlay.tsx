import { Dialog, DialogContent, DialogOverlay } from "./Dialog";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import { t, tf } from "../i18n";
import { SkeletonBlock } from "./Skeleton";

interface LoadingOverlayProps {
  visible: boolean;
  onCancel?: () => void;
  /** 0–100 while analysis is in flight; omit for indeterminate-only copy. */
  progressPct?: number | null;
}

const BAR_HEIGHTS = [0.5, 0.8, 1.0, 0.7, 0.9, 0.6, 1.0, 0.8, 0.5];

export function LoadingOverlay({
  visible,
  onCancel,
  progressPct,
}: LoadingOverlayProps) {
  const reducedMotion = usePrefersReducedMotion();

  if (!visible) return null;

  const hasProgress = progressPct != null && Number.isFinite(progressPct);
  const roundedPct = hasProgress
    ? Math.max(0, Math.min(100, Math.round(progressPct)))
    : null;
  const liveMessage = hasProgress
    ? tf("a11y.analysis_progress_pct", { pct: roundedPct! })
    : t("status.analyzing");
  const description = hasProgress
    ? tf("a11y.analysis_progress_pct_hint", { pct: roundedPct! })
    : t("a11y.analysis_progress");

  return (
    <Dialog.Root open={visible} modal>
      <Dialog.Portal>
        <DialogOverlay
          className="z-40 flex flex-col items-center justify-center gap-6"
          style={{
            background: "rgba(15,15,26,0.85)",
            backdropFilter: reducedMotion ? "none" : "blur(4px)",
          }}
        />
        <DialogContent
          className="fixed inset-0 z-40 flex flex-col items-center justify-center gap-6"
          aria-describedby="loading-overlay-desc"
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => {
            if (onCancel) {
              e.preventDefault();
              onCancel();
            } else {
              e.preventDefault();
            }
          }}
          onOpenAutoFocus={(e) => {
            if (!onCancel) return;
            e.preventDefault();
            e.currentTarget
              .querySelector<HTMLElement>("#loading-overlay-cancel")
              ?.focus();
          }}
        >
          <Dialog.Title className="sr-only">
            {t("status.analyzing")}
          </Dialog.Title>
          <Dialog.Description id="loading-overlay-desc" className="sr-only">
            {description}
          </Dialog.Description>
          <div aria-live="polite" aria-atomic="true" className="sr-only">
            {liveMessage}
          </div>

          {!reducedMotion && (
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
          )}

          <div className="flex items-end gap-1 h-10 mb-2" aria-hidden="true">
            {BAR_HEIGHTS.map((scale, i) => (
              <div
                key={i}
                className={
                  reducedMotion
                    ? "w-1.5 rounded-sm"
                    : "mv-freq-bar w-1.5 rounded-sm"
                }
                style={{
                  height: "100%",
                  background: `linear-gradient(to top, var(--mv-primary), var(--mv-secondary))`,
                  ...(reducedMotion
                    ? {
                        transform: `scaleY(${scale})`,
                        transformOrigin: "bottom",
                      }
                    : {
                        // @ts-expect-error CSS custom property
                        "--dur": `${0.4 + i * 0.07}s`,
                        animationDelay: `${i * 0.06}s`,
                      }),
                }}
              />
            ))}
          </div>

          <p
            className="text-sm font-medium tracking-widest uppercase"
            style={{ color: "rgba(255,255,255,0.6)" }}
            aria-hidden="true"
          >
            {hasProgress
              ? tf("status.analyzing_pct", { pct: roundedPct! })
              : t("status.analyzing")}
          </p>
          {hasProgress && (
            <div
              className="w-48 h-1 rounded-full bg-white/10 overflow-hidden"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={roundedPct!}
              aria-label={tf("a11y.analysis_progress_pct", {
                pct: roundedPct!,
              })}
            >
              <div
                className="h-full rounded-full bg-gradient-to-r from-[var(--mv-primary)] to-[var(--mv-secondary)] transition-[width] duration-300"
                style={{ width: `${roundedPct}%` }}
              />
            </div>
          )}
          {onCancel && (
            <button
              id="loading-overlay-cancel"
              type="button"
              onClick={onCancel}
              className="text-xs font-medium text-white/50 hover:text-white/80 underline underline-offset-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mv-border-focus,#22d3ee)] focus-visible:ring-offset-2 focus-visible:ring-offset-black/80"
            >
              {t("action.cancel")}
            </button>
          )}
          <SkeletonBlock />
        </DialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
