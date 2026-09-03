"""Tests for deterministic delivery ZIP packaging."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from melosviz.export.package import build_delivery_package


def test_online_package_contains_media_manifest_and_vj(tmp_path: Path) -> None:
    media = tmp_path / "festival_master.mov"
    media.write_bytes(b"movie")
    (tmp_path / "storyboard.json").write_text(json.dumps({
        "scenes": [{
            "index": 0,
            "label": "intro",
            "start": 0.0,
            "duration": 4.0,
            "prompt": "neon intro",
            "beats_in_segment": [0.0, 2.0, 4.0],
        }]
    }))
    result = build_delivery_package(tmp_path)
    assert result["mode"] == "online"
    assert Path(result["final_zip"]).is_file()
    with zipfile.ZipFile(result["final_zip"]) as archive:
        names = archive.namelist()
    assert "deliverables/festival_master.mov" in names
    assert "manifest.json" in names
    assert "vj/shot-0000-00.svg" in names
    assert "vj/shot-0000-00.lottie.json" in names


def test_package_is_byte_deterministic(tmp_path: Path) -> None:
    (tmp_path / "club.mp4").write_bytes(b"video")
    first = build_delivery_package(tmp_path)
    first_bytes = Path(first["final_zip"]).read_bytes()
    second = build_delivery_package(tmp_path)
    assert Path(second["final_zip"]).read_bytes() == first_bytes


def test_package_failure_preserves_previous_zip(tmp_path: Path, monkeypatch) -> None:
    final_zip = tmp_path / "final.zip"
    final_zip.write_bytes(b"previous-valid-zip")
    (tmp_path / "club.mp4").write_bytes(b"video")

    real_replace = os.replace

    def fail_replace(source, target):
        if Path(target).name == "final.zip":
            raise OSError("replace failed")
        real_replace(source, target)

    monkeypatch.setattr("melosviz.export.package.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        build_delivery_package(tmp_path)
    assert final_zip.read_bytes() == b"previous-valid-zip"
    assert not (tmp_path / ".final.zip.tmp").exists()


def test_offline_package_retains_readme_and_empty_vj_manifest(tmp_path: Path) -> None:
    result = build_delivery_package(tmp_path)
    assert result["mode"] == "offline"
    with zipfile.ZipFile(result["final_zip"]) as archive:
        names = archive.namelist()
    assert "README.txt" in names
    assert "manifest.json" in names
    assert "vj/manifest.json" in names


def test_duplicate_media_basenames_keep_distinct_archive_paths(tmp_path: Path) -> None:
    first = tmp_path / "festival" / "master.mp4"
    second = tmp_path / "club" / "master.mp4"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"festival")
    second.write_bytes(b"club")
    result = build_delivery_package(tmp_path)
    with zipfile.ZipFile(result["final_zip"]) as archive:
        names = archive.namelist()
        assert archive.read("deliverables/festival/master.mp4") == b"festival"
        assert archive.read("deliverables/club/master.mp4") == b"club"
    assert names.count("deliverables/festival/master.mp4") == 1
    assert names.count("deliverables/club/master.mp4") == 1


def test_manifest_records_caller_supplied_path_not_resolved(
    tmp_path: Path,
) -> None:
    """Regression: ``manifest['job_dir']`` was the *resolved* path, which
    folds in the host's filesystem layout (/private/tmp vs /tmp on
    macOS, realpath chains on bind mounts). Two runs on different hosts
    produced different manifests. The manifest now records exactly what
    the caller passed in."""

    # Create a temp alias by symlinking and run with the *symlink* path.
    target = tmp_path / "real_dir"
    target.mkdir()
    (target / "clip.mp4").write_bytes(b"x")
    alias = tmp_path / "alias_dir"
    alias.symlink_to(target)
    result = build_delivery_package(alias)
    # The manifest must echo the path the caller handed us, not the
    # resolved one.
    assert result["job_dir"] == str(alias)
