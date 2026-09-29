#!/usr/bin/env python3
"""Pass-6 isolated counterexamples for frozen Melosviz source semantics.
These are copied logic fragments / source-structure checks, NOT a product E2E run.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

SOURCE="1aec20a2ba41a01ed557d1c7f63f9a0089f842cf"
ORCH_BLOB="549e70a5741f43546af3d068b5444d54d47affc2"
CACHE_BLOB="9a780c78dedd0201f59f8b47358313314f63201d"
PACKAGE_BLOB="8fc745cf3b3f09c6f997b132a686dbad131ce3f3"
CLI_BLOB="f5e3ff76da68779ba38be12874475fe5868d0975"

def _audio_fingerprint(scene: Mapping[str, Any]) -> str:
    audio = scene.get("audio") or scene.get("wav_path") or scene.get("audio_path")
    if audio is None or audio == "": return ""
    path = Path(str(audio))
    if path.is_file():
        h=hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""): h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    return f"path:{path.as_posix()}"

@dataclass(frozen=True)
class SceneCacheKey:
    backend:str;scene_type:str;prompt:str;seed:int;width:int;height:int;fps:int
    camera:str;camera_motion:str;subject_token:str;env_token:str;palette_key:str
    lrc_phrase_key:str;audio_fingerprint:str;extra:Mapping[str,Any]
    @staticmethod
    def from_scene(scene, backend_key, render_spec):
        continuity=scene.get("continuity") or {};lyric=scene.get("lyric") or {};palette=scene.get("palette") or []
        palette_list=[p.strip() for p in palette.split() if p.strip()] if isinstance(palette,str) else [str(p) for p in palette]
        seed=scene.get("seed");seed=0 if seed is None else seed
        return SceneCacheKey(backend_key,str(scene.get("scene_type","")),str(scene.get("prompt") or ""),int(seed),
            int(scene.get("width",getattr(render_spec,"width",1920) or 1920)),int(scene.get("height",getattr(render_spec,"height",1080) or 1080)),
            int(scene.get("fps",getattr(render_spec,"fps",24) or 24)),str(scene.get("camera") or ""),str(scene.get("camera_motion") or ""),
            str(continuity.get("subject_token") or ""),str(continuity.get("env_token") or ""),"|".join(palette_list),
            f"{lyric.get('phrase_id','')}::{lyric.get('start',0):.3f}->{lyric.get('end',0):.3f}",_audio_fingerprint(scene),copy.deepcopy(scene.get("cache_extra") or {}))
    def fingerprint(self):
        payload={"backend":self.backend,"scene_type":self.scene_type,"prompt":self.prompt,"seed":self.seed,"width":self.width,"height":self.height,
        "fps":self.fps,"camera":self.camera,"camera_motion":self.camera_motion,"subject_token":self.subject_token,"env_token":self.env_token,
        "palette_key":self.palette_key,"lrc_phrase_key":self.lrc_phrase_key,"audio_fingerprint":self.audio_fingerprint,"extra":dict(self.extra)}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def scene_cache_key(seg:dict, cache_root:Path):
    spec_proxy=type("_S",(),{"width":int(seg.get("width",1920) or 1920),"height":int(seg.get("height",1080) or 1080),"fps":int(seg.get("fps",24) or 24)})()
    backend=str(seg.get("backend") or seg.get("scene_type") or "unknown")
    key=SceneCacheKey.from_scene(seg,backend,spec_proxy)
    label=seg.get("scene_name") or seg.get("name") or seg.get("label")
    identity=f"{label if label is not None else ''}#{seg.get('scene_index')}"
    return replace(key,extra={**key.extra,"_scene_identity":identity})

MEDIA_PATTERNS=("*.mp4","*.mov","*.wav","*.aif","*.srt","*.vtt","*.edl")
EXCLUDED_PATH_PARTS=frozenset({".git","node_modules","__pycache__",".venv","venv","target",".pytest_cache",".mypy_cache",".ruff_cache","dist","build",".worktrees"})
MAX_DISCOVERY_DEPTH=6
def discover_media(job_dir:Path):
    excluded={job_dir/"final.zip",job_dir/".final.zip.tmp"};found=set();root=job_dir.resolve()
    for pattern in MEDIA_PATTERNS:
        for path in job_dir.rglob(pattern):
            if not path.is_file() or path in excluded: continue
            if "deliverables" in path.parts: continue
            if any(part in EXCLUDED_PATH_PARTS for part in path.parts): continue
            try: rel=path.relative_to(root)
            except ValueError: continue
            if len(rel.parts)>MAX_DISCOVERY_DEPTH: continue
            found.add(path)
    return sorted(found,key=lambda p:p.relative_to(job_dir).as_posix())

def discover_assemble(out_dir:Path):
    segment_paths=[]
    for sub in sorted(out_dir.iterdir()):
        if not sub.is_dir(): continue
        for f in sorted(sub.glob("*.mp4")): segment_paths.append(f)
        for f in sorted(sub.glob("*.mov")): segment_paths.append(f)
        for f in sorted(sub.rglob("clip.mp4")):
            if f not in segment_paths: segment_paths.append(f)
    return segment_paths

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    base={"scene_type":"comfyui_image","prompt":"same","seed":7,"scene_name":"S1","scene_index":0,
          "reference_image":"/refs/a.png","reference_image_strength":0.2,"model":"model-A","workflow":"wf-A",
          "continuity":{"subject_token":"alice","env_token":"city"}}
    variants={"reference_image":{**base,"reference_image":"/refs/b.png"},"reference_strength":{**base,"reference_image_strength":0.9},
              "model":{**base,"model":"model-B"},"workflow":{**base,"workflow":"wf-B"}}
    first=scene_cache_key(base,Path(".")).fingerprint()
    cache={k:scene_cache_key(v,Path(".")).fingerprint()==first for k,v in variants.items()}
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        intended=["comfyui_image/scene_000.mp4","comfyui_video/scene_001.mp4","comfyui_image/scene_002.mp4","comfyui_video/scene_003.mp4"]
        for rel in intended:
            p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"x")
        observed=[p.relative_to(root).as_posix() for p in discover_assemble(root)]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);p=root/"scene_001"/"garbage.mp4";p.parent.mkdir();p.write_bytes(bytes(64))
        media=discover_media(root);package_mode="online" if media else "offline"
        packaged=[x.relative_to(root).as_posix() for x in media]
    result={"schema_version":1,"source":SOURCE,"source_blobs":{"orchestrator":ORCH_BLOB,"render_cache":CACHE_BLOB,"package":PACKAGE_BLOB,"cli":CLI_BLOB},
      "cache_fingerprint_unchanged":cache,"cache_all_counterexamples_observed":all(cache.values()),
      "intended_timeline":intended,"assemble_discovery_order":observed,"assemble_reordered":observed!=intended,
      "garbage_media_packaging":{"bytes":64,"mode":package_mode,"discovered":packaged,"false_online":package_mode=="online"},
      "product_e2e_executed":False,"interpretation":"Diagnostic counterexamples observed; a successful diagnostic exit is NOT product acceptance."}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    return 0 if result["cache_all_counterexamples_observed"] and result["assemble_reordered"] and result["garbage_media_packaging"]["false_online"] else 1
if __name__=="__main__":raise SystemExit(main())
