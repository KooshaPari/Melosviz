import { useState, useEffect, useRef, useCallback } from 'react';

// ---------------------------------------------------------------------------
// useReducedMotion – detects OS-level prefers-reduced-motion
// ---------------------------------------------------------------------------

export function useReducedMotion(): boolean {
  const [prefersReduced, setPrefersReduced] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (e: MediaQueryListEvent) => setPrefersReduced(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  return prefersReduced;
}

// ---------------------------------------------------------------------------
// useSpring – spring-physics interpolation from initial → target
// ---------------------------------------------------------------------------

interface SpringConfig {
  stiffness?: number;
  damping?: number;
  mass?: number;
  precision?: number;
}

function defaultSpringConfig(): Required<SpringConfig> {
  return { stiffness: 170, damping: 26, mass: 1, precision: 0.01 };
}

/**
 * Animates a numeric value from `initial` to `target` using spring physics.
 * When reduced motion is preferred the hook immediately returns `target`.
 *
 * @param initial – start value (only used on first render)
 * @param target  – end value
 * @param config  – spring tuning (stiffness, damping, mass, precision)
 * @param enabled – when false the spring is paused at its current value
 */
export function useSpring(
  initial: number,
  target: number,
  config?: SpringConfig,
  enabled = true,
): number {
  const reduced = useReducedMotion();
  const cfg = { ...defaultSpringConfig(), ...config };

  const [value, setValue] = useState(() => (reduced ? target : initial));

  // Keep mutable state for the simulation loop so we don't re-subscribe on
  // every frame.
  const stateRef = useRef({
    value: reduced ? target : initial,
    velocity: 0,
    lastTarget: target,
  });

  // Snapshot the config into a ref so the rAF closure always reads fresh values.
  const cfgRef = useRef(cfg);
  cfgRef.current = cfg;

  useEffect(() => {
    if (reduced) {
      setValue(target);
      stateRef.current.value = target;
      stateRef.current.velocity = 0;
      stateRef.current.lastTarget = target;
      return;
    }

    // If we're not enabled, hold the current value.
    if (!enabled) return;

    stateRef.current.lastTarget = target;

    let rafId: number | undefined;
    let prevTime = performance.now();

    const tick = (now: number) => {
      const dt = Math.min((now - prevTime) / 1000, 0.032); // cap at ~30 fps delta
      prevTime = now;

      const s = stateRef.current;
      const c = cfgRef.current;
      const springForce = c.stiffness * (target - s.value);
      const dampingForce = -c.damping * s.velocity;
      const acceleration = (springForce + dampingForce) / c.mass;

      s.velocity += acceleration * dt;
      s.value += s.velocity * dt;

      // Settle check.
      if (
        Math.abs(target - s.value) < c.precision &&
        Math.abs(s.velocity) < c.precision
      ) {
        s.value = target;
        s.velocity = 0;
        setValue(target);
        return;
      }

      setValue(s.value);
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    // eslint-disable-next-line consistent-return
    return () => {
      if (rafId !== undefined) cancelAnimationFrame(rafId);
    };
  }, [target, reduced, enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  return value;
}

// ---------------------------------------------------------------------------
// useInView – IntersectionObserver wrapper
// ---------------------------------------------------------------------------

interface InViewOptions {
  rootMargin?: string;
  threshold?: number | number[];
  once?: boolean;
}

/**
 * Returns an IntersectionObserverEntry (or `null`) when the given ref enters
 * the viewport. When reduced motion is preferred the hook immediately returns
 * a partial entry with `isIntersecting: true` so consumers can reveal content
 * without waiting for a layout observation.
 */
export function useInView(
  ref: React.RefObject<Element | null>,
  options: InViewOptions = {},
): IntersectionObserverEntry | null {
  const reduced = useReducedMotion();
  const [entry, setEntry] = useState<IntersectionObserverEntry | null>(() => {
    if (reduced) return { isIntersecting: true } as IntersectionObserverEntry;
    return null;
  });

  useEffect(() => {
    if (reduced) return;
    const el = ref.current;
    if (!el) return;

    const { rootMargin = '0px', threshold = 0, once = false } = options;

    const observer = new IntersectionObserver(
      ([e]) => {
        setEntry(e);
        if (once && e.isIntersecting) observer.unobserve(el);
      },
      { rootMargin, threshold },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, reduced, options.rootMargin, options.threshold, options.once]);

  return entry;
}

// ---------------------------------------------------------------------------
// useStagger – sequential reveal for lists
// ---------------------------------------------------------------------------

interface StaggerOptions {
  /** Milliseconds between each item reveal (default: 50). */
  interval?: number;
  /** Initial delay before the first item (default: 0). */
  delay?: number;
}

/**
 * Returns a boolean array where `true` means the item at that index should be
 * visible / animated. Items are flipped `true` one-by-one at `interval` ms.
 * When reduced motion is preferred every item is immediately `true`.
 *
 * @param items  – the list/array whose length determines the number of phases
 * @param opts   – interval & delay tuning
 */
export function useStagger<T>(items: T[], opts: StaggerOptions = {}): boolean[] {
  const reduced = useReducedMotion();
  const { interval = 50, delay = 0 } = opts;

  const [revealed, setRevealed] = useState<number>(() => (reduced ? items.length : 0));

  useEffect(() => {
    if (reduced) {
      setRevealed(items.length);
      return;
    }

    // Reset when items change (e.g. list is re-sorted).
    setRevealed(0);

    const timerIds: ReturnType<typeof setTimeout>[] = [];

    const initialTimer = setTimeout(() => {
      if (items.length === 0) return;
      let index = 0;
      const scheduleNext = () => {
        const id = setTimeout(() => {
          index++;
          setRevealed(index);
          if (index < items.length) scheduleNext();
        }, interval);
        timerIds.push(id);
      };
      scheduleNext();
    }, delay);
    timerIds.push(initialTimer);

    return () => {
      timerIds.forEach(clearTimeout);
    };
  }, [items.length, interval, delay, reduced]); // eslint-disable-line react-hooks/exhaustive-deps

  return Array.from({ length: items.length }, (_, i) => i < revealed);
}

// ---------------------------------------------------------------------------
// useHover – tracked hover state with React-compatible handlers
// ---------------------------------------------------------------------------

interface HoverHandlers {
  onMouseEnter: React.MouseEventHandler;
  onMouseLeave: React.MouseEventHandler;
  onFocus: React.FocusEventHandler;
  onBlur: React.FocusEventHandler;
}

/**
 * Tracks whether an element is hovered (or focused). Returns a tuple of
 * `[isHovered, handlers]`. When reduced motion is preferred the hook always
 * returns `false` because hover-driven motion is skipped for accessibility.
 *
 * Usage:
 *   const [isHovered, hoverHandlers] = useHover();
 *   return <div {...hoverHandlers}>{isHovered ? 'hovered' : 'idle'}</div>;
 */
export function useHover(): [boolean, HoverHandlers] {
  const reduced = useReducedMotion();
  const [isHovered, setHovered] = useState(false);

  const handleEnter = useCallback<React.MouseEventHandler>(
    (_e) => {
      if (reduced) return;
      setHovered(true);
    },
    [reduced],
  );

  const handleLeave = useCallback<React.MouseEventHandler>(
    () => setHovered(false),
    [],
  );

  const handleFocus = useCallback<React.FocusEventHandler>(
    (_e) => {
      if (reduced) return;
      setHovered(true);
    },
    [reduced],
  );

  const handleBlur = useCallback<React.FocusEventHandler>(
    () => setHovered(false),
    [],
  );

  const handlers: HoverHandlers = {
    onMouseEnter: handleEnter,
    onMouseLeave: handleLeave,
    onFocus: handleFocus,
    onBlur: handleBlur,
  };

  return [isHovered, handlers];
}
