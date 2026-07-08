# Packaging & distribution channels

MelosViz ships three install surfaces today. This document is the Time-2
packaging map for audit-v38 cluster C11.

## Shipped today

| Channel | Artifact | How |
|---------|----------|-----|
| macOS desktop | DMG via Electrobun | `.github/workflows/release.yml` `macos-desktop` on `v*` tags |
| Linux CLI | `melosviz-mir` + `melosviz-render` tarball | `release.yml` `linux-cli` |
| From source | `pip install -e backend/` + `cargo run` | README quick start |

## Windows (documented channel)

Windows desktop packaging is not yet automated in CI (no Windows runner in
the release matrix). Operators can build locally:

```powershell
cd desktop
bun install
$env:ELECTROBUN_OS = "windows"
bunx electrobun build
bunx electrobun package
```

CLI binaries on Windows:

```powershell
cargo build --release
# target\release\melosviz-mir.exe
# target\release\melosviz-render.exe
```

## Auto-update

Release artifacts land on GitHub Releases. Electrobun auto-update is not
wired yet — track as a follow-up once a signed Windows/macOS channel exists.

## Mutation testing (nightly / local)

```bash
cd backend
pip install mutmut
mutmut run --paths-to-mutate src/melosviz/ --tests-dir tests/
# Target: >=75% mutation score per .qgate.toml
```

Mutation is intentionally out of PR CI (slow). Run locally or on a weekly
cron before cutting a release.
