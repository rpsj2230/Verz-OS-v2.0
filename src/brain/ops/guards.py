"""Which conditions in a module no test can reach, and which test files could reach them.

`brain.ops.mutation` is the harness: it takes a list of deliberate breakages, runs them in a
throwaway worktree and says which ones a test caught. This is the part that decides what to
break and what to run, and it lives here for a reason that took two weeks to notice.

**`CLAUDE.md` has told every reader since 2026-09-07 to use `.scratch/guard_audit.py`, and
`.scratch/` is in `.gitignore`.** The process this repository argues hardest for, the one that
has found roughly fifty real defects, existed only as untracked files on one machine. Anybody
cloning this repository got the instructions and none of the tooling, which is the same shape
as a scheduled control nobody runs: correct, documented, and absent from every direction
except the one that matters. Moving it here is the fix, and the module is written to be read
as well as run, because the two-stage rule below is easier to get wrong than to state.

**A guard is an `if` whose condition decides something, and there are more of them than there
are `if` statements.** `conditions` returns the `if` statements a mutation can address, and
`decisions_not_mutated` returns everything else that decides: a filter inside a comprehension,
an `or` fallback on a return, a conditional expression, and any `if` whose condition wraps
across lines so its source cannot be matched exactly. Both are returned, always, because a
tool that reports twelve guards and stays silent about nine comprehension filters gives a
clean table for a module whose decisions are mostly unwatched. `brain.migration.skills` has
five statements and five filters; `brain.knowledge.search.lexical_legs` has no `if` statement
at all and two decisions, a filter and a fallback. See
`A_CLEAN_TABLE_OVER_HALF_A_MODULE_IS_WORSE_THAN_NO_TABLE`.

**The test set is worked out from the import graph and the depth is an argument.** Naming too
few test files makes every guard the other files cover come back as a survivor, and a survivor
reads as a gap in the code rather than a gap in the run: that is how `gate/leash.py` came to
be written up as having seven unreachable guards, three of them security checks, when it has
none. Naming too many is the opposite failure and it is not theoretical either: followed to a
fixed point, `ops/admission.py` is reachable from a hundred and five test files, which is the
whole suite thirty-three times over, so the audit does not get run at all. `reaching` takes a
depth. Zero is the module and the tests that name it, which is the cheap first pass; one adds
the modules that import it and their tests. The rule is to widen when a survivor is still
standing rather than in advance, and for a foundational module zero is the only depth that
gets run at all. See `A_SCOPE_NOBODY_RUNS_IS_WORTH_LESS_THAN_A_NARROW_ONE_SOMEBODY_DOES`.

**A first-pass survivor is a candidate and never a finding**, and `audit` will not let a
caller forget which of the two they have: the report it returns says how many test files it
ran and at what depth, so a survivor list quoted into a commit message carries its own scope.

What was rejected. Deriving the test set by grepping for the module's name. It hits the name
in a comment and in a docstring arguing against importing it, and it misses every test that
reaches the module through another one, which for a module anything imports is most of them.
The import graph is parsed instead.

Rejected: mutating a wrapped condition by rewriting the whole statement. `ast` does not hand
back source verbatim, so the replacement would be this module's idea of what the condition
said, and `brain.ops.mutation` matches on exact bytes for exactly the reason that a harness
which edits a file it cannot reproduce is one that leaves the tree changed after a crash.
Wrapped conditions are reported instead, and mutating one by hand is two minutes.

Task ids: none
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

from brain.ops.mutation import Mutation, Report, verify


class GuardAuditError(Exception):
    """Raised when an audit would report a scope it did not run."""


# ------------------------------------------------------------------ written-down reasons
#: Why the decisions a mutation cannot address are reported rather than skipped.
A_CLEAN_TABLE_OVER_HALF_A_MODULE_IS_WORSE_THAN_NO_TABLE: Final = (
    "A tool that mutates `if` statements and says nothing about comprehension filters gives "
    "a clean table for a module whose decisions are mostly unwatched, and the table is what "
    "gets quoted into a commit message. brain.migration.skills has five statements and five "
    "filters; brain.knowledge.search.lexical_legs has no `if` statement in it at all and two "
    "decisions, a filter and a fallback. "
    "Every decision this cannot mutate is listed, so a reader counts the decisions rather "
    "than the rows."
)

#: Why the test set has a depth rather than being the transitive closure.
A_SCOPE_NOBODY_RUNS_IS_WORTH_LESS_THAN_A_NARROW_ONE_SOMEBODY_DOES: Final = (
    "Too few test files makes every guard the others cover come back as a survivor, and a "
    "survivor reads as a gap in the code rather than a gap in the run: that is how "
    "gate/leash.py was written up as having seven unreachable guards when it has none. Too "
    "many is the opposite failure and is just as real: at a fixed point ops/admission.py is "
    "reachable from a hundred and five test files, which is the whole suite thirty-three "
    "times over, so nobody runs it. One hop is usually right and the rule is to widen when a "
    "survivor is still standing, not in advance."
)

#: How many lines above an `if` may be pulled in to make its source unique in the file.
#:
#: Eight rather than unbounded. A condition still ambiguous after eight lines of context sits
#: inside a repeated block, and the honest answer there is to say so rather than to widen
#: until something matches. A `before` that swallows half a function is also one that a later
#: edit anywhere in those lines silently invalidates.
MOST_CONTEXT: Final = 8

#: Where the source and the tests live, relative to the repository root.
#:
#: **Read at call time rather than bound as a default argument, and the difference is not
#: style.** A parameter written `src: Path = SRC` captures the value when the module is
#: imported, so reassigning the constant afterwards changes nothing: a test pointing this at a
#: fixture tree got the real one back, ran the whole audit against it, and took ten minutes to
#: say so. Every function below takes `None` and resolves here.
SRC: Final = Path("src")
TESTS: Final = Path("tests")


def _source(path: Path) -> tuple[str, list[str]]:
    """The file as text and as lines, read as bytes and split on a literal newline.

    Never through `read_text`: the strings this module produces have to match what
    `brain.ops.mutation` sees, and that reads bytes. Universal newline translation would hand
    back lines that join into text the harness cannot find in the file.
    """
    text = path.read_bytes().decode("utf-8")
    return text, text.split("\n")


@dataclass(frozen=True)
class Decision:
    """One condition in a module, and whether a mutation can address it."""

    line: int
    source: str
    #: Why this one cannot be mutated automatically, or empty when it can.
    unmutatable: str = ""


def conditions(path: Path) -> tuple[Decision, ...]:
    """Every `if` statement whose source line a mutation can match exactly, in line order.

    Every `if` rather than only the ones that refuse. The shape here is a conjunctive return
    or a condition spread over a call far more often than it is a bare `if x: return False`,
    and skipping a branch that is not a guard is also a behaviour change a test should notice.
    """
    text, lines = _source(path)
    found: list[Decision] = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.If):
            continue
        line = lines[node.lineno - 1]
        if not line.rstrip().endswith(":"):
            continue
        found.append(Decision(line=node.lineno, source=line))
    return tuple(sorted(found, key=lambda one: one.line))


def decisions_not_mutated(path: Path) -> tuple[Decision, ...]:
    """Every other condition in the module, in line order, each saying why it is not mutated.

    Five shapes, and each is a real gap rather than a curiosity. A wrapped `if` cannot be
    matched byte for byte. A comprehension filter and a conditional expression are not `ast.If`
    at all. A `BoolOp` in a `return` is the `or ("tsv",)` fallback shape, which decides what a
    caller gets when everything above produced nothing.

    **The fifth is `match`, and it was missing until 2026-09-11 in the worst way this function
    has: silently, and in both directions.** A `case` arm is not an `ast.If`, a comprehension,
    an `IfExp` or a `Return` holding a `BoolOp`, so it was neither mutated nor listed, and a
    module whose decisions are arms came back with a clean table and no note under it. That is
    exactly `A_CLEAN_TABLE_OVER_HALF_A_MODULE_IS_WORSE_THAN_NO_TABLE`, arriving through a node
    shape this function did not know about rather than through one it declined to handle.

    The measurement is why it matters more than the count suggests: **53 match statements, 213
    case arms, in 31 modules under `src/brain`**, and the modules CLAUDE.md holds up as audited
    with no survivors remaining are among the heaviest users. `gate/leash.py` reports 21 `if`
    statements mutated and 4 decisions named while 18 arms were invisible; `ops/partitioning.py`
    has 22 arms, `core/scope_sql.py` 19, `ops/storage.py` and `identity/lifecycle.py` 13 each,
    `ops/spend.py` and `ops/admission.py` 11 each. Those audits were run honestly and reported
    a number that was true about `if` statements and read as a number about decisions.

    Each arm is listed separately rather than one entry for the statement, because an arm is
    the decision: a reader mutating these by hand has to reach each one, and a single line
    saying "a match statement" tells them how many statements there are rather than how much
    work is in front of them. A wildcard `case _` is listed too. It is where an unmatched value
    lands, which is the branch that decides what happens to input nobody anticipated, and it is
    the arm most likely to be reachable only by something no test builds.

    See `A_CLEAN_TABLE_OVER_HALF_A_MODULE_IS_WORSE_THAN_NO_TABLE`.
    """
    text, lines = _source(path)
    tree = ast.parse(text)
    found: list[Decision] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if not lines[node.lineno - 1].rstrip().endswith(":"):
                found.append(
                    Decision(
                        line=node.lineno,
                        source=lines[node.lineno - 1].strip(),
                        unmutatable="the condition wraps across lines",
                    )
                )
            continue
        if isinstance(node, ast.comprehension):
            found.extend(
                Decision(
                    line=one.lineno,
                    source=lines[one.lineno - 1].strip(),
                    unmutatable="a filter inside a comprehension",
                )
                for one in node.ifs
            )
            continue
        if isinstance(node, ast.IfExp):
            found.append(
                Decision(
                    line=node.lineno,
                    source=lines[node.lineno - 1].strip(),
                    unmutatable="a conditional expression",
                )
            )
            continue
        if isinstance(node, ast.Match):
            found.extend(
                Decision(
                    line=arm.pattern.lineno,
                    source=lines[arm.pattern.lineno - 1].strip(),
                    unmutatable=(
                        "a guarded arm of a match statement"
                        if arm.guard is not None
                        else "an arm of a match statement"
                    ),
                )
                for arm in node.cases
            )
            continue
        if isinstance(node, ast.Return) and isinstance(node.value, ast.BoolOp):
            found.append(
                Decision(
                    line=node.lineno,
                    source=lines[node.lineno - 1].strip(),
                    unmutatable="a boolean fallback on a return",
                )
            )
    return tuple(sorted(found, key=lambda one: one.line))


def _refused(line: str) -> str:
    """The same line with its condition replaced, keeping the indentation and any carriage."""
    body = line.rstrip()
    tail = line[len(body) :]
    indent = " " * (len(line) - len(line.lstrip()))
    return f"{indent}if False:{tail}"


def anchored(path: Path, line: int) -> tuple[str, str] | None:
    """A `before`/`after` pair for the `if` at `line`, unique in the file, or None.

    Grows upward one line at a time, so the table carries the smallest workable context: a
    `before` is invalidated by an edit to any line it covers, and the shortest one that
    identifies the guard survives longest.
    """
    text, lines = _source(path)
    index = line - 1
    for back in range(MOST_CONTEXT + 1):
        start = index - back
        if start < 0:
            break
        before = "\n".join(lines[start : index + 1])
        if text.count(before) == 1:
            after = "\n".join([*lines[start:index], _refused(lines[index])])
            return before, after
    return None


# ------------------------------------------------------------------- the test set
def module_name(path: Path) -> str:
    """The dotted name of a module under `src`, from its path."""
    parts = path.with_suffix("").parts
    if "brain" not in parts:
        msg = f"{path} is not under src/brain"
        raise GuardAuditError(msg)
    return ".".join(parts[parts.index("brain") :])


@cache
def _imports(path: Path) -> frozenset[str]:
    """Every dotted name a file imports, in both `import x.y` and `from x import y` forms.

    Cached, and the cache is what makes a survey possible at all: without it, asking which
    tests reach one module costs a parse of `src` and of `tests`, and asking about every module
    in the tree costs that squared. `brain.ops.controls` carries the same three caches for the
    same reason and its tests clear them, which is the shape to copy if this is ever pointed at
    a tree that changes under it.

    A `frozenset` rather than a `set` because a cached mutable is a shared mutable, and the one
    caller that edited a returned set would be editing every later caller's answer.
    """
    try:
        tree = ast.parse(path.read_bytes().decode("utf-8"))
    except SyntaxError:
        return frozenset()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(one.name for one in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{one.name}" for one in node.names)
    return frozenset(names)


def _python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


@cache
def _graph(root: Path) -> Mapping[str, frozenset[str]]:
    """Every module under `root` and what it imports, read once.

    A `MappingProxyType` rather than a dict, for the reason the `frozenset` above is frozen: a
    cached mapping handed out raw is one any caller can edit for every later caller.
    """
    return MappingProxyType({module_name(path): _imports(path) for path in _python_files(root)})


def reaching(target: str, *, depth: int = 1, src: Path | None = None) -> set[str]:
    """Every module that imports `target` within `depth` hops, including it.

    **Zero is a real depth and is the cheap first pass.** It is the module alone, so
    `covering_tests` then returns the files that name it, which for most modules is one. That
    is what makes auditing affordable at all, and it is the scope whose survivors are
    candidates rather than findings.

    Zero is also the only workable depth for a foundational module. `core/entitlement.py` is
    reachable from two hundred and thirty-nine test files at one hop, because everything
    imports it, and by the argument in
    `A_SCOPE_NOBODY_RUNS_IS_WORTH_LESS_THAN_A_NARROW_ONE_SOMEBODY_DOES` a scope that large does
    not get run. This function refused zero until 2026-09-09, on the stated grounds that it
    would drop the module's own tests, which was simply wrong: the module is in the set from
    the first line, so its own tests are exactly what comes back.
    """
    if depth < 0:
        msg = f"a depth of {depth} is not a number of hops"
        raise GuardAuditError(msg)
    root = SRC if src is None else src
    graph = _graph(root)
    if target not in graph:
        msg = f"{target} is not a module under {root}"
        raise GuardAuditError(msg)
    found = {target}
    for _ in range(depth):
        for module, names in list(graph.items()):
            if module in found:
                continue
            if any(one in found or one.rsplit(".", 1)[0] in found for one in names):
                found.add(module)
    return found


def covering_tests(
    module: Path, *, depth: int = 1, tests: Path | None = None, src: Path | None = None
) -> tuple[str, ...]:
    """Every test file that imports something that can reach this module, in path order.

    Named `covering_tests` rather than anything beginning with the word `test`: pytest collects
    any imported callable whose name starts with it, so the obvious name turns this function
    into a test case that errors on a missing fixture the moment a test module imports it. It
    did, once, which is how the name came to be argued about.
    """
    can_reach = reaching(module_name(module), depth=depth, src=src)
    return tuple(
        path.as_posix()
        for path in _python_files(TESTS if tests is None else tests)
        if any(one in can_reach or one.rsplit(".", 1)[0] in can_reach for one in _imports(path))
    )


# --------------------------------------------------------------------- the audit itself
@dataclass(frozen=True)
class Audit:
    """What an audit found, and the scope it found it in.

    The scope is on the result rather than left to the caller to remember, because a survivor
    list quoted into a commit message without its scope is the exact mistake this module's
    docstring is about.
    """

    report: Report
    tests: tuple[str, ...]
    depth: int
    not_mutated: tuple[Decision, ...]

    @property
    def survivors(self) -> tuple[str, ...]:
        """The labels of the mutations no test caught, which are candidates and not findings."""
        return tuple(one.label for one in self.report.survivors)

    def scope_line(self) -> str:
        """One sentence naming what was run, for a commit message."""
        return (
            f"{len(self.report.verdicts)} mutation(s) against {len(self.tests)} test "
            f"file(s) at "
            f"depth {self.depth}, and {len(self.not_mutated)} decision(s) this cannot mutate"
        )


def audit(
    module: Path,
    *,
    depth: int = 1,
    repo: Path = Path(),
    carry: Sequence[str] = (),
    tests_root: Path | None = None,
) -> Audit:
    """Mutate every addressable condition in one module and say which nothing caught.

    `carry` is for files the worktree will not have, which is anything uncommitted: the
    harness builds its tree at a commit, so a module and a test written in the same session
    both have to be carried or the run dies at a baseline that could not import them.
    """
    tests = covering_tests(module, depth=depth, tests=tests_root)
    if not tests:
        msg = f"no test file reaches {module_name(module)} at depth {depth}"
        raise GuardAuditError(msg)
    mutations: list[Mutation] = []
    ambiguous: list[Decision] = []
    for one in conditions(module):
        if one.source.strip() == "if False:":
            continue
        pair = anchored(module, one.line)
        if pair is None:
            ambiguous.append(
                Decision(
                    line=one.line,
                    source=one.source.strip(),
                    unmutatable=f"still ambiguous with {MOST_CONTEXT} lines of context above it",
                )
            )
            continue
        before, after = pair
        mutations.append(
            Mutation(
                label=f"{module.name}:{one.line} {one.source.strip()[:64]}",
                path=module.as_posix(),
                before=before,
                after=after,
                tests=tests,
            )
        )
    package = sorted(one.as_posix() for one in module.parent.glob("*.py"))
    report = verify(
        mutations,
        repo=repo,
        carry=(*package, module.as_posix(), *tests, *carry),
    )
    return Audit(
        report=report,
        tests=tests,
        depth=depth,
        not_mutated=(*decisions_not_mutated(module), *ambiguous),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run python -m brain.ops.guards <module> [depth] [--carry <path> ...]`.

    Prints the scope before the table and the decisions it could not mutate after it, in that
    order deliberately: a reader who stops at the table has already read what was run, and one
    who reads to the end knows what was not. A survivor list without either is the report this
    module exists to stop somebody quoting.

    `--carry` is for a file the worktree will not have, which is anything not committed yet. A
    module and its test written in one session both arrive through the package copy, but a
    migration or a fixture elsewhere in the tree does not, and the run then dies at a baseline
    that could not import them.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    carry: list[str] = []
    if "--carry" in args:
        at = args.index("--carry")
        carry = args[at + 1 :]
        args = args[:at]
    if not args:
        print("usage: python -m brain.ops.guards <module> [depth] [--carry <path> ...]")
        return 2
    module = Path(args[0])
    depth = int(args[1]) if len(args) > 1 else 1

    found = audit(module, depth=depth, repo=Path(), carry=carry)
    print(found.scope_line())
    print(found.report.table())
    print()
    print(f"survivors: {len(found.survivors)}")
    for label in found.survivors:
        print("  ", label)
    if found.not_mutated:
        print("decisions this cannot mutate, which are yours to break by hand:")
        for decision in found.not_mutated:
            print(f"  {decision.line}: {decision.unmutatable}: {decision.source[:70]}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point, exercised by running it
    raise SystemExit(main())
