"""An automation installed onto an agent: one row that is the automation and its registry entry.

`brain.console.automation_gallery` holds the argument for the install and
`migrations/versions/0055_agent_automation.py` the argument for the policies and the trigger. What
is here is the model that mirrors them.

**One row, not two tables.** `brain.console.agent_automations` describes an automation and its
scheduled job registry entry as two values that must never disagree, and checks the pair with
`registry_gaps` because nothing had stored either. Stored, the two halves share every column but
one: the entry is the automation's id, agent, task, principal and next run, plus the sentence
saying what breaks if it does not run. So `guards` is a column here and the entry is read back out
of the same row, and "updated in the same transaction" becomes "written in the same statement",
which is the stronger property. A second table would be a second place for the next run to be
written, which is the disagreement `registry_gaps` exists to find.

**No `paused` column**, for `A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE`.
Paused is `next_run_at IS NULL`.

**The principal is a value and never a key**, for the reason `brain.tables.automation` gives about
an owner: a key into `auth.principal` would make retiring a person delete, or refuse to delete, the
record of what ran in their name. The agent is a value too, because an agent is archived rather
than deleted and a key would guard a deletion nothing performs.

**The template is required, because the gallery is the only writer.** An automation built by hand
rather than installed is a different leaf with no surface, and the migration that gives it one
relaxes these two columns along with the unique constraint that reads them.

Task ids: M39.6.1.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base, TimestampMixin
from brain.ops.automation_owner import AUTOMATION_ID
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: Widths, named once so the model, the migration and the store agree.
AUTOMATION_ID_CHARS: Final = 128
AGENT_ID_CHARS: Final = 128
NAME_CHARS: Final = 200
TASK_CHARS: Final = 80
TEMPLATE_ID_CHARS: Final = 64

#: `brain.console.automation_gallery.TEMPLATE_ID`, restated rather than imported because this
#: package sits underneath the console; a test holds the two equal.
TEMPLATE_ID_PATTERN: Final = r"^[a-z][a-z0-9_]{2,63}$"

#: `brain.console.agent_automations.FIRST_PERSON_OPENER` and `MINIMUM_OUTCOME_NAME`, and
#: `MINIMUM_GUARDS`, restated for the same reason and held equal by the same test.
FIRST_PERSON_OPENER: Final = "I "
MINIMUM_OUTCOME_NAME: Final = 12
MINIMUM_GUARDS: Final = 12

#: The prefix `brain.agents.model.CEILING_PRINCIPAL_PREFIX` puts on an agent's ceiling set.
CEILING_PRINCIPAL_PREFIX: Final = "agent:"


class AgentAutomationRow(TimestampMixin, Base):
    """`agent.automation`. One automation an agent owns, whose grants it runs at, and when next."""

    __tablename__ = "automation"

    automation_id: Mapped[str] = mapped_column(String(AUTOMATION_ID_CHARS), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    #: An outcome in the first person. `brain.console.agent_automations.outcome_name_refusals`.
    name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    #: The principal whose grants it runs at. A value; see the module docstring.
    runs_as_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    task: Mapped[str] = mapped_column(String(TASK_CHARS), nullable=False)
    #: When it next runs, or null when nothing will pick it up.
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The registry entry's sentence: what breaks if this does not run.
    guards: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[str] = mapped_column(String(TEMPLATE_ID_CHARS), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Who installed it. The audit entry's actor, read off this column by the trigger.
    installed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(f"automation_id ~ '{AUTOMATION_ID}'", name="automation_id_shape"),
        CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        CheckConstraint(f"runs_as_id ~ '{IDENTIFIER}'", name="runs_as_id_is_an_identifier"),
        CheckConstraint(f"installed_by ~ '{IDENTIFIER}'", name="installed_by_is_an_identifier"),
        CheckConstraint(
            f"runs_as_id <> agent_id AND runs_as_id <> ('{CEILING_PRINCIPAL_PREFIX}' || agent_id)",
            name="an_automation_does_not_run_as_its_agent",
        ),
        CheckConstraint(
            f"left(name, {len(FIRST_PERSON_OPENER)}) = '{FIRST_PERSON_OPENER}' "
            f"AND length(btrim(name)) >= {MINIMUM_OUTCOME_NAME}",
            name="name_is_an_outcome",
        ),
        CheckConstraint("length(btrim(task)) > 0", name="task_present"),
        CheckConstraint(
            f"length(btrim(guards)) >= {MINIMUM_GUARDS}", name="guards_says_what_breaks"
        ),
        CheckConstraint(f"template_id ~ '{TEMPLATE_ID_PATTERN}'", name="template_id_shape"),
        CheckConstraint("template_version >= 1", name="template_version_from_one"),
        UniqueConstraint(
            "agent_id",
            "template_id",
            "runs_as_id",
            name="one_install_per_agent_template_and_person",
        ),
        {"schema": "agent"},
    )
