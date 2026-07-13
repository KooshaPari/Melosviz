# MelosViz Desktop / Web — Threat Model (C02 L20 / G-C02-04)

Companion deep-dive for surfaces that are **lighter than the bridge** in
[`BRIDGE_THREAT_MODEL.md`](BRIDGE_THREAT_MODEL.md). Product-wide summary:
[`THREAT_MODEL.md`](THREAT_MODEL.md).

## Scope

| Surface | Code / entry | In scope |
|---------|--------------|----------|
| Electrobun main process | `desktop/src/index.ts` | Sidecar spawn, RPC→HTTP, file dialogs |
| Bridge sidecar | `backend/src/melosviz/bridge/server.py` | Loopback HTTP called by main |
| Desktop webview shell | `desktop/views/main/` | Local UI loading bridge results |
| Web R3F preview | `web/src/` (Vite + React Three Fiber) | Browser canvas consuming RenderSpec JSON |
| Host tools | `video_exporter.py`, `blender_exporter.py` | FFmpeg / Blender subprocesses |

**Out of scope (intentional non-goals):** multi-tenant IdP (OAuth/SAML), cloud
KMS/HSM, mTLS between desktop and bridge, notarization/code-signing org secrets.
Those remain accepted soft goals on C02 L21 / L22 — localhost Bearer + OS file
permissions are the current studio model.

## Trust boundaries

```
┌─────────────────────────┐     loopback HTTP      ┌──────────────────────┐
│ Electrobun main (Bun)   │ ─────────────────────► │ Python bridge sidecar│
│  - file dialogs         │   127.0.0.1:<port>     │  - path containment  │
│  - RPC handlers         │ ◄───────────────────── │  - optional Bearer   │
│  - spawn bridge / CLI   │     JSON RenderSpec    │  - rate / body caps  │
└───────────┬─────────────┘                        └──────────┬───────────┘
            │ webview / views://                               │
            ▼                                                  ▼
┌─────────────────────────┐                        ┌──────────────────────┐
│ Desktop HTML shell /    │                        │ Host tools           │
│ Web R3F (operator)      │                        │ FFmpeg · Blender     │
│  - render JSON UI       │                        │ argv list, no shell  │
└─────────────────────────┘                        └──────────────────────┘
```

1. **Main ↔ sidecar** — main owns the port and process lifetime; bridge binds
   `127.0.0.1` by default (`MELOSVIZ_BRIDGE_ALLOW_PUBLIC` required otherwise).
2. **Webview / browser ↔ JSON** — RenderSpec and plans are treated as
   **untrusted structured data** (no `eval`, no HTML injection of raw fields).
3. **Filesystem** — WAV / `out_dir` paths cross the process boundary; bridge
   `is_path_allowed()` is the containment gate.
4. **Host tools** — FFmpeg and Blender run as child processes with argv arrays;
   they inherit the operator’s OS identity (single-tenant local studio).

## Assets (desktop / web)

| Asset | Sensitivity | Notes |
|-------|-------------|-------|
| Local WAV / project paths | High | Revealed to bridge + exporters |
| RenderSpec / scene / camera JSON | Medium | Drives R3F + bpy scripts |
| Bridge bearer token (env) | High | When `MELOSVIZ_BRIDGE_REQUIRE_AUTH=1` |
| Preview MP4 / frame temp dirs | Medium | Written under user-chosen `out_dir` |
| Host tool binaries on `$PATH` | Medium | Integrity is operator / supply-chain |

---

## STRIDE — Electrobun main ↔ bridge sidecar

| Threat | Scenario | Mitigation | Evidence |
|--------|----------|------------|----------|
| **S**poofing | LAN peer hits bridge if bound publicly | Loopback default; public bind gated; Bearer + `hmac.compare_digest` when auth required | `bridge/security.py`; `BRIDGE_THREAT_MODEL.md` |
| **T**ampering | Malicious RPC body alters `wav_path` / `out_dir` | Path resolve + `is_relative_to(allowed_dir)`; reject 400 | `is_path_allowed()`; `test_bridge_security.py` |
| **R**epudiation | Operator disputes who triggered analyze/render | JSONL audit (`ts`, method, path, status, dur_ms) under `$MELOSVIZ_DATA_DIR` | `docs/PRIVACY.md` |
| **I**nfo disclosure | Bridge error leaks absolute paths / env | Sanitised errors; `/health` has no secrets | Bridge middleware |
| **D**oS | Webview or script floods sidecar | Per-IP rate limit + POST body cap (413); render quotas / circuit breaker | `RateLimiter`, `RenderQuota`, `CircuitBreaker` |
| **E**oP | Sidecar used as confused deputy to spawn shell | Main spawns fixed Python module path + port; no shell interpolation of user paths into command strings | `desktop/src/index.ts` `Bun.spawn([...])` |

**Residual risk:** Electrobun RPC trust is same-user local. A compromised main
process already has full OS access; the bridge hardens *accidental* exposure and
path traversal, not a hostile co-tenant.

---

## STRIDE — Web R3F / desktop shell (XSS · CSP)

| Threat | Scenario | Mitigation | Evidence |
|--------|----------|------------|----------|
| **S**poofing | Remote page pretends to be MelosViz UI | Desktop loads `views://` / packaged assets; web is operator-hosted Vite app (not multi-tenant SaaS) | `desktop/electrobun.config.ts`; `web/` |
| **T**ampering | Attacker injects script via RenderSpec string fields into DOM | UI renders JSON via text/JSON tree — avoid `innerHTML` / `dangerouslySetInnerHTML` for spec fields; R3F consumes numeric/color props, not HTML | Desktop inspector / web canvas patterns |
| **R**epudiation | N/A for pure client preview | Bridge audit covers server-side mutations | — |
| **I**nfo disclosure | XSS steals local paths shown in UI | Treat path labels as text nodes; no remote script origins in packaged shell | Shell HTML uses static markup + module scripts |
| **D**oS | Pathological RenderSpec freezes WebGL | Keep preview on modest keyframe density; backend Hypothesis/fuzz catches parse blow-ups earlier | `test_fuzz_renderspec.py`; cargo-fuzz / atheris |
| **E**oP | Script in webview reaches host FS | Webview has no direct FS; file pick goes through main RPC dialogs | `desktop/src/index.ts` open-file handlers |

**CSP posture (current + target):**

* Packaged desktop shell ships **static local scripts** only (no CDN). That is
  the primary XSS reduction today.
* Web Vite `index.html` does not yet declare a strict
  `Content-Security-Policy` meta/header — tracked as hardening, not a blocker
  for local-studio threat acceptance. Prefer `default-src 'self';
  `script-src 'self'; `connect-src 'self' http://127.0.0.1:*` when enabling
  CSP so R3F + loopback bridge keep working.
* Do not load remote fonts/scripts into the desktop webview without an explicit
  allowlist update.

---

## STRIDE — Local file path exfiltration

| Threat | Scenario | Mitigation | Evidence |
|--------|----------|------------|----------|
| **S**poofing | Forged path in POST body | Contained to `MELOSVIZ_BRIDGE_ALLOWED_DIR` / `$MELOSVIZ_DATA_DIR` / `$HOME` | `allowed_dir()` + resolve |
| **T**ampering | `../../../etc/passwd` or symlink escape | `Path.resolve` + `is_relative_to`; symlink targets must stay inside root | `test_bridge_security.py` traversal cases |
| **R**epudiation | Path read/write without trail | Audit JSONL records request path + status | Audit log |
| **I**nfo disclosure | Spec `metadata.source_audio` or errors leak home layout to a non-loopback client | Loopback default; auth on public bind; minimise absolute paths in API errors | Bridge bind guard |
| **D**oS | Point `out_dir` at huge / sensitive volumes | Operator-chosen dirs via native dialogs; quotas on concurrent renders | Desktop pickers + `RenderQuota` |
| **E**oP | Bridge reads outside allowlist via `file://` tricks | Only filesystem paths through containment helper — no arbitrary URL fetch of local files | `is_path_allowed` |

**Residual risk:** Within the allowlist, the operator can still open any file
they own. Exfil to a *remote* party requires either public bind + stolen token
or a compromised host process.

---

## STRIDE — Host tools (FFmpeg / Blender)

| Threat | Scenario | Mitigation | Evidence |
|--------|----------|------------|----------|
| **S**poofing | PATH hijack replaces `ffmpeg` / `blender` | Resolve via env override + `which`; probe `-version`; document trusted install in `AIRGAP.md` / packaging | `_resolve_ffmpeg_binary`; Blender path probe |
| **T**ampering | User-controlled strings spliced into shell | **No `shell=True`**; argv lists only (`subprocess.run([ffmpeg, ...])`, bpy script driver) | `video_exporter.py`, `blender_exporter.py` |
| **R**epudiation | Render job disputed | Bridge audit + local output artifacts | Audit + `out_dir` |
| **I**nfo disclosure | Tool stderr dumps paths / scene content | Captured for errors; not returned wholesale to remote clients | Exporter error wrapping |
| **D**oS | Infinite / huge frame jobs hang host | Subprocess timeouts; render concurrency + soft RSS caps | timeouts; `RenderQuota` |
| **E**oP | Filtergraph / bpy injection from palette or labels | Palette/colors treated as data (hex / RGB tuples); bpy script built from structured fields, not raw shell | Exporter builders; Hypothesis color/keyframe suites |

**External dependency note:** FFmpeg and Blender remain host-provided (C07 L70 /
`docs/AIRGAP.md`). Threat model assumes a correctly installed binary; supply-chain
integrity is covered under C06, not re-solved here.

---

## Explicit non-goals (IdP / KMS)

| Non-goal | Rationale |
|----------|-----------|
| OAuth / SAML / OIDC IdP | Single-user local studio; optional Bearer is enough (G-C02-03 accepted) |
| Cloud KMS / HSM for bridge token | Token is env-local; rotation in `docs/KEY_ROTATION.md` |
| Multi-tenant isolation | Declared single-tenant in `docs/PRIVACY.md` |
| Mutual TLS main↔sidecar | Loopback + process spawn identity |

## Related

* Product summary: [`THREAT_MODEL.md`](THREAT_MODEL.md)
* Bridge endpoints: [`BRIDGE_THREAT_MODEL.md`](BRIDGE_THREAT_MODEL.md)
* Disclosure: [`../../SECURITY.md`](../../SECURITY.md)
* Gap close: **G-C02-04** (desktop/web deep-dive parity with bridge)
