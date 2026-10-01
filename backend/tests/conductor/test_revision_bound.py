from pathlib import Path
from melosviz.analysis.models import RenderSpec
from melosviz.project_ledger import ProjectLedger,canonical_spec
from melosviz.conductor.revision_bound import RevisionBoundConductor

def _spec(marker):
    return RenderSpec(scene_segments=[{"scene_index":0,"scene_type":"fixture","marker":marker}])

def test_conductor_loads_exact_persisted_revision_after_reopen(tmp_path,monkeypatch):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db)
    r1=l.commit("P",_spec("R1")); r2=l.commit("P",_spec("R2"),parent_revision=r1); l.close()
    seen=[]
    class FakeOrchestrator:
        def __init__(self,**kwargs):pass
        def render(self,spec):
            seen.append(spec.scene_segments[0]["marker"])
            return type("R",(),{"job_id":"job-123"})()
    monkeypatch.setattr("melosviz.conductor.revision_bound.Orchestrator",FakeOrchestrator)
    c=RevisionBoundConductor(db)
    out=c.render_revision("P",r1)
    assert seen==["R1"]
    assert out.project_id=="P" and out.project_revision==r1
    assert out.project_attempt_id==1
    l=ProjectLedger(db); assert out.project_spec_sha256==canonical_spec(l.load("P",r1))[1]; l.close()
    c.render_revision("P",r2); assert seen==["R1","R2"]

def test_unknown_revision_fails_before_orchestrator_creation(tmp_path,monkeypatch):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db); l.commit("P",_spec("R1")); l.close()
    made=[]
    class Fake:
        def __init__(self,**kwargs):made.append(True)
    monkeypatch.setattr("melosviz.conductor.revision_bound.Orchestrator",Fake)
    try: RevisionBoundConductor(db).render_revision("P",99)
    except KeyError: pass
    else: raise AssertionError("unknown revision rendered")
    assert made==[]


def test_attempt_lifecycle_is_durable_and_bound_to_spec_digest(tmp_path,monkeypatch):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db); r=l.commit("P",_spec("R1")); expected=canonical_spec(l.load("P",r))[1]; l.close()
    class Fake:
        def __init__(self,**kwargs):pass
        def render(self,spec): return type("R",(),{"job_id":"J"})()
    monkeypatch.setattr("melosviz.conductor.revision_bound.Orchestrator",Fake)
    out=RevisionBoundConductor(db).render_revision("P",r)
    l=ProjectLedger(db)
    row=l.db.execute("SELECT project_revision,spec_sha256,state,job_id FROM render_attempt WHERE id=?",(out.project_attempt_id,)).fetchone()
    assert row==(r,expected,"completed","J")
    l.close()

def test_failed_conductor_attempt_is_durable(tmp_path,monkeypatch):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db); r=l.commit("P",_spec("R1")); l.close()
    class Boom:
        def __init__(self,**kwargs):pass
        def render(self,spec): raise RuntimeError("renderer failed")
    monkeypatch.setattr("melosviz.conductor.revision_bound.Orchestrator",Boom)
    try: RevisionBoundConductor(db).render_revision("P",r)
    except RuntimeError as e: assert "renderer failed" in str(e)
    else: raise AssertionError("renderer failure swallowed")
    l=ProjectLedger(db)
    assert l.db.execute("SELECT state FROM render_attempt").fetchone()==("failed",)
    l.close()


def test_attempt_evidence_and_assembly_lineage_are_bound_to_completed_attempt(tmp_path,monkeypatch):
    db=tmp_path/"p.sqlite"; l=ProjectLedger(db); r=l.commit("P",_spec("R1")); l.close()
    class Fake:
        def __init__(self,**kwargs):pass
        def render(self,spec): return type("R",(),{"job_id":"J"})()
    monkeypatch.setattr("melosviz.conductor.revision_bound.Orchestrator",Fake)
    out=RevisionBoundConductor(db).render_revision("P",r)
    l=ProjectLedger(db)
    l.record_evidence(out.project_attempt_id,"scene","abc","reviewer:v1","accepted")
    asm=l.freeze_assembly(out.project_attempt_id,[(0,"abc")])
    assert l.db.execute("SELECT state,ordered_inputs_json FROM assembly_attempt WHERE id=?",(asm,)).fetchone()==("frozen",'[[0,"abc"]]')
    assert l.db.execute("SELECT verifier,state FROM attempt_evidence WHERE attempt_id=?",(out.project_attempt_id,)).fetchone()==("reviewer:v1","accepted")

def test_failed_or_running_attempt_cannot_freeze_assembly(tmp_path):
    l=ProjectLedger(tmp_path/"p.sqlite"); r=l.commit("P",_spec("R1")); a=l.start_attempt("P",r)
    try:l.freeze_assembly(a,[(0,"abc")])
    except RuntimeError:pass
    else:raise AssertionError("running attempt froze assembly")
    l.fail_attempt(a)
    try:l.freeze_assembly(a,[(0,"abc")])
    except RuntimeError:pass
    else:raise AssertionError("failed attempt froze assembly")
