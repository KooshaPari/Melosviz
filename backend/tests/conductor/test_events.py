"""Tests for the render event bus + orchestrator event emission."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from melosviz.conductor.events import (
    ALL_STATES,
    RenderEvent,
    RenderEventBus,
    STATE_DONE,
    STATE_ERROR,
    STATE_QUEUED,
    STATE_RENDERING,
    STATE_SKIPPED,
    get_bus,
    reset_bus,
)


# --- RenderEventBus ----------------------------------------------------------


def test_emit_returns_event_with_state() -> None:
    bus = RenderEventBus()
    evt = bus.emit(
        job_id="j1",
        scene_index=0,
        scene_name="intro",
        scene_type="comfyui_image",
        state=STATE_QUEUED,
    )
    assert isinstance(evt, RenderEvent)
    assert evt.job_id == "j1"
    assert evt.scene_index == 0
    assert evt.scene_name == "intro"
    assert evt.state == STATE_QUEUED
    assert evt.timestamp > 0


def test_emit_rejects_unknown_state() -> None:
    bus = RenderEventBus()
    with pytest.raises(ValueError, match="unknown render state"):
        bus.emit(
            job_id="j1",
            scene_index=0,
            scene_name="intro",
            scene_type="comfyui_image",
            state="not_a_real_state",
        )


def test_recent_returns_buffered_events_in_order() -> None:
    bus = RenderEventBus()
    bus.emit_queued(job_id="j", scene_index=0, scene_name="s0", scene_type="comfyui_image")
    bus.emit_rendering(job_id="j", scene_index=0, scene_name="s0", scene_type="comfyui_image")
    bus.emit_done(job_id="j", scene_index=0, scene_name="s0", scene_type="comfyui_image")
    events = bus.recent()
    assert [e.state for e in events] == [STATE_QUEUED, STATE_RENDERING, STATE_DONE]


def test_recent_respects_max_events() -> None:
    bus = RenderEventBus(buffer_size=2)
    bus.emit_queued(job_id="j", scene_index=0, scene_name="s0", scene_type="x")
    bus.emit_queued(job_id="j", scene_index=1, scene_name="s1", scene_type="x")
    bus.emit_queued(job_id="j", scene_index=2, scene_name="s2", scene_type="x")
    events = bus.recent()
    assert len(events) == 2
    assert [e.scene_index for e in events] == [1, 2]


def test_recent_respects_since_ms() -> None:
    bus = RenderEventBus()
    bus.emit_queued(job_id="j", scene_index=0, scene_name="s0", scene_type="x")
    time.sleep(0.05)
    cutoff = time.time() * 1000.0
    time.sleep(0.02)
    bus.emit_rendering(job_id="j", scene_index=1, scene_name="s1", scene_type="x")
    events = bus.recent(since_ms=cutoff)
    assert [e.state for e in events] == [STATE_RENDERING]


def test_subscribe_receives_new_events() -> None:
    bus = RenderEventBus()
    received: list[RenderEvent] = []
    unsub = bus.subscribe(received.append)
    try:
        bus.emit_queued(job_id="j", scene_index=0, scene_name="s0", scene_type="x")
        bus.emit_done(job_id="j", scene_index=0, scene_name="s0", scene_type="x")
        assert [e.state for e in received] == [STATE_QUEUED, STATE_DONE]
    finally:
        unsub()


def test_subscribe_can_be_undone() -> None:
    bus = RenderEventBus()
    received: list[RenderEvent] = []
    unsub = bus.subscribe(received.append)
    bus.emit_queued(job_id="j", scene_index=0, scene_name="s0", scene_type="x")
    assert len(received) == 1
    unsub()
    bus.emit_done(job_id="j", scene_index=0, scene_name="s0", scene_type="x")
    assert len(received) == 1  # no new events after unsubscribe


def test_subscriber_exceptions_do_not_break_the_bus() -> None:
    bus = RenderEventBus()

    def bad(_evt: RenderEvent) -> None:
        raise RuntimeError("subscriber bug")

    bus.subscribe(bad)
    # Must not raise even though the subscriber raised.
    bus.emit_queued(job_id="j", scene_index=0, scene_name="s0", scene_type="x")


def test_renderEvent_to_sse_format() -> None:
    evt = RenderEvent(
        job_id="abc",
        scene_index=2,
        scene_name="verse1",
        scene_type="comfyui_video",
        state=STATE_RENDERING,
        backend="melosviz.render.comfyui_adapter.ComfyUIAdapter",
        progress=0.42,
    )
    sse = evt.to_sse()
    assert sse.startswith("event: render\n")
    assert sse.endswith("\n\n")
    # The payload must be a single-line JSON object parseable by JS clients.
    body = sse.split("data: ", 1)[1].split("\n\n", 1)[0]
    parsed = json.loads(body)
    assert parsed["job_id"] == "abc"
    assert parsed["scene_index"] == 2
    assert parsed["state"] == STATE_RENDERING
    assert parsed["progress"] == 0.42


def test_to_dict_round_trips() -> None:
    evt = RenderEvent(
        job_id="j",
        scene_index=0,
        scene_name="s",
        scene_type="comfyui_image",
        state=STATE_DONE,
        duration_ms=1234.5,
        artifact_path="/tmp/out.png",
    )
    d = evt.to_dict()
    assert d["duration_ms"] == 1234.5
    assert d["artifact_path"] == "/tmp/out.png"
    rebuilt = RenderEvent(**{k: v for k, v in d.items() if k != "ts_ms"})
    assert rebuilt.state == STATE_DONE


def test_get_bus_returns_singleton() -> None:
    reset_bus()
    a = get_bus()
    b = get_bus()
    assert a is b


def test_all_states_constant_includes_every_state() -> None:
    assert STATE_QUEUED in ALL_STATES
    assert STATE_RENDERING in ALL_STATES
    assert STATE_DONE in ALL_STATES
    assert STATE_ERROR in ALL_STATES
    assert STATE_SKIPPED in ALL_STATES


# --- Stream (polling) iterator -----------------------------------------------


def test_stream_yields_emitted_events() -> None:
    bus = RenderEventBus()
    emitted: list[RenderEvent] = []

    def stopper() -> None:
        time.sleep(0.5)
        bus.emit_queued(job_id="j", scene_index=0, scene_name="s", scene_type="x")

    t = threading.Thread(target=stopper)
    t.start()
    seen: list[RenderEvent] = []
    for evt in bus.stream(poll_interval=0.05):
        seen.append(evt)
        if len(seen) >= 1:
            break
    t.join()
    assert len(seen) == 1
    assert emitted == []  # sanity: we didn't accidentally populate the outer list


# --- Orchestrator emission ---------------------------------------------------


def test_orchestrator_emits_events_for_each_scene(tmp_path: Path) -> None:
    """A render run should emit queued -> rendering -> done per scene."""
    from melosviz.conductor.orchestrator import Orchestrator
    from melosviz.conductor.events import reset_bus

    reset_bus()
    bus = get_bus()
    received: list[RenderEvent] = []
    unsub = bus.subscribe(received.append)
    try:
        # Minimal spec dict that the orchestrator accepts
        spec = {
            "version": 2,
            "scene_segments": [
                {"name": "intro", "scene_type": "video_export", "start": 0.0, "end": 5.0},
                {"name": "verse", "scene_type": "video_export", "start": 5.0, "end": 10.0},
            ],
        }
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True, auto_offline=True)
        orch.render(spec, scene_types=["video_export"])  # type: ignore[arg-type]
    finally:
        unsub()

    states_per_scene: dict[int, list[str]] = {}
    for evt in received:
        states_per_scene.setdefault(evt.scene_index, []).append(evt.state)
    # Scene 0 and scene 1 should each have a queued -> rendering -> done triad.
    for idx in (0, 1):
        assert states_per_scene[idx] == [STATE_QUEUED, STATE_RENDERING, STATE_DONE], (
            f"scene {idx} unexpected states: {states_per_scene[idx]}"
        )


def test_orchestrator_emits_error_event_for_missing_adapter(tmp_path: Path) -> None:
    """When no adapter is registered, an error event fires before ConductorError."""
    from melosviz.conductor.orchestrator import ConductorError, Orchestrator
    from melosviz.conductor.events import reset_bus

    reset_bus()
    bus = get_bus()
    received: list[RenderEvent] = []
    unsub = bus.subscribe(received.append)
    try:
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True, auto_offline=False)
        with pytest.raises(ConductorError):
            orch.render(
                {"version": 2, "scene_segments": [{"name": "x", "scene_type": "not_a_real_type"}]},
                scene_types=["not_a_real_type"],  # type: ignore[arg-type]
            )
    finally:
        unsub()

    error_events = [e for e in received if e.state == STATE_ERROR]
    assert len(error_events) == 1
    assert "no adapter" in error_events[0].error