"""The front half's decisions reach the request row, and a redelivered message is claimed once.

The mapping half runs everywhere. The database half needs a server and runs in CI: `0039` then
`0100` for real on a fresh database, written as `brain_app` so the grants and the row-level
security policies are what is exercised, not the owner's bypass.

Task ids: M3.2.2, M3.4.2, M3.6.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.core.entitlement import EntitlementSet
from brain.core.lane import Lane
from brain.gate.context import Channel
from brain.gate.event_store import ExternalIdTooLongError, first_delivery
from brain.gate.finish import Finished, FinishError, FrontRecord, Origin
from brain.gate.ingress import ChannelEvent
from brain.gate.select import SelectionStage
from brain.ops.telemetry import request_telemetry_of
from brain.ops.telemetry_store import record
from brain.tables.channel_event import EXTERNAL_ID_CHARS
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, run, sql
from tests.unit.test_request_finish import asker

#: Far from any wall clock; nothing here is about the present.
AT = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)
FRONT = FrontRecord(
    risk_score=55,
    routed_lane=Lane.ANSWER,
    selection_stage=SelectionStage.ADDRESSED,
    selected_agent="finance",
)


def _finished(front: FrontRecord | None = None, trace: str = "t-front-row") -> Finished:
    origin = Origin(trace_id=trace, principal=asker("u_one"), channel=Channel.CONSOLE)
    return Finished(
        origin,
        AT,
        None,
        completed_at=AT + timedelta(milliseconds=8),
        entitlement_hash=EntitlementSet(principal_id="u_one").ent_hash(),
        lane=Lane.FAST,
        tool_calls=0,
        front=front,
    )


def _event(external_id: str = "m-1", channel: Channel = Channel.LARK) -> ChannelEvent:
    return ChannelEvent(
        channel=channel,
        external_id=external_id,
        channel_identity="someone",
        text="a question",
        received_at=AT,
    )


# ------------------------------------------------------------------ the mapping
def test_the_row_carries_the_front_halfs_decisions_as_they_were_made() -> None:
    """M3.4.2 and M3.6.3: score, routed lane, stage and agent come off the `FrontRecord` the
    chain built, and the routed lane stays distinct from the lane whose budget was spent.

    Delete this and the four columns can be filled from anywhere, or not at all."""
    row = request_telemetry_of(_finished(FRONT)).ledger_row()
    assert row["risk_score"] == 55
    assert row["routed_lane"] is Lane.ANSWER
    assert row["selection_stage"] is SelectionStage.ADDRESSED
    assert row["selected_agent"] == "finance"
    assert row["lane"] is Lane.FAST


def test_a_request_the_front_half_did_not_run_for_leaves_all_four_empty() -> None:
    """None rather than a zero score or a default lane, which a report would believe."""
    row = request_telemetry_of(_finished()).ledger_row()
    for column in ("risk_score", "routed_lane", "selection_stage", "selected_agent"):
        assert row[column] is None, column


@pytest.mark.parametrize("score", [-1, 101])
def test_a_score_outside_the_scale_is_refused(score: int) -> None:
    with pytest.raises(FinishError):
        FrontRecord(score, Lane.ANSWER, SelectionStage.DEFAULT, "general")


def test_an_external_id_longer_than_the_key_is_refused_rather_than_truncated() -> None:
    """Truncation would fold two messages sharing a prefix into one key and drop the second."""

    class Untouched:
        async def execute(self, *_: object) -> None:
            raise AssertionError("nothing may be written for an id the key cannot hold")

    with pytest.raises(ExternalIdTooLongError):
        run(lambda: first_delivery(Untouched(), _event("x" * (EXTERNAL_ID_CHARS + 1))))  # type: ignore[arg-type]


# ------------------------------------------------------------------ the database
DATABASE = "brain_test_m322_front_half"


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """`0039` for the ledger, then `0100`, each run for real on the one before it stamped."""
    scratch = fresh(DATABASE)
    try:
        migrate(DATABASE, "stamp", "0038")
        migrate(DATABASE, "upgrade", "0039")
        migrate(DATABASE, "stamp", "0093")
        migrate(DATABASE, "upgrade", "0100")
        yield scratch
    finally:
        drop(DATABASE)


def _claims(url: str, *events: ChannelEvent) -> list[bool]:
    async def go() -> list[bool]:
        bound = engine(url)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                claimed = [await first_delivery(session, one) for one in events]
                await session.commit()
                return claimed
        finally:
            await bound.dispose()

    return run(go)


def test_a_redelivered_message_is_claimed_once_and_the_same_id_elsewhere_is_its_own(
    database: str,
) -> None:
    """M3.2.2: the unique index on `(channel, external_id)` refuses the second delivery, and the
    same id from another channel is another message.

    Delete this and the dedupe key is only ever compiled, and a webhook's retry is answered
    twice."""
    sql(database, "TRUNCATE gate.channel_event")
    assert _claims(database, _event("m-7"), _event("m-7")) == [True, False]
    assert _claims(database, _event("m-7")) == [False]
    assert _claims(database, _event("m-7", Channel.SLACK)) == [True]
    assert sql(database, "SELECT count(*) FROM gate.channel_event") == [(2,)]


def test_the_front_halfs_columns_are_written_as_the_application_role(database: str) -> None:
    """The recorder's insert, as `brain_app`, lands the four columns on the migrated ledger."""
    sql(database, "TRUNCATE obs.request_telemetry")

    async def go() -> None:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                await record(session, request_telemetry_of(_finished(FRONT)))
                await record(session, request_telemetry_of(_finished(None, trace="t-plain")))
                await session.commit()
        finally:
            await bound.dispose()

    run(go)
    assert sql(
        database,
        "SELECT trace_id, risk_score, routed_lane, selection_stage, selected_agent "
        "FROM obs.request_telemetry ORDER BY trace_id",
    ) == [
        ("t-front-row", 55, "answer", "addressed", "finance"),
        ("t-plain", None, None, None, None),
    ]
