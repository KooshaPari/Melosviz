"""Smoke tests for the ``viz character`` subcommand.

These tests exercise the parser wiring (subcommand is registered, flags
exist, ``main([...])`` dispatches to ``_cmd_character``) and the
``list`` + ``add`` end-to-end behaviour against a tmp directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    """Invoke ``melosviz.cli.main.main(argv)`` and capture stdout/stderr.

    Returns ``(rc, stdout, stderr)``. We redirect the real ``sys.stdout``
    during the call because the command uses ``print()`` rather than a
    ``stream=`` parameter.
    """
    import io

    from melosviz.cli import main as cli_main

    saved_out, saved_err = sys.stdout, sys.stderr
    out_buf, err_buf = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    rc = 0
    try:
        try:
            cli_main.main(argv)
        except SystemExit as exc:  # argparse --help / parse errors
            rc = int(exc.code or 0)
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
    return rc, out_buf.getvalue(), err_buf.getvalue()


def test_character_list_action_reports_empty_registry(tmp_path: Path):
    """Running ``viz character list`` against an empty root prints count=0."""
    rc, out, err = _run_cli(["character", "list", "--root", str(tmp_path)])
    assert rc == 0, err
    payload = json.loads(out)
    assert payload["count"] == 0
    assert payload["characters"] == []
    assert payload["root"] == str(tmp_path)


def test_character_add_then_list_round_trips(tmp_path: Path):
    """``viz character add`` persists a sheet that ``list`` then sees."""
    # 1) add
    front = tmp_path / "alice_front.png"
    front.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    rc, out, err = _run_cli([
        "character", "add",
        "--root", str(tmp_path),
        "--name", "alice",
        "--description", "lead dancer",
        "--engine", "ipadapter",
        "--front", str(front),
    ])
    assert rc == 0, err
    add_payload = json.loads(out)
    assert add_payload["name"] == "alice"
    assert add_payload["engine"] == "ipadapter"
    assert add_payload["is_complete"] is True
    assert add_payload["reference_slots"]["front"] == str(front)
    assert Path(add_payload["saved_to"]).exists()

    # 2) list
    rc, out, err = _run_cli(["character", "list", "--root", str(tmp_path)])
    assert rc == 0, err
    list_payload = json.loads(out)
    assert list_payload["count"] == 1
    names = [entry["name"] for entry in list_payload["characters"]]
    assert names == ["alice"]
    entry = list_payload["characters"][0]
    assert entry["description"] == "lead dancer"
    assert entry["engine"] == "ipadapter"
