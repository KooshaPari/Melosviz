# `@melosviz/bridge-client` (stub)

TypeScript HTTP client stub for the MelosViz bridge.

**Status:** configured for **GitHub Packages** (`publishConfig.registry` →
`npm.pkg.github.com`). Publish via `.github/workflows/publish-sdk-packages.yml`
(WBS-P3.1 / G-C11-06 mitigated — first green publish run pending).

See [`docs/sdk/README.md`](../../docs/sdk/README.md) for consume/login steps and
reserved-name policy in [`docs/SUPPLY_CHAIN.md`](../../docs/SUPPLY_CHAIN.md).

## Package shape

| Field | Value |
|-------|--------|
| name | `@melosviz/bridge-client` |
| registry | GitHub Packages (`npm.pkg.github.com`) |
| exports | `.` → `src/index.ts` |
| version | `0.0.0` (pre-first-publish) |

## Usage (illustrative)

```ts
import { analyze, BRIDGE_PATHS } from '@melosviz/bridge-client'

const summary = await analyze('http://127.0.0.1:8765', {
  audio_path: '/path/to/track.wav',
})
console.log(BRIDGE_PATHS)
```

Wire this into `web/` only after an explicit publish / workspace-link decision.
Until then, the live web app talks to the bridge via its own fetch helpers and
the OpenAPI contract at `docs/api/openapi.json`.
