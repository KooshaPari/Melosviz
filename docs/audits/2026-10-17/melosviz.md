# Melosviz — master audit

**Audit date:** 2026-10-17. **Repo:** `KooshaPari/Melosviz` (stable `1262466303`). **Local clone:** `/Users/kooshapari/CodeProjects/Phenotype/repos/Melosviz`. **Read-only.**

## IDENTITY
Music-visualization authoring + rendering product (Tauri desktop + web frontend + Python backend; renderSpec v2 pipeline). Single owner, v0.1.0 released 2026-09-17 (`Melosviz.app` + `.dmg`).

## INTENT
Author an actual synchronized A/V visualization from a real licensed track through a real render backend, then reopen/edit/re-export it with honest backend-state labels. Per DOSSIER §1 + §8: "installed product produces and edits a real useful synchronized visualization, with honest backend modes" — not a placeholder of one.

## CURRENT STATE
Atlas (AGENT-PROMPT/STATE/DOSSIER/FEDERATION/NEXT-ACTIONS/PROOF-AND-GRADE) is consistent and converged at v1.4. Local HEAD = `ab77c88391` (2026-09-18, docs-5 rebrand), past the 2026-09-17 v0.1.0 tag cited in atlas. Worktree is dirty (17 modified files: branding/CI/docs, no untracked; `git diff --stat` = 32/32). Branch = `main`. Backend tests 1448/1450 and web tests 243/246 in STATE are **carry-forward evidence**, not fresh receipts in this snapshot.

## CODE REALITY
- ComfyUI is the **primary** renderer, but it has a documented "offline placeholder" path: `backend/src/melosviz/render/comfyui_adapter.py:226` `_generate_placeholder_clip` writes a solid-color FFmpeg MP4 explicitly labeled placeholder; `:605, :688` early `return []` paths hand back empty lists/job-specs.
- WGPU adapter is a subprocess bridge to a Rust binary that **may not be built**: `backend/src/melosviz/render/wgpu_adapter.py:80-153` raises `WgpuNotAvailableError` when `melosviz-render` binary is missing (the `is_wgpu_available()` function reports `False` in headless/test envs).
- After Effects, Cinema 4D, Unreal, DaVinci, Media Encoder, Firefly adapters all expect licensed external binaries/templates; `aftereffects_adapter.py:99` documents a "Default AEP project path placeholder (operator sets real path via env/config)". Firefly (`firefly_adapter.py:3`) is explicitly a "job-spec-only" adapter by design — it does not call the API. `blender_exporter.py` (889 LOC) is the heaviest adapter and the closest to runnable in a CI box with `blender --background`.
- App.tsx is wired for the previously-skipped pieces (NEXT-ACTIONS item 5 partly landed): `web/src/App.tsx:19` imports `FullscreenToggle`, `:88, :223, :291` use the fullscreen state — the 3 "skipped spec-first" tests may be ready to turn green on next rerun. Two siblings (playback transport, scene-jump panel) remain unconfirmed grep hits.
- 9 render adapters totaling ~3,400 LOC; bridge `backend/src/melosviz/bridge/server.py` is 1,103 LOC and provides the only stable route to Python services. CLI entry `backend/src/melosviz/cli/main.py` plus `partial_rerender.py` are the operational surface for ATLAS A2 (real creative output).

## STUB/MOCK/MVP-LAZINESS INVENTORY
- ComfyUI placeholder generator (FFmpeg solid-color MP4) — `comfyui_adapter.py:226-295`; canonical offline rehearsal, **must not pass acceptance** as production.
- ComfyUI early `return []` empty-output paths — `comfyui_adapter.py:605, :688`; fail-loud required by `CUR-1262466303-A1` is not yet enforced.
- Firefly adapter — pure job-spec generator, no network/API call (`firefly_adapter.py` whole-module docstring).
- After Effects default AEP template — `aftereffects_adapter.py:99` placeholder; missing real project file.
- WGPU subprocess binary dependency — `wgpu_adapter.py:80-153`; the Rust `melosviz-render` binary is a precondition that isn't declared as a release/install dependency.
- Skipped web spec-first tests (FullscreenToggle, playback transport, scene-jump panel) — only Fullscreen is wired into `App.tsx`; the other 2 still outstanding per NEXT-ACTIONS item 5.
- No fresh test receipt in this snapshot — the 1448/1450 + 243/246 counts are carried from the 2026-09-17 snapshot.

## FWD PATH TO FINISH
1. **Enforce backend-mode labels (CUR-1262466303-A1)**: type-tag every render return as `live_render | placeholder | job_spec_only | unavailable | failed`; reject the placeholder path from any "ship" gate; already substantially in code, needs the type contract + acceptance test.
2. **Real creative render (CUR-1262466303-A2)**: stand up a GPU-equipped ComfyUI box (or document the box), run a licensed track through, inspect A/V sync + frame pacing, attach the artifact + sync-error measurement to STATE.md.
3. **Clean-machine install smoke (NEXT-ACTIONS item 4)**: download the published v0.1.0 `.dmg` + `.tar.gz` on a non-repo box, launch the .app, exercise a basic workflow; record CPU/mem/wall-time + any signing/gatekeeper issues.
4. **Wire the remaining 2 skipped web tests (Fullscreen done; scene-jump + playback transport still pending)** and re-run the web suite to prove 246/246 with no regression.
5. **Re-qualify test receipts**: re-run both suites from a clean checkout and refresh the count + last-green SHA in STATE.md; never report counts older than the snapshot.

## TIME-TO-FINISH ESTIMATE
**2-3 weeks** for items 1-4 above at one owner-chat pace (~5 days for A1 acceptance + A2 GPU run, ~2 days for clean-machine install, ~1-2 days for wire+rerun, ~1 day for STATE refresh). Faster than that means the live-backend proof is being hand-waved; slower means an external binary (ComfyUI server / DAW license) is blocking.

## SUNSET/KEEP CALL
**KEEP.** The product has a real niche (music-specific visualization with a beat-synced RenderSpec), shipped v0.1.0 with installable desktop artifacts, and a substantive render-adapter layer that already reuses FFmpeg/Blender as the dossier requires. The atlas points are diagnosed, not abandoned. Sunset would waste the shipped substrate; the correct move is A1/A2/A4 against the existing tree.

## CONFIDENCE
**High** on identity, branch, dirty worktree state, render-stub inventory, and forward path. **Medium-Low** on test counts (carry-forward, not re-measured) and on whether a real ComfyUI server exists at the operator's box (not verified, no pilot winner in atlas).

**Validation performed (this audit, read-only):**
- Walked all 3 canonical sources (AGENT-PROMPT.md, STATE.md, DOSSIER.md) plus NEXT-ACTIONS.md, FEDERATION.md.
- `git log -1`, `git status --short`, `git rev-parse --abbrev-ref HEAD` on local clone.
- `wc -l` on all 6 large render adapters + `bridge/server.py` + `web/src/App.tsx`.
- Grep for `TODO|FIXME|XXX|stub|placeholder|raise NotImplementedError` across `backend/src/melosviz/render/*.py`; targeted grep on `return []` paths in ComfyUI.
- Grep on `web/src/App.tsx` for `fullscreen|playback transport|scene jump` to verify NEXT-ACTIONS item 5 progress.
- Did NOT run any test suite, build, or `tauri` command; did NOT modify or push anything.
