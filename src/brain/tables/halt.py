"""`ops.halt`: every stop and every resume, one row per act, so a halt outlives the process.

`brain.ops.halt.Halt` is a value meant to be written down and read back after a restart, and until
this table nothing could hold one. **Insert-only**: a resume is a second row rather than an edit to
the first, so who stopped the system is never overwritten by who restarted it, and the state in
force is the latest row for a scope and a target. The application holds SELECT and INSERT and
nothing else, and may write a row only as the session's own principal.

**No effects column**, and no expiry column, which is `brain.ops.halt.halt_gaps`' refusal. Every
halt the console declares is `stop_everything`'s both effects, which is what `Halt` reads back as
by default, so a narrower halt is a column and a migration on the day something declares one.

The vocabularies are the domain's own: the act is `brain.audit.record.HaltAct` and the scope
`HaltScope`, each through `one_of`, and the reason's
floor is `brain.ops.halt.MINIMUM_REASON`, the same length a resume must reach. `0136` copies each,
and `tests/unit/test_halt_table.py` holds the copy to these.

Task ids: none
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.record import HaltAct
from brain.db import Base
from brain.ops.halt import MINIMUM_REASON, HaltScope
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: `resume` is the longest act.
ACT_CHARS: Final = 8

#: `everything` and `department` are the longest scopes, with room for one more.
SCOPE_CHARS: Final = 16

#: What a targeted halt names: a department slug, an agent slug, a connector or a principal id.
TARGET_CHARS: Final = 128

#: The role the actor held when they acted, for the reader deciding whether to resume.
ROLE_CHARS: Final = 64


class HaltRow(Base):
    """One halt or one resume, as it was declared, and never changed afterwards."""

    __tablename__ = "halt"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    act: Mapped[str] = mapped_column(String(ACT_CHARS), nullable=False)
    scope: Mapped[str] = mapped_column(String(SCOPE_CHARS), nullable=False)
    #: Empty for a halt on everything, and only then.
    target: Mapped[str] = mapped_column(String(TARGET_CHARS), nullable=False, server_default="")
    actor_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(ROLE_CHARS), nullable=False)
    #: For an administrator, and never shown to the person a halt refuses.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(one_of("act", HaltAct), name="act"),
        CheckConstraint(one_of("scope", HaltScope), name="scope"),
        CheckConstraint(
            "(scope = 'everything') = (target = '')", name="everything_names_no_target"
        ),
        CheckConstraint(
            f"char_length(btrim(reason)) >= {MINIMUM_REASON}", name="reason_says_something"
        ),
        Index("ix_ops_halt_scope_target_at", "scope", "target", "at"),
        {"schema": "ops"},
    )
