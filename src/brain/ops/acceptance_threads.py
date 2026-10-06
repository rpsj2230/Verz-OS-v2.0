"""Install acceptance checks for a person's threads: kept, continued, searched, and theirs alone.

Each check asks through `/answer`'s own function and keeps the exchange through the route's own
`remembered`, or through the Lark events route itself, as reserved people in the reserved
departments inside the check's rolled-back transaction, and reads the threads back through the
store and the three thread routes the web application reads them at.

**No model is asked.** Every question is one an uploaded table answers on the fast lane, so the
checks need no provider and no key, and the answer kept is the table's own column, which lets a
check tell an answer's words from a question's.

**The chat half goes through Lark's events route**, with the Lark app set up in memory as
`brain.ops.acceptance_checks_chat` sets it up, so a thread begun in a chat is begun by the code a
real message reaches.

Task ids: M38.5.1
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.chat.threads import Thread

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 190

A, B = RESERVED_DEPARTMENTS

#: What a check says when a person's thread held other than the exchanges asked in it.
THE_THREAD_HELD_OTHER_THAN_WHAT_WAS_ASKED: Final = (
    "a person's thread did not hold their questions and the answers they were given, in order"
)


async def _web(h: Harness) -> FastAPI:
    """The state `/answer` and the thread routes read, over the check's transaction, no model."""
    from fastapi import FastAPI

    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    app = FastAPI()
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    # The answer route reads the rule table itself on every question (M6.5.1), so nothing is
    # handed to it here: a preloaded copy would be matched beside the live one, twice.
    state.fast_path_rules = ()
    state.trace_sink = CountingTraceSink()
    return app


def _request(app: FastAPI) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": "POST"})


async def _asking(h: Harness, principal_id: str) -> Any:
    """What the routes read of a signed-in person: the principal, the reach, the instant."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    # A cast at the routes' boundary: they read these three, and a `Caller` is minted only from
    # a verified token.
    # The wall clock, as the routes read it, for `asked_on_the_web`'s reason: what the check kept
    # earlier was kept at the time it happened, after the check's start.
    return cast(
        Any,
        SimpleNamespace(
            caller=SimpleNamespace(principal=person), reach=reach, now=datetime.now(UTC)
        ),
    )


async def asked_on_the_web(
    h: Harness, app: FastAPI, principal_id: str, question: str, thread: str | None, n: int
) -> tuple[Any, str | None]:
    """One question through `/answer`'s own function, kept as the route keeps it: the answer and
    the thread it was kept in."""
    from brain.api_routes import Answering, Question, answered_for, remembered
    from brain.gate.answer import Answered
    from brain.gate.context import Channel, open_trace

    asking = await _asking(h, principal_id)
    # The wall clock, as the route reads it: a chat message kept earlier in the check was kept at
    # the time it arrived, and a web question after it must be kept after it too.
    now = datetime.now(UTC)
    answering = Answering(
        principal=asking.caller.principal, reach=asking.reach, channel=Channel.CONSOLE, now=now
    )
    ask = Question(question=question, thread=thread)
    request = _request(app)
    recorder = open_trace(f"{h.trace_id}-{n}", now, Channel.CONSOLE)
    outcome = await answered_for(request, recorder, answering, ask)
    if not isinstance(outcome, Answered):
        raise CheckFailedError("a question was refused by a window the check never installs")
    return outcome, await remembered(request, answering, ask, outcome, recorder)


async def _thread(h: Harness, principal_id: str, thread_id: str) -> Thread | None:
    from brain.chat.thread_store import StoredThreads

    return await StoredThreads(h.sessions).thread(principal_id, thread_id)


async def _listed(h: Harness, app: FastAPI, principal_id: str, search: str = "") -> list[Any]:
    """The thread list or a search, as the routes answer this person."""
    from brain.thread_routes import my_threads, search_my_threads

    asking = await _asking(h, principal_id)
    request = _request(app)
    found = (
        await search_my_threads(request, asking, search)
        if search
        else await my_threads(request, asking)
    )
    return list(found.items)


async def _opened(h: Harness, app: FastAPI, principal_id: str, thread_id: str) -> Any:
    """One thread as the route reopens it for this person, or None for its one 404."""
    from brain.core.errors import Absent
    from brain.thread_routes import my_thread

    try:
        return await my_thread(_request(app), await _asking(h, principal_id), thread_id)
    except Absent:
        return None


# ------------------------------------------------------------ 1. kept and searched (M9.1.1)
@check(
    leaves=("M9.1.1", "M9.1.3"),
    sentence=(
        "A member of acceptance_a asks a question an uploaded table answers and a follow-up in the "
        "same thread: both, and the answers, are kept in order under that one person; a member of "
        "acceptance_b naming the thread gets a new one and cannot list, open or search the first; "
        "a search finds the member's own question and never an answer's words."
    ),
)
async def a_question_is_kept_in_its_askers_thread_and_searched_by_them(
    h: Harness,
) -> None:
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_checks_chat import uploaded
    from brain.tables.chat import MessageRole

    await h.found_departments()
    table = await uploaded(h)
    member, other = h.principal(A, "member"), h.principal(B, "member")
    await h.person(member, department=A, grants=table.reads(A, held=False))
    await h.person(other, department=B, grants=_in(B, "read:knowledge"))
    app = await _web(h)

    question = table.asking(table.open_column)
    follow_up = table.asking(table.open_column) + " again"
    _, first = await asked_on_the_web(h, app, member, question, None, 1)
    if first is None:
        raise CheckFailedError("an answered question was kept in no thread")
    _, again = await asked_on_the_web(h, app, member, follow_up, first, 2)
    kept = await _thread(h, member, first)
    said = [] if kept is None else [(one.role, one.body) for one in kept.messages]
    if (
        again != first
        or kept is None
        or [role for role, _ in said] != [MessageRole.USER, MessageRole.ASSISTANT] * 2
        or [said[0][1], said[2][1]] != [question, follow_up]
        or table.seen not in said[1][1]
        or kept.title != question
    ):
        raise CheckFailedError(THE_THREAD_HELD_OTHER_THAN_WHAT_WAS_ASKED)

    _, theirs = await asked_on_the_web(h, app, other, h.word(), first, 3)
    if theirs is None or theirs == first:
        raise CheckFailedError("naming somebody else's thread continued it")
    if await _thread(h, other, first) is not None or await _opened(h, app, other, first):
        raise CheckFailedError("a thread was opened by somebody who is not its asker")
    if any(one.thread_id == first for one in await _listed(h, app, other)):
        raise CheckFailedError("a thread was listed to somebody who is not its asker")
    kept = await _thread(h, member, first)
    if kept is None or len(kept.messages) != len(said):
        raise CheckFailedError("somebody else naming a thread changed it")

    mine = [one.thread_id for one in await _listed(h, app, member, table.key)]
    if first not in mine:
        raise CheckFailedError("a search of a person's own words did not find their thread")
    if any(one.thread_id == first for one in await _listed(h, app, other, table.key)):
        raise CheckFailedError("a search found somebody else's thread")
    if any(one.thread_id == first for one in await _listed(h, app, member, table.seen)):
        raise CheckFailedError("a search matched the words of an answer")
    opened = await _opened(h, app, member, first)
    if opened is None or [one.body for one in opened.messages][:1] != [question]:
        raise CheckFailedError("the asker could not reopen their own thread")


# ------------------------------------------------------- 2. across channels (M9.1.2)
@check(
    leaves=("M9.1.2",),
    sentence=(
        "A member of acceptance_a bound in Lark asks twice in one direct chat and once in another: "
        "the first chat is one thread and the second another, both listed on the web beside their "
        "web threads, and a question asked on the web in the first continues it, so one thread "
        "holds messages from Lark and from the web."
    ),
)
async def a_thread_begun_in_lark_is_listed_and_continued_on_the_web(h: Harness) -> None:
    from brain.gate.context import Channel
    from brain.ops.acceptance_checks_chat import bound, chat_id, lark_app, open_id, uploaded

    await h.found_departments()
    chat = await lark_app(h)
    table = await uploaded(h)
    member = h.principal(A, "member")
    await h.person(member, department=A, grants=table.reads(A, held=False))
    identity = open_id()
    await bound(chat, {member: identity})
    question = table.asking(table.open_column)

    first_chat, second_chat = chat_id(), chat_id()
    for where, said in ((first_chat, question), (first_chat, question), (second_chat, question)):
        await chat.post(identity, said, chat=where, group=False, to_bot=False)
    listed = await _listed(h, chat.app, member)
    from_lark = [one for one in listed if one.last_channel == Channel.LARK.value]
    if len(from_lark) != 2:
        raise CheckFailedError("two Lark chats were not two of the person's threads")
    threads = {one.thread_id: await _thread(h, member, one.thread_id) for one in from_lark}
    sizes = sorted(len(one.messages) for one in threads.values() if one is not None)
    if sizes != [2, 4]:
        raise CheckFailedError("a person's messages in one Lark chat were not one thread")
    longer = next(key for key, one in threads.items() if one is not None and len(one.messages) == 4)

    _, continued = await asked_on_the_web(h, chat.app, member, question, longer, 1)
    kept = await _thread(h, member, longer)
    if continued != longer or kept is None:
        raise CheckFailedError("a thread begun in Lark was not continued on the web")
    channels = [one.channel for one in kept.messages]
    if channels != [Channel.LARK] * 4 + [Channel.CONSOLE] * 2:
        raise CheckFailedError("a thread continued on the web did not keep where each message was")
    latest = await _listed(h, chat.app, member)
    if not latest or latest[0].thread_id != longer or latest[0].last_channel != "console":
        raise CheckFailedError("the thread list did not say the thread was last used on the web")


# ------------------------------------------------------ 3. a follow-up's context (M9.2.3)
@check(
    leaves=("M9.2.3",),
    sentence=(
        "A member of acceptance_a asks a question their document answers, then a follow-up in the "
        "same thread naming nothing in it: the model is shown the passage the first answer cited, "
        "re-read under the member's reach, and their earlier question, never the earlier answer; "
        "the same words asked fresh find nothing."
    ),
)
async def a_follow_up_is_answered_from_what_its_thread_cited(h: Harness) -> None:
    from brain.ops.acceptance_answers import asking_with_a_stand_in
    from brain.ops.acceptance_models import pinned, shown
    from brain.ops.acceptance_routing import ANSWERS, STAND_IN_REPLY, step

    s = await asking_with_a_stand_in(h)
    await pinned(h, (step(ANSWERS),))
    first, thread = await asked_on_the_web(h, s.app, s.reader, s.paired.question, None, 1)
    if first.composed is None or thread is None or s.paired.value not in shown(first):
        raise CheckFailedError("the first question was not answered from the member's document")

    follow_up = f"and what does {h.word()} say about that"
    fresh, _ = await asked_on_the_web(h, s.app, s.reader, follow_up, None, 2)
    if fresh.composed is not None:
        raise CheckFailedError("a follow-up's words asked fresh were answered from something")
    before = len(s.responder.bodies)
    continued, same = await asked_on_the_web(h, s.app, s.reader, follow_up, thread, 3)
    if continued.composed is None or same != thread:
        raise CheckFailedError("a follow-up in the same thread was not answered in it")
    if s.paired.value not in shown(continued):
        raise CheckFailedError("a follow-up was not shown the passage its thread had cited")
    sent = "".join(s.responder.bodies[before:])
    if s.paired.question not in sent or STAND_IN_REPLY in sent:
        raise CheckFailedError(
            "a follow-up's model was not shown the earlier question, or was shown the answer"
        )


# ------------------------------------------------------------- 4. a correction (M9.2.4)
@check(
    leaves=("M9.2.4",),
    sentence=(
        "A member of acceptance_a marks the latest answer in their thread as a wrong fact: it is "
        "kept as a note in the thread naming the kind and the records the answer used, and read "
        "by the learning signal as one contradiction; nobody else can mark it, and a thread with "
        "no answer cannot be marked."
    ),
)
async def a_wrong_answer_is_kept_as_a_signal_and_no_words_with_it(h: Harness) -> None:
    from brain.chat.thread_store import CORRECTION_PREFIX, StoredThreads
    from brain.chat.turns import CorrectionKind
    from brain.core.errors import Absent
    from brain.memory.signals import Signal
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_checks_chat import uploaded
    from brain.tables.chat import MessageRole
    from brain.thread_routes import CorrectionAsked, correct_my_thread

    await h.found_departments()
    table = await uploaded(h)
    member, other = h.principal(A, "member"), h.principal(B, "member")
    await h.person(member, department=A, grants=table.reads(A, held=False))
    await h.person(other, department=B, grants=_in(B, "read:knowledge"))
    app = await _web(h)
    _, thread = await asked_on_the_web(h, app, member, table.asking(table.open_column), None, 1)
    if thread is None:
        raise CheckFailedError("an answered question was kept in no thread")

    asked = CorrectionAsked(kind=CorrectionKind.WRONG_FACT)
    try:
        await correct_my_thread(_request(app), await _asking(h, other), thread, asked)
    except Absent:
        pass
    else:
        raise CheckFailedError("somebody who is not the asker marked their answer wrong")
    kept = await correct_my_thread(_request(app), await _asking(h, member), thread, asked)
    if kept.kind != CorrectionKind.WRONG_FACT.value:
        raise CheckFailedError("a correction was not kept with the kind it was given")

    found = await _thread(h, member, thread)
    notes = [] if found is None else [m for m in found.messages if m.role is MessageRole.SYSTEM]
    if [m.body for m in notes] != [f"{CORRECTION_PREFIX}{CorrectionKind.WRONG_FACT.value}"]:
        raise CheckFailedError("a correction was not kept as a note naming its kind alone")
    if not notes[0].refs or any(one.entity != table.entity for one in notes[0].refs):
        raise CheckFailedError("a correction did not keep the records the answer used")
    signals = await StoredThreads(h.sessions).corrections(member)
    if [(one.signal, one.conversation_id) for one in signals] != [(Signal.CONTRADICTED, thread)]:
        raise CheckFailedError(
            "the learning signal did not read the correction as one contradiction"
        )
    if await StoredThreads(h.sessions).corrections(other):
        raise CheckFailedError("the learning signal read one person's correction as another's")


# ------------------------------------------- 5. an agent's conversations (M39.8.9)
@check(
    leaves=("M39.8.9",),
    sentence=(
        "Two members of acceptance_a have a thread each with one agent, one a failed run asked by "
        "a member holding no grant: the Conversations section lists each their own thread only, "
        "with the agent, their first question and how the run ended; the failed one reopens with "
        "no answer shown; and a member of acceptance_b, who may not see the agent, gets its 404."
    ),
)
async def an_agents_conversations_are_its_readers_own_and_say_what_failed(h: Harness) -> None:
    from brain.agent_conversation_routes import agent_conversations_route
    from brain.chat.remember import remember_failure
    from brain.chat.thread_store import Exchange, StoredThreads
    from brain.console.reads import Plane, plane_capability
    from brain.core.errors import Absent
    from brain.gate.context import Channel
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_checks_skills import _an_agent
    from brain.tables.chat import RunState

    await h.found_departments()
    member, colleague, outsider = (
        h.principal(A, "member"),
        h.principal(A, "colleague"),
        h.principal(B, "member"),
    )
    # The colleague holds what the workspace's Conversations tab is read under, and the member
    # holds nothing: a person's own threads need no grant, and holding one shows nobody else's.
    reads = _in(A, "read:question", *(plane_capability(one).value for one in Plane))
    await h.person(member, department=A)
    await h.person(colleague, department=A, grants=reads)
    await h.person(outsider, department=B)
    agent_id = await _an_agent(h, member)
    app = await _web(h)
    store = StoredThreads(h.sessions)
    failed_question, answered_question = h.word(), h.word()

    kept = await remember_failure(
        store,
        principal_id=member,
        thread_id=None,
        channel=Channel.CONSOLE,
        question=failed_question,
        agent_id=agent_id,
        trace_id=f"{h.trace_id}-1",
        now=h.now,
    )
    await store.record(
        colleague,
        thread_id=None,
        channel=Channel.CONSOLE,
        exchange=Exchange(
            question=answered_question,
            answer=h.word(),
            refs=(),
            agent_id=agent_id,
            trace_id=f"{h.trace_id}-2",
            state=RunState.ANSWERED,
        ),
        now=h.now,
    )
    if kept is None:
        raise CheckFailedError("a failed run was kept in no thread")

    async def listed(principal_id: str) -> list[tuple[str, str | None, list[str]]] | None:
        try:
            view = await agent_conversations_route(
                _request(app), agent_id, await _asking(h, principal_id)
            )
        except Absent:
            return None
        return [
            (one.title, one.state, [agent.agent_id for agent in one.agents]) for one in view.items
        ]

    if await listed(member) != [(failed_question, RunState.FAILED.value, [agent_id])]:
        raise CheckFailedError("a member's section did not list their own failed run as failed")
    if await listed(colleague) != [(answered_question, RunState.ANSWERED.value, [agent_id])]:
        raise CheckFailedError("a member's section listed other than their own thread")
    opened = await _opened(h, app, member, kept)
    if opened is None or [one.body for one in opened.messages] != [failed_question]:
        raise CheckFailedError("a failed run reopened with something shown as its answer")
    if await listed(outsider) is not None:
        raise CheckFailedError("the section opened on an agent its reader may not see")
