# MelosViz external SDK stubs

MelosViz is consumed primarily as:

1. **CLI / Python package** — `backend/` (`pip install -e backend/`)
2. **HTTP bridge** — FastAPI on `:8765` (OpenAPI at `/docs` when running)
3. **Rust crates** — `melosviz-mir`, `melosviz-render-wgpu` (workspace members)

## Not published yet

SDK folders under `sdk/` and `docs/sdk/` are **in-repo stubs only**. Nothing here is
published to npm, crates.io, or PyPI. Do not `npm publish` / `cargo publish` /
`twine upload` without an explicit release owner (WBS-P3.1).

Reserved / scoped names for future publish are listed in
[`docs/SUPPLY_CHAIN.md`](../SUPPLY_CHAIN.md) (dependency-confusion policy). Treat
`@melosviz/*` and `melosviz-*` as owned identifiers even while packages stay
`"private": true`.

## Planned SDK surfaces (stubs)

| SDK | Language | Status | Entry |
|-----|----------|--------|-------|
| Bridge HTTP client | TypeScript | stub (publishable shape) | `sdk/ts/` (`@melosviz/bridge-client`) |
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

## Stability

- RenderSpec v2 JSON is the cross-language contract (Python pydantic + Rust serde).
- Bridge paths `/health`, `/ready`, `/metrics`, `/analyze`, `/build`, `/render`
  are the supported HTTP surface; `/debug/profile` is opt-in.
- Contract SoT: `docs/api/openapi.json` (CI drift gate).

## Related

- `docs/SUPPLY_CHAIN.md` — reserved names, install surfaces
- `docs/DISTRIBUTION_POLICY.md` — what MelosViz does / does not ship
- `docs/WBS_PHASED.md` — WBS-P3.1 publish milestone
