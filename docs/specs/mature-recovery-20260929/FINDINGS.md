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


## M-F20 — bridge non-loopback guard is fail-open for arbitrary LAN/hostname binds (blocking security boundary)

`backend/src/melosviz/bridge/security.py::loopback_check` documents that anything other than a true loopback literal/localhost should require `MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1`. The implementation only rejects three wildcard hosts: `0.0.0.0`, `::`, and `*`. Every other string falls through to `return True, "loopback"`.

Concrete source-equivalent probe: `127.0.0.1`, `::1`, and `localhost` return allowed as intended, but so do `192.168.1.10`, `10.0.0.7`, and `example.com` with no public-bind override. `server.py` calls this guard directly before `uvicorn.run`, so this is mounted startup behavior rather than an unused helper.

The threat is compounded by the explicitly supported legacy auth-off mode: protected middleware only checks bearer auth when `MELOSVIZ_BRIDGE_REQUIRE_AUTH=1`, and path containment has a legacy branch that returns the requested path when auth is disabled and no explicit allowed-dir override is set. Packaged desktop normally enables auth, but manual/dev invocation can combine an arbitrary non-loopback `--host` with auth-off defaults.

Required repair experiment: parse host with `ipaddress.ip_address` when literal; allow only `.is_loopback`; resolve hostnames conservatively or reject non-`localhost` names unless explicit public-bind authorization is present. Add negative tests for RFC1918, link-local, public IPv4/IPv6 and arbitrary hostnames. Verify auth + allowed-dir policy is automatically required for any authorized public bind. Do not treat `0.0.0.0` coverage as proof of the general property.


## M-F21 — per-scene orchestrator dispatch calls whole-spec adapters, causing duplicated work and identity collapse (blocking)

The orchestrator constructs one dispatch tuple per scene, then instantiates the adapter and calls `adapter.render(render_spec, ...)` with the **entire RenderSpec**. The ComfyUI adapter explicitly documents and implements `render every scene of render_spec`; it extracts all scenes and writes `scene_NNN` subdirectories. Therefore two same-backend scenes cause two orchestrator invocations, and each invocation can render the whole storyboard again into the same scene-type directory. The corresponding C4D and Unreal adapters filter all scenes of their supported type and likewise loop all matching scenes on every call.

This is not merely `per_scene_results.setdefault(scene_type,...)` losing metadata after correct work. The work unit itself is wrong: **scene dispatch is not scene-bounded**. For N scenes sharing one of these adapters, the path can do repeated N×N scene work, overwrite/shared-directory artifacts, and emit one scene's queued/rendering/done envelope around adapter work that actually touched multiple scenes.

Existing event tests do not catch this. The multi-scene event test uses two `video_export` scenes and asserts only that each scene received queued→rendering→done; it does not assert adapter call identity, output cardinality or independent scene artifacts. The vertical oracle must therefore count backend invocations/artifacts as well as receipts.

Closure requires a scene-targeted adapter contract (scene ID/index + scene payload or equivalent) or an explicitly batch-targeted contract invoked exactly once. The orchestrator and adapters cannot both own iteration.

## M-F22 — Studio generate bridge manifest scans a layout different from the real orchestrator layout (blocking API journey)

`/api/studio/generate` claims that outputs live under `<out_dir>/<scene_type>/scene_*`, but after running the CLI it scans only `out.glob("scene_*")` — flat children of the output root. The real orchestrator passes `output_dir / scene_type` as each adapter's output path. ComfyUI, C4D and Unreal then write their own `scene_NNN` children **inside that scene-type directory**. Thus those real outputs are not discovered by the bridge's manifest loop.

The bridge regression test does not exercise this contract. It pre-creates `out_dir/scene_0/workflow.json`, mocks `_run_studio_subprocess`, then verifies that the pre-created flat directory is returned. It can pass even if the actual CLI/orchestrator layout is incompatible.

Consequences: the web StudioConsole can receive an empty scene manifest after real rendering and mark every requested scene as error/no artifact, while the Electrobun path bypasses this manifest and can mark every scene done on CLI return. The same product can therefore false-green or false-red depending on surface.

Closure: one canonical scene-result schema returned by the mounted generate operation; bridge discovers from structured receipts, not directory guessing. Integration test must run the actual generate path or at minimum the real orchestrator output-layout producer, not pre-seed the expected output.

## M-F23 — current release desktop is Electrobun; Tauri is a separate non-release surface

The frozen release workflow has explicit `macos-desktop` and `windows-desktop` jobs that run `bunx electrobun build/package` and upload Electrobun artifacts. No Tauri build appears in the release workflow. `src-tauri/` is a real buildable/scaffolded surface consuming `web/dist`, but it is not the frozen release desktop path.

Therefore mature/current implementation mapping should treat:
- Electrobun `desktop/` + its webview as the shipping native desktop candidate;
- `web/` as a separate browser/bridge surface and frontend reused by Tauri;
- `src-tauri/` as an alternate/historical/experimental shell until authority or release evidence promotes it.

This resolves one implementation ambiguity without deciding whether the mature product should continue to own both shells.


## M-F24 — two scene ontologies exist; only the weaker index/dict model is on the orchestration spine (blocking identity migration)

`analysis/models.py::RenderSpec` stores `scene_segments` as mutable `list[dict[str, Any]]`. The typed `SceneSegment` helper has an integer `index`, label/start/end and analysis summaries but no stable scene ID or revision. `cli/partial_rerender.py` targets and expands rerenders entirely by integer scene index.

Separately, `scene/models.py::SceneSpec` has a stable-looking `scene_id` plus hybrid assets/scanners. Search for `SceneSpec` construction finds the model itself, hybrid renderer helpers and tests, but no conductor/CLI path that makes `SceneSpec.scene_id` the identity of a RenderSpec scene. Search for `scene_id` in the orchestrator shows event/index/name use rather than consumption of the hybrid SceneSpec identity.

This means the repository currently has **two scene ontologies without a canonical identity bridge**:
1. audio/editorial `RenderSpec.scene_segments[index]` — the mounted orchestration path;
2. hybrid spatial `SceneSpec.scene_id` — a renderer/domain model exercised mainly through hybrid helpers/tests.

The old traceability claim that hybrid SceneSpec is DONE does not prove it is integrated into the mounted product journey.

Migration consequence: do not replace RenderSpec wholesale. Add stable `scene_id` and immutable `scene_revision` semantics to the mounted scene-segment contract with backward-compatible derivation/migration for historical specs, then reference optional hybrid SceneSpec/projection by that identity. Integer index remains order/position, not identity. Partial rerender should resolve a scene ID/revision to the current ordered index set and record why neighbors were invalidated.

Required oracle: reorder scenes without changing IDs; insert a new scene before S2; edit only S2; verify cache/evidence/rerender/assembly follow identity rather than old numerical position. Also prove a hybrid SceneSpec projection round-trips against the same scene ID instead of creating a second product object.

## M-F25 — the advertised web “Re-render this scene” journey cannot reach a render (blocking revision journey)

The web StudioConsole's edit action POSTs `/api/studio/direct` with `storyboard_path`, `scene_index`, `replace_prompt`, and `re_render: true`; it supplies neither `wav_path` nor `render_out`.

The bridge converts `re_render: true` to the CLI `direct --re-render` flag, adding `--wav` only when `req.wav_path` exists. The CLI `_cmd_direct` explicitly returns exit 2 when `--re-render` is requested without WAV. `_run_studio_subprocess` turns every nonzero CLI exit into HTTP 400. Therefore the current web button labelled “Re-render this scene” deterministically hits an error before a render can be launched.

Even with WAV supplied, `_cmd_direct` does **not** execute the render despite comments/docstrings saying “immediate” or “actually invoke.” The implementation sets `re_render_invoked = False`, constructs and prints a `viz generate ... --only-scenes ...` hint, and tells the user to paste it. The bridge/API descriptions claiming the request “also invoke[s] viz generate” are therefore false at the frozen source.

This blocks M-J-REVISE independently of cache correctness. Closure requires one truthful contract: either direct edit persists only and returns a next-action plan, or it actually schedules/executes a revision-bound render and returns that durable job identity.

## M-F26 — default render job identity is process-dependent and not a durable restart identity

`_cmd_generate` computes a default job ID as `job-{hash(str(out_dir)) & 0xFFFFFFFF:08x}` when the caller does not provide `--job-id`. No `PYTHONHASHSEED` configuration exists in the repository. Python string hashing is process-randomized; an isolated local check in this recovery environment produced different 32-bit values for the same path in two separate Python processes.

The web bridge avoids this for its immediate run by generating/passing an explicit job ID. Electrobun's RPC schema advertises an optional `jobId`, but its `runOrchestratedRender` implementation does not destructure or forward it, and the desktop view does not supply one. More generally, neither an event-bus job ID nor a process hash is a durable product revision/job identity.

Consequence: restart/recovery cannot use default `job_id` as the durable key required by M-J-RECOVER. A stable product job/revision ID must be persisted independently from the worker process and event-stream correlation ID.

## M-F27 — cache identity omits reference/character render inputs despite comments claiming edit_count invalidates caches

`_cmd_direct` increments storyboard-level `edit_count` with the comment “so downstream caches invalidate.” `_cmd_generate` does not carry `edit_count` into the render spec or scene cache key. Cache invalidation actually depends on fields selected by `SceneCacheKey.from_scene`.

The cache key includes prompt, seed, dimensions/fps, camera, scene-level continuity subject/env tokens, palette, lyric phrase, audio fingerprint and `cache_extra`. It does **not** include the stamped `reference_image`, `ip_adapter_image`, `reference_image_strength`, or character reference paths/weights that the orchestrator later forwards to adapters. The orchestrator stamps those render-affecting fields onto scenes **before** cache lookup, but the key ignores them.

Therefore changing a storyboard-level reference image/strength or resolved character reference can leave the cache fingerprint unchanged and reuse media rendered from different visual inputs. The global `edit_count` does not rescue this.

Closure requires cache identity to cover every render-affecting dependency by immutable content/config identity, not a manual edit counter. Add negative controls that change only reference image bytes/path, strength, character sheet/ref/model/workflow and prove the old artifact cannot qualify.

### Additional evidence for M-F20 — mounted classifier reproduction and startup implications

`bridge/security.py::loopback_check` only treats `_PUBLIC_HOSTS` (wildcards such as `0.0.0.0`, `::`, `*`) as public. After that branch, it returns `(True, "loopback")` for **anything else**. The docstring claims only loopback IP literals or `localhost` should pass by default, but the implementation therefore accepts RFC1918 addresses, link-local addresses, public IP literals and arbitrary hostnames without `MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1`.

The mounted bridge `main()` calls this helper before `uvicorn.run`, so the classifier participates in the real startup boundary. A source-equivalent pass-6 probe reproduced the false positives for `192.168.1.10`, `10.0.0.7`, and `example.com`, while true loopback controls passed and wildcard hosts were denied as expected. A full-checkout regression test is committed but not yet executed.

Public-bind authorization and bearer authentication are separate controls. A repair must fail closed for every non-loopback target unless explicit public binding is authorized, and startup must also require or explicitly waive an authentication/path policy for that public exposure. Do not treat packaged-desktop defaults as proof that manual/dev/server invocation is safe.


## M-F28 — Electrobun partial-rerender RPC schema and handler disagree on parameter names

The RPC contract in `desktop/src/rpc.ts` names the optional fields `reRender`, `renderOut`, and `renderOffline`. The corresponding Bun main-process handler in `desktop/src/index.ts` destructures `rerender` and `renderOutDir`, and does not destructure/use `renderOffline`.

Therefore a caller honoring the published TypeScript RPC schema does not supply the property names that the handler checks for `--re-render` and `--render-out`; the offline flag is ignored entirely by that handler. This is a deterministic interface mismatch in a mounted desktop RPC definition/implementation, even though current source search did not find `rpc.request.runDirect` used by the existing Electrobun view.

The web StudioConsole uses the separate FastAPI `/api/studio/direct` path, so this finding must not be generalized into “all edit/re-render is broken.” It does show that the desktop RPC surface and documentation cannot be treated as self-validating. Closure requires generated/checked schema parity and an actual consumer test that asserts the CLI argv, including negative cases for omitted versus supplied flags.


## M-F29 — render/job state is process-local or sidecar-derived; restart cannot reconstruct authoritative product state (blocking durable-lifetime journey)

The complete tracked-tree inventory and targeted source review found no project/job state store, resume API, or checkpoint state machine. This is no longer based on filename absence alone:

- `conductor/events.py` explicitly defines its event bus as in-process only; events live for the process lifetime/bounded ring buffer and there is no cross-process coordination.
- `render_cache.py` persists content-addressed artifact blobs + metadata, but it is a cache and its stats do not represent durable job transitions; cache existence cannot establish accepted product state.
- `provenance.py` writes per-artifact JSON sidecars and can scan them back, but orchestration writes are best-effort in observed paths and sidecars do not form an atomic ProjectRevision/RenderAttempt/Acceptance ledger.
- storyboard/project edits are JSON files; default job identity is separately process-dependent (M-F26).
- source searches over the finite tree found no resume/checkpoint/project/job-store implementation under the expected concepts.

Therefore killing/replacing the renderer/app cannot currently reconstruct authoritative queued/running/completed/accepted attempts from durable product state. Scanning artifacts, cache files, or filenames after restart would conflate execution residue with accepted truth.

This finding does **not** mandate SQLite. The required semantic spine is immutable project/scene revisions, render/assembly attempts, artifact/evidence identity and explicit state transitions. M-E03 must first compare (a) an atomic append-only/file manifest + write-ahead journal adequate for the single-user local product against (b) a small transactional SQLite metadata ledger. Select the smaller mechanism that survives the R1→restart→edit-S2→R2 adversarial journey without corrupting history. Distributed workflow engines remain escalation alternatives, not default product truth.


## M-F30 — authenticated bridge mode is incompatible with the direct web StudioConsole (blocking web/public deployment contract)

The standalone React `web/src/components/StudioConsole.tsx` has no authentication input in `StudioConsoleProps`. Its generic POST helper sends only `Content-Type: application/json`, and its render-event subscription uses the browser's native `new EventSource(...)`. Neither carries the bridge bearer token.

This matters because the bridge already supports `MELOSVIZ_BRIDGE_REQUIRE_AUTH=1`, and the M-ESEC candidate correctly extends bearer protection to `/api/studio/*` and `/api/render/*`. Under that policy the direct web StudioConsole cannot storyboard/generate/master/ship and cannot connect to render SSE.

The shipping Electrobun path is different and should not be conflated with this defect. Its Bun main process spawns the authenticated bridge, attaches `Authorization: Bearer ...` via `bridgeAuthHeaders()` to ordinary requests, and proxies render SSE using streaming `fetch` with the same headers. Thus M-ESEC can close the current release-desktop server boundary while leaving standalone web/Tauri authenticated operation blocked.

Do **not** solve this by putting a long-lived bearer token in an EventSource query string: URLs leak into logs/history/referrers and the candidate middleware intentionally does not accept query tokens. M-E03 must choose an authenticated web transport, e.g. a fetch-stream/polling client or a trusted local shell/proxy that injects headers. The web surface must also receive auth capability for its POST requests. If mature scope declares direct standalone web auth out-of-scope, record that authorized decision explicitly rather than silently leaving a broken advertised surface.
