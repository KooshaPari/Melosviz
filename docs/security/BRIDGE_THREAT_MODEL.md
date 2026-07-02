# MelosViz Bridge — Threat Model (B8)

## Scope

The **bridge** is the optional FastAPI/uvicorn process in
`backend/src/melosviz/bridge/server.py` that the Electrobun desktop shell
talks to over localhost. The CLI subprocess fallback (`python -m
melosviz.cli.main`) does NOT route through the bridge and is out of scope
for this threat model.

The bridge accepts three operations:

| Method | Path      | Purpose                              |
| ------ | --------- | ------------------------------------ |
| GET    | /health   | liveness probe                       |
| POST   | /analyze  | WAV → RenderSpec JSON                |
| POST   | /build    | WAV → render plan JSON               |
| POST   | /render   | WAV + out_dir → write plan to disk   |

## Trust boundaries

1. **Loopback** — default bind is `127.0.0.1`. Any other bind address
   (`0.0.0.0`, `::`) requires `MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1` or the bridge
   refuses to start (exit code 2). This prevents accidental LAN exposure of
   a desktop-only process.

2. **Process boundary** — the bridge reads user-controlled WAV files from
   the local filesystem and writes JSON plans to a user-controlled output
   directory. Both must resolve inside the configured allowed directory
   (default: `$MELOSVIZ_DATA_DIR`, else `$HOME`). Path-traversal payloads
   such as `../../../etc/passwd` are rejected with 400.

3. **Auth** — when `MELOSVIZ_BRIDGE_REQUIRE_AUTH=1` (recommended for any
   non-loopback bind), every protected request must carry
   `Authorization: Bearer $MELOSVIZ_BRIDGE_TOKEN`. Token comparison uses
   `hmac.compare_digest` to avoid timing leaks. Missing header → 401;
   malformed scheme → 401; wrong token → 403.

## STRIDE-class threats and mitigations

| Threat                                         | Mitigation                                                                                  |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **S**poofing of caller identity                | Bearer token + hmac.compare_digest; auth required by env var on non-loopback binds.         |
| **T**ampering with the WAV or out_dir payload  | Path containment: resolve() and check `is_relative_to(allowed_dir)`. Reject 400 otherwise.  |
| **R**epudiation of admin actions               | JSONL audit log: ts, ip, method, path, status, dur_ms. I/O errors swallowed, never break req.|
| **I**nformation disclosure                     | /health is unauthenticated by design; does not leak config. Error messages sanitised.      |
| **D**enial of service (request flood)          | Sliding-window rate limit per remote IP, default 30 req/60s, env-tunable. 429 + Retry-After. |
| **D**oS via large payload                      | Body size cap (1 MiB default) on POST; rejected 413 before parse.                           |
| **E**levation of privilege via path traversal  | Path containment + symlink resolve; see `is_path_allowed()`.                                |

## Out of scope (intentional)

* **Network auth between processes** — bridge only listens on loopback by
  default; we do not implement mutual TLS for desktop↔backend.
* **End-to-end encryption of WAV bytes** — files are on the local disk;
  encryption at rest is the operator's responsibility.
* **Rate limiting beyond per-IP** — the limiter is in-process; for a real
  multi-worker deployment, swap in a Redis backend. The current limit
  guards against trivial abuse, not coordinated DDoS.
* **CSRF** — the bridge accepts no cookies and no cross-origin headers;
  CSRF does not apply to a localhost-only JSON API.

## Operational runbook

* **Enable auth for a non-loopback bind**:

  ```bash
  export MELOSVIZ_BRIDGE_REQUIRE_AUTH=1
  export MELOSVIZ_BRIDGE_TOKEN="$(openssl rand -hex 32)"
  export MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1
  python -m melosviz.bridge.server --host 0.0.0.0 --port 8765
  ```

* **Restrict the allowed directory** (default is `$MELOSVIZ_DATA_DIR` or
  `$HOME`):

  ```bash
  export MELOSVIZ_BRIDGE_ALLOWED_DIR=/srv/melosviz/staging
  ```

* **Tune the rate limit**:

  ```bash
  export MELOSVIZ_BRIDGE_RATE_LIMIT=120
  export MELOSVIZ_BRIDGE_WINDOW=60
  ```

* **Read the audit log**:

  ```bash
  tail -f "$MELOSVIZ_DATA_DIR/audit/bridge.jsonl" | jq
  ```

* **Run the regression suite**:

  ```bash
  cd backend
  PYTHONPATH=src \
    MELOSVIZ_DATA_DIR=/tmp/mvz \
    MELOSVIZ_BRIDGE_REQUIRE_AUTH=1 \
    MELOSVIZ_BRIDGE_TOKEN=test \
    python -m pytest tests/test_bridge_security.py -v
  ```

## Provenance

* Cycle-1: 11 RED tests written, ship-blocked by Hard Rule #18.
* Cycle-2: tests GREEN after `melosviz.bridge.security` module landed and
  `melosviz.bridge.server` wired the middleware + path containment +
  loopback guard.
* v37 audit flag: 0% on public-facing backend + file-upload (B8).
* v37 follow-up: see `docs/sessions/20260630-antigame-spectrum/` for the
  fuzz/chaos/SAST/DAST coverage added on top of these mitigations.
