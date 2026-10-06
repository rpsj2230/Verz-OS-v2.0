"""A person's export of their own conversation, over HTTP, on PostgreSQL.

Driven through the real application with signed-in people and the application role, so the thread
store's row-level security, `0207`'s widened data set and `0053`'s ledger trigger are the ones an
install has. What is exported is compared with what the thread page shows, and the record with the
bytes the person received.

Task ids: M33.3.1.3
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.chat.thread_store import Exchange, StoredThreads
from brain.chat.turns import TurnKind
from brain.gate.context import Channel
from brain.session import make_session_factory
from brain.tables.chat import MessageRole
from brain.tables.data_export import ExportDataSet
from brain.thread_routes import AN_EXPORT_IS_THE_THREAD_AS_IT_IS_SHOWN_NOW, TURN_OF_ROLE
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine

#: Nothing here is about the present: the exchange is long ago, and the export is now.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

#: Each person holds nothing: a person's own thread needs no grant to read.
GRANTS: dict[str, tuple[Any, ...]] = {"u_narrow": (), "u_prefix": ()}


def test_a_question_and_an_answer_are_turns_and_a_system_note_is_not() -> None:
    """A question and an answer are turns, and a system note ("this conversation was exported")
    is nobody's turn and is not exported. Delete this and a note the assistant never said leaves
    in the file as something it answered."""
    assert TURN_OF_ROLE == {
        MessageRole.USER: TurnKind.QUESTION,
        MessageRole.ASSISTANT: TurnKind.ANSWER,
    }
    assert MessageRole.SYSTEM not in TURN_OF_ROLE
    assert "now" in AN_EXPORT_IS_THE_THREAD_AS_IT_IS_SHOWN_NOW


@pytest.fixture
def database() -> Iterator[str]:
    with retirable("brain_thread_export") as url:
        for pid in GRANTS:
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name)"
                " VALUES (%s, 'human', 'staff', %s) ON CONFLICT (id) DO NOTHING",
                pid,
                pid,
            )
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient, StoredThreads], Awaitable[T]]) -> T:
    """The application over this database as the application role. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            app = create_app(Settings(env="development"))
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = sessions
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client, StoredThreads(sessions))
        finally:
            await built.dispose()

    return run(go)


def test_a_person_exports_their_thread_as_the_page_shows_it_and_the_export_is_recorded(
    database: str,
) -> None:
    """**M33.3.1.3 on PostgreSQL.** The person's own thread exports as the page shows it now: the
    two questions and the answer whose sources are known, and not the answer whose sources were
    never recorded, which the page does not show again either, nor the note marking an answer
    wrong, which is nobody's turn. The row in `ops.data_export` is a
    conversation export, in their own name, as a subject access request, counting the turns that
    left and holding the sha256 of the exact bytes received, and the ledger has its publish entry.
    Another person asking for the same thread gets the one 404 and nothing is recorded.

    Delete this and an export can carry more than the page shows, or leave with no record of who
    took it, or be taken of somebody else's conversation."""

    async def act(client: httpx.AsyncClient, threads: StoredThreads) -> Any:
        first = await threads.record(
            "u_narrow",
            thread_id=None,
            channel=Channel.CONSOLE,
            exchange=Exchange(question="Where are the price lists?", answer="Here.", refs=()),
            now=LONG_AGO,
        )
        marked = await client.post(
            f"{API_PREFIX}/threads/{first}/corrections",
            json={"kind": "stale"},
            headers=headers("u_narrow"),
        )
        assert marked.status_code == 201, marked.text
        await threads.record(
            "u_narrow",
            thread_id=first,
            channel=Channel.CONSOLE,
            exchange=Exchange(question="And last year's?", answer="Not shown again.", refs=None),
            now=LONG_AGO + timedelta(minutes=5),
        )
        page = await client.get(f"{API_PREFIX}/threads/{first}", headers=headers("u_narrow"))
        taken = await client.post(
            f"{API_PREFIX}/threads/{first}/export", headers=headers("u_narrow")
        )
        stranger = await client.post(
            f"{API_PREFIX}/threads/{first}/export", headers=headers("u_prefix")
        )
        return first, page, taken, stranger

    first, page, taken, stranger = pressed(database, act)

    assert taken.status_code == 200, taken.text
    handed = taken.json()
    assert handed["filename"] == f"conversation-{first}.json"
    assert taken.headers["cache-control"] == "no-store"
    body = json.loads(handed["document"])
    shown = [(one["role"], one["body"]) for one in page.json()["messages"]]
    assert "system" in {role for role, _ in shown}
    exported = [(one["kind"], one["text"]) for one in body["turns"]]
    assert exported == [
        ("question" if role == "user" else "answer", text)
        for role, text in shown
        if role in ("user", "assistant")
    ]
    assert ("answer", "Not shown again.") not in exported
    assert ("answer", "Here.") in exported and body["conversation_id"] == first

    [(data_set, requested_by, reason, reference, entries, digest)] = sql(
        database,
        "SELECT data_set, requested_by, reason, reason_reference, entries, document_digest"
        " FROM ops.data_export",
    )
    assert (data_set, requested_by, reason) == (
        ExportDataSet.CONVERSATION.value,
        "u_narrow",
        "subject_access_request",
    )
    assert reference == f"thread/{first}"
    assert entries == len(exported)
    assert digest == hashlib.sha256(handed["document"].encode("utf-8")).hexdigest()
    assert sql(
        database,
        "SELECT actor_id FROM obs.audit_entry WHERE action = 'publish' AND details->>'fields' = %s",
        ExportDataSet.CONVERSATION.value,
    ) == [("u_narrow",)]

    assert stranger.status_code == 404
    assert sql(database, "SELECT count(*) FROM ops.data_export") == [(1,)]
