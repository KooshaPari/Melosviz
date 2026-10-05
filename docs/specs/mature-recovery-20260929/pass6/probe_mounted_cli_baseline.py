#!/usr/bin/env python3
"""Mounted frozen-baseline probe for M-F09/M-F10.

Success means the EXPECTED DEFECT was reproduced; it is not product acceptance.
Run only against the frozen/recovery baseline, never reinterpret exit 0 as green.
"""
from __future__ import annotations
import hashlib, json, os, pathlib, struct, subprocess, sys, tempfile, wave

EXPECTED_SOURCE = "1aec20a2ba41a01ed557d1c7f63f9a0089f842cf"

def write_wav(path: pathlib.Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        frames=b"".join(struct.pack("<h", 3000 if (i//400)%2 else -3000) for i in range(8000))
        w.writeframes(frames)

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mv-mounted-baseline-") as td:
        root=pathlib.Path(td); wav=root/"fixture.wav"; write_wav(wav)
        sb=root/"storyboard.json"
        scenes=[
            {"scene_index":0,"scene_name":"S1","name":"S1","scene_type":"video_export","start":0.0,"end":0.5,"prompt":"RECOVERY-S1"},
            {"scene_index":1,"scene_name":"S2","name":"S2","scene_type":"video_export","start":0.5,"end":1.0,"prompt":"RECOVERY-S2"},
        ]
        sb.write_text(json.dumps({"concept":"recovery fixture","seed":7,"scenes":scenes}),encoding="utf-8")
        out=root/"out"
        env=os.environ.copy()
        env["MELOSVIZ_COMFYUI_OFFLINE"]="1"
        p=subprocess.run(
            [sys.executable,"-m","melosviz.cli.main","generate",str(wav),"--storyboard",str(sb),"--out",str(out),"--job-id","recovery-mount-r1"],
            env=env,capture_output=True,text=True,timeout=120,check=False,
        )
        payload=None
        try:
            payload=json.loads(p.stdout)
        except Exception:
            pass
        spec_path=out/"assembly"/"ame_batch_job.json"
        assembly_spec=json.loads(spec_path.read_text()) if spec_path.is_file() else None
        sidecars=sorted(str(x.relative_to(out)) for x in out.rglob("*.provenance.json")) if out.exists() else []
        media=sorted(str(x.relative_to(out)) for ext in ("*.mp4","*.mov","*.wav") for x in out.rglob(ext)) if out.exists() else []
        observation={
            "subject":"MOUNTED_CLI_BASELINE_DEFECT_REPRODUCTION_NOT_ACCEPTANCE",
            "expected_source":EXPECTED_SOURCE,
            "command_exit":p.returncode,
            "stdout":p.stdout,
            "stderr_tail":p.stderr[-4000:],
            "parsed_summary":payload,
            "assembly_job_spec_exists":spec_path.is_file(),
            "assembly_segment_count":(assembly_spec or {}).get("melosviz_meta",{}).get("segment_count"),
            "sidecars":sidecars,
            "media":media,
            "storyboard_sha256":hashlib.sha256(sb.read_bytes()).hexdigest(),
            "wav_sha256":hashlib.sha256(wav.read_bytes()).hexdigest(),
        }
        reproduced=(
            p.returncode==0
            and isinstance(payload,dict)
            and payload.get("assembly_ok") is True
            and payload.get("dispatched_scenes")==["video_export"]
            and spec_path.is_file()
            and observation["assembly_segment_count"]==0
        )
        observation["expected_false_green_reproduced"]=reproduced
        dest=pathlib.Path(os.environ.get("MELOSVIZ_RECOVERY_RECEIPT","mounted-cli-baseline.json"))
        dest.write_text(json.dumps(observation,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(observation,indent=2))
        return 0 if reproduced else 1

if __name__=="__main__":
    raise SystemExit(main())
