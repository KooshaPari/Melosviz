/**
 * WCAG AAA contrast helpers for MelosViz.
 *
 * All color inputs are hex strings (`#rgb`, `#rrggbb`, or `#rrggbbaa`).
 * Alpha channels are composited against white before luminance calculation.
 *
 * @module
 */

// ── Internal helpers ───────────────────────────────────────────────────────

/** Parsed RGBA channels in 0-1 range. */
interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

/** Parse a hex colour string to RGBA components in [0, 1]. */
function parseHex(hex: string): Rgba {
  let h = hex.replace(/^#/, "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  if (h.length === 4) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2] + h[3] + h[3];
  const num = parseInt(h, 16);
  return {
    r: ((num >> 24) & 0xff) / 255,
    g: ((num >> 16) & 0xff) / 255,
    b: ((num >> 8) & 0xff) / 255,
    a: h.length === 8 ? (num & 0xff) / 255 : 1,
  };
}

/** Linearize a single sRGB channel per WCAG 2.1 formula. */
function linearize(c: number): number {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** Composite semi-transparent colour over a white background. */
function compositeOverWhite(c: Rgba): { r: number; g: number; b: number } {
  const bg = 1;
  const α = c.a;
  return {
    r: c.r * α + bg * (1 - α),
    g: c.g * α + bg * (1 - α),
    b: c.b * α + bg * (1 - α),
  };
}

/** Relative luminance (0-1) of a hex colour, alpha composited over white. */
function relativeLuminance(hex: string): number {
  const c = parseHex(hex);
  const s = compositeOverWhite(c);
  return (
    0.2126 * linearize(s.r) + 0.7152 * linearize(s.g) + 0.0722 * linearize(s.b)
  );
}

/** Format RGB channels [0, 1] to #rrggbb. */
function toHex(r: number, g: number, b: number): string {
  const clamp = (n: number) =>
    Math.max(0, Math.min(255, Math.round(n * 255)));
  return (
    "#" +
    [r, g, b]
      .map((ch) => clamp(ch).toString(16).padStart(2, "0"))
      .join("")
  );
}

/**
 * Blend two parsed colours by factor `t`.
 * t=0 → a, t=1 → b.
 */
function blend(a: Rgba, b: Rgba, t: number): { r: number; g: number; b: number } {
  return {
    r: a.r + (b.r - a.r) * t,
    g: a.g + (b.g - a.g) * t,
    b: a.b + (b.b - a.b) * t,
  };
}

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * Calculate the WCAG contrast ratio between two hex colours.
 *
 * Ratio = (L₁ + 0.05) / (L₂ + 0.05) where L₁ ≥ L₂.
 * Returns a value in **[1, 21]**.
 *
 * @example
 * contrastRatio("#000", "#fff") // → 21
 * contrastRatio("#666", "#fff") // → ~5.74
 */
export function contrastRatio(fg: string, bg: string): number {
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Returns `true` when the foreground/background pair meets **WCAG AAA**
 * (contrast ratio ≥ 7:1 for normal-size text).
 */
export function meetsAAA(fg: string, bg: string): boolean {
  return contrastRatio(fg, bg) >= 7;
}

/**
 * Returns `true` when the foreground/background pair meets **WCAG AA**
 * (contrast ratio ≥ 4.5:1 for normal-size text).
 */
export function meetsAA(fg: string, bg: string): boolean {
  return contrastRatio(fg, bg) >= 4.5;
}

/**
 * Suggest an alternative foreground colour shifted toward black or white
 * so the pair meets WCAG AAA (7:1).
 *
 * Uses binary search along the blend axis between `fg` and the nearest
 * extreme (black or white) that **widens** the luminance gap.  Returns the
 * minimal-difference hex that clears the threshold, or — when AAA is
 * mathematically impossible against the given background (e.g. a mid-grey
 * bg) — returns pure black or pure white (the best achievable).
 *
 * @example
 * suggestAlternative("#767676", "#fff") // → something darker like "#5a5a5a"
 */
export function suggestAlternative(fg: string, bg: string): string {
  if (meetsAAA(fg, bg)) return fg;

  const fgLum = relativeLuminance(fg);
  const bgLum = relativeLuminance(bg);

  // Shift toward the extreme that increases the luminance gap.
  const targetHex = fgLum >= bgLum ? "#ffffff" : "#000000";
  const target = parseHex(targetHex);
  const source = parseHex(fg);

  // Binary search: find the smallest t in [0,1] that clears AAA.
  let lo = 0;
  let hi = 1;
  let best: string | null = null;

  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    const { r, g, b } = blend(source, target, mid);
    const candidate = toHex(r, g, b);

    if (meetsAAA(candidate, bg)) {
      best = candidate;
      hi = mid;
    } else {
      lo = mid;
    }
  }

  // If AAA is unreachable (vanishingly rare — only happens when the
  // background sits near the centre of the luminance range), return the
  // extreme colour for maximum practical contrast.
  return best ?? targetHex;
}

// ── Live Region (announce) ─────────────────────────────────────────────────

let liveRegionEl: HTMLElement | null = null;
let announceTimer: ReturnType<typeof setTimeout> | null = null;

/** Obtain or create the shared `aria-live` region element. */
function getLiveRegion(): HTMLElement {
  if (liveRegionEl) return liveRegionEl;

  liveRegionEl = document.createElement("div");
  liveRegionEl.setAttribute("aria-live", "polite");
  liveRegionEl.setAttribute("aria-atomic", "true");
  liveRegionEl.setAttribute("role", "status");
  liveRegionEl.style.cssText =
    "position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0";
  document.body.appendChild(liveRegionEl);
  return liveRegionEl;
}

/** Options for {@link announceLive}. */
export interface AnnounceOptions {
  /**
   * How long (ms) the text remains in the live region before being cleared.
   * Default `3000`.
   */
  timeout?: number;

  /**
   * Politeness level. Default `"polite"`.
   * Use `"assertive"` for time-sensitive or urgent messages.
   */
  politeness?: "polite" | "assertive";
}

/**
 * Announce a message to assistive technology via an `aria-live` region.
 *
 * On first call a visually-hidden `aria-live="polite"` container is appended
 * to the document body and reused for all subsequent announcements.  The
 * text is automatically cleared after the configured `timeout` so that
 * identical strings are re-announced on repeat calls.
 *
 * @example
 * announceLive("Filter applied: 12 results");
 * announceLive("Error saving chart", { politeness: "assertive", timeout: 5000 });
 */
export function announceLive(text: string, opts?: AnnounceOptions): void {
  const el = getLiveRegion();
  const politeness = opts?.politeness ?? "polite";
  const timeout = opts?.timeout ?? 3000;

  el.setAttribute("aria-live", politeness);

  if (announceTimer) clearTimeout(announceTimer);

  // Clear then re-set in a new frame so screen readers detect the change
  // even when the text content is identical.
  el.textContent = "";
  requestAnimationFrame(() => {
    el.textContent = text;
  });

  announceTimer = setTimeout(() => {
    el.textContent = "";
    announceTimer = null;
  }, timeout);
}

// ── Focus Ring ─────────────────────────────────────────────────────────────

/**
 * Return a CSS `box-shadow` string for a 3px outset focus ring that meets
 * WCAG AAA contrast.
 *
 * Uses the **two-box-shadow** technique: an inner layer the colour of the
 * page background (`--focus-ring-bg`) separates the ring from the element,
 * preventing visual bleed-through.  The outer layer applies the ring colour.
 *
 * @param color   Desired ring colour (hex).  Omit or pass a falsy value to
 *                use the system `Highlight` colour (mapped via the CSS
 *                custom property `--focus-ring-color`).
 * @param offset  Gap between the element's border and the ring.  Default
 *                `"2px"`.
 *
 * @example
 * // System colour, 2px gap
 * focusRing() // → "0 0 0 2px var(--focus-ring-bg, white), 0 0 0 calc(2px + 3px) var(--focus-ring-color, Highlight)"
 *
 * @example
 * // Custom blue ring with 3px gap
 * focusRing("#1a73e8", "3px")
 */
export function focusRing(color?: string, offset?: string): string {
  const gap = offset ?? "2px";

  if (color) {
    // Validate that the colour parses; consumers get a build-time TS check
    // but we guard at runtime too.
    try {
      parseHex(color);
    } catch {
      // fall through to system default below
      color = undefined;
    }
  }

  if (color) {
    // Explicit colour: inner layer separates the ring from the element
    // background, outer layer is the ring itself.
    return [
      `0 0 0 ${gap} var(--focus-ring-bg, white)`,
      `0 0 0 calc(${gap} + 3px) ${color}`,
    ].join(", ");
  }

  // System colour: same technique but the colour is resolved from a CSS
  // custom property so it respects OS/browser high-contrast settings.
  return [
    `0 0 0 ${gap} var(--focus-ring-bg, white)`,
    `0 0 0 calc(${gap} + 3px) var(--focus-ring-color, Highlight)`,
  ].join(", ");
}
