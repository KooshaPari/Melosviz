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

from repo_paths import find_repo_root

# Marker walk instead of parents[2]: under mutmut the tests/ directory is one
# level deeper, so a fixed depth resolves to backend/ instead of the repo root.
REPO = find_repo_root(__file__)
# The package source is always at backend/src/. A previous version accepted
# either `REPO / "src"` or `REPO / "backend" / "src"` to allow running from
# either root, but the marker walk above can only ever return a directory
# holding `backend/`, so the first branch was dead: at the repo root
# `parents[2]` resolved to the root, `REPO / "src" / "melosviz"` did not exist,
# every entry in TARGETS failed to exist, the loop skipped all three, and
# overall["score"] stayed 0.0 against a 75.0 bar. Keep the one real path.
SRC = REPO / "backend" / "src"
BACKEND = SRC.parent
MUTATIONS_DIR = REPO / ".mutations"
TARGETS = [
    SRC / "melosviz" / "analysis" / "models.py",
    SRC / "melosviz" / "analysis" / "audio.py",
    SRC / "melosviz" / "bridge" / "server.py",
]
# Mutations applied per target file. Read by BOTH the loop below and
# SUBPROCESS_CEILING_S, so the budget cannot drift from the work.
MAX_PER_FILE = 60
TIMEOUT_S = 60
TARGET_SCORE = 75.0
# Ceiling on the share of mutants that produced no verdict at all. A single
# mutant-induced hang is a legitimate kill signal (the mutation broke the
# suite badly enough to wedge it), so this is not zero; but a run where a large
# fraction is unmeasured cannot support a 75% claim, and the honest number then
# depends entirely on whether timeouts are counted. See the scoring block.
MAX_TIMEOUT_RATIO = 0.10
# Wall-clock budget for the whole test, derived from the work it does rather
# than picked to make today's run pass.
#
# The test runs up to max_per_file(60) mutations per target across len(TARGETS)
# targets, and every mutation is a separate pytest subprocess over four test
# files, each capped at TIMEOUT_S. The hard ceiling on subprocess time alone is
# therefore
#     len(TARGETS) * MAX_PER_FILE * TIMEOUT_S = 3 * 60 * 60 = 10800s = 3h
# and the per-mutation AST re-parse, file write/restore, and the JSON report
# writes all count against the outer budget on top of that. Setting the budget
# equal to the ceiling leaves zero headroom, so a run in which every mutant
# hangs exhausts it inside subprocess.run and the outer timeout fires
# mid-measurement -- exactly the "reports Timeout instead of a kill score, with
# no partial results" failure this change exists to eliminate.
#
# So the budget is sized ABOVE the ceiling, at 1.5x, and the per-subprocess caps
# remain the thing that actually bounds the run. On healthy hardware the
# measured average is ~48s per subprocess (~320 tests, dominated by the audio
# tests), giving a real runtime around 65s for the three targets -- well inside
# even the old 300s, so this is headroom for the pathological case, not a
# slower gate.

#
# The ordering this depends on, which is not automatic: the budget must
# fire BEFORE the platform kills the job, or it never produces the
# diagnostic it exists to produce. Inside GitHub Actions,
#     pytest-timeout (this value)  <  job `timeout-minutes`  <  360min default
# and the gate job runs this test with NO `timeout-minutes` of its own, so it
# inherits the 360-minute default. A budget at or above 360min is therefore
# unusable: it would sit on or past the platform cap, and pytest-timeout could
# never fire first, leaving this marker silently redundant rather than
# load-bearing. At 1.5x the 3h ceiling (270min) the ordering holds with 90
# minutes of platform headroom.
#
# What does NOT set this budget: `.github/workflows/mutmut.yml`. That job has
# its own `timeout-minutes: 360` and runs `uv run mutmut run`, whose scope comes
# from [tool.mutmut] source_paths = ["src/melosviz/"] -- the whole package, not
# these three TARGETS. It never collects this test, so the 3 * 60 * 60
# derivation above describes this test's own worst case and has no bearing on
# that job's budget, nor does that job's cap constrain this one. An earlier
# revision of this comment claimed the two "have to move together" and cited a
# "420 cap" that no longer exists; neither claim was true.
#
# The old budget was @pytest.mark.timeout(300) -- 5 minutes for work that can
# legitimately take hours. It only ever passed because killed mutants exit early
# under -x; a single surviving mutant, which by definition runs the entire
# suite, blew it. Dispatched run 36957966430 against e3f3ddd is that case:
#     FAILED tests/test_mutation_engine.py::test_mutation_kill_score_meets_qgate_bar
#       - Failed: Timeout (>300.0s) from pytest-timeout
# The bar being enforced is the 75% kill score, not a duration, so a budget that
# fires before the measurement completes destroys the thing it protects.
# The subprocess ceiling, named so the multiplier below cannot drift away
# from the work it is sizing. 3 targets * 60 mutations * 60s = 10800s = 3h.
SUBPROCESS_CEILING_S = 3 * MAX_PER_FILE * TIMEOUT_S
KILL_SCORE_TIMEOUT_S = SUBPROCESS_CEILING_S * 3 // 2  # 16200s = 270min


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
                # Per-mutant, not a running total: `report.timeout` is
                # cumulative, so it cannot answer "did THIS mutant time out?"
                # which is the only question the survivor branch needs to ask.
                timed_out = False
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
                    # A timeout is not a kill: the suite never reported a
                    # failing assertion, so nothing is proven about the mutant.
                    # Counted separately so the gate can require the bar to be
                    # met by real kills and can bound how much of the run was
                    # unmeasured.
                    killed = False
                    timed_out = True
                    report.timeout += 1
                finally:
                    if backup.exists():
                        shutil.copy(backup, target)
                    else:
                        target.write_text(src_text)

                report.total += 1
                if killed:
                    report.killed += 1
                elif timed_out:
                    # Unmeasured, not survived. A timed-out mutant never reached a
                    # verdict, so listing it under `survived` would assert that
                    # the suite ran to completion and still passed -- the exact
                    # unproven claim this change set out to remove. It stays out
                    # of `survived` and out of the `survivors` triage list, so
                    # that list holds only mutants the suite genuinely finished
                    # and escaped. The score arithmetic is unaffected: it is
                    # killed / total, and total still counts every mutant.
                    pass
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
        # A timeout is NOT a kill, which is why `killed` is False on that path
        # above. That single fact is what closes the vacuous-green hole: an
        # uncollectable suite (a bad `pythonpath`, a missing test module, an
        # import cycle) turns every mutant into a 60s hang, every mutant counts
        # as unmeasured, killed stays 0, and this expression yields 0.0 rather
        # than the 100% it used to score. No separate `timeout == total` branch
        # is needed or present -- it would have duplicated a guarantee the
        # arithmetic already makes.
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
    # Timeouts are excluded from `killed` above, so they already depress the
    # score. This bound catches the degenerate case explicitly rather than
    # relying on the arithmetic: if a large share of the run never produced a
    # verdict, the remaining kills say little about the suite. A high timeout
    # count here almost always means the mutated tree was uncollectable (bad
    # pythonpath, missing test module, import cycle), which is a broken
    # measurement, not a passing one.
    timeout_ratio = overall["timeout"] / overall["total"] if overall["total"] else 0.0
    assert timeout_ratio <= MAX_TIMEOUT_RATIO, (
        f"{timeout_ratio:.0%} of mutants timed out without a verdict "
        f"({overall['timeout']}/{overall['total']}), which is above the "
        f"{MAX_TIMEOUT_RATIO:.0%} ceiling; the kill score below is not "
        f"trustworthy when most mutants went unmeasured"
    )
    assert overall["score"] >= TARGET_SCORE, (
        f"mutation kill-score {overall['score']:.1f}% below qgate bar "
        f"{TARGET_SCORE}%; killed={overall['killed']}/{overall['total']} "
        f"(timeouts={overall['timeout']} do not count as kills)"
    )
