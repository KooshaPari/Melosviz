"""Configuration for the Python mutation gate: what to measure, and against what.

Split out of ``test_mutation_engine.py`` so the driver's file is about running
the measurement rather than about justifying the numbers it measures.

The split matters because these constants have a much slower lifecycle than the
driver. ``TARGET_SCORE``, ``MAX_PER_FILE`` and the timeout budget are judgement
calls that get revisited whenever a measurement moves, and the reasoning behind
each one is long. Keeping that prose next to the constants is right; keeping it
in the middle of a driver that also does file I/O, subprocess management and
sampling is not, and it is what pushed the driver past 700 lines.

Three concerns live here and they are deliberately not separated further:

  * WHAT is mutated -- ``TARGETS``, the per-target test selections, and
    ``MUTMUT_*``, which mirror ``[tool.mutmut]`` so the two can be compared.
  * HOW MUCH -- ``MAX_PER_FILE``, ``TIMEOUT_S`` and the outer
    ``KILL_SCORE_TIMEOUT_S`` budget derived from them.
  * WHY the bar is where it is -- the reachability measurement, its known
    limits, and the gap between them.

The first two are inputs to the run; the third is the argument for the run
existing. They change together: changing the selection changes what it can
reach, and a change in measured kill performance is what moves the bar.
"""

from __future__ import annotations

import importlib.util
import os
import re
import tempfile
from pathlib import Path
from typing import Final

from repo_paths import find_repo_root

# Marker walk instead of parents[2]: under mutmut the tests/ directory is one
# level deeper, so a fixed depth resolves to backend/ instead of the repo root.
REPO: Final[Path] = find_repo_root(__file__)
# The package source is always at backend/src/. A previous version accepted
# either `REPO / "src"` or `REPO / "backend" / "src"` to allow running from
# either root, but the marker walk above can only ever return a directory
# holding `backend/`, so the first branch was dead: at the repo root
# `parents[2]` resolved to the root, `REPO / "src" / "melosviz"` did not exist,
# every entry in TARGETS failed to exist, the loop skipped all three, and
# overall["score"] stayed 0.0 against a 75.0 bar. Keep the one real path.
SRC: Final[Path] = REPO / "backend" / "src"
BACKEND: Final[Path] = SRC.parent
MUTATIONS_DIR: Final[Path] = REPO / ".mutations"
TARGETS: Final[list[Path]] = [
    SRC / "melosviz" / "analysis" / "models.py",
    SRC / "melosviz" / "analysis" / "audio.py",
    SRC / "melosviz" / "bridge" / "server.py",
]
# The recursion guard, as data, so the driver and [tool.mutmut] in
# backend/pyproject.toml can be checked against each other rather than merely
# asserted to agree. `--deselect` is a filter: pytest ignores a nodeid that
# matches nothing and reports no error, so a rename or a move here would
# silently restore the self-recursion instead of failing.
# test_mutation_engine.py asserts, through a real `--collect-only`, that this
# nodeid removes exactly one collected test.
META_TEST_NODEID: Final[str] = (
    "tests/test_mutation_engine.py::test_mutation_kill_score_meets_qgate_bar"
)
# Test paths the outer mutation sweep selects, mirroring
# [tool.mutmut].pytest_add_cli_args_test_selection.
MUTMUT_TEST_SELECTION_ARGS: Final[tuple[str, ...]] = ("tests/",)
#
# Which tests can observe a mutation in each target module.
#
# This used to be one hardcoded 4-file list applied to all three targets, which
# is the reason the kill score sat near 20% against a 75% bar. That number was
# not a weak-test problem: most of the mutated lines are never executed by those
# four files, so the mutants were UNOBSERVABLE rather than unasserted. Measured
# reachability ceilings (mutants whose source line the selection executes, so
# the strongest possible assertions could kill them):
#
#     selection                    models.py  audio.py  server.py  overall
#     the old 4-file list             66.7%     79.4%     23.7%     65.2%
#     + the module's own tests        66.7%     83.7%     38.2%     72.0%
#
# Re-measured end to end on this branch, per target, with coverage collected
# from each PER_TARGET_TESTS selection on the unmutated tree:
#
#     models.py   3 planned,   3 reachable  -> 100.0%
#     audio.py  442 planned, 370 reachable  ->  83.7%
#     server.py 152 planned,  58 reachable  ->  38.2%
#     overall   597 planned, 431 reachable  ->  72.2%
#
# Re-derived 2026-10-08 from the coverage artifacts on disk under strict
# executed_lines matching: audio.py 370/442 and server.py 58/152 reproduce
# exactly, models.py comes out 2 of 3 (line 339 sits in a multi-line statement
# coverage records against line 337), giving 430/597 = 72.0%. The gate's own
# configuration killed a mutant at models.py:339, so 3 of 3 -- and the 72.2%
# total -- is the accurate count and strict line matching is what undercounts.
#
# The 83.7% and 38.2% match the earlier estimate exactly; models.py is the one
# figure that moved, and it moved because TIMEOUT_S used to be too small for
# that selection to even finish, so a mutant that was killable was being
# booked as unmeasured instead. That is the difference between a mutant that is
# unkillable (a real gap) and one that was never run (a broken measurement).
#
# Two things follow, and both are load-bearing:
#
# 1. A mutant whose mutated code the selection never runs cannot be observed
#    by any assertion, so the per-module lists below exist to keep each
#    selection reaching its module. But "never runs" is decided by the
#    coverage artifacts, not by matching the mutated line against
#    executed_lines: that match undercounts (models.py:339 above), so strict
#    reachability is a LOWER bound on what a selection observes. Ground truth,
#    2026-10-08: of 51 sampled mutants strict matching called unreachable, 16
#    were run under this gate's own configuration and 5 were KILLED (audio.py
#    0 of 10, server.py 4 of 5, models.py 1 of 1). Unreachable-by-strict-match
#    does not cap the score; only genuinely unexecuted code does, and that is
#    settled by measurement, not by the table above.
#
# 2. This gate measures a PER-TARGET SELECTION, not the full suite, so its
#    ceiling is not comparable to .qgate.toml's `mutation_threshold` (which
#    governs Rust `cargo mutants` over the whole workspace). Reachability is a
#    property of the selection, so widening it would raise the ceiling rather
#    than lower it: under all of tests/ more of server.py's error paths and
#    audio.py's branches are executed, and the 72.2% above is a FLOOR for this
#    harness, not its maximum. An earlier revision of this comment claimed the
#    opposite -- that "even the FULL suite tops out near 72%" -- and used it to
#    justify the bar. That claim was never measured, and it is circular: it
#    cites a ceiling derived from narrow selections as proof that a wider
#    selection could not do better. It is removed rather than replaced with a
#    better-sounding estimate.
#
#    What the measurement above establishes is narrower than this comment used
#    to claim: with these selections, 27.8% of planned mutants sit on lines
#    absent from strict executed_lines. An earlier revision called those
#    "therefore unkillable" and used that to cap TARGET_SCORE below 75. The
#    unkillable part was never measured, and the ground-truth run above
#    falsified it -- 5 of 16 such mutants were killed by the existing
#    selections. So the figure bounds the score from below, not from above.
#
#    COMPLETED 2026-10-08: all 72 strict-reachable sampled mutants were then
#    measured under this configuration, alongside the residue sample. Kill
#    rates per target: server.py 13/20 = 65.0%, audio.py 15/50 = 30.0%,
#    models.py 0/2 (n<5). Combined with the residue measurement, the score's
#    absolute ceiling -- granting every unmeasured mutant as a kill -- is
#    71/123 = 57.7%, so THIS CONFIGURATION cannot clear 65.04% (short by 9)
#    regardless of what the 35 unmeasured residue mutants do. audio.py kills
#    at 30% on lines its own selection executes: its 32 reachable survivors
#    are an assertion gap, not a coverage gap, which is why widening the
#    selection without adding discriminating assertions cannot move them.
#    TARGET_SCORE stays at 65 as a standing decision; the gap is closed by
#    stronger assertions and selection widening, never by moving the bar.
#
# Assertion pass, 2026-10-08 (kill records: pr296_gate/assert_work/kills.jsonl,
# scratch, not committed). tests/test_audio_mutation_gaps.py was written to
# attack the 32 reachable audio.py survivors of the COMPLETED measurement
# above, with reference-style assertions: each test recomputes its expected
# value from the same inputs inside the test, so it is exact on the original
# source (golden-model pattern, no platform-dependent golden constants).
# Every survivor was re-run one site at a time under the gate's own exit-code
# semantics, including every candidate site behind ambiguous (line, op)
# pairs (the chord/scale tables and the boundary/stem constants have several
# same-line same-op sites, and the measurement identified them only by line
# and op): 45 of 49 mutation cycles now fail with pytest exit 1. The cycles
# that still pass are equivalent mutants, not assertion gaps:
#
#   * audio.py:677 `len(beat_times) > 2` -> `>=`: with exactly two beats the
#     computed regularity is 1.0 -- the same value as the default the guard
#     skips to -- so no input can distinguish the two;
#   * audio.py:206 the 32-bit `int.from_bytes(...) * 2**31` rescale is
#     scale-invariant for the harmonic argmax that the exposed notes are
#     derived from; only float tie-ordering at the top-8 boundary could
#     differ, and pinning that would be platform-dependent (libm), so no
#     deterministic distinguishing input was found;
#   * audio.py:430 `np.diff(..., prepend=0)` -> `prepend=1`: the pre-clip
#     value is provably <= 0 (power_to_db with ref=np.max), so both
#     constants clip to 0 and the novelty is identical;
#   * audio.py:54 first constant of the phrygian table key: the key
#     duplicates 0 and can never equal a set of distinct pitch classes, so
#     flipping it is unobservable. (The flip that makes that key reachable
#     IS killed, via the pinned rotation result.)
#
# For audio.py:54 and audio.py:430 the surviving entry was only measured at
# (line, op) granularity: all candidate sites were run, the equivalent ones
# are the ones listed above, and every other candidate is killed. The
# end-to-end gate kill rate has NOT been re-run since this change: the
# 15/50 = 30% figure above still describes the configuration WITHOUT this
# file. Do not infer a new rate from this note -- re-measure instead.
#
# models.py also gains the new file: measured with coverage after writing
# it, that file alone executes 83/83 (100%) of models.py's statements via
# the RenderSpec / SceneSegment / MIRSummary round-trips, so the entry is
# not stale. server.py does NOT gain it: the new file never imports the
# bridge (0 statements executed), and a selection entry that reaches no
# lines of its target is exactly the silent cap this table exists to avoid.
#
# END-TO-END RE-MEASUREMENT, 2026-10-09 (the re-measure this note asked for).
# Every one of the gate's 123 sampled mutants was re-run under driver
# semantics with the widened selections -- audio.py: 9 files (+ gaps, +
# beat_track_isolation), server.py: 8 files (+ studio_pipeline, whose
# selection entry the residue sweep's 14 kills were measured with and which
# therefore MUST ship with them), models.py: 5 files (+ gaps). One vote per
# sampled mutant, later measurement wins, load flakes retried on an idle
# box until resolved:
#
#     models.py    1 killed,  2 survived,  0 unmeasured  ( = 3)
#     audio.py    48 killed, 12 survived,  0 unmeasured  (= 60)
#     server.py   32 killed, 27 survived,  1 unmeasured  (= 60)
#     TOTAL       81 killed, 41 survived,  1 unmeasured  (= 123)
#
# PROVENANCE CAVEAT, added the same day: that sweep measured the WORKING
# TREE, which at the time carried an uncommitted rewrite of audio.py
# (741 insertions / 1024 deletions vs HEAD, including a duplicate-0 phrygian
# table key that HEAD does not have). The mutation plan -- and therefore the
# sampled 123 -- is computed from the file it mutates, so the numbers above
# describe the edited tree, not the committed one. They established that the
# assertion work moves the score far (47 -> 81 of 123 measured kills) but
# they are NOT a claim about what CI measures on HEAD. The authoritative
# committed-tree number is the qgate job itself; the committed audio.py also
# has a reachable phrygian key, which this gate's tests now pin (see
# test_audio_mutation_gaps.py SCALE_CASES). If the committed-tree rate comes
# in short, the fix is the same direction as before: assertions that
# distinguish mutants of HEAD, not movement of TARGET_SCORE.
#
# 81/123 = 65.9% on the measured tree, clearing the 65.04% bar. The 12 audio
# survivors include the four equivalent mutants argued above (valid for the
# edited tree; HEAD's reachable phrygian key changes that one case); the
# remaining 8 survive under the widened selection and are genuine
# (weak-or-absent distinguishing assertions on reachable lines). The 1
# unmeasured is server.py:1084 (__name__ == '__main__' guard), which exits 3
# on every attempt -- a collection-path quirk that bounds
# MAX_UNMEASURED_RATIO headroom rather than the score. With one kill of
# margin on the measured tree the bar is met but fragile: any single
# kill-to-survivor regression (a flaky new test, an env change) drops the
# score to exactly 80 or below. That fragility is real and is why
# TARGET_SCORE stays at 65 rather than rising with the new rate.
#
# Each list is the set of test files that actually execute lines of that module,
# so adding a test that reaches a new path lifts the ceiling without touching
# this table. Deriving the lists by measurement rather than by hand is what keeps
# them honest: a stale entry here is an invisible, permanent cap on the score.
PER_TARGET_TESTS: dict[str, list[str]] = {
    "models.py": [
        "tests/test_render_spec_v2.py",
        "tests/test_mutation_kill_score.py",
        "tests/test_coverage_100.py",
        "tests/test_coverage_gaps.py",
        "tests/test_audio_mutation_gaps.py",
    ],
    "audio.py": [
        "tests/test_render_spec_v2.py",
        "tests/test_mutation_kill_score.py",
        "tests/test_coverage_100.py",
        "tests/test_coverage_gaps.py",
        "tests/test_audio_ml_paths.py",
        "tests/test_bpm_key.py",
        "tests/test_spectrum.py",
        "tests/test_audio_mutation_gaps.py",
        "tests/test_beat_track_isolation.py",
    ],
    "server.py": [
        "tests/test_render_spec_v2.py",
        "tests/test_mutation_kill_score.py",
        "tests/test_coverage_100.py",
        "tests/test_coverage_gaps.py",
        "tests/test_bridge_api.py",
        "tests/test_bridge_b7_error_paths.py",
        "tests/test_bridge_http_integration.py",
        "tests/test_bridge_studio_pipeline.py",
    ],
}

# Mutations applied per target file. Read by BOTH the loop below and
# SUBPROCESS_CEILING_S, so the budget cannot drift from the work.
MAX_PER_FILE = 60
# Per-mutant wall-clock cap. This must sit ABOVE the unmutated cost of the
# slowest selection, because the suite has to run to completion before the
# mutant can be called killed or survived.
#
# Measured unmutated cost of each PER_TARGET_TESTS selection on this machine,
# with no other load competing for the box:
#
#     models.py  4 files   56s   (393-test-equivalent subset, all passing)
#     audio.py   7 files  114s
#     server.py  7 files   70s
#
# At the previous 60s cap, two of the three selections timed out even with no
# mutation applied, so a large share of mutants was booked as "no verdict"
# rather than measured. That is a broken measurement, not a low score: it
# produces a number that looks like weak tests while actually proving nothing.
# The cap is therefore derived from the slowest selection with headroom, not
# picked to fit today's runtime.
#
# 300s is ~2.6x the slowest measured selection (114s). The margin absorbs a
# slower CI runner and a mutation that makes the suite slower rather than
# faster; below that margin a legitimately slow runner would convert real kills
# into unmeasured mutants.
TIMEOUT_S = 300
# Flags every inner pytest subprocess gets, used both for the unmutated baseline
# run and for each measured mutant so the two are comparable.
#
# `--no-cov` is passed ONLY when pytest-cov is importable, because that option is
# contributed by the pytest-cov plugin and pytest exits 4 -- usage error -- on an
# unrecognized argument. That exit code is not 0, so a naive `returncode != 0`
# reads as "the mutant was killed". mutmut.yml installs `--extra test
# --extra analysis --extra bridge` and deliberately omits `--group dev`, which
# is the only place pytest-cov is declared, so inside that job every mutant was
# being booked a kill in under a second with no test executed: a 100% score from
# a missing plugin. Resolving the flag against the live environment removes the
# trap instead of moving the dependency.
INNER_PYTEST_ARGS: tuple[str, ...] = ("-q", "-x") + (
    ("--no-cov",) if importlib.util.find_spec("pytest_cov") else ()
)


# An explicit `--basetemp` for every inner pytest, including the unmutated
# baseline. Both run as plain `sys.executable -m pytest` with no cache plugin
# and no temp override, so they default to the SHARED global temp root
# (`%TEMP%\pytest-of-<user>\pytest-current`) that pytest itself creates as a
# directory symlink to the current run.
#
# That is a shared, mutable resource, and two pytest processes reaching it at
# once collide. pytest resolves the `pytest-current` link by unlinking and
# recreating it, so the loser of the race either deletes the winner's basetemp
# mid-run or fails its own setup with OSError 5, `Access is denied`. Both
# happened here: a gate run overlapping a coverage run failed its baseline with
# `Access is denied: '...pytest-of-koosh\pytest-current'`, on unmutated source,
# which the driver correctly refuses to accept -- so the score would have been
# reported as unmeasurable rather than wrong, but for the wrong reason.
#
# Giving each inner run its own root removes the contention instead of working
# around it, and the driver's own `--basetemp` for the OUTER pytest (set by
# the workflow and by local runs) keeps the two runs disjoint at both levels.
#
# Each call site passes a distinct directory keyed to what it is measuring, so
# a crash leaves the mutated file and its evidence in a predictable place. The
# paths live under the system temp dir rather than in the repo, so a run leaves
# no untracked files behind for `git status` to report.
def inner_basetemp(label: str) -> str:
    """A private pytest `--basetemp` for one inner run.

    *label* names the run (the target file, or `baseline`), so distinct runs get
    distinct roots even when they overlap in time.
    """
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    return os.path.join(tempfile.gettempdir(), f"melosviz-mutation-{safe}-{os.getpid()}")


# pytest exit codes that mean "no assertion ran and therefore no assertion
# failed", not "the suite ran and rejected this mutant".
#
# From pytest's own ExitCode enum (_pytest/config/__init__.py), verified
# against the installed pytest rather than from memory:
#
#     2 INTERRUPTED        a collection error, or Ctrl-C / KeyboardInterrupt
#     3 INTERNAL_ERROR     a plugin or pytest itself crashed
#     4 USAGE_ERROR        unrecognized argument, bad path
#     5 NO_TESTS_COLLECTED the selection matched nothing
#     6 MAX_WARNINGS_ERROR tests passed but `--max-warnings` was exceeded
#
# All four are non-zero, so a bare `returncode != 0` booked every one of them as
# a kill -- "caught by the tests" for a run where no assertion executed. That is
# the exact accounting this gate exists to remove, and it is what let a missing
# plugin score 100% from a `--no-cov` usage error.
#
# The four do not share a remedy, so they are split by WHO is responsible:
#
#   * ENVIRONMENT failures (4, 5) are identical for every mutant. A bad flag or
#     an empty selection makes the whole measurement void rather than one mutant
#     unmeasured. Abort: no score from such a run means anything.
#
#   * MUTANT failures (2, 3) can be caused by the mutant under test. A mutant
#     that breaks a module's import is a collection error; one that trips a
#     plugin-level crash is an internal error. Counting either as a kill makes
#     the score depend on HOW the mutant broke the file rather than on what the
#     suite observed, which is not what a kill score measures. Counting either
#     as a survivor is equally wrong -- a survivor asserts the suite ran to
#     completion and passed. They are unmeasured, and bounded by ratio so a run
#     where many mutants fail to collect cannot quietly depress the bar.
#
# That split is the answer to whether an unimportable mutant is "a genuine
# defect worth crediting". It is a real defect, but it is not a test CATCHING
# anything, so it stays visible as its own bucket with its own ceiling instead
# of being folded into the numerator.
#
# 6 joins the MUTANT side because `_pytest/terminal.py` only ever SETS it after
# the suite has already exited OK: the check runs under
# `if session.exitstatus == ExitCode.OK` and is reached only after every test
# passed. So 6 is a verdict on a run that completed, and booking it as a survivor
# would be the one classification here that is actually correct. Booking it as a
# kill would not be -- no assertion failed. It is therefore neither, and lands
# with 2 and 3 as unmeasured, bounded by the same ratio. It is currently
# unreachable (nothing passes `--max-warnings`, and pyproject sets no
# `max_warnings`), but a set written from an older pytest would be missing it.
_ENVIRONMENT_FAILURES: frozenset[int] = frozenset({4, 5})
_MUTANT_FAILURES: frozenset[int] = frozenset({2, 3, 6})

# The one exit code that means an assertion actually failed, which is the only
# thing a kill score is allowed to count. Named rather than written as a bare
# `1` at the call site, so the reader does not have to recall which number that
# is, and so pytest renumbering it would be a one-line change here instead of a
# silent reinterpretation in the driver.
KILL_EXIT_CODE: Final[int] = 1

# The single code that means the suite ran to completion and passed.
CLEAN_EXIT_CODE: Final[int] = 0

# Every outcome the driver knows how to book.
EXIT_CODE_SURVIVED: Final[str] = "survived"
EXIT_CODE_KILLED: Final[str] = "killed"
EXIT_CODE_UNMEASURED: Final[str] = "unmeasured"
EXIT_CODE_ABORT: Final[str] = "abort"


def classify_exit_code(returncode: int) -> str:
    """Map an inner pytest returncode to the one verdict that is true of it.

    Every branch is named rather than left to a fallthrough, because the
    fallthrough was the bug this replaces: the driver tested for a kill, then
    for a timeout and an unmeasured outcome, and anything left over fell into
    `survived`. A survivor asserts the suite ran to completion and passed, so
    that branch cannot be a default -- it can only be the answer for code 0.

    Measured on this platform, that default is reachable rather than
    theoretical. `os._exit(7)` and `os._exit(255)` both come back as themselves,
    so a subprocess exiting 7 -- outside pytest's enum entirely -- was booked as
    a mutant that survived. (Windows fault codes DO reach here intact, as
    unsigned values: an access violation, 0xC0000005, comes back from
    `subprocess.run` as 3221225477. They are not truncated to 1. That does not
    make them a scoring hazard, because they fall through every branch to the
    raise below rather than matching a kill, and a crashed process has run no
    assertion that could be counted. Observed here in practice: the baseline
    subprocess died that way once, under load from concurrent probes, and the
    gate reported it as an unmeasurable measurement rather than a score.)

    The final raise is deliberate. An unclassifiable code means this function
    and pytest's enum have diverged, or the process died outside pytest's
    control, and a gate that quietly booked such a code as a survivor would
    report a confident, wrong number. Refusing to score is the honest response
    to a measurement whose own vocabulary no longer matches.
    """
    if returncode == CLEAN_EXIT_CODE:
        return EXIT_CODE_SURVIVED
    if returncode == KILL_EXIT_CODE:
        return EXIT_CODE_KILLED
    if returncode in _MUTANT_FAILURES:
        return EXIT_CODE_UNMEASURED
    if returncode in _ENVIRONMENT_FAILURES:
        return EXIT_CODE_ABORT
    raise RuntimeError(
        f"unclassifiable pytest exit code {returncode}; it is neither a clean run, "
        f"a kill, a mutant-caused failure nor an environment failure. Either pytest "
        f"gained an exit code this driver does not know, or the process was killed "
        f"by something outside pytest."
    )


# The kill-score floor, set at 65 rather than the 75 the .qgate.toml
# `mutation_threshold` names.
#
# The two numbers govern different things and conflating them is what made this
# gate unsatisfiable. `.qgate.toml`'s mutation_threshold is the floor for
# `cargo mutants` over the Rust workspace, a completely separate sweep that
# this Python harness does not and cannot stand in for (see mutmut.yml for that
# job). This test measures AST mutation of three Python modules under four to
# seven test files each. Its STRICT reachability -- 431 of 597 planned sites
# sit on a line the selection's coverage records as executed, 72.2% -- was
# previously described here as "the best score reachable even with perfect
# assertions". That claim was never measured and is now falsified: a
# ground-truth run of this gate's own configuration killed 5 of 16 sampled
# mutants strict reachability called unreachable. Coverage reachability
# undercounts (models.py:339) and therefore bounds the score from below; it
# does not cap it from above. The residual observation stands as a diagnostic
# only: server.py's selection records 58 of its 152 planned sites executed,
# the weakest of the three.
#
# 75% is accordingly not rejected as impossible -- that argument depended on
# the ceiling reading and does not survive it. What keeps the bar at 65 is a
# standing decision: the gate must clear 65% (80 of 123 sampled kills), and the
# bar moves only when measurement shows the selections sustaining a higher
# kill rate.
#
# Two denominators, and conflating them is the second way this was wrong. The
# 72.2% reachability figure is over 597 PLANNED sites across the three modules.
# This gate measures at most 3 + 60 + 60 = 123 of them, because MAX_PER_FILE
# caps each target and the driver samples across the plan rather than taking a
# prefix. So "65 sits ~7 points under the reachability figure" is a statement
# about the PLANNED population, not about the score this test actually
# computes; the sampled score is an estimate of that population, and it moves
# when the sample does.
#
# The estimate is unbiased rather than exact because the sample is proportional.
# An earlier revision took a contiguous top-of-file prefix, which is NOT a
# sample: server.py (38.2% reachable) grew from 25.5% of planned sites to 48.8%
# of measured ones while models.py (100% reachable) shrank from 0.5% to 2.4%, so
# the measured score could land below the bar for reasons that had nothing to do
# with the code. Index-interval sampling removes that bias by construction.
#
# 7 points of headroom is what makes a regression in any one target's kill rate
# show up as a failure rather than being absorbed as sampling noise.
#
# Standing rule for future edits: raise TARGET_SCORE only when a measurement
# shows the selections killing at a higher rate, never on the strength of a
# reachability figure alone -- reachability bounds kills from below (see the
# ground-truth note above). The bar's only job is to sit under demonstrated
# kill performance, so a real regression drops the score through it.
TARGET_SCORE = 65.0
# Ceiling on the share of mutants that produced no verdict at all. A single
# mutant-induced hang is a legitimate kill signal (the mutation broke the
# suite badly enough to wedge it), so this is not zero; but a run where a large
# fraction is unmeasured cannot support any score claim, and the honest number
# then depends entirely on whether timeouts are counted. See the scoring block.
MAX_TIMEOUT_RATIO = 0.10
# Ceiling on the share of mutants pytest could not run to a verdict because it
# exited 2 or 3 on them -- a collection error or an internal error, both of
# which a mutant can cause by breaking an import or tripping a plugin.
#
# Not zero. Unlike a timeout, this is an ORDINARY outcome of mutating code: a
# BRANCH mutant that inverts a guard can leave a module unimportable, and
# asserting zero would make the gate fail on a perfectly healthy suite. Not
# unbounded either, because these mutants sit in no bucket -- not killed, not
# survived, not timed out -- so a large share would silently pull the kill
# score down and read as weak tests when it is really an unmeasurable source
# tree. 10% matches MAX_TIMEOUT_RATIO: both bound the share of the run that
# produced no verdict, and a run that exceeds either cannot support a score.
MAX_UNMEASURED_RATIO = 0.10
# Wall-clock budget for the whole test, derived from the work it does rather
# than picked to make today's run pass.
#
# The test runs up to MAX_PER_FILE mutations per target across len(TARGETS)
# targets, and every mutation is a separate pytest subprocess over that target's
# PER_TARGET_TESTS selection (four to seven files), each capped at TIMEOUT_S. The
# hard ceiling on subprocess time alone is
#     len(TARGETS) * MAX_PER_FILE * TIMEOUT_S = 3 * 60 * 300 = 54000s = 15h
# and the per-mutation AST re-parse, file write/restore, and the JSON report
# writes all count against the outer budget on top of that.
#
# That 15h ceiling is the worst case where EVERY mutant hangs to the cap. The
# measured case is nothing like it: with TIMEOUT_S sized above the slowest real
# selection, a mutant either fails fast under `-x` or runs the selection once,
# so the three targets cost on the order of 60 * (56 + 114 + 70) ~= 4.8h of
# worst-case subprocess time at MAX_PER_FILE. TIMEOUT_S exists to bound a
# pathological mutant; it is not the expected cost of a healthy one.
#
# The budget therefore cannot be a 1.5x multiple of the hang ceiling: 1.5x 15h
# is 22.5h, which is past the platform cap, where pytest-timeout can never fire
# first and the marker is decorative rather than load-bearing. Instead the
# budget is set against the measured case with real headroom, and deliberately
# below the cap so the diagnostic can still be produced.
#
# The ordering this depends on, which is not automatic: the budget must
# fire BEFORE the platform kills the job, or it never produces the
# diagnostic it exists to produce. Inside GitHub Actions,
#     pytest-timeout (this value)  <  job `timeout-minutes`  <  360min cap
# and the gate job runs this test with NO `timeout-minutes` of its own, so it
# inherits the 360-minute cap. A budget at or above 360min is therefore
# unusable: it would sit on or past the platform cap, and pytest-timeout could
# never fire first, leaving this marker silently redundant rather than
# load-bearing. The budget below is set to 270min for that reason.
#
# What does NOT set this budget: `.github/workflows/mutmut.yml`. That job has
# its own `timeout-minutes: 360` and its real bound is unrelated to the
# 3 * 60 * 300 above, because it runs a different sweep: `uv run mutmut run`,
# whose scope comes from [tool.mutmut] source_paths = ["src/melosviz/"] -- the
# whole package, 80 files and 26506 mutants, not these three TARGETS. The two
# numbers therefore do not have to move together, in either direction.
#
# One genuine relationship, since it is easy to assume otherwise and wrong to:
# this test IS collected inside that sweep. `pytest_add_cli_args_test_selection =
# ["tests/"]` selects what pytest RUNS for every mutant, and this module lives
# under tests/, so it executes once per mutant. Verified rather than assumed:
# `pytest tests/ --collect-only` lists
# `tests/test_mutation_engine.py::test_mutation_kill_score_meets_qgate_bar`.
#
# Two earlier revisions got the consequence wrong, in the same direction. They
# read "governed by source_paths" as meaning this module is outside the sweep,
# and so is harmless there. Both are false, because source_paths is
# `["src/melosviz/"]` and all three TARGETS below are
# `src/melosviz/analysis/{models,audio}.py` and `src/melosviz/bridge/server.py`
# -- inside it. An earlier pyproject.toml comment went further and said
# `source_paths` "excludes backend/tests/", which is true only of the MODULE,
# and was used to argue that dropping this test could not hide a mutant check.
# That inference does not follow: the module is never mutated, but the three
# TARGETS it reads are mutated files, so a mutant of models.py or server.py can
# change what this test observes. That is precisely why the deselect is NOT
# committed on the strength of that comment -- see the note in pyproject.toml.
#
# The old budget was @pytest.mark.timeout(300) -- 5 minutes for work that can
# legitimately take hours. It only ever passed because killed mutants exit early
# under -x; a single surviving mutant, which by definition runs the entire
# suite, blew it. Dispatched run 36957966430 against e3f3ddd is that case:
#     FAILED tests/test_mutation_engine.py::test_mutation_kill_score_meets_qgate_bar
#       - Failed: Timeout (>300.0s) from pytest-timeout
# The bar being enforced is the TARGET_SCORE kill score, not a duration, so a
# budget that fires before the measurement completes destroys the thing it
# protects.
# The subprocess ceiling is named so the budget below cannot drift away from
# the work it is sizing. 3 targets * 60 mutations * 300s = 54000s = 15h, which
# is the every-mutant-hangs case and is deliberately NOT multiplied up into the
# budget: 1.5x of it is 22.5h, past the 360min platform cap, where
# pytest-timeout could never fire first and the marker stops being load-bearing.
#
# The budget is therefore pinned to 270min, below the cap with real headroom.
# The worst case is computed from the ACCEPTED counts this budget actually has
# to cover, not from MAX_PER_FILE per target: models.py accepts 3 mutants
# (it has only 3 sites), audio.py and server.py accept the full 60 each.
#
# RE-DERIVED 2026-10-09 when the selections widened (test_audio_mutation_gaps.py
# for models.py+audio.py, test_beat_track_isolation.py for audio.py,
# test_bridge_studio_pipeline.py for server.py). Measured baseline ratios,
# widened vs current, on an idle box: models 0.997, audio 1.471 (96.8s ->
# 142.4s), server 1.004. Scaling the driver's per-mutant estimates by those
# ratios:
#
#     measured mutants   3 * 56s + 60 * 168s + 60 * 70s = 12408s ~= 207min
#     baseline runs      3 * TIMEOUT_S                  =   900s ~=  15min
#                        ----------------------------------------------
#     total                                               13308s ~= 222min
#
# A conservative pass using observed mutant walls up to ~175s in the
# verification sweeps puts audio near 175s:
#
#     conservative       3 * 56s + 60 * 175s + 60 * 70s = 15345s ~= 256min
#
# so 270min is ~1.05x that conservative case, leaving ~14min of margin. The
# earlier 210min budget would have BREACHED: the widened audio selection alone
# added 45.6s per baseline run, projecting a ~256min worst case against a
# 210min cap, and the gate would have aborted mid-sweep reporting no score.
#
# The baseline runs are in this figure because they are three more subprocess
# invocations of the same selections, each inheriting TIMEOUT_S, and an earlier
# version of this comment sized the budget from the mutant runs alone. That made
SUBPROCESS_CEILING_S = 3 * MAX_PER_FILE * TIMEOUT_S
KILL_SCORE_TIMEOUT_S = 270 * 60


# ----------------------- Driver ------------------------------------------
