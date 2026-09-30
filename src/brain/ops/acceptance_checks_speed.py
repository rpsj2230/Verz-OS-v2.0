"""The install acceptance checks for speed: the fast lane, the answer stream and the prompt's shape.

Each check asks through `brain.api_routes.answered_for`, the function the web's Ask and every chat
channel answer through, as reserved people in acceptance_a, on an application whose stores are the
check's rolled-back transaction, and reads back what the install did: the frames a person is sent,
the request row the ledger keeps, and the prompt a model would be sent. What they prove is that
the fast lane answers from rows with no model, that what streams to a person is steps, then
citations, then prose and never reasoning, and that every prompt starts with the same bytes.

**A fast-lane rule is a row the check writes into `gate.fast_path_rule`, and it is read back by
the install's own loader.** `brain.gate.rule_store.load_rules` is what the lifespan calls at start,
so the rule the check asks is the rule a restart would load. What it answers from is a price list
the check uploads into acceptance_a through the Classification routes' own sequence, reused from
`brain.ops.acceptance_checks_tables`, so the row the rule reads is a row a department uploaded.

**Where a model is needed it is the stand-in that keeps its prompt**, from
`brain.ops.acceptance_checks_memory`, for that module's reason: the prompt is the install's and a
provider would only add a bill. The fast-lane checks hold the same stand-in and prove it was never
called, which is the fast lane's whole promise.

**M6.1.3 is proved as the role the lane now reads under.** Since `0162` every read the fast lane
makes is marked as its own (`brain.knowledge.rows.read_as_the_fast_lane`) and read as
`brain_fastlane`, which holds `SELECT` on `proj.record` and `know.classified_row` and nothing else.
The check answers an uploaded list's price on the lane, watches the lane's reads carry the mark,
asks the install's row source who it reads as with the mark and without, and asks the database,
as the role, for every table it answers from and a table in `know`, another schema and a write of
each kind it must refuse. M6.5.1 needs a console
surface for rules, which does not exist, and rules load only at start, so it is listed in the
package's report rather than claimed.

Task ids: M6.1.1, M6.1.2, M6.1.4, M6.1.6, M6.3.1, M6.3.2, M6.3.3, M6.3.4, M6.3.5, M6.4.2
Task ids: M6.4.3, M6.4.4, M6.1.3
"""

from __future__ import annotations

import pkgutil
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in

# The price list upload and the memory checks' stand-in, imported rather than copied, and imported
# first so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks_memory import (
    PAIRED_QUESTION,
    KeptPrompts,
    a_document,
    memory_app,
)
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    SELL_PRICE,
    _administrator,
    _apply,
    _price_list,
    _PriceList,
    _upload,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.gate.answer import Answered
    from brain.gate.context import Channel

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 270

# ------------------------------------------------------------------------ the figures
#: How a rule the check writes asks for a price, around a word nothing else holds. The hole is
#: the slot `name`, the price list's key column.
RULE_TEMPLATE: Final = "acceptance rate {word} for {{name}}"

#: One frame as the encoder writes it: `event: <name>`, then one `data:` line per line of value.
_FRAME: Final = re.compile(r"^event: (?P<event>[a-z_]+)\n(?P<data>(?:data: ?.*(?:\n|$))*)")


@dataclass(frozen=True)
class Frame:
    """One event a person was sent, decoded as a browser's `EventSource` would dispatch it."""

    event: str
    data: str


def decoded(answered: Answered) -> list[Frame]:
    """Every frame of an answer, decoded: its event name and its data lines joined by newlines.

    A frame that is not an event is refused as the check's failure, because a browser drops it.
    """
    found: list[Frame] = []
    for frame in answered.frames:
        matched = _FRAME.match(frame)
        if matched is None or not frame.endswith("\n\n"):
            raise CheckFailedError("an answer was sent a frame that is not a server-sent event")
        lines = [line[len("data:") :].removeprefix(" ") for line in frame.split("\n")[1:] if line]
        found.append(Frame(event=matched["event"], data="\n".join(lines)))
    return found


# ------------------------------------------------------------------------ the set-up
@dataclass(frozen=True)
class RuleOnAList:
    """A price list in acceptance_a, a rule row asking its sell price, and a reader of it."""

    prices: _PriceList
    reader: str
    template: str

    def question(self, service: int = 0) -> str:
        return self.template.replace("{name}", self.prices.rows[service]["name"])


async def a_rule_on_a_list(h: Harness) -> RuleOnAList:
    """Both departments, a price list uploaded into acceptance_a, a rule row over it written into
    the rule table, and a member of acceptance_a holding the list's table grant there."""
    from brain.gate.fast_lane import DECLARED_FIELDS
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.columns import ColumnAccess, table_capability
    from brain.tables.fast_lane import FastPathRuleRow

    await h.found_departments()
    admin = await _administrator(h)
    prices = _price_list(h, "speed", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    # As the table check opens it: a row's department is what a department-scoped grant is
    # matched against, and a first upload holds it restricted.
    opened = await _apply(h, admin, prices.entity, "department", ColumnAccess.OPEN)
    if not opened.applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")
    reader = h.principal(A, "asker")
    await h.person(
        reader,
        department=A,
        grants=_in(A, table_capability(prices.entity).value, *KNOWLEDGE_READS),
    )
    template = RULE_TEMPLATE.format(word=h.word().lower())
    row = {
        "rule_id": f"acceptance_{h.run}_rate",
        "template": template,
        "slot": "name",
        "source": TABLES_SOURCE,
        "entity": prices.entity,
        "match_field": "name",
        "answer_field": SELL_PRICE,
    }
    if set(row) != set(DECLARED_FIELDS):
        raise CheckFailedError("a rule row did not carry exactly the fields a rule is read from")
    await h.execute(*h.attributed(), insert(FastPathRuleRow).values(**row, created_by=h.actor))
    return RuleOnAList(prices=prices, reader=reader, template=template)


async def rules_app(h: Harness, model: KeptPrompts) -> FastAPI:
    """`brain.ops.acceptance_checks_memory.memory_app`, recording each request's row, with the
    rules the install's own loader reads from the rule table in the check's transaction."""
    from brain.gate.rule_store import load_rules

    app = await memory_app(h, model, recorded=True)
    app.state.fast_path_rules = await load_rules(h.sessions)
    return app


async def asked_on(
    h: Harness, app: FastAPI, principal_id: str, question: str, n: int, channel: Channel
) -> Answered:
    """One question through the answer route's own function, as `principal_id` on `channel`, at
    the reach that channel admits a signed-in person, under a trace of this check's own."""
    from starlette.requests import Request

    from brain.api_routes import Answering, Question, answered_for
    from brain.gate.admission import Assurance, admit
    from brain.gate.answer import Answered
    from brain.gate.context import open_trace
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), channel, Assurance.AUTHENTICATED)
    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    outcome = await answered_for(
        request,
        open_trace(trace_of(h, n), h.now, channel),
        Answering(principal=person, reach=reach, channel=channel, now=h.now),
        Question(question=question),
    )
    if not isinstance(outcome, Answered):
        raise CheckFailedError("a question was refused by a window the check never installs")
    return outcome


def trace_of(h: Harness, n: int) -> str:
    """The trace the check's `n`th request runs under."""
    return f"{h.trace_id}-{n}"


async def row_of(h: Harness, n: int) -> tuple[str, str | None, str | None, str] | None:
    """The lane, provider, model and traffic class of the request row the `n`th ask left."""
    rows = (
        await h.execute(
            text(
                "SELECT lane, provider, model, traffic_class FROM obs.request_telemetry"
                " WHERE trace_id = :trace"
            ).bindparams(trace=trace_of(h, n))
        )
    ).all()
    if len(rows) != 1:
        return None
    lane, provider, model, traffic = rows[0]
    return str(lane), provider, model, str(traffic)


# ----------------------------------------------- M6.1.1, M6.1.2, M6.1.4 a rule row answers
@check(
    leaves=("M6.1.1", "M6.1.2", "M6.1.4"),
    sentence=(
        "A rule written as a row, read by the install's own loader, answers a price asked in its "
        "exact words from a list acceptance_a uploaded, on the fast lane with no model call and "
        "a lane that can reach no tool; the same words with more around them, and a rule for a "
        "table nothing serves, are not answered by a rule."
    ),
)
async def a_rule_row_answers_on_the_fast_lane_with_no_model(h: Harness) -> None:
    from brain.gate import fast_lane
    from brain.gate.context import Channel
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.tables.fast_lane import FastPathRuleRow

    made = await a_rule_on_a_list(h)
    stranger = RULE_TEMPLATE.format(word=h.word().lower()).replace("rate", "tariff")
    await h.execute(
        *h.attributed(),
        insert(FastPathRuleRow).values(
            rule_id=f"acceptance_{h.run}_nowhere",
            template=stranger,
            slot="name",
            source=TABLES_SOURCE,
            entity=f"acceptance_{h.run}_nowhere",
            match_field="name",
            answer_field=SELL_PRICE,
            created_by=h.actor,
        ),
    )
    stand_in = KeptPrompts()
    app = await rules_app(h, stand_in)
    ids = {one.rule_id for one in app.state.fast_path_rules}
    if f"acceptance_{h.run}_rate" not in ids:
        raise CheckFailedError("a rule written as a row was not read by the install's loader")

    service = made.prices.rows[0]
    answered = await asked_on(h, app, made.reader, made.question(), 1, Channel.CONSOLE)
    if answered.text is None or service[SELL_PRICE] not in answered.text:
        raise CheckFailedError("a rule row did not answer the price it was written for")
    if stand_in.sent or await row_of(h, 1) != ("fast", None, None, "human_interactive"):
        raise CheckFailedError("a rule row's answer was not recorded on the fast lane alone")
    try:
        fast_lane.assert_reaches_no_tool_and_no_model(fast_lane)
    except Exception:
        raise CheckFailedError("the install's fast lane can reach a tool or a model") from None

    longer = await asked_on(
        h, app, made.reader, f"please tell me {made.question()}", 2, Channel.CONSOLE
    )
    nowhere = await asked_on(
        h, app, made.reader, stranger.replace("{name}", service["name"]), 3, Channel.CONSOLE
    )
    for told in (longer, nowhere):
        if told.text is not None and service[SELL_PRICE] in told.text:
            raise CheckFailedError("a rule answered words it was not written for")
    if stand_in.sent:
        raise CheckFailedError("a question nothing retrieved for was sent to a model")


# ---------------------------------------------------------- M6.1.6 people and not machines
@check(
    leaves=("M6.1.6",),
    sentence=(
        "One person asks the rule's price on the console and a program asks it on the API; both "
        "are answered on the fast lane and recorded, and the lane figures the Models screen "
        "draws count the person and not the program."
    ),
)
async def the_fast_lane_share_counts_people_and_not_machines(h: Harness) -> None:
    from brain.gate.context import Channel
    from brain.operate_routes import lane_traffic, requests_by_lane

    made = await a_rule_on_a_list(h)
    app = await rules_app(h, KeptPrompts())
    for n, channel in ((1, Channel.CONSOLE), (2, Channel.API)):
        told = await asked_on(h, app, made.reader, made.question(), n, channel)
        if told.text is None:
            raise CheckFailedError("a rule row did not answer the price it was written for")
    rows = (await row_of(h, 1), await row_of(h, 2))
    if rows != (
        ("fast", None, None, "human_interactive"),
        ("fast", None, None, "automation"),
    ):
        raise CheckFailedError("a person's and a program's answers were not both recorded")

    # Every ask was received at the check's own instant, so the window holds its rows alone.
    window = (h.now, h.now + timedelta(microseconds=1))
    counted = [one._tuple() for one in (await h.execute(requests_by_lane(*window))).all()]
    figures = {one.lane: one.requests for one in lane_traffic(counted)}
    if figures.get("fast") != 1 or sum(figures.values()) != 1:
        raise CheckFailedError("the lane figures counted a program's question as a person's")


# ------------------------------------- M6.3.1 to M6.3.5 what streams to a person, in order
@check(
    leaves=("M6.3.1", "M6.3.2", "M6.3.3", "M6.3.4", "M6.3.5"),
    sentence=(
        "A fast-lane answer and a model answer each reach the person as server-sent events: "
        "named steps from the fixed vocabulary, with no figure and no source's name in them, "
        "then the citations, then the prose, then done, and no event carrying reasoning."
    ),
)
async def an_answer_streams_steps_then_citations_then_prose(h: Harness) -> None:
    import brain.connectors
    from brain.api_routes import EVENT_STREAM
    from brain.gate.context import Channel
    from brain.gate.streaming import STEP_LABELS, Event, scope_revealing

    if EVENT_STREAM != "text/event-stream":
        raise CheckFailedError("the answer route does not answer as a server-sent event stream")
    made = await a_rule_on_a_list(h)
    words = await a_document(h)
    stand_in = KeptPrompts()
    app = await rules_app(h, stand_in)
    fast = await asked_on(h, app, made.reader, made.question(), 1, Channel.CONSOLE)
    drafted = await asked_on(
        h, app, made.reader, PAIRED_QUESTION.format(key=words.key), 2, Channel.CONSOLE
    )
    if fast.text is None or drafted.composed is None or len(stand_in.sent) != 1:
        raise CheckFailedError("a fast-lane question and a document question were not answered")

    sources = tuple(one.name for one in pkgutil.iter_modules(brain.connectors.__path__))
    named = {one.value for one in Event}
    labels = set(STEP_LABELS.values())
    for answered in (fast, drafted):
        frames = decoded(answered)
        events = [one.event for one in frames]
        if not set(events) <= named or "reasoning" in events:
            raise CheckFailedError("an answer streamed an event outside the vocabulary")
        steps = [one.data for one in frames if one.event == Event.STEP.value]
        if not steps or not set(steps) <= labels:
            raise CheckFailedError("an answer's progress was not named in the fixed vocabulary")
        if any(scope_revealing(one, sources) for one in steps):
            raise CheckFailedError("a progress step carried a figure or a source's name")
        stepped = [n for n, one in enumerate(events) if one == Event.STEP.value]
        cited = [n for n, one in enumerate(events) if one == Event.CITATION.value]
        prose = [n for n, one in enumerate(events) if one == Event.TEXT.value]
        if not cited or not prose or max(stepped) > min(cited) or max(cited) > min(prose):
            raise CheckFailedError("an answer's citations did not arrive before its prose")
        if events[-1] != Event.DONE.value or events.index(Event.STEP.value) != 0:
            raise CheckFailedError("an answer did not open with a step and close with done")


# ------------------------------------------ M6.4.2, M6.4.3, M6.4.4 the prompt's shared bytes
@check(
    leaves=("M6.4.2", "M6.4.3", "M6.4.4"),
    sentence=(
        "Two people in acceptance_a with different grants ask a question their document "
        "answers: the prompt each model call carries opens with the same bytes, holding nothing "
        "of either person or the document, and each call has the answer lane's length "
        "instruction after that and the same output cap beside it."
    ),
)
async def every_prompt_opens_with_the_same_bytes_and_one_length(h: Harness) -> None:
    from brain.core.lane import Lane
    from brain.gate.context import Channel
    from brain.gate.effort import settings_for
    from brain.gate.model_lane import PREFIX

    await h.found_departments()
    words = await a_document(h)
    first, second = h.principal(A, "first"), h.principal(A, "second")
    await h.person(first, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(second, department=A, grants=_in(A, *KNOWLEDGE_READS, "read:knowledge.section"))
    stand_in = KeptPrompts()
    app = await memory_app(h, stand_in)
    question = PAIRED_QUESTION.format(key=words.key)
    for n, person in enumerate((first, second), start=1):
        told = await asked_on(h, app, person, question, n, Channel.CONSOLE)
        if told.composed is None:
            raise CheckFailedError("a question the check's document answers was not answered")
    if len(stand_in.sent) != 2:
        raise CheckFailedError("two people's questions were not each sent to the model once")

    shared = {one[0].content for one in stand_in.sent}
    if shared != {PREFIX.text}:
        raise CheckFailedError("two people's prompts did not open with the same bytes")
    for leaked in (first, second, A, words.key, words.value):
        if leaked.casefold() in PREFIX.text.casefold():
            raise CheckFailedError("the bytes every prompt opens with named a person or a record")
    pinned = settings_for(Lane.ANSWER)
    for sent in stand_in.sent:
        if not sent[1].content.rstrip().endswith(pinned.instruction):
            raise CheckFailedError("a prompt did not end with the lane's length instruction")
    if set(stand_in.caps) != {pinned.max_output_tokens}:
        raise CheckFailedError("two people's calls were not made with the lane's one output cap")
    if pinned.instruction in PREFIX.text:
        raise CheckFailedError("the length instruction sat in the bytes every caller shares")


# ------------------------------------------------------ M6.1.3 the fast lane's own role
#: What the fast lane's role is refused, each a statement the database judges before it reads a
#: row: a table in `know` it was not given, a table in another schema, and a write of each kind.
REFUSED_TO_THE_FAST_LANE: Final[tuple[str, ...]] = (
    "SELECT 1 FROM know.item LIMIT 1",
    "SELECT 1 FROM know.chunk LIMIT 1",
    "SELECT 1 FROM know.classified_table LIMIT 1",
    "SELECT 1 FROM gate.capability_grant LIMIT 1",
    "SELECT 1 FROM mem.persistent LIMIT 1",
    "INSERT INTO know.classified_row (entity, version, position, fields) "
    "VALUES ('acceptance', 1, 0, '{}'::jsonb)",
    "UPDATE know.classified_row SET position = position WHERE false",
    "DELETE FROM proj.record WHERE false",
    "UPDATE proj.record SET entity = entity WHERE false",
)

#: What it may read, and all of it.
READ_BY_THE_FAST_LANE: Final[tuple[str, ...]] = (
    "SELECT 1 FROM proj.record LIMIT 1",
    "SELECT 1 FROM know.classified_row LIMIT 1",
)

#: SQLSTATE `insufficient_privilege`: the database refusing the role, and nothing else.
INSUFFICIENT_PRIVILEGE: Final = "42501"


async def as_the_fast_lane(h: Harness, statement: str) -> str | None:
    """Run one statement as the fast lane's role in a savepoint of its own, and say how it ended:
    None when it ran, or the SQLSTATE the database refused it with. Rolled back either way."""
    from sqlalchemy.exc import DBAPIError

    from brain.knowledge.row_store import SET_FAST_LANE_ROLE

    async with h.sessions() as session:
        try:
            await session.execute(text(SET_FAST_LANE_ROLE))
            await session.execute(text(statement))
        except DBAPIError as refused:
            await session.rollback()
            return str(getattr(refused.orig, "sqlstate", "") or "")
        await session.rollback()
    return None


@check(
    leaves=("M6.1.3",),
    sentence=(
        "A price asked in a rule's exact words of a list acceptance_a uploaded is answered on the "
        "fast lane, whose every read is marked as the lane's and read as brain_fastlane; that "
        "role reads the projected records and uploaded rows, and the database refuses it every "
        "other table in know, every other schema and every write."
    ),
)
async def the_fast_lane_reads_as_a_role_that_reaches_nothing_else(h: Harness) -> None:
    from sqlalchemy import func, select

    from brain.gate.context import Channel
    from brain.gate.fast_lane import respond
    from brain.knowledge.row_store import FAST_LANE_ROLE, SessionRowSource
    from brain.knowledge.rows import RowQuery, is_a_fast_lane_read, read_as_the_fast_lane
    from brain.ops.classification_store import classified_lane_of

    made = await a_rule_on_a_list(h)
    stand_in = KeptPrompts()
    app = await rules_app(h, stand_in)
    answered = await asked_on(h, app, made.reader, made.question(), 1, Channel.CONSOLE)
    if answered.text is None or made.prices.rows[0][SELL_PRICE] not in answered.text:
        raise CheckFailedError("the fast lane did not answer a price from an uploaded list")
    if stand_in.sent or await row_of(h, 1) != ("fast", None, None, "human_interactive"):
        raise CheckFailedError("an uploaded list's price was not answered on the fast lane alone")

    # The lane the route answered through, its reads watched: every one the lane makes is marked.
    lane = await classified_lane_of(app.state)
    marked: list[bool] = []

    def watched(reader: Any) -> Any:
        async def read(*args: Any, **kwargs: Any) -> Any:
            marked.append(is_a_fast_lane_read())
            return await reader(*args, **kwargs)

        return read

    await respond(
        made.question(),
        rules=(*app.state.fast_path_rules, *lane.rules),
        readers={pair: watched(reader) for pair, reader in lane.readers.items()},
        entitlement=await h.reach(made.reader),
        now=h.now,
    )
    if not marked or not all(marked):
        raise CheckFailedError("the fast lane's reads were not marked as its own")

    # The source the install reads every row through, asked who it reads as, marked and not.
    who = RowQuery(
        entity="acceptance",
        source="acceptance",
        columns=("who",),
        statement=select(func.current_user().label("who")),
        certainly_empty=False,
    )
    source = SessionRowSource(h.sessions)
    with read_as_the_fast_lane():
        as_the_lane = [str(one["who"]) for one in await source.rows(who)]
    otherwise = [str(one["who"]) for one in await source.rows(who)]
    if as_the_lane != [FAST_LANE_ROLE]:
        raise CheckFailedError("the fast lane's rows were read as the application")
    if otherwise == [FAST_LANE_ROLE]:
        raise CheckFailedError("a read the fast lane did not make was read as its role")

    for statement in READ_BY_THE_FAST_LANE:
        if await as_the_fast_lane(h, statement) is not None:
            raise CheckFailedError("the fast lane's role could not read what it answers from")
    for statement in REFUSED_TO_THE_FAST_LANE:
        if await as_the_fast_lane(h, statement) != INSUFFICIENT_PRIVILEGE:
            raise CheckFailedError(
                "the database let the fast lane's role past what it answers from"
            )
