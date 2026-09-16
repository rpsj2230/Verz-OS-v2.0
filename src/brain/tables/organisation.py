"""Who is in each team and who leads each department: one row per placement, ended and never edited.

`brain.identity.organisation_store` writes both tables and `migrations/versions/0062_organisation_
and_elevation.py` holds the argument for the policies and the triggers; what is here is the model
that mirrors them. Until these tables `brain.identity.teams.TeamMembership` was a type no table held
and `brain.console.organisation` said so on the screen: a team was listed with nobody under it and a
department with no lead, because nothing anywhere recorded either.

**A placement confers nothing, and that is why these are not grant tables.** Being in the design
team or leading sales is where somebody sits. What they may see is still only what their grants
say: no resolver reads either table, `gate.resolve_entitlements` is untouched, and neither table
bumps `gate.grants_version`, because a write that moves no reach invalidating every cached answer
in the company would be a cost with nothing bought. The names say `membership` and `lead` rather
than anything with `grant` in it, so `brain.ops.sweeps.sweep_grant_isolation`, which finds grant
tables by name, does not hold a record of where people sit to the rules for a record of reach. The
day a team becomes a grant's subject (`brain.identity.teams.TeamSubject`) is the day a bump trigger
belongs on `team_membership`, and `brain.identity.lifecycle` says so.

**Ending a placement marks the row and never removes it.** `ended_at` and `ended_by` move from
nothing to a value once, which is the only update the application role may make, and somebody
placed again is a new row. One live membership per person per team, and one live lead per
department, as partial unique indexes, so the history of every placement stays and a second live
row is refused by the table as well as by the store. No `deleted_at` and no `SoftDeleteMixin`, for
`brain.tables.connector_connection`'s reason: an ended placement is not retired, it is the record
that somebody sat somewhere and when that stopped.

**The person is a foreign key and the actors are values.** A placement of somebody this install
has never heard of is not a placement, so `principal_id` points at `auth.principal`, `RESTRICT`,
as a grant's does. Who placed them and who ended it are values, for `brain.tables.credential`'s
reason about `written_by`: the record of who put somebody in a team outlives the person who did.
Both are held to the ledger's actor grammar, because each is read off the row by the trigger as
the entry's actor, and a value the ledger refuses would roll the placement back.

**The directory sync is an actor too, and it is spelled so the ledger can hold it.**
`brain.identity.staff_sync.ROSTER_PREFIX` is `roster:`, and the ledger's actor grammar admits no
colon, so a placement the sync wrote under that prefix could never be recorded. `SYNC_ACTOR_PREFIX`
is `roster.`, which the grammar admits and no principal id this install mints begins with, and it
is what lets the sync end only the placements it made.

Task ids: M27.7.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: What the actor column says on a placement the directory sync made, before the source's name.
SYNC_ACTOR_PREFIX: Final = "roster."


def _actor_shape(column: str, *, nullable: bool = False) -> str:
    """The ledger's actor grammar on one column, so the trigger's append cannot be refused."""
    shaped = f"{column} ~ '{IDENTIFIER}'"
    return f"{column} IS NULL OR {shaped}" if nullable else shaped


class TeamMembershipRow(Base):
    """`gate.team_membership`. One person in one team, from when, by whom, and when that ended."""

    __tablename__ = "team_membership"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gate.team.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    principal_id: Mapped[str] = mapped_column(
        String(PRINCIPAL_ID_CHARS),
        ForeignKey("auth.principal.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: Who placed them: a principal, or `SYNC_ACTOR_PREFIX` and the source. The entry's actor.
    added_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The database's clock, in the transaction the ledger entry is appended in.
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_actor_shape("added_by"), name="added_by_shape"),
        CheckConstraint(_actor_shape("ended_by", nullable=True), name="ended_by_shape"),
        CheckConstraint(
            "(ended_at IS NULL) = (ended_by IS NULL)", name="an_ending_names_who_and_when"
        ),
        # One live membership per person per team. See the module docstring.
        Index(
            "uq_team_membership_team_id_principal_id_live",
            "team_id",
            "principal_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        {"schema": "gate"},
    )


class DepartmentLeadRow(Base):
    """`gate.department_lead`. Who leads one department, from when, by whom, and when that ended.

    One live lead per department. A department with two leads has no answer to "who leads it",
    which is the only question the row exists to answer, and appointing a new lead is ending the
    old one and writing the new one in one transaction.
    """

    __tablename__ = "department_lead"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gate.department.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    principal_id: Mapped[str] = mapped_column(
        String(PRINCIPAL_ID_CHARS),
        ForeignKey("auth.principal.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    appointed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    appointed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_actor_shape("appointed_by"), name="appointed_by_shape"),
        CheckConstraint(_actor_shape("ended_by", nullable=True), name="ended_by_shape"),
        CheckConstraint(
            "(ended_at IS NULL) = (ended_by IS NULL)", name="an_ending_names_who_and_when"
        ),
        Index(
            "uq_department_lead_department_id_live",
            "department_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        {"schema": "gate"},
    )
