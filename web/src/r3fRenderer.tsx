import { useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { RenderSpec } from './renderSpec'
import { BeatPulse } from './components/BeatPulse'
import { getSceneTemplate, type SceneTemplate, type SceneTemplateId } from './sceneTemplates'
import { resolveSceneBlend, type SceneBlendState } from './utils/sceneBlend'

// ---- Internal: per-frame state ref -----------------------------------------

interface FrameState {
  blend: SceneBlendState
  bpm: number
  elapsedSecs: number
  beatTimes: number[]
  playbackT: number
  durationSecs: number
}

// ---- Internal: camera controller -------------------------------------------

function SceneCamera({ stateRef }: { stateRef: React.RefObject<FrameState> }) {
  const { camera } = useThree()

  useFrame(() => {
    const s = stateRef.current
    if (!s) return
    const { distance, azimuth, elevation } = s.blend.frame.camera

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
    const { brightness, primary } = s.blend.frame.color
    colorRef.current.set(primary)
    colorRef.current.multiplyScalar(Math.min(0.25, brightness * 0.18))
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
      ambientRef.current.intensity = 0.25 + s.blend.frame.color.brightness * 0.45
    }
    if (pointRef.current) {
      pointRef.current.color.set(s.blend.frame.color.secondary)
      const beatPhase = (s.elapsedSecs * s.bpm) / 60
      pointRef.current.intensity = 1.2 + 0.9 * Math.abs(Math.sin(Math.PI * beatPhase))
    }
  })

  return (
    <>
      <ambientLight ref={ambientRef} intensity={0.5} />
      <pointLight ref={pointRef} position={[5, 5, 5]} intensity={1.5} />
    </>
  )
}

// ---- Internal: template-specific geometry ----------------------------------

function TemplateGeometry({ template }: { template: SceneTemplate }) {
  switch (template.geometry) {
    case 'icosahedron':
      return <icosahedronGeometry args={template.geometryArgs as [number, number]} />
    case 'torusKnot':
      return (
        <torusKnotGeometry
          args={template.geometryArgs as [number, number, number, number]}
        />
      )
    case 'octahedron':
      return <octahedronGeometry args={template.geometryArgs as [number, number]} />
    case 'torusRing':
      return (
        <torusGeometry args={template.geometryArgs as [number, number, number, number]} />
      )
    case 'gridPlane':
      return (
        <planeGeometry args={[template.geometryArgs[0] ?? 12, template.geometryArgs[1] ?? 24, 1, 1]} />
      )
    case 'octahedronCluster':
      return <OctahedronCluster count={template.geometryArgs[1] ?? 5} radius={template.geometryArgs[0] ?? 0.9} />
    default:
      return <boxGeometry args={[1, 1, 1]} />
  }
}

function OctahedronCluster({ count, radius }: { count: number; radius: number }) {
  const meshes = Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2
    const r = radius * 0.55
    return (
      <mesh key={i} position={[Math.cos(angle) * r, Math.sin(angle * 0.5) * 0.4, Math.sin(angle) * r]}>
        <octahedronGeometry args={[radius * 0.35, 0]} />
      </mesh>
    )
  })
  return <group>{meshes}</group>
}

function SceneLayer({
  templateId,
  opacity,
  stateRef,
}: {
  templateId: SceneTemplateId
  opacity: number
  stateRef: React.RefObject<FrameState>
}) {
  const rootRef = useRef<THREE.Group>(null)
  const matRef = useRef<THREE.MeshStandardMaterial>(null)
  const template = getSceneTemplate(templateId)

  useFrame((_state, delta) => {
    const s = stateRef.current
    const root = rootRef.current
    const mat = matRef.current
    if (!s || !root) return

    const [rx, ry, rz] = template.rotationSpeed
    root.rotation.x += delta * rx
    root.rotation.y += delta * ry
    root.rotation.z += delta * rz

    const beatPhase = (s.elapsedSecs * s.bpm) / 60
    const pulse = 0.88 + 0.12 * Math.abs(Math.sin(Math.PI * beatPhase))
    const base = 0.75 + s.blend.frame.color.brightness * 0.45
    root.scale.setScalar(base * pulse)

    if (mat) {
      mat.color.set(s.blend.frame.color.primary)
      mat.emissive.set(s.blend.frame.color.primary)
      mat.emissiveIntensity =
        template.material.emissiveScale * (0.3 + s.blend.frame.color.brightness * 0.7)
      mat.opacity = opacity
      mat.transparent = opacity < 0.999
    }
  })

  if (opacity < 0.01) return null

  if (template.geometry === 'octahedronCluster') {
    return (
      <group ref={rootRef}>
        <OctahedronCluster
          count={template.geometryArgs[1] ?? 5}
          radius={template.geometryArgs[0] ?? 0.9}
        />
      </group>
    )
  }

  if (template.geometry === 'gridPlane') {
    return (
      <group ref={rootRef} rotation={[-Math.PI / 2.2, 0, 0]} position={[0, -1.2, -2]}>
        <mesh>
          <planeGeometry args={[template.geometryArgs[0] ?? 12, template.geometryArgs[1] ?? 24]} />
          <meshStandardMaterial
            ref={matRef}
            color="#22d3ee"
            emissive="#22d3ee"
            emissiveIntensity={0.2}
            wireframe
            roughness={0.9}
            metalness={0.1}
            transparent
            opacity={opacity}
          />
        </mesh>
      </group>
    )
  }

  return (
    <group ref={rootRef}>
      <mesh>
        <TemplateGeometry template={template} />
        <meshStandardMaterial
          ref={matRef}
          color="#7c6af7"
          emissive="#7c6af7"
          emissiveIntensity={0.2}
          roughness={template.material.roughness}
          metalness={template.material.metalness}
          wireframe={template.material.wireframe ?? false}
          transparent
          opacity={opacity}
        />
      </mesh>
    </group>
  )
}

// ---- Internal: dual-layer crossfade ----------------------------------------

function MultiSceneLayers({ stateRef }: { stateRef: React.RefObject<FrameState> }) {
  const s = stateRef.current
  const blend = s.blend.blend
  return (
    <>
      <SceneLayer
        templateId={s.blend.fromTemplate}
        opacity={1 - blend}
        stateRef={stateRef}
      />
      <SceneLayer templateId={s.blend.toTemplate} opacity={blend} stateRef={stateRef} />
    </>
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
      <MultiSceneLayers stateRef={stateRef} />
    </>
  )
}

// ---- Public: SceneView -----------------------------------------------------

export interface SceneViewProps {
  spec: RenderSpec
  playbackT: number
  beatEnergy?: number
  className?: string
  currentSceneLabel?: string
  frameloop?: 'always' | 'demand'
}

export function SceneView({
  spec,
  playbackT,
  className,
  currentSceneLabel,
  frameloop = 'always',
}: SceneViewProps) {
  const blend = resolveSceneBlend(spec, playbackT)

  const stateRef = useRef<FrameState>({
    blend,
    bpm: spec.bpm ?? 120,
    elapsedSecs: 0,
    beatTimes: spec.beatTimes ?? [],
    playbackT,
    durationSecs: spec.durationSecs,
  })

  stateRef.current = {
    blend: resolveSceneBlend(spec, playbackT),
    bpm: spec.bpm ?? 120,
    elapsedSecs: performance.now() / 1000,
    beatTimes: spec.beatTimes ?? [],
    playbackT,
    durationSecs: spec.durationSecs,
  }

  const sceneLabel = currentSceneLabel?.trim() || blend.sceneLabel || 'Scene'

  return (
    <div className={className}>
      <div
        className="h-full w-full"
        role="img"
        aria-label={sceneSummary.imgLabel}
        aria-describedby={summaryDetailId}
      >
        <Canvas
          className="h-full w-full"
          frameloop={frameloop}
          gl={{
            antialias: true,
            powerPreference: 'high-performance',
            outputColorSpace: THREE.LinearSRGBColorSpace,
            preserveDrawingBuffer: frameloop === 'demand',
          }}
          dpr={[1, window.devicePixelRatio ?? 2]}
          camera={{ fov: 45, near: 0.1, far: 500, position: [0, 0, 8] }}
          style={{ background: '#080808' }}
          aria-hidden
        >
          <MelosScene stateRef={stateRef} />
        </Canvas>
      </div>
      <SceneSummaryAnnouncer
        summary={sceneSummary}
        detailId={summaryDetailId}
      />
    </div>
  )
}
