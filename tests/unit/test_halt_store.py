"""`ops.halt` read in one place, decided in one place, and asked by every path that starts work.

The first half runs anywhere. It reads the source to hold the store to being the one reader of
the table and the paths that start work to asking the one decider, then holds the decider to
what it may say: nothing halted with no database configured, halted when one is configured and
cannot be read, a refusal that names neither the reason nor who stopped it, and a scoped stop
that reaches only its own department.

The second half builds PostgreSQL to head and works as the application role: a stop that needs no
words and a resume that does, a halt read back through an engine that did not write it, the Stop
screen's routes as three kinds of administrator use them, and the answer route turning a question
away in the halt's own sentence.

Task ids: M27.15.10, M27.15.15, M27.15.16, M27.15.2
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.halt import (
    HALT_CAPABILITY,
    MINIMUM_REASON,
    NOTHING_HALTED,
    Halt,
    HaltScope,
    HaltState,
    in_force,
    stop_everything,
)
from brain.ops.halt_store import (
    STOPPED_FROM_THE_CONSOLE,
    HaltRefusedError,
    Work,
    may_act,
    read_state,
    refusal_for,
    refusal_in,
    resume,
    stop,
)
from brain.tables.audit import attributed_to
from tests.unit.test_answer_route_model import client as client
from tests.unit.test_answer_route_model import transport as transport
from tests.unit.test_model_calls import Scripted

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "brain"

#: Far outside any plausible wall clock. See CLAUDE.md on a fixture with a date in it.
NOW = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
LATER = datetime(2999, 1, 1, 10, 0, tzinfo=UTC)

#: What a person is told when the halts cannot be read, from the domain rather than spelled here.
CANNOT_CONFIRM = HaltState.unknown().refusal()

#: A reason long enough for the domain's floor, and words that must never reach a refused person.
BECAUSE = "the account was phished on Tuesday"
FIXED = "the cause was found and the token revoked"


def reader(principal_id: str, scope: Scope | None) -> EntitlementSet:
    """A reader holding the stop capability in `scope`, or nothing when `scope` is None."""
    grants = () if scope is None else (Grant(capability=HALT_CAPABILITY, scope=scope),)
    return EntitlementSet(principal_id=principal_id, grants=grants)


def run[T](work: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(work())  # type: ignore[arg-type]


# ------------------------------------------------------------------ one reader, one decider


def _modules() -> Iterator[tuple[Path, ast.Module]]:
    for path in sorted(SRC.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_only_the_halt_store_reads_the_halt_table() -> None:
    """**ONE_READER_AND_ONE_DECIDER, the reader half.** No module but the store imports the
    table's model, builds the store's select, or names `ops.halt` after FROM in a string. Delete
    this and a second reader can be added that treats an unreadable store as nothing stopped,
    which is the mistake made in the path nobody exercised until the incident that needed it."""
    allowed = {SRC / "ops" / "halt_store.py", SRC / "tables" / "__init__.py"}
    importing, selecting, raw = [], [], []
    for path, tree in _modules():
        if path in allowed or path == SRC / "tables" / "halt.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "brain.tables.halt":
                importing.append(path.relative_to(ROOT).as_posix())
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "latest_halt_acts":
                selecting.append(path.relative_to(ROOT).as_posix())
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "from ops.halt" in " ".join(node.value.lower().split())
            ):
                raw.append(path.relative_to(ROOT).as_posix())

    assert (importing, selecting, raw) == ([], [], [])
    store = ast.parse((SRC / "ops" / "halt_store.py").read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.ImportFrom) and node.module == "brain.tables.halt"
        for node in ast.walk(store)
    )


def _calls_in(module: str, function: str) -> set[str]:
    path = SRC.joinpath(*module.split(".")[1:]).with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    (found,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function
    ]
    return {
        node.func.id
        for node in ast.walk(found)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


@pytest.mark.parametrize(
    ("module", "function", "asks"),
    [
        ("brain.api_routes", "answered_for", {"read_state", "refusal_in"}),
        ("brain.ops.automation_run_store", "run_one", {"read_state", "refusal_in"}),
        ("brain.ops.connector_sync_run", "sync_on", {"read_state", "refusal_in"}),
        ("brain.ops.live_read_run", "live_records_for", {"read_state", "refusal_in"}),
    ],
)
def test_every_path_that_starts_work_asks_the_one_decider(
    module: str, function: str, asks: set[str]
) -> None:
    """**ONE_READER_AND_ONE_DECIDER, the decider half.** An answer (web and every chat channel go
    through `answered_for`), an automation, a scheduled connector read and a live read each call
    the store, by the call expression in the function and not by a word nearby. Delete this and a
    path can stop asking, and a stop reads as working on the screen while that work carries on."""
    assert asks <= _calls_in(module, function)


# ------------------------------------------------------------------ what the decider says


def test_a_process_with_no_database_configured_has_nothing_halted() -> None:
    """**NO_DATABASE_CONFIGURED_MEANS_NOTHING_COULD_HAVE_BEEN_HALTED, the admitting half.** With
    no database there is no table a halt could be in, so the state is known and empty and work
    starts. Delete this and the rule can be widened by accident into refusing every process
    built without a database, or narrowed into the next test's case."""
    assert run(lambda: read_state(None)) is NOTHING_HALTED
    assert run(lambda: refusal_for(None, Work(person="u_one", department="sales"))) == ""


def test_a_configured_database_that_cannot_be_read_refuses_everything() -> None:
    """**The refusing half.** A database is configured and does not answer: the state is unknown,
    and every piece of work is told the system cannot confirm whether it was stopped. Delete this
    and a database outage reads as nothing stopped during exactly the incident somebody stopped
    the system for."""
    engine = create_async_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    sessions = async_sessionmaker(engine)

    async def ask() -> tuple[HaltState, str, str]:
        try:
            state = await read_state(sessions)
            told = await refusal_for(sessions, Work(person="u_one"))
            nothing = await refusal_for(sessions, Work())
            return state, told, nothing
        finally:
            await engine.dispose()

    state, told, nothing = run(ask)

    assert state.known is False
    assert told == nothing == CANNOT_CONFIRM != ""


def test_a_refusal_names_the_scope_and_never_the_reason_or_who_stopped_it() -> None:
    """The person refused is told they were stopped and nothing an administrator wrote. Delete
    this and the reason, which routinely names a customer or a defect, reaches the person the
    halt was about."""
    halt = Halt(
        scope=HaltScope.PERSON, target="u_one", declared_by="u_admin", at=NOW, reason=BECAUSE
    )

    told = refusal_in(in_force([halt]), Work(person="u_one", department="sales"))

    assert told != ""
    assert BECAUSE not in told
    assert "u_admin" not in told


def test_a_department_halt_stops_that_department_and_no_other() -> None:
    """**M27.15.2 and M27.15.16.** A department's halt refuses work whose department it is and
    admits a colleague elsewhere; a halt on everything refuses both. Delete this and a department
    stop can widen to everybody, or stop nobody."""
    sales = Halt(
        scope=HaltScope.DEPARTMENT, target="sales", declared_by="u_admin", at=NOW, reason=BECAUSE
    )
    everything = stop_everything(declared_by="u_admin", at=NOW, reason=BECAUSE)

    assert refusal_in(in_force([sales]), Work(person="u_one", department="sales")) != ""
    assert refusal_in(in_force([sales]), Work(person="u_two", department="web")) == ""
    assert refusal_in(in_force([sales]), Work(person="u_two")) == ""
    assert refusal_in(in_force([everything]), Work(person="u_two", department="web")) != ""


def test_a_scoped_stop_reaches_its_own_department_and_nothing_wider() -> None:
    """**A_SCOPED_STOP_STOPS_ONLY_WHAT_ITS_SCOPE_NAMES.** The stop held in one department may stop
    that department and not another, and not everything; held unscoped it may stop all three;
    not held, none. Delete this and a department administrator can stop the whole install."""
    scoped = reader("u_admin", Scope.department("web"))
    whole = reader("u_owner", Scope.unrestricted())
    nobody = reader("u_none", None)

    assert may_act(scoped, HaltScope.DEPARTMENT, "web", NOW)
    assert not may_act(scoped, HaltScope.DEPARTMENT, "finance", NOW)
    assert not may_act(scoped, HaltScope.EVERYTHING, "", NOW)
    assert not may_act(scoped, HaltScope.PERSON, "u_one", NOW)
    assert all(
        may_act(whole, scope, target, NOW)
        for scope, target in (
            (HaltScope.DEPARTMENT, "finance"),
            (HaltScope.EVERYTHING, ""),
            (HaltScope.PERSON, "u_one"),
        )
    )
    assert not may_act(nobody, HaltScope.DEPARTMENT, "web", NOW)


def test_the_fixed_stop_reason_passes_the_floor_a_written_one_must() -> None:
    """**A_STOP_NEEDS_NO_WORDS_AND_A_RESUME_DOES.** The sentence a wordless stop is stored with is
    held against the domain's own floor, not against itself, and builds a halt. Delete this and
    the sentence can be shortened under the floor, and every one-press stop is then refused by
    the domain at the moment it is needed."""
    assert len(STOPPED_FROM_THE_CONSOLE.strip()) >= MINIMUM_REASON
    halt = stop_everything(declared_by="u_admin", at=NOW, reason=STOPPED_FROM_THE_CONSOLE)
    assert halt.reason == STOPPED_FROM_THE_CONSOLE


def test_an_axis_nothing_asks_is_refused_before_anything_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**M27.15.16.** Every axis is asked today, so this takes one away: a stop on an axis nothing
    asks is refused before anything is written rather than stored as a halt that refuses nothing.
    Delete this and the day an axis is added to `HaltScope` and to nothing that starts work, the
    screen can show it stopped while it keeps working."""
    import brain.ops.halt_store as halt_store

    owner = reader("u_owner", Scope.unrestricted())
    monkeypatch.setattr(halt_store, "ENFORCED_AXES", frozenset(set(HaltScope) - {HaltScope.AGENT}))

    with pytest.raises(HaltRefusedError, match="agent"):
        run(
            lambda: stop(
                cast("async_sessionmaker[AsyncSession]", None),
                owner,
                scope=HaltScope.AGENT,
                target="a_helper",
                reason="",
                now=NOW,
            )
        )


def test_an_agent_halt_stops_that_agent_s_work_and_no_other() -> None:
    """**M13.7.3.** A halt on one agent refuses work that names it, whoever asks and from which
    department, and admits another agent's work and work no agent does. `Work.agent` is optional,
    so a caller that names no agent is unaffected. Delete this and an agent halt can stop
    everybody's questions, or nothing."""
    agent = Halt(
        scope=HaltScope.AGENT, target="a_helper", declared_by="u_admin", at=NOW, reason=BECAUSE
    )
    state = in_force([agent])

    assert refusal_in(state, Work(person="u_one", department="sales", agent="a_helper")) != ""
    assert refusal_in(state, Work(person="u_two", department="web", agent="a_helper")) != ""
    assert refusal_in(state, Work(person="u_one", department="sales", agent="a_other")) == ""
    assert refusal_in(state, Work(person="u_one", department="sales")) == ""


def test_a_chat_channel_tells_a_halted_person_the_halt_s_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every chat channel answers through `answered_for`, and a halted outcome is sent as its own
    sentence and counted as no answer. Delete this and a chat can render a halted question as an
    empty answer, or crash on an outcome it did not expect."""
    from brain import chat_answer
    from brain.api_routes import Halted
    from brain.core.principal import Employment, Principal, PrincipalKind
    from brain.gate.context import Channel

    async def halted(*args: object) -> Halted:
        del args
        return Halted(CANNOT_CONFIRM)

    monkeypatch.setattr(chat_answer, "answered_for", halted)
    answerer = chat_answer.ChatAnswerer.__new__(chat_answer.ChatAnswerer)
    answerer._request = cast("Any", SimpleNamespace())
    person = Principal(
        id="u_one", kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name="One"
    )
    inbound = SimpleNamespace(
        event=SimpleNamespace(channel=Channel.SLACK),
        address=SimpleNamespace(question="what is the leave policy", agent_id=None),
    )

    reply = run(
        lambda: answerer._ask(
            person, EntitlementSet(principal_id="u_one", grants=()), cast("Any", inbound), NOW
        )
    )

    assert (reply.text, reply.answered) == (CANNOT_CONFIRM, False)


# ------------------------------------------------------------------ on PostgreSQL


@pytest.fixture
def database() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_halt_store") as url:
        yield url


def _sessions(url: str) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    from brain.session import make_session_factory
    from tests.unit.test_suspension_store import app_engine

    engine = app_engine(url)
    return engine, make_session_factory(engine)


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    """One piece of work as the application role, on an engine of its own, disposed after."""

    async def go() -> T:
        engine, sessions = _sessions(url)
        try:
            return await work(sessions)
        finally:
            await engine.dispose()

    return asyncio.run(go())


@pytest.mark.needs_db
def test_on_a_real_database_a_stop_needs_no_words_and_a_resume_does(database: str) -> None:
    """**A_STOP_NEEDS_NO_WORDS_AND_A_RESUME_DOES, and M27.15.10 and M27.15.15.** A stop with no
    reason is stored with the fixed sentence, at once; a resume with none is refused and writes
    nothing; a resume with one lifts it, says it overrides somebody else's stop, and the work is
    admitted again. Two rows and two ledger entries. Delete this and a stop can need typing
    before it works, or a halt can be lifted with nothing for the next reader to go on."""
    from tests.fixtures.scratch_postgres import sql

    owner = reader("u_owner", Scope.unrestricted())
    other = reader("u_other", Scope.unrestricted())

    async def work(sessions: async_sessionmaker[AsyncSession]) -> tuple[Halt, str, str, bool]:
        stopped = await stop(
            sessions,
            owner,
            scope=HaltScope.EVERYTHING,
            target="",
            reason="",
            now=NOW,
            attributed=attributed_to(
                actor_id="u_owner", ent_hash=owner.ent_hash(), trace_id="t-stop"
            ),
        )
        while_stopped = await refusal_for(sessions, Work(person="u_one"))
        with pytest.raises(HaltRefusedError):
            await resume(
                sessions, other, scope=HaltScope.EVERYTHING, target="", reason="  ", now=LATER
            )
        lifted = await resume(
            sessions, other, scope=HaltScope.EVERYTHING, target="", reason=FIXED, now=LATER
        )
        after = await refusal_for(sessions, Work(person="u_one"))
        return stopped, while_stopped, after, lifted.overrides_somebody_else()

    stopped, while_stopped, after, overrides = through(database, work)

    assert stopped.reason == STOPPED_FROM_THE_CONSOLE
    assert while_stopped != "" and after == ""
    assert overrides is True
    assert sql(database, "SELECT act, actor_id, reason FROM ops.halt ORDER BY at") == [
        ("halt", "u_owner", STOPPED_FROM_THE_CONSOLE),
        ("resume", "u_other", FIXED),
    ]
    assert sql(
        database,
        "SELECT actor_id, ent_hash, trace_id FROM obs.audit_entry WHERE action = 'halt'"
        " ORDER BY seq",
    )[0] == ("u_owner", owner.ent_hash(), "t-stop")
    assert sql(database, "SELECT count(*) FROM obs.audit_entry WHERE action = 'halt'") == [(2,)]


@pytest.mark.needs_db
def test_a_halt_survives_a_restart(database: str) -> None:
    """**The literal restart.** A department is stopped through one engine, which is disposed,
    and an engine that wrote nothing reads it back and refuses that department's work and no
    other's. Delete this and a halt held anywhere but the table, which a deploy undoes, passes
    every other test here."""
    scoped = reader("u_admin", Scope.department("sales"))

    async def write(sessions: async_sessionmaker[AsyncSession]) -> None:
        await stop(sessions, scoped, scope=HaltScope.DEPARTMENT, target="sales", reason="", now=NOW)

    async def read(sessions: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
        return (
            await refusal_for(sessions, Work(person="u_one", department="sales")),
            await refusal_for(sessions, Work(person="u_two", department="web")),
        )

    through(database, write)
    sales, web = through(database, read)

    assert sales != ""
    assert web == ""


@pytest.mark.needs_db
def test_a_scoped_reader_writes_nothing_beyond_their_department(database: str) -> None:
    """The store refuses before it writes: a stop held in one department cannot stop everything
    or another department, and no row is left either time. Delete this and a refused stop can be
    half-written, a row in force with nobody having been allowed to declare it."""
    from tests.fixtures.scratch_postgres import sql

    scoped = reader("u_admin", Scope.department("web"))

    async def work(sessions: async_sessionmaker[AsyncSession]) -> None:
        for scope, target in ((HaltScope.EVERYTHING, ""), (HaltScope.DEPARTMENT, "finance")):
            with pytest.raises(HaltRefusedError):
                await stop(sessions, scoped, scope=scope, target=target, reason="", now=NOW)

    through(database, work)

    assert sql(database, "SELECT count(*) FROM ops.halt") == [(0,)]


@pytest.mark.needs_db
def test_a_resume_is_refused_where_nothing_is_stopped_or_the_stop_is_not_the_reader_s(
    database: str,
) -> None:
    """A resume names the halt it lifts, so with nothing stopped there is nothing to name, and a
    scoped administrator cannot lift a stop outside their department. Neither writes a row, and
    the stop each was refused against is recorded under the authority it was made with. Delete
    this and a resume can be a row saying somebody restarted what nobody stopped, or a department
    administrator can lift the company's stop on another department."""
    from tests.fixtures.scratch_postgres import sql

    owner = reader("u_owner", Scope.unrestricted())
    scoped = reader("u_admin", Scope.department("web"))

    async def work(sessions: async_sessionmaker[AsyncSession]) -> None:
        with pytest.raises(HaltRefusedError, match="nothing is stopped"):
            await resume(
                sessions, owner, scope=HaltScope.DEPARTMENT, target="web", reason=FIXED, now=NOW
            )
        await stop(
            sessions, owner, scope=HaltScope.DEPARTMENT, target="finance", reason="", now=NOW
        )
        with pytest.raises(HaltRefusedError, match="may not resume"):
            await resume(
                sessions,
                scoped,
                scope=HaltScope.DEPARTMENT,
                target="finance",
                reason=FIXED,
                now=LATER,
            )

    through(database, work)

    assert sql(database, "SELECT act, target, actor_role FROM ops.halt") == [
        ("halt", "finance", "install administrator")
    ]


# ------------------------------------------------------------------ the Stop screen's routes


def _grants() -> dict[str, tuple[Grant, ...]]:
    from brain.console.reads import Plane, plane_capability

    def held(scope: Scope) -> tuple[Grant, ...]:
        return (
            Grant(capability=HALT_CAPABILITY, scope=scope),
            Grant(capability=plane_capability(Plane.CONFIGURATION), scope=scope),
        )

    return {
        "u_admin": held(Scope.department("web")),
        "u_elsewhere": held(Scope.unrestricted()),
        "u_narrow": (Grant(capability=Capability(value="read:knowledge"), scope=Scope()),),
    }


@pytest.fixture
def served(database: str) -> Iterator[TestClient]:
    from tests.fixtures.console_http import console_client

    engine, sessions = _sessions(database)
    with console_client(_grants()) as (client, _):
        client.app.state.db_sessions = sessions  # type: ignore[attr-defined]
        yield client
    asyncio.run(engine.dispose())


@pytest.mark.needs_db
def test_the_stop_screen_is_not_there_for_a_reader_who_may_not_open_it(
    served: TestClient,
) -> None:
    """The same 404 as an address that does not exist. Delete this and the halts in force, and
    who declared them and why, are read by anybody signed in."""
    from tests.fixtures.console_http import get, post

    assert get(served, "u_narrow", "/api/v1/halts").status_code == 404
    told = post(served, "u_narrow", "/api/v1/halts", {"scope": "everything"})
    assert told.status_code == 404


@pytest.mark.needs_db
def test_a_department_administrator_stops_their_own_department_and_nothing_else(
    served: TestClient, database: str
) -> None:
    """**M27.15.2.** One press stops their department and the screen lists it; another
    department and everything are each the 404 an address that does not exist is; the screen
    says they may not stop everything and names the axis nothing asks. Delete this and a
    department administrator can stop the company."""
    from tests.fixtures.console_http import get, post
    from tests.fixtures.scratch_postgres import sql

    own = post(served, "u_admin", "/api/v1/halts", {"scope": "department", "target": "web"})
    other = post(served, "u_admin", "/api/v1/halts", {"scope": "department", "target": "finance"})
    everything = post(served, "u_admin", "/api/v1/halts", {"scope": "everything"})
    listed = get(served, "u_admin", "/api/v1/halts").json()

    assert own.status_code == 201
    assert own.json()["reason"] == STOPPED_FROM_THE_CONSOLE
    assert (other.status_code, everything.status_code) == (404, 404)
    assert [(one["scope"], one["target"]) for one in listed["halts"]] == [("department", "web")]
    assert listed["known"] is True
    assert listed["may_stop_everything"] is False
    assert listed["not_asked_yet"] == []
    assert sql(database, "SELECT scope, target, actor_role FROM ops.halt") == [
        ("department", "web", "scoped administrator")
    ]


@pytest.mark.needs_db
def test_a_resume_from_the_screen_needs_words_and_says_whose_stop_it_lifts(
    served: TestClient,
) -> None:
    """**M27.15.15.** A resume with no reason is a 422 naming why and lifts nothing; with one, it
    lifts the halt and says another administrator's stop was overridden, and a stop elsewhere, on
    an agent, stands. A resume outside the reader's department is the 404 an address that does not
    exist is, saying nothing of what is stopped there. Delete this and the screen's resume can be
    pressed through with nothing written."""
    from tests.fixtures.console_http import get, post

    post(served, "u_admin", "/api/v1/halts", {"scope": "department", "target": "web"})
    bare = post(
        served,
        "u_elsewhere",
        "/api/v1/halts/resume",
        {"scope": "department", "target": "web", "reason": ""},
    )
    agent = post(served, "u_elsewhere", "/api/v1/halts", {"scope": "agent", "target": "a_one"})
    still = get(served, "u_elsewhere", "/api/v1/halts").json()["halts"]
    lifted = post(
        served,
        "u_elsewhere",
        "/api/v1/halts/resume",
        {"scope": "department", "target": "web", "reason": FIXED},
    )

    elsewhere = post(
        served,
        "u_admin",
        "/api/v1/halts/resume",
        {"scope": "department", "target": "finance", "reason": FIXED},
    )
    assert (bare.status_code, agent.status_code) == (422, 201)
    assert elsewhere.status_code == 404
    assert sorted(one["target"] for one in still) == ["a_one", "web"]
    assert lifted.status_code == 200
    assert lifted.json()["overrides_somebody_else"] is True
    after = get(served, "u_elsewhere", "/api/v1/halts").json()["halts"]
    assert [(one["scope"], one["target"]) for one in after] == [("agent", "a_one")]


# ------------------------------------------------------------------ the answer route


def _ask(client: TestClient) -> Any:
    from tests.fixtures.console_http import headers
    from tests.unit.test_answer_route_model import READER

    return client.post(
        "/api/v1/answer", headers=headers(READER), json={"question": "how much annual leave"}
    )


@pytest.mark.needs_db
def test_a_question_asked_while_everything_is_stopped_is_turned_away_in_the_halt_s_words(
    database: str, client: TestClient, transport: Scripted
) -> None:
    """**A_HALTED_QUESTION_IS_TURNED_AWAY_BEFORE_IT_COSTS_ANYTHING.** A 503 with the domain's
    sentence, no `Retry-After`, nothing of the reason, and no model asked. Delete this and the
    stop button refuses everything except the thing people actually do, which is ask."""
    owner = reader("u_owner", Scope.unrestricted())

    async def write(sessions: async_sessionmaker[AsyncSession]) -> None:
        await stop(sessions, owner, scope=HaltScope.EVERYTHING, target="", reason=BECAUSE, now=NOW)

    through(database, write)
    expected = in_force([stop_everything(declared_by="u_owner", at=NOW, reason=BECAUSE)]).refusal()
    engine, sessions = _sessions(database)
    try:
        client.app.state.db_sessions = sessions  # type: ignore[attr-defined]
        answered = _ask(client)
    finally:
        asyncio.run(engine.dispose())

    assert answered.status_code == 503
    assert answered.json()["message"] == expected
    assert BECAUSE not in answered.text
    assert "retry-after" not in {one.lower() for one in answered.headers}
    assert transport.sent == []


def test_a_question_is_refused_where_the_database_cannot_be_read_and_answered_with_none(
    client: TestClient,
) -> None:
    """**Both halves of NO_DATABASE_CONFIGURED_MEANS_NOTHING_COULD_HAVE_BEEN_HALTED on the route.**
    With no database the question is answered; with one configured and not answering it is the
    503 that says the system cannot confirm it was not stopped. Delete this and the route can
    treat a database outage as nothing stopped, or every database-less process as stopped."""
    engine = create_async_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    try:
        answered = _ask(client)
        client.app.state.db_sessions = async_sessionmaker(engine)  # type: ignore[attr-defined]
        refused = _ask(client)
    finally:
        asyncio.run(engine.dispose())

    assert answered.status_code == 200
    assert refused.status_code == 503
    assert refused.json()["message"] == CANNOT_CONFIRM


@pytest.mark.needs_db
def test_a_stopped_source_is_left_out_of_the_live_reads_an_answer_makes() -> None:
    """**A connector halt, at question time.** The same connected source is offered to an answer
    before the stop and is not offered while it stands, so nothing reaches it until it is lifted.
    Delete this and a stopped source is still read live inside every answer that asks it."""
    from brain.connectors.xero import ENTITY_INVOICE
    from brain.ops.live_read_run import live_records_for
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_connector_sync_run import a_database, connect
    from tests.unit.test_connector_sync_run import through as as_the_sync_does

    async def offered(sessions: async_sessionmaker[AsyncSession]) -> bool:
        live = live_records_for(sessions, None)
        assert live is not None
        return (await live.connected()).reads("xero", ENTITY_INVOICE) is not None

    with a_database("brain_halt_live_reads") as url:
        connect(url)
        before = as_the_sync_does(url, offered)
        sql(
            url,
            "INSERT INTO ops.halt (act, scope, target, actor_id, actor_role, reason, at)"
            " VALUES ('halt', 'connector', 'xero', 'u_admin', 'install administrator', %s, %s)",
            BECAUSE,
            NOW,
        )
        during = as_the_sync_does(url, offered)

    assert (before, during) == (True, False)


@pytest.mark.needs_db
def test_a_question_from_a_stopped_department_is_turned_away_and_its_own_alone(
    database: str, client: TestClient, transport: Scripted
) -> None:
    """**M27.15.2 on the route.** The asker sits in sales: a stop on sales turns their question
    away before any model, and a stop on another department does not. Delete this and the route
    can ask the store with no department, so a department stop refuses nobody's questions."""
    from brain.ops.halt import Halt as Declared

    owner = reader("u_owner", Scope.unrestricted())
    engine, sessions = _sessions(database)

    async def stopping(target: str) -> None:
        await stop(sessions, owner, scope=HaltScope.DEPARTMENT, target=target, reason="", now=NOW)

    try:
        client.app.state.db_sessions = sessions  # type: ignore[attr-defined]
        asyncio.run(stopping("web"))
        elsewhere = _ask(client)
        asyncio.run(stopping("sales"))
        here = _ask(client)
    finally:
        asyncio.run(engine.dispose())

    expected = Declared(
        scope=HaltScope.DEPARTMENT,
        target="sales",
        declared_by="u_owner",
        at=NOW,
        reason=STOPPED_FROM_THE_CONSOLE,
    ).refusal()
    assert elsewhere.status_code == 200
    assert (here.status_code, here.json()["message"]) == (503, expected)


@pytest.mark.needs_db
def test_a_question_routed_to_a_stopped_agent_is_turned_away_and_another_agent_s_is_not(
    database: str, client: TestClient, transport: Scripted
) -> None:
    """**M13.7.3 on the route.** The question is routed to the default agent: a stop on another
    agent leaves it answered, and a stop on the default agent turns it away before any model, in
    the agent halt's own sentence. Delete this and the route can ask the store without the agent
    it chose, so an agent stop refuses no question."""
    from brain.api_routes import DEFAULT_AGENT
    from brain.ops.halt import Halt as Declared

    owner = reader("u_owner", Scope.unrestricted())
    engine, sessions = _sessions(database)

    async def stopping(target: str) -> None:
        await stop(sessions, owner, scope=HaltScope.AGENT, target=target, reason="", now=NOW)

    try:
        client.app.state.db_sessions = sessions  # type: ignore[attr-defined]
        asyncio.run(stopping("a_somebody_else"))
        elsewhere = _ask(client)
        asyncio.run(stopping(DEFAULT_AGENT))
        here = _ask(client)
    finally:
        asyncio.run(engine.dispose())

    expected = Declared(
        scope=HaltScope.AGENT,
        target=DEFAULT_AGENT,
        declared_by="u_owner",
        at=NOW,
        reason=STOPPED_FROM_THE_CONSOLE,
    ).refusal()
    assert elsewhere.status_code == 200
    assert (here.status_code, here.json()["message"]) == (503, expected)
    assert len(transport.sent) == 1
