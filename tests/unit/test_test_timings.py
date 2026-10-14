"""The recorded durations the CI shards are balanced on, asserted over planted trees and this one.

`brain.ops.test_timings` decides which shard a test file lands in, and the way it can go wrong is
quiet: a weight that is wrong makes one shard slow, and a weight that cannot be computed must not
make a test stop running. So the fallback, the refusal-free reading of a damaged record and the
reading of a real JUnit report are each asserted here against a tree built for the purpose, and the
checked-in record is held to the tree it describes.

Task ids: none
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from brain.ops import test_timings
from brain.ops.test_shards import REPO, collected, partition, shard, units_run
from brain.ops.test_timings import (
    A_FILE_WITH_NO_TIME_IS_WEIGHED_BY_ITS_LINES,
    MILLISECONDS_PER_LINE_WITHOUT_TIMINGS,
    TIMINGS_PATH,
    file_of,
    from_junit,
    load,
    main,
    merged,
    oversized,
    unit_path,
    units,
    weights,
    write,
)


def _plant(root: Path, relative: str, lines: int = 10) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * lines, encoding="utf-8", newline="\n")


def _record(root: Path, body: object) -> None:
    path = root / TIMINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ the weights
def test_a_recorded_file_is_weighed_by_its_recorded_time_and_not_by_its_lines(
    tmp_path: Path,
) -> None:
    """The point of the change: a short file that is slow weighs more than a long one that is
    quick. Delete this and the weights can go back to lines, which is the split that left one
    shard at 66 to 123 minutes while the others took 12 to 25."""
    _plant(tmp_path, "tests/unit/test_short_and_slow.py", lines=5)
    _plant(tmp_path, "tests/unit/test_long_and_quick.py", lines=500)
    _record(
        tmp_path,
        {
            "seconds": {
                "tests/unit/test_short_and_slow.py": 3600,
                "tests/unit/test_long_and_quick.py": 2,
            }
        },
    )

    made = weights(
        ["tests/unit/test_short_and_slow.py", "tests/unit/test_long_and_quick.py"], tmp_path
    )

    assert made == {
        "tests/unit/test_short_and_slow.py": 3_600_000,
        "tests/unit/test_long_and_quick.py": 2_000,
    }


def test_a_file_with_no_record_is_weighed_from_its_lines_at_the_rate_the_recorded_files_show(
    tmp_path: Path,
) -> None:
    """A new test file has no time yet, and weighing it as nothing would put every new file in
    one shard. The rate is the median of the recorded files' milliseconds per line, so one outlier
    does not set it. Delete this and a file written today is weighed at zero or at a rate nothing
    measured, and the first nightly after it is the first the shards are lopsided."""
    for name in ("a", "b", "c"):
        _plant(tmp_path, f"tests/unit/test_{name}.py", lines=10)
    _plant(tmp_path, "tests/unit/test_new.py", lines=20)
    _record(
        tmp_path,
        {
            "seconds": {
                "tests/unit/test_a.py": 1,
                "tests/unit/test_b.py": 3,
                "tests/unit/test_c.py": 100,
            }
        },
    )

    # 100, 300 and 10000 milliseconds a line over ten lines: the median is 300 a line.
    assert weights(["tests/unit/test_new.py"], tmp_path) == {"tests/unit/test_new.py": 20 * 300}


def test_with_no_record_at_all_the_weight_is_the_line_count_the_split_used_before(
    tmp_path: Path,
) -> None:
    """The failure direction: no record is the old split, not an error. Delete this and a tree
    with no timings file raises, so a pull request that deletes the record cannot run its tests
    at all instead of running them badly balanced."""
    _plant(tmp_path, "tests/unit/test_one.py", lines=7)

    assert weights(["tests/unit/test_one.py"], tmp_path) == {"tests/unit/test_one.py": 7}
    assert MILLISECONDS_PER_LINE_WITHOUT_TIMINGS == 1.0


@pytest.mark.parametrize(
    "body",
    ["not json at all", "[]", '{"seconds": []}', '{"seconds": "slow"}', '{"seconds": null}'],
)
def test_a_record_that_cannot_be_read_is_no_record_and_never_a_refusal(
    tmp_path: Path, body: str
) -> None:
    """`A_FILE_WITH_NO_TIME_IS_WEIGHED_BY_ITS_LINES`. A damaged record makes the split worse and
    never stops a file running. Delete this and an edit that breaks the file turns every shard into
    a refusal, and the planner, which must never be the reason tests do not run, is."""
    _plant(tmp_path, "tests/unit/test_one.py", lines=4)
    path = tmp_path / TIMINGS_PATH
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8", newline="\n")

    assert load(tmp_path) == {}
    assert weights(["tests/unit/test_one.py"], tmp_path) == {"tests/unit/test_one.py": 4}
    assert "no test stops running" in A_FILE_WITH_NO_TIME_IS_WEIGHED_BY_ITS_LINES


def test_only_a_non_negative_number_is_a_recorded_time(tmp_path: Path) -> None:
    """A string, a boolean and a negative number are not durations. Delete this and `true` is
    read as one second and a negative time sorts a file below zero, so the greedy order, which
    every runner must agree on, depends on junk."""
    _record(
        tmp_path,
        {"seconds": {"a.py": 2.5, "b.py": "9", "c.py": True, "d.py": -1, "e.py": 0}},
    )

    assert load(tmp_path) == {"a.py": 2.5, "e.py": 0.0}


def test_a_recorded_file_that_is_gone_from_the_tree_does_not_set_the_rate(tmp_path: Path) -> None:
    """The rate is read over the recorded files that still exist. Delete this and a deleted file
    with a wild time keeps skewing what every new file is estimated at."""
    _plant(tmp_path, "tests/unit/test_here.py", lines=10)
    _plant(tmp_path, "tests/unit/test_new.py", lines=10)
    _record(
        tmp_path,
        {"seconds": {"tests/unit/test_here.py": 1, "tests/unit/test_gone.py": 99999}},
    )

    assert weights(["tests/unit/test_new.py"], tmp_path) == {"tests/unit/test_new.py": 1000}


def test_the_weights_do_not_depend_on_the_order_the_files_are_given_in(tmp_path: Path) -> None:
    """Every runner computes its own share, so the weights must be a function of the tree. Delete
    this and a weight that follows the order files were found in hands two runners overlapping
    shares, and the file both skipped runs nowhere."""
    for index in range(6):
        _plant(tmp_path, f"tests/unit/test_{index}.py", lines=3 + index)
    _record(tmp_path, {"seconds": {"tests/unit/test_2.py": 7, "tests/unit/test_4.py": 1}})
    names = [f"tests/unit/test_{index}.py" for index in range(6)]

    assert weights(names, tmp_path) == weights(list(reversed(names)), tmp_path)


# ------------------------------------------------------------------ a test carved out of its file
def test_a_carved_test_is_a_unit_of_its_own_and_the_file_stands_for_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The units the split deals in. Delete this and a carved test is dealt with its file, so the
    file that cost an hour is still one weight and still one shard."""
    monkeypatch.setattr(
        test_timings, "CARVED_OUT", {"tests/unit/test_big.py": ("test_a", "test_b")}
    )

    assert units(["tests/unit/test_big.py", "tests/unit/test_small.py"]) == (
        "tests/unit/test_big.py",
        "tests/unit/test_big.py::test_a",
        "tests/unit/test_big.py::test_b",
        "tests/unit/test_small.py",
    )
    assert unit_path("tests/unit/test_big.py::test_a") == "tests/unit/test_big.py"
    assert unit_path("tests/unit/test_small.py") == "tests/unit/test_small.py"


def test_a_junit_case_of_a_carved_test_is_timed_apart_from_the_file_with_every_parameter_summed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The producer of the record, from the raw report as pytest writes it (a parameter id sits in
    the name in brackets). Delete this and the carved test's time lands in its file's, the file
    looks as heavy as it ever did, and the carve balances nothing."""
    _plant(tmp_path, "tests/unit/test_big.py")
    monkeypatch.setattr(test_timings, "CARVED_OUT", {"tests/unit/test_big.py": ("test_slow",)})
    report = _junit(
        tmp_path,
        [
            ("tests.unit.test_big", "test_slow[a]", 100.0),
            ("tests.unit.test_big", "test_slow[b]", 50.0),
            ("tests.unit.test_big", "test_quick", 3.0),
            ("tests.unit.test_big.TestQuick", "test_method", 2.0),
        ],
    )

    assert from_junit([report], tmp_path) == {
        "tests/unit/test_big.py::test_slow": 150.0,
        "tests/unit/test_big.py": 5.0,
    }


def test_the_rate_is_read_from_whole_files_only_and_a_carved_unit_with_no_record_shares_the_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A carved file's times do not add up to its lines, so they must not set the rate every new
    file is estimated at, and a carved unit nobody has timed is its file's lines shared by its
    parts. Delete this and one slow carved test makes every new test file look slow, or a carved
    unit weighs as much as the whole file."""
    monkeypatch.setattr(test_timings, "CARVED_OUT", {"tests/unit/test_big.py": ("test_slow",)})
    _plant(tmp_path, "tests/unit/test_big.py", lines=100)
    _plant(tmp_path, "tests/unit/test_plain.py", lines=10)
    _plant(tmp_path, "tests/unit/test_new.py", lines=10)
    _record(
        tmp_path,
        {"seconds": {"tests/unit/test_big.py::test_slow": 9999, "tests/unit/test_plain.py": 2}},
    )

    made = weights(
        ["tests/unit/test_big.py", "tests/unit/test_big.py::test_slow", "tests/unit/test_new.py"],
        tmp_path,
    )

    # 2 seconds over 10 lines is 200 milliseconds a line, and the carved time is not counted.
    assert made["tests/unit/test_new.py"] == 2000
    assert made["tests/unit/test_big.py::test_slow"] == 9_999_000
    assert made["tests/unit/test_big.py"] == 100 * 200 // 2


# ------------------------------------------------------------------ the split on timings
def test_a_slow_file_gets_a_shard_to_itself_and_the_rest_share_what_is_left() -> None:
    """The measured shape: one file costs about as much as all the others together. Delete this
    and the partition can be handed times it then ignores, which is the lines split again with a
    record kept for show."""
    made = {"slow.py": 3600, "a.py": 900, "b.py": 900, "c.py": 900, "d.py": 900}

    groups = partition(made, 2)

    assert ("slow.py",) in groups
    assert sorted(name for group in groups for name in group) == sorted(made)


def test_this_repositorys_split_covers_every_unit_exactly_once_on_the_recorded_weights() -> None:
    """The union and disjointness, over the checked-in record rather than lines. Delete this and a
    record whose keys the split mishandles (a path pytest does not collect, a stale name) could
    drop a file with the lines-only tests still green."""
    shards = [shard(number, 8) for number in range(1, 9)]
    listed = [name for one in shards for name in sorted(units_run(one))]

    assert sorted(listed) == sorted(units(collected()))


def test_a_shard_is_no_heavier_than_the_lightest_plus_the_heaviest_file() -> None:
    """The balance claim, in the unit the split now has (recorded milliseconds). Delete this and a
    record can be read for the weights and a partition written that ignores them, so the slowest
    shard is as slow as before."""
    files = collected()
    made = weights(files)
    totals = [sum(made[name] for name in one) for one in partition(made, 8)]

    assert max(totals) - min(totals) <= max(made.values())


# ------------------------------------------------------------------ one file too big to balance
def test_a_file_costing_more_than_a_shards_even_share_is_named_and_the_rest_are_not() -> None:
    """No assignment can balance around a file that alone outweighs a shard's share, because the
    shard holding it is the slowest however the rest is dealt. Delete this and the one thing a
    better split cannot fix goes unnamed until a pull request takes an hour again."""
    made = {"huge.py": 6000, "a.py": 500, "b.py": 500, "c.py": 500, "d.py": 500}

    assert oversized(made, 4) == {"huge.py": 6000}


def test_a_file_exactly_at_a_shards_even_share_is_not_oversized() -> None:
    """The boundary, held on both sides: a share is what a perfect split gives a shard, so a file
    equal to it is balanced. Delete this and `>` can become `>=`, and a refresh cries oversized
    over a file the split places without trouble."""
    made = {"a.py": 1000, "b.py": 1000, "c.py": 1000, "d.py": 1000}

    assert oversized(made, 4) == {}
    assert oversized({**made, "d.py": 1001}, 4) == {"d.py": 1001}


def test_a_refresh_says_which_file_cannot_be_balanced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The warning is the point of recording durations: it reaches the person who refreshed the
    record while the file can still be split. Delete this and the oversized check can exist and
    never be printed."""
    _plant(tmp_path, "tests/unit/test_big.py")
    _plant(tmp_path, "tests/unit/test_small.py")
    reports = tmp_path / "downloaded"
    reports.mkdir()
    _junit(
        reports,
        [("tests.unit.test_big", "test_a", 900.0), ("tests.unit.test_small", "test_b", 1.0)],
    ).rename(reports / "one.xml")

    assert main(["refresh", str(reports), "--shards", "8"], root=tmp_path) == 0
    said = capsys.readouterr().out
    assert "OVERSIZED tests/unit/test_big.py: 900 seconds" in said
    assert "test_small" not in said.split("wrote", 1)[1]


# ------------------------------------------------------------------ the checked-in record
def test_the_checked_in_record_names_only_files_that_exist_and_times_every_one_it_names() -> None:
    """The record is regenerated, never edited by hand, and a rename leaves a stale key. Delete
    this and the file drifts from the tree it describes until the rate is read over files that
    are not there."""
    recorded = load()

    assert recorded, "the record is empty, so the split is the lines split"
    assert [name for name in recorded if not (REPO / unit_path(name)).is_file()] == []
    assert all(value >= 0 for value in recorded.values())


def test_no_test_file_costs_more_than_one_shards_share_and_the_refresh_knows_how_many_shards() -> (
    None
):
    """**The guard against the regression this record exists for.** A file that alone outweighs a
    shard's even share makes that shard the wall clock of every pull request that selects it, and
    on 2026-10-14 one did, by about an hour, unseen for a day because lines cannot show it. The
    shard count the refresh warns against is held to the workflow's own matrix, so the warning and
    the split cannot disagree. Delete this and a test that grows past a shard's share is found by a
    person waiting on CI and not by the refresh that recorded it."""
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    shards = len(ci["jobs"]["tests"]["strategy"]["matrix"]["shard"])

    assert shards == test_timings.SHARDS
    assert oversized(weights(collected()), shards) == {}


def test_the_record_is_written_sorted_rounded_and_with_unix_line_endings(tmp_path: Path) -> None:
    """A file regenerated by two people must come out byte for byte the same, or the refresh is a
    diff of noise. Delete this and the order, the rounding or a CRLF depends on who ran it."""
    path = write({"tests/b.py": 2.345, "tests/a.py": 10.0}, tmp_path)

    raw = path.read_bytes()
    assert b"\r" not in raw
    assert list(json.loads(raw)["seconds"]) == ["tests/a.py", "tests/b.py"]
    assert json.loads(raw)["seconds"]["tests/b.py"] == 2.3


# ------------------------------------------------------------------ reading a real report
def _junit(tmp_path: Path, cases: list[tuple[str, str, float]]) -> Path:
    body = "".join(
        f'<testcase classname="{classname}" name="{name}" time="{seconds}"/>'
        for classname, name, seconds in cases
    )
    report = tmp_path / "report.xml"
    report.write_text(
        f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{body}</testsuite>'
        "</testsuites>",
        encoding="utf-8",
        newline="\n",
    )
    return report


def test_a_report_is_read_into_seconds_per_file_whether_a_test_sits_in_a_class_or_not(
    tmp_path: Path,
) -> None:
    """pytest writes `tests.unit.test_x` for a function and `tests.unit.test_x.TestY` for a
    method. Delete this and a class-based file reads as no time at all, and the slowest classes in
    the suite are weighed by their lines."""
    _plant(tmp_path, "tests/unit/test_x.py")
    _plant(tmp_path, "tests/unit/test_y.py")
    report = _junit(
        tmp_path,
        [
            ("tests.unit.test_x", "test_a", 1.5),
            ("tests.unit.test_x.TestY", "test_b", 2.0),
            ("tests.unit.test_y", "test_c", 4.0),
            ("tests.unit.not_a_file", "test_d", 9.0),
        ],
    )

    assert from_junit([report], tmp_path) == {
        "tests/unit/test_x.py": 3.5,
        "tests/unit/test_y.py": 4.0,
    }
    assert file_of("tests.unit.test_x.TestY", tmp_path) == "tests/unit/test_x.py"
    assert file_of("tests.unit.not_a_file", tmp_path) is None


def test_a_refresh_keeps_what_it_did_not_re_time_and_drops_what_is_gone(tmp_path: Path) -> None:
    """The nightly runs the whole suite and a pull request's report holds some of it. Delete this
    and a refresh from a partial report erases the files it did not run, and they fall back to
    lines until the next nightly."""
    _plant(tmp_path, "tests/unit/test_kept.py")
    _plant(tmp_path, "tests/unit/test_new_time.py")

    result = merged(
        {
            "tests/unit/test_kept.py": 5.0,
            "tests/unit/test_new_time.py": 1.0,
            "tests/unit/test_gone.py": 7.0,
        },
        {"tests/unit/test_new_time.py": 2.0},
        tmp_path,
    )

    assert result == {"tests/unit/test_kept.py": 5.0, "tests/unit/test_new_time.py": 2.0}


def test_refresh_rewrites_the_record_from_the_reports_under_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command a person runs after downloading the nightly's reports. Delete this and the
    command can write nothing, or write somewhere the shards do not read."""
    _plant(tmp_path, "tests/unit/test_x.py")
    reports = tmp_path / "downloaded"
    reports.mkdir()
    _junit(reports, [("tests.unit.test_x", "test_a", 12.0)]).rename(reports / "one.xml")

    assert main(["refresh", str(reports)], root=tmp_path) == 0
    assert json.loads((tmp_path / TIMINGS_PATH).read_text(encoding="utf-8"))["seconds"] == {
        "tests/unit/test_x.py": 12.0
    }
    assert "1 test file(s) timed" in capsys.readouterr().out


def test_refresh_refuses_a_directory_with_no_report_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive sibling above would pass a command that always writes. Delete this and a
    refresh pointed at the wrong directory writes an empty record over a good one."""
    empty = tmp_path / "none"
    empty.mkdir()

    assert main(["refresh", str(empty)], root=tmp_path) == 2
    assert "refused" in capsys.readouterr().err
    assert not (tmp_path / TIMINGS_PATH).exists()
