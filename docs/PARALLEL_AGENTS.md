# Parallel agents / worktrees

Contract for concurrent agent work on MelosViz (C03 L30.9 / C00 L4).

## Rules

1. Prefer an isolated git worktree or branch per agent (`git worktree add`).
2. Do not mutate `main` directly; open a PR with DCO (`git commit -s`).
3. Mutating lanes (release, lockfile bumps, scorecard rescores) claim a
   `docs/WORK_DAG.md` ID and avoid overlapping the same files.
4. Read-only lanes (audit, docs review) may share a checkout.
5. Never force-push shared branches; never commit `target/`, secrets, or
   generated `eval/harbor/out/`.

## Local pattern

```bash
git fetch origin
git worktree add ../Melosviz-w255 -b feat/w255-slug origin/main
cd ../Melosviz-w255
# … work …
```

## CI concurrency

Workflows use `concurrency: cancel-in-progress` per ref so parallel pushes on
the same branch collapse to the latest run.
