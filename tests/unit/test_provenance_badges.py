"""A cited document carries its verification badge, at the reach it was cited at.

Every refusal here has a positive sibling. A badge check tested only by what it withholds is
satisfied by one that badges nothing, and an answer with no badge on it is exactly the
reassurance on unchecked documents that `AN_UNVERIFIED_ITEM_STILL_CARRIES_A_BADGE` forbids.

Task ids: M34.2.1.2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.redaction import ChannelPayload
from brain.core.scope import Scope
from brain.gate.compose import Citation, ComposedAnswer, new_trace_ref
from brain.gate.provenance import (
    DEFAULT_HORIZON,
    Anchor,
    BadgeReachError,
    Badging,
    DocumentCitation,
    Provenance,
    RetrievalTrace,
    provenance_for,
)
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.verification import VERIFIER_CAPABILITY
from brain.knowledge.visibility import KnowledgeVisibility

#: Far from any wall clock. The badge's due state is computed against this, never the present.
NOW = datetime(2099, 3, 1, 9, 0, tzinfo=UTC)
VERIFIED_AT = NOW - timedelta(days=200)
REVIEW_BY = NOW + timedelta(days=30)

VERIFIER = "p_priya"
CITED = "k_deployment_sop"

ASKER = EntitlementSet(
    principal_id="p_asker",
    grants=(Grant(capability=Capability(value="read:knowledge"), scope=Scope.unrestricted()),),
)
STEWARD = EntitlementSet(
    principal_id="p_steward",
    grants=(Grant(capability=VERIFIER_CAPABILITY, scope=Scope.unrestricted()),),
)

PASSAGE = DocumentCitation(
    document_id=CITED, title="Web deployment SOP", anchor=Anchor(chunk_id="c_1", page=2)
)
ANSWER = ComposedAnswer(
    text="Deploy on a Tuesday.",
    citations=(),
    payload=ChannelPayload(),
    trace_ref=new_trace_ref(),
    grounded=True,
)


def _item(
    item_id: str = CITED,
    *,
    title: str = "Web deployment SOP",
    verified_by: str = VERIFIER,
    state: KnowledgeState = KnowledgeState.PUBLISHED,
) -> KnowledgeItem:
    return KnowledgeItem(
        item_id=item_id,
        content="Deploy on a Tuesday. Never on a Friday.",
        title=title,
        visibility=KnowledgeVisibility.of_department("web"),
        owner_id="p_wei_ling",
        state=state,
        verified_by=verified_by,
        verified_at=VERIFIED_AT if verified_by else None,
        review_by=REVIEW_BY,
    )


def _badged(
    reader: EntitlementSet,
    items: tuple[KnowledgeItem, ...],
    *,
    retrieved_for: EntitlementSet | None = None,
    answer: ComposedAnswer = ANSWER,
) -> Provenance:
    trace = RetrievalTrace(passages=(PASSAGE,), ent_hash=(retrieved_for or reader).ent_hash())
    return provenance_for(
        answer,
        horizon=DEFAULT_HORIZON,
        now=NOW,
        trace=trace,
        badging=Badging(reader=reader, items=items),
    )


def test_a_cited_verified_document_names_its_verifier_to_a_reader_entitled_to_know() -> None:
    """**The leaf, and the positive case the refusals below are measured against.** The badge
    is in the rendered answer, beside the citation it belongs to.

    Delete this and a badging step that attaches nothing passes every withholding test."""
    rendered = _badged(STEWARD, (_item(),)).render()

    assert len(rendered) == 1
    assert rendered[0].endswith(f"[verified by {VERIFIER} on {VERIFIED_AT.date().isoformat()}]")


def test_a_reader_not_entitled_to_the_verifier_is_told_it_is_verified_and_not_by_whom() -> None:
    """The state reaches everybody and the name reaches only a reader who may have it.

    Delete this and the badge is computed without the reader, which names a colleague in
    every answer anybody receives."""
    provenance = _badged(ASKER, (_item(),))

    (evidence,) = provenance.documents
    assert evidence.badge is not None
    assert evidence.badge.verified_by == ""
    assert evidence.render().endswith("[verified]")
    assert all(VERIFIER not in line for line in provenance.render())


@pytest.mark.parametrize("reader", [ASKER, STEWARD], ids=["asker", "steward"])
def test_a_cited_unverified_document_says_so_to_everybody(reader: EntitlementSet) -> None:
    """The unverified half the leaf's tests must cover. A badge that appeared only on checked
    documents teaches a reader that no badge means nothing to report.

    Delete this and an unverified source can go out bare while the verified tests pass."""
    rendered = _badged(reader, (_item(verified_by=""),)).render()

    assert rendered[0].endswith("[not verified by anyone]")


def test_a_cited_document_with_no_record_on_file_is_badged_as_unverified() -> None:
    """A document no knowledge item describes has been vouched for by nobody, and says so.

    Delete this and the lookup can return no badge for a missing record, which is the bare
    citation the unverified rule exists to prevent."""
    (evidence,) = _badged(STEWARD, ()).documents

    assert evidence.render().endswith("[not verified by anyone]")


def test_an_item_nobody_cited_puts_nothing_into_the_answer() -> None:
    """**The badge follows the citation's reach.** A record handed in for a document retrieval
    did not return is never read: not its title, not its id, not its verifier.

    Listed before the cited record on purpose, so a lookup that ignored the document id and
    took the first record would badge the answer with the uncited one.

    Delete this and a caller holding every item in the department attaches whichever
    verified record it found first to an answer that never cited it."""
    uncited = _item("k_payroll_policy", title="Payroll policy", verified_by="p_hidden_verifier")

    provenance = _badged(STEWARD, (uncited, _item(verified_by="")))

    text = " ".join(provenance.render())
    assert len(provenance.documents) == 1
    assert "p_hidden_verifier" not in text
    assert "Payroll" not in text
    assert "k_payroll_policy" not in text
    assert text.endswith("[not verified by anyone]")


def test_a_badge_for_a_reader_other_than_the_one_retrieval_ran_for_is_refused() -> None:
    """Retrieval ran at the asker's reach and the badges were asked for at the steward's. Each
    half is correct on its own and together they name a colleague to the asker.

    Delete this and whatever reader the caller happens to hold decides whose name goes into
    somebody else's answer."""
    with pytest.raises(BadgeReachError) as refused:
        _badged(STEWARD, (_item(),), retrieved_for=ASKER)

    assert ASKER.principal_id not in str(refused.value)
    assert STEWARD.principal_id not in str(refused.value)


def test_a_trace_that_did_not_record_its_reach_cannot_be_badged() -> None:
    """An empty hash is not a wildcard. A trace that does not say whose reach it ran at cannot
    be shown to match anybody.

    Delete this and a retrieval step that forgot to record its reach admits any reader."""
    with pytest.raises(BadgeReachError):
        provenance_for(
            ANSWER,
            horizon=DEFAULT_HORIZON,
            now=NOW,
            trace=RetrievalTrace(passages=(PASSAGE,)),
            badging=Badging(reader=STEWARD, items=(_item(),)),
        )


def test_an_answer_assembled_without_badging_is_unchanged() -> None:
    """The existing callers, which pass no badging and a trace with no recorded reach, still
    get their provenance.

    Delete this and the reach check can refuse every document answer, badged or not."""
    provenance = provenance_for(
        ANSWER, horizon=DEFAULT_HORIZON, now=NOW, trace=RetrievalTrace(passages=(PASSAGE,))
    )

    (evidence,) = provenance.documents
    assert evidence.badge is None
    assert "[" not in evidence.render()


def test_a_row_citation_never_carries_a_badge() -> None:
    """A field of a record has nobody who vouched for it, and a badge beside one would claim
    a verification that never happened.

    Delete this and badging can be applied to every citation rather than to documents."""
    answer = ComposedAnswer(
        text="12",
        citations=(
            Citation(entity="client", record_id="c_1", field="hours", source="lark", fetched_at=""),
        ),
        payload=ChannelPayload(),
        trace_ref=new_trace_ref(),
        grounded=True,
    )

    provenance = _badged(STEWARD, (_item(),), answer=answer)

    assert [one.badge for one in provenance.rows] == [None]
    assert provenance.documents[0].badge is not None


def test_a_replaced_document_says_so_and_names_nobody() -> None:
    """A superseded item was verified once, and the reader needs to know it was replaced far
    more than who signed the old one.

    Delete this and a replaced document can carry its old verifier into a new answer."""
    rendered = _badged(STEWARD, (_item(state=KnowledgeState.SUPERSEDED),)).render()

    assert rendered[0].endswith("[replaced by a newer version]")
    assert VERIFIER not in rendered[0]


def test_two_records_for_one_item_are_refused() -> None:
    """Which record a badge was read from would depend on the order a query returned them.

    Delete this and the verified and unverified versions of one item take turns."""
    with pytest.raises(ValueError, match="appears twice"):
        Badging(reader=STEWARD, items=(_item(), _item(verified_by="")))
