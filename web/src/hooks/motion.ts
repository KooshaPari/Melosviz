import { useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A single cubic-bezier curve with a recommended CSS transition duration. */
export interface EasingCurve {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Recommended duration in milliseconds for CSS transitions. */
  durationMs: number;
}

/** Resolved state from the spring solver at a point in time. */
export interface SpringState {
  /** Current position (1 = fully resolved). */
  x: number;
  /** Current velocity (units/ms). */
  dx: number;
}

/** Tuning parameters for the critically-damped spring solver. */
export interface SpringConfig {
  /** Spring stiffness. Higher = snappier. Default 300. */
  stiffness: number;
  /** Damping coefficient. Defaults to critical damping when omitted. */
  damping: number;
  /** Attached mass. Higher = heavier feel. Default 1. */
  mass: number;
}

// ---------------------------------------------------------------------------
// Easing curves
// ---------------------------------------------------------------------------

export const standard: EasingCurve = {
  x1: 0.2,
  y1: 0.0,
  x2: 0.0,
  y2: 1.0,
  durationMs: 200,
};

export const emphasized: EasingCurve = {
  x1: 0.2,
  y1: 0.0,
  x2: 0.0,
  y2: 1.0,
  durationMs: 320,
};

export const quick: EasingCurve = {
  x1: 0.4,
  y1: 0.0,
  x2: 0.6,
  y2: 1.0,
  durationMs: 120,
};

export const deliberate: EasingCurve = {
  x1: 0.0,
  y1: 0.0,
  x2: 0.0,
  y2: 1.0,
  durationMs: 500,
};

// ---------------------------------------------------------------------------
// motionTokens — CSS `transition` shorthand values
// ---------------------------------------------------------------------------

function toTransitionValue(ease: EasingCurve): string {
  const bezier = `cubic-bezier(${ease.x1},${ease.y1},${ease.x2},${ease.y2})`;
  return `all ${ease.durationMs}ms ${bezier}`;
}

/** CSS `transition` shorthand strings for every easing curve. */
export const motionTokens: Record<string, string> = {
  standard: toTransitionValue(standard),
  emphasized: toTransitionValue(emphasized),
  quick: toTransitionValue(quick),
  deliberate: toTransitionValue(deliberate),
};

// ---------------------------------------------------------------------------
// Spring solver — critically-damped
//
// Evaluates a damped harmonic oscillator at time `t` (ms).  Internally
// converts t to seconds so stiffness/damping/mass values correspond to
// familiar physical ranges (stiffness ~100-500, damping ~10-50).
// ---------------------------------------------------------------------------

/**
 * Create a critically-damped spring solver function.
 *
 * When `damping` is omitted it is auto-computed for **critical damping**
 * (damping ratio ζ = 1), meaning the system returns to rest as fast as
 * possible without overshoot.
 *
 * @example
 * ```ts
 * const spring = withSpring({ stiffness: 300 })
 * // Evaluate 100 ms after release from x = 1, v = 0
 * const { x, dx } = spring(100, 1, 0)
 * ```
 */
export function withSpring(config?: Partial<SpringConfig>) {
  const { stiffness = 300, damping: userDamping, mass = 1 } = config ?? {};

  // Convert ms → s internally so ω₀ carries the right dimension
  const msToSec = 1 / 1000;
  const omega0 = Math.sqrt(stiffness / mass) * msToSec; // rad/ms → rad/s
  const damping = userDamping ?? 2 * Math.sqrt(stiffness * mass) * msToSec;
  const zeta = damping / (2 * omega0 * mass);

  return (tMs: number, x0: number = 1, v0: number = 0): SpringState => {
    const t = tMs * msToSec; // ms → sec

    if (Math.abs(zeta - 1) < 1e-6) {
      // Critically-damped: x(t) = (A + B·t) · e^(−ω₀·t)
      const A = x0;
      const B = v0 + omega0 * x0;
      const exp = Math.exp(-omega0 * t);
      return {
        x: (A + B * t) * exp,
        dx: (B - omega0 * (A + B * t)) * exp,
      };
    }

    if (zeta > 1) {
      // Over-damped
      const r1 = -omega0 * (zeta - Math.sqrt(zeta * zeta - 1));
      const r2 = -omega0 * (zeta + Math.sqrt(zeta * zeta - 1));
      const c2 = (v0 - r1 * x0) / (r2 - r1);
      const c1 = x0 - c2;
      return {
        x: c1 * Math.exp(r1 * t) + c2 * Math.exp(r2 * t),
        dx: c1 * r1 * Math.exp(r1 * t) + c2 * r2 * Math.exp(r2 * t),
      };
    }

    // Under-damped
    const omegaD = omega0 * Math.sqrt(1 - zeta * zeta);
    const A = x0;
    const B = (v0 + zeta * omega0 * x0) / omegaD;
    const decay = Math.exp(-zeta * omega0 * t);
    const cos = Math.cos(omegaD * t);
    const sin = Math.sin(omegaD * t);
    return {
      x: decay * (A * cos + B * sin),
      dx:
        -zeta * omega0 * decay * (A * cos + B * sin) +
        decay * (-A * omegaD * sin + B * omegaD * cos),
    };
  };
}

// ---------------------------------------------------------------------------
// prefersReducedMotion
// ---------------------------------------------------------------------------

/**
 * React hook that returns `true` when the user prefers reduced motion.
 *
 * Re-evaluates whenever the OS-level preference changes so the value stays
 * reactive across component boundaries.
 *
 * @example
 * ```tsx
 * function FadeIn({ children }: { children: React.ReactNode }) {
 *   const reduced = usePrefersReducedMotion()
 *   return (
 *     <div
 *       style={{
 *         transition: reduced ? 'none' : motionTokens.standard,
 *         opacity: reduced ? 1 : 0,
 *       }}
 *     >
 *       {children}
 *     </div>
 *   )
 * }
 * ```
 */
export function usePrefersReducedMotion(): boolean {
  const [prefersReduced, setPrefersReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReduced(mq.matches);

    const handler = (e: MediaQueryListEvent) => setPrefersReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return prefersReduced;
}
