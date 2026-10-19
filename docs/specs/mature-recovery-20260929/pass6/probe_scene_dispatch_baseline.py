#!/usr/bin/env python3
"""Reproduce M-F21 on the frozen/recovery checkout using the real Orchestrator.

Exit 0 means the EXPECTED BASELINE DEFECT was observed; it is not a product green.
No production source is modified. A controlled adapter records what the mounted
orchestrator passes to each per-scene dispatch.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any

from melosviz.conductor.orchestrator import Orchestrator
from melosviz.conductor import registry as registry_mod

SCENE_TYPE="recovery_same_backend"

class CountingWholeSpecAdapter:
    scene_type=SCENE_TYPE
    calls:list[dict[str,Any]]=[]
    def __init__(self,*args,**kwargs): pass
    def render(self,render_spec:Any,*,output_path:Any=None,**kwargs:Any):
        if hasattr(render_spec,"model_dump"): data=render_spec.model_dump()
        elif isinstance(render_spec,dict): data=render_spec
        else: data={}
        scenes=data.get("scenes") or data.get("scene_segments") or []
        self.__class__.calls.append({
            "output_path":str(output_path),
            "scene_count_received":len(scenes),
            "scene_names":[str(x.get("name") or x.get("scene_name") or "") for x in scenes if isinstance(x,dict)],
        })
        return []

def main()->int:
    out=Path(os.environ.get("MELOSVIZ_RECOVERY_RECEIPT","dispatch-baseline.json"))
    spec={"version":2,"scene_segments":[
        {"scene_index":0,"scene_name":"S1","name":"S1","scene_type":SCENE_TYPE,"start":0.0,"end":1.0},
        {"scene_index":1,"scene_name":"S2","name":"S2","scene_type":SCENE_TYPE,"start":1.0,"end":2.0},
    ]}
    old=registry_mod.ADAPTER_REGISTRY.get(SCENE_TYPE)
    CountingWholeSpecAdapter.calls.clear()
    registry_mod.ADAPTER_REGISTRY[SCENE_TYPE]=CountingWholeSpecAdapter
    try:
        orch=Orchestrator(output_dir=out.parent/"dispatch-output",skip_assembly=True,auto_offline=False)
        result=orch.render(spec,scene_types=[SCENE_TYPE])
    finally:
        if old is None: registry_mod.ADAPTER_REGISTRY.pop(SCENE_TYPE,None)
        else: registry_mod.ADAPTER_REGISTRY[SCENE_TYPE]=old
    calls=CountingWholeSpecAdapter.calls
    reproduced=(len(calls)==2 and all(x["scene_count_received"]==2 for x in calls))
    payload={
      "subject":"M-F21_BASELINE_REPRODUCTION_NOT_ACCEPTANCE",
      "calls":calls,
      "call_count":len(calls),
      "per_scene_result_keys":sorted(result.per_scene_results.keys()),
      "expected_defect_reproduced":reproduced,
      "interpretation":"Per-scene orchestrator dispatch passed the whole two-scene spec to the adapter on each call." if reproduced else "Baseline behavior changed or probe assumptions failed."
    }
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2)+"\n")
    print(json.dumps(payload,indent=2))
    return 0 if reproduced else 1
if __name__=="__main__":raise SystemExit(main())
