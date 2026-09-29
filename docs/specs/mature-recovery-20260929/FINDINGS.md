# Melosviz semantic findings — pass 2

Inspected on 2026-09-29 at product `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf` and registry `85d7cd00cf59c379c05b740e8130a85b0d5bd31b`. Historical PR/user-description text is evidence of repository-directed intent at that time, but not automatically the complete mature horizon.

## M-F01 — original hybrid/API-first horizon has user authority; no supersession witness was recovered (blocking architecture freeze)

Conversation archaeology recovered explicit April 18 user intent: scripting/API-first agent interaction with heavy GUI review/small manual adjustments; hybrid programmable music-video scenes using 3D/splat/depth, scanner/material sweeps, 360 club video, mesh/photo/splat domains and rotoscoping; plus simpler programmed graphics, lyric-driven videos and Canvas-style loops. The user explicitly accepted the concrete hybrid system design in that conversation.

The later studio pivot is real repository evolution. PR #210's user description adds lyrics/moodboard modules into the ComfyUI-centered studio work; PR #211's user description explicitly says the pre-pivot R3F visualizer and Rust MIR were fully replaced by the studio pipeline. That establishes directed implementation intent to replace those **implementations**, not an explicit user decision that the accepted hybrid/live/simple-output product outcomes were deleted.

Current README/AGENTS/SPEC/release descriptions still disagree. Until a supersession decision is recovered or made, architecture must preserve the accepted earlier outcomes as mature-contract candidates while allowing their implementation to change. Do not resurrect R3F merely because the outcome survives.

## M-F02 — artifact-validity tests currently certify bytes, not playable media (blocking)

`backend/tests/conductor/test_artifact_validity.py` defines `_RealClipAdapter` by writing 64 zero bytes to `clip.mp4` and asserts that outcome is `render`. The production helper rejects missing/directory/zero-byte files and known zero-duration WAV, but unsupported/nonempty containers are accepted.

This converts the prior hypothesis into an explicit **oracle defect**: the regression suite calls a non-decodable byte blob a real clip. Replace existence/size acceptance with independent probe/decode and expected stream/timebase/duration checks. FFprobe officially exposes streams, frames and frame counts; decode failure/unknown collector state cannot be green. Correct media identity still requires product/scene/audio/configuration binding beyond ffprobe.

## M-F03 — same-size cache target can retain wrong bytes (blocking evidence identity)

`_materialise_cached_artifact` skips copying when an existing target has the same byte size as the cache blob; it does not compare content. The cache-hit branch then emits done and records cached-scene provenance without re-running artifact validation in this loop.

Counterexample remains: cache blob `NEW!`, target `OLD!`, equal size. Content digest/atomic materialization plus origin evidence are required. Cache key hashing of scene/audio inputs is useful but does not prove the materialized output bytes or backend/tool/model/workflow identity unless those inputs are included and verified.

## M-F04 — generated scene artifacts do not feed final assembly in the inspected orchestrator (blocking journey closure)

This is now corroborated by a pre-existing repo finding: `docs/sessions/20260918-desktop-findings/FINDINGS.md §5.4` states `collected_paths` is initialized and never appended, so assembly receives only caller-supplied `segment_paths`.

Current frozen code still initializes `collected_paths = list(segment_paths or [])`, does not append per-scene artifacts in the render loop, and passes that list to `MEAdapter.render`. The assembly adapter does **not** compensate: with no segment paths and no AME it returns a job spec only; its ffmpeg fallback requires nonempty paths. Therefore an ordinary conductor invocation that renders scenes but supplies no external segment list does not assemble those freshly rendered artifacts.

Separately, `per_scene_results.setdefault(scene_type, result)` retains only the first result per backend type. These are product-state/accounting defects, not proof that every CLI path fails—some callers may explicitly supply segment paths. The vertical oracle must exercise the actual CLI/API path with multiple same-backend scenes and no injected rescue list.

## M-F05 — execution completion and accepted product state are conflated at the event boundary

The loop can emit a `done` event after classifying an artifact malformed; the event call shown does not include the computed outcome. Provenance carries outcome but writes are best-effort. Cache reuse also writes execution/provenance state independently of a durable acceptance decision.

A UI false-green has not yet been reproduced, but the architecture lacks a trustworthy invariant that done == accepted. Persist execution state and acceptance state separately; require evidence-complete acceptance before shipping/GA claims.

## M-F06 — stale global-offline bug corrected; do not resurrect it

Current constructor warns when ComfyUI is unavailable but deliberately does not mutate process-global `os.environ`. Historical work records that repair. Adapter-specific offline behavior and plan/placeholder typing remain separate review subjects.

## M-F07 — SOTA attacks generic orchestration, not the accepted product's stronger thesis

AutoMV already proposes full-song multi-agent music-video planning/generation/verification and reports a 30-song, four-language benchmark; its own paper says multimodal automatic judges still trail human experts. Generic multi-agent MV generation is therefore contested prior art, not Melosviz differentiation.

OpenTimelineIO already models clips/tracks/transitions/time ranges and adapter-based interchange; OpenUSD supplies layered/referenced scene composition; ComfyUI is an existing render runtime; ffprobe supplies media inspection primitives. Build custom only where the accepted audio/hybrid/edit/provenance semantics cannot be faithfully composed from these.

Candidate differentiation remains: durable API-first + GUI-reviewable structured intent, audio/timebase constraints across heterogeneous tools, accepted hybrid scanner/domain semantics, selective revision/recovery and independently qualified deliverables. These require experiment/pilot evidence.

## M-F08 — repository history itself documents repeated evidence-system weaknesses

The September 18 findings already recorded mutation tests editing tracked source in place and earlier cache activation/provenance defects. September CI history includes qgate failures, workflow parse failures and later repairs. This does not invalidate all current tests; it means historical 'green' labels need exact candidate/run/collector provenance.

The mature grader must therefore protect its own policy and source candidate: mutation/fuzz work belongs in isolated copies/worktrees; a test run that mutates the candidate under evaluation without immutable before/after identity cannot qualify that same candidate.


## M-F09 — mounted `viz generate` can report assembly_ok for a spec-only assembly (blocking user-facing oracle)

Tracing the actual CLI removes the earlier caller ambiguity. `_cmd_generate` constructs `Orchestrator(...)` with default assembly enabled and calls `orchestrator.render(spec, audio_path=wav_path)` **without** `segment_paths`. It then reports `"assembly_ok": result.assembly_result is not None`.

The frozen orchestrator initializes `collected_paths` only from caller-supplied `segment_paths`; it never appends freshly rendered artifacts. It passes that empty list to `MEAdapter.render`. MEAdapter deliberately returns a job-spec result when AME is unavailable and no segment paths exist; no assembly is performed. Because that object is non-null, the CLI can report `assembly_ok: true` for a run that assembled no generated scene media.

This is a concrete mounted-surface false positive. It is distinct from the separate `viz assemble` command, which scans the output directory for media. Closure requires the generate contract to either (a) feed exact per-scene accepted artifacts into assembly and validate the resulting media, or (b) report typed assembly states such as `not_attempted`, `plan_only`, `assembled_unverified`, `accepted` rather than object existence. Add a regression with two same-backend scenes and no injected segment list.

## M-F10 — the alternate real compose path also loses scene identity at dispatch

`backend/src/melosviz/compose/assemble.py` loops semantic assignments and, when `mock_adapters=False`, calls `_dispatch_segment(render_spec, asgn)`. That helper creates a fresh Orchestrator and calls `orch.render(render_spec, scene_types=[scene_type])`; it does not pass the assignment's scene index/identity. The orchestrator's explicit scene-type path dispatches **every** segment in the full RenderSpec matching that type, then `per_scene_results.get(scene_type)` returns the type-aggregated result.

Therefore a compose-plan “segment adapter_result” is not proven to correspond to that assignment when multiple scenes share a backend type. This reinforces the ontology decision that scene instance identity cannot be keyed by scene type. Closure needs a scene-ID/index-targeted render API with one-to-one receipts, not a type filter used as a segment selector.


## M-F11 — desktop Studio turns subprocess return into every-scene green (blocking human-interface truth)

The mounted desktop `onStudioGenerate()` pre-marks every queued scene `rendering`, calls `rpc.request.runOrchestratedRender(...)`, and if that call returns, loops over **every** queue entry setting `status: "done"` and `progressPct: 100`. It does not inspect per-scene outcome/provenance/decoded media before doing so.

This makes the event/acceptance ambiguity user-visible: malformed media, job-spec-only adapters, scene-type aggregation, or partial scene completion can be rendered as a full green queue if the subprocess returns normally. The UI must consume typed scene acceptance receipts (or clearly label execution completion) rather than synthesize product acceptance.

## M-F12 — July “100%” trace/completeness catalogs are invalid as current graders

`docs/intent/MelosViz.md` says Status Accepted and asserts exact beat-to-frame alignment, byte-identical reproducibility, 99% render success and 100% traceability. `docs/TRACEABILITY.md` declares “100% documented” across a fixed 50-requirement registry. `docs/COMPLETENESS.md` declares “20/20 DONE (100%)” and “Major Gaps: NONE.”

Current source findings falsify material assumptions behind those scores: media validity can accept a zero-filled MP4 fixture; mounted generate can report assembly success without assembled generated segments; scene identity collapses by type; desktop can mark all scenes done from subprocess return. The historical documents remain useful archaeology and source obligations, but their scalar scores and DONE labels are **quarantined from grading** until each underlying semantic obligation, current implementation surface and oracle is revalidated against the frozen/current candidate.

This is exactly why the new program has no target requirement count or inherited completion percentage.


## M-F13 — cache dependency identity omits material render inputs (blocking correctness/recovery)

Frozen `render_cache.py` claims that unchanged prompt/seed/size/model may reuse an artifact, but `SceneCacheKey` contains no model or workflow field. The convenience `scene_cache_key` derives `backend` from `scene["backend"]` or `scene_type`, not the actual adapter class/version selected by the orchestrator. It hashes continuity subject/env tokens but not the directly stamped `reference_image`, `reference_image_strength`, character reference fields, renderer binary version, model/checkpoint digest, custom nodes, or workflow graph unless a caller manually places them in `cache_extra`.

An isolated pass-6 reproduction changed reference image, reference strength, model and workflow independently; all four variants produced the same fingerprint. This means selective reuse can return an artifact produced under materially different render dependencies.

Closure requires an accepted dependency envelope whose hash is generated by the runtime, not caller convention: scene/project revision, exact adapter implementation/version, model/checkpoint/workflow/custom-node/tool configuration and referenced asset content digests as applicable. Unsupported/unknown dependency identity blocks reuse.

## M-F14 — provenance is not the advertised cache/product identity

`ClipProvenance` declares optional `storyboard_id` and `input_hash`, but the frozen orchestrator constructor call populating provenance sets neither. It also does not bind a project revision, accepted contract/baseline, candidate build digest, exact model/workflow/tool identities or verifier policy. Provenance writes are best-effort and swallowed on error.

Therefore the sidecar can describe an execution attempt without proving which accepted product revision/configuration it qualifies. Its existence is useful evidence, not acceptance. The MACE envelope in the recovery contract remains stricter than this schema.

## M-F15 — standalone assembly can reorder a valid timeline by backend directory (blocking)

`viz assemble` scans immediate output subdirectories in lexical order, then each subdirectory's media files in lexical order. The orchestrator stores scenes under `<out>/<scene_type>/...`. Therefore scenes alternating backend types can be grouped by backend during assembly rather than kept in storyboard/timeline order.

Pass-6 isolated reproduction with intended order image-000 → video-001 → image-002 → video-003 yielded image-000 → image-002 → video-001 → video-003. A valid media set can therefore become a semantically wrong final sequence even when every clip decodes.

Closure requires assembly input to come from an explicit ordered accepted-scene manifest/timeline, never filesystem discovery order.

## M-F16 — shipping classifies arbitrary extension-matched bytes as online deliverables (blocking delivery acceptance)

`build_delivery_package` recursively discovers files by extension, copies them, and sets `mode="online"` whenever the media list is nonempty. It does not require successful decode, accepted provenance, current project/revision membership or artifact digests in the package manifest. Stale media left under the job root is eligible if it matches a media extension and discovery rules.

Pass-6 isolated reproduction wrote 64 zero bytes as `scene_001/garbage.mp4`; discovery included it and the package mode became `online`. This contradicts documentation claiming SHA256/provenance-qualified manifests.

Closure: packaging consumes an accepted deliverable manifest bound to revision/configuration/evidence, verifies content identity and media validity, and treats offline/plan/stale/unverified assets as non-accepted even if they are packaged for debugging.

## M-F17 — selective rerender controls are currently non-operative in two independent places

Full frozen `orchestrator.py` contains exactly one occurrence of `self._only_scenes`: assignment in the constructor. The value is never read, so `viz generate --only-scenes` does not constrain per-scene dispatch.

Separately, `viz direct --re-render` builds and prints a `viz generate ... --only-scenes ...` command but deliberately does not launch it; `re_render_invoked` is initialized false and never set true. Bridge/desktop contracts describe this as optional rerendering. Therefore edit → selective rerender → reuse is not merely unverified; the current paths cannot satisfy it.

Closure requires a first-class scene-ID/revision target in the conductor, an actual bounded execution path, and evidence that only the intended dependency closure rerenders.

## M-F18 — scene-index base differs across HTTP and CLI contracts

Bridge documentation and OpenAPI define `StudioDirectRequest.scene_index` as 0-based (OpenAPI minimum 0). The CLI accepts only 1..N and resolves `scenes[scene_index - 1]`. The bridge forwards the HTTP integer unchanged to the CLI. Desktop render-queue indexing is 1-based, which can mask the mismatch for that client but does not repair the public API.

Index base cannot be part of implicit tribal knowledge. Mature identity should use a stable scene ID/revision; any positional compatibility field must have one explicit base at every boundary.

## M-F19 — execution/delivery UIs synthesize success from subprocess return across multiple stages

The desktop generate path marks every scene done/100% after the CLI call returns. Mastering can intentionally emit an offline `master_plan.json` and return 0 without real master media. Shipping can produce an offline/debug ZIP. Desktop handlers advance status to master/ship done based on request return rather than independent acceptance state.

Thus the earlier execution-vs-acceptance issue is systemic across generate → master → ship, not local to the scene queue. UI state must distinguish planned/executed/validated/accepted and surface the exact evidence subject.
