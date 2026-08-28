// Deterministic text mirror for the R3F canvas (G-C09-01 / W-329).
//
// Pure functions — no wall-clock, no React, no Three.js — so unit tests and
// a11y CI stay stable while the WebGL scene animates.

import type { RenderSpec } from "../renderSpec";
import { lerpKeyframe } from "./interpolate";

export interface SceneSummaryInput {
  spec: RenderSpec;
  /** Normalised playhead position in [0, 1]. */
  playbackT: number;
  /** Resolved scene / shot label from the shell. */
  sceneLabel: string;
}

export interface SceneSummary {
  /** Short label for role=img aria-label. */
  imgLabel: string;
  /** Live-region announcement (scene + discrete playhead %). */
  liveAnnouncement: string;
  /** Full non-visual alternative (aria-describedby target). */
  detailText: string;
  /** Stable key — announce live region only when this changes. */
  liveKey: string;
}

function clamp01(t: number): number {
  return Math.min(1, Math.max(0, t));
}

/** Format seconds as m:ss (floor seconds for stable copy). */
export function formatTrackTime(secs: number): string {
  const total = Math.max(0, Math.floor(secs));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatPercent(t: number): string {
  return `${Math.round(clamp01(t) * 100)}%`;
}

function describeBrightness(brightness: number): string {
  if (brightness < 0.34) return "dim";
  if (brightness < 0.67) return "medium";
  return "bright";
}

function describeElevationRad(elevation: number): string {
  const deg = Math.round((elevation * 180) / Math.PI);
  if (deg <= -5) return "low angle";
  if (deg >= 5) return "elevated angle";
  return "level angle";
}

/**
 * Build deterministic SR text from RenderSpec + playhead.
 * Interpolated camera/color values mirror what MelosScene renders at `playbackT`.
 */
export function buildSceneSummary({
  spec,
  playbackT,
  sceneLabel,
}: SceneSummaryInput): SceneSummary {
  const t = clamp01(playbackT);
  const label = sceneLabel.trim() || "Scene";
  const frame = lerpKeyframe(spec.keyframes, t);
  const duration = Math.max(0, spec.durationSecs);
  const elapsedSecs = duration * t;

  const percent = formatPercent(t);
  const percentInt = Math.round(clamp01(t) * 100);
  const elapsed = formatTrackTime(elapsedSecs);
  const total = formatTrackTime(duration);

  const bpm = spec.bpm ?? 120;
  const keyPart = spec.key ? ` Key ${spec.key}.` : "";
  const beatPart =
    (spec.beatTimes?.length ?? 0) > 0
      ? ` ${spec.beatTimes!.length} beat markers.`
      : "";

  const brightness = describeBrightness(frame.color.brightness);
  const elevation = describeElevationRad(frame.camera.elevation);
  const distance = frame.camera.distance.toFixed(1);

  const visual =
    `Torus knot mesh with ${frame.color.primary} primary glow, ` +
    `${frame.color.secondary} accent lighting, ${brightness} brightness. ` +
    `Camera distance ${distance}, ${elevation}.`;

  const imgLabel = `Melosviz visualization: ${label}, ${percent} through track`;

  const liveAnnouncement =
    `${label}. Playback ${percent}, ${elapsed} of ${total}. ` +
    `Tempo ${bpm} BPM.${keyPart}${beatPart} ${visual}`;

  const detailText =
    `Non-visual scene summary. Scene: ${label}. ` +
    `Playback position ${percent} (${elapsed} of ${total}). ` +
    `Tempo ${bpm} beats per minute.${keyPart}${beatPart} ` +
    `Geometry: ${visual}`;

  return {
    imgLabel,
    liveAnnouncement,
    detailText,
    liveKey: `${label}|${percentInt}`,
  };
}
