# MelosViz air-gap / offline install

Operator procedure for transferring MelosViz into a network-isolated environment.
This is a **bridge + lockfile** bundle — not a full notarized desktop installer.

## Quick path

On a networked build host (same OS/arch as the target):

```bash
# Optional: pull the published bridge image first
docker pull ghcr.io/kooshapari/melosviz-bridge:latest

./scripts/airgap_bundle.sh
# → dist/airgap/melosviz-airgap-YYYYMMDD.tar.gz
```

Copy the tarball (USB / sneaker-net) to the air-gapped host and extract.

## Contents

| Path | Purpose |
|------|---------|
| `bridge-image.tar` | `docker load`able GHCR bridge image (if docker save ran) |
| `locks/uv.lock` + `Cargo.lock` | Frozen dependency graphs |
| `locks/pyproject.toml` | Python package metadata |
| `docs/` | PACKAGING / SUPPLY_CHAIN / this guide |
| `SHA256SUMS` | Integrity of bundle members |

## Offline bridge (container)

```bash
docker load -i bridge-image.tar
docker run --rm -p 8765:8765 ghcr.io/kooshapari/melosviz-bridge:latest
curl -sf http://127.0.0.1:8765/health
```

## Offline Python (wheelhouse)

On the networked host:

```bash
cd backend
uv sync --frozen
uv export --frozen --no-dev -o requirements-airgap.txt
uv pip compile requirements-airgap.txt -o /tmp/reqs.txt   # if needed
pip download -r requirements-airgap.txt -d wheelhouse/
```

Transfer `wheelhouse/` + `backend/src` and on the air-gap host:

```bash
pip install --no-index --find-links=wheelhouse "./backend[bridge]"
```

## Offline Rust (cargo vendor)

```bash
cargo vendor --locked --versioned-dirs vendor
```

`.cargo/config.toml`:

```toml
[source.crates-io]
replace-with = "vendored-sources"

[source.vendored-sources]
directory = "vendor"
```

Then `cargo build --release --locked -p melosviz-mir` with no network.

## Verification

```bash
cd melosviz-airgap-YYYYMMDD
sha256sum -c SHA256SUMS
```

Release artifacts also ship `SHA256SUMS` + cosign bundle — see `docs/PACKAGING.md`.

## Limits

- Desktop Electrobun packages still need a host with Bun/OS toolchains (or a prebuilt DMG/zip from GitHub Releases copied offline).
- Authenticode / Apple notarization remain org-certificate workflows (W-224).
- Native mobile is out of scope (W-223).
