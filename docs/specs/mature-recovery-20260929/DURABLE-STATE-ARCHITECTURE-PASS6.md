# Melosviz candidate durable product-state architecture — pass 6

Status: **CANDIDATE ARCHITECTURE FOR EXPERIMENT**, not accepted product contract. Frozen source `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`. This is driven by observed execution/acceptance false greens and the required worker/product lifetime separation.

## Source finding

Targeted frozen-source searches for `sqlite3`, `aiosqlite`, `sqlalchemy`, `project_revision`, `render_attempt`, `job_store`, `resume_job`, and `sessions.json` found no product-state implementation. `checkpoint` references are workflow/model documentation rather than a durable Melosviz project/job ledger. This is bounded code-search evidence, not a proof that no arbitrary persistence helper exists under another name.

Current orchestration state is distributed among input specs/storyboards, filesystem artifacts, best-effort provenance sidecars, in-process events/cache and caller/GUI variables. That shape cannot by itself meet the required R1 → worker replacement → R2 selective-revision evidence semantics.

## Alternatives considered

### A. Small local transactional ledger — preferred CVP/MVP experiment

Use SQLite for durable **metadata and state transitions**, not rendered media bytes. Artifact files stay content-addressed/hashed on disk; the ledger stores identity, lineage and acceptance references.

Why this fits the current product: single-user/local desktop and CLI are primary current surfaces; the first required recovery problem is process/app/renderer replacement, not global multi-region orchestration. SQLite provides atomic transactions and crash recovery without another service. WAL can support readers alongside a writer, but SQLite documentation requires treating the WAL file as part of persistent state.

2026-specific constraint: SQLite documents a rare WAL-reset corruption bug affecting versions through 3.51.2, fixed in 3.51.3 (2026-03-13) and selected backports. **Do not enable concurrent-process WAL acceptance without verifying the runtime SQLite is patched.** An experiment may use rollback-journal mode or a single-writer design if the embedded runtime is older.

### B. Temporal — rejected as default, keep escalation path

Temporal is a mature MIT-licensed durable-execution platform with replay/retry semantics and worker/service architecture. It is a strong alternative if Melosviz becomes distributed across persistent worker fleets, long-running remote render jobs or cross-host compensation workflows.

Current downside: it adds a service/control-plane and workflow programming model before Melosviz has proven that a local durable state machine is insufficient. It would solve more than the current product has earned and risks making development machinery/product runtime state the same thing.

**Disposition: REJECT for CVP/MVP core; REVISIT on measured multi-host/durable-worker pressure.**

### C. Prefect/Dagster-class orchestration — rejected for core product state

Prefect 3.8.7 is current in September 2026 and its open-source Python package is Apache-2.0; it supplies retries, dependencies, scheduling/caching and optional server/cloud state. Dagster remains supported after joining Prefect in 2026. These are useful pipeline orchestrators, especially for data workloads, but Melosviz still needs its own domain identities/evidence even if a flow engine schedules work.

**Disposition: LEARN FROM / optionally use for operator automation, not canonical product truth.**

## Candidate domain state model

Minimum persistent entities:

```text
Project
  └─ ProjectRevision (immutable accepted input/spec revision)
       ├─ SceneRevision [ordered; stable scene_id + revision]
       │    └─ RenderAttempt*
       │         ├─ ExecutionState
       │         ├─ Artifact* (content digest + media identity)
       │         └─ EvidenceRun*
       └─ AssemblyAttempt*
            ├─ ordered accepted scene-artifact refs
            ├─ Artifact*
            └─ EvidenceRun*

AcceptanceDecision
  -> exact criterion/baseline/candidate/configuration/evidence runs
```

Render worker identity is attached to an attempt, never to Project/Scene identity. Development-agent identity is not a product-state key.

## Required invariants

1. ProjectRevision and SceneRevision are immutable; an edit creates a new revision.
2. `scene_type` is adapter selection metadata, never the scene primary key.
3. One RenderAttempt references exactly one SceneRevision and exact renderer/config inputs.
4. Execution completion cannot set AcceptanceDecision directly.
5. Artifact identity is a cryptographic content digest plus media metadata; path/size is insufficient.
6. EvidenceRun binds verifier/version/policy/candidate/config/environment/run/timestamp/raw artifact and collection state.
7. Missing/skipped/collector-failed/conflicting evidence cannot create accepted state.
8. Cache reuse creates a new applicability/receipt record pointing to immutable prior artifact/evidence; it cannot mutate historical acceptance.
9. AssemblyAttempt stores the exact ordered SceneRevision/Artifact list it consumed.
10. A worker/app restart reconstructs outstanding attempts from the ledger; it does not infer state by scanning filenames and calling them done.
11. Acceptance policy changes are separate revisions and cannot retroactively rewrite old result history.
12. Filesystem artifact deletion/corruption is detectable as a broken reference, not silently converted to accepted.

## Proposed transaction boundaries

- author/edit revision: insert immutable revision + scene rows atomically;
- dispatch claim: transition queued → leased/running with lease identity/expiry;
- render return: record raw execution outcome + artifact candidate in one transaction;
- verifier return: append EvidenceRun; acceptance calculation reads immutable evidence;
- cache hit: verify expected content/origin then append reuse receipt;
- assembly: freeze ordered accepted-input list before invoking encoder;
- restart: expire/recover leases without changing completed evidence.

Do not hold database transactions across external renderer calls.

## Storage boundary

SQLite stores metadata/lineage/decisions. Media, workflow files, model refs and raw large verifier artifacts remain filesystem/object artifacts with hashes. An append-only JSON export can provide inspectability/backups but is not the transactional source of truth.

## Experiment required before acceptance

Implement only the schema/state-machine in an isolated experiment package. Drive the existing three-scene oracle sequence:

R1 author → render attempts S1/S2/S3 → independently accept → assembly → kill app/worker → reopen → edit S2 → R2 → reuse S1/S3 only under exact unchanged identities → rerender S2 → assemble R2 → verify old R1 history unchanged.

Adversarial cases: crash between artifact write and DB commit, crash after DB candidate record but before evidence, stale lease, two workers claiming one attempt, corrupt/deleted media, equal-size replacement, verifier unavailable, migration failure, transaction rollback, old SQLite/WAL policy mismatch.

Success witness is state/recovery correctness, not schema existence.

## Escalation criteria for Temporal/other durable executor

Revisit a dedicated durable-execution platform only if measured requirements include at least one of: multiple persistent remote worker hosts; workflows lasting across machine/service redeployments where local ledger polling becomes unreliable; complex compensation across third-party services; high-volume scheduling/fairness; or operational burden of our small lease/retry state machine exceeds integrating the external platform.

Even after escalation, canonical Project/Scene/Artifact/Evidence identities remain Melosviz domain state rather than Temporal/Prefect object identities.

## External research

- SQLite WAL/recovery: https://sqlite.org/wal.html and https://sqlite.org/walformat.html
- Temporal: https://github.com/temporalio/temporal (MIT, durable execution/retry platform)
- Prefect: https://github.com/PrefectHQ/prefect (current Python orchestration framework; package metadata Apache-2.0)

No implementation is authorized by this document beyond the bounded experiment described above.
