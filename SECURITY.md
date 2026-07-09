# Security Policy

## Reporting Vulnerabilities

Please report security vulnerabilities via GitHub Security Advisories:

- Open a [private security advisory](../../security/advisories/new)
- For sensitive issues, contact the repository owner directly

## Supported Versions

Latest `main` branch. Older versions are not supported.

## Disclosure Policy

We follow coordinated disclosure with reporters. Once an issue is patched, an advisory will be published.

## Cargo-deny / cargo-audit

Rust crates are audited in CI via `.github/workflows/supply-chain.yml`
(`cargo audit` on every PR/push + Monday cron). Org-level `cargo-deny`
may also run from phenotype-tooling.

## pip-audit

Python dependencies are scanned with `pip-audit` in the same supply-chain
workflow. Failures block merge.

## SBOM

CycloneDX SBOMs for Python and Cargo are generated in CI
(`sbom-python.cdx.json`, `sbom-cargo.cdx.json`) and uploaded as artifacts.
Release tags also attach SBOM artifacts when the release workflow runs.

## CodeQL / SonarCloud

Static analysis may run via org SonarCloud and/or CodeQL. SonarCloud
Quality Gate failures on *new code* that are false positives (e.g. local
desktop bridge path handling flagged as hotspots) are tracked here:

- Bridge path containment and bearer auth are intentional localhost
  hardening — see `docs/security/BRIDGE_THREAT_MODEL.md`.
- Hotspots that duplicate gitleaks/bandit/pip-audit findings are waived
  after the supply-chain workflow is green.

## Dependabot

`.github/dependabot.yml` opens weekly PRs for Actions, npm (web/desktop),
Cargo, and pip.
