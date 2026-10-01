import json
from melosviz.project_ledger import ProjectLedger
from melosviz.reviewer_promotion import apply_reviewer_receipt

def test_reviewer_receipt_promotes_only_matching_observed_bytes(tmp_path):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db)
    from melosviz.analysis.models import RenderSpec
    r=l.commit("P",RenderSpec(scene_segments=[])); a=l.start_attempt("P",r); l.finish_attempt(a,"J")
    s="a"*64; f="f"*64
    l.record_evidence(a,"scene",s,"conductor:scene:0","rejected")
    l.promote_scene_evidence(a,s,"precheck:v1")
    asm=l.freeze_assembly(a,[(0,s)]); l.complete_assembly(asm,f); l.close()
    receipt={"verdict":"PASS_REVIEWER_STRUCTURAL","observations":{"promotion_receipt":{"scene_artifacts":[{"scene_index":0,"sha256":s,"verifier":"reviewer-m-e02:v1"}],"final_artifact":{"sha256":f,"verifier":"reviewer-m-e02:v1"}}}}
    p=tmp_path/"receipt.json"; p.write_text(json.dumps(receipt))
    out=apply_reviewer_receipt(db,a,p); assert out["final_sha256"]==f
    l=ProjectLedger(db); assert l.db.execute("SELECT state FROM assembly_attempt WHERE id=?",(asm,)).fetchone()==("accepted",)

def test_reviewer_receipt_cannot_promote_unobserved_or_wrong_final_digest(tmp_path):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db)
    from melosviz.analysis.models import RenderSpec
    r=l.commit("P",RenderSpec(scene_segments=[])); a=l.start_attempt("P",r); l.finish_attempt(a,"J")
    s="a"*64; f="f"*64
    l.record_evidence(a,"scene",s,"conductor:scene:0","rejected")
    l.promote_scene_evidence(a,s,"precheck:v1"); asm=l.freeze_assembly(a,[(0,s)]); l.complete_assembly(asm,f); l.close()
    for scene_digest,final_digest in [("e"*64,f),(s,"e"*64)]:
        receipt={"verdict":"PASS_REVIEWER_STRUCTURAL","observations":{"promotion_receipt":{"scene_artifacts":[{"scene_index":0,"sha256":scene_digest,"verifier":"reviewer:v1"}],"final_artifact":{"sha256":final_digest,"verifier":"reviewer:v1"}}}}
        p=tmp_path/"r.json"; p.write_text(json.dumps(receipt))
        try:apply_reviewer_receipt(db,a,p)
        except RuntimeError:pass
        else:raise AssertionError((scene_digest,final_digest))
