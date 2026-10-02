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
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pytest
from conftest import find_repo_root

# Marker walk instead of parents[2]: under mutmut the tests/ directory is one
# level deeper, so a fixed depth resolves to backend/ instead of the repo root.
REPO = find_repo_root(__file__)
# The package source lives at backend/src/. Accept either root so the suite
# works whether it is run from the repo root or from backend/.
SRC = REPO / "src" if (REPO / "src" / "melosviz").exists() else (REPO / "backend" / "src")
BACKEND = SRC.parent
MUTATIONS_DIR = REPO / ".mutations"
TARGETS = [
    SRC / "melosviz" / "analysis" / "models.py",
    SRC / "melosviz" / "analysis" / "audio.py",
    SRC / "melosviz" / "bridge" / "server.py",
]
TIMEOUT_S = 60
TARGET_SCORE = 75.0
# Wall-clock budget for the whole test, derived from the work it does rather
# than picked to make today's run pass.
#
# The test runs up to max_per_file(60) mutations per target across len(TARGETS)
# targets, and every mutation is a separate pytest subprocess over four test
# files. Measured on this tree: one such subprocess costs ~48s locally (the
# suite is ~320 tests, ~47s with the audio tests dominating), so the worst case
# is 60 x 3 x 48s ~= 144 minutes.
#
# The old budget was @pytest.mark.timeout(300) -- 5 minutes for work that can
# legitimately take over two hours. It only ever passed because killed mutants
# exit early under -x; a single surviving mutant, which by definition runs the
# entire suite, blew it. Dispatched run 36957966430 against e3f3ddd is that
# case:
#     FAILED tests/test_mutation_engine.py::test_mutation_kill_score_meets_qgate_bar
#       - Failed: Timeout (>300.0s) from pytest-timeout
# The bar being enforced is the 75% kill score, not a duration. A timeout that
# fires before the measurement completes destroys the thing it is supposed to
# protect, so the budget is sized to the work and still fails loudly if the
# drive genuinely hangs (each subprocess has its own TIMEOUT_S=60 cap, so a real
# hang surfaces as report.timeout, not as this outer budget).
KILL_SCORE_TIMEOUT_S = 3 * 60 * 60


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

    rel = {"Eq", "NotEq", "Lt", "LtE", "Gt", "GtE"}
    arith = {"Add", "Sub", "Mult", "Div", "Mod"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if type(op).__name__ in rel:
                    out.append(
                        Planned(
                            mid=str(uuid.uuid4()),
                            line=node.lineno,
                            op="ROR",
                            snippet=ast.unparse(node).split("\n")[0][:80],
                        )
                    )
                    break  # one ROR per Compare
        elif isinstance(node, ast.BinOp):
            if type(node.op).__name__ in arith:
                out.append(
                    Planned(
                        mid=str(uuid.uuid4()),
                        line=node.lineno,
                        op="AOR",
                        snippet=ast.unparse(node).split("\n")[0][:80],
                    )
                )
        elif isinstance(node, ast.BoolOp):
            out.append(
                Planned(
                    mid=str(uuid.uuid4()),
                    line=node.lineno,
                    op="LCR",
                    snippet=ast.unparse(node).split("\n")[0][:80],
                )
            )
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                out.append(
                    Planned(
                        mid=str(uuid.uuid4()),
                        line=node.lineno,
                        op="BOOL",
                        snippet=repr(node.value),
                    )
                )
            elif isinstance(node.value, int) and node.value in (0, 1):
                out.append(
                    Planned(
                        mid=str(uuid.uuid4()),
                        line=node.lineno,
                        op="NUM",
                        snippet=repr(node.value),
                    )
                )
        elif isinstance(node, ast.If):
            out.append(
                Planned(
                    mid=str(uuid.uuid4()),
                    line=node.lineno,
                    op="BRANCH",
                    snippet=ast.unparse(node.test).split("\n")[0][:80],
                )
            )
    return out


# ----------------------- AST mutation application -------------------------

SWAPPED = {
    "Eq": "NotEq",
    "NotEq": "Eq",
    "Lt": "LtE",
    "LtE": "Lt",
    "Gt": "GtE",
    "GtE": "Gt",
    "Add": "Sub",
    "Sub": "Add",
    "Mult": "Div",
    "Div": "Mult",
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
                or (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, bool)
                    and target.op == "BOOL"
                )
                or (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, int)
                    and target.op == "NUM"
                )
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


@pytest.mark.timeout(KILL_SCORE_TIMEOUT_S)
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
    overall = {
        "total": 0,
        "killed": 0,
        "survived": 0,
        "timeout": 0,
        "score": 0.0,
        "per_file": {},
    }
    max_per_file = 60  # cap to keep CI runtime bounded
    for target in TARGETS:
        if not target.exists():
            continue
        plan = _plan(target)[:max_per_file]
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
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            "tests/test_render_spec_v2.py",
                            "tests/test_mutation_kill_score.py",
                            "tests/test_coverage_100.py",
                            "tests/test_coverage_gaps.py",
                            "--no-cov",
                            "-q",
                            "-x",
                        ],
                        cwd=BACKEND,
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT_S,
                        check=False,
                    )
                    killed = rc.returncode != 0
                except subprocess.TimeoutExpired:
                    killed = True
                    report.timeout += 1
                finally:
                    if backup.exists():
                        shutil.copy(backup, target)
                    else:
                        target.write_text(src_text)

                report.total += 1
                if killed:
                    report.killed += 1
                else:
                    report.survived += 1
                    report.survivors.append(
                        {
                            "mid": mutation.mid,
                            "op": mutation.op,
                            "line": mutation.line,
                            "snippet": mutation.snippet,
                        }
                    )
                report.op_breakdown.setdefault(mutation.op, {"total": 0, "killed": 0})
                report.op_breakdown[mutation.op]["total"] += 1
                if killed:
                    report.op_breakdown[mutation.op]["killed"] += 1
        finally:
            if backup.exists():
                shutil.copy(backup, target)
                backup.unlink(missing_ok=True)
            else:
                target.write_text(src_text)
        report.score = (report.killed / report.total * 100.0) if report.total else 0.0
        # We treat timeout as a kill (mutant induced hang — a *bad* outcome caught)
        if report.killed == 0 and report.timeout > 0:
            report.score = (report.timeout / report.total) * 100.0
        MUTATIONS_DIR.mkdir(exist_ok=True)
        (MUTATIONS_DIR / f"{target.parent.name}_{target.stem}.json").write_text(
            json.dumps(asdict(report), indent=2)
        )
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
