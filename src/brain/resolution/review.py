"""What a reviewer is handed when the cascade could not decide, and what the page may not
count.

`brain.resolution.guardrails` holds the two rules this is built on: `Evidence` has a field name,
a weight and nowhere to put a value, and `review_queue` admits an item only to somebody who
reaches both of its halves. This is the read model a screen would be drawn from, and it exists
as a separate module because a screen is not built and the domain side is what M14.6.4 is
actually about.

**Filter first, count afterwards, and there is no moment in between when the total exists.**
`review_page` calls `guardrails.review_queue` before it builds a single card, so the collection
the arithmetic runs over is already the reader's. That ordering is what makes the rule
structural rather than remembered: there is no point in this function at which a count of
everything is in scope to be returned by accident. It is
`brain.ops.jobs.dead_letter_summary`'s construction, and the strong form of the property is the
same one that module asserts, which is that a page built from a list where the invisible items
were never written is identical to a page built from the full list. See
`A_PAGE_BUILT_FROM_WHAT_A_READER_SEES_CANNOT_DESCRIBE_WHAT_THEY_DO_NOT`.

**Weighted evidence shown in plain language means a sentence and never a figure (M14.6.4).**
`Evidence.render` is the renderer and it is not reimplemented here: a field name and a band, in
words. A reviewer shown 6.2 beside 4.9 does arithmetic, and the arithmetic they do is a
threshold they invented on a scale nothing has calibrated. What this adds is the other half of
that honesty, which is that the reviewer is told which weight table produced the sentences and
whether anything measured it. See
`A_READER_JUDGING_EVIDENCE_IS_TOLD_WHETHER_ANYTHING_MEASURED_IT`.

**There is no score on a card and no confidence.** A total is the thing a reviewer would
threshold on, and `canonical.A_SCORE_IS_EVIDENCE_AND_NEVER_A_PERMISSION` is why it is not
carried past the cascade. The per-field evidence is here, which is where evidence belongs.

**No count of what a reviewer was not shown, and no field that could hold one.** Not a total, not
a "showing 3 of 47", not a truncation flag, and not an alarm that grows with the queue. The
names such a field arrives under are enumerated in `brain.ops.jobs` and a test runs that check
over the two types here, because the field is added by somebody making a screen more useful
rather than by somebody being careless.

**This is not a page and there is no page.** No route serves it, no console screen is wired to
it, and `brain.console.reads` requires every console read to be a tool call with a required
capability, which nothing here is. What exists is the data such a screen would render and the
filter that decides whose data it is. See `NO_SCREEN_IS_WIRED_TO_ANY_OF_THIS`.

Rejected: ordering the queue by evidence strength, which is what a reviewer would ask for. The
position of an item would then be a statement about evidence they have not read yet, and two
reviewers sharing an item would see it in different places depending on what else each of them
may see. `guardrails.review_queue` orders by the records for that reason and this does not
re-sort.

Rejected: a per-reviewer count of what was filtered out, kept for operators only. There is no
such thing as an operator-only field on a read model: the field exists, the screen renders what
it is given, and the first person to add a debug view has published it.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders a page.

Task ids: M14.6.4
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.resolution.canonical import MemberReach, SourceRef
from brain.resolution.cascade import DECLARED_WEIGHTS, WeightTable
from brain.resolution.guardrails import ReviewItem, Strength, review_queue

# ------------------------------------------------------------------ written-down reasons
#: Why the filter runs before the arithmetic rather than after it.
A_PAGE_BUILT_FROM_WHAT_A_READER_SEES_CANNOT_DESCRIBE_WHAT_THEY_DO_NOT: Final = (
    "Every figure on this page is computed from the cards the reader may see, because the "
    "filter runs first and the arithmetic runs on what is left. That is stronger than "
    "remembering not to publish a total: there is no point in the function at which a count of "
    "everything exists, so there is nothing to return by accident and nothing for a later "
    "field to be computed from. The property worth asserting is the strong one: a page built "
    "from a list where the invisible items were never written is identical to a page built "
    "from the full list. A count that differed by one, a gap in a numbering or a placeholder "
    "would each reconstruct exactly what was hidden."
)

#: Why the reviewer is told which weight table produced the sentences.
A_READER_JUDGING_EVIDENCE_IS_TOLD_WHETHER_ANYTHING_MEASURED_IT: Final = (
    "guardrails.Evidence.render shows a band in words and never a number, which stops a "
    "reviewer inventing a threshold on an uncalibrated scale. It does not stop them assuming "
    "the bands themselves were measured. Nothing in this repository has measured any weight in "
    "the declared table, so the card names the weight table and says whether it came from a "
    "calibration export. That is a fact about the evidence rather than a caveat about the "
    "product, and it belongs on the surface where somebody is being asked to act on it."
)

#: The gap this module does not close, kept as a constant so it has to be deleted.
NO_SCREEN_IS_WIRED_TO_ANY_OF_THIS: Final = (
    "There is no route, no console screen and no ConsoleRead for the review queue. "
    "brain.console.reads requires every console read to name a tool and a required capability, "
    "and nothing here is one, so this is the data a screen would render rather than a screen. "
    "Nothing produces review items either: cascade answers about a pair it was handed and "
    "nothing in the running system hands it one. Said in a constant so that claiming a review "
    "queue exists requires deleting the sentence that says it does not."
)


@dataclass(frozen=True)
class ReviewCard:
    """One pair a person is being asked to judge, in the words they will read.

    Both records are named, because somebody deciding whether two things are one thing has to
    know which two, and `review_page` is what guarantees they reach both.

    No score, no confidence, no stage number and no weight. The evidence is a list of sentences
    and the only figures on the type are the weight table's version and whether anything
    measured it, which are facts about the evidence rather than quantities to compare.
    """

    item_id: str
    left: SourceRef
    right: SourceRef
    #: `guardrails.Evidence.render`'s output, strongest first. Not rebuilt here.
    lines: tuple[str, ...]
    #: Which weight table produced those sentences.
    weight_version: str
    #: Whether that table came from a calibration export. False for everything declared here.
    calibrated: bool


@dataclass(frozen=True)
class ReviewPage:
    """One reviewer's queue and the figures above it.

    Every figure is computed from `cards` and from nothing else. There is no total, no hidden
    count, no truncation flag and no alarm carrying a number, and the check that keeps it that
    way is `brain.ops.jobs.hidden_count_fields` run over this type.

    `by_strongest` counts the cards by the strength of their best piece of evidence, which is a
    count of things the reader is already looking at. Every band is a key, including the ones at
    nought, for the reason `brain.ops.jobs.DeadLetterSummary` names every reason: a caller
    writing `by_strongest.get(Strength.DECISIVE, 0)` reads as though that band were optional.
    """

    reviewer_id: str
    cards: tuple[ReviewCard, ...]
    by_strongest: Mapping[Strength, int]


def card_for(item: ReviewItem, *, weights: WeightTable = DECLARED_WEIGHTS) -> ReviewCard:
    """One review item as a card (M14.6.4).

    `item.explain()` renders the lines, which is `guardrails.Evidence.render` one call down, and
    it is not reimplemented here for the reason that module gives about having one renderer:
    the rule that a reviewer sees a band and not a number would otherwise hold in one of two
    places.

    The weight table is a parameter and is not read from the evidence, because an `Evidence`
    carries a weight and not the table it came from. That means a caller can hand over a table
    that did not produce these weights, which is a real hole and the smaller of the two: the
    alternative is putting the table's version on every `Evidence`, which is a field on the type
    that exists to hold nothing a reviewer reads.
    """
    return ReviewCard(
        item_id=item.item_id,
        left=item.left,
        right=item.right,
        lines=item.explain(),
        weight_version=weights.version,
        calibrated=weights.calibrated,
    )


def _strongest(item: ReviewItem) -> Strength:
    """The best piece of evidence on this item, or `AGAINST` when there is none.

    `AGAINST` for an item with no evidence at all rather than a fourth value, because an item
    with nothing on it is one a reviewer has no reason to merge, which is what that band says.
    """
    return max((one.strength for one in item.evidence), default=Strength.AGAINST)


def review_page(
    items: Sequence[ReviewItem],
    *,
    reviewer_id: str,
    reaches: MemberReach,
    weights: WeightTable = DECLARED_WEIGHTS,
) -> ReviewPage:
    """The queue as one reviewer may see it, with the figures above it (M14.6.4).

    The filter is `guardrails.review_queue` and it runs first. Not a copy of the conjunction and
    not a second call to `reaches` here: a second implementation of who may see an item is a
    second place for it to be wrong, and the permissive copy is the one that wins the day they
    disagree.

    The counting happens afterwards, over the queue that filter returned. See
    `A_PAGE_BUILT_FROM_WHAT_A_READER_SEES_CANNOT_DESCRIBE_WHAT_THEY_DO_NOT`.
    """
    visible = review_queue(items, reviewer_id=reviewer_id, reaches=reaches)
    counts = dict.fromkeys(Strength, 0)
    for item in visible.items:
        counts[_strongest(item)] += 1
    return ReviewPage(
        reviewer_id=visible.reviewer_id,
        cards=tuple(card_for(one, weights=weights) for one in visible.items),
        by_strongest=MappingProxyType(counts),
    )


#: The types a reviewer's screen renders. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`: a type added to this surface and not to this tuple is a
#: type the disclosure check never sees, and the whole value of that check is that it is asked
#: of everything a screen shows.
REVIEW_SURFACE: Final[tuple[type, ...]] = (ReviewCard, ReviewPage)
