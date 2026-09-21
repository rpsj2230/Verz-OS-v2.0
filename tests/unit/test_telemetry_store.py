"""The metadata ledger's row, built from a finished request, and the table that holds it.

Three layers, each tested where it decides something. The mapping: `request_telemetry_of` turns
what the lane finished with into a row, and a withheld record, an absent one and a question no
rule matched become the same row. The recorder: a row is written and committed, and a row that
cannot be built or written is logged and never fails the answer. The table: `0039` is run for
real, partitioned on the column `brain.ops.partitioning` routes on, with row-level security on
the parent and its default partition, and the real route writes to it and a service level
reading is read back from it.

The database half skips without `DATABASE_URL`, and CI always sets it. Its scratch database
has a name of its own, because the scratch server is shared.

Task ids: M30.5.2
"""

from __future__ import annotations

import asyncio
import enum
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.lane import Lane
from brain.db import metadata
from brain.gate.abstain import Abstention, AbstentionReason, scope_of_reach
from brain.gate.answer import Answered
from brain.gate.context import Channel, TrafficClass
from brain.gate.finish import A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS, Finished, Origin
from brain.ops.partitioning import CONTROL_COLUMN
from brain.ops.service_levels import Observation
from brain.ops.telemetry import (
    AN_ABSTENTION_IS_RECORDED_WITHOUT_ITS_REASON,
    UNFILLABLE_TODAY,
    MeteredRequest,
    RequestStatus,
    RequestTelemetry,
    TelemetryError,
    request_telemetry_of,
    status_of_finished,
)
from brain.ops.telemetry_store import (
    TelemetryRecorder,
    metered_between,
    observed_between,
    record,
    service_levels_between,
)
from brain.tables.telemetry import RequestTelemetryRow
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, modelled, run, shape, sql
from tests.unit.test_answer_lane import (
    ACME,
    CLIENT_TOOL,
    NOW,
    SEES_HOURS,
    SEES_NAME_ONLY,
    Rows,
    ents,
)
from tests.unit.test_answer_route import HOURS as PRICE
from tests.unit.test_answer_route import OneRow
from tests.unit.test_api_routes import SOURCE, token_for
from tests.unit.test_question_store import COST
from tests.unit.test_request_finish import (
    DONE,
    OUTCOMES,
    TRACE,
    Broken,
    Kept,
    asker,
    done,
    lane,
    origin_for,
    wired,
)

TABLES = ("obs.request_telemetry",)
DEFAULT_PARTITION = "obs.request_telemetry_default"

#: Far outside any plausible wall clock, for the tests not about the present.
LATER = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)


def finished_by(**arguments: Any) -> Finished:
    """Run the lane once with a recorder and hand back what the recorder was given."""
    kept = Kept()
    lane(**arguments, recorders=(kept,))
    (one,) = kept.seen
    return one


# --- the mapping ----------------------------------------------------------------------------


def test_an_answered_request_is_a_row_of_who_at_which_reach_through_which_lane_and_how_long() -> (
    None
):
    """**The six fields a lane can fill, each from what the gate or the lane decided.** The
    principal off the origin, the hash of the reach answered at, the lane's own budget, no cache,
    answered, and forty-two milliseconds between the judged instant and the clock's. The ingress
    is the origin's trace, the class the channel declares, and the judged instant. Everything
    `UNFILLABLE_TODAY` names is still None.

    Delete this and a row can be built from somewhere that is not the finished request, such as
    a principal the caller supplied or a duration nobody measured."""
    telemetry = request_telemetry_of(finished_by())

    assert telemetry.principal == "p_priya"
    assert telemetry.entitlement_hash == ents(*SEES_HOURS).ent_hash()
    assert telemetry.lane is Lane.FAST
    assert telemetry.cache_hit is False
    assert telemetry.status is RequestStatus.ANSWERED
    assert telemetry.duration_ms == 42.0
    assert telemetry.ingress.trace_id == TRACE
    assert telemetry.ingress.traffic_class is TrafficClass.HUMAN_INTERACTIVE
    assert telemetry.ingress.received_at == NOW
    for name in UNFILLABLE_TODAY:
        assert getattr(telemetry, name) is None, name


def test_the_traffic_class_is_the_one_the_channel_declares() -> None:
    """A question over the API is automation and one on the console is a person, read through
    `traffic_class_for` rather than decided here.

    Delete this and every row can be filed as a person, which is the traffic class the usage
    figures about people exclude machines by."""
    api = done(Origin(trace_id=TRACE, principal=asker(), channel=Channel.API))
    console = done(origin_for())

    assert request_telemetry_of(api).ingress.traffic_class is TrafficClass.AUTOMATION
    assert request_telemetry_of(console).ingress.traffic_class is TrafficClass.HUMAN_INTERACTIVE


def test_a_duration_is_exact_to_the_microsecond_and_counts_whole_days() -> None:
    """Read from the `timedelta` in whole microseconds, so half a millisecond survives and a
    request that crossed a day is a day long rather than a few seconds.

    Delete this and the days or the microseconds can be dropped from the arithmetic, and a
    request that hung over midnight enters the percentile as quick."""
    half = done(origin_for(), completed_at=NOW + timedelta(microseconds=42_500))
    day = done(origin_for(), completed_at=NOW + timedelta(days=1, microseconds=1_000))

    assert request_telemetry_of(half).duration_ms == 42.5
    assert request_telemetry_of(day).duration_ms == 86_400_001.0


def test_a_cache_hit_is_answered_and_served_from_the_cache() -> None:
    """The one outcome with neither an answer nor an abstention on it, and the one where the
    flag is True.

    Delete this and a cache hit can be recorded as an abstention, or as computed, and the
    cache's effect on latency is invisible in the ledger."""
    telemetry = request_telemetry_of(finished_by(**OUTCOMES["served from the cache"]))

    assert telemetry.status is RequestStatus.ANSWERED
    assert telemetry.cache_hit is True


def test_a_fault_is_failed_and_was_served_from_nothing() -> None:
    """The lane raised, so there is no outcome: the status is the fault's and nothing was
    served from the cache. The exception still reaches the caller.

    Delete this and a fault can be recorded as answered, and an outage never costs the success
    rate anything."""
    kept = Kept()
    with pytest.raises(RuntimeError):
        lane(readers={("laravel", "client"): CLIENT_TOOL.reader(Broken())}, recorders=(kept,))

    telemetry = request_telemetry_of(kept.seen[0])

    assert telemetry.status is RequestStatus.FAILED
    assert telemetry.cache_hit is False


@pytest.mark.parametrize("reason", list(AbstentionReason))
def test_every_abstention_is_nothing_returned_whatever_it_abstained_for(
    reason: AbstentionReason,
) -> None:
    """See `AN_ABSTENTION_IS_RECORDED_WITHOUT_ITS_REASON`. Parametrised over every reason there
    is, including the two that must never be told apart, with a detail naming an entity and a
    field, so a status that read either would differ somewhere.

    Delete this and a mapping over the reasons can grow, and the first reason it separates is
    the one a department head reads as refusals."""
    abstained = Answered(
        frames=("closed",),
        abstention=Abstention(
            reason=reason, scope=scope_of_reach(("laravel",)), detail="client.cost locked"
        ),
    )

    assert status_of_finished(done(origin_for(), abstained)) is RequestStatus.NOTHING_RETURNED
    assert AN_ABSTENTION_IS_RECORDED_WITHOUT_ITS_REASON


def test_a_withheld_record_and_an_absent_one_are_one_row_and_no_rule_means_no_call() -> None:
    """**DENIED and ABSENT in the ledger, through the real lane.** One person, one reach, one
    trace: a question about a record whose answer field they may not read and a question about a
    record that does not exist produce two rows equal in every field. A question no rule matches
    is equal to them in every field but `tool_count`, which is zero because no read started, and
    that says whether the installation has a rule for the question's form, which is the same for
    every asker and every record. See `A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS`. The answered
    request beside them is the positive sibling, and it differs.

    Compared as whole ledger rows, so any field that differed would fail it whatever its name.

    Delete this and a row can grow a reason, or a status or a count that splits the first two,
    and the ledger is a count of what each person was refused."""
    narrow = ents(*SEES_NAME_ONLY)
    withheld = finished_by(reach=narrow, rows=Rows(ACME))
    absent = finished_by(reach=narrow, rows=Rows())
    unmatched = finished_by(reach=narrow, question="what colour is the sky")
    answered = finished_by(reach=ents(*SEES_HOURS), rows=Rows(ACME))

    assert A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS
    assert isinstance(withheld.outcome, Answered) and withheld.outcome.abstention is not None
    rows = [dict(request_telemetry_of(one).ledger_row()) for one in (withheld, absent, unmatched)]
    assert rows[0] == rows[1]
    assert {**rows[2], "tool_count": rows[0]["tool_count"]} == rows[0]
    assert (rows[0]["tool_count"], rows[2]["tool_count"]) == (1, 0)
    assert request_telemetry_of(answered).status is not rows[0]["status"]


def test_a_principal_the_trace_grammar_masks_has_no_row() -> None:
    """`A_PRINCIPAL_THE_TRACE_GRAMMAR_REFUSES_HAS_NO_LEDGER_ROW_AT_ALL`, reached from a finished
    request. The positive sibling is every other mapping test here, with a lowercase id.

    Delete this and the mapping can be loosened to pass the id through, and the ledger holds an
    identifier the trace masker would refuse."""
    with pytest.raises(TelemetryError):
        request_telemetry_of(done(origin_for("U_WeiLing")))


def test_a_completion_before_the_judged_instant_is_refused_as_a_negative_duration() -> None:
    """A clock that stepped backwards is a negative duration, which the record refuses. The
    positive sibling is a completion at exactly the judged instant, which is zero.

    Delete this and the arithmetic can be reversed, and every row carries the negative of how
    long its request took, which the record then refuses for every request."""
    with pytest.raises(TelemetryError, match="cannot be negative"):
        request_telemetry_of(done(origin_for(), completed_at=NOW - timedelta(milliseconds=1)))
    assert request_telemetry_of(done(origin_for(), completed_at=NOW)).duration_ms == 0.0


# --- the recorder, without a server ---------------------------------------------------------


class Session:
    """Enough of an `AsyncSession` to see what was executed and whether it was committed."""

    def __init__(self, journal: list[str], statements: list[Any]) -> None:
        self.journal = journal
        self.statements = statements

    async def __aenter__(self) -> Session:
        self.journal.append("open")
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        self.journal.append("execute")
        self.statements.append(statement)

    async def commit(self) -> None:
        self.journal.append("commit")


def recorder_with(journal: list[str], statements: list[Any]) -> TelemetryRecorder:
    return TelemetryRecorder(lambda: Session(journal, statements))  # type: ignore[arg-type]


def test_the_recorder_inserts_the_whole_row_as_text_the_driver_can_write_and_commits() -> None:
    """One insert carrying every key of the ledger row, then a commit. The row goes to the driver
    as `ledger_row` produces it, which is safe only because every closed vocabulary on it is a
    `StrEnum` and is written as its text; that is asserted on the row, so an enum that is not a
    `str` fails here rather than as a refused insert inside the lane's `finally`. The server-side
    half is below.

    Delete this and a recorder that never commits, or a row carrying an enum the driver cannot
    write, passes every test that reads its log."""
    journal: list[str] = []
    statements: list[Any] = []
    request = finished_by()

    asyncio.run(recorder_with(journal, statements).finished(request))

    assert journal == ["open", "execute", "commit"]
    row = request_telemetry_of(request).ledger_row()
    enums = [value for value in row.values() if isinstance(value, enum.Enum)]
    assert len(enums) == 3
    assert all(isinstance(value, str) for value in enums)
    (statement,) = statements
    sent = statement.compile().params
    assert set(sent) == set(request_telemetry_of(request).ledger_row())
    assert sent["status"] == "answered"
    assert sent["lane"] == "fast"
    assert sent["traffic_class"] == "human_interactive"
    assert sent["duration_ms"] == 42.0


def test_a_request_the_ledger_refuses_is_logged_without_the_value_and_opens_no_session(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A principal the trace grammar masks cannot be a row. The recorder says so under the trace
    id, never with the principal, and never raises into the lane's `finally`.

    `capsys` because structlog writes to stdout.

    Delete this and the refusal either fails every answered question for a directory whose ids
    have capitals in them, or writes those ids to the log the ledger refused to hold them in."""
    journal: list[str] = []
    capsys.readouterr()

    asyncio.run(recorder_with(journal, []).finished(done(origin_for("U_WeiLing"))))

    written = capsys.readouterr().out
    assert journal == []
    assert "telemetry.unrecordable" in written, written
    assert TRACE in written, written
    assert "WeiLing" not in written, written


def test_a_row_the_database_refuses_is_logged_and_the_answer_is_still_delivered(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`, the question
    recorder's rule, held for this recorder through the real lane: the sessions are unreachable
    and the lane still returns its answer, and the failure is a warning naming the trace.

    Delete this and a database hiccup turns every answered question into a fault."""

    def unreachable() -> Session:
        raise ConnectionError("database gone")

    capsys.readouterr()
    answered = lane(recorders=(TelemetryRecorder(unreachable),))  # type: ignore[arg-type,arg-type]

    written = capsys.readouterr().out
    assert answered.composed is not None
    assert "telemetry.unrecorded" in written, written
    assert TRACE in written, written
    assert "telemetry.unrecordable" not in written, written


# --- the route, without a server ------------------------------------------------------------


@pytest.fixture
def routed() -> Iterator[tuple[TestClient, Kept]]:
    """The real application and its answer route, with a recorder keeping what it is handed."""
    kept = Kept()
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = wired()
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.fast_path_rules = (PRICE,)
        app.state.request_recorders = (kept,)
        yield client, kept


def test_a_question_asked_over_http_becomes_a_row_of_the_asker_and_a_real_duration(
    routed: tuple[TestClient, Kept],
) -> None:
    """The request path building a row: the directory's principal, the reach the gate computed,
    the fast lane, answered, and a positive duration measured by the wall clock the route hands
    the lane, under the trace id the response carries.

    Delete this and the route can hand the lane something that makes every row unbuildable, and
    every mapping test above still passes against the lane directly."""
    client, kept = routed

    answered = client.post(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for('u_wide')}"},
        json={"question": "what is the price of WEB-1001"},
    )

    telemetry = request_telemetry_of(kept.seen[0])
    assert answered.status_code == 200
    assert telemetry.principal == "u_wide"
    assert telemetry.ingress.trace_id == answered.headers["x-trace-id"]
    assert telemetry.lane is Lane.FAST
    assert telemetry.status is RequestStatus.ANSWERED
    assert telemetry.duration_ms > 0


# --- the table ------------------------------------------------------------------------------


@contextmanager
def built(database: str) -> Iterator[str]:
    """A fresh database with `0039` run for real on top of `0038` stamped, then `0100`.

    `0039` points at nothing and needs only the `obs` schema and the application role, which
    `fresh` makes, so nothing before it is run. `0100` is the only later migration that alters
    this table (the front half's four columns) and needs only the `gate` schema besides.
    """
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0038")
        migrate(database, "upgrade", "0039")
        migrate(database, "stamp", "0093")
        migrate(database, "upgrade", "0100")
        yield scratch
    finally:
        drop(database)


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with built("brain_test_m3052_request_telemetry") as url:
        yield url


@pytest.fixture
def empty(database: str) -> str:
    sql(database, "TRUNCATE obs.request_telemetry")
    return database


def a_row(
    trace: str = "t-one",
    *,
    at: datetime = LATER,
    lane: Lane = Lane.FAST,
    status: RequestStatus = RequestStatus.ANSWERED,
    duration_ms: float = 12.5,
) -> RequestTelemetry:
    finished = Finished(
        Origin(trace_id=trace, principal=asker("u_one"), channel=Channel.CONSOLE),
        at,
        None,
        completed_at=at + timedelta(microseconds=int(duration_ms * 1000)),
        entitlement_hash=ents(*SEES_HOURS, principal="u_one").ent_hash(),
        lane=lane,
        tool_calls=0,
    )
    built_row = request_telemetry_of(finished)
    return RequestTelemetry(
        ingress=built_row.ingress,
        principal=built_row.principal,
        entitlement_hash=built_row.entitlement_hash,
        lane=lane,
        tool_count=built_row.tool_count,
        cache_hit=False,
        status=status,
        duration_ms=built_row.duration_ms,
    )


def write_as_app(database: str, *rows: RequestTelemetry) -> None:
    async def go() -> None:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                for one in rows:
                    await record(session, one)
                await session.commit()
        finally:
            await bound.dispose()

    run(go)


def read_as_app(database: str, start: datetime, end: datetime) -> tuple[Observation, ...]:
    async def go() -> tuple[Observation, ...]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                return await observed_between(session, start=start, end=end)
        finally:
            await bound.dispose()

    return run(go)


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it(database: str) -> None:
    """Compared as constraints, indexes and columns read back from two servers' catalogues, one
    built by `0039` and one by the model, so a width, a check or an index that differs fails here
    rather than at the first write in production.

    Delete this and the migration's copy of the status or lane vocabulary can fall behind the
    enum, and the first request ending a new way is refused inside the lane's `finally`."""
    with modelled("brain_test_m3052_request_telemetry_model", TABLES) as from_model:
        assert shape(database, TABLES) == shape(from_model, TABLES)


def test_every_column_of_the_table_is_a_key_of_the_row_a_real_record_produces() -> None:
    """The table holds `ledger_row` and a surrogate id, compared against a row built from a real
    finished request rather than against a list written here.

    Delete this and a field can be added to the record and not to the table, and the recorder's
    insert is refused for every request while the lane keeps answering."""
    produced = set(request_telemetry_of(finished_by()).ledger_row())

    assert set(RequestTelemetryRow.__table__.columns.keys()) == produced | {"id"}


def test_the_table_is_partitioned_on_the_column_the_partition_scheme_routes_on(
    database: str,
) -> None:
    """Read back from the server and held to `brain.ops.partitioning.CONTROL_COLUMN`, so the
    scheme and the table cannot route on different columns, and a default partition exists so a
    write has somewhere to land before pg_partman makes any period partitions.

    Delete this and the table can be created unpartitioned, which is the rewrite the partitioning
    module records as the change that cannot be undone cheaply."""
    ((partitioned_by,),) = sql(
        database, "SELECT pg_get_partkeydef('obs.request_telemetry'::regclass)"
    )
    children = sql(
        database,
        "SELECT inhrelid::regclass::text, pg_get_expr(c.relpartbound, c.oid) FROM pg_inherits "
        "JOIN pg_class c ON c.oid = inhrelid "
        "WHERE inhparent = 'obs.request_telemetry'::regclass",
    )

    assert partitioned_by == f"RANGE ({CONTROL_COLUMN})"
    assert children == [(DEFAULT_PARTITION, "DEFAULT")]
    # The model routes on the same column, so a table built from the metadata is the same table.
    model_options = metadata.tables["obs.request_telemetry"].dialect_options["postgresql"]
    assert model_options["partition_by"] == f"RANGE ({CONTROL_COLUMN})"


def test_the_ledger_has_row_level_security_and_the_app_may_only_read_and_append(
    database: str,
) -> None:
    """Row-level security on the parent and on its default partition, SELECT and INSERT granted
    on the parent and nothing on the partition, and both policies read back from the server.

    Delete this and a later migration can grant UPDATE, and how a request went becomes an edit
    anybody holding the application's credentials can make."""
    secured = {
        one[0]: one[1]
        for one in sql(
            database,
            "SELECT oid::regclass::text, relrowsecurity FROM pg_class "
            "WHERE oid IN ('obs.request_telemetry'::regclass, %s::regclass)",
            DEFAULT_PARTITION,
        )
    }
    granted = {
        (one[0], one[1])
        for one in sql(
            database,
            "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'brain_app' AND table_schema = 'obs' "
            "AND table_name LIKE 'request_telemetry%%'",
        )
    }
    policies = {
        (one[0], one[1])
        for one in sql(
            database,
            "SELECT polname, polcmd FROM pg_policy "
            "WHERE polrelid = 'obs.request_telemetry'::regclass",
        )
    }

    assert secured == {"obs.request_telemetry": True, DEFAULT_PARTITION: True}
    assert granted == {("request_telemetry", "SELECT"), ("request_telemetry", "INSERT")}
    assert policies == {("request_telemetry_readable", "r"), ("request_telemetry_appendable", "a")}


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE obs.request_telemetry SET status = 'failed'",
        "DELETE FROM obs.request_telemetry",
        "SELECT count(*) FROM obs.request_telemetry_default",
    ],
)
def test_the_application_role_cannot_change_remove_or_go_round_the_parent(
    empty: str, statement: str
) -> None:
    """Refused by the server, as the role the application connects as, including a read of the
    default partition directly, which is the one way round the parent's policies. The positive
    sibling is every write and read below, through the parent, as the same role.

    Delete this and the grants can widen with the migration test still green, because that test
    reads the grants and this one exercises them."""
    write_as_app(empty, a_row())
    with psycopg.connect(empty, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)

    assert sql(empty, "SELECT status FROM obs.request_telemetry") == [("answered",)]


def test_two_requests_under_one_trace_id_are_two_rows(empty: str) -> None:
    """The surrogate key, and the opposite of the question table on purpose: a caller may
    propose a trace id, so reusing one must not drop a request's duration from the percentile.

    Delete this and the key can move to the trace id, and a caller keeps their slow requests out
    of the latency objective by reusing an id."""
    write_as_app(empty, a_row("t-reused", duration_ms=5.0), a_row("t-reused", duration_ms=900.0))

    assert sql(
        empty, "SELECT trace_id, duration_ms FROM obs.request_telemetry ORDER BY duration_ms"
    ) == [("t-reused", 5.0), ("t-reused", 900.0)]


def test_model_usage_is_read_back_by_window_and_only_from_rows_whose_tokens_were_counted(
    empty: str,
) -> None:
    """The usage screen's read, as the application role, against the migrated ledger: a metered
    row inside the window comes back with its model and tokens, a row that called no model does
    not, and neither does a metered row outside the window.

    Delete this and `metered_rows` is only ever compiled, so a column it names wrongly or a filter
    the partitioned table refuses is found on an install, as the usage screen failing."""
    metered = replace(a_row("t-metered", at=LATER), model="kimi-k2", tokens_in=120, tokens_out=9)
    write_as_app(
        empty,
        metered,
        a_row("t-plain", at=LATER + timedelta(minutes=1)),
        replace(a_row("t-late", at=LATER + timedelta(days=2)), tokens_in=5, tokens_out=1),
    )

    async def go() -> tuple[MeteredRequest, ...]:
        bound = engine(empty)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                return await metered_between(session, start=LATER, end=LATER + timedelta(days=1))
        finally:
            await bound.dispose()

    assert run(go) == (
        MeteredRequest(
            trace_id="t-metered",
            principal="u_one",
            model="kimi-k2",
            agent_version=None,
            tokens_in=120,
            tokens_out=9,
        ),
    )


def test_a_window_holds_its_start_and_not_its_end_and_reads_back_as_observations(
    empty: str,
) -> None:
    """`[start, end)` on the partition key, oldest first, four columns and nothing else.

    Delete this and a request at midnight is measured on both days or on neither."""
    write_as_app(
        empty,
        a_row("t-before", at=LATER - timedelta(microseconds=1)),
        a_row("t-start", at=LATER, duration_ms=7.0),
        a_row("t-inside", at=LATER + timedelta(hours=1), status=RequestStatus.NOTHING_RETURNED),
        a_row("t-end", at=LATER + timedelta(days=1)),
    )

    found = read_as_app(empty, LATER, LATER + timedelta(days=1))

    assert found == (
        Observation(
            lane=Lane.FAST, status=RequestStatus.ANSWERED, duration_ms=7.0, received_at=LATER
        ),
        Observation(
            lane=Lane.FAST,
            status=RequestStatus.NOTHING_RETURNED,
            duration_ms=12.5,
            received_at=LATER + timedelta(hours=1),
        ),
    )


# --- the path -------------------------------------------------------------------------------


def client_on(database: str) -> Iterator[TestClient]:
    """The real application, answering through the real route into this database's ledger."""
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
    bound = engine(database)
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    try:
        with TestClient(app, raise_server_exceptions=False, backend_options=options) as client:
            app.state.gate = wired()
            app.state.tools = build_registry(source=SOURCE, records=OneRow())
            app.state.fast_path_rules = (PRICE, COST)
            app.state.request_recorders = (TelemetryRecorder(async_sessionmaker(bound)),)
            yield client
    finally:
        run(bound.dispose)


def ask(client: TestClient, pid: str, question: str) -> Response:
    answered: Response = client.post(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for(pid)}"},
        json={"question": question},
    )
    return answered


def readings(database: str, start: datetime, end: datetime) -> Sequence[Any]:
    async def go() -> Sequence[Any]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                return (await service_levels_between(session, start=start, end=end)).lanes
        finally:
            await bound.dispose()

    return run(go)


def test_requests_through_the_route_are_rows_and_a_service_level_reading_is_read_back(
    empty: str,
) -> None:
    """**M30.5.2 end to end.** Real requests through the real route, recorded by the lane into
    this database, and read back through the store query that feeds the service level reading.

    An answered question, a question about a column the asker may not read, and a question no
    rule matches are three rows; a request with no token is none. The withheld and the absent
    rows agree on every column but the id, the trace, the instant and the duration. The reading
    has three requests on the fast lane, all succeeded, too few for a percentile, and none on the
    other two lanes, which are present and unmeasured.

    Delete this and every half of the path can pass its own test while nothing reaches the
    ledger."""
    for client in client_on(empty):
        statuses = [
            ask(client, "u_wide", "what is the price of WEB-1001").status_code,
            ask(client, "u_narrow", "what is the cost of WEB-1001").status_code,
            ask(client, "u_narrow", "what colour is the sky").status_code,
            client.post(f"{API_PREFIX}/answer", json={"question": "x"}).status_code,
        ]

    assert statuses == [200, 200, 200, 401]
    rows = sql(
        empty,
        "SELECT principal, traffic_class, entitlement_hash, lane, status, cache_hit, "
        "agent_version, model, tokens_in, redaction_count, duration_ms > 0 "
        "FROM obs.request_telemetry ORDER BY received_at",
    )
    assert len(rows) == 3
    answered, withheld, absent = rows
    assert answered[0] == "u_wide" and answered[4] == "answered"
    assert withheld == absent
    assert withheld[0] == "u_narrow" and withheld[4] == "nothing_returned"
    assert withheld[6:10] == (None, None, None, None)
    assert withheld[10] is True

    now = datetime.now(UTC)
    fast, answer, task = readings(empty, now - timedelta(hours=1), now + timedelta(hours=1))
    assert (fast.objective.lane, fast.requests, fast.success_rate, fast.p95_ms) == (
        Lane.FAST,
        3,
        1.0,
        None,
    )
    assert (answer.requests, task.requests) == (0, 0)
    assert not fast.met and not answer.met and not task.met


def test_a_process_started_with_a_database_installs_the_ledger_recorder(database: str) -> None:
    """`lifespan` itself, against a real server: a process with a database finishes requests into
    the ledger recorder as well as the question recorder, bound to the pool it built.

    Delete this and a deployed process can start with no ledger recorder, an empty ledger, and
    every latency objective unmeasured with the store's tests still green."""
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
    app: FastAPI = create_app(
        Settings(env="development", database_url=database, run_migrations=False)
    )
    with TestClient(app, raise_server_exceptions=False, backend_options=options):
        ledger = [one for one in app.state.request_recorders if isinstance(one, TelemetryRecorder)]
        assert len(ledger) == 1
        assert ledger[0].sessions is app.state.db_sessions


def test_the_default_completion_is_the_one_the_lane_used() -> None:
    """The helper this file and `test_request_finish` build finished requests with finishes at
    `DONE`, which the mapping tests read as forty-two milliseconds. Asserted so that a change to
    the helper is a failure here rather than a wrong duration every test above agrees with.

    Delete this and `DONE` can move and the exact-duration assertions above move with it."""
    assert timedelta(milliseconds=42) == DONE - NOW
