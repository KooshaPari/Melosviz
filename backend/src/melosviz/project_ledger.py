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
    def latest_revision(self,project_id:str)->int|None:
        row=self.db.execute("SELECT MAX(revision) FROM project_revision WHERE project_id=?",(project_id,)).fetchone()
        return row[0] if row and row[0] is not None else None
