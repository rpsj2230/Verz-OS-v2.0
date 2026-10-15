"""`agent.template_withdrawal`: a template version withdrawn from new installs, or its undoing.

`agent.template_version` is SELECT and INSERT only (`brain.tables.template`), so a published
version cannot be marked, amended or removed, and every agent installed from one pins its digest.
Hiding a version from the gallery is therefore a row of its own, which is what the architecture
asked for (docs/admin-console-architecture.md, C2). `0261` builds it, and
`brain.ops.template_withdrawal_store` is its one writer.

**One row per change, and the newest row for a version is its state.** A version with no row was
never withdrawn; `withdrawn` true says it is withdrawn from that row on, false says the withdrawal
was undone. Nothing is updated to say a withdrawal ended, so what a version was is in the rows
before the newest, the shape `brain.tables.skill.SkillRetirementRow` has for a skill.

**Keyed to the version, and to nothing else.** The composite key names a version somebody published,
because withdrawing a version nobody published would be a statement about nothing. It names no
instance: an installed agent's pin is `agent.template_instance`'s, and a withdrawal neither reads
nor changes it, which is how installed agents stay pinned.

**A withdrawal says why.** The reason is a sentence for the people who read the Templates page,
required where `withdrawn` is true and optional on an undo. It is not put in the ledger, whose
details admit field names and digests and redact prose.

Task ids: M27.15.35
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: The longest reason a withdrawal may give, which is a sentence and not a document.
REASON_CHARS: Final = 240


class TemplateWithdrawalRow(Base):
    """A template version withdrawn from new installs, or the withdrawal undone. `0261`."""

    __tablename__ = "template_withdrawal"

    #: The order rows were written in, which is what "newest" means here.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    template_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: True from this row on the version is withdrawn; false, the withdrawal is undone.
    withdrawn: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(REASON_CHARS), nullable=True)
    #: Who withdrew it or undid it. The ledger entry's actor, read off this column by the trigger.
    set_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("version >= 1", name="version_is_positive"),
        CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        CheckConstraint(
            "reason IS NULL OR length(btrim(reason)) > 0", name="a_reason_is_a_sentence"
        ),
        CheckConstraint("NOT withdrawn OR reason IS NOT NULL", name="a_withdrawal_says_why"),
        ForeignKeyConstraint(
            ["template_id", "version"],
            ["agent.template_version.template_id", "agent.template_version.version"],
        ),
        Index("ix_agent_template_withdrawal_version", "template_id", "version", "seq"),
        {"schema": "agent"},
    )
