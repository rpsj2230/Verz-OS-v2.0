"""The most expensive question shapes: counted by the lane, read from the ledger, joined to cost.

M21.3.4 in four layers, each tested where it decides something. The count: the answer lane counts
every reader call as it starts, so a withheld record and an absent one are one call each. The
shape: `QUESTION_SHAPE_FIELDS` is the lane and the tool count, and nothing a person typed. The
join: a cost names its request by trace id, and `shapes_by_request` resolves a shape for a trace
and a principal together. The report: `shape_report` filters by the reader's usage grant before
it groups, carries no count of anything, and puts a cost with no known shape on a line of its own.

The database half runs `0043` for real, records the costs of real lane runs, writes their ledger
rows through the real recorder, and reads the report back as the application role. It skips
without `DATABASE_URL`, and CI always sets it.

Task ids: M21.3.4
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import fields
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.console.spend_view import (
    A_COST_IS_JOINED_TO_ITS_OWN_REQUEST_AND_NOBODY_ELSES,
    A_COST_WHOSE_SHAPE_IS_UNKNOWN_IS_SHOWN_AND_NEVER_GUESSED,
    UNRECORDED_SHAPE,
    USAGE_AUTHORITY,
    Line,
    ShapeReport,
    SpendViewError,
    dearest,
    shape_report,
    spend_report,
)
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.answer import ToolCalls
from brain.gate.cache_key import CachedAnswer
from brain.gate.context import Channel, TrafficClass
from brain.gate.finish import A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS, Finished, Origin
from brain.ops.spend import (
    A_COST_NAMES_ITS_REQUEST_AND_COPIES_NOTHING_ABOUT_IT,
    Actual,
    Dimension,
    SpendError,
)
from brain.ops.spend_store import question_shape_report, recorded
from brain.ops.spend_store import record as record_cost
from brain.ops.telemetry import (
    A_QUESTION_SHAPE_IS_HOW_THE_REQUEST_RAN_AND_NEVER_WHAT_WAS_ASKED,
    A_TRACE_THAT_NAMES_TWO_SHAPES_NAMES_NONE,
    FAN_OUT_IS_NOT_A_SHAPE_UNTIL_A_REQUEST_THAT_FANS_OUT_FINISHES_SOMEWHERE,
    QUESTION_SHAPE_FIELDS,
    TELEMETRY_FIELDS,
    UNFILLABLE_TODAY,
    QuestionShape,
    TelemetryError,
    request_telemetry_of,
    shapes_by_request,
)
from brain.ops.telemetry_store import TelemetryRecorder
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, run, secured, sql
from tests.unit.test_answer_lane import ACME, NOW, OTHER, SEES_HOURS, SEES_NAME_ONLY, Rows, ents
from tests.unit.test_request_finish import OUTCOMES, Broken, Kept, asker, lane

DELIVERY = "delivery"
FINANCE = "finance"

#: A shape that read once, and one that read nothing, in the words the report shows them.
READ_ONCE = QuestionShape(Lane.FAST, 1).key
READ_NOTHING = QuestionShape(Lane.FAST, 0).key


def finished(
    trace: str,
    question: str = "hours left on Acme",
    *,
    pid: str = "p_priya",
    sees: Sequence[str] = SEES_HOURS,
    rows: Rows | None = None,
    cached: CachedAnswer | None = None,
) -> Finished:
    """Run the real lane once under this trace and hand back what its recorder was given."""
    kept = Kept()
    lane(
        question,
        reach=ents(*sees, principal=pid),
        origin=Origin(trace_id=trace, principal=asker(pid), channel=Channel.CONSOLE),
        recorders=(kept,),
        rows=rows,
        cached=cached,
    )
    (one,) = kept.seen
    return one


def cost(
    trace: str,
    minor: int,
    *,
    pid: str = "p_priya",
    department: str = DELIVERY,
    machine: bool = False,
) -> Actual:
    """One recorded cost for the request under this trace, through `Actual`'s own checks."""
    return Actual(
        principal_id=pid,
        principal_kind=PrincipalKind.SERVICE if machine else PrincipalKind.HUMAN,
        traffic=TrafficClass.AUTOMATION if machine else TrafficClass.HUMAN_INTERACTIVE,
        department=department,
        agent_id=None,
        model="a-model",
        lane=Lane.FAST,
        cost_minor=minor,
        at=NOW,
        trace_id=trace,
    )


def reader(*departments: str) -> EntitlementSet:
    """Somebody holding the usage grant over these departments, or over none at all."""
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(
            Grant(capability=USAGE_AUTHORITY, scope=Scope.department(one)) for one in departments
        ),
    )


def lines(report: ShapeReport) -> list[tuple[str, int]]:
    return [(one.key, one.cost_minor) for one in report.lines]


# --- the count, at the one completion point -------------------------------------------------

#: How many reads each way out of the lane starts. Keyed by `OUTCOMES`, and held to it below.
CALLS = {
    "answered": 1,
    "nothing matched": 0,
    "the record was withheld": 1,
    "the record does not exist": 1,
    "nothing is connected": 0,
    "served from the cache": 0,
}


@pytest.mark.parametrize("case", sorted(OUTCOMES))
def test_every_way_the_lane_finishes_records_the_reads_it_started(case: str) -> None:
    """**The count is what the lane did.** An answer and both kinds of nothing after a read are
    one call; a cache hit, nothing connected and a question no rule matched are none. Taken from
    the lane's own `Finished`, and carried unchanged into the ledger row.

    Parametrised over the lane's own table of outcomes, and the table here is held to it, so a
    new way out of the lane cannot arrive without a count being decided for it.

    Delete this and `tool_count` can be filled with a constant, and every shape in the report
    is one bucket named after a measurement nobody took."""
    assert set(CALLS) == set(OUTCOMES)
    kept = Kept()
    lane(**OUTCOMES[case], recorders=(kept,))

    (one,) = kept.seen
    assert one.tool_calls == CALLS[case]
    assert request_telemetry_of(one).tool_count == CALLS[case]


def test_a_read_that_raised_is_still_a_call_the_lane_started() -> None:
    """A source that is down still had a call made to it, and the fault reaches the recorders
    with that call counted. See `A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS`.

    Delete this and the counter can move after the await, and a request that spent a read on a
    dead source is recorded as having read nothing."""
    from tests.unit.test_answer_lane import CLIENT_TOOL

    kept = Kept()
    with pytest.raises(RuntimeError, match="source unreachable"):
        lane(readers={("laravel", "client"): CLIENT_TOOL.reader(Broken())}, recorders=(kept,))

    assert kept.seen[0].outcome is None
    assert kept.seen[0].tool_calls == 1


def test_a_withheld_record_an_absent_one_and_two_that_share_a_name_have_one_shape() -> None:
    """**DENIED and ABSENT in the shape.** A record whose answer field the asker may not read, a
    record that does not exist, and a name two records answer to are each one read, so their
    shapes are one shape and the report cannot separate them. The answered request is the
    positive sibling with the same shape, and a cache hit is the sibling with a different one.

    Delete this and the count can be taken from what came back, which is a count of rows, and
    the shape line becomes a count of records each person was refused."""
    narrow = SEES_NAME_ONLY
    withheld = request_telemetry_of(finished("t-w", sees=narrow, rows=Rows(ACME)))
    absent = request_telemetry_of(finished("t-a", sees=narrow, rows=Rows()))
    twice = request_telemetry_of(finished("t-2", rows=Rows(ACME, OTHER)))
    answered = request_telemetry_of(finished("t-y"))
    cached = request_telemetry_of(
        finished("t-c", cached=OUTCOMES["served from the cache"]["cached"])
    )

    assert A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS
    shape_of = {
        name: QuestionShape(one.lane, one.tool_count)
        for name, one in (
            ("withheld", withheld),
            ("absent", absent),
            ("twice", twice),
            ("answered", answered),
            ("cached", cached),
        )
    }
    assert shape_of["withheld"] == shape_of["absent"] == shape_of["twice"] == shape_of["answered"]
    assert shape_of["cached"] != shape_of["answered"]


def test_a_count_belongs_to_one_request_and_never_carries_into_the_next() -> None:
    """Two requests one after the other each record their own one read, not a running total.

    Delete this and the counter can be shared across requests, and the thousandth question of
    the day is recorded as having made a thousand calls."""
    kept = Kept()
    lane(recorders=(kept,))
    lane(recorders=(kept,))

    assert [one.tool_calls for one in kept.seen] == [1, 1]


def test_counted_readers_keep_their_keys_and_count_only_when_called() -> None:
    """The lane matches rules against the reader keys, so wrapping must not change them, and a
    reader handed over but never called is not a call.

    Delete this and a wrapper that renamed or dropped a key would turn every question into a
    rule nobody can match, with the count reading zero as if that were the truth."""
    from tests.unit.test_answer_lane import readers_for

    handed = readers_for(Rows(ACME))
    calls = ToolCalls()
    counted = calls.counting(handed)

    assert set(counted) == set(handed)
    assert calls.started == 0
    assert calls.counting({}) == {}


# --- what a shape is ------------------------------------------------------------------------


def test_a_shape_is_made_only_of_fields_the_ledger_fills_from_what_ran() -> None:
    """**A shape field nothing fills would be a lie, so there is none.** Both shape fields are
    declared on the ledger record, neither is in `UNFILLABLE_TODAY`, and `QuestionShape` has
    exactly those fields in that order. Fan-out is not among them and not on the record, for
    the reason its constant gives.

    Delete this and a shape can grow `fan_out` filled with a declared zero, or a field holding
    something a person typed."""
    assert set(QUESTION_SHAPE_FIELDS) <= set(TELEMETRY_FIELDS)
    assert not set(QUESTION_SHAPE_FIELDS) & set(UNFILLABLE_TODAY)
    assert tuple(one.name for one in fields(QuestionShape)) == QUESTION_SHAPE_FIELDS
    assert "fan_out" not in TELEMETRY_FIELDS
    assert FAN_OUT_IS_NOT_A_SHAPE_UNTIL_A_REQUEST_THAT_FANS_OUT_FINISHES_SOMEWHERE
    assert A_QUESTION_SHAPE_IS_HOW_THE_REQUEST_RAN_AND_NEVER_WHAT_WAS_ASKED

    record = request_telemetry_of(finished("t-shape"))
    built = QuestionShape(**{name: getattr(record, name) for name in QUESTION_SHAPE_FIELDS})
    assert built == QuestionShape(Lane.FAST, 1)


def test_a_shape_is_named_by_its_lane_and_its_count_and_refuses_a_negative_count() -> None:
    """The key is what a reader sees, so it is built from the two fields and from nothing else;
    and a negative count is a request that did not happen. The zero-call shape is the positive
    sibling of the refusal.

    Delete this and two different shapes can share a key and be summed into one line."""
    assert QuestionShape(Lane.FAST, 1).key == "fast lane, 1 tool call(s)"
    assert QuestionShape(Lane.ANSWER, 1).key != QuestionShape(Lane.FAST, 1).key
    assert QuestionShape(Lane.FAST, 0).key != QuestionShape(Lane.FAST, 1).key
    assert QuestionShape(Lane.FAST, 0).tool_count == 0
    with pytest.raises(TelemetryError, match="did not happen"):
        QuestionShape(Lane.FAST, -1)


def test_a_request_is_matched_on_its_trace_and_its_principal_together() -> None:
    """**Two people's requests under one proposed trace id each keep their own shape.** And one
    person's request recorded twice with the same shape is still one shape.

    Delete this and the shape map can key on the trace alone, and one person's cost reads the
    shape of somebody else's request."""
    found = shapes_by_request(
        [
            ("t-1", "p_priya", "fast", 1),
            ("t-1", "p_priya", "fast", 1),
            ("t-1", "p_bob", "fast", 0),
        ]
    )

    assert found == {
        ("t-1", "p_priya"): QuestionShape(Lane.FAST, 1),
        ("t-1", "p_bob"): QuestionShape(Lane.FAST, 0),
    }


def test_a_request_that_names_two_shapes_or_none_has_no_shape() -> None:
    """See `A_TRACE_THAT_NAMES_TWO_SHAPES_NAMES_NONE`. The same person's two requests under one
    trace with different counts resolve to nothing, and so does a row recorded before the lane
    counted. The single agreeing row beside them is the positive sibling.

    Delete this and one of two shapes is picked, and a cost is reported under a shape its
    request may not have had."""
    assert A_TRACE_THAT_NAMES_TWO_SHAPES_NAMES_NONE
    found = shapes_by_request(
        [
            ("t-two", "p_priya", "fast", 1),
            ("t-two", "p_priya", "fast", 0),
            ("t-old", "p_priya", "fast", None),
            ("t-one", "p_priya", "fast", 1),
        ]
    )

    assert found[("t-two", "p_priya")] is None
    assert found[("t-old", "p_priya")] is None
    assert found[("t-one", "p_priya")] == QuestionShape(Lane.FAST, 1)


# --- the report -----------------------------------------------------------------------------

SHAPES = shapes_by_request(
    [
        ("t-dear", "p_priya", "fast", 1),
        ("t-cheap", "p_priya", "fast", 0),
        ("t-also-dear", "p_priya", "fast", 1),
        ("t-hidden", "p_bob", "answer", 3),
    ]
)


def test_the_dearest_shapes_are_ranked_by_what_the_reader_may_see() -> None:
    """**The positive case.** Costs grouped by their request's shape, dearest first, with the
    total equal to the lines, and `dearest` slicing the shape report exactly as it slices the
    agent report.

    Delete this and every refusal below is satisfied by a report that shows nothing."""
    costs = [cost("t-dear", 500), cost("t-cheap", 20), cost("t-also-dear", 300)]

    report = shape_report(costs, SHAPES, reader(DELIVERY), now=NOW)

    assert lines(report) == [(READ_ONCE, 800), (READ_NOTHING, 20)]
    assert report.total_minor == 820
    assert dearest(report, 1) == (Line(key=READ_ONCE, cost_minor=800),)


def test_a_cost_the_reader_may_not_see_moves_no_line_and_no_total() -> None:
    """**DENIED and ABSENT in the report.** A cost in a department the reader's grant does not
    admit, with a shape nobody else has and with a shape the reader's own costs share, produces
    a report identical to the one built without it. Compared as whole objects, so a line, a total
    or any field that moved would fail it.

    Delete this and the shape report can group before it filters, and a line or a total hands
    over another department's spend by subtraction."""
    mine = [cost("t-dear", 500), cost("t-cheap", 20)]
    theirs = [
        cost("t-hidden", 9_000, pid="p_bob", department=FINANCE),
        cost("t-dear", 7_000, pid="p_priya", department=FINANCE),
    ]

    with_theirs = shape_report([*mine, *theirs], SHAPES, reader(DELIVERY), now=NOW)
    without = shape_report(mine, SHAPES, reader(DELIVERY), now=NOW)

    assert with_theirs == without
    assert shape_report([*mine, *theirs], SHAPES, reader(), now=NOW) == ShapeReport(
        lines=(), machine_included=False, total_minor=0
    )


def test_a_cost_reads_its_own_requests_shape_and_not_another_persons_under_its_trace() -> None:
    """See `A_COST_IS_JOINED_TO_ITS_OWN_REQUEST_AND_NOBODY_ELSES`. Somebody else's request under
    the same trace id has a different shape, and the cost is reported under its own.

    Delete this and the lookup can drop the principal, and a reader learns from a shape line
    that another person's request exists under an id they can see."""
    assert A_COST_IS_JOINED_TO_ITS_OWN_REQUEST_AND_NOBODY_ELSES
    # The other person's request first, so a lookup on the trace alone would find theirs.
    shapes = shapes_by_request(
        [("t-shared", "p_bob", "fast", 0), ("t-shared", "p_priya", "fast", 1)]
    )

    report = shape_report([cost("t-shared", 40)], shapes, reader(DELIVERY), now=NOW)

    assert lines(report) == [(READ_ONCE, 40)]


def test_a_cost_with_no_known_shape_is_its_own_line_and_the_total_still_reconciles() -> None:
    """See `A_COST_WHOSE_SHAPE_IS_UNKNOWN_IS_SHOWN_AND_NEVER_GUESSED`. A cost whose trace has no
    ledger row is shown under `UNRECORDED_SHAPE`, and the shape report totals to exactly what the
    agent report over the same rows does.

    Delete this and a cost with no shape can be dropped, and the shape report is quietly smaller
    than every other breakdown of the same spend."""
    assert A_COST_WHOSE_SHAPE_IS_UNKNOWN_IS_SHOWN_AND_NEVER_GUESSED
    costs = [cost("t-dear", 500), cost("t-nowhere", 11)]

    shapes = shape_report(costs, SHAPES, reader(DELIVERY), now=NOW)
    agents = spend_report(costs, reader(DELIVERY), Dimension.AGENT, now=NOW)

    assert lines(shapes) == [(READ_ONCE, 500), (UNRECORDED_SHAPE, 11)]
    assert shapes.total_minor == agents.total_minor
    # Held to something outside itself: a name, and never one a real shape could have.
    assert UNRECORDED_SHAPE.strip()
    assert UNRECORDED_SHAPE not in {QuestionShape(one, n).key for one in Lane for n in range(4)}


def test_machine_traffic_is_left_out_of_the_shapes_unless_asked_for_and_the_report_says_so() -> (
    None
):
    """The same default the spend report has, for the same reason: a nightly sync would be the
    dearest shape in the company. Included when asked, and the flag rides on the report.

    Delete this and the shape report silently counts automation as people's questions."""
    costs = [cost("t-dear", 500), cost("t-cheap", 9_000, machine=True)]

    people = shape_report(costs, SHAPES, reader(DELIVERY), now=NOW)
    everything = shape_report(costs, SHAPES, reader(DELIVERY), now=NOW, include_machine=True)

    assert lines(people) == [(READ_ONCE, 500)]
    assert people.machine_included is False
    assert lines(everything) == [(READ_NOTHING, 9_000), (READ_ONCE, 500)]
    assert everything.machine_included is True


def test_the_shape_report_carries_no_count_and_refuses_a_total_that_is_not_its_lines() -> None:
    """A line is a key and a figure, and the report is lines, a flag and their total. There is
    nowhere to put a number of requests, and a total over anything else is refused at
    construction. The report built above is the positive sibling.

    Delete this and a row count per shape can be added, which is a count of requests the reader
    may not otherwise know about."""
    assert {one.name for one in fields(ShapeReport)} == {"lines", "machine_included", "total_minor"}
    assert {one.name for one in fields(Line)} == {"key", "cost_minor"}
    with pytest.raises(SpendViewError, match="does not equal the lines"):
        ShapeReport(
            lines=(Line(key=READ_ONCE, cost_minor=5),), machine_included=False, total_minor=9
        )


def test_a_cost_names_the_trace_of_its_request_and_nothing_about_its_shape() -> None:
    """Item 59, Option B, as a property of the record: the cost carries the trace id and no
    field of a shape.

    Delete this and Option A can arrive one field at a time, copying the shape onto the cost
    where it drifts from the ledger."""
    assert A_COST_NAMES_ITS_REQUEST_AND_COPIES_NOTHING_ABOUT_IT
    declared = {one.name for one in fields(Actual)}
    assert "trace_id" in declared
    assert not declared & {"tool_count", "fan_out"}


# --- the database ---------------------------------------------------------------------------

DATABASE = "brain_test_m2134_question_shapes"


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """`0034` to `0036` for the cost table, `0039` for the ledger, and `0043` on top.

    Stamped between them, because neither table points at anything the stamped migrations
    build, and `0001` needs pgvector, which the scratch server may not have.
    """
    scratch = fresh(DATABASE)
    try:
        migrate(DATABASE, "stamp", "0033")
        migrate(DATABASE, "upgrade", "0036")
        migrate(DATABASE, "stamp", "0038")
        migrate(DATABASE, "upgrade", "0039")
        migrate(DATABASE, "stamp", "0042")
        migrate(DATABASE, "upgrade", "0043")
        # 0100 adds the front half's four columns the recorder now writes.
        migrate(DATABASE, "stamp", "0093")
        migrate(DATABASE, "upgrade", "0100")
        yield scratch
    finally:
        drop(DATABASE)


async def _write(url: str, requests: Sequence[Finished], costs: Sequence[Actual]) -> None:
    made = engine(url)
    try:
        recorder = TelemetryRecorder(async_sessionmaker(made))
        for one in requests:
            await recorder.finished(one)
        async with async_sessionmaker(made)() as session, session.begin():
            await session.execute(text("SET LOCAL ROLE brain_app"))
            for paid in costs:
                await record_cost(session, paid)
    finally:
        await made.dispose()


async def _report(url: str, reading: EntitlementSet) -> ShapeReport:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session, session.begin():
            await session.execute(text("SET LOCAL ROLE brain_app"))
            return await question_shape_report(session, reading, now=NOW + timedelta(hours=1))
    finally:
        await made.dispose()


def test_the_report_joins_real_costs_to_the_shapes_the_real_lane_recorded(database: str) -> None:
    """**End to end.** Six requests run through the real lane and their ledger rows are written
    by the real recorder; a cost is recorded for each, and one more for a trace the ledger never
    saw, through the real store as the application role. Read back as the application role, the
    delivery reader sees an answer, a withheld record and an absent one on one line, a cache hit
    and an unmatched question on another, and the unrecorded cost on its own. Another
    department's answer is on the finance reader's report and nowhere on theirs, and their
    report equals the one built in Python from their own costs alone.

    Delete this and the join can be right in every unit test and wrong against the table: a
    column the store never writes, a read the application role is not granted, or a ledger row
    whose tool count never reached the database."""
    requests = [
        finished("t-e2e-answered"),
        finished("t-e2e-withheld", sees=SEES_NAME_ONLY, rows=Rows(ACME)),
        finished("t-e2e-absent", sees=SEES_NAME_ONLY, rows=Rows()),
        finished("t-e2e-cached", cached=OUTCOMES["served from the cache"]["cached"]),
        finished("t-e2e-unmatched", "what colour is the sky"),
        finished("t-e2e-bob", pid="p_bob"),
    ]
    ours = [
        cost("t-e2e-answered", 700),
        cost("t-e2e-withheld", 40),
        cost("t-e2e-absent", 60),
        cost("t-e2e-cached", 5),
        cost("t-e2e-unmatched", 3),
        cost("t-e2e-lost", 11),
    ]
    theirs = [cost("t-e2e-bob", 9_000, pid="p_bob", department=FINANCE)]
    run(lambda: _write(database, requests, [*ours, *theirs]))

    delivery = run(lambda: _report(database, reader(DELIVERY)))
    finance = run(lambda: _report(database, reader(FINANCE)))

    assert lines(delivery) == [(READ_ONCE, 800), (UNRECORDED_SHAPE, 11), (READ_NOTHING, 8)]
    assert delivery.total_minor == 819
    assert lines(finance) == [(READ_ONCE, 9_000)]
    tool_counts = dict(sql(database, "SELECT trace_id, tool_count FROM obs.request_telemetry"))
    shapes = shapes_by_request(
        (one.origin.trace_id, one.origin.principal.id, "fast", tool_counts[one.origin.trace_id])
        for one in requests
    )
    assert delivery == shape_report(ours, shapes, reader(DELIVERY), now=NOW)


#: The previous release's insert: every column it knows about, and no trace id.
PREVIOUS_RELEASE_INSERT = (
    "INSERT INTO ops.spend_actual "
    "(principal_id, principal_kind, traffic, department, model, lane, cost_minor, at) "
    "VALUES ('p_x', 'human', 'human_interactive', 'elsewhere', 'm', 'fast', 1, now())"
)


async def _previous_release_writes_then_this_one_reads(url: str) -> None:
    """In one transaction as the application role, rolled back by whatever raises."""
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session, session.begin():
            await session.execute(text("SET LOCAL ROLE brain_app"))
            await session.execute(text(PREVIOUS_RELEASE_INSERT))
            await recorded(session)
    finally:
        await made.dispose()


def test_the_previous_releases_insert_survives_0043_and_its_row_is_never_read_as_linked(
    database: str,
) -> None:
    """**The expand half of a two-release change.** During a deploy the previous release's code
    runs against this schema, and its insert names no trace id: it succeeds, as the application
    role. Reading that row back is refused by `Actual`'s own trace check rather than reported
    under a trace nobody recorded. The transaction rolls back, and the column is nullable on
    the server, which `0043`'s `REQUIRED_IN_A_LATER_RELEASE` says is this release only.

    Delete this and 0043 can make the column NOT NULL, which `brain.deployment.compatibility`
    refuses and a deploy turns into refused inserts; or `actual_from` can fill in a trace, and
    an unlinked cost reads as a request that was recorded."""
    with pytest.raises(SpendError, match="could never be joined"):
        run(lambda: _previous_release_writes_then_this_one_reads(database))

    assert sql(database, "SELECT count(*) FROM ops.spend_actual WHERE principal_id = 'p_x'") == [
        (0,)
    ]
    assert sql(
        database,
        "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'ops' "
        "AND table_name = 'spend_actual' AND column_name = 'trace_id'",
    ) == [("YES",)]


def test_the_trace_column_leaves_row_level_security_and_the_policies_as_they_were(
    database: str,
) -> None:
    """Read back from the server: row-level security is still on, and the two policies `0034`
    created are the only ones, with the same commands and the same expressions.

    Delete this and a later edit to `0043` can add a narrower policy or disable security on the
    table, and `0035`'s argument that its view is no wider than its table stops being true."""
    assert secured(database, ("ops.spend_actual",)) == {"ops.spend_actual": True}
    assert sql(
        database,
        "SELECT policyname, cmd, qual, with_check FROM pg_catalog.pg_policies "
        "WHERE schemaname = 'ops' AND tablename = 'spend_actual' ORDER BY policyname",
    ) == [
        ("spend_actual_appendable", "INSERT", None, "true"),
        ("spend_actual_readable", "SELECT", "true", None),
    ]


def test_0043_comes_down_and_goes_back_up() -> None:
    """Up to `0043`, down to `0042`, up again, asking after the column and its index.

    Delete this and a downgrade that left the index behind fails the next upgrade on `CREATE`."""
    name = "brain_test_m2134_round_trip"
    present = (
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema = 'ops' AND table_name = 'spend_actual' AND column_name = 'trace_id'"
    )
    index = "SELECT to_regclass('ops.ix_spend_actual_trace_id') IS NOT NULL"
    url = fresh(name)
    try:
        migrate(name, "stamp", "0033")
        migrate(name, "upgrade", "0034")
        migrate(name, "stamp", "0042")
        migrate(name, "upgrade", "0043")
        assert sql(url, present) == [(1,)]
        assert sql(url, index) == [(True,)]
        migrate(name, "downgrade", "0042")
        assert sql(url, present) == [(0,)]
        assert sql(url, index) == [(False,)]
        migrate(name, "upgrade", "0043")
        assert sql(url, present) == [(1,)]
    finally:
        drop(name)
