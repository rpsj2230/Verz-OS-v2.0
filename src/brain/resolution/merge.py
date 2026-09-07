"""Merging two entities is a permission event, and every shape here is built against that.

`brain.resolution.canonical` says what a merge may show a reader. `brain.resolution.cascade`
says whether two records look like one thing. This is the module that performs the merge, and
the thing it has to keep in view is the sentence `canonical` opens with: **merging two records
merges two permission surfaces.** Everybody who reaches A now reaches whatever the merged
entity gathers, and nobody writes that deliberately, it arrives as a helpful union.

**Money is where that stops being a data-quality problem, and the refusal is structural rather
than a threshold (M14.5.6).** An entity carrying financial records is somebody's contract value,
somebody's invoice and somebody's margin, and merging it into an entity a whole department
reaches hands that department the money. So there is no confidence at which this module will
merge such a pair automatically, and "auto-merge with money above 0.99" is not a sentence that
can be written here: `AutomaticMerge` refuses construction when either side's money answer is
not `NO_FINANCIAL_RECORDS_FOUND`, there is no threshold parameter anywhere on the automatic
path, and the refusal never reads the confidence. `brain.memory.tiers` classifies
`Change.MONEY_BOUNDARY_MERGE` as `Tier.GATED`, which is that system saying a person decides;
this module is where that classification becomes a shape rather than a policy. See
`A_MONEY_BOUNDARY_MERGE_IS_NOT_A_CONFIDENCE_PROBLEM`. The refusal routes rather than dead ends:
`money_review_item` turns it into a `guardrails.ReviewItem`, which reaches a person only
through `guardrails.review_queue` and its reach filter, because a rule that refuses and offers
nowhere to go is a rule somebody deletes the first time a queue of real clients stops
resolving.

**"Not checked" is a third answer and it refuses like the first.** A boolean would let a caller
who never looked express "no money" by passing False, which is the answer a hurried integration
gives. `MoneyBearing` has three members, the absence of a check is one of them, and only
`NO_FINANCIAL_RECORDS_FOUND` admits an automatic merge. The two sets are written out rather
than derived from each other, so adding a member without deciding which side it falls on fails
`merge_gaps`. See `NOT_CHECKED_IS_AN_ANSWER_AND_IT_IS_A_REFUSAL`.

**An automatic merge cannot exist without a cascade match behind it.** `AutomaticMerge` carries
a `cascade.CascadeResult` rather than a confidence, and refuses one whose decision is not
`MATCHED`. There is no float to hand over, so a caller cannot invent a number, and a pair the
cascade sent to a person cannot be merged automatically by a caller who read the wrong field.

**A merge writes one pointer, and the absence of a source write is a shape (M14.5.2).**
`MergeOutcome` carries the entity that stops being current, its pre-image, an audit and a list
of invalidations. It has no field for a link, an alias, an identifier or a source record
outside the pre-image, so there is nowhere to put a rewritten row, and the one entity it does
carry differs from its pre-image in exactly `merged_into` and `merged_at`. That is
`canonical.A_MERGE_MOVES_ONE_POINTER_AND_NOTHING_ELSE` expressed as a type rather than as a
convention a later author has to keep. See `THERE_IS_NOWHERE_HERE_TO_PUT_A_REWRITTEN_ROW`.

**The pre-image and the unmerge are one property, not two (M14.5.1, M14.5.3).** An unmerge that
cannot restore is a merge that cannot be undone, and a merge nobody can undo is one nobody
should make automatically. So the pre-image is a required field of the outcome, which is what
"captured before any change" means when the function is pure, and `unmerge` restores from it
rather than recomputing: its signature takes the pre-image and the entity graph and has **no
parameter through which a current link, alias or identifier could arrive**. That is
`guardrails.unresolved_for`'s construction applied to a different failure. The case that
settles it is two entities sharing an alias: a recompute keyed on the observed name sees one
name and cannot say which of the two rows belonged to which entity, and a recompute that
gathers the family attaches both to the survivor. The pre-image holds two rows with two
sources and two entity ids, and gives them back unchanged. See
`AN_UNMERGE_RESTORES_AND_DOES_NOT_RECOMPUTE`.

**Everything an id was a key for has to be invalidated, including the id that lost (M14.5.5).**
An id issued before a merge still resolves, which is `canonical`'s M14.1.5, and that is exactly
why a cache keyed on the loser's id would go on serving the pre-merge view for as long as its
entry lives. So the invalidation covers every id in both families rather than the survivor's,
and it names three surfaces because there are three places a resolved view is held: the cache,
memory, and the projection. Each surface names a module that exists, checked by `merge_gaps`
rather than asserted here.

**The audit is who, when, on what evidence, and it carries no values (M14.5.4).** The evidence
is `guardrails.Evidence`, which has a field name and a weight and nowhere to put what the field
said, so a merge audit is readable by an auditor without being a copy of the two records. Who
is read off the authority rather than passed separately, so an audit cannot name somebody the
authority does not.

Rejected: an `approved: bool` on one merge function, with the money rule as a condition inside
it. That is one `if` between a department and a client's contract value, it reads as
equivalent, and the version that decays is the one where somebody adds `or confidence > 0.99`
to clear a backlog. Two authority types with the refusal in a constructor cannot be widened
without deleting a check in a frozen dataclass, which is visible in review.

Rejected: rewriting the child rows to point at the survivor, which is faster to read. It
destroys the only copy of where each row came from, so an unmerge has nothing to restore from.
`canonical` rejects it for the same reason and this module would have been where it happened.

Scope: domain logic. Nothing here opens a connection, reads a clock, writes a row or clears a
cache. `Invalidation` is the instruction and not the eviction, in the split
`brain.ops.limits` and `brain.ops.limit_store` keep.

Task ids: M14.5.1, M14.5.2, M14.5.3, M14.5.4, M14.5.5, M14.5.6
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.resolution.canonical import (
    Alias,
    CanonicalEntity,
    Identifier,
    Link,
    ResolutionError,
    family_of,
)
from brain.resolution.cascade import CascadeResult, Decision
from brain.resolution.guardrails import Evidence, ReviewItem

# ------------------------------------------------------------------ written-down reasons
#: Why money is a structural refusal and not a very high threshold.
A_MONEY_BOUNDARY_MERGE_IS_NOT_A_CONFIDENCE_PROBLEM = (
    "Merging two entities merges two permission surfaces, and when one of them carries "
    "financial records the surface being widened is somebody's contract value, invoice or "
    "margin. Being more certain that the two records are one client does not make it safer to "
    "hand a department a number it was never granted: the confidence is a belief about "
    "identity and the exposure is a fact about access, and no amount of the first bounds the "
    "second. So the refusal is in a constructor and not in a comparison. There is no "
    "threshold parameter on the automatic path to raise, the refusal never reads the "
    "confidence, and 'auto-merge with money above 0.99' is not an expression this module "
    "admits. brain.memory.tiers puts Change.MONEY_BOUNDARY_MERGE at Tier.GATED, which is the "
    "learning system saying a person decides; this is where that becomes a shape. A person can "
    "still merge such a pair, through ReviewedMerge, which is the point: the rule is that "
    "nothing merges it unattended, not that it can never be merged."
)

#: Why the money question has three answers rather than two.
NOT_CHECKED_IS_AN_ANSWER_AND_IT_IS_A_REFUSAL = (
    "A boolean has no way to say 'nobody looked'. A caller who has not wired up the financial "
    "connector passes False, which reads as 'no money here' and is the answer a hurried "
    "integration gives on every entity in the estate, and the guard is then off everywhere "
    "with nothing reporting it. Three members, and the absence of a check refuses exactly as "
    "the presence of money does. The two sets are written out rather than one being derived as "
    "the complement of the other, for the reason brain.memory.tiers.CHANGES_WHAT_ANYBODY_MAY_"
    "SEE is written out: derived, a new member joins whichever side the derivation happens to "
    "put it on, and the side that admits merges is the dangerous one."
)

#: Why there is no field anywhere here that could hold a rewritten source record.
THERE_IS_NOWHERE_HERE_TO_PUT_A_REWRITTEN_ROW = (
    "The source system's record is not ours to edit, and a resolution that rewrote one would "
    "be both unexplainable and unreversible: the row no longer says where it came from, so "
    "nothing can say what it looked like before. A rule saying so is a rule somebody has to "
    "remember. MergeOutcome instead has no field for a link, an alias, an identifier or a "
    "source record outside the pre-image, and the single entity it carries is the loser with "
    "merged_into and merged_at written and every other field the same object it already was. "
    "A later author wanting to rewrite a child row would have to add a field to a frozen type "
    "whose docstring argues against it, which is a visible change in review rather than a "
    "quiet one inside a loop."
)

#: Why an unmerge is handed the pre-image and not the current rows.
AN_UNMERGE_RESTORES_AND_DOES_NOT_RECOMPUTE = (
    "M14.5.1 and M14.5.3 are one property. An unmerge that cannot restore is a merge that "
    "cannot be undone, and a merge nobody can undo is one nobody should make automatically. "
    "The version that decays recomputes: it walks the family, gathers the rows that now "
    "resolve to the survivor and works out which belonged to which entity. That works until "
    "the two entities shared an alias, which is the ordinary case rather than an exotic one, "
    "because two systems holding one client usually hold one name for it. A recompute keyed on "
    "the observed name sees one name and cannot say which row belonged to which entity, and a "
    "recompute that gathers the family attaches both rows to the survivor. So unmerge takes "
    "the pre-image and the entity graph and has no parameter a current link, alias or "
    "identifier could arrive through: recomputing is not something this function declines to "
    "do, it is something it has no inputs for. That is guardrails.unresolved_for's signature "
    "guard applied to a different failure."
)

#: Why the losing entity's id is invalidated as well as the survivor's.
AN_ID_ISSUED_BEFORE_A_MERGE_IS_STILL_A_CACHE_KEY = (
    "A merge moves a pointer and rewrites nothing, which is what makes an id issued before one "
    "go on resolving afterwards. That property is exactly why the loser's id is still a live "
    "key: a cache entry, a memory row or a projection keyed on it answers from before the "
    "merge, and it answers confidently. So the invalidation covers every id in both families "
    "rather than the surviving one, and the natural implementation, which invalidates what the "
    "merge wrote, invalidates the one id nobody was asking with."
)

#: The gap this module does not close, kept as a constant so it has to be deleted.
NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM = (
    "No route, worker or job calls merge or unmerge. Nothing outside brain.resolution imports "
    "this module, there is no er.merge_audit table and no migration creating one, no "
    "pre-image is persisted anywhere, and no cache has ever been cleared by an Invalidation "
    "this module produced. The call site that would have to exist is a resolver service that "
    "holds the entity graph, calls cascade over a candidate pair, hands the result to "
    "AutomaticMerge and writes the outcome's one pointer inside a transaction with the audit "
    "row. That service is not in this repository. Everything here is callable and nothing "
    "calls it, which is the same sentence cascade and normalise say about their own halves."
)


# ------------------------------------------------------- the money boundary (M14.5.6)
class MoneyBearing(enum.StrEnum):
    """Whether one entity carries financial records, including the answer "nobody looked".

    Three members and not a boolean. See `NOT_CHECKED_IS_AN_ANSWER_AND_IT_IS_A_REFUSAL`.

    The fact is asserted by whatever knows: `brain.connectors.xero` holds invoices and
    `brain.connectors.laravel` holds the contract value, and both classify those fields as
    RESTRICTED already. Nothing here infers it, for the reason `cascade.Observation.verified`
    is asserted rather than inferred: an inferred money answer would make the sharpest guard in
    the package a guess.
    """

    #: Invoices, contract values, margins. The answer that refuses.
    CARRIES_FINANCIAL_RECORDS = "carries financial records"
    #: Somebody asked a system that would know, and it said no.
    NO_FINANCIAL_RECORDS_FOUND = "no financial records found"
    #: Nobody asked. Refuses exactly as the first one does.
    NOT_CHECKED = "not checked"


#: The money answers that let a merge happen with nobody looking.
#:
#: One member, and the set exists so that the rule is a lookup rather than a comparison
#: somebody can widen with an `or`.
MONEY_ANSWERS_THAT_ADMIT_AN_AUTOMATIC_MERGE: frozenset[MoneyBearing] = frozenset(
    {MoneyBearing.NO_FINANCIAL_RECORDS_FOUND}
)

#: The money answers that send the pair to a person.
#:
#: Written out rather than derived as the complement of the set above. Derived, the two would
#: agree by construction and a new member would join the admitting side or the refusing side by
#: accident; written out, `merge_gaps` reports a member that is on neither side or on both.
MONEY_ANSWERS_THAT_REFUSE_AN_AUTOMATIC_MERGE: frozenset[MoneyBearing] = frozenset(
    {MoneyBearing.CARRIES_FINANCIAL_RECORDS, MoneyBearing.NOT_CHECKED}
)


@dataclass(frozen=True)
class MoneyCheck:
    """What was asked about each side's financial records, and what came back.

    Both sides, because a merge is symmetric in the thing that matters: the department that
    reaches the entity with no money is exactly who ends up reaching the one that has it.
    """

    left: MoneyBearing
    right: MoneyBearing

    @property
    def permits_automatic(self) -> bool:
        """Whether an unattended merge is allowed to proceed on these two answers."""
        return (
            self.left in MONEY_ANSWERS_THAT_ADMIT_AN_AUTOMATIC_MERGE
            and self.right in MONEY_ANSWERS_THAT_ADMIT_AN_AUTOMATIC_MERGE
        )


# --------------------------------------------------------- who is merging (M14.5.4, M14.5.6)
@dataclass(frozen=True)
class AutomaticMerge:
    """A merge nobody looked at, carrying the cascade result that justifies it.

    **There is no confidence field**, and that is the guard rather than the tidiness. The
    confidence is read off `decision`, which has to be a `MATCHED` result, so a caller cannot
    invent a number and cannot merge a pair the cascade handed to a person by reading the wrong
    field. See `cascade.CascadeResult`, whose own constructor already refuses a match with no
    confidence and a refusal with one.

    **The money refusal is here and it does not read the confidence.** See
    `A_MONEY_BOUNDARY_MERGE_IS_NOT_A_CONFIDENCE_PROBLEM`.
    """

    decision: CascadeResult
    money: MoneyCheck
    #: The job or process performing the merge. A string rather than a principal, for the
    #: reason `canonical.CanonicalEntity.created_by` is one: a backfill is not a person.
    performed_by: str

    def __post_init__(self) -> None:
        if not self.performed_by.strip():
            msg = (
                "an automatic merge with no performed_by is a merge the audit cannot attribute "
                "to anything, and M14.5.4 asks for who as well as when"
            )
            raise ResolutionError(msg)
        if self.decision.decision is not Decision.MATCHED:
            msg = (
                f"the cascade answered {self.decision.decision.value!r} for this pair, so there "
                "is nothing here to merge automatically; a pair in the review band is a "
                "question and merging it unattended answers it without asking anybody"
            )
            raise ResolutionError(msg)
        if not self.decision.evidence:
            msg = (
                "an automatic merge with no evidence is a merge nobody can explain afterwards, "
                "which is the half of M14.5.4 that a pointer and a timestamp do not cover"
            )
            raise ResolutionError(msg)
        if not self.money.permits_automatic:
            msg = (
                f"this pair answers {self.money.left.value!r} and {self.money.right.value!r} "
                "to the money question, and an entity carrying financial records is never "
                "merged with nobody looking, at any confidence. Merging two entities merges "
                "two permission surfaces, and the surface being widened here is a contract "
                "value. A person can decide this one through ReviewedMerge"
            )
            raise ResolutionError(msg)

    @property
    def decided_by(self) -> str:
        return self.performed_by

    @property
    def confidence(self) -> float:
        """What the cascade believed. Never None, because the decision has to be a match."""
        # `CascadeResult` refuses a match with no confidence, so this cannot be None on a
        # value that reached `__post_init__`. Asserted rather than cast, so a change to that
        # invariant fails loudly here instead of putting None into an audit column.
        confidence = self.decision.confidence
        if confidence is None:  # pragma: no cover - CascadeResult refuses this shape
            msg = "a matched cascade result with no confidence cannot be merged on"
            raise ResolutionError(msg)
        return confidence

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        return self.decision.evidence


@dataclass(frozen=True)
class ReviewedMerge:
    """A merge a named person decided, which is the only path money may take.

    No confidence, and its absence is the point: a person did not compute a probability, they
    looked at two records and said they are one thing. Recording a number here would put a
    measured-looking figure on a judgement, on the scale
    `cascade.THE_WEIGHTS_ARE_DECLARED_AND_NOTHING_HAS_CALIBRATED_THEM` says nothing has
    calibrated.

    The money answers are carried and never checked, which is deliberate and is the whole of
    the difference between the two authorities: this type records what was known, and a person
    is allowed to merge across the boundary. `merge_gaps` has no opinion about that either. The
    honest limit is that this module cannot tell a real review from a caller writing a name
    into a string, and the audit is what makes that visible afterwards rather than preventable
    beforehand.
    """

    reviewer_id: str
    #: The review this decision came from, so an auditor can find what the reviewer saw. The
    #: grammar a reference is held to lives in `guardrails`, where a reference is rendered to a
    #: person; here it only has to name something.
    review_ref: str
    money: MoneyCheck
    #: What the reviewer was shown. May be empty: a reviewer who read the two records has
    #: evidence this module never saw, and inventing lines for it would be a fabrication.
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.reviewer_id.strip():
            msg = (
                "a reviewed merge with no reviewer is the automatic path wearing the other "
                "type's name, which is how the money rule would be got round"
            )
            raise ResolutionError(msg)
        if not self.review_ref.strip():
            msg = (
                "a reviewed merge with no review reference cannot be traced back to what the "
                "reviewer was shown, and M14.5.4 asks for the evidence as well as the person"
            )
            raise ResolutionError(msg)

    @property
    def decided_by(self) -> str:
        return self.reviewer_id

    @property
    def confidence(self) -> None:
        """None, always. A person decided; there is no probability to record."""
        return None


#: Who may merge. Two members and no third, so every merge is either unattended and money-free
#: or decided by somebody the audit names.
MergeAuthority = AutomaticMerge | ReviewedMerge


def money_review_item(result: CascadeResult, money: MoneyCheck, *, item_id: str) -> ReviewItem:
    """The pair the money boundary refused, as something a person can be asked about.

    Without this the refusal is a dead end: `cascade.CascadeResult.review_item` deliberately
    refuses anything the cascade decided, because a queue of decided pairs teaches its
    reviewers to approve everything, and a money-blocked pair is a decided pair by that test.
    It is not a decided *merge*, though. The cascade settled the identity question and this
    module refused the merge, so the open question is the one M14.5.6 exists to put in front of
    somebody, and a rule that refuses without routing is a rule that gets deleted the first
    time a queue of real clients stops resolving.

    **Nothing here filters by reach.** `guardrails.review_queue` holds that filter, as a
    conjunction over both halves of the item, and a second copy here would be a second place
    for it to be wrong. The evidence carried is the cascade's, which is field names and weights
    and no values, so an item about a client with invoices names no figure from either record.

    Refuses a pair the money answers would have admitted, because there is nothing to review:
    that pair merges automatically and a review item for it is a question nobody asked.
    """
    if money.permits_automatic:
        msg = (
            "these two answers admit an automatic merge, so there is no money boundary here "
            "for a person to decide about; queueing it would put a settled pair in front of a "
            "reviewer"
        )
        raise ResolutionError(msg)
    if result.decision is not Decision.MATCHED:
        msg = (
            f"the cascade answered {result.decision.value!r}, so the money boundary is not what "
            "stopped this pair; a pair the cascade did not match reaches a person through "
            "cascade.CascadeResult.review_item and its own reason"
        )
        raise ResolutionError(msg)
    return ReviewItem(
        item_id=item_id, left=result.left, right=result.right, evidence=result.evidence
    )


# ------------------------------------------------------------- the pre-image (M14.5.1)
@dataclass(frozen=True)
class PreImage:
    """Every row the merge could affect, as it stood before the merge.

    The two entities and every link, alias and identifier belonging to either family. Rows
    rather than ids, and the same objects that were handed in rather than copies, so a
    restoration can be compared against this by identity and not merely by value.

    The family rather than the entity, because either side may already be the survivor of an
    earlier merge and its rows still name the entity they were written against. That is
    `canonical.family_of`, imported rather than walked again here.
    """

    survivor: CanonicalEntity
    merged: CanonicalEntity
    links: tuple[Link, ...]
    aliases: tuple[Alias, ...]
    identifiers: tuple[Identifier, ...]

    @property
    def entity_ids(self) -> frozenset[str]:
        """Every entity id the captured rows name, plus the two entities themselves."""
        return frozenset(
            {self.survivor.entity_id, self.merged.entity_id}
            | {one.entity_id for one in self.links}
            | {one.entity_id for one in self.aliases}
            | {one.entity_id for one in self.identifiers}
        )


def capture_pre_image(
    *,
    survivor_id: str,
    merged_id: str,
    entities: Mapping[str, CanonicalEntity],
    links: Sequence[Link] = (),
    aliases: Sequence[Alias] = (),
    identifiers: Sequence[Identifier] = (),
) -> PreImage:
    """Everything a merge of these two could affect, before anything is changed (M14.5.1).

    Sorted, so two captures of one graph are the same value and a stored pre-image can be
    compared with a later one without the order of a query result being the difference.

    Rows belonging to other entities are ignored rather than refused, so a caller may hand over
    a whole batch. The quiet failure worth naming is the mirror of
    `guardrails.cap_breaches`': a caller that hands over the wrong batch gets a pre-image with
    nothing in it, and nothing here can tell that from an entity that genuinely has no aliases.
    """
    family = family_of(survivor_id, entities) | family_of(merged_id, entities)
    return PreImage(
        survivor=entities[survivor_id],
        merged=entities[merged_id],
        links=tuple(
            sorted(
                (one for one in links if one.entity_id in family),
                key=lambda one: (one.entity_id, one.source.sort_key()),
            )
        ),
        aliases=tuple(
            sorted(
                (one for one in aliases if one.entity_id in family),
                key=lambda one: (one.entity_id, one.name, one.source.sort_key()),
            )
        ),
        identifiers=tuple(
            sorted(
                (one for one in identifiers if one.entity_id in family),
                key=lambda one: (one.entity_id, one.kind.value, one.key_hash),
            )
        ),
    )


# --------------------------------------------------------- invalidation (M14.5.5)
class InvalidatedSurface(enum.StrEnum):
    """Where a resolved view is held, and therefore where a merge makes one stale.

    Three, and each names a subsystem that exists rather than a category somebody imagined:
    see `SURFACE_MODULES`, which `merge_gaps` checks against the import system.
    """

    #: `brain.cache`. Answers held against a question, which a merge changes the answer to.
    CACHE = "cache"
    #: `brain.memory`. Learnt links and preferences attached to an entity id.
    MEMORY = "memory"
    #: `brain.connectors.projection`. The per-record rows a resolved view is assembled from.
    PROJECTION = "projection"


#: Which module each surface is. Checked against the import system rather than trusted.
#:
#: The check is what stops this being three words somebody chose: a surface naming a module
#: that does not exist is an invalidation nobody will ever act on, and it would read exactly
#: like one that works.
SURFACE_MODULES: Mapping[InvalidatedSurface, str] = MappingProxyType(
    {
        InvalidatedSurface.CACHE: "brain.cache",
        InvalidatedSurface.MEMORY: "brain.memory",
        InvalidatedSurface.PROJECTION: "brain.connectors.projection",
    }
)


@dataclass(frozen=True)
class Invalidation:
    """One instruction: this surface holds something about this entity id and it is now stale.

    A surface and an id, and nothing else. No count of the entries it will drop, because a
    count of what a merge invalidated is a count of what somebody had cached about an entity,
    and no record value, because this is an instruction rather than a payload.

    The instruction and not the eviction. Nothing here opens a connection, in the split
    `brain.ops.limits` and `brain.ops.limit_store` keep.
    """

    surface: InvalidatedSurface
    entity_id: str

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            msg = "an invalidation naming no entity tells a cache to drop nothing in particular"
            raise ResolutionError(msg)


def invalidations_for(
    *,
    survivor_id: str,
    merged_id: str,
    entities: Mapping[str, CanonicalEntity],
    surfaces: Sequence[InvalidatedSurface] = tuple(InvalidatedSurface),
) -> tuple[Invalidation, ...]:
    """Every surface and every id a merge of these two makes stale (M14.5.5).

    Both families, not the survivor. See `AN_ID_ISSUED_BEFORE_A_MERGE_IS_STILL_A_CACHE_KEY`.

    `surfaces` is a parameter so a test can hand over a set that is missing one, for the reason
    `guardrails.guardrail_gaps` takes its caps as a parameter: a function that always returns
    every surface returns every surface whether or not it is still asking the enumeration.
    """
    ids = family_of(survivor_id, entities) | family_of(merged_id, entities)
    return tuple(
        sorted(
            (
                Invalidation(surface=surface, entity_id=entity_id)
                for surface in surfaces
                for entity_id in ids
            ),
            key=lambda one: (one.surface.value, one.entity_id),
        )
    )


# ------------------------------------------------------------------- the audit (M14.5.4)
@dataclass(frozen=True)
class MergeAudit:
    """Who merged two entities, when, and on what evidence.

    `decided_by`, `confidence` and `evidence` are read off the authority rather than passed
    beside it, so an audit cannot name a person the authority does not or record evidence the
    authority never had. The evidence is `guardrails.Evidence`, which carries a field name and
    a weight and has nowhere to put what the field said.
    """

    merge_id: str
    survivor_id: str
    merged_id: str
    decided_at: datetime
    authority: MergeAuthority
    #: Why, in words, for the auditor who is not going to read a weight table.
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.merge_id.strip():
            msg = "a merge audit with no id cannot be cited by the unmerge that reverses it"
            raise ResolutionError(msg)
        if self.decided_at.tzinfo is None:
            msg = "a naive decided_at compares wrongly against an aware one"
            raise ResolutionError(msg)

    @property
    def decided_by(self) -> str:
        return self.authority.decided_by

    @property
    def automatic(self) -> bool:
        return isinstance(self.authority, AutomaticMerge)

    @property
    def confidence(self) -> float | None:
        """What the cascade believed, or None where a person decided."""
        return self.authority.confidence

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        return self.authority.evidence


@dataclass(frozen=True)
class UnmergeAudit:
    """Who reversed a merge, when, why, and which merge it was.

    `merge_id` rather than a copy of the merge audit, so the two rows are one story and an
    unmerge cannot describe a merge that did not happen the way it says.
    """

    unmerge_id: str
    merge_id: str
    survivor_id: str
    restored_id: str
    reversed_at: datetime
    performed_by: str
    reason: str

    def __post_init__(self) -> None:
        if not self.performed_by.strip():
            msg = (
                "an unmerge with no performed_by is an entity coming back with nobody's name "
                "on it, which is the audit question the merge answered and the unmerge did not"
            )
            raise ResolutionError(msg)
        if not self.reason.strip():
            msg = (
                "an unmerge with no reason cannot be told from a mistake; the merge it "
                "reverses was recorded with its evidence and this has to be recorded with its"
            )
            raise ResolutionError(msg)
        if self.reversed_at.tzinfo is None:
            msg = "a naive reversed_at compares wrongly against an aware one"
            raise ResolutionError(msg)


# ------------------------------------------------------------------- merging (M14.5.2)
@dataclass(frozen=True)
class MergeOutcome:
    """What a merge produced: one changed entity, the pre-image, the audit and what to clear.

    **There is no field here for a link, an alias, an identifier or a source record**, outside
    the pre-image that exists to be restored from. See
    `THERE_IS_NOWHERE_HERE_TO_PUT_A_REWRITTEN_ROW`.

    There is no survivor either, and its absence says the same thing: a merge does not change
    the surviving entity, so handing it back would invite a caller to write a row that has not
    changed. `audit.survivor_id` names it.
    """

    #: The entity that stops being current, with `merged_into` and `merged_at` written and
    #: every other field exactly what it already was.
    merged: CanonicalEntity
    pre_image: PreImage
    audit: MergeAudit
    invalidations: tuple[Invalidation, ...]

    def __post_init__(self) -> None:
        if self.merged.entity_id != self.audit.merged_id:
            msg = "the entity this outcome writes is not the one the audit says was merged"
            raise ResolutionError(msg)
        if self.merged.merged_into != self.audit.survivor_id:
            msg = (
                "the pointer this outcome writes does not name the survivor the audit records, "
                "so the graph and the audit trail would disagree about what happened"
            )
            raise ResolutionError(msg)
        if self.merged.merged_at != self.audit.decided_at:
            msg = "the entity stopped being current at a different time than the audit records"
            raise ResolutionError(msg)


def merge(
    *,
    survivor_id: str,
    merged_id: str,
    entities: Mapping[str, CanonicalEntity],
    authority: MergeAuthority,
    at: datetime,
    merge_id: str,
    links: Sequence[Link] = (),
    aliases: Sequence[Alias] = (),
    identifiers: Sequence[Identifier] = (),
    reason: str = "",
) -> MergeOutcome:
    """Merge one entity into another, as a pointer move and nothing else (M14.5.1 to M14.5.5).

    The pre-image is captured first, which is what "before any change" means for a function
    that changes nothing in place: the outcome cannot exist without one, because `MergeOutcome`
    requires it.

    Four refusals, and each is a shape the graph could not recover from:

    - merging an entity into itself, which is a one-hop cycle `canonical` also refuses;
    - merging into a stub, because the result would resolve past the entity the audit names;
    - merging a stub, because writing a second pointer over the first destroys an earlier merge
      and leaves that merge's pre-image describing a graph that no longer exists;
    - merging two entities of different types, because a company and a person gathered under
      one id give every one of the loser's records the survivor's type.

    The money rule is not checked here and that is deliberate: it is checked where
    `AutomaticMerge` is built, so a caller cannot reach this function with an automatic
    authority that crosses the boundary. A check here as well would be a second copy of the
    rule, and the copy that is wrong is the one in production.
    """
    if survivor_id == merged_id:
        msg = (
            f"{survivor_id!r} cannot be merged into itself; following the pointer would never "
            "reach a surviving entity"
        )
        raise ResolutionError(msg)
    for entity_id in (survivor_id, merged_id):
        if entity_id not in entities:
            msg = f"{entity_id!r} is not an entity in this graph, so nothing can be merged to it"
            raise ResolutionError(msg)
    if at.tzinfo is None:
        msg = "a naive merge timestamp compares wrongly against an aware one"
        raise ResolutionError(msg)

    survivor = entities[survivor_id]
    loser = entities[merged_id]
    if not survivor.is_current:
        msg = (
            f"{survivor_id!r} is itself merged into something else, so merging into it would "
            "resolve past the entity this audit names and the trail would not describe the "
            "graph"
        )
        raise ResolutionError(msg)
    if not loser.is_current:
        msg = (
            f"{merged_id!r} is already merged; writing a second pointer over the first "
            "destroys the earlier merge and leaves its pre-image describing a graph that no "
            "longer exists, which is an unmerge that cannot restore"
        )
        raise ResolutionError(msg)
    if survivor.entity_type is not loser.entity_type:
        msg = (
            f"{survivor.entity_type.value} and {loser.entity_type.value} are not the same kind "
            "of thing; gathering them under one id gives every one of the merged entity's "
            "records the survivor's type"
        )
        raise ResolutionError(msg)

    pre_image = capture_pre_image(
        survivor_id=survivor_id,
        merged_id=merged_id,
        entities=entities,
        links=links,
        aliases=aliases,
        identifiers=identifiers,
    )
    return MergeOutcome(
        merged=dataclasses.replace(loser, merged_into=survivor_id, merged_at=at),
        pre_image=pre_image,
        audit=MergeAudit(
            merge_id=merge_id,
            survivor_id=survivor_id,
            merged_id=merged_id,
            decided_at=at,
            authority=authority,
            reason=reason,
        ),
        invalidations=invalidations_for(
            survivor_id=survivor_id, merged_id=merged_id, entities=entities
        ),
    )


# ----------------------------------------------------------------- unmerging (M14.5.3)
@dataclass(frozen=True)
class Restoration:
    """The graph as the pre-image says it was, plus the audit of who put it back.

    Every row here came off the pre-image. Nothing was recomputed and nothing was rebuilt from
    the current graph, which is why a caller can compare a restoration against the pre-image by
    identity. See `AN_UNMERGE_RESTORES_AND_DOES_NOT_RECOMPUTE`.
    """

    entities: tuple[CanonicalEntity, ...]
    links: tuple[Link, ...]
    aliases: tuple[Alias, ...]
    identifiers: tuple[Identifier, ...]
    audit: UnmergeAudit
    invalidations: tuple[Invalidation, ...]


def unmerge(
    pre_image: PreImage,
    *,
    entities: Mapping[str, CanonicalEntity],
    merge_id: str,
    unmerge_id: str,
    at: datetime,
    performed_by: str,
    reason: str,
) -> Restoration:
    """Put back exactly what the pre-image recorded (M14.5.3).

    **There is no parameter here through which a current link, alias or identifier could
    arrive**, so this function has no inputs to recompute from. See
    `AN_UNMERGE_RESTORES_AND_DOES_NOT_RECOMPUTE`.

    `entities` is present and is used for one thing only: refusing to reverse a merge that is
    not the one currently in force. An unmerge run against a graph where the entity has since
    been merged somewhere else would clear a pointer somebody else wrote, and the pre-image it
    restores from would describe a state two merges ago.
    """
    merged_id = pre_image.merged.entity_id
    survivor_id = pre_image.survivor.entity_id
    if merged_id not in entities:
        msg = (
            f"{merged_id!r} is not in this graph, so the merge this pre-image records cannot "
            "be the one in force and reversing it would restore a state nothing is in"
        )
        raise ResolutionError(msg)
    current = entities[merged_id]
    if current.merged_into != survivor_id:
        msg = (
            f"{merged_id!r} is not currently merged into {survivor_id!r}, so this pre-image "
            "does not describe the merge in force; clearing the pointer would reverse somebody "
            "else's merge and restore a state two merges ago"
        )
        raise ResolutionError(msg)
    if at.tzinfo is None:
        msg = "a naive unmerge timestamp compares wrongly against an aware one"
        raise ResolutionError(msg)

    return Restoration(
        entities=(pre_image.survivor, pre_image.merged),
        links=pre_image.links,
        aliases=pre_image.aliases,
        identifiers=pre_image.identifiers,
        audit=UnmergeAudit(
            unmerge_id=unmerge_id,
            merge_id=merge_id,
            survivor_id=survivor_id,
            restored_id=merged_id,
            reversed_at=at,
            performed_by=performed_by,
            reason=reason,
        ),
        invalidations=invalidations_for(
            survivor_id=survivor_id, merged_id=merged_id, entities=entities
        ),
    )


# ------------------------------------------------------------------------- the gaps
def merge_gaps(
    admitting: frozenset[MoneyBearing] = MONEY_ANSWERS_THAT_ADMIT_AN_AUTOMATIC_MERGE,
    refusing: frozenset[MoneyBearing] = MONEY_ANSWERS_THAT_REFUSE_AN_AUTOMATIC_MERGE,
    surfaces: Mapping[InvalidatedSurface, str] = SURFACE_MODULES,
) -> tuple[str, ...]:
    """Every place the tables in this module disagree with each other or with the vocabulary.

    Every table is a parameter, for the reason `guardrails.guardrail_gaps` takes its caps as
    one: a detector that only fires when the tables disagree returns nothing on a healthy tree
    whether or not it is still doing anything.

    The check worth having is the third. A money answer on both sides, or on neither, is a
    member somebody added without deciding what it means, and the failure mode is silent in the
    dangerous direction: on neither, `permits_automatic` says no and merges stop happening,
    which somebody notices; on both, the set that admits automatic merges has grown a member
    and nothing anywhere says so.
    """
    gaps: list[str] = []

    for surface in InvalidatedSurface:
        if surface not in surfaces:
            gaps.append(
                f"the {surface.value} surface names no module, so an invalidation for it is an "
                "instruction with no addressee and nothing will ever act on one"
            )

    for answer in MoneyBearing:
        in_both = answer in admitting and answer in refusing
        in_neither = answer not in admitting and answer not in refusing
        if in_both:
            gaps.append(
                f"the money answer {answer.value!r} both admits and refuses an automatic "
                "merge, so which it does depends on which set a reader happens to consult"
            )
        elif in_neither:
            gaps.append(
                f"the money answer {answer.value!r} is on neither side, so nobody has decided "
                "whether it lets a merge happen with nobody looking"
            )

    if MoneyBearing.CARRIES_FINANCIAL_RECORDS in admitting:
        gaps.append(
            "an entity carrying financial records is in the set that admits an automatic "
            "merge, which is M14.5.6 inverted: a contract value becomes visible to whoever "
            "reaches the other side, with nobody having looked"
        )

    return tuple(gaps)


#: How many entities one merge changes. One, and the one is the whole of M14.5.2.
#:
#: Written down as a figure a test can assert the outcome against rather than as a sentence,
#: because "a pointer move" is checkable only if somebody counts the rows that moved.
ENTITIES_WRITTEN_BY_ONE_MERGE: Final = 1

#: Which fields of that entity a merge is allowed to write.
#:
#: The two halves of the forwarding pointer, and `canonical.CanonicalEntity` already refuses one
#: without the other. A test holds the difference between the pre-image entity and the merged
#: one against this set, so a merge that touched anything else fails rather than being reviewed
#: for.
FIELDS_WRITTEN_BY_ONE_MERGE: frozenset[str] = frozenset({"merged_into", "merged_at"})
