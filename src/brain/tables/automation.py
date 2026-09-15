"""An automation gets a row naming its owner, its credential's digest and its declared ceiling.

`brain.ops.automation_owner` holds the argument for the shape; `docs/needs-rupash.md` item 56
is the decision behind it. What is kept is who the automation runs as and how far it may reach,
and nothing about what that person holds: the owner's entitlements are resolved on every call,
so a column of them would be a grant that outlived its own deletion.

**No standing column.** Whether an automation is running or awaiting an owner is derived from
the owner's principal record when a call arrives. See
`brain.ops.automation_owner.AN_OWNERLESS_AUTOMATION_STOPS_AND_WAITS`.

**No side-effect column.** See `AN_AUTOMATION_READS_UNTIL_ITS_WRITES_CAN_BE_SUSPENDED`.

**The ceiling is JSON grants, and the tools are a text array.** A ceiling is a set of grants
with scopes, which is a model and not a column shape, and it is rebuilt through `Grant` on every
read so a row edited into something `Grant` refuses is refused rather than served. The tools are
names the projector compares exactly, so an array of strings is their whole shape.

**No foreign key to `auth.principal`, and no `deleted_at`.** The owner is a value, for the
reason `0014` gives about an agent: a key into the principal table would make deleting a person
delete the record of what ran in their name, and an automation whose owner has gone must stay
visible so somebody adopts it. Retiring an automation is not built.

Task ids: none
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, TimestampMixin
from brain.gate.leash import IDENTIFIER
from brain.ops.automation_owner import AUTOMATION_ID, DIGEST

#: Widths, named once so the model, the migration and the store agree.
ID_CHARS: Final = 128
DIGEST_CHARS: Final = 64
#: `brain.ops.automation_piece.PieceStep.tool`'s own bound.
TOOL_CHARS: Final = 80


class AutomationOwnerRow(TimestampMixin, Base):
    """`gate.automation_owner`. One automation, who it runs as, and how far it may reach."""

    __tablename__ = "automation_owner"

    automation_id: Mapped[str] = mapped_column(String(ID_CHARS), primary_key=True)
    #: The person this automation runs as. A value, never a key; see the module docstring.
    owner_principal_id: Mapped[str] = mapped_column(String(ID_CHARS), nullable=False)
    credential_digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    declared_tools: Mapped[list[str]] = mapped_column(ARRAY(String(TOOL_CHARS)), nullable=False)
    #: `Grant` dumps. The set is rebuilt under the automation's id on read.
    ceiling: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        CheckConstraint(f"automation_id ~ '{AUTOMATION_ID}'", name="automation_id_shape"),
        CheckConstraint(
            f"owner_principal_id ~ '{IDENTIFIER}'", name="owner_principal_id_is_an_identifier"
        ),
        CheckConstraint(
            "owner_principal_id <> automation_id", name="an_automation_is_not_its_owner"
        ),
        CheckConstraint(f"credential_digest ~ '{DIGEST}'", name="credential_digest_shape"),
        CheckConstraint("cardinality(declared_tools) > 0", name="a_tool_is_declared"),
        CheckConstraint("jsonb_typeof(ceiling) = 'array'", name="a_ceiling_is_a_list_of_grants"),
        Index("ix_automation_owner_owner_principal_id", "owner_principal_id"),
        {"schema": "gate"},
    )
