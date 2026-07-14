#!/usr/bin/env bash
# Fetch signed MelosViz desktop release artifacts for offline / air-gap transfer.
#
# Downloads prebuilt Electrobun packages from GitHub Releases (not a vendored
# offline build — see docs/AIRGAP.md § Desktop prebuilt path).
#
# Usage (from repo root, on a networked host):
#   ./scripts/airgap_fetch_desktop.sh
#   MELOSVIZ_RELEASE_TAG=v0.4.0 ./scripts/airgap_fetch_desktop.sh
#   MELOSVIZ_DESKTOP_OUT=dist/airgap/desktop ./scripts/airgap_fetch_desktop.sh
#
# Requires: curl (or gh). Writes SHA256SUMS for downloaded files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${MELOSVIZ_GITHUB_REPO:-KooshaPari/Melosviz}"
TAG="${MELOSVIZ_RELEASE_TAG:-latest}"
OUT="${MELOSVIZ_DESKTOP_OUT:-${ROOT}/dist/airgap/desktop}"
BASE="https://github.com/${REPO}/releases"

mkdir -p "${OUT}"
cd "${OUT}"

resolve_tag() {
  if [[ "${TAG}" != "latest" ]]; then
    echo "${TAG}"
    return
  fi
  if command -v gh >/dev/null 2>&1; then
    gh release view --repo "${REPO}" --json tagName -q .tagName
    return
  fi
  curl -fsSL "${BASE}/latest" | sed -n 's/.*\/tag\/\(v[^"]*\)".*/\1/p' | head -1
}

RESOLVED_TAG="$(resolve_tag)"
if [[ -z "${RESOLVED_TAG}" ]]; then
  echo "airgap_fetch_desktop: could not resolve release tag (set MELOSVIZ_RELEASE_TAG)" >&2
  exit 1
fi

echo "fetching desktop artifacts for ${REPO}@${RESOLVED_TAG} → ${OUT}"

download_one() {
  local name="$1"
  local url="${BASE}/download/${RESOLVED_TAG}/${name}"
  if [[ -f "${name}" ]]; then
    echo "skip existing ${name}"
    return 0
  fi
  echo "GET ${url}"
  if command -v gh >/dev/null 2>&1; then
    gh release download "${RESOLVED_TAG}" --repo "${REPO}" --pattern "${name}" --dir . 2>/dev/null && return 0
  fi
  curl -fL --retry 3 -o "${name}" "${url}"
}

# macOS DMG is the primary supported desktop surface; Windows desktop is soft-fail in CI.
download_one "MelosViz-${RESOLVED_TAG}-macos.dmg" || echo "warn: macos DMG not found for ${RESOLVED_TAG}"

# Windows desktop artifact name varies (exe/msi/zip under win-desktop-out); try common patterns.
for pattern in \
  "MelosViz-${RESOLVED_TAG}-windows-desktop.zip" \
  "MelosViz-${RESOLVED_TAG}-windows.zip"; do
  download_one "${pattern}" 2>/dev/null || true
done

# Integrity companions from the release job (best-effort).
download_one "SHA256SUMS" 2>/dev/null || true
download_one "SHA256SUMS.cosign.bundle" 2>/dev/null || true

(
  find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | while IFS= read -r -d '' f; do
    rel="${f#./}"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum "${rel}"
    else
      shasum -a 256 "${rel}"
    fi
  done > SHA256SUMS.local
)

cat > README.txt <<EOF
MelosViz desktop offline artifacts (${RESOLVED_TAG})
===============================================

Transfer this directory with the air-gap bundle (see docs/AIRGAP.md).

macOS: open MelosViz-*-macos.dmg, drag MelosViz.app to Applications.
Windows: extract the desktop zip if present (CI packaging may be absent).

Verify:
  sha256sum -c SHA256SUMS.local
  # compare against release SHA256SUMS when downloaded

This is a **prebuilt release copy** path — not a vendored Electrobun offline
build (WBS-P4.3 remains deferred).
EOF

echo "wrote ${OUT} (tag ${RESOLVED_TAG})"
ls -la "${OUT}"
