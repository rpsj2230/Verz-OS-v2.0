"""The peak runs listing: how many it lists, and how a lane no objective covers is shown.

The database half is the install check in `tests/unit/test_acceptance_checks_load_runs.py`; this is
the part that needs no database.

Task ids: M36.2.4.3
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from brain import load_run_routes
from brain.load_run_routes import RUNS_SHOWN, load_runs, view_of
from brain.ops.load_run_store import LaneFigures, RunRecord
from brain.ops.reliability import ReliabilityError

AT = datetime(2999, 1, 1, tzinfo=UTC)


def record(number: int, *lanes: LaneFigures) -> RunRecord:
    return RunRecord(
        run_id=f"r{number}",
        commit="abc1234",
        profile="check",
        started_at=AT - timedelta(hours=number),
        seconds_run=1.0,
        stated_arrivals_per_second=2.0,
        stated_in_flight=16.0,
        arrivals_per_second=40.0,
        planned=80,
        sent=80,
        not_sent=0,
        most_in_flight=9,
        people=1,
        at_stated_peak=False,
        held=True,
        interactive_shed=0,
        lanes=lanes or (LaneFigures("fast", 40, 12.0, 1.0, 0),),
        findings=("the fast lane held",),
    )


def asked_by_a_reader(monkeypatch: pytest.MonkeyPatch, kept: list[RunRecord]) -> Any:
    class Sessions:
        def __call__(self) -> Sessions:
            return self

        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    async def read(_session: object) -> tuple[RunRecord, ...]:
        return tuple(kept)

    monkeypatch.setattr(load_run_routes, "read_runs", read)
    monkeypatch.setattr(load_run_routes, "sessions_of", lambda _request: Sessions())
    monkeypatch.setattr(load_run_routes, "may_read_service_levels", lambda *a, **k: True)
    return SimpleNamespace(reach=object(), now=AT)


def test_no_more_than_the_newest_twenty_runs_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twenty-five kept runs list twenty, in the order the store gave them. Delete this and the
    listing grows with the install's age."""
    kept = [record(number) for number in range(25)]
    shown = asyncio.run(load_runs(object(), asked_by_a_reader(monkeypatch, kept)))  # type: ignore[arg-type]
    assert RUNS_SHOWN == 20
    assert [one.run_id for one in shown.runs] == [f"r{number}" for number in range(20)]


def test_a_lane_with_no_objective_is_shown_with_none_and_the_run_is_still_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lane the objectives table does not cover, because it is unknown or because the table
    refuses it, is drawn with no objective and does not drop the run. Delete this and one lane
    nobody declared an objective for hides a whole run."""
    odd = LaneFigures("zzz", 3, None, None, 0)
    unknown = view_of(record(1, odd))
    assert (unknown.lanes[0].objective_p95_ms, unknown.lanes[0].objective_success_rate) == (
        None,
        None,
    )

    def refused(*args: Any, **kwargs: Any) -> Any:
        raise ReliabilityError("no objective declares that lane")

    monkeypatch.setattr(load_run_routes, "lane_objective", refused)
    declared = view_of(record(2, LaneFigures("fast", 40, 12.0, 1.0, 0)))
    assert declared.lanes[0].objective_p95_ms is None and declared.run_id == "r2"


def test_a_lane_is_shown_beside_its_own_declared_objective() -> None:
    """The fast lane's 95th percentile is 500 milliseconds and the answer lane's is eight seconds,
    written here as the owner stated them. Delete this and a lane can be listed against another's
    promise."""
    shown = view_of(
        record(1, LaneFigures("fast", 40, 12.0, 1.0, 0), LaneFigures("answer", 40, 3000.0, 1.0, 0))
    )
    assert {one.lane: one.objective_p95_ms for one in shown.lanes} == {"fast": 500, "answer": 8000}
