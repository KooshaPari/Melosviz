# M-E02 independent source review — candidate branch

Candidate: experiment/mature-recovery-m-e02, compared to frozen source 1aec20a2ba41a01ed557d1c7f63f9a0089f842cf. Review date 2026-09-30. Source review, not a native/product test run.

## Candidate scope observed

The branch is 18 commits ahead and changes conductor, CLI, bridge, compose, Electrobun/web consumers and focused tests. It is treated as an untrusted implementation candidate, not credited by authorship or commit count.

## Pass-8 contract grade

- Selector: PROVISIONAL PASS — explicit render selector overrides constructor selector; indices validated before adapter work.
- Iteration cardinality: PROVISIONAL PASS — candidate projects RenderSpec to one scene before adapter call; focused test asserts one scene/call.
- Result identity: PROVISIONAL PASS — results keyed by scene_index; same-backend test covers three scenes.
- Artifact identity: **FAIL** — live artifacts still use the old artifact-rejection helper that accepts nonempty malformed MP4/WAV; cache hits trust stored outcome without revalidating materialized media.
- Assembly connectivity/order: PROVISIONAL PASS WITH BLOCKER — render/cache-hit outcome=render artifacts append in dispatch order, but unsound artifact acceptance means malformed/stale cache media can enter assembly.
- Events: PARTIAL — done carries outcome, but remains worker execution classification, not independent acceptance. A rejection-reason map is constructed but emit_done currently passes only outcome.
- Bridge/UI: PARTIAL — CLI emits structured scene manifest; bridge parses stdout; web/Electrobun consume outcome. They still treat outcome=render plus path as green, inheriting weak media validation.
- R2 restart/selective evidence: NOT PROVEN.

**Overall M-E02 candidate: FAIL / REVISE.** Important identity/cardinality defects are improved, but a critical non-averagable artifact/evidence dimension fails.

## Additional findings

### Cache origin/content acceptance remains weak

RenderCache.store records input fingerprint, size, metadata and outcome but no artifact content digest. lookup accepts any nonempty fingerprint.bin. On hit, the candidate materializes bytes, reads old metadata outcome, and if outcome is render appends to assembly without media revalidation. Equal-size destination substitution is fixed, but cache-blob corruption/substitution can inherit prior render classification.

Minimum repair: store artifact SHA-256 at cache write; verify blob digest on lookup/materialization; re-run appropriate media validity before a cache hit becomes assembly-eligible. Missing/legacy digest is non-green or forces rerender.

### Cross-process SSE remains nonfunctional for bridge-spawned generate

The event module explicitly says the bus is in-process. The bridge launches the CLI with subprocess.run and only captures stdout/stderr after completion; it does not proxy child render events. Web StudioConsole subscribes to the bridge process using the same job_id, while events are emitted in the child. Final structured manifest can correct terminal state after completion, but live per-scene SSE progress is not established.

Minimum options: stream child events and republish; run orchestration in bridge process; or remove/disable the live-SSE promise for subprocess-driven runs. Do not build distributed event infrastructure unless mature requirements need it.

### Assembly state remains coarse

CLI reports produced_unverified when an assembly result object exists, better than assembly_ok, but it still does not distinguish plan-only from real assembled media. Independent grader remains authority.

## Required next tests

1. Garbage nonempty MP4 and malformed WAV through candidate render path => malformed/non-assembly.
2. Corrupt cache blob while retaining old outcome=render metadata => forced rerender/block.
3. Missing cache artifact digest => legacy cache non-green.
4. Bridge + child process: demonstrate real-time event receipt or explicitly rely on terminal manifest.
5. Same-backend two-scene candidate with actual adapter fixture plus mutation restoring whole-spec adapter call.
6. R1→restart→edit S1→R2 with exact reuse evidence and independent media oracle.
