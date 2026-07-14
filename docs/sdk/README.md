# MelosViz SDK — GitHub Packages consumer guide

MelosViz ships **publishable-shape** npm packages on **GitHub Packages**
(`npm.pkg.github.com`), not public npmjs.com. PyPI and crates.io publish remain
deferred — see `docs/SUPPLY_CHAIN.md` reserved-name policy.

| Package | Path in repo | Purpose |
|---------|--------------|---------|
| `@melosviz/bridge-client` | `sdk/ts/` | Bridge HTTP client stub |
| `@melosviz/brand-tokens` | `packages/brand-tokens/` | Brand CSS token re-export |
| `@melosviz/ui` | `packages/ui/` | Shared React design-system components |

**Publish:** `.github/workflows/publish-sdk-packages.yml` (`workflow_dispatch` or
tag `sdk-v*`) via `scripts/publish_sdk_packages.sh`. First green Actions publish
run may still be pending — until then, consume from the monorepo with `file:`
links (how `web/package.json` wires UI today).

## First-run: authenticate to GitHub Packages

You need a GitHub **personal access token (classic or fine-grained)** with
`read:packages` for the `KooshaPari/Melosviz` org/user scope.

### Project-local `.npmrc` (recommended)

Create or merge into your app's `.npmrc` (do **not** commit tokens):

```ini
@melosviz:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_PACKAGES_TOKEN}
```

Export the token in your shell (or CI secret):

```bash
export GITHUB_PACKAGES_TOKEN=ghp_xxxxxxxx   # read:packages
```

### One-shot login (interactive)

```bash
npm login --registry=https://npm.pkg.github.com
# Username: your GitHub username
# Password: PAT with read:packages (not your GitHub password)
# Email: (optional)
```

## Install published packages

After a successful publish workflow run:

```bash
npm install @melosviz/brand-tokens @melosviz/bridge-client @melosviz/ui
```

`@melosviz/ui` depends on `@melosviz/brand-tokens` — install both or let npm
resolve the peer tree.

### Bun / pnpm

Bun respects the same `.npmrc` scope mapping:

```bash
bun add @melosviz/bridge-client @melosviz/brand-tokens @melosviz/ui
```

## Consume without publish (monorepo / fork)

Inside this repository, web and smoke tests use **workspace file links** — no
registry auth required:

```json
{
  "dependencies": {
    "@melosviz/brand-tokens": "file:../packages/brand-tokens",
    "@melosviz/ui": "file:../packages/ui"
  }
}
```

Bridge client stub:

```json
"@melosviz/bridge-client": "file:../sdk/ts"
```

Verify publishable shape locally:

```bash
./scripts/check_sdk_pack_smoke.sh
```

## Minimal usage

**Tokens** — load CSS once in your app entry (web loads `brand.css` which
`@import`s the package):

```ts
import '@melosviz/brand-tokens/tokens.css'
```

**UI components:**

```tsx
import { Button, EmptyState, Skeleton } from '@melosviz/ui'
```

**Bridge client** (after publish or `file:` link):

```ts
import { analyze, BRIDGE_PATHS } from '@melosviz/bridge-client'

const summary = await analyze('http://127.0.0.1:8765', {
  audio_path: '/path/to/track.wav',
})
```

The live web app still uses its own fetch helpers against the OpenAPI contract
(`docs/api/openapi.json`) until you explicitly adopt the stub client.

## Bridge dev URL (default port)

Local bridge sidecar defaults to **`http://127.0.0.1:8765`**. Quick health probe:

```bash
./scripts/dev_bridge.sh health
# or: curl -sf http://127.0.0.1:8765/health
```

Packaged desktop may mint bearer auth — for manual bridge debugging set
`MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1` (see `docs/ENV.md`).

## CI / automation

In GitHub Actions, use `GITHUB_TOKEN` or a dedicated `read:packages` PAT:

```yaml
- run: npm ci
  env:
    GITHUB_PACKAGES_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Ensure `.npmrc` in the job uses `${GITHUB_PACKAGES_TOKEN}` as above. For
cross-repo consumers outside GitHub Actions, use a PAT stored as a repository
secret.

## Related docs

- `docs/PACKAGING.md` — SDK publishable-shape gate (C11 L116)
- `docs/SUPPLY_CHAIN.md` — reserved names, dependency-confusion policy
- `sdk/ts/README.md` — bridge-client stub details
- `packages/ui/README.md` — design-system scope and wiring
