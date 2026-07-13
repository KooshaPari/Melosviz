# Packaging & distribution channels

MelosViz ships install surfaces via `.github/workflows/release.yml` on `v*` tags.
This document is the Time-2 packaging map for audit-v38 cluster C11.

## Shipped today (CI)

| Channel | Artifact | Job |
|---------|----------|-----|
| macOS desktop | DMG via Electrobun | `macos-desktop` |
| Linux CLI | `melosviz-mir` + `melosviz-render` tarball | `linux-cli` |
| Windows CLI | `melosviz-mir.exe` + `melosviz-render.exe` zip | `windows-cli` |
| Windows desktop | Electrobun package (packaging soft-fail) | `windows-desktop` (install/build hard-fail; package/upload `continue-on-error`) |
| GHCR bridge | `ghcr.io/kooshapari/melosviz-bridge` | `ghcr-bridge.yml` |
| Air-gap tarball | `scripts/airgap_bundle.sh` → `dist/airgap/*.tar.gz` | local / operator |
| SBOM | CycloneDX Python + Cargo | `sbom` |
| Provenance | GitHub attestations + cosign | `release` |

## Windows CLI-only fallback

`windows-cli` is the supported Windows release path and is **not** gated on
desktop packaging. If `windows-desktop` fails at Electrobun `package` /
artifact collect/upload (soft-fail steps), the `release` job still proceeds
when `windows-cli` (and other hard jobs) succeed — ship CLI zip only.

Install + `cargo build` + Electrobun `build` on `windows-desktop` hard-fail
so regressions in those steps block the job. Only packaging/artifact steps
use step-level `continue-on-error` (job-level soft-fail removed; WBS-P1.10).

## From source

```bash
pip install -e backend/
cargo run --release -p melosviz-mir -- --help
cd web && bun install && bun run dev
```

## Windows local (desktop when CI packaging soft-fails)

```powershell
cd desktop
bun install
$env:ELECTROBUN_OS = "windows"
bunx electrobun build --env=stable
bunx electrobun package --env=stable
```

Provenance: GitHub attestations + CycloneDX SBOM + `SHA256SUMS` + cosign
keyless `SHA256SUMS.cosign.bundle` on each release (`release.yml`).

## SOURCE_DATE_EPOCH (release builds)

On `v*` tags, `release.yml` sets `SOURCE_DATE_EPOCH` from the commit timestamp
before Rust CLI builds. Linux packaging also stamps the CLI tarball with that
epoch (`tar --mtime=@$SOURCE_DATE_EPOCH --sort=name --owner=0 --group=0`).

This improves reproducibility for **Linux CLI binaries / archives**. It does
**not** make Windows MSI/zip or macOS DMG bit-identical across rebuilds — see
`docs/SUPPLY_CHAIN.md` § SOURCE_DATE_EPOCH for the honest scope table and the
`scripts/check_repro_smoke.sh` CI smoke.

## Auto-update

Release artifacts land on GitHub Releases with SLSA-style attestations.
Electrobun auto-update is wired via `release.baseUrl` in
`desktop/electrobun.config.ts` pointing at:

`https://github.com/KooshaPari/Melosviz/releases/latest/download`

Stable-channel builds (`bunx electrobun build --env=stable`) embed the
updater channel; the desktop main process calls `Updater.checkForUpdate()`
on startup and best-effort `downloadUpdate()`. Update manifests
(`stable-<os>-<arch>-update.json` + tarballs) are uploaded from
`desktop/artifacts/` by `release.yml`.

Dev-channel (`electrobun dev`) skips update checks by design.

## Mutation testing (weekly CI + local)

Weekly workflow: `.github/workflows/mutmut.yml`.

```bash
cd backend
pip install mutmut
mutmut run --paths-to-mutate src/melosviz/ --tests-dir tests/
# Target: >=75% mutation score per .qgate.toml
```

## Tray / menubar quick-actions (C11 L110)

The desktop shell (`desktop/src/index.ts`) creates a system tray icon on
startup via Electrobun's `Tray` API (`electrobun/bun` — ships in `1.18.1`,
no extra dependency). Menu items:

| Item | Action |
|------|--------|
| Show MelosViz | Unminimize (if needed) + show/activate the main window |
| Open Bridge Health | Opens `http://127.0.0.1:<port>/health` in the default browser (`Utils.openExternal`) |
| Quit | `Utils.quit()` — graceful app shutdown |

Localized via the existing `desktop/locales/{en,es}.json` catalogs
(`tray.show` / `tray.health` / `tray.quit`). Tray creation is best-effort:
Electrobun's `Tray` constructor already swallows platform/sandbox failures
internally (no native tray support → the icon is simply absent), and
`setupTray()` wraps the whole thing in `try/catch` so a tray failure never
blocks app startup or the main window.

Not yet shipped: dynamic menu state (e.g. bridge-ready checkmark) or a
tray-driven quick-render action — tracked as residual polish, not a blocker.

## Container (GHCR)

Production-oriented bridge image:

```bash
docker build -t ghcr.io/kooshapari/melosviz-bridge:local -f Dockerfile .
docker run --rm -p 8765:8765 ghcr.io/kooshapari/melosviz-bridge:local
```

CI workflow `.github/workflows/ghcr-bridge.yml` builds on PRs and pushes to
GHCR on `main` / `v*` tags (`ghcr.io/<owner>/melosviz-bridge`).
