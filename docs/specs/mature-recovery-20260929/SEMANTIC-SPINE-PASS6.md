# Melosviz semantic spine resolution — pass 6

Frozen product source: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`. This file resolves the highest-risk tracked source family first; it is not the full semantic denominator.

## Tracked inventory

Two product-local inventories now cover **688 unique tracked blobs** across the selected product trees with no duplicate paths between parts A/B. Enumeration does not equal semantic resolution.

## Conductor / API / CLI spine

| Path/family | Meaning understood | Contradictions/obligations | Implementation/journey consequence | Verification consequence | Resolution |
|---|---|---|---|---|---|
| conductor/orchestrator.py | Yes | scene instance/result/assembly/media acceptance currently conflict with intended per-scene product semantics | central execution spine; false-green findings M-F02/03/04/09/10 | mounted 3-scene oracle required | PARTIAL: blocking contradictions remain |
| conductor/events.py | Yes | event `done` is execution state; outcomes live separately; in-process bounded bus is explicitly non-durable | cannot represent durable accepted product state or survive worker/process loss | acceptance receipts must be independent; dropped/reconnect cases | PARTIAL: architecture decision required |
| conductor/provenance.py | Yes | useful sidecar schema, but writer is direct/best-effort at caller; collector silently skips malformed JSON | provenance is supporting evidence, not authoritative acceptance store | corrupt/missing/partial sidecar must block acceptance; atomicity required if promoted | PARTIAL |
| conductor/render_cache.py | Yes enough for current gate | input fingerprint helps invalidation; output materialization identity defect remains | cache cannot qualify artifact solely from key/path/size | wrong-byte/origin/model/tool negative controls | PARTIAL |
| conductor/registry.py | Yes | scene_type is adapter selection; must not become scene identity | retain registry as routing primitive | same-type multi-scene fixture | RESOLVED for role, not all adapters |
| conductor/validate.py | Supporting | validates declared structures, not rendered truth | preflight only | cannot green output criteria | RESOLVED role |
| conductor/visual_diff.py | Supporting | comparison helper is not acceptance identity | optional review signal | evaluator limits required | RESOLVED role |
| bridge/server.py | Yes for mounted studio/generate/security paths | subprocess/result inference plus bridge bind boundary conflicts | mounted API path participates in false greens and security | CLI/API/UI receipts + bind/auth adversarial tests | PARTIAL/blocking |
| bridge/security.py | Yes for loopback/auth/path/quota | `loopback_check` fails open for arbitrary non-wildcard hosts | manual/dev bridge may bind LAN host while treated as loopback | RFC1918/public/hostname bind negatives; auth policy coupling | PARTIAL/blocking M-F13 |
| bridge/errors.py | Yes | problem+json formatting only | support surface | focused unit behavior | RESOLVED role |
| cli/main.py | Yes for generate/assemble/direct paths | generate reports assembly from non-null result, separate assemble scans filesystem | public machine interface needs typed outcome/acceptance | mounted CLI 3-scene oracle | PARTIAL/blocking |
| cli/partial_rerender.py | Supporting, detailed invalidation review still open | selective rerender semantics depend on first-class scene revisions | M-E03 dependency | R1→R2 selective edit/restart | OPEN/PARTIAL |
| api-spec/studio-pipeline.openapi.yaml | Contract source, not yet reconciled line-by-line | must reflect typed result states after experiment | public API compatibility | schema drift + negative response tests | OPEN/PARTIAL |

### Resolved architectural facts

1. `scene_type` selects an adapter; it is not sufficient scene identity.
2. Event completion, adapter outcome, artifact validity and product acceptance are distinct state axes.
3. The current in-process event bus cannot be the durable job/evidence store.
4. Provenance sidecars are useful lineage evidence but current best-effort/direct-write semantics cannot alone authorize acceptance.
5. A bridge bind to a non-loopback host is a security-sensitive configuration and must fail closed unless explicitly authorized.
6. CLI/API/UI must consume typed scene/assembly states rather than infer success from process return/object existence.

## Remaining spine blockers before M-E02 can become a normal implementation package

Run M-E01 on an actual checkout: full-source probe replay, relevant suites, mounted `viz generate`, complete artifact inventory and independent decode; resolve OpenAPI/result compatibility; finish partial-rerender invalidation semantics; establish exact public-state migration surface. M-E02 remains an experimental repair until those receipts return.
