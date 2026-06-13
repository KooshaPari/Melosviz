/**
 * Web Audio adapter for playing MIDI notes with sample-accurate timing.
 *
 * `Note.start` is interpreted as an offset (in seconds) from
 * `AudioContext.currentTime` at the moment the note is scheduled. All
 * envelope automation is performed on a per-note `GainNode` so that the
 * resulting envelope is sample-accurate (the Web Audio engine interpolates
 * automation values at the audio sample rate).
 */

export interface Note {
  /** MIDI note number (e.g. 69 = A4 = 440 Hz). */
  pitch: number
  /** Offset in seconds from `audioContext.currentTime` when the note should start. */
  start: number
  /** Duration in seconds the note is held before the release stage begins. */
  duration: number
  /** Normalized velocity in [0, 1]. Used as the peak gain of the envelope. */
  velocity: number
}

export interface Envelope {
  /** Attack time in seconds (gain ramp from 0 → velocity). */
  attack: number
  /** Decay time in seconds (gain ramp from velocity → sustain). */
  decay: number
  /** Sustain level in [0, 1], relative to velocity. */
  sustain: number
  /** Release time in seconds (gain ramp from sustain → 0 after note ends). */
  release: number
}

const DEFAULT_ENVELOPE: Envelope = {
  attack: 0.01,
  decay: 0.1,
  sustain: 0.7,
  release: 0.15,
}

export class AudioAdapter {
  private ctx: AudioContext | null = null
  private masterGain: GainNode | null = null
  private activeOscillators: Set<OscillatorNode> = new Set()
  private envelope: Envelope

  constructor(envelope: Partial<Envelope> = {}) {
    this.envelope = { ...DEFAULT_ENVELOPE, ...envelope }
  }

  /**
   * Lazily create (or resume) the underlying AudioContext. Browsers require
   * a user gesture to start audio; calling this from a click/tap handler is
   * the recommended pattern. Returns the live context.
   */
  private ensureContext(): AudioContext {
    if (!this.ctx) {
      // Prefer the standard ctor; fall back to webkit prefix for older Safari.
      const Ctor: typeof AudioContext =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext
      this.ctx = new Ctor()
      this.masterGain = this.ctx.createGain()
      this.masterGain.gain.value = 0.5
      this.masterGain.connect(this.ctx.destination)
    }
    if (this.ctx.state === 'suspended') {
      // Fire-and-forget; ignore the promise here for synchronous callers.
      void this.ctx.resume()
    }
    return this.ctx
  }

  /** Convert a MIDI note number to a frequency in Hz (A4 = 69 → 440 Hz). */
  midiToFrequency(pitch: number): number {
    return 440 * Math.pow(2, (pitch - 69) / 12)
  }

  /**
   * Schedule a single note. `when` (if provided) overrides `note.start` and
   * is interpreted as an absolute `AudioContext` time.
   */
  scheduleNote(note: Note, when?: number): void {
    const ctx = this.ensureContext()
    const master = this.masterGain
    if (!master) return

    const startTime = when ?? ctx.currentTime + note.start
    const hold = Math.max(0.001, note.duration)
    const peak = Math.min(1, Math.max(0, note.velocity))
    const env = this.envelope

    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(this.midiToFrequency(note.pitch), startTime)

    const gain = ctx.createGain()
    const attackEnd = startTime + env.attack
    const decayEnd = attackEnd + env.decay
    const sustainEnd = startTime + hold
    const releaseEnd = sustainEnd + env.release
    const stopTime = releaseEnd + 0.005

    // ADSR envelope — sample-accurate automation on the GainNode.
    gain.gain.setValueAtTime(0, startTime)
    gain.gain.linearRampToValueAtTime(peak, attackEnd)
    gain.gain.linearRampToValueAtTime(peak * env.sustain, decayEnd)
    gain.gain.setValueAtTime(peak * env.sustain, sustainEnd)
    gain.gain.linearRampToValueAtTime(0, releaseEnd)

    osc.connect(gain)
    gain.connect(master)

    osc.start(startTime)
    osc.stop(stopTime)

    this.activeOscillators.add(osc)
    osc.onended = () => {
      this.activeOscillators.delete(osc)
    }
  }

  /** Schedule an array of notes relative to "now" in call order. */
  scheduleNotes(notes: Note[]): void {
    for (const note of notes) {
      this.scheduleNote(note)
    }
  }

  /**
   * Stop all currently scheduled notes immediately by issuing a fast release
   * on the master gain. The context is left alive so subsequent notes can be
   * scheduled without re-creating it.
   */
  stop(): void {
    if (!this.ctx || !this.masterGain) return
    const ctx = this.ctx
    const master = this.masterGain
    const now = ctx.currentTime
    const release = 0.02

    // Fast ramp-down of every active oscillator by stopping it with a
    // short fade. Array.from is used so this works under any ES target.
    for (const osc of Array.from(this.activeOscillators)) {
      try {
        osc.stop(now + release)
      } catch {
        // already stopped — ignore
      }
    }
    // Schedule a master-gain dip-and-restore so residual audio is silenced
    // without clipping on the next note.
    const current = master.gain.value
    master.gain.cancelScheduledValues(now)
    master.gain.setValueAtTime(current, now)
    master.gain.linearRampToValueAtTime(0, now + release)
    master.gain.linearRampToValueAtTime(current, now + release * 2)

    this.activeOscillators.clear()
  }

  /** Tear down the AudioContext entirely. After this, scheduleNote will recreate it. */
  dispose(): void {
    this.stop()
    if (this.ctx) {
      void this.ctx.close()
      this.ctx = null
      this.masterGain = null
    }
  }
}
