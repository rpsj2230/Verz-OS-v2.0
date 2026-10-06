"""`gate.role_nomination`: one person proposed for one role, and the decision on it (M33.1.2.3).

The row behind `brain.console.global_surfaces.Nomination`. `0208` builds it.

**A proposal, and the grant is somewhere else.** A confirmed nomination writes a
`gate.role_grant` through `brain.identity.role_store.adding`, in the same transaction, and this row
names it in `grant_id`. The grant is what changes access, so it is the grant that `0102`'s trigger
puts on the ledger, naming the confirmer as `granted_by` and carrying the nomination's reason. The
nomination row is its own record of the proposal: who proposed whom, why, when, and who decided.
Rejected: a ledger entry per nomination, which would put a proposal nobody acted on into the chain
the access review reads as changes to access.

**The scope is held by name, and resolved when somebody confirms.** A Department Admin or an
Approver is nominated over a scope, and the scope is the live `gate.scope` row of that slug when
the nomination is confirmed, so a scope retired in between refuses the confirmation rather than
granting over a predicate nobody can see any more.

**The nominee is a value, not a foreign key.** A key on `auth.principal` would refuse a
nomination of somebody who does not exist, and that refusal would tell anybody on the Roles screen
which principal ids exist. A nomination of nobody is a row a confirmer can only decline: the grant
it would write has the key, and refuses.

**Decided once, in the decider's own name, by somebody who is neither of the two people named.**
The checks hold the two-person rule against a row that arrives some other way, and `0208`'s update
policy admits only an undecided row and only a `decided_by` that is the session's own principal.

Task ids: M33.1.2.3
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.identity.roles import SCOPE_REQUIRED, Role
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from brain.tables.role_grant import ROLE_CHARS

#: A scope's slug, as `gate.scope.slug` is written.
SCOPE_SLUG_CHARS: Final = 60

#: The longest reason a nomination carries, `brain.govern_routes.REASON_CHARS`.
REASON_CHARS: Final = 500


class NominationOutcome(enum.StrEnum):
    """How a nomination was decided. An undecided one has no outcome at all."""

    CONFIRMED = "confirmed"
    DECLINED = "declined"


OUTCOME_CHARS: Final = 16

#: The roles nominated over a scope, written from `SCOPE_REQUIRED` as `role_grant` writes them.
SCOPED: Final = one_of("role", SCOPE_REQUIRED)


class RoleNominationRow(Base):
    """One proposal that one person hold one role, decided once."""

    __tablename__ = "role_nomination"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    role: Mapped[str] = mapped_column(String(ROLE_CHARS), nullable=False)
    scope_slug: Mapped[str | None] = mapped_column(String(SCOPE_SLUG_CHARS), nullable=True)
    nominated_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.statement_timestamp(), nullable=False
    )
    outcome: Mapped[str | None] = mapped_column(String(OUTCOME_CHARS), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gate.role_grant.id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(one_of("role", Role), name="role"),
        CheckConstraint(
            f"({SCOPED}) = (scope_slug IS NOT NULL)", name="scope_exactly_when_required"
        ),
        CheckConstraint(
            f"length(btrim(reason)) > 0 AND length(reason) <= {REASON_CHARS}",
            name="reason_present",
        ),
        CheckConstraint("nominated_by <> principal_id", name="not_self_nominated"),
        CheckConstraint(
            "outcome IS NULL OR " + one_of("outcome", NominationOutcome), name="outcome"
        ),
        CheckConstraint(
            "(outcome IS NULL) = (decided_by IS NULL) AND (outcome IS NULL) = (decided_at IS NULL)",
            name="decided_once_and_whole",
        ),
        CheckConstraint(
            "decided_by IS NULL OR (decided_by <> principal_id AND decided_by <> nominated_by)",
            name="decided_by_a_third_person",
        ),
        CheckConstraint(
            "(outcome IS NOT DISTINCT FROM 'confirmed') = (grant_id IS NOT NULL)",
            name="a_grant_exactly_when_confirmed",
        ),
        Index("ix_gate_role_nomination_created_at", "created_at"),
        {"schema": "gate"},
    )
