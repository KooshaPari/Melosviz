/**
 * MelosViz webview (browser side).
 *
 * Communicates with the bun main process via typed Electrobun RPC.
 * Handles the full UI lifecycle: pick WAV → analyze → build plan → render → preview.
 */

import { defineElectrobunRPC } from "electrobun/view";
import type { BunRequests, WebviewRequests } from "../../src/rpc";

// ---------------------------------------------------------------------------
// RPC bootstrap (webview side)
// ---------------------------------------------------------------------------

const rpc = defineElectrobunRPC<
  { bun: BunRequests; webview: WebviewRequests }
>("webview", {
  handlers: {
    requests: {},
  },
});

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let wavPath: string | null = null;
let outPath: string | null = null;
let renderSpec: Record<string, unknown> | null = null;
let renderPlan: Record<string, unknown> | null = null;
let lastVideoPath: string | null = null;

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function qs<T extends Element>(selector: string): T {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`[MelosViz UI] selector not found: ${selector}`);
  return el;
}

function setStatus(msg: string, state: "ready" | "busy" | "error" = "ready") {
  qs("#status-text").textContent = msg;
  const dot = qs("#status-dot");
  dot.className = "";
  dot.classList.add(state);
}

function showError(err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  qs("#error-box").textContent = msg;
  qs("#error-card").classList.remove("hidden");
  setStatus("Error", "error");
}

function clearError() {
  qs("#error-card").classList.add("hidden");
}

function setProgress(pct: number, label: string) {
  qs("#progress-card").classList.remove("hidden");
  (qs("#progress-bar") as HTMLElement).style.width = `${pct}%`;
  qs("#progress-label").textContent = label;
}

function clearProgress() {
  qs("#progress-card").classList.add("hidden");
}

function showPipelineView() {
  qs("#welcome").style.display = "none";
  qs<HTMLElement>("#pipeline-view").classList.add("active");
}

function switchTab(tabId: string) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
  qs(`[data-tab="${tabId}"]`).classList.add("active");
  qs(`#tab-${tabId}`).classList.add("active");
}

// ---------------------------------------------------------------------------
// JSON colorizer
// ---------------------------------------------------------------------------

/** Escape characters that are meaningful in HTML so they render as literals. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Render a JSON value as syntax-highlighted HTML.
 *
 * Security: JSON.stringify output is HTML-escaped *before* any span tags are
 * inserted, so values from untrusted sources (file paths, backend strings)
 * cannot inject markup.
 */
function colorizeJson(obj: unknown): string {
  // First produce the pretty-printed text, then escape all HTML-special chars.
  const escaped = escapeHtml(JSON.stringify(obj, null, 2));

  // The regex runs on the already-escaped string; the only new characters we
  // add are the safe, hard-coded <span> tags we control.
  return escaped.replace(
    /(&quot;(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\&])*&quot;(\s*:)?|\b(true|false|null)\b|-?\d+(\.\d+)?([eE][+-]?\d+)?)/g,
    (match) => {
      if (match.startsWith("&quot;")) {
        if (match.endsWith(":")) {
          return `<span class="json-key">${match}</span>`;
        }
        return `<span class="json-str">${match}</span>`;
      }
      if (/true|false/.test(match)) return `<span class="json-bool">${match}</span>`;
      if (/null/.test(match)) return `<span class="json-null">${match}</span>`;
      return `<span class="json-num">${match}</span>`;
    }
  );
}

// ---------------------------------------------------------------------------
// Waveform mini-viz (draws a silent gray bar as placeholder)
// ---------------------------------------------------------------------------

function drawWaveformPlaceholder() {
  const canvas = qs<HTMLCanvasElement>("#waveform-canvas");
  canvas.classList.remove("hidden");
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.offsetWidth || 268;
  const H = canvas.offsetHeight || 56;
  canvas.width = W;
  canvas.height = H;
  ctx.clearRect(0, 0, W, H);
  const barCount = 80;
  const barW = W / barCount - 1;
  for (let i = 0; i < barCount; i++) {
    const h = (Math.sin(i * 0.4) * 0.4 + 0.5) * H * 0.7;
    const alpha = 0.3 + Math.sin(i * 0.3) * 0.2;
    ctx.fillStyle = `rgba(124,106,247,${alpha})`;
    ctx.fillRect(i * (barW + 1), (H - h) / 2, barW, h);
  }
}

// ---------------------------------------------------------------------------
// Scene timeline renderer
// ---------------------------------------------------------------------------

function renderTimeline(plan: Record<string, unknown>) {
  const container = qs("#timeline-container");
  container.innerHTML = "";

  // Support both render plan and render spec shapes
  const scenes =
    (plan.scenes as Array<Record<string, unknown>> | undefined) ??
    ((plan.render_plan as Record<string, unknown> | undefined)?.scenes as
      | Array<Record<string, unknown>>
      | undefined) ??
    [];

  if (!scenes.length) {
    container.innerHTML = `<p style="color:var(--text-lo);font-size:13px">No scene data found in plan.</p>`;
    return;
  }

  scenes.forEach((scene, i) => {
    const row = document.createElement("div");
    row.className = "scene-row";

    const beat = document.createElement("div");
    beat.className = "scene-beat";
    beat.textContent = `${String(scene.start_beat ?? i).padStart(4, " ")}`;

    const barWrap = document.createElement("div");
    barWrap.className = "scene-bar-wrap";

    const bar = document.createElement("div");
    bar.className = "scene-bar";
    // Width proportional to duration_beats
    const dur = Number(scene.duration_beats ?? 4);
    const maxDur = Math.max(...scenes.map((s) => Number(s.duration_beats ?? 4)));
    bar.style.width = `${Math.max(5, (dur / maxDur) * 100)}%`;

    const label = document.createElement("div");
    label.className = "scene-label";

    const typeSpan = document.createElement("span");
    typeSpan.className = "scene-type";
    typeSpan.textContent = String(scene.type ?? scene.scene_type ?? "scene");

    label.appendChild(typeSpan);
    label.appendChild(
      document.createTextNode(String(scene.description ?? scene.name ?? `Scene ${i + 1}`).substring(0, 60))
    );

    barWrap.appendChild(bar);
    barWrap.appendChild(label);
    row.appendChild(beat);
    row.appendChild(barWrap);
    container.appendChild(row);
  });
}

// ---------------------------------------------------------------------------
// Button enable/disable
// ---------------------------------------------------------------------------

function syncButtons() {
  (qs("#btn-analyze") as HTMLButtonElement).disabled = !wavPath;
  (qs("#btn-build") as HTMLButtonElement).disabled = !renderSpec;
  (qs("#btn-render") as HTMLButtonElement).disabled = !renderPlan;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function onPickWav() {
  const picked = await rpc.request.pickFile({ accept: "wav" });
  if (!picked) return;
  wavPath = picked;
  const name = picked.split("/").pop() ?? picked;
  qs("#wav-path").textContent = name;
  qs("#wav-path").classList.remove("hidden");
  drawWaveformPlaceholder();
  renderSpec = null;
  renderPlan = null;
  setStatus("WAV loaded — run Analyze", "ready");
  syncButtons();
}

async function onPickOut() {
  const picked = await rpc.request.pickDirectory({});
  if (!picked) return;
  outPath = picked;
  qs("#out-path").textContent = picked;
}

async function onAnalyze() {
  if (!wavPath) return;
  clearError();
  setStatus("Analyzing…", "busy");
  setProgress(10, "Analyzing WAV…");
  showPipelineView();
  try {
    const json = await rpc.request.analyzeWav({ wavPath });
    renderSpec = JSON.parse(json) as Record<string, unknown>;
    qs("#spec-tree").innerHTML = colorizeJson(renderSpec);
    setProgress(100, "Analysis complete");
    setStatus("Analysis complete", "ready");
    switchTab("spec");
    syncButtons();
  } catch (err) {
    showError(err);
  } finally {
    setTimeout(clearProgress, 2000);
  }
}

async function onBuildPlan() {
  if (!renderSpec) return;
  clearError();
  setStatus("Building render plan…", "busy");
  setProgress(20, "Building render plan…");
  try {
    const defaultOut = `${(outPath ?? `${Bun?.env?.HOME ?? "~"}/MelosViz-output`)}`;
    const json = await rpc.request.buildPlan({
      wavPath: wavPath!,
      outDir: outPath ?? undefined,
    });
    renderPlan = JSON.parse(json) as Record<string, unknown>;
    qs("#plan-tree").innerHTML = colorizeJson(renderPlan);
    renderTimeline(renderPlan);
    setProgress(100, "Render plan built");
    setStatus("Render plan ready", "ready");
    switchTab("timeline");
    syncButtons();
  } catch (err) {
    showError(err);
  } finally {
    setTimeout(clearProgress, 2000);
  }
}

async function onRenderVideo() {
  if (!renderPlan || !wavPath) return;
  clearError();
  setStatus("Rendering video…", "busy");
  setProgress(5, "Starting render pipeline…");
  const outDir = outPath ?? `${document.location.hostname}/MelosViz-output`;
  try {
    setProgress(15, "Spawning conductor…");
    const result = await rpc.request.renderVideo({ wavPath, outDir });
    setProgress(100, "Render complete");
    setStatus("Render complete", "ready");

    // result is stdout from viz render — look for a .mp4 path
    const mp4Match = result.match(/([^\n\r]+\.mp4)/);
    if (mp4Match) {
      lastVideoPath = mp4Match[1].trim();
      const vid = qs<HTMLVideoElement>("#preview-video");
      vid.src = `file://${lastVideoPath}`;
      vid.classList.remove("hidden");
      qs("#video-placeholder").classList.add("hidden");
      qs("#video-actions").classList.remove("hidden");
      (qs("#video-actions") as HTMLElement).style.display = "flex";
    }
    switchTab("video");
  } catch (err) {
    showError(err);
  } finally {
    setTimeout(clearProgress, 3000);
  }
}

// ---------------------------------------------------------------------------
// Drag-and-drop
// ---------------------------------------------------------------------------

function initDropzone() {
  const dz = qs<HTMLElement>("#dropzone");

  dz.addEventListener("click", onPickWav);

  dz.addEventListener("dragover", (e) => {
    e.preventDefault();
    dz.classList.add("drag-over");
  });

  dz.addEventListener("dragleave", () => dz.classList.remove("drag-over"));

  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("drag-over");
    const files = (e as DragEvent).dataTransfer?.files;
    if (!files?.length) return;
    const file = files[0];
    if (!file.name.toLowerCase().endsWith(".wav")) {
      showError("Only WAV files are supported.");
      return;
    }
    // Electron-style: file.path is available in webviews with file access
    const filePath = (file as File & { path?: string }).path;
    if (filePath) {
      wavPath = filePath;
      qs("#wav-path").textContent = file.name;
      qs("#wav-path").classList.remove("hidden");
      drawWaveformPlaceholder();
      setStatus("WAV loaded — run Analyze", "ready");
      syncButtons();
    }
  });
}

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------

function initTabs() {
  document.querySelectorAll<HTMLButtonElement>(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      if (tab) switchTab(tab);
    });
  });
}

// ---------------------------------------------------------------------------
// Wire event listeners
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  initDropzone();
  initTabs();

  qs("#btn-pick-wav").addEventListener("click", onPickWav);
  qs("#btn-pick-out").addEventListener("click", onPickOut);
  qs("#btn-analyze").addEventListener("click", onAnalyze);
  qs("#btn-build").addEventListener("click", onBuildPlan);
  qs("#btn-render").addEventListener("click", onRenderVideo);
  qs("#btn-dismiss-error").addEventListener("click", clearError);

  qs("#btn-reveal-video").addEventListener("click", async () => {
    if (lastVideoPath) await rpc.request.revealInFinder({ filePath: lastVideoPath });
  });

  setStatus("Ready", "ready");
  syncButtons();
});
