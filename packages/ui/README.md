# `@melosviz/ui`

Shared MelosViz design-system **component** package (WBS-P3.2 / C10 L105).

Companion to the token package [`@melosviz/brand-tokens`](../brand-tokens):
that package ships the CSS variable source of truth
(`desktop/assets/brand/tokens.css`); this package ships the small set of
**real, already-in-app** React components built on top of those tokens, so
web no longer re-implements the same primitives ad hoc per surface.

## Scope (honest, not a full UI rebuild)

This is intentionally a **small, real surface** — not a from-scratch
component library. Each export below previously lived only under
`web/src/components/`; web now imports the shared version instead:

| Component | Purpose | Consumes |
|-----------|---------|----------|
| `Skeleton`, `SkeletonBlock` | Content-shaped loading placeholders (C10 L99) | `var(--mv-surface)` |
| `Button` | Focusable action control, `accent` \| `ghost` variants (C10 L105) | `var(--mv-primary)`-family Tailwind utility classes |
| `EmptyState` | Branded empty/zero-data wrapper: icon + gradient title + description + action + footnote (C10 L100/L105) | `var(--mv-grad-brand)` |

No component here forks a color/spacing/motion value — all visual
properties trace back to `desktop/assets/brand/tokens.css` via CSS custom
properties already loaded by the consuming app (`web/src/styles/brand.css`).

## Usage

```tsx
import { Button, EmptyState, Skeleton, SkeletonBlock } from '@melosviz/ui'
```

Consumers must already load the token stylesheet (web does this once in
`main.tsx` via `./styles/brand.css`, which `@import`s `@melosviz/brand-tokens`).
This package does not bundle or duplicate that CSS.

## Wiring

`web/package.json` depends on this package the same way it depends on
`@melosviz/brand-tokens`:

```json
"@melosviz/ui": "file:../packages/ui"
```

No build step: components are plain `.tsx` source consumed directly by
Vite/tsc (bundler module resolution), matching how `brand-tokens` is
consumed as source rather than a compiled artifact.

## Non-goals

- This does **not** replace desktop shell markup (HTML/CSS in
  `desktop/views/main/`) — desktop is out of scope for this package.
- This does **not** claim a full design-system rebuild of the web app;
  most feature-specific views (`WaveformDisplay`, `PresetEditor`,
  `SpecViewer`, …) remain app-local and are not forced into this package
  just to inflate surface area.
