"""The proof sweep closes exactly what two install runs proved, and says why it left the rest.

Every run here is a fixture: two runs of made-up rows in the shape `ops.acceptance_result` holds,
read the way the command reads the output of `ROWS_QUERY`. The rule under test is
`A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_TWO_RUNS`, with the held list
(`A_RESULT_ON_SOMETHING_MADE_UP_IS_HELD`), decided tasks and closed tasks applied after it.

Task ids: none
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from brain.ops.proof_sweep import (
    A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_TWO_RUNS,
    HOLDS_PATH,
    ROWS_QUERY,
    SweepError,
    closes_lines,
    evidence_row,
    holds_at,
    judge,
    main,
    rows_from_lines,
    runs_from_rows,
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


def fixture(
    latest: list[tuple[str, str, str]], previous: list[tuple[str, str, str]]
) -> list[dict[str, Any]]:
    """Two runs from (check, leaves, outcome) triples, the newer one second in the rows."""
    rows = [row("r1", OLD, "2999-01-01T01:00:00+00:00", *one) for one in previous]
    rows += [row("r2", NEW, "2999-01-01T02:00:00+00:00", *one) for one in latest]
    return rows


def sweep_of(rows: list[dict[str, Any]], **over: Any) -> Any:
    latest, previous = runs_from_rows(rows)
    options: dict[str, Any] = {"closed": set(), "decided": set(), "holds": {}}
    options.update(over)
    return judge(latest, previous, **options)


def test_a_task_every_check_of_which_passed_on_both_runs_closes() -> None:
    """Two checks name M1.1.1 and both passed twice, so it closes on both checks.

    Delete this and the positive half of the rule goes unwatched: a judge that closes nothing
    passes every refusal test below.
    """
    rows = fixture(
        [("one", "M1.1.1", "passed"), ("two", "M1.1.1 M1.1.2", "passed")],
        [("one", "M1.1.1", "passed"), ("two", "M1.1.1 M1.1.2", "passed")],
    )
    sweep = sweep_of(rows)
    assert dict(sweep.closes) == {"M1.1.1": ("one", "two"), "M1.1.2": ("two",)}
    assert (
        "both of the install's two newest runs"
        in A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_TWO_RUNS
    )


@pytest.mark.parametrize(
    ("latest", "previous"),
    [
        ("not run", "passed"),
        ("passed", "not run"),
        ("failed", "passed"),
        ("passed", "failed"),
    ],
)
def test_one_check_that_did_not_pass_on_either_run_holds_every_task_it_names(
    latest: str, previous: str
) -> None:
    """A second check naming the task did not pass on one of the runs, so the task stays open.

    Delete this and a task can close on the one check of two that happened to pass.
    """
    rows = fixture(
        [("one", "M1.1.1", "passed"), ("two", "M1.1.1", latest)],
        [("one", "M1.1.1", "passed"), ("two", "M1.1.1", previous)],
    )
    sweep = sweep_of(rows)
    assert "M1.1.1" not in sweep.closes
    assert [check for check, _, _ in sweep.blocked["M1.1.1"]] == ["two"]


def test_a_check_seen_only_on_the_newest_run_waits_for_a_second() -> None:
    """A check new on the newest run has been seen once, so its task waits.

    Delete this and a task closes on a single run, the case the rule exists to refuse.
    """
    rows = fixture(
        [("one", "M1.1.1", "passed"), ("new", "M1.1.1", "passed")], [("one", "M1.1.1", "passed")]
    )
    sweep = sweep_of(rows)
    assert "M1.1.1" not in sweep.closes
    assert dict(sweep.one_run) == {"M1.1.1": ("new",)}


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
        fixture(passed, passed),
        holds={"M1.1.1": "made up"},
        decided={"M1.1.2"},
        closed={"M1.1.3"},
    )
    assert dict(sweep.closes) == {"M1.1.4": ("d",)}
    assert dict(sweep.held) == {"M1.1.1": "made up"}
    assert sweep.already_closed == ("M1.1.3",)


def test_the_newest_run_is_the_later_one_whichever_order_the_rows_come_in() -> None:
    """Runs are told apart by when they started, not by the order the rows arrived in.

    Delete this and a query ordered differently swaps the runs, and a check new on the newest
    run reads as one the newest run dropped.
    """
    rows = fixture([("x", "M1.1.1", "passed")], [("x", "M1.1.1", "passed")])
    latest, previous = runs_from_rows(list(reversed(rows)))
    assert (latest.commit, previous.commit) == (NEW, OLD)


def test_fewer_than_two_runs_is_refused() -> None:
    """One run cannot be judged against the rule, so it is refused rather than half-judged."""
    with pytest.raises(SweepError, match="two runs"):
        runs_from_rows([row("r1", OLD, "2999-01-01T01:00:00+00:00", "x", "M1.1.1")])


def test_closes_lines_group_by_module_in_the_work_breakdowns_order() -> None:
    """`M13.5.10` comes after `M13.5.9`, and each module has its own line.

    Delete this and the lines sort as text, which puts M13.5.10 before M13.5.2 and makes the
    commit unreadable against the tracker.
    """
    assert closes_lines(["M13.5.10", "M2.1.1", "M13.5.9", "M13.1.1"]) == [
        "Closes: M2.1.1",
        "Closes: M13.1.1, M13.5.9, M13.5.10",
    ]


def test_the_evidence_row_names_both_runs_and_every_check() -> None:
    """The row the audit document keeps carries the task, both commits and every check.

    Delete this and a row can drop the older run, which is the half that makes it proof.
    """
    rows = fixture(
        [("one", "M1.1.1", "passed"), ("two", "M1.1.1", "passed")],
        [("one", "M1.1.1", "passed"), ("two", "M1.1.1", "passed")],
    )
    sweep = sweep_of(rows)
    text = evidence_row("M1.1.1", sweep.closes["M1.1.1"], sweep, "2999-01-01")
    cells = [cell.strip() for cell in text.strip("|").split("|")]
    assert cells[0] == "M1.1.1"
    assert re.search(r"run on bbbbbbb \(run at 02:00 UTC\) passed one, two", cells[2])
    assert "the run on aaaaaaa (01:00 UTC) passed the same" in cells[2]


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
    """From a rows file, the command prints the Closes and proof lines and appends evidence rows.

    Delete this and the command can stop writing the rows it exists to write, with every function
    above still green.
    """
    monkeypatch.chdir(REPO)
    passed = [("x", "M999.1.1", "passed")]
    rows_file = tmp_path / "rows.jsonl"
    rows_file.write_text(
        "\n".join(json.dumps(one) for one in fixture(passed, passed)), encoding="utf-8"
    )
    evidence = tmp_path / "evidence.md"
    assert main(["--rows", str(rows_file), "--evidence", str(evidence)]) == 0
    printed = capsys.readouterr().out
    assert "Closes: M999.1.1" in printed.splitlines()
    assert any(
        line.startswith("Proved-on-install: acceptance runs at bbbbbbb")
        for line in printed.splitlines()
    )
    assert evidence.read_text(encoding="utf-8").startswith("| M999.1.1 | install and CI |")


@pytest.mark.needs_db
def test_the_two_newest_runs_are_read_from_a_real_database() -> None:
    """Three runs written to `ops.acceptance_result`, and `ROWS_QUERY` reads back the newest two.

    Delete this and the query can read the oldest runs, every run, or nothing, and only a sweep
    on an install would find out, by closing what a newer run disagreed with.
    """
    import asyncio

    from brain.db import normalise_database_url
    from brain.ops.proof_sweep import rows_from_database
    from tests.fixtures.scratch_postgres import database_url, modelled, sql

    if database_url() is None:
        pytest.skip("DATABASE_URL is unset; CI sets it")
    with modelled("brain_proof_sweep", ["ops.acceptance_result"]) as url:
        for run, commit, hour in (
            ("00000000-0000-4000-8000-000000000001", "c" * 40, 1),
            ("00000000-0000-4000-8000-000000000002", OLD, 2),
            ("00000000-0000-4000-8000-000000000003", NEW, 3),
        ):
            sql(
                url,
                "INSERT INTO ops.acceptance_result (run_id, commit, occasion, check_name, leaves,"
                " outcome, reason, started_at, checked_at) VALUES (%s, %s, 'deploy', 'x',"
                " 'M1.1.1', 'passed', NULL, %s, %s)",
                run,
                commit,
                f"2999-01-01T0{hour}:00:00+00:00",
                f"2999-01-01T0{hour}:00:01+00:00",
            )
        rows = asyncio.run(rows_from_database(normalise_database_url(url)))
    latest, previous = runs_from_rows(rows)
    assert (latest.commit, previous.commit) == (NEW, OLD)
    assert {str(one["commit"]) for one in rows} == {NEW, OLD}
