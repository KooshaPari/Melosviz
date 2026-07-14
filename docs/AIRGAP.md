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
| `desktop/` | Optional prebuilt Electrobun release artifacts (`INCLUDE_DESKTOP=1`) |
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

## Hermetic CI smoke (WBS-P1.6 / WBS-P1.14 / C06 L54)

CI does **not** ship a committed `vendor/` tree. Instead, supply-chain
`.github/workflows/supply-chain.yml` job `hermetic-smoke` exercises offline
install paths after a single online prefetch:

| Surface | Script | Offline step |
|---------|--------|--------------|
| Rust | `scripts/check_hermetic_smoke.sh` | `CARGO_NET_OFFLINE=true cargo check -p melosviz-mir --locked` |
| Python | `scripts/check_hermetic_python_smoke.sh` | `PIP_NO_INDEX=1 pip install --no-index --find-links=dist/wheelhouse-python-smoke` then `import melosviz` |

**Python wheelhouse flow (CI + operators):**

```bash
cd backend
uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/reqs.txt
uv build --wheel -o ../dist/wheelhouse/
python -m pip download -r /tmp/reqs.txt -d ../dist/wheelhouse/
# transfer dist/wheelhouse/ to air-gap host, then:
python -m venv .venv && source .venv/bin/activate
export PIP_NO_INDEX=1
pip install --no-index --find-links=../dist/wheelhouse melosviz-*.whl
python -c "import melosviz"
```

Locally (Linux / WSL):

```bash
make hermetic-smoke          # Rust offline check
make hermetic-python-smoke   # Python wheelhouse offline import
# or run the scripts directly under scripts/
```

Optional full-workspace offline Rust check:
`HERMETIC_WORKSPACE=1 ./scripts/check_hermetic_smoke.sh`.

A committed in-repo `vendor/` tree (`cargo vendor`) remains **optional** for
operators who need fully vendored Rust sources; CI wheelhouse/wheel prefetch
is the v2 gate. Operator air-gap install still uses the wheelhouse /
`cargo vendor` steps above.

## Desktop prebuilt path (Electrobun)

MelosViz desktop packages are built in CI and published to GitHub Releases. On a
networked host you can fetch signed artifacts for offline transfer without
vendoring the full Electrobun toolchain:

```bash
./scripts/airgap_fetch_desktop.sh
# → dist/airgap/desktop/ (DMG + SHA256SUMS.local)

# Include in the dated bundle:
INCLUDE_DESKTOP=1 ./scripts/airgap_bundle.sh
```

On the air-gapped host, open the macOS DMG or extract any Windows desktop zip
from the bundle's `desktop/` directory. Verify with `SHA256SUMS.local` and compare
against release `SHA256SUMS` when copied.

This is a **prebuilt release copy** path — not a fully vendored offline Electrobun
build (WBS-P4.3 full installer remains deferred).

## Verification

```bash
cd melosviz-airgap-YYYYMMDD
sha256sum -c SHA256SUMS
```

Release artifacts also ship `SHA256SUMS` + cosign bundle — see `docs/PACKAGING.md`.

## Limits

- Hermetic CI v2 uses prefetch + offline gates for **both** Rust (`CARGO_NET_OFFLINE`) and Python (`PIP_NO_INDEX` wheelhouse import). A committed `vendor/` tree remains optional.
- Desktop Electrobun packages: use prebuilt release copy (`airgap_fetch_desktop.sh`) or build on a networked host with Bun/OS toolchains.
- Authenticode / Apple notarization remain org-certificate workflows (W-224).
- Native mobile is out of scope (W-223).
