"""A finished request, and the one question record it becomes, held without a database.

Three layers and each is tested where it decides something. The lane: every way out of
`answer_lane` reaches the recorders exactly once, and an origin naming somebody other than the
reach is refused before anything is read. The mapping: `question_of` reads who asked off the
resolved principal and never reads the outcome. The route: a question asked over HTTP is
recorded as the directory describes the asker, whatever the request carried, and a request the
gate refused is not recorded at all.

`tests/unit/test_question_store.py` holds the other half, which needs a server: the table, the
key that keeps a hop out, and the whole route writing to it.

Task ids: M37.3.2.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.adoption import (
    A_PERSON_WITH_NO_DEPARTMENT_IS_COUNTED_UNDER_NONE_RATHER_THAN_A_GUESS,
    A_REFUSED_REQUEST_IS_NOT_A_QUESTION_AND_A_REFUSED_RECORD_IS_ONE,
    Asked,
    adoption_by_department,
    question_of,
)
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app, request_recorders_for
from brain.core.entitlement import EntitlementSet
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.gate.answer import LANE, Answered, answer_lane
from brain.gate.cache_key import CachedAnswer
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.context import Channel
from brain.gate.finish import (
    A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO,
    Finished,
    FinishError,
    Origin,
    finish,
)
from brain.identity.bearer import TokenAuthority
from brain.knowledge.rows import RowQuery
from brain.ops.question_gap_store import GapRecorder
from brain.ops.question_store import QuestionRecorder
from brain.ops.sensitive_read_store import SensitiveReadRecorder
from brain.ops.telemetry_store import TelemetryRecorder
from brain.tables.adoption import QuestionAskedRow
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.unit.test_answer_lane import (
    ACME,
    CLIENT_TOOL,
    CLIENTS,
    HOURS,
    NOW,
    SEES_HOURS,
    SEES_NAME_ONLY,
    Rows,
    Sink,
    ents,
    readers_for,
)
from tests.unit.test_answer_route import HOURS as PRICE
from tests.unit.test_answer_route import OneRow
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SOURCE,
    Directory,
    Keys,
    NoCache,
    Store,
    Versions,
    token_for,
    verifier,
)

#: A trace id the audit ledger accepts, for the lane-level tests.
TRACE = "t-finish-1"

#: The six fields a question record holds. Written out rather than read from `Asked`, because
#: a list read from the thing it checks agrees with it whatever it holds.
QUESTION_FIELDS = frozenset(
    {"trace_id", "principal_id", "principal_kind", "channel", "department", "at"}
)


class Kept:
    """A `RequestRecorder` that keeps every finished request it is handed, in order."""

    def __init__(self, label: str = "kept", journal: list[str] | None = None) -> None:
        self.seen: list[Finished] = []
        self.label = label
        self.journal = journal if journal is not None else []

    async def finished(self, request: Finished) -> None:
        self.seen.append(request)
        self.journal.append(self.label)


def asker(
    pid: str = "p_priya",
    *,
    department: str | None = "delivery",
    kind: PrincipalKind = PrincipalKind.HUMAN,
) -> Principal:
    return Principal(
        id=pid,
        kind=kind,
        employment=Employment.SERVICE if kind is PrincipalKind.SERVICE else Employment.STAFF,
        display_name=f"Person {pid}",
        primary_department=department,
    )


def origin_for(pid: str = "p_priya", **kwargs: Any) -> Origin:
    return Origin(trace_id=TRACE, principal=asker(pid, **kwargs), channel=Channel.CONSOLE)


#: When the lane-level tests' requests finish: forty-two milliseconds after they were judged.
DONE = NOW + timedelta(milliseconds=42)


def done(
    origin: Origin,
    outcome: Answered | None = None,
    *,
    at: datetime = NOW,
    completed_at: datetime = DONE,
) -> Finished:
    """A finished request as the lane builds one, for the tests that build one by hand."""
    return Finished(
        origin,
        at,
        outcome,
        completed_at=completed_at,
        entitlement_hash=EntitlementSet(principal_id=origin.principal.id).ent_hash(),
        lane=LANE,
        tool_calls=0,
    )


class Broken:
    """A `RowSource` whose system is down, so the lane raises part way through."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        raise RuntimeError("source unreachable")


def lane(
    question: str = "hours left on Acme",
    *,
    reach: EntitlementSet | None = None,
    origin: Origin | None = None,
    recorders: Sequence[Kept] = (),
    rows: Rows | None = None,
    readers: Mapping[tuple[str, str], Any] | None = None,
    cached: CachedAnswer | None = None,
    completes_at: datetime = DONE,
) -> Answered:
    held = reach if reach is not None else ents(*SEES_HOURS)
    return asyncio.run(
        answer_lane(
            question,
            origin=origin if origin is not None else origin_for(held.principal_id),
            recorders=recorders,
            rules=(HOURS,),
            readers=readers_for(rows if rows is not None else Rows(ACME))
            if readers is None
            else readers,
            entitlement=held,
            policies={"client": CLIENTS.policy()},
            reachable_sources=("laravel",),
            sink=Sink(),
            now=NOW,
            clock=lambda: completes_at,
            cached=cached,
        )
    )


# --- the lane -------------------------------------------------------------------------------


OUTCOMES: dict[str, dict[str, Any]] = {
    "answered": {},
    "nothing matched": {"question": "what colour is the sky"},
    "the record was withheld": {"reach": ents(*SEES_NAME_ONLY)},
    "the record does not exist": {"rows": Rows()},
    "nothing is connected": {"readers": {}},
    "served from the cache": {
        "cached": CachedAnswer(
            key="k",
            payload="Acme has 37 hours.",
            stored_at=NOW - timedelta(minutes=6),
            source_epochs={},
        )
    },
}


@pytest.mark.parametrize("case", sorted(OUTCOMES))
def test_every_way_the_lane_finishes_reaches_the_recorders_exactly_once(case: str) -> None:
    """**The completion point is inside the lane and every exit passes through it.** An answer,
    each kind of abstention and a cache hit are recorded once, with the outcome the caller was
    handed, the origin it was given and the instant it judged at.

    Parametrised over the outcomes rather than written for the answer alone, because a record
    written only on the path that produces prose is a count that depends on whether the record
    existed, which is the leak `A_REFUSED_REQUEST_IS_NOT_A_QUESTION_AND_A_REFUSED_RECORD_IS_ONE`
    names.

    Delete this and the `finally` can become a line after the answer, and every abstention
    silently stops being a question."""
    kept = Kept()
    origin = origin_for()
    arguments = dict(OUTCOMES[case])
    answered = lane(**arguments, origin=origin, recorders=(kept,))

    assert len(kept.seen) == 1
    (finished,) = kept.seen
    assert finished.outcome is answered
    assert finished.origin == origin
    assert finished.at == NOW
    # M30.5.2: the instant the clock gave, the reach the lane answered at, and its budget.
    reach = arguments.get("reach", ents(*SEES_HOURS))
    assert finished.completed_at == DONE
    assert finished.entitlement_hash == reach.ent_hash()
    assert finished.lane is Lane.FAST


def test_the_outcomes_above_are_the_outcomes_they_are_named_for() -> None:
    """The parametrisation above is only worth its names if each case reaches the exit it is
    named for. A case that quietly answered would make the abstention half of that test a
    second copy of the answer half.

    Delete this and a change to the lane's fixtures can collapse five cases into one without
    the recording test noticing."""
    assert lane().composed is not None
    assert lane(cached=OUTCOMES["served from the cache"]["cached"]).from_cache is True
    for case in ("nothing matched", "the record was withheld", "the record does not exist"):
        assert lane(**OUTCOMES[case]).abstention is not None, case
    assert lane(readers={}).abstention is not None


def test_a_question_that_failed_part_way_is_still_a_question_somebody_asked() -> None:
    """A fault is ours and not the asker's, and they still asked. The recorder is handed the
    request with no outcome, which is how it tells a fault from an answer without being handed
    the exception, and the exception still reaches the caller.

    Delete this and a count built from the records drops on the day a source is down, and a
    department head reads that as their people asking less."""
    kept = Kept()

    with pytest.raises(RuntimeError, match="source unreachable"):
        lane(readers={("laravel", "client"): CLIENT_TOOL.reader(Broken())}, recorders=(kept,))

    assert len(kept.seen) == 1
    assert kept.seen[0].outcome is None
    assert kept.seen[0].completed_at == DONE


def test_a_question_answered_at_one_persons_reach_cannot_be_recorded_as_anothers() -> None:
    """See `A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO`. Refused before anything
    is read, so nothing is fetched, nothing is recorded and no frame exists for the pair.

    The positive sibling is every other lane test here, where origin and reach agree.

    Delete this and a caller can answer as the person whose reach is widest and record the
    question against somebody else."""
    kept = Kept()
    rows = Rows(ACME)

    with pytest.raises(FinishError) as refused:
        lane(origin=origin_for("p_somebody_else"), rows=rows, recorders=(kept,))

    assert A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO in str(refused.value)
    assert kept.seen == []
    assert rows.queries == []


def test_every_recorder_is_handed_the_request_once_in_the_order_given() -> None:
    """`finish` is the one place, so it has to reach all of them. A loop that stopped at the
    first, or ran one twice, would make every recorder after the question count wrong.

    Delete this and the second thing a finished request owes, the ledger's duration when it is
    built, can be silently skipped by the first."""
    journal: list[str] = []
    first, second = Kept("first", journal), Kept("second", journal)

    lane(recorders=(first, second))

    assert journal == ["first", "second"]
    assert len(first.seen) == len(second.seen) == 1


def test_finishing_with_no_recorders_is_an_answer_and_not_an_error() -> None:
    """A process with no database has nowhere to record, and still answers. The recorders are a
    required argument, not a non-empty one.

    Delete this and a guard refusing an empty tuple takes down every question on an install
    whose database is not configured yet."""
    assert asyncio.run(finish((), done(origin_for()))) is None
    assert lane(recorders=()).composed is not None


# --- what a finished request becomes --------------------------------------------------------


def test_a_question_is_the_resolved_principal_the_channel_the_trace_and_the_instant() -> None:
    """Every field of the record comes from what the gate decided: the principal's id, kind and
    department, the channel on the origin, the trace id and the instant the lane judged at.

    Delete this and `question_of` can take a department from somewhere that is not the
    directory's answer about the person."""
    # A service principal on a person's channel, so the kind has to come from the principal:
    # every other asker in this file is human, and the channel alone would say a person.
    service = asker("p_ops", department="ops", kind=PrincipalKind.SERVICE)
    finished = done(Origin(trace_id=TRACE, principal=service, channel=Channel.LARK))

    assert question_of(finished) == Asked(
        trace_id=TRACE,
        principal_id="p_ops",
        principal_kind=PrincipalKind.SERVICE,
        channel=Channel.LARK,
        department="ops",
        at=NOW,
    )


def test_a_refused_record_and_an_absent_one_become_the_same_question() -> None:
    """See `A_REFUSED_REQUEST_IS_NOT_A_QUESTION_AND_A_REFUSED_RECORD_IS_ONE`. Asked by the same
    person under the same trace, a question about a record they may not read and a question
    about a record that does not exist are one identical record, and so is a fault.

    Compared as whole records, so a field that differed would fail it whatever its name.

    Delete this and a record can grow an outcome field, which is a per-department count of
    what people were refused."""
    origin = origin_for()
    withheld, absent, broken = Kept(), Kept(), Kept()

    lane(reach=ents(*SEES_NAME_ONLY), origin=origin, recorders=(withheld,))
    lane(rows=Rows(), origin=origin, recorders=(absent,))
    with pytest.raises(RuntimeError):
        lane(
            readers={("laravel", "client"): CLIENT_TOOL.reader(Broken())},
            origin=origin,
            recorders=(broken,),
        )

    recorded = {question_of(one.seen[0]) for one in (withheld, absent, broken)}
    assert len(recorded) == 1
    assert None not in recorded
    assert A_REFUSED_REQUEST_IS_NOT_A_QUESTION_AND_A_REFUSED_RECORD_IS_ONE


def test_a_question_record_holds_who_asked_and_has_nowhere_to_put_what_came_back() -> None:
    """Six fields on the record and the same six columns on the table, and no seventh on either.
    A status, an abstention reason, an entity or a machine flag would each be a figure this
    record must not carry.

    Asserted on the dataclass and on the mapped table against a list written here, so neither
    can gain a column by agreeing with the other.

    Delete this and the next useful-looking column is an outcome."""
    assert {one.name for one in fields(Asked)} == QUESTION_FIELDS
    assert set(QuestionAskedRow.__table__.columns.keys()) == QUESTION_FIELDS


@pytest.mark.parametrize("department", [None, "", "   "])
def test_a_person_the_directory_gives_no_department_is_counted_under_none(
    department: str | None,
) -> None:
    """See `A_PERSON_WITH_NO_DEPARTMENT_IS_COUNTED_UNDER_NONE_RATHER_THAN_A_GUESS`. A blank
    department is the same absence as a missing one. The positive sibling is the test above.

    Delete this and a guessed department collects questions its head reads as their own
    people's."""
    finished = done(origin_for(department=department))

    assert question_of(finished) is None
    assert A_PERSON_WITH_NO_DEPARTMENT_IS_COUNTED_UNDER_NONE_RATHER_THAN_A_GUESS


@pytest.mark.parametrize("trace_id", ["", "has space", "ends-in-newline\n", "x" * 65])
def test_an_origin_under_a_trace_id_the_ledger_would_refuse_cannot_be_built(trace_id: str) -> None:
    """A record under an id the audit ledger refuses can never be joined to the rest of its
    request. `fullmatch`, so a trailing newline is refused as well.

    Delete this and a record can be written under an id no audit entry will ever carry."""
    with pytest.raises(FinishError):
        Origin(trace_id=trace_id, principal=asker(), channel=Channel.CONSOLE)


def test_an_origin_under_a_minted_or_longest_trace_id_is_built() -> None:
    """The positive sibling: a minted uuid4 hex and an id at the ledger's full width.

    Delete this and the guard above can refuse every id and still pass."""
    assert Origin(trace_id="0" * 32, principal=asker(), channel=Channel.API).trace_id == "0" * 32
    assert Origin(trace_id="x" * 64, principal=asker(), channel=Channel.API)


def test_a_finished_request_with_no_timezone_is_refused() -> None:
    """A naive instant files a question in the wrong day at either end of it.

    Delete this and a server running in local time moves questions between adoption windows."""
    with pytest.raises(FinishError, match="naive instant"):
        done(origin_for(), at=NOW.replace(tzinfo=None))
    assert done(origin_for()).at == NOW


# --- the recorder, without a server ---------------------------------------------------------


class FakeResult:
    def __init__(self, kept: str | None) -> None:
        self.kept = kept

    def scalar_one_or_none(self) -> str | None:
        return self.kept


class FakeSession:
    """Enough of an `AsyncSession` to see whether a statement ran and was committed."""

    def __init__(self, journal: list[str], kept: str | None = "kept") -> None:
        self.journal = journal
        self.kept = kept

    async def __aenter__(self) -> FakeSession:
        self.journal.append("open")
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: object) -> FakeResult:
        self.journal.append("execute")
        return FakeResult(self.kept)

    async def commit(self) -> None:
        self.journal.append("commit")


def test_a_wired_process_records_questions_and_one_with_no_database_records_nothing() -> None:
    """`lifespan` installs whatever this returns. A database gets the question recorder, bound
    to that database's sessions; no database gets nothing, because nothing could read it.

    Delete this and a wired process can install no recorder, and the adoption table stays
    empty with every test of the store still green."""
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker()

    assert request_recorders_for(None) == ()
    questions, ledger, gaps, reads = request_recorders_for(sessions)
    assert isinstance(questions, QuestionRecorder)
    assert questions.sessions is sessions
    # M30.5.2: the metadata ledger's recorder, beside the question recorder and not instead.
    assert isinstance(ledger, TelemetryRecorder)
    assert ledger.sessions is sessions
    # M27.7.18: the recorder of questions no connected source covers, beside both.
    assert isinstance(gaps, GapRecorder)
    assert gaps.sessions is sessions
    # M24.3.2: the sensitive read recorder, last, because it raises on a failed write.
    assert isinstance(reads, SensitiveReadRecorder)
    assert reads.sessions is sessions


def test_the_recorder_writes_and_commits_the_question_it_was_handed() -> None:
    """The positive half of the two refusals below, without a server: a question with a
    department is written and the write is committed. The server-side half is in
    `test_question_store`.

    Delete this and a recorder that never commits passes every test that reads its log."""
    journal: list[str] = []
    recorder = QuestionRecorder(lambda: FakeSession(journal))  # type: ignore[arg-type]

    asyncio.run(recorder.finished(done(origin_for())))

    assert journal == ["open", "execute", "commit"]


def test_a_second_record_under_a_trace_is_logged_as_already_recorded_and_a_first_is_not(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The store reports whether it kept the row, and a dropped one is said in the log, which is
    where somebody reconciling a hop count against the requests would look. The first record of
    a trace says nothing, which is the positive half.

    Delete this and the report can be inverted, so every new question is logged as a duplicate
    and every hop is silent."""
    journal: list[str] = []
    capsys.readouterr()

    first = QuestionRecorder(lambda: FakeSession(journal))  # type: ignore[arg-type]
    asyncio.run(first.finished(done(origin_for())))
    after_first = capsys.readouterr().out
    again = QuestionRecorder(lambda: FakeSession(journal, kept=None))  # type: ignore[arg-type]
    asyncio.run(again.finished(done(origin_for())))
    after_second = capsys.readouterr().out

    assert "question.already_recorded" not in after_first, after_first
    assert "question.already_recorded" in after_second, after_second


def test_the_recorder_opens_no_session_for_a_person_with_no_department() -> None:
    """Counted nowhere, and not written as a row with a guessed department either.

    Delete this and the no-department rule can be enforced by `Asked` refusing a blank value,
    which raises inside the lane's `finally` and fails the answer."""
    journal: list[str] = []
    recorder = QuestionRecorder(lambda: FakeSession(journal))  # type: ignore[arg-type]

    asyncio.run(recorder.finished(done(origin_for(department=None))))

    assert journal == []


def test_a_question_that_cannot_be_written_is_logged_and_does_not_fail_the_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """See `A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT` in
    `brain.ops.question_store`. The failure is a warning naming the trace, so a short figure
    can be explained.

    `capsys` for the reason `test_answer_route` gives: structlog writes to stdout.

    Delete this and a database hiccup turns every answered question into a fault."""

    def unreachable() -> FakeSession:
        raise ConnectionError("database gone")

    capsys.readouterr()
    recorder = QuestionRecorder(unreachable)  # type: ignore[arg-type]

    asyncio.run(recorder.finished(done(origin_for())))

    written = capsys.readouterr().out
    assert "question.unrecorded" in written, written
    assert TRACE in written, written


# --- the route ------------------------------------------------------------------------------


class DepartmentlessDirectory(Directory):
    """The test directory, with one person it gives no department."""

    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        found = await super().principal_for_subject(issuer, subject)
        if found is not None and found.id == "u_elsewhere":
            return found.model_copy(update={"primary_department": None})
        return found


def wired() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER,
            audience=AUDIENCE,
            keys=Keys(),
            verify=verifier,
            directory=DepartmentlessDirectory(),
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@pytest.fixture
def routed() -> Iterator[tuple[TestClient, Kept]]:
    """The real application, its answer route, and a recorder that keeps what it is handed."""
    kept = Kept()
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = wired()
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.fast_path_rules = (PRICE,)
        app.state.request_recorders = (kept,)
        yield client, kept


def post(
    client: TestClient,
    pid: str = "u_wide",
    *,
    text: str = "what is the price of WEB-1001",
    claims: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Response:
    sent = {"authorization": f"Bearer {token_for(pid, claims=claims)}", **(headers or {})}
    answered: Response = client.post(f"{API_PREFIX}/answer", headers=sent, json={"question": text})
    return answered


def recorded(kept: Kept) -> list[Asked | None]:
    return [question_of(one) for one in kept.seen]


def test_a_question_asked_over_http_is_recorded_once_as_the_directory_describes_the_asker(
    routed: tuple[TestClient, Kept],
) -> None:
    """**The request path calling the writer.** One POST, one record: the directory's principal
    and department, the kind it gives, the channel the token's session implies, and the trace
    id the response hands back.

    Delete this and the route can stop passing its recorders to the lane, and every other
    recording test still passes against the lane directly."""
    client, kept = routed

    answered = post(client)

    assert answered.status_code == 200
    assert recorded(kept) == [
        Asked(
            trace_id=answered.headers["x-trace-id"],
            principal_id="u_wide",
            principal_kind=PrincipalKind.HUMAN,
            channel=Channel.CONSOLE,
            department="web",
            at=kept.seen[0].at,
        )
    ]


def test_a_request_the_gate_refused_is_not_recorded_as_a_question(
    routed: tuple[TestClient, Kept],
) -> None:
    """See `A_REFUSED_REQUEST_IS_NOT_A_QUESTION_AND_A_REFUSED_RECORD_IS_ONE`. Not signed in, an
    empty question, a question longer than the cache can key, and a question put in a URL are
    all turned away before the lane, and none of them is a record.

    The positive sibling is the test above, through the same fixture.

    Delete this and a flood of unauthenticated requests reads as adoption."""
    client, kept = routed

    unsigned = client.post(f"{API_PREFIX}/answer", json={"question": "what is the price of X"})
    empty = post(client, text="")
    too_long = post(client, text="a" * (MAX_QUESTION_CHARS + 1))
    in_a_url = client.get(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for('u_wide')}"},
        params={"question": "what is the price of WEB-1001"},
    )

    assert (unsigned.status_code, empty.status_code, too_long.status_code) == (401, 422, 422)
    assert in_a_url.status_code == 405
    assert kept.seen == []


def test_a_caller_who_reaches_nothing_is_recorded_exactly_as_one_who_reaches_the_record(
    routed: tuple[TestClient, Kept],
) -> None:
    """DENIED and ABSENT on the wire. One person reaches the price list and is answered; another
    holds nothing over it and is told nothing was found. Their records differ in who asked and
    under which trace, and in nothing else.

    Delete this and the route can pass the lane a recorder that skips a question the reach
    turned into nothing."""
    client, kept = routed

    post(client, "u_wide")
    post(client, "u_none")

    reached, refused = recorded(kept)
    assert reached is not None and refused is not None
    assert replace(refused, trace_id=reached.trace_id, principal_id="u_wide", at=reached.at) == (
        reached
    )


def test_a_machine_asking_over_the_api_is_recorded_and_counted_as_nobody(
    routed: tuple[TestClient, Kept],
) -> None:
    """A token with no session is the API channel, which `traffic_class_for` declares automation,
    so the question is recorded, because it reached the lane, and adoption counts it as nobody
    asking. The console question beside it is counted, which is the positive half.

    Delete this and an integration polling the API makes its owner's department look like the
    keenest in the company."""
    client, kept = routed

    post(client, "u_wide", claims={"sid": None})
    post(client, "u_narrow")

    machine, person = recorded(kept)
    assert machine is not None and person is not None
    assert machine.channel is Channel.API
    assert machine.machine is True
    assert person.machine is False
    window = {"start": person.at - timedelta(days=1), "end": person.at + timedelta(days=1)}
    (line,) = adoption_by_department([machine, person], frozenset({"web"}), **window)
    assert (line.questions, line.people) == (1, 1)


def test_nothing_the_request_carries_can_set_the_department_it_is_recorded_under(
    routed: tuple[TestClient, Kept],
) -> None:
    """The department is the directory's. A token claiming another department and a header
    naming one change nothing about the record.

    Delete this and a caller files their questions under whichever department they choose, and
    the adoption report is whatever its readers were told."""
    client, kept = routed

    post(
        client,
        claims={"department": "hr", "primary_department": "hr"},
        headers={"x-department": "hr"},
    )

    (one,) = recorded(kept)
    assert one is not None
    assert one.department == "web"


def test_a_person_with_no_department_finishes_the_request_and_is_counted_nowhere(
    routed: tuple[TestClient, Kept],
) -> None:
    """The lane still finishes, the recorder is still handed the request, and no question is
    built from it. The answer is unaffected.

    Delete this and a principal with no department either fails their own question or is
    counted in a department somebody picked."""
    client, kept = routed

    answered = post(client, "u_elsewhere")

    assert answered.status_code == 200
    assert len(kept.seen) == 1
    assert recorded(kept) == [None]


def test_a_trace_id_the_caller_proposed_is_the_one_the_question_is_recorded_under(
    routed: tuple[TestClient, Kept],
) -> None:
    """The middleware accepts a proposed id that fits the ledger's grammar, and the record is
    filed under the id the system actually bound, which is the one every log line and the
    response carry. A delegated hop finishing under the root's id is one question for that
    reason; `test_question_store` shows the table keeping it to one row.

    Delete this and the record can be filed under a freshly minted id while the logs carry the
    caller's, and nothing joins the two."""
    client, kept = routed

    answered = post(client, headers={"x-trace-id": "caller-chosen-1"})

    assert answered.headers["x-trace-id"] == "caller-chosen-1"
    (one,) = recorded(kept)
    assert one is not None
    assert one.trace_id == "caller-chosen-1"


def test_a_process_built_without_a_database_answers_with_no_recorders_installed() -> None:
    """`lifespan` installs no recorder without a database, and the route reads the empty tuple
    rather than failing.

    Delete this and an install whose database is not configured yet answers 500 to every
    question."""
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as client:
        assert app.state.request_recorders == ()
        app.state.gate = wired()
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.fast_path_rules = (PRICE,)
        assert post(client).status_code == 200


def test_the_instant_a_question_is_recorded_at_is_the_one_its_reach_was_judged_at(
    routed: tuple[TestClient, Kept],
) -> None:
    """The lane reads no clock, so the record is dated by the route's `now`, which is also when
    the entitlements were resolved. Bounded by the wall clock either side of the request.

    Delete this and a record can be dated by a fixture's clock or by nothing."""
    client, kept = routed
    before = datetime.now(UTC)

    post(client)

    after = datetime.now(UTC)
    assert before <= kept.seen[0].at <= after


def test_a_naive_completion_instant_is_refused_and_a_late_or_early_one_is_not() -> None:
    """M30.5.2. A clock with no timezone is a wiring fault identical for every request and fails
    the first test that runs the lane. A completion instant before the judged one is not refused
    here, because `Finished` is built in the lane's `finally` and refusing would turn an answer
    into a fault over a clock that stepped backwards; the ledger's record refuses the negative
    duration instead, and its recorder logs it.

    Delete this and either a naive clock reaches a subtraction that raises inside every
    recorder, or the ordering check moves here and fails answered questions."""
    with pytest.raises(FinishError, match="naive completion instant"):
        done(origin_for(), completed_at=DONE.replace(tzinfo=None))
    assert done(origin_for(), completed_at=NOW - timedelta(seconds=1)).completed_at < NOW
    assert done(origin_for()).completed_at == DONE


def test_the_lane_reads_its_clock_once_after_the_outcome_exists_and_before_any_recorder() -> None:
    """M30.5.2. The completion instant is taken when the outcome exists, and every recorder is
    handed that one instant, so none of them is timed by the recorders before it.

    A clock that counts its reads shows both halves: one read for a request, and the first
    recorder's instant equal to the second's.

    Delete this and the clock can be read inside each recorder, or before the outcome, and the
    ledger's duration includes somebody else's database write or excludes the lane."""
    reads: list[datetime] = []

    def clock() -> datetime:
        reads.append(DONE + timedelta(milliseconds=len(reads)))
        return reads[-1]

    first, second = Kept("first"), Kept("second")
    answered = asyncio.run(
        answer_lane(
            "hours left on Acme",
            origin=origin_for(),
            recorders=(first, second),
            rules=(HOURS,),
            readers=readers_for(Rows(ACME)),
            entitlement=ents(*SEES_HOURS),
            policies={"client": CLIENTS.policy()},
            reachable_sources=("laravel",),
            sink=Sink(),
            now=NOW,
            clock=clock,
        )
    )

    assert answered.composed is not None
    assert reads == [DONE]
    assert first.seen[0].completed_at == second.seen[0].completed_at == DONE


def test_a_question_asked_over_http_finishes_at_a_wall_clock_instant_after_it_was_judged(
    routed: tuple[TestClient, Kept],
) -> None:
    """M30.5.2. The route hands the lane the wall clock, so the completion instant falls after
    the judged instant and inside the request, and the difference is the duration the ledger
    records.

    Delete this and the route can hand the lane its own judged instant as the clock, and every
    request is recorded as taking no time at all."""
    client, kept = routed
    before = datetime.now(UTC)

    post(client)

    after = datetime.now(UTC)
    (finished,) = kept.seen
    assert before <= finished.at < finished.completed_at <= after
