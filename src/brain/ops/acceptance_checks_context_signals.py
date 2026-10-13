"""Install checks for what a turn's context names, and for a conversation handed to a person.

**A turn's trace names its context and never what the context said (M16.6.1).** A model is shown a
turn's parts through one assembler, `brain.gate.turn_context.assemble`, and the trace keeps which
parts were shown and why each other was not, in a closed vocabulary. The check asks a question a
department's document answers twice through `/answer`'s own route: once as a person who said
remember that on Ask, and once as a colleague who said nothing. The first is shown the memory as a
hint and the company's knowledge, the second the knowledge alone, and for both the two parts nothing
in the product holds, the project and the agent's own memory, are named as having no source. The
words of the memory are in neither's note, and the note's attributes survive `mask` unchanged, which
is what makes the trace able to keep them.

**A question handed to a person is a signal naming its answer (M16.2.4).** A skill that declares a
queue hands an abstained question on to the person named for it and says so in the answer. The
check asks such a question through `/answer`'s own function, keeps the exchange as the route keeps
it, and reads the asker's own signals: one escalation, naming the thread and the answer, holding no
word of the question. The same question asked of no agent hands nothing on and leaves none.

Task ids: M16.2.4, M16.6.1
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_checks_memory import (
    PAIRED_QUESTION,
    KeptPrompts,
    a_document,
    ask,
    memory_app,
    people,
)
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 874

THE_CONTEXT_WAS_NOT_NAMED: Final = "a question a model answered carried no note of its context"
THE_MEMORY_WAS_NOT_A_PART: Final = (
    "the parts a model was shown did not include the asker's memory and the company's knowledge"
)
A_COLLEAGUE_WAS_SHOWN_A_MEMORY: Final = "a colleague with no memory was named as shown one"
A_PART_WITH_NO_SOURCE_WAS_NOT_SAID: Final = (
    "the project and the agent's memory were not named as parts nothing holds"
)
THE_NOTE_CARRIED_WORDS: Final = "the note of a turn's context carried what a part said"
THE_NOTE_WAS_NOT_KEPT_BY_THE_TRACE: Final = "the note's attributes were changed by the trace's mask"
NO_ESCALATION_WAS_KEPT: Final = (
    "a question handed to a person was not kept as one escalation naming its answer"
)
THE_SIGNAL_CARRIED_WORDS: Final = "a signal row carried the words of the question handed on"
AN_ORDINARY_QUESTION_WAS_ESCALATED: Final = (
    "a question asked of no agent was kept as handed to a person"
)


# ---------------------------------------------------------------------------- M16.6.1
@check(
    leaves=("M16.6.1",),
    sentence=(
        "A person who said remember that on Ask asks a question their department's document "
        "answers and the model is shown their memory and the document; their note says so, a "
        "colleague with no memory is shown the document alone, both notes name the project and "
        "the agent's memory as parts nothing holds, none carries a word a part said, and the "
        "trace keeps the note's attributes as they are."
    ),
)
async def a_turns_trace_names_its_parts_and_never_what_they_said(
    h: Harness,
) -> None:
    from brain.gate.turn_context import LeftOut, Part
    from brain.ops.tracing import Span, mask

    placed = await people(h)
    words = await a_document(h)
    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in)
    hint = h.word()
    await ask(h, app, placed.member, f"Remember that I want {hint} in every reply.", 1)
    mine = await ask(h, app, placed.member, PAIRED_QUESTION.format(key=words.key), 2)
    theirs = await ask(h, app, placed.colleague, PAIRED_QUESTION.format(key=words.key), 3)

    if mine.context is None or theirs.context is None:
        raise CheckFailedError(THE_CONTEXT_WAS_NOT_NAMED)
    if not {Part.ASKER_MEMORY, Part.KNOWLEDGE} <= set(mine.context.included):
        raise CheckFailedError(THE_MEMORY_WAS_NOT_A_PART)
    if (
        Part.ASKER_MEMORY in theirs.context.included
        or Part.KNOWLEDGE not in theirs.context.included
    ):
        raise CheckFailedError(A_COLLEAGUE_WAS_SHOWN_A_MEMORY)
    for note in (mine.context, theirs.context):
        nothing_holds = {(Part.PROJECT, LeftOut.NO_SOURCE), (Part.AGENT_MEMORY, LeftOut.NO_SOURCE)}
        if not nothing_holds <= set(note.left_out):
            raise CheckFailedError(A_PART_WITH_NO_SOURCE_WAS_NOT_SAID)
        said = " ".join(note.attributes().values())
        if hint in said or words.value in said or words.key in said:
            raise CheckFailedError(THE_NOTE_CARRIED_WORDS)
        attributes = dict(note.attributes())
        if (
            dict(
                mask(
                    Span(name="request", environment=h.settings.env, attributes=attributes)
                ).attributes
            )
            != attributes
        ):
            raise CheckFailedError(THE_NOTE_WAS_NOT_KEPT_BY_THE_TRACE)


# ---------------------------------------------------------------------------- M16.2.4
@check(
    leaves=("M16.2.4",),
    sentence=(
        "A member of acceptance_a asks an agent whose skill escalates a question nothing answers: "
        "the exchange is kept with one escalation signal naming the thread and the answer and "
        "holding no word of the question, and the same question asked of no agent leaves none."
    ),
)
async def a_question_handed_to_a_person_is_a_signal_naming_its_answer(h: Harness) -> None:
    from brain.api_routes import Answering, Question, answered_for, remembered
    from brain.gate.answer import Answered
    from brain.gate.context import Channel, open_trace
    from brain.memory.signals import Signal
    from brain.ops.acceptance_escalation import _escalating_agent
    from brain.ops.acceptance_routing import roster_over
    from brain.ops.acceptance_threads import _asking, _request, _web
    from brain.ops.signal_store import StoredSignals

    await h.found_departments()
    agent, _ = await _escalating_agent(h)
    member = h.principal(A, "handed_on")
    await h.person(member, department=A, grants=_in(A, "read:knowledge"))
    app = await _web(h)
    app.state.agent_roster = roster_over(h)

    async def one(question: str, picked: str | None, n: int) -> tuple[Answered, str | None]:
        asking = await _asking(h, member)
        answering = Answering(
            principal=asking.caller.principal,
            reach=asking.reach,
            channel=Channel.CONSOLE,
            now=asking.now,
        )
        ask_ = Question(question=question, agent=picked)
        request = _request(app)
        recorder = open_trace(f"{h.trace_id}-{n}", answering.now, Channel.CONSOLE)
        outcome = await answered_for(request, recorder, answering, ask_)
        if not isinstance(outcome, Answered):
            raise CheckFailedError("a question was refused by a window the check never installs")
        return outcome, await remembered(request, answering, ask_, outcome, recorder)

    planted = h.word()
    handed, thread = await one(f"Who signs off the {planted} retainer renewal", agent, 1)
    if not handed.escalated or thread is None:
        raise CheckFailedError(NO_ESCALATION_WAS_KEPT)
    signals = StoredSignals(h.sessions)
    kept = [one for one in await signals.own(member) if one.signal is Signal.ESCALATED]
    if len(kept) != 1 or kept[0].conversation_id != thread:
        raise CheckFailedError(NO_ESCALATION_WAS_KEPT)
    if planted.lower() in repr(kept[0]).lower():
        raise CheckFailedError(THE_SIGNAL_CARRIED_WORDS)

    ordinary, other = await one(f"Who signs off the {h.word()} contract renewal", None, 2)
    if ordinary.escalated or any(
        one.signal is Signal.ESCALATED and one.conversation_id == other
        for one in await signals.own(member)
    ):
        raise CheckFailedError(AN_ORDINARY_QUESTION_WAS_ESCALATED)
