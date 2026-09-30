"""A trial read of the staff source: when it is owed, what the worker does, and the row it asks by.

`brain.ops.staff_trial` holds the rule between the Staff sources screen and the worker. The rule is
tested as a function of three instants; the worker's pass with its two reads and its thread
replaced, so what is under test is whether a read is started and not the read itself (that is
`tests/unit/test_staff_sync_run.py`); and the request row and the newest run's start against a real
PostgreSQL, which CI provides and a laptop without `DATABASE_URL` skips.

Task ids: M1.6.11, M27.7.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.identity.staff_roster import RunOutcome
from brain.ops import staff_trial
from brain.ops.staff_sync_run import StaffSyncRun
from brain.ops.staff_sync_store import RunRecord, read_last_started, run_row
from brain.ops.staff_trial import (
    REQUEST_KEY,
    TRIAL_ANSWERED_WITHIN,
    TrialRequestError,
    request_trial,
    tick_staff_trial,
    trial_owed,
    trial_requested,
    waiting,
)
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.scratch_postgres import modelled, run

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
PRESSED = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)
A_MINUTE = timedelta(minutes=1)


# ------------------------------------------------------------------------------ the rule
def test_a_trial_is_owed_once_asked_until_a_run_starts_at_or_after_the_press() -> None:
    """Delete this and a trial is made on every tick, or never, and the button either spends the
    company's directory allowance every minute or does nothing."""
    assert trial_owed(PRESSED, None, now=PRESSED + A_MINUTE)
    assert trial_owed(PRESSED, PRESSED - A_MINUTE, now=PRESSED + A_MINUTE)
    assert not trial_owed(PRESSED, PRESSED, now=PRESSED + A_MINUTE)
    assert not trial_owed(PRESSED, PRESSED + A_MINUTE, now=PRESSED + A_MINUTE)


def test_nothing_asked_a_press_in_the_future_and_a_stale_press_are_owed_nothing() -> None:
    """A press after the tick began waits for the next tick, and one no run could answer in
    `TRIAL_ANSWERED_WITHIN` is let go. Delete this and a source switched to none leaves a request
    that starts a thread on every tick for ever."""
    assert not trial_owed(None, None, now=PRESSED)
    assert not trial_owed(PRESSED, None, now=PRESSED - A_MINUTE)
    assert not trial_owed(PRESSED, None, now=PRESSED + TRIAL_ANSWERED_WITHIN + A_MINUTE)
    assert trial_owed(PRESSED, None, now=PRESSED + TRIAL_ANSWERED_WITHIN)


def test_a_request_is_let_go_well_after_the_worker_has_had_its_chances() -> None:
    """The worker ticks every minute, so the window has to hold several ticks. Held against the
    tick rather than against itself. Delete this and the window can shrink below one tick, and a
    press is let go before any worker could have answered it."""
    from brain.ops.schedule import TICK

    assert TRIAL_ANSWERED_WITHIN >= 5 * TICK


def test_the_screen_says_waiting_for_a_press_the_worker_has_not_reached_yet() -> None:
    """`waiting` is what the screen shows, and a press newer than the last tick is still waiting.
    Delete this and the screen says nothing is waiting in the second after somebody pressed."""
    assert waiting(PRESSED, None, now=PRESSED)
    assert waiting(PRESSED, PRESSED - A_MINUTE, now=PRESSED)
    assert not waiting(PRESSED, PRESSED, now=PRESSED + A_MINUTE)
    assert not waiting(None, None, now=PRESSED)
    assert not waiting(PRESSED, None, now=PRESSED + TRIAL_ANSWERED_WITHIN + A_MINUTE)


def test_a_request_at_a_naive_instant_is_refused_before_it_is_written() -> None:
    """Delete this and a press is answered early or late by the host's offset."""
    with pytest.raises(TrialRequestError):
        asyncio.run(request_trial(object(), at=PRESSED.replace(tzinfo=None), by="u_admin"))  # type: ignore[arg-type]


# ------------------------------------------------------------------------ the worker's pass
class NoSession:
    async def __aenter__(self) -> NoSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _pass(
    monkeypatch: pytest.MonkeyPatch, requested: datetime | None, started: datetime | None
) -> tuple[StaffSyncRun | None, list[datetime]]:
    made: list[datetime] = []

    async def asked(_: object) -> datetime | None:
        return requested

    async def last(_: object) -> datetime | None:
        return started

    def trial_in_thread(url: str, now: datetime) -> StaffSyncRun:
        made.append(now)
        return StaffSyncRun(outcome=RunOutcome.TRIED, detail="read")

    monkeypatch.setattr(staff_trial, "trial_requested", asked)
    monkeypatch.setattr(staff_trial, "read_last_started", last)
    monkeypatch.setattr(staff_trial, "_trial_in_thread", trial_in_thread)
    now = PRESSED + A_MINUTE
    ran = asyncio.run(tick_staff_trial(lambda: NoSession(), now=now, database_url="unused"))  # type: ignore[arg-type]
    return ran, made


def test_the_worker_makes_an_owed_trial_once_at_the_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and the pass can read the request and never start the read."""
    ran, made = _pass(monkeypatch, PRESSED, None)

    assert made == [PRESSED + A_MINUTE]
    assert ran is not None
    assert ran.outcome is RunOutcome.TRIED


def test_the_worker_starts_nothing_when_no_trial_is_owed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sibling. Delete this and a pass that reads the directory on every tick passes the test
    above."""
    assert _pass(monkeypatch, None, None) == (None, [])
    assert _pass(monkeypatch, PRESSED, PRESSED) == (None, [])


# ------------------------------------------------------------------------ against a table
TABLES: tuple[str, ...] = ("ops.setting", "auth.staff_sync_run")


@pytest.fixture
def url() -> Iterator[str]:
    with modelled("brain_test_staff_trial", TABLES) as scratch:
        yield scratch


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


async def _ask_then_read(sessions: async_sessionmaker[AsyncSession]) -> tuple[Any, ...]:
    async with sessions() as session, session.begin():
        before = await trial_requested(session)
        await request_trial(session, at=PRESSED, by="u_admin")
    async with sessions() as session, session.begin():
        await request_trial(session, at=PRESSED + A_MINUTE, by="u_admin")
    async with sessions() as session, session.begin():
        after = await trial_requested(session)
        nothing_ran = await read_last_started(session)
        record = RunRecord(
            source="lark",
            started_at=PRESSED + 2 * A_MINUTE,
            finished_at=PRESSED + 3 * A_MINUTE,
            outcome=RunOutcome.TRIED,
            detail="Trial read.",
            report=("Read 3 people; 3 placed in a department.",),
        )
        await session.execute(run_row(record))
    async with sessions() as session, session.begin():
        started = await read_last_started(session)
    return before, after, nothing_ran, started


def test_a_press_is_one_row_whose_second_press_moves_the_instant_and_a_run_answers_it(
    url: str,
) -> None:
    """A request is one key in `ops.setting`, pressed twice is the newer instant, and the newest
    run's start is read back for the rule above. Delete this and the request or the start could be
    read from a column nobody writes, with every stand-in test green."""
    before, after, nothing_ran, started = through(url, _ask_then_read)

    assert before is None
    assert after == PRESSED + A_MINUTE
    assert nothing_ran is None
    assert started == PRESSED + 2 * A_MINUTE
    assert not trial_owed(after, started, now=PRESSED + 3 * A_MINUTE)
    assert REQUEST_KEY == "staff_source.trial_requested"
