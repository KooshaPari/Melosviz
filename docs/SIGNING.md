# Code signing / notarization (prep)

Tracked as **W-224**. This doc is the operator checklist; certificates are
org-owned and not stored in-repo.

## Apple (macOS DMG)

1. Developer ID Application certificate in the org keychain / CI secret.
2. `codesign --deep --force --options runtime` on MelosViz.app.
3. `xcrun notarytool submit` + staple.
4. Attach notarized DMG to the GitHub Release.

## Windows (Authenticode)

1. Org code-signing cert (OV/EV) available to the release runner.
2. `signtool sign /fd SHA256` on `.exe` / installer.
3. Publish signed artifacts beside `SHA256SUMS`.

## Until then

- Releases ship **unsigned** desktop packages with SLSA attestations + cosign
  on the checksum manifest (`docs/PACKAGING.md`).
- Air-gap operators verify `SHA256SUMS` / cosign bundles manually.
