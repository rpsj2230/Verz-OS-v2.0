"""Testing a connection, the worker half: asked for through the store, made once, kept nowhere.

A PostgreSQL database of the test's own holds the connections, the attempts, the projection and
`ops.setting`; a source is connected through the store the Connectors route writes with; a test is
asked for through `brain.ops.connector_sync_store.StoredProbes`, the route's own store; and the
worker's pass is `brain.ops.connector_probe_run.probe_on` against the recorded Xero answers in
`tests/fixtures/cassettes/`, replayed by the stand-in caller `test_connector_sync_run` uses. The
rule half is `tests/unit/test_connector_probe.py`.

**What a test keeps is asserted over the database, not over a return value.** A test that answered
leaves one attempt row and nothing in `proj.record`, and the key is looked for in every row it left.

No test here calls a live API. The key is a sentinel, the call is a replay, and the address is the
one a stand-in resolver hands out.

Task ids: M27.15.8
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops import connector_probe_run, worker
from brain.ops.connector_probe import PROBE_LOCK, PROBE_SPACING, REQUEST_NAMESPACE
from brain.ops.connector_probe_run import ProbeRun, probe_on, tick_probes
from brain.ops.connector_sync import (
    KEY_DECLINED,
    NO_KEY,
    PROBE_ANSWERED,
    PROBE_NOT_SENT_WHILE_WAITING,
    PROBE_REFUSED_FOR_NOW,
    ProbeVerdict,
)
from brain.ops.connector_sync_store import StoredProbes, read_states
from brain.ops.schedule_store import take_the_lock
from brain.ops.worker import ControlTick
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import add_modelled, migrate, run, sql
from tests.unit.test_connector_sync_run import (
    KEY,
    NOW,
    Keys,
    NoKeys,
    Replay,
    Resolver,
    a_database,
    answer_for,
    attempts,
    connect,
    leases,
    projected,
    sync,
    through,
)
from tests.unit.test_credential_writes import entries
from tests.unit.test_tables import migration_module

#: The revision `0142` sits on, read from the migration so re-pointing it at landing moves this too.
DOWN_REVISION: Final = str(
    migration_module(
        Path(__file__).parents[2] / "migrations/versions/0142_connector_probe_outcome.py"
    ).down_revision
)

#: Who presses Test connection in these tests.
ADMIN: Final = "u_admin"


@contextmanager
def a_probe_database(name: str) -> Iterator[str]:
    """`test_connector_sync_run`'s database, with `ops.setting` for the requests."""
    with a_database(name) as url:
        add_modelled(url, ("ops.setting",))
        yield url


def ask(url: str, at: datetime = NOW, connector: str = "xero") -> None:
    """Press Test connection, through the store the route writes with."""
    through(
        url,
        lambda sessions: StoredProbes(sessions).ask(
            connector, at=at, by=ADMIN, trace_id="t-probe", ent_hash="0" * 32
        ),
    )


def status(url: str) -> Any:
    return through(url, lambda sessions: StoredProbes(sessions).status("xero"))


def probe(url: str, caller: Replay, *, at: datetime = NOW, keys: Any = None) -> ProbeRun:
    clock = iter(at + timedelta(seconds=n) for n in range(10_000))

    async def work(sessions: async_sessionmaker[AsyncSession]) -> ProbeRun:
        return await probe_on(
            sessions=sessions,
            now=at,
            keys=Keys() if keys is None else keys,
            caller=caller,
            resolver=Resolver(),
            clock=lambda: next(clock),
        )

    return through(url, work)


# ------------------------------------------------------------------------------ the proof


@pytest.mark.needs_db
def test_a_test_asked_for_is_made_once_with_the_workers_key_and_keeps_nothing() -> None:
    """**The leaf, end to end.** A press writes a request, the worker's pass makes one call with the
    key it leased, the answer is interpreted and dropped, one attempt row says what was found, and
    the request is answered, so the next pass calls nothing.

    Delete this and a test could write the source's records into the projection, leave the request
    waiting for ever, or be made on every pass after one press."""
    with a_probe_database("brain_connector_probe_answered") as url:
        connect(url)
        ask(url)
        waiting = status(url)
        caller = Replay([answer_for("XERO-200-invoices")])
        first = probe(url, caller)
        again = probe(url, caller, at=NOW + PROBE_SPACING * 2)
        rows = attempts(url)
        kept = projected(url)
        ended = leases(url)
        done = status(url)
        everything = str(sql(url, "SELECT * FROM ops.connector_sync")) + str(
            sql(url, "SELECT * FROM ops.setting")
        )

    assert waiting.pending and waiting.verdict is None
    assert (first.answered, again.answered) == (1, 0)
    assert len(caller.calls) == 1
    assert caller.calls[0].headers["Authorization"] == f"Bearer {KEY}"
    assert kept == []
    ((outcome, health, records, _, failures, _, _, detail),) = rows
    assert (outcome, health, records, failures, detail) == ("probed", "ok", 0, 0, PROBE_ANSWERED)
    assert ended == ["revoked"]
    assert not done.pending and done.verdict is ProbeVerdict.ANSWERED
    assert KEY not in everything


@pytest.mark.needs_db
def test_a_declined_key_is_recorded_on_the_sources_health_and_the_schedule_is_unmoved() -> None:
    """A scheduled read found the key declined; the key is tested again and still declined. The
    test is the source's newest attempt, down, and the read's backoff is exactly where it was.

    Delete this and a test's finding never reaches the source's health, or a test pushes a failing
    source further into its backoff."""
    with a_probe_database("brain_connector_probe_declined") as url:
        connect(url)
        sync(url, Replay([answer_for("XERO-401-expired")]))
        ask(url, at=NOW + timedelta(minutes=1))
        probe(url, Replay([answer_for("XERO-401-expired")]), at=NOW + timedelta(minutes=2))
        rows = attempts(url)
        newest = through(url, lambda sessions: _states(sessions))

    read, tested = rows
    assert (tested[0], tested[1], tested[7]) == ("probed", "down", KEY_DECLINED)
    assert (tested[4], tested[5]) == (read[4], read[5])
    (state,) = newest.values()
    assert (state.outcome.value, state.health.value) == ("probed", "down")


async def _states(sessions: async_sessionmaker[AsyncSession]) -> Any:
    async with sessions() as session:
        return await read_states(session)


@pytest.mark.needs_db
def test_a_source_that_asked_to_wait_is_not_called_and_says_why() -> None:
    """The recorded daily refusal leaves a wait; a test asked for inside it makes no call and says
    so, and one asked for after it is made. Delete this and a test spends a call the tenant does not
    have, which is the allowance the ceiling exists to protect."""
    with a_probe_database("brain_connector_probe_waits") as url:
        connect(url)
        sync(url, Replay([answer_for("XERO-429")]))
        wait_ends = attempts(url)[0][5]
        ask(url, at=NOW + timedelta(seconds=30))
        caller = Replay([answer_for("XERO-200-invoices")])
        held = probe(url, caller, at=NOW + timedelta(minutes=1))
        ask(url, at=wait_ends)
        made = probe(url, caller, at=wait_ends + timedelta(seconds=1))
        rows = attempts(url)

    assert (held.not_sent, made.answered) == (1, 1)
    assert len(caller.calls) == 1
    assert [one[7] for one in rows] == [
        rows[0][7],
        PROBE_NOT_SENT_WHILE_WAITING,
        PROBE_ANSWERED,
    ]


@pytest.mark.needs_db
def test_a_refusal_for_volume_and_a_missing_key_are_findings_and_not_failures_of_the_read() -> None:
    """A 429 to a test waits as the source asked and is not failing; an empty slot calls nothing and
    is a failure the page names. Delete this and a busy source reads as a broken one, or a test with
    no key is sent anyway."""
    with a_probe_database("brain_connector_probe_findings") as url:
        connect(url)
        ask(url)
        probe(url, Replay([answer_for("XERO-429")]))
        ask(url, at=NOW + timedelta(hours=2))
        silent = Replay([answer_for("XERO-200-invoices")])
        probe(url, silent, at=NOW + timedelta(hours=2, seconds=1), keys=NoKeys())
        rows = attempts(url)
        ended = leases(url)

    assert [(one[0], one[1], one[4], one[7]) for one in rows] == [
        ("probed", "degraded", 0, PROBE_REFUSED_FOR_NOW),
        ("probed", "degraded", 0, NO_KEY),
    ]
    assert silent.calls == []
    assert ended[1] == "none"


@pytest.mark.needs_db
def test_a_test_waits_while_a_scheduled_read_holds_the_lock() -> None:
    """A test and a read never spend one source's allowance together, and two replicas never both
    answer one press. Delete this and the pass ignores the read's lock."""
    with a_probe_database("brain_connector_probe_lock") as url:
        connect(url)
        ask(url)

        async def contended(sessions: async_sessionmaker[AsyncSession]) -> ProbeRun:
            async with sessions() as holder, holder.begin():
                assert await take_the_lock(holder, PROBE_LOCK)
                return await probe_on(
                    sessions=sessions,
                    now=NOW,
                    keys=Keys(),
                    caller=Replay([answer_for("XERO-200-invoices")]),
                    resolver=Resolver(),
                    clock=lambda: NOW,
                )

        held = through(url, contended)
        rows = attempts(url)
        made = probe(url, Replay([answer_for("XERO-200-invoices")]))

    assert held.held_by_a_read and rows == []
    assert made.answered == 1


@pytest.mark.needs_db
def test_the_worker_starts_a_pass_only_when_a_test_is_owed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The worker asks this on every tick, so the common case must start nothing. Delete this and
    the worker opens a thread, an engine and a vault token every thirty seconds, or never starts
    the pass a press asked for."""
    started: list[datetime] = []

    def stand_in(database_url: str, now: datetime) -> ProbeRun:
        started.append(now)
        return ProbeRun()

    monkeypatch.setattr(connector_probe_run, "_probe_in_thread", stand_in)

    def tick(url: str, at: datetime) -> Any:
        async def go() -> Any:
            engine = make_app_engine(url)
            try:
                return await tick_probes(make_session_factory(engine), now=at, database_url=url)
            finally:
                await engine.dispose()

        return run(go)

    with a_probe_database("brain_connector_probe_tick") as url:
        connect(url)
        nothing = tick(url, NOW)
        ask(url)
        early = tick(url, NOW - timedelta(seconds=1))
        owed = tick(url, NOW)

    assert (nothing, early) == (None, None)
    assert owed == ProbeRun()
    assert started == [NOW]


# ------------------------------------------------------------------ the ledger and 0142


@pytest.mark.needs_db
def test_a_press_is_on_the_ledger_and_a_test_survives_the_downgrade() -> None:
    """Built through every migration: a press appends a `setting` entry naming who pressed it, a
    `probed` row is admitted, and after `0142`'s downgrade the row is still there while a new one is
    refused. Delete this and a press could go unrecorded, or the downgrade could delete history or
    fail on it, which `0026` and `tests/unit/test_downgrade_keeps_history.py` argue against."""
    database = "brain_connector_probe_ledger"
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to head needs pgvector, which CI has")
        connection_id = connect(url)
        ask(url)
        _probed_row(url, connection_id)
        found = [
            (one.actor_id, one.subject, dict(one.details))
            for one in entries(url)
            if one.action.value == "setting"
        ]
        migrate(database, "downgrade", DOWN_REVISION)
        kept = sql(url, "SELECT outcome FROM ops.connector_sync")
        with pytest.raises(Exception, match="outcome"):
            _probed_row(url, connection_id)

    assert found == [(ADMIN, f"setting:{REQUEST_NAMESPACE}.xero", {"change": "set"})]
    assert kept == [("probed",)]


def _probed_row(url: str, connection_id: Any) -> None:
    sql(
        url,
        "INSERT INTO ops.connector_sync (connection_id, connector, started_at, finished_at, "
        "outcome, health, next_attempt_at, detail) VALUES (%s, 'xero', %s, %s, 'probed', 'ok', "
        "%s, %s)",
        connection_id,
        NOW,
        NOW,
        NOW,
        PROBE_ANSWERED,
    )


def test_each_tick_of_the_worker_is_followed_by_a_pass_and_a_pass_that_raises_is_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The worker's schedule makes the pass after each tick with its own sessions, and a pass that
    raises is printed and the next tick still happens. Delete this and the worker's schedule can
    drop the call with every test above still green, or one unreachable vault stops the schedule."""
    order: list[str] = []
    handed: list[object] = []

    async def tick(*_: object, **__: object) -> tuple[ControlTick, ...]:
        order.append("tick")
        return ()

    async def refresh(_: object) -> tuple[str, ...]:
        return ()

    async def probes(sessions: object, *, now: datetime, database_url: str) -> None:
        order.append("probes")
        handed.append(sessions)
        if len(handed) == 1:
            msg = "the vault did not answer"
            raise OSError(msg)

    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise asyncio.CancelledError

    sessions = object()
    monkeypatch.setattr(worker, "tick_controls", tick)
    monkeypatch.setattr(worker, "tick_probes", probes)
    with pytest.raises(asyncio.CancelledError):
        run(
            lambda: worker.run_schedule(
                sessions,  # type: ignore[arg-type]
                database_url="unused",
                clock=lambda: NOW,
                sleep=sleep,
                refresh=refresh,
            )
        )

    assert order == ["tick", "probes", "tick", "probes"]
    assert handed == [sessions, sessions]
    assert "OSError: the vault did not answer" in capsys.readouterr().err
