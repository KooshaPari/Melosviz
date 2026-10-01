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
    receipt={"verdict":"PASS_REVIEWER_STRUCTURAL","candidate":"candidate-sha","observations":{"promotion_receipt":{"project_revision":"R1","scene_artifacts":[{"scene_index":0,"sha256":s,"verifier":"reviewer-m-e02:v1"}],"final_artifact":{"sha256":f,"verifier":"reviewer-m-e02:v1"}}}}
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
        receipt={"verdict":"PASS_REVIEWER_STRUCTURAL","observations":{"promotion_receipt":{"project_revision":"R1","scene_artifacts":[{"scene_index":0,"sha256":scene_digest,"verifier":"reviewer:v1"}],"final_artifact":{"sha256":final_digest,"verifier":"reviewer:v1"}}}}
        p=tmp_path/"r.json"; p.write_text(json.dumps(receipt))
        try:apply_reviewer_receipt(db,a,p)
        except RuntimeError:pass
        else:raise AssertionError((scene_digest,final_digest))


def test_real_shaped_reviewer_receipt_roundtrip_to_attempt_and_final_acceptance(tmp_path):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db)
    from melosviz.analysis.models import RenderSpec
    r=l.commit("P",RenderSpec(scene_segments=[])); a=l.start_attempt("P",r); l.finish_attempt(a,"J")
    scene_bytes=b"scene-real"; final_bytes=b"final-real"
    import hashlib
    s=hashlib.sha256(scene_bytes).hexdigest(); f=hashlib.sha256(final_bytes).hexdigest()
    l.record_evidence(a,"scene",s,"conductor:scene:0","rejected")
    l.promote_scene_evidence(a,s,"precheck:v1")
    asm=l.freeze_assembly(a,[(0,s)]); l.complete_assembly(asm,f); l.close()
    receipt={
      "verdict":"PASS_REVIEWER_STRUCTURAL",
      "candidate":"candidate-sha",
      "checks":{"media":True},
      "observations":{"promotion_receipt":{
        "project_revision":"R1",
        "scene_artifacts":[{"scene_index":0,"sha256":s,"verifier":"reviewer-m-e02:v1"}],
        "final_artifact":{"sha256":f,"verifier":"reviewer-m-e02:v1"}}}}
    p=tmp_path/"reviewer-evidence.json"; p.write_text(json.dumps(receipt))
    applied=apply_reviewer_receipt(db,a,p)
    assert applied=={"attempt_id":a,"scene_digests":[s],"assembly_id":asm,"final_sha256":f}
    l=ProjectLedger(db)
    assert l.db.execute("SELECT state FROM assembly_attempt WHERE id=?",(asm,)).fetchone()==("accepted",)
    assert l.db.execute("SELECT COUNT(*) FROM attempt_evidence WHERE attempt_id=? AND state='accepted'",(a,)).fetchone()[0]>=2


def test_reviewer_candidate_must_match_durable_attempt(tmp_path):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db)
    from melosviz.analysis.models import RenderSpec
    r=l.commit("P",RenderSpec(scene_segments=[])); a=l.start_attempt("P",r,"actual-sha"); l.finish_attempt(a,"J")
    s="a"*64; f="f"*64
    l.record_evidence(a,"scene",s,"conductor","rejected"); l.promote_scene_evidence(a,s,"precheck")
    asm=l.freeze_assembly(a,[(0,s)]); l.complete_assembly(asm,f); l.close()
    receipt={"verdict":"PASS_REVIEWER_STRUCTURAL","candidate":"wrong-sha","observations":{"promotion_receipt":{"project_revision":"R1","scene_artifacts":[{"scene_index":0,"sha256":s,"verifier":"reviewer"}],"final_artifact":{"sha256":f,"verifier":"reviewer"}}}}
    p=tmp_path/"r.json"; p.write_text(json.dumps(receipt))
    try:apply_reviewer_receipt(db,a,p)
    except RuntimeError as e: assert "candidate" in str(e)
    else:raise AssertionError("wrong candidate reviewer receipt accepted")


def test_reviewer_revision_must_match_durable_attempt(tmp_path):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db)
    from melosviz.analysis.models import RenderSpec
    r1=l.commit("P",RenderSpec(scene_segments=[])); r2=l.commit("P",RenderSpec(scene_segments=[]),parent_revision=r1)
    a=l.start_attempt("P",r2,"candidate-sha"); l.finish_attempt(a,"J")
    s="a"*64; f="f"*64
    l.record_evidence(a,"scene",s,"conductor","rejected"); l.promote_scene_evidence(a,s,"precheck")
    asm=l.freeze_assembly(a,[(0,s)]); l.complete_assembly(asm,f); l.close()
    receipt={"verdict":"PASS_REVIEWER_STRUCTURAL","candidate":"candidate-sha","observations":{"promotion_receipt":{"project_revision":"R1","scene_artifacts":[{"scene_index":0,"sha256":s,"verifier":"reviewer"}],"final_artifact":{"sha256":f,"verifier":"reviewer"}}}}
    p=tmp_path/"r.json"; p.write_text(json.dumps(receipt))
    try:apply_reviewer_receipt(db,a,p)
    except RuntimeError as e: assert "revision" in str(e)
    else:raise AssertionError("stale revision reviewer receipt accepted")
