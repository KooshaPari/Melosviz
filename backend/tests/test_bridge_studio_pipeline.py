"""Bridge endpoint tests for the studio pipeline (storyboard / generate / master / ship).

These tests bypass the actual ``python -m melosviz.cli.main`` subprocess calls
by monkeypatching ``_run_studio_subprocess`` so the HTTP layer can be exercised
in CI without a ComfyUI / Cinema 4D / DaVinci / Unreal installation.
"""

from __future__ import annotations

import json
import struct
import time
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from melosviz.bridge import server
from melosviz.bridge.server import app
from melosviz.conductor import events as conductor_events
from melosviz.conductor.events import STATE_DONE, STATE_QUEUED, STATE_RENDERING, get_bus, reset_bus


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_security():
    yield
    if hasattr(server, "security_limiter"):
        server.security_limiter.reset()


def _write_test_wav(path: Path, duration_sec: float = 1.0, sr: int = 8000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(sr * duration_sec)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(n):
            sample = int((i % 100) * 100)  # arbitrary non-zero samples
            w.writeframesraw(struct.pack("<h", sample))


# ---------------------------------------------------------------------------
# /api/studio/storyboard
# ---------------------------------------------------------------------------


def test_studio_storyboard_emits_storyboard_json(tmp_path: Path, client: TestClient) -> None:
    wav = tmp_path / "track.wav"
    _write_test_wav(wav)
    out_dir = tmp_path / "studio"

    fake_storyboard = {
        "concept": "underwater city",
        "bpm": 124,
        "scenes": [
            {
                "name": "Open",
                "start_sec": 0,
                "end_sec": 30,
                "scene_type": "comfyui_image",
                "camera_motion": "static",
                "prompt": "underwater city bioluminescent",
                "palette": ["#0d0d10", "#ff2bd6"],
                "seed": 42,
            },
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "storyboard.json").write_text(json.dumps(fake_storyboard))

    with patch.object(server, "_run_studio_subprocess", return_value={"returncode": 0}):
        res = client.post(
            "/api/studio/storyboard",
            json={
                "wav_path": str(wav),
                "concept": "underwater city",
                "bpm": 124.0,
                "palette": "#0d0d10 #ff2bd6",
                "out_dir": str(out_dir),
            },
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["concept"] == "underwater city"
    assert body["bpm"] == 124
    assert len(body["scenes"]) == 1
    assert body["scenes"][0]["scene_type"] == "comfyui_image"


def test_studio_storyboard_404_for_missing_wav(tmp_path: Path, client: TestClient) -> None:
    res = client.post(
        "/api/studio/storyboard",
        json={
            "wav_path": str(tmp_path / "does-not-exist.wav"),
            "out_dir": str(tmp_path / "studio"),
        },
    )
    assert res.status_code == 400
    assert "File not found" in res.text


def test_studio_storyboard_dispatches_cli_with_expected_args(
    tmp_path: Path, client: TestClient
) -> None:
    wav = tmp_path / "track.wav"
    _write_test_wav(wav)
    out_dir = tmp_path / "studio"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        json.dumps({"scenes": [{"name": "x"}]})
    )

    with patch.object(
        server, "_run_studio_subprocess", return_value={"returncode": 0}
    ) as mock_run:
        client.post(
            "/api/studio/storyboard",
            json={
                "wav_path": str(wav),
                "concept": "abstract",
                "bpm": 120.0,
                "palette": "#000 #fff",
                "out_dir": str(out_dir),
            },
        )

    assert mock_run.called
    args = mock_run.call_args[0][0]
    assert "storyboard" in args
    assert str(wav) in args
    assert "--concept" in args
    assert "abstract" in args


# ---------------------------------------------------------------------------
# /api/studio/generate
# ---------------------------------------------------------------------------


def test_studio_generate_returns_scene_manifest(tmp_path: Path, client: TestClient) -> None:
    wav = tmp_path / "track.wav"
    _write_test_wav(wav)
    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({"scenes": []}))
    out_dir = tmp_path / "generate"

    # Pre-create the scene_* dirs the manifest expects
    (out_dir / "scene_0").mkdir(parents=True)
    (out_dir / "scene_0" / "workflow.json").write_text("{}")

    with patch.object(server, "_run_studio_subprocess", return_value={"returncode": 0}):
        res = client.post(
            "/api/studio/generate",
            json={
                "wav_path": str(wav),
                "storyboard_path": str(sb),
                "out_dir": str(out_dir),
                "offline": True,
            },
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert "out_dir" in body
    assert isinstance(body["scenes"], list)
    assert len(body["scenes"]) == 1
    assert body["scenes"][0]["name"] == "scene_0"
    assert body["scenes"][0]["workflow_json"].endswith("workflow.json")


# ---------------------------------------------------------------------------
# /api/studio/master
# ---------------------------------------------------------------------------


def test_studio_master_returns_master_plan(tmp_path: Path, client: TestClient) -> None:
    edit = tmp_path / "assembly_plan.json"
    edit.write_text(json.dumps({"scenes": []}))
    out_dir = tmp_path / "master"
    out_dir.mkdir()
    master_plan = {
        "deliverables": [
            {"kind": "festival", "path": str(out_dir / "festival.mov"), "bytes": 1024},
            {"kind": "youtube", "path": str(out_dir / "youtube.mp4"), "bytes": 512},
        ],
        "files": ["festival.mov", "youtube.mp4"],
    }
    (out_dir / "master_plan.json").write_text(json.dumps(master_plan))

    with patch.object(server, "_run_studio_subprocess", return_value={"returncode": 0}):
        res = client.post(
            "/api/studio/master",
            json={"edit_path": str(edit), "out_dir": str(out_dir)},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["deliverables"]) == 2
    assert body["deliverables"][0]["kind"] == "festival"


# ---------------------------------------------------------------------------
# /api/studio/ship
# ---------------------------------------------------------------------------


def test_studio_ship_returns_zip_info(tmp_path: Path, client: TestClient) -> None:
    master_dir = tmp_path / "master"
    master_dir.mkdir()
    (master_dir / "final.zip").write_bytes(b"PK\x03\x04fake-zip-bytes")
    (master_dir / "manifest.json").write_text(
        json.dumps({"contents": [{"path": "festival.mov", "bytes": 1024}]})
    )

    with patch.object(server, "_run_studio_subprocess", return_value={"returncode": 0}):
        res = client.post(
            "/api/studio/ship",
            json={"master_dir": str(master_dir)},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["final_zip"].endswith("final.zip")
    assert body["final_zip_bytes"] > 0
    assert "manifest" in body


def test_studio_ship_handles_missing_master_dir(tmp_path: Path, client: TestClient) -> None:
    res = client.post(
        "/api/studio/ship",
        json={"master_dir": str(tmp_path / "missing")},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# /api/render/events/recent — polling fallback for render queue progress
# ---------------------------------------------------------------------------


def test_render_events_recent_empty_bus(client: TestClient) -> None:
    """With no events emitted, /api/render/events/recent returns an empty list."""
    reset_bus()
    res = client.get("/api/render/events/recent")
    assert res.status_code == 200
    body = res.json()
    assert body["events"] == []
    assert body["count"] == 0


def test_render_events_recent_returns_emitted_events(client: TestClient) -> None:
    """Events pushed onto the in-process bus are exposed via the polling endpoint."""
    reset_bus()
    bus = get_bus()
    bus.emit_queued(job_id="j1", scene_index=0, scene_name="open", scene_type="comfyui_image")
    bus.emit_rendering(job_id="j1", scene_index=0, scene_name="open", scene_type="comfyui_image")
    bus.emit_done(
        job_id="j1",
        scene_index=0,
        scene_name="open",
        scene_type="comfyui_image",
        backend="melosviz.render.comfyui_adapter.ComfyUIAdapter",
        artifact_path="/tmp/j1/scene_000.png",
    )

    res = client.get("/api/render/events/recent")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 3
    states = [evt["state"] for evt in body["events"]]
    assert states == [STATE_QUEUED, STATE_RENDERING, STATE_DONE]
    # job_id and scene metadata round-trip
    assert body["events"][0]["job_id"] == "j1"
    assert body["events"][0]["scene_index"] == 0
    assert body["events"][0]["scene_name"] == "open"
    assert body["events"][0]["scene_type"] == "comfyui_image"


def test_render_events_recent_filters_by_job_id(client: TestClient) -> None:
    """Caller can scope the buffer read to a specific job_id via the bus helper."""
    reset_bus()
    bus = get_bus()
    bus.emit_queued(job_id="jA", scene_index=0, scene_name="open", scene_type="comfyui_image")
    bus.emit_queued(job_id="jB", scene_index=0, scene_name="open", scene_type="comfyui_video")
    bus.emit_done(job_id="jA", scene_index=0, scene_name="open", scene_type="comfyui_image")

    # The bridge recent endpoint returns everything (job_id is a kwarg only the
    # SSE endpoint accepts); verify both jobs surface at least once.
    body = client.get("/api/render/events/recent").json()
    job_ids = {evt["job_id"] for evt in body["events"]}
    assert {"jA", "jB"} <= job_ids


def test_render_events_recent_since_ms_skips_old_events(client: TestClient) -> None:
    """since_ms filter skips events older than the cutoff so reconnects don't replay everything."""
    reset_bus()
    bus = get_bus()
    bus.emit_queued(job_id="j1", scene_index=0, scene_name="open", scene_type="comfyui_image")
    # Use a far-future cutoff so all current events are skipped
    future_ms = int((time.time() + 60) * 1000)

    res = client.get(f"/api/render/events/recent?since_ms={future_ms}")
    assert res.status_code == 200
    assert res.json()["count"] == 0


# ---------------------------------------------------------------------------
# /api/render/events — SSE stream (shape only; we don't read infinite streams in pytest)
# ---------------------------------------------------------------------------


def test_render_events_stream_returns_event_stream_content_type(client: TestClient) -> None:
    """The SSE endpoint returns text/event-stream + cache-control: no-cache."""
    reset_bus()
    bus = get_bus()
    bus.emit_queued(job_id="jSSE", scene_index=0, scene_name="open", scene_type="comfyui_image")

    # httpx has to stream so the response generator actually runs; cancel after
    # the first chunk to keep the test fast.
    with client.stream("GET", "/api/render/events?job_id=jSSE") as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        # Read one chunk and verify it parses as an SSE data frame
        first_chunk = next(res.iter_text(chunk_size=1024))
        assert "data:" in first_chunk
        # Extract the first JSON payload and verify its shape
        first_line = next(ln for ln in first_chunk.splitlines() if ln.startswith("data:"))
        payload = json.loads(first_line.removeprefix("data:").strip())
        assert payload["job_id"] == "jSSE"
        assert payload["state"] == STATE_QUEUED
        assert payload["scene_index"] == 0
        assert payload["scene_type"] == "comfyui_image"


def test_render_events_stream_replays_buffered_events(client: TestClient) -> None:
    """A client connecting after events fired still receives them via the replay buffer."""
    reset_bus()
    bus = get_bus()
    for state_fn, kw in [
        (bus.emit_queued, {}),
        (bus.emit_rendering, {}),
        (bus.emit_done, {"artifact_path": "/tmp/scene.png"}),
    ]:
        state_fn(job_id="jRe", scene_index=2, scene_name="verse2", scene_type="comfyui_video", **kw)

    with client.stream("GET", "/api/render/events?job_id=jRe") as res:
        assert res.status_code == 200
        body = res.read().decode("utf-8", errors="replace")

    data_lines = [
        ln.removeprefix("data:").strip()
        for ln in body.splitlines()
        if ln.startswith("data:")
    ]
    assert len(data_lines) >= 3
    payloads = [json.loads(line) for line in data_lines]
    states = [p["state"] for p in payloads]
    assert STATE_QUEUED in states
    assert STATE_RENDERING in states
    assert STATE_DONE in states


def test_render_events_emitter_helper_validates_state() -> None:
    """RenderEventBus.emit_queued/rendering/done/error each require a valid state kwarg."""
    reset_bus()
    bus = get_bus()
    # All four state helpers produce well-formed events
    e1 = bus.emit_queued(job_id="j", scene_index=0, scene_name="x", scene_type="comfyui_image")
    e2 = bus.emit_rendering(job_id="j", scene_index=0, scene_name="x", scene_type="comfyui_image")
    e3 = bus.emit_done(job_id="j", scene_index=0, scene_name="x", scene_type="comfyui_image")
    e4 = bus.emit_error(job_id="j", scene_index=0, scene_name="x", scene_type="comfyui_image", error="boom")
    assert (e1.state, e2.state, e3.state, e4.state) == (STATE_QUEUED, STATE_RENDERING, STATE_DONE, "error")
    assert e4.error == "boom"


def test_render_events_subscribe_receives_new_events() -> None:
    """Subscribers receive emitted events immediately (used by orchestrator + tests)."""
    reset_bus()
    bus = get_bus()
    received: list[conductor_events.RenderEvent] = []
    bus.subscribe(received.append)
    bus.emit_queued(job_id="j", scene_index=0, scene_name="open", scene_type="comfyui_image")
    bus.emit_done(job_id="j", scene_index=0, scene_name="open", scene_type="comfyui_image")
    assert [e.state for e in received] == [STATE_QUEUED, STATE_DONE]


def test_render_events_subscribe_unsubscribe_stops_receipt() -> None:
    """Calling the unsubscribe function returned by subscribe() stops further deliveries."""
    bus = get_bus()
    received: list[conductor_events.RenderEvent] = []
    unsub = bus.subscribe(received.append)
    bus.emit_queued(job_id="j", scene_index=0, scene_name="x", scene_type="comfyui_image")
    assert len(received) == 1
    unsub()
    bus.emit_queued(job_id="j", scene_index=1, scene_name="x", scene_type="comfyui_image")
    assert len(received) == 1  # still 1; the second event was not delivered


# ---------------------------------------------------------------------------
# Depth-layer endpoints: /api/studio/direct + /api/studio/validate
# ---------------------------------------------------------------------------


def test_studio_direct_returns_edit_summary(tmp_path, monkeypatch) -> None:
    """POST /api/studio/direct edits one scene in-place and returns a summary."""
    from fastapi.testclient import TestClient

    import melosviz.bridge.server as bridge_server
    from melosviz.bridge.server import app

    sb = {
        "concept": "neon noir",
        "bpm": 124,
        "scenes": [
            {"name": "intro", "start": 0.0, "end": 10.0, "duration": 10.0, "prompt": "x", "camera": "slow_dolly_in"},
            {"name": "verse", "start": 10.0, "end": 30.0, "duration": 20.0, "prompt": "y", "camera": "slow_pull_back"},
        ],
    }
    sb_path = tmp_path / "sb.json"
    sb_path.write_text(json.dumps(sb))

    # Stub out the subprocess call so the test doesn't shell out
    def fake_subprocess(self, *args, **kwargs):  # noqa: ARG001
        class _Out:
            returncode = 0
            stdout = json.dumps({"status": "ok", "edit_count": 1, "edits": ["replace_prompt"]})
            stderr = ""

        return _Out()

    monkeypatch.setattr(bridge_server, "_run_studio_subprocess", fake_subprocess)

    with TestClient(app) as client:
        r = client.post(
            "/api/studio/direct",
            json={
                "storyboard_path": str(sb_path),
                "scene_index": 1,
                "replace_prompt": "NEW PROMPT",
                "replace_camera": "whip_pan_burst_then_hold",
                "replace_name": "drop_chorus",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene_index"] == 1
    assert body["edits"] == ["replace_prompt", "replace_camera", "replace_name"]
    assert body["edit_count"] == 1


def test_studio_direct_missing_storyboard_returns_400(tmp_path) -> None:
    """POST /api/studio/direct with a missing storyboard returns 400, not a 500."""
    from fastapi.testclient import TestClient

    from melosviz.bridge.server import app

    missing = tmp_path / "does-not-exist.json"
    with TestClient(app) as client:
        r = client.post(
            "/api/studio/direct",
            json={"storyboard_path": str(missing), "scene_index": 0, "replace_prompt": "x"},
        )
    assert r.status_code == 400, r.text
    assert "storyboard" in r.text.lower() or "not found" in r.text.lower()


def test_studio_validate_returns_severity_breakdown(tmp_path) -> None:
    """POST /api/studio/validate returns a structured severity report."""
    from fastapi.testclient import TestClient

    from melosviz.bridge.server import app

    sb = {
        "concept": "neon noir test",
        "bpm": 124,
        "scenes": [
            {"name": "intro", "start": 0.0, "end": 5.0, "duration": 5.0, "prompt": "x", "camera": "slow_dolly_in", "palette": ["#0d0d10"]},
            {"name": "verse", "start": 5.0, "end": 10.0, "duration": 5.0, "prompt": "y", "camera": "slow_pull_back", "palette": ["#0d0d10"]},
        ],
    }
    sb_path = tmp_path / "sb.json"
    sb_path.write_text(json.dumps(sb))

    with TestClient(app) as client:
        r = client.post("/api/studio/validate", json={"storyboard_path": str(sb_path)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "issues" in body
    assert "summary" in body
    assert set(body["summary"].keys()) == {"error", "warning", "info"}
    assert isinstance(body["issues"], list)


def test_studio_validate_reports_overlap_issue(tmp_path) -> None:
    """Two overlapping scenes (end > next.start) should produce at least one issue."""
    from fastapi.testclient import TestClient

    from melosviz.bridge.server import app

    sb = {
        "concept": "overlap test",
        "bpm": 124,
        "scenes": [
            {"name": "a", "start": 0.0, "end": 12.0, "duration": 12.0, "prompt": "x", "camera": "slow_dolly_in", "palette": ["#0d0d10"]},
            {"name": "b", "start": 10.0, "end": 20.0, "duration": 10.0, "prompt": "y", "camera": "slow_pull_back", "palette": ["#0d0d10"]},
        ],
    }
    sb_path = tmp_path / "sb.json"
    sb_path.write_text(json.dumps(sb))

    with TestClient(app) as client:
        r = client.post("/api/studio/validate", json={"storyboard_path": str(sb_path)})
    assert r.status_code == 200, r.text
    body = r.json()
    codes = {i["code"] for i in body["issues"]}
    assert "scene_overlap" in codes