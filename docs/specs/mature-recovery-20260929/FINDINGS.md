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
