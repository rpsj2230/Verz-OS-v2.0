"""Which agent answered each turn and how its run ended, a failed run included, and an agent's
Conversations section built from them.

`0192` is read as rendered SQL, as `tests/unit/test_tables.py` reads every migration. The listing is
decided in memory over real `Thread`s. The store, the check on the table, the answer route's failure
path and the section's route run on PostgreSQL as the application role, so row-level security is
the one an install has. **The server half skips when there is no server**, and CI always has one.
Dates are pinned far from any wall clock, for CLAUDE.md's reason.

Task ids: M39.8.9
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from brain.agent_conversation_routes import router
from brain.agents import model as agent_model
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.chat.remember import run_state_of
from brain.chat.thread_store import (
    FAILED_RUN_SHOWS_NOTHING,
    Exchange,
    StoredThreads,
    failed_exchange,
)
from brain.chat.threads import Thread, ThreadMessage
from brain.console.agent_conversations import agent_conversations
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Degraded, Failed
from brain.core.scope import Scope
from brain.db import metadata
from brain.gate.context import Channel
from brain.session import make_session_factory
from brain.tables import chat as chat_table
from brain.tables.adoption import TRACE_ID_CHARS
from brain.tables.chat import MessageRole, RunState
from brain.tables.identity import one_of
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_answer_route_gate import an_agent, roster_of
from tests.unit.test_answer_route_model import READER
from tests.unit.test_answer_route_model import client as client
from tests.unit.test_answer_route_model import transport as transport
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import VERSIONS, rendered, squash

MIGRATION = VERSIONS / "0192_agent_and_run_on_a_thread_turn.py"
AT = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
ME = "u_me"


# ------------------------------------------------------------------------- the migration
def test_0192_holds_the_widths_and_words_the_model_and_the_tables_it_names_hold() -> None:
    """The widths are an agent id's and a request trace's as their own tables hold them, and the
    vocabulary and the one-answer rule are the model's. Delete this and an agent id or a trace the
    product writes is refused by the table, or a run state added to the enum is refused after the
    run it records."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_0192", MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.AGENT_ID_CHARS == chat_table.AGENT_ID_CHARS == agent_model.AGENT_ID_CHARS
    assert migration.TRACE_ID_CHARS == chat_table.TRACE_ID_CHARS == TRACE_ID_CHARS
    assert migration.RUN_STATE_CHARS == chat_table.RUN_STATE_CHARS
    assert max(len(one.value) for one in RunState) <= migration.RUN_STATE_CHARS
    assert migration.RUN_CHECKS == chat_table.RUN_CHECKS
    assert one_of("run_state", RunState) in migration.RUN_CHECKS["run_state_on_an_answer"]
    assert all(
        one.startswith(f"{column} IS NULL OR ")
        for one, column in zip(
            migration.RUN_CHECKS.values(), ("run_state", "agent_id", "trace_id"), strict=True
        )
    )


def test_0192_emits_the_columns_checks_and_index_its_amendment_claims() -> None:
    """`AMENDS_CREATE_TABLE` is a claim the DDL comparison trusts, so the ALTERs it describes are
    held to what the upgrade emits, and the downgrade takes each back. Delete this and the
    amendment can claim a column the upgrade never adds."""
    up = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))

    for column, width in (("agent_id", 60), ("trace_id", 64), ("run_state", 16)):
        assert f"ALTER TABLE chat.message ADD COLUMN {column} VARCHAR({width});" in up
        assert f"ALTER TABLE chat.message DROP COLUMN {column};" in down
    for name in ("run_state_on_an_answer", "agent_on_an_answer", "trace_on_an_answer"):
        assert f"ALTER TABLE chat.message ADD CONSTRAINT ck_message_{name} CHECK" in up
        assert f"ALTER TABLE chat.message DROP CONSTRAINT ck_message_{name};" in down
    assert "CREATE INDEX ix_message_agent ON chat.message (agent_id, created_at);" in up
    assert "DROP INDEX chat.ix_message_agent;" in down
    assert "ix_message_agent" in {one.name for one in metadata.tables["chat.message"].indexes}


# ------------------------------------------------------------------------- the domain
def message(
    role: MessageRole, minutes: int, *, agent: str = "", state: RunState | None = None
) -> ThreadMessage:
    return ThreadMessage(
        role=role,
        at=AT + timedelta(minutes=minutes),
        channel=Channel.CONSOLE,
        body="asked" if role is MessageRole.USER else "",
        refs=None if role is MessageRole.ASSISTANT else (),
        agent_id=agent,
        run_state=state,
    )


def thread(thread_id: str, *messages: ThreadMessage, owner: str = ME) -> Thread:
    return Thread(
        thread_id=thread_id, owner_id=owner, title=f"about {thread_id}", messages=messages
    )


ASK, ANSWER = MessageRole.USER, MessageRole.ASSISTANT


def test_the_section_lists_the_readers_threads_the_agent_answered_in_with_who_and_how() -> None:
    """**M39.8.9.** A thread the agent answered in is listed with the agents that answered, this one
    first, and how its latest run there ended, a failed one included; a thread only another agent
    answered in is not; somebody else's thread is not, whatever answered in it; and the newest is
    first. Delete this and the section lists threads the agent never answered in, somebody else's,
    or a run's state from another agent."""
    reader = EntitlementSet(principal_id=ME)
    threads = [
        thread(
            "t_failed", message(ASK, 1), message(ANSWER, 2, agent="desk", state=RunState.FAILED)
        ),
        thread(
            "t_shared",
            message(ASK, 3),
            message(ANSWER, 4, agent="other", state=RunState.ANSWERED),
            message(ASK, 5),
            message(ANSWER, 6, agent="desk", state=RunState.ABSTAINED),
            message(ASK, 7),
            message(ANSWER, 8, agent="other", state=RunState.FAILED),
        ),
        thread("t_elsewhere", message(ASK, 9), message(ANSWER, 10, agent="other")),
        thread(
            "t_theirs",
            message(ASK, 11),
            message(ANSWER, 12, agent="desk", state=RunState.ANSWERED),
            owner="u_somebody_else",
        ),
    ]

    listed = agent_conversations(threads, "desk", principal_id=ME, reader=reader, now=AT)

    assert [(one.thread_id, one.agents, one.state) for one in listed] == [
        ("t_shared", ("desk", "other"), RunState.ABSTAINED),
        ("t_failed", ("desk",), RunState.FAILED),
    ]
    assert listed[0].title == "about t_shared"
    assert listed[0].last_at == AT + timedelta(minutes=8)


def test_a_thread_says_how_the_agents_latest_run_ended_and_names_no_agent_for_an_older_answer() -> (
    None
):
    """The state is this agent's latest run in the thread, not its first: it failed, then answered,
    so the thread reads answered. And an answer written before `0192`, which names no agent, adds
    no participant: the agents are the ones the table recorded and nothing blank. Delete this and
    a thread that recovered still reads failed, or the section draws an empty name beside the
    agent's."""
    reader = EntitlementSet(principal_id=ME)
    one = thread(
        "t_recovered",
        message(ASK, 1),
        message(ANSWER, 2),
        message(ASK, 3),
        message(ANSWER, 4, agent="desk", state=RunState.FAILED),
        message(ASK, 5),
        message(ANSWER, 6, agent="desk", state=RunState.ANSWERED),
    )

    [listed] = agent_conversations([one], "desk", principal_id=ME, reader=reader, now=AT)

    assert (listed.agents, listed.state) == (("desk",), RunState.ANSWERED)


def test_a_reader_whose_principal_has_expired_is_listed_nothing() -> None:
    """The sibling of the listing: `recent_threads`' rule, reached through this section. Delete this
    and a titled list of somebody's questions outlives their access."""
    expired = EntitlementSet(principal_id=ME, not_after=AT - timedelta(days=1))
    one = thread("t", message(ASK, 1), message(ANSWER, 2, agent="desk", state=RunState.ANSWERED))

    assert agent_conversations([one], "desk", principal_id=ME, reader=expired, now=AT) == ()


def test_a_failed_exchange_carries_no_words_and_no_references_and_every_outcome_has_a_state() -> (
    None
):
    """`FAILED_RUN_SHOWS_NOTHING`, in the type: a failed turn with words in it is refused, the one
    `failed_exchange` builds has none, and an answered, a declined and a degraded outcome each read
    as themselves. Delete this and a failed run can be stored with model output nobody was shown."""
    made = failed_exchange("why", agent_id="desk", trace_id="tr-1")
    assert (made.answer, made.refs, made.state) == ("", None, RunState.FAILED)
    with pytest.raises(ValueError, match="nobody was shown"):
        Exchange(question="why", answer="words", refs=None, state=RunState.FAILED)
    assert FAILED_RUN_SHOWS_NOTHING

    def outcome(**fields: Any) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            **{"abstention": None, "composed": None, "partial": None, "from_cache": False, **fields}
        )

    assert run_state_of(outcome(composed=object())) is RunState.ANSWERED
    assert run_state_of(outcome(abstention=object())) is RunState.ABSTAINED
    assert run_state_of(outcome(partial=object())) is RunState.DEGRADED
    assert run_state_of(outcome(from_cache=True)) is RunState.ANSWERED


# ------------------------------------------------------------------------- on a server
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_thread_runs_{uuid.uuid4().hex[:8]}") as url:
        yield url


def test_a_run_is_kept_with_its_agent_and_trace_and_a_question_cannot_carry_one(
    database: str,
) -> None:
    """On PostgreSQL as the application role: an answer is kept with its agent, trace and state,
    a failed run as its question and an empty failed turn, both read back as they were written;
    and the table refuses a run state on a question. Delete this and the columns can be written
    and never read, or a question can claim a run."""
    import psycopg

    async def go() -> Any:
        built = app_engine(database)
        try:
            store = StoredThreads(make_session_factory(built))
            kept = await store.record(
                ME,
                thread_id=None,
                channel=Channel.CONSOLE,
                exchange=Exchange(
                    question="first",
                    answer="An answer.",
                    refs=(),
                    agent_id="desk",
                    trace_id="tr-1",
                    state=RunState.ANSWERED,
                ),
                now=AT,
            )
            await store.record(
                ME,
                thread_id=kept,
                channel=Channel.CONSOLE,
                exchange=failed_exchange("second", agent_id="desk", trace_id="tr-2"),
                now=AT + timedelta(minutes=1),
            )
            return await store.thread(ME, kept)
        finally:
            await built.dispose()

    found = run(go)
    assert found is not None
    answers = [one for one in found.messages if one.role is MessageRole.ASSISTANT]
    assert [(one.agent_id, one.run_state, one.body) for one in answers] == [
        ("desk", RunState.ANSWERED, "An answer."),
        ("desk", RunState.FAILED, ""),
    ]
    assert answers[1].refs is None
    assert sql(
        database, "SELECT trace_id FROM chat.message WHERE role = 'assistant' ORDER BY created_at"
    ) == [("tr-1",), ("tr-2",)]
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            database,
            "INSERT INTO chat.message (conversation_id, role, channel, run_state)"
            " SELECT id, 'user', 'console', 'failed' FROM chat.conversation LIMIT 1",
        )


#: What a lane can raise: an error the taxonomy already names, either kind `answered_for` keeps,
#: and anything else, which it wraps. Each goes through its own `except` and each keeps the run.
LANE_ERRORS = (
    RuntimeError("the model step failed"),
    Failed("the model step failed"),
    Degraded("the model step failed"),
)


@pytest.mark.parametrize("raised", LANE_ERRORS, ids=lambda one: type(one).__name__)
def test_a_run_that_fails_on_the_answer_route_is_kept_as_failed_and_shows_nothing(
    database: str, client: TestClient, monkeypatch: pytest.MonkeyPatch, raised: Exception
) -> None:
    """**A failed run appears as failed and shows no model output.** The answer route addressed to
    a stored agent fails inside the lane; the asker's thread then holds the question and one answer
    turn naming that agent and the request's trace, marked failed, with no words, which the thread
    reader never shows; and the error still goes out. Run once for each kind of error the lane can
    raise, since a taxonomy error and anything else leave `answered_for` by different branches.
    Delete this and a failed run leaves no trace in the thread, or is kept as if it had answered."""

    def lane_fails(*args: Any, **kwargs: Any) -> Any:
        raise raised

    monkeypatch.setattr("brain.api_routes.answer_lane", lane_fails)
    built = app_engine(database)
    sessions = make_session_factory(built)
    client.app.state.db_sessions = sessions  # type: ignore[attr-defined]
    client.app.state.agent_roster = roster_of(an_agent("helper"))  # type: ignore[attr-defined]
    try:
        sent = client.post(
            f"{API_PREFIX}/answer",
            headers=headers(READER),
            json={"question": "what changed this week", "agent": "helper"},
        )

        async def kept() -> Any:
            store = StoredThreads(sessions)
            [only] = await store.threads(READER)
            return only

        found = run(kept)
    finally:
        run(built.dispose)

    assert sent.status_code >= 500
    assert "the model step failed" not in sent.text
    assert [(one.role, one.body) for one in found.messages] == [
        (MessageRole.USER, "what changed this week"),
        (MessageRole.ASSISTANT, ""),
    ]
    failed = found.messages[1]
    assert (failed.agent_id, failed.run_state, failed.refs) == ("helper", RunState.FAILED, None)
    from brain.chat.thread_store import CONSOLE_SURFACE, surfaces
    from brain.chat.threads import shown_on

    shown = shown_on(
        found,
        EntitlementSet(principal_id=READER),
        reading=CONSOLE_SURFACE,
        surfaces=surfaces(),
        now=datetime.now(UTC),
    )
    assert [one.role for one in shown] == [MessageRole.USER]


@pytest.mark.parametrize("raised", LANE_ERRORS, ids=lambda one: type(one).__name__)
def test_a_referred_question_whose_run_fails_is_written_nowhere(
    database: str, client: TestClient, monkeypatch: pytest.MonkeyPatch, raised: Exception
) -> None:
    """**M24.2.2 holds on the failure path too.** A question the sensitive-topic interception
    referred, whose run then fails, leaves no thread at all: the failure is not a second way for
    its words to reach a transcript. The failed-run test above is the sibling that is written.
    Run for each kind of error, for the reason the failed-run test gives. Delete this and a
    referred question lands in a thread whenever its run breaks."""

    async def a_referral(request: Any, reach: Any, question: str) -> str:
        return "Somebody named for this will be in touch."

    def lane_fails(*args: Any, **kwargs: Any) -> Any:
        raise raised

    monkeypatch.setattr("brain.api_routes.referred", a_referral)
    monkeypatch.setattr("brain.api_routes.answer_lane", lane_fails)
    built = app_engine(database)
    sessions = make_session_factory(built)
    client.app.state.db_sessions = sessions  # type: ignore[attr-defined]
    try:
        sent = client.post(
            f"{API_PREFIX}/answer", headers=headers(READER), json={"question": "a private matter"}
        )

        async def kept() -> Any:
            return await StoredThreads(sessions).threads(READER)

        found = run(kept)
    finally:
        run(built.dispose)

    assert sent.status_code >= 500
    assert found == ()


def test_the_store_finds_only_the_threads_the_agent_answered_in(database: str) -> None:
    """On PostgreSQL as the application role: of a person's two threads, the one another agent
    answered is not found for this one. The section filters again in memory, so this is held at the
    store, where a thread found in error takes a place in the limit from one that belongs. Delete
    this and the store's query can return every thread a person has, and the section shows fewer
    of the agent's than it should once a person has more threads than the limit."""

    async def go() -> Any:
        built = app_engine(database)
        try:
            store = StoredThreads(make_session_factory(built))
            ids = []
            for agent in ("desk", "other"):
                ids.append(
                    await store.record(
                        ME,
                        thread_id=None,
                        channel=Channel.CONSOLE,
                        exchange=Exchange(
                            question=f"to {agent}",
                            answer="Yes.",
                            refs=(),
                            agent_id=agent,
                            trace_id=f"tr-{agent}",
                            state=RunState.ANSWERED,
                        ),
                        now=AT,
                    )
                )
            found = await store.threads_with_agent(ME, "desk")
            return ids, [one.thread_id for one in found]
        finally:
            await built.dispose()

    (desk, other), found = run(go)
    assert found == [desk]
    assert other not in found


# ------------------------------------------------------------------------- the route
AGENT_ROW = (
    "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
    " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
    " created_by) VALUES (%s, %s, 'Answer briefly.', 'main', %s, %s, NULL,"
    " '{\"clauses\": []}', '{}', '{}', '{}', 'none', 'u_steward')"
)


def everywhere(*capabilities: Capability | str) -> tuple[Grant, ...]:
    return tuple(
        Grant(
            capability=one if isinstance(one, Capability) else Capability(value=one),
            scope=Scope.unrestricted(),
        )
        for one in capabilities
    )


#: `u_admin` holds `read:question` and every plane, the workspace's Conversations tab's read;
#: `u_narrow` holds nothing at all, and may still see a company's agent.
CONVERSATIONS_READ = (tab(Tab.CONVERSATIONS).read.requires, *(plane_capability(p) for p in Plane))
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": everywhere(*CONVERSATIONS_READ),
    "u_narrow": (),
}


def test_each_reader_is_listed_their_own_threads_with_or_without_read_question(
    database: str,
) -> None:
    """**M39.8.9 over HTTP on PostgreSQL, and `A_PERSONS_OWN_THREADS_NEED_NO_GRANT`.** Two people
    asked the same agent, one holding `read:question` and one holding nothing at all: each is listed
    their own thread and never the other's, with the agent named, the failed run marked failed and
    the preview their own first question. Another agent that answered in the same thread is named
    when the reader may see it and left out when they may not. An agent the reader may not see,
    and one that does not exist, are one 404. Delete this and the section can list somebody else's
    questions, name an agent the reader may not see, or hide a person's own conversations from
    them behind a grant that governs other people's."""
    sql(database, AGENT_ROW, "desk", "Sales desk", "company", "u_steward")
    sql(database, AGENT_ROW, "hidden", "Private desk", "personal", "u_somebody_else")
    sql(database, AGENT_ROW, "floor", "Shop floor", "company", "u_steward")

    async def go() -> Any:
        built = app_engine(database)
        try:
            sessions = make_session_factory(built)
            store = StoredThreads(sessions)
            mine = await store.record(
                "u_admin",
                thread_id=None,
                channel=Channel.CONSOLE,
                exchange=Exchange(
                    question="my question",
                    answer="From the floor.",
                    refs=(),
                    agent_id="floor",
                    trace_id="tr-f",
                    state=RunState.ANSWERED,
                ),
                now=AT - timedelta(minutes=1),
            )
            await store.record(
                "u_admin",
                thread_id=mine,
                channel=Channel.CONSOLE,
                exchange=failed_exchange("my follow-up", agent_id="desk", trace_id="tr-a"),
                now=AT,
            )
            theirs = await store.record(
                "u_narrow",
                thread_id=None,
                channel=Channel.LARK,
                exchange=Exchange(
                    question="their question",
                    answer="Yes.",
                    refs=(),
                    agent_id="desk",
                    trace_id="tr-b",
                    state=RunState.ANSWERED,
                ),
                now=AT,
            )
            await store.record(
                "u_narrow",
                thread_id=theirs,
                channel=Channel.LARK,
                exchange=Exchange(
                    question="their follow-up",
                    answer="Privately.",
                    refs=(),
                    agent_id="hidden",
                    trace_id="tr-c",
                    state=RunState.ANSWERED,
                ),
                now=AT + timedelta(minutes=1),
            )
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = sessions
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as http:
                path = f"{API_PREFIX}/agents/desk/conversations"
                elsewhere = [
                    (
                        await http.get(
                            f"{API_PREFIX}/agents/{agent}/conversations", headers=headers(who)
                        )
                    ).status_code
                    for agent in ("hidden", "nobody")
                    for who in ("u_admin", "u_narrow")
                ]
                return (
                    (await http.get(path, headers=headers("u_admin"))).json(),
                    (await http.get(path, headers=headers("u_narrow"))).json(),
                    elsewhere,
                )
        finally:
            await built.dispose()

    mine, theirs, elsewhere = run(go)

    assert [(one["title"], one["state"], one["last_channel"]) for one in mine["items"]] == [
        ("my question", "failed", "console")
    ]
    assert mine["items"][0]["agents"] == [
        {"agent_id": "desk", "display_name": "Sales desk"},
        {"agent_id": "floor", "display_name": "Shop floor"},
    ]
    # Another agent answered in their thread too, one this reader may not see: it is not named.
    assert theirs["items"][0]["agents"] == [{"agent_id": "desk", "display_name": "Sales desk"}]
    assert [(one["title"], one["state"], one["last_channel"]) for one in theirs["items"]] == [
        ("their question", "answered", "lark")
    ]
    assert elsewhere == [404, 404, 404, 404]
