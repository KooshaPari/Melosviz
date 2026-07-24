# MelosViz Motion Design

> Motion language for the MelosViz music-visualization studio — beat-driven, neon-drenched, accessible.

---

## 1. Easing Curves

Four canonical easings govern all UI and scene motion. Rooted in the brand's festival-neon character: **snappy on the leading edge, floaty on the tail** — never mechanical, never sluggish.

| Token | Curve | Character | Use |
|---|---|---|---|
| `mv-ease-snappy` | `cubic-bezier(0.05, 0.7, 0.1, 1.0)` | Quick ramp with soft overshoot | Press feedback, toast entry, toggle, knob snap |
| `mv-ease-out` | `cubic-bezier(0.0, 0.0, 0.2, 1.0)` | Decelerating settle | Panel open/close, tooltip, scene-transition camera dolly |
| `mv-ease-emphasis` | `cubic-bezier(0.34, 1.56, 0.64, 1.0)` | Springy overshoot | Hero reveal, pulse burst, beat-hit flash, badge pop |
| `mv-ease-beat` | `cubic-bezier(0.4, 0.0, 0.6, 1.0)` | Symmetric smooth | Continuous BPM-driven animation (torus scale, wave drift, shimmer sweep) |

---

## 2. Motion Tokens

Five tokens control duration and scale. Their values are scaled by `--mv-motion-reduce` (see §3) when the user requests reduced motion.

| Token | Normal | Reduced | Notes |
|---|---|---|---|
| `--mv-dur-instant` | `80ms` | `0ms` | Micro-interactions: hover dim, active press, ripple |
| `--mv-dur-fast` | `150ms` | `50ms` | Checkbox toggle, focus ring, knob snap, sidebar item select |
| `--mv-dur-base` | `250ms` | `80ms` | Panel reveal, button state, slider thumb, scene label crossfade |
| `--mv-dur-expressive` | `400ms` | `120ms` | Dialog open, preset-swap transition, mode switch, playlist drawer slide |
| `--mv-dur-entrance` | `600ms` | `150ms` | Splash dissolve, initial loading-skeleton shimmer, first-frame camera push-in |

**Common shorthand** — apply via the token alias in component CSS:

```css
/* Standard */
transition: opacity var(--mv-dur-fast) var(--mv-ease-out);
transform: translateY(0) scale(1);
transition: transform var(--mv-dur-base) var(--mv-ease-snappy);

/* Reduced motion — token values change, code stays same */
@media (prefers-reduced-motion: reduce) {
  :root {
    --mv-dur-base: 80ms;
    --mv-dur-expressive: 120ms;
  }
}
```

---

## 3. Accessibility Contract

Every animation in MelosViz must satisfy **all** of the following checks before shipping:

### 3.1 Reduced-motion compliance

- Respect `prefers-reduced-motion: reduce`. When active:
  - All `--mv-dur-*` tokens collapse to their Reduced column values above.
  - All `mv-ease-emphasis` curves flatten to `mv-ease-out`.
  - Continuous motion (BPM pulse, shimmer, wave drift) must have zero opacity or be replaced with a static frame.
  - Brand SVG animations (icon-animated, identity demo) must pause or freeze at the first frame.
- Test: `chrome://flags/#force-prefers-reduced-motion` or DevTools Rendering tab.

### 3.2 Flash-safety

- **No luminance flash > 3 Hz** in any UI element (buttons, panels, toasts).
- Audio-driven 3D-scene flashing is governed by the render-backend `apply_flash_safety()` limiter — but overlay UI (menus, cursors, labels) must never flash.
- Test: record 5 s of the interaction and verify no frame exceeds 50 % luminance delta from its neighbour.

### 3.3 No seizure-inducing patterns

- Striped rotating patterns, high-contrast strobes, and full-screen rapid alpha pulses are forbidden in UI chrome.
- The 3D scene may contain intense visual content (that is the product's purpose), but **no UI layer** may independently strobe.

### 3.4 Motion-distance constraint

- Elements must not travel more than 20 % of the viewport during any single animation.
- Exceptions: full-screen scene transitions (these fade to black first), playlist drawer slide (follows motion token duration).

### 3.5 Interaction-triggered motion only

- Do not animate on page load unless the animation conveys loading progress (skeleton shimmer, spinner) or is part of the splash screen (which the user dismisses).
- Every entrance animation must complete within `--mv-dur-entrance` and settle before the component is interactive.

---

## 4. Web / Desktop Parity Table

| Motion pattern | Web (React / CSS) | Desktop (Electron / same stack) | Gap? |
|---|---|---|---|
| Transition tokens | `var(--mv-dur-*)` + `var(--mv-ease-*)` | Same CSS custom properties | No gap |
| R3F scene animation | `useFrame` lerp with `mv-ease-beat` | Same `useFrame` — Three.js is cross-platform | No gap |
| Beat-pulse mesh | `BeatPulse.tsx` sine-scaled to BPM | Same component | No gap |
| Skeleton shimmer | Tailwind `animate-pulse` / CSS gradient sweep | Same class — Electron renders with Chromium | No gap |
| Icon-animated brand | SMIL `<animate>` in SVG | Same SVG — SMIL is engine-agnostic | No gap |
| Dialog / drawer slide | Radix `data-[state=open]` + CSS transition | Same Radix + CSS — no platform divergence | No gap |
| Loading spinner | `border-[3px] border-transparent border-t-current animate-spin` | Same Tailwind utility | No gap |
| CSS `transition` on hover/focus | Chromium CSS engine | Same Chromium CSS engine | No gap |
| `prefers-reduced-motion` | CSS media query | Same media query — Electron passes OS preference | No gap |
| `requestAnimationFrame` loop | Browser rAF | Chromium rAF — identical scheduling | No gap |
| 60 fps vs. 120 fps | Display refresh rate bound | Electron inherits OS refresh rate | No gap (both respect `requestAnimationFrame`) |
| Hardware acceleration | GPU compositor layer | Same GPU compositor — Electron uses GPU process | No gap |
| SVG SMIL pause | `document.pauseAnimations()` | Same DOM API via preload script | No gap (verify preload exposes document) |

**Verification protocol**: every motion pattern above must pass visual-inspection QA on both web (`bun run dev`) and desktop (`npm run electron:dev`) before a PR is marked ready.

---

*Canonical reference. Rev 1 — 2026-07-07.*
