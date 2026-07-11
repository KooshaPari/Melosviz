# Bridge token / key rotation

The MelosViz bridge authenticates with a shared bearer secret
(`MELOSVIZ_BRIDGE_TOKEN`) when `MELOSVIZ_BRIDGE_REQUIRE_AUTH=1`.

## Rotation procedure

1. Generate a new high-entropy secret (≥32 bytes):
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Update the desktop/operator env (or secret store) with the new value.
3. Restart the bridge process so it reloads env.
4. Update any clients (Electrobun main, curl scripts, CI) in the same window.
5. Invalidate the old token by ensuring it is no longer present in env files,
   shell history, or CI variable history.

## Storage guidance

- Prefer OS secret stores / CI encrypted secrets over plaintext `.env` in git.
- Never commit `MELOSVIZ_BRIDGE_TOKEN`.
- Compare uses `hmac.compare_digest` (timing-safe); do not log the raw token.

## Out of scope

Hardware KMS / cloud CMK integration is not required for the localhost desktop
threat model. Documented here for C02 L22 / C01 L18 evidence.
