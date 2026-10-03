# Melosviz scene identity migration — pass 6

Status: candidate migration contract for experimental implementation. Frozen source: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`. Motivated by M-F04/M-F09/M-F10/M-F14.

## Preserve the mounted contract; strengthen its identity

Do **not** replace `RenderSpec` with a new project format as the first repair. `RenderSpec` is consumed widely across analysis, CLI, conductor, renderer adapters, web mapping and tests. The compatible path is to enrich the mounted `scene_segments` rows and separate durable project state around them.

Candidate scene row additions:

```json
{
  "scene_id": "stable opaque/product ID",
  "scene_revision": 3,
  "index": 4,
  "start": 32.0,
  "end": 48.0,
  "scene_type": "comfyui_video",
  "hybrid_scene_ref": "optional stable scene projection ID"
}
```

`index` is the ordering projection at one ProjectRevision. It may change when scenes are inserted/reordered and must never identify cache/evidence/job state.

## Backward compatibility

For a historical RenderSpec with no `scene_id`, import/migration may derive an ID once from immutable import context (e.g. source-spec digest + original index) and then persist it. Do not regenerate the ID on every load. A name/label is human-readable metadata, not a uniqueness guarantee.

`scene_revision` increments only when identity-relevant accepted scene intent changes. Pure execution retries produce new RenderAttempt IDs, not new scene revisions. Reordering without changing scene intent creates a new ProjectRevision/order mapping but may retain scene revisions.

## Link the hybrid ontology rather than duplicating it

`SceneSpec.scene_id` should either equal/reference the mounted `scene_id` or become a named renderer projection owned by that scene. Its asset/scanner/material structures do not replace editorial timing or durable revision identity. A scene without hybrid content needs no SceneSpec.

## Cache/invalidation

Cache key/application identity must include at least `scene_id`, `scene_revision`, exact accepted input asset digests, backend/workflow/model/tool/configuration and any neighboring/transition dependency declared by the renderer.

Partial rerender policy changes from `target index ± N` as the truth to:

1. resolve requested `scene_id` at current ProjectRevision;
2. compute dependency/invalidation set (transition neighbors may still be position-dependent);
3. record the reason each scene was selected;
4. schedule attempts by stable scene revision;
5. allow reuse only when the complete dependency identity is unchanged.

The current neighbor-count policy may remain a simple initial dependency rule, but its output becomes a documented invalidation set, not implicit correctness.

## Adversarial migration fixtures

- historical spec lacking IDs imported twice → same persisted scene IDs;
- insert scene before S2 → S2 evidence/cache remains attached to S2, not old index;
- reorder S1/S2 → assembly ordering changes but artifacts remain associated with their scene IDs;
- duplicate labels/names → no identity collision;
- edit S2 only → scene_revision changes only S2; project revision changes;
- change a transition dependency → the exact neighbor set is invalidated and reason recorded;
- hybrid SceneSpec with mismatched scene ID → explicit rejection, not a new silent scene;
- stale API request using prior project revision/index → conflict/stale response, not mutation of current wrong scene.

## API transition

During compatibility window, CLI/API may accept `scene_index` but must resolve it against an explicit project revision and return the resolved `scene_id`. New machine interfaces should target scene ID/revision directly. Once all mounted clients migrate, index-only mutation becomes deprecated.

## Acceptance boundary

This migration is accepted only after mounted CLI/API/UI tests demonstrate identity under insertion/reordering/restart and the independent three-scene oracle binds artifacts/evidence to IDs. Schema tests alone do not close M-F14.
