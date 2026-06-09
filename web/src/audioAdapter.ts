export interface AudioData {
  energy: number
  beatFlash: number
  downbeatFlash: number
  beatPhase: number
  intensity: number
  hue: number
  frequencyData: Uint8Array
}

export class AudioAdapter {
  private ctx: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private stream: MediaStream | null = null
  private raf: number = 0
  private onData: (data: AudioData) => void
  private frequencyData: Uint8Array
  private timeData: Uint8Array
  private lastBeatTime = 0
  private beatInterval = 0
  private beatFlash = 0
  private downbeatFlash = 0
  private beatPhase = 0

  constructor(onData: (data: AudioData) => void) {
    this.onData = onData
    this.frequencyData = new Uint8Array(0)
    this.timeData = new Uint8Array(0)
  }

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    })

    this.ctx = new AudioContext({
      sampleRate: 48000,
      latencyHint: 'interactive',
    })

    this.analyser = this.ctx.createAnalyser()
    this.analyser.fftSize = 2048
    this.analyser.smoothingTimeConstant = 0.8

    this.source = this.ctx.createMediaStreamSource(this.stream)
    this.source.connect(this.analyser)

    this.frequencyData = new Uint8Array(this.analyser.frequencyBinCount)
    this.timeData = new Uint8Array(this.analyser.frequencyBinCount)

    this.loop()
  }

  stop(): void {
    cancelAnimationFrame(this.raf)
    this.source?.disconnect()
    this.ctx?.close()
    this.stream?.getTracks().forEach((t) => t.stop())
    this.ctx = null
    this.analyser = null
    this.source = null
    this.stream = null
  }

  private loop = (): void => {
    if (!this.analyser) return
    this.analyser.getByteFrequencyData(this.frequencyData)
    this.analyser.getByteTimeDomainData(this.timeData)

    const energy = this.computeEnergy()
    this.detectBeat(energy)

    const data: AudioData = {
      energy,
      beatFlash: this.beatFlash,
      downbeatFlash: this.downbeatFlash,
      beatPhase: this.beatPhase,
      intensity: this.computeIntensity(),
      hue: this.computeHue(),
      frequencyData: new Uint8Array(this.frequencyData),
    }

    this.onData(data)
    this.raf = requestAnimationFrame(this.loop)
  }

  private computeEnergy(): number {
    let sum = 0
    for (let i = 0; i < this.frequencyData.length; i++) {
      sum += this.frequencyData[i] * this.frequencyData[i]
    }
    return Math.sqrt(sum / this.frequencyData.length) / 128
  }

  private computeIntensity(): number {
    let bass = 0
    const bassBins = Math.floor(this.frequencyData.length * 0.1)
    for (let i = 0; i < bassBins; i++) {
      bass += this.frequencyData[i]
    }
    return bass / bassBins / 255
  }

  private computeHue(): number {
    const centroid = this.computeSpectralCentroid()
    return (centroid / (this.frequencyData.length || 1)) * 360
  }

  private computeSpectralCentroid(): number {
    let num = 0
    let den = 0
    for (let i = 0; i < this.frequencyData.length; i++) {
      num += i * this.frequencyData[i]
      den += this.frequencyData[i]
    }
    return den === 0 ? 0 : num / den
  }

  private detectBeat(energy: number): void {
    const now = performance.now() / 1000
    const threshold = 0.15

    if (energy > threshold && now - this.lastBeatTime > 0.2) {
      if (this.beatInterval === 0) {
        this.beatInterval = now - this.lastBeatTime
      }
      this.lastBeatTime = now
      this.beatFlash = 1
      this.beatPhase = (this.beatPhase + 1) % 4
      if (this.beatPhase === 0) {
        this.downbeatFlash = 1
      }
    }

    this.beatFlash *= 0.9
    this.downbeatFlash *= 0.9
  }

  dispose(): void {
    this.stop()
  }
}
