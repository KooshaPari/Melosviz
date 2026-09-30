"""Bounded durable-state experiment for mature recovery.

Not product integration. SQLite owns metadata/lineage only; media remains external
and content-addressed. The API is intentionally small enough for adversarial tests.
"""
from __future__ import annotations
import hashlib, json, sqlite3, time
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS project(
 id TEXT PRIMARY KEY, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS revision(
 project_id TEXT NOT NULL REFERENCES project(id),
 revision INTEGER NOT NULL,
 parent_revision INTEGER,
 spec_sha256 TEXT NOT NULL,
 created_at REAL NOT NULL,
 PRIMARY KEY(project_id, revision)
);
CREATE TABLE IF NOT EXISTS scene_revision(
 project_id TEXT NOT NULL,
 project_revision INTEGER NOT NULL,
 scene_id TEXT NOT NULL,
 scene_revision INTEGER NOT NULL,
 ordinal INTEGER NOT NULL,
 input_sha256 TEXT NOT NULL,
 PRIMARY KEY(project_id, project_revision, scene_id),
 FOREIGN KEY(project_id, project_revision) REFERENCES revision(project_id, revision)
);
CREATE TABLE IF NOT EXISTS render_attempt(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 project_id TEXT NOT NULL,
 project_revision INTEGER NOT NULL,
 scene_id TEXT NOT NULL,
 scene_revision INTEGER NOT NULL,
 input_sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('queued','leased','executed','failed')),
 lease_owner TEXT,
 lease_expires REAL,
 artifact_sha256 TEXT,
 FOREIGN KEY(project_id, project_revision, scene_id)
   REFERENCES scene_revision(project_id, project_revision, scene_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_attempt
ON render_attempt(project_id, project_revision, scene_id)
WHERE state IN ('queued','leased');
CREATE TABLE IF NOT EXISTS evidence(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 attempt_id INTEGER NOT NULL REFERENCES render_attempt(id),
 verifier TEXT NOT NULL,
 artifact_sha256 TEXT NOT NULL,
 collection_state TEXT NOT NULL CHECK(collection_state IN ('accepted','rejected','failed')),
 created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reuse_receipt(
 project_id TEXT NOT NULL,
 project_revision INTEGER NOT NULL,
 scene_id TEXT NOT NULL,
 source_attempt_id INTEGER NOT NULL REFERENCES render_attempt(id),
 artifact_sha256 TEXT NOT NULL,
 input_sha256 TEXT NOT NULL,
 PRIMARY KEY(project_id, project_revision, scene_id)
);
CREATE TABLE IF NOT EXISTS assembly_attempt(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 project_id TEXT NOT NULL,
 project_revision INTEGER NOT NULL,
 ordered_inputs_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('frozen','executed','accepted','failed')),
 artifact_sha256 TEXT
);
"""

def digest(obj) -> str:
    raw=json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

class Ledger:
    def __init__(self,path:Path):
        self.path=Path(path)
        self.db=sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self): self.db.close()

    def create_project(self,pid:str):
        self.db.execute("INSERT INTO project VALUES(?,?)",(pid,time.time())); self.db.commit()

    def author_revision(self,pid:str, scenes:list[dict], parent:int|None=None)->int:
        rev=(self.db.execute("SELECT COALESCE(MAX(revision),0)+1 FROM revision WHERE project_id=?",(pid,)).fetchone()[0])
        spec_sha=digest(scenes)
        with self.db:
            self.db.execute("INSERT INTO revision VALUES(?,?,?,?,?)",(pid,rev,parent,spec_sha,time.time()))
            prior={}
            if parent:
                prior={r[0]:(r[1],r[2]) for r in self.db.execute(
                    "SELECT scene_id,scene_revision,input_sha256 FROM scene_revision WHERE project_id=? AND project_revision=?",(pid,parent))}
            for ordinal,scene in enumerate(scenes):
                sid=scene["scene_id"]; inp=digest(scene)
                old=prior.get(sid)
                srev=old[0] if old and old[1]==inp else ((old[0]+1) if old else 1)
                self.db.execute("INSERT INTO scene_revision VALUES(?,?,?,?,?,?)",(pid,rev,sid,srev,ordinal,inp))
        return rev

    def queue(self,pid:str,rev:int,sid:str)->int:
        row=self.db.execute("SELECT scene_revision,input_sha256 FROM scene_revision WHERE project_id=? AND project_revision=? AND scene_id=?",(pid,rev,sid)).fetchone()
        if not row: raise KeyError(sid)
        with self.db:
            cur=self.db.execute("INSERT INTO render_attempt(project_id,project_revision,scene_id,scene_revision,input_sha256,state) VALUES(?,?,?,?,?,'queued')",(pid,rev,sid,row[0],row[1]))
        return cur.lastrowid

    def claim(self,attempt:int,worker:str,ttl:float=30)->bool:
        now=time.time()
        with self.db:
            cur=self.db.execute("UPDATE render_attempt SET state='leased',lease_owner=?,lease_expires=? WHERE id=? AND state='queued'",(worker,now+ttl,attempt))
        return cur.rowcount==1

    def execute(self,attempt:int,artifact_sha:str):
        with self.db:
            cur=self.db.execute("UPDATE render_attempt SET state='executed',artifact_sha256=?,lease_owner=NULL,lease_expires=NULL WHERE id=? AND state='leased'",(artifact_sha,attempt))
            if cur.rowcount!=1: raise RuntimeError("attempt not leased")

    def accept(self,attempt:int,verifier:str,artifact_sha:str):
        row=self.db.execute("SELECT state,artifact_sha256 FROM render_attempt WHERE id=?",(attempt,)).fetchone()
        if not row or row != ("executed",artifact_sha): raise RuntimeError("evidence does not bind executed artifact")
        with self.db:
            self.db.execute("INSERT INTO evidence(attempt_id,verifier,artifact_sha256,collection_state,created_at) VALUES(?,?,?,'accepted',?)",(attempt,verifier,artifact_sha,time.time()))

    def reusable(self,source_attempt:int,pid:str,rev:int,sid:str)->bool:
        target=self.db.execute("SELECT input_sha256 FROM scene_revision WHERE project_id=? AND project_revision=? AND scene_id=?",(pid,rev,sid)).fetchone()
        source=self.db.execute("""SELECT a.input_sha256,a.artifact_sha256 FROM render_attempt a
          WHERE a.id=? AND a.state='executed' AND EXISTS(
            SELECT 1 FROM evidence e WHERE e.attempt_id=a.id AND e.collection_state='accepted' AND e.artifact_sha256=a.artifact_sha256)""",(source_attempt,)).fetchone()
        if not target or not source or target[0]!=source[0]: return False
        with self.db:
            self.db.execute("INSERT INTO reuse_receipt VALUES(?,?,?,?,?,?)",(pid,rev,sid,source_attempt,source[1],source[0]))
        return True

    def freeze_assembly(self,pid:str,rev:int)->int:
        scenes=list(self.db.execute("SELECT scene_id,input_sha256 FROM scene_revision WHERE project_id=? AND project_revision=? ORDER BY ordinal",(pid,rev)))
        ordered=[]
        for sid,inp in scenes:
            reused=self.db.execute("SELECT artifact_sha256 FROM reuse_receipt WHERE project_id=? AND project_revision=? AND scene_id=?",(pid,rev,sid)).fetchone()
            if reused: ordered.append([sid,reused[0]]); continue
            fresh=self.db.execute("""SELECT a.artifact_sha256 FROM render_attempt a WHERE a.project_id=? AND a.project_revision=? AND a.scene_id=? AND a.input_sha256=? AND a.state='executed' AND EXISTS(
              SELECT 1 FROM evidence e WHERE e.attempt_id=a.id AND e.collection_state='accepted' AND e.artifact_sha256=a.artifact_sha256) ORDER BY a.id DESC LIMIT 1""",(pid,rev,sid,inp)).fetchone()
            if not fresh: raise RuntimeError(f"scene {sid} lacks accepted artifact")
            ordered.append([sid,fresh[0]])
        with self.db:
            cur=self.db.execute("INSERT INTO assembly_attempt(project_id,project_revision,ordered_inputs_json,state) VALUES(?,?,?,'frozen')",(pid,rev,json.dumps(ordered)))
        return cur.lastrowid
