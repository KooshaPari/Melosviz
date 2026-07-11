# MelosViz external SDK stubs

MelosViz is consumed primarily as:

1. **CLI / Python package** — `backend/` (`pip install -e backend/`)
2. **HTTP bridge** — FastAPI on `:8765` (OpenAPI at `/docs` when running)
3. **Rust crates** — `melosviz-mir`, `melosviz-render-wgpu` (workspace members)

## Planned SDK surfaces (stubs)

| SDK | Language | Status | Entry |
|-----|----------|--------|-------|
| Bridge HTTP client | TypeScript | stub | `sdk/ts/README.md` |
| RenderSpec types | TypeScript | partial | `web/src/renderSpec.ts` |
| MIR CLI | Rust binary | shipped | `cargo run -p melosviz-mir` |

These stubs document the intended public contract. They are **not** published to
npm/crates.io/PyPI (see `docs/SUPPLY_CHAIN.md` / `docs/DISTRIBUTION_POLICY.md`).

## Stability

- RenderSpec v2 JSON is the cross-language contract (Python pydantic + Rust serde).
- Bridge paths `/health`, `/ready`, `/metrics`, `/analyze`, `/build`, `/render`
  are the supported HTTP surface; `/debug/profile` is opt-in.
