/**
 * Director's Console — a thin orchestrator-backed UI for the
 * ComfyUI-centric music-video pipeline.
 *
 * The user supplies a WAV path + concept + BPM + palette; this component
 * drives the melosviz backend's storyboard → generate → master → ship
 * stages over HTTP and shows per-scene status. It is **not** a 3D editor.
 *
 * Endpoints:
 *   POST /api/studio/storyboard   → storyboard.json
 *   POST /api/studio/generate     → { out_dir, scenes: [...] }
 *   POST /api/studio/master       → master_plan.json
 *   POST /api/studio/ship         → { final_zip, manifest }
 *
 * @module
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type * as React from "react";
import { t } from "../i18n";

/* ─── Types ─────────────────────────────────────────────────────────────────── */

export interface StudioScene {
  index: number;
  name: string;
  startSec: number;
  endSec: number;
  sceneType: string;
  camera: string;
  prompt: string;
  palette: string[];
  seed: number;
  status: "queued" | "rendering" | "done" | "error";
  /** Path to the emitted workflow.json / job_spec.json / plan.json */
  artifactPath?: string;
  errorMessage?: string;
}

export interface StudioMasterDeliverable {
  kind: "festival" | "club" | "youtube" | "mix" | "captions" | "other";
  path: string;
  bytes: number;
}

export interface StudioConsoleProps {
  /** Base URL of the MelosViz bridge (e.g. `http://127.0.0.1:8765`). */
  bridgeBase?: string;
  /** Pre-loaded wav path (e.g. from a global input). */
  initialWavPath?: string;
  /** Optional auto-elevation via a global "open studio" signal. */
  autoOpenSignal?: number;
  /** Optional i18n override (defaults to the global `t()` helper). */
  i18n?: (key: string, fallback?: string) => string;
}

/* ─── Helpers ───────────────────────────────────────────────────────────────── */

interface StoryboardScene {
  name?: string;
  start_sec?: number;
  end_sec?: number;
  scene_type?: string;
  camera_motion?: string;
  prompt?: string;
  palette?: string[];
  seed?: number;
}

interface StoryboardPayload {
  concept?: string;
  bpm?: number;
  scenes?: StoryboardScene[];
}

interface GenerateSceneMeta {
  name?: string;
  scene_dir?: string;
  workflow_json?: string;
  job_spec_json?: string;
  plan_json?: string;
}

interface GeneratePayload {
  out_dir?: string;
  scenes?: GenerateSceneMeta[];
}

interface MasterPlanDeliverable {
  kind?: string;
  path?: string;
  bytes?: number;
}

interface MasterPlan {
  deliverables?: MasterPlanDeliverable[];
  files?: string[];
}

interface ShipPayload {
  final_zip?: string;
  final_zip_bytes?: number;
  manifest?: { contents?: Array<{ path: string; bytes?: number }> };
}

const DEFAULT_PALETTE = "#0d0d10 #ff2bd6 #22d3ee #c084fc #f0f0f8";

function inferKind(name: string): StudioMasterDeliverable["kind"] {
  const lower = name.toLowerCase();
  if (lower.includes("festival") || lower.endsWith(".mov")) return "festival";
  if (lower.includes("youtube")) return "youtube";
  if (lower.includes("club")) return "club";
  if (lower.endsWith(".wav") || lower.includes("mix")) return "mix";
  if (lower.endsWith(".srt") || lower.includes("caption")) return "captions";
  return "other";
}

/* ─── Component ────────────────────────────────────────────────────────────── */

export function StudioConsole({
  bridgeBase = "",
  initialWavPath = "",
  autoOpenSignal,
  i18n,
}: StudioConsoleProps): React.ReactElement {
  const tr = i18n ?? t;

  /* ----- Inputs ---------------------------------------------------------- */
  const [wavPath, setWavPath] = useState(initialWavPath);
  const [concept, setConcept] = useState(
    "abstract underwater city, bioluminescent, 35mm grain",
  );
  const [bpm, setBpm] = useState(124);
  const [palette, setPalette] = useState(DEFAULT_PALETTE);
  const [useLlmDirector, setUseLlmDirector] = useState(true);
  const [offline, setOffline] = useState(true);
  /** Optional LRC file path for lyric-aligned scene boundaries. */
  const [lyricsPath, setLyricsPath] = useState("");
  /** Optional comma-separated list of reference image paths for mood-board palette extraction. */
  const [moodBoardPaths, setMoodBoardPaths] = useState("");
  /** Cinematic anchors — pinned across every scene to keep the video coherent. */
  const [continuityCharacter, setContinuityCharacter] = useState("");
  const [continuityEnvironment, setContinuityEnvironment] = useState("");
  /** Audio finishing: EBU R128 LUFS delivery target. */
  const [lufsTarget, setLufsTarget] = useState<string>("youtube");
  /** Audio finishing: export stems for live-mix use. */
  const [exportStems, setExportStems] = useState(true);
  /** Cinematic anchor: aspect-ratio preset. */
  const [aspectRatio, setAspectRatio] = useState<string>("youtube_16x9_1080p");
  /** Audio finishing: explicit source WAV path (defaults to wavPath when blank). */
  const [audioWavPath, setAudioWavPath] = useState("");

  /* ----- Outputs --------------------------------------------------------- */
  const [storyboard, setStoryboard] = useState<StoryboardPayload | null>(null);
  const [scenes, setScenes] = useState<StudioScene[]>([]);
  const [, setMasterPlan] = useState<MasterPlan | null>(null);
  const [masterDeliverables, setMasterDeliverables] = useState<
    StudioMasterDeliverable[]
  >([]);
  const [shipResult, setShipResult] = useState<ShipPayload | null>(null);

  /* ----- Stage state ----------------------------------------------------- */
  const [stage, setStage] = useState<
    "idle" | "storyboard" | "generate" | "master" | "ship"
  >("idle");
  const [error, setError] = useState<string | null>(null);

  /* ----- Auto-open signal ----------------------------------------------- */
  useEffect(() => {
    if (initialWavPath) setWavPath(initialWavPath);
  }, [initialWavPath]);
  useEffect(() => {
    if (typeof autoOpenSignal === "number" && initialWavPath) {
      void runStoryboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoOpenSignal]);

  /* ----- API helpers ---------------------------------------------------- */
  const post = useCallback(
    async <T,>(path: string, body: Record<string, unknown>): Promise<T> => {
      const res = await fetch(`${bridgeBase}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => res.statusText);
        throw new Error(`${res.status} ${res.statusText}: ${detail}`);
      }
      const text = await res.text();
      return JSON.parse(text) as T;
    },
    [bridgeBase],
  );

  /* ----- SSE render event stream ---------------------------------------- */
  /** Per-scene state subscription via /api/render/events SSE.
   *
   * The orchestrator emits RenderEvent{job_id, scene_index, scene_type,
   * state, backend, artifact_path, error_message, duration_ms} on every
   * per-scene transition. We open an SSE connection while any scene is
   * queued or rendering, and patch scene state in place as events arrive.
   */
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const url = `${bridgeBase}/api/render/events?job_id=${encodeURIComponent(jobId)}`;
    let es: EventSource | null = null;
    let cancelled = false;
    try {
      es = new EventSource(url);
    } catch {
      return;
    }
    es.addEventListener("render_event", (msg) => {
      if (cancelled) return;
      try {
        const payload = JSON.parse((msg as MessageEvent).data) as {
          scene_index?: number;
          state?: "queued" | "rendering" | "done" | "error";
          artifact_path?: string;
          error_message?: string;
          duration_ms?: number;
        };
        const idx = payload.scene_index;
        const next = payload.state;
        if (typeof idx !== "number" || !next) return;
        setScenes((prev) => {
          if (idx >= prev.length) return prev;
          const cur = prev[idx];
          if (!cur || cur.status === next) return prev;
          return [
            ...prev.slice(0, idx),
            {
              ...cur,
              status: next,
              artifactPath: payload.artifact_path ?? cur.artifactPath,
              errorMessage: payload.error_message ?? cur.errorMessage,
            },
            ...prev.slice(idx + 1),
          ];
        });
      } catch {
        /* ignore malformed events */
      }
    });
    es.onerror = () => {
      /* EventSource auto-reconnects on transient errors */
    };
    return () => {
      cancelled = true;
      es?.close();
    };
  }, [jobId, bridgeBase]);

  /* ----- Stage runners -------------------------------------------------- */
  const runStoryboard = useCallback(async () => {
    if (!wavPath.trim()) {
      setError(tr("studio.error.no_wav", "Please provide a WAV path."));
      return;
    }
    setError(null);
    setStage("storyboard");
    setScenes([]);
    setMasterPlan(null);
    setMasterDeliverables([]);
    setShipResult(null);
    try {
      const payload = await post<StoryboardPayload>("/api/studio/storyboard", {
        wav_path: wavPath,
        concept,
        bpm: Number(bpm),
        palette,
        out_dir: wavPath.replace(/\.[^.]+$/, "") + ".studio",
        use_llm_director: useLlmDirector,
        lyrics_path: lyricsPath.trim() || undefined,
        mood_board_paths: moodBoardPaths.trim()
          ? moodBoardPaths
              .split(",")
              .map((p) => p.trim())
              .filter(Boolean)
          : undefined,
        continuity_character: continuityCharacter.trim() || undefined,
        continuity_environment: continuityEnvironment.trim() || undefined,
        aspect_ratio: aspectRatio,
      });
      setStoryboard(payload);
      const seed = Math.floor(Math.random() * 1e9);
      const sceneList = (payload.scenes ?? []).map((s, i) => ({
        index: i,
        name: s.name ?? `Scene ${i + 1}`,
        startSec: s.start_sec ?? 0,
        endSec: s.end_sec ?? 0,
        sceneType: s.scene_type ?? "comfyui_image",
        camera: s.camera_motion ?? "static",
        prompt: s.prompt ?? "",
        palette: s.palette ?? [],
        seed: s.seed ?? seed + i,
        status: "queued" as const,
      }));
      setScenes(sceneList);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStage("idle");
    }
  }, [
    wavPath,
    concept,
    bpm,
    palette,
    useLlmDirector,
    lyricsPath,
    moodBoardPaths,
    continuityCharacter,
    continuityEnvironment,
    aspectRatio,
    post,
    tr,
  ]);

  const runGenerate = useCallback(async () => {
    if (!storyboard || !scenes.length) {
      setError(tr("studio.error.no_storyboard", "Storyboard a track first."));
      return;
    }
    setError(null);
    setStage("generate");
    // Mark every scene as rendering
    setScenes((prev) =>
      prev.map((s) => ({ ...s, status: "rendering" as const })),
    );
    // Open SSE stream so per-scene done/error events arrive in real time.
    const generatedJobId = `gen-${Date.now().toString(36)}`;
    setJobId(generatedJobId);
    try {
      const storyboardPath =
        wavPath.replace(/\.[^.]+$/, "") + ".studio/storyboard.json";
      const outDir = wavPath.replace(/\.[^.]+$/, "") + ".studio/generate";
      const payload = await post<GeneratePayload>("/api/studio/generate", {
        wav_path: wavPath,
        storyboard_path: storyboardPath,
        out_dir: outDir,
        offline,
        job_id: generatedJobId,
      });
      // Mark every scene done + attach emitted artifact path
      const emitted = new Map<string, GenerateSceneMeta>();
      for (const sceneMeta of payload.scenes ?? []) {
        const stem = sceneMeta.name ?? "";
        if (stem) emitted.set(stem, sceneMeta);
      }
      setScenes((prev) =>
        prev.map((s, i) => {
          const meta = emitted.get(`scene_${i}`);
          if (!meta) {
            return {
              ...s,
              status: "error" as const,
              errorMessage: "No artifact emitted",
            };
          }
          return {
            ...s,
            status: "done" as const,
            artifactPath:
              meta.workflow_json ??
              meta.job_spec_json ??
              meta.plan_json ??
              meta.scene_dir,
          };
        }),
      );
    } catch (err) {
      setScenes((prev) =>
        prev.map((s) => ({
          ...s,
          status: "error" as const,
          errorMessage: err instanceof Error ? err.message : String(err),
        })),
      );
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStage("idle");
    }
  }, [storyboard, scenes.length, wavPath, offline, post, tr]);

  const runMaster = useCallback(async () => {
    if (!scenes.length) {
      setError(tr("studio.error.no_scenes", "Generate scenes first."));
      return;
    }
    setError(null);
    setStage("master");
    try {
      const outDir = wavPath.replace(/\.[^.]+$/, "") + ".studio/master";
      const editPath =
        wavPath.replace(/\.[^.]+$/, "") +
        ".studio/generate/assembly/assembly_plan.json";
      const audioForMaster = audioWavPath.trim() || wavPath;
      const payload = await post<MasterPlan>("/api/studio/master", {
        edit_path: editPath,
        out_dir: outDir,
        offline,
        lufs_target: lufsTarget,
        export_stems: exportStems,
        audio_wav_path: audioForMaster,
      });
      setMasterPlan(payload);
      const deliverables: StudioMasterDeliverable[] = (
        payload.deliverables ?? []
      ).map((d) => ({
        kind:
          (inferKind(d.path ?? "") as StudioMasterDeliverable["kind"]) ??
          "other",
        path: d.path ?? "",
        bytes: d.bytes ?? 0,
      }));
      // Fallback: derive deliverables from raw files list
      if (!deliverables.length && payload.files) {
        for (const file of payload.files) {
          deliverables.push({ kind: inferKind(file), path: file, bytes: 0 });
        }
      }
      setMasterDeliverables(deliverables);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStage("idle");
    }
  }, [
    scenes.length,
    wavPath,
    offline,
    lufsTarget,
    exportStems,
    audioWavPath,
    post,
    tr,
  ]);

  const runShip = useCallback(async () => {
    if (!scenes.length) {
      setError(tr("studio.error.no_scenes", "Generate scenes first."));
      return;
    }
    setError(null);
    setStage("ship");
    try {
      const masterDir = wavPath.replace(/\.[^.]+$/, "") + ".studio/master";
      const payload = await post<ShipPayload>("/api/studio/ship", {
        master_dir: masterDir,
        offline,
      });
      setShipResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStage("idle");
    }
  }, [scenes.length, wavPath, offline, post, tr]);

  /* ----- Render helpers ------------------------------------------------- */
  const stageLabel = useMemo(() => {
    switch (stage) {
      case "idle":
        return tr("studio.stage.idle", "Idle");
      case "storyboard":
        return tr("studio.stage.storyboard", "Storyboarding…");
      case "generate":
        return tr("studio.stage.generate", "Generating…");
      case "master":
        return tr("studio.stage.master", "Mastering…");
      case "ship":
        return tr("studio.stage.ship", "Shipping…");
    }
  }, [stage, tr]);

  const totalScenes = scenes.length;
  const completedScenes = scenes.filter((s) => s.status === "done").length;
  const errorScenes = scenes.filter((s) => s.status === "error").length;
  const queueProgress =
    totalScenes === 0 ? 0 : Math.round((completedScenes / totalScenes) * 100);

  return (
    <section
      className="studio-console"
      aria-label="MelosViz Director's Console"
    >
      <header className="studio-console-header">
        <div>
          <h2 className="studio-console-title">
            {tr("studio.title", "Director's Console")}
          </h2>
          <p className="studio-console-subtitle">
            {tr(
              "studio.subtitle",
              "Drive the ComfyUI / Cinema 4D / Unreal / DaVinci music-video pipeline.",
            )}
          </p>
        </div>
        <span className="studio-console-stage" data-stage={stage}>
          {stageLabel}
        </span>
      </header>

      {error && (
        <p role="alert" className="studio-console-error">
          {error}
        </p>
      )}

      {/* ---- Concept inputs ----------------------------------------------- */}
      <div className="studio-console-inputs">
        <label className="studio-field">
          <span>{tr("studio.field.wav", "WAV path")}</span>
          <input
            type="text"
            value={wavPath}
            onChange={(e) => setWavPath(e.target.value)}
            placeholder="/path/to/track.wav"
            data-testid="studio-wav-input"
          />
        </label>
        <label className="studio-field">
          <span>{tr("studio.field.concept", "Concept")}</span>
          <input
            type="text"
            value={concept}
            onChange={(e) => setConcept(e.target.value)}
            data-testid="studio-concept-input"
          />
        </label>
        <label className="studio-field studio-field-bpm">
          <span>{tr("studio.field.bpm", "BPM")}</span>
          <input
            type="number"
            value={bpm}
            min={40}
            max={220}
            onChange={(e) => setBpm(Number(e.target.value))}
            data-testid="studio-bpm-input"
          />
        </label>
        <label className="studio-field studio-field-palette">
          <span>
            {tr("studio.field.palette", "Palette (hex, space-separated)")}
          </span>
          <input
            type="text"
            value={palette}
            onChange={(e) => setPalette(e.target.value)}
            data-testid="studio-palette-input"
          />
        </label>
        <label className="studio-toggle">
          <input
            type="checkbox"
            checked={useLlmDirector}
            onChange={(e) => setUseLlmDirector(e.target.checked)}
            data-testid="studio-llm-toggle"
          />
          <span>{tr("studio.field.llm", "Use LLM director")}</span>
        </label>
        <label className="studio-toggle">
          <input
            type="checkbox"
            checked={offline}
            onChange={(e) => setOffline(e.target.checked)}
            data-testid="studio-offline-toggle"
          />
          <span>{tr("studio.field.offline", "Offline mode")}</span>
        </label>
      </div>

      {/* ---- Cinematic anchors + lyric / mood-board inputs ---------------- */}
      <details className="studio-advanced" data-testid="studio-advanced">
        <summary>
          {tr(
            "studio.advanced.toggle",
            "Advanced: lyrics, mood-board, continuity",
          )}
        </summary>
        <div className="studio-console-inputs">
          <label className="studio-field studio-field-wide">
            <span>{tr("studio.field.lyrics", "Lyrics (LRC path)")}</span>
            <input
              type="text"
              value={lyricsPath}
              onChange={(e) => setLyricsPath(e.target.value)}
              placeholder="/path/to/song.lrc"
              data-testid="studio-lyrics-input"
            />
          </label>
          <label className="studio-field studio-field-wide">
            <span>
              {tr(
                "studio.field.moodboard",
                "Mood-board (comma-separated image paths)",
              )}
            </span>
            <input
              type="text"
              value={moodBoardPaths}
              onChange={(e) => setMoodBoardPaths(e.target.value)}
              placeholder="/path/ref1.png, /path/ref2.jpg"
              data-testid="studio-moodboard-input"
            />
          </label>
          <label className="studio-field studio-field-wide">
            <span>
              {tr("studio.field.character", "Continuity · character")}
            </span>
            <input
              type="text"
              value={continuityCharacter}
              onChange={(e) => setContinuityCharacter(e.target.value)}
              placeholder="young woman with short silver hair, neon trenchcoat"
              data-testid="studio-character-input"
            />
          </label>
          <label className="studio-field studio-field-wide">
            <span>
              {tr("studio.field.environment", "Continuity · environment")}
            </span>
            <input
              type="text"
              value={continuityEnvironment}
              onChange={(e) => setContinuityEnvironment(e.target.value)}
              placeholder="bioluminescent underwater city of glass and coral"
              data-testid="studio-environment-input"
            />
          </label>
          <label className="studio-field">
            <span>
              {tr(
                "studio.field.aspect_ratio",
                "Aspect ratio (delivery preset)",
              )}
            </span>
            <select
              value={aspectRatio}
              onChange={(e) => setAspectRatio(e.target.value)}
              data-testid="studio-aspect-select"
              aria-label="Aspect-ratio delivery preset"
            >
              <option value="festival_16x9_4k">
                Festival 4K (3840×2160 @ 24fps)
              </option>
              <option value="youtube_16x9_1080p">
                YouTube 1080p (1920×1080 @ 24fps)
              </option>
              <option value="club_9x16">
                Club / Vertical (1080×1920 @ 30fps)
              </option>
              <option value="ig_9x16">
                Instagram Reels (1080×1920 @ 30fps)
              </option>
              <option value="instagram_1x1">
                Instagram Square (1080×1080 @ 30fps)
              </option>
              <option value="cinema_21x9">
                Cinema 21:9 (5120×2160 @ 24fps)
              </option>
              <option value="vertical_4x5">
                Vertical 4:5 (1080×1350 @ 30fps)
              </option>
            </select>
          </label>
          <label className="studio-field">
            <span>{tr("studio.field.lufs", "Master LUFS target")}</span>
            <select
              value={lufsTarget}
              onChange={(e) => setLufsTarget(e.target.value)}
              data-testid="studio-lufs-select"
              aria-label="LUFS delivery target"
            >
              <option value="club_pa">Club PA (-9 LUFS, -1 dBTP)</option>
              <option value="youtube">YouTube (-14 LUFS)</option>
              <option value="spotify">Spotify (-14 LUFS, -1 dBTP)</option>
              <option value="broadcast">Broadcast EBU R128 (-23 LUFS)</option>
              <option value="cinema">Cinema / theatrical (-20 LUFS)</option>
            </select>
          </label>
          <label className="studio-field">
            <span>
              {tr("studio.field.export_stems", "Export stems for live-mix")}
            </span>
            <input
              type="checkbox"
              checked={exportStems}
              onChange={(e) => setExportStems(e.target.checked)}
              data-testid="studio-stems-toggle"
              aria-label="Export audio stems"
            />
          </label>
          <label className="studio-field studio-field-wide">
            <span>
              {tr(
                "studio.field.audio",
                "Audio WAV for master (defaults to source)",
              )}
            </span>
            <input
              type="text"
              value={audioWavPath}
              onChange={(e) => setAudioWavPath(e.target.value)}
              placeholder={wavPath || "/path/to/track.wav"}
              data-testid="studio-audio-input"
            />
          </label>
        </div>
      </details>

      {/* ---- Stage ribbon ------------------------------------------------- */}
      <div className="studio-console-ribbon">
        <button
          type="button"
          onClick={() => void runStoryboard()}
          disabled={stage !== "idle"}
          className="studio-btn"
          data-testid="studio-btn-storyboard"
        >
          {tr("studio.btn.storyboard", "1 · Storyboard")}
        </button>
        <button
          type="button"
          onClick={() => void runGenerate()}
          disabled={stage !== "idle" || !scenes.length}
          className="studio-btn"
          data-testid="studio-btn-generate"
        >
          {tr("studio.btn.generate", "2 · Generate")}
        </button>
        <button
          type="button"
          onClick={() => void runMaster()}
          disabled={stage !== "idle" || !scenes.length}
          className="studio-btn"
          data-testid="studio-btn-master"
        >
          {tr("studio.btn.master", "3 · Master")}
        </button>
        <button
          type="button"
          onClick={() => void runShip()}
          disabled={stage !== "idle" || !scenes.length}
          className="studio-btn"
          data-testid="studio-btn-ship"
        >
          {tr("studio.btn.ship", "4 · Ship")}
        </button>
      </div>

      {/* ---- Render queue ------------------------------------------------- */}
      <section className="studio-queue" aria-label="Render queue">
        <header className="studio-queue-header">
          <h3 className="studio-queue-title">
            {tr("studio.queue.title", "Render queue")}
          </h3>
          <span
            className="studio-queue-status"
            data-state={
              errorScenes > 0
                ? "error"
                : completedScenes === totalScenes && totalScenes > 0
                  ? "done"
                  : stage === "generate"
                    ? "running"
                    : "queued"
            }
          >
            {totalScenes === 0
              ? tr("studio.queue.empty", "No scenes yet")
              : tr("studio.queue.progress", "{completed} / {total} done{error}")
                  .replace("{completed}", String(completedScenes))
                  .replace("{total}", String(totalScenes))
                  .replace(
                    "{error}",
                    errorScenes > 0 ? ` · ${errorScenes} errors` : "",
                  )}
          </span>
        </header>

        {totalScenes > 0 && (
          <div
            className="studio-queue-progress"
            role="progressbar"
            aria-valuenow={queueProgress}
          >
            <span style={{ width: `${queueProgress}%` }} />
          </div>
        )}

        <ul className="studio-queue-list">
          {scenes.length === 0 && (
            <li className="studio-queue-empty">
              {tr("studio.queue.idle_hint", "Run step 1 to generate scenes.")}
            </li>
          )}
          {scenes.map((s) => (
            <li
              key={s.index}
              className="studio-queue-item"
              data-state={s.status}
            >
              <span className="studio-queue-num">{s.index + 1}</span>
              <span className="studio-queue-name">{s.name}</span>
              <span className="studio-queue-meta">
                {s.sceneType} · {s.camera}
              </span>
              <span className="studio-queue-badge" data-state={s.status}>
                {s.status === "queued" &&
                  tr("studio.queue.badge.queued", "queued")}
                {s.status === "rendering" &&
                  tr("studio.queue.badge.rendering", "rendering")}
                {s.status === "done" && tr("studio.queue.badge.done", "done")}
                {s.status === "error" &&
                  tr("studio.queue.badge.error", "error")}
              </span>
              {s.artifactPath && (
                <span className="studio-queue-artifact" title={s.artifactPath}>
                  {s.artifactPath.split("/").pop()}
                </span>
              )}
              {s.errorMessage && (
                <span className="studio-queue-error">{s.errorMessage}</span>
              )}
            </li>
          ))}
        </ul>
      </section>

      {/* ---- Master deliverables ----------------------------------------- */}
      {masterDeliverables.length > 0 && (
        <section className="studio-master" aria-label="Master deliverables">
          <h3 className="studio-master-title">
            {tr("studio.master.title", "Master deliverables")}
          </h3>
          <ul className="studio-master-list">
            {masterDeliverables.map((d, i) => (
              <li key={i} className="studio-master-item" data-kind={d.kind}>
                <span className="studio-master-kind">{d.kind}</span>
                <span className="studio-master-path">
                  {d.path.split("/").pop()}
                </span>
                {d.bytes > 0 && (
                  <span className="studio-master-bytes">
                    {(d.bytes / 1024 / 1024).toFixed(1)} MB
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---- Ship result -------------------------------------------------- */}
      {shipResult?.final_zip && (
        <section className="studio-ship" aria-label="Ship result">
          <h3 className="studio-ship-title">
            {tr("studio.ship.title", "Shipped bundle")}
          </h3>
          <p className="studio-ship-path">{shipResult.final_zip}</p>
          {shipResult.final_zip_bytes !== undefined && (
            <p className="studio-ship-bytes">
              {(shipResult.final_zip_bytes / 1024 / 1024).toFixed(1)} MB
            </p>
          )}
        </section>
      )}
    </section>
  );
}

export default StudioConsole;
