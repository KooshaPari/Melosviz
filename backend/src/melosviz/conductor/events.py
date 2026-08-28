"""Render event bus — live SSE feed of per-scene render progress.

When the orchestrator dispatches a render job to a backend adapter, it
emits :class:`RenderEvent` records through an in-process bus. UI
clients (web StudioConsole, desktop Director's Console) subscribe via
SSE to ``/api/render/events`` and update their render queue in real
time instead of waiting for the whole pipeline to finish.

The bus is intentionally simple: an in-process pub/sub with a bounded
ring buffer for late subscribers (SSE clients reconnecting after a
network blip). There is no cross-process coordination — every
``viz storyboard/generate/assemble/master/ship`` invocation runs in
its own process and its events live only for the lifetime of that
process. The bridge server runs as a long-lived process and proxies
events from the CLI child process through stdio if it wants to surface
events in-process; by default, events are scoped to the current
process and live only for ``buffer_seconds``.

This is the same pattern ffmpeg, Blender, Unreal, and DaVinci all use
for their render queues: a fire-and-forget event stream the operator
can tail or attach a UI to.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Deque, Iterator


# Event states
STATE_QUEUED = "queued"
STATE_RENDERING = "rendering"
STATE_DONE = "done"
STATE_ERROR = "error"
STATE_SKIPPED = "skipped"

ALL_STATES = (STATE_QUEUED, STATE_RENDERING, STATE_DONE, STATE_ERROR, STATE_SKIPPED)


@dataclass
class RenderEvent:
    """A single per-scene render event."""

    job_id: str
    scene_index: int
    scene_name: str
    scene_type: str
    state: str  # one of ALL_STATES
    backend: str = ""  # adapter key that handled it
    duration_ms: float = 0.0  # actual render time (for done/error)
    progress: float = 0.0  # 0.0 - 1.0; -1.0 = unknown
    error: str = ""  # populated on error
    artifact_path: str = ""  # populated on done
    timestamp: float = field(default_factory=time.time)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def ts_ms(self) -> int:
        """Wall-clock timestamp in milliseconds (matches the ``since_ms``
        query-param convention used by the SSE bridge endpoint)."""
        return int(self.timestamp * 1000)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts_ms"] = self.ts_ms
        return d

    def to_sse(self) -> str:
        """Format as an SSE ``data:`` line."""
        payload = json.dumps(self.to_dict(), separators=(",", ":"))
        return f"event: render\ndata: {payload}\n\n"


class RenderEventBus:
    """Thread-safe in-process pub/sub for :class:`RenderEvent` records."""

    def __init__(self, *, buffer_size: int = 256, buffer_seconds: float = 60.0) -> None:
        self._buffer: Deque[RenderEvent] = deque(maxlen=buffer_size)
        self._subscribers: list[Callable[[RenderEvent], None]] = []
        self._lock = threading.Lock()
        self._buffer_seconds = buffer_seconds

    # --- emit -----------------------------------------------------------

    def emit(
        self,
        *,
        job_id: str,
        scene_index: int,
        scene_name: str,
        scene_type: str,
        state: str,
        backend: str = "",
        duration_ms: float = 0.0,
        progress: float = 0.0,
        error: str = "",
        artifact_path: str = "",
        extras: dict[str, Any] | None = None,
    ) -> RenderEvent:
        if state not in ALL_STATES:
            raise ValueError(f"unknown render state: {state!r}")
        evt = RenderEvent(
            job_id=job_id,
            scene_index=scene_index,
            scene_name=scene_name,
            scene_type=scene_type,
            state=state,
            backend=backend,
            duration_ms=duration_ms,
            progress=progress,
            error=error,
            artifact_path=artifact_path,
            extras=extras or {},
        )
        with self._lock:
            self._buffer.append(evt)
            subs = list(self._subscribers)
        for sub in subs:
            try:
                sub(evt)
            except Exception:  # pragma: no cover - subscriber errors must not break the bus
                pass
        return evt

    def emit_queued(self, *, job_id: str, scene_index: int, scene_name: str, scene_type: str, backend: str = "") -> RenderEvent:
        return self.emit(
            job_id=job_id,
            scene_index=scene_index,
            scene_name=scene_name,
            scene_type=scene_type,
            state=STATE_QUEUED,
            backend=backend,
            progress=0.0,
        )

    def emit_rendering(self, *, job_id: str, scene_index: int, scene_name: str, scene_type: str, backend: str = "", progress: float = 0.05) -> RenderEvent:
        return self.emit(
            job_id=job_id,
            scene_index=scene_index,
            scene_name=scene_name,
            scene_type=scene_type,
            state=STATE_RENDERING,
            backend=backend,
            progress=progress,
        )

    def emit_done(self, *, job_id: str, scene_index: int, scene_name: str, scene_type: str, backend: str = "", duration_ms: float = 0.0, artifact_path: str = "") -> RenderEvent:
        return self.emit(
            job_id=job_id,
            scene_index=scene_index,
            scene_name=scene_name,
            scene_type=scene_type,
            state=STATE_DONE,
            backend=backend,
            duration_ms=duration_ms,
            progress=1.0,
            artifact_path=artifact_path,
        )

    def emit_error(self, *, job_id: str, scene_index: int, scene_name: str, scene_type: str, backend: str = "", error: str = "", duration_ms: float = 0.0) -> RenderEvent:
        return self.emit(
            job_id=job_id,
            scene_index=scene_index,
            scene_name=scene_name,
            scene_type=scene_type,
            state=STATE_ERROR,
            backend=backend,
            duration_ms=duration_ms,
            progress=0.0,
            error=error,
        )

    # --- subscribe ------------------------------------------------------

    def subscribe(self, callback: Callable[[RenderEvent], None]) -> Callable[[], None]:
        """Register a callback; returns an unsubscribe function."""
        with self._lock:
            self._subscribers.append(callback)
        def _unsub() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass
        return _unsub

    # --- replay ---------------------------------------------------------

    def recent(
        self,
        *,
        since_ms: float | None = None,
        job_id: str | None = None,
        max_events: int = 256,
    ) -> list[RenderEvent]:
        """Return buffered events newer than ``since_ms`` (or all if None).

        If ``job_id`` is provided, the replay is filtered to that job only
        so a reconnecting SSE client doesn't see events from a sibling
        pipeline run.
        """
        cutoff = (since_ms / 1000.0) if since_ms is not None else None
        # Anything older than buffer_seconds is treated as gone; replay
        # callers should know the buffer is bounded.
        if cutoff is not None and self._buffer_seconds > 0:
            cutoff = max(cutoff, time.time() - self._buffer_seconds)
        with self._lock:
            buf = list(self._buffer)
        if cutoff is not None:
            buf = [e for e in buf if e.timestamp >= cutoff]
        if job_id is not None:
            buf = [e for e in buf if e.job_id == job_id]
        return buf[-max_events:]

    def stream(
        self,
        *,
        since_ms: float | None = None,
        job_id: str | None = None,
        poll_interval: float = 0.5,
    ) -> Iterator[RenderEvent]:
        """Block-yield events until the iterator is closed.

        Uses polling on ``recent()`` for late-joining subscribers so
        reconnects after network blips pick up where they left off.

        If ``job_id`` is provided, only events for that job are yielded
        so the stream stays scoped to the current pipeline run.
        """
        seen_ts = (since_ms / 1000.0) if since_ms is not None else 0.0
        while True:
            for evt in self.recent(job_id=job_id):
                if evt.timestamp > seen_ts:
                    seen_ts = evt.timestamp
                    yield evt
            time.sleep(poll_interval)


# --- module-level singleton --------------------------------------------------

_BUS: RenderEventBus | None = None
_BUS_LOCK = threading.Lock()


def get_bus() -> RenderEventBus:
    """Return the process-wide :class:`RenderEventBus` (lazy-initialized)."""
    global _BUS
    with _BUS_LOCK:
        if _BUS is None:
            _BUS = RenderEventBus()
        return _BUS


def reset_bus() -> None:
    """Drop the singleton (test helper)."""
    global _BUS
    with _BUS_LOCK:
        _BUS = None


__all__ = [
    "RenderEvent",
    "RenderEventBus",
    "STATE_QUEUED",
    "STATE_RENDERING",
    "STATE_DONE",
    "STATE_ERROR",
    "STATE_SKIPPED",
    "ALL_STATES",
    "get_bus",
    "reset_bus",
]