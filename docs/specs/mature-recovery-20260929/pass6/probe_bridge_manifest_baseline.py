#!/usr/bin/env python3
"""Reproduce M-F22 through the mounted FastAPI /api/studio/generate route.

Uses the real bridge subprocess helper -> real CLI -> real orchestrator in offline
mode. Exit 0 means the EXPECTED baseline layout/manifest mismatch was observed.
It is not product acceptance.
"""
from __future__ import annotations
import json, os, struct, tempfile, wave
from pathlib import Path
from fastapi.testclient import TestClient
from melosviz.bridge.server import app

def write_wav(path:Path)->None:
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h",2000 if i%200<100 else -2000) for i in range(8000)))

def main()->int:
    receipt=Path(os.environ.get("MELOSVIZ_RECOVERY_RECEIPT","bridge-layout-baseline.json"))
    with tempfile.TemporaryDirectory(prefix="mv-bridge-layout-") as td:
        root=Path(td);wav=root/"fixture.wav";write_wav(wav)
        sb=root/"storyboard.json"
        sb.write_text(json.dumps({"concept":"recovery","seed":1,"scenes":[
            {"scene_index":0,"scene_name":"S1","name":"S1","scene_type":"comfyui_image","start":0.0,"end":1.0,"prompt":"recovery red card","width":64,"height":64,"fps":8}
        ]}))
        out=root/"generate"
        with TestClient(app) as client:
            res=client.post("/api/studio/generate",json={
              "wav_path":str(wav),"storyboard_path":str(sb),"out_dir":str(out),
              "offline":True,"job_id":"recovery-bridge-layout-r1"
            })
        body=None
        try: body=res.json()
        except Exception: pass
        nested=sorted(str(p.relative_to(out)) for p in out.rglob("scene_*") if p.is_dir()) if out.exists() else []
        files=sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()) if out.exists() else []
        manifest_scenes=body.get("scenes",[]) if isinstance(body,dict) else None
        reproduced=(res.status_code==200 and nested and all("/scene_" in p for p in nested) and manifest_scenes==[])
        payload={
          "subject":"M-F22_MOUNTED_BRIDGE_BASELINE_NOT_ACCEPTANCE",
          "http_status":res.status_code,
          "response":body if body is not None else res.text[-2000:],
          "nested_scene_dirs":nested,
          "output_files":files,
          "expected_defect_reproduced":reproduced,
          "interpretation":"Real route/CLI produced nested scene output that bridge manifest failed to discover." if reproduced else "Baseline changed, route failed, or output assumptions need review."
        }
    receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(payload,indent=2)+"\n")
    print(json.dumps(payload,indent=2));return 0 if payload["expected_defect_reproduced"] else 1
if __name__=="__main__":raise SystemExit(main())
