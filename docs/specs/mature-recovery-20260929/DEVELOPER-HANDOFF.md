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

**M-E01 — baseline reproduction and full source inventory (start now).** Read all files; write only an experiment worktree's `tests/recovery/`, `docs/specs/mature-recovery-20260929/pass5/receipts/`, and external temporary outputs. First preserve frozen source, run full-source AST checks and the existing relevant conductor suites without modifying tracked source, then exercise real `viz generate` with at least two same-backend scenes and record CLI stdout, exit, artifact inventory and independent decoding. Inspect any failed dependency/model setup; never substitute a mock and label it E2E. Enumerate the complete Git tree with the registry source-inventory utility. Opening or enumerating a source does not semantically resolve it. Closure: exact candidate/environment/command/raw evidence; observed failures or a justified falsification of each reported defect.

**M-E02 — smallest typed scene/assembly repair experiment (after M-E01).** Own `backend/src/melosviz/conductor/{orchestrator,events,provenance,render_cache}.py` and associated focused tests on a dedicated `experiment/` branch. One scene instance must retain its own result; type chooses the adapter, not identity. Preserve ordered artifact collection and distinguish planned/executed/validated outcomes. Do not build a new workflow platform or database merely to repair these semantics. Present any public-schema change as an experimental contract delta. Closure: the same baseline counterexamples become non-green for the right reason, real positive controls remain valid, and the worker cannot change the reviewer policy to pass.

**M-E03 — mounted consumer propagation and restart witness (after M-E02 result contract review).** Own CLI/bridge/desktop consumers and tests, not E02's files concurrently. Report per-scene execution versus independent acceptance; remove object-exists/all-rows-done inference. Exercise one persisted scene edit, stop/restart the actual application/renderer, rerun and prove which work was reused. A synthetic R2 verifier selftest is NOT this restart witness. Closure: real CLI/API/UI observations with identity-bound media; no job plan or placeholder counted as accepted output.

**M-ESEC — bridge bind fail-closed repair (READY NOW, independent of M-E02).** Own `backend/src/melosviz/bridge/security.py`, focused bridge startup/security tests, and only the necessary startup policy hook in `bridge/server.py`. Start from `pass6/test_bridge_bind_contract.py`: frozen main should fail non-wildcard LAN/hostname cases. Repair must accept only true loopback without override; any authorized public bind must have an explicit auth/path policy. Do not mix rendering/result-schema changes into this worktree. Closure: RFC1918/link-local/public IPv4/IPv6/hostname negatives, explicit-public positives, and startup integration receipt.

M-E01 may run alongside Khostty K-E01/K-E02/K-E03 and M-ESEC in separate worktrees. M-E02 and M-E03 share a contract dependency and must not write concurrently before it is reviewed. Registry receives compact receipts, not a competing canonical contract.

## Stop conditions / forbidden shortcuts

Stop and record a blocker for missing authorized tool access, a genuinely new product-scope choice, a proposed merge/release, or a material public-schema change that would constrain the mature architecture. Do not run mutation tests against the authoritative working tree. Do not change expected scene IDs/order, disable decode/time checks, shrink the denominator, skip cases to green, or claim a declared candidate hash authenticates an execution. The grader and expected policy need separate reviewer control.

## Authority correction

Earlier passes described April 18 acceptance as directly recovered. Pass 5's retrieval returned prior assistant summaries, and a targeted search excluding those summaries returned no primary conversation. Treat that historical acceptance as an imported/unverified attribution until the actual user message is recovered. The registry/repo ADR remains useful supporting evidence, not independent confirmation. This is not a claim the user never accepted it.

## General handoff blockers

Full semantic source ledger; authority/supersession reconciliation; complete mature obligations/quality/journeys; SOTA integration decisions and high-risk experiments; mounted product verification; complete bidirectional trace graph; current CI/catalog enforcement; fresh independent review. Existing workflows were NOT changed to enforce catalog quarantine in this pass. General and parallel GENERAL development remain blocked.
