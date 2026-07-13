/**
 * @melosviz/bridge-client — stub surface (not published).
 *
 * Illustrative types + helpers for the FastAPI bridge on :8765.
 * Wire into consumers only after an explicit publish decision
 * (see docs/sdk/README.md, docs/SUPPLY_CHAIN.md).
 */

export type AnalyzeRequest = {
  wav_path?: string
  audio_path?: string
}

export type ProblemJson = {
  type?: string
  title?: string
  status?: number
  detail?: string
  [key: string]: unknown
}

/** Placeholder client — fetch wrapper against the supported bridge paths. */
export async function analyze(
  baseUrl: string,
  body: AnalyzeRequest,
  token?: string,
): Promise<unknown> {
  const headers: Record<string, string> = {
    'content-type': 'application/json',
  }
  if (token) headers.authorization = `Bearer ${token}`
  const res = await fetch(`${baseUrl.replace(/\/$/, '')}/analyze`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const problem = (await res.json().catch(() => null)) as ProblemJson | null
    throw Object.assign(new Error(res.statusText || `HTTP ${res.status}`), {
      status: res.status,
      problem,
    })
  }
  return res.json()
}

/** Supported bridge paths (contract SoT: docs/api/openapi.json). */
export const BRIDGE_PATHS = [
  '/health',
  '/ready',
  '/metrics',
  '/analyze',
  '/build',
  '/render',
] as const
