"""AST mutation planner and applier for the Python mutation gate.

Split out of ``test_mutation_engine.py`` so the two halves of this problem can be
tested apart:

  * ``test_mutation_engine.py`` owns the SCORE -- what to assert, against which
    ceiling, within what time budget. Those are judgement calls that change.
  * this module owns the MECHANISM -- how many mutants exist, and how to rewrite
    exactly one of them. Those are mechanical and should be pinned by tests that
    assert them directly rather than inferred from a 10-minute score run.

Nothing here runs tests or measures anything. It reads source, plans mutations,
and returns rewritten source. That separation is the whole point: a planner bug
and a threshold mistake produce different symptoms, and the driver used to be
able to hide both behind one red number.

The invariant this module exists to protect is that the planner and the applier
enumerate sites in the SAME order. Everything else -- per-op occurrence indexes,
rejection of no-ops, the operator tables -- follows from that. See ``_Indexer``
for the traversal-order contract and ``Planned.index`` for why indexes are
per-op rather than global.
"""

from __future__ import annotations

import ast
import uuid
from dataclasses import dataclass
from pathlib import Path

# Mutually-reversing operators. Every key must have an alter, because `_op_for`
# gates on this table to decide what is a target at all: a site whose operator is
# missing would be planned, counted, and then left unaltered, reading as a
# survivor no test could ever have killed.
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
# `Or` is here as well as `And`. A previous revision carried only `And` (plus a
# stray "Eq" entry that is not a BoolOp at all), so every `or` site was a phantom
# mutant: planned, indexed, and never altered.
OPPOSITE_BOOL = {"And": "Or", "Or": "And"}

# Human-readable names for the error messages, so a failure names the mutation
# rather than the three-letter code.
OP_LABEL = {
    "ROR": "relation-override",
    "AOR": "arithmetic-override",
    "LCR": "logical-constant",
    "BOOL": "boolean-constant",
    "NUM": "0/1-constant",
    "BRANCH": "if-branch",
}


@dataclass
class Planned:
    """One mutant: a site, the op to apply there, and which occurrence it is."""

    mid: str
    line: int
    op: str
    snippet: str
    # Which occurrence of `op` in this file's traversal order to alter.
    #
    # This must be the per-op index, NOT the driver's loop position. The two are
    # different coordinate systems: `_apply_one` counts matching sites *of one
    # op*, so passing the global position asks for e.g. the 41st BRANCH site in a
    # file that has 36. `remaining` then never reaches 0, no node is altered, the
    # driver writes an unmutated file, the suite passes, and the entry is booked
    # as a survivor. Those entries are unkillable by construction and silently
    # drag the score down: 28 of 123 planned mutants were phantom no-ops before
    # this field existed.
    #
    # The index is also only meaningful because planner and applier enumerate in
    # the SAME order; see `_Indexer` and `_op_for`.
    index: int = 0

    def describe(self) -> str:
        """One-line identity used in failure messages and JSON reports."""
        return f"{self.op}#{self.index}@{self.line} {self.snippet!r}"


def _op_for(node: ast.AST) -> str | None:
    """The mutation op this node supports, or None if it is not a target.

    Single source of truth for BOTH the planner and the applier, and the reason
    the phantom-mutant class is gone. Two properties matter:

    1. Only operators that `_alter_one` can actually change qualify. A bare
       `isinstance(node, ast.BinOp)` test also accepts `float | None` union
       annotations, `x | y` flags and `%` remainders, none of which have a
       counterpart in SWAPPED. Those were counted as arithmetic sites and
       consumed an index each, so every index after the first one named a
       different site than the planner recorded.

       The `Compare` branch deliberately tests only `ops[0]`, because that is
       the operator `_alter_one` rewrites. Testing any op in the chain (as the
       planner used to) admits `x in y == z`-shaped nodes where ops[0] is not
       swappable, which would again plan a site the applier cannot change.

    2. The predicate must be pure, so planner and applier can never disagree
       about what counts as a site.
    """
    if isinstance(node, ast.Compare):
        if node.ops and type(node.ops[0]).__name__ in SWAPPED:
            return "ROR"
        return None
    if isinstance(node, ast.BinOp):
        return "AOR" if type(node.op).__name__ in SWAPPED else None
    if isinstance(node, ast.BoolOp):
        return "LCR" if type(node.op).__name__ in OPPOSITE_BOOL else None
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "BOOL"
        if isinstance(node.value, int) and node.value in (0, 1):
            return "NUM"
        return None
    if isinstance(node, ast.If):
        return "BRANCH"
    return None


def _snippet(node: ast.AST) -> str:
    """A short human-readable identity for a site, for reports and errors."""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.If):
        return ast.unparse(node.test).split("\n")[0][:80]
    return ast.unparse(node).split("\n")[0][:80]


class _Indexer(ast.NodeVisitor):
    """Collect mutation sites in the order the applier will visit them.

    `generic_visit` runs before the node is recorded, so children are seen before
    their parent. That is exactly the order `Hit.visit` in `_apply_one` uses,
    because `NodeTransformer.visit` there calls `generic_visit` first as well.
    That agreement is the entire point: the planner previously enumerated with
    `ast.walk`, which is breadth-first, so index N named one node when planning
    and a different node when applying. The result was 11 mutants that reported
    "altered" while emitting byte-identical text.
    """

    def __init__(self) -> None:
        self.sites: list[tuple[str, ast.AST]] = []

    def visit(self, node: ast.AST) -> None:  # type: ignore[override]
        self.generic_visit(node)
        op = _op_for(node)
        if op is not None:
            self.sites.append((op, node))


def sites(source_text: str) -> list[tuple[str, ast.AST]]:
    """Every alterable site in *source_text*, in the applier's traversal order."""
    indexer = _Indexer()
    indexer.visit(ast.parse(source_text))
    return indexer.sites


def plan(source_text: str) -> list[Planned]:
    """Plan one mutant per alterable site, numbered per-op in traversal order.

    Takes source TEXT rather than a path so the planner can be unit-tested
    against inline fixtures without touching the filesystem, and so the "plan
    this" and "rewrite this" operations can never disagree about which text they
    are talking about.
    """
    counts: dict[str, int] = {}
    out: list[Planned] = []
    for op, node in sites(source_text):
        idx = counts.get(op, 0)
        counts[op] = idx + 1
        out.append(
            Planned(
                mid=str(uuid.uuid4()),
                line=getattr(node, "lineno", 0),
                op=op,
                snippet=_snippet(node),
                index=idx,
            )
        )
    return out


def plan_file(source_path: Path) -> list[Planned]:
    """Plan mutants for a file on disk."""
    return plan(source_path.read_text())


def alter_one(node: ast.AST, op: str) -> bool:
    """Apply *op* to *node* in place. Returns False if nothing changed.

    Every branch is total. An operator with no counterpart reports False rather
    than silently doing nothing, so the caller can refuse to record a mutant it
    could not actually create.
    """
    if op == "ROR" and isinstance(node, ast.Compare) and node.ops:
        name = type(node.ops[0]).__name__
        if name in SWAPPED:
            node.ops[0] = getattr(ast, SWAPPED[name])()
            return True
        return False
    if op == "AOR" and isinstance(node, ast.BinOp):
        name = type(node.op).__name__
        if name in SWAPPED:
            node.op = getattr(ast, SWAPPED[name])()
            return True
        return False
    if op == "LCR" and isinstance(node, ast.BoolOp):
        name = type(node.op).__name__
        if name in OPPOSITE_BOOL:
            node.op = getattr(ast, OPPOSITE_BOOL[name])()
            return True
        return False
    if op == "BOOL" and isinstance(node, ast.Constant) and isinstance(node.value, bool):
        node.value = not node.value
        return True
    if (
        op == "NUM"
        and isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and node.value in (0, 1)
    ):
        node.value = 1 - node.value
        return True
    if op == "BRANCH" and isinstance(node, ast.If):
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        return True
    return False


def apply_one(source_text: str, target: Planned) -> str:
    """Rewrite *source_text*, mutating the `target.index`-th site of `target.op`.

    Raises RuntimeError if nothing was altered. A no-op return would be written
    to disk, the suite would pass on unmutated code, and the entry would be
    booked as a survivor -- a phantom that no test could kill. Failing loudly
    keeps that class of bug out of the score entirely.
    """
    tree = ast.parse(source_text)
    altered = False

    class Hit(ast.NodeTransformer):
        def __init__(self) -> None:
            super().__init__()
            self.remaining = target.index

        def visit(self, node: ast.AST) -> ast.AST:
            nonlocal altered
            self.generic_visit(node)
            if self.remaining < 0 or _op_for(node) != target.op:
                return node
            if self.remaining == 0:
                # _op_for already guarantees _alter_one can change this node, but
                # assert rather than assume: if that ever stops holding, the
                # entry must not be recorded as a survivor.
                if not alter_one(node, target.op):
                    raise RuntimeError(
                        f"{target.describe()} is alterable by _op_for but alter_one changed nothing"
                    )
                self.remaining = -1
                altered = True
            else:
                self.remaining -= 1
            return node

    Hit().visit(tree)
    ast.fix_missing_locations(tree)
    if not altered:
        raise RuntimeError(
            f"no {OP_LABEL.get(target.op, target.op)} site #"
            f"{target.index} to alter in {target.snippet!r} "
            f"(planned at line {target.line}); refusing to record a "
            f"survivor that was never mutated"
        )
    return ast.unparse(tree)


def is_noop(original: str, mutated: str) -> bool:
    """Whether *mutated* is the same program as *original*.

    Compares normalised source, not raw text. Comparing the raw strings can
    never report a no-op, because `apply_one` round-trips through `ast.unparse`,
    which reformats everything it touches: a real mutation still differs in
    whitespace, and a fake mutation that only changed formatting would be caught.
    The comparison has to be on the normalised form in both directions or the
    guard is decorative.
    """
    try:
        return ast.unparse(ast.parse(original)) == ast.unparse(ast.parse(mutated))
    except SyntaxError:
        # If either side does not parse, we cannot claim equivalence. Treat it as
        # a real change so the driver surfaces it rather than silently rejecting.
        return False
