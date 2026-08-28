import { useEffect, useId, useState } from "react";
import { t } from "../i18n";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import { EmptyState } from "@melosviz/ui";

/** Compact spectrum mark — mirrors desktop/assets/brand/gfx/empty-state.svg */
function WelcomeArt({ staticBars }: { staticBars?: boolean }) {
  const uid = useId().replace(/:/g, "");
  const grad = `ob-${uid}`;
  const glow = staticBars ? undefined : `obg-${uid}`;

  const bars = (
    <>
      <rect
        x="122"
        y="80"
        width="8"
        height="20"
        rx="2"
        fill={`url(#${grad})`}
      />
      <rect
        x="134"
        y="72"
        width="8"
        height="28"
        rx="2"
        fill={`url(#${grad})`}
      />
      <rect
        x="146"
        y="66"
        width="8"
        height="34"
        rx="2"
        fill={`url(#${grad})`}
      />
      <rect
        x="158"
        y="62"
        width="8"
        height="38"
        rx="2"
        fill={`url(#${grad})`}
      />
      <rect
        x="170"
        y="66"
        width="8"
        height="34"
        rx="2"
        fill={`url(#${grad})`}
      />
      <rect
        x="182"
        y="72"
        width="8"
        height="28"
        rx="2"
        fill={`url(#${grad})`}
      />
      <rect
        x="194"
        y="80"
        width="8"
        height="20"
        rx="2"
        fill={`url(#${grad})`}
      />
    </>
  );

  return (
    <svg
      viewBox="0 0 320 200"
      className="w-full max-w-[200px] mx-auto opacity-90"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={grad} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="var(--mv-accent, #4c40b0)" />
          <stop offset="50%" stopColor="var(--mv-primary, #7c6af7)" />
          <stop offset="100%" stopColor="#c084fc" />
        </linearGradient>
        {!staticBars && (
          <filter id={glow}>
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        )}
      </defs>
      <circle
        cx="160"
        cy="90"
        r="70"
        fill="none"
        stroke="var(--mv-primary, #7c6af7)"
        strokeWidth="1"
        opacity="0.08"
      />
      <circle
        cx="160"
        cy="90"
        r="52"
        fill="none"
        stroke="var(--mv-primary, #7c6af7)"
        strokeWidth="1"
        opacity="0.12"
      />
      <circle
        cx="160"
        cy="90"
        r="34"
        fill="none"
        stroke="var(--mv-primary, #7c6af7)"
        strokeWidth="1.5"
        opacity="0.18"
      />
      {staticBars ? (
        <g opacity="0.65">{bars}</g>
      ) : (
        <g filter={`url(#${glow})`} opacity="0.65">
          {bars}
        </g>
      )}
    </svg>
  );
}

const STEPS = [
  "onboarding.step_load",
  "onboarding.step_analyze",
  "onboarding.step_preview",
] as const;

/**
 * First-visit guidance overlay — shown until the user loads or analyzes audio.
 * Mirrors the desktop shell welcome empty state (C10 L100 / studio maturity).
 */
export function OnboardingBanner() {
  const reducedMotion = usePrefersReducedMotion();
  const [entered, setEntered] = useState(reducedMotion);

  useEffect(() => {
    if (reducedMotion) return;
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, [reducedMotion]);

  return (
    <div
      className="pointer-events-none absolute inset-0 z-[5] flex items-center justify-center px-6"
      role="region"
      aria-label={t("onboarding.welcome_title")}
    >
      <div
        className={`pointer-events-auto max-w-sm rounded-xl border border-white/10 bg-black/55 px-5 py-4 shadow-xl ${
          reducedMotion
            ? ""
            : "backdrop-blur-sm transition-opacity duration-500 ease-out"
        }`}
        style={{ opacity: entered ? 1 : reducedMotion ? 1 : 0 }}
      >
        <EmptyState
          icon={<WelcomeArt staticBars={reducedMotion} />}
          title={t("onboarding.welcome_title")}
          description={t("onboarding.welcome_desc")}
          footnote={t("onboarding.hint")}
        />
        <ol
          className="mt-3 flex justify-center gap-2"
          aria-label={t("onboarding.steps_label")}
        >
          {STEPS.map((key, i) => (
            <li
              key={key}
              className="flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-white/50"
            >
              <span className="font-mono text-white/30">{i + 1}</span>
              {t(key)}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
