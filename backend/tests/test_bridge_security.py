"""Hard Rule #18: failing tests FIRST for B8 MelosViz bridge security hardening.

Each test documents a specific exploit class and asserts the bridge refuses it.
When the test passes, the bridge is hardened against that vector.

Coverage:

1. **Path traversal** — /analyze must reject requests whose wav_path escapes the
   user-configured allowed directory (default: $HOME or MELOSVIZ_DATA_DIR).

2. **Auth** — /analyze, /build, /render must require a Bearer token when
   MELOSVIZ_BRIDGE_REQUIRE_AUTH=1 (the new explicit-yes default for any non-loopback
   bind). Without the env var the legacy desktop-local mode is preserved.

3. **Rate limit** — sliding-window per remote-IP limiter: requests beyond N/min from
   one source return 429 with Retry-After.

4. **Audit log** — every protected call records a row (timestamp, IP, method,
   path, status, dur_ms) to $MELOSVIZ_DATA_DIR/audit/bridge.jsonl.

5. **Loopback assertion** — main() refuses --host 0.0.0.0 unless
   MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1.

6. **Body size cap** — POST bodies > 1 MiB rejected with 413 before parse.

Run:
    MELOSVIZ_DATA_DIR=/tmp/mvz-sec pytest backend/tests/test_bridge_security.py -x -q
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bridge_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set a clean env for the bridge subprocess; never inherit host state."""
    monkeypatch.setenv("MELOSVIZ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MELOSVIZ_BRIDGE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_TOKEN", "test-token-aaa")
    # Generous limit so non-rate-limit tests never trip 429 by accident.
    # The rate-limit test patches the limit directly via TestRateLimit
    # and the burst is 50 requests → the default 30 would be too tight.
    monkeypatch.setenv("MELOSVIZ_BRIDGE_RATE_LIMIT", "1000")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_WINDOW", "60")
    # Reset the global limiter between tests so cross-test bleed is impossible.
    try:
        from melosviz.bridge import server
        server.security_limiter.reset()
    except Exception:
        pass
    yield tmp_path
    try:
        from melosviz.bridge import server
        server.security_limiter.reset()
    except Exception:
        pass


def _client(bridge_env):
    """Build a TestClient; the bridge module reads env vars at import time."""
    from fastapi.testclient import TestClient

    from melosviz.bridge import server

    # Re-import doesn't re-evaluate os.environ on top-level; the security module
    # we'll add reads env lazily on each request, so this is fine.
    return TestClient(server.app), bridge_env


# ---------------------------------------------------------------------------
# 1. Loopback assertion
# ---------------------------------------------------------------------------


class TestLoopbackAssertion:
    def test_main_refuses_public_bind_without_allow_flag(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        """main() must exit non-zero if --host 0.0.0.0 and no allow flag."""
        from melosviz.bridge import server

        monkeypatch.setattr("sys.argv", ["server", "--host", "0.0.0.0", "--port", "0"])
        monkeypatch.delenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", raising=False)

        with pytest.raises(SystemExit) as excinfo:
            server.main()
        assert excinfo.value.code != 0
        captured = capsys.readouterr()
        assert "loopback" in captured.err.lower() or "0.0.0.0" in captured.err

    def test_main_allows_public_bind_with_allow_flag(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        """main() must accept 0.0.0.0 when MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1.

        We don't actually start uvicorn here — we verify the env gate clears the
        loopback check (no SystemExit on the validation step).
        """
        from melosviz.bridge import server

        monkeypatch.setenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", "1")

        # Patch uvicorn.run to a no-op so the test doesn't bind a real socket.
        import unittest.mock as mock

        called = {}
        with mock.patch.object(server.uvicorn, "run", **{
            "side_effect": lambda app, host, port, log_level: called.update(
                {"host": host, "port": port, "log_level": log_level}
            )
        }) as _run:
            monkeypatch.setattr("sys.argv", ["server", "--host", "0.0.0.0", "--port", "9123"])
            server.main()

        assert called["host"] == "0.0.0.0"
        assert called["port"] == 9123


# ---------------------------------------------------------------------------
# 2. Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_analyze_requires_bearer_token(self, bridge_env):
        client, _ = _client(bridge_env)
        resp = client.post("/analyze", json={"wav_path": "/tmp/x.wav"})
        assert resp.status_code == 401
        body = resp.json()
        assert "WWW-Authenticate" in resp.headers or "auth" in body.get("detail", "").lower()

    def test_analyze_rejects_wrong_token(self, bridge_env):
        client, _ = _client(bridge_env)
        resp = client.post(
            "/analyze",
            json={"wav_path": "/tmp/x.wav"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 403

    def test_analyze_accepts_correct_token(self, bridge_env, tmp_path: Path):
        client, _ = _client(bridge_env)
        # Provide a real (empty) wav — write one inline.
        wav = bridge_env / "ok.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)  # placeholder; spec_from_wav will reject → 400 is fine
        resp = client.post(
            "/analyze",
            json={"wav_path": str(wav)},
            headers={"Authorization": "Bearer test-token-aaa"},
        )
        # Either 200 (parsed) or 400 (bad wav) — BOTH prove auth passed.
        assert resp.status_code in (200, 400), resp.text
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# 3. Rate limit
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_burst_returns_429_with_retry_after(
        self, bridge_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """More than N requests/min from one source returns 429."""
        monkeypatch.setenv("MELOSVIZ_BRIDGE_RATE_LIMIT", "5")
        monkeypatch.setenv("MELOSVIZ_BRIDGE_WINDOW", "60")
        from melosviz.bridge import security, server

        fresh = security.RateLimiter(max_requests=5, window_seconds=60)
        # Register the new limiter so the middleware picks it up.
        security._LIVE_LIMITERS[id(server.app)] = fresh
        try:
            client, _ = _client(bridge_env)
            headers = {"Authorization": "Bearer test-token-aaa"}
            last = None
            triggered = False
            for _ in range(50):
                last = client.get("/health", headers=headers)
                if last.status_code == 429:
                    triggered = True
                    break
            assert triggered, f"rate limiter did not trigger; last={last.status_code if last else 'None'}"
            assert "Retry-After" in last.headers
        finally:
            # Restore the original limiter so other tests aren't affected.
            security._LIVE_LIMITERS[id(server.app)] = server.security_limiter


# ---------------------------------------------------------------------------
# 4. Audit log
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_jsonl_records_protected_requests(self, bridge_env):
        client, data_dir = _client(bridge_env)
        headers = {"Authorization": "Bearer test-token-aaa"}
        client.get("/health", headers=headers)
        client.post("/analyze", json={"wav_path": "/nonexistent.wav"}, headers=headers)

        audit_path = data_dir / "audit" / "bridge.jsonl"
        assert audit_path.exists(), f"audit log missing at {audit_path}"
        rows = [json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()]
        assert len(rows) >= 2
        # Required fields per row.
        for row in rows:
            assert {"ts", "ip", "method", "path", "status", "dur_ms"} <= set(row.keys())
            assert row["method"] in {"GET", "POST"}
            assert row["path"].startswith("/")
            assert 100 <= row["status"] < 600

    def test_audit_swallows_io_errors_without_breaking_request(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        """An audit-log write failure must not surface as a 500 to the caller."""
        client, _ = _client(bridge_env)
        # Force the audit writer to raise, then prove the response is still 200/401.
        import unittest.mock as mock

        def boom(*_a, **_k):
            raise OSError("disk full")

        # Patch lazily — the audit module is imported inside the bridge handler.
        with mock.patch("melosviz.bridge.security.append_audit", side_effect=boom):
            resp = client.get(
                "/health",
                headers={"Authorization": "Bearer test-token-aaa"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. Path traversal
# ---------------------------------------------------------------------------


class TestPathContainment:
    def test_outside_allowed_dir_is_rejected_with_400(self, bridge_env):
        client, _ = _client(bridge_env)
        headers = {"Authorization": "Bearer test-token-aaa"}
        # /etc/passwd is outside any reasonable user data dir.
        resp = client.post(
            "/analyze",
            json={"wav_path": "/etc/passwd"},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "outside" in resp.json().get("detail", "").lower() or "path" in resp.json().get("detail", "").lower()

    def test_inside_allowed_dir_is_accepted_or_400_not_403(self, bridge_env, tmp_path: Path):
        client, _ = _client(bridge_env)
        headers = {"Authorization": "Bearer test-token-aaa"}
        wav = bridge_env / "song.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)
        resp = client.post(
            "/analyze",
            json={"wav_path": str(wav)},
            headers=headers,
        )
        # Authorized; either spec parses (200) or fails on wav format (400),
        # never 401/403/404 due to auth/path.
        assert resp.status_code in (200, 400), resp.text


# ---------------------------------------------------------------------------
# 6. Body size cap
# ---------------------------------------------------------------------------


class TestBodySizeCap:
    def test_huge_body_rejected_with_413(self, bridge_env):
        client, _ = _client(bridge_env)
        headers = {"Authorization": "Bearer test-token-aaa"}
        huge = {"wav_path": "/" + ("A" * (2 * 1024 * 1024))}  # 2 MiB > 1 MiB cap
        resp = client.post("/analyze", json=huge, headers=headers)
        assert resp.status_code == 413
