# Supply chain & dependency-confusion policy

MelosViz publishes no private package index. All installs resolve from public
registries via locked manifests only.

## Reserved / owned names

| Ecosystem | Package / crate | Registry | Notes |
|-----------|-----------------|----------|-------|
| PyPI | `melosviz` (bridge / backend) | pypi.org | Install only via `backend/uv.lock` |
| crates.io | `melosviz-*` workspace crates | crates.io | Workspace members; do not yank-replace |
| npm | `melosviz-web` / desktop private | npmjs.com | `"private": true` — never publish |

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
- Dependabot weekly PRs only (no ad-hoc unpinned bumps in feature PRs)
- Release artifacts ship `SHA256SUMS` (`MelosViz-Checksums`)

## Incident response

If a confusing public package appears under a MelosViz-adjacent name: pin the
known-good hash in the lockfile, open a security issue, and document the
blocklist here.
