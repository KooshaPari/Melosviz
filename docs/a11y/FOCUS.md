# Focus choreography contract

Applies to desktop shell (`desktop/views/main/index.html`) and web a11y fixture.

## Rules

1. **Skip link** — first focusable control is “Skip to main content” → `#main`.
2. **Focus ring** — interactive controls use `:focus-visible` with
   `outline: 3px solid var(--mv-neon-cyan / #22d3ee); outline-offset: 2px`.
3. **Tab order** — titlebar → pipeline actions → inspector → status; no
   positive `tabindex` except skip target.
4. **Modals / errors** — error dismiss button remains in tab order when visible.
5. **Reduced motion** — focus rings stay; animations collapse (see tokens).

## Verification

- Manual: Tab from cold start; skip link appears; Enter lands in `#main`.
- Automated: axe `wcag2a,wcag2aa` on fixture (includes focusable controls).
