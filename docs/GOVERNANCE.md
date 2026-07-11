# MelosViz project governance

## Decision makers

- **Maintainers** listed in `CODEOWNERS` merge to `main`.
- Security reports follow `SECURITY.md` (private advisories).
- Conduct follows `CODE_OF_CONDUCT.md`.

## Contribution

See `CONTRIBUTING.md` (DCO sign-off required). Claim work via `docs/WORK_DAG.md`.

## Release authority

- Version tags `v*` trigger `.github/workflows/release.yml`.
- Artifacts include attestations, `SHA256SUMS`, and cosign bundles.
- Distribution policy: `docs/DISTRIBUTION_POLICY.md`.

## Scorecard / audits

Product scorecards live in `audit/` and are mirrored to
`phenotype-org-audits` for org-wide tracking.
