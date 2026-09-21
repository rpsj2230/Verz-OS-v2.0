"""`ops.requirement_check`: a person's check of one requirement on this install, kept for good.

Four leaves ask the same thing of four areas: every permissions, departments, models and
observability requirement in the register "is demonstrated on an install by a person, and each check
is recorded against the requirement it proves" (M1.8.8, M2.3.2, M5.6.5, M24.3.6). Until this table
a check lived in a conversation or a commit message, which is where the first brief lived, and the
tracker audit of 2026-09-17 reopened a thousand tasks because nothing on the install recorded what
anybody had seen work. This is that record: who checked which requirement, on which release, what
they found, and a sentence saying what they did.

**Append only, and a later check supersedes an earlier one rather than editing it.** A requirement
checked on one release and failing on the next is two facts, and the second must not erase the
first: that it used to pass is exactly what somebody reading a regression needs. SELECT and INSERT
for the application role, row-level security with a policy for each and no other, for `0093`'s
reason. The screen reads the newest check per requirement.

**The requirement is named by its register id and not by a foreign key**, because the register is
a file shipped with the release, not a table: `docs/requirements/register.json`. A check naming an
id the register no longer carries is still a fact about what was checked on that day, and the
screen shows it as belonging to a requirement that has since been retired rather than dropping it.

**`release_commit` is the commit the install was running**, read from the image's
`RELEASE.json`, so "passed" is always "passed on this build". Null on a process with no manifest,
which is a development checkout, and the screen says so rather than inventing one.

**The note is a sentence about what the person did and saw, bounded, and never a value from the
company's data.** It is not written to the ledger, and it is shown only to holders of the check
authority. Rejected: a ledger entry per check. The ledger's actions and subject kinds are closed,
a check is neither a grant nor a setting, and a new kind is a new question for Needs Rupash item
48's list of what a department head reads; the row is already attributed and nothing edits it.

Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.tables.identity import one_of

#: A register id: `ARC-A-001`, `DEC-30`, `GAP2-03`, `FEAT-1.10`. Read off the register's rows.
REQUIREMENT_ID_PATTERN: Final = r"^[A-Z][A-Z0-9]*(-[A-Z0-9.]+)+$"
REQUIREMENT_ID_CHARS: Final = 32

#: A commit, as the release manifest records one.
COMMIT_PATTERN: Final = r"^[0-9a-f]{7,40}$"

#: What a note may hold: a few sentences about what was done and seen, never a document.
NOTE_CHARS: Final = 1000

#: The principal who checked. `IDENTIFIER` is bounded at 128.
CHECKED_BY_CHARS: Final = 128


class CheckOutcome(enum.StrEnum):
    """What the person found. Two, because a check that was not finished is not a check."""

    PASSED = "passed"
    FAILED = "failed"


class RequirementCheckRow(Base):
    """`ops.requirement_check`. One person's check of one requirement, on one release."""

    __tablename__ = "requirement_check"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    requirement_id: Mapped[str] = mapped_column(String(REQUIREMENT_ID_CHARS), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    checked_by: Mapped[str] = mapped_column(String(CHECKED_BY_CHARS), nullable=False)
    #: The database's clock, which is the one instant here nobody chose.
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    release_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"requirement_id ~ '{REQUIREMENT_ID_PATTERN}'", name="requirement_id_shape"
        ),
        CheckConstraint(one_of("outcome", CheckOutcome), name="outcome"),
        CheckConstraint(f"checked_by ~ '{IDENTIFIER}'", name="checked_by_shape"),
        CheckConstraint(
            f"release_commit IS NULL OR release_commit ~ '{COMMIT_PATTERN}'",
            name="release_commit_shape",
        ),
        CheckConstraint(
            f"length(btrim(note)) >= 1 AND length(note) <= {NOTE_CHARS}", name="note_is_a_sentence"
        ),
        Index("ix_requirement_check_requirement_id", "requirement_id", "checked_at"),
        {"schema": "ops"},
    )
