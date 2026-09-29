# Melosviz semantic findings — pass 1

Inspected on 2026-09-29 at product `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf` and registry `85d7cd00cf59c379c05b740e8130a85b0d5bd31b`. Early source reconnaissance is not the final mature-contract implementation map.

## M-F01 — product horizon and surface authority conflict (blocking)

README promotes a browser visualizer; AGENTS.md describes a studio conductor, deprecates browser rendering and calls the desktop a Director's Console. SPEC.md lines 1–180 retain hybrid scene/scanner models and Electrobun/Rust surface claims. Registry ADR0003 anchors hybrid representation switching and structured GUI override round-trip to the earlier exploration. September registry STATE instead reports a Tauri artifact. None alone resolves the complete intended horizon.

History leads: `ff5f1fc4215ef6940b2c701b5ee04d2f275c58fb` (August 28 studio pivot), `99127a6ba8ff312f3fe4c26e352d7614566cf71e` (Rust removal), `b804174d7acc02a765a47ef4c5545abfdfdddaf1` (September 12 delivery work including Rust reintroduction), `316bac0be7c3c983d236825342e6853b4091a76a` (September 17 release-note reconciliation). These commit messages establish leads and author assertions, not independent user approval or verified implementation completeness.

Required: recover pivot authority and diffs, decide whether hybrid/live/simple-output and studio-generation are retained projections or explicitly superseded, then reconcile canonical docs without erasing history.

## M-F02 — nonempty unknown media is not independently verified (blocking)

Source `backend/src/melosviz/conductor/orchestrator.py`, blob `549e70a5741f43546af3d068b5444d54d47affc2`. `_is_zero_duration` recognizes WAV only and returns unknown for unsupported formats/errors. `_artifact_rejection` rejects absence/directories/zero bytes/known zero-duration WAV, but returns no rejection for other nonempty files. The render loop then assigns OUTCOME_RENDER to an artifact not classified malformed, placeholder or plan-only.

Concrete counterexample design: nonempty garbage named `.mp4`; malformed nonempty `.wav`; readable file with no decodable video; valid video for a different audio/spec/candidate. Needed oracle: media probe and actual decode, expected streams/timebase/duration, content identity and exact contract/configuration binding. Unknown collector result is BLOCKED, never accepted. This pass's source observation does not assert that every downstream release path accepts the file.

## M-F03 — same-size materialization is weaker than cache evidence identity (blocking)

The same source's `_materialise_cached_artifact` preserves an existing target when target and cache blob sizes match, without comparing their contents. The cache-hit branch emits done and continues without passing the materialized file through `_artifact_rejection` in this loop.

Counterexample: cached bytes `NEW!`, target bytes `OLD!`, equal size. A returned pathname can identify old content while the result describes a cache reuse. Also test corrupt cached media, wrong origin mode, stale model/workflow/tool, missing provenance and concurrent writers. This is a specific function-level identity risk, not an independently reproduced entire release failure.

## M-F04 — per-scene dispatch versus per-type results / assembly is unresolved (blocking)

Full orchestrator ranges were read. `collected_paths` initializes from caller-supplied `segment_paths`; the inspected render body does not append newly returned scene artifacts before forwarding that list to final assembly. `per_scene_results.setdefault(scene_type, result)` retains only the first result per type. Adapters receive the full RenderSpec in each per-scene iteration and share a scene-type output directory.

Needed witness: at least two distinct scenes using the same backend, nonidentical nonce-bearing outputs, no caller-supplied paths, exact one-to-one receipts and ordered final timeline. Inspect adapter and assembly implementations before claiming the full pipeline necessarily fails; they may perform their own collection. The observed orchestration alone does not establish scene completeness.

## M-F05 — execution done and product acceptance are not the same state

The loop emits a done event even after setting a malformed outcome, and the inspected call does not pass that outcome into event extras. Provenance records carry the outcome but are best-effort; write failures log and continue. Cache records also preserve non-production outcomes. A UI may interpret done only as execution completion, so an actual UI false green is not yet established.

Needed: explicit execution/acceptance state separation across events, persisted receipts, CLI/API/UI and shipping; missing receipt cannot qualify output. Test provenance write failure, placeholder reuse and event replay after worker replacement.

## M-F06 — an earlier global-offline claim is stale, not a current bug

AGENTS.md and constructor documentation say automatic offline detection sets MELOSVIZ_COMFYUI_OFFLINE. Current constructor code warns but deliberately does not mutate os.environ; the September delivery history records that repair. Do not report the historical global-mutation defect as still present. Adapter fallback behavior and production-required mode need separate current inspection.

## M-F07 — lineage and research do not yet justify existence

Registry `docs/boundary/backend-melosviz.md` records an older backend absorption into phenotype-python-sdk/packages/melosviz, at short commit bbeedd5; owner and ancestry were not verified. Keep it as a predecessor lead rather than move canonical ownership on this assertion.

External AutoMV overlaps generic multi-agent music-video planning/generation/verification. OpenTimelineIO, OpenUSD, ComfyUI and FFmpeg already solve substantial constituent problems. Candidate differentiation is an editable, audio-constrained, cross-tool, provenance-qualified workflow and possibly hybrid spatial scenes—not simply generating music videos. These claims remain unverified; research does not certify superiority.

## Source blobs

README `8489968676c2fe53fadbafa88444644fa93da6c8`; AGENTS `48c27ebde7523dd5fcefb2636c69ff6316df4df3`; SPEC `4dfb05bab8b415a40cd2bd5dfde4faec461cd08c`; STUDIO_PIPELINE `e35e1c982c2e80bd272f9de9e2c3db11e00c1f90`; orchestrator `549e70a5741f43546af3d068b5444d54d47affc2`. Registry ADR0003 `f77eb8f0da3093e8a8d2acd00f0de21b4cd906fb`; predecessor boundary `0f64c3fefe8845410a2e350efdf6d528d8aed5da`.
