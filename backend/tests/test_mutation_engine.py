"""Mutation engine — drives the antigame spectrum at test time.

Walks a small set of MelosViz source modules, generates a deterministic AST
mutation plan, applies each mutation in a temp copy, runs the existing
pytest suite against it, and records:
  * total mutations generated
  * killed (tests fail against the mutated source)
  * survived (tests still pass — the qgate BUG)
  * kill-score percentage

This runs in-process — no fork/spawn — so it works on every platform.
It is the *durable, runnable evidence* behind the mutation kill-score gate. The
floor it enforces is TARGET_SCORE below, which is deliberately NOT the 75% in
.qgate.toml -- see the comment on that constant for why the two numbers govern
different sweeps.

Use:
    pytest tests/test_mutation_engine.py -q -s
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field

import pytest
from mutation_engine import apply_one, plan_file
from mutation_gate_config import (
    BACKEND,
    EXIT_CODE_ABORT,
    EXIT_CODE_KILLED,
    EXIT_CODE_UNMEASURED,
    INNER_PYTEST_ARGS,
    KILL_SCORE_TIMEOUT_S,
    MAX_PER_FILE,
    MAX_TIMEOUT_RATIO,
    MAX_UNMEASURED_RATIO,
    META_TEST_NODEID,
    MUTATIONS_DIR,
    MUTMUT_TEST_SELECTION_ARGS,
    PER_TARGET_TESTS,
    SRC,
    TARGET_SCORE,
    TARGETS,
    TIMEOUT_S,
    classify_exit_code,
    inner_basetemp,
)


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
    # How many sites the planner found for this target, before any budget cut.
    # Recorded because the gate measures a STRIDE of the plan, so `total` is a
    # sample and the sites left unmeasured are otherwise invisible -- nothing
    # in the report would distinguish "every site was measured and 70% were
    # killed" from "60 of 442 sites were measured and all 60 were killed".
    planned: int = 0
    # Planned mutants that never became mutants: the applier could not alter the
    # site, or the emitted text was identical to the original or to an earlier
    # mutant. Counted separately so they neither inflate the denominator nor
    # hide in the survivor list, which must hold only mutants the suite
    # genuinely ran and escaped.
    rejected: int = 0
    rejections: list[dict] = field(default_factory=list)
    # Mutants whose pytest run exited with a code that means NO ASSERTION RAN:
    # 2 (interrupted, which is what a collection error reports) or 3 (internal
    # error), either of which the mutant itself can cause. These are not kills,
    # and they are not survivors either -- a survivor asserts the suite ran to
    # completion and passed, which is exactly as untrue here. Codes 4 and 5 are
    # environment failures and abort the run instead of landing in this bucket,
    # so what is tracked here is specifically the mutant-caused unmeasured share.
    unmeasured: int = 0
    # The test files this target's mutants were run against. Recorded so a low
    # score can be triaged against the selection that produced it instead of
    # guessed at: a mutant on a line the selection never executes is invisible,
    # and that is visible here but nowhere else.
    selection: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0


@pytest.mark.timeout(KILL_SCORE_TIMEOUT_S)
@pytest.mark.skipif(
    not (SRC / "melosviz" / "analysis" / "models.py").exists(),
    reason="melosviz analysis models not in this checkout",
)
def test_mutation_kill_score_meets_qgate_bar() -> None:
    """Drive the mutation engine across the antigame-targeted source files
    and assert the TARGET_SCORE bar is met.

    Runable evidence behind the bar — measures how many mutants the
    integration tests actually kill.  Each targeted file gets its own AST
    plan + applied mutations; per-file reports are written to
    `.mutations/<file>.json`.
    """
    overall = {
        "total": 0,
        "killed": 0,
        "survived": 0,
        "timeout": 0,
        "unmeasured": 0,
        "rejected": 0,
        # Sites the planner found, summed over targets. Larger than `total`
        # because the gate measures a stride of each plan, so this is the
        # honest denominator for "how much of this source was left unmeasured".
        "planned": 0,
        "score": 0.0,
        "per_file": {},
    }
    for target in TARGETS:
        if not target.exists():
            continue
        if not plan_file(target):
            continue
        src_text = target.read_text()
        report = MutationReport(target=str(target))
        # Tests scoped to THIS module. A mutant on a line nothing in this list
        # executes cannot be killed by any assertion, so the selection is the
        # binding constraint on the score -- see PER_TARGET_TESTS.
        selection = PER_TARGET_TESTS.get(
            target.name,
            [
                "tests/test_render_spec_v2.py",
                "tests/test_mutation_kill_score.py",
                "tests/test_coverage_100.py",
                "tests/test_coverage_gaps.py",
            ],
        )
        report.selection = list(selection)
        # This check runs BEFORE the sidecar is written, and that ordering is
        # load-bearing. The assert below used to sit between the sidecar being
        # created and the try/finally that cleans it up, so a selection naming a
        # file that no longer existed fired the assert with
        # `<target>.py.mutbak` already sitting beside its source and nothing to
        # remove it. The guard comment further down explains why the sidecar has
        # an owner at all; it is only true for statements that run after the
        # guard. Checking the selection first keeps that invariant true for the
        # whole prologue: nothing between here and the guard can create a file.
        #
        # Impact of the old ordering was bounded -- `.mutbak` is gitignored and
        # the next run overwrites it -- but it left an unexplained artifact under
        # src/melosviz/, which is the sort of thing a later reader mistakes for
        # real source.
        missing = [p for p in selection if not (BACKEND / p).is_file()]
        assert not missing, f"{target.name}: selection files missing: {missing}"
        backup = target.with_suffix(".py.mutbak")
        shutil.copy(target, backup)
        # The no-op baseline is the original source put through the SAME renderer
        # the applier uses, so a mutant that changes nothing compares equal.
        # `mutated` is `ast.unparse(...)` output; comparing it to the raw file
        # text could never match, because unparsing normalises formatting and
        # discards comments.
        baseline_text = ast.unparse(ast.parse(src_text))
        # Every mutant is measured by running this exact selection, so a selection
        # that cannot run at all would fail fast and identically for every mutant.
        # Under `killed = rc.returncode != 0` that reads as 100% kills with nothing
        # executed, which is how a renamed test file could turn this gate green.
        # Require the unmutated selection to be green once, before any mutant is
        # measured, so a broken selection fails loudly instead of inflating the
        # score.
        #
        # The baseline run sits inside this try/except rather than before it.
        # `backup` already exists at this point, so the except has a sidecar to
        # clean up; anything that could fire BEFORE the sidecar was created has
        # been moved above, which is what makes that cleanup sufficient.
        try:
            baseline_rc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *selection,
                    *INNER_PYTEST_ARGS,
                    f"--basetemp={inner_basetemp(f'{target.name}-baseline')}",
                ],
                cwd=BACKEND,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                check=False,
            )
            assert baseline_rc.returncode == 0, (
                f"{target.name}: unmutated selection is not green "
                f"(rc={baseline_rc.returncode}); every kill would be vacuous. "
                f"tail: {baseline_rc.stdout[-500:]}"
            )
        except BaseException:
            # Nothing is mutated at this point, so restoring `target` is not
            # needed -- only the sidecar has an owner now.
            if backup.exists():
                backup.unlink(missing_ok=True)
            raise
        # Walk the WHOLE plan, not a prefix, and accept mutants until the budget
        # is full. Truncating first would waste the budget on entries that dedup
        # or get rejected later, silently shrinking the measured set.
        seen_texts: set[str] = set()
        accepted = 0
        # Measure a STRIDE of the plan, not a prefix. `_Indexer` records sites
        # children-before-parent and top-of-file first, so taking the first
        # MAX_PER_FILE entries measures the head of each file and says nothing
        # about the rest. That is not just imprecise, it breaks the denominator
        # TARGET_SCORE is derived from: the 72.2% reachability figure is over
        # 597 PLANNED sites while the gate measures at most 3 + 60 + 60 = 123,
        # and because the three files have very different reachability (server.py
        # 38.2%, models.py 100%) an unrepresentative prefix can land the sampled
        # score below the bar. Note the figure bounds kills from below rather than
        # capping them -- strict executed_lines matching undercounts, and a
        # ground-truth run killed 5 of 16 mutants it called unreachable; see the
        # re-derivation note in mutation_gate_config.py.
        #
        # Spreading the measured sites across the whole plan keeps the
        # set proportional to the file, so the sampled reachability tracks the
        # real one. The interval is recomputed per target because the plans
        # differ in size by two orders of magnitude.
        plan = plan_file(target)
        # Sample by INDEX INTERVAL rather than a fixed stride.
        #
        # A fixed stride cannot do both jobs at once: a large stride spans the
        # file but leaves the budget unfilled (a stride of 7 over 442 sites picks
        # 31, not the 60 the budget allows), and a stride of 1 fills the budget
        # but is a prefix again. Spacing the picks evenly at
        # `len(plan) / MAX_PER_FILE` intervals fills the budget exactly AND spans
        # the file, which is the point of sampling rather than truncating.
        # For plans no larger than the budget the step is <= 1, so every site is
        # measured and a small file behaves exactly as before.
        step = max(1.0, len(plan) / MAX_PER_FILE)
        report.planned = len(plan)
        try:
            for position, mutation in enumerate(plan):
                # Land on each sampling boundary, plus the final site so the
                # tail of the file is never excluded.
                # The `position == 0` disjunct is not just readability: it is
                # what keeps `(position - 1) / step` from being evaluated at
                # position 0, where it would index one before the start. Written
                # as a bare ternary the whole comparison is conditional, which
                # reads as `int(...) != (int(...) if position else True)` to
                # anyone editing it later.
                on_sample = position == 0 or int(position / step) != int((position - 1) / step)
                if not on_sample and position != len(plan) - 1:
                    continue
                if accepted >= MAX_PER_FILE:
                    break
                try:
                    mutated = apply_one(src_text, mutation)
                except RuntimeError as exc:
                    report.rejected += 1
                    report.rejections.append(
                        {
                            "mid": mutation.mid,
                            "op": mutation.op,
                            "line": mutation.line,
                            "snippet": mutation.snippet,
                            "reason": str(exc),
                        }
                    )
                    continue
                # Two independent guards on the emitted bytes. `_apply_one`
                # proves a node was altered, but the driver additionally refuses
                # text identical to the original or to a mutant already measured,
                # because either one would be booked twice for a single change.
                #
                # The no-op comparison is against the UNPARSED ORIGINAL, not
                # `src_text`. `mutated` comes from `ast.unparse`, which
                # renormalises quotes and whitespace and drops every comment, so
                # it never equals the raw file text -- comparing against
                # `src_text` made this guard unreachable, and a mutation that
                # altered nothing would have been measured as a real mutant.
                if mutated == baseline_text:
                    report.rejected += 1
                    report.rejections.append(
                        {
                            "mid": mutation.mid,
                            "op": mutation.op,
                            "line": mutation.line,
                            "snippet": mutation.snippet,
                            "reason": "emitted text identical to the original",
                        }
                    )
                    continue
                if mutated in seen_texts:
                    report.rejected += 1
                    report.rejections.append(
                        {
                            "mid": mutation.mid,
                            "op": mutation.op,
                            "line": mutation.line,
                            "snippet": mutation.snippet,
                            "reason": "duplicate of an already-measured mutant",
                        }
                    )
                    continue
                seen_texts.add(mutated)
                accepted += 1
                target.write_text(mutated)
                # Per-mutant, not a running total: `report.timeout` is
                # cumulative, so it cannot answer "did THIS mutant time out?"
                # which is the only question the survivor branch needs to ask.
                timed_out = False
                # Same shape, same reason: `report.unmeasured` is cumulative, so
                # the survivor branch needs a per-mutant flag to avoid booking a
                # mutant that pytest could not even collect as one the suite
                # finished and passed.
                unmeasured = False
                try:
                    rc = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            *selection,
                            *INNER_PYTEST_ARGS,
                            f"--basetemp={inner_basetemp(f'{target.name}-m{accepted}')}",
                        ],
                        cwd=BACKEND,
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT_S,
                        check=False,
                    )
                    # Exit codes that mean "no assertion ran" are not evidence
                    # that the mutant was caught, and booking them as kills is
                    # what let a broken selection score 100%. `classify_exit_code`
                    # owns the whole mapping, including which codes abort the run
                    # and which mark only this mutant unmeasured; see
                    # _ENVIRONMENT_FAILURES / _MUTANT_FAILURES for why they
                    # split.
                    verdict = classify_exit_code(rc.returncode)
                    if verdict == EXIT_CODE_ABORT:
                        raise RuntimeError(
                            f"{target.name}: pytest could not run the selection "
                            f"(rc={rc.returncode}); kills would be vacuous. "
                            f"tail: {rc.stdout[-500:]}"
                        )
                    # 2, 3 and 6 can be the mutant's own doing -- a broken
                    # import, a plugin crash, or a run that passed but blew a
                    # warnings threshold -- so this one mutant is unmeasured
                    # rather than the whole run. Aborting here would kill the
                    # sweep the first time a mutant made a module unimportable,
                    # which is an ordinary outcome of mutation rather than a
                    # defect in the measurement. The ratio assertion below bounds
                    # how much of the run can land here.
                    if verdict == EXIT_CODE_UNMEASURED:
                        report.unmeasured += 1
                        unmeasured = True
                    killed = verdict == EXIT_CODE_KILLED
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
                elif timed_out or unmeasured:
                    # Unmeasured, not survived. A timed-out mutant never reached a
                    # verdict, so listing it under `survived` would assert that
                    # the suite ran to completion and still passed -- the exact
                    # unproven claim this change set out to remove. It stays out
                    # of `survived` and out of the `survivors` triage list, so
                    # that list holds only mutants the suite genuinely finished
                    # and escaped. The score arithmetic is unaffected: it is
                    # killed / total, and total still counts every mutant.
                    #
                    # A mutant-caused collection or internal error is the same
                    # shape of absence for a different reason: pytest stopped
                    # before any assertion ran, so nothing survived it either.
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
        # Accumulated alongside the rest, because the unmeasured-share assertion
        # below reads `overall["unmeasured"]`. It was not being summed at all:
        # this line read `report.infrastructure`, a field the dataclass does not
        # declare, so the whole assertion raised AttributeError before the score
        # was ever checked. Worse, `overall` had no "unmeasured" key either, so
        # even with a dataclass field the ratio line would have raised KeyError.
        # Both halves are now consistent, and the run's own printed summary
        # carries the count, so a run that trips the ceiling says how many.
        overall["unmeasured"] += report.unmeasured
        overall["rejected"] += report.rejected
        overall["planned"] += report.planned
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
        f"(timeouts={overall['timeout']} do not count as kills, "
        f"rejected={overall['rejected']} never became mutants)"
    )
    # Rejections shrink `total`, which is the score's DENOMINATOR, so a plan that
    # starts collapsing into rejections raises the score with nothing failing.
    # `MAX_TIMEOUT_RATIO` bounds the unmeasured-by-timeout share but nothing
    # bounded this one; only the failure message above mentions the count, and
    # that renders when the gate is already red. The honest expectation is
    # that a correct planner/applier pair rejects nothing, so assert that
    # outright rather than allowing a proportional slack: every rejection is a
    # phantom mutant the no-op and dedup guards exist to prevent.
    assert overall["rejected"] == 0, (
        f"{overall['rejected']} planned sites never became mutants; a correct "
        f"planner/applier pair rejects none, and rejections shrink the "
        f"denominator ({overall['killed']}/{overall['total']})"
    )
    # `killed` is now `rc == 1`, so a mutant-caused collection or internal error
    # (2, 3) is neither a kill nor a survivor. That is the honest verdict -- no
    # assertion ran -- but bounded by ratio rather than asserted zero, because a
    # mutant that makes its module unimportable is an ordinary outcome of
    # mutation, not a defect in the measurement. Zero would make the gate fail
    # on a healthy suite.
    #
    # The share matters because these mutants depress the score without being
    # counted anywhere else: not killed, not survived, not timed out. Without
    # this bound, a source change that made one module unimportable under
    # mutation would silently pull the bar down. With it, a large share fails
    # loudly as a broken measurement. Codes 4 and 5 never reach here -- they
    # abort the run outright, because they are identical for every mutant.
    unmeasured_ratio = overall["unmeasured"] / overall["total"] if overall["total"] else 0.0
    assert unmeasured_ratio <= MAX_UNMEASURED_RATIO, (
        f"{unmeasured_ratio:.0%} of mutants could not be run to a verdict "
        f"({overall['unmeasured']}/{overall['total']}) because pytest exited 2 "
        f"or 3 on them, which is above the {MAX_UNMEASURED_RATIO:.0%} ceiling; "
        f"a mutant that breaks collection proves nothing either way, so the "
        f"kill score below is not trustworthy when this is high"
    )


def test_meta_test_deselect_still_matches_exactly_one_test() -> None:
    """Assert the recursion guard still points at a real test.

    `--deselect` is a FILTER, not an assertion. If the nodeid in
    [tool.mutmut].pytest_add_cli_args stops matching -- because the test is
    renamed, moved, or wrapped -- pytest collects and runs it anyway and reports
    no error at all. The recursion this guard exists to prevent then returns in
    full: the outer sweep runs this module once per outer mutant, and this module
    drives its own nested mutation sweep. Across the ~26506 mutants the workflow
    reports, that is the whole self-recursion, and the only symptom is a job
    that quietly stops finishing.

    A comment cannot catch that, and neither can reading the config. So resolve
    the nodeid the way pytest does and assert it selects exactly one collected
    test. This runs `pytest --collect-only` against the same selection the
    mutation sweep uses, which is cheap (no test bodies execute).
    """
    backend = BACKEND
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *MUTMUT_TEST_SELECTION_ARGS,
            "--deselect",
            META_TEST_NODEID,
        ],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, (
        f"collect-only failed (rc={result.returncode}); the deselect nodeid may "
        f"be malformed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
    )
    collected = sum(
        1 for line in result.stdout.splitlines() if "::" in line and line.startswith("tests/")
    )
    # Without the guard this module's one test is collected alongside the rest,
    # so the deselect must remove exactly one node from a non-empty selection.
    # Asserting the exact delta rather than the absolute count keeps the check
    # honest if the suite grows: it verifies the filter fires, not the size of
    # the suite.
    baseline = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *MUTMUT_TEST_SELECTION_ARGS,
        ],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert baseline.returncode == 0, f"baseline collect failed:\n{baseline.stdout[-2000:]}"
    baseline_count = sum(
        1 for line in baseline.stdout.splitlines() if "::" in line and line.startswith("tests/")
    )
    assert baseline_count > 0, "baseline collection was empty, so the check is vacuous"
    assert baseline_count - collected == 1, (
        f"--deselect {META_TEST_NODEID} removed "
        f"{baseline_count - collected} tests, expected exactly 1 "
        f"(baseline {baseline_count}, deselected {collected}). If this is 0 the "
        f"nodeid no longer matches and the outer mutation sweep will recurse "
        f"into this module."
    )
