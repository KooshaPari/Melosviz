from __future__ import annotations

from unittest import mock

import pytest


def test_public_bind_requires_explicit_data_root(monkeypatch, capsys):
    from melosviz.bridge import server

    monkeypatch.setenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", "1")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_TOKEN", "test-token-aaa")
    monkeypatch.delenv("MELOSVIZ_BRIDGE_ALLOWED_DIR", raising=False)
    monkeypatch.delenv("MELOSVIZ_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.argv", ["server", "--host", "192.168.1.10", "--port", "0"])

    with pytest.raises(SystemExit) as excinfo:
        server.main()

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "ALLOWED_DIR" in err or "DATA_DIR" in err


def test_authorized_public_bind_with_auth_token_and_root_reaches_uvicorn(
    tmp_path, monkeypatch
):
    from melosviz.bridge import server

    monkeypatch.setenv("MELOSVIZ_BRIDGE_ALLOW_PUBLIC", "1")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_TOKEN", "test-token-aaa")
    monkeypatch.setenv("MELOSVIZ_BRIDGE_ALLOWED_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["server", "--host", "192.168.1.10", "--port", "9123"])

    called = {}
    with mock.patch.object(
        server.uvicorn,
        "run",
        side_effect=lambda app, host, port, log_level: called.update(
            {"host": host, "port": port, "log_level": log_level}
        ),
    ):
        server.main()

    assert called["host"] == "192.168.1.10"
    assert called["port"] == 9123
