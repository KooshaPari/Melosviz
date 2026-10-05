#!/usr/bin/env python3
"""Fail-closed integrity checks for mature-recovery metadata.

This checks recovery bookkeeping only, not product correctness.
"""
from __future__ import annotations
import argparse,json,re
from pathlib import Path

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path("docs/specs/mature-recovery-20260929"))
    p.add_argument("--prefix",required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args();root=a.root
    findings=(root/"FINDINGS.md").read_text(encoding="utf-8")
    state=load(root/"CURRENT-STATE.json");dag=load(root/"EXPERIMENTAL-WORK-DAG.json")
    ids=re.findall(r"^## ("+re.escape(a.prefix)+r"\d+)\b",findings,re.M)
    seen=set();dups=[]
    for x in ids:
        if x in seen and x not in dups:dups.append(x)
        seen.add(x)
    refs=[x for x in state.get("blocking_findings",[]) if isinstance(x,str) and re.fullmatch(re.escape(a.prefix)+r"\d+",x)]
    missing=[x for x in refs if x not in seen]
    ready_state=sorted(state.get("ready_work_packages",[]))
    ready_dag=sorted(n["id"] for n in dag.get("nodes",[]) if n.get("state") in {"READY","READY_IN_PROGRESS"})
    checks={
      "finding_ids_unique":not dups,
      "blocking_refs_resolve":not missing,
      "ready_work_packages_match_dag":ready_state==ready_dag,
    }
    inventory={}
    A=root/"inventory/TRACKED-TREE-A.json";B=root/"inventory/TRACKED-TREE-B.json";S=root/"inventory/SUMMARY.json"
    if A.exists() and B.exists():
        rows=load(A).get("rows",[])+load(B).get("rows",[])
        raw=len(rows);by={}
        for row in rows:by.setdefault(row["path"],[]).append(row)
        unique=len(by);overlap=sum(1 for v in by.values() if len(v)>1)
        extra=raw-unique
        conflicts=sum(1 for v in by.values() if len({r["object_id"] for r in v})>1)
        inventory={"raw_rows":raw,"unique_paths":unique,"overlap_paths":overlap,"overlap_extra_rows":extra,"object_id_conflicts":conflicts}
        checks["inventory_has_no_object_conflicts"]=conflicts==0
        if S.exists():
            summary=load(S)
            if "raw_inventory_rows" in summary: checks["summary_raw_matches"]=summary["raw_inventory_rows"]==raw
            if "unique_inventory_paths" in summary: checks["summary_unique_matches"]=summary["unique_inventory_paths"]==unique
            if "overlap_paths_between_parts" in summary: checks["summary_overlap_matches"]=summary["overlap_paths_between_parts"]==overlap
            if "exact_blob_inventory_rows" in summary: checks["legacy_summary_exact_rows_matches_raw"]=summary["exact_blob_inventory_rows"]==raw
        inv_state=state.get("tracked_product_relevant_inventory",{})
        if "raw_rows" in inv_state: checks["state_raw_matches"]=inv_state["raw_rows"]==raw
        if "unique_blobs" in inv_state: checks["state_unique_matches"]=inv_state["unique_blobs"]==unique
    result={"subject":"RECOVERY_METADATA_INTEGRITY_NOT_PRODUCT_ACCEPTANCE","prefix":a.prefix,
      "finding_count":len(ids),"duplicates":dups,"missing_blocking_refs":missing,
      "ready_state":ready_state,"ready_dag":ready_dag,"inventory":inventory,
      "checks":checks,"pass":all(checks.values())}
    out=json.dumps(result,indent=2)+"\n"
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(out,encoding="utf-8")
    print(out,end="");return 0 if result["pass"] else 1
if __name__=="__main__":raise SystemExit(main())
