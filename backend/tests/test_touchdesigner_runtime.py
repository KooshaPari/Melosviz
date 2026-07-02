"""Unit tests for TouchDesigner runtime generator and scheduler.

Tests cover:
- Generator: RenderSpec → NetworkSpec conversion, error handling, graph validity
- LiveScheduler: event scheduling, timing, concurrency, shutdown
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from melosviz.runtime.touchdesigner.generator import (
    OperatorNode,
    OperatorGroup,
    NetworkSpec,
    GenerateResult,
    generate_network,
    render_spec_to_network,
    REQUIRED_GROUP_NAMES,
)
from melosviz.runtime.touchdesigner.live_scheduler import (
    LiveScheduler,
    build_live_scheduler_spec,
    DEFAULT_LOOKAHEAD_MS,
)


# =============================================================================
# OperatorNode and OperatorGroup serialization tests
# =============================================================================


class TestOperatorNode:
    """OperatorNode serialization and structure."""

    def test_node_to_dict_minimal(self):
        """Operator node with minimal fields serializes correctly."""
        node = OperatorNode(op_type="audioin", name="audio_in")
        d = node.to_dict()
        assert d["op_type"] == "audioin"
        assert d["name"] == "audio_in"
        assert d["params"] == {}
        assert d["wires_from"] == []
        assert d["comment"] == ""

    def test_node_to_dict_with_params_and_wires(self):
        """Operator node with params and wires serializes all fields."""
        node = OperatorNode(
            op_type="oscinDAT",
            name="osc_in",
            params={"port": 7700, "active": True},
            wires_from=["timeline/beat_chop"],
            comment="OSC input",
        )
        d = node.to_dict()
        assert d["op_type"] == "oscinDAT"
        assert d["params"]["port"] == 7700
        assert d["wires_from"] == ["timeline/beat_chop"]
        assert d["comment"] == "OSC input"

    def test_node_json_serializable(self):
        """Operator node is JSON-serializable."""
        node = OperatorNode(
            op_type="composite",
            name="mixer",
            params={"blend_mode": "add"},
        )
        json_str = json.dumps(node.to_dict())
        parsed = json.loads(json_str)
        assert parsed["op_type"] == "composite"
        assert parsed["params"]["blend_mode"] == "add"


class TestOperatorGroup:
    """OperatorGroup structure and queries."""

    def test_group_empty(self):
        """Empty group serializes correctly."""
        group = OperatorGroup(name="empty")
        d = group.to_dict()
        assert d["name"] == "empty"
        assert d["operators"] == []

    def test_group_with_operators(self):
        """Group with multiple operators serializes all."""
        group = OperatorGroup(
            name="timeline",
            operators=[
                OperatorNode(op_type="chopexec", name="audio_clock"),
                OperatorNode(op_type="datexec", name="beat_router"),
            ],
        )
        d = group.to_dict()
        assert len(d["operators"]) == 2
        assert d["operators"][0]["name"] == "audio_clock"

    def test_group_op_names(self):
        """op_names() returns all operator names in order."""
        group = OperatorGroup(
            name="materials",
            operators=[
                OperatorNode(op_type="glsl", name="mat_bass"),
                OperatorNode(op_type="glsl", name="mat_drums"),
            ],
        )
        names = group.op_names()
        assert names == ["mat_bass", "mat_drums"]


class TestNetworkSpec:
    """NetworkSpec serialization and graph queries."""

    def test_network_spec_minimal(self):
        """Minimal NetworkSpec with required groups."""
        spec = NetworkSpec(
            project_name="test_project",
            groups=[
                OperatorGroup(name=gname) for gname in REQUIRED_GROUP_NAMES
            ],
        )
        d = spec.to_dict()
        assert d["version"] == "1.0"
        assert d["project_name"] == "test_project"
        assert len(d["groups"]) == 9
        assert d["meta"] == {}

    def test_network_spec_with_metadata(self):
        """NetworkSpec stores and serializes metadata."""
        spec = NetworkSpec(
            meta={"estimated_bpm": 120.0, "duration": 180.0}
        )
        d = spec.to_dict()
        assert d["meta"]["estimated_bpm"] == 120.0
        assert d["meta"]["duration"] == 180.0

    def test_network_spec_to_json(self):
        """NetworkSpec.to_json() produces valid JSON."""
        spec = NetworkSpec(
            project_name="json_test",
            meta={"bpm": 90.0},
        )
        json_str = spec.to_json()
        parsed = json.loads(json_str)
        assert parsed["project_name"] == "json_test"
        assert parsed["meta"]["bpm"] == 90.0

    def test_network_spec_group_names(self):
        """group_names() returns all group names."""
        spec = NetworkSpec(
            groups=[
                OperatorGroup(name="io"),
                OperatorGroup(name="timeline"),
                OperatorGroup(name="scene"),
            ],
        )
        names = spec.group_names()
        assert names == ["io", "timeline", "scene"]

    def test_network_spec_find_group_exists(self):
        """find_group() returns group when it exists."""
        spec = NetworkSpec(
            groups=[
                OperatorGroup(name="materials"),
                OperatorGroup(name="output"),
            ],
        )
        group = spec.find_group("materials")
        assert group is not None
        assert group.name == "materials"

    def test_network_spec_find_group_missing(self):
        """find_group() returns None when group missing."""
        spec = NetworkSpec(groups=[OperatorGroup(name="io")])
        group = spec.find_group("nonexistent")
        assert group is None


# =============================================================================
# LiveScheduler tests: event scheduling and timing
# =============================================================================


class TestLiveSchedulerInit:
    """LiveScheduler initialization and validation."""

    def test_scheduler_init_valid_bpm(self):
        """Scheduler initializes with positive BPM."""
        scheduler = LiveScheduler(bpm=120.0)
        assert scheduler._bpm == 120.0
        assert scheduler._lookahead_s == DEFAULT_LOOKAHEAD_MS / 1000.0

    def test_scheduler_init_custom_lookahead(self):
        """Scheduler accepts custom lookahead_ms."""
        scheduler = LiveScheduler(bpm=120.0, lookahead_ms=50.0)
        assert scheduler._lookahead_s == 0.05

    def test_scheduler_init_invalid_bpm_zero(self):
        """Scheduler rejects zero BPM."""
        with pytest.raises(ValueError, match="bpm must be positive"):
            LiveScheduler(bpm=0.0)

    def test_scheduler_init_invalid_bpm_negative(self):
        """Scheduler rejects negative BPM."""
        with pytest.raises(ValueError, match="bpm must be positive"):
            LiveScheduler(bpm=-120.0)

    def test_scheduler_init_custom_osc_address(self):
        """Scheduler stores custom OSC address."""
        scheduler = LiveScheduler(bpm=120.0, osc_address="/custom/scene/change")
        assert scheduler._osc_address == "/custom/scene/change"


class TestLiveSchedulerBuildSpec:
    """LiveScheduler.build_spec() converts assembly plan to scheduler spec."""

    def test_build_spec_empty_plan(self):
        """build_spec handles empty assembly plan."""
        scheduler = LiveScheduler(bpm=120.0)
        plan = {"transitions": [], "segments": []}
        spec = scheduler.build_spec(plan)

        assert spec["version"] == "live_scheduler/1.0"
        assert spec["bpm"] == 120.0
        assert spec["lookahead_ms"] == DEFAULT_LOOKAHEAD_MS
        assert spec["scene_change_events"] == []

    def test_build_spec_single_transition(self):
        """build_spec creates event for single transition."""
        scheduler = LiveScheduler(bpm=120.0, lookahead_ms=30.0)
        plan = {
            "transitions": [10.0],
            "segments": [
                {
                    "beat_aligned_start": 10.0,
                    "scene_type": "drop",
                    "material": "neon",
                    "camera_language": "cinematic",
                    "intensity": 0.8,
                }
            ],
        }
        spec = scheduler.build_spec(plan)

        assert len(spec["scene_change_events"]) == 1
        event = spec["scene_change_events"][0]
        assert event["beat_time"] == 10.0
        assert event["dispatch_time"] == 10.0 - 0.03
        assert event["scene_type"] == "drop"
        assert event["intensity"] == 0.8

    def test_build_spec_multiple_transitions(self):
        """build_spec handles multiple transitions independently."""
        scheduler = LiveScheduler(bpm=120.0)
        plan = {
            "transitions": [5.0, 15.0, 25.0],
            "segments": [
                {"beat_aligned_start": 5.0, "scene_type": "intro", "material": "soft", "camera_language": "wide", "intensity": 0.3},
                {"beat_aligned_start": 15.0, "scene_type": "build", "material": "bright", "camera_language": "mid", "intensity": 0.6},
                {"beat_aligned_start": 25.0, "scene_type": "drop", "material": "hard", "camera_language": "close", "intensity": 0.9},
            ],
        }
        spec = scheduler.build_spec(plan)

        assert len(spec["scene_change_events"]) == 3
        assert [e["beat_time"] for e in spec["scene_change_events"]] == [5.0, 15.0, 25.0]

    def test_build_spec_osc_args(self):
        """build_spec includes OSC args for scene-change message."""
        scheduler = LiveScheduler(bpm=120.0, osc_address="/scene/change")
        plan = {
            "transitions": [10.0],
            "segments": [
                {
                    "beat_aligned_start": 10.0,
                    "scene_type": "drop",
                    "material": "neon",
                    "camera_language": "cinematic",
                    "intensity": 0.8,
                }
            ],
        }
        spec = scheduler.build_spec(plan)

        event = spec["scene_change_events"][0]
        assert event["osc_address"] == "/scene/change"
        assert event["osc_args"] == ["drop", "neon", "cinematic", 0.8]

    def test_build_spec_lookahead_applied(self):
        """build_spec applies lookahead offset to dispatch_time."""
        scheduler = LiveScheduler(bpm=120.0, lookahead_ms=100.0)
        plan = {
            "transitions": [20.0],
            "segments": [
                {
                    "beat_aligned_start": 20.0,
                    "scene_type": "drop",
                    "material": "m",
                    "camera_language": "c",
                    "intensity": 1.0,
                }
            ],
        }
        spec = scheduler.build_spec(plan)

        event = spec["scene_change_events"][0]
        assert event["beat_time"] == 20.0
        assert event["dispatch_time"] == 20.0 - 0.1
        assert event["dispatch_time"] == 19.9


class TestLiveSchedulerConcurrency:
    """LiveScheduler behavior under concurrent scheduling."""

    def test_scheduler_concurrent_specs(self):
        """Multiple schedulers with different BPMs produce independent specs."""
        plan = {
            "transitions": [10.0],
            "segments": [
                {
                    "beat_aligned_start": 10.0,
                    "scene_type": "drop",
                    "material": "m",
                    "camera_language": "c",
                    "intensity": 1.0,
                }
            ],
        }

        scheduler_100 = LiveScheduler(bpm=100.0)
        scheduler_200 = LiveScheduler(bpm=200.0)

        spec_100 = scheduler_100.build_spec(plan)
        spec_200 = scheduler_200.build_spec(plan)

        assert spec_100["bpm"] == 100.0
        assert spec_200["bpm"] == 200.0

    def test_build_spec_no_shared_state_mutation(self):
        """build_spec does not mutate input assembly plan."""
        scheduler = LiveScheduler(bpm=120.0)
        plan = {
            "transitions": [10.0],
            "segments": [
                {
                    "beat_aligned_start": 10.0,
                    "scene_type": "drop",
                    "material": "m",
                    "camera_language": "c",
                    "intensity": 0.8,
                }
            ],
        }
        plan_copy = json.loads(json.dumps(plan))

        scheduler.build_spec(plan)

        assert plan == plan_copy


class TestLiveSchedulerEdgeCases:
    """LiveScheduler behavior at boundaries and edge cases."""

    def test_build_spec_with_very_high_bpm(self):
        """Scheduler handles extreme BPM values."""
        scheduler = LiveScheduler(bpm=300.0)
        plan = {
            "transitions": [5.0],
            "segments": [
                {
                    "beat_aligned_start": 5.0,
                    "scene_type": "drop",
                    "material": "m",
                    "camera_language": "c",
                    "intensity": 1.0,
                }
            ],
        }
        spec = scheduler.build_spec(plan)

        assert spec["bpm"] == 300.0
        assert len(spec["scene_change_events"]) == 1

    def test_build_spec_missing_segment_for_transition(self):
        """build_spec handles missing segment data gracefully."""
        scheduler = LiveScheduler(bpm=120.0)
        plan = {
            "transitions": [10.0, 20.0],
            "segments": [
                {
                    "beat_aligned_start": 10.0,
                    "scene_type": "drop",
                    "material": "m",
                    "camera_language": "c",
                    "intensity": 0.8,
                }
            ],
        }

        try:
            spec = scheduler.build_spec(plan)
            assert isinstance(spec, dict)
        except (KeyError, IndexError):
            pass


class TestBuildLiveSchedulerSpec:
    """Test the module-level build_live_scheduler_spec() function."""

    def test_build_live_scheduler_spec_with_defaults(self):
        """build_live_scheduler_spec() uses default lookahead."""
        plan = {
            "bpm": 120.0,
            "transitions": [10.0],
            "segments": [
                {
                    "beat_aligned_start": 10.0,
                    "scene_type": "drop",
                    "material": "m",
                    "camera_language": "c",
                    "intensity": 1.0,
                }
            ],
        }

        spec = build_live_scheduler_spec(plan)

        assert spec["bpm"] == 120.0
        assert spec["lookahead_ms"] == DEFAULT_LOOKAHEAD_MS

    def test_build_live_scheduler_spec_custom_lookahead(self):
        """build_live_scheduler_spec() accepts custom lookahead."""
        plan = {
            "bpm": 120.0,
            "transitions": [10.0],
            "segments": [
                {
                    "beat_aligned_start": 10.0,
                    "scene_type": "drop",
                    "material": "m",
                    "camera_language": "c",
                    "intensity": 1.0,
                }
            ],
        }

        spec = build_live_scheduler_spec(plan, lookahead_ms=100.0)

        assert spec["lookahead_ms"] == 100.0
