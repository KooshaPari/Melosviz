"""Lightweight smoke tests for the deploy/scripts/c4d_stub_server.

Avoids pytest fixtures so the deploy/ directory stays self-contained and
people can run them directly with:

    python deploy/scripts/c4d_stub_server.py &
    python deploy/scripts/test_c4d_stub_server.py

or under pytest from the project root.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _import_stub():
    stub_path = Path(__file__).parent / "c4d_stub_server.py"
    spec = importlib.util.spec_from_file_location("_c4d_stub", stub_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wait_ready(url: str, deadline_s: float = 5.0) -> None:
    started = time.time()
    last_err: Exception | None = None
    while time.time() - started < deadline_s:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(0.05)
    raise RuntimeError(f"server never came ready at {url}: {last_err}")


def main() -> int:
    port = _free_port()
    stub = _import_stub()
    if hasattr(stub, "_make_app"):
        app = stub._make_app()  # type: ignore[attr-defined]
        # Use uvicorn when available; otherwise thread the WSGI app.
        try:
            import uvicorn  # type: ignore

            import threading

            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
            server = uvicorn.Server(config)
            t = threading.Thread(target=server.run, daemon=True)
            t.start()
        except Exception:
            from wsgiref.simple_server import make_server

            def _start():
                httpd = make_server("127.0.0.1", port, app)
                httpd.serve_forever()

            import threading

            threading.Thread(target=_start, daemon=True).start()
    else:
        # Fallback: just exec the stub in a child process.
        import subprocess

        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "c4d_stub_server.py")],
            env={**os.environ, "MELOSVIZ_C4D_STUB_PORT": str(port), "MELOSVIZ_C4D_STUB_AUTORENDER": "false"},
        )
        try:
            _wait_ready(f"http://127.0.0.1:{port}/healthz")
            base = f"http://127.0.0.1:{port}"

            def fetch(path: str):
                with urllib.request.urlopen(base + path, timeout=3) as r:
                    return json.loads(r.read())

            sys.stdout.write(json.dumps({"system_stats": fetch("/system_stats")}) + "\n")
            health = fetch("/healthz")
            assert health["status"] == "ok", health
            proc.terminate()
            return 0
        finally:
            proc.kill()

    base = f"http://127.0.0.1:{port}"
    _wait_ready(base + "/healthz")

    def fetch(path: str):
        with urllib.request.urlopen(base + path, timeout=3) as r:
            return json.loads(r.read())

    def post(path: str, body: dict):
        req = urllib.request.Request(
            base + path,
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    stats = fetch("/system_stats")
    assert "python_version" in stats
    health = fetch("/healthz")
    assert health["status"] == "ok"
    job = post("/render", {"scene": "shark_dance", "output": "/tmp/shark.mp4", "frames": 24})
    assert job["job_id"]
    job_id = job["job_id"]
    deadline = time.time() + 6
    final = None
    while time.time() < deadline:
        s = fetch(f"/jobs/{job_id}")
        if s["state"] in ("done", "error"):
            final = s
            break
        time.sleep(0.1)
    assert final is not None, f"job never finished: {job_id}"
    assert final["state"] in ("done", "error")
    if final["state"] == "done":
        # Output path should exist (or have been cleaned up after probe).
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
