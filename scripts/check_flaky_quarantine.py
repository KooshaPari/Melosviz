#!/usr/bin/env python3
"""CI gate: @pytest.mark.flaky tests must appear in the quarantine registry (C08 L78).

Scans backend/tests for the flaky marker (AST) and cross-checks docs/EVAL.md
(or docs/eval/FLAKY_QUARANTINE.md) quarantine table rows.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO / "backend" / "tests"
EVAL_DOC = REPO / "docs" / "EVAL.md"
FLAKY_DOC = REPO / "docs" / "eval" / "FLAKY_QUARANTINE.md"

TABLE_HEADER = re.compile(
    r"^\|\s*Node\s*ID\s*\|.*\|\s*$", re.IGNORECASE | re.MULTILINE
)
TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|", re.MULTILINE)


@dataclass(frozen=True)
class FlakyTest:
    rel_path: str
    qualname: str

    @property
    def nodeid(self) -> str:
        return f"{self.rel_path}::{self.qualname}"


def _decorator_is_flaky(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "mark"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "pytest"
            and node.attr == "flaky"
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return _decorator_is_flaky(node.func)
    if isinstance(node, ast.Name) and node.id == "flaky":
        return True
    return False


def _has_flaky_mark(decorator_list: list[ast.expr]) -> bool:
    return any(_decorator_is_flaky(d) for d in decorator_list)


class _FlakyCollector(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.found: list[FlakyTest] = []
        self._class_flaky = False
        self._class_name: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        prev_flaky = self._class_flaky
        prev_name = self._class_name
        self._class_flaky = _has_flaky_mark(node.decorator_list)
        self._class_name = node.name
        self.generic_visit(node)
        self._class_flaky = prev_flaky
        self._class_name = prev_name

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not node.name.startswith("test_"):
            return
        flaky = _has_flaky_mark(node.decorator_list) or self._class_flaky
        if flaky:
            qual = (
                f"{self._class_name}::{node.name}"
                if self._class_name
                else node.name
            )
            self.found.append(FlakyTest(rel_path=self.rel_path, qualname=qual))


def _collect_flaky_tests(tests_dir: Path) -> list[FlakyTest]:
    found: list[FlakyTest] = []
    for path in sorted(tests_dir.rglob("test_*.py")):
        rel = path.relative_to(REPO / "backend").as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise SystemExit(f"FAIL: syntax error in {rel}: {exc}") from exc
        collector = _FlakyCollector(rel)
        collector.visit(tree)
        found.extend(collector.found)
    return found


def _registry_paths() -> list[Path]:
    paths: list[Path] = []
    if FLAKY_DOC.is_file():
        paths.append(FLAKY_DOC)
    if EVAL_DOC.is_file():
        paths.append(EVAL_DOC)
    return paths


def _parse_registry_rows(text: str) -> set[str]:
    """Return normalized node IDs / keys documented in markdown tables."""
    if not TABLE_HEADER.search(text):
        return set()

    keys: set[str] = set()
    in_table = False
    for line in text.splitlines():
        if TABLE_HEADER.match(line):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.strip().startswith("|"):
            in_table = False
            continue
        if re.match(r"^\|\s*[-:]+\s*\|", line):
            continue
        m = TABLE_ROW.match(line)
        if not m:
            continue
        cell = m.group(1).strip()
        if not cell or cell.startswith("*") or cell.lower() in {"none", "—", "-"}:
            continue
        keys.add(cell)
        if "::" in cell:
            keys.add(cell.split("::")[-1])
        else:
            keys.add(cell)
    return keys


def _load_documented_keys() -> set[str]:
    keys: set[str] = set()
    for path in _registry_paths():
        keys |= _parse_registry_rows(path.read_text(encoding="utf-8"))
    return keys


def _matches_registry(test: FlakyTest, documented: set[str]) -> bool:
    candidates = {
        test.nodeid,
        test.qualname,
        test.rel_path,
        f"{test.rel_path}::{test.qualname}",
    }
    return bool(candidates & documented) or any(
        doc in test.nodeid or test.nodeid in doc for doc in documented
    )


def _write_summary(path: Path, flaky: list[FlakyTest], documented: set[str]) -> None:
    lines = [
        "# Flaky quarantine summary",
        "",
        f"**Tests marked `@pytest.mark.flaky`:** {len(flaky)}",
        "",
    ]
    if flaky:
        lines.append("| Node ID | Documented |")
        lines.append("|---------|------------|")
        for test in flaky:
            ok = "yes" if _matches_registry(test, documented) else "no"
            lines.append(f"| `{test.nodeid}` | {ok} |")
    else:
        lines.append("_No quarantined tests — registry is empty._")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="Write markdown summary artifact to this path",
    )
    parser.add_argument(
        "--check-orphan-docs",
        action="store_true",
        help="Fail when registry rows lack a matching @pytest.mark.flaky test",
    )
    args = parser.parse_args()

    if not TESTS_DIR.is_dir():
        print(f"FAIL: missing {TESTS_DIR}", file=sys.stderr)
        return 1
    if not _registry_paths():
        print("FAIL: no quarantine registry doc (EVAL.md or FLAKY_QUARANTINE.md)", file=sys.stderr)
        return 1

    flaky = _collect_flaky_tests(TESTS_DIR)
    documented = _load_documented_keys()

    if args.summary_out:
        _write_summary(args.summary_out, flaky, documented)

    missing_docs = [t for t in flaky if not _matches_registry(t, documented)]
    if missing_docs:
        print("FAIL: flaky tests missing quarantine registry row:", file=sys.stderr)
        for test in missing_docs:
            print(f"  - {test.nodeid}", file=sys.stderr)
        print(
            "Add a row to docs/EVAL.md (Flaky quarantine registry) or "
            "docs/eval/FLAKY_QUARANTINE.md",
            file=sys.stderr,
        )
        return 1

    if args.check_orphan_docs:
        orphan_docs = [
            key
            for key in sorted(documented)
            if not any(_matches_registry(t, {key}) for t in flaky)
        ]
        if orphan_docs:
            print("FAIL: registry rows without @pytest.mark.flaky:", file=sys.stderr)
            for key in orphan_docs:
                print(f"  - {key}", file=sys.stderr)
            return 1

    print(
        f"PASS: {len(flaky)} flaky test(s) synced with quarantine registry "
        f"({len(documented)} doc key(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
