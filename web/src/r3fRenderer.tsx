// Three.js / React Three Fiber scene-graph renderer for melosviz.
//
// Accepts a RenderSpec + normalised playbackT [0-1] and drives:
//   - Camera position  (spherical → Cartesian from keyframe.camera)
//   - Background color (tinted from keyframe.color.primary)
//   - Mesh emissive    (keyframe.color.primary)
//   - Mesh scale pulse (bpm-rate sine from keyframe.color.brightness)
//
// Architecture:
//   SceneView (public, exported)   — R3F <Canvas> mount + resize observer
//   MelosScene (internal)          — useFrame loop reading SceneParams
//   SceneBackground (internal)     — background color/brightness driven by params
//   SceneCamera (internal)         — camera position driven by params
//
// Workstream plug-in points (future):
//   A — pass spectral FFT → SpectralMesh inside MelosScene
//   B — pass beatEnergy → ParticleSystem inside MelosScene
//   D — replace lerpKeyframe linear lerp with spline easing

import { useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { RenderSpec } from './renderSpec'
import { lerpKeyframe } from './utils/interpolate'
import type { InterpolatedFrame } from './utils/interpolate'
import { BeatPulse } from './components/BeatPulse'

// ---- Internal: per-frame state ref -----------------------------------------

interface FrameState {
  frame: InterpolatedFrame
  bpm: number
  /** Elapsed wall-clock seconds — used for bpm pulse independent of playbackT. */
  elapsedSecs: number
  /** Beat onset times (seconds) from RenderSpec. */
  beatTimes: number[]
  /** Normalised playhead position [0, 1]. */
  playbackT: number
  /** Track duration in seconds. */
  durationSecs: number
}

// ---- Internal: camera controller -------------------------------------------

function SceneCamera({ stateRef }: { stateRef: React.RefObject<FrameState> }) {
  const { camera } = useThree()

  useFrame(() => {
    const s = stateRef.current
    if (!s) return
    const { distance, azimuth, elevation } = s.frame.camera

    // Spherical → Cartesian (Three.js Y-up)
    camera.position.set(
      distance * Math.cos(elevation) * Math.sin(azimuth),
      distance * Math.sin(elevation),
      distance * Math.cos(elevation) * Math.cos(azimuth),
    )
    camera.lookAt(0, 0, 0)
  })

  return null
}

// ---- Internal: background color --------------------------------------------

function SceneBackground({ stateRef }: { stateRef: React.RefObject<FrameState> }) {
  const { scene } = useThree()
  const colorRef = useRef(new THREE.Color())

  useFrame(() => {
    const s = stateRef.current
    if (!s) return
    const { brightness } = s.frame.color
    // Dark festival background tinted by primary palette
    colorRef.current.set(s.frame.color.primary)
    colorRef.current.multiplyScalar(Math.min(0.2, brightness * 0.15))
    scene.background = colorRef.current.clone()
  })

  return null
}

// ---- Internal: ambient + accent lighting -----------------------------------

function SceneLights({ stateRef }: { stateRef: React.RefObject<FrameState> }) {
  const ambientRef = useRef<THREE.AmbientLight>(null)
  const pointRef = useRef<THREE.PointLight>(null)

  useFrame(() => {
    const s = stateRef.current
    if (!s) return

    if (ambientRef.current) {
      ambientRef.current.intensity = 0.3 + s.frame.color.brightness * 0.4
    }
    if (pointRef.current) {
      pointRef.current.color.set(s.frame.color.secondary)
      // Subtle beat-locked accent brightness via bpm sine
      const beatPhase = (s.elapsedSecs * s.bpm) / 60
      pointRef.current.intensity = 1.5 + 0.8 * Math.abs(Math.sin(Math.PI * beatPhase))
    }
  })

  return (
    <>
      <ambientLight ref={ambientRef} intensity={0.5} />
      <pointLight ref={pointRef} position={[5, 5, 5]} intensity={1.5} />
    </>
  )
}

// ---- Internal: primary geometry driven by frame state ----------------------

function CoreMesh({ stateRef }: { stateRef: React.RefObject<FrameState> }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const matRef = useRef<THREE.MeshStandardMaterial>(null)

  useFrame((_state, delta) => {
    const s = stateRef.current
    const mesh = meshRef.current
    const mat = matRef.current
    if (!s || !mesh || !mat) return

    // Slow base rotation
    mesh.rotation.x += delta * 0.3
    mesh.rotation.y += delta * 0.5

    // BPM-rate scale pulse: subtle ±10% pulse per beat
    const beatPhase = (s.elapsedSecs * s.bpm) / 60
    const pulse = 0.9 + 0.1 * Math.abs(Math.sin(Math.PI * beatPhase))
    const base = 0.8 + s.frame.color.brightness * 0.4
    mesh.scale.setScalar(base * pulse)

    // Color morphs from keyframe interpolation
    mat.color.set(s.frame.color.primary)
    mat.emissive.set(s.frame.color.primary)
    mat.emissiveIntensity = 0.15 + s.frame.color.brightness * 0.4
  })

  return (
    <mesh ref={meshRef}>
      <torusKnotGeometry args={[1, 0.35, 128, 16]} />
      <meshStandardMaterial
        ref={matRef}
        color="#7c6af7"
        emissive="#7c6af7"
        emissiveIntensity={0.2}
        roughness={0.3}
        metalness={0.7}
      />
    </mesh>
  )
}

// ---- Internal: full scene wiring -------------------------------------------

function MelosScene({ stateRef }: { stateRef: React.RefObject<FrameState> }) {
  const s = stateRef.current
  return (
    <>
      <SceneBackground stateRef={stateRef} />
      <SceneCamera stateRef={stateRef} />
      <SceneLights stateRef={stateRef} />
      {s.beatTimes.length > 0 && (
        <BeatPulse
          beatTimes={s.beatTimes}
          playbackT={s.playbackT}
          durationSecs={s.durationSecs}
        />
      )}
      <CoreMesh stateRef={stateRef} />
    </>
  )
}

// ---- Public: SceneView -----------------------------------------------------

export interface SceneViewProps {
  /**
   * The full RenderSpec produced by spec_builder.py (or the placeholder).
   * Keyframe interpolation happens inside SceneView so consumers only need
   * to track a single normalised position.
   */
  spec: RenderSpec
  /**
   * Normalised playhead position in [0, 1].
   * 0 = start of track, 1 = end of track.
   */
  playbackT: number
  /** Optional beat energy [0, 1] — defaults to 0 until workstream B lands. */
  beatEnergy?: number
  className?: string
}

/**
 * SceneView mounts the R3F Canvas and drives the scene from `spec` keyframes
 * interpolated at `playbackT`.
 *
 * Usage:
 *   <SceneView spec={renderSpec} playbackT={0.42} className="absolute inset-0" />
 */
export function SceneView({ spec, playbackT, className }: SceneViewProps) {
  // Store derived per-frame state in a ref so useFrame callbacks never trigger
  // React re-renders — critical for 60fps.
  const stateRef = useRef<FrameState>({
    frame: lerpKeyframe(spec.keyframes, playbackT),
    bpm: spec.bpm ?? 120,
    elapsedSecs: 0,
    beatTimes: spec.beatTimes ?? [],
    playbackT,
    durationSecs: spec.durationSecs,
  })

  // Keep ref current every render (no useEffect needed — synchronous update)
  stateRef.current = {
    frame: lerpKeyframe(spec.keyframes, playbackT),
    bpm: spec.bpm ?? 120,
    elapsedSecs: performance.now() / 1000,
    beatTimes: spec.beatTimes ?? [],
    playbackT,
    durationSecs: spec.durationSecs,
  }

  return (
    <Canvas
      className={className}
      gl={{
        antialias: true,
        powerPreference: 'high-performance',
        outputColorSpace: THREE.LinearSRGBColorSpace,
      }}
      dpr={[1, window.devicePixelRatio ?? 2]}
      camera={{ fov: 45, near: 0.1, far: 500, position: [0, 0, 8] }}
      style={{ background: '#080808' }}
    >
      <MelosScene stateRef={stateRef} />
    </Canvas>
  )
}
