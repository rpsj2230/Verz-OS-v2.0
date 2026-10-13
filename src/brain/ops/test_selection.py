"""Which test files a pull request's diff reaches, and the plan that runs only those.

The eight unit shards were 68% of CI's runner minutes over the last 50 pull-request runs
(measured 2026-09-30), and every one of them runs every test file whatever the diff touched. The
cheaper design is to run only the files that import something the diff changed. Its danger is
the one CI exists to prevent: a failure in a file the selection left out is a red test nobody
runs, and a skipped test passes. So it was measured first: for seven pull requests the
`selection_shadow` job asked this module what it would have selected, read which files actually
failed from the shards' JUnit reports, and recorded whether the selection would have missed any
of them. **At depths 0, 1 and 2 it missed nothing, including both real failures in those runs,
while running 113 to 582 of about 1,020 files on an ordinary diff and the whole suite on the two
that touched shared infrastructure.**

**It is switched on for pull requests at depth 1 (`brain.ops.test_plan`).** The shadow job is
retired with it: once a shard runs only the selected files, a failure outside the selection is
never observed by that run, so the shadow could only ever report "no miss". The measurement is
now the nightly full suite (`.github/workflows/nightly-suite.yml`), which runs every file every
night and is also where the coverage floor is held. `main` here and the CLI below stay, because
a record is still how a change to the selection itself is checked against real failures.

**The selection is `brain.ops.guards.covering_tests`, the import graph the mutation audit
already trusts**, at three depths at once, so the record says which depth would have been safe
and what each costs. Zero is the changed module's own importers; each extra hop adds the modules
that import those.

**The full suite, never a selection, for what the graph cannot see.** A change to a conftest,
a fixture, `pyproject.toml`, `uv.lock` or the workflow changes every test at once, and a test
support module under `tests/` that is not itself a test is imported in ways the source graph does
not follow. Those are `FULL_SUITE`, and a diff touching one records "full".

**What the import graph cannot see, and the two widenings that cover it.** A test reads files that
are not Python (the console's source, the documents, the realm, the compose files), and some
tests walk the whole source tree looking for a shape (`test_installation` refuses a function
named for a restore anywhere under `src/brain`). A diff to either selects no test through
imports. So a changed file that is not a source module also selects every test that **names its
top-level directory or its file name** (`readers_of`), and any change to a file that is not a
test also selects every test that **walks a tree** (`scanners`). Both only ever add files, so
they can only make the selection safer, and the cost is measured in `test_plan`'s record. What
remains blind is a test that reads a file with no mention of its directory, and that is the
nightly's to find.

**A deleted source module runs the full suite.** The graph is read from the files that exist, so
a module removed by the diff has no importers to ask, and an importer the diff did not touch is
exactly the test that would break.

Task ids: none
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from brain.ops.guards import GuardAuditError, covering_tests
from brain.ops.test_shards import REPO, collected

#: A diff touching one of these runs the whole suite: the graph cannot say what it reaches.
FULL_SUITE: Final[tuple[str, ...]] = (
    "*conftest.py",
    "tests/fixtures/*",
    "pyproject.toml",
    "uv.lock",
    ".github/workflows/*",
    "src/brain/ops/test_selection.py",
    "src/brain/ops/guards.py",
    "src/brain/ops/test_shards.py",
    "src/brain/ops/test_plan.py",
)

#: Patterns in `FULL_SUITE` that name no file today, and why each is kept. The repository has no
#: conftest; the first one anybody writes reaches every test and must run the suite.
MAY_BE_ABSENT: Final[frozenset[str]] = frozenset({"*conftest.py"})

#: The import-graph depths each record measures side by side.
DEPTHS: Final[tuple[int, ...]] = (0, 1, 2)

#: Run whatever else is selected: cheap, and what a change to any rule is held to.
ALWAYS: Final[str] = "tests/invariants/"

#: A test that walks a tree is asked about every change to a file that is not a test: it may be
#: looking for a shape the change introduces, and no import links the two.
WALKS_A_TREE: Final = re.compile(r"\.r?glob\(|os\.walk\(|ls-files|\.iterdir\(\)")

#: Top-level directories whose name every test mentions for a reason that has nothing to do with
#: the file changed: a test naming `"src"` is not thereby reading each of the thousand files in it.
TOO_COMMON_TO_NAME: Final[frozenset[str]] = frozenset({"src", "tests"})


@dataclass(frozen=True)
class Selection:
    """What one depth would have run: every collected file, or the ones the graph reaches."""

    depth: int
    full: bool
    files: tuple[str, ...]


def _full(changed: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, one) for path in changed for one in FULL_SUITE)


@cache
def _text(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8", errors="replace")


def _needles(path: str) -> tuple[str, ...]:
    """The strings a test would contain if it read this file, from where the file sits.

    A file under a top-level directory (`docs`, `console`, `ops`, `migrations`) is named by that
    directory, quoted or followed by a slash, because tests join path parts rather than writing
    the whole path. A file at the root, or one under `src` or `tests` that is not Python, is named
    by its own name and its folder's.
    """
    parts = path.split("/")
    needles = {parts[-1]}
    if len(parts) > 1:
        top = parts[0]
        if top in TOO_COMMON_TO_NAME:
            if len(parts) > 2:
                needles |= {f'"{parts[-2]}"', f"'{parts[-2]}'", f"{parts[-2]}/"}
        else:
            needles = {f'"{top}"', f"'{top}'", f"{top}/"}
    return tuple(sorted(needles))


def readers_of(path: str, suite: Sequence[str]) -> set[str]:
    """The collected test files whose text names this file's directory or this file."""
    needles = _needles(path)
    return {one for one in suite if any(needle in _text(one) for needle in needles)}


def scanners(suite: Sequence[str]) -> set[str]:
    """The collected test files that walk a tree of files looking for a shape."""
    return {one for one in suite if WALKS_A_TREE.search(_text(one))}


def select(changed: Sequence[str], *, depth: int, suite: Sequence[str]) -> Selection:
    """The test files this diff reaches at `depth`, or the full suite where the graph is blind.

    `suite` is every collected test file, so a selection is always a subset of what a shard runs.
    A diff that cannot be computed (None upstream, empty here) is the full suite.
    """
    if not changed or _full(changed):
        return Selection(depth=depth, full=True, files=tuple(suite))
    chosen: set[str] = {one for one in suite if one.startswith(ALWAYS)}
    everything = Selection(depth=depth, full=True, files=tuple(suite))
    touched_a_non_test = False
    for path in changed:
        exists = (REPO / path).exists()
        if path.startswith("tests/"):
            if path in suite:
                chosen.add(path)
            elif path.endswith(".py") and exists:
                # A support module a test imports: the source graph does not follow it.
                return everything
            elif not path.endswith(".py"):
                touched_a_non_test = True
                chosen.update(readers_of(path, suite))
            continue
        touched_a_non_test = True
        if path.startswith("src/brain/") and path.endswith(".py"):
            if not exists:
                # The graph is read from files that exist: a deleted module has no importers.
                return everything
            try:
                chosen.update(covering_tests(Path(path), depth=depth))
            except GuardAuditError:
                return everything
        else:
            chosen.update(readers_of(path, suite))
    if touched_a_non_test:
        chosen.update(scanners(suite))
    return Selection(depth=depth, full=False, files=tuple(sorted(chosen & set(suite))))


def failed_files(reports: Iterable[Path]) -> set[str]:
    """The test files with a failure or an error in these JUnit reports, as repository paths."""
    failed: set[str] = set()
    for report in reports:
        root = ET.parse(report).getroot()  # noqa: S314  our own pytest's output
        for case in root.iter("testcase"):
            if case.find("failure") is None and case.find("error") is None:
                continue
            dotted = case.get("classname", "")
            # pytest writes `tests.unit.test_x` or `tests.unit.test_x.TestClass`.
            parts = dotted.split(".")
            while parts and not parts[-1].startswith("test_"):
                parts.pop()
            if parts:
                failed.add("/".join(parts) + ".py")
    return failed


def changed_files(base: str, head: str) -> list[str]:
    """What `git diff --name-only base head` names; empty when git cannot say."""
    if not base:
        return []
    done = subprocess.run(  # noqa: S603  two commit ids from the workflow's context, no shell
        ["git", "diff", "--name-only", base, head],  # noqa: S607  git on PATH, as elsewhere here
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.splitlines() if done.returncode == 0 else []


def depth_rows(
    changed: Sequence[str], failed: set[str], suite: Sequence[str]
) -> list[dict[str, object]]:
    """Per depth, what the selection would run and which failed files it would leave out."""
    rows: list[dict[str, object]] = []
    for depth in DEPTHS:
        chosen = select(changed, depth=depth, suite=suite)
        missed = sorted(failed - set(chosen.files))
        rows.append(
            {"depth": depth, "full": chosen.full, "files": len(chosen.files), "missed": missed}
        )
    return rows


def record(changed: Sequence[str], failed: set[str], suite: Sequence[str]) -> dict[str, object]:
    """One pull request's shadow record."""
    rows = depth_rows(changed, failed, suite)
    return {
        "changed": len(changed),
        "suite": len(suite),
        "failed": sorted(failed),
        "depths": rows,
        "would_have_missed": {str(one["depth"]): bool(one["missed"]) for one in rows},
    }


def summary(made: dict[str, object]) -> list[str]:
    """One line per depth, for the job's log and summary."""
    lines = []
    for one in made["depths"] if isinstance(made["depths"], list) else []:
        missed = one["missed"]
        verdict = "MISSED " + ", ".join(missed) if missed else "no miss"
        shape = "full suite" if one["full"] else f"{one['files']} of {made['suite']} files"
        lines.append(f"depth {one['depth']}: {shape}; {verdict}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Write the record and a summary. Always exits 0: the shadow decides nothing."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args(argv)
    suite = collected()
    failed = failed_files(sorted(args.junit.rglob("*.xml")) if args.junit.exists() else [])
    made = record(changed_files(args.base, args.head), failed, suite)
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(made, indent=2) + "\n", encoding="utf-8", newline="\n")
    for line in summary(made):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
