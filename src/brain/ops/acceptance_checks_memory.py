"""The install acceptance checks for memory: a person is remembered, and only as far as they reach.

Each check asks through `brain.api_routes.answered_for`, the one function the web's Ask and every
chat channel answer through, as a reserved person in a reserved department, on an application whose
stores are the check's rolled-back transaction. Then it reads back what the install's own tables
hold and what the install's own decisions say about it: the rows in `mem.persistent`,
`mem.adaptive` and `mem.learning`, `brain.console.govern_estate.subject_memory`, which is what the
Memory screen and My workspace show, and `brain.ops.memory_store.StoredRecall`, which is what a
model answering the person is shown. So what is proved is the install forming a memory from a real
conversation and recalling it within the rules, and not a store called by hand.

**Until 2026-09-29 none of these could pass on any install**, because nothing called
`StoredFormations.after_turn`: the Memory and Learning screens could only ever be empty. These
checks are what says that stays fixed.

**The model is a stand-in that keeps its prompt, and nothing else here is.** Whether a model is
shown a person's memories is a fact about the prompt the install builds, and a provider's reply
adds nothing to it but a cost and a vendor's words. So the check that needs a model answer puts a
stand-in behind `app.state.models` that keeps every prompt it is sent and replies with one fixed
sentence, and everything before it is the install's own: the gate, the passage search over the
check's own document, the redactor, the recall and the prompt. See
`A_MODEL_THAT_KEEPS_ITS_PROMPT_STANDS_IN_FOR_THE_PROVIDER`. Rejected: asking a real provider, which
would send a reserved person's memory to a vendor on every deploy to prove a string was in a prompt.

**A document is the check's own and names words nothing else holds.** The passage search is the
text leg alone, whose query needs every word of the question, so the only passage anybody is shown
is the check's own sentence; this is `brain.ops.acceptance_models`'
`A_CHECK_S_QUESTION_IS_SHOWN_ONLY_ITS_OWN_DOCUMENT`, reused with its helpers.

Task ids: M16.1.2, M16.1.3, M16.1.4, M16.1.5, M16.4.1, M16.4.4, M16.6.3, M16.7.10, M16.7.12
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import text

from brain.core.entitlement import Capability
from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check

# The documents check's upload and its reader's grants, and the Ask helpers, imported rather than
# copied, and imported first so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
from brain.ops.acceptance_models import asked
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.models.disclosure import DataCategory
    from brain.models.driver import DriverMessage, DriverResponse
    from brain.models.metering import Meter
    from brain.models.registry import ModelPin
    from brain.models.routing import RoutingRequest, Tier

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 160

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the checks that need a model answer put a stand-in behind it.
A_MODEL_THAT_KEEPS_ITS_PROMPT_STANDS_IN_FOR_THE_PROVIDER: Final = (
    "Whether a model is shown a person's memories is a fact about the prompt the install builds. "
    "So a stand-in behind the model service keeps every prompt and replies with one fixed "
    "sentence, and the gate, the search, the redactor, the recall and the prompt are the "
    "install's own. No provider is sent a reserved person's memory, and nothing is billed."
)

# ------------------------------------------------------------------------ the figures
#: What the stand-in replies, whatever it is asked. Words nothing else holds, so a memory or a
#: learning holding them is a memory formed from an answer.
REPLY: Final = "The paired word is QZREPLYSTANDIN."

#: How long past formation an inference is asked about, in days: three half-lives, well past the
#: point an extracted memory's confidence falls below the floor.
DECAYED_AFTER_DAYS: Final = 90

#: How long past formation a stated memory is asked about, in days: ten years.
STATED_AFTER_DAYS: Final = 3_650

#: The one sentence each check's document holds, and the question that finds it.
DOCUMENT: Final = (
    "What is {key} paired with? {key} is paired with {value}. I prefer {pref} answers."
)
PAIRED_QUESTION: Final = "What is {key} paired with?"
PREFERENCE_QUESTION: Final = "I prefer {pref} answers. What is {key} paired with?"


# ------------------------------------------------------------------------ the model stand-in
@dataclass
class KeptPrompts:
    """`brain.gate.model_lane.AnswerModel` keeping each prompt and replying with `REPLY`."""

    sent: list[tuple[DriverMessage, ...]] = field(default_factory=list)
    categories: list[tuple[str, ...]] = field(default_factory=list)
    #: The output cap each call was made with, as `brain.gate.effort` pinned it for the lane.
    caps: list[int | None] = field(default_factory=list)

    async def complete(
        self,
        messages: Sequence[DriverMessage],
        *,
        lane: Any,
        meter: Meter,
        trace_id: str,
        tier: Tier | None = None,
        routing: RoutingRequest | None = None,
        reach: Sequence[Scope] = (),
        agent_version: str | None = None,
        max_output_tokens: int | None = None,
        pin: ModelPin | None = None,
        categories: Sequence[DataCategory] = (),
    ) -> DriverResponse:
        from brain.models.driver import DriverResponse, TokenUsage

        self.sent.append(tuple(messages))
        self.categories.append(tuple(one.value for one in categories))
        self.caps.append(max_output_tokens)
        meter.attempted()
        response = DriverResponse(
            deployment_id="acceptance_stand_in",
            model="acceptance_stand_in",
            text=REPLY,
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            finish_reason="stop",
        )
        meter.answered(response, provider="acceptance_stand_in", agent_version=agent_version)
        return response

    def told(self) -> str:
        """Every request turn the stand-in was sent, as one text."""
        return "\n".join(message.content for sent in self.sent for message in sent[1:])


# ------------------------------------------------------------------------ the application
async def memory_app(
    h: Harness, model: KeptPrompts | None = None, *, recorded: bool = False
) -> FastAPI:
    """The state `/answer` reads, each part over the check's transaction.

    What `brain.app.lifespan` installs, as `brain.ops.acceptance_models.asking_app` builds it, with
    `model` behind the model service when the check needs an answer from one. With none, a question
    no rule answers is abstained on, which is what a stated memory must survive. `recorded` adds
    the request row's recorder, for a check that reads the ledger; the cost is never recorded,
    because the stand-in has no price.
    """
    import httpx
    from fastapi import FastAPI

    from brain.gate.model_lane import DocumentSearchTool
    from brain.gate.rule_store import load_rules
    from brain.knowledge.document_tools import searcher
    from brain.knowledge.row_store import SessionRowSource
    from brain.models.calls import ModelCalls
    from brain.ops.model_service import ModelService
    from brain.ops.telemetry_store import TelemetryRecorder
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    try:
        rules = await load_rules(h.sessions)
    except Exception:
        # The lifespan's choice for a rule table that cannot be read: an empty rule set.
        rules = ()
    app = FastAPI()
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    state.fast_path_rules = rules
    state.trace_sink = CountingTraceSink()
    state.request_recorders = (TelemetryRecorder(h.sessions),) if recorded else ()
    if model is not None:
        client = httpx.Client()
        h.removes(client.close)
        # The stand-in is an `AnswerModel`, which is every part of `ModelCalls` the lane calls.
        state.models = ModelService(calls=cast(ModelCalls, model), client=client)
        state.passage_search = DocumentSearchTool(handler=searcher(SessionRowSource(h.sessions)))
    return app


@dataclass(frozen=True)
class Placed:
    """The people a check asks as: a member of acceptance_a, a colleague beside them, and a member
    of acceptance_b holding the same capabilities over their own department."""

    member: str
    colleague: str
    other: str


async def people(h: Harness) -> Placed:
    """Both departments founded, and three people whose every grant is scoped to a department."""
    await h.found_departments()
    placed = Placed(
        member=h.principal(A, "member"),
        colleague=h.principal(A, "colleague"),
        other=h.principal(B, "member"),
    )
    await h.person(placed.member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(placed.colleague, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(placed.other, department=B, grants=_in(B, *KNOWLEDGE_READS))
    return placed


@dataclass(frozen=True)
class Words:
    """A document's key, the value it pairs it with, and a preference word, none held elsewhere."""

    key: str
    value: str
    pref: str


async def a_document(h: Harness) -> Words:
    """A Markdown document in acceptance_a, uploaded by a library keeper there."""
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.ops.acceptance_documents import a_markdown_document

    keeper = h.principal(A, "library")
    await h.person(keeper, department=A, grants=_in(A, "admin:knowledge"))
    words = Words(key=h.word(), value=h.word(), pref=h.word())
    body = a_markdown_document(
        "Acceptance check",
        DOCUMENT.format(key=words.key, value=words.value, pref=words.pref),
    )
    read = await _upload(
        h,
        keeper,
        filename="Acceptance.md",
        declared=MediaType.MARKDOWN.value,
        body=body,
        department=A,
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed document the door accepts could not be read")
    return words


# ------------------------------------------------------------------------ reading back
@dataclass(frozen=True)
class Row:
    """One memory row of a person's, as the check reads it."""

    memory_id: str
    kind: str
    statement: str
    tags: tuple[str, ...]
    scope: Mapping[str, Any]
    confidence: float | None


async def memories_of(h: Harness, principal_id: str) -> list[Row]:
    """Every memory formed while `principal_id` was asking, from both tables."""
    rows = (
        await h.execute(
            text(
                "SELECT id, kind, statement, capability_tags, scope, NULL::float8"
                " FROM mem.persistent WHERE principal_id = :pid"
                " UNION ALL SELECT id, kind, statement, capability_tags, scope, formed_confidence"
                " FROM mem.adaptive WHERE principal_id = :pid ORDER BY 3"
            ).bindparams(pid=principal_id)
        )
    ).all()
    return [
        Row(
            memory_id=str(one[0]),
            kind=str(one[1]),
            statement=str(one[2]),
            tags=tuple(one[3]),
            scope=one[4],
            confidence=None if one[5] is None else float(one[5]),
        )
        for one in rows
    ]


async def learnings_of(h: Harness, memory_ids: Sequence[str]) -> list[tuple[str, int, str | None]]:
    """The change, tier and agent each of these memories' learning records names."""
    rows = (
        await h.execute(
            text(
                "SELECT change, tier, agent_id FROM mem.learning WHERE memory_id = ANY(:ids)"
                " ORDER BY memory_id"
            ).bindparams(ids=list(memory_ids))
        )
    ).all()
    return [(str(one[0]), int(one[1]), one[2]) for one in rows]


async def held_anywhere(h: Harness, word: str) -> bool:
    """Whether any memory, learning or correction row of the install holds `word`."""
    found = (
        await h.execute(
            text(
                "SELECT 1 FROM mem.persistent WHERE position(:w in statement) > 0"
                " UNION ALL SELECT 1 FROM mem.adaptive WHERE position(:w in statement) > 0"
                " UNION ALL SELECT 1 FROM mem.learning WHERE position(:w in subject) > 0"
                " UNION ALL SELECT 1 FROM mem.correction"
                " WHERE position(:w in coalesce(field, '')) > 0 LIMIT 1"
            ).bindparams(w=word)
        )
    ).first()
    return found is not None


async def shown_about(
    h: Harness, subject: str, reader: EntitlementSet, now: datetime
) -> dict[str, float]:
    """What the Memory screen and My workspace show `reader` about `subject`, statement by
    statement with its confidence, through the functions both routes call."""
    from brain.console.govern_estate import subject_memory
    from brain.estate_routes import MAX_MEMORIES_CONSIDERED, remembered_about

    async with h.sessions() as session:
        stored = await remembered_about(session, subject, MAX_MEMORIES_CONSIDERED)
    remembered = subject_memory(
        subject_id=subject,
        entries=stored.entries,
        reader=reader,
        now=now,
        supersessions=stored.corrections.supersessions,
        demotions=stored.corrections.demotions,
    )
    return {
        one.statement: one.seen.confidence
        for one in (*remembered.memory.curated, *remembered.memory.extracted)
    }


async def recalled_for(
    h: Harness, reader: EntitlementSet, department: str, now: datetime
) -> tuple[str, ...]:
    """What a model answering `reader` would be shown about them, through the recall store the
    answer route binds, at the place the route recalls from."""
    from brain.memory.turn import recall_place
    from brain.ops.memory_store import StoredRecall

    return await StoredRecall(h.sessions).recalled(
        reader, where=recall_place(reader.principal_id, department), now=now
    )


async def recalled_of(
    h: Harness, subject: str, reader: EntitlementSet, department: str, now: datetime
) -> tuple[str, ...]:
    """What recall would admit of `subject`'s memories for `reader` asking from their own place.

    The store's own reading of the rows and `brain.memory.recall.recall`, asked about somebody
    else's memories, which the answer route never reads: this is the rule, shown to refuse them."""
    from brain.memory.recall import recall
    from brain.memory.turn import recall_place
    from brain.ops.memory_store import (
        MAX_READ_FOR_RECALL,
        corrections_naming,
        corrections_of,
        inferred_rows_of,
        kept_of,
        stated_rows_of,
    )

    async with h.sessions() as session:
        rows = [
            *(await session.execute(stated_rows_of(subject, MAX_READ_FOR_RECALL))).scalars(),
            *(await session.execute(inferred_rows_of(subject, MAX_READ_FOR_RECALL))).scalars(),
        ]
        kept = [one for one in map(kept_of, rows) if one is not None]
        marks = (
            (await session.execute(corrections_naming([one.memory_id for one in kept])))
            .scalars()
            .all()
        )
    found = corrections_of(marks)
    said = {one.memory_id: one.statement for one in kept}
    admitted = recall(
        kept,
        reader,
        now=now,
        supersessions=found.supersessions,
        demotions=found.demotions,
        where=recall_place(reader.principal_id, department),
    )
    return tuple(said[one.memory_id] for one in admitted)


def unending(reach: EntitlementSet) -> EntitlementSet:
    """The same grants with no end, for a reading made long after the check started.

    A reserved person lapses an hour after their check begins, which is the harness's rule and not
    the memory's; a reading ninety days or ten years on is about decay, so it is made as the same
    person holding the same grants with no bound."""
    return reach.model_copy(update={"not_after": None})


async def ask(h: Harness, app: FastAPI, principal_id: str, question: str, n: int) -> Answered:
    """One question through the answer route's own function, as `principal_id`."""
    return await asked(h, app, principal_id, question, n)


def cited(answered: Answered) -> str:
    """Every citation frame the person was sent, as one text."""
    return "\n".join(one for one in answered.frames if one.startswith("event: citation"))


# -------------------------------------------------------- M16.1.2, M16.7.12 formed and read
@check(
    leaves=("M16.1.2", "M16.7.12"),
    sentence=(
        "A person whose every grant is scoped to acceptance_a says remember that on Ask, and the "
        "install keeps it as a stated memory with its learning record and shows it back to them "
        "on their memory page and to a model answering them; a colleague beside them is shown "
        "none of it in answers, and a person in acceptance_b holding the same grants none at all."
    ),
)
async def a_stated_memory_forms_and_only_its_person_reads_it(
    h: Harness,
) -> None:
    placed = await people(h)
    app = await memory_app(h)
    word = h.word()
    said = f"Remember that I work from {word} on Fridays."
    await ask(h, app, placed.member, said, 1)

    rows = await memories_of(h, placed.member)
    statement = f"I work from {word} on Fridays"
    if [(one.kind, one.statement, one.confidence) for one in rows] != [
        ("persistent", statement, None)
    ]:
        raise CheckFailedError("saying remember that on Ask did not keep a stated memory")
    [row] = rows
    if not _names(row.scope, placed.member, A):
        raise CheckFailedError("a stated memory was not kept in its person's own place")
    if await learnings_of(h, [row.memory_id]) != [("preference", 1, None)]:
        raise CheckFailedError("a stated memory was kept with no tier one learning record")

    member, colleague, other = (
        await h.reach(placed.member),
        await h.reach(placed.colleague),
        await h.reach(placed.other),
    )
    if await shown_about(h, placed.member, member, h.now) != {statement: 1.0}:
        raise CheckFailedError(
            "a person whose grants are scoped to their department was not shown their own memory"
        )
    if await recalled_for(h, member, A, h.now) != (statement,):
        raise CheckFailedError("a model answering the person would not be shown their memory")
    for reader, department in ((colleague, A), (other, B)):
        if await recalled_of(h, placed.member, reader, department, h.now):
            raise CheckFailedError("somebody else's answer would be shown a person's memory")
    if await shown_about(h, placed.member, other, h.now):
        raise CheckFailedError("a person in another department was shown somebody's memory")


def answered_at(reach: EntitlementSet) -> EntitlementSet:
    """The reach Ask answers a signed-in person at, as `brain.ops.acceptance_models.asked` admits
    it: what a memory formed on Ask is tagged with."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel

    return admit(reach, Channel.CONSOLE, Assurance.AUTHENTICATED)


def _names(scope: Mapping[str, Any], principal_id: str, department: str) -> bool:
    """Whether a stored scope names the person and the department they said it in, and nothing
    else. Read through `brain.memory.formation.place_of`, the reading recall itself makes."""
    from brain.memory.formation import place_of

    try:
        place = place_of(Scope.model_validate(scope))
    except ValueError:
        return False
    return place == {"principal_id": principal_id, "department": department}


# ------------------------------------------------ M16.1.4, M16.4.4 re-checked at every read
@check(
    leaves=("M16.1.4", "M16.4.4"),
    sentence=(
        "A memory a person formed on Ask records the capabilities they held, is shown back to "
        "them while they hold them, and stops being shown on the Memory screen and to a model "
        "the moment one of those grants is removed, with nothing purged."
    ),
)
async def a_memory_is_not_recalled_once_its_grant_goes(
    h: Harness,
) -> None:
    from brain.govern_routes import retire_grant

    placed = await people(h)
    app = await memory_app(h)
    word = h.word()
    await ask(h, app, placed.member, f"Remember that I sign as {word}.", 1)
    statement = f"I sign as {word}"

    rows = await memories_of(h, placed.member)
    if len(rows) != 1:
        raise CheckFailedError("saying remember that on Ask did not keep a stated memory")
    [row] = rows
    held = await h.reach(placed.member)
    capabilities = sorted({grant.capability.value for grant in answered_at(held).grants})
    if sorted(row.tags) != capabilities or "read:knowledge.title" not in capabilities:
        raise CheckFailedError("a memory did not record the capabilities its person held")
    if statement not in await shown_about(h, placed.member, held, h.now):
        raise CheckFailedError("a memory was not shown to its person while they held its grants")

    await h.execute(*h.attributed(), retire_grant(placed.member, "read:knowledge.title"))
    narrower = await h.reach(placed.member)
    if narrower.holds(Capability(value="read:knowledge.title"), h.now):
        raise CheckFailedError("a removed grant was still held on the next read of the reach")
    if await shown_about(h, placed.member, narrower, h.now):
        raise CheckFailedError("a memory was still shown after a grant it needed was removed")
    if await recalled_for(h, narrower, A, h.now):
        raise CheckFailedError("a model would still be shown a memory after its grant was removed")
    if len(await memories_of(h, placed.member)) != 1:
        raise CheckFailedError("removing a grant deleted a memory rather than leaving it unread")


# --------------------------------------------- M16.1.3, M16.4.1, M16.7.10 decay by kind
@check(
    leaves=("M16.1.3", "M16.4.1", "M16.7.10"),
    sentence=(
        "A person states one thing and lets slip a preference in an answered question on Ask; "
        "the preference is kept as an inference below full confidence and is no longer recalled "
        "three months later, while the statement is recalled at full confidence ten years on."
    ),
)
async def an_inference_decays_and_a_statement_does_not(
    h: Harness,
) -> None:
    from brain.memory.formation import RECALL_FLOOR

    placed = await people(h)
    words = await a_document(h)
    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in)
    stated = h.word()
    await ask(h, app, placed.member, f"Remember that I file under {stated}.", 1)
    answered = await ask(
        h,
        app,
        placed.member,
        PREFERENCE_QUESTION.format(pref=words.pref, key=words.key),
        2,
    )
    if answered.composed is None or not stand_in.sent:
        raise CheckFailedError("a question the check's document answers was not answered")

    kinds = {
        row.statement: (row.kind, row.confidence) for row in await memories_of(h, placed.member)
    }
    inferred = f"I prefer {words.pref} answers"
    said = f"I file under {stated}"
    if kinds.get(said) != ("persistent", None):
        raise CheckFailedError("a stated memory was not kept as stated")
    kept = kinds.get(inferred)
    if kept is None or kept[0] != "adaptive" or kept[1] is None or not RECALL_FLOOR < kept[1] < 1:
        raise CheckFailedError(
            "a preference said in an answered question was not kept as an inference"
        )

    member = unending(await h.reach(placed.member))
    now = await shown_about(h, placed.member, member, h.now)
    if set(now) != {said, inferred}:
        raise CheckFailedError("a person was not shown both memories the day they formed")
    later = h.now + timedelta(days=DECAYED_AFTER_DAYS)
    if set(await shown_about(h, placed.member, member, later)) != {said}:
        raise CheckFailedError("an inference was still recalled after three half-lives")
    if await recalled_for(h, member, A, later) != (said,):
        raise CheckFailedError("a model would still be shown an inference after it decayed")
    ten_years = await shown_about(
        h, placed.member, member, h.now + timedelta(days=STATED_AFTER_DAYS)
    )
    if ten_years != {said: 1.0}:
        raise CheckFailedError("a stated memory lost confidence with time")


# ------------------------------------------------ M16.6.3, M16.1.5 a hint and never a source
@check(
    leaves=("M16.6.3", "M16.1.5"),
    sentence=(
        "A person who said remember that on Ask asks a question their department's document "
        "answers; the model is sent their memory as a hint beside the question and the answer "
        "cites the document alone, while a colleague asking the same is sent no hint of theirs, "
        "and no memory holds a word the answer carried."
    ),
)
async def a_model_sees_the_askers_memory_as_a_hint_only(
    h: Harness,
) -> None:
    from brain.gate.model_lane import HINTS_HEADING

    placed = await people(h)
    words = await a_document(h)
    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in)
    hint = h.word()
    await ask(h, app, placed.member, f"Remember that I want {hint} in every reply.", 1)
    answered = await ask(h, app, placed.member, PAIRED_QUESTION.format(key=words.key), 2)

    if answered.composed is None or len(stand_in.sent) != 1:
        raise CheckFailedError("a question the check's document answers was not answered")
    told = stand_in.told()
    if f"- I want {hint} in every reply" not in told or HINTS_HEADING not in told:
        raise CheckFailedError("a model was not shown the asker's memory as a hint")
    if hint in stand_in.sent[0][0].content:
        raise CheckFailedError("an asker's memory reached the prompt region every caller shares")
    if "memory_hints" not in stand_in.categories[0]:
        raise CheckFailedError("a prompt carrying a memory did not say so on its attempt")
    if hint in cited(answered) or words.value not in told:
        raise CheckFailedError("an answer cited a memory, or the model was not shown the document")
    documents = [] if answered.provenance is None else answered.provenance.documents
    if not documents:
        raise CheckFailedError("an answer built beside a memory did not cite its document")

    await ask(h, app, placed.colleague, PAIRED_QUESTION.format(key=words.key), 3)
    if len(stand_in.sent) != 2:
        raise CheckFailedError("a colleague's question the document answers was not answered")
    if hint in "\n".join(message.content for message in stand_in.sent[1]):
        raise CheckFailedError("a colleague's model was shown somebody else's memory")
    for word in (words.value, "QZREPLYSTANDIN"):
        if await held_anywhere(h, word):
            raise CheckFailedError("a value an answer carried was kept in a memory or a learning")
