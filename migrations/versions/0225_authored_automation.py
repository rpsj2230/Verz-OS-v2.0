"""An automation a person wrote, rather than installed from a template, gets somewhere to be kept.

`brain.console.automation_authoring` lets a person start a new automation from a named outcome
template with its trigger, condition and instruction changed, or from a description in plain words.
`0055`'s row had one place for what it does, the template's task, and one place for when, the
template's cadence, so neither could be said by a person. This adds the columns that say them and
changes nothing about who may read or write the row.

**Columns on the row, not a second table.** `brain.tables.agent_automation` argues that an
automation and its registry entry are one row, so that "updated in the same transaction" is
"written in the same statement". What a person wrote is the same row's: a second table would be a
second place for the cadence to be read from, which is the disagreement that argument exists to
prevent, and the worker reads one row per automation. Every new column is nullable, and a check
holds the two shapes apart: a row installed from a template carries none of them, and a row
authored carries exactly what its trigger needs.

**The trigger is one of three kinds and the database says so.** `trigger_kind` is a closed list,
`brain.orchestration.unattended.TriggerKind`'s, and the columns each kind needs are required for it
and refused for the others, which is `unattended.Trigger`'s own rule written where a row cannot get
round it. A schedule carries its cadence in three columns, as `brain.console.automation_gallery.
Cadence` does, so the worker's next-run arithmetic is the one it already runs. A connector event
names the source it listens to and a webhook names its endpoint, both in `trigger_source`.

**The condition is one comparison and nothing the database could run.** Three columns, all or none:
a field a connected system reports, one of five named comparisons, and a value, held as text. No
expression, no operator a person types: `brain.console.automation_authoring.ConditionOp` is the
list, and the check admits those words and no others, so a row cannot hold code however it got
there. See needs-rupash 177.

**The instruction is prose for the agent and never parsed.** It is what the agent is told to do on
each run, held to the length `brain.console.automation_authoring` allows, and what it may use is
named in `tools`, which a run still intersects with the agent's own ceiling and the person's reach.
Naming a tool here grants nothing: `E_run(caller, agent) = E(caller) ∩ agent_ceiling`.

**Uniqueness moves to the installs.** `0055`'s unique constraint allowed one automation per agent,
template and person, so that pressing Install twice answered with the first. An authored automation
has no template, so it carries the placeholder id `authored` and a person may write as many as they
like. The constraint becomes a unique index over the same three columns for every row except an
authored one, and the store's `ON CONFLICT DO NOTHING` names no index, so the install is answered
exactly as before.

**The ledger entry says which kind of attachment it was.** `0055`'s trigger recorded every row as
`template_install`. The function is replaced with one that records `authored_install` for an
authored row, because an entry that said a person's own words were a product template would be a
record that lies. The details are otherwise `0055`'s, to the letter.

**No policy, grant or role changes.** `0055`'s insert policy admits a row whose runs-as and
installer are the session's principal, `0067`'s admits a read to everybody the application serves,
and neither mentions a column.

The downgrade refuses while an authored automation exists, because dropping the columns would turn
a person's own instruction into a row that silently does something else, and putting back the
unique constraint would fail on a person's second one. It says so and changes nothing.

Task ids: M39.9.2.1, M17.4.2

Revision ID: 0225
Revises: 0212
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0225"
down_revision = "0212"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: The placeholder template id an authored row carries, and `brain.console.automation_authoring.
#: AUTHORED_TEMPLATE`, held equal to it by `tests/unit/test_automation_authoring_store.py`.
AUTHORED = "authored"

#: `brain.orchestration.unattended.TriggerKind`, `brain.console.automation_gallery.Every` and
#: `brain.console.automation_authoring.ConditionOp`, copied for the reason `0009` gives and held
#: equal by the same test.
TRIGGER_KINDS = "('schedule', 'connector_event', 'webhook')"
EVERIES = "('day', 'weekday', 'week')"
CONDITION_OPS = "('equals', 'is_over', 'is_under', 'contains', 'within_days')"

#: The longest and shortest instruction a row may hold.
INSTRUCTION_MIN = 12
INSTRUCTION_MAX = 2000

#: What an authored row says, as one expression per rule so a failure names the rule.
IS_AUTHORED = f"template_id = '{AUTHORED}'"
NOT_AUTHORED_HAS_NONE = (
    f"{IS_AUTHORED} OR (trigger_kind IS NULL AND trigger_source IS NULL AND cadence_every IS NULL "
    "AND cadence_hour IS NULL AND cadence_weekday IS NULL AND condition_field IS NULL "
    "AND condition_op IS NULL AND condition_value IS NULL AND instruction IS NULL "
    "AND tools IS NULL AND from_template_id IS NULL)"
)
AUTHORED_HAS_AN_INSTRUCTION = (
    f"NOT ({IS_AUTHORED}) OR (instruction IS NOT NULL "
    f"AND length(btrim(instruction)) >= {INSTRUCTION_MIN} "
    f"AND length(instruction) <= {INSTRUCTION_MAX} AND tools IS NOT NULL)"
)
AUTHORED_HAS_ONE_OF_THREE_TRIGGERS = (
    f"NOT ({IS_AUTHORED}) OR (trigger_kind IS NOT NULL AND trigger_kind IN {TRIGGER_KINDS})"
)
A_SCHEDULE_NAMES_ITS_CADENCE_AND_NOTHING_ELSE_DOES = (
    f"NOT ({IS_AUTHORED}) OR ((trigger_kind = 'schedule') = (cadence_every IS NOT NULL))"
)
A_CADENCE_IS_ALL_ITS_PARTS_OR_NONE = (
    "(cadence_every IS NULL AND cadence_hour IS NULL AND cadence_weekday IS NULL) OR "
    f"(cadence_every IS NOT NULL AND cadence_every IN {EVERIES} "
    "AND cadence_hour IS NOT NULL AND cadence_hour BETWEEN 0 AND 23 AND "
    "((cadence_every = 'week') = (cadence_weekday IS NOT NULL)) AND "
    "(cadence_weekday IS NULL OR cadence_weekday BETWEEN 0 AND 6))"
)
AN_EVENT_OR_A_WEBHOOK_NAMES_ITS_SOURCE = (
    f"NOT ({IS_AUTHORED}) OR ((trigger_kind = 'schedule') = (trigger_source IS NULL))"
)
A_CONDITION_IS_ALL_ITS_PARTS_OR_NONE = (
    "(condition_field IS NULL AND condition_op IS NULL AND condition_value IS NULL) OR "
    f"(condition_field IS NOT NULL AND condition_op IS NOT NULL "
    f"AND condition_op IN {CONDITION_OPS} "
    "AND condition_value IS NOT NULL AND length(btrim(condition_value)) > 0)"
)
A_SOURCE_TEMPLATE_IS_A_TEMPLATE_ID = (
    "from_template_id IS NULL OR from_template_id ~ '^[a-z][a-z0-9_]{2,63}$'"
)

#: Name, expression, in the order they are created and dropped in reverse.
CHECKS: tuple[tuple[str, str], ...] = (
    ("only_an_authored_row_carries_authoring", NOT_AUTHORED_HAS_NONE),
    ("an_authored_row_has_an_instruction_and_tools", AUTHORED_HAS_AN_INSTRUCTION),
    ("an_authored_row_has_one_of_three_triggers", AUTHORED_HAS_ONE_OF_THREE_TRIGGERS),
    ("only_a_schedule_has_a_cadence", A_SCHEDULE_NAMES_ITS_CADENCE_AND_NOTHING_ELSE_DOES),
    ("a_cadence_is_all_its_parts_or_none", A_CADENCE_IS_ALL_ITS_PARTS_OR_NONE),
    ("only_an_event_or_a_webhook_has_a_source", AN_EVENT_OR_A_WEBHOOK_NAMES_ITS_SOURCE),
    ("a_condition_is_all_its_parts_or_none", A_CONDITION_IS_ALL_ITS_PARTS_OR_NONE),
    ("a_source_template_is_a_template_id", A_SOURCE_TEMPLATE_IS_A_TEMPLATE_ID),
)

#: `0055`'s unique constraint, and what replaces it.
OLD_UNIQUE = "uq_automation_agent_template_person"
ONE_INSTALL_INDEX = "uq_automation_one_install_per_agent_template_and_person"

#: Drops `0055`'s unique constraint over the three columns, whatever it is called.
DROP_THE_OLD_UNIQUE = f"""
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT c.conname INTO v_name
      FROM pg_constraint c
     WHERE c.conrelid = 'agent.automation'::regclass AND c.contype = 'u'
       AND c.conname = '{OLD_UNIQUE}';
    IF v_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE agent.automation DROP CONSTRAINT %I', v_name);
    END IF;
END
$$
"""

#: `0055`'s function, to the letter, with the reason code decided by the row.
AUTOMATION_INSTALL_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION agent.record_automation_install() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.agent_id;
    v_details jsonb := jsonb_build_object(
        'part', 'automation', 'reference', NEW.automation_id,
        'direction', 'attached',
        'reason_code', CASE WHEN NEW.template_id = 'authored'
                            THEN 'authored_install' ELSE 'template_install' END
    );
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32));
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, NEW.installed_by, 'compose_change', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.installed_by, 'compose_change', v_subject,
                v_ent_hash, v_trace, v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the ledger already holds seq ' || v_seq
                      || '; the audit entry was not appended',
            ERRCODE = 'restrict_violation',
            HINT = 'an append that is discarded silently is the failure this refuses';
    END IF;
    RETURN NULL;
END;
$$
"""

#: `0055`'s function as it shipped, which the downgrade puts back.
AUTOMATION_INSTALL_TRIGGER_FUNCTION_AS_0055_SHIPPED = AUTOMATION_INSTALL_TRIGGER_FUNCTION.replace(
    """'reason_code', CASE WHEN NEW.template_id = 'authored'
                            THEN 'authored_install' ELSE 'template_install' END""",
    "'reason_code', 'template_install'",
)

#: The columns added, name and type, in the order they are created.
COLUMNS: tuple[tuple[str, sa.types.TypeEngine[object]], ...] = (
    ("trigger_kind", sa.String(32)),
    ("trigger_source", sa.String(200)),
    ("cadence_every", sa.String(16)),
    ("cadence_hour", sa.SmallInteger()),
    ("cadence_weekday", sa.SmallInteger()),
    ("condition_field", sa.String(200)),
    ("condition_op", sa.String(32)),
    ("condition_value", sa.String(200)),
    ("instruction", sa.Text()),
    ("tools", sa.ARRAY(sa.String(200))),
    ("from_template_id", sa.String(64)),
)


def upgrade() -> None:
    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    for name, kind in COLUMNS:
        op.add_column("automation", sa.Column(name, kind, nullable=True), schema="agent")
    for name, expression in CHECKS:
        op.create_check_constraint(name, "automation", expression, schema="agent")
    # Found by what it covers rather than named, because the model no longer declares it and a
    # migration that drops a name no model declares is one `tests/unit/test_tables.py` refuses.
    op.execute(DROP_THE_OLD_UNIQUE)
    op.execute(
        f"CREATE UNIQUE INDEX {ONE_INSTALL_INDEX} ON agent.automation "
        f"(agent_id, template_id, runs_as_id) WHERE template_id <> '{AUTHORED}'"
    )
    op.execute(AUTOMATION_INSTALL_TRIGGER_FUNCTION)


def downgrade() -> None:
    # Offline, where SQL is only rendered, there is no database to ask, and the guard is a check on
    # the live one.
    if not op.get_context().as_sql:
        held = op.get_bind().execute(
            sa.text("SELECT count(*) FROM agent.automation WHERE template_id = :authored"),
            {"authored": AUTHORED},
        )
        if held.scalar_one():
            msg = (
                "an automation a person wrote is still stored, and this downgrade would turn "
                "their instruction into a row that does something else. Remove those "
                "automations first"
            )
            raise RuntimeError(msg)
    op.execute(AUTOMATION_INSTALL_TRIGGER_FUNCTION_AS_0055_SHIPPED)
    op.execute(f"DROP INDEX agent.{ONE_INSTALL_INDEX}")
    op.create_unique_constraint(
        OLD_UNIQUE,
        "automation",
        ["agent_id", "template_id", "runs_as_id"],
        schema="agent",
    )
    for name, _expression in reversed(CHECKS):
        op.drop_constraint(name, "automation", schema="agent", type_="check")
    for name, _kind in reversed(COLUMNS):
        op.drop_column("automation", name, schema="agent")
