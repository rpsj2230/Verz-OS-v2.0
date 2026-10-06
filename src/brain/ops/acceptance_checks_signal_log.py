"""The install acceptance check for the learning signal's log: kept where it happens, in no words.

The check asks through `/answer`'s own function and keeps the exchange through the route's own
`remembered`, as `brain.ops.acceptance_threads` does, marks an answer wrong through the
corrections route's own function, and reads what was kept back through `brain.ops.signal_store`,
as reserved people in the reserved departments, inside the check's rolled-back transaction.

**It needs no model.** It asks two questions that share their subject in different words and one
that does not, so the re-ask detector has a real decision to make in each direction, and every
answer is the abstention a process with no model lane gives, which is kept in the thread like
any other. A word nothing on the install holds is planted in the first question, and the check
reads every column of every signal it wrote looking for it, and reads the thread to prove the
word was really there to be copied. See `A_PLANTED_WORD_IS_LOOKED_FOR_IN_EVERY_COLUMN`.

A retrieval is not checked here: `ops.retrieval_event` (migration `0193`) keeps M15.3.4's log, and
its own check proves it.

Task ids: M16.2.8, M9.2.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.gate.answer import Answered

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 442

A, B = RESERVED_DEPARTMENTS

#: Why the planted word is looked for in the whole row and not in a column chosen for it.
A_PLANTED_WORD_IS_LOOKED_FOR_IN_EVERY_COLUMN: Final = (
    "A signal table that copied a question would copy it into whatever column was nearest, so "
    "the check reads each row whole, as JSON, and looks for a word nothing else on the install "
    "holds. It reads the thread too, because a word that was never stored anywhere proves "
    "nothing by being absent."
)

# ---------------------------------------------------------------- what a check says on failure
#: A question asked again in different words left no signal naming the earlier answer.
NO_REASK_KEPT: Final = (
    "a question asking the thread's last one again in different words was not kept as a signal "
    "naming the earlier answer, at the trace it was asked on"
)
#: A question on another subject was kept as a re-ask.
AN_UNRELATED_QUESTION_WAS_A_REASK: Final = (
    "a question on another subject was kept as a re-ask of the answer before it"
)
#: Marking an answer wrong left no contradiction naming it.
NO_CORRECTION_KEPT: Final = (
    "an answer marked wrong was not kept as one contradiction naming that answer"
)
#: The planted word reached a signal row.
WORDS_IN_A_SIGNAL: Final = "a signal row carried the words of the question it was about"
#: The planted word was not in the thread, so its absence from the signals proves nothing.
THE_WORD_WAS_NEVER_ASKED: Final = (
    "the planted word was not kept in the asker's thread, so the check proved nothing"
)
#: Another person read the asker's signals, or wrote one in their name.
ANOTHER_PERSON_REACHED_A_SIGNAL: Final = (
    "somebody who is not the asker read their signals or wrote one in their name"
)
#: Signals were counted by person, or the install's count was not by kind.
COUNTED_BY_PERSON: Final = (
    "signals could be counted per person, or the install's count was not by kind alone"
)


async def _asked(
    h: Harness,
    app: FastAPI,
    principal_id: str,
    question: str,
    thread: str | None,
    n: int,
) -> tuple[Answered, str | None, str]:
    """One question through `/answer`'s own function, kept as the route keeps it, at its own
    trace: the answer, the thread it was kept in, and the trace."""
    from brain.api_routes import Answering, Question, answered_for, remembered
    from brain.gate.answer import Answered
    from brain.gate.context import Channel, open_trace
    from brain.ops.acceptance_threads import _asking, _request

    asking = await _asking(h, principal_id)
    answering = Answering(
        principal=asking.caller.principal,
        reach=asking.reach,
        channel=Channel.CONSOLE,
        now=asking.now,
    )
    ask = Question(question=question, thread=thread)
    request = _request(app)
    trace = f"{h.trace_id}-{n}"
    recorder = open_trace(trace, answering.now, Channel.CONSOLE)
    outcome = await answered_for(request, recorder, answering, ask)
    if not isinstance(outcome, Answered):
        raise CheckFailedError("a question was refused by a window the check never installs")
    kept = await remembered(request, answering, ask, outcome, recorder)
    return outcome, kept, trace


async def _answers(h: Harness, principal_id: str, thread: str) -> list[str]:
    """The ids of the answers in this person's thread, oldest first, read in their name."""
    from brain.tables.chat import MessageRole

    async with h.sessions() as session:
        await session.execute(
            text("SELECT set_config('app.principal_id', :p, true)"), {"p": principal_id}
        )
        rows = (
            await session.execute(
                text(
                    "SELECT id FROM chat.message WHERE conversation_id = CAST(:t AS uuid)"
                    " AND role = :role ORDER BY created_at, id"
                ),
                {"t": thread, "role": MessageRole.ASSISTANT.value},
            )
        ).all()
        await session.rollback()
    return [str(one[0]) for one in rows]


async def _rows_as_text(h: Harness, principal_id: str, table: str) -> list[str]:
    """Every row of `table` this person may read, each whole, as JSON text."""
    async with h.sessions() as session:
        await session.execute(
            text("SELECT set_config('app.principal_id', :p, true)"), {"p": principal_id}
        )
        # The table is one of this module's two literals, never input.
        rows = (await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} AS t"))).all()  # noqa: S608
        await session.rollback()
    return [str(one[0]) for one in rows]


async def _thread_text(h: Harness, principal_id: str, thread: str) -> str:
    """Every word kept in this person's thread, questions included."""
    from brain.chat.thread_store import StoredThreads

    found = await StoredThreads(h.sessions).thread(principal_id, thread)
    return "" if found is None else "\n".join(one.body for one in found.messages)


async def _written_as(h: Harness, writer: str, owner: str, thread: str, answer: str) -> bool:
    """Whether `writer`'s session may write a signal in `owner`'s name; in a savepoint, undone."""
    from sqlalchemy.exc import DBAPIError

    async with h.sessions() as session:
        await session.execute(
            text("SELECT set_config('app.principal_id', :p, true)"), {"p": writer}
        )
        try:
            await session.execute(
                text(
                    "INSERT INTO mem.signal (signal, conversation_id, message_id, principal_id, at)"
                    " VALUES ('reasked', CAST(:t AS uuid), CAST(:m AS uuid), :owner, :at)"
                ),
                {"t": thread, "m": answer, "owner": owner, "at": h.now},
            )
            await session.flush()
        except DBAPIError:
            await session.rollback()
            return False
        await session.rollback()
    return True


# ------------------------------------------------- 1. a re-ask and a correction (M16.2.8, M9.2.4)
@check(
    leaves=("M16.2.8", "M9.2.4"),
    sentence=(
        "A member of acceptance_a asks a question with a planted word, asks it again in other "
        "words, asks about something else and marks the last answer wrong: the re-ask and the "
        "correction are two signals naming their answers, the other question is none, no signal "
        "holds the planted word, acceptance_b can neither read nor write one, and signals are "
        "counted by kind and never per person."
    ),
)
async def a_reask_and_a_correction_are_logged_by_id_and_never_in_words(h: Harness) -> None:
    from brain.chat.turns import CorrectionKind
    from brain.memory.signals import Signal
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_threads import _asking, _request, _web
    from brain.ops.signal_store import StoredSignals
    from brain.thread_routes import CorrectionAsked, correct_my_thread

    await h.found_departments()
    member, other = h.principal(A, "member"), h.principal(B, "member")
    await h.person(member, department=A, grants=_in(A, "read:knowledge"))
    await h.person(other, department=B, grants=_in(B, "read:knowledge"))
    app = await _web(h)
    started = datetime.now(UTC)

    planted, subject = h.word(), h.word()
    first = f"How many hours are left on the {subject} retainer {planted}"
    again = f"What is the remaining hours balance for the {subject} retainer"
    elsewhere = f"Who approved the {h.word()} invoice last week"
    _, thread, _ = await _asked(h, app, member, first, None, 1)
    if thread is None:
        raise CheckFailedError("an answered question was kept in no thread")
    _, same, reasked_on = await _asked(h, app, member, again, thread, 2)
    _, still, _ = await _asked(h, app, member, elsewhere, thread, 3)
    if same != thread or still != thread:
        raise CheckFailedError("a question naming the asker's own thread was kept elsewhere")
    answers = await _answers(h, member, thread)
    if len(answers) != 3:
        raise CheckFailedError("the thread did not hold the three answers given in it")

    # The word first, before anything else is read off a row, so a row carrying it fails as that.
    if planted not in await _thread_text(h, member, thread):
        raise CheckFailedError(THE_WORD_WAS_NEVER_ASKED)
    rows = await _rows_as_text(h, member, "mem.signal")
    if any(planted.lower() in one.lower() for one in rows):
        raise CheckFailedError(WORDS_IN_A_SIGNAL)

    signals = StoredSignals(h.sessions)
    kept = await signals.own(member)
    reasks = [one for one in kept if one.signal is Signal.REASKED]
    if len(reasks) > 1:
        raise CheckFailedError(AN_UNRELATED_QUESTION_WAS_A_REASK)
    if [(one.conversation_id, one.message_id) for one in reasks] != [(thread, answers[0])]:
        raise CheckFailedError(NO_REASK_KEPT)
    traced = [one for one in await _rows_as_text(h, member, "mem.signal") if reasked_on in one]
    if len(traced) != 1:
        raise CheckFailedError(NO_REASK_KEPT)

    asked = CorrectionAsked(kind=CorrectionKind.WRONG_FACT)
    await correct_my_thread(_request(app), await _asking(h, member), thread, asked)
    kept = await signals.own(member)
    corrections = [one for one in kept if one.signal is Signal.CONTRADICTED]
    if [(one.conversation_id, one.message_id) for one in corrections] != [(thread, answers[2])]:
        raise CheckFailedError(NO_CORRECTION_KEPT)

    rows = await _rows_as_text(h, member, "mem.signal")
    if len(rows) != 2 or any(planted.lower() in one.lower() for one in rows):
        raise CheckFailedError(WORDS_IN_A_SIGNAL)

    if await signals.own(other) or await _written_as(h, other, member, thread, answers[1]):
        raise CheckFailedError(ANOTHER_PERSON_REACHED_A_SIGNAL)
    if not await _written_as(h, member, member, thread, answers[1]):
        raise CheckFailedError("the asker could not write a signal in their own name")

    try:
        await signals.counts_by(member, "principal_id")
    except ValueError:
        pass
    else:
        raise CheckFailedError(COUNTED_BY_PERSON)
    mine = await signals.counts_by(member, "signal")
    counted = await signals.counted(
        since=started - timedelta(minutes=1), until=datetime.now(UTC) + timedelta(minutes=1)
    )
    kinds = {one.value for one in Signal}
    if (
        dict(mine) != {Signal.REASKED.value: 1, Signal.CONTRADICTED.value: 1}
        or not set(counted) <= kinds
        or counted.get(Signal.REASKED.value, 0) < 1
        or counted.get(Signal.CONTRADICTED.value, 0) < 1
    ):
        raise CheckFailedError(COUNTED_BY_PERSON)
