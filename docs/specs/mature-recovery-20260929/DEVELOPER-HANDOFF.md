# Melosviz developer-agent handoff

**READY FOR PARALLEL EXPERIMENTAL IMPLEMENTATION. NOT READY FOR GENERAL DEV HANDOFF.**
Updated 2026-09-30, pass 6. Source under test: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`. Specification branch: `docs/mature-recovery-20260929`. Draft #297; registry draft #593. Only Khostty and Melosviz are product subjects.

This readiness applies to the bounded work packages below, not to the full mature product. No agent is authorized to invent missing accepted scope, select a new platform-wide architecture, weaken an oracle, merge, release, or spend on a provider.

## What is now executable

From a checkout of this specification branch (Python 3.10+; observed run used 3.13.5 and FFmpeg/FFprobe 7.1.5):

```sh
P=docs/specs/mature-recovery-20260929/pass5
python "$P/selftest_oracle.py" --out /tmp/mv-oracle-fresh-run
python "$P/probe_source.py" --repo . --out /tmp/mv-frozen-source-probes.json
```

Use a fresh output directory. The first command generates actual three-scene FFV1/PCM media and tests verifier behavior. It must report 28 expected/matched cases at the recorded verifier revision; later additions require explicit versioning, not maintaining a target count. It is NOT Melosviz acceptance. The second verifies the full frozen orchestrator Git blob and executable AST before isolated probes. That full-source replay was not run in the sandbox: only copied function bodies were executed there. The six probe observations include three defects and three controls; diagnostic exit 0 means successful reproduction, NOT product correctness.

`pass5/oracle.py` can separately evaluate reviewer-controlled policy + candidate receipt + output root. Its current profile is deliberately tiny/lossless and does not evaluate aesthetics, inferred beats, codecs such as AAC/ProRes, GUI state, or real tool provenance. Do not add this selftest to a product percentage.

## Bounded work DAG / ownership

**M-E01 — baseline reproduction + mounted contract validation (IN PROGRESS; continue now).** The frozen tracked-tree enumeration is already complete (688 exact blob rows); do not redo it except to verify hashes. Work in a dedicated experiment worktree and preserve candidate identity. Run full-source AST probe checks and relevant conductor/bridge/CLI tests without mutating tracked source; then exercise real `viz generate` with at least two same-backend scenes and capture invocation count, per-scene artifacts, output layout, CLI summary and independent decode. Exercise `/api/studio/generate` against those real outputs rather than pre-seeded directories. Separately invoke the web/direct contract with `re_render=true` and establish the baseline failure. Record whether a restarted Python process changes the default job ID and whether changing only reference-image/character inputs changes the cache fingerprint. Closure: raw evidence for M-F02/03/09/10/11/13/14/16/17/18, not merely existing unit-test greens.

**M-E02 — smallest typed scene/result/cache repair experiment (after M-E01 evidence).** Own `backend/src/melosviz/conductor/{orchestrator,events,provenance,render_cache}.py`, the minimum affected adapter entry contract, and focused tests. Choose exactly one iteration owner: scene-targeted adapters called once per scene, or explicit batch adapters called once per batch. A scene instance must retain its own result; `scene_type` selects implementation but is never identity. Ordered accepted artifacts must feed assembly. Cache identity must cover every render-affecting reference/character/model/workflow input by immutable identity. Separate planned/executed/validated/accepted states. Do not introduce a database unless M-E01 proves files cannot satisfy the accepted durable-state contract.

**M-E03 — mounted consumer + durable revision/restart witness (after M-E02 result contract review).** Own CLI/bridge/Electrobun/web consumers and tests, not E02 files concurrently. Fix the generate manifest to consume structured receipts rather than directory guessing. `direct` must truthfully either return a persisted edit-only result or schedule/execute a real revision-bound rerender; UI labels must match. Introduce a stable persisted product job/revision identity distinct from process/event correlation IDs. Exercise R1 → edit only S2 → restart UI/renderer/process → R2 and prove exact reuse/invalidation. A synthetic verifier R2 is not this witness.

**M-ESEC — bridge bind + route-policy repair (IN PROGRESS on draft #300; independent of M-E02).** Own `backend/src/melosviz/bridge/security.py`, focused bridge startup/security tests, and only the necessary startup policy hook in `bridge/server.py`. Start from `pass6/test_bridge_bind_contract.py`: frozen main should fail non-wildcard LAN/hostname cases. Repair must accept only true loopback without override; any authorized public bind must have an explicit auth/path policy. Do not mix rendering/result-schema changes into this worktree. Closure: RFC1918/link-local/public IPv4/IPv6/hostname negatives; explicit-public positives; public bind requires bearer mode + non-empty token + explicit data root; `/api/studio/*`, `/api/render/*`, and `/debug/profile` are protected when auth is enabled; adjacent bridge regressions pass; exact candidate receipt. Experimental candidate: `experiment/melosviz-bridge-security-pass6`, draft #300. Do not merge from this handoff.

M-E01 may run alongside Khostty K-E01/K-E02/K-E03 and M-ESEC in separate worktrees. M-E02 and M-E03 share a contract dependency and must not write concurrently before it is reviewed. Registry receives compact receipts, not a competing canonical contract.

## Stop conditions / forbidden shortcuts

Stop and record a blocker for missing authorized tool access, a genuinely new product-scope choice, a proposed merge/release, or a material public-schema change that would constrain the mature architecture. Do not run mutation tests against the authoritative working tree. Do not change expected scene IDs/order, disable decode/time checks, shrink the denominator, skip cases to green, or claim a declared candidate hash authenticates an execution. The grader and expected policy need separate reviewer control.

## Authority correction

Earlier passes described April 18 acceptance as directly recovered. Pass 5's retrieval returned prior assistant summaries, and a targeted search excluding those summaries returned no primary conversation. Treat that historical acceptance as an imported/unverified attribution until the actual user message is recovered. The registry/repo ADR remains useful supporting evidence, not independent confirmation. This is not a claim the user never accepted it.

## General handoff blockers

Full semantic source ledger; authority/supersession reconciliation; complete mature obligations/quality/journeys; SOTA integration decisions and high-risk experiments; mounted product verification; complete bidirectional trace graph; current CI/catalog enforcement; fresh independent review. Existing workflows were NOT changed to enforce catalog quarantine in this pass. General and parallel GENERAL development remain blocked.

## Pass 6 mandatory regression set for M-E01/M-E02/M-E03

The next agent must preserve these counterexamples as raw receipts before repair:

1. Two same-backend scenes: count adapter invocations and generated scene artifacts. Current source predicts whole-spec adapter work repeated per orchestrator scene. A passing repair must prove exactly one intended render action per scene (or one explicit batch action for the whole set), not merely three event rows.
2. Bridge layout: run actual `viz generate` through `/api/studio/generate`; verify returned manifest identifies nested `<scene_type>/scene_NNN` outputs. Pre-creating `out/scene_0` is prohibited as an integration fixture.
3. Electrobun truth: subprocess exit alone must not make all queue rows accepted/done. Feed one malformed/plan-only result and observe a non-green user state.
4. Web truth: bridge manifest absence must not convert real successful nested outputs to `No artifact emitted`; consume structured receipts rather than directory guesses.
5. Partial rerender RPC parity: a typed Electrobun `runDirect` request with `reRender`, `renderOut`, and `renderOffline` must produce the corresponding CLI flags/environment. Current handler uses different property names. If this RPC remains unused, mark/remove/deprecate it explicitly rather than silently keeping a false contract.
6. Assembly: `viz generate` may only report assembly accepted after actual scene media is assembled and independently validated; a non-null job spec is not assembly.
7. Media/cache: retain pass-5 garbage-media and equal-size stale-cache controls.

Do not repair these by changing only UI wording while leaving false product state underneath. The product-state/result schema is the spine; UI/CLI/API should project it.


## Live experimental drafts

- **M-E01 baseline:** draft #301, branch `experiment/melosviz-baseline-pass6`, frozen base `1aec20a2...`. Diagnostic tests intentionally assert current broken scene-dispatch and bridge-layout behavior; green means reproduction succeeded, not product acceptance.
- **M-ESEC security:** draft #300, branch `experiment/melosviz-bridge-security-pass6`, frozen base `1aec20a2...`. Production-code repair is isolated to bridge security/startup policy plus focused tests; keep separate from M-E02 scene/result work.

These two may run concurrently. **M-E02 is not ready until M-E01 receipts are reviewed. M-E03 is not ready until M-E02's result/state contract is reviewed.**


## Pass 6 M-ESEC review status

Draft #300 candidate `f43717dc25c0021c47b41f638e0ecd184942931c` remains **experimental / unaccepted**. The five-file diff is within the declared write scope. Source review supports the intended bind classifier, public-bind auth/token/root preconditions and prefix protection for Studio/render/debug routes. The dedicated evidence workflow has been tightened to run Ruff in addition to compile + focused/adjacent tests and artifact identity capture. Do not promote or merge until that exact candidate's dedicated workflow completes and raw receipts are inspected. The broader middleware currently rate-limits unprotected requests too; that is an unresolved operational-policy question outside this narrow repair and must not be silently redefined here.


## Pass 6 web/auth boundary discovered during M-ESEC review

M-ESEC may harden the server for the shipping Electrobun path without expanding into web UI work. The direct React StudioConsole currently has no bearer-token input: POST requests send no Authorization header and render progress uses native EventSource. Therefore authenticated `/api/studio/*` and `/api/render/*` cannot work from that surface. Do not weaken the bridge or put bearer secrets in SSE URLs to make the experiment green.

**M-E03 additionally owns the web auth projection:** choose an authenticated fetch-stream/polling transport or a trusted shell/proxy, add authenticated POST support, and prove 401/403/valid-token behavior. If standalone authenticated web is later explicitly removed from mature scope, preserve that as an authorized scope decision instead.


## Pass 6 delta — narrowed experimental target

Tracked-tree enumeration is complete at the frozen source: 688 exact blobs across every top-level tree, all recursive responses untruncated. Do not re-enumerate files.

Source tracing found two new blockers that M-E01/M-E02 must reproduce before repair:
1. The orchestrator dispatches once per scene but passes the whole RenderSpec; ComfyUI explicitly renders every scene per call, while C4D/UE render all matching scenes. Two same-backend scenes can therefore cause repeated whole-set work into shared directories while per-scene events imply isolated work.
2. The Studio bridge documents nested `<out>/<scene_type>/scene_*` outputs but scans only flat `out/scene_*`. Its regression test pre-creates the flat directory and mocks the subprocess. The web path can false-red while the release Electrobun path marks all scenes done on CLI return.

Release CI establishes Electrobun as the current packaged desktop; Tauri is a separate alternate scaffold/surface at this snapshot.

**Next executable Melosviz work:** on a runnable checkout, create a two-scene same-backend fixture and count actual adapter calls, media writes and event identities. Exercise the real bridge generate route without pre-seeding output. Preserve the failing receipts. Then make the smallest typed repair so iteration has exactly one owner (scene-targeted call OR explicit batch call), return structured per-scene results, and have bridge/UI consume those results rather than infer from subprocess exit or directory guessing. The independent media oracle remains reviewer-controlled and must reject placeholders/plan-only/wrong scene evidence.


## Pass 7 delta — selective rerender is currently inert

Do not assume `--only-scenes` works. Frozen source proves both selector entry points are dead: constructor `self._only_scenes` is assigned and never read; `render(..., only_scenes=...)` mentions the parameter only in signature/docstring. The CLI passes selection into the constructor. Therefore the advertised one-scene/neighbor rerender does not currently select conductor work.

M-E02 minimum patch should reuse existing `scene_index` identity already present in events/provenance/cache/API. Resolve one effective selector at render entry, validate/filter dispatch, and make exactly one layer own scene iteration. Replace `per_scene_results: {scene_type: result}` with a scene-indexed/ordered result projection. Do not invent UUID infrastructure unless later requirements prove storyboard indices insufficient. Add same-backend two-scene call-count assertions and verify unselected adapters/scenes are untouched.


## Pass 8 M-E02 acceptance contract

A candidate M-E02 repair is admissible only if all of these hold on the same exact candidate:

1. **Selector:** `--only-scenes=1` on a 3-scene fixture invokes no adapter work for scenes 0/2. Invalid indices fail before rendering. Constructor/render selector ambiguity is removed by one documented precedence rule.
2. **Iteration cardinality:** with S0 and S1 using the same backend, exactly two scene work units occur—not four whole-spec renders. The adapter contract is either scene-targeted once per selected scene or explicitly batch-targeted once; never both loops.
3. **Result identity:** result cardinality equals selected-scene cardinality and keys/order preserve scene_index. Same scene_type does not overwrite another result.
4. **Artifact identity:** every accepted real-media scene has its own artifact + digest/provenance; malformed, unavailable, placeholder and plan-only outcomes remain non-accepted.
5. **Assembly connectivity:** accepted scene artifacts (including qualified cache hits) enter assembly once, in storyboard order. The final assembly may not infer inputs by globbing or receive an empty list after successful scene renders.
6. **Events:** queued/rendering/done remain execution telemetry. A done event must expose typed outcome or consumers must separately fetch typed result; no UI may translate bare done/process exit into accepted green.
7. **Bridge/UI:** generate returns structured scene results from conductor truth. No pre-created directory fixture or filesystem-layout guess may stand in for the producer contract.
8. **R2:** edit only S1, restart the relevant process, rerender requested policy, and prove reuse/recompute by identity. The independent oracle, controlled outside the candidate, must accept final media and reject stale R1 substitution.

Required negative mutations: restore `setdefault(scene_type,...)`; remove selector filter; make adapter render full spec; omit one collected artifact; swap assembly order; return exit 0 with malformed media; delay audio PTS; substitute equal-size stale cache bytes. Each must make at least one critical criterion non-green.


## Pass 9 authoritative product constraint

Current user intent makes **multi-scene composition the product spine**. Do not “fix” M-E02 by reducing the system to one scene per job or by treating the multi-scene fixture as merely a test convenience. The repair must make a composition with multiple, potentially heterogeneous scenes truthful end-to-end. A scene-targeted adapter call is an execution primitive inside a composition; the conductor still owns composition ordering, audio/timeline alignment, transitions, evidence and assembly.

Preserve future offline short/long-form and live projections: do not couple canonical scene/timeline identity to a specific offline renderer directory layout. Beat/rhythm, semantic/musical structure and editorial timing are distinct signals. M-E02 need not implement all of them, but it must not collapse the model so they cannot be added without replacing the spine.


## Pass 9 authority correction — multi-scene is mandatory product shape

Current user intent explicitly defines Melosviz as a multi-scene audio-conditioned visual generation/programming system. Agents must not optimize the architecture around a single generated scene. A scene is a composition work unit.

M-E02 positive fixture must therefore remain multi-scene and audio-bound. At minimum it must prove: distinct same-backend scenes; ordered timing; meaningful audio alignment anchors; transitions/neighborhood semantics where fixture uses them; selective revision; accepted assembly. Linear video is the first executable projection, not the only mature output. Preserve a path for live/festival playout over shared project/audio/scene intent rather than baking the canonical model around files-only offline assembly.

OTIO may be used as an editorial projection/interchange experiment for rational time/tracks/transitions/markers/media references, but it must not erase generative scene programs, audio-analysis uncertainty, backend/model/workflow identity or live-control state.
