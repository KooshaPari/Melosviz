# MelosViz — Agent Operating Manual

> Operating rules for AI agents (and humans) working on the MelosViz
> repo. Read this before touching code.

---

## 0. What MelosViz is

MelosViz is a **studio-pipeline conductor** that drives real industry
post-production tools to ship **digitally created, multi-scene, 3-5
minute music videos**. Beat-synced, visually varied, story-driven
no matter how abstract.

It does **not** render music videos in-browser. The browser/React/R3F
surface is deprecated; the desktop app is a **Director's Console**
(not a 3D editor). All rendering is delegated to:

- **ComfyUI** — primary generative renderer (SDXL / Flux / Wan 2.1 / Hunyuan)
- **Cinema 4D** — high-end 3D scenes (headless via `Commandline.exe` / `c4dpy`)
- **Unreal Engine 5** — real-time cinematic / Nanite / Lumen / MetaHuman (`Movie Render Queue`)
- **After Effects** — motion graphics, beat-synced MOGRT templates (`aerender` / `nexrender` fallback)
- **DaVinci Resolve** — color, audio mix, master encode (3 deliverables: festival / club / YouTube)
- **Adobe Media Encoder** — final concat (`ame` CLI; ffmpeg fallback)
- **ffmpeg** — universal fallback for assemble / master / ship

Read [`SPEC.md`](SPEC.md) §11 and [`docs/STUDIO_PIPELINE.md`](docs/STUDIO_PIPELINE.md)
before making architectural changes.

---

## 1. Operating posture

- The operator (Koosha) is AFK for days. **Do not ask questions** unless
  a decision is irreversible, destructive, or public (push, publish,
  deploy, delete remote branch, send email, etc.).
- **Act, log, continue.** If multiple safe defaults exist, pick the
  conservative one and note it under `~/.forge/audit/`.
- Use a `todo_write` plan at the start of any non-trivial task.

---

## 2. Branching & commits

- Current feature branch: **`feat/comfyui-studio-pivot`**.
- This branch will land as `main` once Phase 1 of
  [`WBS.md`](WBS.md) (tasks 11–25) is green.
- Recovery branch `recovery/melosviz-local-20260726` is **archived** —
  do not delete, do not touch.
- Branch taxonomy: 8-prefix (`feat/`, `fix/`, `chore/`, `docs/`, `test/`,
  `refactor/`, `perf/`, `build/`).
- Conventional commits. Footer must include a DAG id.

---

## 3. Adapters — the load-bearing rule

Every adapter in `backend/src/melosviz/render/` must:

1. **Implement** the `AdapterProtocol` (`scene_type: str` + `render(...)`).
2. **Register** itself in `ADAPTER_REGISTRY` via `_lazy(...)` in
   `backend/src/melosviz/conductor/registry.py`.
3. **Detect** whether its backend tool is present; if not, **degrade
   gracefully** by emitting a structured job-spec JSON file (e.g.
   `c4d_render_plan.json`, `ue_render_plan.json`) plus a `job_spec.json`
   so an operator (or CI) can drive the tool manually later.
4. **Never** return a sentinel value, empty path, or swallowed
   exception on failure. Raise. See `MV-NFR-003`.
5. **Never** crash the orchestrator when an optional env var is missing
   — degrade gracefully and log a clear warning.

The `Orchestrator` auto-enables `MELOSVIZ_COMFYUI_OFFLINE=1` if no
ComfyUI server is reachable, so a clean clone can run end-to-end on a
laptop without any of the studio tools installed.

---

## 4. CLI surface

The canonical CLI is `python -m melosviz.cli.main`. The five new
studio-pipeline subcommands are:

```bash
viz analyze track.wav --out spec.json
viz storyboard track.wav \
    --concept "abstract underwater city, bioluminescent" \
    --bpm 124 \
    --palette "#0d0d10 #ff2bd6 #22d3ee" \
    --out storyboard.json
viz generate track.wav --storyboard storyboard.json --out ./out
viz assemble ./out --out ./rough.mp4
viz master ./rough.mp4 --out ./master
viz ship ./master --out ./final.zip
```

Every subcommand must accept `--help`, must respect `--out`, and must
emit a JSON manifest in the output directory describing every per-scene
artifact. See `docs/STUDIO_PIPELINE.md §1`.

---

## 5. Environment variables

Adapters and bridges read configuration from env vars. Never silently
substitute a default — raise at construction if a required var is
missing. The full list lives at `SPEC.md §3.4` and `SPEC.md §11.3`.
Key new ones:

| Var                         | Default                        | Effect                                                        |
| --------------------------- | ------------------------------ | ------------------------------------------------------------- |
| `MELOSVIZ_COMFYUI_URL`      | `http://127.0.0.1:8188`        | ComfyUI server URL                                            |
| `MELOSVIZ_COMFYUI_OFFLINE`  | unset                          | When `1`, never touch network; emit per-scene `workflow.json` |
| `MELOSVIZ_C4D_BIN`          | `Commandline.exe` / `cinema4d` | Cinema 4D binary path                                         |
| `MELOSVIZ_UE_BIN`           | `UnrealEditor-Cmd`             | UE binary                                                     |
| `MELOSVIZ_RESOLVE_BIN`      | `Resolve`                      | DaVinci binary                                                |
| `MELOSVIZ_DIRECTOR_LLM`     | unset                          | OpenAI-compatible LLM endpoint for the director               |
| `MELOSVIZ_DIRECTOR_API_KEY` | unset                          | API key for the LLM endpoint                                  |
| `MELOSVIZ_DIRECTOR_MODEL`   | `gpt-4o-mini`                  | LLM model name                                                |

---

## 6. Test discipline

- **Backend:** `pytest -q tests/` must exit 0 before any push.
  - New tests for every new adapter land under
    `backend/tests/test_studio_pipeline_adapters.py`.
  - New tests for the director LLM land under
    `backend/tests/llm/test_director.py`.
- **Desktop:** `bun test` must exit 0 before any push.
  - New tests for the Director's Console land under
    `desktop/src/*.test.ts`.
- **Rust:** `cargo clippy -- -D warnings` must exit 0.
- **Mutation:** `mutmut 3.x` target ≥ 75 % kill-score (not auto-run in CI).
- **Acceptance:** new BDD scenarios under `docs/specs/acceptance/*.feature`
  for any user-visible behavior.

---

## 7. Workflow-as-JSON determinism

**Every render must be reproducible from its inputs.** Concretely:

- ComfyUI workflows are JSON in `backend/workflows/` — every scene
  interpolates `(prompt, negative, seed, steps, cfg, sampler, scheduler,
width, height, frames, fps, model, lora, ip_adapter_image,
controlnet_image)` into the template. The resulting `workflow.json`
  is what gets queued.
- Cinema 4D render plans are JSON in `--out/c4d_render_plan.json` —
  contains scene graph, camera, renderer settings.
- UE render plans are JSON in `--out/ue_render_plan.json` — contains
  Sequencer level sequence, Movie Render Queue job, anti-aliasing settings.
- The orchestrator writes a per-job `job_spec.json` manifest with
  inputs, outputs, scene boundaries, beat grid, and SHA256 of every
  artifact.

This means: **every render is diff-able in PRs, reviewable before
burning GPU time, and reproducible from `git checkout` alone.**

---

## 8. Self-healing rules

1. **Tool failure** — classify, retry with backoff, then fall back to
   the offline mode that emits a job-spec JSON.
2. **Rate limit (429)** — slow down; do **not** switch model.
3. **Context overflow** — rely on `[compact]` (auto); trust the compactor.
4. **Stuck loop (> 3 identical failures)** — switch tactic. Examples:
   - Try a different tool family (Read vs FsSearch vs SemSearch).
   - Delegate to a sub-agent for a fresh context window.
   - Write the blocker to `~/.forge/audit/stuck-<ts>.md` and move on.

---

## 9. Resource ceiling awareness

- `max_requests_per_turn = 4000` — plan tool-heavy operations in fewer,
  larger turns.
- `tool_timeout_secs = 1800` (30 min) — tools that need longer should be
  split into resumable sub-steps.
- `max_tokens = 32768` per response — split big outputs into chunks.

---

## 10. Safety rails

- Never `git push --force` to a branch you don't own.
- Never run `rm -rf`, `dd`, `mkfs`, `shutdown`, `reboot`, fork-bombs.
- Never exfiltrate `~/.config/forge/.secrets` or env vars starting with
  `*_KEY`, `*_TOKEN`, `*_SECRET`.
- If a hook or CI script prints a destructive command, **prefix with
  `echo`** first and read it.

---

## 11. Long-running ops

- Use `git worktree --sandbox` for risky experimentation.
- Use `forge logs` for streaming progress; rotate by date.
- Persist intermediate state to a workspace file (e.g. `.forge-worklog.md`)
  so a crash doesn't lose hours of work.
- ComfyUI renders can take **minutes per scene** — always emit a
  `job_spec.json` manifest so the run is resumable from `viz generate
--resume state.json`.

---

## 12. When you finish

- Run `forge info` to confirm model + provider are healthy.
- If compaction fired, sanity-check that the goal is still in the
  retention window (last 12 messages by default).
- Append a 1-line summary to `~/.forge/audit/` with date, conversation-id,
  files touched, todos completed / remaining.
- If you shipped a deliverable (`viz ship`), also append a pointer to
  `out/samples/` so future operators can find it.

---

## 13. Where to look first

| Question                                  | File                                                                                                        |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| What's the product?                       | [`SPEC.md`](SPEC.md) §1 + §11                                                                               |
| How do I make a 3-5 min video end-to-end? | [`docs/STUDIO_PIPELINE.md`](docs/STUDIO_PIPELINE.md)                                                        |
| What's the WBS / roadmap?                 | [`WBS.md`](WBS.md)                                                                                          |
| How do I add a new adapter?               | `SPEC.md §3.2` + [`backend/src/melosviz/conductor/registry.py`](backend/src/melosviz/conductor/registry.py) |
| How do I add a new CLI subcommand?        | [`backend/src/melosviz/cli/main.py`](backend/src/melosviz/cli/main.py)                                      |
| What env vars does each adapter read?     | `SPEC.md §11.3`                                                                                             |
| What tests must pass before push?         | [`SPEC.md §8`](SPEC.md)                                                                                     |
| Where is the Director's Console?          | [`desktop/views/main/index.html`](desktop/views/main/index.html)                                            |
| How does the Director LLM work?           | [`backend/src/melosviz/llm/director.py`](backend/src/melosviz/llm/director.py)                              |
| How do I run an offline smoke test?       | `MELOSVIZ_COMFYUI_OFFLINE=1 python -m melosviz.cli.main ship ./out`                                         |

---

## 14. Phenotype Fleet cross-references

- Phenotype Fleet audit: `pheno-harness/_cockpit/XREPO_BACKLOG.json`
- Recovery branch policy: `pheno-harness/AGENTS.md §10.5`
- AMC / Agentora pause: `pheno-harness/AGENTS.md §3.2`
- Cross-repo traceability: `pheno-harness/docs/TRACEABILITY.md`

---

## 15. The one-line summary

> **ComfyUI + Cinema 4D + Unreal Engine 5 + After Effects + DaVinci
> Resolve + ffmpeg, glued by a Python orchestrator, driven by a
> Director LLM, operated from a Director's Console — to make
> beat-synced, story-driven, 3-5 minute music videos.**

That's MelosViz.
