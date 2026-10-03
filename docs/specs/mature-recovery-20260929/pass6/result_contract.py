#!/usr/bin/env python3
"""Reference-only result/identity model for Melosviz M-E02.

This file is NOT production code and does not choose storage technology.
It exists so implementation agents have an executable semantic contract.
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable

class ExecutionOutcome(str, Enum):
    REAL_MEDIA="real-media"
    OFFLINE_PLACEHOLDER="offline-placeholder"
    JOB_SPEC_ONLY="job-spec-only"
    UNAVAILABLE="unavailable"
    MALFORMED="malformed"
    FAILED="failed"
    CACHE_HIT="cache-hit"

class AcceptanceState(str, Enum):
    NOT_EVALUATED="not-evaluated"
    BLOCKED="blocked"
    REJECTED="rejected"
    ACCEPTED="accepted"

class AssemblyState(str, Enum):
    NOT_ATTEMPTED="not-attempted"
    PLAN_ONLY="plan-only"
    ASSEMBLED_UNVERIFIED="assembled-unverified"
    ACCEPTED="accepted"
    FAILED="failed"

@dataclass(frozen=True, slots=True)
class SceneRef:
    scene_id: str
    scene_revision: int
    index: int
    scene_type: str

    def __post_init__(self):
        if not self.scene_id or self.scene_revision < 1 or self.index < 0 or not self.scene_type:
            raise ValueError("invalid scene identity")

@dataclass(frozen=True, slots=True)
class ArtifactRef:
    digest: str
    path: str
    media_kind: str
    def __post_init__(self):
        if len(self.digest) != 64 or not self.path or not self.media_kind:
            raise ValueError("artifact identity must be complete")

@dataclass(frozen=True, slots=True)
class SceneExecution:
    scene: SceneRef
    attempt_id: str
    outcome: ExecutionOutcome
    artifacts: tuple[ArtifactRef,...]=()
    acceptance: AcceptanceState=AcceptanceState.NOT_EVALUATED
    evidence_run_ids: tuple[str,...]=()

    def independently_accept(self, evidence_run_ids: Iterable[str]) -> "SceneExecution":
        ids=tuple(evidence_run_ids)
        if self.outcome not in (ExecutionOutcome.REAL_MEDIA,ExecutionOutcome.CACHE_HIT):
            raise ValueError("non-production execution cannot become accepted")
        if not self.artifacts or not ids:
            raise ValueError("accepted state requires artifacts and independent evidence")
        return replace(self, acceptance=AcceptanceState.ACCEPTED, evidence_run_ids=ids)

@dataclass(frozen=True, slots=True)
class AssemblyExecution:
    attempt_id: str
    inputs: tuple[tuple[str,int,str],...]  # scene_id, revision, artifact digest in exact order
    state: AssemblyState
    artifact: ArtifactRef|None=None
    evidence_run_ids: tuple[str,...]=()

    def independently_accept(self, evidence_run_ids: Iterable[str]) -> "AssemblyExecution":
        ids=tuple(evidence_run_ids)
        if self.state != AssemblyState.ASSEMBLED_UNVERIFIED or not self.inputs or self.artifact is None or not ids:
            raise ValueError("assembly acceptance prerequisites missing")
        return replace(self,state=AssemblyState.ACCEPTED,evidence_run_ids=ids)

@dataclass(slots=True)
class OrchestratorResult:
    scenes: list[SceneExecution]=field(default_factory=list)
    assembly: AssemblyExecution|None=None

    def by_id(self)->dict[str,SceneExecution]:
        out={}
        for x in self.scenes:
            if x.scene.scene_id in out:
                raise ValueError("duplicate scene identity")
            out[x.scene.scene_id]=x
        return out

    def ordered(self)->list[SceneExecution]:
        return sorted(self.scenes,key=lambda x:x.scene.index)

    def accepted_inputs(self)->tuple[tuple[str,int,str],...]:
        rows=[]
        for x in self.ordered():
            if x.acceptance != AcceptanceState.ACCEPTED or len(x.artifacts)!=1:
                raise ValueError(f"scene {x.scene.scene_id} is not one accepted single-artifact input")
            rows.append((x.scene.scene_id,x.scene.scene_revision,x.artifacts[0].digest))
        return tuple(rows)
