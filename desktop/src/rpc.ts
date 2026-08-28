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
    renderWithWgpu: { params: { renderSpec: string; outDir: string }; response: string };
    pickFile:    { params: { accept?: string };                    response: string | null };
    pickDirectory: { params: Record<string, never>;               response: string | null };
    revealInFinder: { params: { filePath: string };               response: void };

    // New: studio pipeline (ComfyUI + C4D + UE + AE + DaVinci) — storyboards
    // the audio into a shot list and renders every scene through the
    // matching adapter. See docs/STUDIO_PIPELINE.md.
    runStoryboard: {
      params: {
        wavPath: string;
        outDir?: string;
        concept?: string;
        bpm?: number;
        palette?: string;
        /** v2 — narrative inputs. */
        lyricsPath?: string;
        moodBoardPaths?: string[] | string;
        continuityCharacter?: string;
        continuityEnvironment?: string;
        aspectRatio?: string;
      };
      response: string;
    };
    runOrchestratedRender: {
      params: {
        wavPath: string;
        storyboardPath: string;
        outDir?: string;
        /** Job id used to tag emitted orchestrator events for SSE filtering.
         *  If omitted, the bun side mints one and returns it via the
         *  `jobId` field of the response envelope (Bun returns a string,
         *  so we encode as JSON `{"out": "...", "jobId": "..."}`). */
        jobId?: string;
      };
      response: string;
    };
    /** Returns the URL the webview should open with `new EventSource(url)`
     *  to live-consume orchestrator render events. Appended `?token=...`
     *  when the bridge has bearer-auth enabled (Electrobun's webview
     *  can't set custom headers on EventSource). */
    getRenderEventStreamUrl: {
      params: { jobId: string };
      response: string;
    };
    runMaster: {
      params: {
        inputPath: string;
        outDir?: string;
        /** Delivery-target preset name (youtube, spotify, broadcast_ebu_r128,
         *  club_pa, cinema, custom). Resolves to LUFS + true-peak + dither. */
        lufsTarget?: string;
        /** Split audio into stems (drums / bass / synths) for VJ re-mixing. */
        exportStems?: boolean;
        /** Explicit source WAV for the master (defaults to the loaded track). */
        audioWavPath?: string;
      };
      response: string;
    };
    runShip: {
      params: {
        masterDir: string;
        outPath?: string;
        lyricsPath?: string;
      };
      response: string;
    };
    /** Art-director single-scene edit. Mutates one scene's prompt / camera /
     *  name in the storyboard JSON, optionally fires a partial-scene
     *  re-render of just that scene, and returns the edit summary. */
    runDirect: {
      params: {
        storyboardPath: string;
        sceneIndex: number;
        /** Optional edits — only the fields present get applied. */
        replacePrompt?: string;
        replaceCamera?: string;
        replaceName?: string;
        /** Write the edited storyboard to a separate file instead of
         *  mutating the original. */
        outPath?: string;
        /** Trigger a viz generate --only-scenes=<sceneIndex> subprocess. */
        reRender?: boolean;
        /** Source audio for the partial re-render. */
        wavPath?: string;
        /** Output directory for the partial re-render. */
        renderOut?: string;
        /** Force MELOSVIZ_COMFYUI_OFFLINE=1 in the subprocess. */
        renderOffline?: boolean;
      };
      response: string;
    };
    /** Storyboard validation — runs StoryboardValidator + returns the
     *  severity breakdown (errors / warnings / info) so the desktop
     *  Director's Console can surface bad storyboards before render. */
    runValidate: {
      params: { storyboardPath: string };
      response: string;
    };
  };
}>;

// Requests the bun main process sends TO the webview.
export type WebviewRequests = RPCSchema<{
  /**
   * Live render-event pushed from the orchestrator's per-scene event bus
   * (see backend/src/melosviz/conductor/events.py). The bun-side proxy
   * holds the SSE connection to /api/render/events?job_id=... and pushes
   * each event here so the webview can update its render-queue UI
   * without needing a direct SSE connection (Electrobun's webview
   * doesn't expose EventSource in every build).
   */
  pushRenderEvent: {
    params: {
      jobId: string;
      event: {
        scene_index: number;
        scene_type: string;
        state: "queued" | "rendering" | "done" | "error";
        backend: string;
        started_at?: number;
        finished_at?: number;
        error_class?: string;
        error_message?: string;
        artifacts?: string[];
      };
    };
    response: void;
  };
}>;
