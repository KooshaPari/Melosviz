# MelosViz Product Threat Model

Companion models:

* Bridge endpoints: [`BRIDGE_THREAT_MODEL.md`](BRIDGE_THREAT_MODEL.md)
* Desktop / web deep-dive (Electrobun ↔ sidecar, R3F XSS/CSP, path exfil,
  FFmpeg/Blender): [`DESKTOP_WEB_THREAT_MODEL.md`](DESKTOP_WEB_THREAT_MODEL.md)

This document covers the **whole product** (desktop, web, CLI, render adapters)
at summary level. Use the companions for surface-specific STRIDE tables.

## Assets

| Asset | Sensitivity |
|-------|-------------|
| User WAV / project files | High (local content) |
| RenderSpec JSON / render plans | Medium |
| Bridge bearer token | High |
| Release binaries / SBOM | Medium (integrity) |
| Optional cloud API keys (Firefly, etc.) | High (when configured) |

## Trust boundaries

1. **Local desktop process** — Electrobun main + Python sidecar (default).
2. **Localhost HTTP bridge** — loopback-only unless explicitly opened.
3. **Host tools** — ffmpeg / Blender / TouchDesigner invoked as subprocesses.
4. **Optional cloud adapters** — Firefly / AE nexrender (credentials TBD).
5. **Web surface** — browser / R3F talking to a local or remote bridge (operator-run).

## STRIDE summary (product-wide)

| Threat | Surface | Mitigation |
|--------|---------|------------|
| Spoofing | Bridge / web | Optional bearer auth; loopback default |
| Tampering | Release artifacts | SLSA attestations + CycloneDX SBOM |
| Repudiation | Bridge | JSONL audit log under `$MELOSVIZ_DATA_DIR` |
| Information disclosure | Path traversal | Path containment in bridge security |
| Denial of service | Bridge | Rate limit + body size cap |
| Elevation of privilege | Subprocess tools | No shell=True; env-gated public bind |

Desktop/web attack-surface detail (main↔sidecar, XSS/CSP, path exfil, host tools)
lives in [`DESKTOP_WEB_THREAT_MODEL.md`](DESKTOP_WEB_THREAT_MODEL.md) — closes
gap **G-C02-04**.

## Explicit non-goals

- Multi-tenant SaaS isolation / IdP (OAuth/SAML) — out of scope for local studio.
- Cloud KMS / HSM for bridge token — env-local rotation only (`docs/KEY_ROTATION.md`).
- Full hermetic/air-gap builds — tracked as supply-chain soft goal.
- Platform code signing / notarization — requires org secrets + Apple/Windows certs.

## Related

- Desktop / web detail: [`DESKTOP_WEB_THREAT_MODEL.md`](DESKTOP_WEB_THREAT_MODEL.md)
- Bridge detail: [`BRIDGE_THREAT_MODEL.md`](BRIDGE_THREAT_MODEL.md)
- Security policy: [`../../SECURITY.md`](../../SECURITY.md)
- Observability / alerts: [`../OBSERVABILITY.md`](../OBSERVABILITY.md)
