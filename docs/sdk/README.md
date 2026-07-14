# MelosViz external SDK stubs

MelosViz is consumed primarily as:

1. **CLI / Python package** — `backend/` (`pip install -e backend/`)
2. **HTTP bridge** — FastAPI on `:8765` (OpenAPI at `/docs` when running)
3. **Rust crates** — `melosviz-mir`, `melosviz-render-wgpu` (workspace members)

## Not published yet

SDK folders under `sdk/` and `packages/` are **in-repo stubs with publishable shape**.
Nothing here is published to npm, crates.io, or PyPI today. Do not `npm publish` /
`cargo publish` / `twine upload` without an explicit release owner (WBS-P3.1).

Reserved / scoped names for future publish are listed in
[`docs/SUPPLY_CHAIN.md`](../SUPPLY_CHAIN.md) (dependency-confusion policy). Treat
`@melosviz/*` and `melosviz-*` as owned identifiers even while packages stay
`"private": true`.

## Publishable-shape gate (CI)

`.github/workflows/supply-chain.yml` job **`sdk-pack-smoke`** runs
`scripts/check_sdk_pack_smoke.sh` on every PR / `main` push:

1. `npm pack` for `@melosviz/brand-tokens`, `@melosviz/bridge-client`, `@melosviz/ui`
2. Install the tarballs into a throwaway directory (`npm install *.tgz`)
3. Import entrypoints via `scripts/sdk_pack_smoke.mjs` (bun)

This proves tarball layout + exports are installable. It does **not** publish to a
registry and does **not** close G-C11-06 (live PyPI/crates/npm publish).

## Planned SDK surfaces (stubs)

| SDK | Language | Status | Entry |
|-----|----------|--------|-------|
| Bridge HTTP client | TypeScript | stub (publishable shape) | `sdk/ts/` (`@melosviz/bridge-client`) |
| Brand tokens | CSS | stub (publishable shape) | `packages/brand-tokens` (`@melosviz/brand-tokens`) |
| Design system | React/TS | shipped in-repo | `packages/ui` (`@melosviz/ui`) |
| RenderSpec types | TypeScript | partial | `web/src/renderSpec.ts` |
| MIR CLI | Rust binary | shipped | `cargo run -p melosviz-mir` |

### TypeScript package shape (`sdk/ts`)

`@melosviz/bridge-client` is a **private** package stub with:

- `"private": true` — npm publish blocked by default
- Scoped name reserved under the MelosViz supply-chain policy
- `exports` map pointing at `src/index.ts` (placeholder API)
- No registry publish config / no `publishConfig.access`

See `sdk/ts/README.md` and `sdk/ts/package.json`. Full client generation from
OpenAPI remains WBS-P3.1.

## How real publish would work (not done)

When WBS-P3.1 is explicitly owned:

| Package | Registry | Steps (outline) |
|---------|----------|-----------------|
| `@melosviz/bridge-client` | npm or GitHub Packages | Remove `"private": true`; add `publishConfig`; `npm publish --access public` (or `npm publish --registry=https://npm.pkg.github.com`) with `NODE_AUTH_TOKEN` |
| `@melosviz/brand-tokens` | npm / GH Packages | Same; ensure `tokens.css` SoT sync from `desktop/assets/brand/tokens.css` in release checklist |
| `@melosviz/ui` | npm / GH Packages | Publish `@melosviz/brand-tokens` first; replace `file:../brand-tokens` with semver range before publish |

Rust crates (`melosviz-mir`, `melosviz-render-wgpu`) would follow `cargo publish`
with workspace versioning policy — also WBS-P3.1 / G-C11-06.

## Stability

- RenderSpec v2 JSON is the cross-language contract (Python pydantic + Rust serde).
- Bridge paths `/health`, `/ready`, `/metrics`, `/analyze`, `/build`, `/render`
  are the supported HTTP surface; `/debug/profile` is opt-in.
- Contract SoT: `docs/api/openapi.json` (CI drift gate).

## Related

- `docs/PACKAGING.md` — channel map + SDK gate
- `docs/SUPPLY_CHAIN.md` — reserved names, install surfaces
- `docs/DISTRIBUTION_POLICY.md` — what MelosViz does / does not ship
- `docs/WBS_PHASED.md` — WBS-P3.1 publish milestone
