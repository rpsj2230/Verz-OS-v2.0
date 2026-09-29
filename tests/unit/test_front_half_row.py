"""The front half's decisions reach the request row, and a redelivered message is claimed once.

The mapping half runs everywhere. The database half needs a server and runs in CI: `0039`, `0100`
and `0113` for real on a fresh database, written as `brain_app` so the grants and the row-level
security policies are what is exercised, not the owner's bypass.

Task ids: M3.2.2, M3.4.2, M3.6.3
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.core.entitlement import EntitlementSet
from brain.core.lane import Lane
from brain.gate.answer import route_of
from brain.gate.classify import LaneBasis
from brain.gate.context import Channel
from brain.gate.event_store import ExternalIdTooLongError, first_delivery
from brain.gate.finish import Finished, FinishError, FrontRecord, Origin
from brain.gate.ingress import ChannelEvent
from brain.gate.select import SelectionStage
from brain.models.metering import Meter, ModelRoute
from brain.models.routing import RoutingRequest, Tier, TierBasis, classify_tier
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
    lane_basis=LaneBasis.FAST_REFUSED,
)
ROUTE = ModelRoute(tier=Tier.HEAVY, basis=TierBasis.PINNED)


def _finished(
    front: FrontRecord | None = None,
    trace: str = "t-front-row",
    route: ModelRoute | None = None,
) -> Finished:
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
        route=route,
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
    assert row["lane_basis"] is LaneBasis.FAST_REFUSED
    assert row["lane"] is Lane.FAST


def test_the_row_carries_the_route_the_executor_noted_and_not_one_derived_from_the_lane() -> None:
    """M3.6.3: the tier and its basis come off `Finished.route`, which the meter took from the
    executor's decision. A heavy pinned route beside an answer-lane question is what a derivation
    from the lane could never produce, so it can only have come from the route.

    Delete this and the row's tier can be filled from the lane after the fact, which is the
    inference the leaf forbids."""
    row = request_telemetry_of(_finished(FRONT, route=ROUTE)).ledger_row()
    assert (row["routed_tier"], row["tier_basis"]) == (Tier.HEAVY, TierBasis.PINNED)
    assert row["routed_lane"] is Lane.ANSWER


def test_a_request_the_front_half_did_not_run_for_leaves_all_its_columns_empty() -> None:
    """None rather than a zero score, a default lane or a default tier, which a report would
    believe."""
    row = request_telemetry_of(_finished()).ledger_row()
    for column in (
        "risk_score",
        "routed_lane",
        "selection_stage",
        "selected_agent",
        "lane_basis",
        "routed_tier",
        "tier_basis",
    ):
        assert row[column] is None, column


@pytest.mark.parametrize("score", [-1, 101])
def test_a_score_outside_the_scale_is_refused(score: int) -> None:
    with pytest.raises(FinishError):
        FrontRecord(score, Lane.ANSWER, SelectionStage.DEFAULT, "general", LaneBasis.DEFAULT)


def test_a_front_half_tier_is_recorded_with_the_step_that_settled_it_or_not_at_all() -> None:
    """A tier with no basis would put a routing decision on the row with no reason beside it,
    and a basis with no tier a reason for nothing. Delete this and either half can reach the row
    alone, where a report reads it as a decision."""
    with pytest.raises(FinishError):
        replace(FRONT, routed_tier=Tier.MAIN)
    with pytest.raises(FinishError):
        replace(FRONT, tier_basis=TierBasis.DEFAULT)
    held = replace(FRONT, routed_tier=Tier.MAIN, tier_basis=TierBasis.DEFAULT)
    assert (held.routed_tier, held.tier_basis) == (Tier.MAIN, TierBasis.DEFAULT)


#: What the front half decided at ROUTE for an answer-lane question: the default tier.
ROUTED_MAIN = replace(FRONT, routed_tier=Tier.MAIN, tier_basis=TierBasis.DEFAULT)


def test_a_request_no_call_was_classified_for_is_routed_where_the_front_half_sent_it() -> None:
    """`THE_ROW_HOLDS_THE_LAST_ROUTING_DECISION_MADE`, the front half's half: a question answered
    by a rule or abstained on before a model carries the tier ROUTE chose, and a cache hit, which
    ROUTE never ran for, and a request that never passed the front half carry none.

    Delete this and such a request's row holds a lane and no tier, which is the defect every
    routed row on the owner's install had until 2026-09-29."""
    assert route_of(Meter(), ROUTED_MAIN) == ModelRoute(tier=Tier.MAIN, basis=TierBasis.DEFAULT)
    assert route_of(Meter(), FRONT) is None
    assert route_of(Meter(), None) is None


def test_the_executor_s_decision_outranks_the_front_half_s_even_when_it_names_none() -> None:
    """The executor's half: a call classified heavy for its size is recorded heavy although the
    front half said main, and two calls that disagree record no tier rather than falling back to
    the front half's, because a disagreement is the executor's answer and not the absence of one.

    Delete this and the row can name the tier the front half guessed before the messages were
    built instead of the one the call was sent to, or turn a disagreement into a false agreement."""
    heavy = Meter()
    heavy.routed(classify_tier(RoutingRequest(lane=Lane.ANSWER, estimated_context_tokens=10**6)))
    assert route_of(heavy, ROUTED_MAIN) == ModelRoute(tier=Tier.HEAVY, basis=TierBasis.CONTEXT)
    split = Meter()
    split.routed(classify_tier(RoutingRequest(lane=Lane.ANSWER)))
    split.routed(classify_tier(RoutingRequest(lane=Lane.TASK)))
    assert route_of(split, ROUTED_MAIN) is None


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
    """`0039` for the ledger, then `0100` and `0113`, each run for real on the one before it
    stamped."""
    scratch = fresh(DATABASE)
    try:
        migrate(DATABASE, "stamp", "0038")
        migrate(DATABASE, "upgrade", "0039")
        migrate(DATABASE, "stamp", "0097")
        migrate(DATABASE, "upgrade", "0100")
        migrate(DATABASE, "stamp", "0108")
        migrate(DATABASE, "upgrade", "0113")
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
    """The recorder's insert, as `brain_app`, lands the routing decision on the migrated ledger,
    and each check admits the codes the enums hold."""
    sql(database, "TRUNCATE obs.request_telemetry")

    async def go() -> None:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                await record(session, request_telemetry_of(_finished(FRONT, route=ROUTE)))
                await record(session, request_telemetry_of(_finished(None, trace="t-plain")))
                await session.commit()
        finally:
            await bound.dispose()

    run(go)
    assert sql(
        database,
        "SELECT trace_id, risk_score, routed_lane, selection_stage, selected_agent, lane_basis, "
        "routed_tier, tier_basis FROM obs.request_telemetry ORDER BY trace_id",
    ) == [
        ("t-front-row", 55, "answer", "addressed", "finance", "fast_refused", "heavy", "pinned"),
        ("t-plain", None, None, None, None, None, None, None),
    ]


@pytest.mark.parametrize(
    ("column", "real", "invented"),
    [
        ("lane_basis", "long_question", "guessed"),
        ("routed_tier", "small", "biggest"),
        ("tier_basis", "residency_floor", "hunch"),
    ],
)
def test_a_route_code_no_enum_holds_is_refused_by_that_columns_check(
    database: str, column: str, real: str, invented: str
) -> None:
    """0113's checks, run for real: the longest real code is written, and a code outside
    `LaneBasis`, `Tier` or `TierBasis` is refused by the check named for that column.

    Delete this and a check copied wrongly into the migration admits any word, or a width too
    narrow refuses a real code, and a five-year row says a question was routed for a reason no
    release ever had."""
    import psycopg

    statement = (
        "INSERT INTO obs.request_telemetry (received_at, trace_id, traffic_class, principal, "
        "entitlement_hash, lane, cache_hit, status, duration_ms, lane_basis, routed_tier, "
        "tier_basis) VALUES (%s, 't-code', 'human_interactive', 'u_one', %s, 'fast', false, "
        "'answered', 1, %s, %s, %s)"
    )
    ent_hash = EntitlementSet(principal_id="u_one").ent_hash()

    def insert(code: str) -> None:
        # Every other route column holds a real code, so only `column`'s check can refuse.
        codes = {"lane_basis": "default", "routed_tier": "main", "tier_basis": "default"}
        codes[column] = code
        sql(database, statement, AT, ent_hash, *codes.values())

    insert(real)
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        insert(invented)
    assert refused.value.diag.constraint_name == f"ck_request_telemetry_{column}"
