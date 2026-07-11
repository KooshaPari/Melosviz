# MelosViz privacy model (single-tenant)

MelosViz is a **local / single-operator** desktop+CLI tool. It is not a
multi-tenant SaaS.

## Data handled

| Data | Where | Retention |
|------|-------|-----------|
| Source WAV paths | Operator disk; path must stay under allowed dir | Operator-controlled |
| RenderSpec JSON | Out dirs chosen by operator | Operator-controlled |
| Bridge audit JSONL | `$MELOSVIZ_DATA_DIR/audit/bridge.jsonl` | See retention below |
| Metrics | In-process `/metrics` (ephemeral) | Process lifetime |

## Isolation

- Default bind is loopback; non-loopback requires `MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1`.
- Optional Bearer auth (`MELOSVIZ_BRIDGE_REQUIRE_AUTH=1`).
- Path containment rejects escapes outside the allowed directory.
- No shared cloud tenancy, org IDs, or cross-user storage in-product.

## Retention (audit JSONL)

Default recommendation: rotate or delete `bridge.jsonl` every **30 days**, or
when it exceeds **100 MiB**. Operators may ship the file to their own SIEM;
MelosViz does not phone home.

## Multi-tenant future

A hosted multi-tenant mode would require IdP, per-tenant storage isolation, and
a revised threat model — tracked as product backlog, not current scope.
