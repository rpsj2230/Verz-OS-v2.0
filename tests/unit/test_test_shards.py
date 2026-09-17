"""The split of the unit suite into CI shards, asserted over this repository and over pytest.

The two claims `brain.ops.test_shards` exists for both fail silently: a file in no shard stops
running with every job green, and two runners that disagree about the split drop or repeat
files between them. So the union and the disjointness are asserted over this repository's own
tests, and the list of files is compared with what pytest itself collects from a planted tree,
never with a second copy of the rules written here.

Task ids: none
"""

from __future__ import annotations

import itertools
import subprocess
import sys
from pathlib import Path

import pytest

from brain.ops.test_shards import (
    REPO,
    ShardError,
    collected,
    main,
    partition,
    shard,
    weight,
)

#: The shard count CI runs today. The union and disjointness hold for any count, and the
#: workflow's own matrix is held to this module in `test_ci_workflow.py`.
SHARDS = 4


def _plant(root: Path, relative: str, body: str = "def test_it():\n    pass\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ over this repository
def test_every_test_file_in_the_repository_lands_in_exactly_one_shard() -> None:
    """The claim that makes splitting the suite safe. Delete this and a change to the split
    can leave a file in no shard, and that file's tests stop running while every shard, the
    coverage floor and the deploy all stay green."""
    everything = collected()
    shards = [shard(number, SHARDS) for number in range(1, SHARDS + 1)]
    listed = [name for one in shards for name in one]

    assert sorted(listed) == sorted(everything), "a file is in no shard, or in two"
    assert len(listed) == len(set(listed)) == len(everything)
    for directory in ("tests/unit/", "tests/invariants/", "tests/e2e/", "tests/load/"):
        assert any(name.startswith(directory) for name in listed), f"nothing from {directory}"


def test_no_two_shards_share_a_file() -> None:
    """Disjointness asserted on its own rather than inferred from a count. Delete this and a
    split that repeats one file and drops another of the same weight passes a check that only
    compares totals."""
    shards = [set(shard(number, SHARDS)) for number in range(1, SHARDS + 1)]

    for left, right in itertools.combinations(shards, 2):
        assert not left & right, f"shared: {sorted(left & right)}"
    assert all(shards), "a shard is empty, and pytest given no file runs the whole suite"


def test_the_shards_are_balanced_to_within_one_file() -> None:
    """The point of the split is wall time, and the longest shard is the wall time. The greedy
    assignment keeps the heaviest and lightest shards within the weight of the heaviest file.

    Delete this and a split that puts nearly everything in shard one still passes the union
    and disjointness tests, and CI is as slow as it was with four runners billed for it."""
    weights = {name: weight(REPO / name) for name in collected()}
    totals = [sum(weights[name] for name in one) for one in partition(weights, SHARDS)]

    assert max(totals) - min(totals) <= max(weights.values())


# ------------------------------------------------------------------ against pytest itself
def test_the_files_listed_are_the_files_a_bare_pytest_collects(tmp_path: Path) -> None:
    """Compared with pytest's own collection over a planted tree rather than with the rules
    restated. Nested directories, both default file patterns, a helper module, a hidden
    directory and `node_modules` are each a place the two could disagree.

    Delete this and the helper can miss a file pytest runs, say one named `*_test.py` or one
    two directories down, and every shard passes while that file runs nowhere."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8", newline="\n"
    )
    for relative in (
        "tests/test_top.py",
        "tests/deep/er/test_nested.py",
        "tests/suffix_test.py",
        "tests/helper.py",
        "tests/.hidden/test_hidden.py",
        "tests/node_modules/test_vendored.py",
        "elsewhere/test_outside.py",
    ):
        _plant(tmp_path, relative)

    run = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    by_pytest = sorted({line.split("::")[0] for line in run.stdout.splitlines() if "::" in line})

    assert run.returncode == 0, run.stdout + run.stderr
    assert by_pytest == [
        "tests/deep/er/test_nested.py",
        "tests/suffix_test.py",
        "tests/test_top.py",
    ]
    assert list(collected(tmp_path)) == by_pytest


# ------------------------------------------------------------------ every runner agrees
def test_the_split_does_not_depend_on_the_order_files_were_found_in() -> None:
    """Each shard is a different machine computing its own share, and a directory listing's
    order is not promised. Delete this and a split that follows discovery order can hand two
    runners overlapping shares, and the file both of them skipped runs nowhere."""
    weights = {f"tests/unit/test_{index:02}.py": 10 + index % 3 for index in range(20)}
    reversed_order = dict(reversed(list(weights.items())))

    assert partition(weights, SHARDS) == partition(reversed_order, SHARDS)


def test_a_file_weighs_the_same_with_crlf_line_endings(tmp_path: Path) -> None:
    """A checkout with CRLF endings has larger files and the same lines. Delete this and the
    split can be weighed in bytes, so a split computed on a Windows checkout to reproduce a
    shard is not the split the runner used."""
    lf = tmp_path / "lf.py"
    crlf = tmp_path / "crlf.py"
    lf.write_bytes(b"a = 1\nb = 2\nc = 3\n")
    crlf.write_bytes(b"a = 1\r\nb = 2\r\nc = 3\r\n")

    assert weight(lf) == weight(crlf) == 3


# ------------------------------------------------------------------ refusals, and the command
def test_more_shards_than_files_is_refused() -> None:
    """An empty shard hands pytest no arguments, and pytest then runs `testpaths`, which is
    the whole suite again. Delete this and a small tree split widely runs everything several
    times over and reports it as a shard."""
    with pytest.raises(ShardError, match="cannot fill"):
        partition({"tests/test_one.py": 1}, 2)
    assert partition({"tests/test_one.py": 1, "tests/test_two.py": 1}, 2) == (
        ("tests/test_one.py",),
        ("tests/test_two.py",),
    )


@pytest.mark.parametrize("number", [0, SHARDS + 1])
def test_a_shard_outside_the_split_is_refused_with_status_two(
    number: int, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shards count from one. Delete this and `--shard 0` can quietly print the last shard's
    files, so a matrix written from zero runs one shard twice and never runs another."""
    assert main(["--shard", str(number), "--of", str(SHARDS)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refused" in captured.err


def test_the_command_prints_one_existing_file_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    """The positive sibling of the refusals: the output is exactly what CI hands to pytest.
    Delete this and the command can print something pytest cannot open, a Windows path or a
    trailing blank, with every function test above still green."""
    assert main(["--shard", str(SHARDS), "--of", str(SHARDS)]) == 0
    lines = capsys.readouterr().out.splitlines()

    assert lines == list(shard(SHARDS, SHARDS))
    assert all((REPO / line).is_file() and "\\" not in line for line in lines)
