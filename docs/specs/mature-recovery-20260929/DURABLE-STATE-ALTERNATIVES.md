# Melosviz durable product-state alternatives — pass 6

Frozen product source: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`.
Status: architecture research / candidate decision, not a production migration.

## Problem

Current mounted state is split across storyboard JSON, process-local render events, content-addressed cache files, provenance sidecars and generated media. None alone is authoritative for project revision, scene revision, render/assembly attempt identity, accepted state, artifact/evidence binding, restart recovery, worker replacement or selective invalidation.

M-F29 identifies this as a product-state gap. It does not mandate a database.

## Alternatives

| Alternative | Disposition | Benefit | Cost / mismatch |
|---|---|---|---|
| Atomic file manifest + append-only journal | ADAPT candidate | Minimal dependency/ops; human-inspectable | Multi-record atomicity, indexing, concurrency and recovery need custom implementation |
| SQLite via stdlib | COMPOSE candidate | Local transactions, constraints, indexing, single-file ownership | Requires migrations, durability policy, backup/export and explicit file-artifact transaction boundary |
| DBOS on SQLite | LEARN FROM / spike only | Durable workflow/step recovery with SQLite by default | Adds execution framework/version semantics that may exceed the local product need |
| Temporal | REJECT for current local-first stage; escalation option | Strong event-history durable execution and worker replacement | Adds Temporal Service + Worker operational architecture and deterministic workflow constraints |
| Hatchet | REJECT for current local-first stage; escalation option | Durable tasks/workflows and worker management | Adds external orchestration/runtime surface not justified by current single-user local spine |

## Candidate semantic state model

Storage technology remains replaceable. The minimum semantic model should express:

- Project and immutable ProjectRevision
- stable SceneRevision identity plus order index and dependency digest
- Render/Assembly Attempt with candidate/configuration and lifecycle state
- Artifact bound by content digest
- Evidence bound to criterion, subject identity and verifier/version
- Acceptance bound to contract revision and authorized evidence

Process-local events are projections of durable transitions, not product truth. Cache entries may accelerate work but cannot create acceptance.

## M-E03 storage comparison

Prototype the same small R1 → process restart → R2 sequence with:

1. an append-only file journal plus atomic snapshot;
2. a SQLite ledger with foreign keys and explicit transactions.

The comparison must prove:
- R1 history remains immutable after reopen;
- incomplete attempts remain distinguishable from completed/accepted attempts;
- only changed scene dependencies invalidate reuse;
- duplicate/stale acceptance is rejected;
- partial state writes recover or fail closed;
- output filenames are not used as authoritative state.

Measure implementation LOC, custom locking/recovery mechanisms, ambiguity after reopen, startup/recovery latency, portability and migration complexity.

Decision rule: choose the smaller mechanism that passes every invariant.

## Provisional architecture-to-beat

Direct SQLite is the architecture-to-beat for the current single-host desktop product, not yet an accepted product decision. Keep large media outside the DB by content digest and atomically record product metadata/state. If accepted future scope requires multiple machines/services to own work concurrently, reopen DBOS/Temporal/Hatchet rather than stretching the local ledger into a distributed scheduler.

## External evidence notes

SQLite documents atomic transactions and local WAL semantics. DBOS provides durable workflows backed by a system database and defaults to SQLite for local use. Temporal reconstructs workflows from Event History through a separate service/worker runtime. These are architecture references, not product measurements.
