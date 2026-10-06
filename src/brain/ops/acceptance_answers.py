"""Install acceptance checks for what an answer on Ask stands on, and for the ways it declines.

The citations, their freshness and badges, the passage a citation opens at, the four kinds of
nothing and the scope statement were built and page-tested before these checks, and none of it had
been seen on an install: the Ask page's tests answer from a stand-in API, and every model check
before these read the answer's words and not what stood behind them. So each check here asks a
question through `/answer`'s own function, `brain.api_routes.answered_for`, as a reserved person,
and reads the `Answered` the route would have streamed: its citation evidence, its abstention and
its text. Everything follows `brain.ops.acceptance`'s rules: reserved people in reserved
departments, one rolled-back transaction per check, a reason that is a sentence the source wrote.

**A model is a stand-in answering in the process, so no provider is asked and no key is read.**
The model lane's citations are derived from the passages the model was shown, and what the model
says is prose; proving that needs a model that says something, and a real provider would make each
deploy's check cost a call and depend on a key. So the ladder is pinned, inside the transaction, to
`brain.ops.acceptance_routing`'s stand-in, whose transport is the product's own over a responder
in the process, with two more replies added here: one naming a document nobody uploaded, for the
citation that must not follow the model's words, and one saying nothing, for the answer the lane
must decline. See `THE_MODEL_IS_A_STAND_IN_BECAUSE_WHAT_IS_CHECKED_IS_WHAT_IT_WAS_SHOWN`.

**A record's citation needs no model at all.** An uploaded table's rule answers on the fast lane,
so the row citation, its field and its read time are the lane's own work over the install's rows.

**The not-entitled state is read off the abstention the route returns, never off a log.** A
refusal is written to the application log as a warning for an administrator, and reading that log
from inside a check would mean replacing the process's log configuration while the worker runs
other work. The abstention the route hands back carries the reason and what the administrator's
trace is given, `Abstention.for_administrator`, which is the value the lane logs, so the check reads
that and compares the frames the asker was sent with those of a record that does not exist. See
`A_REFUSAL_IS_READ_OFF_THE_ABSTENTION_AND_NOT_OFF_THE_LOG`.

**The rule for a source nobody connected is written to the install's own rule table** inside the
transaction, with a word nothing else holds in its template, so the lane reads it the way it reads
every rule and no real question could match it.

Task ids: M38.5.1
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

import httpx
from sqlalchemy import insert

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _found, _in
from brain.ops.acceptance_models import (
    STAND_IN,
    STAND_IN_ADDRESS,
    Paired,
    a_reader_with_a_document,
    askable,
    asked,
    asking_app,
    models_for,
    pinned,
)
from brain.ops.acceptance_routing import (
    ANSWERS,
    STAND_IN_REPLY,
    StandIns,
    constrained,
    stand_in_drivers,
    step,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.gate.answer import Answered
    from brain.gate.provenance import Evidence
    from brain.ops.model_service import ModelService

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 120

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why these checks ask a stand-in and not a provider.
THE_MODEL_IS_A_STAND_IN_BECAUSE_WHAT_IS_CHECKED_IS_WHAT_IT_WAS_SHOWN: Final = (
    "What these checks prove is what stood behind an answer: the passages the model was shown, "
    "their freshness, badge and link, and what the asker is told when nothing does. A stand-in "
    "whose transport is the product's own, answering in the process, proves all of it with no "
    "call leaving the server and no key read, and it can name a document nobody uploaded or say "
    "nothing at all, which a real provider cannot be made to do on the day a deploy is checked."
)

#: Why the not-entitled state is read off the abstention.
A_REFUSAL_IS_READ_OFF_THE_ABSTENTION_AND_NOT_OFF_THE_LOG: Final = (
    "The lane logs a refusal as a warning for an administrator, and capturing that log inside a "
    "check would replace the worker's log configuration while it runs other work. The route "
    "returns the abstention the warning is written from, so the check reads its reason and what "
    "the administrator's trace is given, and compares the frames the asker was sent with those "
    "of a record that does not exist."
)

# ------------------------------------------------------------------------ the figures
#: The stand-in model that names a document nobody uploaded, as a model citing from memory would.
CITES_ELSEWHERE: Final = "cites-elsewhere"

#: The stand-in model that answers with no words at all.
SILENT: Final = "silent"

#: The stand-in model that reads one passage and refuses a longer prompt as too long for it, in
#: the error body OpenAI documents for a context-length refusal, which Moonshot shares.
READS_ONE: Final = "reads-one-passage"

#: That refusal. `brain.models.wire.CONTEXT_EXCEEDED_CODES` is what reads its code.
TOO_LONG: Final = (
    400,
    {
        "error": {
            "message": "This model's maximum context length was exceeded by the messages.",
            "type": "invalid_request_error",
            "param": "messages",
            "code": "context_length_exceeded",
        }
    },
)

#: The document reference the citing stand-in names. Shaped like an item id, and held by nothing.
ELSEWHERE_REFERENCE: Final = "acceptance-document-nobody-uploaded"

#: How far ahead the verification these checks record sets the review date.
REVIEW_AHEAD: Final = timedelta(days=180)


# ------------------------------------------------------------------------ the stand-in
def _completion(model: str, content: str) -> httpx.Response:
    """A chat completion in the shape `brain.models.wire.completion_from` reads, ending normally."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-acceptance",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 40, "completion_tokens": 8 if content else 0},
        },
    )


@dataclass
class Replies(StandIns):
    """`StandIns`, with the two replies these checks need beside the ones it answers."""

    said: list[str] = field(default_factory=list)
    #: Every request body the stand-in was sent, for a check reading what a model was shown.
    bodies: list[str] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(request.content.decode("utf-8", "replace"))
        model = str(json.loads(request.content).get("model", ""))
        if model == SILENT:
            self.asked[(request.url.host, model)] += 1
            return _completion(model, "")
        if model == READS_ONE:
            self.asked[(request.url.host, model)] += 1
            if request.content.decode("utf-8", "replace").count("Passage ") > 1:
                return httpx.Response(TOO_LONG[0], json=TOO_LONG[1])
            self.said.append(STAND_IN_REPLY)
            return _completion(model, STAND_IN_REPLY)
        if model == CITES_ELSEWHERE:
            self.asked[(request.url.host, model)] += 1
            reply = f"{STAND_IN_REPLY} It is set out in document {ELSEWHERE_REFERENCE}, passage 1."
            self.said.append(reply)
            return _completion(model, reply)
        return super().__call__(request)


@dataclass(frozen=True)
class Asking:
    """What a check starts from: a reader in acceptance_a, their document, the stand-in, the app."""

    reader: str
    library: str
    paired: Paired
    responder: Replies
    models: ModelService
    app: FastAPI

    def ask_sent(self) -> int:
        """How many requests reached the stand-in, whatever it was asked for."""
        return self.responder.sent_to(STAND_IN_ADDRESS)


async def asking_with_a_stand_in(h: Harness) -> Asking:
    """A member of acceptance_a with a document, no residency rule, and the stand-in held.

    `brain.ops.acceptance_routing.standing_by` with `Replies` in the place of `StandIns`. Not run
    on an install keeping text on its own hardware, for that function's reason.
    """
    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    responder = Replies()
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    return Asking(
        reader=reader,
        library=h.principal(A, "library"),
        paired=paired,
        responder=responder,
        models=models,
        app=await asking_app(h, models),
    )


async def _document_of(h: Harness, reader: str, word: str) -> tuple[str, frozenset[str]]:
    """The one document a text search for `word` finds for this reader, and its chunks."""
    found, _ = await _found(h, reader, word)
    documents = {one.document_id for one in found.records}
    if len(documents) != 1:
        raise CheckFailedError("the document a check uploaded was not found by its own word")
    return documents.pop(), frozenset(str(one.id) for one in found.records)


def _documents(answered: Answered) -> tuple[Evidence, ...]:
    if answered.composed is None or answered.provenance is None:
        raise CheckFailedError("a question the reader's own document answers was not answered")
    return answered.provenance.documents


# ------------------------------------------------ 1. a document's citation (M8.1.2, M8.1.4, M7.4.7)
@check(
    leaves=("M8.1.2", "M8.1.4", "M7.4.7"),
    sentence=(
        "A member of acceptance_a asks Ask a question their department's document answers and a "
        "model answers naming a document nobody uploaded: the answer cites the passage it was "
        "shown and nothing the model named, live, with a link that opens the document at that "
        "passage for the member and for nobody in acceptance_b; its badge says unverified, and "
        "verified once the steward verifies it."
    ),
)
async def a_document_answer_cites_the_passage_it_was_shown_with_its_badge(h: Harness) -> None:
    from brain.core.errors import Absent
    from brain.gate.provenance import DOCUMENT_KIND, Freshness
    from brain.knowledge.item import VerificationState
    from brain.ops.acceptance_checks_lifecycle import _as, _verify

    s = await asking_with_a_stand_in(h)
    document_id, chunks = await _document_of(h, s.reader, s.paired.key)
    await pinned(h, (step(CITES_ELSEWHERE),))

    first = await asked(h, s.app, s.reader, s.paired.question, 1, at=datetime.now(UTC))
    cited = _documents(first)
    if not s.responder.said or not cited:
        raise CheckFailedError("the answer drawn from a document cited nothing it was shown")
    views = [one.view() for one in cited]
    if {view.get("document_id") for view in views} != {document_id} or any(
        view.get("kind") != DOCUMENT_KIND for view in views
    ):
        raise CheckFailedError("an answer cited something other than the document it was shown")
    if ELSEWHERE_REFERENCE in json.dumps(views):
        # The reply's words are prose; a citation built from them is the failure M8.1.4 names.
        raise CheckFailedError("a document the model named and nobody uploaded was cited")
    anchors = {str(view.get("anchor", "")).removeprefix("chunk=").split("&")[0] for view in views}
    if not anchors or not anchors <= chunks:
        raise CheckFailedError("a citation's link did not point at a passage of the document")
    if any(one.freshness.state is not Freshness.LIVE or not one.view()["read_at"] for one in cited):
        raise CheckFailedError("a passage stored a moment ago was not cited as live with its time")
    if any(one.badge is None or one.vouched_for for one in cited):
        raise CheckFailedError("a document nobody has verified was not badged as unverified")

    # The link: the route the citation opens, at the reader's reach and at another's.
    opened = await _cited(h, s.app, s.reader, document_id)
    if opened is None or not anchors <= {one.chunk_id for one in opened.passages}:
        raise CheckFailedError("the cited document did not open at the passage it was cited for")
    outsider = h.principal(B, "member")
    await h.person(outsider, department=B, grants=_in(B, *KNOWLEDGE_READS))
    for who, which in ((outsider, document_id), (s.reader, h.word().lower())):
        try:
            await _cited(h, s.app, who, which)
        except Absent:
            continue
        raise CheckFailedError(
            "a document outside the reader's reach opened, or was refused unlike a missing one"
        )

    # The badge once the steward vouches for it, read at the asker's reach.
    steward = await _as(h, s.library)
    if await _verify(h, steward, document_id, review_by=h.now + REVIEW_AHEAD) is None:
        raise CheckFailedError("the steward of an uploaded document could not verify it")
    second = _documents(await asked(h, s.app, s.reader, s.paired.question, 2, at=datetime.now(UTC)))
    if not second or any(
        not one.vouched_for or one.view()["badge_state"] != VerificationState.VERIFIED.value
        for one in second
    ):
        raise CheckFailedError("a verified document's citation did not carry the verified badge")


async def _cited(h: Harness, app: FastAPI, principal_id: str, document_id: str) -> Any:
    """The cited document route, as `principal_id` in the console, for `document_id`."""
    from starlette.requests import Request

    from brain.cited_document_routes import cited_document
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel

    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    request = Request({"type": "http", "app": app, "headers": [], "method": "GET"})
    # A cast at the route's boundary: it reads the reach and the instant of the caller the
    # console admits, and a `Caller` can only be minted from a verified token.
    asking = cast(Any, SimpleNamespace(reach=reach, now=h.now))
    return await cited_document(request, document_id, asking)


# ------------------------------------------------------ 2. a record's citation (M8.1.1, M9.2.1)
@check(
    leaves=("M8.1.1", "M9.2.1"),
    sentence=(
        "A member of acceptance_a asks Ask a question an uploaded table answers, with no model: "
        "the answer is the column they may read from the one row, assembled from the rows read and "
        "redacted at their reach, and its citation names the table, the record, the field and the "
        "time it was read, sent before the prose."
    ),
)
async def a_record_answer_cites_the_record_field_and_read_time(h: Harness) -> None:
    from brain.gate.provenance import RECORD_KIND, Freshness
    from brain.gate.streaming import Event
    from brain.ops.acceptance_checks_chat import uploaded

    s = await asking_with_a_stand_in(h)
    table = await uploaded(h)
    for capability, scope in table.reads(A, held=False):
        await h.grant(s.reader, capability, scope)
    before = s.ask_sent()
    answered = await asked(
        h, s.app, s.reader, table.asking(table.open_column), 1, at=datetime.now(UTC)
    )
    if answered.composed is None or answered.provenance is None or s.ask_sent() != before:
        raise CheckFailedError(
            "a question an uploaded table answers was not answered without a model"
        )
    if table.seen not in (answered.text or "") or table.held in json.dumps(
        [dict(one) for one in answered.composed.payload.records], default=str
    ):
        raise CheckFailedError(
            "the answer was not the column the reader may read, from rows redacted at their reach"
        )
    # One citation per field that survived redaction, `brain.gate.compose`'s rule: the answered
    # column among them, the withheld one never.
    rows = answered.provenance.rows
    views = [one.view() for one in rows]
    fields = {view.get("field") for view in views}
    if (
        table.open_column not in fields
        or table.held_column in fields
        or any(
            view.get("kind") != RECORD_KIND
            or view.get("entity") != table.entity
            or not view.get("record_id")
            or not view.get("read_at")
            for view in views
        )
    ):
        raise CheckFailedError("a record's citation did not name its table, record, field and time")
    if any(one.freshness.state is not Freshness.LIVE for one in rows):
        raise CheckFailedError("a row read a moment ago was not cited as live")
    kinds = [_event(frame) for frame in answered.frames]
    cited_at, said_at = kinds.index(Event.CITATION.value), kinds.index(Event.TEXT.value)
    if not cited_at < said_at:
        raise CheckFailedError("an answer's citation was not sent before its prose")


def _event(frame: str) -> str:
    """A frame's event name, read by the event-stream format's own rule."""
    return next(
        (
            line.partition(":")[2].strip()
            for line in frame.splitlines()
            if line.startswith("event:")
        ),
        "",
    )


# ------------------------------------------------------------- 3. four kinds of nothing (M8.2.1)
@check(
    leaves=("M8.2.1",),
    sentence=(
        "Members of acceptance_a are told apart what they may be told: a question nothing answers "
        "is nothing found and asks no model, a document a model says nothing about is found but "
        "not answering, a rule for a source nobody connected is nothing connected; a column they "
        "hold no grant for is refused to the administrator's trace and reads to them word for word "
        "as a record that does not exist."
    ),
)
async def four_kinds_of_nothing_are_kept_apart(h: Harness) -> None:
    from brain.gate.abstain import (
        NOT_ANSWERING_TEXT,
        NOT_FOUND_TEXT,
        NOTHING_CONNECTED_TEXT,
        AbstentionReason,
    )
    from brain.ops.acceptance_checks_chat import uploaded
    from brain.tables.fast_lane import FastPathRuleRow

    s = await asking_with_a_stand_in(h)
    await pinned(h, (step(SILENT),))

    # Nothing retrieved, decided before any model is asked.
    before = s.ask_sent()
    nothing = await asked(h, s.app, s.reader, Paired(h.word(), "").question, 1)
    _declined(nothing, AbstentionReason.NOTHING_RETRIEVED, NOT_FOUND_TEXT)
    if s.ask_sent() != before:
        raise CheckFailedError(
            "a model was asked about a question nothing the reader may see answers"
        )

    # Retrieved, and the model said nothing.
    silent = await asked(h, s.app, s.reader, s.paired.question, 2)
    _declined(silent, AbstentionReason.RETRIEVED_BUT_NOT_ANSWERING, NOT_ANSWERING_TEXT)
    if s.responder.sent_to(STAND_IN_ADDRESS, SILENT) != 1:
        raise CheckFailedError("the passage found was not put to the model that said nothing")

    # Nothing connected: a rule in the install's own table for a source nothing reads.
    source, thing = f"acceptance_{h.run}", h.word()
    await h.execute(
        *h.attributed(),
        insert(FastPathRuleRow).values(
            rule_id=f"acceptance_{h.run}",
            template=f"what does {thing} say about {{subject}}",
            slot="subject",
            source=source,
            entity=f"acceptance_{h.run}",
            match_field="name",
            answer_field="status",
            created_by=h.actor,
        ),
    )
    table = await uploaded(h)
    for capability, scope in table.reads(A, held=False):
        await h.grant(s.reader, capability, scope)
    app = await asking_app(h, s.models)
    unconnected = await asked(h, app, s.reader, f"what does {thing} say about {h.word()}", 3)
    declined = _declined(unconnected, AbstentionReason.NOTHING_CONNECTED, NOTHING_CONNECTED_TEXT)
    if declined.missing_source != source:
        raise CheckFailedError("nothing connected did not record the source the rule names")

    # Not entitled: a held column of a row that exists, against the same column of a row that does
    # not. See A_REFUSAL_IS_READ_OFF_THE_ABSTENTION_AND_NOT_OFF_THE_LOG.
    refused = await asked(h, app, s.reader, table.asking(table.held_column), 4)
    absent = await asked(h, app, s.reader, table.asking(table.held_column, h.word()), 5)
    told = _declined(refused, AbstentionReason.NOT_ENTITLED, NOT_FOUND_TEXT)
    _declined(absent, AbstentionReason.NOTHING_RETRIEVED, NOT_FOUND_TEXT)
    if told.for_administrator() != {
        "reason": "not_entitled",
        "entity": table.entity,
        "field": table.held_column,
    }:
        raise CheckFailedError("a refused column did not reach the administrator's trace by name")
    if refused.frames != absent.frames or table.held in "".join(refused.frames):
        raise CheckFailedError("a refused column read differently to the asker from a missing row")


def _declined(answered: Answered, reason: Any, text: str) -> Any:
    """The abstention, when it is `reason` and its text is what the asker hears; else a failure."""
    declined = answered.abstention
    if answered.composed is not None or declined is None or declined.reason is not reason:
        raise CheckFailedError(_KINDS_OF_NOTHING_WERE_MIXED)
    if not _spoken(answered).startswith(text):
        raise CheckFailedError(_KINDS_OF_NOTHING_WERE_MIXED)
    return declined


#: What the check says when one kind of nothing was answered as another.
_KINDS_OF_NOTHING_WERE_MIXED: Final = (
    "one kind of nothing was answered as another, or told to the asker in another's words"
)


def _spoken(answered: Answered) -> str:
    """What the text frames said, joined."""
    from brain.gate.streaming import Event

    said: list[str] = []
    for frame in answered.frames:
        if _event(frame) == Event.TEXT.value:
            said.extend(
                line.partition(":")[2].removeprefix(" ")
                for line in frame.splitlines()
                if line.startswith("data:")
            )
    return "\n".join(said)


# ------------------------------------------------------------ 4. the scope statement (M8.2.2)
@check(
    leaves=("M8.2.2",),
    sentence=(
        "A member of acceptance_a who reads the department's documents and an uploaded table is "
        "told what their answers and refusals cover, the knowledge library and the uploaded "
        "tables, in the same sentence on both; a member who reads the table alone is not told of "
        "the library, and one who reads the documents alone is not told of the tables."
    ),
)
async def an_answer_and_a_refusal_say_what_the_asker_s_reach_covers(h: Harness) -> None:
    from brain.api_routes import KNOWLEDGE_COVERED, TABLES_COVERED
    from brain.gate.abstain import scope_of_reach
    from brain.ops.acceptance_checks_chat import uploaded

    s = await asking_with_a_stand_in(h)
    await pinned(h, (step(ANSWERS),))
    table = await uploaded(h)
    both = s.reader
    tables_only = h.principal(A, "tables")
    await h.person(tables_only, department=A, grants=table.reads(A, held=False))
    for capability, scope in table.reads(A, held=False):
        await h.grant(both, capability, scope)
    app = await asking_app(h, s.models)

    everything = _statement(scope_of_reach((KNOWLEDGE_COVERED, TABLES_COVERED)))
    answered = await asked(h, app, both, s.paired.question, 1)
    refused = await asked(h, app, both, Paired(h.word(), "").question, 2)
    if answered.composed is None or not _spoken(answered).endswith(everything):
        raise CheckFailedError("an answer did not say it covered the library and the tables")
    if refused.abstention is None or not _spoken(refused).endswith(everything):
        raise CheckFailedError("a refusal did not say what it covered in the answer's words")

    only_tables = await asked(h, app, tables_only, Paired(h.word(), "").question, 3)
    if not _spoken(only_tables).endswith(_statement(scope_of_reach((TABLES_COVERED,)))):
        raise CheckFailedError("a reader of the tables alone was told of more than the tables")
    documents_only = h.principal(A, "documents")
    await h.person(documents_only, department=A, grants=_in(A, *KNOWLEDGE_READS))
    only_documents = await asked(h, app, documents_only, Paired(h.word(), "").question, 4)
    if not _spoken(only_documents).endswith(_statement(scope_of_reach((KNOWLEDGE_COVERED,)))):
        raise CheckFailedError("a reader of the documents alone was told of more than the library")


def _statement(scope: Any) -> str:
    """The statement as the lane renders it, from the same type."""
    said = str(scope.render())
    if not said:
        raise CheckFailedError("a scope naming what a reader reaches rendered no statement")
    return said


# ----------------------------------------------------------- 5. a kind narrows it (M7.6.1)
@check(
    leaves=("M7.6.1",),
    sentence=(
        "An FAQ and an SOP added in acceptance_a pair one word with two values: the library lists "
        "each under its kind and narrows to one, a member's question narrowed to FAQs shows the "
        "model the FAQ alone and one asked of every kind shows both, and a pricing note holding a "
        "table is refused."
    ),
)
async def a_question_narrowed_to_a_kind_is_answered_from_that_kind_alone(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.kinds import KindError, KnowledgeKind
    from brain.ops.acceptance_checks import _upload
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.acceptance_models import ASKED, PAIRED, shown

    s = await asking_with_a_stand_in(h)
    await pinned(h, (step(ANSWERS),))
    key, values = h.word(), {KnowledgeKind.FAQ: h.word(), KnowledgeKind.SOP: h.word()}
    items: dict[KnowledgeKind, str] = {}
    for kind, value in values.items():
        read = await _upload(
            h,
            s.library,
            filename=f"Acceptance {kind.value}.md",
            declared=MediaType.MARKDOWN.value,
            body=a_markdown_document("Acceptance kind", PAIRED.format(key=key, value=value)),
            kind=kind,
        )
        if isinstance(read, ParseFailure):
            raise CheckFailedError("a document added with a kind could not be read")
        items[kind] = str(read.item.item_id)

    listed = await _library(h, s.app, s.reader, (f"kind:{KnowledgeKind.FAQ.value}",))
    ours = {one.item_id: one.kind for one in listed if one.item_id in items.values()}
    if ours != {items[KnowledgeKind.FAQ]: KnowledgeKind.FAQ.value}:
        raise CheckFailedError("the library did not list the FAQ under its kind, and it alone")

    question = ASKED.format(key=key)
    narrowed = await asked(h, s.app, s.reader, question, 1, kinds=(KnowledgeKind.FAQ,))
    everything = await asked(h, s.app, s.reader, question, 2)
    seen_narrowed, seen_everything = shown(narrowed), shown(everything)
    if values[KnowledgeKind.FAQ] not in seen_narrowed or values[KnowledgeKind.SOP] in seen_narrowed:
        raise CheckFailedError("a question narrowed to FAQs was shown a document of another kind")
    if not all(value in seen_everything for value in values.values()):
        raise CheckFailedError("a question asked of every kind was not shown both documents")

    table = "\n".join(["| Service | Price |", "| --- | --- |", f"| {h.word()} | 900 |"])
    try:
        await _upload(
            h,
            s.library,
            filename="Acceptance pricing note.md",
            declared=MediaType.MARKDOWN.value,
            body=a_markdown_document("Acceptance pricing", table),
            kind=KnowledgeKind.PRICING_NOTE,
        )
    except KindError:
        return
    raise CheckFailedError("a pricing note holding a table of prices was added")


async def _library(
    h: Harness, app: FastAPI, principal_id: str, filters: tuple[str, ...]
) -> tuple[Any, ...]:
    """The Knowledge list as the route answers `principal_id`, narrowed by `filters`."""
    from starlette.requests import Request

    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge_lifecycle_routes import knowledge_list
    from brain.listing import ListAsked

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    request = Request({"type": "http", "app": app, "headers": [], "method": "GET"})
    # A cast at the route's boundary, for `_cited`'s reason: a `Caller` is minted from a token.
    asking = cast(
        Any, SimpleNamespace(caller=SimpleNamespace(principal=person), reach=reach, now=h.now)
    )
    page = await knowledge_list(request, asking, ListAsked(filters=filters))
    return tuple(page.items)


# ---------------------------------------------- 6. more than the largest model reads (M15.4.1)
@check(
    leaves=("M15.4.1",),
    sentence=(
        "Three documents in acceptance_a answer a member's question and the only model on the "
        "ladder refuses any prompt holding more than one passage as too long: the member is "
        "answered from one passage, citing that one alone, and the answer says it drew on one of "
        "the three passages found."
    ),
)
async def a_prompt_too_long_for_every_model_is_answered_from_fewer(h: Harness) -> None:
    from brain.core.errors import Degraded
    from brain.gate.model_lane import TRIMMED_TEXT
    from brain.ops.acceptance_models import ASKED, paired_in, shown

    s = await asking_with_a_stand_in(h)
    key = h.word()
    papers = [await paired_in(h, A, s.library, key=key) for _ in range(3)]
    await pinned(h, (step(READS_ONE),))
    try:
        answered = await asked(h, s.app, s.reader, ASKED.format(key=key), 1, at=datetime.now(UTC))
    except Degraded:
        raise CheckFailedError(
            "a prompt too long for every model was answered with the provider's failure rather "
            "than from fewer passages"
        ) from None
    cited = _documents(answered)
    drew_on = [one.value for one in papers if one.value in shown(answered)]
    if len(drew_on) != 1 or len({one.view().get("document_id") for one in cited}) != 1:
        raise CheckFailedError("the answer was not drawn from, and cited for, one passage alone")
    if s.responder.sent_to(STAND_IN_ADDRESS, READS_ONE) != 2:
        raise CheckFailedError("the model was not asked again with fewer passages, once")
    if TRIMMED_TEXT.format(shown=1, found=3) not in (answered.text or ""):
        raise CheckFailedError("the answer did not say it drew on one of the three passages found")


# ---------------------------------------------- 7. the retrieval log (M15.3.4)
#: The columns a retrieval is kept under, which name no document, question or person.
RETRIEVAL_COLUMNS: Final = frozenset(
    {"event_id", "at", "retrievers", "returned", "corroborated", "used", "latency_ms"}
)


def _asking_as(h: Harness, reach: Any) -> Any:
    """What the retrieval routes read of a signed-in caller: the reach and the instant."""
    # A cast at the routes' boundary: they read these two, and a `Caller` is minted only from a
    # verified token.
    return cast(Any, SimpleNamespace(reach=reach, now=h.now))


@check(
    leaves=("M15.3.4",),
    sentence=(
        "A member of acceptance_a is answered on Ask from their document: the retrieval is kept "
        "with the retrievers that ran, the passages shown and no document, question or person; "
        "following the cited passage keeps its place once, a place outside the list and an id "
        "naming nothing are one 404, a search outside Ask keeps nothing, and the signal is read "
        "by a knowledge administrator alone."
    ),
)
async def a_followed_citation_is_kept_as_a_place_and_nothing_else(h: Harness) -> None:
    from uuid import uuid4

    from sqlalchemy import func, select, text

    from brain.api_routes import logged_retrieval
    from brain.core.errors import Absent
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.gate.model_lane import PASSAGES_SHOWN
    from brain.knowledge.quality import signal
    from brain.knowledge.retrieval_log import collected
    from brain.ops.retrieval_store import StoredRetrievals
    from brain.retrieval_routes import NOT_ENOUGH_YET, UseAsked, retrieval_signal, used
    from brain.tables.retrieval import RetrievalEventRow

    s = await asking_with_a_stand_in(h)
    await pinned(h, (step(ANSWERS),))
    with collected() as searched:
        answered = await asked(h, s.app, s.reader, s.paired.question, 1, at=datetime.now(UTC))
    cited = _documents(answered)
    event_id = await logged_retrieval(s.app.state, searched, answered)
    if event_id is None:
        raise CheckFailedError("an answer on Ask drawn from a document kept no retrieval")

    async def kept() -> dict[str, Any]:
        async with h.sessions() as session, session.begin():
            found = await session.execute(
                text("SELECT * FROM ops.retrieval_event WHERE event_id = CAST(:id AS uuid)"),
                {"id": event_id},
            )
            row = found.mappings().first()
        return {} if row is None else dict(row)

    row = await kept()
    shown = len(answered.composed.payload.records) if answered.composed is not None else 0
    if set(row) != RETRIEVAL_COLUMNS:
        raise CheckFailedError("a retrieval was kept with a column beyond what the signal reads")
    if (row["retrievers"], row["returned"], list(row["used"])) != ("lexical", shown, []):
        raise CheckFailedError(
            "a retrieval was not kept as the retrievers that ran and the list shown"
        )
    positions = {one.view().get("position") for one in cited}
    if "1" not in positions:
        raise CheckFailedError("a cited passage did not carry its place in the reader's list")

    # Following the citation, as the cited page does, twice; then two uses that name nothing.
    asking = _asking_as(h, admit(await h.reach(s.reader), Channel.CONSOLE, Assurance.AUTHENTICATED))
    for _ in range(2):
        await used(_request(s.app), asking, event_id, UseAsked(position=1))
    if list((await kept())["used"]) != [1]:
        raise CheckFailedError("a followed citation's place was not kept, or was kept twice")
    for wrong_id, position in ((event_id, shown + 1), (str(uuid4()), 1)):
        if position > PASSAGES_SHOWN:
            # Past what any list shows, which the route's own body refuses before the store.
            continue
        try:
            await used(_request(s.app), asking, wrong_id, UseAsked(position=position))
        except Absent:
            continue
        raise CheckFailedError("a place outside the list, or an id naming nothing, was kept")

    # A search made outside Ask keeps nothing.
    async with h.sessions() as session, session.begin():
        before = await session.scalar(select(func.count()).select_from(RetrievalEventRow))
    await _found(h, s.reader, s.paired.key)
    async with h.sessions() as session, session.begin():
        after = await session.scalar(select(func.count()).select_from(RetrievalEventRow))
    if before != after:
        raise CheckFailedError("a search made outside Ask kept a retrieval nobody could follow")

    # The signal, for a knowledge administrator and for nobody else.
    try:
        await retrieval_signal(_request(s.app), asking)
    except Absent:
        pass
    else:
        raise CheckFailedError("a member who runs no part of the library read the retrieval signal")
    # An administrator's verbs are admitted at a strong sign-in, as the console signs one in.
    administering = _asking_as(
        h, admit(await h.reach(s.library), Channel.CONSOLE, Assurance.STRONG)
    )
    view = await retrieval_signal(_request(s.app), administering)
    recent = await StoredRetrievals(h.sessions).recent()
    expected = signal(recent)
    if expected is None:
        if view.enough or view.told != NOT_ENOUGH_YET:
            raise CheckFailedError("a signal was answered with fewer retrievals than it needs")
    elif not view.enough or view.events != expected.events:
        raise CheckFailedError("the signal was not read over the most recent retrievals")


def _request(app: FastAPI) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": "POST"})
