#!/usr/bin/env bash
# Codesign and notarize script for Melosviz Desktop (macOS).
# Produces a notarized .dmg ready for distribution.

set -euo pipefail

APP_NAME="Melosviz Desktop"
BUNDLE_ID="com.melosviz.desktop"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SRC_DIR}/src-tauri/target/universal-apple-darwin/release/bundle"
DMG_PATH="${BUILD_DIR}/dmg/${APP_NAME}_0.1.0_universal.dmg"
APP_PATH="${BUILD_DIR}/macos/${APP_NAME}.app"

echo "=== Codesign + Notarize ==="
echo "App: ${APP_PATH}"
echo "DMG: ${DMG_PATH}"

# 1. Codesign the .app bundle
codesign --force --deep --sign "Developer ID Application" \
  --entitlements "${SRC_DIR}/src-tauri/Entitlements.plist" \
  --options runtime \
  "${APP_PATH}"

# 2. Create .dmg (if not already built by tauri)
if [ ! -f "${DMG_PATH}" ]; then
  echo "Creating .dmg..."
  create-dmg \
    --volname "${APP_NAME}" \
    --window-size 800 400 \
    --icon-size 100 \
    --app-drop-link 600 185 \
    --icon "${APP_NAME}.app" 200 185 \
    "${DMG_PATH}" \
    "${APP_PATH}"
fi

# 3. Codesign the .dmg
codesign --force --sign "Developer ID Application" "${DMG_PATH}"

# 4. Notarize
echo "Submitting for notarization..."
xcrun notarytool submit "${DMG_PATH}" \
  --team-id "${TEAM_ID}" \
  --apple-id "${APPLE_ID}" \
  --password "${APPLE_PASSWORD}" \
  --wait

# 5. Staple
xcrun stapler staple "${DMG_PATH}"

echo "=== Done ==="
echo "Notarized .dmg: ${DMG_PATH}"
