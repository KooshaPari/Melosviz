# Packaging & distribution channels

MelosViz ships install surfaces via `.github/workflows/release.yml` on `v*` tags.
This document is the Time-2 packaging map for audit-v38 cluster C11.

## Shipped today (CI)

| Channel | Artifact | Job |
|---------|----------|-----|
| macOS desktop | DMG via Electrobun | `macos-desktop` |
| Linux CLI | `melosviz-mir` + `melosviz-render` tarball | `linux-cli` |
| Windows CLI | `melosviz-mir.exe` + `melosviz-render.exe` zip | `windows-cli` |
| Windows desktop | Electrobun package (best-effort) | `windows-desktop` (`continue-on-error`) |
| SBOM | CycloneDX Python + Cargo | `sbom` |
| Provenance | GitHub attestations | `release` |

## From source

```bash
pip install -e backend/
cargo run --release -p melosviz-mir -- --help
cd web && bun install && bun run dev
```

## Windows local (if CI desktop job is skipped)

```powershell
cd desktop
bun install
$env:ELECTROBUN_OS = "windows"
bunx electrobun build
bunx electrobun package
```

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

## Container (GHCR)

Production-oriented bridge image:

```bash
docker build -t ghcr.io/kooshapari/melosviz-bridge:local -f Dockerfile .
docker run --rm -p 8765:8765 ghcr.io/kooshapari/melosviz-bridge:local
```

CI workflow `.github/workflows/ghcr-bridge.yml` builds on PRs and pushes to
GHCR on `main` / `v*` tags (`ghcr.io/<owner>/melosviz-bridge`).
