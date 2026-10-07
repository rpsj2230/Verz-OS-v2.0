"""The install checks for operating the install from the console, each passing on PostgreSQL at
head and each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes and leaves nothing, the run rows and the connection included. Then each is shown failing:
Live runs dropping what runs or showing it to anybody, a pause that is not written, a reader of the
queue allowed to press, the Tools tab open to anybody or a switch that stops nothing, Connectors
open to anybody or listing only what is connected, and a test of a source that nothing records or
that anybody may ask for.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.2.2, M27.8.13, M27.15.47, M27.15.7, M27.15.36, M27.15.39
Task ids: M27.2.4, M27.12.2, M27.15.8
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_operations_console_2 import (
    A_SOURCE_IS_CONNECTED_HERE_ALREADY,
    THE_RUN_RECORD_IS_NOT_WRITABLE_HERE,
    a_job,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_operations_console_2"
RUNS = "what_runs_and_what_waits_is_shown_to_its_readers"
JOBS = "a_job_is_paused_run_and_resumed_and_lists_its_runs"
TOOLS = "every_tool_is_listed_and_one_switched_off_is_refused"
SOURCE = "a_connected_source_is_kept_apart_and_exported_without_a_key"
PROBE = "a_source_test_is_one_call_whose_health_is_shown"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Five checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (RUNS, ("M27.2.2",)),
        (JOBS, ("M27.8.13", "M27.15.47")),
        (TOOLS, ("M27.15.7", "M27.15.36")),
        (SOURCE, ("M27.15.39",)),
        (PROBE, ("M27.15.8", "M27.12.2", "M27.2.4")),
    ]


def test_the_operations_console_2_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [RUNS, JOBS, TOOLS, SOURCE, PROBE]


def test_the_job_the_checks_press_deletes_nothing_and_the_scheduler_may_run_it() -> None:
    """Held against the scheduler's own lists. Delete this and the jobs check can pause, and ask
    for a run of, the one job that deletes, or one the scheduler never starts."""
    from brain.ops.schedule import DESTRUCTIVE, schedulable

    job = a_job()
    assert job in schedulable() and job.name not in DESTRUCTIVE


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why a check was not run is cut short on the Install page."""
    assert len(A_SOURCE_IS_CONNECTED_HERE_ALREADY) <= REASON_CHARS
    assert len(THE_RUN_RECORD_IS_NOT_WRITABLE_HERE) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_ops_console_2") as url:
        yield url


def run_ops(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


#: What these checks write beyond the suite's list.
ALSO_WRITTEN = ("ops.control_run", "ops.connector_connection", "ops.connector_sync")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_every_operations_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All five pass and nothing a check wrote is left: no
    run row, no pause, no tool stop, no connection and no test. Delete this and a check that can
    never pass on a real schema, or one that leaves a job paused, reaches the owner's server."""
    before = _counts(install)
    outcomes = run_ops(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 5
    assert _counts(install) == before


@pytest.mark.needs_db
def test_the_jobs_check_passes_where_the_switch_was_already_on() -> None:
    """**An install that has used the screen has the switch on already.** Switching it on again
    changes nothing and writes no entry, so the trail holds one change fewer than on the empty
    database every other test uses. The check failed on the owner's install for exactly that
    ("a change to a job from the console is not in the audit trail") and passed in CI. Delete this
    and the check goes red on every install whose owner has switched pausing on, which is the one
    that matters."""
    from brain.ops.features import SCHEDULE_CONTROL, switch
    from tests.unit.test_budget_stop_store import _as_app

    with at_head("brain_acceptance_ops_console_2_on") as url:

        async def switched_on(sessions: Any) -> None:
            async with sessions() as session, session.begin():
                await switch(session, SCHEDULE_CONTROL, on=True, by="u_owner")

        _as_app(url, switched_on)
        assert run_ops(url, JOBS) == {JOBS: (PASSED, "")}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_ops(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_live_runs_dropping_or_showing_everything_fails_the_runs_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live runs listing nothing running, then listing it to anybody. Delete this and M27.2.2
    closes on a screen that shows nothing, or everything to everybody."""
    from brain import operate_routes
    from brain.console import operate

    with monkeypatch.context() as patched:
        patched.setattr(operate_routes, "unattended_running", lambda *args: ())
        assert "did not list a run" in _failed(install, RUNS)
    monkeypatch.setattr(operate, "may_watch_unattended", lambda *args, **kwargs: True)
    assert "may not see running work" in _failed(install, RUNS)


@pytest.mark.needs_db
def test_a_pause_not_written_or_pressed_by_a_reader_fails_the_jobs_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pause that writes nothing, then the schedule's authority given to every reader. Delete
    this and M27.8.13 closes on buttons that change nothing, or that anybody may press."""
    from brain import jobs_routes

    async def nothing(session: Any, name: str, *, paused: bool, by: str) -> None:
        return None

    with monkeypatch.context() as patched:
        patched.setattr(jobs_routes, "set_paused", nothing)
        assert "held as paused" in _failed(install, JOBS)
    monkeypatch.setattr(jobs_routes, "may_control", lambda reach, now: True)
    assert "reader of the queue paused" in _failed(install, JOBS)


@pytest.mark.needs_db
def test_a_tools_tab_open_to_anybody_or_a_switch_that_stops_nothing_fails_the_tools_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tab answering a person with no authority, then a switch that writes no stop. Delete
    this and M27.15.7 closes on a switch that reaches no catalogue."""
    from brain import tool_routes

    with monkeypatch.context() as patched:
        patched.setattr(tool_routes, "may_open", lambda reach, now: True)
        assert "without the authority" in _failed(install, TOOLS)

    async def nothing(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(tool_routes, "switch_off", nothing)
    assert "off for the install" in _failed(install, TOOLS)


@pytest.mark.needs_db
def test_connectors_open_to_anybody_or_listing_only_the_connected_fails_the_source_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen's read removed, then a list keeping only what is connected. Delete this and
    M27.15.39's check passes a screen open to anybody, or one that cannot tell available from
    connected."""
    from brain import connector_routes
    from brain.console.connector_detail import SourceStatus
    from brain.console.connector_detail import source_rows as real

    with monkeypatch.context() as patched:
        patched.setattr(connector_routes, "_permitted", lambda reach, now: None)
        assert "may not open Connectors" in _failed(install, SOURCE)

    def connected_only(**kwargs: Any) -> Any:
        return tuple(one for one in real(**kwargs) if one.status is not SourceStatus.NOT_CONNECTED)

    monkeypatch.setattr(connector_routes, "source_rows", connected_only)
    assert "available to connect" in _failed(install, SOURCE)


@pytest.mark.needs_db
def test_a_test_nothing_records_or_anybody_asks_for_fails_the_probe_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker's pass making no test, then the authority given to anybody. Delete this and
    M27.15.8 closes on a button nothing answers, or that anybody may press."""
    from brain import connector_routes
    from brain.ops import connector_probe_run

    async def nothing(**kwargs: Any) -> Any:
        return None

    with monkeypatch.context() as patched:
        patched.setattr(connector_probe_run, "probe_on", nothing)
        assert "other than one call" in _failed(install, PROBE)
    monkeypatch.setattr(connector_routes, "may_connect_source", lambda *args: True)
    assert "without the authority" in _failed(install, PROBE)
