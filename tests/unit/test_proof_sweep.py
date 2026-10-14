"""The proof sweep closes what one complete install run proved, and says why it left the rest.

Every run here is a fixture: made-up rows in the shape `ops.acceptance_result` holds, read the way
the command reads the output of `ROWS_QUERY`. The rule under test is
`A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_ONE_COMPLETE_RUN`, which the owner set on 2026-10-14
in place of two runs, with the held list (`A_RESULT_ON_SOMETHING_MADE_UP_IS_HELD`), decided tasks
and closed tasks applied after it.

Task ids: M38.5.4
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import CARRIED_FORWARD_FROM
from brain.ops.proof_sweep import (
    A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_ONE_COMPLETE_RUN,
    HOLDS_PATH,
    ROWS_QUERY,
    SweepError,
    carried,
    closes_lines,
    evidence_row,
    holds_at,
    judge,
    main,
    proof_line,
    report,
    rows_from_lines,
    run_from_rows,
)

REPO = Path(__file__).resolve().parents[2]
OLD, NEW = "a" * 40, "b" * 40


def row(
    run: str,
    commit: str,
    at: str,
    check: str,
    leaves: str,
    outcome: str = "passed",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "run_id": run,
        "commit": commit,
        "occasion": "deploy",
        "check_name": check,
        "leaves": leaves,
        "outcome": outcome,
        "reason": reason,
        "started_at": at,
        "checked_at": at,
    }


def one_run(checks: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    """One run from (check, leaves, outcome) triples."""
    return [row("r2", NEW, "2999-01-01T02:00:00+00:00", *one) for one in checks]


def older_run(checks: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    """An older complete run, as a file printed by the query this replaced still holds."""
    return [row("r1", OLD, "2999-01-01T01:00:00+00:00", *one) for one in checks]


def sweep_of(rows: list[dict[str, Any]], **over: Any) -> Any:
    options: dict[str, Any] = {"closed": set(), "decided": set(), "holds": {}}
    options.update(over)
    return judge(run_from_rows(rows), **options)


def test_a_task_every_check_of_which_passed_on_the_complete_run_closes() -> None:
    """Two checks name M1.1.1 and both passed on the one run, so it closes on both checks, and
    M1.1.2 closes on the one check that names it. The rule's words say one complete run.

    Delete this and the positive half of the rule goes unwatched: a judge that closes nothing
    passes every refusal test below.
    """
    sweep = sweep_of(one_run([("one", "M1.1.1", "passed"), ("two", "M1.1.1 M1.1.2", "passed")]))

    assert dict(sweep.closes) == {"M1.1.1": ("one", "two"), "M1.1.2": ("two",)}
    assert "newest complete run" in A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_ONE_COMPLETE_RUN
    assert "two" not in A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_ONE_COMPLETE_RUN.split()


def test_one_run_is_enough_where_two_were_once_needed() -> None:
    """**The owner's decision of 2026-10-14.** A check seen on one run only closed nothing under
    the old rule, which waited for a second run. It closes now, on one complete clean run.

    Delete this and the sweep can go back to demanding a previous run that the owner no longer
    wants and the install no longer waits for."""
    sweep = sweep_of(one_run([("fresh", "M1.1.1", "passed")]))

    assert dict(sweep.closes) == {"M1.1.1": ("fresh",)}
    assert not hasattr(sweep, "one_run")
    assert not hasattr(sweep, "previous")


@pytest.mark.parametrize("outcome", ["not run", "failed"])
def test_one_check_that_did_not_pass_holds_every_task_it_names(outcome: str) -> None:
    """A second check naming the task did not pass on the run, so the task stays open and the
    blocker names that check and what it came to.

    Delete this and a task can close on the one check of two that happened to pass.
    """
    rows = one_run([("one", "M1.1.1", "passed"), ("two", "M1.1.1", outcome)])

    sweep = sweep_of(rows)

    assert "M1.1.1" not in sweep.closes
    assert [(check, came_to) for check, came_to, _ in sweep.blocked["M1.1.1"]] == [("two", outcome)]


def test_an_older_runs_failure_does_not_hold_what_the_newest_run_passed() -> None:
    """Only the newest complete run is judged. A rows file from the old query holds an older run
    too, and a check that failed there and passed on the newest is not a blocker.

    Delete this and the old two-run reading survives by accident, holding tasks on a run nobody
    is asking about."""
    rows = older_run([("x", "M1.1.1", "failed")]) + one_run([("x", "M1.1.1", "passed")])

    sweep = sweep_of(rows)

    assert dict(sweep.closes) == {"M1.1.1": ("x",)}
    assert sweep.blocked == {}
    assert sweep.run.commit == NEW


def test_a_held_a_decided_and_an_already_closed_task_are_not_claimed() -> None:
    """Each of the three is proved and none of them is on the Closes lines.

    Delete this and the sweep claims a pass on a made-up account, a task the owner decided
    against, or a task an earlier commit closed, and the count moves by nothing or by a lie.
    """
    passed = [
        ("a", "M1.1.1", "passed"),
        ("b", "M1.1.2", "passed"),
        ("c", "M1.1.3", "passed"),
        ("d", "M1.1.4", "passed"),
    ]
    sweep = sweep_of(
        one_run(passed),
        holds={"M1.1.1": "made up"},
        decided={"M1.1.2"},
        closed={"M1.1.3"},
    )
    assert dict(sweep.closes) == {"M1.1.4": ("d",)}
    assert dict(sweep.held) == {"M1.1.1": "made up"}
    assert sweep.already_closed == ("M1.1.3",)


def test_the_newest_run_is_the_later_one_whichever_order_the_rows_come_in() -> None:
    """Runs are told apart by when they started, not by the order the rows arrived in.

    Delete this and a query ordered differently judges the older run, and a task closes on a
    result the install has since replaced.
    """
    rows = older_run([("x", "M1.1.1", "passed")]) + one_run([("x", "M1.1.1", "passed")])

    assert run_from_rows(rows).commit == NEW
    assert run_from_rows(list(reversed(rows))).commit == NEW


def test_rows_of_no_run_at_all_are_refused() -> None:
    """With nothing to judge the sweep says so rather than closing nothing in silence. Delete
    this and an empty query result reads as a clean sweep that closed no task."""
    with pytest.raises(SweepError, match="one complete run is needed"):
        run_from_rows([])


def with_status(rows: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    """Rows as `ROWS_QUERY` prints them, each saying what its run's status is."""
    return [{**one, "run_status": status} for one in rows]


def test_a_resumed_run_is_read_as_one_run_whenever_its_rows_were_written() -> None:
    """A run the worker finished after a restart has rows written hours apart under one id, and
    that is one run: one commit, one start, every check once. Delete this and a run is read as two
    because its rows are far apart, or its late checks are lost, and no task closes on it."""
    early = [row("r2", NEW, "2999-01-01T02:00:00+00:00", "one", "M1.1.1")]
    late = [
        {**row("r2", NEW, "2999-01-01T02:00:00+00:00", "two", "M1.1.2"), "checked_at": "2999-01-02"}
    ]
    rows = with_status(early + late, "complete")

    run = run_from_rows(rows)

    assert (run.run_id, run.commit) == ("r2", NEW)
    assert sorted(run.results) == ["one", "two"]
    assert dict(sweep_of(rows).closes) == {"M1.1.1": ("one",), "M1.1.2": ("two",)}


def test_a_run_that_is_not_complete_is_ignored_whatever_it_says() -> None:
    """A run still going, or abandoned for a newer release, has rows and is not a run that was
    seen: the newest *complete* one is judged. Delete this and a half-written newest run, with
    most checks missing, is the one that decides which tasks close."""
    complete = one_run([("x", "M1.1.1", "passed")])
    partial = [row("r3", "c" * 40, "2999-01-01T03:00:00+00:00", "x", "M1.1.1", "failed")]
    gone = [row("r4", "d" * 40, "2999-01-01T04:00:00+00:00", "x", "M1.1.1", "failed")]
    rows = with_status(complete, "complete")
    rows += with_status(partial, "running") + with_status(gone, "abandoned")

    assert run_from_rows(rows).commit == NEW
    assert dict(sweep_of(rows).closes) == {"M1.1.1": ("x",)}


def test_only_runs_that_are_not_complete_leave_nothing_to_judge() -> None:
    """With a run that is still going and no complete one there is no run: refused, not judged on
    the incomplete one. Delete this and the sweep closes a task on a run nobody finished, which is
    the failure the single-run gate has no second run to catch."""
    rows = with_status(one_run([("x", "M1.1.1", "passed")]), "running")

    with pytest.raises(SweepError, match="one complete run is needed"):
        run_from_rows(rows)


def test_rows_with_no_status_are_complete_runs_as_every_run_was_before_the_status_existed() -> None:
    """A file printed by an older query, or a run written whole before `ops.acceptance_run`, has
    no status and is complete. Delete this and every saved file and every old run is ignored."""
    assert run_from_rows(one_run([("x", "M1.1.1", "passed")])).commit == NEW


def test_a_run_whose_rows_name_two_releases_is_refused() -> None:
    """A_RUN_NAMES_ONE_RELEASE. Results of two builds under one run id would close a task on a
    mixture, so the sweep stops and says so. Delete this and a resume that crossed releases goes
    through as a run."""
    rows = one_run([("x", "M1.1.1", "passed")])
    rows.append(row("r2", OLD, "2999-01-01T02:00:00+00:00", "y", "M1.1.2"))

    with pytest.raises(SweepError, match="more than one commit"):
        run_from_rows(rows)


def test_the_query_asks_for_one_complete_run_and_says_each_rows_status() -> None:
    """Structure of `ROWS_QUERY`: it joins the run record, filters the choice of runs to complete
    ones with a missing record counting as complete, takes the newest one only, and returns the
    status as a key. Delete this and the query can be edited back to two runs, or to every run,
    without the database test noticing on a machine that skips it."""
    query = " ".join(ROWS_QUERY.split())

    assert "left join ops.acceptance_run y on y.run_id = x.run_id" in query
    assert "where coalesce(y.status, 'complete') = 'complete'" in query
    assert "jsonb_build_object('run_status', coalesce(u.status, 'complete'))" in query
    assert query.index("coalesce(y.status") < query.index("limit 1")
    assert "limit 2" not in query


def test_closes_lines_group_by_module_in_the_work_breakdowns_order() -> None:
    """`M13.5.10` comes after `M13.5.9`, and each module has its own line.

    Delete this and the lines sort as text, which puts M13.5.10 before M13.5.2 and makes the
    commit unreadable against the tracker.
    """
    assert closes_lines(["M13.5.10", "M2.1.1", "M13.5.9", "M13.1.1"]) == [
        "Closes: M2.1.1",
        "Closes: M13.1.1, M13.5.9, M13.5.10",
    ]


def test_the_evidence_row_names_the_run_and_every_check() -> None:
    """The row the audit document keeps carries the task, the commit, the run's start and every
    check, and says the run was complete. It names no second run, because there is none.

    Delete this and a row can drop a check, or keep telling a reader that a second run saw the
    same."""
    sweep = sweep_of(one_run([("one", "M1.1.1", "passed"), ("two", "M1.1.1", "passed")]))

    text = evidence_row("M1.1.1", sweep.closes["M1.1.1"], sweep, "2999-01-01")

    cells = [cell.strip() for cell in text.strip("|").split("|")]
    assert cells[0] == "M1.1.1"
    assert re.search(r"run on bbbbbbb \(run at 02:00 UTC, complete, every registered", cells[2])
    assert "passed one, two" in cells[2]
    assert "the run on" not in cells[2]
    assert "passed the same" not in cells[2]


def test_the_proof_line_names_one_complete_run() -> None:
    """The `Proved-on-install:` line a commit carries says one run, complete with every registered
    check recorded. Delete this and the line can go back to naming two runs the sweep no longer
    reads, which a reader would take for evidence that was never gathered."""
    line = proof_line(sweep_of(one_run([("x", "M1.1.1", "passed")])))

    assert line.startswith(
        "Proved-on-install: the acceptance run at bbbbbbb (2999-01-01 02:00 UTC)"
    )
    assert "complete with every registered check recorded" in line
    assert " and " not in line


def test_a_check_carried_from_an_earlier_run_of_the_same_commit_is_reported_as_carried() -> None:
    """A repeat copies the passes of the run it repeats and says so in each reason. The sweep
    counts them and the report prints how many, so a person writing the commit sees which results
    were not run again. Delete this and a repeat is indistinguishable from a first run."""
    rows = one_run(
        [("one", "M1.1.1", "passed"), ("two", "M1.1.1", "passed"), ("three", "M1.1.2", "passed")]
    )
    rows[0]["reason"] = f"{CARRIED_FORWARD_FROM}00000000-0000-4000-8000-000000000001 of this commit"
    sweep = sweep_of(rows)

    assert carried(sweep.run) == ("one",)
    assert "checks carried forward from an earlier run of the same commit: 1" in report(sweep)


def test_a_run_with_nothing_carried_reports_none() -> None:
    """The positive sibling: a first run reports zero carried, not the count of its passes. Delete
    this and `carried` can claim every pass was carried forward."""
    sweep = sweep_of(one_run([("one", "M1.1.1", "passed")]))

    assert carried(sweep.run) == ()
    assert "checks carried forward from an earlier run of the same commit: 0" in report(sweep)


def test_rows_are_read_from_the_query_output_and_nothing_else() -> None:
    """Each JSON line is a row, and a header or footer line around them is skipped.

    Delete this and the command reads a psql header as a row, or reads nothing.
    """
    lines = [
        "?column?",
        json.dumps(row("r1", OLD, "2999-01-01T01:00:00+00:00", "x", "M1.1.1")),
        "(1 row)",
    ]
    assert [one["check_name"] for one in rows_from_lines(lines)] == ["x"]
    assert ROWS_QUERY.lower().startswith("select ")


def test_the_held_list_names_only_tasks_and_a_reason_for_each() -> None:
    """Every held entry is a task id with a reason, and the file names no install.

    Delete this and the list can hold a task with no reason, or carry a value that belongs to one
    install rather than the product.
    """
    held = holds_at(REPO / HOLDS_PATH)
    assert held
    for leaf, reason in held.items():
        assert re.fullmatch(r"M\d+(\.\d+)+", leaf), leaf
        assert len(reason) > 20, leaf


def test_the_command_prints_the_closes_and_appends_the_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """From a rows file of one run, the command prints the Closes and proof lines and appends
    evidence rows.

    Delete this and the command can stop writing the rows it exists to write, or start refusing a
    single run, with every function above still green.
    """
    monkeypatch.chdir(REPO)
    rows_file = tmp_path / "rows.jsonl"
    rows_file.write_text(
        "\n".join(json.dumps(one) for one in one_run([("x", "M999.1.1", "passed")])),
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.md"

    assert main(["--rows", str(rows_file), "--evidence", str(evidence)]) == 0

    printed = capsys.readouterr().out
    assert "Closes: M999.1.1" in printed.splitlines()
    assert any(
        line.startswith("Proved-on-install: the acceptance run at bbbbbbb")
        for line in printed.splitlines()
    )
    assert evidence.read_text(encoding="utf-8").startswith("| M999.1.1 | install and CI |")


def test_the_command_refuses_rows_of_no_complete_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rows file holding only a run that is still going is refused with a message and a failing
    exit, never a clean sweep that closed nothing. Delete this and the command exits 0 on a file
    it could not read as a run."""
    monkeypatch.chdir(REPO)
    rows_file = tmp_path / "rows.jsonl"
    rows_file.write_text(
        "\n".join(
            json.dumps(one) for one in with_status(one_run([("x", "M1.1.1", "passed")]), "running")
        ),
        encoding="utf-8",
    )

    assert main(["--rows", str(rows_file)]) == 1
    assert "one complete run is needed" in capsys.readouterr().err


@pytest.mark.needs_db
def test_the_newest_complete_run_is_read_from_a_real_database() -> None:
    """Three runs written to `ops.acceptance_result`, and `ROWS_QUERY` reads back the newest one.

    Delete this and the query can read the oldest runs, every run, or nothing, and only a sweep
    on an install would find out, by closing what a newer run disagreed with.
    """
    import asyncio

    from brain.db import normalise_database_url
    from brain.ops.proof_sweep import rows_from_database
    from tests.fixtures.scratch_postgres import database_url, modelled, sql

    if database_url() is None:
        pytest.skip("DATABASE_URL is unset; CI sets it")
    with modelled("brain_proof_sweep", ["ops.acceptance_result", "ops.acceptance_run"]) as url:
        for run, commit, hour in (
            ("00000000-0000-4000-8000-000000000001", "c" * 40, 1),
            ("00000000-0000-4000-8000-000000000002", OLD, 2),
            ("00000000-0000-4000-8000-000000000003", NEW, 3),
        ):
            sql(
                url,
                "INSERT INTO ops.acceptance_result (run_id, commit, occasion, check_name, leaves,"
                " outcome, reason, started_at, checked_at) VALUES (%s, %s, 'deploy', 'a_check',"
                " 'M1.1.1', 'passed', NULL, %s, %s)",
                run,
                commit,
                f"2999-01-01T0{hour}:00:00+00:00",
                f"2999-01-01T0{hour}:00:01+00:00",
            )
        rows = asyncio.run(rows_from_database(normalise_database_url(url)))
    assert run_from_rows(rows).commit == NEW
    assert {str(one["commit"]) for one in rows} == {NEW}


@pytest.mark.needs_db
def test_the_query_reads_the_newest_complete_run_and_never_a_running_or_abandoned_one() -> None:
    """Five runs: two complete with a record, one complete with none (written whole before the
    record existed), one running and one abandoned. `ROWS_QUERY` returns the newest *complete*
    one, however new the unfinished runs are, each row saying `complete`. Delete this and the
    newest unfinished run is judged, or an old run with no record is dropped."""
    import asyncio

    from brain.db import normalise_database_url
    from brain.ops.proof_sweep import rows_from_database
    from tests.fixtures.scratch_postgres import database_url, modelled, sql

    if database_url() is None:
        pytest.skip("DATABASE_URL is unset; CI sets it")
    runs = (
        ("00000000-0000-4000-8000-000000000001", "1" * 40, 1, "complete"),
        ("00000000-0000-4000-8000-000000000002", "2" * 40, 2, None),
        ("00000000-0000-4000-8000-000000000003", "3" * 40, 3, "complete"),
        ("00000000-0000-4000-8000-000000000004", "4" * 40, 4, "running"),
        ("00000000-0000-4000-8000-000000000005", "5" * 40, 5, "abandoned"),
    )
    with modelled(
        "brain_proof_sweep_status", ["ops.acceptance_result", "ops.acceptance_run"]
    ) as url:
        for run, commit, hour, status in runs:
            started = f"2999-01-01T0{hour}:00:00+00:00"
            sql(
                url,
                "INSERT INTO ops.acceptance_result (run_id, commit, occasion, check_name, leaves,"
                " outcome, reason, started_at, checked_at) VALUES (%s, %s, 'deploy', 'a_check',"
                " 'M1.1.1', 'passed', NULL, %s, %s)",
                run,
                commit,
                started,
                started,
            )
            if status is not None:
                sql(
                    url,
                    "INSERT INTO ops.acceptance_run (run_id, commit, occasion, status, started_at,"
                    " ended_at) VALUES (%s, %s, 'deploy', %s, %s, %s)",
                    run,
                    commit,
                    status,
                    started,
                    None if status == "running" else started,
                )
        rows = asyncio.run(rows_from_database(normalise_database_url(url)))
    assert run_from_rows(rows).commit == "3" * 40
    assert {str(one["run_status"]) for one in rows} == {"complete"}
    assert len(rows) == 1
