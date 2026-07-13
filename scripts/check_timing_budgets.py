#!/usr/bin/env python3
"""Feedback-loop timing budget gate (WBS-P1.11 / C03 L30.10).

Runs a small set of inner-loop commands, records wall times, and fails if any
exceed the generous CI-safe budgets in docs/TIMING_BUDGETS.md.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Budget:
    name: str
    budget_s: float
    argv: Sequence[str]
    cwd: Optional[Path] = None
    env_key: str = ""


def _budget(name: str, default: float, env_key: str) -> float:
    raw = os.environ.get(env_key, "").strip()
    if raw:
        return float(raw)
    return default


def budgets() -> List[Budget]:
    backend = REPO / "backend"
    return [
        Budget(
            name="diagnose",
            budget_s=_budget("diagnose", 60.0, "MELOSVIZ_BUDGET_DIAGNOSE"),
            argv=[sys.executable, str(REPO / "scripts" / "diagnose.py")],
            cwd=REPO,
            env_key="MELOSVIZ_BUDGET_DIAGNOSE",
        ),
        Budget(
            name="backend_pytest_smoke",
            budget_s=_budget("backend_pytest_smoke", 180.0, "MELOSVIZ_BUDGET_PYTEST_SMOKE"),
            # Narrow, import-light subset — not the full CI suite.
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "tests/test_optional_dep_imports.py",
                "tests/test_top_level_spec_md_spec.py",
                "-q",
                "--tb=line",
            ],
            cwd=backend,
            env_key="MELOSVIZ_BUDGET_PYTEST_SMOKE",
        ),
        Budget(
            name="cargo_check",
            budget_s=_budget("cargo_check", 600.0, "MELOSVIZ_BUDGET_CARGO_CHECK"),
            argv=["cargo", "check", "--locked", "--workspace"],
            cwd=REPO,
            env_key="MELOSVIZ_BUDGET_CARGO_CHECK",
        ),
        Budget(
            name="make_golden",
            budget_s=_budget("make_golden", 180.0, "MELOSVIZ_BUDGET_GOLDEN"),
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "tests/test_golden_corpus.py",
                "-q",
                "--tb=line",
            ],
            cwd=backend,
            env_key="MELOSVIZ_BUDGET_GOLDEN",
        ),
    ]


def _run(b: Budget) -> tuple[float, int]:
    cwd = b.cwd or REPO
    t0 = time.perf_counter()
    proc = subprocess.run(
        list(b.argv),
        cwd=str(cwd),
        env=os.environ.copy(),
    )
    elapsed = time.perf_counter() - t0
    return elapsed, int(proc.returncode)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Skip a named budget (repeatable). Names: diagnose, backend_pytest_smoke, cargo_check, make_golden",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print budgets and exit",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    items = budgets()
    if args.list:
        for b in items:
            print(f"{b.name:24s} {b.budget_s:8.1f}s  {' '.join(b.argv)}")
        return 0

    skip = set(args.skip or [])
    failed = False
    print("MelosViz timing budgets (docs/TIMING_BUDGETS.md)")
    print(f"{'loop':24s} {'budget':>8s} {'wall':>8s} {'status':>8s}")
    print("-" * 56)

    for b in items:
        if b.name in skip:
            print(f"{b.name:24s} {b.budget_s:8.1f}s {'—':>8s} {'SKIP':>8s}")
            continue
        elapsed, rc = _run(b)
        over = elapsed > b.budget_s
        cmd_fail = rc != 0
        if cmd_fail:
            status = "CMDFAIL"
            failed = True
        elif over:
            status = "OVER"
            failed = True
        else:
            status = "OK"
        print(f"{b.name:24s} {b.budget_s:8.1f}s {elapsed:7.1f}s {status:>8s}")
        if cmd_fail:
            print(f"  command failed (exit {rc}): {' '.join(b.argv)}", file=sys.stderr)

    if failed:
        print("timing budgets: FAILED", file=sys.stderr)
        return 1
    print("timing budgets: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
