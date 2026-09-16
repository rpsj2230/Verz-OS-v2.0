"""Two tables: what a learning proposed and what it replaced, and every correction since.

Storage for `brain.memory.digest.Learning` and for `brain.memory.correction`'s two corrections.
Until 2026-09-17 both were values that every function in `brain.memory` built and returned "for
whoever owns the table", and no table existed. So the Learning screen's undo had nothing to write,
the Memory screen's history had no record of what a memory replaced, and recall had nothing to
read that could make an undo change what it returned.

**`mem.learning` is the half of a `Learning` the memory tables do not hold.** `mem.persistent` and
`mem.adaptive` hold the formation and the statement; this holds the proposal (the change and the
tier its blast radius needs), the agent that was running, the evidence kinds and the memory it
replaced. Keyed by the memory id, one row per memory, because a memory is proposed once. Rejected:
columns on the two memory tables. Both grant INSERT and SELECT only, a column added now would be
null on every row already written, and `brain.tables.memory` gives the argument against a nullable
column a later reader treats as a value.

**The tier is stored and the database refuses one the change does not need.** A check constraint
built from `brain.memory.tiers.BLAST_RADIUS` pairs each change with its tier, so a row claiming a
scope widening is tier one is refused by the table as well as by `Proposal`. The row can arrive
from a migration, a backfill or a psql session, none of which construct a `Proposal`, which is
`brain.tables.memory`'s argument about the capability tags.

**`mem.correction` is one row per correction, both kinds in one table.** A supersession names the
memory marked, the memory that replaced it and the signal that prompted it; a demotion names the
memory and the field the correction was about. One table rather than two, because recall asks one
question, `brain.memory.correction.corrected`, and two tables are two loads of which one gets
forgotten at a call site. The shape of each kind is a check constraint, so a supersession with no
replacement and a demotion carrying a signal are both refused.

**Neither table holds what anybody said**, for the reason `brain.memory.correction` gives: a
correction log holding the old and the new text is a transcript under permissions belonging to
neither conversation. The statements stay in the memory tables under the capability tags they were
formed with, and a diff is computed at read time from two admissions.

**SELECT and INSERT only, on both, and no `updated_at`.** A correction is undone by a later
correction the other way, which `correction.superseded_ids` reads as the pair's latest word, never
by editing or deleting the row that made it. `brain.memory.correction.A_DELETED_MEMORY_CANNOT_
EXPLAIN_ITSELF` is the argument, and the grant is what makes it true of the database rather than of
the code that happens to write there today.

**A correction is audited and a learning is not.** A correction is somebody deciding the system
learnt something it should not have, which is the question an auditor asks. A tier-one learning is
the system acting within what `brain.memory.tiers` lets it do by itself, and a ledger entry per
inferred preference would bury the corrections among the ordinary. `0061`'s trigger writes the
entry on the correction's insert.

Task ids: M27.7.21, M27.7.22
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.memory.correction import Correction
from brain.memory.signals import Signal
from brain.memory.tiers import BLAST_RADIUS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide a memory id is: a ULID, the width `mem.persistent.id` and `mem.adaptive.id` declare.
MEMORY_ID_CHARS: Final = 26

#: How wide a change word may be. The longest today is `money_boundary_merge`, at twenty.
CHANGE_CHARS: Final = 32

#: How wide a signal word may be. The longest today is `contradicted`, at twelve.
SIGNAL_CHARS: Final = 32

#: How wide what a learning is about may be, and the field a demotion names. An opaque reference
#: the caller understands, never a value, so it is bounded as a reference is.
SUBJECT_CHARS: Final = 200

#: The widest correction word, `superseded`.
CORRECTION_CHARS: Final = 16


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


def change_needs_its_tier() -> str:
    """Every change paired with the tier its blast radius needs, and no other pairing.

    Generated from `BLAST_RADIUS` in the map's own order, for `one_of`'s reason: a hand-written
    list is a second copy of the policy, and the copy is the one that lowers a tier quietly.
    """
    return " OR ".join(
        f"(change = '{change.value}' AND tier = {int(tier)})"
        for change, tier in BLAST_RADIUS.items()
    )


def evidence_is_signals() -> str:
    """The evidence array holds signal words and nothing else. Sorted, as `one_of` sorts."""
    words = ", ".join(f"'{one}'" for one in sorted(signal.value for signal in Signal))
    return f"evidence <@ ARRAY[{words}]::varchar[]"


def a_correction_has_its_kinds_shape() -> str:
    """A supersession names its replacement and its signal; a demotion names a field and neither.

    One constraint over both kinds, so the failure names the whole rule, which is
    `brain.tables.memory._tags_are_a_real_requirement`'s argument for writing a rule once.
    """
    return (
        f"(correction = '{Correction.SUPERSEDED.value}' AND by_id IS NOT NULL "
        "AND prompted_by IS NOT NULL AND field IS NULL AND by_id <> memory_id) OR "
        f"(correction = '{Correction.DEMOTED.value}' AND by_id IS NULL "
        f"AND prompted_by IS NULL AND field IS NOT NULL AND {_present('field')})"
    )


class LearningRow(Base):
    """`mem.learning`. What one memory proposed, at which tier, while which agent ran.

    The formation and the statement are the memory row's, joined by `memory_id`. See the module
    docstring for why this is a table beside them rather than columns on them.
    """

    __tablename__ = "learning"

    #: The memory this learning is, in `mem.persistent` or `mem.adaptive`. No foreign key: the id
    #: may be in either table, and a key into one would refuse the other.
    memory_id: Mapped[str] = mapped_column(String(MEMORY_ID_CHARS), primary_key=True)
    #: `Proposal.change`, as its word.
    change: Mapped[str] = mapped_column(String(CHANGE_CHARS), nullable=False)
    #: `Proposal.tier`. Held to the change by `change_needs_its_tier`.
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: `Proposal.subject`: what the learning is about, as an opaque reference.
    subject: Mapped[str] = mapped_column(String(SUBJECT_CHARS), nullable=False)
    #: The agent that was running, or nothing for a learning from a plain conversation.
    agent_id: Mapped[str | None] = mapped_column(String(AGENT_ID_CHARS), nullable=True)
    #: The memory this one replaced, when it replaced one. What an undo restores, and what the
    #: Memory screen's history diffs against.
    replaced_id: Mapped[str | None] = mapped_column(String(MEMORY_ID_CHARS), nullable=True)
    #: The signal kinds that prompted it, as words. Never whose conversation they came from.
    evidence: Mapped[list[str]] = mapped_column(
        ARRAY(String(SIGNAL_CHARS)), nullable=False, server_default=text("'{}'")
    )
    #: When the row was written, by the database's clock. When the memory formed is the memory's.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"memory_id ~ '{IDENTIFIER}'", name="memory_id_shape"),
        CheckConstraint(one_of("change", (one.value for one in BLAST_RADIUS)), name="change"),
        CheckConstraint(change_needs_its_tier(), name="change_needs_its_tier"),
        CheckConstraint(_present("subject"), name="subject_present"),
        CheckConstraint(
            f"agent_id IS NULL OR {_present('agent_id')}", name="agent_id_present_when_named"
        ),
        CheckConstraint(
            "replaced_id IS NULL OR replaced_id <> memory_id", name="not_its_own_replacement"
        ),
        CheckConstraint(evidence_is_signals(), name="evidence_is_signals"),
        Index("ix_learning_agent_id", "agent_id"),
        {"schema": "mem"},
    )


class CorrectionRow(Base):
    """`mem.correction`. One supersession or one demotion, who recorded it and when.

    Append only. A correction is reversed by a later one the other way, never by changing this row.
    """

    __tablename__ = "correction"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The memory marked: `Supersession.superseded_id` or `Demotion.memory_id`. The ledger subject.
    memory_id: Mapped[str] = mapped_column(String(MEMORY_ID_CHARS), nullable=False)
    #: Which of the two, as `Correction`'s word.
    correction: Mapped[str] = mapped_column(String(CORRECTION_CHARS), nullable=False)
    #: `Supersession.by_id`: the memory that takes this one's place. Null on a demotion.
    by_id: Mapped[str | None] = mapped_column(String(MEMORY_ID_CHARS), nullable=True)
    #: `Supersession.prompted_by`, as the signal's word. Null on a demotion.
    prompted_by: Mapped[str | None] = mapped_column(String(SIGNAL_CHARS), nullable=True)
    #: `Demotion.field`. Null on a supersession.
    field: Mapped[str | None] = mapped_column(String(SUBJECT_CHARS), nullable=True)
    #: Who recorded it. The ledger entry's actor, read off this column by the trigger.
    recorded_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The correction's own instant, which `correction.superseded_ids` orders a pair's word by.
    #: Written by the store from the database's clock, read in the same transaction.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"memory_id ~ '{IDENTIFIER}'", name="memory_id_shape"),
        CheckConstraint(one_of("correction", Correction), name="correction"),
        CheckConstraint(
            f"prompted_by IS NULL OR {one_of('prompted_by', Signal)}", name="prompted_by"
        ),
        CheckConstraint(
            a_correction_has_its_kinds_shape(), name="a_correction_has_its_kinds_shape"
        ),
        CheckConstraint(f"recorded_by ~ '{IDENTIFIER}'", name="recorded_by_shape"),
        Index("ix_correction_memory_id", "memory_id"),
        Index("ix_correction_by_id", "by_id"),
        {"schema": "mem"},
    )
