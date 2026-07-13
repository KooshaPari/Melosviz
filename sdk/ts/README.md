# `@melosviz/bridge-client` (stub)

Private TypeScript HTTP client stub for the MelosViz bridge.

**Status:** not published to npm. `"private": true` in `package.json`.
Publish remains WBS-P3.1 — see [`docs/sdk/README.md`](../../docs/sdk/README.md)
and reserved-name policy in [`docs/SUPPLY_CHAIN.md`](../../docs/SUPPLY_CHAIN.md).

## Package shape

| Field | Value |
|-------|--------|
| name | `@melosviz/bridge-client` |
| private | `true` |
| exports | `.` → `src/index.ts` |
| version | `0.0.0` (pre-publish) |

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
