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

**The template is required, and an authored automation carries the placeholder `authored`.**
`brain.console.automation_authoring` lets a person write one, and `0225` gives it eleven nullable
columns for what they said: the trigger, the cadence a schedule needs, one condition, the
instruction and the tools it names. They are nullable so that a row installed from a template
carries none of them, which `ck_automation_only_an_authored_row_carries_authoring` holds, and the
unique constraint on agent, template and person became an index that leaves authored rows out, so a
person may write as many as they like and still cannot press Install twice.

Task ids: M39.6.1.3, M39.9.2.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
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
SOURCE_CHARS: Final = 200
FIELD_CHARS: Final = 200
VALUE_CHARS: Final = 200
TOOL_CHARS: Final = 200

#: The placeholder template id an authored automation carries, `brain.console.automation_authoring.
#: AUTHORED_TEMPLATE`, restated for the reason `TEMPLATE_ID_PATTERN` is, and held equal by a test.
AUTHORED_TEMPLATE: Final = "authored"

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


#: What an authored row says, name and expression, held where a row cannot get round it. `0225`
#: argues each rule and carries the same text, held equal to this by a test.
AUTHORING_CHECKS: Final[tuple[tuple[str, str], ...]] = (
    (
        "only_an_authored_row_carries_authoring",
        (
            "template_id = 'authored' OR (trigger_kind IS NULL AND trigger_source IS NULL AND "
            "cadence_every IS NULL AND cadence_hour IS NULL AND cadence_weekday IS NULL AND "
            "condition_field IS NULL AND condition_op IS NULL AND condition_value IS NULL AND "
            "instruction IS NULL AND tools IS NULL AND from_template_id IS NULL)"
        ),
    ),
    (
        "an_authored_row_has_an_instruction_and_tools",
        (
            "NOT (template_id = 'authored') OR (instruction IS NOT NULL AND "
            "length(btrim(instruction)) >= 12 AND length(instruction) <= 2000 AND tools IS NOT "
            "NULL)"
        ),
    ),
    (
        "an_authored_row_has_one_of_three_triggers",
        (
            "NOT (template_id = 'authored') OR (trigger_kind IS NOT NULL AND trigger_kind IN "
            "('schedule', 'connector_event', 'webhook'))"
        ),
    ),
    (
        "only_a_schedule_has_a_cadence",
        (
            "NOT (template_id = 'authored') OR ((trigger_kind = 'schedule') = (cadence_every IS "
            "NOT NULL))"
        ),
    ),
    (
        "a_cadence_is_all_its_parts_or_none",
        (
            "(cadence_every IS NULL AND cadence_hour IS NULL AND cadence_weekday IS NULL) OR "
            "(cadence_every IS NOT NULL AND cadence_every IN ('day', 'weekday', 'week') AND "
            "cadence_hour IS NOT NULL AND cadence_hour BETWEEN 0 AND 23 AND ((cadence_every = "
            "'week') = (cadence_weekday IS NOT NULL)) AND (cadence_weekday IS NULL OR "
            "cadence_weekday BETWEEN 0 AND 6))"
        ),
    ),
    (
        "only_an_event_or_a_webhook_has_a_source",
        (
            "NOT (template_id = 'authored') OR ((trigger_kind = 'schedule') = (trigger_source "
            "IS NULL))"
        ),
    ),
    (
        "a_condition_is_all_its_parts_or_none",
        (
            "(condition_field IS NULL AND condition_op IS NULL AND condition_value IS NULL) OR "
            "(condition_field IS NOT NULL AND condition_op IS NOT NULL AND condition_op IN "
            "('equals', 'is_over', 'is_under', 'contains', 'within_days') AND condition_value "
            "IS NOT NULL AND length(btrim(condition_value)) > 0)"
        ),
    ),
    (
        "a_source_template_is_a_template_id",
        ("from_template_id IS NULL OR from_template_id ~ '^[a-z][a-z0-9_]{2,63}$'"),
    ),
)


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
    #: What a person wrote, and null on a row installed from a template. See the module docstring.
    #: `brain.orchestration.unattended.TriggerKind`'s value.
    trigger_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: The connector a connector event listens to, or the endpoint a webhook is called at.
    trigger_source: Mapped[str | None] = mapped_column(String(SOURCE_CHARS), nullable=True)
    #: A schedule's cadence, as `brain.console.automation_gallery.Cadence` holds it.
    cadence_every: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cadence_hour: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    cadence_weekday: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: One comparison: a field a connected system reports, a named operation and a value.
    condition_field: Mapped[str | None] = mapped_column(String(FIELD_CHARS), nullable=True)
    condition_op: Mapped[str | None] = mapped_column(String(32), nullable=True)
    condition_value: Mapped[str | None] = mapped_column(String(VALUE_CHARS), nullable=True)
    #: What the agent is told to do on each run. Prose, and never parsed.
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The tools it names. Naming one grants nothing: the run still intersects with the ceiling.
    tools: Mapped[list[str] | None] = mapped_column(ARRAY(String(TOOL_CHARS)), nullable=True)
    #: The template it was started from, when it was.
    from_template_id: Mapped[str | None] = mapped_column(String(TEMPLATE_ID_CHARS), nullable=True)

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
        *(CheckConstraint(expression, name=name) for name, expression in AUTHORING_CHECKS),
        # One install per agent, template and person, except for an authored row, which has no
        # template. `uq_` because `brain.db.NAMING_CONVENTION` has no `constraint_name` token for a
        # unique index either, so the name carries the prefix itself.
        Index(
            "uq_automation_one_install_per_agent_template_and_person",
            "agent_id",
            "template_id",
            "runs_as_id",
            unique=True,
            postgresql_where=text(f"template_id <> '{AUTHORED_TEMPLATE}'"),
        ),
        {"schema": "agent"},
    )
