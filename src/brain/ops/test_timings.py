"""What each test file costs to run, recorded, so the CI shards can be balanced on it.

The shards were balanced by line count and that was a guess: a file's lines say how much there is
to read and nothing about how long it takes to run. Measured on 2026-10-14 over the last ten
successful pull request runs, **one shard in every run took 66 to 123 minutes while the other
seven took 12 to 25**, and which one it was changed from run to run, because it was whichever
shard the one slow test file happened to land in. A split that weighs files by lines cannot see a
single file that costs an hour, so the slowest shard set the wall clock of every pull request.

**The weights are recorded durations, in a checked-in file, and the split stays a pure function of
the tree.** Every shard is a separate machine computing its own share, so what it balances on must
be the same on all of them: a file in the repository is, a timing fetched at run time is not.
`ops/ci/test-timings.json` holds seconds per test file and is regenerated from the JUnit reports
the shards keep (`python -m brain.ops.test_timings refresh <directory>`), which the nightly suite
produces for the whole suite every night.

**A file with no recorded time is weighed from its lines at the rate the recorded files show**
(their median milliseconds per line), so a new test file lands somewhere sensible the day it is
written and not in a shard of its own with a weight of nothing. A file that is gone from the tree
is ignored and dropped by the next refresh. A timings file that cannot be read is treated as no
timings at all, which is the old split by lines: **the failure direction is a worse balance and
never a file that does not run**, because the weights only ever decide which shard a file lands in.

**A test that costs minutes can be carved out of its file (`CARVED_OUT`).** A shard is handed
files, and `tests/unit/test_acceptance.py` holds three tests that each run the whole acceptance
registry against a real database (about 570 checks, once, twice and once), so the file alone cost
more than a shard's even share and no assignment of files could balance around it. Each of the
three is a unit of its own with a timing of its own, the file's other tests are one more unit, and
`brain.ops.test_shards.arguments` turns a shard's units back into pytest arguments with a
`--deselect` for each carved test that runs elsewhere, so every test still runs exactly once. The
list is short on purpose: a carve is a node id on a command line, and it is for a test that is
slow by its nature and not for a file that is merely long.

**Rejected: timing the shards at run time and handing them a plan.** That puts a serial job in
front of every shard and a second place for the runners to disagree, the reasons `test_plan`
computes its own plan too. **Rejected: a timing per test for every test.** It would put a node id on
every command line for no gain over the few tests that are slow by nature.

Task ids: none
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Final

REPO: Final = Path(__file__).resolve().parents[3]

#: Where the recorded durations live, relative to the repository root.
TIMINGS_PATH: Final = Path("ops") / "ci" / "test-timings.json"

#: How many shards CI splits the suite into, for the refresh's warning. The workflow's own matrix is
#: the truth and `tests/unit/test_ci_workflow.py` holds the two equal.
SHARDS: Final = 8

#: The rate used for a file with no recorded time when there are no recorded times at all, which
#: makes the split by lines the old one (a weight of one millisecond per line).
MILLISECONDS_PER_LINE_WITHOUT_TIMINGS: Final = 1.0

#: Tests carved out of their file because each costs minutes: test file to the names of the test
#: functions that are a unit of their own. A test named here must exist in the file and no other
#: test in it may start with its name, because `--deselect` matches by prefix
#: (`tests/unit/test_test_shards.py` holds both). Each of these runs the whole acceptance registry
#: over a migrated database, which is why they are slow, and why they are independent: each makes
#: a scratch database of its own.
CARVED_OUT: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "tests/unit/test_acceptance.py": (
            "test_on_a_real_database_the_checks_pass_and_leave_nothing_but_their_results",
            "test_the_page_serves_the_newest_run_of_the_commit_it_is_asked_about",
            "test_the_worker_runs_once_per_commit_and_again_when_asked",
        ),
    }
)

#: The rule the weights keep, in words, for the test that holds it.
A_FILE_WITH_NO_TIME_IS_WEIGHED_BY_ITS_LINES: Final = (
    "A file with no recorded time is weighed from its lines at the rate the recorded files show, "
    "and a timings file that cannot be read is no timings at all: the split gets worse and no "
    "test stops running."
)


def lines(path: Path) -> int:
    """The cost of one file in lines, so a CRLF checkout weighs a file the same as LF.

    At least one, so an empty file still counts as a file a shard has to hold.
    """
    return max(1, path.read_bytes().count(b"\n"))


def load(root: Path = REPO) -> dict[str, float]:
    """The recorded seconds per test file, or nothing when the file is absent or unreadable."""
    path = root / TIMINGS_PATH
    if not path.is_file():
        return {}
    try:
        seconds = json.loads(path.read_text(encoding="utf-8")).get("seconds", {})
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(seconds, dict):
        return {}
    return {
        str(name): float(value)
        for name, value in seconds.items()
        if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0
    }


def unit_path(unit: str) -> str:
    """The file a unit lives in: the unit itself for a file, the part before `::` for a test."""
    return unit.partition("::")[0]


def units(files: Iterable[str]) -> tuple[str, ...]:
    """Every file, and after each the tests carved out of it, in the order given.

    A carved file's own unit stands for the tests that were not carved out.
    """
    made: list[str] = []
    for name in files:
        made.append(name)
        made.extend(f"{name}::{test}" for test in CARVED_OUT.get(name, ()))
    return tuple(made)


def rate(known: Mapping[str, float], root: Path = REPO) -> float:
    """Milliseconds a line costs, as the median over the recorded whole files that still exist.

    A carved file and its carved tests are left out: their times do not add up to the file's lines.
    """
    ratios = [
        seconds * 1000 / lines(root / name)
        for name, seconds in sorted(known.items())
        if name not in CARVED_OUT and "::" not in name and (root / name).is_file()
    ]
    return statistics.median(ratios) if ratios else MILLISECONDS_PER_LINE_WITHOUT_TIMINGS


def weights(
    wanted: Iterable[str], root: Path = REPO, timings: Mapping[str, float] | None = None
) -> dict[str, int]:
    """Every unit's weight in milliseconds, recorded where there is a record and by lines where not.

    A unit with no record is weighed from the lines of its file, and a carved file's lines are
    shared among its tests and the rest. A pure function of the tree and the timings file, so every
    runner computes the same weights.
    """
    known = load(root) if timings is None else timings
    per_line = rate(known, root)
    made: dict[str, int] = {}
    for name in wanted:
        seconds = known.get(name)
        if seconds is not None:
            made[name] = max(1, round(seconds * 1000))
            continue
        path = unit_path(name)
        parts = len(CARVED_OUT.get(path, ())) + 1
        made[name] = max(1, round(lines(root / path) * per_line / parts))
    return made


def file_of(classname: str, root: Path = REPO) -> str | None:
    """The test file a JUnit `classname` belongs to, as a repository path, if one exists.

    pytest writes `tests.unit.test_x` for a function and `tests.unit.test_x.TestClass` for a method,
    so trailing parts are dropped until what is left is a file in the tree.
    """
    parts = classname.split(".")
    while parts:
        candidate = "/".join(parts) + ".py"
        if (root / candidate).is_file():
            return candidate
        parts.pop()
    return None


def from_junit(reports: Iterable[Path], root: Path = REPO) -> dict[str, float]:
    """Seconds per unit, summed over every test case in these JUnit reports.

    A test carved out of its file is a unit of its own (`file::test`, with every parameter of it
    summed) and the file's unit holds the rest.
    """
    totals: dict[str, float] = {}
    for report in reports:
        tree = ET.parse(report).getroot()  # noqa: S314  our own pytest's output
        for case in tree.iter("testcase"):
            name = file_of(case.get("classname", ""), root)
            if name is None:
                continue
            test = case.get("name", "").partition("[")[0]
            unit = f"{name}::{test}" if test in CARVED_OUT.get(name, ()) else name
            totals[unit] = totals.get(unit, 0.0) + float(case.get("time", "0") or 0)
    return totals


def oversized(made: Mapping[str, int], shards: int) -> dict[str, int]:
    """The files that alone cost more than one shard's even share of everything.

    **No split can balance around one of these**: the shard holding it is the slowest however the
    rest is dealt, so the file has to be made faster or split in two. A refresh names them, and a
    test holds the checked-in record to having none, so a test that grows past a shard's share is
    found on the day the record says so and not on the day a pull request takes an hour.
    """
    share = sum(made.values()) / shards
    return {name: weight for name, weight in sorted(made.items()) if weight > share}


def merged(
    old: Mapping[str, float], fresh: Mapping[str, float], root: Path = REPO
) -> dict[str, float]:
    """The new record: fresh times win, old times stand for files this run did not run, and a
    file that is gone from the tree is dropped."""
    combined = {**old, **fresh}
    return {name: combined[name] for name in sorted(combined) if (root / unit_path(name)).is_file()}


def write(seconds: Mapping[str, float], root: Path = REPO) -> Path:
    """Write the record sorted, rounded to a tenth of a second, with LF endings."""
    path = root / TIMINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "note": (
            "Seconds per test file, and per carved-out test as file::test, regenerated from the "
            "shards' JUnit reports by `python -m brain.ops.test_timings refresh <directory>`. "
            "Read by brain.ops.test_shards to balance the CI shards; a file missing here is "
            "weighed by its lines."
        ),
        "seconds": {name: round(value, 1) for name, value in sorted(seconds.items())},
    }
    path.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv: Sequence[str] | None = None, *, root: Path = REPO) -> int:
    """`refresh <directory>`: rewrite the record from every JUnit report under a directory."""
    parser = argparse.ArgumentParser(
        prog="python -m brain.ops.test_timings",
        description="Regenerate the recorded test durations from the shards' JUnit reports.",
    )
    parser.add_argument("command", choices=["refresh"])
    parser.add_argument("directory", type=Path, help="a directory holding the shards' XML reports")
    parser.add_argument(
        "--shards", type=int, default=SHARDS, help="how many shards CI splits the suite into"
    )
    args = parser.parse_args(argv)
    reports = sorted(args.directory.rglob("*.xml"))
    if not reports:
        print(f"refused: no JUnit report under {args.directory}", file=sys.stderr)
        return 2
    fresh = from_junit(reports, root)
    record = merged(load(root), fresh, root)
    path = write(record, root)
    print(f"{len(fresh)} test file(s) timed from {len(reports)} report(s); wrote {path}")
    for name, milliseconds in oversized(weights(sorted(record), root, record), args.shards).items():
        print(
            f"OVERSIZED {name}: {milliseconds / 1000:.0f} seconds, more than a shard's even share; "
            "make it faster or split it, no assignment can balance around it"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point a person runs
    raise SystemExit(main())
