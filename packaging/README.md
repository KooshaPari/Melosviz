# Melosviz — release & publishing

End-to-end release pipeline for Melosviz binaries + every major package manager.

## Channels wired

| Channel                                                                                                      | Trigger                  | Workflow                              |
| ------------------------------------------------------------------------------------------------------------ | ------------------------ | ------------------------------------- |
| GitHub Release (macOS DMG + Linux tarball + Windows zip + Windows desktop + SBOM + cosign-signed SHA256SUMS) | `release.yml` (tag push) | `.github/workflows/release.yml`       |
| **PyPI** (Python orchestrator)                                                                               | release published        | `.github/workflows/pypi-publish.yml`  |
| **crates.io** (`melosviz-demo`, `melosviz-mir`)                                                              | release published        | `.github/workflows/cargo-publish.yml` |
| **npm** (Electrobun desktop)                                                                                 | release published        | `.github/workflows/npm-publish.yml`   |
| **Homebrew tap** (macOS)                                                                                     | release published        | `.github/workflows/homebrew-tap.yml`  |
| **Scoop bucket** (Windows)                                                                                   | release published        | `.github/workflows/scoop-bucket.yml`  |
| **winget-pkgs** (Windows)                                                                                    | release published        | `.github/workflows/winget-pr.yml`     |

All publish channels use **OIDC trusted publishing** (no long-lived secrets); GitHub
App tokens (HOMEBREW_TAP_TOKEN, SCOOP_BUCKET_TOKEN, WINGET_PKGS_TOKEN) are PATs
with `contents: read` + `pull-requests: write` only.

## Manual templates

If the auto-PR workflow is disabled or the tap isn't owned by you yet, the commit-shaped
files live under `packaging/`:

- `packaging/homebrew-tap/Formula/melosviz.rb.template`
- `packaging/scoop-bucket/melosviz.json.template`
- `packaging/winget/manifests/kooshapari/Melosviz/{melosviz,melosviz.installer}.yaml.template`

Substitute `{{version}}` and `{{sha256}}` after a tag is published.

## One-shot local dry-run

```bash
# Tag the release + publish everything (CI does this for real)
export MELOSVIZ_VERSION=0.1.0
make release          # task release — bumps versions, builds, tags
make publish-check    # verify every package-local build without uploading
```

## Trusted-publishing setup (org-level)

| Index        | Trust level           | Required secret                                          |
| ------------ | --------------------- | -------------------------------------------------------- |
| PyPI         | Project-scoped        | `pypi` trusted publisher (configured on pypi.org)        |
| crates.io    | crates.io token       | `CARGO_REGISTRY_TOKEN` OR `crates.io` OIDC (set in repo) |
| npm          | Package provenance    | `NODE_AUTH_TOKEN` OR npm OIDC (`workflow_dispatch` job)  |
| Homebrew tap | Personal access token | `HOMEBREW_TAP_TOKEN`                                     |
| Scoop bucket | Personal access token | `SCOOP_BUCKET_TOKEN`                                     |
| winget-pkgs  | Personal access token | `WINGET_PKGS_TOKEN`                                      |

Pushing a `v0.1.0`-style tag to `main` triggers `release.yml`, whose `publish` job
emits the GitHub Release. Every publish workflow above has `on.release.types:
[published]`, so all 6 channels populate within ~10 minutes of one tag.
