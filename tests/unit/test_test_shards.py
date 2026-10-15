"""The split of the unit suite into CI shards, asserted over this repository and over pytest.

The two claims `brain.ops.test_shards` exists for both fail silently: a file in no shard stops
running with every job green, and two runners that disagree about the split drop or repeat
files between them. So the union and the disjointness are asserted over this repository's own
tests, and the list of files is compared with what pytest itself collects from a planted tree,
never with a second copy of the rules written here.

Task ids: none
"""

from __future__ import annotations

import ast
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

from brain.ops import test_timings
from brain.ops.test_shards import (
    REPO,
    ShardError,
    arguments,
    collected,
    main,
    partition,
    shard,
    units_run,
    weight,
)
from brain.ops.test_timings import CARVED_OUT, unit_path, units

#: The shard count CI runs today. The union and disjointness hold for any count, and the
#: workflow's own matrix is held to this module in `test_ci_workflow.py`.
SHARDS = 4


def _plant(root: Path, relative: str, body: str = "def test_it():\n    pass\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ over this repository
def test_every_test_file_in_the_repository_lands_in_exactly_one_shard() -> None:
    """The claim that makes splitting the suite safe, in the unit the split deals in (a file, or a
    test carved out of one). Delete this and a change to the split can leave a file, or a carved
    test, in no shard, and its tests stop running while every shard, the coverage floor and the
    deploy all stay green."""
    everything = units(collected())
    shards = [shard(number, SHARDS) for number in range(1, SHARDS + 1)]
    listed = [name for one in shards for name in sorted(units_run(one))]

    assert sorted(listed) == sorted(everything), "a unit is in no shard, or in two"
    assert len(listed) == len(set(listed)) == len(everything)
    files = {unit_path(name) for name in listed}
    for directory in ("tests/unit/", "tests/invariants/", "tests/e2e/", "tests/load/"):
        assert any(name.startswith(directory) for name in files), f"nothing from {directory}"


def test_no_two_shards_share_a_unit() -> None:
    """Disjointness asserted on its own rather than inferred from a count. Delete this and a
    split that repeats one unit and drops another of the same weight passes a check that only
    compares totals."""
    shards = [units_run(shard(number, SHARDS)) for number in range(1, SHARDS + 1)]

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
    assert all(
        (REPO / unit_path(line.removeprefix("--deselect="))).is_file() and "\\" not in line
        for line in lines
    )


# ------------------------------------------------------------------ balanced on recorded time
def test_a_file_recorded_as_slow_gets_a_shard_to_itself_though_it_is_the_shortest_to_read(
    tmp_path: Path,
) -> None:
    """**The measured failure, reproduced on a planted tree.** The slow file has the fewest lines,
    so a split by lines puts it beside others and its shard takes an hour; the record says what it
    costs, so the split gives it a shard alone and deals the rest around it. Delete this and
    `shard` can read the record and still deal by lines, which is the split that left one shard
    at 66 to 123 minutes while the other seven took 12 to 25."""
    for index in range(6):
        _plant(tmp_path, f"tests/test_long_{index}.py", body="def test_it():\n    pass\n" * 40)
    _plant(tmp_path, "tests/test_short_and_slow.py")
    record = tmp_path / "ops" / "ci" / "test-timings.json"
    record.parent.mkdir(parents=True)
    seconds = {f"tests/test_long_{index}.py": 60 for index in range(6)}
    seconds["tests/test_short_and_slow.py"] = 3600
    record.write_text(json.dumps({"seconds": seconds}), encoding="utf-8", newline="\n")

    shards = [shard(number, 3, tmp_path) for number in range(1, 4)]

    assert ("tests/test_short_and_slow.py",) in shards
    assert sorted(name for one in shards for name in one) == sorted(collected(tmp_path))


def test_with_no_record_the_split_is_still_a_split_of_every_file(tmp_path: Path) -> None:
    """The sibling of the one above: take the record away and the shards are the old ones, by
    lines, and still hold every file once. Delete this and the record can become a thing the split
    cannot run without, so a pull request that deletes it runs no tests."""
    for index in range(5):
        _plant(tmp_path, f"tests/test_{index}.py", body="def test_it():\n    pass\n" * (index + 1))

    shards = [shard(number, 2, tmp_path) for number in range(1, 3)]

    assert sorted(name for one in shards for name in one) == sorted(collected(tmp_path))
    assert all(shards)


# ------------------------------------------------------------------ a test carved out of its file
SLOW_FILE = "tests/test_heavy.py"
SLOW_BODY = (
    "import pytest\n\n\n"
    "def test_slow_one():\n    pass\n\n\n"
    "@pytest.mark.parametrize('flavour', ['a', 'b'])\n"
    "def test_slow_two(flavour):\n    pass\n\n\n"
    "def test_quick():\n    pass\n\n\n"
    "class TestQuick:\n    def test_method(self):\n        pass\n"
)


def _collect(root: Path, *args: str) -> list[str]:
    """The node ids pytest collects from these arguments in `root`, in the order it gives them."""
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return [line for line in run.stdout.splitlines() if "::" in line]


def test_every_way_of_dealing_a_carved_file_runs_each_of_its_tests_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Proved with pytest's own collection, over a planted file, for every way its four units can
    be dealt into groups that cover them.** The file, one carved test with a parameter, one without
    and the tests that stayed, collected from each group's arguments and put together, are exactly
    the file's own collection with nothing twice, which is the claim `--deselect` and `file::test`
    exist to keep. Delete this and a shard can run a carved test twice (the file and its node id)
    or never (a deselect with no node id anywhere), and the shards stay green around the hole.

    The positive half is the first case: every unit in one group collects the whole file."""
    _plant(tmp_path, SLOW_FILE, SLOW_BODY)
    carved = ("test_slow_one", "test_slow_two")
    monkeypatch.setattr(test_timings, "CARVED_OUT", {SLOW_FILE: carved})
    every = units([SLOW_FILE])
    whole = _collect(tmp_path, SLOW_FILE)
    assert every == (SLOW_FILE, f"{SLOW_FILE}::test_slow_one", f"{SLOW_FILE}::test_slow_two")
    assert len(whole) == 5

    rest, one, two = every
    for dealing in (
        [every],
        [(rest,), (one,), (two,)],
        [(rest, one), (two,)],
        [(rest, two), (one,)],
        [(one, two), (rest,)],
        [(rest,), (one, two)],
    ):
        collected_by_groups: list[str] = []
        for group in dealing:
            collected_by_groups += _collect(tmp_path, *arguments(group))
        assert sorted(collected_by_groups) == sorted(whole), dealing


def test_the_arguments_for_a_group_never_name_a_file_and_one_of_its_carved_tests_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two forms the arguments take, asserted as text so the collection test above cannot be
    satisfied by an accident of ordering. Delete this and a group holding a file and its carved test
    can print both, which pytest runs twice, or print a deselect for a test the same group runs."""
    monkeypatch.setattr(test_timings, "CARVED_OUT", {"a.py": ("test_x", "test_y")})

    assert arguments(["a.py", "a.py::test_x", "a.py::test_y"]) == ("a.py",)
    assert arguments(["a.py"]) == ("a.py", "--deselect=a.py::test_x", "--deselect=a.py::test_y")
    assert arguments(["a.py", "a.py::test_y"]) == ("a.py", "--deselect=a.py::test_x")
    assert arguments(["a.py::test_y", "a.py::test_x"]) == ("a.py::test_x", "a.py::test_y")
    assert arguments(["b.py", "a.py"]) == (
        "a.py",
        "--deselect=a.py::test_x",
        "--deselect=a.py::test_y",
        "b.py",
    )


def test_every_carved_out_test_exists_and_no_other_test_in_its_file_starts_with_its_name() -> None:
    """`--deselect` matches by prefix, so a second test whose name begins with a carved one's would
    be dropped from the shard that runs the rest of the file and run nowhere, and a carved name that
    no longer exists would be a node id pytest cannot find. Delete this and a rename or an
    innocently named neighbour silently removes a test from the suite."""
    for name, carved in CARVED_OUT.items():
        tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
        defined = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        for test in carved:
            assert defined.count(test) == 1, f"{name} has no single test called {test}"
            neighbours = [one for one in defined if one.startswith(test) and one != test]
            assert neighbours == [], f"{neighbours} would be deselected with {test}"
