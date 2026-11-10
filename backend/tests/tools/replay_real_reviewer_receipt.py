"""Replay a real reviewer promotion receipt through the durable M-E03 ledger.

This witness intentionally uses no renderer. It proves that the exact independent
M-E02 receipt can be bound to a persisted R2 attempt, pre-observed scene bytes,
a completed assembly digest, and then atomically promoted after restart.
"""
from __future__ import annotations
import argparse, json, tempfile
from pathlib import Path
from melosviz.analysis.models import RenderSpec
from melosviz.project_ledger import ProjectLedger
from melosviz.reviewer_promotion import apply_reviewer_receipt

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--receipt",required=True); ap.add_argument("--candidate",required=True)
    a=ap.parse_args(); receipt=json.loads(Path(a.receipt).read_text())
    if receipt.get("candidate") != a.candidate: raise RuntimeError("receipt candidate mismatch")
    promotion=receipt["observations"]["promotion_receipt"]
    with tempfile.TemporaryDirectory(prefix="m-e03-real-receipt-") as td:
        db=Path(td)/"project.sqlite"
        scenes=[{"scene_index":s["scene_index"],"scene_type":"reviewer_fixture"} for s in promotion["scene_artifacts"]]
        l=ProjectLedger(db)
        r1=l.commit("P",RenderSpec(scene_segments=scenes))
        r2=l.commit("P",RenderSpec(scene_segments=scenes),parent_revision=r1)
        attempt=l.start_attempt("P",r2,a.candidate); l.finish_attempt(attempt,"held-out-reviewer")
        ordered=[]
        for s in promotion["scene_artifacts"]:
            l.record_evidence(attempt,"scene",s["sha256"],f"candidate-observation:{s['scene_index']}","rejected")
            # A pre-assembly verifier has independently accepted the scene bytes;
            # final reviewer promotion will add its own authority record.
            l.promote_scene_evidence(attempt,s["sha256"],"preassembly-review:v1")
            ordered.append((s["scene_index"],s["sha256"]))
        asm=l.freeze_assembly(attempt,ordered)
        l.complete_assembly(asm,promotion["final_artifact"]["sha256"])
        l.close()
        # Restart boundary before consuming the external receipt.
        result=apply_reviewer_receipt(db,attempt,a.receipt)
        l=ProjectLedger(db)
        assert l.db.execute("SELECT state FROM assembly_attempt WHERE id=?",(asm,)).fetchone()==("accepted",)
        assert l.db.execute("SELECT COUNT(*) FROM attempt_evidence WHERE attempt_id=? AND verifier='reviewer-m-e02:v1' AND state='accepted'",(attempt,)).fetchone()[0]==len(scenes)+1
        l.close()
        print(json.dumps(result,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
