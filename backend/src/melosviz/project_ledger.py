"""M-E03 bounded product-ledger seam.

This is deliberately metadata-only and does not own rendering. It persists the
canonical RenderSpec revision before execution and can reconstruct it after a
process replacement. Media/evidence/attempt integration remains a later slice.
"""
from __future__ import annotations
import hashlib, json, sqlite3, time
from pathlib import Path
from melosviz.analysis.models import RenderSpec

SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS project(
 id TEXT PRIMARY KEY, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS project_revision(
 project_id TEXT NOT NULL REFERENCES project(id),
 revision INTEGER NOT NULL,
 parent_revision INTEGER,
 spec_sha256 TEXT NOT NULL,
 spec_json TEXT NOT NULL,
 created_at REAL NOT NULL,
 PRIMARY KEY(project_id,revision)
);
CREATE TABLE IF NOT EXISTS render_attempt(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 project_id TEXT NOT NULL,
 project_revision INTEGER NOT NULL,
 spec_sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('running','completed','failed')),
 job_id TEXT,
 started_at REAL NOT NULL,
 completed_at REAL,
 FOREIGN KEY(project_id,project_revision) REFERENCES project_revision(project_id,revision)
);
CREATE INDEX IF NOT EXISTS render_attempt_revision_idx
ON render_attempt(project_id,project_revision);
CREATE TABLE IF NOT EXISTS attempt_evidence(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 attempt_id INTEGER NOT NULL REFERENCES render_attempt(id),
 kind TEXT NOT NULL,
 artifact_sha256 TEXT NOT NULL,
 verifier TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('accepted','rejected','failed')),
 created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS assembly_attempt(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 render_attempt_id INTEGER NOT NULL REFERENCES render_attempt(id),
 ordered_inputs_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('frozen','completed','accepted','failed')),
 artifact_sha256 TEXT
);
"""

def canonical_spec(spec:RenderSpec)->tuple[str,str]:
    raw=json.dumps(spec.model_dump(mode="json"),sort_keys=True,separators=(",",":"))
    return raw,hashlib.sha256(raw.encode()).hexdigest()

class ProjectLedger:
    def __init__(self,path:Path):
        self.path=Path(path); self.db=sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys=ON"); self.db.executescript(SCHEMA); self.db.commit()
    def close(self): self.db.close()
    def ensure_project(self,project_id:str):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO project VALUES(?,?)",(project_id,time.time()))
    def commit(self,project_id:str,spec:RenderSpec,parent_revision:int|None=None)->int:
        self.ensure_project(project_id)
        raw,sha=canonical_spec(spec)
        if parent_revision is not None:
            if not self.db.execute("SELECT 1 FROM project_revision WHERE project_id=? AND revision=?",(project_id,parent_revision)).fetchone():
                raise ValueError("unknown parent revision")
        rev=self.db.execute("SELECT COALESCE(MAX(revision),0)+1 FROM project_revision WHERE project_id=?",(project_id,)).fetchone()[0]
        with self.db:
            self.db.execute("INSERT INTO project_revision VALUES(?,?,?,?,?,?)",(project_id,rev,parent_revision,sha,raw,time.time()))
        return rev
    def load(self,project_id:str,revision:int)->RenderSpec:
        row=self.db.execute("SELECT spec_json,spec_sha256 FROM project_revision WHERE project_id=? AND revision=?",(project_id,revision)).fetchone()
        if not row: raise KeyError((project_id,revision))
        raw,expected=row
        if hashlib.sha256(raw.encode()).hexdigest()!=expected: raise RuntimeError("stored RenderSpec digest mismatch")
        return RenderSpec.model_validate_json(raw)
    def start_attempt(self,project_id:str,revision:int)->int:
        row=self.db.execute("SELECT spec_sha256 FROM project_revision WHERE project_id=? AND revision=?",(project_id,revision)).fetchone()
        if not row: raise KeyError((project_id,revision))
        with self.db:
            cur=self.db.execute("INSERT INTO render_attempt(project_id,project_revision,spec_sha256,state,started_at) VALUES(?,?,?,'running',?)",(project_id,revision,row[0],time.time()))
        return cur.lastrowid

    def finish_attempt(self,attempt_id:int,job_id:str|None):
        with self.db:
            cur=self.db.execute("UPDATE render_attempt SET state='completed',job_id=?,completed_at=? WHERE id=? AND state='running'",(job_id,time.time(),attempt_id))
            if cur.rowcount!=1: raise RuntimeError("attempt not running")

    def fail_attempt(self,attempt_id:int):
        with self.db:
            cur=self.db.execute("UPDATE render_attempt SET state='failed',completed_at=? WHERE id=? AND state='running'",(time.time(),attempt_id))
            if cur.rowcount!=1: raise RuntimeError("attempt not running")

    def record_evidence(self,attempt_id:int,kind:str,artifact_sha256:str,verifier:str,state:str):
        if state not in {"accepted","rejected","failed"}: raise ValueError(state)
        row=self.db.execute("SELECT state,spec_sha256 FROM render_attempt WHERE id=?",(attempt_id,)).fetchone()
        if not row: raise KeyError(attempt_id)
        if state=="accepted" and row[0]!="completed":
            raise RuntimeError("accepted evidence requires completed render attempt")
        if not artifact_sha256 or len(artifact_sha256)!=64:
            raise ValueError("artifact digest must be sha256 hex")
        try: int(artifact_sha256,16)
        except ValueError as exc: raise ValueError("artifact digest must be sha256 hex") from exc
        if not verifier.strip(): raise ValueError("verifier identity required")
        with self.db:
            self.db.execute("INSERT INTO attempt_evidence(attempt_id,kind,artifact_sha256,verifier,state,created_at) VALUES(?,?,?,?,?,?)",(attempt_id,kind,artifact_sha256,verifier,state,time.time()))

    def freeze_assembly(self,attempt_id:int,ordered_inputs:list[tuple[int,str]])->int:
        row=self.db.execute("SELECT state FROM render_attempt WHERE id=?",(attempt_id,)).fetchone()
        if row != ("completed",): raise RuntimeError("render attempt not completed")
        if not ordered_inputs: raise RuntimeError("assembly input denominator empty")
        raw=json.dumps(ordered_inputs,separators=(",",":"))
        with self.db:
            cur=self.db.execute("INSERT INTO assembly_attempt(render_attempt_id,ordered_inputs_json,state) VALUES(?,?,'frozen')",(attempt_id,raw))
        return cur.lastrowid

    def latest_revision(self,project_id:str)->int|None:
        row=self.db.execute("SELECT MAX(revision) FROM project_revision WHERE project_id=?",(project_id,)).fetchone()
        return row[0] if row and row[0] is not None else None
