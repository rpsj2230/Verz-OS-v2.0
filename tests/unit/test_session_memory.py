"""Session memory: what a person said for one conversation, kept for them and that conversation
alone, shown to a model as a hint, and told to nobody (M16.1.1, M16.3.1).

The store is run against a fake of the two Valkey commands it uses, which is the seam
`brain.cache.AsyncValkeyClient` exists to be; the prompt and the trace are run through the real
answer lane and a real executor, through `tests.unit.test_model_lane.ask`.

Task ids: M16.1.1, M16.3.1
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from brain.api_routes import session_formed, sessions_of, with_session
from brain.gate.model_lane import (
    MAX_HINTS_SHOWN,
    SESSION_HEADING,
    ModelLane,
    messages_of,
    prompt_bytes,
    prompt_for,
    session_block,
    shown,
)
from brain.gate.turn_context import Part
from brain.memory.digest import DIGEST_TIERS
from brain.memory.formation import (
    MAX_SESSION_STATEMENTS,
    SESSION_IDLE_SECONDS,
    session_key,
)
from brain.memory.tiers import BLAST_RADIUS, Change, Tier
from brain.memory.turn import MAX_STATEMENT_CHARS, candidate, sentences, session_statements
from brain.ops.session_memory_store import (
    A_SESSION_MEMORY_IS_ONE_PERSONS_ONE_CONVERSATION_AND_GOES_WITH_IT,
    SessionRecollection,
    StoredSessions,
    merged,
)
from tests.unit.test_model_lane import ask

#: Pinned far from any wall clock: nothing here is about the present.
AT = datetime(2019, 3, 4, 12, tzinfo=UTC)
THREAD = "6f1d1c3e-0000-4000-8000-000000000001"


class Valkey:
    """The two commands the store uses, over a dict, keeping every expiry it was given."""

    def __init__(self, *, failing: bool = False) -> None:
        self.held: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.failing = failing

    async def get(self, name: str) -> bytes | None:
        if self.failing:
            raise ConnectionError("down")
        return self.held.get(name)

    async def setex(self, name: str, time: int, value: bytes) -> object:
        if self.failing:
            raise ConnectionError("down")
        self.held[name] = value
        self.ttls[name] = time
        return True

    async def ping(self) -> object:
        return True


# --------------------------------------------------------------------- what counts (M16.1.1)


def test_a_sentence_said_for_this_conversation_is_a_session_statement_and_forms_no_memory() -> None:
    """**The positive case.** "For now, I want figures in euros" keeps "I want figures in euros"
    for the conversation, and the same sentence forms no stored memory of any kind, so a thing said
    for one conversation never outlives it.

    Delete this and session memory can be fed by nothing, or the same words can also be written to
    the person's permanent memory."""
    said = "For now, I want figures in euros. How much did we invoice?"

    assert session_statements(said) == ("I want figures in euros",)
    assert [candidate(one) for one in sentences(said)] == [None, None]


def test_only_the_persons_own_words_about_themselves_are_kept_once_each_and_bounded() -> None:
    """A sentence about somebody else, one with no opener, one too long, and a repeat are not kept.

    Delete this and a client's figure, said in passing ("for now, Acme owes twelve thousand"),
    becomes a note the model is shown as the person's own instruction (M16.7.5)."""
    said = " ".join(
        (
            "For now, Acme owes twelve thousand.",
            "I want figures in euros.",
            "In this chat, " + "I " + "x" * MAX_STATEMENT_CHARS + ".",
            "For this conversation, I want short answers.",
            "For this conversation, I want short answers!",
        )
    )

    assert session_statements(said) == ("I want short answers",)


def test_a_session_statement_is_tier_zero_and_in_no_digest() -> None:
    """Tier zero is silent: the change a session statement is sits at `Tier.SESSION`, and the
    weekly digest's tiers stop above it.

    Delete this and session notes could be listed in the digest, telling the person (and anybody
    reading over their shoulder) what they said in a conversation they thought was over."""
    assert BLAST_RADIUS[Change.SESSION_CONTEXT] is Tier.SESSION
    assert Tier.SESSION not in DIGEST_TIERS


# ------------------------------------------------------------------------------ the store


def test_what_is_said_is_kept_for_the_conversations_idle_lifetime_and_read_back() -> None:
    """**The store's positive case.** A statement is kept under the person and the thread, read
    back for them, and expires a full idle lifetime after the turn that wrote it.

    Delete this and the store could keep nothing, or keep it for ever."""
    valkey = Valkey()
    store = StoredSessions(valkey)

    asyncio.run(store.remember(THREAD, "p_ana", ("I want figures in euros",), now=AT))

    assert asyncio.run(store.recalled(THREAD, "p_ana")) == ("I want figures in euros",)
    assert valkey.ttls == {session_key(THREAD, "p_ana"): SESSION_IDLE_SECONDS}


def test_two_people_on_one_thread_id_reach_two_memories() -> None:
    """**Never shared across people.** Somebody else naming the same thread id reads nothing the
    first person said, because the person is in the key.

    Delete this and a thread id passed around, or guessed, reads somebody else's notes."""
    store = StoredSessions(Valkey())
    asyncio.run(store.remember(THREAD, "p_ana", ("I want figures in euros",), now=AT))

    assert asyncio.run(store.recalled(THREAD, "p_ben")) == ()
    assert A_SESSION_MEMORY_IS_ONE_PERSONS_ONE_CONVERSATION_AND_GOES_WITH_IT


def test_a_turn_saying_nothing_for_the_conversation_writes_nothing() -> None:
    """Nothing is written for a turn with no session statement, so an empty conversation is not
    kept alive by questions.

    Delete this and every question resets an expiry on a key holding nothing."""
    valkey = Valkey()
    asyncio.run(StoredSessions(valkey).remember(THREAD, "p_ana", (), now=AT))

    assert valkey.held == {}


def test_a_statement_said_again_is_held_once_and_the_oldest_go_first() -> None:
    """Repeats move to the end, and past the bound the oldest are dropped.

    Delete this and one conversation's notes can grow without limit, past what the prompt's byte
    bound was measured with."""
    many = tuple(f"I want rule {n}" for n in range(MAX_SESSION_STATEMENTS + 3))
    kept = merged(many[:2], (*many[2:], "I WANT RULE 0"))

    assert len(kept) == MAX_SESSION_STATEMENTS
    assert kept[-1] == "I WANT RULE 0"
    assert "I want rule 1" not in kept


def test_an_outage_reads_as_nothing_remembered_and_never_raises() -> None:
    """A Valkey outage costs the conversation its notes and never the person their answer.

    Delete this and a cache going down fails every follow-up question."""
    store = StoredSessions(Valkey(failing=True))

    asyncio.run(store.remember(THREAD, "p_ana", ("I want figures in euros",), now=AT))
    assert asyncio.run(store.recalled(THREAD, "p_ana")) == ()


def test_a_stored_value_that_is_not_a_list_of_statements_reads_as_nothing() -> None:
    """Anything in the key that is not a JSON list of bounded strings is ignored.

    Delete this and a value written by anything else under the key reaches a prompt."""
    valkey = Valkey()
    key = session_key(THREAD, "p_ana")
    store = StoredSessions(valkey)
    for raw in (b"not json", json.dumps({"a": 1}).encode(), json.dumps([1, "x" * 999]).encode()):
        valkey.held[key] = raw
        assert asyncio.run(store.recalled(THREAD, "p_ana")) == ()


# ------------------------------------------------------------------------ the route's half


def test_the_route_binds_session_memory_only_to_a_conversation_it_found_as_the_askers() -> None:
    """`with_session` binds the person and the thread only when a thread was found; otherwise the
    lane is handed back as it was, and a process with no cache keeps no session memory.

    Delete this and a question naming no conversation, or somebody else's, could be shown notes."""
    valkey = Valkey()
    state: Any = SimpleNamespace(valkey=valkey)
    lane = ModelLane(search=object(), model=object())  # type: ignore[arg-type]

    bound = with_session(state, lane, principal_id="p_ana", thread_id=THREAD)
    assert bound is not None and isinstance(bound.session, SessionRecollection)
    assert (bound.session.thread_id, bound.session.principal_id) == (THREAD, "p_ana")
    assert with_session(state, lane, principal_id="p_ana", thread_id=None) is lane
    assert sessions_of(SimpleNamespace()) is None
    assert with_session(SimpleNamespace(), lane, principal_id="p_ana", thread_id=THREAD) is lane


def test_the_route_keeps_what_was_said_once_the_exchange_has_its_thread() -> None:
    """`session_formed` keeps the session statements of the question under the thread the
    exchange was kept in, and nothing when it was kept in none.

    Delete this and session memory is read by the route and written by nothing."""
    valkey = Valkey()
    state: Any = SimpleNamespace(valkey=valkey)
    said = "For now, I want figures in euros. What did we invoice?"

    asyncio.run(session_formed(state, principal_id="p_ana", thread_id=None, said=said, now=AT))
    assert valkey.held == {}
    asyncio.run(session_formed(state, principal_id="p_ana", thread_id=THREAD, said=said, now=AT))
    assert json.loads(valkey.held[session_key(THREAD, "p_ana")]) == ["I want figures in euros"]


# ---------------------------------------------------------------------------- the model's half


def test_the_model_is_shown_the_conversations_notes_as_a_hint_and_cites_none() -> None:
    """**What a person said for this conversation reaches the model, labelled as their words,
    after the question and before the passages, and the trace names the part (M16.6.1).** Nothing
    cites it and it is in no frame.

    Delete this and session memory can be kept and shown to nobody, or shown as a source."""
    note = "I want figures in euros SESSIONVERMILION"
    run = ask(session=(note,))

    [request] = run.sent
    user = request.messages[1].content
    assert user.index("Question:") < user.index(SESSION_HEADING) < user.index("Passages:")
    assert f"- {note}" in user and note not in request.messages[0].content
    assert "SESSIONVERMILION" not in "".join(run.answered.frames if run.answered else ())
    assert run.answered is not None and run.answered.context is not None
    assert Part.SESSION in run.answered.context.included
    [categories] = [row["categories"] for row in run.attempts.rows.values()]
    assert "memory_hints" in cast(tuple[str, ...], categories)


def test_the_largest_prompt_with_every_hint_and_session_note_still_fits_the_answer_tier() -> None:
    """The byte measurement `THE_PROMPT_FITS_ITS_TIER_BY_ITS_BYTES` makes, with the most hints and
    the most session notes a prompt can carry, each longer than either may be.

    Delete this and a long conversation's notes can push a legitimate question past what the
    provider accepts."""
    from brain.core.lane import Lane
    from brain.core.redaction import ChannelPayload
    from brain.gate.caches import MAX_QUESTION_CHARS
    from brain.gate.model_lane import PASSAGES_SHOWN, SHOWN_FIELDS
    from brain.knowledge.document_tools import KNOWLEDGE_ENTITY
    from brain.models.routing import (
        ESCALATION_HEADROOM,
        TIER_CONTEXT_WINDOW,
        RoutingRequest,
        classify_tier,
    )

    wide = "\N{GRINNING FACE}"
    passage = {"entity": KNOWLEDGE_ENTITY, "id": "c", **dict.fromkeys(SHOWN_FIELDS, wide * 10_000)}
    payload = ChannelPayload(records=tuple(dict(passage) for _ in range(PASSAGES_SHOWN * 2)))
    hints = tuple(wide * 4_000 for _ in range(MAX_HINTS_SHOWN * 3))
    notes = tuple(wide * 4_000 for _ in range(MAX_SESSION_STATEMENTS * 3))
    layout = prompt_for(wide * (MAX_QUESTION_CHARS * 2), shown(payload), (), hints, session=notes)
    tier = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier

    assert session_block(notes).count("\n- ") == MAX_SESSION_STATEMENTS
    assert prompt_bytes(messages_of(layout)) <= ESCALATION_HEADROOM * TIER_CONTEXT_WINDOW[tier]


def test_a_session_note_expires_a_full_idle_lifetime_after_the_last_turn_that_wrote_one() -> None:
    """A later turn adding a note moves the expiry forward to a full idle lifetime from then.

    Delete this and a busy conversation's notes vanish twelve hours after its first note."""
    valkey = Valkey()
    store = StoredSessions(valkey)
    asyncio.run(store.remember(THREAD, "p_ana", ("I want a",), now=AT))
    asyncio.run(store.remember(THREAD, "p_ana", ("I want b",), now=AT + timedelta(hours=11)))

    assert valkey.ttls[session_key(THREAD, "p_ana")] == SESSION_IDLE_SECONDS
    assert asyncio.run(store.recalled(THREAD, "p_ana")) == ("I want a", "I want b")


def test_the_route_reads_notes_only_through_a_follow_up_and_keeps_them_by_thread() -> None:
    """The route binds session memory with the thread only when a follow-up found the
    conversation as the asker's own and live, and keeps notes under the thread the exchange was
    kept in. Read from the call expressions rather than from text, so a comment cannot satisfy it.

    Delete this and the route can bind any thread id a request names, including one that is not
    the asker's, or stop keeping notes while every helper test stays green."""
    import ast
    import inspect

    import brain.api_routes as routes

    def keywords(function: Any, name: str) -> list[dict[str, str]]:
        tree = ast.parse(inspect.getsource(function))
        return [
            {one.arg or "": ast.unparse(one.value) for one in node.keywords}
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == name
        ]

    [bound] = keywords(routes.answered_for, "with_session")
    assert bound["thread_id"] == "ask.thread if follow_up is not None else None"
    [kept] = keywords(routes.answer, "session_formed")
    assert (kept["thread_id"], kept["said"]) == ("thread", "ask.question")


def test_a_retired_conversation_is_continued_by_nothing_so_its_notes_are_read_by_nobody(
    monkeypatch: Any,
) -> None:
    """**Session memory goes with the conversation.** A conversation found but retired brings no
    follow-up, and session memory is read only through one, so its notes reach no prompt from the
    moment it goes; the same conversation live is continued as before.

    Delete this and an erased or retired conversation's notes stay readable for the rest of their
    idle lifetime."""
    import brain.chat.remember as remember
    from brain.api_routes import Answering, Question, follow_up_for
    from brain.chat.threads import Thread, ThreadMessage
    from brain.core.entitlement import EntitlementSet
    from brain.core.principal import Employment, Principal, PrincipalKind
    from brain.gate.context import Channel
    from brain.tables.chat import MessageRole

    asked_before = ThreadMessage(role=MessageRole.USER, at=AT, channel=Channel.CONSOLE, body="q")

    class Threads:
        def __init__(self, retired: bool) -> None:
            self.retired = retired

        async def thread(self, principal_id: str, thread_id: str) -> Thread:
            return Thread(
                thread_id=thread_id,
                owner_id=principal_id,
                title="t",
                messages=(asked_before,),
                retired=self.retired,
            )

    asking = Answering(
        principal=Principal(
            id="p_ana",
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name="Ana",
        ),
        reach=EntitlementSet(principal_id="p_ana", grants=()),
        channel=Channel.CONSOLE,
        now=AT,
    )
    ask = Question(question="and in euros?", thread=THREAD)
    state: Any = SimpleNamespace(db_sessions=None)

    monkeypatch.setattr(remember, "threads_of", lambda state: Threads(retired=True))
    assert asyncio.run(follow_up_for(state, asking, ask)) is None
    monkeypatch.setattr(remember, "threads_of", lambda state: Threads(retired=False))
    live = asyncio.run(follow_up_for(state, asking, ask))
    assert live is not None and live.earlier == ("q",)
