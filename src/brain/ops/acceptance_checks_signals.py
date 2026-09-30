"""The install acceptance checks for what a person tells the system about an answer, and a pause.

Each check asks through `brain.api_routes.answered_for`, as `brain.ops.acceptance_checks_memory`
does, and then acts through the stores the routes write through: `brain.ops.learning_signal_store.
StoredMarks`, what `POST /answer/mark` writes, and `StoredLearningPauses`, what `POST
/agents/{agent_id}/learning` writes. Everything is in the check's rolled-back transaction.

**A mark is proved to change nothing by asking again.** The same person asks the same question
after marking its answer unhelpful, and the model stand-in is sent the same prompt and the answer
cites the same passages, and no memory, learning or rule row appeared. That is the leaf's own
sentence, "a mark alone alters nothing a later answer retrieves", measured on the install.

**A pause is proved on an agent the check installs**, with `brain.ops.acceptance_checks_skills`'
own helper, in acceptance_a, and addressed on Ask as a person would pick it.

Task ids: M16.7.4, M16.7.13, M16.7.5
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in

# The memory checks' people, application, readers and stand-in, the tables checks' upload and the
# skills checks' agent, imported rather than copied, and imported first so the suite's own checks
# are registered ahead of these.
from brain.ops.acceptance_checks_memory import (
    PAIRED_QUESTION,
    KeptPrompts,
    a_document,
    held_anywhere,
    learnings_of,
    memories_of,
    memory_app,
    people,
)
from brain.ops.acceptance_checks_skills import _an_agent
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    SELL_PRICE,
    _administrator,
    _apply,
    _price_list,
    _upload,
)
from brain.ops.acceptance_models import asked, trace_of
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.gate.answer import Answered

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 300

#: What the steward pausing the check's agent writes as the reason.
PAUSED_BECAUSE: Final = "Paused by an install acceptance check for the length of the check"


async def rows_in_memory_and_rules(h: Harness) -> tuple[int, ...]:
    """How many rows each table that learning or a rule could change holds, in order."""
    counts = (
        await h.execute(
            text(
                "SELECT (SELECT count(*) FROM mem.persistent), (SELECT count(*) FROM mem.adaptive),"
                " (SELECT count(*) FROM mem.learning), (SELECT count(*) FROM mem.correction),"
                " (SELECT count(*) FROM gate.fast_path_rule)"
            )
        )
    ).one()
    return tuple(int(one) for one in counts)


def cited(answered: Answered) -> tuple[str, ...]:
    """The citation frames of an answer, which say what it drew on."""
    return tuple(one for one in answered.frames if one.startswith("event: citation"))


# ----------------------------------------------------------------- M16.7.4 a mark, counted
@check(
    leaves=("M16.7.4",),
    sentence=(
        "A person marks an answer from their department's document unhelpful: the mark is "
        "counted against that answer, a colleague cannot mark it, and the same question asked "
        "again sends the model the same passages and cites them, with no memory, learning or "
        "rule row written by the mark."
    ),
)
async def a_mark_is_counted_and_changes_nothing(h: Harness) -> None:
    from brain.ops.learning_signal_store import StoredMarks, Tallied

    placed = await people(h)
    words = await a_document(h)
    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in, recorded=True)
    question = PAIRED_QUESTION.format(key=words.key)
    first = await asked(h, app, placed.member, question, 1)
    if first.composed is None or len(stand_in.sent) != 1:
        raise CheckFailedError("a question the check's document answers was not answered")

    marks = StoredMarks(h.sessions)
    before = await rows_in_memory_and_rules(h)
    if await marks.mark(
        principal_id=placed.colleague, trace_id=trace_of(h, 1), helpful=False, now=h.now
    ):
        raise CheckFailedError("a colleague could mark an answer somebody else was given")
    if not await marks.mark(
        principal_id=placed.member, trace_id=trace_of(h, 1), helpful=False, now=h.now
    ):
        raise CheckFailedError("a person could not mark an answer they were given")
    if await marks.on(trace_of(h, 1)) != Tallied(helpful=0, unhelpful=1):
        raise CheckFailedError("a mark was not counted against the answer it was put on")
    if await rows_in_memory_and_rules(h) != before:
        raise CheckFailedError("a mark wrote a memory, a learning or a rule")

    again = await asked(h, app, placed.member, question, 2)
    if again.composed is None or len(stand_in.sent) != 2:
        raise CheckFailedError("the same question asked again after a mark was not answered")
    if stand_in.sent[1][1].content != stand_in.sent[0][1].content:
        raise CheckFailedError("a mark changed what the model was sent for the same question")
    if cited(again) != cited(first):
        raise CheckFailedError("a mark changed what an answer to the same question cited")


# ------------------------------------------------ M16.7.13, M16.7.5 a pause, and no values
@check(
    leaves=("M16.7.13", "M16.7.5"),
    sentence=(
        "A person reads a price from their department's uploaded list on Ask and says remember "
        "that through the department's agent: it is remembered, with no word of the price in any "
        "memory or rule. With the agent's learning paused it forms nothing while a plain question "
        "still does, and resumed it forms again."
    ),
)
async def pausing_an_agent_stops_what_its_runs_teach(h: Harness) -> None:
    from sqlalchemy import select

    from brain.agent_routes import record_of
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
    from brain.console.govern import _in_reach
    from brain.core.scope import Scope
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.columns import ColumnAccess, table_capability
    from brain.ops.acceptance_checks_speed import rules_app
    from brain.ops.acceptance_routing import roster_over
    from brain.ops.learning_signal_store import StoredLearningPauses
    from brain.prompt_routes import agent_scope_row
    from brain.tables.agent import AgentRow

    placed = await people(h)
    admin = await _administrator(h)
    prices = _price_list(h, "signals", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    if not (await _apply(h, admin, prices.entity, "department", ColumnAccess.OPEN)).applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")
    await h.grant(placed.member, table_capability(prices.entity).value, Scope.department(A))
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=_in(A, AGENT_LIFECYCLE_CAPABILITY.value))
    agent = await _an_agent(h, steward, capabilities=KNOWLEDGE_READS)

    app = await rules_app(h, KeptPrompts())
    app.state.agent_roster = roster_over(h)
    service = prices.rows[0]
    canary = service[SELL_PRICE]
    read = await asked(
        h,
        app,
        placed.member,
        QUESTION_SHAPES[0].format(label=label_of(SELL_PRICE), slot=service["name"]),
        1,
    )
    if read.text is None or canary not in read.text:
        raise CheckFailedError("a price the person may read was not answered from the list")

    async def remembered(word: str, n: int, *, through: str | None) -> bool:
        await asked(h, app, placed.member, f"Remember that I file under {word}.", n, agent=through)
        statement = f"I file under {word}"
        return any(one.statement == statement for one in await memories_of(h, placed.member))

    first, paused_word, plain, resumed = h.word(), h.word(), h.word(), h.word()
    if not await remembered(first, 2, through=agent):
        raise CheckFailedError("saying remember that through an agent did not keep it")
    formed = [one for one in await memories_of(h, placed.member) if first in one.statement]
    if await learnings_of(h, [one.memory_id for one in formed]) != [("preference", 1, agent)]:
        raise CheckFailedError("a memory formed through an agent was not recorded as its learning")
    if await held_anywhere(h, canary) or await _in_a_rule(h, canary):
        raise CheckFailedError("a value read from a source was kept in a memory or a rule")

    async with h.sessions() as session:
        row = (await session.execute(select(AgentRow).where(AgentRow.id == agent))).scalar_one()
    record = record_of(row)
    if record is None or not _in_reach(
        await h.reach(steward), AGENT_LIFECYCLE_CAPABILITY, agent_scope_row(record), h.now
    ):
        raise CheckFailedError("the agent's steward may not switch its learning")
    pauses = StoredLearningPauses(h.sessions)
    await pauses.set(agent_id=agent, paused=True, reason=PAUSED_BECAUSE, by=steward)
    if await remembered(paused_word, 3, through=agent):
        raise CheckFailedError("an agent whose learning is paused still formed a memory")
    if not await remembered(plain, 4, through=None):
        raise CheckFailedError("pausing one agent stopped a plain conversation forming memories")
    await pauses.set(agent_id=agent, paused=False, reason=PAUSED_BECAUSE, by=steward)
    if not await remembered(resumed, 5, through=agent):
        raise CheckFailedError("an agent resumed after a pause did not form memories again")


async def _in_a_rule(h: Harness, word: str) -> bool:
    """Whether any fast-path rule row holds `word`."""
    found = (
        await h.execute(
            text("SELECT 1 FROM gate.fast_path_rule WHERE position(:w in template) > 0").bindparams(
                w=word
            )
        )
    ).first()
    return found is not None
