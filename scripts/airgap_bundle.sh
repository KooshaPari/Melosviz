#!/usr/bin/env bash
# Build an offline / air-gap transfer bundle for MelosViz bridge + locks.
# Produces dist/airgap/melosviz-airgap-<date>.tar.gz with:
#   - docker image tar (optional, if docker available)
#   - backend uv/pip freeze hint + pyproject
#   - Cargo.lock + instructions for cargo vendor
#   - SHA256SUMS for included files
#
# Usage (from repo root):
#   ./scripts/airgap_bundle.sh
#   SKIP_DOCKER=1 ./scripts/airgap_bundle.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date -u +%Y%m%d)"
OUT="${ROOT}/dist/airgap/melosviz-airgap-${STAMP}"
IMAGE="${MELOSVIZ_AIRGAP_IMAGE:-ghcr.io/kooshapari/melosviz-bridge:latest}"

mkdir -p "${OUT}/locks" "${OUT}/docs"
cd "${ROOT}"

cp -f Cargo.lock "${OUT}/locks/" 2>/dev/null || true
cp -f backend/uv.lock "${OUT}/locks/" 2>/dev/null || true
cp -f backend/pyproject.toml "${OUT}/locks/"
cp -f docs/AIRGAP.md "${OUT}/docs/" 2>/dev/null || true
cp -f docs/PACKAGING.md "${OUT}/docs/" 2>/dev/null || true
cp -f docs/SUPPLY_CHAIN.md "${OUT}/docs/" 2>/dev/null || true

cat > "${OUT}/README.md" <<'EOF'
# MelosViz air-gap bundle

Transfer this archive to an offline host, then:

1. **Bridge image** (if `bridge-image.tar` present):
   `docker load -i bridge-image.tar`
   `docker run --rm -p 8765:8765 ghcr.io/kooshapari/melosviz-bridge:<tag>`

2. **Python from source** (online build host first):
   `uv sync --frozen` using `locks/uv.lock`, then copy the venv or wheelhouse.

3. **Rust crates** (online build host):
   `cargo vendor --locked --versioned-dirs` into `vendor/`, then
   `.cargo/config.toml` with `[source.crates-io] replace-with = "vendored-sources"`.

See `docs/AIRGAP.md` for the full operator procedure.
EOF

if [[ "${SKIP_DOCKER:-0}" != "1" ]] && command -v docker >/dev/null 2>&1; then
  if docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    echo "saving ${IMAGE} → bridge-image.tar"
    docker save -o "${OUT}/bridge-image.tar" "${IMAGE}"
  else
    echo "image ${IMAGE} not local; skip docker save (pull first or set SKIP_DOCKER=1)"
  fi
else
  echo "SKIP_DOCKER=1 or docker missing — omitting bridge-image.tar"
fi

(
  cd "${OUT}"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | while IFS= read -r -d '' f; do
    # portable checksum
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum "${f#./}"
    else
      shasum -a 256 "${f#./}"
    fi
  done > SHA256SUMS
)

mkdir -p "${ROOT}/dist/airgap"
ARCHIVE="${ROOT}/dist/airgap/melosviz-airgap-${STAMP}.tar.gz"
tar -C "$(dirname "${OUT}")" -czf "${ARCHIVE}" "$(basename "${OUT}")"
echo "wrote ${ARCHIVE}"
ls -la "${ARCHIVE}"
