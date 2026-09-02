"""Tests for the `viz ship` CLI command."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from melosviz.cli.main import main


def test_ship_online_prints_zip_metadata(tmp_path: Path, capsys) -> None:
    (tmp_path / "master.mp4").write_bytes(b"video")
    with pytest.raises(SystemExit) as exit_info:
        main(["ship", str(tmp_path)])
    assert exit_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "online"
    assert payload["final_zip"].endswith("final.zip")
    assert payload["final_zip_bytes"] > 0
    with zipfile.ZipFile(payload["final_zip"]) as archive:
        assert "deliverables/master.mp4" in archive.namelist()


def test_ship_missing_directory_exits_nonzero(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    try:
        main(["ship", str(missing)])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("main must exit nonzero for a missing job directory")
