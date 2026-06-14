// WebSocket client for melosviz — subscribes to live job status and progress.
// Thin wrapper around the browser WebSocket API with auto-reconnect logic.

export interface JobStatusEvent {
  jobId: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  /** Optional ETA in seconds. */
  eta?: number
  /** Optional message for the current stage. */
  stage?: string
}

export type JobEventCallback = (event: JobStatusEvent) => void
export type ConnectionStateCallback = (connected: boolean) => void

const RECONNECT_DELAY_MS = 3000
const MAX_RECONNECT_ATTEMPTS = 5

export class WsClient {
  private url: string
  private ws: WebSocket | null = null
  private onEvent: JobEventCallback
  private onConnectionChange: ConnectionStateCallback
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _connected = false
  private disposed = false

  constructor(
    url: string,
    onEvent: JobEventCallback,
    onConnectionChange: ConnectionStateCallback = () => {},
  ) {
    this.url = url
    this.onEvent = onEvent
    this.onConnectionChange = onConnectionChange
  }

  get connected(): boolean {
    return this._connected
  }

  connect(): void {
    if (this.disposed || this.ws) return
    try {
      const ws = new WebSocket(this.url)
      ws.onopen = () => {
        this.reconnectAttempts = 0
        this._connected = true
        this.onConnectionChange(true)
      }
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data) as JobStatusEvent
          this.onEvent(data)
        } catch {
          // ignore malformed messages
        }
      }
      ws.onclose = () => {
        this.ws = null
        this._connected = false
        this.onConnectionChange(false)
        this.scheduleReconnect()
      }
      ws.onerror = () => {
        ws.close()
      }
      this.ws = ws
    } catch {
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect(): void {
    if (this.disposed || this.reconnectTimer) return
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return
    this.reconnectAttempts++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, RECONNECT_DELAY_MS)
  }

  /** Send a subscription request for a specific job ID. */
  subscribeJob(jobId: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'subscribe', jobId }))
    }
  }

  /** Unsubscribe from a specific job ID. */
  unsubscribeJob(jobId: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'unsubscribe', jobId }))
    }
  }

  disconnect(): void {
    this.reconnectAttempts = MAX_RECONNECT_ATTEMPTS
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  dispose(): void {
    this.disposed = true
    this.disconnect()
  }
}
