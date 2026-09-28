"""The tool catalogue as the database holds it, and the switch that stops a tool.

**`agent.tool_definition`: one row per tool name this install has registered (M12.1.1).** Written
from the frozen registry by `brain.ops.tool_store.record_definition`, never deleted, and carrying
the name under the closed grammar as a check constraint derived from
`brain.core.envelope.TOOL_NAME_PATTERN`, so the database refuses a name no registry would accept.
Beside it: the capability the tool needs, its side effect, whether a person approves every call,
the sensitive effect it names, its result contract (M12.1.4) and its identity mode. SELECT, INSERT
and UPDATE of the described columns, and no DELETE: a tool a release stops registering keeps its
row, so a stop naming it still points at something.

**`agent.tool_switch`: the stops (M12.4.3).** One live row is one tool switched off for the whole
install, `department` null, or stopped for one department's people. Switching back on retires the
row with `deleted_at`, `switched_on_by` and `on_reason`; nothing is ever deleted, and there is no
row that says a tool is on. One live stop per tool and department, the install's included, by a
partial unique index over `coalesce(department, '')`. The policies are `0109`'s for a retirable
table, so a retired stop is invisible to the application from the statement that retires it.

**`agent.record_tool_switch` audits every change** as a `setting` entry under
`setting:tool_switch.<id>`: `off` on an insert, `on` on a retirement, with the tool, whether the
stop was the install's or a department's, and the department as a sha256 digest, because a
department's name is not a field name and the ledger refuses anything that is not a name or a
digest (`brain.audit.ledger.redact_details`). Neither reason is in the entry: a reason is prose an
administrator typed and routinely names a client or a person.

**The downgrade** drops the trigger, the function and both tables. The stops go with their table,
which is the state before this release: nothing could be switched off.

Task ids: M12.1.1, M12.1.4, M12.4.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0117"
# The newest migration on origin/main when this was written. The coordinator re-points it at
# landing, since 0110 to 0116 are held by packages landing before this one.
down_revision = "0108"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.tool_definition", "agent.tool_switch")

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to `brain.tables.tool_definition` by
#: `tests/unit/test_tool_switch.py`.
TOOL_NAME_CHARS = 80
ENTITY_CHARS = 60
DESCRIPTION_CHARS = 400
CAPABILITY_CHARS = 200
VOCABULARY_CHARS = 32
DEPARTMENT_CHARS = 120
PRINCIPAL_ID_CHARS = 128
TOOL_NAME_GRAMMAR = r"name ~ '^([a-z][a-z0-9_]*)\.([a-z][a-z0-9]*)_([a-z][a-z0-9_]*)$'"
ENTITY_GRAMMAR = "entity ~ '^[a-z][a-z0-9_]*$'"
CAPABILITY_GRAMMAR = (
    r"required_capability ~ '^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*|\.\*)*$'"
)
SIDE_EFFECTS = "side_effect IN ('draft', 'money', 'none', 'send', 'write')"
RESULT_CONTRACTS = "result_contract IN ('opaque', 'typed')"
IDENTITY_MODES = "identity_mode IN ('delegated', 'service')"
SENSITIVE_EFFECTS = (
    "sensitive_effect IS NULL OR sensitive_effect IN ('client_message', 'deletion', "
    "'dns_or_hosting', 'financial_record', 'production_change', 'publication', 'quotation')"
)

DEFINITION_GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.tool_definition TO brain_app",
    "GRANT UPDATE (source, entity, description, required_capability, side_effect, sensitive, "
    "sensitive_effect, result_contract, identity_mode, updated_at) "
    "ON agent.tool_definition TO brain_app",
)

DEFINITION_RLS: tuple[str, ...] = (
    "ALTER TABLE agent.tool_definition ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY tool_definition_readable ON agent.tool_definition
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY tool_definition_insertable ON agent.tool_definition
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY tool_definition_updatable ON agent.tool_definition
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

SWITCH_GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.tool_switch TO brain_app",
    "GRANT UPDATE (deleted_at, updated_at, switched_on_by, on_reason) "
    "ON agent.tool_switch TO brain_app",
)

SWITCH_RLS: tuple[str, ...] = (
    "ALTER TABLE agent.tool_switch ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY tool_switch_live ON agent.tool_switch
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY tool_switch_insertable ON agent.tool_switch
        FOR INSERT TO brain_app
        WITH CHECK (deleted_at IS NULL)
    """,
    """
    CREATE POLICY tool_switch_updatable ON agent.tool_switch
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
)

#: The append, `0003`'s block, over one change, as `0109` copies it.
_APPEND = """
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
        v_seq, v_at, v_actor, v_action, v_subject, v_ent_hash, v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, v_action, v_subject, v_ent_hash, v_trace,
                v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the ledger already holds seq ' || v_seq
                      || '; the audit entry was not appended',
            ERRCODE = 'restrict_violation',
            HINT = 'an append that is discarded silently is the failure this refuses';
    END IF;
"""

_DECLARATIONS = """
    v_action text;
    v_actor text;
    v_supplied text;
    v_writer text;
    v_subject text;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

_SWITCH_AUDIT_TEMPLATE = """
CREATE FUNCTION agent.record_tool_switch() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE__DECLARATIONS__BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        END IF;
        v_details := jsonb_build_object('change', 'off');
        v_writer := NEW.switched_off_by;
    ELSE
        IF OLD.deleted_at IS NOT NULL OR NEW.deleted_at IS NULL THEN
            RETURN NULL;
        END IF;
        v_details := jsonb_build_object('change', 'on');
        v_writer := NEW.switched_on_by;
    END IF;
    v_action := 'setting';
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, v_writer);
    v_subject := 'setting:tool_switch.' || NEW.id::text;
    v_details := v_details || jsonb_build_object(
        'source', 'tool_switch',
        'tool', NEW.tool_name,
        'scope', CASE WHEN NEW.department IS NULL THEN 'install' ELSE 'department' END
    );
    IF NEW.department IS NOT NULL THEN
        v_details := v_details || jsonb_build_object(
            'department_digest', encode(sha256(convert_to(NEW.department, 'UTF8')), 'hex')
        );
    END IF;
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
"""

SWITCH_AUDIT_FUNCTION = _SWITCH_AUDIT_TEMPLATE.replace("__DECLARATIONS__", _DECLARATIONS).replace(
    "__APPEND__", _APPEND
)

SWITCH_AUDIT_TRIGGER = """
CREATE TRIGGER tool_switch_is_audited
    AFTER INSERT OR UPDATE ON agent.tool_switch
    FOR EACH ROW EXECUTE FUNCTION agent.record_tool_switch()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in (*DEFINITION_GRANTS, *SWITCH_GRANTS))
    assert all("DELETE" not in statement for statement in (*DEFINITION_GRANTS, *SWITCH_GRANTS))

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "tool_definition",
        sa.Column("name", sa.String(TOOL_NAME_CHARS), nullable=False),
        sa.Column("source", sa.String(TOOL_NAME_CHARS), nullable=False),
        sa.Column("entity", sa.String(ENTITY_CHARS), nullable=False),
        sa.Column("description", sa.String(DESCRIPTION_CHARS), nullable=False),
        sa.Column("required_capability", sa.String(CAPABILITY_CHARS), nullable=False),
        sa.Column("side_effect", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("sensitive", sa.Boolean(), nullable=False),
        sa.Column("sensitive_effect", sa.String(VOCABULARY_CHARS), nullable=True),
        sa.Column("result_contract", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("identity_mode", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("name", name="pk_tool_definition"),
        sa.CheckConstraint(TOOL_NAME_GRAMMAR, name="name_grammar"),
        sa.CheckConstraint("source = split_part(name, '.', 1)", name="source_is_the_name_prefix"),
        sa.CheckConstraint(ENTITY_GRAMMAR, name="entity_grammar"),
        sa.CheckConstraint(CAPABILITY_GRAMMAR, name="required_capability_grammar"),
        sa.CheckConstraint(SIDE_EFFECTS, name="side_effect"),
        sa.CheckConstraint(RESULT_CONTRACTS, name="result_contract"),
        sa.CheckConstraint(IDENTITY_MODES, name="identity_mode"),
        sa.CheckConstraint(SENSITIVE_EFFECTS, name="sensitive_effect"),
        sa.CheckConstraint(
            "sensitive_effect IS NULL OR (sensitive AND side_effect <> 'none')",
            name="a_named_effect_is_sensitive",
        ),
        sa.CheckConstraint("length(btrim(description)) > 0", name="description_present"),
        schema="agent",
    )
    for statement in DEFINITION_RLS:
        op.execute(statement)
    for statement in DEFINITION_GRANTS:
        op.execute(statement)

    op.create_table(
        "tool_switch",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(TOOL_NAME_CHARS), nullable=False),
        sa.Column("department", sa.String(DEPARTMENT_CHARS), nullable=True),
        sa.Column("switched_off_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("off_reason", sa.Text(), nullable=True),
        sa.Column("switched_on_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("on_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tool_switch"),
        sa.CheckConstraint(
            "department IS NULL OR length(btrim(department)) > 0", name="department_present"
        ),
        sa.CheckConstraint(
            "off_reason IS NULL OR length(btrim(off_reason)) > 0", name="off_reason_present"
        ),
        sa.CheckConstraint(
            "on_reason IS NULL OR length(btrim(on_reason)) > 0", name="on_reason_present"
        ),
        sa.ForeignKeyConstraint(
            ["tool_name"],
            ["agent.tool_definition.name"],
            name="fk_tool_switch_tool_name_tool_definition",
            ondelete="RESTRICT",
        ),
        schema="agent",
    )
    op.create_index(
        "ix_agent_tool_switch_deleted_at", "tool_switch", ["deleted_at"], schema="agent"
    )
    op.create_index(
        "uq_tool_switch_tool_name_department_live",
        "tool_switch",
        ["tool_name", sa.text("coalesce(department, '')")],
        unique=True,
        schema="agent",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    for statement in SWITCH_RLS:
        op.execute(statement)
    for statement in SWITCH_GRANTS:
        op.execute(statement)
    op.execute(SWITCH_AUDIT_FUNCTION)
    op.execute(SWITCH_AUDIT_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER tool_switch_is_audited ON agent.tool_switch")
    op.execute("DROP FUNCTION agent.record_tool_switch()")
    op.drop_index("uq_tool_switch_tool_name_department_live", "tool_switch", schema="agent")
    op.drop_index("ix_agent_tool_switch_deleted_at", "tool_switch", schema="agent")
    op.drop_table("tool_switch", schema="agent")
    op.drop_table("tool_definition", schema="agent")
