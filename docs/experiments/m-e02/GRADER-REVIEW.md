# Experimental grader review — pass 9 source re-grade

Candidate branch: `experiment/mature-recovery-m-e02`. Baseline: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`.

Status: **BLOCKED ON EXACT-CANDIDATE EXECUTION. NO PRODUCT ACCEPTANCE.**

This supersedes the earlier source-level FAIL/REVISE review for the final branch tree. Earlier findings remain historical evidence; they are not deleted.

## Source contract now addressed

- scene-indexed results and selector precedence/filtering;
- one-scene projection per adapter invocation;
- isolated dispatch output roots;
- equal-size cache replacement;
- ordered real-render artifact collection into assembly;
- typed outcome in execution-done events;
- structured CLI/bridge scene manifest;
- web/desktop produced-vs-accepted distinction;
- nonempty garbage/malformed WAV no longer qualify by existence alone;
- production-looking video containers require ffprobe parseability; missing ffprobe blocks production-media classification;
- historical cache `render` metadata is revalidated against materialized bytes and downgraded to malformed when current validation fails;
- contract tests use real decodable WAV fixtures rather than text bytes named MP4;
- web status no longer assigns the removed `done` state; real render becomes `produced`, not independently `accepted`.

## Still required before experimental PASS

1. Run focused M-E02 tests on the exact branch head.
2. Run relevant pre-existing conductor/cache/bridge suites.
3. Run web TypeScript/build and Electrobun desktop type/build checks.
4. Run the external pass-5 media oracle against candidate-produced real media.
5. Exercise actual `viz generate` and bridge generate with two same-backend scenes; preserve adapter-call/media/event/result cardinality.
6. R1 → edit only S1 → restart → R2, with reuse/recompute evidence.
7. Run required mutation controls. A worker-authored test suite is not independent grading.
8. Bind receipts to exact commit, environment, tool/model/workflow configuration and raw artifacts.

The candidate's ffprobe validation is deliberately a product execution gate, not the final independent quality grader. Creative quality, beat correctness, color/delivery profiles and durable project persistence remain outside M-E02.

## Disposition

Keep experimental. If the execution matrix passes without weakening the external oracle, M-E02 may become **EXPERIMENTALLY ACCEPTED**. That still does not make Melosviz ready for general developer handoff or merge this branch automatically.
