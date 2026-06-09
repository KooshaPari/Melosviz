# Contributing

Thanks for contributing to Melosviz.

## Workflow

1. Branch from `main`: `git checkout -b <type>/<short-topic> origin/main`.
2. Keep commits small and scoped to one concern.
3. Match the existing toolchain per component (`backend/`, `desktop/`, `sdk/`, `web/`).
4. Open a PR with a clear title (`<type>(scope): summary`) and reference any related issue or design note.

## Component Setup

See the per-component install steps in `README.md` (`backend`, `desktop`, `sdk/python`, `sdk/rust`, `web`).

## Style

- Follow each component's existing linters and formatters.
- Don't disable lint or type checks to make a change pass — fix the underlying issue.
- Keep Markdown UTF-8.

## Reporting Issues

File issues with reproduction steps, expected vs. actual behavior, and the affected component (`backend`, `desktop`, `sdk`, `web`).
