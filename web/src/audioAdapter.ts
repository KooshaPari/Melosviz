/**
 * AudioAdapter — thin wrapper over the Web Audio API.
 *
 * Contract (from App.tsx):
 *   new AudioAdapter()   — initialises AudioContext + requests mic access;
 *                          throws if the browser denies permission.
 *   .stop()              — suspend the context and disconnect the source.
 *   .dispose()           — close the context and release all resources.
 *
 * Design notes:
 *   • Microphone input is the most sensible default: App.tsx passes no URL
 *     or File argument, so the adapter captures live audio and exposes an
 *     AnalyserNode that downstream workstreams (A/B spectral/beat) can read.
 *   • The AnalyserNode is exposed as a public readonly so the renderer can
 *     pull FFT data when Workstream A wires up the visualiser.
 *   • Construction is synchronous; microphone acquisition is kicked off in
 *     the constructor body (fire-and-forget with error surfaced via the
 *     `ready` promise). App.tsx wraps `new AudioAdapter()` in async/await
 *     already, so callers can await adapter.ready to gate on permission.
 */
export class AudioAdapter {
  readonly context: AudioContext
  readonly analyser: AnalyserNode

  /** Resolves when the mic stream is connected; rejects on permission deny. */
  readonly ready: Promise<void>

  private source: MediaStreamAudioSourceNode | null = null
  private stream: MediaStream | null = null

  constructor() {
    this.context = new AudioContext()

    this.analyser = this.context.createAnalyser()
    this.analyser.fftSize = 2048
    this.analyser.smoothingTimeConstant = 0.8
    this.analyser.connect(this.context.destination)

    this.ready = this._init()
  }

  private async _init(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.stream = stream
    this.source = this.context.createMediaStreamSource(stream)
    this.source.connect(this.analyser)

    // Resume in case the context started suspended (autoplay policy).
    if (this.context.state === 'suspended') {
      await this.context.resume()
    }
  }

  /**
   * Copy the current time-domain waveform into a Float32Array.
   * Useful for Workstream B (beat energy) once it hooks in.
   */
  getWaveform(out: Float32Array<ArrayBuffer>): void {
    this.analyser.getFloatTimeDomainData(out)
  }

  /**
   * Copy the current frequency-domain data (dB) into a Float32Array.
   * Useful for Workstream A (spectral FFT visualiser).
   */
  getFrequencyData(out: Float32Array<ArrayBuffer>): void {
    this.analyser.getFloatFrequencyData(out)
  }

  /** Suspend the AudioContext and stop the mic stream tracks. */
  stop(): void {
    this.context.suspend().catch(() => {
      // suspension failure is non-fatal; log and continue
      console.warn('[AudioAdapter] context.suspend() failed')
    })
    this.stream?.getTracks().forEach((t) => t.stop())
  }

  /** Close the AudioContext and release all resources. */
  dispose(): void {
    this.stop()
    this.context.close().catch(() => {
      console.warn('[AudioAdapter] context.close() failed')
    })
  }
}
