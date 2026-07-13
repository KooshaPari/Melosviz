"""C00 L8 — global memory-cap enforcement (process-level RSS ceiling).

Distinct from ``TestRenderQuota`` in ``test_bridge_security.py``: those tests
cover the *per-slot* soft RSS check tied to concurrency accounting
(``RenderQuota``). These tests cover the *global* ``MemoryCapGuard`` — a
process-wide ceiling independent of how many render slots are in flight,
with two tiers (soft → 429, hard → 503) and a guarantee that the process
itself never crashes, even when RSS can't be measured.

Run:
    pytest backend/tests/test_bridge_memory_cap.py -x -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Unit tests — security.MemoryCapGuard in isolation (no HTTP, no psutil dep)
# ---------------------------------------------------------------------------


class TestMemoryCapGuardUnit:
    def test_under_both_ceilings_is_a_noop(self):
        from melosviz.bridge.security import MemoryCapGuard

        guard = MemoryCapGuard(
            hard_cap_mb=1000, soft_cap_mb=500, rss_probe=lambda: 10.0
        )
        guard.check()  # must not raise

    def test_over_soft_ceiling_raises_soft(self):
        from melosviz.bridge.security import MemoryCapExceeded, MemoryCapGuard

        guard = MemoryCapGuard(
            hard_cap_mb=1000, soft_cap_mb=500, rss_probe=lambda: 600.0
        )
        with pytest.raises(MemoryCapExceeded) as excinfo:
            guard.check()
        assert excinfo.value.tier == "soft"
        assert excinfo.value.rss_mb == 600.0
        assert excinfo.value.cap_mb == 500

    def test_over_hard_ceiling_raises_hard_not_soft(self):
        """When RSS clears both ceilings, hard must win (worse outcome first)."""
        from melosviz.bridge.security import MemoryCapExceeded, MemoryCapGuard

        guard = MemoryCapGuard(
            hard_cap_mb=1000, soft_cap_mb=500, rss_probe=lambda: 1500.0
        )
        with pytest.raises(MemoryCapExceeded) as excinfo:
            guard.check()
        assert excinfo.value.tier == "hard"
        assert excinfo.value.cap_mb == 1000

    def test_disabled_when_both_caps_zero_or_negative(self):
        from melosviz.bridge.security import MemoryCapGuard

        guard = MemoryCapGuard(
            hard_cap_mb=0, soft_cap_mb=0, rss_probe=lambda: 999_999.0
        )
        guard.check()  # must not raise — fully disabled

    def test_fails_open_when_rss_unmeasurable(self):
        """No psutil / unsupported platform → probe returns None → never raise."""
        from melosviz.bridge.security import MemoryCapGuard

        guard = MemoryCapGuard(hard_cap_mb=1, soft_cap_mb=1, rss_probe=lambda: None)
        guard.check()  # must not raise — fails open, bridge keeps serving

    def test_soft_cap_defaults_to_85pct_of_hard(self, monkeypatch: pytest.MonkeyPatch):
        from melosviz.bridge import security

        monkeypatch.setenv("MELOSVIZ_MEMORY_CAP_MB", "1000")
        monkeypatch.delenv("MELOSVIZ_MEMORY_SOFT_CAP_MB", raising=False)
        assert security.memory_soft_cap_mb() == 850

    def test_explicit_soft_cap_env_wins_over_default(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from melosviz.bridge import security

        monkeypatch.setenv("MELOSVIZ_MEMORY_CAP_MB", "1000")
        monkeypatch.setenv("MELOSVIZ_MEMORY_SOFT_CAP_MB", "200")
        assert security.memory_soft_cap_mb() == 200

    def test_hard_cap_disabled_via_env_disables_default_soft_too(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from melosviz.bridge import security

        monkeypatch.setenv("MELOSVIZ_MEMORY_CAP_MB", "0")
        monkeypatch.delenv("MELOSVIZ_MEMORY_SOFT_CAP_MB", raising=False)
        assert security.memory_cap_mb() == 0
        assert security.memory_soft_cap_mb() == 0

    def test_default_hard_cap_is_4096_mb(self, monkeypatch: pytest.MonkeyPatch):
        from melosviz.bridge import security

        monkeypatch.delenv("MELOSVIZ_MEMORY_CAP_MB", raising=False)
        assert security.memory_cap_mb() == 4096


# ---------------------------------------------------------------------------
# HTTP integration — /analyze rejects with problem+json 503/429 and audits
# ---------------------------------------------------------------------------


@pytest.fixture()
def bridge_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Clean bridge env; auth disabled so we isolate the memory-cap path."""
    monkeypatch.setenv("MELOSVIZ_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MELOSVIZ_BRIDGE_REQUIRE_AUTH", raising=False)
    monkeypatch.setenv("MELOSVIZ_BRIDGE_RATE_LIMIT", "1000")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_WINDOW", "60")
    try:
        from melosviz.bridge import server

        server.security_limiter.reset()
        server.render_quota.reset()
        server.mir_breaker.reset()
    except Exception:
        pass
    yield tmp_path
    try:
        from melosviz.bridge import server

        server.security_limiter.reset()
        server.render_quota.reset()
        server.mir_breaker.reset()
        # Restore a real (unpatched) guard so later tests aren't affected.
        server.memory_cap = server.security.MemoryCapGuard()
    except Exception:
        pass


def _client(bridge_env):
    from fastapi.testclient import TestClient

    from melosviz.bridge import server

    return TestClient(server.app), bridge_env


class TestMemoryCapHttpIntegration:
    def test_hard_cap_exceeded_returns_503_problem_json(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        from melosviz.bridge import security, server

        tight = security.MemoryCapGuard(
            hard_cap_mb=100, soft_cap_mb=0, rss_probe=lambda: 200.0
        )
        monkeypatch.setattr(server, "memory_cap", tight)

        wav = bridge_env / "song.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)
        client, _ = _client(bridge_env)
        resp = client.post("/analyze", json={"wav_path": str(wav)})

        assert resp.status_code == 503
        assert resp.headers.get("content-type", "").startswith(
            "application/problem+json"
        )
        body = resp.json()
        assert body["status"] == 503
        assert "memory" in body["detail"].lower()

    def test_soft_cap_exceeded_returns_429_with_retry_after(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        from melosviz.bridge import security, server

        tight = security.MemoryCapGuard(
            hard_cap_mb=1000, soft_cap_mb=100, rss_probe=lambda: 150.0
        )
        monkeypatch.setattr(server, "memory_cap", tight)

        wav = bridge_env / "song.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)
        client, _ = _client(bridge_env)
        resp = client.post("/analyze", json={"wav_path": str(wav)})

        assert resp.status_code == 429
        assert resp.headers.get("content-type", "").startswith(
            "application/problem+json"
        )
        assert "Retry-After" in resp.headers

    def test_memory_cap_rejection_appends_audit_row(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        from melosviz.bridge import security, server

        tight = security.MemoryCapGuard(
            hard_cap_mb=100, soft_cap_mb=0, rss_probe=lambda: 200.0
        )
        monkeypatch.setattr(server, "memory_cap", tight)

        wav = bridge_env / "song.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)
        client, data_dir = _client(bridge_env)
        client.post("/analyze", json={"wav_path": str(wav)})

        audit_path = data_dir / "audit" / "bridge.jsonl"
        assert audit_path.exists()
        rows = [
            json.loads(line)
            for line in audit_path.read_text().splitlines()
            if line.strip()
        ]
        memory_rows = [r for r in rows if r.get("reason") == "memory_cap_exceeded"]
        assert memory_rows, f"no memory_cap_exceeded audit row found in {rows}"
        row = memory_rows[0]
        assert row["tier"] == "hard"
        assert row["status"] == 503
        assert row["cap_mb"] == 100
        assert row["rss_mb"] == pytest.approx(200.0)

    def test_under_cap_proceeds_normally(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        """Sanity: a guard well under both ceilings never blocks the request."""
        from melosviz.bridge import security, server

        loose = security.MemoryCapGuard(
            hard_cap_mb=999_999, soft_cap_mb=0, rss_probe=lambda: 10.0
        )
        monkeypatch.setattr(server, "memory_cap", loose)

        wav = bridge_env / "song.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)
        client, _ = _client(bridge_env)
        resp = client.post("/analyze", json={"wav_path": str(wav)})

        # Never 503/429 due to the memory cap; either parses (200) or fails
        # on the placeholder WAV body (400) — both prove the cap let it pass.
        assert resp.status_code in (200, 400)

    def test_unmeasurable_rss_never_blocks_request(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        """Fail-open guarantee: if RSS can't be read, requests still proceed."""
        from melosviz.bridge import security, server

        blind = security.MemoryCapGuard(
            hard_cap_mb=1, soft_cap_mb=1, rss_probe=lambda: None
        )
        monkeypatch.setattr(server, "memory_cap", blind)

        wav = bridge_env / "song.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)
        client, _ = _client(bridge_env)
        resp = client.post("/analyze", json={"wav_path": str(wav)})

        assert resp.status_code in (200, 400)

    def test_metrics_endpoint_exposes_rss_and_cap_gauges(self, bridge_env):
        client, _ = _client(bridge_env)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "melosviz_memory_cap_mb" in resp.text
        # RSS gauge is best-effort (may be absent on exotic platforms without
        # psutil/resource); the cap gauge must always be present.

    def test_build_and_render_also_enforce_memory_cap(
        self, bridge_env, monkeypatch: pytest.MonkeyPatch
    ):
        from melosviz.bridge import security, server

        tight = security.MemoryCapGuard(
            hard_cap_mb=100, soft_cap_mb=0, rss_probe=lambda: 200.0
        )
        monkeypatch.setattr(server, "memory_cap", tight)

        wav = bridge_env / "song.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 64)
        out_dir = bridge_env / "out"
        client, _ = _client(bridge_env)

        build_resp = client.post("/build", json={"wav_path": str(wav)})
        assert build_resp.status_code == 503

        render_resp = client.post(
            "/render", json={"wav_path": str(wav), "out_dir": str(out_dir)}
        )
        assert render_resp.status_code == 503
