from pathlib import Path
import importlib.util

P=Path(__file__).parents[1]/"experiments"/"mature_recovery_durable_ledger.py"
spec=importlib.util.spec_from_file_location("ledger",P); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def scenes(mid="one"):
    return [
      {"scene_id":"S1","prompt":"zero","backend":"fixture:v1"},
      {"scene_id":"S2","prompt":mid,"backend":"fixture:v1"},
      {"scene_id":"S3","prompt":"two","backend":"fixture:v1"},
    ]

def accepted(l,pid,rev,sid,artifact):
    path=l.path.parent/f"{pid}-{rev}-{sid}-{artifact}.bin"
    path.write_bytes(artifact.encode())
    sha=m.hashlib.sha256(path.read_bytes()).hexdigest()
    a=l.queue(pid,rev,sid); assert l.claim(a,"worker-a"); l.execute(a,sha,str(path)); l.accept(a,"oracle:v1",sha); return a

def test_r1_restart_r2_selective_reuse_and_immutable_history(tmp_path):
    db=tmp_path/"state.sqlite"; l=m.Ledger(db); l.create_project("P")
    r1=l.author_revision("P",scenes())
    a1=accepted(l,"P",r1,"S1","A1"); a2=accepted(l,"P",r1,"S2","A2"); a3=accepted(l,"P",r1,"S3","A3")
    asm1=l.freeze_assembly("P",r1); l.close()

    # Process replacement: reopen only from durable ledger.
    l=m.Ledger(db)
    r2=l.author_revision("P",scenes("one revised"),parent=r1)
    assert l.reusable(a1,"P",r2,"S1")
    assert not l.reusable(a2,"P",r2,"S2")
    assert l.reusable(a3,"P",r2,"S3")
    a2r2=accepted(l,"P",r2,"S2","A2-R2")
    asm2=l.freeze_assembly("P",r2)
    assert asm2 != asm1
    old=l.db.execute("SELECT artifact_sha256 FROM render_attempt WHERE id IN (?,?,?) ORDER BY id",(a1,a2,a3)).fetchall()
    assert len(old)==3 and all(len(row[0])==64 for row in old)
    ordered=l.db.execute("SELECT ordered_inputs_json FROM assembly_attempt WHERE id=?",(asm2,)).fetchone()[0]
    parsed=m.json.loads(ordered); assert [x[0] for x in parsed]==["S1","S2","S3"]; assert len({x[1] for x in parsed})==3
    l.close()

def test_execution_cannot_self_accept_and_wrong_digest_evidence_fails(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r=l.author_revision("P",scenes())
    a=l.queue("P",r,"S1"); assert l.claim(a,"w"); l.execute(a,"GOOD")
    try: l.accept(a,"oracle","WRONG")
    except RuntimeError: pass
    else: raise AssertionError("wrong artifact evidence accepted")
    assert not l.reusable(a,"P",r,"S1")

def test_only_one_live_claimable_attempt_per_scene(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r=l.author_revision("P",scenes())
    a=l.queue("P",r,"S1")
    try: l.queue("P",r,"S1")
    except m.sqlite3.IntegrityError: pass
    else: raise AssertionError("duplicate live attempt admitted")
    assert l.claim(a,"w1"); assert not l.claim(a,"w2")

def test_assembly_refuses_missing_acceptance(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r=l.author_revision("P",scenes())
    accepted(l,"P",r,"S1","A1"); accepted(l,"P",r,"S2","A2")
    try: l.freeze_assembly("P",r)
    except RuntimeError as e: assert "S3" in str(e)
    else: raise AssertionError("assembly froze with missing scene evidence")


def test_stale_lease_recovery_is_time_bounded(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r=l.author_revision("P",scenes())
    a=l.queue("P",r,"S1"); assert l.claim(a,"dead-worker",ttl=30)
    expiry=l.db.execute("SELECT lease_expires FROM render_attempt WHERE id=?",(a,)).fetchone()[0]
    assert l.recover_expired_leases(expiry-1)==0
    assert not l.claim(a,"replacement")
    assert l.recover_expired_leases(expiry+1)==1
    assert l.claim(a,"replacement")


def test_revision_rows_cannot_be_rewritten_by_second_authoring(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r1=l.author_revision("P",scenes())
    original=l.db.execute("SELECT spec_sha256 FROM revision WHERE project_id='P' AND revision=?",(r1,)).fetchone()[0]
    r2=l.author_revision("P",scenes("changed"),parent=r1)
    assert r2==r1+1
    assert l.db.execute("SELECT spec_sha256 FROM revision WHERE project_id='P' AND revision=?",(r1,)).fetchone()[0]==original


def test_equal_size_replacement_and_deletion_break_reuse(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r1=l.author_revision("P",scenes())
    artifact=tmp_path/"scene.bin"; artifact.write_bytes(b"GOOD")
    sha=m.hashlib.sha256(artifact.read_bytes()).hexdigest()
    a=l.queue("P",r1,"S1"); assert l.claim(a,"w"); l.execute(a,sha,str(artifact)); l.accept(a,"oracle",sha)
    r2=l.author_revision("P",scenes(),parent=r1)
    artifact.write_bytes(b"EVIL")  # same byte length, wrong content
    assert not l.reusable(a,"P",r2,"S1")
    artifact.unlink()
    assert not l.reusable(a,"P",r2,"S1")


def test_corruption_after_reuse_receipt_blocks_assembly_freeze(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r1=l.author_revision("P",scenes())
    artifact=tmp_path/"s1.bin"; artifact.write_bytes(b"GOOD"); sha=m.hashlib.sha256(b"GOOD").hexdigest()
    a=l.queue("P",r1,"S1"); assert l.claim(a,"w"); l.execute(a,sha,str(artifact)); l.accept(a,"oracle",sha)
    # Other scenes can be symbolic in this isolated metadata experiment.
    accepted(l,"P",r1,"S2","A2"); accepted(l,"P",r1,"S3","A3")
    r2=l.author_revision("P",scenes(),parent=r1)
    assert l.reusable(a,"P",r2,"S1")
    # establish valid reuse/fresh evidence for the rest
    a2=l.db.execute("SELECT id FROM render_attempt WHERE project_revision=? AND scene_id='S2'",(r1,)).fetchone()[0]
    a3=l.db.execute("SELECT id FROM render_attempt WHERE project_revision=? AND scene_id='S3'",(r1,)).fetchone()[0]
    assert l.reusable(a2,"P",r2,"S2"); assert l.reusable(a3,"P",r2,"S3")
    artifact.write_bytes(b"EVIL")
    try: l.freeze_assembly("P",r2)
    except RuntimeError as e: assert "corrupt" in str(e)
    else: raise AssertionError("assembly froze after accepted artifact corruption")


def test_failed_verifier_is_durable_but_never_reusable(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r=l.author_revision("P",scenes())
    path=tmp_path/"bad.bin"; path.write_bytes(b"BAD"); sha=m.hashlib.sha256(b"BAD").hexdigest()\n    a=l.queue("P",r,"S1"); assert l.claim(a,"w"); l.execute(a,sha,str(path))\n    l.record_failed_evidence(a,"oracle:v1",sha,"failed")
    assert l.db.execute("SELECT collection_state FROM evidence WHERE attempt_id=?",(a,)).fetchone()==("failed",)
    assert not l.reusable(a,"P",r,"S1")


def test_acceptance_requires_executed_state_not_queued_or_leased(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r=l.author_revision("P",scenes())
    a=l.queue("P",r,"S1")
    try: l.accept(a,"oracle","A1")
    except RuntimeError: pass
    else: raise AssertionError("queued attempt accepted")
    assert l.claim(a,"w")
    try: l.accept(a,"oracle","A1")
    except RuntimeError: pass
    else: raise AssertionError("leased attempt accepted")


def test_assembly_execution_cannot_self_accept_and_digest_must_match(tmp_path):
    l=m.Ledger(tmp_path/"s.sqlite"); l.create_project("P"); r=l.author_revision("P",scenes())
    accepted(l,"P",r,"S1","A1"); accepted(l,"P",r,"S2","A2"); accepted(l,"P",r,"S3","A3")
    asm=l.freeze_assembly("P",r)
    assert l.db.execute("SELECT state FROM assembly_attempt WHERE id=?",(asm,)).fetchone()==("frozen",)
    try: l.accept_assembly(asm,"FINAL")
    except RuntimeError: pass
    else: raise AssertionError("frozen assembly accepted before execution")
    l.execute_assembly(asm,"FINAL")
    assert l.db.execute("SELECT state FROM assembly_attempt WHERE id=?",(asm,)).fetchone()==("executed",)
    try: l.accept_assembly(asm,"WRONG")
    except RuntimeError: pass
    else: raise AssertionError("wrong final digest accepted")
    l.accept_assembly(asm,"FINAL")
    assert l.db.execute("SELECT state FROM assembly_attempt WHERE id=?",(asm,)).fetchone()==("accepted",)
