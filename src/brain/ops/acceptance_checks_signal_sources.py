"""Install check for a follow-up that says the answer was wrong, noticed as a signal about it.

`brain.memory.signals.is_contradiction` was written and argued and nothing called it: the only way a
`CONTRADICTED` signal came to be written was a person pressing the mark-wrong button. A person who
types "that is wrong, it is X" into the thread has said the same thing in words, and
`brain.chat.thread_store.StoredThreads.record` now asks the question of each follow-up, in the
asker's own session, where both texts already are, and keeps a signal naming the answer it follows.

**The check asks through `/answer`'s own function and keeps the exchange as the route keeps it**,
as `brain.ops.acceptance_checks_signal_log` does, with no model: every answer is the abstention a
process with no model lane gives, which is kept in the thread like any other. A word nothing on the
install holds is planted in the follow-up, and every column of every signal the check wrote is read
looking for it, because a signal that kept the follow-up would keep what the person said.

**What is shown and what is not.** A follow-up in the words people use to correct an assistant is
one signal naming the answer before it; a plain follow-up is none; the follow-up's words are in no
signal; and a correction said again after the next answer is a signal about that one, since one
answer is one piece of evidence per kind. What is not shown is whether a person's correction
teaches anything: that is the learning loop's, which counts a signal and never acts on one.

Task ids: M16.2.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 820

A, B = RESERVED_DEPARTMENTS

NO_CONTRADICTION_KEPT: Final = (
    "a follow-up saying the answer was wrong was not kept as one contradiction naming that answer"
)
A_PLAIN_FOLLOW_UP_WAS_ONE: Final = (
    "a follow-up that does not say the answer was wrong was kept as one"
)
SAID_AGAIN_WAS_NOT_ABOUT_THE_NEXT: Final = (
    "a correction said again after the next answer was not kept as a signal about that answer"
)
THE_FOLLOW_UP_WAS_KEPT: Final = "a signal carried the words of the follow-up that caused it"
THE_WORD_WAS_NEVER_SAID: Final = (
    "the planted word was not kept in the asker's thread, so the check proved nothing"
)


@check(
    leaves=("M16.2.3",),
    sentence=(
        "A member of acceptance_a asks a question and follows it with a plain one and then with "
        "words saying the answer was wrong: only the last is a contradiction, one signal naming "
        "the answer before it and holding none of its words, and saying it again after the next "
        "answer is a second signal about that answer."
    ),
)
async def a_follow_up_saying_the_answer_was_wrong_is_a_signal_about_it(h: Harness) -> None:
    from brain.memory.signals import Signal
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_checks_signal_log import _answers, _asked, _rows_as_text, _thread_text
    from brain.ops.acceptance_threads import _web
    from brain.ops.signal_store import StoredSignals

    await h.found_departments()
    member = h.principal(A, "member")
    await h.person(member, department=A, grants=_in(A, "read:knowledge"))
    app = await _web(h)

    planted = h.word()
    _, thread, _ = await _asked(
        h, app, member, f"How many hours are left on the {h.word()} retainer", None, 1
    )
    if thread is None:
        raise CheckFailedError("an answered question was kept in no thread")
    await _asked(h, app, member, f"What is the {h.word()} contact address", thread, 2)
    answers = await _answers(h, member, thread)
    signals = StoredSignals(h.sessions)
    if [one for one in await signals.own(member) if one.signal is Signal.CONTRADICTED]:
        raise CheckFailedError(A_PLAIN_FOLLOW_UP_WAS_ONE)

    wrong = f"That is wrong, the figure is {planted}"
    await _asked(h, app, member, wrong, thread, 3)
    answers = await _answers(h, member, thread)
    if planted not in await _thread_text(h, member, thread):
        raise CheckFailedError(THE_WORD_WAS_NEVER_SAID)
    found = [one for one in await signals.own(member) if one.signal is Signal.CONTRADICTED]
    if [(one.conversation_id, one.message_id) for one in found] != [(thread, answers[1])]:
        raise CheckFailedError(NO_CONTRADICTION_KEPT)
    if any(planted.lower() in one.lower() for one in await _rows_as_text(h, member, "mem.signal")):
        raise CheckFailedError(THE_FOLLOW_UP_WAS_KEPT)

    # Said again after the answer to it: the newest answer is now the one it follows.
    await _asked(h, app, member, "That is wrong again", thread, 4)
    again = [one for one in await signals.own(member) if one.signal is Signal.CONTRADICTED]
    if len(again) != 2 or len({one.message_id for one in again}) != 2:
        raise CheckFailedError(SAID_AGAIN_WAS_NOT_ABOUT_THE_NEXT)
