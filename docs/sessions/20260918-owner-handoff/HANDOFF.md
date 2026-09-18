# Melosviz — Owner Session Handoff

**Written:** 2026-09-18 (Pacific) · **Author session:** Jcode on `Kooshas-Laptop` · **Handoff to:** new owner session running on the operator's desktop

This document transfers ownership of `KooshaPari/Melosviz` and all future work. It is written to be read **before touching anything**. Everything here is either verified-with-date or explicitly marked UNKNOWN. Do not upgrade an UNKNOWN to a pass.

---

## 0. Read order

1. This file (top to bottom).
2. `/Users/kooshapari/CodeProjects/docs/docs-5/products/Melosviz/START-HERE.md` (authority entrypoint, if reachable).
3. `/Users/kooshapari/CodeProjects/docs/docs-5/products/Melosviz/STATE.md` (dated current state).
4. `/Users/kooshapari/CodeProjects/docs/docs-5/products/Melosviz/NEXT-ACTIONS.md` (bounded work, acceptance criteria).
5. `/Users/kooshapari/CodeProjects/docs/docs-5/products/Melosviz/DOSSIER.md` + `AGENT-PROMPT.md`.

`DOSSIER.md` and `PILOT.json` are context, **not** proof. Prior audit verdicts are dated evidence, not a fresh pass.

---

## 1. Machine topology and how to reach this host

The new session runs on the operator's **desktop**. The live repo, venv, and release artifacts currently exist on **this laptop** (`Kooshas-Laptop`). SSH over when a task needs local-only state (dirty files, venv, GPU, Tauri build, ffmpeg renders).

| Fact | Value | Verified |
|---|---|---|
| Hostname / ComputerName | `Kooshas-Laptop.local` / "Koosha's Laptop" | 2026-09-18 |
| Local user | `kooshapari` | 2026-09-18 |
| Tailscale node | `kooshas-laptop` = `100.112.14.98` (online) | 2026-09-18 |
| LAN address | `192.168.1.23` (en0) | 2026-09-18 |
| sshd | listening on port 22 (loopback verified) | 2026-09-18 |
| Tailscale SSH | UNKNOWN — not confirmed enabled | — |

Connect:

```bash
ssh kooshapari@100.112.14.98        # Tailscale, preferred
ssh kooshapari@192.168.1.23         # same LAN only
ssh kooshapari@Kooshas-Laptop.local # mDNS on the same LAN
```

Tailnet peers observed at handoff: `cachyos` (100.97.123.10, offline 41d), `kooshapari-desk-1` (100.84.189.31, offline 136d), `kooshapari-desk-2` (100.122.128.84, offline 16d), `iphone182` (online). **The desktop's own tailnet node was offline at handoff** — if SSH from the desktop fails, confirm Tailscale is up on the desktop first. This laptop being online is the dependable direction.

### Preferred working model

- **Do repo work where the repo is.** Clone/fetch from GitHub on the desktop for read and light edits, but run tests, Tauri builds, and media renders here — the venv, ffmpeg, and toolchain are provisioned here.
- **Do not duplicate the checkout** across machines without `git fetch` first; the repo has 17 uncommitted files owned by other sessions (see §8).
- Heavy work (GPU render, large media) belongs on the machine with the GPU. This laptop is 1TB/16GB/1 iGPU; the stronger box (5.5TB/64GB/2 GPUs) is a separate host. Decide placement before starting heavy work and record which placement served the job.

---

## 2. Repository identity and locations

| Item | Value |
|---|---|
| Repo path (this host) | `/Users/kooshapari/CodeProjects/Phenotype/repos/Melosviz` |
| Remote | `git@github.com:KooshaPari/Melosviz.git` (SSH) |
| Default branch | `main` |
| HEAD at handoff | `84468ce` |
| GitHub repo ID | `1262466303` |
| Live docs-5 dossier | `/Users/kooshapari/CodeProjects/docs/docs-5/products/Melosviz/` |
| Backend venv | `backend/.venv` (Python 3.11.14) |
| Tags present | `v0.1.0` (released), `v0.1.1` (`316bac0`, ancestor of main), `v0.2.0` (`5835da3`, on remote — release assets UNVERIFIED) |

**Correction to prior reviews:** an earlier review asserted this worktree "is not a git repository." That is **wrong**. `git rev-parse --show-toplevel` resolves to this path and the remote is live. Treat that claim as retracted.

**Note on release gap:** `v0.2.0` is tagged on the remote but this handoff does not verify its contents, assets, or notes. Verify before relying on it.

---

## 3. Ownership and governance contract

You now own this repository's work. Constraints that are not optional:

| Rule | Consequence |
|---|---|
| **One owner chat per repository** | Do not spawn a second permanent owner chat or a 10-seat topology. |
| **No history rewrite** | `git push --force`, `git reset --hard`, `git clean -fd`, `git branch -D` are blocked. Fix forward. |
| **Ledger trailers** | Commits carry `tx-agent`, `tx-validated`, plus `tx-scope`/`tx-intent` where useful. |
| **Preserve other sessions' work** | 17 dirty files belong to other sessions (§8). Never `checkout`/`stash`/discard them. |
| **Honest evidence states** | Keep inventory / candidate / local / hosted / delivered / installed / adopted separate. A green local suite is not installation, not adoption, not user acceptance. |
| **Dated evidence** | Historical results keep their observation date and never silently become a fresh pass. |
| **No fabricated progress** | Report UNKNOWN where evidence is missing. No invented percentages, ETAs, or completion claims. |
| **Screenshots** | No whole-desktop or pre-existing-process capture. Isolated agent-started processes only. |
| **Retired/held scope** | RepoLedger stays retired. ResearchLedger goes last. Honor sponsor account-name holds. |

Authority: source truth belongs to Git; repo identity to observed GitHub state; native execution truth to a qualified runner with a retained receipt. A doc calling itself "canonical" is an observation, not authority.

---

## 4. Verified current state (dated)

| Area | State | Evidence | Date |
|---|---|---|---|
| A1 outcome typing (narrow slice) | **Delivered** | `2d4bcce`, `84468ce`; conductor 86/86 | 2026-09-18 |
| Conductor package | 86 passed | `pytest tests/conductor/ -q` | 2026-09-18 |
| Full backend suite | 1458 passed, 2 failed, 28 skipped, 1 xpassed | commit `2d4bcce`, no `-x` | 2026-09-18 00:36 |
| The 2 failures | Order-dependent; pass in isolation and file-level (78/78) | `tests/test_qgate_backfill.py::TestCLICommands` | 2026-09-18 00:38 |
| E2E 3-min pipeline | 3 passed | `tests/test_e2e_3min_pipeline.py` | 2026-09-18 00:15 |
| Web suite | 243/246, 3 skipped spec-first | docs-5 STATE (carry-forward) | 2026-09-17 |
| Desktop bundle | `.app` + `.dmg` produced via `cargo tauri build` | `f082aa5`, docs-5 STATE | 2026-09-17 |
| Live creative render backend | **PARTIAL** — offline placeholder only | docs-5 DOSSIER/STATE | 2026-09-17 |
| Clean-machine install | **NOT RUN** | docs-5 STATE | 2026-09-17 |
| Published artifact downloads | 0 | docs-5 review | 2026-09-17 |

---

## 5. What landed in the handing-off session

| Commit | Summary |
|---|---|
| `2d4bcce` | Orchestrator surfaces `artifact_path` for `list[Path]`-returning adapters (ComfyUI, C4D, DaVinci); provenance records `outcome=offline-placeholder` vs `render`. Regression test reproduced the gap red first. |
| `33292f6` | `_librosa_segment_boundaries`: `<=` → `<` (was appending one extra zero-duration segment before the `[:n_segments]` slice); replaced a `<REDACTED>` issue URL with the real repo path. |
| `84468ce` | Extends the A1 regression to assert the provenance sidecar's `extra.outcome` on the render path. |

All three are pushed to `origin/main`.

**Earlier same-day commits** (previous session, also pushed): `390b859` web test fixes, `f082aa5` macOS bundle targets.

---

## 6. Pending work, in priority order

Ordering rule: smallest remaining effort, fastest useful outcome, fewest dependencies. `NEXT-ACTIONS.md` is authoritative if it differs.

### A1 remainder — label the remaining outcome classes
`CUR-1262466303-A1` closed only the placeholder-vs-render distinction. Still unlabeled in a machine-readable way: **job-spec-only**, **unavailable**, **failed**. Still unimplemented: rejection/blocking of malformed or zero-duration media so release acceptance cannot silently consume fixture output.
Acceptance: a known-absent backend, a failed render, and malformed/zero-duration media are rejected or explicitly blocked; rehearsal stays runnable.

### Item 4 — clean-machine install smoke (smallest gap to a verifiable installed product)
Install the published `.dmg` and `.tar.gz` on a machine without the repo, launch, confirm the packaged frontend loads and a basic workflow runs. Report signing/Gatekeeper and missing-resource errors.
This is the only major gap in the release/install concern. **Requires a different machine** — do it from the desktop.

### Item 5 — wire the three spec-first components
`FullscreenToggle`, `PlaybackTransport`, `SceneJumpPanel` exist as spec-first tests but are not wired into `App.tsx`. Acceptance: the 3 skipped web tests pass with no other regression.

### A2 — real creative output
Import a licensed track, use the intended available renderer, edit scene/preset, export, inspect A/V sync and content. Acceptance: real output reviewed, not merely a non-empty file; run parameters and derivatives traceable. **Needs the GPU-capable host or a qualified remote renderer.**

### A3 — installation and comparison qualification
On a clean machine, install v0.1.0, create/reopen a project from real input, export, repeat; compare against a stated baseline workflow. Acceptance: repeated runs produce the same usable result; record install/startup and time-to-useful-output, qualitative differences, and CPU/memory/storage/wall-time. Fixture-only or source-tree success does not count.

### Item 6 — delivery contract documentation
Confirm the shipped feature set matches the release notes; amend `CHANGELOG.md`/`docs/` if the public claim exceeds what the artifact delivers. Check `v0.2.0` here since its assets are unverified.

---

## 7. Open risks and unknowns

- **Order-dependent test failures.** `tests/test_qgate_backfill.py::TestCLICommands::test_cmd_diff_identical_specs` and `::test_main_dispatch_diff` fail under full-suite ordering but pass in isolation. Cause UNKNOWN — investigate shared state, do not paper over with `-p no:randomly` or by marking xfail.
- **E2E flakiness under full-suite load.** `test_full_pipeline_three_minute_track` failed once in a full `-x` run, then passed isolated (189s) and with its file (3/3, 122s). Timing/resource contention suspected.
- **Offline placeholder path is rehearsal, not product proof.** Placeholders are labeled but are not real renders.
- **`ComfyUIAdapter` can return workflow JSON when placeholder generation fails**, so a downstream consumer must distinguish metadata from playable media. Partially addressed by provenance typing; no rejection test exists yet.
- **GPU/live renderers unproven**; clean-machine install unproven; zero artifact downloads observed.
- **`v0.2.0`** tag verified to exist; contents and assets UNVERIFIED.

---

## 8. Uncommitted files owned by other sessions — preserve

17 files were dirty at handoff and are **not mine to commit**. Do not discard, stash, or revert them; determine ownership before touching.

```
CODE_OF_CONDUCT.md                              README.md
Taskfile.yml                                    api-spec/studio-pipeline.openapi.yaml
crates/melosviz-mir/Cargo.toml                  desktop/electrobun.config.ts
docs/PACKAGING.md                               docs/WAVE_P1PQ_MERGE_STATUS.md
packages/brand-tokens/package.json              packages/ui/package.json
packaging/homebrew-tap/Formula/melosviz.rb.template
packaging/scoop-bucket/melosviz.json.template
packaging/winget/manifests/kooshapari/Melosviz/melosviz.installer.yaml.template
packaging/winget/manifests/kooshapari/Melosviz/melosviz.yaml.template
sdk/rust/Cargo.toml                             sdk/ts/package.json
trace-gate.toml
```

Some look like release-metadata/version bumps (packaging, sdk, packages, `trace-gate.toml`). If they are yours to finish: validate them, commit with trailers, push. If not, leave them.

---

## 9. Resume commands (run on this host)

```bash
# repo
cd /Users/kooshapari/CodeProjects/Phenotype/repos/Melosviz
git fetch --all && git status --short

# backend tests (venv is provisioned here)
cd backend
.venv/bin/python -m pytest tests/conductor/ -q                    # fast, 86 tests
.venv/bin/python -m pytest -q --ignore=tests/performance          # full, ~3.5 min

# the two order-dependent tests, isolated
.venv/bin/python -m pytest tests/test_qgate_backfill.py -q        # expect 78 passed

# e2e pipeline (~2 min, needs ffmpeg)
.venv/bin/python -m pytest tests/test_e2e_3min_pipeline.py -q

# desktop bundle (from repo root)
cd desktop && cargo tauri build                                   # emits .app + .dmg
```

Notes: run long suites in the background and prefer progress-emitting commands. Keep scratch/worktrees under `$JCODE_SCRATCH_DIR`, not `/tmp` (RAM-backed here). `git push` uses SSH, not `gh` — `gh` auth has expired before on this host.

---

## 10. Environment quirks and failure modes

- `python cli.py` exists in some Phenotype repos; **this repo uses direct pytest via `backend/.venv`** — there is no top-level `cli.py`. Don't assume the generic CLI guidance applies.
- `gh` CLI auth may be expired; Git SSH works. Use `git push`, and if you need API access, re-auth first.
- Duplicate-definition oddity: `melosviz/render/video_exporter.py` defines `_extract_envelope` twice (the second shadows the first with v2 `dense_keyframes` support). Harmless today, a real bug if the first is ever relied on.
- ffmpeg is required for placeholder clips and e2e; tests skip rather than fail without it.
- `audioop` deprecation warnings appear on Python 3.11 test runs; expected.

---

## 11. What "done" means for this product

Parent outcome, unchanged: **the installed product produces and edits a real useful synchronized visualization, with honest backend modes.**

Hard gates before claiming success:

1. A real licensed track flows through import → analyze → edit → export → reopen, with measured A/V sync.
2. Backend mode is truthful in the artifact (live vs placeholder vs job-spec-only vs unavailable vs failed).
3. The published artifact installs and runs on a clean machine.
4. Independent unit/integration/E2E gates pass on the real entrypoints, with critical behaviors fully covered.
5. Reuse FFmpeg/Blender/licensed tools; do not hand-roll codecs or pass fixture output off as production.

---

## 12. First actions for the new owner

1. `git fetch --all`; confirm `main` = `84468ce` (or later) and inspect the 17 dirty files.
2. Decide placement: which tasks need this laptop, which need the GPU host, which are desktop-local.
3. Take **item 4** (clean-machine install smoke) if a clean desktop is available — smallest gap, fastest useful outcome, no code dependency.
4. Otherwise take **A1 remainder** (label unavailable/failed/job-spec-only; reject malformed and zero-duration media), writing the rejection test red first.
5. Confirm the `v0.2.0` tag's contents before citing any release claim.
6. Only after a verified pass, update `docs-5/products/Melosviz/STATE.md` with a new observation date and the fresh numbers.

Do not reopen closed audits, do not create a competing ledger, and do not restart work whose evidence is already dated above.
