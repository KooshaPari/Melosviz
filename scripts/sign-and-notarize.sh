#!/usr/bin/env bash
set -euo pipefail

# Tauri codesign + notarize script for melosviz-desktop
# Usage:
#   TEAM_ID=<team-id> APPLE_ID=<apple-id> APP_PASSWORD=<app-password> \
#     ./scripts/sign-and-notarize.sh
#
# Required environment variables:
#   TEAM_ID      - Apple Developer Team ID (10-character string)
#   APPLE_ID     - Apple ID email for notarization
#   APP_PASSWORD - App-specific password for notarization

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESKTOP_DIR="${PROJECT_ROOT}/desktop"
SRC_TAURI_DIR="${DESKTOP_DIR}/src-tauri"
TAURI_CONF="${SRC_TAURI_DIR}/tauri.conf.json"

# Extract app name from tauri.conf.json
APP_NAME=$(python3 -c "import json; print(json.load(open('${TAURI_CONF}'))['productName'])" 2>/dev/null || echo "Melosviz Desktop")
APP_BUNDLE_NAME="${APP_NAME}.app"

# Bundle paths
BUNDLE_DIR="${SRC_TAURI_DIR}/target/release/bundle"
APP_BUNDLE="${BUNDLE_DIR}/macos/${APP_BUNDLE_NAME}"
DMG_DIR="${BUNDLE_DIR}/dmg"
DMG_NAME="${APP_NAME}.dmg"
DMG_PATH="${DMG_DIR}/${DMG_NAME}"

# Signing identity
SIGN_IDENTITY="Developer ID Application: ${TEAM_ID}"

echo "=== Melosviz Desktop Sign & Notarize ==="
echo "App:       ${APP_NAME}"
echo "Team ID:   ${TEAM_ID}"
echo "Apple ID:  ${APPLE_ID}"
echo ""

# Validate env vars
if [[ -z "${TEAM_ID}" ]]; then
    echo "ERROR: TEAM_ID environment variable is not set"
    exit 1
fi
if [[ -z "${APPLE_ID}" ]]; then
    echo "ERROR: APPLE_ID environment variable is not set"
    exit 1
fi
if [[ -z "${APP_PASSWORD}" ]]; then
    echo "ERROR: APP_PASSWORD environment variable is not set"
    exit 1
fi

# Validate tools
if ! command -v xcrun &> /dev/null; then
    echo "ERROR: xcrun not found. Run this script on macOS."
    exit 1
fi

# Step 1: Build Tauri app in release mode
# -----------------------------------------------------------------------------
echo "Step 1/4: Building Tauri app in release mode..."
cd "${SRC_TAURI_DIR}"

if cargo tauri --version &> /dev/null; then
    cargo tauri build
elif command -v cargo-tauri &> /dev/null; then
    cargo-tauri build
else
    echo "ERROR: cargo-tauri (tauri-cli) is not installed."
    echo "Install with: cargo install tauri-cli"
    exit 1
fi

if [[ ! -d "${APP_BUNDLE}" ]]; then
    echo "ERROR: Expected app bundle not found: ${APP_BUNDLE}"
    exit 1
fi

# Step 2: Sign the .app bundle
# -----------------------------------------------------------------------------
echo "Step 2/4: Signing .app bundle with codesign..."

# Sign with hardened runtime and timestamp
codesign --force --deep --sign "${SIGN_IDENTITY}" \
    --options runtime \
    --timestamp \
    "${APP_BUNDLE}"

# Verify signing
codesign --verify --verbose "${APP_BUNDLE}"

# Step 3: Create a .dmg
# -----------------------------------------------------------------------------
echo "Step 3/4: Creating .dmg..."
mkdir -p "${DMG_DIR}"

# Remove old DMG if it exists
rm -f "${DMG_PATH}"

# Create a temporary DMG, then convert to compressed UDZO
temp_dmg="${DMG_DIR}/temp_${RANDOM}.dmg"
hdiutil create \
    -srcfolder "${APP_BUNDLE}" \
    -volname "${APP_NAME}" \
    -fs "HFS+" \
    -format "UDRW" \
    -o "${temp_dmg}"

hdiutil convert "${temp_dmg}" -format "UDZO" -o "${DMG_PATH}"
rm -f "${temp_dmg}"

# Sign the .dmg as well
codesign --sign "${SIGN_IDENTITY}" --timestamp "${DMG_PATH}"

# Step 4: Notarize the .dmg
# -----------------------------------------------------------------------------
echo "Step 4/4: Notarizing .dmg with xcrun notarytool..."

xcrun notarytool submit "${DMG_PATH}" \
    --apple-id "${APPLE_ID}" \
    --team-id "${TEAM_ID}" \
    --password "${APP_PASSWORD}" \
    --wait

# Staple the notarization ticket to the .dmg
echo "Stapling notarization ticket..."
xcrun stapler staple "${DMG_PATH}"

# Verify stapling
xcrun stapler validate "${DMG_PATH}" || true

echo ""
echo "=== Done ==="
echo "Notarized .dmg: ${DMG_PATH}"
