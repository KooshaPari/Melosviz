// Canonical R3F scene-template definitions — mirrors backend scene_families.py.

export type SceneTemplateId =
  | 'wire_orb'
  | 'torus_flow'
  | 'crystal_burst'
  | 'ring_drift'
  | 'grid_depth'
  | 'octa_pulse'

export interface SceneMaterialProps {
  roughness: number
  metalness: number
  wireframe?: boolean
  emissiveScale: number
}

export interface SceneTemplate {
  id: SceneTemplateId
  displayName: string
  geometry: 'icosahedron' | 'torusKnot' | 'octahedronCluster' | 'torusRing' | 'gridPlane' | 'octahedron'
  geometryArgs: number[]
  material: SceneMaterialProps
  rotationSpeed: [number, number, number]
  /** Optional camera FOV override for this look. */
  fov?: number
}

export const SCENE_TEMPLATES: Record<SceneTemplateId, SceneTemplate> = {
  wire_orb: {
    id: 'wire_orb',
    displayName: 'Establishing',
    geometry: 'icosahedron',
    geometryArgs: [1.4, 2],
    material: { roughness: 0.85, metalness: 0.15, wireframe: true, emissiveScale: 0.25 },
    rotationSpeed: [0.08, 0.15, 0.04],
  },
  torus_flow: {
    id: 'torus_flow',
    displayName: 'Performance',
    geometry: 'torusKnot',
    geometryArgs: [1, 0.35, 128, 16],
    material: { roughness: 0.3, metalness: 0.7, emissiveScale: 0.4 },
    rotationSpeed: [0.3, 0.5, 0.1],
  },
  crystal_burst: {
    id: 'crystal_burst',
    displayName: 'Anthem',
    geometry: 'octahedronCluster',
    geometryArgs: [0.9, 5],
    material: { roughness: 0.15, metalness: 0.9, emissiveScale: 0.65 },
    rotationSpeed: [0.45, 0.7, 0.2],
    fov: 50,
  },
  ring_drift: {
    id: 'ring_drift',
    displayName: 'Interlude',
    geometry: 'torusRing',
    geometryArgs: [1.6, 0.08, 32, 64],
    material: { roughness: 0.6, metalness: 0.35, emissiveScale: 0.2 },
    rotationSpeed: [0.05, 0.12, 0.35],
  },
  grid_depth: {
    id: 'grid_depth',
    displayName: 'Horizon',
    geometry: 'gridPlane',
    geometryArgs: [12, 24],
    material: { roughness: 0.9, metalness: 0.1, wireframe: true, emissiveScale: 0.35 },
    rotationSpeed: [0, 0.08, 0],
    fov: 55,
  },
  octa_pulse: {
    id: 'octa_pulse',
    displayName: 'Pulse',
    geometry: 'octahedron',
    geometryArgs: [1.2, 0],
    material: { roughness: 0.2, metalness: 0.85, emissiveScale: 0.55 },
    rotationSpeed: [0.6, 0.9, 0.35],
    fov: 48,
  },
}

export function getSceneTemplate(id: string | undefined): SceneTemplate {
  const key = (id ?? 'torus_flow') as SceneTemplateId
  return SCENE_TEMPLATES[key] ?? SCENE_TEMPLATES.torus_flow
}

/** Preset → label→template map (client mirror of backend PRESET_SCENE_FAMILIES). */
export const PRESET_SCENE_FAMILIES: Record<string, Partial<Record<string, SceneTemplateId>>> = {
  dark_street: {
    intro: 'grid_depth',
    verse: 'torus_flow',
    chorus: 'crystal_burst',
    drop: 'octa_pulse',
    breakdown: 'wire_orb',
    outro: 'grid_depth',
  },
  classy: {
    intro: 'wire_orb',
    verse: 'ring_drift',
    chorus: 'torus_flow',
    drop: 'crystal_burst',
    breakdown: 'wire_orb',
    outro: 'ring_drift',
  },
  energetic: {
    intro: 'grid_depth',
    verse: 'torus_flow',
    chorus: 'octa_pulse',
    drop: 'crystal_burst',
    breakdown: 'ring_drift',
    outro: 'grid_depth',
  },
  ambient: {
    intro: 'ring_drift',
    verse: 'wire_orb',
    chorus: 'torus_flow',
    drop: 'crystal_burst',
    breakdown: 'ring_drift',
    outro: 'wire_orb',
  },
  chillout: {
    intro: 'ring_drift',
    verse: 'wire_orb',
    chorus: 'torus_flow',
    drop: 'torus_flow',
    breakdown: 'ring_drift',
    outro: 'wire_orb',
  },
  retro_disco: {
    intro: 'grid_depth',
    verse: 'torus_flow',
    chorus: 'octa_pulse',
    drop: 'crystal_burst',
    breakdown: 'wire_orb',
    outro: 'grid_depth',
  },
  urban: {
    intro: 'grid_depth',
    verse: 'octa_pulse',
    chorus: 'crystal_burst',
    drop: 'octa_pulse',
    breakdown: 'torus_flow',
    outro: 'grid_depth',
  },
  euphoria: {
    intro: 'wire_orb',
    verse: 'torus_flow',
    chorus: 'crystal_burst',
    drop: 'octa_pulse',
    breakdown: 'ring_drift',
    outro: 'wire_orb',
  },
  cinematic: {
    intro: 'wire_orb',
    verse: 'grid_depth',
    chorus: 'crystal_burst',
    drop: 'octa_pulse',
    breakdown: 'ring_drift',
    outro: 'wire_orb',
  },
  synthwave: {
    intro: 'grid_depth',
    verse: 'torus_flow',
    chorus: 'octa_pulse',
    drop: 'crystal_burst',
    breakdown: 'wire_orb',
    outro: 'grid_depth',
  },
  lofi: {
    intro: 'ring_drift',
    verse: 'wire_orb',
    chorus: 'torus_flow',
    drop: 'torus_flow',
    breakdown: 'wire_orb',
    outro: 'ring_drift',
  },
  minimal: {
    intro: 'wire_orb',
    verse: 'ring_drift',
    chorus: 'torus_flow',
    drop: 'crystal_burst',
    breakdown: 'wire_orb',
    outro: 'wire_orb',
  },
}
