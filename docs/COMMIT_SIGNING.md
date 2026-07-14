# Commit signing (local contributors)

MelosViz enforces **DCO Signed-off-by** on every PR commit
(`.github/workflows/dco.yml`). This document covers optional **cryptographic**
commit signatures (SSH or GPG) for contributors who want verified commits on
GitHub before org-wide branch protection lands (W-228 / G-C04-01).

## DCO (required today)

Every commit must include `Signed-off-by: Your Name <email>`:

```bash
git commit -s -m "feat: example change"
```

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the full Developer Certificate of
Origin text.

## SSH commit signing (recommended for GitHub users)

1. Create or use an existing SSH key enrolled for **Signing** in GitHub →
   Settings → SSH and GPG keys.
2. Configure Git:

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub   # or your signing key
git config --global commit.gpgsign true
```

3. Commit with sign-off:

```bash
git commit -s -S -m "feat: example signed commit"
```

GitHub shows **Verified** when the signing key is registered on your account.

## GPG commit signing (alternative)

1. Generate a key: `gpg --full-generate-key` (RSA or Ed25519).
2. Add the public key to GitHub → Settings → SSH and GPG keys.
3. Configure Git:

```bash
git config --global user.signingkey <KEY_ID>
git config --global commit.gpgsign true
```

4. Commit: `git commit -s -S -m "feat: example GPG-signed commit"`.

## What this does **not** close

- **Org GPG / verified-commit branch protection** (G-C04-01 / WBS-P2.1) still
  requires repository/org admin policy — local signing alone does not enforce
  verified commits on all contributors.
- DCO and cryptographic signing are complementary: DCO is CI-gated; signing is
  opt-in per contributor until W-228 ships.

## Related

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — DCO requirement
- [GitHub: About commit signature verification](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification)
