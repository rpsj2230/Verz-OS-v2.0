"""The answer lane's model step, held to what a model is shown and to what it is never trusted with.

Driven through `brain.gate.answer.answer_lane`, the real `serialise_for_channel`, the real
`compose` and a real `brain.models.calls.ModelCalls` over an SDK driver whose transport records
every request, so the prompt a provider would receive is read off the request that was sent rather
than off a function that builds one. A stand-in only where a database or a network would be.

**The search stand-in returns what a real search at this reach would not.** It hands back a
passage of a document the caller may not read, beside one they may read with a field they may not.
That is a bug in the layer above, planted on purpose: the redactor is the last line and the only
one that catches such a bug, so the proof that nothing withheld reaches a model is a proof with the
first wall already breached. `tests/unit/test_model_lane_db.py` asks the same of the real search
on PostgreSQL, where the first wall is standing.

**Every surface a value could escape through is read separately**, the prompt, the attempt rows,
the trace sink, the ledger row, the frames and the log, so a failure names the one that leaked.

Task ids: none
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from structlog.testing import capture_logs

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import ChannelPayload, RedactionTrace
from brain.core.scope import Clause, Op, Scope
from brain.gate.abstain import (
    NOT_ANSWERING_TEXT,
    NOT_FOUND_TEXT,
    NOTHING_CONNECTED_TEXT,
    REFUSED_TEXT,
    AbstentionReason,
)
from brain.gate.answer import Answered, answer_lane, no_rule_matches
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.context import Channel
from brain.gate.effort import settings_for
from brain.gate.fast_lane import FastPathRule
from brain.gate.finish import Finished, Origin
from brain.gate.model_lane import (
    A_DEPARTMENT_SCOPED_FIELD_GRANT_READS_ITS_OWN_DEPARTMENTS_PASSAGES,
    A_DEPARTMENT_TEXT_RIGHT_READS_COMPANY_AND_OWN_PERSONAL_PASSAGES,
    EARLIER_CHARS,
    EARLIER_SHOWN,
    HINTS_HEADING,
    MAX_HINTS_SHOWN,
    PASSAGE_POLICY,
    PASSAGES_SHOWN,
    PREFIX,
    SHOWN_FIELDS,
    DocumentSearchTool,
    FixedHints,
    FollowUp,
    ModelLane,
    hints_block,
    messages_of,
    passage_reach,
    prompt_bytes,
    prompt_for,
    redact_passages,
    shown,
    tier_for,
)
from brain.gate.streaming import Event, Progress, frames, step_label
from brain.identity.lifecycle import STARTER_PACK
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, QUESTION_CHARS, KnowledgePassage
from brain.models.adapter import Completion
from brain.models.driver import DriverRequest, ProviderUnavailable, Role
from brain.models.routing import (
    DEFAULT_TIER,
    ESCALATION_HEADROOM,
    TIER_CONTEXT_WINDOW,
    RoutingRequest,
    classify_tier,
)
from brain.ops.telemetry import request_telemetry_of
from tests.unit.test_answer_lane import (
    ACME,
    CLIENTS,
    HOURS,
    OTHER,
    SEES_HOURS,
    UNREAD,
    Rows,
    Sink,
    readers_for,
)
from tests.unit.test_model_calls import T0, Ladder, Log, Scripted, executor, rung
from tests.unit.test_streaming import decode

NOW = T0

#: The document the caller may read, and the one they may not. Every planted value is a word no
#: other string in this file or in the lane's own constants contains, so its absence is its own.
READABLE_DOCUMENT = "doc_handbook"
WITHHELD_DOCUMENT = "doc_quarantined"

VISIBLE = KnowledgePassage(
    entity=KNOWLEDGE_ENTITY,
    id="c_handbook_1",
    document_id=READABLE_DOCUMENT,
    # Locked for the caller below: they hold no `read:knowledge.title`.
    title="Handbook LOCKEDTITLEVERMILION",
    section="Leave",
    document="Annual leave is twenty five days a year.",
    updated_at="2999-01-01T00:00:00+00:00",
)

WITHHELD = KnowledgePassage(
    entity=KNOWLEDGE_ENTITY,
    id="c_withheldrecordid_1",
    document_id=WITHHELD_DOCUMENT,
    title="Salaries WITHHELDTITLEOCHRE",
    section="WITHHELDSECTIONUMBER",
    document="Salary bands are WITHHELDBODYCERULEAN for every grade.",
    updated_at="2999-02-02T00:00:00+00:00",
)

#: What must reach nowhere: the withheld passage's values and the visible one's locked field.
PLANTED: tuple[str, ...] = (
    "c_withheldrecordid_1",
    WITHHELD_DOCUMENT,
    "WITHHELDTITLEOCHRE",
    "WITHHELDSECTIONUMBER",
    "WITHHELDBODYCERULEAN",
    "LOCKEDTITLEVERMILION",
)

REPLY = "Annual leave is twenty five days a year, according to the handbook."

QUESTION = "how much annual leave do we get"


def on_the_readable_document(capability: str) -> Grant:
    return Grant(
        capability=Capability(value=capability),
        scope=Scope(clauses=(Clause(field="document_id", op=Op.EQ, value=READABLE_DOCUMENT),)),
    )


#: The caller: the fast lane's client grants, the knowledge plane, and every passage field but
#: the title, on the readable document only.
CALLER = EntitlementSet(
    principal_id="p_priya",
    grants=(
        *(Grant(capability=Capability(value=one), scope=Scope()) for one in SEES_HOURS),
        Grant(capability=Capability(value="read:knowledge"), scope=Scope()),
        on_the_readable_document("read:knowledge.document"),
        on_the_readable_document("read:knowledge.section"),
        on_the_readable_document("read:knowledge.updated_at"),
    ),
)


class Passages:
    """A `PassageSearch` handing back fixed passages, and every question it was asked."""

    def __init__(self, *records: KnowledgePassage) -> None:
        self.records = records
        self.asked: list[tuple[str, EntitlementSet, datetime]] = []

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        self.asked.append((question, entitlement, now))
        return TypedResult(records=self.records, source="knowledge", fetched_at=NOW.isoformat())


class Kept:
    """A `RequestRecorder` keeping what it was handed."""

    def __init__(self) -> None:
        self.seen: list[Finished] = []

    async def finished(self, request: Finished) -> None:
        self.seen.append(request)


@dataclasses.dataclass
class Run:
    """One run of the lane and everything it left behind."""

    answered: Answered | None
    finished: Finished
    sent: list[DriverRequest]
    attempts: Log
    sink: Sink
    search: Passages
    logged: Sequence[Mapping[str, Any]]
    raised: BaseException | None = None


def completion(text: str = REPLY, finish_reason: str = "stop") -> Completion:
    return Completion(text=text, finish_reason=finish_reason, input_tokens=321, output_tokens=45)


def ask(
    question: str = QUESTION,
    *,
    search: Passages | None = None,
    reply: Completion | BaseException | None = None,
    script: Sequence[Completion | BaseException] = (),
    with_model: bool = True,
    entitlement: EntitlementSet = CALLER,
    rules: Sequence[FastPathRule] = (HOURS,),
    rows: Rows | None = None,
    hints: tuple[str, ...] = (),
    follow_up: FollowUp | None = None,
) -> Run:
    """The lane, with a model step whose model is a real executor over a recording transport."""
    transport = Scripted(*script) if script else Scripted(completion() if reply is None else reply)
    calls, attempts = executor(Ladder((rung("anthropic"),)), {"anthropic": transport})
    found = search if search is not None else Passages(VISIBLE, WITHHELD)
    sink = Sink()
    kept = Kept()
    origin = Origin(
        trace_id="t-model-lane",
        principal=Principal(
            id=entitlement.principal_id,
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name="Lane asker",
        ),
        channel=Channel.CONSOLE,
    )
    answered: Answered | None = None
    raised: BaseException | None = None
    with capture_logs() as logged:
        try:
            answered = asyncio.run(
                answer_lane(
                    question,
                    origin=origin,
                    recorders=(kept,),
                    rules=rules,
                    readers=readers_for(Rows(ACME) if rows is None else rows),
                    entitlement=entitlement,
                    policies={"client": CLIENTS.policy()},
                    reachable_sources=("laravel",),
                    sink=sink,
                    now=NOW,
                    clock=lambda: NOW,
                    model=ModelLane(
                        search=found,
                        model=calls,
                        hints=FixedHints(hints) if hints else None,
                        follow_up=follow_up,
                    )
                    if with_model
                    else None,
                )
            )
        except ProviderUnavailable as exc:
            raised = exc
    (finished,) = kept.seen
    return Run(
        answered=answered,
        finished=finished,
        sent=transport.sent,
        attempts=attempts,
        sink=sink,
        search=found,
        logged=logged,
        raised=raised,
    )


def events(answered: Answered | None) -> list[tuple[str, str]]:
    assert answered is not None
    return [(one.event, one.data) for one in decode(frames(answered.frames))]


def prompt(run: Run) -> str:
    return "\n".join(message.content for request in run.sent for message in request.messages)


# --- the model answers --------------------------------------------------------------------------


def test_a_question_no_rule_answers_is_answered_by_a_model_citing_before_its_prose() -> None:
    """**The positive case.** A question no fast-path rule matches reaches the model step, the
    passage the caller may read is shown to the model, the model's reply is the prose, the
    citations are the readable passage's and arrive before the prose, and the stream closes.

    Delete this and a lane that abstains on every question passes every refusal in this file, and
    a fresh install with a provider still answers nothing."""
    run = ask()

    assert run.answered is not None and run.answered.composed is not None
    assert len(run.sent) == 1
    assert "Annual leave is twenty five days a year." in prompt(run)
    seen = events(run.answered)
    names = [name for name, _ in seen]
    assert names.index("citation") < names.index("text")
    assert names[-1] == "done"
    assert any(data.startswith(REPLY) for name, data in seen if name == "text")
    cited = {one.record_id for one in run.answered.composed.citations}
    assert cited == {VISIBLE.id}


def test_the_steps_of_a_model_answer_are_a_lookup_a_reading_and_composing() -> None:
    """The progress steps a person watches, exactly: nothing is read for the fast path first, and
    the composing step appears only once a model has been asked, which a withheld passage and an
    absent one never reach.

    Delete this and a composing step can go out before the search has found anything, which tells
    a watcher that something survived before the answer says whether it did."""
    steps = [data for name, data in events(ask().answered) if name == Event.STEP.value]

    assert steps == [
        step_label(one)
        for one in (
            Progress.UNDERSTANDING,
            Progress.CHECKING,
            Progress.LOOKING_UP,
            Progress.READING,
            Progress.COMPOSING,
        )
    ]


def test_a_model_answer_is_recorded_under_the_answer_lane_with_the_providers_tokens() -> None:
    """The ledger row says the request spent the answer lane's budget and carries the provider's
    own token counts from the meter the call was made on, and the passage search counts as the
    tool call it was.

    Delete this and every model answer is filed under the fast lane with no tokens, so the usage
    screen reports nothing for the traffic that costs the most."""
    run = ask()

    assert run.finished.lane is Lane.ANSWER
    assert run.finished.tool_calls == 1
    usage = run.finished.model_usage
    assert usage is not None
    assert (usage.calls, usage.tokens_in, usage.tokens_out) == (1, 321, 45)
    assert request_telemetry_of(run.finished).lane is Lane.ANSWER


def test_the_call_is_made_on_the_answer_lane_at_the_pinned_length_and_the_request_trace() -> None:
    """The executor is told the lane, handed the output cap `brain.gate.effort` pins for it, and
    the attempt rows carry the request's own trace, so the chain a question walked is joined to
    the question.

    Delete this and the call can be made with no cap, which on a chat completions provider is a
    bill bounded only by the model's window, or under a trace nothing else in the request shares."""
    run = ask()

    (request,) = run.sent
    assert request.max_output_tokens == settings_for(Lane.ANSWER).max_output_tokens
    assert [row["trace_id"] for row in run.attempts.rows.values()] == ["t-model-lane"]


def test_a_question_a_rule_answers_asks_no_model_and_stays_on_the_fast_lane() -> None:
    """With a model step present, a question a fast-path rule answers is still answered by the rule
    alone: no passage search, no model call, and the fast lane on the ledger row.

    Delete this and the model step can run in front of the fast path, which costs a model call for
    every question the product promised to answer with none."""
    run = ask("hours left on Acme")

    assert run.answered is not None and run.answered.composed is not None
    assert run.sent == []
    assert run.search.asked == []
    assert run.finished.lane is Lane.FAST
    assert run.finished.model_usage is None


def test_a_question_a_rule_matched_stays_the_fast_lanes_whatever_its_read_found() -> None:
    """**The model step takes only a question no rule matched.** A rule that matched and found
    two records under one name abstains exactly as the lane with no model step abstains on it,
    frame for frame, and neither the passage search nor a model is asked.

    Delete this and a matched rule's read can be handed on to a model when it found two records,
    and the different steps and answer that follow tell the asker a second record exists."""
    both = Rows(ACME, OTHER)
    with_model = ask("hours left on Acme", rows=both)
    without = ask("hours left on Acme", rows=Rows(ACME, OTHER), with_model=False)

    assert with_model.answered is not None and without.answered is not None
    assert with_model.answered.frames == without.answered.frames
    assert with_model.answered.abstention is not None
    assert with_model.answered.abstention.reason is AbstentionReason.NOTHING_RETRIEVED
    assert with_model.search.asked == []
    assert with_model.sent == []
    assert with_model.finished.lane is Lane.FAST


def test_a_rule_for_a_source_nothing_connects_is_still_nothing_connected_with_a_model_step() -> (
    None
):
    """A question whose wording matches a rule for a source this install does not read is told
    nothing is connected before anything is read, and the model step does not take it over.

    Delete this and a question about a system nobody connected is answered from documents by a
    model, and the Questions and gaps screen never hears of the missing source."""
    run = ask("hours left on Acme", rules=(UNREAD,))

    assert run.answered is not None and run.answered.abstention is not None
    assert run.answered.abstention.reason is AbstentionReason.NOTHING_CONNECTED
    assert run.answered.abstention.missing_source == "xero"
    assert NOTHING_CONNECTED_TEXT in next(d for n, d in events(run.answered) if n == "text")
    assert (run.search.asked, run.sent) == ([], [])


def test_whether_no_rule_matches_ignores_what_this_install_connects() -> None:
    """A rule counts as matching whether or not its source is read here, and so do two rules at
    once; only wording no rule has counts as no rule matching.

    Delete this and a question two rules match, or one only an unconnected rule matches, can be
    handed to a model, which a configuration change would then silently reroute."""
    twin = HOURS.model_copy(update={"rule_id": "client_hours_twin"})

    assert no_rule_matches(QUESTION, (HOURS, UNREAD)) is True
    assert no_rule_matches("hours left on Acme", (HOURS,)) is False
    assert no_rule_matches("hours left on Acme", (UNREAD,)) is False
    assert no_rule_matches("hours left on Acme", (HOURS, twin)) is False
    assert no_rule_matches("hours left on Acme", ()) is True


def test_without_a_model_step_a_question_no_rule_answers_abstains_as_it_always_did() -> None:
    """The lane handed no model is the lane that existed before it could be handed one.

    Delete this and a caller that passes no model, the golden corpus among them, silently changes
    what it measures."""
    run = ask(with_model=False)

    assert run.answered is not None and run.answered.abstention is not None
    assert run.answered.abstention.reason is AbstentionReason.NOTHING_RETRIEVED
    assert run.search.asked == []
    assert run.finished.lane is Lane.FAST


# --- what a model is shown ----------------------------------------------------------------------


def test_a_withheld_passage_and_a_locked_field_reach_no_prompt_attempt_trace_row_frame_or_log() -> (
    None
):
    """**The property this module exists for, with the first wall breached on purpose.** The
    search hands back a passage of a document the caller may not read, and a readable passage whose
    title they may not read. Neither the withheld passage's id, reference, title, section or body
    nor the locked title reaches the prompt the provider was sent, the attempt rows, the trace
    sink's payload or trace, the ledger row, the frames the person receives, or any log line.

    The positive half is asserted beside it, so the absences are not the absence of everything:
    the readable passage's body is in the prompt and its citation is in the frames.

    Delete this and the prompt can be built from what the search returned rather than from what
    the redactor let through, and the first model answer on a real install is the leak."""
    run = ask()
    assert run.answered is not None and run.answered.composed is not None

    (emitted,) = run.sink.emitted
    surfaces = {
        "prompt": prompt(run),
        "attempt rows": repr(run.attempts.rows),
        "trace sink": emitted[1].model_dump_json() + emitted[2].model_dump_json(),
        "ledger row": repr(request_telemetry_of(run.finished)),
        "frames": frames(run.answered.frames),
        "log": repr(run.logged),
    }
    for where, text in surfaces.items():
        for value in PLANTED:
            assert value not in text, f"{value} reached the {where}"

    assert VISIBLE.document in surfaces["prompt"]
    assert VISIBLE.id in surfaces["frames"]


def test_a_withheld_passage_and_an_absent_one_are_one_event_and_neither_asks_a_model() -> None:
    """**DENIED and ABSENT, through the model step.** A search that found only a passage the
    caller may not read and a search that found nothing produce byte-identical frames, the same
    abstention reason, no model call and the fast lane on the ledger row.

    Positive sibling:
    `test_a_question_no_rule_answers_is_answered_by_a_model_citing_before_its_prose`.

    Delete this and asking a model about a withheld passage is observable as a different answer,
    a different step or a different ledger lane, and a person can map what exists by asking."""
    withheld = ask(search=Passages(WITHHELD))
    absent = ask(search=Passages())

    assert withheld.answered is not None and absent.answered is not None
    assert withheld.answered.frames == absent.answered.frames
    assert withheld.answered.abstention == absent.answered.abstention
    assert withheld.answered.abstention is not None
    assert withheld.answered.abstention.reason is AbstentionReason.NOTHING_RETRIEVED
    assert NOT_FOUND_TEXT in next(d for n, d in events(withheld.answered) if n == "text")
    assert withheld.sent == absent.sent == []
    assert withheld.finished.lane is absent.finished.lane is Lane.FAST
    steps = [data for name, data in events(withheld.answered) if name == Event.STEP.value]
    assert step_label(Progress.COMPOSING) not in steps


def test_the_model_is_given_no_address_it_could_cite() -> None:
    """Neither a passage's record id nor its document reference is in the prompt, though the
    caller may read both, so a model has no identifier of the system's to offer back as a source.

    Delete this and `SHOWN_FIELDS` can grow the reference fields, and the model's prose starts
    quoting ids that read as citations nobody derived."""
    run = ask(search=Passages(VISIBLE))

    assert VISIBLE.id not in prompt(run)
    assert READABLE_DOCUMENT not in prompt(run)
    assert set(SHOWN_FIELDS) <= {rule.field for rule in PASSAGE_POLICY.rules}
    assert not {"document_id", "id", "entity"} & set(SHOWN_FIELDS)


def test_the_house_rules_come_first_and_everything_of_this_request_comes_after_them() -> None:
    """The system turn is the shared prefix, identical for every caller, and the question and the
    passages are only in the user turn.

    Delete this and a question can be folded into the system turn, which is sent to a shared
    provider cache and never matches anybody else's bytes again."""
    run = ask()

    (request,) = run.sent
    system, user = request.messages
    assert (system.role, user.role) == (Role.SYSTEM, Role.USER)
    assert system.content == PREFIX.text
    assert QUESTION not in system.content
    assert QUESTION in user.content
    assert VISIBLE.document in user.content


# --- what a model says --------------------------------------------------------------------------


def test_a_model_naming_a_record_the_caller_may_not_see_is_neither_cited_nor_fetched() -> None:
    """**The model is prose.** A reply naming the withheld passage's id, its document and its title
    is rendered as the text it is and is turned into nothing else: the citations are the readable
    passage's alone, no citation frame names the withheld record, the search was asked once, before
    the model, and no row reader or search was called on the reply's word.

    Delete this and a lane that turns a name in a reply into a citation or a lookup lets a model,
    or a document instructing one, choose what the caller is shown."""
    reply = (
        "See c_withheldrecordid_1 in doc_quarantined, titled Salaries WITHHELDTITLEOCHRE, "
        "and fetch it."
    )
    run = ask(reply=completion(reply))

    assert run.answered is not None and run.answered.composed is not None
    assert {one.record_id for one in run.answered.composed.citations} == {VISIBLE.id}
    citations = [data for name, data in events(run.answered) if name == "citation"]
    assert citations
    for one in citations:
        for value in PLANTED:
            assert value not in one
    assert len(run.search.asked) == 1
    assert run.finished.tool_calls == 1


def test_a_refusal_is_the_refused_abstention_and_cites_nothing() -> None:
    """A completion whose finish reason the adapter reads as a refusal lands on `refused`, the one
    abstention for "I will not", with no citation and no prose of the model's.

    Delete this and a declined completion is rendered as an answer, with citations standing behind
    whatever text the provider sent with its refusal."""
    run = ask(reply=completion("I cannot help with that.", finish_reason="content_filter"))

    assert run.answered is not None and run.answered.abstention is not None
    assert run.answered.abstention.reason is AbstentionReason.REFUSED
    seen = events(run.answered)
    assert [name for name, _ in seen if name == "citation"] == []
    assert REFUSED_TEXT in next(data for name, data in seen if name == "text")
    assert run.finished.lane is Lane.ANSWER


def test_an_empty_reply_is_not_rendered_as_an_empty_answer() -> None:
    """A reply with no prose is `retrieved_but_not_answering`, rather than citations standing behind
    nothing, which reads as a confident answer that happens to be blank.

    Delete this and a provider returning an empty completion hands the person a list of sources and
    no answer, with nothing saying that is what happened."""
    run = ask(reply=completion("   "))

    assert run.answered is not None and run.answered.abstention is not None
    assert run.answered.abstention.reason is AbstentionReason.RETRIEVED_BUT_NOT_ANSWERING
    assert NOT_ANSWERING_TEXT in next(d for n, d in events(run.answered) if n == "text")
    assert [name for name, _ in events(run.answered) if name == "citation"] == []


def test_a_model_that_cannot_be_reached_is_degraded_and_the_request_is_still_recorded() -> None:
    """Every rung failing raises `ProviderUnavailable`, which is `Degraded` and says the model could
    not be reached rather than substituting anything, and the request is finished once, with no
    outcome and the attempts it made on the answer lane.

    Delete this and a provider outage can be turned into an abstention, which tells a person there
    was nothing to find when there was nothing to read it with."""
    from brain.models.adapter import TransportStatusError

    run = ask(reply=TransportStatusError(503))

    assert run.answered is None
    assert isinstance(run.raised, ProviderUnavailable)
    assert run.finished.outcome is None
    assert run.finished.lane is Lane.ANSWER


# --- the bounds ---------------------------------------------------------------------------------


def test_the_largest_prompt_the_lane_can_build_fits_the_answer_tier_by_its_bytes() -> None:
    """**Measured, not estimated.** The largest question the answer route admits, the most
    passages the lane shows, the most of a follow-up's earlier questions it repeats (M9.2.3) and
    the most of the asker's hints it shows (M16.6.3), every character of each four bytes wide,
    give a prompt whose UTF-8 length fits inside the answer tier's escalation headroom, so
    `classify_tier` keeps it on that tier and no tokeniser can find it too long.

    Delete this and a cap can be raised until a legitimate question is refused by the provider as
    too long, which the chain reads as a 400 and stops on."""
    wide = "\N{GRINNING FACE}"
    passage = {
        "entity": KNOWLEDGE_ENTITY,
        "id": "c_wide",
        **dict.fromkeys(SHOWN_FIELDS, wide * 10_000),
    }
    payload = ChannelPayload(records=tuple(dict(passage) for _ in range(PASSAGES_SHOWN * 2)))
    earlier = [wide * (EARLIER_CHARS * 2)] * (EARLIER_SHOWN * 2)
    hints = tuple(wide * 4_000 for _ in range(MAX_HINTS_SHOWN * 3))
    messages = messages_of(
        prompt_for(wide * (MAX_QUESTION_CHARS * 2), shown(payload), (), hints, earlier=earlier)
    )
    tier = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier

    assert prompt_bytes(messages) <= ESCALATION_HEADROOM * TIER_CONTEXT_WINDOW[tier]
    assert tier_for(messages) is tier is DEFAULT_TIER


def test_a_follow_up_s_prompt_repeats_the_newest_earlier_questions_each_cut_to_its_length() -> None:
    """The prompt names the person's newest `EARLIER_SHOWN` earlier questions, oldest first, each
    cut to `EARLIER_CHARS`, before the question; a question on its own names none (M9.2.3).

    Delete this and the cap the byte bound above is measured with can stop being the cap the
    prompt applies, or a follow-up can lose the words that say what "it" was."""
    earlier = [f"question {number} " + "x" * (EARLIER_CHARS * 2) for number in range(5)]
    text = "\n\n".join(prompt_for("and who signs it", ChannelPayload(), earlier=earlier).variable)
    listed = text.split("Earlier in this conversation the person asked:\n", 1)[1]
    lines = listed.split("\n\n", 1)[0].split("\n")
    assert lines == [f"- {one[:EARLIER_CHARS]}" for one in earlier[-EARLIER_SHOWN:]]
    assert text.index("Earlier in this conversation") < text.index("Question:")
    alone = "\n\n".join(prompt_for("and who signs it", ChannelPayload()).variable)
    assert "Earlier in this conversation" not in alone


def test_the_largest_prompt_with_every_hint_shown_still_fits_the_answer_tier() -> None:
    """The same measurement with the most hints a prompt carries, each longer than a hint may be:
    they are cut to `HINT_CHARS` and counted to `MAX_HINTS_SHOWN`, so the ceiling holds.

    Delete this and a person's edited memory of four thousand characters, or a recall returning
    more than it should, can push a legitimate question past what the provider accepts."""
    wide = "\N{GRINNING FACE}"
    passage = {
        "entity": KNOWLEDGE_ENTITY,
        "id": "c_wide",
        **dict.fromkeys(SHOWN_FIELDS, wide * 10_000),
    }
    payload = ChannelPayload(records=tuple(dict(passage) for _ in range(PASSAGES_SHOWN * 2)))
    hints = tuple(wide * 4_000 for _ in range(MAX_HINTS_SHOWN * 3))
    layout = prompt_for(wide * (MAX_QUESTION_CHARS * 2), shown(payload), (), hints)
    messages = messages_of(layout)
    tier = classify_tier(RoutingRequest(lane=Lane.ANSWER)).tier

    assert hints_block(hints).count("\n- ") == MAX_HINTS_SHOWN
    assert prompt_bytes(messages) <= ESCALATION_HEADROOM * TIER_CONTEXT_WINDOW[tier]
    assert tier_for(messages) is tier is DEFAULT_TIER


def test_the_askers_hints_are_shown_after_the_question_and_nothing_cites_one() -> None:
    """**What the asker said about themselves reaches the model as a hint and never as a source
    (M16.6.3).** The hint is in the request's own turn, after the question and before the passages,
    under the heading that says what it is; the shared prefix every caller's prompt starts with is
    byte for byte what it was; the attempt row names the category; and the answer cites the passage
    and nothing else.

    Delete this and a memory could be put in the payload, where a citation could name it, or in the
    shared region, where it would change the cached prefix every other caller shares."""
    hint = "I prefer the figure first HINTVERMILION"
    run = ask(hints=(hint,))

    [request] = run.sent
    system, user = request.messages
    assert system.content == PREFIX.text
    assert hint not in system.content
    assert user.content.index("Question:") < user.content.index(HINTS_HEADING)
    assert user.content.index(f"- {hint}") < user.content.index("Passages:")
    assert run.answered is not None and run.answered.composed is not None
    assert {one.record_id for one in run.answered.composed.citations} == {VISIBLE.id}
    assert "HINTVERMILION" not in "".join(run.answered.frames)
    [categories] = [row["categories"] for row in run.attempts.rows.values()]
    assert categories == ("document_passages", "memory_hints", "question")

    plain = ask()
    [unhinted] = plain.sent
    assert HINTS_HEADING not in unhinted.messages[1].content
    [bare] = [row["categories"] for row in plain.attempts.rows.values()]
    assert bare == ("document_passages", "question")


def test_a_search_returning_more_than_asked_for_is_cut_before_the_model_and_the_citations() -> None:
    """The lane shows at most `PASSAGES_SHOWN` passages whatever a search returns, and cites only
    those, keeping the locks of the passages it kept.

    Delete this and a search that ignores its limit makes the byte bound above a claim about a
    prompt the lane no longer builds."""
    many = tuple(
        VISIBLE.model_copy(update={"id": f"c_handbook_{number}"})
        for number in range(PASSAGES_SHOWN + 3)
    )
    run = ask(search=Passages(*many))

    assert run.answered is not None and run.answered.composed is not None
    cited = {one.record_id for one in run.answered.composed.citations}
    assert cited == {f"c_handbook_{number}" for number in range(PASSAGES_SHOWN)}
    assert prompt(run).count("Passage ") == PASSAGES_SHOWN
    kept = run.answered.composed.payload
    assert {one.record_id for one in kept.locked} == cited
    assert kept.truncated is True


def test_the_search_tool_asks_for_the_passages_the_lane_shows_at_the_callers_reach() -> None:
    """The adapter over the registered handler asks for exactly `PASSAGES_SHOWN`, at the reach and
    instant it was given, with the question cut to what the tool binds.

    Delete this and the handler's default page is what the lane reads, which is not the number the
    byte bound is computed from, or a long question is refused by the tool's own validation."""
    seen: list[tuple[Any, EntitlementSet, datetime | None]] = []

    async def handler(
        request: Any, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[KnowledgePassage]:
        seen.append((request, entitlement, now))
        return TypedResult(records=())

    asyncio.run(
        DocumentSearchTool(handler=handler).passages("x" * 5_000, entitlement=CALLER, now=NOW)
    )

    ((request, reach, at),) = seen
    assert request.limit == PASSAGES_SHOWN
    assert request.question == "x" * QUESTION_CHARS
    assert (reach, at) == (CALLER, NOW)


def departmental(department: str) -> EntitlementSet:
    """The plane and every passage field over one department, as a pack assignment grants them."""
    return EntitlementSet(
        principal_id="p_joiner",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.department(department))
            for one in (
                "read:knowledge",
                "read:knowledge.document",
                "read:knowledge.title",
                "read:knowledge.section",
                "read:knowledge.updated_at",
            )
        ),
    )


#: A passage of a web department document, carrying the place its item was stored at (M7.7.1).
WEB_PASSAGE = KnowledgePassage(
    entity=KNOWLEDGE_ENTITY,
    id="c_webhandover_1",
    document_id="upload.webhandover",
    title="Site handover",
    document="A site is handed over only after the client signs the TEALHANDOVER checklist.",
    updated_at="2999-01-01T00:00:00+00:00",
    department="web",
    visibility="department",
    owner_id="u_uploader",
)


def test_a_department_field_grant_reads_its_departments_passage_and_a_model_is_asked() -> None:
    """**The repair of a stated limit** (M7.7.1). A caller holding the plane and every passage
    field over their own department, which is how a pack assignment grants them, is shown a
    passage of that department's document, because the passage carries the department its item
    was stored with and the scope has something to test. The model is asked, and the words reach
    it; the department, visibility and owner do not, because the prompt shows only `SHOWN_FIELDS`.

    Delete this and a passage can lose its department again, every department reader is withheld
    every passage, and the sibling below is satisfied by a lane that reads nothing. See
    `A_DEPARTMENT_SCOPED_FIELD_GRANT_READS_ITS_OWN_DEPARTMENTS_PASSAGES`."""
    run = ask(search=Passages(WEB_PASSAGE), entitlement=departmental("web"))

    assert run.answered is not None and run.answered.abstention is None
    (request,) = run.sent
    user = "\n".join(message.content for message in request.messages)
    assert "TEALHANDOVER" in user
    assert "u_uploader" not in user
    assert A_DEPARTMENT_SCOPED_FIELD_GRANT_READS_ITS_OWN_DEPARTMENTS_PASSAGES


def test_a_field_grant_over_one_department_reads_no_passage_of_another_and_asks_no_model() -> None:
    """The same passage, asked by somebody whose grants are over another department: withheld,
    the nothing-retrieved abstention, and no model called, which is exactly what a passage that
    never existed produces (DENIED and ABSENT are one event).

    Delete this and the positive case above is satisfied by a passage policy that ignores the
    department, so a grant over sales reads web's bodies."""
    run = ask(search=Passages(WEB_PASSAGE), entitlement=departmental("sales"))
    nothing = ask(search=Passages(), entitlement=departmental("sales"))

    assert run.answered is not None and run.answered.abstention is not None
    assert run.answered.abstention.reason is AbstentionReason.NOTHING_RETRIEVED
    assert run.sent == []
    assert nothing.answered is not None and nothing.answered.abstention is not None
    assert events(run.answered) == events(nothing.answered)


def _placed(visibility: str, *, department: str | None = None, owner: str = "p_joiner") -> Any:
    """`WEB_PASSAGE` stored at another level, as a company or personal item's passage carries it."""
    return WEB_PASSAGE.model_copy(
        update={"department": department, "visibility": visibility, "owner_id": owner}
    )


def _words_read(passage: KnowledgePassage, entitlement: EntitlementSet) -> bool:
    """Whether `redact_passages` leaves this reader the passage's words."""
    kept = redact_passages(
        TypedResult[KnowledgePassage](records=(passage,), source="knowledge.search"),
        entitlement=entitlement,
        now=None,
    ).payload.records
    return bool(kept) and bool(kept[0].get("document"))


def test_a_department_text_right_reads_company_passages_and_the_readers_own() -> None:
    """**The owner's decision 106 (2026-09-28): company-wide means everyone, and one's own
    personal upload is one's own.** A reader whose passage fields are granted over one department
    is retrieved a company-wide passage and their own personal one, and until 2026-09-29 was shown
    neither's words, because neither names a department for the grant to test.

    Delete this and a department reader is found company-wide documents and told nothing from
    them, which is the owner's install answering "I could not find that" about his own company
    policies."""
    reader = departmental("web")
    assert _words_read(WEB_PASSAGE, reader)
    assert _words_read(_placed("company"), reader)
    assert _words_read(_placed("personal", owner="p_joiner"), reader)
    assert A_DEPARTMENT_TEXT_RIGHT_READS_COMPANY_AND_OWN_PERSONAL_PASSAGES


def test_the_widening_reads_no_other_department_and_nobody_elses_personal_passage() -> None:
    """The sibling: the same reader is still withheld another department's passage and another
    person's personal one, even handed straight to the redactor. Delete this and the widening can
    become "any holding of the capability reads every passage", which reads every department's
    bodies."""
    reader = departmental("web")
    assert not _words_read(_placed("department", department="sales"), reader)
    assert not _words_read(_placed("personal", owner="p_someone_else"), reader)


def test_a_mixed_result_keeps_retrievals_order_and_each_half_its_own_redaction() -> None:
    """A result holding a department passage the reader may not read, a company-wide one and their
    own personal one comes back in retrieval's order with the two they may read, and the trace
    records the refusal under the reader's own reach hash. Delete this and joining the two halves
    can reorder an answer's passages, drop a lock or name a widened reach in the audit trace."""
    reader = departmental("web")
    company = _placed("company").model_copy(update={"id": "c_company"})
    mine = _placed("personal").model_copy(update={"id": "c_mine"})
    other = _placed("department", department="sales").model_copy(update={"id": "c_sales"})
    redacted = redact_passages(
        TypedResult[KnowledgePassage](records=(company, other, mine), source="knowledge.search"),
        entitlement=reader,
        now=None,
    )
    kept = [(one["id"], bool(one.get("document"))) for one in redacted.payload.records]
    assert kept == [("c_company", True), ("c_mine", True)]
    assert redacted.trace.ent_hash == reader.ent_hash()
    refused = {one.record_id for one in redacted.trace.redactions}
    assert redacted.trace.dropped or "c_sales" in refused


def test_a_grant_narrowed_by_anything_but_a_department_is_not_widened() -> None:
    """A field grant scoped to a department and something else is not a department's right to
    read, and the decision says nothing about it: there is nothing to widen, and an unrestricted
    grant already reads every passage. Delete this and a grant narrowed to one kind of document
    reads every company-wide passage of every kind."""
    narrowed = EntitlementSet(
        principal_id="p_joiner",
        grants=(
            Grant(
                capability=Capability(value="read:knowledge.document"),
                scope=Scope(
                    clauses=(
                        Clause(field="department", op=Op.EQ, value="web"),
                        Clause(field="kind", op=Op.EQ, value="sop"),
                    )
                ),
            ),
        ),
    )
    everywhere = EntitlementSet(
        principal_id="p_joiner",
        grants=(Grant(capability=Capability(value="read:knowledge.document"), scope=Scope()),),
    )
    assert passage_reach(narrowed) is None
    assert passage_reach(everywhere) is None
    assert not _words_read(_placed("company"), narrowed)
    assert _words_read(_placed("company"), everywhere)


def test_the_passage_policy_asks_for_the_capabilities_a_joiner_is_already_given() -> None:
    """The passage fields a joiner's starter pack names are governed by exactly the capabilities
    that pack grants, so the policy asks for nothing the product never grants.

    Delete this and the policy can name a capability nobody is granted, and every passage is
    withheld from everybody, which reads as an empty knowledge base."""
    granted = {one.value for one in STARTER_PACK.capabilities}
    required = {rule.field: rule.required_capability.value for rule in PASSAGE_POLICY.rules}

    for field in ("document", "title", "updated_at"):
        assert required[field] in granted, field


def test_the_prompt_says_nothing_about_a_field_the_redactor_removed() -> None:
    """A passage whose title was withheld is shown without a title line and without a line saying
    one was withheld, because a model told that a field exists and is hidden reasons about it.

    Delete this and a renderer that prints every shown field name with an empty value tells the
    model which fields were withheld."""
    record = {"entity": KNOWLEDGE_ENTITY, "id": "c_1", "document": "Words."}
    user = messages_of(prompt_for("q", ChannelPayload(records=(record,))))[1].content

    assert "title" not in user
    assert "Words." in user


def test_a_trace_emitted_for_a_model_answer_names_the_passage_policy_and_the_reach() -> None:
    """The trace a model answer leaves says which policy and which reach it was computed at, which
    is what an auditor opening it needs and all the payload-free half can say.

    Delete this and a model answer's trace can carry the fast lane's client policy, and an auditor
    reads the wrong epoch for a passage answer."""
    run = ask()

    ((_, _, trace),) = run.sink.emitted
    assert isinstance(trace, RedactionTrace)
    assert trace.policy_epoch == PASSAGE_POLICY.epoch()
    assert trace.ent_hash == CALLER.ent_hash()


# --- M5.4.1 and M5.6.4 --------------------------------------------------------------------------


def test_a_refusal_the_provider_reports_as_an_error_is_the_refused_abstention() -> None:
    """M5.4.1: a model's content refusal is recorded and answered once through abstention, never
    tried on another model. A provider that declines with an error body arrives as a failure the
    chain stopped on, marked refused, and lands on the same `refused` abstention as a declining
    reply, with the attempt row saying `refused`.

    Delete this and a refusal reported as an error is shown as a model nobody could reach."""
    from brain.models.adapter import ContentPolicyRefusedError

    run = ask(reply=ContentPolicyRefusedError(status=400))

    assert run.raised is None
    assert run.answered is not None and run.answered.abstention is not None
    assert run.answered.abstention.reason is AbstentionReason.REFUSED
    assert len(run.sent) == 1
    assert run.attempts.outcomes() == [("main-0", 0, "refused")]


# --- M15.4.1 -----------------------------------------------------------------------------------


def _many(count: int) -> Passages:
    return Passages(
        *(VISIBLE.model_copy(update={"id": f"c_handbook_{number}"}) for number in range(count))
    )


def test_a_prompt_too_long_for_every_model_is_asked_again_with_fewer_passages_and_says_so() -> None:
    """The largest model refuses the prompt as too long twice: the lane asks again with half the
    passages, then half again, and answers from the one it could send, citing that one alone and
    saying it drew on one of the six found (M15.4.1).

    Delete this and a question whose passages are longer than a model reads is answered with the
    provider's failure, or from fewer passages with nothing said, which is the silent truncation
    `A_REQUEST_TOO_LONG_FOR_EVERY_MODEL_IS_ANSWERED_FROM_FEWER_PASSAGES_AND_SAYS_SO` forbids."""
    from brain.gate.model_lane import TRIMMED_TEXT
    from brain.models.adapter import ContextWindowExceededError

    too_long = ContextWindowExceededError("context_length_exceeded")
    run = ask(search=_many(PASSAGES_SHOWN), script=(too_long, too_long, completion()))

    assert run.raised is None
    assert run.answered is not None and run.answered.composed is not None
    shown_per_request = [
        "\n".join(message.content for message in request.messages).count("Passage ")
        for request in run.sent
    ]
    assert shown_per_request == [PASSAGES_SHOWN, PASSAGES_SHOWN // 2, 1]
    assert {one.record_id for one in run.answered.composed.citations} == {"c_handbook_0"}
    said = TRIMMED_TEXT.format(shown=1, found=PASSAGES_SHOWN)
    assert run.answered.text is not None and said in run.answered.text


def test_the_passages_counted_as_found_are_only_those_the_reader_could_read() -> None:
    """Four readable passages and two the reader's grants withhold, refused as too long once: the
    answer says it drew on two of the four found, never of six. DENIED and ABSENT read the same,
    and a count that included the withheld two would tell the reader two things exist that they
    may not see. Delete this and the sentence can count what the search found rather than what
    survived redaction, which is a count of hidden items by subtraction."""
    from brain.gate.model_lane import TRIMMED_TEXT
    from brain.models.adapter import ContextWindowExceededError

    readable = tuple(
        VISIBLE.model_copy(update={"id": f"c_handbook_{number}"}) for number in range(4)
    )
    withheld = tuple(
        WITHHELD.model_copy(update={"id": f"c_withheldrecordid_{number}"}) for number in range(2)
    )
    run = ask(
        search=Passages(*withheld, *readable),
        script=(ContextWindowExceededError("context_length_exceeded"), completion()),
    )

    assert run.answered is not None and run.answered.text is not None
    assert TRIMMED_TEXT.format(shown=2, found=4) in run.answered.text
    assert "of the 6 passages" not in run.answered.text


def test_an_answer_that_fit_says_nothing_about_fewer_passages() -> None:
    """The positive sibling: a prompt the model read first time is answered from every passage
    and the answer says nothing about drawing on fewer. Delete this and the sentence can be added
    to every answer, which would make it mean nothing."""
    run = ask(search=_many(3))

    assert run.answered is not None and run.answered.text is not None
    assert "passages found for you" not in run.answered.text
    assert len(run.sent) == 1


def test_one_passage_too_long_and_any_other_failure_are_not_asked_again() -> None:
    """A single passage the model still cannot read, and a provider failing for any other reason,
    are the provider's failure after one request: there is nothing fewer to send, and a failure
    that is not about length is not cured by sending less. Delete this and the lane can loop on a
    failure that trimming cannot fix, paying for each attempt."""
    from brain.models.adapter import ContextWindowExceededError, TransportStatusError

    alone = ask(search=_many(1), script=(ContextWindowExceededError("context_length_exceeded"),))
    down = ask(search=_many(PASSAGES_SHOWN), script=(TransportStatusError(503),))

    for run in (alone, down):
        assert isinstance(run.raised, ProviderUnavailable)
        assert len(run.sent) == 1


def test_the_attempt_row_names_the_categories_of_data_the_prompt_carried() -> None:
    """M5.6.4: the question and the passages, as `brain.models.disclosure` names them.

    Delete this and the provider register counts calls with nothing said about what they sent."""
    run = ask()

    categories = [row["categories"] for row in run.attempts.rows.values()]
    assert categories == [("document_passages", "question")]


# --- a file attached to the thread (M12.3.6) ----------------------------------------------------


def test_a_file_attached_to_the_thread_is_read_by_its_tool_at_the_run_reach_and_shown() -> None:
    """**AN_ATTACHED_FILE_IS_READ_BY_ITS_TOOL_AT_THE_RUN_S_REACH.** The search finds nothing, and
    the passage of the file the person attached is read through the attachment reader with the
    reach the answer runs at, passes the redactor, reaches the model and is cited. Delete this and
    a question about the file someone attached is answered from a search that never reads it."""
    read: list[tuple[str, EntitlementSet]] = []

    async def attached(
        attachment_id: str, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[KnowledgePassage]:
        del now
        read.append((attachment_id, entitlement))
        return TypedResult(records=(VISIBLE,), source="knowledge", fetched_at=NOW.isoformat())

    run = ask(
        "summarise the file I attached",
        search=Passages(),
        follow_up=FollowUp(attached=(READABLE_DOCUMENT,), read_attached=attached),
    )

    assert read == [(READABLE_DOCUMENT, CALLER)]
    assert run.answered is not None and run.answered.composed is not None
    assert "Annual leave is twenty five days a year." in prompt(run)
    assert {one.record_id for one in run.answered.composed.citations} == {VISIBLE.id}


def test_an_attached_file_the_reach_may_not_read_contributes_nothing() -> None:
    """The positive test's sibling: the attachment reader handed back a passage the caller may not
    read, and the redactor withholds it as it withholds any other, so nothing reaches a model.
    Delete this and an attachment could be the one passage that skips the redactor."""

    async def attached(
        attachment_id: str, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[KnowledgePassage]:
        del attachment_id, entitlement, now
        return TypedResult(records=(WITHHELD,), source="knowledge", fetched_at=NOW.isoformat())

    run = ask(
        "summarise the file I attached",
        search=Passages(),
        follow_up=FollowUp(attached=(WITHHELD_DOCUMENT,), read_attached=attached),
    )

    assert run.sent == []
