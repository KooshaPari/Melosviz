# Melosviz candidate architecture — pass 6

Status: **preferred architecture for falsification/vertical-slice experiments, not accepted mature contract.** Frozen product source `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`.

## Product hypothesis

Melosviz is not a renderer and should not become a generic workflow engine. Its surviving thesis is an **audio-constrained, revisionable visual-production system** that keeps authoritative creative/editorial intent independent of any one GUI/render backend, orchestrates replaceable tools, and independently qualifies what was actually produced.

## Canonical state versus projections

```text
Project / ProjectRevision             durable domain state
  ├─ source audio/assets + digests
  ├─ ordered SceneRevision references
  ├─ accepted creative/editorial constraints
  └─ accepted human overrides
           │
           ├── RenderSpec projection         analysis/render-input compatibility
           ├── OTIO projection               editorial interchange
           ├── optional USD projection       hybrid spatial/DCC interchange
           └── UI/API projections            human/machine editing

SceneRevision
  ├─ stable scene_id + immutable revision
  ├─ timing/order projection
  ├─ adapter/render intent
  └─ optional Hybrid SceneSpec projection
           │
           └─ RenderAttempt* → Artifact* → EvidenceRun*

ProjectRevision
  └─ AssemblyAttempt* (exact ordered accepted artifact refs)
                   → Artifact → EvidenceRun → AcceptanceDecision
```

### Durable product truth

Use a minimal local transactional domain ledger first (candidate: SQLite metadata + content-hashed filesystem artifacts). It owns project/revision/attempt/acceptance lineage. External renderer queues, process memory, filenames and development-agent state are not product truth.

Do not put large media blobs in SQLite. Do not hold DB transactions over renderer calls. Verify the runtime SQLite recovery/journal mode before choosing WAL concurrency; current SQLite documentation records a WAL-reset corruption bug fixed in 3.51.3 and selected backports.

Escalate to Temporal/another durable executor only if measured multi-host/long-running workflow pressure makes the small lease/retry model operationally worse.

### Mounted render contract

Strengthen existing `RenderSpec.scene_segments` rather than replacing RenderSpec:
- add stable `scene_id` + immutable `scene_revision` semantics;
- keep integer index as order only;
- preserve legacy import with one-time persisted ID derivation;
- `scene_type` selects an adapter and never identifies a scene.

The richer hybrid `SceneSpec.scene_id` becomes an optional scene projection/reference under the same canonical identity rather than a second product ontology.

### Editorial interchange

Use OpenTimelineIO as an editorial projection/interchange candidate for ordered cuts, time ranges, transitions and media references. OTIO is not the canonical product truth and does not own musical intent, scene revisions, renderer provenance or acceptance.

### Hybrid spatial interchange

Use OpenUSD only if a scanner/hybrid scene fidelity spike proves sufficient round-trip/interoperability benefit. Keep it optional: USD layering/references/variants are useful, but scanner/music/evidence semantics remain Melosviz-owned. Current OpenUSD licensing is TOST 1.0 and must be treated accordingly.

### Renderers

Renderer adapters are replaceable external capabilities. ComfyUI stays an external process/API runtime; pin exact ComfyUI revision/version, workflow, custom nodes, models and config into the attempt receipt. Do not use its queue/history as Melosviz acceptance state. Apply the same principle to Blender, Adobe, Resolve, TouchDesigner or future generation models.

### Media/evidence

FFprobe/FFmpeg supply media decode/probe primitives. The independent Melosviz grader adds subject identity, expected stream/timebase/content/timing, candidate/config/verifier/run provenance and negative controls. Renderer success, path existence or event `done` never sets acceptance directly.

### Human interface

Desktop/web UI reads durable project state and may display separate `execution` and `acceptance` statuses. It does not synthesize every-scene green from subprocess return. GUI edits create explicit revisions/overrides that survive restart and can be diffed/replayed.

## Initial runtime state machine

```text
SceneAttempt: queued → leased/running → produced|failed|deferred
                                      produced → validating
                                      validating → accepted|rejected|blocked

AssemblyAttempt: waiting_inputs → running → assembled_unverified|failed
                                          assembled_unverified → accepted|rejected|blocked
```

`offline-placeholder` and `job-spec-only` are useful execution products but cannot transition to production-media accepted.

## Build-versus-integrate decisions

| Capability | Direction |
|---|---|
| Audio/project/scene revision truth | BUILD minimal Melosviz domain model |
| Generic editorial timeline interchange | INTEGRATE OTIO projection |
| Hybrid scene interchange | EXPERIMENT optional USD projection |
| ComfyUI/generative rendering | INTEGRATE external runtime |
| Other DCC/editor renderers | INTEGRATE adapters; no native-format lock-in |
| Durable distributed workflow engine | REJECT by default; revisit on measured need |
| Media probing/decode | USE FFmpeg/FFprobe |
| Creative automatic judge | AUXILIARY/calibrated only |
| Generic multi-agent MV planner | LEARN FROM existing research, not differentiation |

## Vertical slice that can mature

One real known audio fixture → ProjectRevision R1 → three stable scenes (two same backend) → actual artifacts → independent validation → exact ordered assembly → UI review → persist edit S2 → kill/restart app/renderer → R2 → reuse S1/S3 only under exact unchanged dependencies → rerender S2 → accepted R2 assembly. Export an OTIO projection and, only if relevant, a hybrid USD projection without replacing canonical state.

## Explicit non-goals until evidence changes

- building another generic timeline format;
- building another renderer/model;
- inventing a distributed workflow platform;
- using an LLM/vision critic as correctness authority;
- treating historical 50-ID/20-of-20 catalogs as the new denominator;
- rebuilding hybrid/DCC primitives already available through interoperable formats without a failed integration spike.

## Architecture acceptance criterion

This architecture earns acceptance when the vertical slice closes with restart/revision/evidence integrity; OTIO/USD/render-runtime spikes define their lossy boundaries; source/authority denominator is semantically resolved; and fresh independent review cannot produce an unexplained behavior/lifecycle/configuration/alternative. Until then it remains the preferred hypothesis, not the product contract.
