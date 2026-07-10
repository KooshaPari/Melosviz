"""Bridge load / soak smoke (C08 L73).

Concurrent `/health` and light `/analyze` traffic via FastAPI TestClient.
Resets and raises the shared rate limiter so load traffic is not 429'd.
"""

from __future__ import annotations

import math
import struct
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from melosviz.bridge import server
from melosviz.bridge.server import app


def _make_wav(path: Path, duration_s: float = 0.25) -> Path:
    sr = 44100
    n = int(duration_s * sr)
    samples = [int(32767 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(n)]
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{n}h", *samples))
    return path


@pytest.fixture()
def client() -> TestClient:
    lim = server.security_limiter
    lim.reset()
    # Raise ceiling for load smoke; restore after.
    prev = lim._max
    lim._max = 10_000
    try:
        yield TestClient(app)
    finally:
        lim._max = prev
        lim.reset()


def test_load_health_concurrent(client: TestClient) -> None:
    n = 64

    def one(_: int) -> int:
        r = client.get("/health")
        return r.status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = [
            f.result() for f in as_completed(pool.submit(one, i) for i in range(n))
        ]
    assert codes.count(200) == n


def test_load_analyze_burst(client: TestClient, tmp_path: Path) -> None:
    wav = _make_wav(tmp_path / "burst.wav")
    n = 12
    server.security_limiter.reset()

    def one(_: int) -> int:
        r = client.post("/analyze", json={"wav_path": str(wav)})
        return r.status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = [
            f.result() for f in as_completed(pool.submit(one, i) for i in range(n))
        ]
    assert all(c == 200 for c in codes), codes


def test_load_metrics_after_traffic(client: TestClient) -> None:
    server.security_limiter.reset()
    for _ in range(8):
        assert client.get("/health").status_code == 200
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "melosviz_up 1" in body
    assert "melosviz_http_requests_total" in body
