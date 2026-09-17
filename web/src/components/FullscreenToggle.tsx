import { useEffect } from "react";
import { t } from "../i18n";

export interface FullscreenToggleProps {
  fullscreen: boolean;
  onToggle: () => void;
  onEscape?: () => void;
  /** Optional className. */
  className?: string;
}

/**
 * Single-button fullscreen toggle that flips `aria-pressed` and listens for
 * Escape so screen-reader / keyboard users have a real, accessible handle on
 * the scene view.
 */
export function FullscreenToggle({
  fullscreen,
  onToggle,
  onEscape,
  className,
}: FullscreenToggleProps) {
  useEffect(() => {
    if (!fullscreen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (onEscape) onEscape();
        else onToggle();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [fullscreen, onToggle, onEscape]);

  return (
    <button
      type="button"
      aria-pressed={fullscreen ? "true" : "false"}
      aria-label={
        fullscreen ? t("fullscreen.exit_aria") : t("fullscreen.enter_aria")
      }
      onClick={onToggle}
      className={
        "rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-white/80 hover:bg-white/10 hover:border-white/20 transition-colors " +
        (className ?? "")
      }
    >
      {fullscreen ? t("fullscreen.exit") : t("fullscreen.enter")}
    </button>
  );
}
