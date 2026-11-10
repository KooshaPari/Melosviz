# Melosviz vertical slice and oracle design

Status: CANDIDATE, not a built or accepted journey. Frozen source 1aec20a2ba41a01ed557d1c7f63f9a0089f842cf. Motivated by M-F01–M-F07; journeys M-J-PRODUCE, REVISE, RECOVER and DELIVER. Governance research: PhenoRegistry draft #593.

## Slice that matures the spine

Use a known audio fixture with independently recorded timing anchors and content digest. Author at least two distinct scenes on the same real backend so aggregation by scene type cannot masquerade as scene completeness. Persist a revisioned project, submit rendering through the actual mounted CLI/API, capture backend job identities, independently decode the outputs, assemble them in intended order with the intended audio, and verify one required delivery profile.

Open the real human interface, edit one scene, persist the structured revision, then restart the application and a rendering worker. Verify the edit survives, unaffected scene evidence remains applicable only when its complete dependency identity matches, affected scene/transition work is rerendered, and the exported media represents the new revision. Rehearsal plans/placeholder media cannot satisfy the production-render criterion. No paid tool execution is required without explicit authorization; choose an actually available qualified backend.

## Verification is distinct from rendering and creative critique

Deterministic oracles check expected scene set, unique identities, asset/tool/configuration hashes, actual decode, stream/profile attributes, timeline duration/PTS and audio correspondence. ffprobe/decode are reusable primitives, not proof of creative quality or musical intent. Evaluate creative fidelity separately using an accepted human rubric and calibrated automated critique; a high aesthetic score cannot compensate for wrong audio, missing scenes, missing evidence or unauthorized assets.

Numeric timing and quality tolerances require an accepted contract. Compute and record rounding from audio samples to render frames; do not silently accept an arbitrary epsilon. Separate editorial beat alignment, estimated-beat accuracy and generative motion alignment because they need different references and evaluators.

## Positive and adversarial cases

| Case | Fixture / intervention | Required result |
|---|---|---|
| Actual production | Distinct same-backend scenes, known audio, approved configuration | Every expected scene has a uniquely bound real-media receipt; final decoded timeline contains each in order |
| Unknown/malformed media | Garbage .mp4, malformed WAV, empty file, zero-frame file or missing decoder | FAIL/BLOCKED for the relevant media criterion, never render acceptance on size alone |
| Wrong scope | Valid clip from another scene/project/audio or previous revision | Reject evidence transfer despite a plausible filename/preview |
| Cache substitution | Equal-size different bytes at materialization target | Verify content identity or rematerialize; never claim the old bytes match the cached subject |
| Cache origin | Reuse plan/placeholder, change model/custom nodes/tool, or lose origin receipt | Do not upgrade rehearsal or unknown provenance into production evidence |
| Missing/conflicting evidence | Delete/corrupt sidecar or produce contradictory run receipts | Explicit unresolved/blocked state; execution completion is retained separately |
| Partial assembly | Same-type scenes, no caller-provided segment paths, one missing output | Ordered completeness check fails rather than returning a shortened successful deliverable |
| Dependency failure | Renderer unavailable, model missing, cancelled/timeout job | Typed deferred/failed/cancelled result; a saved job plan is useful but not a rendered outcome |
| Edit/restart | GUI-only edit, crash before persistence, new worker after render | Canonical revision is either durable and replayed or explicitly not saved; no silent lost edit |
| Authorization/security | Unapproved provider/cost, out-of-root artifact path, code-bearing untrusted workflow | Deny or require authorized scope; no hidden spend or privileged arbitrary execution |
| Regression | Remove decode, content-identity, scene-completeness or mode guard | Corresponding negative fixture becomes a false green and must be caught by an independent control |

These cases are semantic oracle design, not mass-generated tests. The current isolated helper probe is narrower than this slice and does not close it.

## Evidence envelope and authority-aware tracing

Bind product/project, capability/journey, accepted contract revision, criterion, source/build candidate, project/scene revision, input digests, tool/backend/workflow/model/configuration, environment, verifier/policy version, evaluation/run, timestamp and raw artifact/provenance. Store explicit collection status and outcome. A same-path/same-size artifact or an in-process event is not this identity.

Trace accepted intent ↔ design ↔ implementation ↔ tests ↔ raw evidence ↔ runtime observations, preserving relation provenance, validating actor and authority state. Imported assertion, agent inference, deterministic source fact, verified observation and authorized decision remain different. A 99% inferred relation cannot approve an obligation or suppress a conflicting fact.

The worker sees the rubric. Independently accepted policy and expected-case inventory are outside the implementation candidate's authority. A candidate cannot remove its failing criteria, relabel a placeholder, skip a collector or weaken the grader to advance. Missing, skipped, stale, empty, collector-failed and wrong-candidate evidence are non-green; critical dimensions cannot be averaged away. Scope deltas and implementation deltas are recorded separately.

## Three lifetimes and the retry loop

Development worker attempt is ephemeral: model/tools/process/worktree/lease/actions. Durable development effort persists specification revisions, plans, work packages, dependencies, reviews and grader receipts. Product state persists project/scene identities, accepted revisions/configurations, render jobs/artifacts, releases and evidence. **A render job is durable product-runtime state, not the development effort itself.** Its renderer executor may also be replaceable. Killing either development agent or renderer does not authorize loss or invention of accepted product truth.

Loop: accepted assignment → bounded source context → worker action → independent grader → multidimensional result → localized criterion/subject/expected-versus-observed feedback → retry/replan/clarify/escalate. Repeated failed attempts retain history; no replacement worker resets a regression. Distinguish functional coverage, real journey closure, evidence quality, traceability, regressions, performance/cost, reliability, security, accessibility/usability, uncertainty and transition debt. Comparable dated samples are required for delta/velocity/stagnation/thrashing; no trend or asymptote is inferred from this pass.
