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


class AutomationChangeRow(Base := __import__("brain.db", fromlist=["Base"]).Base):  # type: ignore[misc,valid-type]
    pass
