"""Live IO bridge — OSC/WebSocket timeline-event streamer.

Streams :class:`~melosviz.analysis.models.TimelineEvent` objects (beats,
onsets, sections) from the MelosViz Python process to a running
TouchDesigner instance in real time (festival live mode).

Two transports are supported:
* **OSC** (default port 7700) — low-latency UDP; preferred for beat pulses.
* **WebSocket** (default port 7701) — reliable TCP; preferred for section
  changes and dense-keyframe payloads.

Both transports send JSON-encoded messages that the TD ``/io/event_router``
script CHOP decodes.

Message schema
--------------
Every message is a JSON object with at minimum::

    {
      "type":  "<event_type>",  // "beat" | "onset" | "section" | "keyframe"
      "t":     <float>,         // seconds
      // event-specific fields follow
    }

For ``"keyframe"`` events the full :class:`DenseKeyframe` dict is included.

Usage::

    from melosviz.runtime.touchdesigner.bridge import TDBridge, BridgeConfig

    cfg = BridgeConfig(osc_host="127.0.0.1", osc_port=7700, ws_port=7701)
    bridge = TDBridge(cfg)

    # Blocking — call from a thread / async task while playback runs
    bridge.stream_render_spec(render_spec)
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "BridgeConfig",
    "TDBridge",
    "serialise_timeline_event",
    "serialise_dense_keyframe",
]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class BridgeConfig:
    """Configuration for the OSC/WebSocket bridge.

    Attributes:
        osc_host: Hostname/IP of the running TD instance.
        osc_port: UDP port TD ``/io/osc_in`` is listening on.
        ws_port: TCP port TD ``/io/ws_in`` is listening on.
        transport: ``"osc"``, ``"websocket"``, or ``"both"``.
        playback_rate: Real-time multiplier (1.0 = wall clock).
    """

    osc_host: str = "127.0.0.1"
    osc_port: int = 7700
    ws_port: int = 7701
    transport: str = "osc"  # "osc" | "websocket" | "both"
    playback_rate: float = 1.0


# ---------------------------------------------------------------------------
# Serialisation helpers (tested without running TD)
# ---------------------------------------------------------------------------


def serialise_timeline_event(event: Any) -> dict[str, Any]:
    """Convert a TimelineEvent (Pydantic model or dict) to a bridge message.

    Args:
        event: A :class:`~melosviz.analysis.models.TimelineEvent` instance or
            a plain dict with at least ``"type"`` and ``"t"`` keys.

    Returns:
        A JSON-safe dict ready to send over OSC/WS.
    """
    if isinstance(event, dict):
        return dict(event)
    # Pydantic model — use model_dump if available, else vars
    if hasattr(event, "model_dump"):
        return event.model_dump()
    return vars(event)


def serialise_dense_keyframe(keyframe: Any) -> dict[str, Any]:
    """Convert a DenseKeyframe (Pydantic model or dict) to a bridge message.

    Adds ``"type": "keyframe"`` so the TD event_router can dispatch it.

    Args:
        keyframe: A :class:`~melosviz.analysis.models.DenseKeyframe` instance
            or a plain dict.

    Returns:
        A JSON-safe dict with ``"type": "keyframe"`` injected.
    """
    if isinstance(keyframe, dict):
        msg = dict(keyframe)
    elif hasattr(keyframe, "model_dump"):
        msg = keyframe.model_dump()
    else:
        msg = vars(keyframe)
    msg["type"] = "keyframe"
    return msg


# ---------------------------------------------------------------------------
# OSC transport (minimal, no external lib required)
# ---------------------------------------------------------------------------


class _OscTransport:
    """Minimal OSC UDP sender (OSC 1.0 string+blob encoding).

    Sends a single string argument per message — the JSON payload.
    This is sufficient for the TD ``/io/osc_in`` DAT to parse via
    ``callbacks DAT`` using ``json.loads(args[0])``.

    No dependency on python-osc — uses raw UDP sockets for portability.
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, address: str, payload: dict[str, Any]) -> None:
        """Send a JSON payload as an OSC string message.

        Args:
            address: OSC address string (e.g. ``"/melosviz/event"``).
            payload: JSON-serialisable dict.
        """
        json_str = json.dumps(payload)
        packet = self._encode_osc(address, json_str)
        self._sock.sendto(packet, (self._host, self._port))

    @staticmethod
    def _pad4(data: bytes) -> bytes:
        """Pad bytes to the next 4-byte boundary."""
        rem = len(data) % 4
        return data + b"\x00" * ((4 - rem) % 4)

    def _encode_osc(self, address: str, arg: str) -> bytes:
        """Encode a minimal OSC 1.0 packet with a single string argument."""
        addr_bytes = self._pad4((address + "\x00").encode("utf-8"))
        type_tag = self._pad4(b",s\x00\x00")
        arg_bytes = self._pad4((arg + "\x00").encode("utf-8"))
        return addr_bytes + type_tag + arg_bytes

    def close(self) -> None:
        self._sock.close()


# ---------------------------------------------------------------------------
# WebSocket transport (asyncio)
# ---------------------------------------------------------------------------


class _WsTransport:
    """Minimal asyncio WebSocket client transport.

    Falls back to a direct TCP write (newline-delimited JSON) if the
    ``websockets`` package is not installed, so the bridge works in
    minimal environments and tests without the full WS dependency.
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._ws: Any = None

    async def connect(self) -> None:
        try:
            import websockets  # type: ignore[import]
            uri = f"ws://{self._host}:{self._port}"
            self._ws = await websockets.connect(uri)
            logger.debug("WS connected to %s", uri)
        except ImportError:
            logger.warning(
                "websockets not installed; WS transport will use raw TCP."
            )
            self._ws = None

    async def send(self, payload: dict[str, Any]) -> None:
        json_str = json.dumps(payload)
        if self._ws is not None:
            await self._ws.send(json_str)
        else:
            # Raw TCP fallback — write newline-delimited JSON
            try:
                reader, writer = await asyncio.open_connection(self._host, self._port)
                writer.write((json_str + "\n").encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except OSError as exc:
                logger.warning("WS/TCP send failed: %s", exc)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class TDBridge:
    """Streams RenderSpec timeline events to TouchDesigner.

    Args:
        config: :class:`BridgeConfig` controlling transport and target.
    """

    _OSC_ADDRESS = "/melosviz/event"

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self._config = config or BridgeConfig()
        self._osc: _OscTransport | None = None
        self._ws: _WsTransport | None = None

        if self._config.transport in ("osc", "both"):
            self._osc = _OscTransport(self._config.osc_host, self._config.osc_port)
        if self._config.transport in ("websocket", "both"):
            self._ws = _WsTransport(self._config.osc_host, self._config.ws_port)

    def _send_sync(self, payload: dict[str, Any]) -> None:
        """Send payload synchronously via OSC (and/or schedule WS via asyncio)."""
        if self._osc is not None:
            try:
                self._osc.send(self._OSC_ADDRESS, payload)
            except OSError as exc:
                logger.warning("OSC send failed: %s", exc)
        if self._ws is not None:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._ws.send(payload))
            except RuntimeError:
                # Already in an event loop — fire and forget
                asyncio.ensure_future(self._ws.send(payload))

    def stream_render_spec(
        self,
        render_spec: RenderSpec,
        *,
        realtime: bool = False,
    ) -> None:
        """Stream all timeline events and dense keyframes to TD.

        Args:
            render_spec: The RenderSpec v2 to stream.
            realtime: If True, sleep between events to match wall-clock timing
                (scaled by ``config.playback_rate``).  If False, send all
                events as fast as possible (useful for tests / batch mode).
        """
        events: list[dict[str, Any]] = []

        for ev in (render_spec.timeline_events or []):
            events.append(serialise_timeline_event(ev))

        for kf in (render_spec.dense_keyframes or []):
            events.append(serialise_dense_keyframe(kf))

        # Sort by time
        events.sort(key=lambda e: float(e.get("t", 0.0)))

        prev_t = 0.0
        prev_wall = time.monotonic()

        for msg in events:
            t = float(msg.get("t", 0.0))
            if realtime:
                delay = (t - prev_t) / self._config.playback_rate
                elapsed = time.monotonic() - prev_wall
                sleep_for = delay - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
                prev_t = t
                prev_wall = time.monotonic()

            self._send_sync(msg)

    def close(self) -> None:
        """Release transport resources."""
        if self._osc is not None:
            self._osc.close()
