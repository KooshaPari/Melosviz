# MelosViz — Contributor Guide

Thanks for contributing. MelosViz is a **spec-first** music-to-visual toolkit
(Python backend + Electrobun desktop + R3F web + Rust MIR/wgpu).

## Quick start

```bash
# Backend
cd backend && pip install -e ".[test,lint,bridge,analysis]"
python -m ruff check src/ tests/
python -m pytest -q

# Bridge
python -m melosviz.bridge.server --port 8765

# Web
cd web && bun install && bun run dev

# Desktop (macOS/Windows host)
cd desktop && bun install && bun run dev
```

Or use the [devcontainer](.devcontainer/devcontainer.json).

## Before you open a PR

1. Link an FR / NFR from [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) or
   [`docs/functional_requirements.md`](docs/functional_requirements.md).
2. Prefer a task from [`docs/WORK_DAG.md`](docs/WORK_DAG.md).
3. Run locally:
   - `cd backend && ruff check src/ tests/ && ruff format --check src/ tests/`
   - `cd backend && pytest -q`
4. Use the PR template (What / Why / How / Testing).
5. **DCO** — every commit must be signed-off (`git commit -s`) affirming the
   Developer Certificate of Origin (see below). Optional SSH/GPG signing:
   [`docs/COMMIT_SIGNING.md`](docs/COMMIT_SIGNING.md). Org branch protection for
   verified/signed commits is tracked separately (W-228).

## Developer Certificate of Origin

By contributing, you certify the [DCO 1.1](https://developercertificate.org/):

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

Sign-off line format: `Signed-off-by: Your Name <email@example.com>`

## Architecture pointers

- Product spec: [`SPEC.md`](SPEC.md)
- Architecture ADR: [`docs/adr/0003-spec-first-conductor.md`](docs/adr/0003-spec-first-conductor.md)
- Layout overview: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Bridge threat model: [`docs/security/BRIDGE_THREAT_MODEL.md`](docs/security/BRIDGE_THREAT_MODEL.md)
- Product threat model: [`docs/security/THREAT_MODEL.md`](docs/security/THREAT_MODEL.md)
- Desktop / web threat model: [`docs/security/DESKTOP_WEB_THREAT_MODEL.md`](docs/security/DESKTOP_WEB_THREAT_MODEL.md)
- Observability: [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md)
- Packaging: [`docs/PACKAGING.md`](docs/PACKAGING.md)
- Scorecard: [`audit/SCORECARD.md`](audit/SCORECARD.md)

## Code of conduct / security

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) and [`SECURITY.md`](SECURITY.md).
Report vulnerabilities via GitHub Security Advisories.
