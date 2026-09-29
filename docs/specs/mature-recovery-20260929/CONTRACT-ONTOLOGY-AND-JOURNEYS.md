# Melosviz candidate mature horizon, ontology and journeys

Program MR-20260929. Source 1aec20a2ba41a01ed557d1c7f63f9a0089f842cf. Status: PROPOSAL, NOT ACCEPTED; mature scope and later pivot authority remain unresolved. This is not a complete requirements catalog.

## Horizon recovered before stages

Earlier user-intent retrieval supports music-driven programmable visuals, including simpler loops/lyrics and advanced hybrid scenes, with strong script/API access and GUI review. Later repository history centers a multi-tool music-video studio. A candidate mature identity is an audio-constrained, editable visual-production conductor: durable structured intent and revisioned assets drive one or more rendering tools, human/agent edits remain inspectable, and deliverables are verified against their actual project and configuration.

That identity may retain hybrid/live and studio-generation as distinct projections. It may instead be narrowed by a later accepted decision. Do not resolve this by treating the latest code as authority. A new DCC, video model, general workflow platform or handwritten media engine is not automatically required; consult registry SOTA before building replacements.

## Product ontology: intersecting structures

| Projection | Principal entities and relations | Required distinction |
|---|---|---|
| Authored intent | Project identity, immutable revision, concept, constraints, approved overrides and decision provenance | Human instruction versus inferred creative suggestion |
| Music / time | Source audio digest, sample clock, timebase, analysis revision, beat/section annotations and uncertainty | Measured/estimated beat versus accepted editorial anchor |
| Editorial | Sequence, scene/shot identity, timing, transitions, track, references | A scene instance is not a backend type; two same-type scenes are distinct |
| Spatial / hybrid | Assets, representation, camera, material, scanner/mask, occlusion and transforms | Semantic scene model versus a renderer-specific file; applicability awaits scope decision |
| Production | Render job, scene attempt, tool capability/version, workflow/model/configuration, desired versus observed artifacts | Job-plan, offline rehearsal, real render and cache reuse are separate outcomes |
| Review / revision | Human or agent edit, structured delta, preview, acceptance/rejection and selective invalidation | Browser-local state or DCC-only change is not a durable canonical edit |
| Evidence / delivery | Criterion, run, raw media, provenance, artifact digests, qualified profile, bundle and release | 'Done', path existence, schema validity and product acceptance differ |
| Operations | Budget authorization, queue/lease, checkpoint, recovery, observability, install and support | Render executor lifetime is not durable project/job lifetime |

Do not flatten these into a single feature tree or multiply generic concerns across every scene feature. Applicable quality overlays bind to precise subjects/configurations: audiovisual timing, decode/profile correctness, budget/reliability, operator UX/accessibility, asset/workflow security, creative quality and evidence completeness. Accepted numerical targets are not recovered yet; no arbitrary latency, cost or creative-quality pass threshold is invented.

## Identity, timing and growth constraints

Candidate canonical keys distinguish project/revision, scene/shot revision, input asset digest, render configuration and artifact identity. A content-addressed cache entry needs matching inputs and origin evidence; path or size equality is not enough. Tool/workflow/model changes, scene edits and relevant neighbor transitions must invalidate the correct projection. Generated suggestions remain suggestions until accepted; confidence is not approval.

Audio synchronization needs a declared rational mapping from sample time to editorial/render time, plus explicit frame rounding and allowed error. Detector uncertainty is not eliminated by storing a BPM. A guarantee about edit/cut timing is not a guarantee that generative dancers move on beat. The oracle must state which promise is being evaluated and use an appropriate external reference.

Existing RenderSpec, SceneSpec and job formats are starting evidence, not a mandate to replace or duplicate them. The preferred migration extends a stable identity/time/receipt spine. OTIO and USD may supply projections, not necessarily the complete product truth model. Their integration/fidelity must be tested before architecture freeze.

## Candidate actor-to-outcome journeys

**M-J-PRODUCE:** creator imports known audio/assets, reviews analysis/constraints, creates an editable sequence, runs a real renderer, independently validates per-scene output, assembles and exports a playable intended deliverable.

**M-J-REVISE:** creator opens the project in the human interface, changes one scene, persists a structured revision, inspects the exact delta, selectively rerenders affected work, and reopens the same accepted state after restart.

**M-J-RECOVER:** operator loses an executor/service, restarts or replaces it, identifies completed versus incomplete scene attempts, resumes or deliberately reruns work, and retains correct provenance without false cache hits or duplicate scene acceptance.

**M-J-HYBRID:** artist uses accepted spatial/scanner/representation semantics and obtains a faithful render/projection. Live operation is a separate applicability axis awaiting scope reconciliation, not an implied capability of the studio demo.

**M-J-DELIVER:** recipient receives the required playable profiles and referenced assets/manifest, verifies their identity, reopens or traces the project as required, and can distinguish production media from plans/rehearsal placeholders.

## Stage projections over that horizon

An earliest usable projection closes a narrow approved M-J-PRODUCE outcome with actual media, durable project/scene identities and qualified failure reporting. Placeholder breadth is allowed but labeled unavailable/deferred. An MVP adds the required revision and recovery paths using the same core state, not a new disposable product. Beta widens selected adapters/configurations and closes their failure/quality cases. GA qualifies the accepted install/support/delivery/security/accessibility obligations. Mature is the full recovered contract, not a count or expansion quota.

Hybrid/live obligations cannot be discarded to manufacture an easier percentage; they must be assigned to justified stages or explicitly superseded by authority. Conversely, no assistant-created adapter inventory automatically becomes mandatory mature scope.

## Transition debt and specification record shape

Track browser-versus-studio and Tauri-versus-Electrobun authority; old backend/SDK ownership; scene-type versus scene-instance accounting; display/event 'done' versus accepted media; best-effort versus required evidence; and unpinned workflow/model reproducibility. Each needs compatibility/migration disposition and a witnessing journey, not just a rewrite ticket.

Future accepted obligations carry stable ID, statement, rationale, source/decision authority, parent capability, dependencies, product role, stages/configurations, journeys, positive/negative acceptance, quality references, actual work/implementation surfaces, verification strategy, required traces and growth disposition. Represent implemented/mounted/persisted/tested/evidenced/current/stale/conflicting separately. Requirement count remains an output of semantic decomposition, not a target.
