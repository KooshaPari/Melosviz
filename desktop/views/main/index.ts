/**
 * MelosViz webview (browser side).
 *
 * Communicates with the bun main process via typed Electrobun RPC.
 * Handles the full UI lifecycle: pick WAV → analyze → build plan → render → preview.
 */

import { Electroview } from "electrobun/view";
import type { BunRequests, WebviewRequests } from "../../src/rpc";

// ---------------------------------------------------------------------------
// RPC bootstrap (webview side)
// ---------------------------------------------------------------------------

// defineElectrobunRPC is not re-exported from electrobun/view in 1.18.1;
// use the equivalent Electroview.defineRPC static helper instead.
const rpc = Electroview.defineRPC<
  { bun: BunRequests; webview: WebviewRequests }
>({
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
  qs("#progress-card").classList.add("visible");
  (qs("#progress-bar") as HTMLElement).style.width = `${pct}%`;
  qs("#progress-label").textContent = label;
  qs("#progress-pct").textContent = `${pct}%`;
}

function clearProgress() {
  qs("#progress-card").classList.remove("visible");
}

function setOverlayProgress(pct: number, label: string) {
  (qs("#overlay-bar") as HTMLElement).style.width = `${pct}%`;
  qs("#overlay-label").textContent = label;
  qs("#overlay-pct").textContent = `${pct}%`;
}

function showRenderOverlay(sub: string) {
  qs("#overlay-sub").textContent = sub;
  qs("#render-overlay").classList.add("visible");
  setOverlayProgress(0, "");
}

function hideRenderOverlay() {
  qs("#render-overlay").classList.remove("visible");
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

function markTabHasData(tabId: string) {
  qs(`[data-tab="${tabId}"]`).classList.add("has-data");
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
          return `<span class="j-key">${match}</span>`;
        }
        return `<span class="j-str">${match}</span>`;
      }
      if (/true|false/.test(match)) return `<span class="j-bool">${match}</span>`;
      if (/null/.test(match)) return `<span class="j-null">${match}</span>`;
      return `<span class="j-num">${match}</span>`;
    }
  );
}

// ---------------------------------------------------------------------------
// Inspector renderer (rich JSON tree with syntax highlighting)
// ---------------------------------------------------------------------------

function renderInspector(containerId: string, obj: unknown) {
  const container = qs(`#${containerId}`);
  // Safety: colorizeJson() calls escapeHtml() on the full JSON.stringify output
  // *before* the regex inserts hardcoded <span> tags that we control.  No
  // untrusted value can reach innerHTML as unescaped HTML.  The <pre> wrapper
  // and span class names are static string literals.
  const pre = document.createElement("pre");
  pre.style.cssText = "white-space:pre;overflow-x:auto";
  pre.innerHTML = colorizeJson(obj);
  container.replaceChildren(pre);
  container.classList.remove("inspector-placeholder");
}

// ---------------------------------------------------------------------------
// Waveform mini-viz (sinusoidal bar placeholder)
// ---------------------------------------------------------------------------

function drawWaveformPlaceholder() {
  const canvas = qs<HTMLCanvasElement>("#waveform-canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.offsetWidth || 256;
  const H = 44;
  canvas.width = W;
  canvas.height = H;
  ctx.clearRect(0, 0, W, H);
  const barCount = 72;
  const barW = W / barCount - 1;
  for (let i = 0; i < barCount; i++) {
    const t = i / barCount;
    const h = (Math.sin(t * Math.PI * 3) * 0.4 + 0.55) * H * 0.82;
    const alpha = 0.25 + Math.abs(Math.sin(t * Math.PI * 2)) * 0.4;
    // Interpolate violet → pink across the waveform
    const r = Math.round(76  + (244 - 76)  * t);
    const g = Math.round(64  + (114 - 64)  * t);
    const b = Math.round(176 + (182 - 176) * t);
    ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(i * (barW + 1), (H - h) / 2, barW, h, 2);
    } else {
      ctx.rect(i * (barW + 1), (H - h) / 2, barW, h);
    }
    ctx.fill();
  }
}

// ---------------------------------------------------------------------------
// Scene timeline renderer
// ---------------------------------------------------------------------------

/** Map scene type string to CSS class suffix used by .scene-bar.t-* and .scene-type-badge.t-* */
function sceneTypeCls(type: string): string {
  const t = type.toLowerCase();
  if (t.includes("beat"))                      return "beat";
  if (t.includes("ambient") || t.includes("calm")) return "ambient";
  if (t.includes("drop") || t.includes("peak"))    return "drop";
  if (t.includes("rise") || t.includes("build"))   return "rise";
  if (t.includes("outro") || t.includes("fade"))   return "outro";
  return "default";
}

function renderTimeline(plan: Record<string, unknown>) {
  const rowsEl = qs("#scene-rows");
  rowsEl.innerHTML = "";

  // Support both render plan and render spec shapes
  const scenes =
    (plan.scenes as Array<Record<string, unknown>> | undefined) ??
    ((plan.render_plan as Record<string, unknown> | undefined)?.scenes as
      | Array<Record<string, unknown>>
      | undefined) ??
    [];

  if (!scenes.length) {
    const empty = document.createElement("p");
    empty.style.cssText = "color:var(--mv-text-lo);font-size:11px;font-family:var(--mv-font-mono)";
    empty.textContent = "No scene data found in plan.";
    rowsEl.appendChild(empty);
    qs("#scene-count").textContent = "";
    return;
  }

  qs("#scene-count").textContent = `${scenes.length} scene${scenes.length !== 1 ? "s" : ""}`;

  const maxDur = Math.max(...scenes.map((s) => Number(s.duration_beats ?? 4)));

  scenes.forEach((scene, i) => {
    const typeStr = String(scene.type ?? scene.scene_type ?? "scene");
    // cls is a hardcoded enum value from sceneTypeCls — safe to use in className
    const cls = sceneTypeCls(typeStr);
    const dur = Number(scene.duration_beats ?? 4);
    // durPct is a clamped number — safe to use in style.width
    const durPct = Math.max(6, (dur / maxDur) * 100);
    const desc = String(scene.description ?? scene.name ?? `Scene ${i + 1}`).substring(0, 55);
    const beatLabel = String(scene.start_beat ?? i).padStart(4, " ");
    const tooltip = `beat ${String(scene.start_beat ?? i)} · ${String(dur)} beats · ${typeStr}`;

    // Build every node via DOM APIs so no dynamic content reaches innerHTML.
    const row = document.createElement("div");
    row.className = "scene-row";

    const beatEl = document.createElement("div");
    beatEl.className = "scene-beat";
    beatEl.textContent = beatLabel;

    const barWrap = document.createElement("div");
    barWrap.className = "scene-bar-wrap";
    // data-tip is read back by CSS attr() — it is not parsed as HTML
    barWrap.setAttribute("data-tip", tooltip);

    const bar = document.createElement("div");
    bar.className = `scene-bar t-${cls}`;
    bar.style.width = `${durPct}%`;

    const labelEl = document.createElement("div");
    labelEl.className = "scene-label";

    const badge = document.createElement("span");
    badge.className = `scene-type-badge t-${cls}`;
    badge.textContent = typeStr;

    const descEl = document.createElement("span");
    descEl.className = "scene-desc";
    descEl.textContent = desc;

    const durEl = document.createElement("span");
    durEl.className = "scene-dur";
    durEl.textContent = `${String(dur)}b`;

    labelEl.appendChild(badge);
    labelEl.appendChild(descEl);
    labelEl.appendChild(durEl);
    barWrap.appendChild(bar);
    barWrap.appendChild(labelEl);
    row.appendChild(beatEl);
    row.appendChild(barWrap);
    rowsEl.appendChild(row);
  });

  markTabHasData("timeline");
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
// WAV loaded / unloaded UI transitions
// ---------------------------------------------------------------------------

function showWavLoaded(name: string) {
  (qs<HTMLElement>("#dropzone") as HTMLElement).style.display = "none";
  qs("#wav-loaded-info").classList.add("visible");
  qs("#wav-filename").textContent = name;
  qs("#wav-badge").classList.remove("hidden");
  drawWaveformPlaceholder();
  const sf = qs<HTMLElement>("#status-file");
  sf.textContent = name;
  sf.style.display = "block";
}

// ---------------------------------------------------------------------------
// Copy to clipboard
// ---------------------------------------------------------------------------

async function copyJson(obj: unknown, btnId: string) {
  if (!obj) return;
  const btn = qs<HTMLButtonElement>(`#${btnId}`);
  try {
    await navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
    const orig = btn.textContent ?? "";
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = orig; }, 1800);
  } catch {
    // Clipboard unavailable in restricted webviews — fail silently
  }
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function onPickWav() {
  const picked = await rpc.request.pickFile({ accept: "wav" });
  if (!picked) return;
  wavPath = picked;
  const name = picked.split("/").pop() ?? picked;
  showWavLoaded(name);
  renderSpec = null;
  renderPlan = null;
  setStatus("WAV loaded — run Analyze", "ready");
  syncButtons();
  clearError();
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
    renderInspector("spec-tree", renderSpec);
    markTabHasData("spec");
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
    const json = await rpc.request.buildPlan({
      wavPath: wavPath!,
      outDir: outPath ?? undefined,
    });
    renderPlan = JSON.parse(json) as Record<string, unknown>;
    renderInspector("plan-tree", renderPlan);
    markTabHasData("plan");
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
  showRenderOverlay("Spawning conductor pipeline");
  const outDir = outPath ?? `${document.location.hostname}/MelosViz-output`;
  try {
    setOverlayProgress(15, "Spawning conductor…");
    const result = await rpc.request.renderVideo({ wavPath, outDir });
    setOverlayProgress(100, "Complete");
    setProgress(100, "Render complete");
    setStatus("Render complete", "ready");
    hideRenderOverlay();

    // result is stdout from viz render — look for a .mp4 path
    const mp4Match = result.match(/([^\n\r]+\.mp4)/);
    if (mp4Match) {
      lastVideoPath = mp4Match[1].trim();
      const vid = qs<HTMLVideoElement>("#preview-video");
      vid.src = `file://${lastVideoPath}`;
      vid.classList.remove("hidden");
      qs("#video-placeholder").classList.add("hidden");
      const actions = qs<HTMLElement>("#video-actions");
      actions.classList.remove("hidden");
      actions.style.display = "flex";
      markTabHasData("video");
    }
    switchTab("video");
  } catch (err) {
    hideRenderOverlay();
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
    // Electron/Electrobun-style: file.path is available in webviews with file access
    const filePath = (file as File & { path?: string }).path;
    if (filePath) {
      wavPath = filePath;
      showWavLoaded(file.name);
      renderSpec = null;
      renderPlan = null;
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

  qs("#btn-change-wav").addEventListener("click", onPickWav);
  qs("#btn-pick-out").addEventListener("click", onPickOut);
  qs("#btn-analyze").addEventListener("click", onAnalyze);
  qs("#btn-build").addEventListener("click", onBuildPlan);
  qs("#btn-render").addEventListener("click", onRenderVideo);
  qs("#btn-dismiss-error").addEventListener("click", clearError);
  qs("#btn-copy-spec").addEventListener("click", () => copyJson(renderSpec, "btn-copy-spec"));
  qs("#btn-copy-plan").addEventListener("click", () => copyJson(renderPlan, "btn-copy-plan"));

  qs("#btn-reveal-video").addEventListener("click", async () => {
    if (lastVideoPath) await rpc.request.revealInFinder({ filePath: lastVideoPath });
  });

  qs("#btn-re-render").addEventListener("click", onRenderVideo);

  setStatus("Ready", "ready");
  syncButtons();
});
