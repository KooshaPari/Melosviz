#!/usr/bin/env python3
"""Generate real lossless media; attack the independent oracle. No product run."""
from __future__ import annotations
import argparse, copy, json, math, struct, subprocess, wave
from pathlib import Path
from oracle import evaluate, sha, VERSION

def encode(root, name, rgb, pcm):
    frame=root/f"{name}.rgb"; frame.write_bytes(rgb)
    wav=root/f"{name}.wav"
    with wave.open(str(wav),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(pcm)
    target=root/f"{name}.mkv"
    subprocess.run(["ffmpeg","-v","error","-y","-f","rawvideo","-pixel_format","rgb24",
        "-video_size","32x24","-framerate","12","-i",str(frame),"-i",str(wav),
        "-c:v","ffv1","-pix_fmt","bgr0","-c:a","pcm_s16le",str(target)],check=True,timeout=20)
    return target

def desc(rgb,pcm):
    return dict(width=32,height=24,fps="12",pts_tolerance_s="0.001",frames=len(rgb)//(32*24*3),sample_rate=48000,samples=len(pcm)//2,
                rgb_sha256=sha(rgb),pcm_sha256=sha(pcm))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",required=True,type=Path);args=ap.parse_args()
    root=args.out;root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()): raise ValueError("use a fresh output directory; preserve prior receipts")
    rgb_parts=[];pcm_parts=[];expected=[];actual=[]
    for i in range(3):
        # Time-varying grayscale marker: stable fixture content, not creative-quality proof.
        rgb=b"".join(bytes([30+i*70+f])*32*24*3 for f in range(12))
        pcm=b"".join(struct.pack("<h",round(8000*math.sin(2*math.pi*(330+i*220)*n/48000))) for n in range(48000))
        target=encode(root,f"S{i+1}",rgb,pcm);rgb_parts.append(rgb);pcm_parts.append(pcm)
        expected.append(dict(id=f"S{i+1}",revision="r1",backend="same-fixture-backend",**desc(rgb,pcm)))
        actual.append(dict(id=f"S{i+1}",revision="r1",mode="real-media",path=target.name,artifact_sha256=sha(target.read_bytes())))
    final=encode(root,"assembly",b"".join(rgb_parts),b"".join(pcm_parts))
    policy=dict(product="Melosviz-oracle-fixture-NOT-PRODUCT",project_revision="r1",contract="lossless-fixture-v1",
        candidate="oracle-selftest-not-product",configuration="ffv1-pcm-32x24-12fps",expected_run_id="selftest-r1",
        scenes=expected,assembly=desc(b"".join(rgb_parts),b"".join(pcm_parts)))
    receipt={k:policy[k] for k in ("product","project_revision","contract","candidate","configuration")}
    receipt.update(run_id="selftest-r1",collector_status="complete",scenes=actual,
        assembly=dict(state="assembled_unverified",path=final.name,artifact_sha256=sha(final.read_bytes())))
    cases=[]
    def check(name, r, expected_verdict="FAIL", p=None, **kw):
        result=evaluate(p or policy,r,root,**kw)
        cases.append(dict(case=name,expected=expected_verdict,actual=result["verdict"],matched=result["verdict"]==expected_verdict,errors=result["errors"]))
    check("real_three_scene_positive",receipt,"PASS")
    for field,value in [("candidate","wrong-sha"),("project_revision","r0"),("contract","weakened-policy"),("configuration","wrong-config"),("run_id","stale-run"),("collector_status","skipped")]:
        r=copy.deepcopy(receipt);r[field]=value;check(field,r)
    r=copy.deepcopy(receipt);r["scenes"].pop(1);check("missing_middle_scene",r)
    r=copy.deepcopy(receipt);r["scenes"][1]=copy.deepcopy(r["scenes"][0]);check("duplicate_scene_identity",r)
    r=copy.deepcopy(receipt);r["scenes"][0],r["scenes"][1]=r["scenes"][1],r["scenes"][0];check("reordered_receipts",r)
    r=copy.deepcopy(receipt);r["scenes"][1]["mode"]="offline-placeholder";check("placeholder_is_not_production",r)
    r=copy.deepcopy(receipt);r["assembly"]={"state":"plan_only"};check("plan_only_assembly",r)
    r=copy.deepcopy(receipt);r["scenes"][1]["artifact_sha256"]="0"*64;check("wrong_artifact_digest",r)
    bad=root/"garbage.mp4";bad.write_bytes(bytes(64))
    r=copy.deepcopy(receipt);r["scenes"][1].update(path=bad.name,artifact_sha256=sha(bad.read_bytes()));check("nonempty_garbage_mp4",r)
    r=copy.deepcopy(receipt);r["scenes"][1].update(path="S1.mkv",artifact_sha256=actual[0]["artifact_sha256"]);check("valid_wrong_scene_content",r)
    wrong=encode(root,"reordered-assembly",b"".join([rgb_parts[1],rgb_parts[0],rgb_parts[2]]),b"".join(pcm_parts))
    r=copy.deepcopy(receipt);r["assembly"].update(path=wrong.name,artifact_sha256=sha(wrong.read_bytes()));check("valid_media_wrong_assembly_order",r)
    wrongaudio=encode(root,"wrong-audio",b"".join(rgb_parts),b"".join(reversed(pcm_parts)))
    r=copy.deepcopy(receipt);r["assembly"].update(path=wrongaudio.name,artifact_sha256=sha(wrongaudio.read_bytes()));check("valid_video_wrong_audio",r)
    late=root/"late-presentation.mkv"
    subprocess.run(["ffmpeg","-v","error","-y","-i",str(final),"-vf","setpts=PTS+gte(N\\,18)*1/TB", "-fps_mode","passthrough","-c:v","ffv1","-pix_fmt","bgr0","-c:a","copy",str(late)],check=True,timeout=20)
    r=copy.deepcopy(receipt);r["assembly"].update(path=late.name,artifact_sha256=sha(late.read_bytes()));check("wrong_presentation_timeline",r)
    r=copy.deepcopy(receipt);r["scenes"][1]["path"]="../escape.mkv";check("path_escape",r)
    check("collector_missing",receipt,"BLOCKED",ffprobe="/nonexistent/verifier")
    check("empty_receipt",{})
    check("non_object_receipt",[])
    r=copy.deepcopy(receipt);r["scenes"]=[1,2,3];check("malformed_scene_rows",r)
    r=copy.deepcopy(receipt);r["assembly"]=[];check("malformed_assembly_record",r)
    lateaudio=root/"late-audio.mkv"
    subprocess.run(["ffmpeg","-v","error","-y","-i",str(final),"-itsoffset","0.5","-i",str(final),
        "-map","0:v:0","-map","1:a:0","-c","copy",str(lateaudio)],check=True,timeout=20)
    r=copy.deepcopy(receipt);r["assembly"].update(path=lateaudio.name,artifact_sha256=sha(lateaudio.read_bytes()));check("audio_PTS_offset",r)
    empty=copy.deepcopy(policy);empty["scenes"]=[];check("empty_trusted_denominator",receipt,p=empty)
    # R2: only S2 changes; independent policy must change too. Old receipt cannot qualify R2.
    updated=bytes([245])*32*24*3*12
    second=encode(root,"S2-r2",updated,pcm_parts[1]);r2final=encode(root,"assembly-r2",rgb_parts[0]+updated+rgb_parts[2],b"".join(pcm_parts))
    p2=copy.deepcopy(policy);p2["project_revision"]="r2";p2["expected_run_id"]="selftest-r2"
    p2["scenes"][1].update(revision="r2",**desc(updated,pcm_parts[1]));p2["assembly"]=desc(rgb_parts[0]+updated+rgb_parts[2],b"".join(pcm_parts))
    r2=copy.deepcopy(receipt);r2.update(project_revision="r2",run_id="selftest-r2")
    r2["scenes"][1].update(revision="r2",path=second.name,artifact_sha256=sha(second.read_bytes()))
    r2["assembly"].update(path=r2final.name,artifact_sha256=sha(r2final.read_bytes()))
    check("selective_S2_revision_positive",r2,"PASS",p=p2);check("stale_R1_cannot_qualify_R2",receipt,p=p2)
    (root/"policy.json").write_text(json.dumps(policy,indent=2));(root/"receipt.json").write_text(json.dumps(receipt,indent=2))
    (root/"policy-r2.json").write_text(json.dumps(p2,indent=2));(root/"receipt-r2.json").write_text(json.dumps(r2,indent=2))
    report=dict(verifier=VERSION,subject="ORACLE_SELFTEST_NOT_MELOSVIZ",cases=cases,
        expected_cases=len(cases),matched_cases=sum(c["matched"] for c in cases),
        product_e2e_executed=False,render_service_executed=False,
        limits="Lossless tiny media; no artistic/beat-detection/GUI/restart qualification. R2 tests identity rules, not product persistence.")
    (root/"selftest-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2));return 0 if all(c["matched"] for c in cases) else 1

if __name__=="__main__":raise SystemExit(main())
