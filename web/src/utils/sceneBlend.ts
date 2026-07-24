// Scene-boundary blend resolution for multi-scene crossfades.

import type { Keyframe, RenderSpec } from './renderSpec'
import { lerpKeyframe, type InterpolatedFrame } from './interpolate'
import type { SceneTemplateId } from './sceneTemplates'

export interface SceneBlendState {
  fromTemplate: SceneTemplateId
  toTemplate: SceneTemplateId
  /** 0 = fully ``fromTemplate``, 1 = fully ``toTemplate``. */
  blend: number
  frame: InterpolatedFrame
  sceneLabel: string
}

function sortedKeyframes(keyframes: Keyframe[]): Keyframe[] {
  return [...keyframes].sort((a, b) => a.t - b.t)
}

/**
 * Resolve which scene templates are active and the crossfade blend at ``playbackT``.
 */
export function resolveSceneBlend(spec: RenderSpec, playbackT: number): SceneBlendState {
  const clamped = Math.min(1, Math.max(0, playbackT))
  const frame = lerpKeyframe(spec.keyframes, clamped)
  const kfs = sortedKeyframes(spec.keyframes)

  if (kfs.length === 0) {
    return {
      fromTemplate: 'torus_flow',
      toTemplate: 'torus_flow',
      blend: 0,
      frame,
      sceneLabel: 'Scene',
    }
  }

  if (kfs.length === 1) {
    const only = kfs[0]!
    return {
      fromTemplate: (only.scene_template ?? 'torus_flow') as SceneTemplateId,
      toTemplate: (only.scene_template ?? 'torus_flow') as SceneTemplateId,
      blend: 0,
      frame,
      sceneLabel: only.scene ?? 'Scene',
    }
  }

  let idx = 0
  for (let i = 0; i < kfs.length - 1; i++) {
    if (clamped >= kfs[i]!.t && clamped <= kfs[i + 1]!.t) {
      idx = i
      break
    }
    if (clamped > kfs[i + 1]!.t) idx = i + 1
  }

  const current = kfs[idx]!
  const next = kfs[Math.min(idx + 1, kfs.length - 1)]!
  const fromTemplate = (current.scene_template ?? 'torus_flow') as SceneTemplateId
  const toTemplate = (next.scene_template ?? fromTemplate) as SceneTemplateId

  if (fromTemplate === toTemplate || next.t <= current.t) {
    return {
      fromTemplate,
      toTemplate,
      blend: 0,
      frame,
      sceneLabel: current.scene ?? 'Scene',
    }
  }

  const transitionNorm = Math.min(
    0.35,
    (current.transition_secs ?? spec.durationSecs * (spec.transitionFraction ?? 0.12)) /
      Math.max(spec.durationSecs, 0.001),
  )
  const boundary = next.t
  const windowStart = boundary - transitionNorm

  let blend = 0
  if (clamped >= windowStart && transitionNorm > 1e-6) {
    blend = Math.min(1, (clamped - windowStart) / transitionNorm)
  }

  const sceneLabel =
    blend > 0.5 ? (next.scene ?? sceneLabelFromTemplate(toTemplate)) : (current.scene ?? sceneLabelFromTemplate(fromTemplate))

  return { fromTemplate, toTemplate, blend, frame, sceneLabel }
}

function sceneLabelFromTemplate(id: SceneTemplateId): string {
  const names: Record<SceneTemplateId, string> = {
    wire_orb: 'Establishing',
    torus_flow: 'Performance',
    crystal_burst: 'Anthem',
    ring_drift: 'Interlude',
    grid_depth: 'Horizon',
    octa_pulse: 'Pulse',
  }
  return names[id] ?? 'Scene'
}
