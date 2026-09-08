"""What one person put into the system, and what came back out of it for them.

`brain.console.own_things` is this surface seen from the administrator's side and it is the
thing to read first: "their own" is a permission claim rather than a filter, the narrowing is
a `Scope`, and `is_own` is the one predicate. Nothing here writes a second one. What this
module adds is the half a console does not need, which is the acting half: uploading,
replacing, retiring, submitting for review, asking for a promotion, and handing something to
a colleague.

**Ownership admits a row and it is not an entitlement.** `own_knowledge` narrows by
`KnowledgeItem.owner_id` and deliberately does not narrow by visibility level, because an item
somebody uploaded and had promoted is still theirs to steward. That is right for a console
listing what a person is accountable for and it is not enough for a personal library, because
an owner is not automatically a reader: `owner_id` never moves and a department does, so an
item somebody uploaded into a department they have since left is theirs and out of their
reach. `reachable_own_items` is the conjunction, and M40.3.1.5's "including their own
department's restricted rows" is exactly that case. See
`AN_OWNER_IS_NOT_AUTOMATICALLY_A_READER_AND_A_DEPARTMENT_MOVES`.

**A review cycle is set at upload and no later path may drop it.** A document with no review
date is one nobody is ever asked about again, and `brain.knowledge.item` already argues that a
review date nothing reads is documentation rather than a control. So `upload` requires one and
`replace` refuses a successor without one, which is the half that would otherwise be lost:
version one carries a date, version two is uploaded in a hurry, and the item silently leaves
the re-verification sweep while looking newer than it was.

**A usage count on your own document counts reads and never names readers.** M40.3.1.3 asks
whether anything reads what somebody wrote, which is a figure that moves when other people
work, and `brain.console.workspace.A_FIGURE_THAT_MOVES_WHEN_SOMEBODY_ELSE_WORKS_IS_THEIR_
ACTIVITY` is the rule that usually forbids one. It does not forbid this one, and the
difference is attribution: `AuthoredUse` carries an item and a number and there is no
principal anywhere on this surface, so the author learns that their handbook page is read and
never who read it. There is a residual and it is stated rather than papered over: a count of
one against an item only two people can reach narrows the reader to one of two. That is a
property of a small audience rather than of this count, and the alternative, withholding the
figure, is the leaf.

**A promotion request is routed and never granted.** `brain.knowledge.visibility` already
holds the gate: a proposal, then an approval by a second principal holding the capability,
then `apply_promotion`. What M40.3.1.4 adds is the tier, and the tier is read from
`brain.memory.tiers.blast_radius(Change.COMPANY_KNOWLEDGE)` rather than written as three here,
so a `PromotionRequest` cannot claim a tier its own blast radius disagrees with. There is no
approver field on it and no `apply`, following `brain.memory.tiers.
THIS_MODULE_HAS_NOWHERE_TO_APPROVE`.

**Sharing is the only control here that could widen somebody, and it does not.** A share makes
reachable-and-unfound into found. It never makes not-reachable into reachable, and the
mechanism is that `Share` carries no entitlement, no hash, no capability and no token, so
there is nothing on it a read could consult. `open_share` returns
`brain.console.agent_output.may_download`'s answer about the recipient as they are now, and
the share contributes the artifact id and the recipient id and nothing else. **A share is
admitted once and a read is decided every time.** The admission at share time is a refusal to
create a pointer to something the colleague cannot have, which is honesty to the sharer rather
than a permission; the read is `may_download`, asked again, on every open. A colleague whose
entitlement narrows after the share finds a dead pointer; one whose entitlement widens gains
nothing, because they could already have had it. See
`A_SHARE_IS_ADMITTED_ONCE_AND_THE_READ_IS_DECIDED_EVERY_TIME`.

Rejected: accepting a share whose recipient cannot reach the artifact and letting the read
fail later. It is the version with no disclosure in it, and it is the failure
`brain.knowledge.visibility.admit_upload` refuses in the same words: somebody who asked for
one thing and silently received another believes they did it and never checks. The cost of
refusing is real and is named rather than denied: a refusal tells the sharer that this
colleague does not reach this artifact, which is a fact about somebody else's grants. It is
bounded by shape rather than by wording. There is no parameter here naming several colleagues,
no function answering who an artifact could be shared with, and no return value distinguishing
"cannot reach it" from "does not exist", so the surface is a poor oracle to sit and probe. See
`A_REFUSAL_TO_SHARE_NAMES_A_GRANT_AND_MUST_NOT_BECOME_A_PROBE`.

Rejected: a `Share` with an expiry, a revocation or a scope of its own. Each reads as a
control and each is a second permission model beside the entitlement set, and the second one
is the one that ends up deciding. A share is withdrawn by deleting it, exactly as a grant is,
and until then it decides nothing anyway.

**Nothing here removes an artifact and nothing here approves anything.** `brain.console.
agent_output` keeps the row and supersedes or archives; this module has no delete path at all,
and `library_gaps` reports a callable whose name could be read as approving.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything; `now`
and the windows are parameters, as in every module this one calls.

Task ids: M40.3.1.1, M40.3.1.2, M40.3.1.3, M40.3.1.4, M40.3.1.5, M40.3.2.1, M40.3.2.2
Task ids: M40.3.2.3, M40.3.2.4, M40.3.3.1, M40.3.3.2, M40.3.3.3
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from brain.agents.model import AgentRecord
from brain.console.agent_output import (
    NAMES_THAT_WOULD_BE_A_BEARER_TOKEN,
    Artifact,
    may_download,
)
from brain.console.agent_tabs import ItemRetrieval, Review, review_state
from brain.console.own_things import is_own, own_knowledge
from brain.core.department import DEPARTMENT_FIELD
from brain.core.entitlement import EntitlementSet
from brain.knowledge.item import (
    KnowledgeItem,
    KnowledgeState,
    VerificationState,
    badge,
    supersede,
)
from brain.knowledge.visibility import (
    OWNER_FIELD,
    KnowledgeVisibility,
    PromotionProposal,
    Visibility,
    admit_upload,
    propose_promotion,
)
from brain.memory.tiers import Change, Tier, blast_radius
from brain.ops.jobs import hidden_count_fields
from brain.tools.skills import ImportedSkill, SkillSource, SkillState, SourceKind

# ------------------------------------------------------------------ written-down reasons
#: Why a personal library is ownership and reach rather than ownership alone.
AN_OWNER_IS_NOT_AUTOMATICALLY_A_READER_AND_A_DEPARTMENT_MOVES: Final = (
    "brain.console.own_things.own_knowledge narrows by owner and says in its own docstring "
    "that it deliberately does not narrow by visibility level, because an item somebody had "
    "promoted is still theirs to steward. That is right for a list of what a person answers "
    "for and wrong for a list of what they may open, and the two come apart because "
    "owner_id never moves and a department does: an item uploaded into a department somebody "
    "has since left is still owned by them and no longer reachable by them. A personal "
    "library is the conjunction, so ownership decides whose row it is and the item's own "
    "scope decides whether they may read it."
)

#: Why the review cycle cannot be dropped by a later version.
A_REPLACEMENT_WITH_NO_REVIEW_DATE_LEAVES_THE_SWEEP_WITHOUT_ANNOUNCING_IT: Final = (
    "brain.knowledge.item.due_for_reverification skips an item whose review_by is None, "
    "which is correct: an item nobody set a cycle on is not overdue. So a version two "
    "uploaded without one does not become overdue either, it leaves the sweep entirely, and "
    "the console shows a newer document with no date beside it. The absence looks like "
    "freshness and is the opposite. The cycle is therefore required at upload and required "
    "again of any successor, because the successor is the version that will still be there "
    "in a year."
)

#: Why an author may be told how often their document is read.
A_USAGE_COUNT_ON_YOUR_OWN_DOCUMENT_COUNTS_READS_AND_NEVER_NAMES_READERS: Final = (
    "A figure that moves when somebody else works is normally that person's activity, which "
    "is brain.console.workspace's rule and the reason a front page carries a basis. This "
    "figure carries no basis because it carries no attribution: an AuthoredUse is an item "
    "and a number, there is no principal on any shape here, and no function returns a "
    "breakdown by reader. What is left is the question the leaf asks, which is whether "
    "anything reads what this person wrote. The residual is real and is not hidden: one "
    "retrieval of an item only two people can reach narrows the reader to one of two, which "
    "is a property of a small audience rather than of the count, and the alternative is "
    "withholding the only figure that tells an author their work is unread."
)

#: Why a promotion request reads its tier rather than declaring one.
THE_TIER_OF_A_PROMOTION_IS_ITS_BLAST_RADIUS_AND_NOT_THE_ASKERS_OPINION: Final = (
    "Promoting an item to company visibility is brain.memory.tiers.Change.COMPANY_KNOWLEDGE, "
    "which sits in CHANGES_WHAT_ANYBODY_MAY_SEE and is therefore gated. A request that wrote "
    "three into a field would agree with that map on the day it was written and afterwards "
    "only by coincidence, and the direction it drifts is downwards, because the pressure on "
    "this path is always somebody wanting their document published this afternoon. The tier "
    "is read from blast_radius and the request refuses to exist at any other, so lowering "
    "the map fails here rather than publishing quietly."
)

#: Why a share can never be the thing that admits a read.
A_SHARE_IS_ADMITTED_ONCE_AND_THE_READ_IS_DECIDED_EVERY_TIME: Final = (
    "Sharing makes something that was already reachable findable, and it must never make "
    "something reachable. The admission at share time is a refusal to create a pointer to "
    "something the colleague cannot have, which is honesty to the sharer and confers "
    "nothing; the read is may_download asked of the recipient as they are at the moment they "
    "open it. Share therefore carries no entitlement, no hash, no capability and no token, "
    "so a read has nothing on it to consult, and open_share takes the recipient's own set as "
    "the only input to the verdict. A colleague whose grants narrow after the share finds a "
    "pointer to nothing; one whose grants widen gains nothing they did not already have."
)

#: Why the refusal is loud, and the shape that stops it being an oracle.
A_REFUSAL_TO_SHARE_NAMES_A_GRANT_AND_MUST_NOT_BECOME_A_PROBE: Final = (
    "Refusing to share tells the sharer that this colleague does not reach this artifact, "
    "which is a fact about somebody else's grants and is a real cost. The alternative costs "
    "more: a share accepted and silently useless is the failure admit_upload refuses in the "
    "same words, where somebody believes they did a thing and never checks. So the refusal "
    "is loud and the disclosure is bounded by shape instead of by wording. One artifact and "
    "one colleague per call, no parameter naming several, no function anywhere answering who "
    "an artifact could be shared with, and a refusal that names neither the capability nor "
    "the scope, so what a probe learns is one bit per call it has to make by hand."
)


class LibraryError(Exception):
    """A personal library was asked to do something to somebody else's, or to lie about one.

    Outside `brain.core.errors` for the reason `brain.console.own_things.OwnThingsError` is:
    those five outcomes describe an answer given to somebody who asked a question, and this
    is a refusal to operate a control on a personal screen.
    """


# ------------------------------------------------- the reader's own rows (M40.3.1.5)
def _reader_rows(principal_id: str, departments: Iterable[str]) -> tuple[dict[str, str], ...]:
    """This person, as the rows a knowledge item's own scope is tested against.

    The construction `brain.agents.model._viewer_rows` uses against an agent's audience, and
    it is the same question one layer along: both are `brain.knowledge.visibility.scope_for`
    predicates, so a row shaped for one is the row the other needs. One row with no
    department and one per department they sit in, because `Clause.matches` admits no row
    missing the field, so a bare row can never satisfy a department predicate by omission and
    a person in two departments is still one person.
    """
    base = {OWNER_FIELD: principal_id}
    return (base, *({**base, DEPARTMENT_FIELD: one} for one in sorted(set(departments))))


def reaches(item: KnowledgeItem, principal_id: str, departments: Iterable[str]) -> bool:
    """Whether this person's own scope admits this item, by the item's own predicate.

    `KnowledgeItem.scope` is derived from the visibility rather than stored beside it, so
    this asks the item what it means rather than comparing a level here. Any of the person's
    rows matching is enough, for the reason `brain.agents.model.visible_to` gives: requiring
    every row to match would hide a Web document from somebody who is also in Sales.
    """
    return any(item.scope.matches(row) for row in _reader_rows(principal_id, departments))


def reachable_own_items(
    items: Iterable[KnowledgeItem],
    *,
    principal_id: str,
    departments: Iterable[str] = (),
) -> tuple[KnowledgeItem, ...]:
    """This person's own items that this person can also read (M40.3.1.5).

    The conjunction, and the conjunction is the leaf. `own_knowledge` decides whose row it
    is, by the same `Scope` a store would be handed, and `reaches` decides whether the item's
    own predicate admits them. See
    `AN_OWNER_IS_NOT_AUTOMATICALLY_A_READER_AND_A_DEPARTMENT_MOVES`.

    Order follows `items`, for the reason `brain.console.own_things.own_agents` gives: the
    caller's order is usually meaningful and re-sorting discards it.

    Returns what survived and says nothing about the rest. An item somebody owns and cannot
    read is absent rather than greyed out, because a row saying "you own this and may not
    open it" is the department they left printed on their own library page.
    """
    return tuple(
        one
        for one in own_knowledge(items, principal_id=principal_id)
        if reaches(one, principal_id, departments)
    )


# ------------------------------------------------------- the library listing (M40.3.1.1)
@dataclass(frozen=True)
class LibraryEntry:
    """One item on a person's own library page (M40.3.1.1).

    Everything M40.3.1.1 names and nothing else. There is no owner field, because every row
    here is this person's and repeating that on each one is an invitation to render a list
    that is not; and no count of anything, which `library_gaps` asks of the type rather than
    of whoever edits it next.
    """

    item_id: str
    title: str
    #: The scope the item is stored at, in `brain.knowledge.visibility`'s own vocabulary.
    visibility: Visibility
    #: `brain.knowledge.item.badge`'s verdict, never a second reading of the same dates.
    verification: VerificationState
    #: When somebody vouched for it, or `None` when nobody has.
    verified_at: datetime | None
    #: When somebody must look again, or `None` when no cycle was set. See `upload`.
    review_by: datetime | None


def my_library(
    items: Iterable[KnowledgeItem],
    *,
    principal_id: str,
    departments: Iterable[str] = (),
    now: datetime,
) -> tuple[LibraryEntry, ...]:
    """What this person uploaded, with scope, verification and review date (M40.3.1.1).

    Built over `reachable_own_items`, so the listing and M40.3.1.5's rule are one function
    call apart rather than two rules that could disagree. A caller cannot get the wider list
    from here, because there is no parameter that would produce it.

    The verification state is `brain.knowledge.item.badge`'s, so an item reads the same way
    on this page as it does beside an answer that cited it. A second comparison of
    `review_by` against `now` is how a document comes to be due on one screen and current on
    another, which is the failure that makes a badge worse than none.
    """
    return tuple(
        LibraryEntry(
            item_id=one.item_id,
            title=one.title,
            visibility=one.visibility.level,
            verification=badge(one, now=now).state,
            verified_at=one.verified_at,
            review_by=one.review_by,
        )
        for one in reachable_own_items(items, principal_id=principal_id, departments=departments)
    )


# ----------------------------------------- upload, replace and retire (M40.3.1.2)
def upload(
    *,
    item_id: str,
    content: str,
    owner_id: str,
    review_by: datetime,
    now: datetime,
    title: str = "",
    requested: Visibility | None = None,
    uploader_department: str = "",
) -> KnowledgeItem:
    """Add one item to this person's library, at a level the gate admits (M40.3.1.2).

    Three decisions and only one of them is made here. The level is
    `brain.knowledge.visibility.admit_upload`'s, which refuses a request wider than the
    uploader's default rather than quietly narrowing it. The state is `DRAFT`, which is
    `KnowledgeState`'s own "written, not yet vouched for" and the only honest state for
    something nobody has verified. What is decided here is the review cycle: it is required,
    it must be in the future, and no later path may drop it. See
    `A_REPLACEMENT_WITH_NO_REVIEW_DATE_LEAVES_THE_SWEEP_WITHOUT_ANNOUNCING_IT`.

    A cycle already behind us is refused rather than accepted, for the reason
    `brain.knowledge.visibility.propose_promotion` refuses one: the sweep opens a task on the
    day of the upload, the owner is asked to re-verify something nobody has read, and the
    second time that happens the notification stops being read.

    There is no `verified_by` parameter and no `verified_at`. A verification is a person and
    a date and `KnowledgeItem.verified` is the only way one is ever set, so an uploader
    cannot vouch for their own document on the way in.
    """
    if review_by <= now:
        msg = (
            f"{item_id!r} is uploaded with a review date of {review_by.isoformat()}, which "
            "is not in the future; the sweep would open a task on the day it was written. "
            f"{A_REPLACEMENT_WITH_NO_REVIEW_DATE_LEAVES_THE_SWEEP_WITHOUT_ANNOUNCING_IT}"
        )
        raise LibraryError(msg)
    level = admit_upload(requested, uploader_department=uploader_department)
    return KnowledgeItem(
        item_id=item_id,
        content=content,
        title=title,
        visibility=KnowledgeVisibility(
            level=level, owner_id=owner_id, department=uploader_department
        ),
        owner_id=owner_id,
        state=KnowledgeState.DRAFT,
        review_by=review_by,
    )


def replace(
    current: KnowledgeItem, successor: KnowledgeItem
) -> tuple[KnowledgeItem, KnowledgeItem]:
    """Replace one of this person's items with a newer version (M40.3.1.2).

    `brain.knowledge.item.supersede` does the work and both of its refusals stay there: an
    item cannot supersede itself, an already-superseded one cannot be superseded again, and a
    successor may never be wider than what it replaces, which is the line that stops
    supersession being the promotion path. Restating any of them here would be a second
    opinion about a rule that has one.

    What is added is the one thing that module cannot ask, because it takes no view on where
    an item came from: the successor carries a review cycle. Version one is uploaded with a
    date and version two is uploaded in a hurry, and an item with no date is not overdue, it
    is outside the sweep, which reads on a console as a document that is newer and fine.

    Returns both, as `supersede` does, so the caller cannot forget to write the predecessor
    back and leave two live items saying different things.
    """
    if successor.review_by is None:
        msg = (
            f"{successor.item_id!r} replaces {current.item_id!r} and carries no review date, "
            "so the replacement leaves the re-verification sweep rather than becoming "
            "overdue in it. "
            f"{A_REPLACEMENT_WITH_NO_REVIEW_DATE_LEAVES_THE_SWEEP_WITHOUT_ANNOUNCING_IT}"
        )
        raise LibraryError(msg)
    return supersede(current, successor)


def retire(item: KnowledgeItem) -> KnowledgeItem:
    """Withdraw one of this person's items, keeping the row (M40.3.1.2).

    `KnowledgeState.ARCHIVED`, which that enum defines as withdrawn deliberately and
    distinguishes from superseded precisely so that an asker who finds nothing is not told a
    successor exists. Nothing is deleted, for the reason `brain.knowledge.item` gives at
    length: an answer given last month is only explainable while the thing it was drawn from
    still exists.

    Two refusals. An already-archived item, because a second withdrawal in a history that
    only had one reads as somebody having done it twice, which is `brain.console.agent_output.
    archive`'s refusal in the same words. And a superseded item, because it already has a
    successor a reader is following, and withdrawing the old version leaves that chain
    ending in a withdrawal rather than in a replacement.
    """
    if item.state is KnowledgeState.ARCHIVED:
        msg = (
            f"{item.item_id!r} is already archived; recording it again puts a second "
            "withdrawal in a history that only had one"
        )
        raise LibraryError(msg)
    if item.state is KnowledgeState.SUPERSEDED:
        msg = (
            f"{item.item_id!r} has already been replaced, so withdrawing it would leave a "
            "reader following the successor from a version that says it was withdrawn"
        )
        raise LibraryError(msg)
    return item.model_copy(update={"state": KnowledgeState.ARCHIVED})


# ------------------------------------------------------- who reads it (M40.3.1.3)
@dataclass(frozen=True)
class AuthoredUse:
    """One of this person's items and how often anything drew on it (M40.3.1.3).

    An item and a number. No principal, no agent, no share and no rank, which is
    `brain.console.workspace.CallerSpend`'s argument about a share and
    `A_USAGE_COUNT_ON_YOUR_OWN_DOCUMENT_COUNTS_READS_AND_NEVER_NAMES_READERS` about the rest.
    """

    item_id: str
    retrievals: int


@dataclass(frozen=True)
class AuthorUsage:
    """What this person's library is read for, and what nothing has touched (M40.3.1.3).

    Both halves from one function, for the reason `brain.console.agent_tabs.ItemUsage` gives:
    the unread list is only meaningful as the complement of the read one, and two calls over
    two different sets produce two lists that do not add up.

    There is no basis field, and its absence is the design rather than an omission. A basis
    exists to say whose figures these are, and these are nobody's: every count here is over
    every retrieval of one document by anybody, and no shape on this surface names a reader.
    """

    author_id: str
    #: Items something drew on inside the window, heaviest first.
    read: tuple[AuthoredUse, ...]
    #: Items in this person's library with no retrieval in the window. The unread list.
    unread: tuple[str, ...]


def authored_usage(
    retrievals: Sequence[ItemRetrieval],
    *,
    within: Sequence[KnowledgeItem],
    author_id: str,
    since: datetime,
    until: datetime,
) -> AuthorUsage:
    """How often anything read each of this person's items (M40.3.1.3).

    `within` is this person's own library as they may see it, which is
    `reachable_own_items`' output, and passing anything else is what makes the unread list
    wrong in one of two ways: the whole corpus makes it a list of everything that exists, and
    a set they cannot read makes it a disclosure.

    Every agent's retrievals count, because the question is whether the document is used and
    not which assistant used it. Every person's count too, and that is the disclosure
    decision rather than an oversight: see
    `A_USAGE_COUNT_ON_YOUR_OWN_DOCUMENT_COUNTS_READS_AND_NEVER_NAMES_READERS`.

    Ordered by retrievals and then by id, so two readings of an unchanged log are the same
    list; ordering by count alone leaves ties to whatever the mapping iterated.
    """
    ids = frozenset(one.item_id for one in within)
    tally = dict.fromkeys(ids, 0)
    for one in retrievals:
        if one.item_id in ids and since <= one.at <= until:
            tally[one.item_id] += 1
    return AuthorUsage(
        author_id=author_id,
        read=tuple(
            AuthoredUse(item_id=item_id, retrievals=count)
            for item_id, count in sorted(tally.items(), key=lambda pair: (-pair[1], pair[0]))
            if count
        ),
        unread=tuple(sorted(item_id for item_id, count in tally.items() if not count)),
    )


# --------------------------------------------- asking for company visibility (M40.3.1.4)
#: What promoting an item to the whole company changes, in `brain.memory.tiers`' vocabulary.
#: Named here so the tier below is read from the blast radius map rather than written out.
PROMOTION_CHANGE: Final = Change.COMPANY_KNOWLEDGE


def promotion_tier() -> Tier:
    """The tier a promotion request waits at, from what promoting would reach.

    `blast_radius`, never a literal. See
    `THE_TIER_OF_A_PROMOTION_IS_ITS_BLAST_RADIUS_AND_NOT_THE_ASKERS_OPINION`. That function
    refuses a change it has no rule for rather than defaulting, so this cannot answer
    quietly for a change nobody classified.
    """
    return blast_radius(PROMOTION_CHANGE)


@dataclass(frozen=True)
class PromotionRequest:
    """One person asking for their item to be published, and the tier it waits at (M40.3.1.4).

    **No approver, no decision, no approved_at**, exactly as `brain.memory.tiers.Proposal`
    carries none: approving this is not a field away, it is
    `brain.knowledge.visibility.approve_promotion`, which needs a second principal holding
    the capability and refuses the proposer. `library_gaps` reports a field here that could
    hold a decision.

    The proposal is `brain.knowledge.visibility.PromotionProposal` whole rather than copied
    apart, so the digest an approval is granted against is the one this request carries.
    """

    proposal: PromotionProposal
    tier: Tier

    def __post_init__(self) -> None:
        if self.tier is not promotion_tier():
            msg = (
                f"a promotion of {self.proposal.item_id!r} claims tier {int(self.tier)} and "
                f"promoting to the company is tier {int(promotion_tier())}; the tier is not "
                "the asker's to choose. "
                f"{THE_TIER_OF_A_PROMOTION_IS_ITS_BLAST_RADIUS_AND_NOT_THE_ASKERS_OPINION}"
            )
            raise LibraryError(msg)


def request_promotion(
    item: KnowledgeItem,
    *,
    proposer_id: str,
    review_by: datetime,
    reason: str,
    now: datetime,
) -> PromotionRequest:
    """Ask for one of this person's items to be published company-wide (M40.3.1.4).

    Refuses somebody proposing a promotion of an item that is not theirs, which is the check
    `brain.knowledge.visibility` cannot make because it takes an item id rather than an item:
    a member control that took the id from a form would otherwise propose a widening of
    somebody else's document, and the approval that followed would look entirely correct.

    The owner on the proposal is the item's own steward and is not a parameter. A proposal
    naming a different steward is one whose approval hands the widened item to somebody who
    was never asked, and the two identifiers being separate arguments is how that happens.

    `to_level` is `COMPANY` and there is no parameter for it. A request for department
    visibility is not this control: it is an upload at that level, which `admit_upload`
    already admits without an approver, and offering both here would make the gated path and
    the ungated one one function with a flag.
    """
    if not is_own(proposer_id, item.owner_id):
        msg = (
            f"{proposer_id!r} does not steward {item.item_id!r} and may not ask for it to be "
            "published; a promotion request is made by whoever answers for the item"
        )
        raise LibraryError(msg)
    return PromotionRequest(
        proposal=propose_promotion(
            item_id=item.item_id,
            from_level=item.visibility.level,
            to_level=Visibility.COMPANY,
            proposer_id=proposer_id,
            owner_id=item.owner_id,
            review_by=review_by,
            reason=reason,
            now=now,
        ),
        tier=promotion_tier(),
    )


# --------------------------------------------------------- personal skills (M40.3.2)
class Origin(enum.StrEnum):
    """The three ways a personal skill arrives, exactly as M40.3.2.2 lists them.

    A separate vocabulary from `brain.tools.skills.SourceKind` rather than a reuse of it, and
    the mapping below is the whole reason: `SourceKind` records what a re-fetch would have to
    do, which is why an authored skill and an uploaded file are one kind to it. A person
    choosing between "write one here" and "send me a file" is making a different choice, and
    a surface that collapsed the two would offer a studio button that produced an upload.
    """

    #: Written here. Bytes with no address, pinned by their digest.
    STUDIO = "studio"
    #: Fetched from a repository, pinned to a commit.
    REPOSITORY = "repository"
    #: Fetched from an address somebody pasted, pinned by digest.
    URL = "url"


#: Which import each origin has to be. A mapping rather than a branch, so the whole rule is
#: one thing a reviewer reads, and exhaustive over `Origin` by test.
ORIGIN_SOURCE: Mapping[Origin, SourceKind] = MappingProxyType(
    {
        Origin.STUDIO: SourceKind.UPLOAD,
        Origin.REPOSITORY: SourceKind.GITHUB,
        Origin.URL: SourceKind.URL,
    }
)


@dataclass(frozen=True)
class PersonalSkill:
    """One skill somebody holds in their own library, and who holds it.

    **`brain.tools.skills.ImportedSkill` deliberately carries no owner** and that is right for
    it: it records what arrived, where from, and who reviewed it, which are facts about the
    skill. A personal library needs a fact about a person, so the pairing is made here rather
    than by adding a field to a model whose absence of one is load-bearing. The same split
    `brain.console.agent_tabs.SkillInvocation` makes when it declines to be a `RunOutcome`.
    """

    owner_id: str
    imported: ImportedSkill

    def __post_init__(self) -> None:
        if not self.owner_id.strip():
            msg = (
                f"a personal copy of {self.imported.skill.name!r} belonging to nobody is in "
                "everybody's library, because a personal scope with no owner is the "
                "unrestricted scope"
            )
            raise LibraryError(msg)


@dataclass(frozen=True)
class SkillRow:
    """One personal skill as its owner reads it (M40.3.2.1).

    Source, version and review state, which is what the leaf names, plus the location in the
    source's own spelling because a person with two forks of one skill has nothing else to
    tell them apart. `brain.console.agent_tabs.SkillChip` is the same row for an agent's
    configuration tab and carries the digest as well, because a chip is compared against what
    an agent is pinned to and a personal library entry is not.
    """

    name: str
    version: str
    origin: Origin
    location: str
    review: Review


def origin_of(source: SkillSource) -> Origin:
    """Which of the three routes this import came by.

    Derived from the source rather than stored beside it, so a row cannot claim to have been
    written in the studio while carrying a repository pin. Refuses a kind no origin maps to,
    rather than defaulting: a fourth `SourceKind` would otherwise be rendered as whichever
    origin the lookup happened to return, which is `brain.console.reach_view.provenance_of`'s
    refusal for the same shape of question.
    """
    for origin, kind in ORIGIN_SOURCE.items():
        if kind is source.kind:
            return origin
    msg = (
        f"{source.kind.value} is not one of the three routes a personal skill arrives by, so "
        "a library row would name a studio, a repository or an address it did not come from"
    )
    raise LibraryError(msg)


def add_skill(*, owner_id: str, imported: ImportedSkill, origin: Origin) -> PersonalSkill:
    """Put one skill in this person's own library, by one of the three routes (M40.3.2.2).

    The route is checked against the import rather than recorded beside it. A skill pasted
    from an address and filed as authored here is one whose provenance the reviewer reads
    wrongly, and `brain.tools.skills.SkillSource` already refuses an import that cannot be
    fetched again, so the pin is the thing to compare against.

    There is no parameter a URL, a repository or a commit could arrive through, which is
    `brain.console.workspace_capabilities.AN_ATTACH_PATH_THAT_TAKES_A_URL_IS_A_ROUTE_ROUND_
    THE_REVIEW` one step earlier: the fetching and the pinning happen in
    `brain.tools.skills` before anything reaches here, so this cannot import on the way past.
    """
    found = origin_of(imported.source)
    if found is not origin:
        msg = (
            f"{imported.skill.name!r} is filed as {origin.value} and its import is "
            f"{found.value}; a library row would describe a provenance the pin contradicts"
        )
        raise LibraryError(msg)
    return PersonalSkill(owner_id=owner_id, imported=imported)


def my_skills(skills: Iterable[PersonalSkill], *, principal_id: str) -> tuple[SkillRow, ...]:
    """This person's own skills, with source, version and review state (M40.3.2.1).

    Narrowed by `brain.console.own_things.is_own`, which is the repository's one personal
    predicate, so this list and a query narrowed by the same scope agree by construction.

    The review state is `brain.console.agent_tabs.review_state`'s, which is the only place
    that distinguishes a skill approved from one approved and then edited: the state column
    still reads approved while the bytes have moved, and a personal library showing the
    column would tell somebody their skill is ready when nobody has read what is there.

    Sorted by name, so two readings of an unchanged library are the same list.
    """
    return tuple(
        SkillRow(
            name=one.imported.skill.name,
            version=one.imported.skill.version,
            origin=origin_of(one.imported.source),
            location=one.imported.source.location,
            review=review_state(one.imported),
        )
        for one in sorted(
            (one for one in skills if is_own(principal_id, one.owner_id)),
            key=lambda one: one.imported.skill.name,
        )
    )


@dataclass(frozen=True)
class Submission:
    """One personal skill offered to the department library (M40.3.2.3).

    **No reviewer, no decision, no decided_at.** Submitting is asking, and a type with
    nowhere to record an answer is one nobody can approve by filling a field in;
    `brain.tools.skills.ImportedSkill.approved_by` is where a named person decides, and
    `brain.tools.review.pending` is the queue they read. `library_gaps` reports a field here
    that could hold a decision.
    """

    owner_id: str
    skill_name: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        if not self.skill_name.strip():
            msg = "a submission naming no skill is not something anybody can be asked to read"
            raise LibraryError(msg)
        if self.submitted_at.tzinfo is None:
            msg = (
                f"{self.skill_name!r} was submitted at a naive instant, so its place in a "
                "queue ordered by how long things have waited is wrong by the host's offset"
            )
            raise LibraryError(msg)


def submit_for_review(one: PersonalSkill, *, at: datetime) -> Submission:
    """Offer one personal skill to the department library (M40.3.2.3).

    Refuses a skill that has already been decided. `ImportedSkill._decided` refuses a second
    decision because the record of who approved what is the entire product of a review, and
    the matching rule on the asking side is that a decided skill is not resubmitted: an
    author who disagrees with a rejection edits the skill, and `with_content` clears the
    review, which is what puts it back in the queue with new bytes to read.

    The submission carries the owner, so `brain.tools.review.pending` sorting by how long
    something has waited cannot be gamed by resubmitting: a second submission of the same
    bytes is refused here rather than moving the entry to the front.
    """
    if one.imported.state is not SkillState.IMPORTED:
        msg = (
            f"{one.imported.skill.name!r} is already {one.imported.state.value} and cannot be "
            "submitted again; an author who disagrees edits the skill, which clears the "
            "review and puts new bytes in the queue"
        )
        raise LibraryError(msg)
    return Submission(
        owner_id=one.owner_id,
        skill_name=one.imported.skill.name,
        submitted_at=at,
    )


def attach_refusals(
    one: PersonalSkill, record: AgentRecord, *, in_library: bool = False
) -> tuple[str, ...]:
    """Why this personal skill may not go on this agent. Empty when it may (M40.3.2.4).

    Two refusals and neither is a second opinion about a review. The first is
    `brain.console.agent_tabs.review_state`'s verdict, which is derived from
    `ImportedSkill.is_executable` and is therefore the same three clauses
    `brain.tools.skills.pin_skill` refuses on. The second is the leaf: until the department
    has accepted it, a personal skill goes only on agents its owner stewards.

    **Stewardship and not authorship**, by `brain.console.own_things.is_own` against
    `AgentRecord.audience.owner_id`, for the reason that module gives: `created_by` never
    moves, so an agent somebody built and handed over would carry their personal skills
    forever.

    Refusals rather than a bool, because the two are different things to tell somebody: one
    says wait for a reviewer and the other says put it on your own agent. A bool would be
    rendered as one sentence and the sentence would be wrong half the time.
    """
    gaps: list[str] = []
    if review_state(one.imported) is not Review.APPROVED:
        gaps.append(
            f"{one.imported.skill.name!r} has not been approved by a named person against "
            "the bytes that are there now, so nothing may be pinned to it"
        )
    if not in_library and not is_own(one.owner_id, record.audience.owner_id):
        gaps.append(
            f"{one.imported.skill.name!r} is a personal skill and {record.agent_id!r} is not "
            f"stewarded by {one.owner_id!r}; a personal skill reaches other people's agents "
            "when the department library accepts it and not before"
        )
    return tuple(gaps)


# ------------------------------------------------ what agents produced for me (M40.3.3)
def produced_for_me(
    entries: Sequence[Artifact],
    *,
    principal_id: str,
    reader: EntitlementSet,
    now: datetime,
) -> tuple[Artifact, ...]:
    """Everything any agent produced for this person, newest first (M40.3.3.1).

    `brain.console.agent_output.visible_artifacts` requires an agent id and has no value
    meaning every agent, because a listing that could be asked for the whole estate is the
    global pile with an optional filter on it. This is that rule turned ninety degrees: the
    required narrowing is the person, `principal_id` is keyword-only with no default and no
    value meaning everybody, and there is no agent parameter at all, because "by any agent"
    is the leaf.

    Refuses an entitlement set belonging to somebody else. A caller passing a name in one
    argument and another person's reach in the other is the mistake that happens once, in a
    handler with the wrong variable in scope, and here it would assemble one person's page
    out of another person's grants. `brain.knowledge.visibility.approve_promotion` makes the
    same check for the same reason.

    **The entitlement half of `may_download` does no work on this list and that is worth
    saying out loud.** `may_see` admits an artifact whose `caller_id` is the reader, and
    every row here has that by construction, so what actually removes a row is the retention
    horizon. The call is still `may_download` rather than an expiry check written here,
    because retention and permission are one question at the point of a download and two
    implementations of it would answer differently the day the ownership branch changes.

    Newest first, ties broken by id, so two readings of an unchanged store are the same list.
    Returns one value; there is nowhere in it for a count of what was left out.
    """
    if reader.principal_id != principal_id:
        msg = (
            f"the reach offered belongs to {reader.principal_id!r} and this page is "
            f"{principal_id!r}'s; a personal listing assembled from somebody else's grants "
            "is one person's page showing another person's rows"
        )
        raise LibraryError(msg)
    kept = [
        one for one in entries if one.caller_id == principal_id and may_download(one, reader, now)
    ]
    return tuple(sorted(kept, key=lambda one: (one.at, one.artifact_id), reverse=True))


def may_redownload(
    one: Artifact, requester: EntitlementSet, now: datetime, *, principal_id: str
) -> bool:
    """Whether this person may fetch these bytes again, asked now (M40.3.3.2).

    The verdict is `brain.console.agent_output.may_download`'s and is not recomputed here.
    There is no parameter a link, a token or a signature could arrive through, which is that
    module's `A_LINK_THAT_CARRIES_ITS_OWN_PERMISSION_IS_A_GRANT_ANYBODY_CAN_FORWARD` carried
    onto the member surface, and `library_gaps` reads this signature to say so.

    What is added is the narrowing a member control needs and a console check does not. A
    download control on a personal page is invoked with an artifact id from that page, and a
    check that only asked whether the requester holds an artifact grant would let somebody
    with one operate their own page's control on a row that was never on it. So an artifact
    produced for somebody else is refused here whatever the requester holds, and the refusal
    is a False rather than a message, because a control that explained itself would say which
    of the two things was wrong.

    Refuses outright, rather than returning False, when the entitlement belongs to somebody
    other than the person whose control this is. That is a caller fault and not a member's
    refusal, and reporting it as a refusal would hide it behind a screen that reads as
    working.
    """
    if requester.principal_id != principal_id:
        msg = (
            f"the reach offered belongs to {requester.principal_id!r} and this control is "
            f"{principal_id!r}'s; a download decided from somebody else's grants is a "
            "download nobody asked for"
        )
        raise LibraryError(msg)
    if one.caller_id != principal_id:
        return False
    return may_download(one, requester, now)


@dataclass(frozen=True)
class Share:
    """One artifact handed to one colleague (M40.3.3.3).

    **There is no field here a read could consult.** No entitlement, no hash, no capability,
    no scope, no token and no expiry: a share that carried any of them would be a second
    permission model beside the entitlement set, and the second one is the one that ends up
    deciding. What it carries is an artifact, two people and a time, which is enough to put a
    row on somebody's page and not enough to admit them to anything. See
    `A_SHARE_IS_ADMITTED_ONCE_AND_THE_READ_IS_DECIDED_EVERY_TIME`, and `library_gaps` reads
    the fields of this type rather than trusting the paragraph.
    """

    artifact_id: str
    shared_by: str
    shared_with: str
    at: datetime

    def __post_init__(self) -> None:
        for name in ("artifact_id", "shared_by", "shared_with"):
            if not str(getattr(self, name)).strip():
                msg = (
                    f"a share with no {name} names nobody or everybody depending on who "
                    "reads it, and a row on a personal page has to name one person"
                )
                raise LibraryError(msg)
        if self.shared_by.strip() == self.shared_with.strip():
            msg = (
                f"{self.shared_by!r} shared {self.artifact_id!r} with themselves, which is a "
                "bookmark wearing the word shared and renders as somebody else having been "
                "given something"
            )
            raise LibraryError(msg)
        if self.at.tzinfo is None:
            msg = (
                f"a share of {self.artifact_id!r} is dated with no timezone, so its order "
                "against the artifact's own horizon is wrong by the host's offset from UTC"
            )
            raise LibraryError(msg)


def share(
    one: Artifact,
    *,
    sharer: EntitlementSet,
    colleague: EntitlementSet,
    now: datetime,
) -> Share:
    """Hand one artifact to one colleague who can already reach it (M40.3.3.3).

    Three refusals, and the middle one is the leaf.

    *The sharer cannot pass on what they cannot have.* Asked first, so somebody probing with
    an artifact id they have no business holding is refused before anything is evaluated
    about the colleague, and learns nothing about them.

    *The colleague must already reach it.* `may_download` asked of their own set, so this is
    the same question their own read will ask and not a second rule that could be more
    generous. A share is refused rather than accepted-and-useless, which is
    `brain.knowledge.visibility.admit_upload`'s argument: silently doing something narrower
    than what was asked for leaves somebody believing they did it. The cost is a disclosure
    about a colleague's grants and it is stated, and bounded by shape: see
    `A_REFUSAL_TO_SHARE_NAMES_A_GRANT_AND_MUST_NOT_BECOME_A_PROBE`.

    *Not with yourself*, which `Share` refuses at construction.

    One artifact and one colleague. There is no parameter naming several, no list, and no
    function anywhere in this module answering who an artifact could be shared with, so a
    map of somebody's grants costs one deliberate call per artifact.

    The refusal names neither the capability nor the scope, following
    `brain.ops.denial_alerts`, which names the shape of a denial and never the thing denied.
    """
    if not may_download(one, sharer, now):
        msg = (
            f"{sharer.principal_id!r} cannot open {one.artifact_id!r}, so there is nothing "
            "for them to pass on; sharing hands over what somebody has rather than granting "
            "what they have not"
        )
        raise LibraryError(msg)
    if not may_download(one, colleague, now):
        msg = (
            f"{colleague.principal_id!r} does not already reach {one.artifact_id!r}, and "
            "sharing makes something findable rather than reachable. "
            f"{A_SHARE_IS_ADMITTED_ONCE_AND_THE_READ_IS_DECIDED_EVERY_TIME}"
        )
        raise LibraryError(msg)
    return Share(
        artifact_id=one.artifact_id,
        shared_by=sharer.principal_id,
        shared_with=colleague.principal_id,
        at=now,
    )


def open_share(
    one: Share,
    artifact: Artifact,
    *,
    recipient: EntitlementSet,
    now: datetime,
) -> bool:
    """Whether the colleague may open what was shared, asked now (M40.3.3.3).

    **The share is not an input to the verdict.** It supplies which artifact and which
    person, both of which are checked against what the caller handed in, and then the answer
    is `may_download` about the recipient as they are at this moment. There is no branch in
    which a `Share` makes a read succeed that would otherwise fail, which is the whole of
    "sharing does not grant": see `A_SHARE_IS_ADMITTED_ONCE_AND_THE_READ_IS_DECIDED_EVERY_TIME`.

    So a colleague whose entitlement narrows after the share gets False, exactly as if the
    artifact had aged out, and a colleague whose entitlement widens gains nothing, because
    `may_download` would already have said yes. The share was admitted once, at a moment when
    the answer was yes, and that moment is not consulted again.

    Two refusals that are caller faults rather than answers, and both raise. A share pointing
    at a different artifact from the one supplied would otherwise let a page render one row's
    permission beside another row's bytes; and a recipient who is not the person named on the
    share would be opening somebody else's row, which is the mistake that reads as the
    feature working.
    """
    if artifact.artifact_id != one.artifact_id:
        msg = (
            f"this share names {one.artifact_id!r} and the artifact supplied is "
            f"{artifact.artifact_id!r}; a verdict reached about one and rendered beside the "
            "other is a permission decision about the wrong bytes"
        )
        raise LibraryError(msg)
    if recipient.principal_id != one.shared_with:
        msg = (
            f"this share was made out to {one.shared_with!r} and the reach offered belongs "
            f"to {recipient.principal_id!r}; a share is not a bearer token and cannot be "
            "opened by whoever is holding it"
        )
        raise LibraryError(msg)
    return may_download(artifact, recipient, now)


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this surface is handed. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`: a type added here and not to this tuple is
#: one the checks below never see.
LIBRARY_SURFACE: Final[tuple[type, ...]] = (
    LibraryEntry,
    AuthoredUse,
    AuthorUsage,
    SkillRow,
    Submission,
    Share,
)

#: Field names by which a share would start carrying its own permission. Names rather than a
#: rule about values, because the failure arrives as a field somebody adds to save a lookup,
#: and it arrives with one of these on it.
NAMES_THAT_WOULD_MAKE_A_SHARE_A_GRANT: Final[frozenset[str]] = frozenset(
    {
        "capabilities",
        "capability",
        "entitlement",
        "entitlement_hash",
        "ent_hash",
        "grant",
        "grants",
        "reach",
        "scope",
        "signature",
        "token",
        "url",
    }
)

#: Parameter names by which one call would reach several colleagues at once. A share refused
#: one at a time is a slow oracle; a share offered over a list is a directory of who reaches
#: what, returned in one call. See `A_REFUSAL_TO_SHARE_NAMES_A_GRANT_AND_MUST_NOT_BECOME_A_PROBE`.
NAMES_THAT_WOULD_BE_A_BULK_SHARE: Final[frozenset[str]] = frozenset(
    {
        "audience",
        "colleagues",
        "department",
        "everybody",
        "everyone",
        "principals",
        "recipients",
        "team",
    }
)

#: Field names on a request or a submission that would let it answer itself.
NAMES_THAT_WOULD_BE_A_DECISION: Final[frozenset[str]] = frozenset(
    {"approved", "approved_at", "approver", "approver_id", "decided_at", "decision", "reviewer"}
)


def library_gaps(
    *,
    surface: Sequence[type] = LIBRARY_SURFACE,
    share_type: type = Share,
    request_types: Sequence[type] = (PromotionRequest, Submission),
    sharing: Sequence[Callable[..., Any]] = (share, open_share),
    download: Callable[..., Any] = may_redownload,
    origins: Mapping[Origin, SourceKind] = ORIGIN_SOURCE,
    promotion_change: Change = PROMOTION_CHANGE,
) -> tuple[str, ...]:
    """Everything about this surface that would widen somebody or decide something for them.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason `brain.console.agent_output.artifact_gaps` gives about itself: a diagnostic that
    can only run against the healthy tree has nothing to report, so switching off any of its
    refusals changes nothing observable and every one of them survives. Calling it with no
    arguments is the deployment check and calling it with a constructed type is the test.

    **`promotion_change` is a parameter for exactly that reason and it was added because a
    mutation survived.** The tier check read `PROMOTION_CHANGE` directly, so the branch could
    only fire on a tree where `BLAST_RADIUS` had already been lowered, which is a state no
    fixture could build: switching the refusal off changed nothing any test could see. A
    change whose blast radius is not gated is now one argument away, which is the difference
    between a guard and a paragraph.

    Six checks. A count of what a reader was not shown; a share that carries its own
    permission; a request that carries its own answer; a call that could reach several
    colleagues at once; a download that could be handed a link; and a promotion whose tier
    has stopped being gated, which is the one that reads a map somebody else maintains.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{share_type.__name__}.{name} would put a permission on a share, and a read that "
        f"consulted it would be admitted by the share rather than by their own grants. "
        f"{A_SHARE_IS_ADMITTED_ONCE_AND_THE_READ_IS_DECIDED_EVERY_TIME}"
        for name in getattr(share_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_MAKE_A_SHARE_A_GRANT
    )
    for asking in request_types:
        gaps.extend(
            f"{asking.__name__}.{name} would let a request record its own answer, so asking "
            "and deciding would be one act by one person"
            for name in getattr(asking, "__dataclass_fields__", {})
            if name in NAMES_THAT_WOULD_BE_A_DECISION
        )
    for handing in sharing:
        offered = set(inspect.signature(handing).parameters)
        gaps.extend(
            f"{getattr(handing, '__name__', 'a sharing path')} takes {name}, which reaches "
            "several people in one call. "
            f"{A_REFUSAL_TO_SHARE_NAMES_A_GRANT_AND_MUST_NOT_BECOME_A_PROBE}"
            for name in sorted(offered & NAMES_THAT_WOULD_BE_A_BULK_SHARE)
        )

    taken = set(inspect.signature(download).parameters)
    gaps.extend(
        f"{getattr(download, '__name__', 'the download check')} takes {name}, so a stored "
        "link decides a download that is supposed to be re-checked"
        for name in sorted(taken & NAMES_THAT_WOULD_BE_A_BEARER_TOKEN)
    )

    if blast_radius(promotion_change) is not Tier.GATED:
        gaps.append(
            f"{promotion_change.value} no longer waits for a person, so asking for a document "
            "to be published company-wide would be granted by whatever counts agreement"
        )

    missing = sorted(route.value for route in Origin if route not in origins)
    gaps.extend(
        f"{name} is a route a personal skill can arrive by with no import kind behind it, so "
        "a library row would describe a provenance nothing pinned"
        for name in missing
    )

    return tuple(gaps)


def library_notes() -> tuple[str, ...]:
    """What this surface decides and something else has to enforce.

    Separate from `library_gaps` for the reason `brain.console.agent_output.
    retention_enforcement_gaps` is separate from `artifact_gaps`: that one is a deployment
    check and a check that is red on the day it lands is a check somebody switches off. This
    one is red today and is meant to be.

    The finding is real. `brain.console.agent_output.may_see` admits an artifact whose
    `caller_id` is the reader, before it looks at any grant, and `may_download` is
    `is_expired` and then `may_see`. So a person whose grants were revoked after a run can
    still fetch what that run produced until its retention horizon passes, and every
    surface that re-checks a download, including this one, inherits that. It is a deliberate
    decision in that module, argued as findability, and it is worth naming here because a
    member's page is where it is most often exercised.
    """
    return (
        "a producer's own download is admitted by brain.console.agent_output.may_see's "
        "caller branch before any grant is read, so re-checking a download against current "
        "entitlement does its work on the retention horizon and not on the grants; a "
        "revoked reader keeps their own outputs until the horizon passes",
    )
