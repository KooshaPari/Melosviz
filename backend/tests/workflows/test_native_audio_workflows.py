"""Tests for the new native-audio ComfyUI workflow JSONs.

WBS-107: Wan 2.1 S2V — verifies the audio-conditioned latent node replaces
the empty-latent node from ``wan_video.json``.

WBS-108: Seedance A2V — verifies the topology is the canonical three-node
chain (LoadAudio → SeedanceA2VSampler → VHS_VideoCombine).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "workflows"


def _load(name: str) -> dict:
    return json.loads((WORKFLOWS_DIR / name).read_text())


def test_wan_s2v_audio_replaces_latent_node() -> None:
    """wan_s2v_audio.json must use the audio-conditioned latent node."""
    wf = _load("wan_s2v_audio.json")
    class_types = {node["class_type"] for node in wf.values()}
    # New audio-conditioned latent node is present
    assert "WanVideoAudioConditionedLatent" in class_types
    # The old empty-latent node is gone
    assert "WanVideoEmptyLatent" not in class_types
    # The WanVideoSampler → WanVideoDecode → VHS_VideoCombine chain is intact
    assert "WanVideoSampler" in class_types
    assert "WanVideoDecode" in class_types
    assert "VHS_VideoCombine" in class_types
    # The audio latent node wires into the sampler's latent_image input
    latent_node = next(
        node for node in wf.values()
        if node["class_type"] == "WanVideoAudioConditionedLatent"
    )
    assert latent_node["inputs"]["audio_path"] == "{audio_path}"


def test_seedance_a2v_has_canonical_three_node_topology() -> None:
    """seedance_a2v.json must be exactly LoadAudio → SeedanceA2VSampler → VHS_VideoCombine."""
    wf = _load("seedance_a2v.json")
    class_types = {node["class_type"] for node in wf.values()}
    assert class_types == {"LoadAudio", "SeedanceA2VSampler", "VHS_VideoCombine"}
    # The sampler must receive audio and motion_strength
    sampler = next(
        node for node in wf.values()
        if node["class_type"] == "SeedanceA2VSampler"
    )
    assert "audio" in sampler["inputs"]
    assert "motion_strength" in sampler["inputs"]
    assert "audio_influence" in sampler["inputs"]
    assert sampler["inputs"]["prompt"] == "{prompt}"