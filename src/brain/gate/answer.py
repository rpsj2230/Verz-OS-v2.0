"""The answer lane: one question in, a stream of frames out, and a model only where no rule answers.

Until this module the pieces of an answer existed and nothing joined them.
`brain.gate.fast_lane.respond` matched a data-driven rule and fetched a row and was called
by nothing. `brain.gate.abstain` classified an outcome and was called by nothing.
`brain.gate.streaming` encoded frames and was called by nothing. `brain.gate.compose.compose`
derived citations from a redacted payload and was called by nothing. Four correct, tested,
documented modules with no path between them and a request, which is the recurring defect in
this repository and by the time this was written it had thirteen recorded instances.

**A question no rule matched at all goes to a model, when the lane is handed one, and nothing
else does.** A question whose wording a rule matches stays the fast path's, answered or abstained
on exactly as before, including a rule for a source this install does not connect, which is
"nothing connected" before anything is read. A question no rule's shape matches is handed to
`brain.gate.model_lane.draft` when the caller passed a `ModelLane`, which finds passages at the
caller's reach, redacts them with the same reach, asks a model only when something survived, and
derives the citations from what the model was shown. The ordering, the redaction and the frames
around it are the code that was already here. With no `ModelLane` the lane abstains exactly as it
did, which is what the golden corpus and every caller without a model sees. See
`brain.gate.model_lane` for what a model is shown and why nothing it says is read for references.

**Whether a rule matched is decided before anything is read, from the question and the install's
rules, which is why it may choose the lane.** A rule that matched and then found two records under
one name, or a record whose answer field is withheld, is not handed on to a model: the read has
happened by then, and a different set of steps or a different answer after it would tell the
asker what the read found. See `THE_MODEL_STEP_TAKES_ONLY_A_QUESTION_NO_RULE_MATCHED`.

The branch that finds no row readers still says nothing is connected, with or without a model.
The document plane is read through the same row source the readers are, and
`brain.tools.startup` registers the one exactly when it registers the other, so a process with
no readers has no passage search to hand the lane either.

**Every frame goes through `brain.gate.streaming.AnswerStream`, so the order is enforced
rather than intended.** Citations before prose, no step once the prose has started, nothing
after the stream closes. A lane that assembled its own frames would be a second place that
decides what a person may watch arriving, and the first place is the one with the argument in
front of it.

**Redaction happens exactly where the records route does it**, through
`brain.core.redaction.redact` (which `serialise_for_channel` wraps) with the caller's own reach.
Not a second enforcement point: the same one, called from a second place, which is the
difference between defence in depth and two rules that can disagree. The row reader was already
handed the same entitlement, so the scope predicate was inside the query as well as around the
result.

**The abstention is classified from the post-redaction payload**, which is what makes DENIED
and ABSENT one event here. A record this caller may not see is not in the payload, so it
reaches `nothing_retrieved` by the same route as a record that never existed, and
`abstention_for_search` has nowhere to put a pre-redaction count that would let the two be
told apart.

The one place this module does distinguish them is the audit reason, and only there.
`ChannelPayload.locked` names a field present on a record and withheld from this caller,
so a fast-lane answer whose answer field is locked is a refusal this layer saw, and
`not_entitled` exists so the ledger can record it. Its public half is the same constant
`nothing_retrieved` renders, referenced twice rather than written twice, so the two are
byte identical to the asker and the ledger still says what happened.

**A question the fast path cannot answer abstains rather than erroring.** No served rule matched,
two matched, or two records answered to one name: `respond` returns None for all three and the
distinction is deliberately not visible to the asker, because "two rules matched your
question" is a fact about this installation's configuration and "two records matched that
name" is a fact about its data. A question no rule matched at all never reaches `respond` when
the lane has a model step.

**The scope statement is derived from the asker's reach and never from what ran.** That is
`brain.gate.abstain.SearchScope`'s rule and this module obeys it by passing the sources the
caller may be told about, which the caller computes from their own entitlements. A statement
assembled from the sources that actually answered would vary with whether a record existed,
and the variation is readable by asking twice.

**A request is recorded under the lane whose budget it spent, and the meter is what says so.**
A request that attempted a model call spent the answer lane's allowance and is recorded as
`Lane.ANSWER`, with the meter's usage on its ledger row; every other request, an answer from a
rule, a cache hit, an abstention decided before any model was asked and a fault before one,
spent the fast lane's and is recorded as `Lane.FAST`. Recording every question a model could
have read as `ANSWER` would compare a two-millisecond abstention against an eight-second
objective and report it met. The decision is read off the one `Meter` the request's calls were
counted on, so it cannot disagree with the tokens on the same row. See
`A_REQUEST_IS_RECORDED_UNDER_THE_LANE_WHOSE_BUDGET_IT_SPENT`.

Scope: this module opens no connection and reads no clock of its own. `now` is a parameter, the
readers are handed in, the rules are handed in, and the trace sink is handed in. The completion
instant comes from `clock`, which the caller hands in and the lane reads exactly once, in the
`finally` that finishes the request. It is `async` because a row read, a passage search and a
model call are, which are the things here that wait on anything.

**Every reader call is counted as it starts, by a wrapper the lane puts around the readers it was
handed (M21.3.4).** The count reaches `Finished.tool_calls` and from there the trace ledger's
`tool_count`, which is one half of a question's shape. The lane wraps rather than `respond`
counting, because `respond` returns None both before a read and after one, and a count it
reported would have to be threaded out through every one of those returns. A wrapper cannot
miss a return, and it counts a read that raised, which is a call the lane made. See
`brain.gate.finish.A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS`.

**The trace handed to the sink is the redactor's own (M4.4.4).** The lane calls `redact`, which
returns the payload and the trace together, and gives the payload to the frames and the pair to
`compose`. Until 2026-09-21 it called `serialise_for_channel` and built an empty trace beside it,
so the sink recorded that nothing was redacted on requests where something was.

**A department the question names and the reader cannot reach is stated, in the same words
whether it exists or not (M2.2.4).** The route passes the gaps `brain.core.department` planned from
the question and the reader's own scope; the lane appends them to the text of an answer and of a
refusal alike, so their presence cannot tell the two apart.

**The back half enters its steps on the request's recorder (M3.1.2).** A row read or a passage
search is INVOKE, the redactor is REDACT and the sentence or the model's prose is COMPOSE, each
entered before the work it names, so the order `GateStep` declares is checked on the whole path
and not only in front of the model. A cache hit enters none of them: nothing was invoked.

**The route the model call took is read off the same meter (M3.6.3).** The executor notes the
tier it classified on the request's `Meter` as it decides it, and `finish` hands `Meter.route` to
the recorders beside the usage, so the row's tier is the one walked and never one re-derived.
**A request no call was classified for carries the front half's tier**, which `FrontRecord` holds
as ROUTE decided it. Until 2026-09-29 it carried none: the owner's install had four request rows,
two with a routed lane, and not one with a tier, because no model call had been classified for
either question the front half routed. See `THE_ROW_HOLDS_THE_LAST_ROUTING_DECISION_MADE`.

**A record a connected source holds is answered from that source, read while the asker waits
(M11.9.2, M11.5.1).** The index row the fast path found names the record; when the lane was handed
`LiveRecords` and the source reads that kind of record live, the lane reads it again from the source
through `brain.gate.live_records.LiveRecords` inside the live read budget, and
redacts and answers from what came back. A source that did not answer in time is not waited for: the
asker is told `PartialRead.notice`, which names the source only when their own reach
already discloses it (M11.5.5), and the request is recorded as degraded. A live answer is never
kept in the answer cache, because a kept value served later is a copy rather than a read; and a
request that read live spent the answer lane's budget, so it is recorded there. See
`A_LIVE_READ_SPENDS_THE_ANSWER_LANES_BUDGET` and `A_LIVE_VALUE_IS_NOT_KEPT_FOR_THE_NEXT_ASKER`.

**Each source's rows are redacted by that source's own classification (M15.4.2).** `source_policies`
is keyed by source and entity, and a policy found there is the one used; `policies`, keyed by entity
alone, is the fallback for a caller that has no source to give. Two sources projecting the same kind
of record are then each redacted as their own, rather than one of them by whichever was classified
first, which withheld every field only the other one classified.

**Every citation goes out as its evidence (M8.1.1 to M8.1.3, M8.2.4, M11.4.9).** Until
2026-09-28 the lane wrote `Citation.render()` for each of the composer's citations and nothing
else, so no answer said how fresh its evidence was, which document a passage came from or who had
vouched for it, and `brain.gate.provenance.provenance_for` had no caller. Now the fast path builds
`Provenance` from the composer's citations and the model step from its passages, the stream writes
`Evidence.view` for each, the text carries `Provenance.notice` when the weakest evidence is not
current, and an answer nothing stands behind is refused by `abstain_if_uncited` before it is
written.

**The source a question read is noted by the same wrapper that counts the reads (M27.1.5).** A
reader is registered under its source and entity, so the wrapper knows which source each call is
for without reading what came back, and the ledger's `connector` names it: one source, or none
when a request read none or several (`ONE_SOURCE_OR_NONE`). An uploaded table is read under its
own source name, `tables`, which names no connector. The skills the model step offered reach
`Finished` the same way, from the step's own call rather than from anything the model said.

Task ids: M30.5.2, M21.3.4, M3.9.3, M4.4.4, M2.2.4, M3.1.2, M3.6.3, M11.9.2, M11.5.1, M11.5.5
Task ids: M15.4.2, M8.1.3, M8.2.1, M11.4.9
Task ids: M27.1.5, M27.15.9
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

import structlog

from brain.core.department import Gap
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.field_policy import FieldPolicy
from brain.core.lane import Lane
from brain.core.redaction import ChannelPayload, redact
from brain.gate.abstain import (
    Abstention,
    AbstentionReason,
    SearchScope,
    abstain_if_uncited,
    abstention_for_search,
    not_entitled,
    nothing_connected,
    nothing_retrieved,
    scope_of_reach,
)
from brain.gate.answer_cache import serve_cached
from brain.gate.cache_key import CachedAnswer
from brain.gate.compose import ComposedAnswer, TraceSink, compose
from brain.gate.context import GateStep, Recorder
from brain.gate.fast_lane import (
    AmbiguityReader,
    FastLaneAnswer,
    FastLaneUnresolved,
    FastPathRule,
    RowReader,
    match_rule,
    respond,
    unserved_match,
)
from brain.gate.finish import (
    Finished,
    FrontRecord,
    Origin,
    RequestRecorder,
    SkillUse,
    attributable,
    finish,
)
from brain.gate.live_records import LiveRecords, PartialRead
from brain.gate.model_lane import ModelLane, draft
from brain.gate.provenance import (
    SEED_HORIZONS,
    UNCITED_TEXT,
    Horizons,
    Provenance,
    provenance_for,
)
from brain.gate.streaming import AnswerStream, Progress, at_tool_input_start, cache_hit
from brain.knowledge.rows import RowRecord, RowRequest
from brain.models.metering import Meter, ModelRoute
from brain.resolution.guardrails import (
    REVIEWER_CAPABILITY,
    UNRESOLVED_TEXT,
    UnresolvedNotice,
)

log = structlog.get_logger(__name__)

#: Why a lane that cannot answer says nothing about why.
THE_ASKER_IS_NEVER_TOLD_WHICH_KIND_OF_NOTHING_HAPPENED = (
    "No rule matched, two rules matched, two records answered to one name, the record was "
    "withheld, and the record does not exist all produce the same sentence. The first two "
    "are facts about how this installation is configured and the last three are facts about "
    "its data, and a person who could tell them apart could map both by asking. The "
    "abstention vocabulary already carries the distinction for the audit log, which is the "
    "only reader entitled to it. One exception, and it is not a fact the asker lacked: records "
    "the asker reads, which the registry says are more than one client, are named as ambiguous; "
    "see fast_lane.NAMING_AMBIGUITY_ONLY_AMONG_RECORDS_THE_ASKER_READS. A withheld record never "
    "reaches that branch, so this sentence holds for it unchanged."
)

#: Why the answer text is assembled from the payload rather than written by a model.
A_SENTENCE_BUILT_BEFORE_REDACTION_IS_A_SENTENCE_THAT_SKIPPED_IT = (
    "The fast lane returns a TypedResult and not a sentence, deliberately, because a "
    "sentence built from what was fetched would be a payload that never went through the "
    "redaction walker. So the text here is derived from the payload after redaction, and "
    "the field the rule was written to answer with is a name the payload either kept or "
    "did not. If it did not, the field was withheld, and the answer is an abstention rather "
    "than a sentence with a gap in it."
)

#: Why a request's lane is read off its meter.
A_REQUEST_IS_RECORDED_UNDER_THE_LANE_WHOSE_BUDGET_IT_SPENT: Final = (
    "A lane is a budget, and the budget a request spent is decided by what ran, not by what "
    "the question would have been classified as. A request that attempted a model call spent "
    "the answer lane's allowance, answered or not; an answer from a rule, a cache hit, an "
    "abstention decided before any model was asked and a fault before one spent the fast "
    "lane's. Filing those under the answer lane because a model could have read them measures "
    "a lane that did not run against an objective sized for one that did. The meter the calls "
    "were counted on decides, so the lane and the tokens on one ledger row cannot disagree."
)

#: Why only a question no rule matched is handed to a model.
THE_MODEL_STEP_TAKES_ONLY_A_QUESTION_NO_RULE_MATCHED: Final = (
    "Whether a rule's wording matches a question is decided from the question and the install's "
    "rules before anything is read, so it is the same for every asker and every record. What a "
    "matched rule's read found is not: two records under one name, or one whose answer field is "
    "withheld, would reach a model with different steps and a different answer from a record "
    "that does not exist, and the asker would learn which. So a matched rule stays the fast "
    "lane's whatever it found, and only a question no rule matched at all is the model's."
)

#: Why a request that read a source live is recorded under the answer lane.
A_LIVE_READ_SPENDS_THE_ANSWER_LANES_BUDGET: Final = (
    "A live read is allowed its own timeout, which is longer than the fast lane's whole objective, "
    "and it waits on a system this one does not run. A request that made one spent the answer "
    "lane's allowance whether or not a model was asked, and recording it under the fast lane "
    "would measure a source's latency against a target no source call can meet."
)

#: Why an answer read live carries no text for the answer cache.
A_LIVE_VALUE_IS_NOT_KEPT_FOR_THE_NEXT_ASKER: Final = (
    "The owner's rule is that every value an answer uses from a connected source is read from the "
    "source when the question is asked. An answer kept in the cache and served to the next asker "
    "is a value read some minutes ago, served as though it were read now, which is a copy by "
    "another name. So a live answer is shown and not kept."
)

#: Why a request that read two sources names neither.
ONE_SOURCE_OR_NONE: Final = (
    "The ledger row has one connector column. A request whose readers read one source names it, "
    "which is what a connector's page counts as a question that read it; a request that read "
    "two would file one source's read under the other if it named either, so it names none, as "
    "a request answered by two models names no model."
)

#: Why the row's tier is the executor's when a call was classified and the front half's otherwise.
THE_ROW_HOLDS_THE_LAST_ROUTING_DECISION_MADE: Final = (
    "The front half classifies a tier at ROUTE before the lane runs, and the executor classifies "
    "again from the messages it is about to send when a model is called. The row holds the "
    "executor's when it classified a call, because that is where the call was sent, and the "
    "front half's when it classified none: a question answered by a rule, abstained on before a "
    "model or kept on the fast lane was still routed, and a row with no tier left that decision "
    "to be inferred from the lane afterwards, which is what M3.6.3 forbids."
)

#: The lane a request that called no model is recorded under. See the constant above.
LANE: Final = Lane.FAST

#: The lane a request that attempted a model call is recorded under. See the constant above.
MODEL_LANE: Final = Lane.ANSWER


class ToolCalls:
    """How many reader calls one request has started, and from which sources, by wrapping them.

    One instance per request, made inside `answer_lane`, so a count cannot leak from one
    request into the next. See `brain.gate.finish.A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS`. The
    source is the first half of the key a reader is registered under, noted as the call starts,
    for the ledger's `connector` (M27.1.5); the skills are what the model step offered (M27.15.9).
    """

    def __init__(self) -> None:
        self.started = 0
        #: Source calls made live for this request, which also moves it to the answer lane.
        self.live = 0
        #: Every source a reader was called for. A name each, never a record.
        self.sources: set[str] = set()
        #: The skills the model step offered to a model, by digest. Empty until it offers any.
        self.skills: tuple[SkillUse, ...] = ()

    def read_live(self, calls: int) -> None:
        """Count the live reads of one refresh, as calls started and as live reads."""
        self.started += calls
        self.live += calls

    def start(self) -> None:
        """Count one call that is about to start and is not a row read, such as a passage search."""
        self.started += 1

    def use(self, skills: tuple[SkillUse, ...]) -> None:
        """The model step is about to send these skills' cards; see `model_lane.draft`."""
        self.skills = skills

    @property
    def connector(self) -> str | None:
        """The one source read, or None for none or several. See `ONE_SOURCE_OR_NONE`."""
        return next(iter(self.sources)) if len(self.sources) == 1 else None

    def counting(
        self, readers: Mapping[tuple[str, str], RowReader]
    ) -> Mapping[tuple[str, str], RowReader]:
        """The same readers under the same keys, each counting a call before it makes it."""
        return {pair: self._counted(pair[0], reader) for pair, reader in readers.items()}

    def _counted(self, source: str, reader: RowReader) -> RowReader:
        def call(
            request: RowRequest,
            *,
            entitlement: EntitlementSet,
            now: datetime | None = None,
        ) -> Awaitable[TypedResult[RowRecord]]:
            # Counted before the call, so a read that raises is still a read that started.
            self.started += 1
            self.sources.add(source)
            return reader(request, entitlement=entitlement, now=now)

        return call


#: Why a cache hit does not re-run the lane.
A_CACHED_ANSWER_IS_SERVED_WITHOUT_ASKING_ANYTHING_AGAIN = (
    "The answer cache is keyed on the entitlement hash and the source epochs, so a hit is an "
    "answer computed for this reach against this data. Re-running the lane to check would "
    "spend the read the cache exists to avoid, and re-running it and then serving the cached "
    "one would be worse: two answers computed and the older shown."
)


@dataclass(frozen=True)
class Answered:
    """One question's outcome, for the caller that has to log it and write the frames.

    Carries the frames and the internal outcome side by side. The frames are what a person
    sees; `abstention` is what the audit log records and is never rendered, which is the
    division `brain.gate.abstain.Abstention` describes about its own `detail`.

    `composed` is present only when there was an answer, and it carries the trace reference,
    which is quotable and grants nothing.
    """

    frames: tuple[str, ...]
    #: Present when the lane answered. None when it abstained or served a cache hit.
    composed: ComposedAnswer | None = None
    #: Present when the lane declined. Recorded, never rendered.
    abstention: Abstention | None = None
    #: True when the answer came from the cache and no read happened.
    from_cache: bool = False
    #: The answer's text exactly as the text frame carries it, present only beside `composed`.
    #: What the answer cache stores, so a later hit says what this answer said. None for an answer
    #: read live, which is not kept: see `A_LIVE_VALUE_IS_NOT_KEPT_FOR_THE_NEXT_ASKER`.
    text: str | None = None
    #: What a live read left out, when it left anything out. With no `composed` beside it, the
    #: request is degraded: the source that holds the answer did not answer in time.
    partial: PartialRead | None = None
    #: What stands behind the answer, as its citation frames carried it, present only beside
    #: `composed`. For a channel that draws its own citations rather than writing the frames.
    provenance: Provenance | None = None
    #: True when the sensitive-topic interception answered with its referral, which is recorded
    #: by that path without the question's words and must be written down nowhere else, a
    #: person's thread included (M24.2.2, M9.1.1).
    referred: bool = False
    #: True when the abstention was handed to a person named for a skill's queue and the asker
    #: was told so (M8.3.1). A fact about what the asker was told, which the learning signal reads
    #: as `brain.memory.signals.Signal.ESCALATED` once the exchange is kept (M16.2.4, M16.2.8).
    escalated: bool = False

    def __post_init__(self) -> None:
        if not self.frames:
            msg = "an answered question with no frames is a request that hung"
            raise ValueError(msg)
        if self.composed is not None and self.abstention is not None:
            msg = (
                "an outcome that is both an answer and an abstention leaves the caller to "
                "pick, and the one they pick is the one they wrote the branch for first"
            )
            raise ValueError(msg)
        if self.text is not None and self.composed is None:
            # Text with no answer beside it is a refusal's words, which the cache must not keep.
            msg = "an answer's text is carried only beside the answer it is the text of"
            raise ValueError(msg)
        if self.provenance is not None and self.composed is None:
            msg = "evidence is carried only beside the answer it stands behind"
            raise ValueError(msg)


def served_from(answer: FastLaneAnswer, payload: ChannelPayload) -> str:
    """The sentence, built from what survived redaction and nothing else.

    The rule names the field it was written to answer with, and that field is either in the
    payload or was withheld. Reading it out of the payload rather than out of the fetched
    record is the whole of `A_SENTENCE_BUILT_BEFORE_REDACTION_IS_A_SENTENCE_THAT_SKIPPED_IT`.

    Returns the empty string when the field is not there, which the caller turns into an
    abstention. A sentence naming the field and leaving the value blank would say that the
    field exists and is not for them, which is the DENIED and ABSENT distinction rendered.
    """
    for record in payload.records:
        if answer.field in record:
            return f"{record[answer.field]}"
    return ""


def route_of(meter: Meter, front: FrontRecord | None) -> ModelRoute | None:
    """Where the request was routed and why: the executor's decision when it classified a call,
    the front half's when it classified none, or None when neither routed it (a cache hit, or a
    request that never passed the front half). See `THE_ROW_HOLDS_THE_LAST_ROUTING_DECISION_MADE`.

    Asked of `Meter.classified` rather than of `Meter.route`, which is None for two calls that
    disagree as well, and a disagreement is the executor's answer, not an absence of one.
    """
    if meter.classified():
        return meter.route()
    if front is None or front.routed_tier is None or front.tier_basis is None:
        return None
    return ModelRoute(tier=front.routed_tier, basis=front.tier_basis)


async def answer_lane(
    question: str,
    *,
    origin: Origin,
    recorders: Sequence[RequestRecorder],
    rules: Sequence[FastPathRule],
    readers: Mapping[tuple[str, str], RowReader],
    entitlement: EntitlementSet,
    policies: Mapping[str, FieldPolicy],
    reachable_sources: Iterable[str],
    sink: TraceSink,
    now: datetime,
    clock: Callable[[], datetime],
    cached: CachedAnswer | None = None,
    model: ModelLane | None = None,
    front: FrontRecord | None = None,
    gaps: Sequence[Gap] = (),
    referral: str | None = None,
    recorder: Recorder | None = None,
    live: LiveRecords | None = None,
    source_policies: Mapping[tuple[str, str], FieldPolicy] | None = None,
    horizons: Horizons = SEED_HORIZONS,
    ambiguity: AmbiguityReader | None = None,
) -> Answered:
    """Answer one question, and finish the request once whatever the answer was.

    **This is the single place a question ends**, which is why the recorders are a required
    argument rather than something a caller adds after it returns. See `brain.gate.finish`
    for why the completion point is here and not in a route or a channel adapter.

    The origin is checked against the reach before anything is read, so a question cannot be
    answered as one person and recorded as another. See
    `brain.gate.finish.A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO`.

    `finish` runs in a `finally`, so an answer, every kind of abstention, a cache hit and a
    fault all reach the recorders exactly once. The recorders are told which of those it was
    through `Finished.outcome`, and a recorder with no business knowing does not look.

    `clock` is read once, as the first thing the `finally` does, so the completion instant is
    the moment the outcome existed and not the moment some earlier recorder finished writing.
    It is a required argument with no default for the reason the recorders are: a default
    wall clock would be a clock this module reads, and a test passing a fixed `now` would then
    record a duration measured against the machine's real time.

    `model` is the model step for a question no rule answers, or None for a lane that abstains
    on it. One `Meter` is made here per request and handed to that step, and it is what the
    ledger row's lane and usage are read from: see
    `A_REQUEST_IS_RECORDED_UNDER_THE_LANE_WHOSE_BUDGET_IT_SPENT`.

    `front` is what `brain.gate.front.run_front_half` decided, carried to the request row; `gaps`
    are the departments the question named outside the reader's reach, stated after the text.

    `referral` is the sentence for a question `brain.audit.compliance.intercept` kept off the
    ordinary path (M24.2.2): nothing is looked up, cached or asked, and the frames carry the same
    steps an answer does, so only the sentence differs. See `_referred`.

    `live` reads a fast-path record's values from its source (M11.9.2), and `source_policies`
    redacts each source's rows by its own classification (M15.4.2); both are absent on a lane that
    reads nothing live and knows no source's classification, which answers exactly as before.

    `horizons` judge how fresh each citation is, a row's and a document's apart; the seeds until
    an install sets its own. See `brain.gate.provenance.Horizons`.
    """
    attributable(origin, entitlement.principal_id)
    calls = ToolCalls()
    meter = Meter()
    outcome: Answered | None = None
    try:
        outcome = await _outcome(
            question,
            rules=rules,
            readers=calls.counting(readers),
            entitlement=entitlement,
            policies=policies,
            reachable_sources=reachable_sources,
            sink=sink,
            now=now,
            cached=cached,
            model=model,
            meter=meter,
            trace_id=origin.trace_id,
            calls=calls,
            gaps=tuple(gaps),
            referral=referral,
            recorder=recorder,
            live=live,
            source_policies=source_policies,
            horizons=horizons,
            ambiguity=ambiguity,
        )
        return outcome
    finally:
        completed_at = clock()
        usage = meter.usage()
        await finish(
            recorders,
            Finished(
                origin=origin,
                at=now,
                outcome=outcome,
                completed_at=completed_at,
                entitlement_hash=entitlement.ent_hash(),
                # A model call or a live read spent the answer lane's budget. See
                # A_LIVE_READ_SPENDS_THE_ANSWER_LANES_BUDGET.
                lane=LANE if usage is None and not calls.live else MODEL_LANE,
                tool_calls=calls.started,
                model_usage=usage,
                front=front,
                # The agent the model step ran, for the sensitive read recorder (M24.3.2).
                agent_id=None
                if model is None or model.agent is None
                else model.agent.record.agent_id,
                # Where the request was routed, as it was decided (M3.6.3).
                route=route_of(meter, front),
                # The skills the model step offered (M27.15.9) and the one source read (M27.1.5).
                skills=calls.skills,
                connector=calls.connector,
            ),
        )


async def _outcome(
    question: str,
    *,
    rules: Sequence[FastPathRule],
    readers: Mapping[tuple[str, str], RowReader],
    entitlement: EntitlementSet,
    policies: Mapping[str, FieldPolicy],
    reachable_sources: Iterable[str],
    sink: TraceSink,
    now: datetime,
    cached: CachedAnswer | None,
    model: ModelLane | None,
    meter: Meter,
    trace_id: str,
    calls: ToolCalls,
    gaps: tuple[Gap, ...] = (),
    referral: str | None = None,
    recorder: Recorder | None = None,
    live: LiveRecords | None = None,
    source_policies: Mapping[tuple[str, str], FieldPolicy] | None = None,
    horizons: Horizons = SEED_HORIZONS,
    ambiguity: AmbiguityReader | None = None,
) -> Answered:
    """Answer one question, or decline, and hand back the frames either way.

    The order of the steps is the order of the work, and it is enforced by `AnswerStream`
    rather than by this function getting it right: understanding, checking reach, the tool
    input starting, reading what came back, then citations, then the prose.

    `policies` is a mapping rather than a callback because a callback is a place a caller
    could compute a policy from the answer, and a field policy chosen after the rows are
    known is a policy that can be chosen to fit them.

    A cache hit short-circuits everything: see
    `A_CACHED_ANSWER_IS_SERVED_WITHOUT_ASKING_ANYTHING_AGAIN`.
    """
    if referral is not None:
        # Before the cache and before anything is read: an intercepted question is served from
        # no store and written to none. See `brain.audit.compliance.intercept`.
        return _referred(referral)

    scope = scope_of_reach(reachable_sources)

    if cached is not None:
        served = serve_cached(cached, now)
        return Answered(frames=cache_hit(served), from_cache=True)

    stream = AnswerStream()
    frames = [stream.step(Progress.UNDERSTANDING), stream.step(Progress.CHECKING)]

    unserved = unserved_match(question, rules, readers)
    if not readers or unserved is not None:
        # A fact about this company's setup, identical for everybody, which is why abstain
        # treats it as safe to say. It is not a permission outcome and must not be reported
        # as one: nothing is connected for anybody, so saying so tells this caller nothing
        # about themselves.
        #
        # **And a question whose shape a rule matches, for a source nothing here reads, is the
        # same fact about one subject (M27.7.18).** Decided from the rules and the readers and
        # nothing else, before anything is read, so it is identical for every asker and for a
        # record that exists and one that does not. Until 2026-09-17 it was "I could not find
        # that", which is true and sends somebody to look for a record in a system nobody
        # connected; the source the rule names is kept for the ledger and never rendered.
        return _abstained(
            stream,
            frames,
            gaps,
            nothing_connected(
                scope,
                detail="no row readers" if unserved is None else "no reader for a matched rule",
                missing_source="" if unserved is None else unserved.rule.source,
            ),
        )

    if model is not None and no_rule_matches(question, rules):
        # Before anything is read. See THE_MODEL_STEP_TAKES_ONLY_A_QUESTION_NO_RULE_MATCHED.
        return await _answered_by_model(
            question,
            stream,
            frames,
            model=model,
            entitlement=entitlement,
            scope=scope,
            sink=sink,
            now=now,
            meter=meter,
            trace_id=trace_id,
            calls=calls,
            gaps=gaps,
            recorder=recorder,
            horizons=horizons,
        )

    frames.append(stream.step(at_tool_input_start()))
    _enter(recorder, GateStep.INVOKE)
    found = await respond(
        question,
        rules=rules,
        readers=readers,
        entitlement=entitlement,
        now=now,
        ambiguity=ambiguity,
    )

    # Emitted here rather than inside the branch below, and the reason is the second leak
    # found while writing this module's tests. `respond` returns None without reading when no
    # rule matched and after reading when two records answered to one name, so a step emitted
    # only on the paths that read would show one fewer step for one of them, and a caller
    # watching the steps could tell "two records exist under that name" from "no record does".
    # A progress step describes the lane's phases and never what a particular call found,
    # which is the same reason `at_tool_input_start` takes no argument.
    frames.append(stream.step(Progress.READING))

    if found is None:
        # No rule matched, two did, or two records answered to one name. One sentence for all
        # three: see THE_ASKER_IS_NEVER_TOLD_WHICH_KIND_OF_NOTHING_HAPPENED.
        return _abstained(stream, frames, gaps, nothing_retrieved(scope, detail="no single rule"))
    if isinstance(found, FastLaneUnresolved):
        # Records the asker reads, which are more than one client (M14.6.5). Named as ambiguous
        # and never combined: see fast_lane.NAMING_AMBIGUITY_ONLY_AMONG_RECORDS_THE_ASKER_READS.
        return _unresolved(
            stream, frames, gaps, found, entitlement=entitlement, scope=scope, now=now
        )

    policy = policy_for(found, policies, source_policies)
    if policy is None:
        # An entity with a rule and no classification is a misconfigured install, and it is
        # answered like every other nothing. Redacting against a default policy would be the
        # other option and it is the one that ships an unclassified column.
        log.warning("answer.no_policy", entity=found.entity, rule=found.rule_id)
        return _abstained(stream, frames, gaps, nothing_retrieved(scope, detail="unclassified"))

    read_live = False
    if live is not None:
        # The index found the record; its source answers for it. See
        # brain.ops.live_records.THE_INDEX_FINDS_A_RECORD_AND_THE_SOURCE_ANSWERS_FOR_IT.
        refreshed = await live.refresh(
            found.result,
            source=found.source,
            entity=found.entity,
            asker=entitlement.principal_id,
            trace_id=trace_id,
        )
        if refreshed is not None:
            calls.read_live(refreshed.calls)
            if refreshed.result is None:
                return _unreached(stream, frames, gaps, refreshed.partial, scope)
            found = replace(found, result=refreshed.result)
            read_live = True

    # The redactor's own pair, so the trace the sink records is the one that did the work.
    _enter(recorder, GateStep.REDACT)
    redacted = redact(found.result, entitlement=entitlement, policy=policy, now=now)
    payload = redacted.payload

    sentence = served_from(found, payload)
    declined = abstention_for_search(
        payload,
        scope=scope,
        sources_connected=True,
        # True, always, and the reason is the leak found while writing this module's tests.
        # Passing `bool(sentence)` here is the obvious thing to write and it separates two
        # outcomes that must never be separable: a record that came back with the answer
        # field locked has records in the payload, so the classifier answers "retrieved but
        # not answering", while a name that does not exist has no records and answers "I
        # could not find that". A caller comparing the two sentences learns which clients
        # exist and which columns they are refused. The withheld case is handled below, with
        # the same public sentence as the absent one.
        answers_the_question=True,
    )
    if declined is None and not sentence:
        declined = _withheld_or_absent(
            found, payload, scope, policy=policy, entitlement=entitlement, now=now
        )
    if declined is not None:
        return _abstained(stream, frames, gaps, declined)

    _enter(recorder, GateStep.COMPOSE)
    composed = compose(served_from(found, payload), redacted, sink=sink, now=now)
    # The evidence from the composer's own citations, and the rule that a claim needs one
    # (M8.2.4). A sentence read out of the payload always has its field behind it, so this
    # refuses nothing today; it is here so that stops being true loudly rather than quietly.
    evidence = provenance_for(composed, horizon=horizons.rows, now=now)
    uncited = abstain_if_uncited(evidence, scope=scope)
    if uncited is not None:
        return _abstained(stream, frames, gaps, uncited)
    return _answered(stream, frames, gaps, composed, scope, evidence, kept=not read_live)


def policy_for(
    found: FastLaneAnswer,
    policies: Mapping[str, FieldPolicy],
    source_policies: Mapping[tuple[str, str], FieldPolicy] | None,
) -> FieldPolicy | None:
    """The classification this answer's rows are redacted by: its own source's, first (M15.4.2).

    Keyed by source and entity where the caller knows the sources' classifications, so a second
    source projecting the same kind of record never redacts the first one's rows by its own rules.
    The entity-keyed mapping is the fallback for an entity only the product classifies, such as an
    uploaded table, which is the same for whichever source is named.
    """
    if source_policies is not None:
        own = source_policies.get((found.source, found.entity))
        if own is not None:
            return own
    return policies.get(found.entity)


def _unreached(
    stream: AnswerStream,
    frames: list[str],
    gaps: Sequence[Gap],
    partial: PartialRead,
    scope: SearchScope,
) -> Answered:
    """The source holding the answer did not answer in time, said as the asker may hear it.

    `PartialRead.notice` names the source only when this asker's reach already discloses it,
    which is `scope`, derived from reach and never from what ran (M11.5.5). Not an abstention: the
    record exists at this reach and was not read, which is a degraded request and not a gap in
    what the company's data covers, so the ledger records it as degraded and no gap row is kept.
    """
    notice = partial.notice(disclosable=frozenset(scope.covered))
    return Answered(
        frames=(*frames, stream.text(_with_gaps(notice, gaps)), stream.done()),
        partial=partial,
    )


def _referred(referral: str) -> Answered:
    """The referral as frames, with the steps every answer shows and no abstention.

    Not an abstention, because an abstention is recorded as a gap in what the company's data
    covers, and a gap row would say a question was asked here that the ordinary path could not
    answer. Not a composed answer either, because nothing was retrieved to compose it from. The
    steps are the fast path's, so the stream's shape does not say which kind of reply it carries.
    """
    stream = AnswerStream()
    return Answered(
        frames=(
            stream.step(Progress.UNDERSTANDING),
            stream.step(Progress.CHECKING),
            stream.step(at_tool_input_start()),
            stream.step(Progress.READING),
            stream.text(referral),
            stream.done(),
        ),
        referred=True,
    )


def no_rule_matches(question: str, rules: Sequence[FastPathRule]) -> bool:
    """Whether no rule's wording matches this question, whatever this install connects.

    Each rule is asked through `match_rule` on its own, as though its own source were served, so a
    rule for an unconnected source still counts as matching and two rules matching still count.
    Nothing about the caller and nothing read reaches this. See
    `THE_MODEL_STEP_TAKES_ONLY_A_QUESTION_NO_RULE_MATCHED`.
    """
    return all(
        match_rule(question, (rule,), served=frozenset({(rule.source, rule.entity)})) is None
        for rule in rules
    )


async def _answered_by_model(
    question: str,
    stream: AnswerStream,
    frames: list[str],
    *,
    model: ModelLane,
    entitlement: EntitlementSet,
    scope: SearchScope,
    sink: TraceSink,
    now: datetime,
    meter: Meter,
    trace_id: str,
    calls: ToolCalls,
    gaps: tuple[Gap, ...] = (),
    recorder: Recorder | None = None,
    horizons: Horizons = SEED_HORIZONS,
) -> Answered:
    """The model step's frames, after the understanding and checking steps.

    The looking-up and reading steps go out whatever the step found, for the reason the fast
    path emits its reading step unconditionally: a step describes the lane's phases and never
    what a call found. The composing step goes out only when a model was asked, which is decided
    by what survived redaction at this caller's reach, so a withheld passage and an absent one
    produce the same steps.

    The citations come from `ComposedAnswer.citations`, which `compose` derived from the payload
    the model was shown, and they go out before the prose, which is the model's reply and the
    only thing of the model's that reaches a frame.
    """
    frames.append(stream.step(at_tool_input_start()))
    drafted = await draft(
        question,
        lane=model,
        entitlement=entitlement,
        scope=scope,
        sink=sink,
        now=now,
        meter=meter,
        trace_id=trace_id,
        searching=calls.start,
        entering=None if recorder is None else recorder.enter,
        horizons=horizons,
        using=calls.use,
    )
    frames.append(stream.step(Progress.READING))
    if drafted.asked:
        frames.append(stream.step(Progress.COMPOSING))
    if isinstance(drafted.outcome, Abstention):
        return _abstained(stream, frames, gaps, drafted.outcome)
    said = "" if drafted.trimmed is None else drafted.trimmed.sentence()
    return _answered(stream, frames, gaps, drafted.outcome, scope, drafted.provenance, said=said)


def _withheld_or_absent(
    found: FastLaneAnswer,
    payload: ChannelPayload,
    scope: SearchScope,
    *,
    policy: FieldPolicy,
    entitlement: EntitlementSet,
    now: datetime,
) -> Abstention:
    """The record came back and the field the rule answers with is not in it. Which of the
    two reasons that is, for the audit log only.

    **Both produce the same sentence**, because `PUBLIC_TEXT` maps `NOT_ENTITLED` and
    `NOTHING_RETRIEVED` to one constant referenced twice rather than to two literals that
    happen to agree. So the branch below is invisible to the asker by construction, and
    `test_a_withheld_answer_and_an_absent_one_produce_identical_frames` asserts it on whole
    frame streams rather than on the two sentences looking alike.

    It is visible to an auditor, which is the entire reason `not_entitled` exists: "DENIED
    exists only for the audit log". Two layers can have refused the field, and this one can
    tell which of them did. `ChannelPayload.locked` names a field present on a record and
    withheld by the redactor. **A field the projection never fetched is the other, and it is
    the one every fast-lane refusal is**: `compile_projection` builds the SELECT list from the
    columns this caller holds a grant for, so a column they may not read is never read, the
    redactor never sees it and records no lock. Until 2026-09-29 only the first was looked for,
    so the lane logged an absence wherever a refusal had happened, and not one refusal of a
    column on Ask ever reached an administrator (M8.2.1). See
    `A_FIELD_THE_ASKER_HOLDS_NO_GRANT_FOR_WAS_REFUSED_AND_NOT_ABSENT`.
    """
    withheld = any(
        lock.field == found.field and lock.entity == found.entity for lock in payload.locked
    ) or _held_no_grant_for(found, policy, entitlement, now)
    if withheld:
        return not_entitled(
            scope,
            detail=f"{found.entity}.{found.field} locked",
            entity=found.entity,
            field=found.field,
        )
    return nothing_retrieved(scope, detail=f"{found.entity}.{found.field} absent")


def _held_no_grant_for(
    found: FastLaneAnswer, policy: FieldPolicy, entitlement: EntitlementSet, now: datetime
) -> bool:
    """Whether this caller holds no grant at all for the field the rule answers with.

    Decided from the field's own rule and the caller's reach, which is what
    `compile_projection` decided it from, so it names the refusal that layer made. Reached only
    once a record came back, so it never records a refusal beside a record that does not exist.
    A field nothing classifies is not a refusal of this caller but a gap in the install's
    classification, and a grant held in a narrower scope than the rows is left an absence:
    recording it as one fails towards the old behaviour rather than towards naming a refusal
    that did not happen.
    """
    rule = policy.rule_for(found.entity, found.field)
    return rule is not None and entitlement.scope_for(rule.required_capability, now) is None


#: Why a field the projection left out because of the caller's grants is recorded as a refusal.
A_FIELD_THE_ASKER_HOLDS_NO_GRANT_FOR_WAS_REFUSED_AND_NOT_ABSENT: Final = (
    "The projection reads only the columns the caller holds a grant for, so a field they hold "
    "none for is never fetched and the redactor records no lock. That field was refused, not "
    "absent, and the administrator's trace says so; the asker is told what an absent record "
    "tells them, word for word, because the two reasons share one public sentence."
)


def _enter(recorder: Recorder | None, step: GateStep) -> None:
    """Enter a back-half step on the request's recorder, when the caller brought one."""
    if recorder is not None:
        recorder.enter(step)


def _answered(
    stream: AnswerStream,
    frames: list[str],
    gaps: Sequence[Gap],
    composed: ComposedAnswer,
    scope: SearchScope,
    provenance: Provenance,
    *,
    kept: bool = True,
    said: str = "",
) -> Answered:
    """Close the stream with the evidence, then the prose, then done.

    One function for the fast path and the model step, so the text the frame carries and the
    text the cache stores are one value and cannot drift. `kept` is False for an answer read live,
    which carries no text for the cache: see `A_LIVE_VALUE_IS_NOT_KEPT_FOR_THE_NEXT_ASKER`. Each
    citation goes out as its evidence, with its freshness and badge (M8.1.1 to M8.1.3, M7.4.7), and
    the text carries the sentence about the weakest of them (M11.4.9), or says nothing stands
    behind it (M8.2.4). `said` is what the lane adds about how it answered, such as drawing on
    fewer passages than were found (M15.4.1), after the evidence notice.
    """
    noticed = with_evidence_notice(composed.text, provenance)
    noticed = f"{noticed} {said}" if said else noticed
    text = _with_gaps(_with_scope(noticed, scope), gaps)
    for one in provenance.evidence:
        frames.append(stream.evidence(one))
    frames.append(stream.text(text))
    frames.append(stream.done())
    return Answered(
        frames=tuple(frames),
        composed=composed,
        text=text if kept else None,
        provenance=provenance,
    )


def with_evidence_notice(text: str, provenance: Provenance) -> str:
    """The answer, followed by what it says about its evidence: old, or none at all."""
    said = UNCITED_TEXT if provenance.is_empty else provenance.notice()
    return f"{text} {said}" if said else text


def _abstained(
    stream: AnswerStream, frames: list[str], gaps: Sequence[Gap], declined: Abstention
) -> Answered:
    """Close the stream with the one sentence the asker is allowed to hear.

    `for_asker` rather than anything assembled here, because `AbstentionNotice` has no reason
    field precisely so that a caller trying to be helpful cannot render one. A refusal is told to
    an administrator instead, as a warning under the request's trace reference (M8.2.1): see
    `brain.gate.abstain.A_REFUSAL_IS_TOLD_TO_AN_ADMINISTRATOR_AND_READS_AS_NOTHING_TO_THE_ASKER`.
    """
    told = declined.for_administrator()
    if told is not None:
        log.warning("answer.withheld", **told)
    notice = declined.for_asker()
    return Answered(
        frames=(*frames, stream.text(_with_gaps(notice.render(), gaps)), stream.done()),
        abstention=declined,
    )


def unresolved_text(
    found: FastLaneUnresolved, *, entitlement: EntitlementSet, now: datetime
) -> str:
    """The sentence an ambiguous name is answered with, and the review link for a reviewer.

    The link is shown only to a reader holding the reviewer's capability over everything, and
    only when a review item is open; everybody else is given the plain sentence, review item or
    not, because whether one is open is reviewer state a non-reviewer must not learn.
    """
    scope = entitlement.scope_for(REVIEWER_CAPABILITY, now)
    reviewer = scope is not None and scope.matches({})
    if reviewer and found.review_ref is not None:
        return UnresolvedNotice(review_ref=found.review_ref).render()
    return UNRESOLVED_TEXT


def _unresolved(
    stream: AnswerStream,
    frames: list[str],
    gaps: Sequence[Gap],
    found: FastLaneUnresolved,
    *,
    entitlement: EntitlementSet,
    scope: SearchScope,
    now: datetime,
) -> Answered:
    """Close the stream with the unresolved sentence. Recorded as records retrieved and not
    answering, which is what happened: the records came back and none of them is the answer."""
    text = unresolved_text(found, entitlement=entitlement, now=now)
    declined = Abstention(
        reason=AbstentionReason.RETRIEVED_BUT_NOT_ANSWERING,
        scope=scope,
        detail="the name belongs to more than one client the asker reads",
    )
    return Answered(
        frames=(*frames, stream.text(_with_gaps(text, gaps)), stream.done()),
        abstention=declined,
    )


def _with_scope(text: str, scope: SearchScope) -> str:
    """The answer, followed by what it covered, when there is anything to say.

    The same shape `AbstentionNotice.render` uses, so an answer and a refusal carry the
    statement identically. A statement on one and not the other would let a reader tell them
    apart by its presence.
    """
    statement = scope.render()
    return f"{text} {statement}" if statement else text


def _with_gaps(text: str, gaps: Sequence[Gap]) -> str:
    """The text, followed by one sentence per department named outside the reader's reach.

    `Gap.message` and `Gap.request_access`, which carry the name the asker typed and nothing
    about whether it exists or what is behind it. Appended to answers and refusals alike.
    """
    stated = " ".join(f"{gap.message} {gap.request_access}" for gap in gaps)
    return f"{text} {stated}" if stated else text


async def frames_of(answered: Answered) -> AsyncIterator[str]:
    """The frames as a stream, for a response that writes them as they are ready.

    A generator over an already-complete tuple today, because the lane computes its answer
    before it writes any of it: a fast-path answer is one row read, and a model's answer is one
    call that is not streamed from the provider, so there is nothing yet to show in the
    meantime. It is written as a generator anyway so the response body's type does not change
    on the day the lane yields while it works, which is the change that would otherwise touch
    every caller.
    """
    for frame in answered.frames:
        yield frame
