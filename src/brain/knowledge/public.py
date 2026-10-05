"""Who may mark a document public for the website widget, and what a marking is.

needs-rupash 26 decided the widget on 2026-09-06: an anonymous visitor reads knowledge a Super Admin
or a Department Admin marked public, and nothing else. `brain.knowledge.search.PublicReach` is what
the visitor may read. This is the other half, the decision to put a document there (M10.7.2).

**A capability, `approve:knowledge.public`, and its scope is the whole of the difference between
the two roles.** `brain.identity.roles` holds that no role implies a capability, so "a Department
Admin marks their own department's documents" is a grant scoped to their department, and "a Super
Admin has no such limit" is the same grant over everything. The first administrator is granted it
at appointment, as `approve:knowledge.visibility` is, and grants it onward scoped to a department
from the People screen, which bounds every grant by what its writer holds. Rejected: reusing
`approve:knowledge.visibility`. That is the approval of a company-wide promotion, which a
Department Admin proposes and must not decide, so granting it to one to let them mark their own
department's documents would let them approve every promotion too.

**The scope is read as departments, and anything else is refused rather than trimmed.** A
department document is marked by a grant whose scope admits its department; a company-wide
document, which every department reads, by a grant no department narrows. A grant scoped by
something other than a department (an owner, a prefix of a name) decides nothing here, for
`brain.knowledge.search.A_SCOPE_THAT_CANNOT_BE_REDUCED_IS_REFUSED_NOT_TRIMMED`'s reason: a
reduction that guessed would be a second answer to whose documents these are.

**Only a published document is marked, and a personal one never.** A draft marked public would
reach the internet the moment its author published it, with nobody deciding at that moment; an
older version answers nothing. A personal document has been shared with nobody, and the database
refuses the marking on one as well (`0171`). Unmarking is refused only by the scope: withdrawing
something from the public is never the harmful direction.

**A marking names the person and the time, on the item, and the ledger entry says which way it
went.** `0171` adds `public_by` and `public_at`, and `know.record_item` appends a `setting` entry
naming the actor the request attributed, the columns changed and `public` true or false. That is
the audit needs-rupash 26 asks for, "in the same way a grant does", written by the database in the
transaction that made the change, so a marking without its entry is not a state the table can be in.

Task ids: M10.7.2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.core.department import DEPARTMENT_FIELD, admits_department
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Op, Scope
from brain.knowledge.item import KnowledgeState
from brain.knowledge.lifecycle import StoredItem
from brain.knowledge.visibility import Visibility

#: The decision over what the public may read. See the module docstring.
PUBLIC_MARKING: Final = Capability(value="approve:knowledge.public")

# ------------------------------------------------------------------ written-down reasons
#: Why a Department Admin's marking stops at their department.
A_DEPARTMENT_ADMIN_MARKS_ONLY_THEIR_OWN_DEPARTMENT: Final = (
    "The owner decided that a Department Admin decides what is public for their own department's "
    "knowledge and a Super Admin for any. No role implies a capability here, so the difference is "
    "the scope of approve:knowledge.public: a department document needs a grant admitting its "
    "department, and a company-wide one a grant no department narrows."
)

#: Why the marking is audited by the database rather than by the route.
A_MARKING_NAMES_WHO_MADE_IT: Final = (
    "Once an answer has been given to the internet it has been given, so a marking is recorded "
    "like a grant: the item holds who marked it and when, and know.record_item appends an entry "
    "naming the attributed actor and whether it was marked or unmarked, in the same transaction."
)

# ------------------------------------------------------------------ what the marker is told
#: Each refusal is said to a person who can already see the document, so each may say why.
NOT_GRANTED: Final = "You have not been given the decision over what the public may read."
NOT_PUBLISHED: Final = (
    "Only a published document can be made public, not a draft or an old version."
)
NEVER_PERSONAL: Final = (
    "A personal document cannot be made public. Share it with its department first."
)
OUTSIDE_YOUR_DEPARTMENT: Final = (
    "You decide what is public for your own department's documents only."
)
COMPANY_NEEDS_EVERY_DEPARTMENT: Final = (
    "A company-wide document is made public by somebody who decides for every department."
)
NOT_A_DEPARTMENT_GRANT: Final = (
    "Your decision over what the public may read is not scoped to departments, so it decides "
    "nothing about this document."
)


@dataclass(frozen=True)
class PublicMarking:
    """Whether an item is public, and who made it so and when. Both or neither, as `0171` holds."""

    marked_by: str = ""
    marked_at: datetime | None = None

    def __post_init__(self) -> None:
        if bool(self.marked_by) != (self.marked_at is not None):
            msg = "a public marking is a person and a time, both or neither"
            raise ValueError(msg)

    @property
    def is_public(self) -> bool:
        return self.marked_at is not None


#: An item nobody has marked.
NOT_PUBLIC: Final = PublicMarking()


def _narrowing(scope: Scope) -> tuple[bool, bool]:
    """Whether the scope tests anything but a department, and whether it narrows departments."""
    testing = [clause for clause in scope.clauses if clause.op is not Op.ANY]
    elsewhere = any(clause.field != DEPARTMENT_FIELD for clause in testing)
    return elsewhere, bool(testing)


def marking_refusal(
    item: StoredItem, *, marker: EntitlementSet, now: datetime, public: bool
) -> str | None:
    """Why this person may not mark (or unmark) this document public, or None when they may.

    Asked only of a document the marker can already see, so each sentence may name the reason.
    See `A_DEPARTMENT_ADMIN_MARKS_ONLY_THEIR_OWN_DEPARTMENT`.
    """
    scope = marker.scope_for(PUBLIC_MARKING, now)
    if scope is None:
        return NOT_GRANTED
    level = item.visibility.level
    if level is Visibility.PERSONAL:
        return NEVER_PERSONAL
    if public and item.state is not KnowledgeState.PUBLISHED:
        return NOT_PUBLISHED
    elsewhere, narrowed = _narrowing(scope)
    if elsewhere:
        return NOT_A_DEPARTMENT_GRANT
    department = item.visibility.department
    if level is Visibility.DEPARTMENT and not admits_department(scope, department):
        return OUTSIDE_YOUR_DEPARTMENT
    if level is not Visibility.DEPARTMENT and narrowed:
        return COMPANY_NEEDS_EVERY_DEPARTMENT
    return None
