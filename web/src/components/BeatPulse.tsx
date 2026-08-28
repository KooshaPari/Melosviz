// BeatPulse — R3F torus ring that pulses on each beat crossing.
//
// Workstream B: beat detection visualization.
// Given `beatTimes` (seconds, sorted ascending) and `playbackT` [0-1],
// fires a scale 1→2→1 pulse over ~0.3 s whenever the playhead crosses a beat.

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export interface BeatPulseProps {
  /** Beat onset times in seconds (sorted ascending). */
  beatTimes: number[];
  /** Normalised playhead position in [0, 1]. */
  playbackT: number;
  /** Total track duration in seconds — used to convert playbackT → absolute time. */
  durationSecs: number;
}

// Pulse duration in seconds (rise + fall)
const PULSE_DURATION = 0.3;

/**
 * BeatPulse renders a semi-transparent cyan torus that pulses (scale 1→2→1)
 * each time the playhead crosses a beat onset in `beatTimes`.
 *
 * Position: slightly behind the main TorusKnot (z = -2).
 */
export function BeatPulse({
  beatTimes,
  playbackT,
  durationSecs,
}: BeatPulseProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.MeshStandardMaterial>(null);

  // Ref tracking state between useFrame calls — avoids React re-renders.
  const state = useRef({
    lastBeatIndex: -1,
    pulseT: 1, // 0 = just fired, 1 = fully settled (no pulse)
    prevCurrentTime: -1,
  });

  useFrame((_rState, delta) => {
    const mesh = meshRef.current;
    const mat = matRef.current;
    if (!mesh || !mat) return;

    const currentTime = playbackT * Math.max(durationSecs, 0.001);
    const s = state.current;

    // Detect beat crossing: find the highest beat index whose time ≤ currentTime.
    let newBeatIndex = -1;
    for (let i = 0; i < beatTimes.length; i++) {
      if (beatTimes[i]! <= currentTime) {
        newBeatIndex = i;
      } else {
        break;
      }
    }

    // Trigger pulse when we cross into a new beat.
    // Guard: only fire if playback moved forward (avoid re-trigger on seek back).
    if (
      newBeatIndex > s.lastBeatIndex &&
      currentTime >= (s.prevCurrentTime ?? currentTime)
    ) {
      s.pulseT = 0;
    }
    s.lastBeatIndex = newBeatIndex;
    s.prevCurrentTime = currentTime;

    // Advance pulse clock
    if (s.pulseT < 1) {
      s.pulseT = Math.min(1, s.pulseT + delta / PULSE_DURATION);
    }

    // Map pulseT [0,1] → scale using a smooth triangle (peak at pulseT=0.5)
    // scale = 1 + sin(π * pulseT)  →  1 at ends, 2 at midpoint
    const scale = 1 + Math.sin(Math.PI * s.pulseT);
    mesh.scale?.setScalar(scale);

    // Fade opacity with the pulse
    const opacity = 0.35 + 0.4 * Math.sin(Math.PI * s.pulseT);
    mat.opacity = opacity;
  });

  return (
    <mesh ref={meshRef} position={[0, 0, -2]}>
      <torusGeometry args={[2.2, 0.08, 16, 64]} />
      <meshStandardMaterial
        ref={matRef}
        color="#22d3ee"
        emissive="#22d3ee"
        emissiveIntensity={1.2}
        transparent
        opacity={0.35}
        roughness={0.2}
        metalness={0.5}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}
