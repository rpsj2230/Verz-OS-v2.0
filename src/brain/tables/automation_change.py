"""Every pause, resume, schedule change, removal and adoption of an installed automation.

`brain.console.automations` decides each of them and `migrations/versions/0145_automation_change.py`
argues the policies and the trigger. What is here is the model that mirrors them.

**Insert only, and read as a fold.** `agent.automation` is the install as it was made and the
application may move nothing on it but the next run. So a change of cadence or of owner is not an
edit of that row: it is a row here, and what an automation is now is the install with its changes
folded over it, newest last (`brain.console.automations.folded`). Rejected: granting UPDATE on the
install's `runs_as_id`. A second permissive update policy cannot narrow the one `0067` already
grants, so the adopter could not be pinned to the session's own principal, and the record of whose
automation it was before would be gone the moment it was overwritten.

**One row per change, and each kind carries exactly what it changed.** A schedule change carries
its cadence and nothing else does; an adoption carries the new owner and nothing else does; a
resume leaves a next run and a pause, a removal and an adoption leave none. The constraints below
are that sentence, so a row cannot say it was a pause and name a cadence.

**An adoption is always in the adopter's own name.** `runs_as_id = changed_by` is a constraint, and
the insert policy pins `changed_by` to the session's principal, so nobody can hand an automation to
somebody else and have it run at that person's reach.

**Points at the automation by value**, for the reason `brain.tables.agent_automation` gives: the
record of a change outlives anything that would delete what it changed.

Task ids: M27.12.3, M27.15.37, M39.6.1.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.ops.automation_owner import AUTOMATION_ID
from brain.tables.agent_automation import (
    AGENT_ID_CHARS,
    AUTOMATION_ID_CHARS,
    CEILING_PRINCIPAL_PREFIX,
)
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: `brain.console.automations.ChangeKind`, restated rather than imported because this package sits
#: underneath the console; `tests/unit/test_automation_change_store.py` holds the two equal.
PAUSED: Final = "paused"
RESUMED: Final = "resumed"
RESCHEDULED: Final = "rescheduled"
REMOVED: Final = "removed"
ADOPTED: Final = "adopted"
CHANGE_KINDS: Final[tuple[str, ...]] = (PAUSED, RESUMED, RESCHEDULED, REMOVED, ADOPTED)

#: `brain.console.automation_gallery.Every`, restated for the same reason and held equal by the
#: same test. `WEEK` is the one that names a day.
EVERY: Final[tuple[str, ...]] = ("day", "weekday", "week")
WEEK: Final = "week"

#: A kind's width. The longest member is well inside it.
KIND_CHARS: Final = 16
EVERY_CHARS: Final = 8


class AutomationChangeRow(Base):
    """`agent.automation_change`. One change to one automation, by whom, when, and what it left."""

    __tablename__ = "automation_change"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    automation_id: Mapped[str] = mapped_column(String(AUTOMATION_ID_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    #: The next run the change left: set for a resume, and for a schedule change while running.
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: A schedule change's cadence. `brain.console.automation_gallery.Cadence`'s three fields.
    every: Mapped[str | None] = mapped_column(String(EVERY_CHARS), nullable=True)
    #: Monday is nought. Only for a weekly cadence.
    weekday: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    hour_utc: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: The owner an adoption leaves. A value, never a key; always the adopter.
    runs_as_id: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    #: Who changed it. The ledger entry's actor, read off this column by the trigger.
    changed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The change's own instant.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"automation_id ~ '{AUTOMATION_ID}'", name="automation_id_shape"),
        CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        CheckConstraint(f"changed_by ~ '{IDENTIFIER}'", name="changed_by_is_an_identifier"),
        CheckConstraint(one_of("kind", CHANGE_KINDS), name="kind"),
        CheckConstraint(f"every IS NULL OR {one_of('every', EVERY)}", name="every"),
        CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6", name="weekday_is_a_day"),
        CheckConstraint("hour_utc IS NULL OR hour_utc BETWEEN 0 AND 23", name="hour_is_an_hour"),
        CheckConstraint(
            f"(kind = '{RESCHEDULED}') = (every IS NOT NULL AND hour_utc IS NOT NULL)",
            name="a_cadence_exactly_when_rescheduled",
        ),
        CheckConstraint(
            f"(every IS NOT DISTINCT FROM '{WEEK}') = (weekday IS NOT NULL)",
            name="a_day_exactly_when_weekly",
        ),
        CheckConstraint(
            f"(kind = '{ADOPTED}') = (runs_as_id IS NOT NULL)",
            name="an_owner_exactly_when_adopted",
        ),
        CheckConstraint(
            f"runs_as_id IS NULL OR (runs_as_id = changed_by AND runs_as_id <> agent_id"
            f" AND runs_as_id <> ('{CEILING_PRINCIPAL_PREFIX}' || agent_id))",
            name="an_adoption_is_in_the_adopters_own_name",
        ),
        CheckConstraint(
            f"kind NOT IN ('{PAUSED}', '{REMOVED}', '{ADOPTED}') OR next_run_at IS NULL",
            name="a_stop_leaves_no_next_run",
        ),
        CheckConstraint(
            f"kind <> '{RESUMED}' OR next_run_at IS NOT NULL",
            name="a_resume_leaves_a_next_run",
        ),
        Index("ix_automation_change_automation_at", "automation_id", "at"),
        {"schema": "agent"},
    )
