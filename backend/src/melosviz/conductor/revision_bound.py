"""Revision-bound conductor entrypoint for M-E03.

The existing Orchestrator remains the renderer. This seam makes project/revision
identity mandatory at the boundary and loads the exact immutable RenderSpec
from ProjectLedger immediately before execution.
"""
from __future__ import annotations
from pathlib import Path
from .orchestrator import Orchestrator, OrchestratorResult
from ..project_ledger import ProjectLedger, canonical_spec

class RevisionBoundConductor:
    def __init__(self, ledger_path:Path|str, **orchestrator_kwargs):
        self.ledger_path=Path(ledger_path)
        self.orchestrator_kwargs=orchestrator_kwargs

    def render_revision(self,project_id:str,revision:int)->OrchestratorResult:
        ledger=ProjectLedger(self.ledger_path)
        try:
            spec=ledger.load(project_id,revision)
            expected=ledger.db.execute(
                "SELECT spec_sha256 FROM project_revision WHERE project_id=? AND revision=?",
                (project_id,revision),
            ).fetchone()
            if expected is None or canonical_spec(spec)[1] != expected[0]:
                raise RuntimeError("revision identity changed before execution")
            attempt_id=ledger.start_attempt(project_id,revision)
        finally:
            ledger.close()
        orchestrator=Orchestrator(**self.orchestrator_kwargs)
        try:
            result=orchestrator.render(spec)
        except Exception:
            ledger=ProjectLedger(self.ledger_path)
            try: ledger.fail_attempt(attempt_id)
            finally: ledger.close()
            raise
        ledger=ProjectLedger(self.ledger_path)
        try: ledger.finish_attempt(attempt_id,getattr(result,"job_id",None))
        finally: ledger.close()
        # Result identity is additive for this experiment; consumers that do not
        # know these fields remain compatible.
        result.project_id=project_id
        result.project_revision=revision
        result.project_spec_sha256=expected[0]
        result.project_attempt_id=attempt_id
        return result
