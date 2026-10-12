"""Install check for session memory: said for one conversation, silent, and gone with it.

`brain.ops.session_memory_store.StoredSessions` keeps, in the install's own cache, what a person
said for one conversation only, and `brain.api_routes` binds it to the model's next turn once the
route has found the conversation as the asker's own and live. Its unit tests run over a fake
client. What they cannot show is that, on an install, over the real cache and the real answer path,
a statement made for a conversation is shown to the model on the next turn of that conversation and
on no other, to nobody else, and not at all once the conversation is retired, and that keeping it
changes nothing a person could later be shown.

**The cache is the install's and the keys are the check's own.** The check asks the install's cache,
which `brain.app.lifespan` builds from the address in the settings, and says it was not run where
the process was given none. Every key it writes is named from a reserved principal and a thread
nothing else holds, and is deleted by name when the check ends whatever happened, which is
`brain.ops.acceptance.WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`; the store itself has
no delete, so the check's own cleanup uses a client of its own.

**The model is a stand-in that keeps its prompt**, as `brain.ops.acceptance_checks_memory` puts one
behind the model service, because whether a statement is shown is a fact about the prompt the
install builds. Everything before it is the install's own: the gate, the passage search over the
check's document, the redactor, the recall, the prompt, and the session store.

**The route's two halves are asked in the route's order.** `/answer` answers and then, once the
exchange has its thread, keeps what was said (`brain.api_routes.session_formed`). The check asks
through `answered_for` and `remembered`, as `brain.ops.acceptance_threads` does, and then calls
`session_formed` as the route does, because `asked_on_the_web` stops before it.

**Silence is checked as rows and as a person's screen.** Keeping a statement writes the cache and
nothing else: the counts of every table that learning or a rule could change are the same after, and
no weekly digest is told to anybody about it. A memory held only in a cache is not one the Memory
screen could list.

Task ids: M16.1.1, M16.3.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_memory import (
    PAIRED_QUESTION,
    KeptPrompts,
    a_document,
    memory_app,
    people,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.cache import AsyncValkeyClient

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 825

A, B = RESERVED_DEPARTMENTS

NO_CACHE: Final = (
    "the worker running this check was not given the cache address the application uses, so "
    "there is no cache to keep a conversation's notes in"
)
NOT_SHOWN_ON_THE_NEXT_TURN: Final = (
    "what a person said for one conversation was not shown to the model on that conversation's "
    "next turn"
)
SHOWN_ELSEWHERE: Final = (
    "what a person said for one conversation was shown on another conversation, to another "
    "person, or after the conversation was retired"
)
NOT_KEPT_IN_THE_CACHE: Final = "what a person said for one conversation was not kept in the cache"
KEPT_IN_A_MEMORY: Final = (
    "keeping what a person said for one conversation changed a memory, a learning, a correction "
    "or a rule"
)


@dataclass
class KeptKeys:
    """The session store's client over another, keeping each key name it is told to write."""

    inner: AsyncValkeyClient
    keys: list[str] = field(default_factory=list)

    async def get(self, name: str) -> bytes | None:
        return await self.inner.get(name)

    async def setex(self, name: str, time: int, value: bytes) -> object:
        self.keys.append(name)
        return await self.inner.setex(name, time, value)

    async def ping(self) -> object:
        return await self.inner.ping()


def session_client(h: Harness) -> KeptKeys:
    """The install's own cache as the application's session memory uses it, with every key the
    check writes removed when the check ends. Not run on a process given no cache address.

    The store has no delete, so the cleanup uses a client of its own and deletes the keys named by
    `KeptKeys`. A module-level function so a test can stand an in-memory client where the install's
    stands.
    """
    from brain.cache import make_async_client, make_client

    if not h.settings.valkey_url:
        raise CheckNotRunError(NO_CACHE)
    url = h.settings.valkey_url
    client = make_async_client(url)
    sync = make_client(url)
    kept = KeptKeys(client)

    async def closed() -> None:
        await client.aclose()

    def removed() -> None:
        if kept.keys:
            cast(Any, sync).delete(*kept.keys)

    h.removes(closed)
    h.removes(cast(Any, sync).close)
    h.removes(removed)
    return kept


def _prompt(model: KeptPrompts) -> str:
    """The last request the stand-in was sent, every turn of it after the system message."""
    return "\n".join(message.content for message in model.sent[-1][1:])


def _holds_the_heading(model: KeptPrompts) -> bool:
    """Whether the last prompt carries the section a session memory is shown under.

    The heading and not the words: a follow-up's prompt holds the thread's earlier turns, which
    include what the person typed, so the words alone would be found there with the session store
    switched off. The heading is what only the session store's memory is shown under.
    """
    from brain.gate.model_lane import SESSION_HEADING

    return SESSION_HEADING in _prompt(model)


def _holds(model: KeptPrompts, said: str) -> bool:
    return _holds_the_heading(model) and said in _prompt(model)


async def _asked(
    h: Harness, app: Any, principal_id: str, question: str, thread: str | None, n: int
) -> str:
    """One question as the web's route asks it and keeps it, and the thread it was kept in."""
    from brain.ops.acceptance_threads import asked_on_the_web

    _, kept = await asked_on_the_web(h, app, principal_id, question, thread, n)
    if kept is None:
        raise CheckFailedError("an answered question was kept in no thread")
    return kept


@check(
    leaves=("M16.1.1", "M16.3.1"),
    sentence=(
        "A member of acceptance_a says, for one conversation, how they want answers: the next "
        "question in that conversation shows the model the statement, a new conversation, a "
        "colleague naming the same thread and a conversation retired do not, and keeping it wrote "
        "only the cache, changing no memory, learning, correction or rule."
    ),
)
async def session_memory_is_one_conversations_own_and_silent(h: Harness) -> None:
    from brain.api_routes import session_formed
    from brain.ops.acceptance_checks_signals import rows_in_memory_and_rules
    from brain.ops.session_memory_store import StoredSessions

    client = session_client(h)
    placed = await people(h)
    words = await a_document(h)
    model = KeptPrompts()
    app = await memory_app(h, model)
    app.state.session_memory = StoredSessions(client)
    # A word of its own: the document holds the preference word, so a model shown that passage
    # would seem to have been shown the statement.
    said = h.word()
    statement = f"I want {said} answers"
    before = await rows_in_memory_and_rules(h)

    thread = await _asked(h, app, placed.member, f"For this conversation, {statement}.", None, 1)
    await session_formed(
        app.state,
        principal_id=placed.member,
        thread_id=thread,
        said=f"For this conversation, {statement}.",
        now=datetime.now(UTC),
    )
    sessions = StoredSessions(client)
    if not await sessions.recalled(thread, placed.member):
        raise CheckFailedError(NOT_KEPT_IN_THE_CACHE)
    if await sessions.recalled(thread, placed.colleague):
        raise CheckFailedError(SHOWN_ELSEWHERE)

    question = PAIRED_QUESTION.format(key=words.key)
    mark = len(model.sent)
    await _asked(h, app, placed.member, question, thread, 2)
    if len(model.sent) == mark or not _holds(model, said):
        raise CheckFailedError(NOT_SHOWN_ON_THE_NEXT_TURN)

    for who, naming in ((placed.member, None), (placed.colleague, thread)):
        mark = len(model.sent)
        await _asked(h, app, who, question, naming, 3)
        if len(model.sent) == mark or _holds_the_heading(model):
            raise CheckFailedError(SHOWN_ELSEWHERE)

    # The conversation is retired as the table's own policy allows, at the statement's instant:
    # it is no longer the asker's live one, so nothing is shown.
    await h.execute(
        text("SELECT set_config('app.principal_id', :who, true)").bindparams(who=placed.member),
        text(
            "UPDATE chat.conversation SET deleted_at = statement_timestamp()"
            " WHERE id = CAST(:thread AS uuid)"
        ).bindparams(thread=thread),
    )
    mark = len(model.sent)
    await _asked(h, app, placed.member, question, thread, 4)
    if len(model.sent) == mark or _holds_the_heading(model):
        raise CheckFailedError(SHOWN_ELSEWHERE)

    if await rows_in_memory_and_rules(h) != before:
        raise CheckFailedError(KEPT_IN_A_MEMORY)
