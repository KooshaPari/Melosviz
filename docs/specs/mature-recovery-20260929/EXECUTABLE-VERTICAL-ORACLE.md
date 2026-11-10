# Melosviz executable vertical oracle contract — pass 1

Frozen source: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`. Status: oracle specification, not a passing test. It is designed to fail current false-green paths rather than accommodate them.

## Fixture

One short, redistributable/locally generated WAV with a verifier-owned SHA-256 and explicit sample rate/channel count. Three scenes with stable IDs `S1`, `S2`, `S3`; S1 and S2 deliberately share the same backend/scene_type. Each scene requests a visibly and machine-distinguishably unique nonce card (for example text/QR/solid-frame sequence) and has explicit start/end timing. S3 uses a different backend where an actually available qualified backend permits it; otherwise all three may share one backend because same-type identity is the critical case.

The accepted fixture stores expected project revision, scene IDs/revisions, input audio digest, expected order and timing. Backend/model/workflow/tool configuration is pinned in the evaluation receipt. No paid provider is invoked without explicit authorization.

## Mounted execution

Primary path: invoke the same CLI entry used by `viz generate <wav> --storyboard ... --out ...`. Secondary path: invoke the Studio bridge/desktop route that calls orchestrated render. Do not call `_artifact_rejection`, `Orchestrator.render`, or adapter helpers directly as the product-journey qualification.

Current expected baseline outcome is FAIL/BLOCKED because source tracing shows generated artifacts are not appended to assembly input, per-scene results aggregate by scene type, media acceptance can accept nondecodable bytes, and desktop UI infers all-scenes-done from subprocess return.

## Independent grader

The grader is a separate process/package boundary from the candidate render path and consumes raw filesystem/process receipts.

For each expected scene:
1. exactly one accepted scene receipt exists for that scene ID + revision;
2. artifact content digest is recorded and differs where fixture demands;
3. media is probed and actually decoded; unknown/failed decode is BLOCKED/FAIL;
4. expected video stream, dimensions/fps/timebase/duration are within accepted fixture tolerances;
5. scene nonce is independently detected or fixture-specific content predicate passes;
6. provenance binds project/revision, scene, audio digest, backend/tool/workflow/model/config and candidate.

For final assembly:
1. one accepted assembled artifact exists;
2. decoded timeline contains S1→S2→S3 in order;
3. intended audio digest/correspondence and duration are verified;
4. every accepted scene artifact is accounted for exactly once unless an accepted transition contract says otherwise;
5. assembly state is typed: `not_attempted | plan_only | assembled_unverified | accepted | failed`. Object existence is not a state transition.

## Negative controls

- replace S2 with valid media from another project/revision;
- create equal-size wrong target bytes before cache materialization;
- use 64 zero bytes named `.mp4`;
- corrupt provenance while keeping media valid;
- return a plan/job spec but no media;
- remove S2 while keeping S1/S3;
- swap S1/S2 order;
- make two scenes share scene_type and ensure receipts remain scene-specific;
- change only S2 and verify S1/S3 evidence remains applicable only if full dependency identity matches;
- change model/workflow/tool version without scene prompt change;
- kill renderer after one scene and replace worker;
- fail verifier/ffprobe/decode collector;
- let candidate return exit 0 while one scene is malformed.

Every negative control must make the relevant criterion non-green. If deleting a guard manufactures a green, add that mutation to the held-out/control set.

## UI/API acceptance invariant

Execution `done` is not acceptance. The Studio queue may display rendering/execution state, but 100% accepted requires the independent scene receipt. Current desktop behavior that marks every queue entry done after `runOrchestratedRender` returns is not acceptable evidence. Bridge/CLI responses must expose typed per-scene and assembly states rather than infer success from process return or non-null objects.

## Restart/revision sequence

Run R1. Stop/replace renderer process and product UI. Reopen durable project state. Edit only S2 through the supported human interface, persist revision R2, rerun. Grader checks:
- R1 history remains immutable;
- S2 gets a new scene revision/artifact/evidence;
- S1/S3 reuse, if any, binds to unchanged dependencies and exact bytes;
- final assembly binds R2 and contains the R2 S2;
- no worker/agent replacement loses accepted project truth.

## Evidence envelope

`product, project_id, project_revision, journey, contract_revision, criterion, candidate_sha/build/package_digest, scene_id/revision, input_asset_digests, backend/tool/workflow/model/configuration, environment, verifier+version, evaluation_id, timestamp, artifact_digest, raw_artifact_location, collection_status, observation, authority/provenance`.

Missing/skipped/stale/wrong-candidate/conflicting/collector-failed evidence cannot be accepted.

## Implementation changes implied, not yet authorized as final architecture

- first-class scene ID/revision in render target and result, never scene_type as identity;
- ordered per-scene artifact collection feeds assembly explicitly;
- media acceptance uses real probe/decode plus subject identity;
- cache materialization verifies content and origin;
- provenance/acceptance becomes required for product acceptance, not best-effort;
- CLI/API/UI expose typed execution and acceptance states;
- durable project/revision/job state survives replaceable renderer and development workers.

These are semantic obligations derived from observed false greens. Storage technology and exact API shapes remain architecture choices until alternatives/source coverage close.
