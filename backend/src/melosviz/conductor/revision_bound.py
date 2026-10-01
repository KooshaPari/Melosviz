"""Revision-bound conductor entrypoint for M-E03.

The existing Orchestrator remains the renderer. This seam makes project/revision
identity mandatory at the boundary and loads the exact immutable RenderSpec
from ProjectLedger immediately before execution.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
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
        try:
            ledger.finish_attempt(attempt_id,getattr(result,"job_id",None))
            # Persist only observed concrete scene artifacts as non-accepted
            # execution evidence. Independent verifier authority promotes them
            # later; the conductor cannot self-accept its own output.
            for scene_index,scene_result in sorted((getattr(result,"per_scene_results",None) or {}).items()):
                path=None
                if isinstance(scene_result,dict): path=scene_result.get("artifact_path")
                else: path=getattr(scene_result,"artifact_path",None)
                if path:
                    p=Path(path)
                    if p.is_file():
                        ledger.record_evidence(
                            attempt_id,"scene",
                            hashlib.sha256(p.read_bytes()).hexdigest(),
                            f"conductor:scene:{scene_index}",
                            "rejected",
                        )
        finally:
            ledger.close()
        # Result identity is additive for this experiment; consumers that do not
        # know these fields remain compatible.
        result.project_id=project_id
        result.project_revision=revision
        result.project_spec_sha256=expected[0]
        result.project_attempt_id=attempt_id
        return result
