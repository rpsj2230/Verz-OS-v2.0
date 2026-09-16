"""The answer lane: one question in, a stream of frames out, and no model anywhere in it.

Until this module the pieces of an answer existed and nothing joined them.
`brain.gate.fast_lane.respond` matched a data-driven rule and fetched a row and was called
by nothing. `brain.gate.abstain` classified an outcome and was called by nothing.
`brain.gate.streaming` encoded frames and was called by nothing. `brain.gate.compose.compose`
derived citations from a redacted payload and was called by nothing. Four correct, tested,
documented modules with no path between them and a request, which is the recurring defect in
this repository and by the time this was written it had thirteen recorded instances.

**This is a lane and not the lane.** There is no model call here. A model can be called now,
through `brain.models.calls.ModelCalls`, and this lane does not call it, because a model step
needs what it may be shown decided first and that is not decided here. So the lane answers what a
fast-path rule can answer, and abstains otherwise, using the abstention vocabulary that already
exists rather than a sentence written here. When the model lane is built, it goes where `_abstained`
currently sits, and everything around it, the ordering, the redaction and the frames, is
already right.

**Every frame goes through `brain.gate.streaming.AnswerStream`, so the order is enforced
rather than intended.** Citations before prose, no step once the prose has started, nothing
after the stream closes. A lane that assembled its own frames would be a second place that
decides what a person may watch arriving, and the first place is the one with the argument in
front of it.

**Redaction happens exactly where the records route does it**, through
`brain.core.redaction.serialise_for_channel` with the caller's own reach. Not a second
enforcement point: the same one, called from a second place, which is the difference between
defence in depth and two rules that can disagree. The row reader was already handed the same
entitlement, so the scope predicate was inside the query as well as around the result.

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

**A question that matched no rule abstains rather than erroring.** No rule matched, two
matched, or two records answered to one name: `respond` returns None for all three and the
distinction is deliberately not visible to the asker, because "two rules matched your
question" is a fact about this installation's configuration and "two records matched that
name" is a fact about its data.

**The scope statement is derived from the asker's reach and never from what ran.** That is
`brain.gate.abstain.SearchScope`'s rule and this module obeys it by passing the sources the
caller may be told about, which the caller computes from their own entitlements. A statement
assembled from the sources that actually answered would vary with whether a record existed,
and the variation is readable by asking twice.

**The lane declares the budget it runs under, and it is the fast lane's.** No path through this
module calls a model, so every request it finishes spent what `brain.core.lane.Lane.FAST`
allows, including a question `brain.gate.classify` would have sent to the answer lane and this
lane abstained on. Recording those as `ANSWER` would compare a two-millisecond abstention against
an eight-second objective and report it met. See
`NO_PATH_THROUGH_THIS_LANE_CALLS_A_MODEL_SO_EVERY_REQUEST_SPENT_THE_FAST_BUDGET`; when the model
lane goes where `_abstained` sits, which lane produced an outcome becomes a property of the
outcome rather than of this module.

Scope: this module opens no connection and reads no clock of its own. `now` is a parameter, the
readers are handed in, the rules are handed in, and the trace sink is handed in. The completion
instant comes from `clock`, which the caller hands in and the lane reads exactly once, in the
`finally` that finishes the request. It is `async` only because a row read is, which is the one
thing here that waits on anything.

**Every reader call is counted as it starts, by a wrapper the lane puts around the readers it was
handed (M21.3.4).** The count reaches `Finished.tool_calls` and from there the trace ledger's
`tool_count`, which is one half of a question's shape. The lane wraps rather than `respond`
counting, because `respond` returns None both before a read and after one, and a count it
reported would have to be threaded out through every one of those returns. A wrapper cannot
miss a return, and it counts a read that raised, which is a call the lane made. See
`brain.gate.finish.A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS`.

Task ids: M30.5.2, M21.3.4
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import structlog

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.field_policy import FieldPolicy
from brain.core.lane import Lane
from brain.core.redaction import (
    ChannelPayload,
    RedactedAnswer,
    RedactionTrace,
    serialise_for_channel,
)
from brain.gate.abstain import (
    Abstention,
    SearchScope,
    abstention_for_search,
    not_entitled,
    nothing_connected,
    nothing_retrieved,
    scope_of_reach,
)
from brain.gate.answer_cache import serve_cached
from brain.gate.cache_key import CachedAnswer
from brain.gate.compose import ComposedAnswer, TraceSink, compose
from brain.gate.fast_lane import FastLaneAnswer, FastPathRule, RowReader, respond
from brain.gate.finish import Finished, Origin, RequestRecorder, attributable, finish
from brain.gate.streaming import AnswerStream, Progress, at_tool_input_start, cache_hit
from brain.knowledge.rows import RowRecord, RowRequest

log = structlog.get_logger(__name__)

#: Why a lane that cannot answer says nothing about why.
THE_ASKER_IS_NEVER_TOLD_WHICH_KIND_OF_NOTHING_HAPPENED = (
    "No rule matched, two rules matched, two records answered to one name, the record was "
    "withheld, and the record does not exist all produce the same sentence. The first two "
    "are facts about how this installation is configured and the last three are facts about "
    "its data, and a person who could tell them apart could map both by asking. The "
    "abstention vocabulary already carries the distinction for the audit log, which is the "
    "only reader entitled to it."
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

#: Why every request this lane finishes is recorded under the fast lane.
NO_PATH_THROUGH_THIS_LANE_CALLS_A_MODEL_SO_EVERY_REQUEST_SPENT_THE_FAST_BUDGET: Final = (
    "A lane is a budget, and the budget a request spent is decided by what ran, not by what "
    "the question would have been classified as. Nothing in this module calls a model, so an "
    "answer, an abstention, a cache hit and a fault all spent the fast lane's allowance. "
    "Filing the abstentions under the answer lane because a model would have read them there "
    "measures a lane that did not run against an objective sized for one that did."
)

#: The lane this module is, for the ledger. See the constant above.
LANE: Final = Lane.FAST


class ToolCalls:
    """How many reader calls one request has started, counted by wrapping the readers.

    One instance per request, made inside `answer_lane`, so a count cannot leak from one
    request into the next. See `brain.gate.finish.A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS`.
    """

    def __init__(self) -> None:
        self.started = 0

    def counting(
        self, readers: Mapping[tuple[str, str], RowReader]
    ) -> Mapping[tuple[str, str], RowReader]:
        """The same readers under the same keys, each counting a call before it makes it."""
        return {pair: self._counted(reader) for pair, reader in readers.items()}

    def _counted(self, reader: RowReader) -> RowReader:
        def call(
            request: RowRequest,
            *,
            entitlement: EntitlementSet,
            now: datetime | None = None,
        ) -> Awaitable[TypedResult[RowRecord]]:
            # Counted before the call, so a read that raises is still a read that started.
            self.started += 1
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
    """
    attributable(origin, entitlement.principal_id)
    calls = ToolCalls()
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
        )
        return outcome
    finally:
        completed_at = clock()
        await finish(
            recorders,
            Finished(
                origin=origin,
                at=now,
                outcome=outcome,
                completed_at=completed_at,
                entitlement_hash=entitlement.ent_hash(),
                lane=LANE,
                tool_calls=calls.started,
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
    cached: CachedAnswer | None = None,
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
    scope = scope_of_reach(reachable_sources)

    if cached is not None:
        served = serve_cached(cached, now)
        return Answered(frames=cache_hit(served), from_cache=True)

    stream = AnswerStream()
    frames = [stream.step(Progress.UNDERSTANDING), stream.step(Progress.CHECKING)]

    if not readers:
        # A fact about this company's setup, identical for everybody, which is why abstain
        # treats it as safe to say. It is not a permission outcome and must not be reported
        # as one: nothing is connected for anybody, so saying so tells this caller nothing
        # about themselves.
        return _abstained(stream, frames, nothing_connected(scope, detail="no row readers"))

    frames.append(stream.step(at_tool_input_start()))
    found = await respond(question, rules=rules, readers=readers, entitlement=entitlement, now=now)

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
        return _abstained(stream, frames, nothing_retrieved(scope, detail="no single rule"))

    policy = policies.get(found.entity)
    if policy is None:
        # An entity with a rule and no classification is a misconfigured install, and it is
        # answered like every other nothing. Redacting against a default policy would be the
        # other option and it is the one that ships an unclassified column.
        log.warning("answer.no_policy", entity=found.entity, rule=found.rule_id)
        return _abstained(stream, frames, nothing_retrieved(scope, detail="unclassified"))

    payload = serialise_for_channel(found.result, entitlement=entitlement, policy=policy, now=now)

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
        declined = _withheld_or_absent(found, payload, scope)
    if declined is not None:
        return _abstained(stream, frames, declined)

    composed = compose(
        served_from(found, payload),
        _redacted(payload, policy=policy, entitlement=entitlement),
        sink=sink,
        now=now,
    )

    for citation in composed.citations:
        frames.append(stream.citation(citation))
    frames.append(stream.text(_with_scope(composed.text, scope)))
    frames.append(stream.done())

    return Answered(frames=tuple(frames), composed=composed)


def _withheld_or_absent(
    found: FastLaneAnswer, payload: ChannelPayload, scope: SearchScope
) -> Abstention:
    """The record came back and the field the rule answers with is not in it. Which of the
    two reasons that is, for the audit log only.

    **Both produce the same sentence**, because `PUBLIC_TEXT` maps `NOT_ENTITLED` and
    `NOTHING_RETRIEVED` to one constant referenced twice rather than to two literals that
    happen to agree. So the branch below is invisible to the asker by construction, and
    `test_a_withheld_answer_and_an_absent_one_produce_identical_frames` asserts it on whole
    frame streams rather than on the two sentences looking alike.

    It is visible to an auditor, which is the entire reason `not_entitled` exists: "DENIED
    exists only for the audit log". `ChannelPayload.locked` names fields present on a record
    and withheld from this caller, so this layer is the one that saw the refusal and is
    therefore the one that can record it. A lane that recorded every one of these as an
    absence would leave a ledger in which nobody was ever refused anything.
    """
    # Unreachable through the fast lane as it stands, and kept with the reason stated rather
    # than deleted. `compile_projection` builds the SELECT list from the columns this caller
    # reaches, so a column they may not read is never fetched, so the redactor never sees it
    # and records no lock. The refusal has already happened, one layer down, and left nothing
    # here to record: this lane logs an absence where a refusal occurred, and that is a real
    # gap in the ledger rather than a tidy outcome. The branch is here for a payload whose
    # lock came from the redactor rather than the projection, which is what a document answer
    # or a widened projection would produce.
    withheld = any(
        lock.field == found.field and lock.entity == found.entity for lock in payload.locked
    )
    if withheld:
        return not_entitled(scope, detail=f"{found.entity}.{found.field} locked")
    return nothing_retrieved(scope, detail=f"{found.entity}.{found.field} absent")


def _abstained(stream: AnswerStream, frames: list[str], declined: Abstention) -> Answered:
    """Close the stream with the one sentence the asker is allowed to hear.

    `for_asker` rather than anything assembled here, because `AbstentionNotice` has no reason
    field precisely so that a caller trying to be helpful cannot render one.
    """
    notice = declined.for_asker()
    return Answered(
        frames=(*frames, stream.text(notice.render()), stream.done()),
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


def _redacted(
    payload: ChannelPayload, *, policy: FieldPolicy, entitlement: EntitlementSet
) -> RedactedAnswer:
    """Pair the payload with a trace, for `compose`, which wants the redaction's own result.

    `serialise_for_channel` deliberately returns the payload alone, so a channel adapter
    calling it cannot reach the trace, the redaction reasons or the dropped records. This
    lane is such a caller and is held to the same limit, so the trace it can build carries
    the two facts it does have, the policy epoch and the entitlement hash, and no redactions
    and no drops.

    **That is a real gap and it is stated rather than hidden.** An auditor opening this trace
    reference learns which policy version and which reach the answer was computed at, and
    learns nothing about what was withheld, because this lane was never told. Closing it
    means calling `redact_for_gate`, which takes a `GateContext` and a `Recorder`, which is
    the pipeline that does not exist yet. An empty list of redactions is not a claim that
    nothing was redacted: `RedactionTrace` puts the counts where only an auditor reads them,
    and an auditor reading a count of zero here would be reading this module's ignorance.
    """
    return RedactedAnswer(
        payload=payload,
        trace=RedactionTrace(policy_epoch=policy.epoch(), ent_hash=entitlement.ent_hash()),
    )


async def frames_of(answered: Answered) -> AsyncIterator[str]:
    """The frames as a stream, for a response that writes them as they are ready.

    A generator over an already-complete tuple today, because the lane computes its answer
    before it writes any of it: a fast-path answer is one row read and there is nothing to
    show in the meantime. It is written as a generator anyway so the response body's type
    does not change on the day the lane yields while it works, which is the change that
    would otherwise touch every caller.
    """
    for frame in answered.frames:
        yield frame
