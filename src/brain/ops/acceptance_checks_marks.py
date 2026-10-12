"""Install check for marking an answer helpful or unhelpful with one action, web and chat.

`POST /answer/mark` (`brain.api_routes.mark_answer`) and a chat reply of a word and a reference
(`brain.channels.marks`) are the two halves of one action, and each writes through
`brain.ops.learning_signal_store.StoredMarks`. The unit tests run each half over fakes, and the
existing install check of marks (`brain.ops.acceptance_checks_signals`) calls the store by hand.
What neither shows is the two doors an install has: the console route called as a signed-in person
calls it, and a chat reply that goes through the events address, the binding and the reply line the
answer itself offered, each ending in one stored mark counted against the answer it was put on.

**The two halves are asked on the answers they were offered on.** The web question is asked through
`/answer`'s own function at a trace the check knows, as `brain.ops.acceptance_threads` asks one, and
the mark goes in through the route's function with the body the page sends. The chat question is a
direct message through Lark's events address, and the reference is read off the reply, where the
answer offers it, rather than assumed: a check that built the reference would test the parser
against the check's own string. The mark is then sent as the reply a person types.

**No words are kept, and the check looks at the table.** `MarkAsked` has no field for any, so the
route cannot be handed one; the check reads every column of the marks table's definition on the
install and refuses a column that could hold a sentence. A mark that kept a reason would be a
free-text store reached from a button.

**Somebody else's answer is the same refusal either way.** A colleague marking the web answer is
refused, in the words that route gives for a trace that does not exist.

Task ids: M16.6.4
"""

from __future__ import annotations

import re
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 830

A, B = RESERVED_DEPARTMENTS

NOT_COUNTED_ON_THE_WEB: Final = (
    "a mark put on a web answer through the console's route was not counted"
)
A_COLLEAGUE_MARKED_IT: Final = "a colleague marked an answer somebody else was given"
NO_REFERENCE_OFFERED: Final = "a chat answer did not offer the reference a mark is made with"
NOT_COUNTED_IN_CHAT: Final = "a mark replied in a chat was not counted against the answer"
A_SENTENCE_COULD_BE_KEPT: Final = "the marks table has a column that could hold a person's words"

#: The widest a column may be and still be a token and not a sentence.
TOKEN_CHARS: Final = 128


@check(
    leaves=("M16.6.4",),
    sentence=(
        "A member marks a web answer helpful through the console's route and a chat answer "
        "unhelpful by replying the word and the reference the answer offered: each is counted "
        "once against its own answer, a colleague marking the web answer is refused, and the "
        "marks table holds no column that could keep words."
    ),
)
async def an_answer_is_marked_with_one_action_on_the_web_and_in_a_chat(h: Harness) -> None:
    from brain.api_routes import MarkAsked, mark_answer
    from brain.core.errors import Absent
    from brain.ops.acceptance_checks_chat import bound, chat_id, lark_app, open_id, uploaded
    from brain.ops.acceptance_threads import _asking, asked_on_the_web
    from brain.ops.learning_signal_store import StoredMarks, Tallied
    from brain.ops.telemetry_store import TelemetryRecorder

    await h.found_departments()
    chat = await lark_app(h)
    chat.app.state.request_recorders = (TelemetryRecorder(h.sessions),)
    table = await uploaded(h)
    member, colleague = h.principal(A, "marker"), h.principal(A, "colleague")
    await h.person(member, department=A, grants=table.reads(A, held=False))
    await h.person(colleague, department=A, grants=table.reads(A, held=False))
    ids = {member: open_id()}
    await bound(chat, ids)
    marks = StoredMarks(h.sessions)
    question = table.asking(table.open_column)

    # The web: asked at a trace the check knows, marked through the route as the page sends it.
    await asked_on_the_web(h, chat.app, member, question, None, 1)
    web = f"{h.trace_id}-1"
    request = chat.request()
    marked = await mark_answer(
        request, await _asking(h, member), MarkAsked(trace_id=web, helpful=True)
    )
    if not marked.counted or await marks.on(web) != Tallied(helpful=1, unhelpful=0):
        raise CheckFailedError(NOT_COUNTED_ON_THE_WEB)
    try:
        await mark_answer(
            request, await _asking(h, colleague), MarkAsked(trace_id=web, helpful=False)
        )
    except Absent:
        pass
    else:
        raise CheckFailedError(A_COLLEAGUE_MARKED_IT)

    # The chat: a direct message answered, the reference read off the reply, the mark replied.
    direct = chat_id()
    before = len(chat.lark.sent)
    await chat.post(ids[member], question, chat=direct, group=False, to_bot=False)
    answered = [one[2] for one in chat.lark.messages()[before:]]
    found = [
        ref for text_ in answered for ref in re.findall(r"unhelpful (chat-[A-Za-z0-9._:-]+)", text_)
    ]
    if len(set(found)) != 1:
        raise CheckFailedError(NO_REFERENCE_OFFERED)
    reference = found[0]
    await chat.post(ids[member], f"unhelpful {reference}", chat=direct, group=False, to_bot=False)
    if await marks.on(reference) != Tallied(helpful=0, unhelpful=1):
        raise CheckFailedError(NOT_COUNTED_IN_CHAT)

    columns = (
        await h.execute(
            text(
                "SELECT data_type, character_maximum_length FROM information_schema.columns"
                " WHERE table_schema = 'mem' AND table_name = 'mark'"
            )
        )
    ).all()
    if not columns or any(
        kind == "text" or (length is not None and length > TOKEN_CHARS) for kind, length in columns
    ):
        raise CheckFailedError(A_SENTENCE_COULD_BE_KEPT)
