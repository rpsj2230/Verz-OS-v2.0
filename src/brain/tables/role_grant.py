"""`gate.role_grant`: who holds a platform role, as a person granted it (M1.3.2).

The row behind `brain.identity.roles.RoleGrant`. `auth.directory_role_grant` records what a
directory asserts and is owned by the sync; this is what a person granted and is retired, never
deleted. `migrations/versions/0102_role_grant_and_team_grants.py` builds it with the guard that
keeps deputies depth one and the Super Admin floor at two, and the trigger that audits it.

`deputy_of` is the principal a deputy covers for, as `RoleGrant.deputy_of` is, so depth is a
question about that person's standing grant. `acknowledgement` is the reason somebody gave for
appointing one person to two roles the separation of duties keeps apart (M1.8.7).

Task ids: M1.3.2, M1.3.3, M1.8.7
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, SoftDeleteMixin, TimestampMixin
from brain.identity.roles import DEPUTY_MAX, SCOPE_REQUIRED, Role
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Wide enough for the longest role value with room.
ROLE_CHARS: Final = 32

#: The roles whose grant carries a scope, written from `SCOPE_REQUIRED`.
SCOPED: Final = one_of("role", SCOPE_REQUIRED)


class RoleGrantRow(TimestampMixin, SoftDeleteMixin, Base):
    """One person holding one role, optionally as a deputy, retired and never deleted."""

    __tablename__ = "role_grant"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    principal_id: Mapped[str] = mapped_column(
        String(PRINCIPAL_ID_CHARS),
        ForeignKey("auth.principal.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(ROLE_CHARS), nullable=False)
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    deputy_of: Mapped[str | None] = mapped_column(
        String(PRINCIPAL_ID_CHARS),
        ForeignKey("auth.principal.id", ondelete="RESTRICT"),
        nullable=True,
    )
    granted_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledgement: Mapped[str | None] = mapped_column(Text, nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(one_of("role", Role), name="role"),
        CheckConstraint(f"({SCOPED}) = (scope IS NOT NULL)", name="scope_exactly_when_required"),
        CheckConstraint(
            "scope IS NULL OR (jsonb_typeof(scope) = 'object' "
            "AND jsonb_typeof(scope -> 'clauses') = 'array')",
            name="scope_shape",
        ),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        CheckConstraint(
            "acknowledgement IS NULL OR length(btrim(acknowledgement)) > 0",
            name="acknowledgement_present",
        ),
        CheckConstraint(
            "deputy_of IS NULL OR deputy_of <> principal_id", name="not_its_own_deputy"
        ),
        CheckConstraint(
            "deputy_of IS NULL OR (not_after IS NOT NULL "
            f"AND not_after <= created_at + make_interval(days => {DEPUTY_MAX.days}))",
            name="a_deputy_is_bounded",
        ),
        Index("ix_gate_role_grant_principal_id", "principal_id"),
        Index(
            "uq_role_grant_principal_id_role_standing_live",
            "principal_id",
            "role",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND deputy_of IS NULL AND scope IS NULL"),
        ),
        {"schema": "gate"},
    )
