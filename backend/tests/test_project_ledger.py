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


def test_existing_v1_render_attempt_schema_migrates_without_losing_rows(tmp_path):
    import sqlite3
    db=tmp_path/"legacy.sqlite"
    c=sqlite3.connect(db)
    c.executescript("""
      PRAGMA foreign_keys=OFF;
      CREATE TABLE project(id TEXT PRIMARY KEY, created_at REAL NOT NULL);
      CREATE TABLE project_revision(project_id TEXT NOT NULL,revision INTEGER NOT NULL,parent_revision INTEGER,spec_sha256 TEXT NOT NULL,spec_json TEXT NOT NULL,created_at REAL NOT NULL,PRIMARY KEY(project_id,revision));
      CREATE TABLE render_attempt(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,project_revision INTEGER NOT NULL,spec_sha256 TEXT NOT NULL,state TEXT NOT NULL,job_id TEXT,started_at REAL NOT NULL,completed_at REAL);
      INSERT INTO project VALUES('P',1);
      INSERT INTO project_revision VALUES('P',1,NULL,'abc','{}',1);
      INSERT INTO render_attempt(project_id,project_revision,spec_sha256,state,job_id,started_at,completed_at) VALUES('P',1,'abc','completed','J',1,2);
    """)
    c.commit(); c.close()
    l=ProjectLedger(db)
    assert l.schema_version()==2
    assert "candidate_sha" in {row[1] for row in l.db.execute("PRAGMA table_info(render_attempt)")}
    assert l.db.execute("SELECT job_id,candidate_sha FROM render_attempt WHERE id=1").fetchone()==("J",None)
