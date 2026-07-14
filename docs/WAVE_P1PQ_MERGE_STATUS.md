# Wave P1P/P1Q — PR merge status (#156–#163)

Triage run: **2026-07-14** (branch `feat/melosviz-pr-merge`, worktree `pr-merge`).

Policy: merge when **required GitHub Actions CI** is green; ignore soft checks (CodeRabbit prepaid credits, Kilo pending, Sonar pending). Do **not** invent SCORECARD lifts.

## Summary

| Merged | Blocked |
|--------|---------|
| **4** (#156, #158, #160, #161) | **4** (#157, #159, #162, #163) |

## Per-PR status

| PR | Title | State | Required CI | Soft (ignored) | Next action |
|----|-------|-------|-------------|----------------|-------------|
| [#156](https://github.com/KooshaPari/Melosviz/pull/156) | chore: widen WORK_DAG parallel lanes + fuzz/uninstall polish | **MERGED** | All green | Kilo pending | — |
| [#157](https://github.com/KooshaPari/Melosviz/pull/157) | feat(a11y): deepen R3F canvas non-visual scene summary (W-329) | OPEN | **SonarCloud QG failed**: Security Rating on New Code &lt; A (required ≥ A) | CodeRabbit credits; Kilo pending | Fix Sonar security findings on new code in `web/` (see [Sonar PR dashboard](https://sonarcloud.io/dashboard?id=KooshaPari_Melosviz&pullRequest=157)); all Actions jobs otherwise green |
| [#158](https://github.com/KooshaPari/Melosviz/pull/158) | ci(qgate): in-repo reusable quality-gate workflow | **MERGED** | All green | CodeRabbit credits; Kilo pending | — |
| [#159](https://github.com/KooshaPari/Melosviz/pull/159) | feat(i18n): expand en/es CLI, desktop, web + keyboard/preset (W-325) | OPEN | **`Backend — pytest + coverage + ruff (Python 3.12)`** fails at `ruff check` before pytest runs: `SIM401` at `src/melosviz/i18n/__init__.py:58:16` | CodeRabbit credits; Sonar QG failed; Kilo pending | Apply SIM401 suggestion (or targeted `# noqa: SIM401`); [comment posted](https://github.com/KooshaPari/Melosviz/pull/159#issuecomment-4967178939) |
| [#160](https://github.com/KooshaPari/Melosviz/pull/160) | feat(airgap): Electrobun desktop prebuilt fetch path (W-326) | **MERGED** | All green | CodeRabbit credits; Kilo pending | — |
| [#161](https://github.com/KooshaPari/Melosviz/pull/161) | test(desktop): expand bridge-layer e2e (WBS-P1.9) | **MERGED** | All green | CodeRabbit credits; Kilo pending | — |
| [#162](https://github.com/KooshaPari/Melosviz/pull/162) | ci(supply-chain): add pip-licenses gate for backend Python deps | OPEN | **`pip-licenses (backend)`** fails: `license UNKNOWN not in allow-only licenses was found for package melosviz:0.1.0` | CodeRabbit credits; Kilo pending | Add SPDX license to root `pyproject.toml` or exclude editable `melosviz` from gate; [comment posted](https://github.com/KooshaPari/Melosviz/pull/162#issuecomment-4967189466) |
| [#163](https://github.com/KooshaPari/Melosviz/pull/163) | feat(web): p1q studio polish — SDK consume, bridge DX, onboarding, a11y (W-333–352) | OPEN | **SonarCloud QG failed**: Reliability Rating on New Code &lt; A (required ≥ A) | CodeRabbit credits; Kilo pending | Fix Sonar reliability findings on new code in `web/` (see [Sonar PR dashboard](https://sonarcloud.io/dashboard?id=KooshaPari_Melosviz&pullRequest=163)); all Actions jobs otherwise green |

## Merge method

Green PRs merged with:

```bash
gh pr merge <n> --repo KooshaPari/Melosviz --squash --admin
```

## Blocker detail

### #159 — ruff (not pytest)

```
SIM401 Use `en.get(key, fallback if fallback is not None else key)` instead of an `if` block
  --> src/melosviz/i18n/__init__.py:58:16
```

Job: [Backend — pytest + coverage + ruff](https://github.com/KooshaPari/Melosviz/actions/runs/29307632053/job/87004199695) (exit 1 at ruff step).

### #162 — pip-licenses

```
license UNKNOWN not in allow-only licenses was found for package melosviz:0.1.0
```

Job: [pip-licenses (backend)](https://github.com/KooshaPari/Melosviz/actions/runs/29307647273/job/87004245215).

### #157 / #163 — SonarCloud quality gate

GitHub Actions CI is fully green on both PRs. Merge withheld because SonarCloud reports a failed quality gate (not merely pending):

- **#157**: Security Rating on New Code below A
- **#163**: Reliability Rating on New Code below A
