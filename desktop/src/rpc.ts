/**
 * Shared RPC schema for MelosViz desktop.
 *
 * Pure type definitions — no runtime imports — so this file is safe to
 * import from both the Bun main process (src/main.ts) and the webview
 * (views/main/index.ts) without pulling in platform-specific code.
 */

import type { RPCSchema } from "electrobun/bun";

// Requests the webview sends TO the bun main process.
export type BunRequests = RPCSchema<{
  requests: {
    analyzeWav:  { params: { wavPath: string };                    response: string };
    buildPlan:   { params: { wavPath: string; outDir?: string };   response: string };
    renderVideo: { params: { wavPath: string; outDir: string };    response: string };
    pickFile:    { params: { accept?: string };                    response: string | null };
    pickDirectory: { params: Record<string, never>;               response: string | null };
    revealInFinder: { params: { filePath: string };               response: void };
  };
}>;

// Requests the bun main process sends TO the webview (currently none).
export type WebviewRequests = RPCSchema<Record<string, never>>;
