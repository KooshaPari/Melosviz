# MelosViz external SDK stubs

MelosViz is consumed primarily as:

1. **CLI / Python package** — `backend/` (`pip install -e backend/`)
2. **HTTP bridge** — FastAPI on `:8765` (OpenAPI at `/docs` when running)
3. **Rust crates** — `melosviz-mir`, `melosviz-render-wgpu` (workspace members)

## GitHub Packages (npm) — publish path

Three scoped npm packages are configured for **GitHub Packages**
(`https://npm.pkg.github.com`) under the `KooshaPari/Melosviz` repository:

| Package | Path |
|---------|------|
| `@melosviz/bridge-client` | `sdk/ts/` |
| `@melosviz/brand-tokens` | `packages/brand-tokens/` |
| `@melosviz/ui` | `packages/ui/` |

**Publish workflow:** `.github/workflows/publish-sdk-packages.yml`

- `workflow_dispatch` (optional `dry_run` input — pack only, no registry write)
- `push` on tags matching `sdk-v*` (e.g. `sdk-v0.1.0`)

Uses `GITHUB_TOKEN` / `NODE_AUTH_TOKEN` with `packages: write`. Publish order:
`@melosviz/brand-tokens` → `@melosviz/bridge-client` → `@melosviz/ui` (see
`scripts/publish_sdk_packages.sh`).

**Status (honest):** workflow + `publishConfig` + consumption docs ship in-repo.
G-C11-06 is **mitigated** until the first successful Actions publish run lands on
`main`. PyPI and crates.io remain open (same gap row).

### Consume from GitHub Packages

1. Create a [GitHub personal access token](https://github.com/settings/tokens) with
   `read:packages` (and `repo` if the package is private).

2. Authenticate npm to GitHub Packages:

```bash
npm login --registry=https://npm.pkg.github.com
# Username: your GitHub username
# Password: <PAT with read:packages>
# Email: your GitHub email
```

Or write `~/.npmrc`:

```ini
@melosviz:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=ghp_xxxxxxxx
```

3. Install (publish `@melosviz/brand-tokens` before `@melosviz/ui` if you pin versions manually):

```bash
npm install @melosviz/brand-tokens @melosviz/bridge-client @melosviz/ui
```

4. Import (TypeScript / bundler):

```ts
import { analyze, BRIDGE_PATHS } from "@melosviz/bridge-client";
import { Button, EmptyState, Skeleton } from "@melosviz/ui";
import "@melosviz/brand-tokens/tokens.css";
```

### Local publish dry-run (no registry)

```bash
make sdk-publish-dry-run
# or: MELOSVIZ_SDK_PUBLISH_DRY_RUN=1 bash scripts/publish_sdk_packages.sh
```

## Not on public npm / PyPI / crates.io yet

- **npmjs.com** — MelosViz does not publish to the public npm registry today.
- **PyPI / crates.io** — Python and Rust SDK surfaces remain in-repo / from source;
  `cargo publish` / `twine upload` require an explicit release owner (WBS-P3.1).

Reserved / scoped names are listed in [`docs/SUPPLY_CHAIN.md`](../SUPPLY_CHAIN.md).

## Publishable-shape gate (CI)

`.github/workflows/supply-chain.yml` job **`sdk-pack-smoke`** runs
`scripts/check_sdk_pack_smoke.sh` on every PR / `main` push:

1. `npm pack` for `@melosviz/brand-tokens`, `@melosviz/bridge-client`, `@melosviz/ui`
2. Install the tarballs into a throwaway directory (`npm install *.tgz`)
3. Import entrypoints via `scripts/sdk_pack_smoke.mjs` (bun)

This proves tarball layout + exports are installable. Registry publish is a
separate workflow (`publish-sdk-packages.yml`).

## Planned SDK surfaces (stubs)

| SDK | Language | Status | Entry |
|-----|----------|--------|-------|
| Bridge HTTP client | TypeScript | stub (GH Packages path) | `sdk/ts/` (`@melosviz/bridge-client`) |
| Brand tokens | CSS | stub (GH Packages path) | `packages/brand-tokens` (`@melosviz/brand-tokens`) |
| Design system | React/TS | shipped in-repo | `packages/ui` (`@melosviz/ui`) |
| RenderSpec types | TypeScript | partial | `web/src/renderSpec.ts` |
| MIR CLI | Rust binary | shipped | `cargo run -p melosviz-mir` |

### TypeScript package shape (`sdk/ts`)

`@melosviz/bridge-client` is a publishable-shape stub with:

- `publishConfig.registry` → `https://npm.pkg.github.com`
- Scoped name reserved under the MelosViz supply-chain policy
- `exports` map pointing at `src/index.ts` (placeholder API)

See `sdk/ts/README.md` and `sdk/ts/package.json`. Full client generation from
OpenAPI remains WBS-P3.1.

## Stability

- RenderSpec v2 JSON is the cross-language contract (Python pydantic + Rust serde).
- Bridge paths `/health`, `/ready`, `/metrics`, `/analyze`, `/build`, `/render`
  are the supported HTTP surface; `/debug/profile` is opt-in.
- Contract SoT: `docs/api/openapi.json` (CI drift gate).

## Related

- `docs/PACKAGING.md` — channel map + SDK gate + GH Packages consume
- `docs/SUPPLY_CHAIN.md` — reserved names, install surfaces
- `docs/DISTRIBUTION_POLICY.md` — what MelosViz does / does not ship
- `docs/WBS_PHASED.md` — WBS-P3.1 publish milestone
