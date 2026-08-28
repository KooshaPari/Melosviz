"""Tests for the comfyui_adapter character-consistency routing (WBS-101..106)."""

from __future__ import annotations


def test_resolve_workflow_routes_to_ipadapter_for_ipadapter_engine():
    from melosviz.render.comfyui_adapter import _resolve_workflow_for_scene

    reg = {"alice": {"engine": "ipadapter"}}
    scene = {"character": "alice", "prompt": "portrait of alice"}

    assert _resolve_workflow_for_scene(scene, registry=reg) == "ipadapter_character"


def test_resolve_workflow_routes_to_pulid_for_pulid_engine():
    from melosviz.render.comfyui_adapter import _resolve_workflow_for_scene

    reg = {"bob": {"engine": "pulid"}}
    scene = {"character": "bob", "prompt": "bob walking"}

    assert _resolve_workflow_for_scene(scene, registry=reg) == "pulid_character"


def test_resolve_workflow_passes_through_explicit_scene_type():
    from melosviz.render.comfyui_adapter import _resolve_workflow_for_scene

    reg = {"alice": {"engine": "ipadapter"}}
    # Even with a character registered, an explicit scene_type wins.
    scene = {
        "character": "alice",
        "scene_type": "ipadapter_character",
        "prompt": "x",
    }
    assert _resolve_workflow_for_scene(scene, registry=reg) == "ipadapter_character"

    scene_pulid = {"character": "alice", "scene_type": "pulid_character"}
    assert _resolve_workflow_for_scene(scene_pulid, registry=reg) == "pulid_character"


def test_stamp_character_fields_copies_refs_and_metadata_onto_scene():
    from melosviz.render.comfyui_adapter import _stamp_character_fields

    sheet = {
        "name": "alice",
        "engine": "ipadapter",
        "references": {
            "front": "/tmp/alice_front.png",
            "three_quarter": "/tmp/alice_3q.png",
            "style": "/tmp/style.png",
        },
        "metadata": {"face_weight": 0.85, "style_weight": 0.4},
    }
    reg = {"alice": sheet}
    scene = {"character": "alice", "prompt": "alice dancing"}

    stamped = _stamp_character_fields(scene, registry=reg)
    assert stamped["character_front"] == "/tmp/alice_front.png"
    assert stamped["character_three_quarter"] == "/tmp/alice_3q.png"
    assert stamped["character_style_ref"] == "/tmp/style.png"
    assert stamped["character_face_weight"] == "0.85"
    assert stamped["character_style_weight"] == "0.4"
    assert stamped["character_engine"] == "ipadapter"

    # The original scene must not be mutated (downstream code may reuse it).
    assert "character_front" not in scene
