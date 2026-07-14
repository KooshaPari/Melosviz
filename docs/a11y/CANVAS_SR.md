# Canvas screen-reader text mirror (R3F / SceneView)

MelosViz renders music visualizations in a WebGL canvas. Assistive technology
cannot read pixels. `SceneView` (`web/src/r3fRenderer.tsx`) exposes a
**non-visual alternative** that mirrors deterministic scene state.

## Architecture

```
┌─────────────────────────────────────────────┐
│ role="img"  aria-label + aria-describedby   │
│  ┌─────────────────────────────────────┐    │
│  │ <canvas aria-hidden>  (WebGL)       │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
│ sr-only detail paragraph (full summary)     │
│ sr-only aria-live="polite" status           │
```

| Piece | File | Purpose |
|-------|------|---------|
| Summary builder | `web/src/utils/sceneSummary.ts` | Pure `buildSceneSummary({ spec, playbackT, sceneLabel })` |
| Announcer | `web/src/components/SceneSummary.tsx` | Renders detail + live region siblings |
| Mount | `web/src/r3fRenderer.tsx` | Wires wrapper, canvas, announcer |

## Determinism contract

Strings must **not** depend on:

- `performance.now()` or RAF elapsed time
- Random values or animation phase

They **may** depend on:

- `RenderSpec` keyframes (lerped at `playbackT`)
- `playbackT`, `durationSecs`, `bpm`, `key`, `beatTimes`
- Resolved `sceneLabel` from the shell

Unit tests: `web/src/test/sceneSummary.test.ts`.

The R3F golden fixture (`web/src/fixtures/r3fCanvasFixture.tsx`) still freezes
`performance.now()` for **pixels** only; the text mirror is stable without that
freeze.

## What screen readers hear

**Short label** (`aria-label` on the img wrapper):

> Melosviz visualization: Anthem, 42% through track

**Full description** (`aria-describedby`, on focus):

> Non-visual scene summary. Scene: Anthem. Playback position 42% (1:41 of 4:00).
> Tempo 128 beats per minute. Key C major. … Geometry: Torus knot mesh …

**Live region** (polite, on scene jump or seek):

> Scene Bridge. Playback 50%, 2:00 of 4:00. Tempo 128 BPM. …

Live text updates when `liveAnnouncement` changes (scene label or playhead
bucket). Continuous autoplay scrubbing does not spam announcements every frame.

## Verification

- `npm test --prefix web` — `sceneSummary.test.ts`
- Manual: Tab to visualization, verify describedby detail; jump scenes and
  confirm live region
- axe CI (`web/a11y/fixture.html`) unchanged — static fixture; SPA depth is
  covered by unit tests + manual SR checklist in `docs/a11y/FOCUS.md`

## Related gaps

- G-C09-01 (closed): baseline canvas SR wrapper
- W-329: deeper text mirror (this document + summary builder)
- C09 L83 residual: optional future work — haptic / sonification, not scorecard blockers
