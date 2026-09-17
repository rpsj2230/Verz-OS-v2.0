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
`pyproject.toml` settings pytest reads, and they are weighed by line count rather than by
bytes, because a checkout with CRLF line endings has different byte sizes and the same lines.

**Balanced by size because there is no record of durations.** The repository keeps no timings
per file, and the pytest progress log of the single job advanced at a roughly even rate through
the alphabet, so the lines in a file are a fair proxy for its cost. The assignment is the
classic greedy one, heaviest file first onto the lightest shard, which keeps the heaviest and
lightest shards within one file's weight of each other.

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
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

REPO: Final = Path(__file__).resolve().parents[3]

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
    """The cost of one file, in lines, so a CRLF checkout weighs a file the same as LF.

    At least one, so an empty file still counts as a file a shard has to hold.
    """
    return max(1, path.read_bytes().count(b"\n"))


def partition(weights: Mapping[str, int], shards: int) -> tuple[tuple[str, ...], ...]:
    """Every file into exactly one of `shards` groups, heaviest first onto the lightest group.

    Ties are broken by path and then by shard number, never by the order the mapping was
    built in, so every runner reaches the same answer from the same files.
    """
    if shards < 1:
        msg = f"a split needs at least one shard, not {shards}"
        raise ShardError(msg)
    if len(weights) < shards:
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


def shard(number: int, of: int, root: Path = REPO) -> tuple[str, ...]:
    """The files shard `number` runs, counting from one, out of `of` shards."""
    if not 1 <= number <= of:
        msg = f"shard {number} is not one of 1 to {of}"
        raise ShardError(msg)
    files = collected(root)
    return partition({name: weight(root / name) for name in files}, of)[number - 1]


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
