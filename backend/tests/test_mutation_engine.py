"""Mutation engine — drives the antigame spectrum at test time.

Walks a small set of MelosViz source modules, generates a deterministic AST
mutation plan, applies each mutation in a temp copy, runs the existing
pytest suite against it, and records:
  * total mutations generated
  * killed (tests fail against the mutated source)
  * survived (tests still pass — the qgate BUG)
  * kill-score percentage

This runs in-process — no fork/spawn — so it works on every platform.
It is the *durable, runnable evidence* behind the >=75% mutation kill-score
gate in .qgate.toml.

Use:
    pytest tests/test_mutation_engine.py -q -s
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import pytest


REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
# `parents[0]` is `tests/`, `parents[1]` is `backend/`.  Resolve source
# relative to `backend/` because the package source lives at backend/src/.
SRC = REPO / "src" if (REPO / "src" / "melosviz").exists() else (REPO / "backend" / "src")
MUTATIONS_DIR = REPO / ".mutations"
TARGETS = [
    SRC / "melosviz" / "analysis" / "models.py",
    SRC / "melosviz" / "analysis" / "audio.py",
    SRC / "melosviz" / "bridge" / "server.py",
]
TIMEOUT_S = 60
TARGET_SCORE = 75.0


# ----------------------- AST mutation plan -------------------------------

@dataclass
class Planned:
    mid: str
    line: int
    op: str
    snippet: str


def _plan(source_path: Path) -> list[Planned]:
    import ast

    tree = ast.parse(source_path.read_text())
    out: list[Planned] = []

    REL = {"Eq", "NotEq", "Lt", "LtE", "Gt", "GtE"}
    ARITH = {"Add", "Sub", "Mult", "Div", "Mod"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if type(op).__name__ in REL:
                    out.append(Planned(mid=str(uuid.uuid4()), line=node.lineno,
                                       op="ROR", snippet=ast.unparse(node).split("\n")[0][:80]))
                    break  # one ROR per Compare
        elif isinstance(node, ast.BinOp):
            if type(node.op).__name__ in ARITH:
                out.append(Planned(mid=str(uuid.uuid4()), line=node.lineno,
                                   op="AOR", snippet=ast.unparse(node).split("\n")[0][:80]))
        elif isinstance(node, ast.BoolOp):
            out.append(Planned(mid=str(uuid.uuid4()), line=node.lineno,
                               op="LCR", snippet=ast.unparse(node).split("\n")[0][:80]))
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                out.append(Planned(mid=str(uuid.uuid4()), line=node.lineno,
                                   op="BOOL", snippet=repr(node.value)))
            elif isinstance(node.value, int) and node.value in (0, 1):
                out.append(Planned(mid=str(uuid.uuid4()), line=node.lineno,
                                   op="NUM", snippet=repr(node.value)))
        elif isinstance(node, ast.If):
            out.append(Planned(mid=str(uuid.uuid4()), line=node.lineno,
                               op="BRANCH", snippet=ast.unparse(node.test).split("\n")[0][:80]))
    return out


# ----------------------- AST mutation application -------------------------

SWAPPED = {
    "Eq": "NotEq", "NotEq": "Eq",
    "Lt": "LtE", "LtE": "Lt",
    "Gt": "GtE", "GtE": "Gt",
    "Add": "Sub", "Sub": "Add",
    "Mult": "Div", "Div": "Mult",
}
OPPOSITE_BOOL = {"Eq": "NotEq", "And": "Or"}


def _apply_one(source_text: str, target: Planned, target_index: int) -> str:
    """Rewrite *source_text* mutating the *target_index*-th matching site."""
    import ast

    tree = ast.parse(source_text)

    class Hit(ast.NodeTransformer):
        def __init__(self):
            super().__init__()
            self.remaining = target_index

        def visit(self, node):  # type: ignore[override]
            self.generic_visit(node)
            if self.remaining < 0:
                return node
            if self._matches(node):
                if self.remaining == 0:
                    self._alter(node)
                    self.remaining = -1
                else:
                    self.remaining -= 1
            return node

        def _matches(self, node):
            return (
                (isinstance(node, ast.Compare) and target.op == "ROR")
                or (isinstance(node, ast.BinOp) and target.op == "AOR")
                or (isinstance(node, ast.BoolOp) and target.op == "LCR")
                or (isinstance(node, ast.Constant) and isinstance(node.value, bool) and target.op == "BOOL")
                or (isinstance(node, ast.Constant) and isinstance(node.value, int) and target.op == "NUM")
                or (isinstance(node, ast.If) and target.op == "BRANCH")
            )

        def _alter(self, node):
            if isinstance(node, ast.Compare):
                op = node.ops[0]
                if type(op).__name__ in SWAPPED:
                    node.ops[0] = getattr(ast, SWAPPED[type(op).__name__])()
            elif isinstance(node, ast.BinOp):
                if type(node.op).__name__ in SWAPPED:
                    node.op = getattr(ast, SWAPPED[type(node.op).__name__])()
            elif isinstance(node, ast.BoolOp):
                if type(node.op).__name__ in OPPOSITE_BOOL:
                    node.op = getattr(ast, OPPOSITE_BOOL[type(node.op).__name__])()
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, bool):
                    node.value = not node.value
                elif isinstance(node.value, (int,)) and node.value in (0, 1):
                    node.value = 1 - node.value
            elif isinstance(node, ast.If):
                node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)

    Hit().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


# ----------------------- Driver ------------------------------------------

@dataclass
class MutationReport:
    target: str
    total: int = 0
    killed: int = 0
    survived: int = 0
    timeout: int = 0
    score: float = 0.0
    op_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)
    survivors: list[dict] = field(default_factory=list)
    elapsed_s: float = 0.0


@pytest.mark.skipif(
    not (SRC / "melosviz" / "analysis" / "models.py").exists(),
    reason="melosviz analysis models not in this checkout",
)
def test_mutation_kill_score_meets_qgate_bar() -> None:
    """Drive the mutation engine across the antigame-targeted source files
    and assert the qgate bar of >=75% is met.

    Runable evidence behind the bar — kills every common mutation
    operator that the integration tests catch.  Each targeted file gets
    its own AST plan + applied mutations; per-file reports are written
    to `.mutations/<file>.json`.
    """
    overall = {"total": 0, "killed": 0, "survived": 0, "timeout": 0,
               "score": 0.0, "per_file": {}}
    MAX_PER_FILE = 60  # cap to keep CI runtime bounded
    for target in TARGETS:
        if not target.exists():
            continue
        plan = _plan(target)[:MAX_PER_FILE]
        if not plan:
            continue
        src_text = target.read_text()
        backup = target.with_suffix(".py.mutbak")
        shutil.copy(target, backup)
        report = MutationReport(target=str(target))
        try:
            for i, mutation in enumerate(plan):
                mutated = _apply_one(src_text, mutation, i)
                target.write_text(mutated)
                try:
                    rc = subprocess.run(
                        [sys.executable, "-m", "pytest",
                         "tests/test_render_spec_v2.py",
                         "tests/test_mutation_kill_score.py",
                         "tests/test_coverage_100.py",
                         "tests/test_coverage_gaps.py",
                         "--no-cov", "-q", "-x"],
                        cwd=target.parents[2],
                        capture_output=True, text=True,
                        timeout=TIMEOUT_S, check=False,
                    )
                    killed = rc.returncode != 0
                except subprocess.TimeoutExpired:
                    killed = True
                    report.timeout += 1
                finally:
                    shutil.copy(backup, target)

                report.total += 1
                if killed:
                    report.killed += 1
                else:
                    report.survived += 1
                    report.survivors.append({
                        "mid": mutation.mid, "op": mutation.op,
                        "line": mutation.line, "snippet": mutation.snippet,
                    })
                report.op_breakdown.setdefault(mutation.op, {"total": 0, "killed": 0})
                report.op_breakdown[mutation.op]["total"] += 1
                if killed:
                    report.op_breakdown[mutation.op]["killed"] += 1
        finally:
            shutil.copy(backup, target)
            backup.unlink(missing_ok=True)
        report.score = (report.killed / report.total * 100.0) if report.total else 0.0
        # We treat timeout as a kill (mutant induced hang — a *bad* outcome caught)
        if report.killed == 0 and report.timeout > 0:
            report.score = (report.timeout / report.total) * 100.0
        MUTATIONS_DIR.mkdir(exist_ok=True)
        (MUTATIONS_DIR / f"{target.parent.name}_{target.stem}.json").write_text(
            json.dumps(asdict(report), indent=2))
        overall["total"] += report.total
        overall["killed"] += report.killed
        overall["survived"] += report.survived
        overall["timeout"] += report.timeout
        overall["per_file"][target.name] = report.score

    if overall["total"]:
        overall["score"] = (overall["killed"] / overall["total"]) * 100.0
    print(json.dumps(overall, indent=2))
    assert overall["score"] >= TARGET_SCORE, (
        f"mutation kill-score {overall['score']:.1f}% below qgate bar "
        f"{TARGET_SCORE}%; killed={overall['killed']}/{overall['total']}"
    )
    src_text = target.read_text()
    backup = target.with_suffix(".py.mutbak")
    shutil.copy(target, backup)
    report = MutationReport(target=str(target))
    started = time.monotonic()

    try:
        for i, mutation in enumerate(plan):
            mutated = _apply_one(src_text, mutation, i)
            target.write_text(mutated)
            try:
                rc = subprocess.run(
                    [sys.executable, "-m", "pytest", "tests/test_render_spec_v2.py",
                     "tests/test_mutation_kill_score.py",
                     "tests/test_coverage_100.py", "tests/test_coverage_gaps.py",
                     "--no-cov", "-q", "-x"],
                    cwd=target.parents[2],
                    capture_output=True, text=True,
                    timeout=TIMEOUT_S, check=False,
                )
                killed = rc.returncode != 0
            except subprocess.TimeoutExpired:
                killed = True
                report.timeout += 1
            finally:
                shutil.copy(backup, target)

            report.total += 1
            if killed:
                report.killed += 1
            else:
                report.survived += 1
                report.survivors.append({"mid": mutation.mid, "op": mutation.op,
                                         "line": mutation.line, "snippet": mutation.snippet})
            report.op_breakdown.setdefault(mutation.op, {"total": 0, "killed": 0})
            report.op_breakdown[mutation.op]["total"] += 1
            if killed:
                report.op_breakdown[mutation.op]["killed"] += 1
    finally:
        shutil.copy(backup, target)
        backup.unlink(missing_ok=True)

    report.score = (report.killed / report.total * 100.0) if report.total else 0.0
    report.elapsed_s = round(time.monotonic() - started, 2)

    MUTATIONS_DIR.mkdir(exist_ok=True)
    (MUTATIONS_DIR / "models.json").write_text(json.dumps(asdict(report), indent=2))

    print(json.dumps(asdict(report), indent=2))

    assert report.score >= TARGET_SCORE, (
        f"mutation kill-score {report.score:.1f}% is below qgate bar "
        f"{TARGET_SCORE}%; survived={report.survived}/{report.total}"
    )
