"""Deterministic delivery ZIP packaging for MelosViz."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path

from .vj import discover_shots, export_vj_cues


MEDIA_PATTERNS = ("*.mp4", "*.mov", "*.wav", "*.aif", "*.srt", "*.vtt", "*.edl")
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
EXCLUDED_PATH_PARTS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "target",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".worktrees",
    }
)
MAX_DISCOVERY_DEPTH = 6


def _discover_media(job_dir: Path) -> list[Path]:
    excluded = {job_dir / "final.zip", job_dir / ".final.zip.tmp"}
    found: set[Path] = set()
    job_dir_resolved = job_dir.resolve()
    for pattern in MEDIA_PATTERNS:
        for path in job_dir.rglob(pattern):
            if not path.is_file() or path in excluded:
                continue
            if "deliverables" in path.parts:
                continue
            # Skip paths inside excluded build / VCS / dependency trees.
            if any(part in EXCLUDED_PATH_PARTS for part in path.parts):
                continue
            # Bound recursion depth: an unexpectedly huge tree (bind mounts,
            # accidental nested checkouts) must not OOM the packaging step.
            try:
                relative = path.relative_to(job_dir_resolved)
            except ValueError:
                continue
            if len(relative.parts) > MAX_DISCOVERY_DEPTH:
                continue
            found.add(path)
    return sorted(found, key=lambda path: path.relative_to(job_dir).as_posix())


def _safe_archive_name(relative: Path) -> str:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe archive path: {relative}")
    return relative.as_posix()


def _write_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(_safe_archive_name(Path(name)), FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_delivery_package(
    job_dir: Path,
    *,
    bundle_name: str | None = None,
    bundle_output_dir: Path | None = None,
) -> dict:
    # Record the *caller-supplied* path in the manifest, not the
    # resolved one. .resolve() would fold in the host's filesystem
    # layout (e.g. /private/tmp vs /tmp on macOS, symlinked bind
    # mounts, realpath chains) and break byte-stable reproducibility
    # across machines. The resolved root is still used internally for
    # safe rglob + relative_to work.
    manifest_root = job_dir.expanduser()
    root = manifest_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    media = _discover_media(root)
    deliverables = root / "deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in media:
        relative = source.relative_to(root)
        target = deliverables / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)

    shots = discover_shots(root, media)
    vj_files = export_vj_cues(shots, deliverables / "vj")
    mode = "online" if media else "offline"
    manifest = {
        "schema_version": "1.0",
        "job_dir": str(manifest_root),
        "mode": mode,
        "count": len(copied),
        "deliverables": [
            path.relative_to(deliverables).as_posix() for path in copied
        ],
        "vj": [path.relative_to(deliverables).as_posix() for path in vj_files],
    }
    if mode == "offline":
        manifest["note"] = (
            "No rendered media files found. Re-run viz master and viz ship "
            "after rendering real clips."
        )
    manifest_path = deliverables / "manifest.json"
    _atomic_json(manifest_path, manifest)

    output_dir = bundle_output_dir if bundle_output_dir is not None else root
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_zip = output_dir / (bundle_name or "final.zip")
    temporary_zip = output_dir / ".final.zip.tmp"
    try:
        with zipfile.ZipFile(temporary_zip, "w") as archive:
            if mode == "offline":
                _write_entry(
                    archive,
                    "README.txt",
                    b"MelosViz offline render - no clips produced yet.\n",
                )
            _write_entry(archive, "manifest.json", manifest_path.read_bytes())
            for path in sorted(copied, key=lambda value: value.as_posix()):
                name = "deliverables/" + path.relative_to(deliverables).as_posix()
                if path.is_file():
                    _write_entry(archive, name, path.read_bytes())
            for path in sorted(vj_files, key=lambda value: value.as_posix()):
                name = path.relative_to(deliverables).as_posix()
                if path.is_file():
                    _write_entry(archive, name, path.read_bytes())
        os.replace(temporary_zip, final_zip)
    except BaseException:
        if temporary_zip.exists():
            temporary_zip.unlink()
        raise
    return {
        **manifest,
        "manifest": str(manifest_path),
        "final_zip": str(final_zip),
        "final_zip_bytes": final_zip.stat().st_size,
    }
