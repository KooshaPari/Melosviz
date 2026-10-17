# Melosviz mounted product-state spine — candidate contract

Frozen implementation evidence: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`.
Status: **CANDIDATE CONTRACT FOR M-E02/M-E03 EXPERIMENTS — NOT ACCEPTED MATURE PRODUCT CONTRACT.**

This document resolves only the implementation ambiguities necessary to test a coherent vertical slice. It does not settle the unresolved mature product horizon, renderer portfolio, artistic-quality rubric, or original user-authority gap.

## 1. One canonical scene identity

The mounted product currently uses mutable positional dictionaries under `RenderSpec.scene_segments`, while the hybrid domain model separately owns `SceneSpec.scene_id`. Position, backend type and scene name are not stable identity.

Candidate invariant:

```
SceneIdentity = (project_id, project_revision, scene_id, scene_revision)
```

- `scene_id`: stable across reorder/insert and ordinary edits.
- `scene_revision`: immutable version of that scene's semantic/render-affecting content.
- `order_index`: projection of the current project revision, never identity.
- `scene_type`: adapter-selection/capability property, never identity.
- optional hybrid `SceneSpec` is a projection/reference keyed by the same `scene_id`, not a second product object.

Historical specs lacking IDs require an explicit migration/derivation rule. A derived ID must be persisted on first migration; it cannot be regenerated from current list position forever.

## 2. Exactly one iteration owner

Current source has both the orchestrator and major adapters iterating scenes. That is forbidden.

Preferred experiment:

```
orchestrator
  for RenderTarget(scene identity):
      adapter.render(target, scene_payload, project_context) -> AttemptResult
```

Adapters receive one scene target. Batch-capable adapters may expose a separate explicit `render_batch(targets,...)` capability invoked once by the orchestrator. A batch adapter must return one result per requested scene identity plus any batch-level result. It may not silently reinterpret a single-target call as the entire RenderSpec.

The experiment must retain compatibility adapters around existing tools rather than rewriting every renderer at once.

## 3. Separate execution result from acceptance

Candidate states:

```
AttemptState:
  queued
  running
  produced
  failed
  cancelled

ArtifactQualification:
  missing
  plan_only
  placeholder
  malformed
  decoded_unverified
  verified

AcceptanceState:
  pending
  blocked
  rejected
  accepted
  superseded
```

No state implicitly upgrades another.

- `done`/process exit means execution ended, not accepted.
- plan/job-spec existence cannot become media.
- decoded media is not necessarily the intended scene.
- accepted evidence for R1 cannot qualify R2 merely because the path still exists.
- cache hit describes origin/reuse, not qualification.

UI, CLI and API may project these states with simpler language but cannot fabricate a stronger state.

## 4. Typed per-scene result

M-E02 should prototype an explicit result shape equivalent to:

```json
{
  "project_id": "...",
  "project_revision": "...",
  "scene_id": "...",
  "scene_revision": "...",
  "order_index": 1,
  "scene_type": "comfyui_image",
  "backend": {
    "key": "...",
    "tool_version": "...",
    "workflow_digest": "...",
    "model_digests": []
  },
  "attempt_id": "...",
  "attempt_state": "produced",
  "artifact": {
    "path": "...",
    "sha256": "...",
    "kind": "video",
    "qualification": "decoded_unverified"
  },
  "evidence_ids": [],
  "acceptance": "pending"
}
```

Exact serialization/typing is experimental. The semantic fields are the obligation.

`OrchestratorResult.per_scene_results: {scene_type: result}` is not compatible with this invariant and must become scene-identity keyed/ordered results or a typed list with a uniqueness validator.

## 5. Assembly consumes accepted ordered subjects

Assembly input is not a directory scan and not a caller-maintained rescue list.

Given project revision R:

1. resolve expected scene identities in R's order;
2. require the applicable artifact/qualification criterion for every required scene;
3. bind each artifact by content digest + attempt/evidence identity;
4. construct the ordered assembly request;
5. produce an assembly attempt/artifact;
6. independently validate assembly;
7. only then set assembly acceptance.

Missing, duplicate, wrong-revision, stale, placeholder and conflicting artifacts block acceptance. An accepted transition may deliberately overlap/reuse media, but that rule is explicit.

## 6. Cache identity follows render dependencies

A cache key is an optimization key, not scene identity.

It must cover every render-affecting dependency, including at minimum where applicable:
- scene semantic revision/digest;
- source audio content/range identity;
- reference image/content digest and strength;
- character/reference-sheet/content/model identity;
- backend/tool/workflow/model versions/digests;
- prompt/seed/camera/palette/resolution/fps;
- relevant transition/neighbor dependencies;
- explicitly versioned renderer settings.

Changing only a manual `edit_count` is neither necessary nor sufficient. The cache metadata must record its origin attempt and outcome. Cache materialization verifies content digest rather than byte length.

## 7. Durable product truth survives workers

Development agent, renderer executor and product state are separate lifetimes.

M-E03 must persist:
- ProjectRevision;
- SceneRevision;
- Attempt state transitions;
- Artifact digests;
- Evidence/Acceptance bindings.

Process-local `RenderEventBus` becomes a projection/notification channel. Provenance sidecars and cache files remain useful derived artifacts but cannot reconstruct authoritative acceptance on their own.

Storage experiment: compare atomic append-only file journal/snapshot against a small SQLite ledger. Choose the smaller mechanism that passes the restart oracle; no workflow engine is presumed.

## 8. Mounted surface obligations

### CLI

`viz generate` returns a structured run/scene/assembly receipt. Human-readable output is a projection. `assembly_ok` may only mean accepted assembly, not non-null object.

`viz direct --re-render` either actually schedules/executes a revision-bound attempt or truthfully reports edit-only/next action. No documentation may call a printed command an invoked rerender.

### FastAPI bridge

Bridge responses consume the structured receipt, not output-directory globbing. HTTP scene identity is stable ID; positional compatibility is explicitly named/base-defined.

### Electrobun

Subprocess return may move attempt execution state, but queue acceptance follows structured scene receipts. Its authenticated bridge proxy remains valid for release-desktop networking.

### Web/Tauri

Direct web bridge calls need a defined authentication transport when bridge auth is enabled. Do not put bearer tokens into EventSource URLs. Tauri remains alternate/non-release until separately promoted.

## 9. Required M-E02 tests

The repair is not reviewable without these controls:

- two same-backend scenes => exactly one intended scene render per target or one explicit batch call;
- reorder S1/S2 without changing IDs => evidence follows IDs;
- insert S0 => old S1/S2 identity not renumbered;
- wrong scene valid media => non-green;
- garbage media => non-green;
- same-size cache substitution => non-green;
- reference image only changes => cache invalidated;
- character/model/workflow only changes => cache invalidated;
- plan-only adapter => produced/plan-only, never accepted-media;
- assembly missing S2 => blocked;
- execution exit 0 + one malformed scene => overall accepted journey false;
- stale R1 scene/assembly receipt against R2 => rejected/blocked;
- candidate attempts to weaken expected policy => grader remains independently pinned.

## 10. Promotion criterion

M-E02 may be promoted from experiment toward implementation only when the same mounted three-scene oracle that exposes the frozen defects closes under the candidate without weakening its independent policy, and the result shape is sufficient for M-E03 restart/revision work.

Passing unit counts, generated trace catalogs, UI green state or a new database do not satisfy this gate.
