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
            return type("R",(),{})()
    monkeypatch.setattr("melosviz.conductor.revision_bound.Orchestrator",FakeOrchestrator)
    c=RevisionBoundConductor(db)
    out=c.render_revision("P",r1)
    assert seen==["R1"]
    assert out.project_id=="P" and out.project_revision==r1
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
