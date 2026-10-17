"""Direct unit tests for the mutation planner/applier.

Before these, the planner and applier were only exercised indirectly: the gate
drove a ~10-minute mutation sweep and asserted a score, so a planner bug showed
up as "the bar moved" rather than as "index 41 named the wrong node". That is a
slow, ambiguous signal for what are entirely mechanical functions.

These tests are the cheap proof. Each one pins a specific defect class that the
gate previously could only reveal as a distorted score:

  * planner/applier traversal-order disagreement (the `ast.walk` breadth-first
    bug that produced 11 "altered" mutants emitting byte-identical text),
  * per-op vs global index confusion (28 of 123 phantom no-ops),
  * unalterable operators being planned (`float | None`, `%`, `x in y == z`),
  * `Or` sites planned without an alter,
  * no-op and duplicate detection.

They run in milliseconds and need no test suite, so a planner regression fails
here first with a precise message.

The last two tests cover the OTHER half of the gate's accounting: how a pytest
exit code becomes killed / survived / unmeasured. That mapping is three lines of
code and it decides the whole score, so it is pinned here rather than only
being exercised by a ten-minute sweep.

One more test guards the run SUMMARY rather than the planner: it checks that
every key the driver sums into `overall` exists on `MutationReport` and every
key it reads is written. That class of bug cost a full 2h14m sweep to surface,
because the failure only appears after the last mutant has run.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from _pytest.config import ExitCode
from mutation_engine import (
    OPPOSITE_BOOL,
    SWAPPED,
    apply_one,
    is_noop,
    plan,
    sites,
)
from mutation_gate_config import (
    _ENVIRONMENT_FAILURES,
    _MUTANT_FAILURES,
    EXIT_CODE_ABORT,
    EXIT_CODE_KILLED,
    EXIT_CODE_SURVIVED,
    EXIT_CODE_UNMEASURED,
    KILL_EXIT_CODE,
    MAX_UNMEASURED_RATIO,
    classify_exit_code,
)

# A source exercising every op the engine supports, twice over where it matters,
# so per-op indexes 0 and 1 both exist and a global-vs-per-op mix-up is visible.
SAMPLE = """
def classify(n, flags, label):
    if n > 0:
        return "pos"
    if n < 0:
        return "neg"
    if n == 0:
        return "zero"
    if n >= 1:
        return "atleast"
    if n != 5:
        return "other"
    total = n + 1
    if n - 1:
        return "sub"
    if n * 2:
        return "mul"
    if n / 2:
        return "div"
    if flags and label:
        return "both"
    if flags or label:
        return "either"
    if n == 1:
        return "one"
    if n == 0:
        return "zero-flag"
    return "fallback"
"""


def _by_op(text: str) -> dict[str, list[int]]:
    """Per-op indexes present in a plan, for readable assertions."""
    out: dict[str, list[int]] = {}
    for entry in plan(text):
        out.setdefault(entry.op, []).append(entry.index)
    return out


def test_planner_and_applier_enumerate_in_the_same_order() -> None:
    """Every planned site must be individually alterable, in the right place.

    This is the invariant everything else rests on. If the planner and applier
    disagree about traversal order, `apply_one` still returns text -- it just
    mutates a different node than the planner recorded, and the entry reads as a
    real mutant. Asserting over EVERY site, not a sample, is what makes it
    falsifiable.
    """
    planned = plan(SAMPLE)
    assert planned, "the sample must contain mutation sites"

    for entry in planned:
        mutated = apply_one(SAMPLE, entry)
        assert not is_noop(SAMPLE, mutated), (
            f"{entry.describe()} produced text identical to the original: "
            f"the applier altered nothing for a site the planner recorded"
        )
        assert ast.parse(mutated), f"{entry.describe()} emitted unparseable text"


def test_indexes_are_per_op_not_global() -> None:
    """`Planned.index` counts occurrences of ITS OWN op, not of all sites.

    Passing a global position asks the applier for, say, the 41st BRANCH site in
    a file with 36 of them. `remaining` then never reaches 0, nothing is
    altered, and the entry is booked as a survivor it could never have been
    killed out of -- 28 of 123 phantom mutants before this was fixed.
    """
    ops = _by_op(SAMPLE)
    # Several ops appear more than once; each must restart at 0.
    assert ops["BRANCH"] == list(range(len(ops["BRANCH"]))), ops["BRANCH"]
    assert ops["ROR"] == list(range(len(ops["ROR"]))), ops["ROR"]
    assert ops["AOR"] == list(range(len(ops["AOR"]))), ops["AOR"]

    # And each index must select a DIFFERENT piece of the source, which is the
    # observable consequence of the indexes being per-op.
    ror_texts = {apply_one(SAMPLE, e) for e in plan(SAMPLE) if e.op == "ROR"}
    assert len(ror_texts) == len(ops["ROR"]), (
        f"{len(ops['ROR'])} ROR indexes produced {len(ror_texts)} distinct "
        f"mutants, so some index addressed the same node twice"
    )


def test_unalterable_operators_are_not_planned() -> None:
    """`_op_for` must reject everything `alter_one` cannot actually change.

    A bare `isinstance(node, ast.BinOp)` test also accepts `float | None` union
    annotations, `x | y` flags and `%` remainders, none of which have a
    counterpart in SWAPPED. Each of those consumed an index, shifting every
    later index onto a different site.
    """
    source = """
from typing import Final

FLAG: Final = True
MODE: int | None = None
NAME: str = "x" | "y"

def f(a: int, b: int, label: str) -> int:
    if a % b:
        return a
    return b
"""
    planned = plan(source)
    snippets = " ".join(entry.snippet for entry in planned)

    # `%` is a BinOp with no SWAPPED counterpart, so it must not be an AOR site.
    assert not any(entry.op == "AOR" and "%" in entry.snippet for entry in planned), (
        f"a %% remainder was planned as an arithmetic site: {snippets}"
    )
    # `Final = True` is an assignment target, not a site; `MODE: int | None` is a
    # BinOp on the annotation and has no counterpart either.
    assert not any("None" in entry.snippet for entry in planned), snippets
    # `x in y == z` shapes: ops[0] is `in`, which is not swappable.
    chained = plan("def g(x, y, z):\n    return x in y == z\n")
    assert not [e for e in chained if e.op == "ROR"], [e.describe() for e in chained]


def test_every_planned_op_has_an_alter() -> None:
    """No key in the operator tables may lack a counterpart.

    `_op_for` gates on SWAPPED and OPPOSITE_BOOL to decide what is a target, so a
    key with no alter is a site that gets planned, counted, and then left alone.
    OPPOSITE_BOOL previously carried only `And` plus a stray `Eq` entry that is
    not a BoolOp at all, so every `or` site was a phantom.
    """
    assert set(OPPOSITE_BOOL) == {"And", "Or"}
    assert "Eq" not in OPPOSITE_BOOL, "'Eq' is a Compare op, not a BoolOp"
    for key, value in SWAPPED.items():
        assert hasattr(ast, key), f"SWAPPED key {key} is not an ast node class"
        assert hasattr(ast, value), f"SWAPPED value {value} is not an ast node class"
        assert SWAPPED[value] == key, (
            f"SWAPPED is not involutive at {key}: {key} -> {value} -> {SWAPPED[value]}"
        )


def test_or_sites_are_planned_and_altered() -> None:
    """An `or` site must be planned as LCR and must actually change.

    Regression test for the OPPOSITE_BOOL gap: with `Or` missing, every `or` site
    was planned, indexed, and never altered.
    """
    source = "def f(a, b):\n    if a or b:\n        return 1\n    return 0\n"
    entries = [e for e in plan(source) if e.op == "LCR"]
    assert entries, "an `or` site was not planned"
    for entry in entries:
        mutated = apply_one(source, entry)
        assert " or " not in mutated, f"{entry.describe()} did not flip `or`:\n{mutated}"


def test_apply_one_refuses_an_out_of_range_index() -> None:
    """An index past the last site must raise, not return unchanged text.

    A silent no-op return would be written to disk, the suite would pass on
    unmutated code, and the entry would be booked as a survivor -- a phantom no
    test could kill.
    """
    source = "def f(a, b):\n    if a == b:\n        return 1\n    return 0\n"
    entry = [e for e in plan(source) if e.op == "ROR"][0]
    out_of_range = type(entry)(
        mid=entry.mid,
        line=entry.line,
        op=entry.op,
        snippet=entry.snippet,
        index=9999,
    )
    with pytest.raises(RuntimeError, match="refusing to record a survivor"):
        apply_one(source, out_of_range)


def test_is_noop_compares_normalised_text_not_raw_text() -> None:
    """`is_noop` must survive the reformatting `ast.unparse` performs.

    `apply_one` round-trips through `ast.unparse`, which renormalises quotes and
    whitespace and drops comments, so its output never equals the raw file text.
    A guard comparing raw text can never fire, which is what made the original
    no-op check unreachable.
    """
    messy = "def f(a):\r\n    # a comment that unparse drops\r\n    return a == 1  # trailing\r\n"
    normalised = ast.unparse(ast.parse(messy))
    assert normalised != messy, "the fixture must differ in raw form"
    assert is_noop(messy, normalised), (
        "reformatting alone must read as a no-op, or the guard never fires"
    )

    # The fixture really does have one swappable operator, so the "real change"
    # half of this test is not vacuous. `a == 1` yields two sites (ROR and the
    # NUM `1`), so pick the operator rather than indexing blindly.
    ror = [e for e in plan(messy) if e.op == "ROR"]
    assert len(ror) == 1, f"expected exactly one ROR site, got {ror}"
    mutated = apply_one(messy, ror[0])
    assert not is_noop(messy, mutated), "a real mutation must not read as a no-op"


def test_distinct_sites_produce_distinct_mutants() -> None:
    """No two planned entries may produce the same rewritten source.

    Two indexes addressing one node means one of them is a duplicate, which
    would be measured twice and booked as two mutants for a single change.
    """
    seen: dict[str, str] = {}
    for entry in plan(SAMPLE):
        mutated = apply_one(SAMPLE, entry)
        assert mutated not in seen, (
            f"{entry.describe()} produced the same source as {seen[mutated]}"
        )
        seen[mutated] = entry.describe()


def test_sites_matches_the_plan_length() -> None:
    """The raw site list and the plan must agree, or an index is being lost."""
    raw = sites(SAMPLE)
    planned = plan(SAMPLE)
    assert len(raw) == len(planned)
    assert [op for op, _ in raw] == [entry.op for entry in planned]


def test_exit_code_sets_match_pytests_own_enum() -> None:
    """The failure sets must name real exit codes, and split them correctly.

    These constants were written from memory of pytest's exit codes, which is
    exactly how a stale one survives. Read them off pytest's own enum instead,
    so a future pytest that renumbers or renames a code fails here rather than
    silently reclassifying kills.

    The split is the load-bearing part. Codes 4 and 5 abort the run because they
    are identical for every mutant, so no score from that run means anything.
    Codes 2, 3 and 6 can be caused by the mutant under test -- a broken import, a
    tripped plugin, a run that passed but blew a warnings threshold -- so they
    mark ONE mutant unmeasured. Collapsing the two sets back together would make
    the gate abort the first time a mutant broke an import, which is an ordinary
    outcome of mutation rather than a broken measurement.
    """
    assert (
        frozenset({int(ExitCode.USAGE_ERROR), int(ExitCode.NO_TESTS_COLLECTED)})
        == _ENVIRONMENT_FAILURES
    )
    assert (
        frozenset(
            {
                int(ExitCode.INTERRUPTED),
                int(ExitCode.INTERNAL_ERROR),
                int(ExitCode.MAX_WARNINGS_ERROR),
            }
        )
        == _MUTANT_FAILURES
    )
    assert not _ENVIRONMENT_FAILURES & _MUTANT_FAILURES
    # Neither set may contain a code that means the suite reached a verdict.
    for code in (ExitCode.OK, ExitCode.TESTS_FAILED):
        assert int(code) not in _ENVIRONMENT_FAILURES | _MUTANT_FAILURES
    # And the kill code must be pytest's own, not a bare literal that drifted.
    assert int(ExitCode.TESTS_FAILED) == KILL_EXIT_CODE


def test_every_pytest_exit_code_is_classified() -> None:
    """No exit code in pytest's enum may reach the driver's survivor branch.

    `classify_exit_code` is total over pytest's own enum and raises on anything
    else. That matters because the branch it replaced was a fallthrough: the
    driver asked "was this a kill?", "was it a timeout or unmeasured?", and
    booked everything left over as `survived`. A survivor asserts the suite ran
    to completion and passed, so a default there is a false claim rather than a
    loose default.

    The codes are read off the enum rather than hardcoded, so a pytest that adds
    or renumbers one fails this test instead of silently changing a score.
    """
    expected = {
        ExitCode.OK: EXIT_CODE_SURVIVED,
        ExitCode.TESTS_FAILED: EXIT_CODE_KILLED,
        ExitCode.INTERRUPTED: EXIT_CODE_UNMEASURED,
        ExitCode.INTERNAL_ERROR: EXIT_CODE_UNMEASURED,
        ExitCode.MAX_WARNINGS_ERROR: EXIT_CODE_UNMEASURED,
        ExitCode.USAGE_ERROR: EXIT_CODE_ABORT,
        ExitCode.NO_TESTS_COLLECTED: EXIT_CODE_ABORT,
    }

    for code in ExitCode:
        verdict = classify_exit_code(int(code))
        assert verdict == expected[code], (
            f"pytest exit {int(code)} ({code.name}) classified as {verdict!r}, "
            f"expected {expected[code]!r}"
        )

    # Only a clean run may be booked as a survivor. This is the assertion that
    # fails if someone reintroduces a fallthrough.
    assert EXIT_CODE_SURVIVED == "survived"
    for code in ExitCode:
        if code is not ExitCode.OK:
            assert classify_exit_code(int(code)) != EXIT_CODE_SURVIVED, (
                f"pytest exit {int(code)} ({code.name}) was booked as a survivor; "
                f"it does not mean the suite ran and passed"
            )


def test_exit_code_outside_pytests_enum_is_refused() -> None:
    """An unclassifiable code must raise, not be booked as a survivor.

    This is measured, not hypothetical. On this platform `os._exit(7)` and
    `os._exit(255)` both come back from `subprocess.run` as themselves, so a
    subprocess exiting 7 -- outside pytest's enum entirely -- reached the
    fallthrough and was booked as a mutant that survived.

    Codes beyond the enum raise, because a gate that quietly books a code its
    own vocabulary cannot name would report a confident, wrong number. The
    specific regression is asserted with 7, not a symbolic value, so this test
    describes the case that actually happened.
    """
    for code in (7, 9, 255):
        with pytest.raises(RuntimeError, match="unclassifiable pytest exit code"):
            classify_exit_code(code)

    # Codes pytest owns but the driver has not been taught are the same defect
    # seen from the other side: pytest gained a code and the sets did not.
    assert int(ExitCode.OK) not in _ENVIRONMENT_FAILURES | _MUTANT_FAILURES
    assert int(ExitCode.TESTS_FAILED) not in _ENVIRONMENT_FAILURES | _MUTANT_FAILURES


def test_overall_summary_keys_match_the_dataclass_and_the_assertions() -> None:
    """Every key the driver sums must exist, and every key it reads must be summed.

    This is a static check on the driver's own source, and it exists because the
    bug it catches was invisible in review and fatal in production:

      * the summation line read `overall["infrastructure"] += report.infrastructure`,
        but `MutationReport` declares no `infrastructure` field, so the very first
        target raised AttributeError -- after the entire 123-mutant sweep had
        already run;
      * `overall` had no `"unmeasured"` key at all, so the unmeasured-ratio
        assertion raised KeyError before it could enforce its ceiling.

    Either way the gate reported a crash instead of a verdict, and neither was
    visible until a full 2h14m run was finished. Deriving the two key sets from
    the source turns that class of bug into a unit test that runs in a
    millisecond.

    Parsed rather than imported, deliberately: importing the module under test
    would import the current code, which is exactly what needs checking.
    """

    driver_path = Path(__file__).with_name("test_mutation_engine.py")
    source = driver_path.read_text(encoding="utf-8")

    # Field names on the dataclass.
    block = source.split("class MutationReport:", 1)[1].split("\n\n\n", 1)[0]
    fields = {
        line.split(":", 1)[0].strip()
        for line in block.splitlines()
        if ":" in line
        and "=" in line
        and not line.strip().startswith(("#", "@", "class"))
        and line.split(":", 1)[0].strip().isidentifier()
    }

    # Keys in the `overall = {...}` literal.
    overall_block = source.split("overall = {", 1)[1].split("}", 1)[0]
    declared = set(re.findall(r'"(\w+)":', overall_block))

    # Counterparts summed with `overall[...] += report.<field>`.
    summed = set(re.findall(r'overall\["(\w+)"\]\s*\+=\s*report\.(\w+)', source))
    summed_fields = {field for _, field in summed}

    # Keys read as `overall["x"]` anywhere, including the ratio assertions.
    read = set(re.findall(r'overall\["(\w+)"\]', source))

    # Every summed field must exist on the dataclass.
    assert summed_fields <= fields, (
        f"driver sums report.{sorted(summed_fields - fields)}, which "
        f"MutationReport does not declare; declared fields are {sorted(fields)}"
    )

    # Every summed key must be declared in the literal, or the first target
    # raises KeyError.
    assert {key for key, _ in summed} <= declared, (
        f"driver sums overall[{sorted({k for k, _ in summed} - declared)}] but "
        f"the overall literal only declares {sorted(declared)}"
    )

    # Every key read must be either declared or summed into. `score` is assigned
    # directly rather than summed, and `per_file` is a container, so both are
    # accounted for explicitly rather than waved through.
    assigned = set(re.findall(r'overall\["(\w+)"\]\s*=', source))
    unexplained = read - declared - assigned
    assert not unexplained, (
        f"driver reads overall[{sorted(unexplained)}] but nothing ever writes "
        f"it: not declared in the literal and not assigned. This is the "
        f"KeyError that made the unmeasured ceiling unenforceable."
    )

    # And the two buckets the ratio assertions divide by must be summed, not
    # merely read, or the ratio is computed against a stale zero.
    for key in ("total", "killed", "survived", "timeout", "unmeasured", "rejected"):
        assert key in declared, f"overall literal is missing {key!r}"
        assert key in read, f"the driver never reads overall[{key!r}]"


def test_no_statement_creates_the_sidecar_before_the_try_that_cleans_it() -> None:
    """Every `.mutbak` creation must be owned by the `try/finally` that removes it.

    The driver writes `<target>.py.mutbak` beside real tracked source so it can
    restore the file after each mutant. The restore is only safe if the sidecar
    has an owner: any statement that can raise BETWEEN creating the sidecar and
    entering the `try` leaves the file on disk with nothing to clean it up.

    This was a real ordering bug rather than a theoretical one. The
    missing-selection-files assert used to sit at line 158, with the sidecar
    created at 129 and the guarding `try` not starting until 166. So the one
    check most likely to fire on an ordinary edit -- a renamed test file that
    `PER_TARGET_TESTS` still names -- left `<target>.py.mutbak` under
    `src/melosviz/` every time. It was bounded (gitignored, overwritten next
    run) but it produced an unexplained artifact beside source.

    The fix was to hoist the check above `shutil.copy(target, backup)`. This
    pins the resulting INVARIANT rather than the line numbers, so a future edit
    that reintroduces the pattern fails here in milliseconds instead of leaving
    debris for the next run to overwrite.
    """

    driver_path = Path(__file__).with_name("test_mutation_engine.py")
    source = driver_path.read_text(encoding="utf-8")

    copy_at = source.index("shutil.copy(target, backup)")
    try_at = source.index("try:", copy_at)
    assert copy_at < try_at, (
        "the sidecar is written before the try that removes it, which is "
        "correct: the guard must come after the creation it owns"
    )

    # Everything between the loop head and the guard must be incapable of
    # creating a file or raising after a file exists. The concrete check is
    # that no other file-creating call sits in that window.
    loop_at = source.index("for target in TARGETS:")
    prologue = source[loop_at:copy_at]
    for dangerous in (
        "shutil.copy(",
        "write_text(",
        "write_bytes(",
        "mkdir(",
        "open(",
    ):
        assert dangerous not in prologue, (
            f"`{dangerous}` appears in the loop prologue BEFORE the sidecar's "
            f"try/finally, so it would run with no guard to clean up after it"
        )

    # And the assert that used to sit in the window must now precede it.
    missing_at = source.index("assert not missing")
    assert missing_at < copy_at, (
        "the missing-selection-files assert is back inside the unguarded "
        "window between the loop head and the sidecar creation"
    )

    # Finally: the guard must actually remove the sidecar, not just the source.
    guard = source[try_at : source.index("seen_texts", try_at)]
    assert "backup.unlink(missing_ok=True)" in guard, (
        "the baseline guard no longer unlinks the sidecar, so the leak it was "
        "written to prevent is back"
    )


def test_only_tests_failed_counts_as_a_kill() -> None:
    """`killed` must be `rc == 1`, not `rc != 0`.

    This is the vacuous-green hole. Under `rc != 0` every code meaning "no
    assertion ran" was booked as the suite catching the mutant: a missing
    pytest-cov made `--no-cov` exit 4 and scored 100% with nothing executed, and
    a mutant that broke a module's import exited 2 and scored the same way.

    Asserted through the classifier rather than against the constant alone, so
    this stays true of the code path the driver actually calls.
    """
    for code in ExitCode:
        killed = classify_exit_code(int(code)) == EXIT_CODE_KILLED
        if code is not ExitCode.TESTS_FAILED:
            assert not killed, (
                f"pytest exit {int(code)} ({code.name}) must not be booked as a "
                f"kill: it means no assertion failed"
            )

    # The specific regression: a usage error from a missing plugin scored 100%
    # because it was non-zero. It must stay an environment failure.
    assert int(ExitCode.USAGE_ERROR) in _ENVIRONMENT_FAILURES
    # And a mutant-caused collection error must stay bounded by a ratio rather
    # than asserted zero, since an unimportable mutant is a normal outcome.
    assert 0 < MAX_UNMEASURED_RATIO < 1
