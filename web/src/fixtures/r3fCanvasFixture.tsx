// Deterministic R3F canvas golden-screenshot fixture (G-C10-03 / WBS-P3.3).
//
// Mounts SceneView with a fixed RenderSpec + fixed playbackT, frameloop
// "demand", and a frozen `performance.now()` so the CoreMesh/light pulse
// (driven by wall-clock time in r3fRenderer.tsx) always renders the exact
// same frame. This avoids screenshotting the live App (no audio, no
// requestAnimationFrame drift) — see docs/VISUAL_SPEC.md + docs/visual/PROVENANCE.md.
import { createRoot } from 'react-dom/client'
import { SceneView } from '../r3fRenderer'
import type { RenderSpec } from '../renderSpec'

// Freeze the clock the CoreMesh rotation + beat-pulse lighting read from
// (stateRef.elapsedSecs = performance.now() / 1000; THREE.Clock deltas also
// derive from performance.now()) so repeated CI runs render pixel-identical
// output regardless of when the page happened to load.
const FIXED_NOW_MS = 1_000
performance.now = () => FIXED_NOW_MS

const FIXTURE_SPEC: RenderSpec = {
  durationSecs: 240,
  bpm: 128,
  beatTimes: [],
  keyframes: [
    {
      t: 0,
      scene: 'Anthem (fixture)',
      camera: { distance: 4, azimuth: -0.3, elevation: 0.3 },
      color: { primary: '#f97316', secondary: '#a3e635', brightness: 1.0 },
    },
  ],
}

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('[melosviz] r3f-canvas fixture mount point #root not found')
}

createRoot(rootEl).render(
  <SceneView
    spec={FIXTURE_SPEC}
    playbackT={0}
    currentSceneLabel="Anthem (fixture)"
    frameloop="demand"
    className="h-full w-full"
  />,
)

// R3F sizes the <canvas> element from a ResizeObserver on its container,
// which lands a frame or two after mount — with frameloop="demand" the
// canvas only repaints once `invalidate()` runs off that resize. Poll for
// the fixture's fixed 960x540 backing-store size (not just DOM presence)
// before flipping the ready flag Playwright's --wait-for-selector waits on,
// otherwise the screenshot can race a still-300x150 default canvas.
const FIXTURE_WIDTH = 960
const FIXTURE_HEIGHT = 540

function waitForCanvasSize(onReady: () => void): void {
  const check = () => {
    const canvas = document.querySelector('canvas')
    if (canvas && canvas.width === FIXTURE_WIDTH && canvas.height === FIXTURE_HEIGHT) {
      // One extra frame so the resized canvas has actually painted.
      requestAnimationFrame(() => requestAnimationFrame(onReady))
      return
    }
    requestAnimationFrame(check)
  }
  requestAnimationFrame(check)
}

waitForCanvasSize(() => {
  document.body.setAttribute('data-fixture-ready', 'true')
})
