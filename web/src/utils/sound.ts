// WebAudio chime utilities for workstream-completion feedback.
//
// Uses a lazily-created AudioContext that is resumed on the first user
// gesture so browsers do not block playback.  All tones are synthesised
// with oscillators — no audio file dependencies.
//
// Toggle globally via setEnabled() without discarding the AudioContext.

// ---- Internal state ---------------------------------------------------------

let ctx: AudioContext | null = null;
let enabled = true;

// ---- Private helpers --------------------------------------------------------

/**
 * Lazily create (or return) the shared AudioContext.
 * Resumes it if suspended — safe to call from a click/tap handler.
 */
function getCtx(): AudioContext {
  if (!ctx) {
    ctx = new AudioContext();
  }
  if (ctx.state === "suspended") {
    void ctx.resume();
  }
  return ctx;
}

/**
 * Schedule a single sine-wave tone on the given AudioContext.
 *
 * @param c       - The AudioContext to schedule on.
 * @param freq    - Frequency in Hz.
 * @param start   - Start time (seconds, ctx.currentTime-relative).
 * @param dur     - Duration in seconds.
 * @param volume  - Gain [0, 1].
 */
function tone(
  c: AudioContext,
  freq: number,
  start: number,
  dur: number,
  volume = 0.18,
): void {
  const osc = c.createOscillator();
  const gain = c.createGain();

  osc.type = "sine";
  osc.frequency.setValueAtTime(freq, start);

  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(volume, start + 0.008);
  gain.gain.exponentialRampToValueAtTime(0.001, start + dur);

  osc.connect(gain);
  gain.connect(c.destination);

  osc.start(start);
  osc.stop(start + dur + 0.05);
}

/** Tone sequences keyed by chime type. */
const SEQUENCES: Record<
  string,
  { freq: number; dur: number; delay: number }[]
> = {
  /** Ascending major triad (C4 → E4 → G4). */
  complete: [
    { freq: 261.63, dur: 0.15, delay: 0.0 },
    { freq: 329.63, dur: 0.15, delay: 0.12 },
    { freq: 392.0, dur: 0.3, delay: 0.24 },
  ],

  /** Descending diminished triad (B3 → D4 → F4). */
  error: [
    { freq: 246.94, dur: 0.25, delay: 0.0 },
    { freq: 293.66, dur: 0.25, delay: 0.18 },
    { freq: 349.23, dur: 0.35, delay: 0.36 },
  ],

  /** Short single blip (C5). */
  stage: [{ freq: 523.25, dur: 0.08, delay: 0.0 }],
};

// ---- Public API -------------------------------------------------------------

/**
 * Play a chime tone sequence.
 *
 * @param type - One of `'complete'`, `'error'`, or `'stage'`.
 *
 * The AudioContext is created lazily on the first call and resumed if the
 * browser has suspended it.  This makes it safe to call from event handlers
 * triggered by a user gesture (click, keydown, etc.).
 */
export function playChime(type: "complete" | "error" | "stage"): void {
  if (!enabled) return;

  const seq = SEQUENCES[type];
  if (!seq) return;

  const c = getCtx();
  const now = c.currentTime;

  for (const note of seq) {
    tone(c, note.freq, now + note.delay, note.dur);
  }
}

/**
 * Enable or disable all chime sounds.
 *
 * Passing `false` suppresses future `playChime()` calls but does **not**
 * close the underlying AudioContext — toggling back to `true` is instant.
 */
export function setEnabled(on: boolean): void {
  enabled = on;
}
