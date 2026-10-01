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
    candidate=receipt.get("candidate")
    if not candidate: raise RuntimeError("reviewer receipt lacks candidate identity")
    promotion=(receipt.get("observations") or {}).get("promotion_receipt") or {}
    receipt_revision=promotion.get("project_revision")
    if receipt_revision is None: raise RuntimeError("reviewer receipt lacks project revision")
    scenes=promotion.get("scene_artifacts") or []
    final=promotion.get("final_artifact") or {}
    if not scenes or not final.get("sha256"):
        raise RuntimeError("reviewer receipt lacks promotion evidence")
    ledger=ProjectLedger(Path(ledger_path))
    promoted=[]
    try:
        attempt=ledger.db.execute("SELECT candidate_sha,project_revision FROM render_attempt WHERE id=?",(attempt_id,)).fetchone()
        if not attempt: raise RuntimeError("unknown render attempt")
        if attempt[0] is None:
            raise RuntimeError("render attempt lacks candidate identity")
        if attempt[0] != candidate:
            raise RuntimeError("reviewer candidate does not match render attempt")
        normalized_revision=str(receipt_revision).removeprefix("R")
        if normalized_revision != str(attempt[1]):
            raise RuntimeError("reviewer revision does not match render attempt")
        # Validate the complete receipt before mutating any acceptance state.
        for scene in scenes:
            digest=scene["sha256"]; verifier=scene["verifier"]
            if not verifier.strip(): raise RuntimeError("scene verifier identity missing")
            observed=ledger.db.execute(
                "SELECT 1 FROM attempt_evidence WHERE attempt_id=? AND kind='scene' AND artifact_sha256=? AND state='rejected'",
                (attempt_id,digest),
            ).fetchone()
            if not observed: raise RuntimeError("reviewer scene digest was not observed by candidate")
        assembly=ledger.db.execute(
            "SELECT id,artifact_sha256,state FROM assembly_attempt WHERE render_attempt_id=? ORDER BY id DESC LIMIT 1",
            (attempt_id,),
        ).fetchone()
        if not assembly or assembly[2]!="completed":
            raise RuntimeError("no completed assembly for reviewer promotion")
        if assembly[1] != final["sha256"]:
            raise RuntimeError("reviewer final digest does not match completed assembly")
        if not str(final.get("verifier","")).strip():
            raise RuntimeError("final verifier identity missing")
        with ledger.db:
            for scene in scenes:
                digest=scene["sha256"]; verifier=scene["verifier"]
                ledger.db.execute(
                    "INSERT INTO attempt_evidence(attempt_id,kind,artifact_sha256,verifier,state,created_at) VALUES(?,?,?,?,?,?)",
                    (attempt_id,"scene",digest,verifier,"accepted",__import__("time").time()),
                )
                promoted.append(digest)
            ledger.db.execute("UPDATE assembly_attempt SET state='accepted' WHERE id=? AND state='completed'",(assembly[0],))
            ledger.db.execute(
                "INSERT INTO attempt_evidence(attempt_id,kind,artifact_sha256,verifier,state,created_at) VALUES(?,?,?,?,?,?)",
                (attempt_id,"assembly",final["sha256"],final["verifier"],"accepted",__import__("time").time()),
            )
        return {"attempt_id":attempt_id,"scene_digests":promoted,"assembly_id":assembly[0],"final_sha256":final["sha256"]}
    finally:
        ledger.close()
