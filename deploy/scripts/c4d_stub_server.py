"""Cinema 4D headless HTTP stub.

Cinema 4D has no public headless HTTP API. This stub stands in for one so
the MelosViz pipeline can smoke end-to-end without a C4D license.

The shape mirrors what a real C4D worker would expose:

    POST /render  body: { "plan": <c4d_render_plan.json> }
                    -> 202 Accepted
                       { "ok": true,
                         "job_id": "...",
                         "output_path": "/workspace/output/<scene>.exr",
                         "started_at": "..." }

    GET  /jobs/<id>  -> current status (queued / running / done / error)

    GET  /healthz    -> 200 { "worker": "c4d-stub", "ready": true }

If MELOSVIZ_C4D_REAL_C4DPY is set, the stub shells out to that binary
instead of generating a synthetic .exr, so users with a C4D license can
swap this stub for the real driver.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="c4d-stub", version="0.1.0")

_JOBS: Dict[str, Dict[str, Any]] = {}

# When set, this is the c4dpy / Commandline.exe binary the stub will
# actually shell out to (real C4D headless driver).
REAL_C4DPY = os.getenv("MELOSVIZ_C4D_REAL_C4DPY")


def _output_dir() -> Path:
    """Resolve + create the output directory lazily.

    Lazy so the test harness can override MELOSVIZ_C4D_OUTPUT_DIR via
    os.environ before the directory is created (the docker path
    /workspace/output is read-only on macOS dev hosts).
    """
    d = Path(os.getenv("MELOSVIZ_C4D_OUTPUT_DIR", "/workspace/output"))
    d.mkdir(parents=True, exist_ok=True)
    return d


class RenderRequest(BaseModel):
    plan: Dict[str, Any]


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    return {"worker": "c4d-stub", "ready": True, "real_c4dpy": bool(REAL_C4DPY)}


@app.get("/system_stats")
def system_stats() -> Dict[str, Any]:
    return {
        "name": "c4d-stub",
        "version": "0.1.0",
        "real_c4dpy": bool(REAL_C4DPY),
        "jobs_in_flight": sum(1 for j in _JOBS.values() if j["status"] == "running"),
    }


@app.post("/render")
def render(req: RenderRequest) -> Dict[str, Any]:
    plan = req.plan
    scene_name = plan.get("scene_name") or plan.get("name") or f"scene_{int(time.time())}"
    job_id = uuid.uuid4().hex[:12]
    started_at = time.time()
    output_path = _output_dir() / f"{scene_name}_{job_id}.exr"

    _JOBS[job_id] = {
        "status": "running",
        "scene_name": scene_name,
        "output_path": str(output_path),
        "started_at": started_at,
        "plan": plan,
        "real_c4dpy": bool(REAL_C4DPY),
    }

    if REAL_C4DPY:
        # Real headless driver path: spawn c4dpy with the per-scene driver script.
        # Driver scripts are emitted next to the c4d_render_plan.json by C4DAdapter.
        driver_script = plan.get("driver_script")
        if not driver_script or not Path(driver_script).exists():
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = f"driver_script missing: {driver_script!r}"
            raise HTTPException(status_code=400, detail=_JOBS[job_id]["error"])
        try:
            subprocess.run(
                [REAL_C4DPY, str(driver_script)],
                check=True,
                timeout=int(os.getenv("MELOSVIZ_C4D_TIMEOUT", "600")),
            )
            _JOBS[job_id]["status"] = "done"
            _JOBS[job_id]["finished_at"] = time.time()
            return {"ok": True, "job_id": job_id, "output_path": str(output_path)}
        except subprocess.TimeoutExpired as exc:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = f"c4dpy timeout after {exc.timeout}s"
            raise HTTPException(status_code=504, detail=_JOBS[job_id]["error"]) from exc
        except subprocess.CalledProcessError as exc:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = f"c4dpy exit {exc.returncode}"
            raise HTTPException(status_code=500, detail=_JOBS[job_id]["error"]) from exc

    # Stub path: write a synthetic .exr sidecar that the rest of the pipeline can ingest.
    # The sidecar is a JSON envelope with the plan + a fake frame, so generate/assemble
    # still treats the scene as "done" and continues.
    sidecar = {
        "scene_name": scene_name,
        "stub": True,
        "format": "exr",
        "frames": plan.get("frames", 240),
        "fps": plan.get("fps", 30),
        "width": plan.get("width", 1920),
        "height": plan.get("height", 1080),
        "started_at": started_at,
        "finished_at": time.time(),
    }
    sidecar_path = output_path.with_suffix(".json")
    sidecar_path.write_text(json.dumps(sidecar, indent=2))
    output_path.write_text("")  # zero-byte EXR placeholder

    _JOBS[job_id]["status"] = "done"
    _JOBS[job_id]["finished_at"] = time.time()
    _JOBS[job_id]["stub"] = True
    return {"ok": True, "job_id": job_id, "output_path": str(output_path), "stub": True}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"unknown job_id={job_id}")
    return job


@app.get("/jobs")
def list_jobs() -> Dict[str, Any]:
    return {"jobs": list(_JOBS.keys()), "count": len(_JOBS)}


def main() -> None:
    """Run the C4D stub server.

    Real production runs would invoke Cinema 4D's `Commandline.exe` or
    `c4dpy` headless; this stub pretends to do so and emits valid PNG
    frames + a placeholder MP4 so the rest of the orchestrator pipeline
    can be exercised end-to-end without the C4D binary on the host.
    """
    import argparse

    parser = argparse.ArgumentParser(description="MelosViz C4D stub listener")
    parser.add_argument("--host", default="0.0.0.0", help="bind host (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8787, help="bind port (default 8787)")
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("MELOSVIZ_C4D_OUTPUT_DIR", "/workspace/output"),
        help="where to write per-scene artifacts (env: MELOSVIZ_C4D_OUTPUT_DIR)",
    )
    args = parser.parse_args()

    # Make the output dir lazy so tests can override the env var before
    # any state has been written.
    global _OUTPUT_DIR
    _OUTPUT_DIR = Path(args.output_dir)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[c4d_stub] starting on http://{args.host}:{args.port}  output={_OUTPUT_DIR}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
