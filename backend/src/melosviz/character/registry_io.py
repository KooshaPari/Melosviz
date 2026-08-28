"""Filesystem I/O for character sheets + registries.

The character system accepts two on-disk layouts so it can fit
into existing art-bible workflows without forcing a migration:

1. **File-per-character** — ``<root>/alice.yaml``,
   ``<root>/bob.json``, … Each file is a single sheet.
2. **Directory-per-character** — ``<root>/alice/`` containing the
   canonical reference images::

       <root>/alice/front.{png,jpg,webp}
       <root>/alice/three_quarter.{png,jpg,webp}
       <root>/alice/profile.{png,jpg,webp}
       <root>/alice/full_body.{png,jpg,webp}
       <root>/alice/style.{png,jpg,webp}
       <root>/alice/sheet.yaml      # optional metadata

Both layouts can coexist in the same root. YAML takes precedence
when both ``alice.yaml`` and ``alice/`` exist; the directory's
reference images are loaded as well so a "file-only" sheet can
still pick up references if the user dropped them next door.

Everything in this module is pure-Python; pyyaml is imported
lazily so a deployment that only uses the JSON layout doesn't
pay the cost.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from melosviz.character.sheet import (
    CHARACTER_IPADAPTER,
    CHARACTER_PULID,
    ENGINE_IPADAPTER,
    ENGINE_PULID,
    REFERENCE_SLOTS,
    CharacterRegistry,
    CharacterSheet,
)


# ---- Exceptions --------------------------------------------------------------

class CharacterIOError(IOError):
    """Raised when a character sheet / registry cannot be read or written.

    Subclasses :class:`IOError` so existing ``except IOError`` blocks in
    the orchestrator catch it without modification. Callers that want
    to distinguish character I/O errors from generic filesystem errors
    can ``except CharacterIOError`` directly.
    """


# ---- Module-level constants --------------------------------------------------

#: Image extensions accepted when scanning a directory-per-character layout.
#: Lowercase only — the scan lower-cases before comparing.
DEFAULT_IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")


# ---- YAML helper (lazy import) ----------------------------------------------

def _yaml() -> Any:
    """Import pyyaml on first use; raises ImportError with a friendly msg.

    Wrapped here so the rest of the module doesn't need to know whether
    pyyaml is installed. Returns the ``yaml`` module.
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise CharacterIOError(
            "PyYAML is required to read or write .yaml character sheets. "
            "Install with `pip install pyyaml`."
        ) from exc
    return yaml


# ---- Sheet-level I/O ---------------------------------------------------------

def _read_yaml(path: Path) -> dict[str, Any]:
    yaml = _yaml()
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise CharacterIOError(
            f"{path}: top-level YAML must be a mapping, got {type(loaded).__name__}"
        )
    return loaded


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise CharacterIOError(
            f"{path}: top-level JSON must be an object, got {type(loaded).__name__}"
        )
    return loaded


def _read_sheet_file(path: Path, root: Path) -> CharacterSheet:
    """Parse one sheet file (YAML or JSON) into a :class:`CharacterSheet`."""
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        data = _read_yaml(path)
    elif suffix == ".json":
        data = _read_json(path)
    else:
        raise CharacterIOError(
            f"{path}: unsupported sheet extension {suffix!r} "
            f"(expected .yaml, .yml, or .json)"
        )
    sheet = CharacterSheet.from_dict(data)
    # If the YAML omitted a name, fall back to the file stem. This makes
    # `viz character add` work when the user only fills in description /
    # style_prompt and saves as ``alice.yaml``.
    if not sheet.name:
        sheet.name = path.stem
    # Resolve reference paths relative to the source file.
    _resolve_reference_paths(sheet, source=path, root=root)
    return sheet


def _resolve_reference_paths(
    sheet: CharacterSheet, *, source: Path, root: Path
) -> None:
    """Make every ``references[slot]`` path absolute if it isn't already.

    Relative paths resolve against ``source.parent`` (the directory the
    sheet was loaded from), falling back to ``root`` for the directory-
    per-character layout where there is no sheet file. Already-absolute
    paths are left untouched.
    """
    base = source.parent if source.is_file() else source
    for slot in REFERENCE_SLOTS:
        path_str = sheet.references.get(slot) or ""
        if not path_str:
            continue
        p = Path(path_str)
        if p.is_absolute():
            continue
        resolved = (base / p).resolve()
        if not resolved.exists():
            # Don't raise here — a missing reference just means the
            # adapter will see an empty string. ``is_complete`` will
            # flip to False and the CLI can warn.
            continue
        sheet.references[slot] = str(resolved)


def _find_reference_image(
    char_dir: Path, slot: str, extensions: tuple[str, ...]
) -> Path | None:
    """Return the first existing image for ``slot`` in ``char_dir``.

    Walks the extension list in order so ``front.png`` wins over
    ``front.jpg`` if both exist (artist usually keeps the highest
    quality as the primary).
    """
    for ext in extensions:
        candidate = char_dir / f"{slot}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _scan_directory_layout(
    char_dir: Path, root: Path, extensions: tuple[str, ...]
) -> CharacterSheet:
    """Build a :class:`CharacterSheet` from a directory-per-character layout.

    Pulls reference images by canonical slot name and loads any
    ``sheet.yaml`` / ``sheet.json`` next to them for metadata. A
    bare directory with only images still works — every other
    field falls back to the dataclass default.
    """
    sheet = CharacterSheet(name=char_dir.name)
    sheet.engine = ENGINE_IPADAPTER  # default

    # Metadata file (optional). Try yaml first, then json.
    for meta_name in ("sheet.yaml", "sheet.yml", "sheet.json"):
        meta_path = char_dir / meta_name
        if not meta_path.is_file():
            continue
        meta_sheet = _read_sheet_file(meta_path, root=root)
        # Directory name wins as the canonical name; other fields
        # merge in unless the metadata file explicitly set them.
        sheet.description = meta_sheet.description or sheet.description
        sheet.style_prompt = meta_sheet.style_prompt or sheet.style_prompt
        sheet.negative_prompt = meta_sheet.negative_prompt or sheet.negative_prompt
        sheet.engine = meta_sheet.engine or sheet.engine
        sheet.metadata = {**meta_sheet.metadata, **sheet.metadata}
        break

    # Reference images by canonical slot.
    for slot in REFERENCE_SLOTS:
        img = _find_reference_image(char_dir, slot, extensions)
        if img is not None:
            sheet.references[slot] = str(img.resolve())

    # Source-root bookkeeping so the orchestrator can relativise paths
    # back to the user later.
    sheet.metadata.setdefault("source_dir", str(char_dir.resolve()))
    return sheet


# ---- Public API --------------------------------------------------------------

def load_registry(
    root: str | Path,
    *,
    extensions: tuple[str, ...] = DEFAULT_IMAGE_EXTENSIONS,
) -> CharacterRegistry:
    """Scan a root directory for character sheets and return a registry.

    Accepts both the file-per-character and directory-per-character
    layouts described at the top of this module. Missing root is
    treated as "no characters" and returns an empty registry — that
    keeps the orchestrator's bootstrap flow simple: ``load_registry(
    args.character_root or "")`` always succeeds.

    Raises :class:`CharacterIOError` for individual files that are
    present but unreadable (so a single bad YAML doesn't silently
    disappear), but does *not* raise for missing optional slots or
    empty directories.
    """
    root_path = Path(root).expanduser() if root else None
    registry = CharacterRegistry(source_root=str(root_path) if root_path else "")

    if root_path is None or not root_path.exists() or not root_path.is_dir():
        return registry

    # Pass 1: file-per-character sheets. Track which basenames we've seen
    # so we don't double-load when both ``alice.yaml`` and ``alice/`` exist.
    seen_names: set[str] = set()
    for entry in sorted(root_path.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in (".yaml", ".yml", ".json"):
            continue
        if entry.stem.startswith("."):
            continue  # skip dotfiles / hidden config
        try:
            sheet = _read_sheet_file(entry, root=root_path)
        except CharacterIOError:
            raise  # surface parse errors loudly
        except Exception as exc:  # pragma: no cover - defensive
            raise CharacterIOError(f"{entry}: failed to read sheet: {exc}") from exc
        registry.add(sheet)
        seen_names.add(entry.stem)

    # Pass 2: directory-per-character layouts.
    for entry in sorted(root_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name in seen_names:
            # Already loaded as a file — but still augment its references
            # from the directory's images, in case the YAML omitted them.
            existing = registry.get(entry.name)
            if existing is not None:
                _augment_references_from_dir(
                    existing, char_dir=entry, extensions=extensions
                )
                continue
        # Bare directory: synthesize a sheet from the images.
        sheet = _scan_directory_layout(
            entry, root=root_path, extensions=extensions
        )
        if sheet.is_complete or any(sheet.references.values()):
            registry.add(sheet)

    return registry


def _augment_references_from_dir(
    sheet: CharacterSheet, *, char_dir: Path, extensions: tuple[str, ...]
) -> None:
    """Fill in any missing reference slots on ``sheet`` from ``char_dir``."""
    for slot in REFERENCE_SLOTS:
        if sheet.references.get(slot):
            continue
        img = _find_reference_image(char_dir, slot, extensions)
        if img is not None:
            sheet.references[slot] = str(img.resolve())


def save_sheet(
    sheet: CharacterSheet,
    root: str | Path,
    *,
    fmt: str = "yaml",
    overwrite: bool = False,
) -> Path:
    """Persist a single sheet to ``root/<name>.<ext>``.

    ``fmt`` may be ``"yaml"`` (default), ``"yml"``, or ``"json"``.
    The directory is created if it doesn't exist. The returned path
    is the absolute, resolved location of the written file.

    Raises :class:`CharacterIOError` if a sheet with the same name
    already exists and ``overwrite=False``.
    """
    if not sheet.name:
        raise CharacterIOError("CharacterSheet.name is required to save a sheet")
    fmt = fmt.lower().lstrip(".")
    if fmt not in ("yaml", "yml", "json"):
        raise CharacterIOError(
            f"unsupported format {fmt!r} (expected yaml, yml, or json)"
        )

    root_path = Path(root).expanduser()
    root_path.mkdir(parents=True, exist_ok=True)

    target = root_path / f"{sheet.name}.{fmt}"
    if target.exists() and not overwrite:
        raise CharacterIOError(
            f"{target}: file already exists (pass overwrite=True to replace)"
        )

    data = sheet.to_dict()
    if fmt in ("yaml", "yml"):
        yaml = _yaml()
        with target.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    else:
        with target.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return target.resolve()


def save_registry(
    registry: CharacterRegistry,
    root: str | Path,
    *,
    fmt: str = "yaml",
    overwrite: bool = False,
) -> list[Path]:
    """Persist every sheet in ``registry`` under ``root``.

    Convenience wrapper around :func:`save_sheet`. Returns the list
    of written paths in registry order. Existing files are skipped
    unless ``overwrite=True`` — a single bad write aborts the loop
    and leaves earlier files on disk.
    """
    written: list[Path] = []
    for sheet in registry:
        written.append(
            save_sheet(sheet, root, fmt=fmt, overwrite=overwrite)
        )
    return written


# ---- Engine helpers ----------------------------------------------------------

#: Map of engine identifier → workflow JSON stem. Mirrors
#: ``melosviz.render.comfyui_adapter.DEFAULT_WORKFLOWS`` but lives here so
#: the CLI / orchestrator can resolve a character to a workflow without
#: importing the adapter (which depends on optional ComfyUI client libs).
ENGINE_WORKFLOWS: dict[str, str] = {
    ENGINE_IPADAPTER: CHARACTER_IPADAPTER,
    ENGINE_PULID: CHARACTER_PULID,
}


def workflow_for_engine(engine: str) -> str:
    """Return the ComfyUI workflow stem for ``engine``.

    Falls back to IP-Adapter when the engine is unrecognised —
    same conservative default as :attr:`CharacterSheet.engine_workflow`.
    """
    return ENGINE_WORKFLOWS.get(engine, CHARACTER_IPADAPTER)