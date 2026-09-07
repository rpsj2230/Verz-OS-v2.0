"""The lane that finally joins the pieces, held to the order and to the one sentence.

Everything here runs against the real `fast_lane.respond`, the real `serialise_for_channel`
and the real `abstain`, with a stand-in only where a database would be. That is the point of
the file: the four modules it composes were each correct and each called by nothing, and a
test that stubbed the joins would prove the joins in the same way the docstrings did.

Two properties carry the weight.

**Every kind of nothing produces the same frames.** A caller who may not see the record, a
name that does not exist, a question no rule matches, and a question two rules match must be
indistinguishable to the person who asked. Asserted by comparing whole frame streams for
equality rather than by checking each says something similar, because "similar" is what two
sentences are right up until somebody improves one of them.

**The order is the state machine's, not this lane's.** Citations before prose is asserted on
the decoded stream, so a lane that emitted them in the right order by luck and a lane that
was held to it read the same here, and the mutation table says which.

The decoder is the one from `tests/unit/test_streaming.py`, written from the event-stream
specification rather than by inverting the encoder.

Task ids: none
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.field_policy import Classification
from brain.core.redaction import ChannelPayload, LockedField, RedactionTrace
from brain.core.scope import Scope
from brain.gate import answer as answer_module
from brain.gate.abstain import (
    NOT_ANSWERING_TEXT,
    NOT_FOUND_TEXT,
    NOTHING_CONNECTED_TEXT,
    AbstentionReason,
    scope_of_reach,
)
from brain.gate.answer import Answered, answer_lane, frames_of, served_from
from brain.gate.answer_cache import AGE_MARKER
from brain.gate.cache_key import CachedAnswer
from brain.gate.fast_lane import FastLaneAnswer, FastPathRule, RowReader
from brain.gate.streaming import Event, Progress, frames, step_label
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.rows import RowQuery, RowTool
from tests.unit.test_streaming import decode

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

CLIENTS = TableClassification(
    entity="client",
    rules=(
        ColumnRule(
            column="name",
            required_capability=Capability(value="read:client.name"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="hours_remaining",
            required_capability=Capability(value="read:client.hours_remaining"),
            classification=Classification.CONFIDENTIAL,
        ),
    ),
)

CLIENT_TOOL = RowTool(source="laravel", classification=CLIENTS, description="Read a client.")

HOURS = FastPathRule(
    rule_id="client_hours_remaining",
    template="hours left on {client}",
    slot="client",
    source="laravel",
    entity="client",
    match_field="name",
    answer_field="hours_remaining",
)

ACME = {"entity": "client", "id": "c_447", "name": "Acme", "hours_remaining": "37"}
OTHER = {"entity": "client", "id": "c_448", "name": "Acme", "hours_remaining": "40"}

SEES_HOURS = ("read:client", "read:client.name", "read:client.hours_remaining")
SEES_NAME_ONLY = ("read:client", "read:client.name")


def ents(*caps: str, principal: str = "p_priya") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=one), scope=Scope()) for one in caps),
    )


class Rows:
    """A `RowSource` answering with fixed rows, so no database is needed to run the lane."""

    def __init__(self, *returns: Mapping[str, Any]) -> None:
        self.returns = list(returns)
        self.queries: list[RowQuery] = []

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.queries.append(query)
        return self.returns


class Sink:
    """A `TraceSink` that records what it was handed exactly once."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, ChannelPayload, RedactionTrace]] = []

    def emit(self, reference: str, payload: ChannelPayload, trace: RedactionTrace) -> None:
        self.emitted.append((reference, payload, trace))


def readers_for(source: Rows) -> dict[tuple[str, str], RowReader]:
    return {("laravel", "client"): CLIENT_TOOL.reader(source)}


def run(
    question: str = "hours left on Acme",
    *,
    rows: Rows | None = None,
    rules: Sequence[FastPathRule] = (HOURS,),
    entitlement: EntitlementSet | None = None,
    policies: Mapping[str, Any] | None = None,
    sources: Sequence[str] = ("laravel",),
    sink: Sink | None = None,
    cached: CachedAnswer | None = None,
    readers: Mapping[tuple[str, str], RowReader] | None = None,
) -> Answered:
    """One run of the lane, driven to completion the way this repository drives coroutines.

    `asyncio.run` inside a synchronous test rather than a plugin, which is the house
    convention: there is no `pytest-asyncio` here.
    """
    source = rows if rows is not None else Rows(ACME)
    return asyncio.run(
        answer_lane(
            question,
            rules=rules,
            readers=readers_for(source) if readers is None else readers,
            entitlement=entitlement if entitlement is not None else ents(*SEES_HOURS),
            policies=policies if policies is not None else {"client": CLIENTS.policy()},
            reachable_sources=sources,
            sink=sink if sink is not None else Sink(),
            now=NOW,
            cached=cached,
        )
    )


def body(answered: Answered) -> str:
    return frames(answered.frames)


def texts(answered: Answered) -> list[str]:
    return [one.data for one in decode(body(answered)) if one.event == Event.TEXT.value]


# --- the lane answers ----------------------------------------------------------------------


def test_a_question_a_rule_answers_comes_back_as_an_answer() -> None:
    """**The positive case, and without it every refusal below is satisfied by a lane that
    declines everything.**

    A lane that refuses every question passes every permission test in this file and is not a
    product. This asserts the whole way through: a rule matched, a row was read at the
    caller's reach, the field survived redaction, and the value reached the person.

    Delete this and the lane can return an abstention unconditionally with the file green."""
    answered = run()

    assert answered.abstention is None
    assert answered.composed is not None
    assert "37" in texts(answered)[0]


def test_an_answer_carries_its_citations_and_they_arrive_before_the_prose() -> None:
    """A reader reads prose as it lands and has decided whether to believe it before the last
    token arrives, so citations appended afterwards are read by nobody.

    Asserted on the decoded stream rather than on the call order, because the property is
    about what the receiver sees, and because a lane that got the order right by luck and one
    that was held to it look the same from the call site.

    Delete this and the citations move to wherever the composition loop happens to produce
    them, which is after the text, because that is when the text is finished."""
    seen = [one.event for one in decode(body(run()))]

    assert "citation" in seen
    assert seen.index("citation") < seen.index("text")
    assert seen[-1] == "done"


def test_a_citation_names_the_field_and_never_its_value() -> None:
    """`Citation` carries a field name because a citation holding the value would be a second
    copy of the answer travelling under a different name, into places the payload does not
    reach. The lane must not undo that by rendering one.

    Delete this and a citation grows the figure it stands behind, which reads as helpful and
    puts a confidential column in a frame that is not the answer."""
    citations = [one.data for one in decode(body(run())) if one.event == "citation"]

    assert citations
    assert any("hours_remaining" in one for one in citations)
    for one in citations:
        assert "37" not in one, one


def test_the_answer_says_what_it_covered_in_terms_of_the_askers_own_reach() -> None:
    """`SearchScope` is derived from what the asker may be told about and never from what ran,
    because a statement assembled from the sources that answered varies with whether a record
    existed, and the variation is readable by asking twice.

    The same statement appears on an answer and on a refusal, because a statement on one and
    not the other lets a reader tell them apart by its presence.

    Delete this and the scope sentence is dropped from the answer path, and its presence
    becomes a signal that the system declined."""
    answered = run()
    declined = run("hours left on Nobody", rows=Rows())

    assert "This covers laravel." in texts(answered)[0]
    assert "This covers laravel." in texts(declined)[0]


def test_the_trace_is_emitted_once_and_the_reference_grants_nothing() -> None:
    """M3.9.2: the sink is the one destination for a post-redaction payload. Once, because a
    trace emitted twice is two rows an auditor has to reconcile, and emitted before the answer
    is returned, because the runs worth reading are the ones that went wrong.

    The reference is in the frames only by way of nothing: it is not streamed at all today,
    and if it ever is, knowing it must not be a way to read the trace.

    Delete this and the lane can compose without a sink, which is the one thing `compose`
    exists to make impossible."""
    sink = Sink()
    answered = run(sink=sink)

    assert len(sink.emitted) == 1
    assert answered.composed is not None
    assert sink.emitted[0][0] == answered.composed.trace_ref


def test_the_trace_records_the_policy_and_the_reach_the_answer_was_computed_at() -> None:
    """The lane calls `serialise_for_channel`, which returns the payload alone so a channel
    adapter cannot reach the trace, so the trace it can build carries the two facts it has.
    Those two are the ones an auditor needs to reproduce the decision: which policy version
    and whose reach.

    Delete this and the trace is built with placeholder strings, and a reference points at a
    record that cannot be tied to a policy epoch."""
    sink = Sink()
    run(sink=sink)

    trace = sink.emitted[0][2]
    assert trace.policy_epoch == CLIENTS.policy().epoch()
    assert trace.ent_hash == ents(*SEES_HOURS).ent_hash()


# --- every kind of nothing is the same nothing ---------------------------------------------


def test_a_withheld_answer_and_an_absent_one_produce_identical_frames() -> None:
    """**The sharpest property in this file.** A caller who may not read the answer field and
    a caller asking about a client that does not exist must receive the same bytes.

    Compared as whole frame streams rather than as two sentences that look alike, because two
    sentences agree until somebody improves the wording of one, and the improvement is a
    permission leak in a diff that reads as copy editing.

    The withheld case is a real one: the caller holds the name capability and not the hours
    capability, so the row comes back and the answer field does not survive redaction.

    Delete this and the two paths drift, and a caller comparing them learns which clients
    exist by asking about names."""
    withheld = run(entitlement=ents(*SEES_NAME_ONLY))
    absent = run("hours left on Nobody", rows=Rows())

    assert withheld.frames == absent.frames
    assert NOT_FOUND_TEXT in texts(withheld)[0]


def test_no_rule_and_two_rules_produce_identical_frames() -> None:
    """ "Two rules matched your question" is a fact about how this installation is configured
    and a person who could see it could map the configuration by asking. `respond` returns
    None for both and this lane must not reintroduce the difference.

    The two-rule case uses two rules whose templates both match one question, which is what
    `fast_lane` treats as a fall-through.

    Delete this and somebody adds a helpful "your question was ambiguous", which is a report
    on the rule table."""
    both = FastPathRule(
        rule_id="client_hours_second",
        template="hours left on {name}",
        slot="name",
        source="laravel",
        entity="client",
        match_field="name",
        answer_field="hours_remaining",
    )

    unmatched = run("what is the weather")
    ambiguous = run(rules=(HOURS, both))

    assert unmatched.frames == ambiguous.frames
    assert NOT_FOUND_TEXT in texts(unmatched)[0]


def test_two_records_answering_to_one_name_is_the_same_nothing_again() -> None:
    """Two clients called Acme is a fact about this company's data, and telling the asker
    would confirm that at least two records exist under a name they may not otherwise be able
    to count.

    Delete this and the lane answers "I found more than one", which is a count."""
    two = run(rows=Rows(ACME, OTHER))
    none = run("hours left on Nobody", rows=Rows())

    assert two.frames == none.frames


def test_an_abstention_carries_no_reason_a_channel_could_render() -> None:
    """`AbstentionNotice` has no reason field, so a channel adapter trying to be helpful
    cannot render one, and this lane must not hand the reason out beside the frames in a way
    that invites it.

    The reason is on `Answered.abstention`, which is the auditor's half and is documented as
    never rendered. What is asserted here is that the two indistinguishable reasons produce
    equal notices while the audit record still tells them apart.

    Delete this and the public text and the recorded reason are read off the same object by
    whoever writes the channel."""
    withheld = run(entitlement=ents(*SEES_NAME_ONLY))
    absent = run("hours left on Nobody", rows=Rows())

    assert withheld.abstention is not None
    assert absent.abstention is not None
    assert withheld.abstention.for_asker() == absent.abstention.for_asker()
    assert withheld.abstention.for_asker().render() == absent.abstention.for_asker().render()


def test_the_ledger_records_a_refusal_that_the_asker_cannot_see() -> None:
    """**The one place the two nothings are told apart, and the place where telling them
    apart is the point.**

    `not_entitled` exists so the ledger can record what actually happened: DENIED exists only
    for the audit log. A lane that recorded every withheld field as an absence would leave a
    ledger in which nobody was ever refused anything, which is the audit trail failing at the
    only job it has.

    Its public half is `NOT_FOUND_TEXT`, the same constant `nothing_retrieved` renders,
    referenced twice rather than written twice, so the branch is invisible to the asker by
    construction. Both halves are asserted here: the reasons differ, and the notices are
    equal objects.

    Delete this and the branch is simplified away as a distinction without a difference, and
    the difference is the audit trail."""
    locked = ChannelPayload(
        records=({"entity": "client", "id": "c_447", "name": "Acme"},),
        locked=(LockedField(entity="client", record_id="c_447", field="hours_remaining"),),
    )
    absent = ChannelPayload(records=({"entity": "client", "id": "c_447", "name": "Acme"},))
    found = FastLaneAnswer(
        rule_id=HOURS.rule_id,
        entity="client",
        source="laravel",
        field="hours_remaining",
        result=TypedResult(records=()),
    )
    scope = scope_of_reach(("laravel",))

    refused = answer_module._withheld_or_absent(found, locked, scope)
    missing = answer_module._withheld_or_absent(found, absent, scope)

    assert refused.reason is AbstentionReason.NOT_ENTITLED
    assert missing.reason is AbstentionReason.NOTHING_RETRIEVED
    assert refused.for_asker() == missing.for_asker()
    assert refused.for_asker().render() == missing.for_asker().render()


def test_a_lock_on_another_field_is_not_a_refusal_of_the_one_that_was_asked_for() -> None:
    """**Written because a mutation survived.** Dropping the field comparison and matching a
    lock on the entity alone leaves every test above green, because they all lock the field
    the rule answers with.

    The record here has a lock on its name and the answer field is simply not present. The
    caller was refused something, and they were not refused this: recording it as a refusal
    of the answer field would put a reason in the ledger that names a capability nobody was
    denied, which is the audit trail lying in the direction that looks diligent.

    Delete this and the lock check becomes an entity check, and every partially locked record
    reports a refusal of whatever was asked for."""
    other = ChannelPayload(
        records=({"entity": "client", "id": "c_447"},),
        locked=(LockedField(entity="client", record_id="c_447", field="name"),),
    )
    found = FastLaneAnswer(
        rule_id=HOURS.rule_id,
        entity="client",
        source="laravel",
        field="hours_remaining",
        result=TypedResult(records=()),
    )

    recorded = answer_module._withheld_or_absent(found, other, scope_of_reach(("laravel",)))

    assert recorded.reason is AbstentionReason.NOTHING_RETRIEVED
    assert recorded.detail.endswith("absent")


def test_a_column_the_caller_cannot_read_is_refused_before_it_is_ever_fetched() -> None:
    """**The reason the branch above cannot fire through this lane, asserted so nobody
    mistakes it for a bug in the ledger.**

    `compile_projection` builds the SELECT list from the columns this caller reaches, so a
    column they may not read is never fetched, so the redactor never sees it and records no
    lock. The refusal happened one layer down and left nothing here to record, which means
    this lane logs an absence where a refusal occurred. That is a real gap in the audit trail
    and it is stated rather than implied.

    Delete this and somebody reading `_withheld_or_absent` concludes the ledger distinguishes
    the two, and writes a report that counts refusals at zero."""
    withheld = run(entitlement=ents(*SEES_NAME_ONLY))

    assert withheld.abstention is not None
    assert withheld.abstention.reason is AbstentionReason.NOTHING_RETRIEVED
    assert withheld.abstention.detail.endswith("absent")


# --- the shape of the stream ---------------------------------------------------------------


def test_a_question_reaching_a_lane_with_nothing_connected_is_told_so() -> None:
    """Nothing connected is a fact about this company's setup, identical for everybody, which
    is why `abstain` treats it as safe to say and useful to hear. It is not a permission
    outcome and must not be reported as one.

    Delete this and an installation with no connectors answers "I could not find that" to
    every question, which reads to every user as their own permissions."""
    answered = run(readers={})

    assert NOTHING_CONNECTED_TEXT in texts(answered)[0]
    assert answered.abstention is not None
    assert answered.abstention.reason is AbstentionReason.NOTHING_CONNECTED


def test_the_progress_steps_are_the_work_in_the_order_it_happens() -> None:
    """The steps are what a person watches while they wait, and they must describe the lane's
    real order rather than a fixed animation: reading the question, checking reach, the tool
    input starting, then reading what came back.

    Delete this and the steps become decoration, and the first one to be emitted out of order
    teaches a reader to ignore all of them."""
    steps = [one.data for one in decode(body(run())) if one.event == Event.STEP.value]

    assert steps == [
        step_label(Progress.UNDERSTANDING),
        step_label(Progress.CHECKING),
        step_label(Progress.LOOKING_UP),
        step_label(Progress.READING),
    ]


def test_a_lane_that_declines_before_reading_does_not_claim_to_have_read() -> None:
    """The step that says the tool started is emitted when the tool starts, and the step that
    says something came back is emitted when something did. An abstention raised before the
    read must not carry either.

    Delete this and a refusal shows the full progression, which tells a reader the system
    looked when it did not, and makes the steps worthless as a signal."""
    steps = [one.data for one in decode(body(run(readers={}))) if one.event == "step"]

    assert steps == [step_label(Progress.UNDERSTANDING), step_label(Progress.CHECKING)]
    assert step_label(Progress.READING) not in steps


def test_every_outcome_ends_the_stream_exactly_once() -> None:
    """A stream that never closes is a client that spins, and one that closes twice is a frame
    written into a client that has stopped listening.

    All four outcomes, because a lane that closes on the paths somebody remembered is a lane
    with a hole on the path they did not.

    Delete this and an early return skips the close, and the symptom is a request that appears
    to hang while its answer sits complete on the server."""
    for answered in (
        run(),
        run(readers={}),
        run("hours left on Nobody", rows=Rows()),
        run(entitlement=ents(*SEES_NAME_ONLY)),
    ):
        events = [one.event for one in decode(body(answered))]
        assert events.count("done") == 1, events
        assert events[-1] == "done", events


# --- the cache hit --------------------------------------------------------------------------


def test_a_cache_hit_answers_without_reading_a_row() -> None:
    """**M6.3.6 wired.** The cache is keyed on the entitlement hash and the source epochs, so
    a hit is an answer computed for this reach against this data. Re-running the lane to check
    would spend exactly the read the cache exists to avoid.

    The evidence is an empty query log rather than a matching answer: a lane that read the row
    and then served the cached text would pass a text comparison.

    Delete this and the cache saves the model call it is not making and nothing else."""
    rows = Rows(ACME)
    stored = CachedAnswer(
        key="k",
        payload="Acme has 37 hours.",
        stored_at=NOW - timedelta(minutes=6),
        source_epochs={},
    )

    answered = run(rows=rows, cached=stored)

    assert rows.queries == []
    assert answered.from_cache is True
    assert answered.composed is None


def test_a_cached_answer_still_says_how_old_it_is_after_it_has_been_framed() -> None:
    """The whole chain, end to end: `serve_cached` puts the age after a blank line, a blank
    line ends an event, and `encode` splits the value so it survives. Any one of the three
    failing removes the disclosure and nothing raises.

    Delete this and the join between the cache and the transport is untested, which is where
    the two correct halves stop adding up."""
    stored = CachedAnswer(
        key="k",
        payload="Acme has 37 hours.",
        stored_at=NOW - timedelta(minutes=6),
        source_epochs={},
    )

    text = texts(run(cached=stored))[0]

    assert AGE_MARKER in text
    assert "6 minutes ago" in text
    assert "Acme has 37 hours." in text


# --- the pieces -----------------------------------------------------------------------------


def test_the_sentence_is_read_out_of_the_payload_and_not_out_of_the_record() -> None:
    """The fast lane hands back a `TypedResult` rather than a sentence, deliberately, because
    a sentence built from what was fetched would be a payload that never went through the
    redaction walker.

    Asserted directly on `served_from` with a payload that has had the field removed, so the
    claim is about the function rather than about one run of the lane.

    Delete this and the sentence is built from `answer.result.records`, which is the obvious
    thing to write and reads the value the redactor withheld."""
    empty = ChannelPayload(records=({"entity": "client", "id": "c_447", "name": "Acme"},))
    full = ChannelPayload(records=(dict(ACME),))

    class Stub:
        field = "hours_remaining"

    stub: Any = Stub()

    assert served_from(stub, empty) == ""
    assert served_from(stub, full) == "37"


def test_an_entity_with_a_rule_and_no_classification_answers_like_every_other_nothing() -> None:
    """A rule naming an entity nothing classifies is a misconfigured install. Redacting it
    against a default policy is the other option and it is the one that ships an unclassified
    column to whoever asked.

    Delete this and a `KeyError` reaches the response, or worse, a permissive default does."""
    answered = run(policies={})
    absent = run("hours left on Nobody", rows=Rows())

    assert answered.frames == absent.frames


def test_an_outcome_cannot_be_both_an_answer_and_a_refusal() -> None:
    """A caller handed both has to pick, and the one they pick is the one they wrote the
    branch for first, which is whichever the happy path was.

    Delete this and a partially assembled outcome carries a stale abstention from an earlier
    branch, and the refusal is logged beside the answer that was shown."""
    with pytest.raises(ValueError, match="both an answer and an abstention"):
        Answered(
            frames=("x",),
            composed=run().composed,
            abstention=run(readers={}).abstention,
        )


def test_an_outcome_with_no_frames_cannot_be_constructed() -> None:
    """An answered question that produced nothing to write is a request that hangs, and it
    hangs in the client rather than failing on the server, so nothing here would notice.

    Delete this and an early return with an empty tuple is a silent timeout for the asker."""
    with pytest.raises(ValueError, match="request that hung"):
        Answered(frames=())


def test_the_frames_can_be_walked_as_a_stream() -> None:
    """The response writes frames as they are ready, so the lane hands back something
    iterable rather than one string. It is a generator over a complete tuple today because a
    fast-path answer is one row read with nothing to show in the meantime, and it is written
    as a generator so the body's type does not change on the day the lane yields while it
    works.

    Delete this and the route builds the body by concatenating, and adding a real yield later
    is a change at every call site."""

    answered = run()

    async def collected() -> list[str]:
        return [frame async for frame in frames_of(answered)]

    assert asyncio.run(collected()) == list(answered.frames)


def test_the_lane_never_says_which_kind_of_nothing_happened() -> None:
    """The constant states the rule in words so it survives the person who wrote it, and the
    three public sentences are the only ones a person can receive.

    Delete this and a fourth sentence is added for a case that felt worth distinguishing."""
    assert "could tell them apart could map both" in (
        answer_module.THE_ASKER_IS_NEVER_TOLD_WHICH_KIND_OF_NOTHING_HAPPENED
    )

    said = set()
    for answered in (
        run(readers={}),
        run("hours left on Nobody", rows=Rows()),
        run(entitlement=ents(*SEES_NAME_ONLY)),
        run("what is the weather"),
    ):
        said.add(texts(answered)[0].split(" This covers")[0])

    assert said <= {NOT_FOUND_TEXT, NOT_ANSWERING_TEXT, NOTHING_CONNECTED_TEXT}
