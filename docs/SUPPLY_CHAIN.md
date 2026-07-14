# Supply chain & dependency-confusion policy

MelosViz publishes no private package index. All installs resolve from public
registries via locked manifests only.

## Reserved / owned names

| Ecosystem | Package / crate | Registry | Notes |
|-----------|-----------------|----------|-------|
| PyPI | `melosviz` (bridge / backend) | pypi.org | Install only via `backend/uv.lock` |
| crates.io | `melosviz-*` workspace crates | crates.io | Workspace members; do not yank-replace |
| npm | `melosviz-web` / desktop private | npmjs.com | `"private": true` — never publish |
| npm | `@melosviz/bridge-client` (`sdk/ts`) | npm.pkg.github.com | GH Packages publish via `publish-sdk-packages.yml` (G-C11-06 mitigated) |
| npm | `@melosviz/brand-tokens` | npm.pkg.github.com | GH Packages; SoT remains `desktop/assets/brand/tokens.css` |
| npm | `@melosviz/ui` | npm.pkg.github.com | GH Packages; depends on published `@melosviz/brand-tokens` |
| npm | `@melosviz/*` (scoped) | npmjs.com | Reserved — **not** published to public npm |

Agents and CI **must not**:

- Add `--extra-index-url`, `--index-url` overrides, or unscoped private mirrors
- Install packages by typo-squatted names adjacent to MelosViz identifiers
- Publish workspace crates/npm packages without an explicit release owner

## Install surfaces

| Surface | Lockfile | Tool |
|---------|----------|------|
| Python bridge | `backend/uv.lock` | `uv sync --frozen` |
| Rust workspace | `Cargo.lock` | `cargo … --locked` |
| Web | `web/package-lock.json` (if present) / npm lock | `npm ci` |
| Desktop | `desktop/package-lock.json` (if present) | `npm ci` |

## CI enforcement

- `.github/workflows/supply-chain.yml` — frozen lock verify + cargo-deny + audits
- `scripts/check_reserved_names.py` — reserved-name / dependency-confusion scanner
  (allowlists `melosviz` / `melosviz-*` workspace names; fails on typo-adjacent
  confuse deps such as `melosvis` / `melos-viz` / `melosvizs`, and on unexpected
  private registry / `--extra-index-url` overrides in manifests)
- `scripts/check_repro_smoke.sh` — Linux SOURCE_DATE_EPOCH smoke (same-epoch
  double-build / deterministic archive hash compare); wired as `repro-smoke`
  in `supply-chain.yml`
- `scripts/check_hermetic_smoke.sh` — Linux Rust hermetic/offline smoke (`cargo fetch`
  once, then `CARGO_NET_OFFLINE=true cargo check -p melosviz-mir --locked`);
  wired as `hermetic-smoke` in `supply-chain.yml` (WBS-P1.6 / C06 L54)
- `scripts/check_hermetic_python_smoke.sh` — Linux Python wheelhouse prefetch +
  `PIP_NO_INDEX=1` offline install + `import melosviz` smoke; same
  `hermetic-smoke` job (WBS-P1.14 / C06 L54)
- `scripts/check_portability_smoke.py` — core import + CLI version without
  FFmpeg/Blender (graceful `FFMpegNotFoundError` / `BlenderNotFoundError`);
  wired as `portability-smoke` in `supply-chain.yml` (C07 L70)
- `scripts/check_sdk_pack_smoke.sh` — SDK `npm pack` + tarball install + import
  smoke for `@melosviz/*` stubs; wired as `sdk-pack-smoke` in `supply-chain.yml`
  (C11 L116 publishable-shape gate; does not publish to a registry)
- Dependabot weekly PRs only (no ad-hoc unpinned bumps in feature PRs)
- Release artifacts ship `SHA256SUMS` (`MelosViz-Checksums`)

## Hermetic / offline CI (WBS-P1.6 / WBS-P1.14 / C06 L54)

CI proves locked dependency graphs can be consumed with **no further network**
after a single online prefetch:

```bash
./scripts/check_hermetic_smoke.sh         # Rust
./scripts/check_hermetic_python_smoke.sh  # Python wheelhouse
# or: make hermetic-smoke / make hermetic-python-smoke
```

| Step | Network | Rust | Python |
|------|---------|------|--------|
| Prefetch | online once | `cargo fetch --locked` | `uv export` + `uv build` + `pip download` → `dist/wheelhouse-python-smoke/` |
| Verify | offline | `CARGO_NET_OFFLINE=true cargo check -p melosviz-mir --locked` | `PIP_NO_INDEX=1 pip install --no-index --find-links=wheelhouse` + `import melosviz` |

Committed `vendor/` + `.cargo/config.toml` source replacement remains **optional**
for operators — see `docs/AIRGAP.md` for the full vendor path.

## Core portability without host render tools (C07 L70)

`scripts/check_portability_smoke.py` (job `portability-smoke`) asserts the
default Python install imports cleanly and FFmpeg/Blender resolution fails with
actionable errors when absent — host render binaries are optional, not required
for core CLI/analysis usage.

Windows/macOS: Rust hermetic scripts exit 0 with a skip message; use the
`hermetic-smoke` / `portability-smoke` GitHub Actions jobs on `ubuntu-22.04`.

## SOURCE_DATE_EPOCH / reproducible builds (WBS-P1.5 / C06 L52)

Release Rust CLI jobs in `.github/workflows/release.yml` export
`SOURCE_DATE_EPOCH` from the tagged commit’s author timestamp
(`git log -1 --pretty=%ct`). That value is consumed by:

- **rustc / cargo** — embeds a stable build epoch instead of wall-clock time
- **Linux CLI tarball** — GNU tar `--mtime=@$SOURCE_DATE_EPOCH` (plus sorted
  names / numeric owner) so the archive metadata is stable for a given tag

### What we claim

| Artifact | Claim | Notes |
|----------|-------|-------|
| Linux `melosviz-mir` / `melosviz-render` (same runner image, same toolchain) | Best-effort bit-identity under fixed epoch + path remap | Smoke-checked in CI |
| Linux release `.tar.gz` metadata | Deterministic mtimes/owners for a given tag | Not a full hermetic rebuild across distros |
| Windows CLI `.zip` / desktop MSI / Electrobun packages | **Not** bit-identical | PE timestamps, Authenticode, Electrobun bundling, and absolute paths differ across hosts |
| macOS DMG | **Not** bit-identical | `hdiutil` / signing / notarization mutate bytes |

Local / CI smoke (Linux):

```bash
./scripts/check_repro_smoke.sh
```

Windows developers: the script exits 0 with a skip message — use WSL or the
`repro-smoke` GitHub Actions job. Full Windows desktop MSI bit-identity is
out of scope.

## Incident response

If a confusing public package appears under a MelosViz-adjacent name: pin the
known-good hash in the lockfile, open a security issue, and document the
blocklist here.
