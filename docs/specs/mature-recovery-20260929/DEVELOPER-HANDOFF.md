# Melosviz developer-agent handoff

**READY FOR EXPERIMENTAL IMPLEMENTATION. NOT READY FOR GENERAL DEV HANDOFF.**
Updated 2026-09-29, pass 5. Source under test: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`. Specification branch: `docs/mature-recovery-20260929`. Draft #297; registry draft #593. Only Khostty and Melosviz are product subjects.

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

**M-ESEC — bridge bind fail-closed repair (READY NOW, independent of M-E02).** Own `backend/src/melosviz/bridge/security.py`, focused bridge startup/security tests, and only the necessary startup policy hook in `bridge/server.py`. Start from `pass6/test_bridge_bind_contract.py`: frozen main should fail non-wildcard LAN/hostname cases. Repair must accept only true loopback without override; any authorized public bind must have an explicit auth/path policy. Do not mix rendering/result-schema changes into this worktree. Closure: RFC1918/link-local/public IPv4/IPv6/hostname negatives, explicit-public positives, and startup integration receipt.

M-E01 may run alongside Khostty K-E01/K-E02/K-E03 and M-ESEC in separate worktrees. M-E02 and M-E03 share a contract dependency and must not write concurrently before it is reviewed. Registry receives compact receipts, not a competing canonical contract.

## Stop conditions / forbidden shortcuts

Stop and record a blocker for missing authorized tool access, a genuinely new product-scope choice, a proposed merge/release, or a material public-schema change that would constrain the mature architecture. Do not run mutation tests against the authoritative working tree. Do not change expected scene IDs/order, disable decode/time checks, shrink the denominator, skip cases to green, or claim a declared candidate hash authenticates an execution. The grader and expected policy need separate reviewer control.

## Authority correction

Earlier passes described April 18 acceptance as directly recovered. Pass 5's retrieval returned prior assistant summaries, and a targeted search excluding those summaries returned no primary conversation. Treat that historical acceptance as an imported/unverified attribution until the actual user message is recovered. The registry/repo ADR remains useful supporting evidence, not independent confirmation. This is not a claim the user never accepted it.

## General handoff blockers

Full semantic source ledger; authority/supersession reconciliation; complete mature obligations/quality/journeys; SOTA integration decisions and high-risk experiments; mounted product verification; complete bidirectional trace graph; current CI/catalog enforcement; fresh independent review. Existing workflows were NOT changed to enforce catalog quarantine in this pass. General and parallel GENERAL development remain blocked.
