# MelosViz distribution policy

## Channels

| Channel | Audience | Signed? | Notes |
|---------|----------|---------|-------|
| GitHub Releases (`v*` tags) | End users / operators | Attestations + cosign on `SHA256SUMS` | Primary |
| GHCR `melosviz-bridge` | Operators / k8s | Image digest via GHCR | `Dockerfile` + `ghcr-bridge.yml` |
| Source (this repo) | Developers | N/A | MIT; use lockfiles |
| Air-gap tarball | Isolated networks | Bundle `SHA256SUMS` | `scripts/airgap_bundle.sh` |
| Air-gap desktop (prebuilt) | Isolated networks | Release `SHA256SUMS` + local checksums | `scripts/airgap_fetch_desktop.sh`; see `docs/AIRGAP.md` |
| PyPI / crates.io | — | — | **Not published** (see `docs/SUPPLY_CHAIN.md`) |
| npm | — | — | Packages marked `"private": true` |

## Support window

Only the latest `main` and the newest `v*` release are supported for security
fixes. Older tags receive best-effort advice only.

## Integrity expectations

Consumers **should**:

1. Verify `SHA256SUMS` from the release (and cosign bundle when present).
2. Prefer GHCR digests over floating `:latest` in production.
3. Install Python/Rust deps only from committed lockfiles (`uv.lock`, `Cargo.lock`).

Consumers **must not** treat unsigned third-party mirrors of MelosViz binaries
as authoritative.

## Prohibited / out of scope

- Publishing private-index typo-squats of MelosViz names
- Shipping unsigned Windows Authenticode / Apple notarized installers without
  org certificate ownership (tracked as W-224)
- Native iOS/Android stores (W-223)
- Claiming a fully vendored Electrobun offline build farm in-repo (WBS-P4.3
  deferred; prebuilt release copy is the operator mitigation)

## Related

- `docs/PACKAGING.md` — channel map + local build
- `docs/AIRGAP.md` — offline transfer
- `docs/SUPPLY_CHAIN.md` — dependency-confusion policy
- `SECURITY.md` — vulnerability reporting
- `LICENSE` — MIT
