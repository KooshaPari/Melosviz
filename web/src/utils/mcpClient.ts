/**
 * JSON-RPC 2.0 MCP client for the MelosViz bridge `/mcp` endpoint.
 *
 * Provides `initialize()`, `toolsList()`, and `toolsCall()` with
 * exponential-backoff retry and AbortSignal support.
 *
 * @module
 */

/* ─── Types ─────────────────────────────────────────────────────────────────── */

interface JsonRpcRequest {
  jsonrpc: '2.0'
  id: number
  method: string
  params?: Record<string, unknown>
}

interface JsonRpcError {
  code: number
  message: string
  data?: unknown
}

interface JsonRpcResponse<T = unknown> {
  jsonrpc: '2.0'
  id: number
  result?: T
  error?: JsonRpcError
}

interface InitializeParams {
  protocolVersion: string
  capabilities: Record<string, unknown>
  clientInfo: { name: string; version: string }
}

export interface InitializeResult {
  protocolVersion: string
  capabilities: Record<string, unknown>
  serverInfo: { name: string; version: string }
}

export interface McpTool {
  name: string
  description?: string
  inputSchema?: Record<string, unknown>
}

export type ToolCallArguments = Record<string, unknown>

export interface ToolCallContent {
  type: string
  text?: string
  [key: string]: unknown
}

export interface ToolCallResult {
  content: ToolCallContent[]
  isError?: boolean
}

/* ─── Retry / backoff helpers ───────────────────────────────────────────────── */

interface BackoffOptions {
  /** Initial delay in ms (default 1000). */
  baseDelayMs?: number
  /** Maximum delay in ms (default 30 000). */
  maxDelayMs?: number
  /** Jitter fraction, 0 = none, 1 = full (default 0.2). */
  jitter?: number
}

const DEFAULT_BACKOFF: Required<BackoffOptions> = {
  baseDelayMs: 1_000,
  maxDelayMs: 30_000,
  jitter: 0.2,
}

/**
 * Return a promise that resolves after `ms` milliseconds, or rejects with
 * an `AbortError` if `signal` fires before the timer elapses.
 */
function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }

    const timer = setTimeout(resolve, ms)
    const onAbort = () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }

    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/**
 * Compute the backoff delay for the given attempt number using exponential
 * backoff with configurable jitter.
 *
 * `attempt` is 0-indexed.  Returns a whole number of milliseconds.
 */
function computeBackoff(
  attempt: number,
  opts: Required<BackoffOptions>,
): number {
  const exp = opts.baseDelayMs * 2 ** attempt
  const clamped = Math.min(exp, opts.maxDelayMs)
  const jitterRange = clamped * opts.jitter
  const jitterAmount = Math.random() * jitterRange - jitterRange / 2
  return Math.round(clamped + jitterAmount)
}

/* ─── McpError ─────────────────────────────────────────────────────────────── */

/**
 * Error returned in a JSON-RPC error response from the MCP server.
 *
 * Carries the JSON-RPC error `code` and optional `data` payload so callers
 * can distinguish protocol-level errors from transport failures.
 */
export class McpError extends Error {
  readonly code: number
  readonly data?: unknown

  constructor(code: number, message: string, data?: unknown) {
    super(message)
    this.name = 'McpError'
    this.code = code
    this.data = data
  }
}

/* ─── McpClient ────────────────────────────────────────────────────────────── */

/**
 * JSON-RPC 2.0 MCP client that talks to a bridge `/mcp` endpoint over HTTP.
 *
 * Every request is retried with exponential backoff on transport failure
 * (HTTP errors, network errors).  All public methods accept an optional
 * `AbortSignal` to cancel in-flight requests and stop retrying.
 *
 * @example
 * ```ts
 * const mcp = new McpClient('/mcp')
 * const info = await mcp.initialize('melosviz', '0.1.0')
 * const tools = await mcp.toolsList()
 * const result = await mcp.toolsCall('some_tool', { arg1: 'val' })
 * ```
 */
export class McpClient {
  private readonly baseUrl: string
  private readonly backoffOpts: Required<BackoffOptions>
  private nextId = 1
  private initialized = false

  /**
   * @param baseUrl     - URL of the MCP bridge endpoint (default `/mcp`).
   * @param backoffOpts - Exponential backoff tuning.
   */
  constructor(baseUrl: string = '/mcp', backoffOpts?: BackoffOptions) {
    this.baseUrl = baseUrl
    this.backoffOpts = { ...DEFAULT_BACKOFF, ...backoffOpts }
  }

  /** Whether the MCP handshake (`initialize`) has completed. */
  get isInitialized(): boolean {
    return this.initialized
  }

  /* ── Private helpers ────────────────────────────────────────────────── */

  /**
   * Allocate a fresh JSON-RPC request ID (monotonically increasing).
   */
  private allocId(): number {
    return this.nextId++
  }

  /**
   * Core transport: POST a JSON-RPC 2.0 request and return the `result`
   * field, retrying on failure with exponential backoff.
   *
   * JSON-RPC error responses are **not** retried — they are thrown
   * immediately as `McpError`.  Only transport-level failures (network
   * errors, HTTP 5xx, timeouts) trigger a retry.
   */
  private async send<T>(
    method: string,
    params?: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<T> {
    const id = this.allocId()
    const body: JsonRpcRequest = { jsonrpc: '2.0', id, method, params }

    let lastError: Error | null = null

    for (let attempt = 0; ; attempt++) {
      // Honour caller-initiated cancellation before each attempt
      if (signal?.aborted) {
        throw new DOMException('Aborted', 'AbortError')
      }

      try {
        const res = await fetch(this.baseUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal,
        })

        if (!res.ok) {
          // HTTP-level failure — treat as transport error, retry
          throw new Error(`HTTP ${res.status} ${res.statusText}`)
        }

        const json = (await res.json()) as JsonRpcResponse<T>

        if (json.error) {
          // JSON-RPC error — NOT retried, the server spoke valid JSON
          throw new McpError(json.error.code, json.error.message, json.error.data)
        }

        return json.result as T
      } catch (err) {
        // AbortSignal cancellation — propagate immediately, no retry
        if (err instanceof DOMException && err.name === 'AbortError') {
          throw err
        }

        // Re-throw JSON-RPC errors without retrying
        if (err instanceof McpError) {
          throw err
        }

        lastError = err instanceof Error ? err : new Error(String(err))

        // Wait before the next attempt (the wait itself can be aborted)
        const ms = computeBackoff(attempt, this.backoffOpts)
        try {
          await delay(ms, signal)
        } catch {
          // delay was aborted — surface the original error
          throw lastError
        }
      }
    }
  }

  /* ── Public API ─────────────────────────────────────────────────────── */

  /**
   * Perform the MCP `initialize` handshake.
   *
   * Must be called (and resolve successfully) before `toolsList()` or
   * `toolsCall()` will work.  Sets `isInitialized` to `true` on success.
   *
   * @param clientName    - Name advertised to the server.
   * @param clientVersion - Version advertised to the server.
   * @param signal        - Optional AbortSignal.
   */
  async initialize(
    clientName: string = 'melosviz',
    clientVersion: string = '0.1.0',
    signal?: AbortSignal,
  ): Promise<InitializeResult> {
    const params: InitializeParams = {
      protocolVersion: '2024-11-05',
      capabilities: { tools: {} },
      clientInfo: { name: clientName, version: clientVersion },
    }

    const result = await this.send<InitializeResult>(
      'initialize',
      params as unknown as Record<string, unknown>,
      signal,
    )
    this.initialized = true
    return result
  }

  /**
   * List available tools exposed by the MCP server.
   *
   * @param signal - Optional AbortSignal.
   */
  async toolsList(signal?: AbortSignal): Promise<McpTool[]> {
    const result = await this.send<{ tools: McpTool[] }>(
      'tools/list',
      undefined,
      signal,
    )
    return result.tools
  }

  /**
   * Call an MCP tool by name with the supplied arguments.
   *
   * @param name      - Tool name.
   * @param arguments - Tool arguments (must be JSON-serialisable).
   * @param signal    - Optional AbortSignal.
   */
  async toolsCall(
    name: string,
    args: ToolCallArguments = {},
    signal?: AbortSignal,
  ): Promise<ToolCallResult> {
    return await this.send<ToolCallResult>(
      'tools/call',
      { name, arguments: args },
      signal,
    )
  }
}
