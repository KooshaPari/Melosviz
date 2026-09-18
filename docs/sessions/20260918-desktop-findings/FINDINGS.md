# Melosviz — Desktop Session Findings

**Written:** 2026-09-18 (Pacific) · **Author session:** owner session on `kooshapari-desk` (Windows) · **Reads with:** `docs/sessions/20260918-owner-handoff/HANDOFF.md`

This records what the desktop session found and changed after taking ownership from
the laptop handoff. Every claim below is either reproduced here with its command
and observed output, or marked UNKNOWN. Nothing is upgraded from UNKNOWN to pass.

The laptop handoff's first recommended action (item 4, clean-machine install smoke)
could not reach step one: a clean Windows clone of `main` failed to check out. That
gate is what this session opened first.

---

## 1. Blocker: `main` could not be checked out on Windows

**Symptom (reproduced on a clean clone):**

```
$ git clone --branch main https://github.com/KooshaPari/Melosviz.git clone
error: invalid path 'backend/<MagicMock name='mock().render().files.__getitem__()' id='4477427152'>.provenance.json'
fatal: unable to checkout working tree
warning: Clone succeeded, but checkout failed.
-> 672 tracked files missing from the worktree
```

`git read-tree main` failed the same way, so the index could not even be built and the
usual `git rm --cached` repair is unavailable on Windows.

**Cause:** two provenance sidecars committed at `6539d2b` whose names came from a
MagicMock repr. `<`, `>` and `:` are illegal in Windows paths. Their payloads carry
`backend=tests.test_coverage_100.MockVideoExport`, so a test wrote provenance into the
repo root instead of a temp dir.

**This was not only a local problem — it broke the release pipeline.** GitHub's Windows
runner hit the identical error checking out tag `v0.1.1` (run `35206041272`,
2026-09-17T09:36:45Z):

```
##[error]error: invalid path 'backend/<MagicMock name='mock().render().files.__getitem__()' id='4477427152'>.provenance.json'
```

Both Windows release jobs failed at their **Checkout** step because of it, and
`Create GitHub Release` was then skipped. See §6.1 for the full job breakdown.

**Note on the earlier partial fix:** `8bee0d4` (same day) added `*.provenance.json` to
`.gitignore` for exactly these artifacts. Ignoring does not untrack, so the two
already-tracked files kept breaking every Windows checkout. A green CI on Linux/macOS
cannot see this class of defect.

**Fixed forward in `d501aa2`** (tree-plumbing commit, not a history rewrite; the
working tree could not be checked out to stage it conventionally). Tree audit: 670
files vs 672 at `c6f7212`, and the only differences are those two removals.

**Verified:**
- `git read-tree origin/main` → exit 0, 670 entries (was `error: invalid path`)
- fresh clone of `f32e282` on Windows → `Updating files: 100% (672/672), done.`, `git status --porcelain` empty

## 2. Root cause: provenance sidecars escaped the output directory

**Fixed in `f5879a8`.** Two defects, both reached by the repo's own test suite:

1. **Artifact extraction.** `hasattr(result, "files")` is true for *every* Mock, so
   `result.files[0]` returned a mock and `str()` produced
   `"<MagicMock name='mock().render().files.__getitem__()' ...>"`. Extraction now
   accepts only real path-like values (`str` / `os.PathLike`) found in a list or tuple.
2. **Sidecar placement.** The extracted value had no directory part, so
   `provenance_path_for` resolved it against the process CWD. Running
   `tests/test_coverage_100.py` from `backend/` wrote the sidecar into the repository
   itself: untracked on macOS/Linux, committed at `6539d2b`, fatal to Windows checkout.
   Relative artifacts are now resolved under the scene output dir, and a render with no
   artifact path still gets a traceable sidecar named from the scene index inside that
   directory (a spec-supplied scene label cannot steer the path).

Also added: a portability guard in `provenance_path_for` that refuses Windows-illegal
names and drive-relative paths such as `c:clip.mp4` (whose colon never reaches
`Path.name`, so a plain name check misses it), and the outcome label `unavailable` for
a scene that reported no usable artifact path.

**Verified:** 11 tests in `tests/conductor/test_provenance_containment.py` fail against
`d501aa2` and pass here; `tests/conductor` 97 passed at that commit; after a full suite
run no `*.provenance.json` exists outside a `tmp_path`.

## 3. Render-cache hit path was unreachable and would have raised

**Fixed in `8e546da`.** The cache fast-path built its `done` event in three ways that
could only fail:

1. `_now_ms()` is not defined in the module (ruff F821).
2. `RenderEvent` declares no `started_at` / `finished_at` fields.
3. `bus._events` does not exist; the bus buffer is `_buffer`, so the event would never
   have reached SSE subscribers either.

**Why it stayed hidden:** the orchestrator builds
`RenderCache(self._output_dir / "_render_cache")` without creating that directory, so
every store fails into a `logger.debug` and the cache is never populated:

```
DEBUG melosviz.conductor.orchestrator: render cache store skipped:
[Errno 2] No such file or directory: '...\out\_render_cache\89fed8f9....bin'
```

**Scope — deliberately not activated.** Creating the directory is left out on purpose:
a cache hit returns a `<fingerprint>.bin` artifact path and skips the provenance
sidecar and outcome label entirely, so cached scenes would silently lose the A1
traceability. Activating the cache is a decision with its own coverage, not a one-liner.

**Verified:** `tests/conductor/test_render_cache_hit.py` reaches the branch (it
pre-creates the cache directory, as documented in the test) and failed once per fault
against the previous code; `tests/conductor` 98 passed.

## 4. Hygiene guard

`f32e282` adds `*.mutbak` to `.gitignore`. `backend/tests/test_mutation_engine.py`
snapshots the file it mutates to `<source>.py.mutbak`; those backups were previously
untracked noise on every suite run, and one was committed at `6539d2b`.

---

## 5. Open risks (new evidence)

### 5.1 The mutation tests mutate tracked source files in place — HIGH

`test_mutation_engine.py:266` writes each mutant **into the tracked file**
(`target.write_text(mutated)`) and restores from `<file>.py.mutbak` in a `finally`.
The module docstring claims it "applies each mutation in a temp copy"; it does not.
The subprocess it runs imports the mutated file, so mutating a copy would need a
distinct import path — this is a design change, not a one-liner.

Observed consequences on this host:

- A full-suite run killed by pytest-timeout at
  `test_mutation_kill_score_meets_qgate_bar` left
  `backend/src/melosviz/analysis/audio.py` containing a mutant, plus a stray
  `audio.py.mutbak`.
- Proof: `git hash-object backend/src/melosviz/analysis/audio.py` → `6f10e4f…`;
  `git hash-object …audio.py.mutbak` → `ed92482…` == `HEAD:…/audio.py`. The diff is a
  single operator mutation:

  ```diff
  -    if n == target_len:
  +    if not n == target_len:
  ```

- Both `tests/test_coverage_100.py::TestResampleList::test_downsample` and
  `::test_upsample` failed in that session and pass at the pristine baseline: unrelated
  tests fail because a mutant is sitting in the tree.
- A mutant left in the working tree is one `git add -A` away from `main`.

Recommendation: point the mutation runner at an isolated copy (or worktree) so the
tracked tree is never the mutation target, and fail loudly if the source differs from
`HEAD` after the run. Not attempted here: verifying it needs a full mutation run
(60 mutations × up to 60 s each) that this environment cannot complete.

### 5.2 Render cache is still inert — see §3

### 5.3 A1 remainder unchanged

Still open: machine-readable labels for **job-spec-only**, **unavailable** (partly done
in `f5879a8` for pathless results), **failed**, and rejection/blocking of malformed or
zero-duration media so release acceptance cannot silently consume fixture output.

### 5.4 `collected_paths` is never appended to — observation, intent UNKNOWN

`orchestrator.py:556` initialises `collected_paths` and it is only read (`.len` at
`:863`, passed to the assembly adapter at `:870`). Rendered artifacts are never added,
so the final assembly step receives only caller-supplied `segment_paths`. This may be
intentional; it is recorded because nothing in the code says so.

---

## 6. Published artifacts and the install gate

Resolves the "**v0.2.0** tag verified to exist; contents and assets UNVERIFIED" item
from HANDOFF §7.

| Fact | Observed |
|---|---|
| GitHub releases | exactly one: `Melosviz v0.1.1`, published 2026-09-17, not draft/prerelease |
| `v0.2.0` release | **does not exist** (`gh release view v0.2.0` -> `release not found`); the tag `5835da3` has no release and therefore **no assets at all** |
| `v0.1.1` assets | `Melosviz_0.1.1_aarch64.dmg` (4,810,712 B) and `Melosviz-v0.1.1-macos-arm64.tar.gz` (4,805,307 B) — **both macOS arm64**, no Windows or Linux artifact |
| Recorded downloads | dmg 1, tar.gz 0 (matches the "0 artifact downloads" observation) |

**Integrity verified (this session):** both assets were downloaded and their SHA-256
digests match the published release digests exactly:

```
1c588123e7964a063e2d9358e449b8ff4f6590f031b86216cdce1b067cc45496  Melosviz-v0.1.1-macos-arm64.tar.gz
2946909e4143f112754275ea931568e1f3271791632b8d945df880dd4b1e0d51  Melosviz_0.1.1_aarch64.dmg
```

**Structure verified:** the tarball holds a well-formed bundle —
`Melosviz.app/Contents/{Info.plist, MacOS/melosviz-desktop, Resources/icon.icns}`.
The executable is a genuine 64-bit Mach-O (`cf fa ed fe`, cputype `0x0100000c` = arm64),
13,652,288 bytes, and it contains the embedded frontend markers `index.html`,
`assets/`, `<div id=`, plus `tauri`, `wry`, `WebView` and `brotli`.

**Defect found — the shipped app reports the wrong version.** `Info.plist` declares
`CFBundleShortVersionString` = **0.1.0** and `CFBundleVersion` = **0.1.0** inside an
artifact released and named as **v0.1.1**. Anyone verifying an install by reading the
app's version will see 0.1.0. Relevant to item 6 (shipped feature set vs release notes).
The same plist still carries a 2000s-era DTD reference and `LSRequiresCarbon`, both
stale for a Tauri 2 bundle — recorded as an observation, cause UNKNOWN.

**Item 4 consequence.** The install smoke cannot run on this desktop: nothing published
is installable on Windows, and both assets target Apple Silicon macOS. Item 4 therefore
needs an arm64 Mac, and the only version available to install there is **v0.1.1**, since
v0.2.0 has no release. Launch, packaged-frontend load and a basic workflow run remain
**NOT RUN**.


### 6.1 Why no Windows or desktop artifact exists (CI evidence)

The Release workflow (`release.yml`) defines macOS, Linux and Windows build jobs and the
packaging workflows expect Windows asset names. For the only published release, the run
at tag `v0.1.1` (`35206041272`, 95 s) ended like this:

| Job | Outcome | Failing step |
|---|---|---|
| Release SBOM (CycloneDX) | success | |
| **Windows — desktop app (Electrobun)** | **failure** | **Checkout** (the illegal-path error in §1) |
| **macOS — desktop app DMG** | **failure** | **Build desktop app (Electrobun, stable channel)** |
| Linux — CLI tarball (Rust binaries) | success | |
| **Windows — CLI zip (Rust binaries)** | **failure** | **Checkout** (same cause) |
| **Create GitHub Release** | **skipped** | dependencies failed |

Two separate root causes:

1. **Windows jobs:** the illegal provenance paths (§1). Because git refuses those paths on
   Windows, `actions/checkout` fails before any build starts. `d501aa2` removes the cause,
   so these jobs can run again.
2. **Desktop bundle jobs (macOS and Windows):** `bunx electrobun build --env=stable`
   aborts with

   ```
   BuildMessage: ModuleNotFound resolving ".../Melosviz/desktop/src/bun/index.ts" (entry point)
   error: CottontailBuildFailed
   ```

   `desktop/src/bun/` has **never existed in any branch or tag** (`git log --all -- desktop/src/bun`
   is empty, and `git ls-tree -r v0.1.1 desktop/src` shows `index.ts`, not `bun/index.ts`).
   `desktop/electrobun.config.ts:21` still declares the v1-style `entrypoint: "src/index.ts"`,
   while `desktop/package.json` pins `electrobun: "^2.0.1"` and the log shows 2.0.1 resolving
   `src/bun/index.ts`. The 1.18.1 → 2.0.1 bump (#218) was not accompanied by the layout
   migration, so the desktop bundle cannot be built by CI at all.

**Consequence for what is published.** `Create GitHub Release` was skipped, so the release
that exists for `v0.1.1` was not produced by the pipeline. Its two macOS assets are named
`0.1.1` while the app inside reports `0.1.0` (§6), which matches the v0.1.1 commit subject
"reconcile v0.1.0 artifact under new v0.1.1 changelog". The result is one installable
artifact in existence, for macOS arm64, built as 0.1.0.

**Claim-vs-delivery gaps (item 6 acceptance).**

- `CHANGELOG.md` carries `## [0.2.0] - 2026-07-04`, but no `v0.2.0` release exists: that
  run (`28702033023`) failed in 7 s with `Create GitHub Release` skipped. The changelog
  also orders 0.1.1 (2026-09-17) after 0.2.0 (2026-07-04) by date while ranking it lower,
  against the file's own SemVer statement.
- `README.md:55` documents a "Native app (macOS .app / Windows .exe)" via `task app`, a
  source-build instruction rather than a download claim, but that route cannot work while
  the electrobun entry point is missing.
- `packaging/winget/...` and `packaging/scoop-bucket/...` templates plus
  `.github/workflows/winget-pr.yml` and `scoop-bucket.yml` require
  `melosviz-desktop-windows-x86_64.zip` and `melosviz-cli-windows-x86_64.zip`. Neither
  exists in the only release, so those workflows cannot succeed as written.

**Why I did not amend the public claims.** `CHANGELOG.md` is generated
(`1c32005` "regenerate from full git history"), so hand-edits would be overwritten, and
`desktop/electrobun.config.ts` is one of the 17 uncommitted files owned by another session.
Rewriting release claims is also a product decision. Recommendation: (a) migrate the
desktop layout to the electrobun 2.x entry point and prove it with a real
`build:stable` run, then (b) re-cut a release from the pipeline so asset names, the
binary's own version, the changelog headings and the winget/scoop manifests agree.

## 7. Verification and failure attribution

Same Windows host, `--ignore=tests/performance`, one hanging test deselected
(`tests/test_mutation_engine.py::test_mutation_kill_score_meets_qgate_bar`, which self
times out here without cargo):

| Commit | Result | Time |
|---|---|---|
| `d501aa2` (baseline, pristine) | 31 failed, 1429 passed, 28 skipped, 1 deselected, 1 xpassed | 577 s |
| `f5879a8` (this session) | 32 failed, 1439 passed, 28 skipped, 1 deselected, 1 xpassed | 633 s |

Failure-set difference: the only failures present on `f5879a8` and not at baseline are
`test_coverage_100.py::TestResampleList::test_downsample` and `::test_upsample`, both
explained by §5.1 (mutated `_resample_list` in the tree). One baseline-only failure
(`test_studio_pipeline_adapters::test_comfyui_offline_mode_emits_job_spec_without_network`)
is a flake. **Zero failures are attributable to the changes in this session.**

The counts reconcile exactly: 1429 + 12 new tests − 2 mutation-contamination failures
= 1439.

The remaining 31 failures are pre-existing on this host:

```
 14  tests/test_beat_track_isolation.py
  4  tests/test_qgate_backfill.py          (includes the two order-dependent failures HANDOFF §7 already documents)
  3  tests/test_e2e_3min_pipeline.py
  2  tests/test_coverage_100.py
  2  tests/test_audio_ml_paths.py
  1  each: test_studio_pipeline_adapters, test_coverage_gaps, llm/test_director,
           cli/test_gpu_smoke, character/test_registry_io, render/test_native_audio_routing
```

After full-suite runs, `git status --porcelain` is empty; the only leftover is the
already-ignored `.mutations/` directory.

**Honest limits.** These are local suite results on one Windows host with no cargo and
no GPU. The laptop's recorded baseline (1458 passed / 2 failed, macOS) is not
comparable test-for-test. A green local suite is not installation, not adoption and not
user acceptance.

---

### 7.5 Item 5 was already done; the handoff entry is stale

The handoff (and the docs-5 STATE carry-forward behind it) says
`FullscreenToggle`, `PlaybackTransport` and `SceneJumpPanel` "exist as spec-first
tests but are not wired into `App.tsx`", with acceptance "the 3 skipped web tests
pass". That is no longer true of `main`:

- `390b859` ("resolve all test failures - 243/246 passing (3 skipped spec-first)") is
  where the 3 skips came from.
- `d14aa8e` ("wire FullscreenToggle + SceneJumpPanel + PlaybackTransport",
  2026-09-17 01:45) wired all three into `App.tsx` and added the a11y coverage. Both
  commits are ancestors of `main`.
- `web/src/App.tsx` imports and renders all three (state wired through `fullscreen`,
  `activeSpec`, `playbackT`, `autoPlay`, with `onJumpToKeyframe` / `onSeek` /
  `onReset` handlers), and `web/src/__tests__/App.a11y.test.tsx` carries the active
  (not skipped) tests, including "fullscreen toggle exposes aria-pressed and Escape
  exits".

**Verified on this host:** `npm install --no-audit --no-fund` then `npm test`
(`vitest run`) -> **27 test files passed, 246 tests passed, 0 skipped, 0 failed**,
52.26 s. `git status --porcelain` was empty afterwards, so the install changed no
tracked file (the lockfile included).

**Environment note:** `npm ci` fails on this host with ERESOLVE because
`@testing-library/react@15` declares `peerOptional @types/react ^18` while the project
pins `@types/react ^19`; npm 11 rejects it whereas CI's Node 20 / npm 10 accepts the
tree. CI already runs `npm ci ... || npm install ...`, and `npm install` works here.
The web test step in `.github/workflows/ci.yml` ends with
`|| echo "::warning::test failures (advisory)"`, so web test failures do not fail the
build gate today. That is a coverage-honesty gap worth a deliberate decision, not
something to change unilaterally.

## 8. Real-path acceptance evidence

The unit tests in this repo use test doubles, so the fixes above were re-checked
against the shipped package through its public interfaces on this host. ffmpeg is present
(ImageMagick's build), so the offline placeholder path runs for real.

### 8.1 Provenance containment, real adapter

`Orchestrator.render` was driven directly with the **real** `ComfyUIAdapter` from
`ADAPTER_REGISTRY` (no monkeypatching) from a clean CWD, with a deliberately hostile
scene label:

```
cwd        = ...\rp1\cwd
real adapter = melosviz.conductor.registry.ComfyUIAdapter
done       artifact_path='...\out\comfyui_image\scene_000\clip.mp4'

sidecars inside output dir: 1
  ...\out\comfyui_image\scene_000\clip.mp4.provenance.json
    artifact_path = '...\clip.mp4'
    scene_name    = '../../escape-attempt'
    outcome       = 'offline-placeholder'
    contained     = True
stray sidecars under cwd: 0
files left in cwd: 0
```

The label `../../escape-attempt` did not steer the path, and nothing was written
outside the output directory. `visual-diff.svg`, `visual-diff-frame.png`,
`workflow.json` and `job_spec.json` all landed beside the clip.

### 8.2 Real CLI, end to end

A 4-second WAV was synthesized (standard library only) and the shipped CLI was run from
a clean CWD:

```
viz analyze <track.wav>     -> exit 0, 39,359 bytes of RenderSpec JSON
viz generate <track.wav> --concept ... --bpm 120 --seed 7 --out <out>
                            -> exit 0, assembly_ok true,
                               scenes: comfyui_audio_video_seedance, comfyui_image, comfyui_video
```

Output audit for that run: 3 provenance sidecars, **all contained** in the output dir,
**0 sidecars outside**, **0 files left in the CWD**, 12 MP4 artifacts, 3 `job_spec.json`.

### 8.3 A label defect this exposed, found only on the real path

The first CLI run recorded

```
outcome tally: {'render': 2, 'offline-placeholder': 1}
```

while the adapter was in offline mode and had touched no network, and all three scene
directories contained `job_spec.json` plus placeholder MP4s. `ComfyUIAdapter.render`
branches on offline mode **once, before any scene-type dispatch**
(`comfyui_adapter.py:611`), and the registry routes seven scene types to that adapter,
but the orchestrator compared `scene_type` against the single literal `comfyui_image`.

Fixed in `5b20a6f`: the label now asks the serving adapter
(`emits_offline_placeholders`, declared by `ComfyUIAdapter`, absent elsewhere). Re-running
the same command with the same seed:

```
before: {'render': 2, 'offline-placeholder': 1}
after : {'offline-placeholder': 3}
```

sidecars still contained 3/3, 0 files in the CWD, `assembly_ok` true. New tests in
`tests/conductor/test_offline_outcome_scope.py` fail against the old code
(`offline-produced scene labelled 'render'`) and pass after; conductor 101 passed.

**Still open, and deliberately not labelled:** the Cinema4D, Unreal, After Effects and
Blender adapters also branch on the same env var (`cinema4d_adapter.py:308`,
`unreal_adapter.py:296`, `blender_exporter.py:759`). Whether their offline branch emits a
placeholder clip or only a job spec decides whether they are `offline-placeholder` or
`job-spec-only`, and that needs its own check. They keep reporting `render` until then.

### 8.4 Render cache: what the real path does today

Driven through the public API with the real adapter, twice per phase:

| Phase | Observation |
|---|---|
| **A — shipped default (no `_render_cache` dir)** | `cache entries after first render: 0`; second render `from_cache=False`, artifact suffix `.mp4`; product works, cache inert. |
| **B — cache dir present** | `cache entries after first render: 1`; second render `from_cache=True`; **the real subscriber received the cache-hit event** (`('done', True)` in the subscriber sequence) and it is in `bus.recent()`; `to_sse()` renders. The hit's `artifact_path` suffix is **`.bin`**. |

Phase B is what `8e546da` repaired and it now works, including the SSE delivery that
`bus._events` would have swallowed. Phase B also measures why activation stays deferred:
a hit hands downstream a `_render_cache\<sha>.bin`, not an `.mp4`, and skips provenance
and the outcome label.

### 8.5 `*.mutbak` guard, real git interface

```
$ git check-ignore -v backend/src/melosviz/analysis/_probe2.py.mutbak
.gitignore:86:*.mutbak  backend/src/melosviz/analysis/_probe2.py.mutbak
$ git add -A && git status --porcelain
(no output: the backup is not staged)
```

A mutation backup cannot be committed. `git ls-files` still matches no `*.mutbak`, so the
rule hides no tracked file.

## 9. Handoff backlog status

| Item | Status |
|---|---|
| **Item 4** clean-machine install smoke | **Step one unblocked** (cloning and checking out now work on Windows). **Still NOT RUN, and not runnable here**: both published assets are macOS arm64, so this needs an arm64 Mac; see §6. |
| **Item 5** wire the three spec-first web components | **Already complete on `main`** (`d14aa8e`, 2026-09-17). The handoff entry is stale; see §7.5. Verified here: web suite 246/246 passed, 0 skipped. |
| **A2** real creative output | Unchanged; needs the GPU-capable host or a qualified remote renderer. |
| **A3** installation + comparison qualification | Unchanged. |
| **Item 6** delivery contract docs | Unchanged. `v0.2.0` tag contents and assets remain **UNVERIFIED**. |
| A1 remainder | Partly advanced (§2 added `unavailable`); see §5.3 for what is left. |

## 10. Resume commands (this host, owner session)

```bat
git clone --branch main --single-branch https://github.com/KooshaPari/Melosviz.git <dir>
cd <dir>\backend
uv venv --python 3.11 .venv
uv pip install --python .venv -e ".[test]"
.venv\Scripts\python.exe -m pytest tests/conductor -q --no-header -p no:cacheprovider --basetemp=<scratch>\ptmp
```

Notes: pass `--basetemp` (pytest's default `pytest-current` symlink cleanup raises
`PermissionError` on this host). Keep scratch under `agents\sandbox\`, never the user
profile root. `git push` works over HTTPS with the credential manager; `gh` is
authenticated with `repo` + `workflow` scopes.

## 11. What this session deliberately did not do

- No force push, no history rewrite: all four commits are fix-forward on `main`
  (`d501aa2`, `f5879a8`, `8e546da`, `f32e282`).
- Did not touch the 17 uncommitted files owned by other sessions (they live on the
  laptop; the desktop clone `Melosviz-work` was clean).
- Did not activate the render cache (§3) or modify the mutation engine (§5.1).
- Did not restate item 4 as done, and did not create a competing ledger.
