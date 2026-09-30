# Experimental grader review — 2026-09-30

Candidate: `experiment/mature-recovery-m-e02@1066a61cabadfd3578c1e3561d23b7b5943f2a8c`.
Baseline: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`.
Status: **FAIL / REVISE. No product acceptance.**

## What the candidate improves

The candidate is narrowly scoped to six files and directly addresses several M-E02 obligations:
- scene-indexed `per_scene_results`;
- constructor/render selector precedence and pre-dispatch bounds validation;
- single-scene RenderSpec projection per adapter invocation;
- per-dispatch output roots;
- equal-size cache overwrite defect;
- ordered artifact collection into assembly;
- typed outcome in done-event extras;
- structured CLI manifest consumed by bridge;
- desktop/web distinction between produced output and independent acceptance.

These are implementation improvements, not accepted evidence until executed.

## Blocking grader findings

### G-ME02-01 — media validity false green remains

The candidate leaves `_artifact_rejection` semantically unchanged for non-WAV containers. A nonempty garbage `.mp4` still has no rejection. The new `SceneAdapter` contract test writes text bytes to `clip.mp4`; that fixture is itself non-decodable media but is accepted as `OUTCOME_RENDER`, hashed, collected and sent to assembly.

This directly violates pass-8 artifact-identity acceptance and the independent oracle's `nonempty_garbage_mp4` control. Fixing scene cardinality while retaining byte-exists acceptance cannot pass M-E02.

Required repair: product execution may classify an adapter output as produced/unverified, but it may not label arbitrary nonempty bytes `render`/production media. Integrate a fail-closed media probe or change the outcome taxonomy so independent acceptance is required before a product-facing production state. The candidate test must use actual decodable media for its positive artifact path.

### G-ME02-02 — cache hit trusts historical outcome metadata without current media revalidation

On a cache hit, the candidate reads `scene_cache_meta(...).get("outcome")`, materializes bytes and can propagate `OUTCOME_RENDER` directly into per-scene result/done event. The added cache-hit test explicitly mocks metadata to `OUTCOME_RENDER` and uses bytes `cached-real-media`, not real media.

Content replacement is fixed, but evidence identity is not: stale/malformed cache bytes plus a historical render label can still become a current render outcome. Required repair: bind cache metadata to content digest + complete relevant configuration and independently validate the materialized media before a current production/accepted state.

### G-ME02-03 — web candidate violates its own queue status type

`StudioScene.status` was changed to `queued | rendering | produced | accepted | error`, but `runGenerate` still returns `status: "done" as const` for a render result. This should be rejected by the TypeScript build when this surface is compiled and semantically collapses the new state model.

Required repair: produced real media becomes `produced`, never `accepted` without independent evidence. Add a typecheck/build receipt for the exact candidate.

### G-ME02-04 — no independent execution receipt

The experiment head has only CodeRabbit combined status in the queried status API. No pytest/TypeScript/native renderer receipt bound to `1066a61…` was found. Commit messages and test source are not execution evidence.

Required evidence: run focused M-E02 tests, relevant existing conductor/bridge suites, TypeScript build/typecheck, and the external pass-5 media oracle against candidate-produced real fixtures. Preserve exact candidate/environment/commands/raw outputs.

## Non-blocking follow-up

The branch is 24 commits ahead of the frozen source, more churn than the six-file final diff suggests. Preserve the commit chain for review, but grade the final tree. Do not merge while the above critical failures remain.
