"""Tests for melosviz.character.registry_io — load_registry + save_sheet IO."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_images(root: Path, slot_to_name: dict[str, str]) -> None:
    """Write minimal fake image files at ``root/<name>_<slot>.png``.

    This matches the optional ``<name>_<slot>.png`` shorthand the CLI's
    ``--reference``-style flow expects; the registry IO also accepts
    directory layouts with arbitrary names, so this is just one of the
    supported shapes.
    """
    for slot, name in slot_to_name.items():
        (root / f"{name}_{slot}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")


def test_load_registry_picks_up_file_per_character_yaml(tmp_path: Path):
    """A single .yaml sheet at <root>/<name>.yaml becomes a registry entry."""
    from melosviz.character.registry_io import load_registry
    from melosviz.character.sheet import CharacterSheet

    sheet = CharacterSheet(
        name="alice",
        description="lead dancer",
        engine="ipadapter",
        references={"front": str(tmp_path / "alice_front.png")},
    )
    yaml_path = tmp_path / "alice.yaml"
    # Render the sheet to YAML the same way save_sheet does, then validate
    # that load_registry can read it back. We rely on PyYAML, which we
    # already verified is available in the environment.
    import yaml

    yaml_path.write_text(yaml.safe_dump(sheet.to_dict(), sort_keys=False))

    reg = load_registry(tmp_path)
    assert "alice" in reg.names()
    alice = reg.get("alice")
    assert alice.description == "lead dancer"
    assert alice.engine == "ipadapter"
    assert alice.references["front"].endswith("alice_front.png")


def test_load_registry_picks_up_directory_per_character(tmp_path: Path):
    """``<root>/<name>/{front,three_quarter,profile,...}.{png,jpg,webp}`` works."""
    from melosviz.character.registry_io import load_registry

    char_dir = tmp_path / "bob"
    char_dir.mkdir()
    for slot in ("front", "three_quarter", "profile"):
        (char_dir / f"{slot}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")

    reg = load_registry(tmp_path)
    assert "bob" in reg.names()
    bob = reg.get("bob")
    assert bob.references["front"].endswith("bob/front.png")
    assert bob.references["three_quarter"].endswith("bob/three_quarter.png")
    assert bob.references["profile"].endswith("bob/profile.png")


def test_save_sheet_writes_yaml_or_json(tmp_path: Path):
    """save_sheet() picks YAML when available, falls back to JSON."""
    from melosviz.character.registry_io import save_sheet
    from melosviz.character.sheet import CharacterSheet

    sheet = CharacterSheet(
        name="charlie",
        description="drummer",
        engine="pulid",
        references={"front": str(tmp_path / "charlie_front.png")},
    )
    out_path = save_sheet(sheet, tmp_path)
    assert out_path.exists()
    text = out_path.read_text()
    # Either YAML or JSON extension is fine; we accept whichever the
    # environment provides.
    assert out_path.suffix in {".yaml", ".yml", ".json"}
    # And the content can be parsed back.
    if out_path.suffix in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    assert data["name"] == "charlie"
    assert data["engine"] == "pulid"


def test_load_registry_raises_character_io_error_for_malformed_sheet(tmp_path: Path):
    """A present-but-broken sheet raises CharacterIOError loudly (no silent skip).

    The registry treats ``broken.json`` as a hard error instead of papering
    over the parse failure; this is what operators usually want, since
    silent skipping makes directory typos invisible.
    """
    from melosviz.character.registry_io import (
        CharacterIOError,
        load_registry,
    )

    (tmp_path / "broken.json").write_text("{ this is not valid json")
    with pytest.raises(CharacterIOError):
        load_registry(tmp_path)
