#!/usr/bin/env python3
from __future__ import annotations
from result_contract import *

def art(ch,path):
    return ArtifactRef(ch*64,path,"video")

def real(id,rev,index,typ,ch):
    x=SceneExecution(SceneRef(id,rev,index,typ),f"a-{id}-{rev}",ExecutionOutcome.REAL_MEDIA,(art(ch,f"{id}.mkv"),))
    return x.independently_accept([f"ev-{id}-{rev}"])

def main():
    checks={}
    s1=real("S1",1,0,"same","1");s2=real("S2",1,1,"same","2");s3=real("S3",1,2,"other","3")
    r=OrchestratorResult([s1,s2,s3])
    checks["same_backend_preserves_three_scene_results"]=len(r.scenes)==3 and set(r.by_id())=={"S1","S2","S3"}
    checks["adapter_type_not_identity"]=s1.scene.scene_type==s2.scene.scene_type and s1.scene.scene_id!=s2.scene.scene_id
    inputs=r.accepted_inputs()
    a=AssemblyExecution("asm-r1",inputs,AssemblyState.ASSEMBLED_UNVERIFIED,art("a","final.mkv")).independently_accept(["asm-evidence"])
    checks["assembly_freezes_exact_order_and_identity"]=a.state==AssemblyState.ACCEPTED and [x[0] for x in a.inputs]==["S1","S2","S3"]
    # reorder changes index/order only, not scene/revision/artifact identity
    reordered=OrchestratorResult([
        replace(s2,scene=replace(s2.scene,index=0)),
        replace(s1,scene=replace(s1.scene,index=1)),
        s3,
    ])
    checks["reorder_preserves_identity_changes_assembly_order"]=[x.scene.scene_id for x in reordered.ordered()]==["S2","S1","S3"] and reordered.by_id()["S2"].scene.scene_revision==1
    # R2 changes only S2 scene revision; S1/S3 can remain exact accepted inputs
    s2r2=real("S2",2,1,"same","4");r2=OrchestratorResult([s1,s2r2,s3])
    checks["selective_revision_changes_only_S2"]=r2.by_id()["S1"]==s1 and r2.by_id()["S3"]==s3 and r2.by_id()["S2"].scene.scene_revision==2
    try:
        SceneExecution(SceneRef("P",1,0,"same"),"p",ExecutionOutcome.OFFLINE_PLACEHOLDER,(art("5","p.mkv"),)).independently_accept(["fake"])
        checks["placeholder_cannot_be_accepted"]=False
    except ValueError: checks["placeholder_cannot_be_accepted"]=True
    try:
        OrchestratorResult([s1,replace(s1,attempt_id="duplicate")]).by_id();checks["duplicate_scene_id_rejected"]=False
    except ValueError:checks["duplicate_scene_id_rejected"]=True
    try:
        OrchestratorResult([s1,SceneExecution(SceneRef("S2",1,1,"same"),"failed",ExecutionOutcome.FAILED)]).accepted_inputs();checks["assembly_cannot_consume_unaccepted_scene"]=False
    except ValueError:checks["assembly_cannot_consume_unaccepted_scene"]=True
    print(checks)
    return 0 if all(checks.values()) else 1
if __name__=="__main__":raise SystemExit(main())
