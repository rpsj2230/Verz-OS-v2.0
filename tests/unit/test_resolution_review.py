"""The review page: what a person is shown, and what the page cannot say about what it hid.

`tests/unit/test_resolution_guardrails.py` holds the two rules underneath this: `Evidence` has
nowhere to put a value, and `review_queue` admits an item only to somebody who reaches both of
its halves. These are about the page built on top, and two of them carry M14.6.4.

**The strong form of "indistinguishable".** A page built from a list where the invisible items
were never written is identical, field for field, to a page built from the full list. That is
the only version worth asserting: a count that differs by one, a gap in a numbering or a
truncation flag would each reconstruct exactly what was hidden.

**Weighted evidence in plain language means a sentence and never a figure**, and the page adds
the one fact a reviewer needs in order to read those sentences correctly, which is whether
anything ever measured the weights behind them.

Task ids: M14.6.4
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields

from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, hidden_count_fields
from brain.resolution.canonical import SourceRef
from brain.resolution.cascade import DECLARED_WEIGHTS, WeightTable
from brain.resolution.guardrails import (
    DECISIVE_WEIGHT,
    SUPPORTING_WEIGHT,
    Evidence,
    ReviewItem,
    Strength,
)
from brain.resolution.review import REVIEW_SURFACE, ReviewCard, ReviewPage, card_for, review_page

MINE = SourceRef(source="hubspot", entity="company", source_id="1")
ALSO_MINE = SourceRef(source="hubspot", entity="company", source_id="2")
THEIRS = SourceRef(source="freshdesk", entity="company", source_id="9")

#: A weight table that names an export, so the card's "was this measured" half has a True case.
FITTED = WeightTable(
    version="fitted-v1",
    weights=dict(DECLARED_WEIGHTS.weights),
    calibration_ref="em-2026-09-07",
)


def item(item_id: str, left: SourceRef, right: SourceRef, *, weight: float) -> ReviewItem:
    return ReviewItem(
        item_id=item_id,
        left=left,
        right=right,
        evidence=(
            Evidence(field="uen", weight=weight),
            Evidence(field="country", weight=0.0),
        ),
    )


def reaches_hubspot(member: SourceRef) -> bool:
    return member.source == "hubspot"


def reaches_everything(member: SourceRef) -> bool:
    return bool(member.source)


# ------------------------------------------------- filter first, count afterwards (M14.6.4)
def test_a_page_is_identical_to_one_built_from_a_queue_that_never_held_the_hidden_items() -> None:
    """**The strong form of the rule, and the only one worth asserting.**

    A count that differed by one, a gap in the item ids, a truncation flag or an "and others"
    would each let a reader reconstruct exactly what they were not shown. So the assertion is
    not that the page omits the invisible items; it is that the page is indistinguishable, field
    for field, from the page of a queue that never contained them.

    The sibling below shows the hidden item is real: a test where nothing was filtered would
    pass this trivially.

    Delete this and the first useful summary field added to the page is computed over
    everything."""
    visible = item("a", MINE, ALSO_MINE, weight=DECISIVE_WEIGHT)
    hidden = item("b", MINE, THEIRS, weight=DECISIVE_WEIGHT)

    filtered = review_page([visible, hidden], reviewer_id="rupash", reaches=reaches_hubspot)
    never_written = review_page([visible], reviewer_id="rupash", reaches=reaches_hubspot)

    assert filtered == never_written
    assert [one.item_id for one in filtered.cards] == ["a"]

    everything = review_page([visible, hidden], reviewer_id="admin", reaches=reaches_everything)
    assert {one.item_id for one in everything.cards} == {"a", "b"}


def test_an_item_the_reviewer_reaches_only_one_half_of_is_not_on_the_page() -> None:
    """A review decides that two records are one thing, so a reviewer who reaches one of them
    cannot make the decision and must not be told the other exists.

    The filter is `guardrails.review_queue`'s conjunction and is not re-implemented here, which
    is the point: a second copy of who may see an item is a second place for it to be wrong.
    The item below is reachable on its left half only, which is the case a filter written on
    either half rather than both would admit.

    Delete this and the page can be built from a filter that checks one side."""
    half = item("half", MINE, THEIRS, weight=SUPPORTING_WEIGHT)

    page = review_page([half], reviewer_id="rupash", reaches=reaches_hubspot)

    assert page.cards == ()
    assert sum(page.by_strongest.values()) == 0


def test_the_counts_name_every_band_including_the_ones_at_nothing() -> None:
    """A caller writing `by_strongest.get(Strength.DECISIVE, 0)` reads as though that band were
    optional, and the band most likely to be missing on a quiet day is the one that matters
    most.

    Counted over the visible cards only, which is what makes the figure a count of things the
    reader is already looking at: the only kind of count this surface has.

    Delete this and the summary becomes a sparse mapping, and a screen renders a missing key as
    an absent band rather than an empty one."""
    page = review_page(
        [
            item("a", MINE, ALSO_MINE, weight=DECISIVE_WEIGHT),
            item("b", MINE, ALSO_MINE, weight=SUPPORTING_WEIGHT),
            item("c", MINE, THEIRS, weight=DECISIVE_WEIGHT),
        ],
        reviewer_id="rupash",
        reaches=reaches_hubspot,
    )

    assert set(page.by_strongest) == set(Strength)
    assert page.by_strongest[Strength.DECISIVE] == 1
    assert page.by_strongest[Strength.SUPPORTING] == 1
    assert page.by_strongest[Strength.STRONG] == 0
    assert sum(page.by_strongest.values()) == len(page.cards)


def test_no_field_on_the_review_surface_could_hold_a_count_of_what_was_hidden() -> None:
    """A rule that lives only in prose is defeated by somebody adding one field, and the field
    is added by somebody making a screen better rather than by somebody being careless.

    `brain.ops.jobs.hidden_count_fields` is the check and it is reused rather than rewritten,
    because the list of names such a field arrives under is the rule. Run over both types here,
    and shown to fire against a type that carries one, so this is a check rather than a
    restatement.

    Delete this and "showing 3 of 47" arrives on the page as a helpful total."""
    assert hidden_count_fields(REVIEW_SURFACE) == ()
    assert set(REVIEW_SURFACE) == {ReviewCard, ReviewPage}

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class WithATotal:
        cards: tuple[ReviewCard, ...]
        total: int

    assert hidden_count_fields((WithATotal,)) == ("WithATotal.total",)
    assert "total" in NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT


def test_the_page_keeps_the_queue_order_and_does_not_sort_by_evidence() -> None:
    """Ordering a queue by how strong its evidence is would be useful and would make the
    position of an item a statement about evidence the reviewer has not read yet.

    Worse, it would differ between two reviewers sharing an item, because each one's page holds
    a different set. `guardrails.review_queue` orders by the record ids for that reason and this
    does not re-sort; the item with the strongest evidence is deliberately last here.

    Delete this and the page sorts by score, which is the first thing anybody would add."""
    weak = item("z-weak", MINE, ALSO_MINE, weight=SUPPORTING_WEIGHT)
    strong = ReviewItem(
        item_id="z-strong",
        left=SourceRef(source="hubspot", entity="company", source_id="3"),
        right=SourceRef(source="hubspot", entity="company", source_id="4"),
        evidence=(Evidence(field="uen", weight=DECISIVE_WEIGHT),),
    )

    page = review_page([strong, weak], reviewer_id="rupash", reaches=reaches_hubspot)

    assert [one.item_id for one in page.cards] == ["z-weak", "z-strong"]


# ----------------------------------------------------- plain language on the card (M14.6.4)
def test_a_card_reads_as_sentences_with_no_number_anywhere_on_the_line() -> None:
    """A reviewer shown 6.2 beside 4.9 does arithmetic, and the arithmetic is a threshold they
    invented on a scale nothing has calibrated.

    The renderer is `guardrails.Evidence.render` and is not reimplemented here, so the rule
    holds in one place. What this asserts is that the page does not put the figure back: the
    lines are the rendered sentences and there is no digit in any of them.

    Delete this and a weight column is added to the card, which is the most natural improvement
    anybody could suggest for a screen like this."""
    card = card_for(item("a", MINE, ALSO_MINE, weight=DECISIVE_WEIGHT))

    assert card.lines == (
        "uen agreed, and on its own that is very nearly the whole answer",
        "country did not agree, and that counts against these being one thing",
    )
    for line in card.lines:
        assert not any(character.isdigit() for character in line), line


def test_a_reviewer_is_told_which_weights_produced_the_sentences_and_whether_measured() -> None:
    """The bands stop a reviewer inventing a threshold. They do not stop them assuming the
    bands themselves were measured, and nothing in this repository has measured any weight in
    the declared table.

    So the card names the weight table and says whether it came from a calibration export. Both
    cases are asserted, because a field hard-wired to False would satisfy the honest half and
    would stop being true the day a fit lands.

    Delete this and a reviewer acts on evidence bands nobody measured, with nothing on the page
    saying so."""
    declared = card_for(item("a", MINE, ALSO_MINE, weight=DECISIVE_WEIGHT))
    assert declared.weight_version == DECLARED_WEIGHTS.version
    assert declared.calibrated is False

    fitted = card_for(item("a", MINE, ALSO_MINE, weight=DECISIVE_WEIGHT), weights=FITTED)
    assert fitted.weight_version == "fitted-v1"
    assert fitted.calibrated is True


def test_a_card_carries_no_score_and_no_confidence() -> None:
    """A total is the thing a reviewer would threshold on, and
    `canonical.A_SCORE_IS_EVIDENCE_AND_NEVER_A_PERMISSION` is why it is not carried past the
    cascade.

    Asserted on the declared fields rather than on an instance, so a field that happened to be
    None on this particular card is not mistaken for a field that does not exist.

    Delete this and a score arrives on the card because the queue would be easier to triage
    with one."""
    names = {one.name for one in dataclass_fields(ReviewCard)}

    assert names == {"item_id", "left", "right", "lines", "weight_version", "calibrated"}
    assert not names & {"score", "confidence", "total", "stage", "similarity"}
