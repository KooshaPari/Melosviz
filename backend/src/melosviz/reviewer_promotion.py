"""Apply an independent reviewer receipt to an existing M-E03 attempt.

The receipt cannot invent bytes: every promoted scene digest must already exist
as a candidate observation for the exact attempt. Final assembly acceptance is
likewise digest-bound to a completed assembly row.
"""
from __future__ import annotations
import json
from pathlib import Path
from .project_ledger import ProjectLedger

def apply_reviewer_receipt(ledger_path:Path|str,attempt_id:int,receipt_path:Path|str)->dict:
    receipt=json.loads(Path(receipt_path).read_text())
    if not str(receipt.get("verdict","")).startswith("PASS"):
        raise RuntimeError("reviewer receipt is not passing")
    promotion=(receipt.get("observations") or {}).get("promotion_receipt") or {}
    scenes=promotion.get("scene_artifacts") or []
    final=promotion.get("final_artifact") or {}
    if not scenes or not final.get("sha256"):
        raise RuntimeError("reviewer receipt lacks promotion evidence")
    ledger=ProjectLedger(Path(ledger_path))
    promoted=[]
    try:
        for scene in scenes:
            digest=scene["sha256"]; verifier=scene["verifier"]
            ledger.promote_scene_evidence(attempt_id,digest,verifier)
            promoted.append(digest)
        assembly=ledger.db.execute(
            "SELECT id,artifact_sha256,state FROM assembly_attempt WHERE render_attempt_id=? ORDER BY id DESC LIMIT 1",
            (attempt_id,),
        ).fetchone()
        if not assembly or assembly[2]!="completed":
            raise RuntimeError("no completed assembly for reviewer promotion")
        if assembly[1] != final["sha256"]:
            raise RuntimeError("reviewer final digest does not match completed assembly")
        ledger.accept_assembly(assembly[0],final["sha256"],final["verifier"])
        return {"attempt_id":attempt_id,"scene_digests":promoted,"assembly_id":assembly[0],"final_sha256":final["sha256"]}
    finally:
        ledger.close()
