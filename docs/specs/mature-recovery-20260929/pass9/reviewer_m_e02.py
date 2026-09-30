#!/usr/bin/env python3
"""Reviewer-owned mounted M-E02 grader for an EXACT candidate checkout.
This is structural product evidence, not creative-quality acceptance.
"""
from __future__ import annotations
import argparse, hashlib, json, os, struct, subprocess, sys, tempfile, wave
from pathlib import Path

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False, **kw)

def probe(path: Path):
    if not path.is_file() or path.stat().st_size <= 0: raise AssertionError(f"missing/empty {path}")
    p=run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)])
    if p.returncode: raise AssertionError(p.stderr)
    j=json.loads(p.stdout); streams=j.get("streams") or []
    if not any(s.get("codec_type")=="video" for s in streams): raise AssertionError(f"no video {path}")
    return {"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"size":path.stat().st_size,
            "duration":float((j.get("format") or {}).get("duration") or 0)}

def wav(path:Path):
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        for i in range(8000):w.writeframesraw(struct.pack("<h",((i%80)-40)*300))

def storyboard(path:Path,prompt1="scene one"):
    path.write_text(json.dumps({"concept":"reviewer M-E02","seed":17,"scenes":[
      {"index":0,"name":"s0","start":0.0,"end":0.5,"scene_type":"video_export","prompt":"scene zero","palette":["#ff0000"]},
      {"index":1,"name":"s1","start":0.5,"end":1.0,"scene_type":"video_export","prompt":prompt1,"palette":["#0000ff"]}]},indent=2))

def cli(candidate:Path,w:Path,sb:Path,out:Path,only=None):
    env=os.environ.copy();env["PYTHONPATH"]=str(candidate/"backend");env.pop("MELOSVIZ_COMFYUI_OFFLINE",None)
    cmd=[sys.executable,"-m","melosviz.cli.main","generate",str(w),"--storyboard",str(sb),"--out",str(out),"--job-id","reviewer-m-e02"]
    if only is not None:cmd += ["--only-scenes",str(only)]
    p=run(cmd,cwd=candidate,env=env)
    if p.returncode:raise AssertionError(f"CLI failed\n{p.stdout}\n{p.stderr}")
    return json.loads(p.stdout)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--candidate",type=Path,required=True);ap.add_argument("--expected-sha",required=True);ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    candidate=a.candidate.resolve()
    got=run(["git","rev-parse","HEAD"],cwd=candidate).stdout.strip()
    if got!=a.expected_sha:raise SystemExit(f"wrong candidate {got} != {a.expected_sha}")
    result={"candidate":got,"subject":"REVIEWER_OWNED_M_E02_MOUNTED_STRUCTURE","checks":{}}
    with tempfile.TemporaryDirectory(prefix="m-e02-reviewer-") as td:
        root=Path(td);w=root/"track.wav";sb=root/"storyboard.json";out=root/"out";wav(w);storyboard(sb)
        r1=cli(candidate,w,sb,out)
        scenes=r1.get("scenes") or []
        assert r1.get("dispatched_scenes")==[0,1],r1
        assert [x.get("scene_index") for x in scenes]==[0,1],scenes
        assert [x.get("outcome") for x in scenes]==["render","render"],scenes
        p1=[Path(x["artifact_path"]).resolve() for x in scenes]
        assert len(set(p1))==2 and all(x.is_relative_to(out.resolve()) for x in p1)
        scene_obs=[probe(x) for x in p1]
        assembly=out/"assembly"/"melosviz-assembled.mp4";a1=probe(assembly)
        assert r1.get("assembly_state")=="produced_unverified",r1
        result["checks"]["r1_two_scene_real_media"]=True

        # Held-out producer-identity mutation. The candidate's own tests know
        # about this contract, so the reviewer independently corrupts the
        # stored producer identity and requires an unchanged selected scene to
        # render again rather than laundering the stale cache entry.
        cache_meta=list((out/"_render_cache").glob("*.json"))
        scene0_meta=None
        for meta_path in cache_meta:
            meta=json.loads(meta_path.read_text())
            if meta.get("scene_index")==0 and meta.get("outcome")=="render":
                scene0_meta=(meta_path,meta)
                break
        assert scene0_meta is not None,cache_meta
        meta_path,meta=scene0_meta
        assert meta.get("backend_identity"),meta
        accepted_identity=meta["backend_identity"]
        meta["backend_identity"]="reviewer:stale-producer"
        meta_path.write_text(json.dumps(meta,indent=2)+"\n")
        stale=cli(candidate,w,sb,out,0)
        stale_scenes=stale.get("scenes") or []
        assert stale.get("dispatched_scenes")==[0],stale
        assert len(stale_scenes)==1 and stale_scenes[0].get("scene_index")==0,stale_scenes
        assert stale_scenes[0].get("outcome")=="render",stale_scenes
        repaired=json.loads(meta_path.read_text())
        assert repaired.get("backend_identity")==accepted_identity,repaired
        result["checks"]["stale_producer_identity_forces_rerender"]=True

        # New process + selected S1. Prompt is a declared cache input.
        storyboard(sb,"scene one revised")
        r2=cli(candidate,w,sb,out,1)
        assert r2.get("dispatched_scenes")==[1],r2
        assert r2.get("only_scenes")==[1],r2
        a2=probe(assembly)
        assert a2["duration"]>1.5,(r2,a2)
        result["checks"]["r2_selected_scene_full_timeline"]=True
        # R2 must not merely be valid media; the final assembly must differ from
        # R1 after the declared scene edit, otherwise selective rerender/reassembly
        # may have laundered stale final output.
        assert a2["sha256"] != a1["sha256"], (a1, a2)
        result["checks"]["r2_final_digest_changed"]=True
        result["observations"]={"r1_scenes":scene_obs,"r1_assembly":a1,"r2_assembly":a2}
        # Wrong selector must fail before claiming product output.
        env=os.environ.copy();env["PYTHONPATH"]=str(candidate/"backend")
        bad=run([sys.executable,"-m","melosviz.cli.main","generate",str(w),"--storyboard",str(sb),"--out",str(root/"bad"),"--only-scenes","99"],cwd=candidate,env=env)
        assert bad.returncode!=0,(bad.stdout,bad.stderr)
        result["checks"]["invalid_selector_non_green"]=True
    result["verdict"]="PASS_REVIEWER_STRUCTURAL" if all(result["checks"].values()) else "FAIL"
    a.out.write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,indent=2))
    return 0 if result["verdict"].startswith("PASS") else 1
if __name__=="__main__":raise SystemExit(main())
