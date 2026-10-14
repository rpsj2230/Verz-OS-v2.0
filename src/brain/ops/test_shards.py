"""Which of the test files one CI shard runs.

The unit job ran every test file in one process and took longer than every other job in CI put
together, so it is split into shards that run side by side, each with a database of its own.
That split is only safe if two things hold, and both fail silently:

**Every file lands in exactly one shard.** A file in no shard is a test that stops running
with every job green, which reads in a diff as nothing at all. A file in two is only slower,
but it is the same mistake in the other direction, and a split that can duplicate can drop.

**Every runner computes the same split.** Each shard is a separate machine asking this module
for its own share, and none of them sees the others' answers. So the split is a pure function
of the tree: the files are the ones a bare `pytest` would collect, read from the same
`pyproject.toml` settings pytest reads, and they are weighed from `ops/ci/test-timings.json`, a
file in the repository, never from anything fetched at run time.

**Balanced by recorded duration, with the lines in a file as the fallback (2026-10-14).** It was
balanced by line count alone, "because there is no record of durations", and that was measured to
be wrong where it mattered: one shard in every pull request run took 66 to 123 minutes while the
other seven took 12 to 25, because a line count cannot see one file that costs an hour
(`brain.ops.test_timings` has the measurement and the reasons). A file with a recorded time is
weighed by it, a file without one by its lines at the rate the recorded files show, and the
assignment is the classic greedy one, heaviest first onto the lightest shard, which keeps the
heaviest and lightest shards within one file's weight of each other.

**A test that costs minutes is a unit of its own (`brain.ops.test_timings.CARVED_OUT`).** The shard
is handed pytest arguments and not only files: the file, with a `--deselect` for each carved test
that runs in another shard, and `file::test` for a carved test that runs here without its file.
Every test still runs exactly once, which `tests/unit/test_test_shards.py` proves by asking pytest
to collect each shard's arguments and comparing the union with the file's own collection.

**A shard with nothing in it is refused rather than printed.** The workflow hands this output
to `pytest` as arguments, and `pytest` given no arguments runs `testpaths`: an empty shard would
silently run the whole suite again rather than run nothing.

Task ids: none
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from brain.ops import test_timings

REPO: Final = test_timings.REPO

#: pytest's own defaults for the two settings, used when `pyproject.toml` does not set them.
DEFAULT_PYTHON_FILES: Final = ("test_*.py", "*_test.py")
DEFAULT_NORECURSEDIRS: Final = (
    "*.egg",
    ".*",
    "_darcs",
    "build",
    "CVS",
    "dist",
    "node_modules",
    "venv",
    "{arch}",
)


class ShardError(ValueError):
    """A shard that cannot be computed, with the reason in words."""


def _pytest_settings(root: Path) -> Mapping[str, object]:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    settings = parsed.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return settings if isinstance(settings, dict) else {}


def _setting(settings: Mapping[str, object], key: str, default: Sequence[str]) -> tuple[str, ...]:
    value = settings.get(key)
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        return tuple(value.split())
    if isinstance(value, list):
        return tuple(str(one) for one in value)
    msg = f"pytest's {key} in pyproject.toml is neither a string nor a list: {value!r}"
    raise ShardError(msg)


def collected(root: Path = REPO) -> tuple[str, ...]:
    """Every test file a bare `pytest` in `root` would collect, as sorted POSIX paths.

    Read from the same settings pytest reads: `testpaths` for where to start, `python_files`
    for what a test file is called, and `norecursedirs` for the directories it never enters.
    """
    settings = _pytest_settings(root)
    starts = _setting(settings, "testpaths", ("",))
    patterns = _setting(settings, "python_files", DEFAULT_PYTHON_FILES)
    skipped = _setting(settings, "norecursedirs", DEFAULT_NORECURSEDIRS)

    found: set[str] = set()
    for start in starts:
        for path in (root / start).rglob("*.py"):
            relative = path.relative_to(root)
            directories = relative.parts[len(Path(start).parts) : -1]
            if any(fnmatch.fnmatch(part, rule) for part in directories for rule in skipped):
                continue
            if any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
                found.add(relative.as_posix())
    return tuple(sorted(found))


def weight(path: Path) -> int:
    """The cost of one file in lines: the fallback weight, and what a test file with no recorded
    time is estimated from (`brain.ops.test_timings.weights`)."""
    return test_timings.lines(path)


def partition(
    weights: Mapping[str, int], shards: int, *, allow_empty: bool = False
) -> tuple[tuple[str, ...], ...]:
    """Every file into exactly one of `shards` groups, heaviest first onto the lightest group.

    Ties are broken by path and then by shard number, never by the order the mapping was
    built in, so every runner reaches the same answer from the same files.

    **`allow_empty` is for a selection and never for the whole suite.** A selected run
    (`brain.ops.test_plan`) can legitimately hand a shard nothing, and the caller then runs no
    pytest at all instead of handing it no arguments; the whole suite has no such excuse, so
    the default still refuses a split with a shard that would run everything.
    """
    if shards < 1:
        msg = f"a split needs at least one shard, not {shards}"
        raise ShardError(msg)
    if len(weights) < shards and not allow_empty:
        msg = (
            f"{len(weights)} test file(s) cannot fill {shards} shards, and an empty shard hands "
            "pytest no arguments, which runs the whole suite"
        )
        raise ShardError(msg)
    groups: list[list[str]] = [[] for _ in range(shards)]
    totals = [0] * shards
    for name in sorted(weights, key=lambda one: (-weights[one], one)):
        lightest = min(range(shards), key=lambda index: (totals[index], index))
        groups[lightest].append(name)
        totals[lightest] += weights[name]
    return tuple(tuple(sorted(group)) for group in groups)


def arguments(group: Iterable[str]) -> tuple[str, ...]:
    """The pytest arguments that run exactly the units in `group`.

    A plain file is itself. A carved file whose own unit is here is the file, with a `--deselect`
    for each carved test that is not here; a carved test here without its file is `file::test`.
    Never both the file and one of its tests, which pytest would run twice.
    """
    chosen = set(group)
    made: list[str] = []
    for name in sorted(one for one in chosen if "::" not in one):
        made.append(name)
        made.extend(
            f"--deselect={name}::{test}"
            for test in test_timings.CARVED_OUT.get(name, ())
            if f"{name}::{test}" not in chosen
        )
    made.extend(
        sorted(one for one in chosen if "::" in one and test_timings.unit_path(one) not in chosen)
    )
    return tuple(made)


def units_run(args: Iterable[str]) -> set[str]:
    """The units a set of pytest arguments runs: the inverse of `arguments`.

    A file is its own unit and, with it, every carved test of that file that is not deselected;
    `file::test` is that test alone. Asserting the units of every shard are disjoint and cover the
    suite is how the split is held to running every test once.
    """
    given = list(args)
    deselected = {one.removeprefix("--deselect=") for one in given if one.startswith("--deselect=")}
    ran: set[str] = set()
    for one in given:
        if one.startswith("--"):
            continue
        ran.add(one)
        if "::" not in one:
            ran |= {
                f"{one}::{test}"
                for test in test_timings.CARVED_OUT.get(one, ())
                if f"{one}::{test}" not in deselected
            }
    return ran


def shard(number: int, of: int, root: Path = REPO) -> tuple[str, ...]:
    """The pytest arguments shard `number` runs, counting from one, out of `of` shards."""
    if not 1 <= number <= of:
        msg = f"shard {number} is not one of 1 to {of}"
        raise ShardError(msg)
    wanted = test_timings.units(collected(root))
    return arguments(partition(test_timings.weights(wanted, root), of)[number - 1])


def main(argv: Sequence[str] | None = None) -> int:
    """Print one shard's files, one per line, or refuse with exit status 2."""
    parser = argparse.ArgumentParser(
        prog="python -m brain.ops.test_shards",
        description="List the test files one CI shard runs.",
    )
    parser.add_argument("--shard", type=int, required=True, help="which shard, counting from 1")
    parser.add_argument("--of", type=int, required=True, help="how many shards there are")
    args = parser.parse_args(argv)
    try:
        files = shard(args.shard, args.of)
    except ShardError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print("\n".join(files))
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point CI runs
    raise SystemExit(main())
