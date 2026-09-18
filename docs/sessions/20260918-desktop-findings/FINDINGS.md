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

## 6. Verification and failure attribution

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

## 7. Handoff backlog status

| Item | Status |
|---|---|
| **Item 4** clean-machine install smoke | **Step one unblocked** (cloning and checking out now work on Windows). **Still NOT RUN**: it needs the published `.dmg` / `.tar.gz` and a machine without the repo. |
| **Item 5** wire the three spec-first web components | Unchanged; 3 web tests still skipped. Desktop-local, no blocker. |
| **A2** real creative output | Unchanged; needs the GPU-capable host or a qualified remote renderer. |
| **A3** installation + comparison qualification | Unchanged. |
| **Item 6** delivery contract docs | Unchanged. `v0.2.0` tag contents and assets remain **UNVERIFIED**. |
| A1 remainder | Partly advanced (§2 added `unavailable`); see §5.3 for what is left. |

## 8. Resume commands (this host, owner session)

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

## 9. What this session deliberately did not do

- No force push, no history rewrite: all four commits are fix-forward on `main`
  (`d501aa2`, `f5879a8`, `8e546da`, `f32e282`).
- Did not touch the 17 uncommitted files owned by other sessions (they live on the
  laptop; the desktop clone `Melosviz-work` was clean).
- Did not activate the render cache (§3) or modify the mutation engine (§5.1).
- Did not restate item 4 as done, and did not create a competing ledger.
