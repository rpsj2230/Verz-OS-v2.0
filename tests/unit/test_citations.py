"""What an answer on Ask stands on: each citation's link, how fresh it is, and who vouched for it.

`tests/unit/test_abstain.py` holds `brain.gate.provenance` to its own rules one function at a time.
This file holds the answer lane to using them: the citation frames a person receives, the sentence
an answer carries when its evidence is old, the badge beside a cited document, and the refusal that
reaches an administrator's trace and never the asker. Driven through `answer_lane` with the real
`compose`, `redact`, `provenance` and stream, and a stand-in only where a database or a network
would be, for `tests/unit/test_answer_lane.py`'s reason.

Every refusal has a positive sibling, and every constant is held against something outside the
module that defines it.

Task ids: M8.1.1, M8.1.2, M8.1.3, M8.1.4, M8.2.1, M8.2.4, M11.4.9, M7.4.7
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.abstain import (
    NOT_FOUND_TEXT,
    REQUIRE_CITATION,
    Abstention,
    AbstentionReason,
    CitationPolicy,
    SearchScope,
    not_entitled,
)
from brain.gate.answer import Answered, answer_lane, with_evidence_notice
from brain.gate.compose import Citation
from brain.gate.context import Channel
from brain.gate.fast_lane import RowReader
from brain.gate.finish import Origin
from brain.gate.model_lane import ModelLane
from brain.gate.provenance import (
    DEFAULT_HORIZON,
    DOCUMENT_HORIZON,
    DOCUMENT_KIND,
    FRESHNESS_TEXT,
    RECORD_KIND,
    SEED_HORIZONS,
    STALENESS_TEXT,
    UNCITED_TEXT,
    Anchor,
    DocumentCitation,
    Evidence,
    Freshness,
    Horizons,
    Provenance,
    StalenessHorizon,
    state_freshness,
)
from brain.gate.streaming import AnswerStream, Progress, StreamOrderError, frames
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, KnowledgePassage
from brain.knowledge.item import KnowledgeItem, KnowledgeState, VerificationState
from brain.knowledge.rows import RowRecord, RowRequest
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.log_capture import VOCABULARY, Kind, kept_word
from tests.unit import test_answer_lane as lane
from tests.unit import test_model_lane as model
from tests.unit.test_model_calls import Ladder, Scripted, executor, rung
from tests.unit.test_streaming import decode

NOW = lane.NOW

# ------------------------------------------------------------------------------ helpers


def citations(answered: Answered | None) -> list[dict[str, str]]:
    """Every citation frame, parsed as the fields the Ask screen reads."""
    assert answered is not None
    return [
        json.loads(one.data) for one in decode(frames(answered.frames)) if one.event == "citation"
    ]


def texts(answered: Answered | None) -> list[str]:
    assert answered is not None
    return [one.data for one in decode(frames(answered.frames)) if one.event == "text"]


def reader_of(record: dict[str, Any], *, fetched_at: datetime) -> RowReader:
    """A row reader handing back one record read at `fetched_at`, whatever it was asked.

    It returns the whole record, answer field included, so a field the redactor locks is a lock
    the lane sees, which the projection-compiled reader never gives it: see
    `brain.gate.answer._withheld_or_absent`.
    """

    async def read(
        request: RowRequest, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[RowRecord]:
        del request, entitlement, now
        return TypedResult(
            records=(RowRecord(**record),), source="laravel", fetched_at=fetched_at.isoformat()
        )

    return read


def origin_for(reach: EntitlementSet) -> Origin:
    """Whoever the reach belongs to, because the lane refuses anything else."""
    return Origin(
        trace_id="t-citations",
        principal=Principal(
            id=reach.principal_id,
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name="Asker",
        ),
        channel=Channel.CONSOLE,
    )


def answered_from(
    *,
    fetched_at: datetime = NOW,
    entitlement: EntitlementSet | None = None,
    horizons: Horizons = SEED_HORIZONS,
) -> Answered:
    """The fast lane over `reader_of`, at the horizons given."""
    reach = entitlement if entitlement is not None else lane.ents(*lane.SEES_HOURS)
    return asyncio.run(
        answer_lane(
            "hours left on Acme",
            origin=origin_for(reach),
            recorders=(),
            rules=(lane.HOURS,),
            readers={("laravel", "client"): reader_of(lane.ACME, fetched_at=fetched_at)},
            entitlement=reach,
            policies={"client": lane.CLIENTS.policy()},
            reachable_sources=("laravel",),
            sink=lane.Sink(),
            now=NOW,
            clock=lambda: NOW,
            horizons=horizons,
        )
    )


def a_row_citation(fetched_at: str) -> Citation:
    return Citation(
        entity="client",
        record_id="c_447",
        field="hours_remaining",
        source="laravel",
        fetched_at=fetched_at,
    )


def a_document_citation(fetched_at: str = "") -> DocumentCitation:
    return DocumentCitation(
        document_id="doc_handbook",
        title="Handbook",
        anchor=Anchor(chunk_id="doc_handbook.0003", page=2, section="Leave"),
        source="knowledge",
        fetched_at=fetched_at,
    )


def evidence(citation: Citation | DocumentCitation, horizon: StalenessHorizon) -> Evidence:
    return Evidence(
        citation=citation,
        freshness=state_freshness(citation.fetched_at, horizon=horizon, now=NOW),
    )


# ----------------------------------------------- a citation reaches a screen as fields (M8.1.x)


def test_a_row_citation_is_sent_as_the_record_and_field_it_names_and_when_it_was_read() -> None:
    """M8.1.1 on the wire. The screen links the record's entity, names the record and the field
    and dates the read, each from its own field.

    Delete this and a citation reaches the screen as a sentence again, which nobody can follow."""
    sent = evidence(a_row_citation(NOW.isoformat()), DEFAULT_HORIZON).view()

    assert sent["kind"] == RECORD_KIND
    assert (sent["entity"], sent["record_id"], sent["field"]) == (
        "client",
        "c_447",
        "hours_remaining",
    )
    assert sent["read_at"] == NOW.isoformat()
    assert sent["freshness"] == Freshness.LIVE.value
    assert sent["freshness_text"] == FRESHNESS_TEXT[Freshness.LIVE]
    assert NOW.isoformat() not in sent["label"]


def test_a_document_citation_is_sent_with_the_anchor_its_passage_is_linked_by() -> None:
    """M8.1.2 on the wire. The anchor is the fragment `Anchor.fragment` builds, so the link the
    screen draws lands on the chunk the passage is, by position and never by quotation.

    Delete this and a document citation names a document and not the place in it."""
    cited = a_document_citation(NOW.isoformat())
    sent = evidence(cited, DOCUMENT_HORIZON).view()

    assert sent["kind"] == DOCUMENT_KIND
    assert sent["document_id"] == "doc_handbook"
    assert sent["anchor"] == cited.anchor.fragment() == "chunk=doc_handbook.0003&page=2"
    assert sent["where"] == "page 2, section Leave"
    assert sent["title"] == "Handbook"


def test_a_read_time_nobody_can_date_is_not_sent_beside_its_citation() -> None:
    """ "Read time not stated" beside the string that could not be dated is the inference
    `provenance` refuses, arriving through the wire instead of the sentence.

    Delete this and a wall-clock "14:31" is drawn as though it were a date."""
    sent = evidence(a_row_citation("14:31"), DEFAULT_HORIZON).view()

    assert sent["freshness"] == Freshness.UNSTATED.value
    assert sent["read_at"] == ""


def test_no_value_on_the_wire_is_a_number() -> None:
    """Every field is a string, so nothing on a citation frame can be read as a count of what
    the reader was not shown.

    Delete this and a "passages: 3" field can be added by whoever wanted the screen to say so."""
    for one in (
        evidence(a_row_citation(NOW.isoformat()), DEFAULT_HORIZON),
        evidence(a_document_citation(NOW.isoformat()), DOCUMENT_HORIZON),
    ):
        assert all(isinstance(value, str) for value in one.view().values())


# ------------------------------------------------ the sentence about old evidence (M11.4.9)


def test_one_stale_citation_makes_the_answer_say_it_may_be_out_of_date() -> None:
    """**The leaf.** An answer standing on a live row and a stale one is a stale answer, and it
    says so in words a person reads, not only beside the citation.

    Delete this and a two-day-old figure is quoted with nothing said about its age."""
    live = evidence(a_row_citation(NOW.isoformat()), DEFAULT_HORIZON)
    stale = evidence(a_row_citation((NOW - timedelta(days=2)).isoformat()), DEFAULT_HORIZON)

    notice = Provenance(rows=(live, stale)).notice()

    assert notice == STALENESS_TEXT[Freshness.STALE]
    assert "may be out of date" in notice


def test_an_answer_whose_evidence_is_current_says_nothing_about_its_age() -> None:
    """The positive case. A reassurance on every answer trains a reader to skip the line.

    Delete this and a notice that always speaks passes the test above."""
    live = evidence(a_row_citation(NOW.isoformat()), DEFAULT_HORIZON)

    assert Provenance(rows=(live,)).notice() == ""


def test_an_undated_read_is_said_to_be_possibly_out_of_date() -> None:
    """UNSTATED outranks STALE in `stalest`, and the sentence follows it.

    Delete this and an undated read reaches the reader as silence, which reads as current."""
    unknown = evidence(a_row_citation(""), DEFAULT_HORIZON)

    assert Provenance(rows=(unknown,)).notice() == STALENESS_TEXT[Freshness.UNSTATED]
    assert "may be out of date" in STALENESS_TEXT[Freshness.UNSTATED]


def test_nothing_standing_behind_an_answer_is_said_once_and_not_as_staleness() -> None:
    """An empty provenance is the uncited sentence and never a staleness one, so an answer with
    no evidence is not told that its evidence is old.

    Delete this and an uncited answer is told its sources may be out of date."""
    assert Provenance().notice() == ""
    assert with_evidence_notice("Answer.", Provenance()) == f"Answer. {UNCITED_TEXT}"


def test_a_document_is_judged_in_months_and_a_row_in_hours() -> None:
    """The seeds' relation rather than their values: a document is current for longer than a row
    stays anything but stale, because a document's read time is when its words were written.

    Delete this and one horizon for both calls every uploaded document out of date tomorrow."""
    assert SEED_HORIZONS.rows == DEFAULT_HORIZON
    assert SEED_HORIZONS.documents.live_for > DEFAULT_HORIZON.stale_after
    two_days = (NOW - timedelta(days=2)).isoformat()
    assert state_freshness(two_days, horizon=SEED_HORIZONS.rows, now=NOW).state is Freshness.STALE
    assert (
        state_freshness(two_days, horizon=SEED_HORIZONS.documents, now=NOW).state is Freshness.LIVE
    )
    old = (NOW - DOCUMENT_HORIZON.stale_after - timedelta(days=1)).isoformat()
    assert state_freshness(old, horizon=SEED_HORIZONS.documents, now=NOW).state is Freshness.STALE


# ------------------------------------------------------------ the fast lane on the wire


def test_a_rule_answer_streams_its_citation_as_fields_and_never_the_value() -> None:
    """The fast lane's citation is the record and field it read, when it read it, and not the
    figure the answer quotes.

    Delete this and the lane can go back to writing sentences, or write the value into a field."""
    answered = answered_from()
    sent = citations(answered)

    assert {one["kind"] for one in sent} == {RECORD_KIND}
    assert {(one["entity"], one["record_id"], one["field"]) for one in sent} == {
        ("client", "c_447", "hours_remaining"),
        ("client", "c_447", "name"),
    }
    assert {one["freshness"] for one in sent} == {Freshness.LIVE.value}
    assert "37" not in json.dumps(sent)
    assert answered.provenance is not None and answered.provenance.rows


def test_a_row_read_two_days_ago_is_answered_with_a_sentence_saying_it_may_be_out_of_date() -> None:
    """**The install check in miniature.** The value is still given, and the answer's own text
    says it may be out of date, and the citation says stale.

    Delete this and the lane can drop `Provenance.notice` from the text with every other test in
    this file green."""
    answered = answered_from(fetched_at=NOW - timedelta(days=2))

    (text,) = texts(answered)
    assert text.startswith("37 ")
    assert STALENESS_TEXT[Freshness.STALE] in text
    assert citations(answered)[0]["freshness"] == Freshness.STALE.value


def test_the_horizons_the_lane_is_handed_decide_whether_a_read_is_old() -> None:
    """The horizons are the caller's, so an install that sets its own is obeyed.

    Delete this and the lane can ignore `horizons` and read the seed, which no other test sees."""
    patient = Horizons(
        rows=StalenessHorizon(live_for=timedelta(days=3), stale_after=timedelta(days=4)),
        documents=DOCUMENT_HORIZON,
    )
    answered = answered_from(fetched_at=NOW - timedelta(days=2), horizons=patient)

    assert texts(answered)[0].split(" This covers")[0] == "37"
    assert citations(answered)[0]["freshness"] == Freshness.LIVE.value


# ------------------------------------------- a refusal is told to an administrator (M8.2.1)


def test_a_withheld_answer_field_reaches_the_log_as_a_refusal_and_the_asker_as_nothing() -> None:
    """**M8.2.1's two halves at once.** A record whose answer field the redactor locked is a
    refusal the lane saw: the asker receives the frames an absent record produces, byte for byte,
    and the log receives a warning naming the reason, the entity and the field.

    Delete this and the refusal is either told to the asker or recorded nowhere anybody reads."""
    name_only = lane.ents(*lane.SEES_NAME_ONLY)
    with capture_logs() as withheld_log:
        withheld = answered_from(entitlement=name_only)
    with capture_logs() as absent_log:
        absent = lane.run("hours left on Nobody", rows=lane.Rows(), entitlement=name_only)

    assert withheld.abstention is not None
    assert withheld.abstention.reason is AbstentionReason.NOT_ENTITLED
    assert withheld.frames == absent.frames
    assert NOT_FOUND_TEXT in texts(withheld)[0]
    told = [one for one in withheld_log if one["event"] == "answer.withheld"]
    assert told == [
        {
            "event": "answer.withheld",
            "log_level": "warning",
            "reason": "not_entitled",
            "entity": "client",
            "field": "hours_remaining",
        }
    ]
    assert not [one for one in absent_log if one["event"] == "answer.withheld"]


def test_the_refusal_fields_are_ones_the_log_capture_keeps_as_words() -> None:
    """The Logs screen shows a field's value only when the capture's vocabulary keeps it as a
    word, so the refusal is written under keys it keeps and in a value it accepts.

    Delete this and the warning reaches the Logs screen as three shapes, which is what the route's
    `abstained` line always did."""
    told = not_entitled(SearchScope(), entity="client", field="hours_remaining").for_administrator()

    assert told is not None
    for key, value in told.items():
        assert VOCABULARY[key] is Kind.WORD
        assert kept_word(value, ()) == value


@pytest.mark.parametrize(
    "reason", [one for one in AbstentionReason if one is not AbstentionReason.NOT_ENTITLED]
)
def test_only_a_refusal_names_what_was_withheld_or_reaches_the_administrator(
    reason: AbstentionReason,
) -> None:
    """Nothing found, not answering, nothing connected and refused are not refusals, so they name
    no withheld field and write no refusal to the log.

    Delete this and "nothing found" can carry an entity and a field, inventing a refusal."""
    with pytest.raises(ValueError, match="cannot name what was withheld"):
        Abstention(reason=reason, withheld_field="hours_remaining")
    assert Abstention(reason=reason).for_administrator() is None
    assert not_entitled(SearchScope()).for_administrator() == {"reason": "not_entitled"}


# ------------------------------------------------ a passage is cited as its document (M8.1.2)


class Items:
    """An `ItemLookup` holding fixed items, and every set of references it was asked for."""

    def __init__(self, *items: KnowledgeItem) -> None:
        self.held = items
        self.asked: list[tuple[str, ...]] = []

    async def items(
        self, document_ids: Sequence[str], *, entitlement: EntitlementSet, now: datetime
    ) -> tuple[KnowledgeItem, ...]:
        self.asked.append(tuple(document_ids))
        return tuple(one for one in self.held if one.item_id in document_ids)


def an_item(*, verified_by: str, document_id: str = model.READABLE_DOCUMENT) -> KnowledgeItem:
    return KnowledgeItem(
        item_id=document_id,
        content="Annual leave is twenty five days a year.",
        title="Handbook",
        visibility=KnowledgeVisibility.of_department("web"),
        owner_id="p_owner",
        state=KnowledgeState.PUBLISHED,
        verified_by=verified_by,
        verified_at=model.NOW - timedelta(days=10),
        review_by=model.NOW + timedelta(days=300),
    )


def ask_with(
    *passages: KnowledgePassage,
    items: Items | None = None,
    policy: CitationPolicy = REQUIRE_CITATION,
    entitlement: EntitlementSet = model.CALLER,
    reply: str = model.REPLY,
) -> Answered:
    """`tests/unit/test_model_lane.ask`'s lane, with an item lookup and a citation policy on it.

    The readable and the withheld passage by default, so the search stand-in breaches the first
    wall exactly as that file's does and the redactor is what is being relied on.
    """
    transport = Scripted(model.completion(reply))
    calls, _ = executor(Ladder((rung("anthropic"),)), {"anthropic": transport})
    found = model.Passages(*(passages or (model.VISIBLE, model.WITHHELD)))
    return asyncio.run(
        answer_lane(
            model.QUESTION,
            origin=origin_for(entitlement),
            recorders=(),
            rules=(lane.HOURS,),
            readers=lane.readers_for(lane.Rows(lane.ACME)),
            entitlement=entitlement,
            policies={"client": lane.CLIENTS.policy()},
            reachable_sources=("laravel",),
            sink=lane.Sink(),
            now=model.NOW,
            clock=lambda: model.NOW,
            model=ModelLane(search=found, model=calls, items=items, citations=policy),
        )
    )


def test_a_passage_is_cited_as_its_documents_passage_and_not_field_by_field() -> None:
    """**M8.1.2 through the lane.** The readable passage is one document citation anchored at its
    chunk; it is not cited again as a row per field; the withheld passage is not cited at all.

    Delete this and the model lane goes back to "knowledge c_handbook_1: section from knowledge",
    once per field, which names no document and links nowhere."""
    run = ask_with()
    sent = citations(run)

    assert [one["kind"] for one in sent] == [DOCUMENT_KIND]
    (cited,) = sent
    assert cited["document_id"] == model.READABLE_DOCUMENT
    assert cited["anchor"] == f"chunk={model.VISIBLE.id}"
    assert cited["where"] == "section Leave"
    for value in model.PLANTED:
        assert value not in json.dumps(sent)


def test_a_title_the_reader_may_not_read_is_left_off_the_citation_and_the_reference_named() -> None:
    """The caller holds no `read:knowledge.title`, so the citation carries no title and names the
    document by the reference the body's own capability let through.

    Delete this and the title is read off the fetched passage rather than the redacted one."""
    (cited,) = citations(ask_with())

    assert cited["title"] == ""
    assert cited["label"].startswith(model.READABLE_DOCUMENT)


def test_a_passage_whose_document_reference_is_withheld_is_cited_as_the_row_it_arrived_as() -> None:
    """A reader who may read a passage's section and not its document still had the section
    shown to the model, so something stands behind the answer: the row citation of that field.

    Delete this and such an answer is cited by nothing, and the uncited rule refuses it."""
    sections_only = EntitlementSet(
        principal_id="p_priya",
        grants=(
            Grant(capability=Capability(value="read:knowledge"), scope=Scope()),
            model.on_the_readable_document("read:knowledge.section"),
        ),
    )
    run = ask_with(model.VISIBLE, entitlement=sections_only)
    sent = citations(run)

    assert sent
    assert {one["kind"] for one in sent} == {RECORD_KIND}
    assert {(one["entity"], one["record_id"], one["field"]) for one in sent} == {
        (KNOWLEDGE_ENTITY, model.VISIBLE.id, "section")
    }


def test_the_model_cannot_add_a_citation_by_naming_a_document() -> None:
    """M8.1.4 through the lane. A reply naming the withheld document is prose and nothing else:
    the only document cited is the one the redacted passages hold.

    Delete this and a citation can be read off the reply, which is a model choosing sources."""
    run = ask_with(reply=f"See {model.WITHHELD_DOCUMENT}, chunk {model.WITHHELD.id}.")

    assert {one["document_id"] for one in citations(run)} == {model.READABLE_DOCUMENT}


def test_a_stale_document_is_answered_with_a_sentence_saying_it_may_be_out_of_date() -> None:
    """A document whose stored copy is two years old is quoted, and the answer says so.

    Delete this and the model lane's text can drop the notice the fast lane carries."""
    old = model.VISIBLE.model_copy(
        update={"updated_at": (model.NOW - timedelta(days=730)).isoformat()}
    )
    run = ask_with(old)

    assert STALENESS_TEXT[Freshness.STALE] in texts(run)[-1]
    assert citations(run)[0]["freshness"] == Freshness.STALE.value


def test_a_recent_document_is_answered_with_no_sentence_about_its_age() -> None:
    """The positive sibling. A document written last week is current, and nothing is said.

    Delete this and a notice that always speaks passes the test above."""
    recent = model.VISIBLE.model_copy(
        update={"updated_at": (model.NOW - timedelta(days=7)).isoformat()}
    )
    run = ask_with(recent)

    text = texts(run)[-1]
    assert all(sentence not in text for sentence in STALENESS_TEXT.values() if sentence)
    assert citations(run)[0]["freshness"] == Freshness.LIVE.value


# ---------------------------------------------------------------- the badge (M7.4.7)


def test_a_cited_document_its_reader_verified_carries_the_badge_with_their_name() -> None:
    """**The leaf through the lane.** The caller verified the handbook, so the badge beside its
    citation names them and the date; `verification.may_name_verifier` admits the verifier.

    Delete this and a lane that never reads the item passes every withholding test below."""
    held = Items(an_item(verified_by=model.CALLER.principal_id))
    (cited,) = citations(ask_with(items=held))

    assert cited["badge_state"] == VerificationState.VERIFIED.value
    assert cited["badge"] == (
        f"verified by {model.CALLER.principal_id} on "
        f"{(model.NOW - timedelta(days=10)).date().isoformat()}"
    )


def test_a_reader_not_entitled_to_the_verifier_is_told_verified_and_not_by_whom() -> None:
    """The state reaches everybody and the name only a reader who may have it.

    Delete this and the lane badges with the item's own record, naming a colleague to everyone."""
    held = Items(an_item(verified_by="p_somebody_else"))
    (cited,) = citations(ask_with(items=held))

    assert cited["badge_state"] == VerificationState.VERIFIED.value
    assert cited["badge"] == "verified"
    assert "p_somebody_else" not in json.dumps(cited)


def test_the_item_lookup_is_asked_for_the_cited_documents_and_no_others() -> None:
    """A badge exists only beside a citation, so the item of an uncited document is never read.

    Delete this and the lookup can be asked for every passage the search returned, withheld
    ones included, which reads items for documents the reader was not shown."""
    held = Items()
    ask_with(items=held)

    assert held.asked == [(model.READABLE_DOCUMENT,)]


def test_a_lane_with_no_item_lookup_badges_nothing_rather_than_calling_all_unverified() -> None:
    """With no lookup, no citation carries a badge. "Not verified by anyone" on an item a steward
    did verify would be false; a missing badge is only quiet.

    Delete this and a process with no database tells every asker that nothing was ever verified."""
    (cited,) = citations(ask_with())

    assert cited["badge"] == "" and cited["badge_state"] == ""


def test_a_cited_document_with_no_item_on_file_is_badged_as_verified_by_nobody() -> None:
    """With a lookup, a cited document whose item the reader cannot read or nobody wrote is
    unverified and says so, for `AN_UNVERIFIED_ITEM_STILL_CARRIES_A_BADGE`'s reason.

    Delete this and only checked documents carry a badge, which teaches that no badge is fine."""
    (cited,) = citations(ask_with(items=Items()))

    assert cited["badge_state"] == VerificationState.UNVERIFIED.value
    assert cited["badge"] == "not verified by anyone"


# ------------------------------------------------------------- the citation rule (M8.2.4)


def test_an_agent_allowed_to_answer_uncited_still_cites_what_it_used() -> None:
    """Loosening the rule changes only the answer nothing stands behind; an answer with a passage
    behind it is cited exactly as under the default.

    Delete this and `require_citation=False` can be read as "cite nothing"."""
    loose = ask_with(policy=CitationPolicy(require_citation=False))
    strict = ask_with()

    assert citations(loose) == citations(strict)
    assert UNCITED_TEXT not in texts(loose)[-1]


# ------------------------------------------------------------------ the frame (M8.1.x)


def test_an_evidence_frame_cannot_go_out_after_the_prose_it_supports() -> None:
    """The same window as a bare citation, because a citation scrolled past is not read however
    much it carries.

    Delete this and the lane can write evidence after the text with every frame well formed."""
    stream = AnswerStream()
    stream.step(Progress.UNDERSTANDING)
    stream.text("Thirty seven.")

    with pytest.raises(StreamOrderError):
        stream.evidence(evidence(a_row_citation(NOW.isoformat()), DEFAULT_HORIZON))


def test_an_evidence_frame_is_one_event_whatever_its_title_holds() -> None:
    """A title with a blank line in it would end an event written naively; JSON escapes it, so a
    citation is one event and parses whole.

    Delete this and a document titled over two paragraphs splits its citation in two."""
    cited = DocumentCitation(
        document_id="doc_x", title="Part one\n\nPart two", anchor=Anchor(chunk_id="doc_x.0001")
    )
    frame = AnswerStream().evidence(evidence(cited, DOCUMENT_HORIZON))

    (one,) = decode(frame)
    assert one.event == "citation"
    assert json.loads(one.data)["title"] == "Part one\n\nPart two"


def test_an_answer_carries_its_evidence_only_beside_the_answer() -> None:
    """`Answered.provenance` is present beside an answer and refused beside a refusal, so a
    channel drawing citations cannot draw them under a refusal.

    Delete this and an abstention can carry the evidence of the record it withheld."""
    with pytest.raises(ValueError, match="only beside the answer"):
        Answered(
            frames=("x",),
            provenance=Provenance(),
            abstention=Abstention(reason=AbstentionReason.NOTHING_RETRIEVED),
        )


def test_a_cited_documents_read_time_is_its_stored_copys_and_never_the_request_instant() -> None:
    """The document citation's read time is the passage's `updated_at`, which the reader may read,
    and not the search's `fetched_at`, which is always now and would call every document current.

    Delete this and every document answer is fresh by construction."""
    old = (model.NOW - timedelta(days=500)).isoformat()
    run = ask_with(model.VISIBLE.model_copy(update={"updated_at": old}))

    (cited,) = citations(run)
    assert cited["read_at"] == old
    assert cited["read_at"] != model.NOW.isoformat()


def test_a_citation_of_a_row_is_never_badged() -> None:
    """A row is a field of a record and nobody vouches for it, so its badge fields are empty.

    Delete this and a row citation can borrow a badge meant for a document."""
    for sent in citations(answered_from()):
        assert sent["badge"] == "" and sent["badge_state"] == ""


def test_every_state_that_is_not_current_has_a_sentence_and_current_has_none() -> None:
    """Held against `Freshness` itself, so a fifth state cannot arrive without a sentence.

    Delete this and a new state reaches the answer as a `KeyError`."""
    assert set(STALENESS_TEXT) == set(Freshness)
    assert STALENESS_TEXT[Freshness.LIVE] == ""
    assert all(STALENESS_TEXT[one] for one in Freshness if one is not Freshness.LIVE)
