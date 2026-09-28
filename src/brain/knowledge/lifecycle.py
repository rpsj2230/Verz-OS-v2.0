"""A stored document after it is added: who answers for it, who may act, and what they are asked.

`brain.knowledge.item` holds the record and its rules and `brain.knowledge.visibility` the
promotion gate; both take values somebody else holds. Once K1's upload route existed there was a
stored row in `know.item` and nothing could do anything to it: nobody could verify it, hand it to
another steward, replace it with a newer version or ask for it to be published, and the audit that
reopened M7.4.4 and M7.4.5 on 2026-09-17 said exactly that. This module is the rule half of those
four acts over the stored row, and `brain.knowledge.lifecycle_store` and
`brain.knowledge_lifecycle_routes` are the rest.

**The stored row is its own type, and it carries no text.** `StoredItem` is `know.item` as a value:
stewardship, place, state and verification. `KnowledgeItem` refuses to construct without content,
and the only way to give it some would be to read the corpus the row was kept apart from, or to
invent a placeholder, which is a record that lies. `item.assert_supersedable`, `item.badge` and
`verification.disclose` read the fields they need through protocols, so a stored row goes through
the same rules a document does and there is no second copy of any of them.

**Who may act on a document is its steward or whoever administers where it sits, and nobody else.**
The steward acts while they can still read it: `owner_id` never moves and a department does, so a
steward who has left the department is asked nothing and may do nothing, which is
`brain.knowledge.item_store`'s rule about the nag applied to every act. An administrator is
somebody holding `admin:knowledge` over the document's department, the grant K1's upload already
asks, so the people who may add a document where it sits are the people who may keep it. A
personal document is its owner's alone and a company document with no department has no
administrator but its steward. See
`THE_STEWARD_ACTS_WHILE_THEY_CAN_READ_IT_AND_AN_ADMINISTRATOR_WHERE_THEY_ADD`.

**Seeing a document, acting on it and reading it are three questions.** `may_see` is the lifecycle
view: a steward or an administrator sees the record, and so does a reader whose reach admits it.
`may_read` is the text, and only a read admits it, because administering a department's knowledge
is adding to it and not reading it, which is K1's line and `brain.identity.first_administrator`'s.
Everything a person may not see is absent in the same words as a document that does not exist.

**A history is judged version by version.** A superseded row is out of `know.item`'s policy, so a
history is read past it, and each version is shown to a reader whose reach admits that version's
own place as if it were still live. The older version stays readable to exactly the people who
could read it when it was current, and to nobody new. See `place_row`.

**A steward is handed over to somebody who can reach the document, and the refusal names nobody.**
Handing a document to a person who cannot read it or administer it would make a steward the sweep
never asks. The refusal is one sentence whether the person does not exist, has no reach, or reaches
another department, so the control is not a way to ask who reads what. That is a real cost and it
is bounded by shape: one person per call, and an administrator of the document already decides who
in their department adds to it.

**A task is a sentence about one document and never a count.** The four kinds are what the
database opens for a person: a review that fell due, a document handed to them, a promotion they
asked for decided, and a solution they captured decided. The sentence names the document and the
date, and nothing says how many others there are, for the reason `ReverificationTask.message`
gives.

Rejected: letting an administrator act on a personal document to hand it over when its owner
leaves. A personal document reaches its owner and nobody else, so any other person acting on it
learns it exists, which is the disclosure the level exists to prevent.

Task ids: M7.4.5, M7.4.6, M7.7.2
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.core.entitlement import Capability, EntitlementSet
from brain.knowledge.item import (
    RETRIEVABLE_STATES,
    KnowledgeError,
    KnowledgeState,
    ReverificationTask,
)
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD, Reach, SearchError, reach_for
from brain.knowledge.visibility import KnowledgeVisibility, Visibility, VisibilityError

# ------------------------------------------------------------------ written-down reasons
#: Who may act on a stored document, and why the steward's act lapses with their reach.
THE_STEWARD_ACTS_WHILE_THEY_CAN_READ_IT_AND_AN_ADMINISTRATOR_WHERE_THEY_ADD: Final = (
    "A document's steward is whoever answers for it being right, and they act on it while they "
    "can still read it: owner_id never moves and a department does, so a steward who left the "
    "department is asked nothing and may do nothing. Whoever holds admin:knowledge where the "
    "document sits may act on it too, because the people who may add a document there are the "
    "people who may keep it. A personal document is its owner's alone, and anybody else acting "
    "on it would learn it exists."
)

#: Why a verification needs a review date ahead of it.
A_VERIFICATION_SETS_THE_NEXT_REVIEW: Final = (
    "Verifying a document says it is right today, and the review date says when somebody must "
    "look again. A verification with no date leaves the re-verification sweep for good, which "
    "reads on every screen as a document that is verified and fine; one with a date already "
    "behind it opens a task on the day it is written. So the date is required and it is ahead."
)

#: Why the refusal to hand over is one sentence.
A_STEWARD_IS_SOMEBODY_WHO_CAN_REACH_THE_DOCUMENT: Final = (
    "A steward who cannot read or administer the document is a steward the sweep never asks, "
    "so the person named must reach it. The refusal is the same sentence whether that person "
    "does not exist, reaches nothing, or reaches another department, so naming a steward is not "
    "a way to ask who reads what."
)

#: Why a new version of a company-wide document starts in its department.
A_NEW_VERSION_OF_COMPANY_KNOWLEDGE_STARTS_IN_ITS_DEPARTMENT: Final = (
    "Company scope is published only when a named person has verified the text and a second "
    "person has approved the widening. A new version has neither: nobody has read it yet. So a "
    "new version of a company-wide document is placed in the department the document came from, "
    "the older version is kept in its history, and the new one is proposed for the whole company "
    "again once it is verified. A company document with no department has nowhere to start and "
    "is added as a new document instead."
)

# ------------------------------------------------------------------ the words
#: The one refusal every act on a document it may not act on gets, and every document that does
#: not exist. See the module docstring on DENIED and ABSENT.
NOT_OFFERED: Final = "that document is not one you may act on"

#: The one refusal a history or a text read gets for a version the reader may not see.
NOT_SEEN: Final = "that document is not one you may see"

#: The one refusal a hand-over to an unsuitable person gets. See
#: `A_STEWARD_IS_SOMEBODY_WHO_CAN_REACH_THE_DOCUMENT`.
STEWARD_REFUSED: Final = "that person cannot be named steward of this document"


class LifecycleError(Exception):
    """A lifecycle act that would be unsafe or meaningless on this document, said to its actor.

    The actor may act on the document, so the reason is theirs to be told; refusals about whether
    they may act at all are `NOT_OFFERED`, raised as absence by the route.
    """


# ------------------------------------------------------------------ the stored row
@dataclass(frozen=True)
class StoredItem:
    """`know.item` as a value: everything about a document except what it says.

    Satisfies `item.Superseding`, `item.Vouched`, `verification.Attributable` and
    `item.UnderReview`, so the rules over documents read it unchanged.
    """

    item_id: str
    title: str
    owner_id: str
    visibility: KnowledgeVisibility
    state: KnowledgeState
    kind: KnowledgeKind | None = None
    verified_by: str = ""
    verified_at: datetime | None = None
    review_by: datetime | None = None
    supersedes: str = ""
    added_at: datetime | None = None

    @property
    def is_retrievable(self) -> bool:
        return self.state in RETRIEVABLE_STATES

    def place_row(self) -> dict[str, object]:
        """The row `Reach.admits` judges this version by: its place, as if it were still live.

        A superseded or archived version is judged as published where it sat, so a history shows
        an older version to exactly the people it reached when it was current. A draft stays a
        draft, its owner's alone. See the module docstring on histories.
        """
        state = KnowledgeState.DRAFT if self.state is KnowledgeState.DRAFT else None
        return {
            "deleted_at": None,
            "state": (state or KnowledgeState.PUBLISHED).value,
            "owner_id": self.owner_id,
            "visibility": self.visibility.level.value,
            "department": self.visibility.department or None,
        }


# ------------------------------------------------------------------ who may do what
def _reach_or_none(
    entitlement: EntitlementSet,
    *,
    departments: Sequence[str],
    now: datetime,
    capability: Capability,
) -> Reach | None:
    """`reach_for`, with a grant the document plane cannot reduce read as no reach.

    The reading `brain.knowledge.item_store.reach_from` and `brain.knowledge_routes.may_add` give
    the same refusal, for `item_store.A_GRANT_THE_DOCUMENT_PLANE_CANNOT_READ_REACHES_NOTHING_HERE`.
    """
    try:
        return reach_for(entitlement, departments=departments, now=now, capability=capability)
    except SearchError:
        return None


@dataclass(frozen=True)
class Authority:
    """One person's reach over stored documents: what they read and where they add.

    Built from the admitted entitlement and the live department registry by `authority_for`, so
    the departments in each reach are exactly the ones that exist and the grant admits.
    """

    principal_id: str
    reads: Reach | None = None
    adds: Reach | None = None

    def __post_init__(self) -> None:
        for held in (self.reads, self.adds):
            if held is not None and held.principal_id != self.principal_id:
                msg = (
                    f"a reach for {held.principal_id!r} was offered as {self.principal_id!r}'s; "
                    "what somebody may do to a document is their own reach's question"
                )
                raise LifecycleError(msg)

    def may_read(self, item: StoredItem) -> bool:
        """Whether their read of the knowledge plane admits this version's place."""
        return self.reads is not None and self.reads.admits(item.place_row())

    def administers(self, item: StoredItem) -> bool:
        """Whether they hold `admin:knowledge` where this document sits.

        Never a personal document, and never one with no department. See
        `THE_STEWARD_ACTS_WHILE_THEY_CAN_READ_IT_AND_AN_ADMINISTRATOR_WHERE_THEY_ADD`.
        """
        department = item.visibility.department
        if self.adds is None or not department:
            return False
        if item.visibility.level is Visibility.PERSONAL:
            return False
        return department in self.adds.departments

    def stewards(self, item: StoredItem) -> bool:
        """Whether they are its steward and can still read it."""
        return item.owner_id == self.principal_id and self.may_read(item)

    def may_act(self, item: StoredItem) -> bool:
        """Whether they may verify it, replace it, hand it over or ask for it to be published."""
        return item.is_retrievable and (self.stewards(item) or self.administers(item))

    def may_see(self, item: StoredItem) -> bool:
        """Whether the lifecycle record of this version is theirs to see."""
        return self.may_read(item) or self.stewards(item) or self.administers(item)

    def store_reach(self) -> Reach:
        """The reach the database's second wall is told for this person: read and add together.

        The union `brain.knowledge.chunk_store.store_reach` makes for the same reason: an
        administrator acts on documents in a department they may not read, and the policy has to
        admit the row for the act to reach it. What they are shown is decided in Python above.
        """
        read = self.reads.departments if self.reads else ()
        added = self.adds.departments if self.adds else ()
        return Reach(principal_id=self.principal_id, departments=tuple(dict.fromkeys(read + added)))

    def deciding_setting(self) -> str:
        """The departments `0120`'s solution policy lets this person decide in: where they add."""
        return ",".join(self.adds.departments if self.adds else ())


def authority_for(
    entitlement: EntitlementSet, *, departments: Sequence[str], now: datetime
) -> Authority:
    """This person's authority over stored documents, from their admitted reach and the registry."""
    return Authority(
        principal_id=entitlement.principal_id,
        reads=_reach_or_none(
            entitlement, departments=departments, now=now, capability=KNOWLEDGE_READ
        ),
        adds=_reach_or_none(
            entitlement, departments=departments, now=now, capability=KNOWLEDGE_UPLOAD
        ),
    )


# ------------------------------------------------------------------ verifying (M7.4.6)
@dataclass(frozen=True)
class Verification:
    """Who vouched, when, and when somebody must look again. All three, always."""

    verified_by: str
    verified_at: datetime
    review_by: datetime


def verification_of(
    item: StoredItem, *, by: str, at: datetime, review_by: datetime
) -> Verification:
    """Record a verification of a live document, with the next review ahead of it (M7.4.6).

    The actor's authority is the caller's question and is asked before this. What is refused here
    is the act itself: a document that has been replaced or withdrawn is not verified, because a
    badge on it would vouch for text no answer uses; and a review date that is missing, naive or
    not ahead of the verification is `A_VERIFICATION_SETS_THE_NEXT_REVIEW`.
    """
    if item.state is not KnowledgeState.PUBLISHED:
        msg = (
            f"{item.title or item.item_id} is {item.state.value}; only the version answers are "
            "drawn from is verified"
        )
        raise LifecycleError(msg)
    if review_by.tzinfo is None or at.tzinfo is None:
        msg = "a review date is a moment in a timezone; a naive date is a silent bug"
        raise LifecycleError(msg)
    if review_by <= at:
        msg = (
            f"the next review date has to be ahead of today. {A_VERIFICATION_SETS_THE_NEXT_REVIEW}"
        )
        raise LifecycleError(msg)
    return Verification(verified_by=by, verified_at=at, review_by=review_by)


# ------------------------------------------------------------------ a new version (M7.4.5)
def successor_place(predecessor: StoredItem) -> KnowledgeVisibility:
    """Where a new version of this document is placed: where it sits, stewarded as it is.

    The steward carries across versions, because stewardship is of the document and not of a
    file. A company-wide document's new version starts in its department:
    `A_NEW_VERSION_OF_COMPANY_KNOWLEDGE_STARTS_IN_ITS_DEPARTMENT`.
    """
    place = predecessor.visibility
    match place.level:
        case Visibility.DEPARTMENT:
            return KnowledgeVisibility.of_department(
                place.department, owner_id=predecessor.owner_id
            )
        case Visibility.PERSONAL:
            return KnowledgeVisibility.personal(predecessor.owner_id)
        case Visibility.COMPANY:
            if not place.department:
                msg = (
                    f"{predecessor.title or predecessor.item_id} is company-wide and names no "
                    f"department. {A_NEW_VERSION_OF_COMPANY_KNOWLEDGE_STARTS_IN_ITS_DEPARTMENT}"
                )
                raise LifecycleError(msg)
            return KnowledgeVisibility.of_department(
                place.department, owner_id=predecessor.owner_id
            )


# ------------------------------------------------------------------ handing over (M7.7.2)
def assert_may_hand_over(item: StoredItem, *, to: str, theirs: Authority | None) -> None:
    """Refuse a steward who could not act on this document, in one sentence (M7.7.2).

    A personal document has one owner and one column says who, so it is not handed over; a draft
    is its owner's until it is published. The person named must be somebody else, and must read the
    document or administer where it sits. See `A_STEWARD_IS_SOMEBODY_WHO_CAN_REACH_THE_DOCUMENT`.
    """
    if item.visibility.level is Visibility.PERSONAL or item.state is not KnowledgeState.PUBLISHED:
        msg = (
            f"{item.title or item.item_id} is its owner's alone until it is published in a "
            "department, so it is not handed to a steward"
        )
        raise LifecycleError(msg)
    if to == item.owner_id:
        msg = "that person is already this document's steward"
        raise LifecycleError(msg)
    if theirs is None or theirs.principal_id != to:
        raise LifecycleError(STEWARD_REFUSED)
    if not (theirs.may_read(item) or theirs.administers(item)):
        raise LifecycleError(STEWARD_REFUSED)


# ------------------------------------------------------------------ asking to publish (M7.4.4)
def assert_may_propose(item: StoredItem) -> None:
    """Refuse a promotion the gate could never carry out (M7.4.4).

    Company scope refuses an unverified published item (`KnowledgeItem`'s own rule), so a document
    nobody has verified is refused here rather than on the Approvals screen after somebody has
    read the card. And a document already company-wide has nowhere to widen to.
    """
    if item.state is not KnowledgeState.PUBLISHED:
        msg = f"{item.title or item.item_id} is {item.state.value} and is not published further"
        raise LifecycleError(msg)
    if item.visibility.level is Visibility.COMPANY:
        msg = f"{item.title or item.item_id} is already readable by the whole company"
        raise VisibilityError(msg)
    if item.verified_at is None:
        msg = (
            f"{item.title or item.item_id} has not been verified. Company scope is the level "
            "nobody double-checks, so a document is verified before it is proposed for it"
        )
        raise LifecycleError(msg)


# ------------------------------------------------------------------ tasks (M7.4.6, M7.7.2)
class TaskKind(enum.StrEnum):
    """What the database opens a task for. Closed, and held equal to `0120`'s check by a test."""

    #: A document this person stewards fell due for review. Opened by the nag the sweep records.
    REVERIFY = "reverify"
    #: A document was handed to this person to steward.
    STEWARD_NAMED = "steward_named"
    #: A promotion this person asked for was decided on the Approvals screen.
    PROMOTION_DECIDED = "promotion_decided"
    #: A solution this person captured was approved or refused.
    SOLUTION_DECIDED = "solution_decided"


#: The kinds a person may clear by saying they have read it. A review is cleared by verifying the
#: document or replacing it, never by dismissing the task, or the task list lies.
DISMISSABLE: Final[frozenset[TaskKind]] = frozenset(
    {TaskKind.STEWARD_NAMED, TaskKind.PROMOTION_DECIDED, TaskKind.SOLUTION_DECIDED}
)


class Outcome(enum.StrEnum):
    """How a decision a task reports went."""

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StewardTask:
    """One open task, addressed to one person, about one document or one captured solution."""

    task_id: str
    kind: TaskKind
    item_id: str
    opened_at: datetime
    due_at: datetime | None = None
    outcome: Outcome | None = None


#: What each decided task says. A mapping rather than branches, so the sentences sit together.
DECIDED_SENTENCES: Final[Mapping[tuple[TaskKind, Outcome], str]] = MappingProxyType(
    {
        (TaskKind.PROMOTION_DECIDED, Outcome.APPROVED): (
            "{named} was approved for the whole company and is now readable by everyone."
        ),
        (TaskKind.PROMOTION_DECIDED, Outcome.REJECTED): (
            "Publishing {named} to the whole company was not approved. It stays where it was."
        ),
        (TaskKind.SOLUTION_DECIDED, Outcome.APPROVED): (
            "The solution you captured, {named}, was approved and is now company knowledge."
        ),
        (TaskKind.SOLUTION_DECIDED, Outcome.REJECTED): (
            "The solution you captured, {named}, was not approved, so it was not added."
        ),
    }
)


def task_sentence(task: StewardTask, *, title: str) -> str:
    """What the person reads. One document by name, a date where there is one, and no count.

    The review sentence is `ReverificationTask.message`, so the sweep's wording has one home.
    """
    named = title or task.item_id
    match task.kind:
        case TaskKind.REVERIFY:
            if task.due_at is None:
                msg = f"task {task.task_id!r} is a review with no date, which the table refuses"
                raise KnowledgeError(msg)
            due = ReverificationTask(
                item_id=task.item_id, owner_id="", title=named, review_by=task.due_at
            ).message()
            return f"{due} Verify it again with a new review date, or add a newer version."
        case TaskKind.STEWARD_NAMED:
            return (
                f"You are now the steward of {named}. You are asked when it falls due for review."
            )
        case TaskKind.PROMOTION_DECIDED | TaskKind.SOLUTION_DECIDED:
            if task.outcome is None:
                msg = f"task {task.task_id!r} reports a decision and says nothing about it"
                raise KnowledgeError(msg)
            return DECIDED_SENTENCES[(task.kind, task.outcome)].format(named=named)
