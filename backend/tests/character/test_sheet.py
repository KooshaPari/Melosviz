"""Tests for melosviz.character.sheet — CharacterSheet + CharacterRegistry."""

from __future__ import annotations


def test_character_sheet_round_trip_through_to_from_dict():
    """CharacterSheet.to_dict() → from_dict() preserves every public field."""
    from melosviz.character.sheet import CharacterSheet

    sheet = CharacterSheet(
        name="alice",
        description="lead dancer",
        engine="pulid",
        style_prompt="silk gown, soft chiaroscuro",
        references={
            "front": "/tmp/refs/alice_front.png",
            "three_quarter": "/tmp/refs/alice_3q.png",
            "profile": "/tmp/refs/alice_prof.png",
            "full_body": "/tmp/refs/alice_full.png",
            "style": "/tmp/refs/style.png",
        },
        metadata={"face_weight": 0.85, "style_weight": 0.6, "tags": ["lead", "human"]},
    )
    payload = sheet.to_dict()
    assert payload["name"] == "alice"
    assert payload["engine"] == "pulid"
    assert payload["references"]["front"] == "/tmp/refs/alice_front.png"
    assert payload["metadata"]["face_weight"] == 0.85

    rebuilt = CharacterSheet.from_dict(payload)
    assert rebuilt.name == "alice"
    assert rebuilt.engine == "pulid"
    assert rebuilt.references["front"] == "/tmp/refs/alice_front.png"
    assert rebuilt.metadata["face_weight"] == 0.85
    # Defaults are preserved through round-trip
    assert rebuilt.is_complete is True


def test_character_sheet_is_complete_requires_at_least_one_reference():
    """A CharacterSheet without any reference image is not render-ready."""
    from melosviz.character.sheet import CharacterSheet

    bare = CharacterSheet(name="bob")
    assert bare.is_complete is False
    assert bare.engine == "ipadapter"  # default engine

    # Adding a single front reference flips is_complete.
    bare.references["front"] = "/tmp/bob_front.png"
    assert bare.is_complete is True


def test_character_registry_add_get_and_names_behave_like_a_dict():
    """CharacterRegistry uses name as the dedupe key and exposes names() / get()."""
    import pytest

    from melosviz.character.sheet import CharacterRegistry, CharacterSheet

    reg = CharacterRegistry()
    assert reg.names() == []
    assert reg.get("ghost") is None

    alice = CharacterSheet(name="alice", description="lead")
    bob = CharacterSheet(name="bob", description="villain")
    reg.add(alice)
    reg.add(bob)
    assert sorted(reg.names()) == ["alice", "bob"]
    assert reg.get("alice").description == "lead"
    assert reg.get("bob").description == "villain"

    # Adding the same name without overwrite raises — the renderer must
    # ask explicitly to replace, since an unexpected shadow is usually a
    # typo in a character name and we don't want to silently shadow the
    # original sheet on disk.
    alice_v2 = CharacterSheet(name="alice", description="lead v2")
    with pytest.raises(ValueError):
        reg.add(alice_v2)

    # overwrite=True swaps the entry.
    reg.add(alice_v2, overwrite=True)
    assert reg.get("alice").description == "lead v2"
    assert sorted(reg.names()) == ["alice", "bob"]

    # An empty name is rejected outright.
    with pytest.raises(ValueError):
        reg.add(CharacterSheet(name=""))

    # to_list() is what the CLI prints.
    listing = reg.to_list()
    assert isinstance(listing, list)
    assert {entry["name"] for entry in listing} == {"alice", "bob"}
