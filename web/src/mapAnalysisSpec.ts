// Map backend RenderSpec v2 JSON → canonical web RenderSpec.

import type { Keyframe, RenderSpec, SceneSegment } from "./renderSpec";
import {
  getSceneTemplate,
  PRESET_SCENE_FAMILIES,
  type SceneTemplateId,
} from "./sceneTemplates";

export interface RawAnalysisSpec {
  durationSecs?: number;
  duration_sec?: number;
  bpm?: number;
  key?: string;
  keyframes?: Keyframe[];
  beat_times?: number[];
  beatTimes?: number[];
  scene_segments?: SceneSegment[];
  sceneSegments?: SceneSegment[];
  palette?: string[];
  metadata?: {
    duration?: number;
    preset?: string;
    transition_fraction?: number;
  };
  mir?: { tempo_bpm?: number; key?: string; mode?: string };
  [key: string]: unknown;
}

function durationFromRaw(raw: RawAnalysisSpec): number {
  const meta = raw.metadata ?? {};
  return (
    raw.durationSecs ??
    raw.duration_sec ??
    (meta.duration as number | undefined) ??
    240
  );
}

function beatTimesFromRaw(raw: RawAnalysisSpec): number[] {
  if (Array.isArray(raw.beat_times)) return raw.beat_times;
  if (Array.isArray(raw.beatTimes)) return raw.beatTimes;
  const events = raw.timeline_events as
    Array<{ t?: number; type?: string }> | undefined;
  if (events) {
    return events.filter((e) => e.type === "beat").map((e) => Number(e.t ?? 0));
  }
  return [];
}

function keyFromRaw(raw: RawAnalysisSpec): string | undefined {
  if (raw.key) return String(raw.key);
  const mir = raw.mir;
  if (mir?.key && mir?.mode) return `${mir.key} ${mir.mode}`;
  return mir?.key;
}

/** Convert analyze endpoint JSON into the web RenderSpec contract. */
export function mapAnalysisToRenderSpec(raw: RawAnalysisSpec): RenderSpec {
  const durationSecs = durationFromRaw(raw);
  const segments = (raw.scene_segments ??
    raw.sceneSegments ??
    []) as SceneSegment[];
  const keyframes = (raw.keyframes ?? []) as Keyframe[];

  return {
    durationSecs,
    bpm: raw.bpm ?? raw.mir?.tempo_bpm,
    key: keyFromRaw(raw),
    beatTimes: beatTimesFromRaw(raw),
    keyframes,
    sceneSegments: segments,
    palette: raw.palette,
    preset: raw.metadata?.preset as string | undefined,
    transitionFraction:
      (raw.metadata?.transition_fraction as number | undefined) ?? 0.12,
  };
}

/** Remap segment scene templates when a UI preset is applied. */
export function applyPresetToSpec(
  spec: RenderSpec,
  presetId: string,
): RenderSpec {
  const family = PRESET_SCENE_FAMILIES[presetId];
  if (!family || !spec.sceneSegments?.length) {
    return { ...spec, preset: presetId };
  }

  const pool: SceneTemplateId[] = [
    "wire_orb",
    "torus_flow",
    "crystal_burst",
    "ring_drift",
    "grid_depth",
    "octa_pulse",
  ];
  let prev: SceneTemplateId | null = null;
  const remappedSegments = spec.sceneSegments.map((seg, i) => {
    const label = seg.label ?? "unknown";
    let template = family[label] ?? family.unknown ?? "torus_flow";
    if (prev && template === prev) {
      const alt = pool.find((t) => t !== prev);
      if (alt) template = alt;
    }
    prev = template;
    const display = getSceneTemplate(template).displayName;
    return {
      ...seg,
      scene_template: template,
      scene: display,
    };
  });

  const keyframes = remappedSegments.map((seg, i) => {
    const t = Math.min(1, Math.max(0, seg.start / spec.durationSecs));
    const existing = spec.keyframes[i];
    return {
      t,
      scene: seg.scene ?? getSceneTemplate(seg.scene_template).displayName,
      scene_template: seg.scene_template,
      camera: existing?.camera ?? {
        distance: 6,
        azimuth: 0.3 * i,
        elevation: 0.1,
      },
      color: existing?.color ?? {
        primary: spec.palette?.[i % (spec.palette?.length ?? 1)] ?? "#7c6af7",
        secondary:
          spec.palette?.[(i + 1) % (spec.palette?.length ?? 1)] ?? "#22d3ee",
        brightness: 0.7,
      },
      transition_secs: existing?.transition_secs,
      segment_index: seg.index,
      label: seg.label,
    };
  });

  if (keyframes.length > 0 && keyframes[keyframes.length - 1]!.t < 0.999) {
    const last = remappedSegments[remappedSegments.length - 1]!;
    keyframes.push({
      ...keyframes[keyframes.length - 1]!,
      t: 1,
      scene: last.scene ?? "Outro",
      scene_template: last.scene_template,
    });
  }

  return {
    ...spec,
    preset: presetId,
    sceneSegments: remappedSegments,
    keyframes,
  };
}
