from melosviz.analysis.models import RenderSpec
from melosviz.project_ledger import ProjectLedger,canonical_spec

def spec(marker="one"):
    return RenderSpec(metadata={"audio":"track.wav"},scene_segments=[
      {"scene_index":0,"scene_type":"video_export","marker":"zero"},
      {"scene_index":1,"scene_type":"video_export","marker":marker},
      {"scene_index":2,"scene_type":"video_export","marker":"two"},
    ])

def test_revision_roundtrip_survives_process_replacement(tmp_path):
    db=tmp_path/"project.sqlite"; l=ProjectLedger(db)
    r1=l.commit("P",spec()); assert r1==1; sha1=canonical_spec(spec())[1]; l.close()
    l=ProjectLedger(db); restored=l.load("P",r1); assert canonical_spec(restored)[1]==sha1
    r2=l.commit("P",spec("revised"),parent_revision=r1); assert r2==2; l.close()
    l=ProjectLedger(db); assert l.latest_revision("P")==2
    assert l.load("P",1).scene_segments[1]["marker"]=="one"
    assert l.load("P",2).scene_segments[1]["marker"]=="revised"

def test_unknown_parent_fails_before_revision_creation(tmp_path):
    l=ProjectLedger(tmp_path/"p.sqlite")
    try:l.commit("P",spec(),parent_revision=99)
    except ValueError:pass
    else:raise AssertionError("unknown parent accepted")
    assert l.latest_revision("P") is None

def test_digest_corruption_is_non_green(tmp_path):
    l=ProjectLedger(tmp_path/"p.sqlite"); r=l.commit("P",spec())
    with l.db:l.db.execute("UPDATE project_revision SET spec_json='{}' WHERE project_id='P' AND revision=?",(r,))
    try:l.load("P",r)
    except RuntimeError:pass
    else:raise AssertionError("corrupt persisted spec accepted")
