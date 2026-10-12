"""The install check for a copied answer, kept as the one positive signal and in no words.

A member asks a question through `/answer`'s own function, which keeps the exchange in their thread
as the route does, and copies the answer through `POST /answer/copied`'s own function
(`brain.api_routes.copied_answer`). The signal log then holds one copy naming the thread and the
answer, no row of it holds a word of the question, a colleague copying the same trace is told the
same sentence and nothing is kept for them or for the member, a trace that never ran is the same,
and copying twice is still one piece of evidence. Everything is inside the check's transaction.

**The sentence is the same whether or not anything was kept**, and the check holds it to that: a
route that told a person whether a trace was theirs would be a way to find out which traces exist.

Task ids: M16.2.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 873

NO_COPY_WAS_KEPT: Final = "a copied answer was not kept as one copy naming its thread and answer"
A_WORD_WAS_KEPT: Final = "a copy's signal row carried a word of the question it was about"
A_COLLEAGUE_S_COPY_WAS_KEPT: Final = "somebody else's copy of an answer was kept for somebody"
A_COPY_TWICE_WAS_TWO: Final = "one answer copied twice was kept as two pieces of evidence"
A_COPY_TOLD_WHETHER_IT_WAS_KEPT: Final = (
    "a copy was answered differently whether or not it was the caller's own answer"
)
A_NON_ANSWER_WAS_COPIED: Final = "a trace that never ran was kept as a copied answer"


@check(
    leaves=("M16.2.2",),
    sentence=(
        "A member of acceptance_a copies an answer they were given: one copy signal names the "
        "thread and the answer and holds no word of the question, copying it again adds nothing, "
        "a colleague's copy of the same answer and a copy of a trace that never ran keep nothing "
        "and are told what the member was told."
    ),
)
async def a_copied_answer_is_one_signal_naming_it_and_no_words(h: Harness) -> None:
    from brain.api_routes import CopiedAsked, copied_answer
    from brain.memory.signals import Signal
    from brain.ops.acceptance_checks_signal_log import _rows_as_text, _thread_text
    from brain.ops.acceptance_threads import _asking, _request, _web, asked_on_the_web
    from brain.ops.signal_store import StoredSignals

    await h.found_departments()
    member, colleague = h.principal(A, "copier"), h.principal(A, "colleague")
    await h.person(member, department=A, grants=_in(A, "read:knowledge"))
    await h.person(colleague, department=A, grants=_in(A, "read:knowledge"))
    app = await _web(h)
    planted = h.word()
    _, thread = await asked_on_the_web(
        h, app, member, f"How many hours are left on the {planted} retainer", None, 1
    )
    if thread is None or planted not in await _thread_text(h, member, thread):
        raise CheckFailedError("the answered question was not kept in the member's thread")
    trace = f"{h.trace_id}-1"
    request = _request(app)
    signals = StoredSignals(h.sessions)

    async def copy(who: str, which: str) -> str:
        said = await copied_answer(request, await _asking(h, who), CopiedAsked(trace_id=which))
        return said.told

    first = await copy(member, trace)
    kept = [one for one in await signals.own(member) if one.signal is Signal.COPIED]
    if len(kept) != 1 or kept[0].conversation_id != thread:
        raise CheckFailedError(NO_COPY_WAS_KEPT)
    if any(planted.lower() in one.lower() for one in await _rows_as_text(h, member, "mem.signal")):
        raise CheckFailedError(A_WORD_WAS_KEPT)

    again = await copy(member, trace)
    if len([one for one in await signals.own(member) if one.signal is Signal.COPIED]) != 1:
        raise CheckFailedError(A_COPY_TWICE_WAS_TWO)

    theirs = await copy(colleague, trace)
    nothing = await copy(member, f"{h.trace_id}-never")
    if await signals.own(colleague):
        raise CheckFailedError(A_COLLEAGUE_S_COPY_WAS_KEPT)
    if len([one for one in await signals.own(member) if one.signal is Signal.COPIED]) != 1:
        raise CheckFailedError(A_NON_ANSWER_WAS_COPIED)
    if len({first, again, theirs, nothing}) != 1:
        raise CheckFailedError(A_COPY_TOLD_WHETHER_IT_WAS_KEPT)
