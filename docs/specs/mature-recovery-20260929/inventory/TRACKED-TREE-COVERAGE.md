# Tracked-tree coverage — Melosviz

Frozen product source: `1aec20a2ba41a01ed557d1c7f63f9a0089f842cf`.

## Enumeration result

Every top-level Git tree at the frozen revision was recursively enumerated through Git object APIs with `truncated=false`. Exact blob rows are persisted in `inventory/TRACKED-TREE-A.json` and `TRACKED-TREE-B.json`.

- Part A: 278 blobs.
- Part B: 410 blobs.
- **Tracked blobs explicitly inventoried: 688.**
- Root files are included in Part B.
- No top-level tree remains uncovered.

This closes **tracked-file enumeration only**. It does not close source semantics, history, conversations, deleted/moved predecessor repositories, Registry evidence, PR/issue authority or external research.

## Initial source-family projection

| Family | Blob rows | Semantic status |
|---|---:|---|
| Human interface | 210 | OPEN; distinguish desktop/web/Tauri mounted/current/historical |
| Verification | 114 | OPEN; classify mock/live/mutation/fuzz/oracle and candidate identity |
| Documentation | 68 | OPEN; authority/supersession conflicts known |
| Support | 54 | OPEN |
| CI | 48 | OPEN; current enforcement and skipped jobs need exact review |
| Root contract/config | 35 | OPEN |
| Automation/scripts | 31 | OPEN |
| Integration/SDK/packages | 20 | OPEN |
| Render | 17 | OPEN; adapter outcome semantics and tool qualification |
| Historical audit | 13 | HISTORICAL by default until individually promoted |
| Historical sessions/plans | 11 | HISTORICAL/PROPOSAL pending authority |
| Domain | 10 | OPEN; scene/compose semantics |
| Rust support | 9 | OPEN; current role after studio pivot |
| Conductor | 8 | HIGH PRIORITY / OPEN |
| Deployment | 7 | OPEN |
| Packaging | 7 | HIGH PRIORITY / OPEN |
| API | 5 | HIGH PRIORITY / OPEN |
| Examples | 5 | SUPPORTING |
| Assets | 4 | AUXILIARY unless referenced by accepted journey |
| Analysis | 3 | HIGH PRIORITY / OPEN |
| CLI | 3 | HIGH PRIORITY / OPEN |
| Localization | 3 | QUALITY SUPPORT |
| Design-intent | 2 | AUTHORITY REVIEW REQUIRED |
| Auxiliary | 1 | AUXILIARY pending review |

Counts are inventory navigation aids, not requirement counts and not completion weights.

## Resolution order

1. Mounted product spine: CLI/API/desktop → project/storyboard state → conductor → render/cache/provenance → assembly/master/ship.
2. Canonical schemas/domain/audio timing.
3. Verification and CI surfaces, especially historical false-green mechanisms and mutation isolation.
4. Alternative render/edit/interchange stack and licensing.
5. Remaining UI/support/docs/configuration sources.
6. Historical/auxiliary material, with explicit supersession/irrelevance decisions.

A family is resolved only when meaning, contradictions, obligation disposition, implementation surfaces, journey/stage implications and verification consequences are all addressed.
