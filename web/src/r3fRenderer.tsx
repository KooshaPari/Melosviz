// Three.js / React Three Fiber scene-graph renderer for melosviz.
//
// Replaces the vanilla WebGL2 rotating-quad renderer with a proper
// scene-graph that accepts SceneParams from the data-binding seam
// (renderSpec.ts) and drives camera/color/geometry per-frame.
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
//   D — replace linear lerp in renderSpec with spline easing

import { useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { SceneParams } from './renderSpec'

// ---- Internal: camera controller ----------------------------------------

interface SceneCameraProps {
  paramsRef: React.RefObject<SceneParams>
}

function SceneCamera({ paramsRef }: SceneCameraProps) {
  const { camera } = useThree()

  useFrame(() => {
    const p = paramsRef.current
    if (!p) return
    const { distance, azimuth, elevation } = p.camera

    // Spherical → Cartesian (Three.js Y-up)
    const x = distance * Math.cos(elevation) * Math.sin(azimuth)
    const y = distance * Math.sin(elevation)
    const z = distance * Math.cos(elevation) * Math.cos(azimuth)

    camera.position.set(x, y, z)
    camera.lookAt(0, 0, 0)
  })

  return null
}

// ---- Internal: background color -----------------------------------------

interface SceneBackgroundProps {
  paramsRef: React.RefObject<SceneParams>
}

function SceneBackground({ paramsRef }: SceneBackgroundProps) {
  const { scene } = useThree()
  const colorRef = useRef(new THREE.Color())

  useFrame(() => {
    const p = paramsRef.current
    if (!p) return
    const { brightness } = p.color
    // Festival-screen friendly: dark background tinted with the primary palette
    colorRef.current.set(p.color.primary)
    // Scale brightness down so the bg reads as dark (0.05–0.15 range)
    colorRef.current.multiplyScalar(Math.min(0.2, brightness * 0.15))
    scene.background = colorRef.current.clone()
  })

  return null
}

// ---- Internal: ambient + accent lighting --------------------------------

interface SceneLightsProps {
  paramsRef: React.RefObject<SceneParams>
}

function SceneLights({ paramsRef }: SceneLightsProps) {
  const ambientRef = useRef<THREE.AmbientLight>(null)
  const pointRef = useRef<THREE.PointLight>(null)

  useFrame(() => {
    const p = paramsRef.current
    if (!p) return

    if (ambientRef.current) {
      ambientRef.current.intensity = 0.3 + p.color.brightness * 0.4
    }
    if (pointRef.current) {
      pointRef.current.color.set(p.color.secondary)
      pointRef.current.intensity = 1.5 + p.beatEnergy * 3
    }
  })

  return (
    <>
      <ambientLight ref={ambientRef} intensity={0.5} />
      <pointLight ref={pointRef} position={[5, 5, 5]} intensity={1.5} />
    </>
  )
}

// ---- Internal: primary geometry driven by params -------------------------

interface CoreMeshProps {
  paramsRef: React.RefObject<SceneParams>
}

function CoreMesh({ paramsRef }: CoreMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const matRef = useRef<THREE.MeshStandardMaterial>(null)

  useFrame((_state, delta) => {
    const p = paramsRef.current
    const mesh = meshRef.current
    const mat = matRef.current
    if (!p || !mesh || !mat) return

    // Slow base rotation; beat energy adds a brief kick
    mesh.rotation.x += delta * 0.3
    mesh.rotation.y += delta * (0.5 + p.beatEnergy * 2)

    mat.color.set(p.color.primary)
    mat.emissive.set(p.color.secondary)
    mat.emissiveIntensity = 0.1 + p.color.brightness * 0.3 + p.beatEnergy * 0.5
  })

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1.2, 1]} />
      <meshStandardMaterial
        ref={matRef}
        color="#7c3aed"
        emissive="#06b6d4"
        emissiveIntensity={0.2}
        roughness={0.4}
        metalness={0.6}
      />
    </mesh>
  )
}

// ---- Internal: full scene wiring ----------------------------------------

interface MelosSceneProps {
  paramsRef: React.RefObject<SceneParams>
}

function MelosScene({ paramsRef }: MelosSceneProps) {
  return (
    <>
      <SceneBackground paramsRef={paramsRef} />
      <SceneCamera paramsRef={paramsRef} />
      <SceneLights paramsRef={paramsRef} />
      <CoreMesh paramsRef={paramsRef} />
    </>
  )
}

// ---- Public: SceneView --------------------------------------------------

export interface SceneViewProps {
  /** Live per-frame scene parameters from the data-binding seam. */
  params: SceneParams
  className?: string
}

/**
 * SceneView mounts the R3F Canvas and wires SceneParams into the scene graph.
 *
 * Usage:
 *   const params = specToSceneParams(spec, audioTimeSecs)
 *   <SceneView params={params} className="absolute inset-0 w-full h-full" />
 */
export function SceneView({ params, className }: SceneViewProps) {
  // Use a ref so useFrame callbacks read the latest params without triggering
  // React re-renders on every animation frame — critical for 60fps.
  const paramsRef = useRef<SceneParams>(params)
  paramsRef.current = params

  return (
    <Canvas
      className={className}
      gl={{
        antialias: true,
        powerPreference: 'high-performance',
        // Festival screens are often HDR-capable; linear encoding is correct
        // for physically-based materials.
        outputColorSpace: THREE.LinearSRGBColorSpace,
      }}
      dpr={[1, window.devicePixelRatio ?? 2]}
      camera={{ fov: 45, near: 0.1, far: 500, position: [0, 0, 5] }}
      style={{ background: '#080808' }}
    >
      <MelosScene paramsRef={paramsRef} />
    </Canvas>
  )
}
