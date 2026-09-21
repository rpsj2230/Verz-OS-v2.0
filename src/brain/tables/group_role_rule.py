"""`auth.group_role_rule`: which identity-provider group confers which platform role (M1.1.5).

The row behind `brain.identity.oidc.GroupRoleRule`, kept by an administrator on the Roles screen
rather than in a file, because which groups a company's directory holds is that company's fact and
never this repository's. `migrations/versions/0109_group_role_rule.py` builds it with the trigger
that audits every change.

**There is no capability column, and there is no version of this table with one.** A group maps
to a role and to nothing else (`brain.identity.oidc.CLAIMS_NEVER_GRANT`); a pack of capabilities
behind a group would move the answer to "who may see this client's margin" into a directory nobody
here reviews. The scope lives here and never on `auth.directory_role_grant`, for the reason that
table's model gives: the rule is the one reviewed copy.

Retired with `deleted_at`, and one live rule per group.

Task ids: M1.1.5
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from sqlalchemy import CheckConstraint, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, SoftDeleteMixin, TimestampMixin
from brain.identity.roles import SCOPE_REQUIRED, Role
from brain.tables.identity import PRINCIPAL_ID_CHARS, SOURCE_GROUP_CHARS, one_of

#: Wide enough for the longest role value with room, as `brain.tables.role_grant` has it.
ROLE_CHARS: Final = 32

#: The group as the identity provider spells it, as wide as the synced row's `source_group`, so
#: a rule the table accepts is always a group the sync can record.
GROUP_CHARS: Final = SOURCE_GROUP_CHARS

#: The roles whose rule carries a scope, written from `SCOPE_REQUIRED`.
SCOPED: Final = one_of("role", SCOPE_REQUIRED)


class GroupRoleRuleRow(TimestampMixin, SoftDeleteMixin, Base):
    """One group conferring one role, retired and never deleted."""

    __tablename__ = "group_role_rule"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    idp_group: Mapped[str] = mapped_column(String(GROUP_CHARS), nullable=False)
    role: Mapped[str] = mapped_column(String(ROLE_CHARS), nullable=False)
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("role", Role), name="role"),
        CheckConstraint(f"({SCOPED}) = (scope IS NOT NULL)", name="scope_exactly_when_required"),
        CheckConstraint(
            "scope IS NULL OR (jsonb_typeof(scope) = 'object' "
            "AND jsonb_typeof(scope -> 'clauses') = 'array')",
            name="scope_shape",
        ),
        CheckConstraint("length(btrim(idp_group)) > 0", name="group_present"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        Index(
            "uq_group_role_rule_idp_group_live",
            "idp_group",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "auth"},
    )
