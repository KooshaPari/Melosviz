"""Tests for `viz direct` — the art-director single-scene edit command.

Verifies that `viz direct <storyboard.json> --scene-index N --replace-prompt '...'`
patches a storyboard.json in-place (or to --out) and bumps the edit counter,
without touching any of the other scenes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    # melosviz package lives at backend/src/melosviz/ — point PYTHONPATH at the
    # absolute backend/src so subprocess finds it regardless of the caller's cwd.
    backend_src = (Path(__file__).resolve().parent.parent / "src").resolve()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_src)
    return subprocess.run(
        [sys.executable, "-m", "melosviz.cli.main", *args],
        cwd=str(cwd) if cwd else str(backend_src.parent),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def _make_storyboard(tmp_path: Path) -> Path:
    """A 3-scene storyboard.json with prompts + cameras + palette."""
    sb = {
        "concept": "neon noir test",
        "bpm": 124,
        "scenes": [
            {
                "name": "intro",
                "start": 0.0,
                "end": 10.0,
                "duration": 10.0,
                "prompt": "A bioluminescent underwater city at dusk",
                "camera": "slow_dolly_in",
                "palette": ["#0d0d10", "#ff2bd6"],
                "scene_type": "comfyui_image",
            },
            {
                "name": "verse",
                "start": 10.0,
                "end": 30.0,
                "duration": 20.0,
                "prompt": "A silver-haired dancer in a neon trenchcoat",
                "camera": "slow_pull_back",
                "palette": ["#0d0d10", "#22d3ee"],
                "scene_type": "comfyui_video",
            },
            {
                "name": "chorus",
                "start": 30.0,
                "end": 50.0,
                "duration": 20.0,
                "prompt": "Whip pan across a glass skyway",
                "camera": "whip_pan_burst",
                "palette": ["#0d0d10", "#c084fc"],
                "scene_type": "comfyui_image",
            },
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb, indent=2))
    return p


def test_direct_help_lists_required_args() -> None:
    """`viz direct --help` shows --scene-index is required and the editable fields."""
    result = _run_cli("direct", "--help")
    assert result.returncode == 0
    assert "--scene-index" in result.stdout
    assert "--replace-prompt" in result.stdout
    assert "--replace-camera" in result.stdout
    assert "--replace-name" in result.stdout
    assert "--re-render" in result.stdout


def test_direct_replaces_prompt_only(tmp_path: Path) -> None:
    """`viz direct <sb.json> --scene-index 2 --replace-prompt 'new'` patches
    scene 2's prompt in-place and leaves scenes 1 + 3 untouched."""
    sb_path = _make_storyboard(tmp_path)
    new_prompt = "Silver-haired dancer in a neon trenchcoat, slow motion"
    result = _run_cli(
        "direct",
        str(sb_path),
        "--scene-index", "2",
        "--replace-prompt", new_prompt,
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    patched = json.loads(sb_path.read_text())
    assert patched["scenes"][1]["prompt"] == new_prompt
    # Other scenes untouched
    assert patched["scenes"][0]["prompt"] == "A bioluminescent underwater city at dusk"
    assert patched["scenes"][2]["prompt"] == "Whip pan across a glass skyway"
    # edit counter bumped
    assert patched.get("edit_count") == 1
    assert patched.get("last_edit", {}).get("scene") == 2


def test_direct_replaces_multiple_fields(tmp_path: Path) -> None:
    """A single `direct` call can replace prompt + camera + name at once."""
    sb_path = _make_storyboard(tmp_path)
    result = _run_cli(
        "direct",
        str(sb_path),
        "--scene-index", "1",
        "--replace-prompt", "NEW intro prompt",
        "--replace-camera", "whip_pan_burst",
        "--replace-name", "INTRO_v2",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    patched = json.loads(sb_path.read_text())
    s = patched["scenes"][0]
    assert s["prompt"] == "NEW intro prompt"
    assert s["camera"] == "whip_pan_burst"
    assert s["name"] == "INTRO_v2"
    # 3 edits logged
    assert len(patched.get("last_edit", {}).get("edits", [])) == 3
    assert patched["edit_count"] == 1


def test_direct_writes_to_out_path_without_overwriting_original(tmp_path: Path) -> None:
    """With --out, the original storyboard.json is left untouched and a new
    file is written with the patch applied."""
    sb_path = _make_storyboard(tmp_path)
    out_path = tmp_path / "patched.json"
    result = _run_cli(
        "direct",
        str(sb_path),
        "--scene-index", "3",
        "--replace-name", "FINALE",
        "--out", str(out_path),
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    # Original untouched (no edit_count bumped)
    original = json.loads(sb_path.read_text())
    assert original["scenes"][2]["name"] == "chorus"
    assert "edit_count" not in original

    # New file has the patch
    patched = json.loads(out_path.read_text())
    assert patched["scenes"][2]["name"] == "FINALE"
    assert patched["edit_count"] == 1


def test_direct_rerender_emits_generate_hint(tmp_path: Path) -> None:
    """With --re-render + --render-out, stdout ends with a `viz generate`
    invocation the user can paste to re-render that scene."""
    # Use a real on-disk wav so --re-render's wav-existence check passes.
    track = tmp_path / "track.wav"
    track.write_bytes(b"RIFF$\x00\x00\x00WAVEfmt ")
    sb_path = _make_storyboard(tmp_path)
    render_out = tmp_path / "out"
    result = _run_cli(
        "direct",
        str(sb_path),
        "--scene-index", "2",
        "--replace-prompt", "test",
        "--re-render",
        "--wav", str(track),
        "--render-out", str(render_out),
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "viz generate" in result.stdout
    # The hint should scope to the edited scene
    assert "scene" in result.stdout.lower() or "2" in result.stdout


def test_direct_fails_when_scene_index_out_of_range(tmp_path: Path) -> None:
    """Asking for a scene past the end prints an error and exits non-zero."""
    sb_path = _make_storyboard(tmp_path)
    result = _run_cli(
        "direct",
        str(sb_path),
        "--scene-index", "99",
        "--replace-prompt", "x",
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "scene" in result.stderr.lower() or "out of" in result.stderr.lower()
    # Original file untouched
    original = json.loads(sb_path.read_text())
    assert "edit_count" not in original


def test_direct_fails_when_storyboard_missing(tmp_path: Path) -> None:
    """A non-existent storyboard path exits non-zero with a clear error."""
    result = _run_cli(
        "direct",
        str(tmp_path / "does_not_exist.json"),
        "--scene-index", "1",
        "--replace-prompt", "x",
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert (
        "not found" in result.stderr.lower()
        or "no such" in result.stderr.lower()
        or "missing" in result.stderr.lower()
    )


def test_direct_bumps_edit_count_on_each_run(tmp_path: Path) -> None:
    """Running `viz direct` twice on the same storyboard increments edit_count
    twice and records both edits in `last_edit`."""
    sb_path = _make_storyboard(tmp_path)
    r1 = _run_cli(
        "direct",
        str(sb_path),
        "--scene-index", "1",
        "--replace-prompt", "first edit",
        cwd=tmp_path,
    )
    assert r1.returncode == 0, r1.stderr
    r2 = _run_cli(
        "direct",
        str(sb_path),
        "--scene-index", "2",
        "--replace-camera", "whip_pan_burst",
        cwd=tmp_path,
    )
    assert r2.returncode == 0, r2.stderr
    patched = json.loads(sb_path.read_text())
    assert patched["edit_count"] == 2
    assert patched["last_edit"]["scene"] == 2
    assert "replace_camera" in patched["last_edit"]["edits"]
