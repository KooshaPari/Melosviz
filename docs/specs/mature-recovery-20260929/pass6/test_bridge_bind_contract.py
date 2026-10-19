"""Recovery regression for the bridge bind contract.

Run from the Melosviz backend environment:
  pytest docs/specs/mature-recovery-20260929/pass6/test_bridge_bind_contract.py -q

This test intentionally fails frozen source until the fail-open host classifier is
repaired. It tests one security contract only; it is not product acceptance.
"""
from __future__ import annotations
import os
import pytest
from melosviz.bridge import security

@pytest.mark.parametrize("host", ["127.0.0.1", "127.12.3.4", "::1", "localhost"])
def test_true_loopback_allowed_without_public_override(monkeypatch, host):
    monkeypatch.delenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", raising=False)
    ok, _ = security.loopback_check(host)
    assert ok is True

@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0", "::", "*",
        "192.168.1.10", "10.0.0.7", "172.16.1.2",
        "169.254.1.2", "8.8.8.8", "2001:4860:4860::8888",
        "example.com", "my-laptop.local",
    ],
)
def test_non_loopback_requires_explicit_public_authorization(monkeypatch, host):
    monkeypatch.delenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", raising=False)
    ok, reason = security.loopback_check(host)
    assert ok is False, f"{host!r} was accepted as {reason!r} without public-bind authorization"

@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "example.com"])
def test_explicit_public_authorization_allows_non_loopback(monkeypatch, host):
    monkeypatch.setenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", "1")
    ok, reason = security.loopback_check(host)
    assert ok is True
    assert "ALLOW_PUBLIC" in reason

def test_public_bind_must_not_silently_inherit_legacy_auth_off(monkeypatch):
    """Architecture guard for the repair: public authorization and auth are distinct.

    Current helper exposes auth_required independently; after the bind classifier is
    fixed, server startup must couple an authorized public bind to an explicit auth
    policy. This test is xfail until that startup contract is implemented.
    """
    monkeypatch.setenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", "1")
    monkeypatch.delenv("MELOSVIZ_BRIDGE_REQUIRE_AUTH", raising=False)
    ok, _ = security.loopback_check("192.168.1.10")
    assert ok
    pytest.xfail("server startup must require or explicitly waive bearer auth for public bind")
