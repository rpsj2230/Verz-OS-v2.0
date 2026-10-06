"""A connector for a new API is a reviewed row, and every submission and decision is on the ledger.

M11.7.8 asks that an administrator adds a connector for an API this release does not ship from the
console, by its specification, field mapping and credential reference, and that it becomes
available to agents after review without a release. `brain.ops.custom_connector` compiles a
definition into the declaration a shipped connector makes; this is where a definition is kept.

**`ops.custom_connector` is one row per definition, edited in place.** It holds the OpenAPI document
as submitted (JSON, bounded), the name, each entity's operations and field mapping with each
field's classification, the key scheme and credential shape (one of the existing members), the
ceiling with the vendor's page, the department, the submitter, the reviewer, the state and the
times. `brain.ops.connector_catalogue` reads the approved rows at every request and every worker
cycle, so approving one makes it available and changing one takes it away, with nothing restarted.

**Nobody reviews their own, and the database says so too.** A check constraint refuses a row whose
reviewer is its submitter, and the update policy admits a decision only when the reviewer is the
actor the transaction is attributed to, so the route's refusal is not the only one. An edit is the
other half: the update policy admits a row going back to unreviewed only with its submitter as the
attributed actor, and the decision constraint holds that an unreviewed row names no reviewer, so a
definition changed after approval is waiting again in the statement that changed it.

**Every submission, edit and decision is appended to the ledger by the database**, under the
source's own subject `connector:<name>`, with the change and the revision and never the document,
in the transaction that wrote the row. `0167`'s steward trigger is the template, and the ledger
append is `0003`'s.

SELECT, INSERT and UPDATE to the application role, and never DELETE: a definition nobody wants is
rejected, which is a decision the ledger records, rather than removed.

The downgrade drops the trigger, its function and the table; the ledger entries stay, for `0026`'s
reason.

Written as `0181` revising `0154`; renumbered `0203` revising `0202` when it joined the train.

Task ids: M11.7.8

Revision ID: 0203
Revises: 0202
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0203"
# The train's migration below it.
down_revision = "0202"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.custom_connector",)

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.custom_connector` by `tests/unit/test_custom_connector_store.py`.
CONNECTOR_CHARS = 64
CONNECTOR_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128
LABEL_CHARS = 80
CITED_CHARS = 500
DEPARTMENT_CHARS = 64
PARAMETER_CHARS = 80
DEPARTMENT_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
DOCUMENT_BYTES = 512 * 1024
STATES = ("unreviewed", "approved", "rejected")
KEY_SCHEMES = ("bearer", "basic_key_as_user", "none")
CREDENTIAL_SHAPES = ("key", "none")

#: The actor a transaction is attributed to, empty when none was set.
ACTOR = "NULLIF(current_setting('brain.actor_id', true), '')"


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{one}'" for one in values) + ")"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.custom_connector ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY custom_connector_readable ON ops.custom_connector
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY custom_connector_submitted_by_the_actor ON ops.custom_connector
        FOR INSERT TO brain_app
        WITH CHECK (state = 'unreviewed' AND submitted_by = {ACTOR})
    """,
    f"""
    CREATE POLICY custom_connector_changed_or_decided_by_the_actor ON ops.custom_connector
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (
            (state = 'unreviewed' AND submitted_by = {ACTOR})
            OR (state <> 'unreviewed' AND reviewed_by = {ACTOR} AND reviewed_by <> submitted_by)
        )
    """,
)

#: SELECT, INSERT and UPDATE. Never DELETE: a definition is rejected, not removed.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT, UPDATE ON ops.custom_connector TO brain_app",)

#: A submission, an edit or a decision, appended to the ledger under the source's subject.
TRIGGER_FUNCTION = """
CREATE FUNCTION ops.record_custom_connector() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'connector:' || NEW.name;
    v_change text;
    v_actor text;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.state = OLD.state AND NEW.revision = OLD.revision THEN
        RETURN NULL;
    END IF;
    IF NEW.state = 'unreviewed' THEN
        v_change := 'definition_submitted';
        v_actor := NEW.submitted_by;
    ELSE
        v_change := 'definition_' || NEW.state;
        v_actor := NEW.reviewed_by;
    END IF;
    v_details := jsonb_build_object('change', v_change, 'revision', NEW.revision);
    -- The append, as 0003's gate.record_entitlement_change and every trigger since write it.
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
        v_seq, v_at, v_actor, 'connector', v_subject, v_ent_hash, v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'connector', v_subject,
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

TRIGGER = """
CREATE TRIGGER custom_connector_is_audited
    AFTER INSERT OR UPDATE ON ops.custom_connector
    FOR EACH ROW EXECUTE FUNCTION ops.record_custom_connector()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "custom_connector",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(CONNECTOR_CHARS), nullable=False),
        sa.Column("label", sa.String(LABEL_CHARS), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("entities", postgresql.JSONB(), nullable=False),
        sa.Column("key_scheme", sa.String(32), nullable=False),
        sa.Column("credential_shape", sa.String(16), nullable=False),
        sa.Column("ceiling_per_minute", sa.Integer(), nullable=False),
        sa.Column("ceiling_per_day", sa.Integer(), nullable=True),
        sa.Column("ceiling_cited", sa.String(CITED_CHARS), nullable=False),
        sa.Column("department", sa.String(DEPARTMENT_CHARS), nullable=False),
        sa.Column("page_parameter", sa.String(PARAMETER_CHARS), nullable=True),
        sa.Column("page_size", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("submitted_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name"),
        sa.CheckConstraint(f"name ~ '{CONNECTOR_NAME_PATTERN}'", name="name_shape"),
        sa.CheckConstraint("length(btrim(label)) > 0", name="label_given"),
        sa.CheckConstraint(
            f"octet_length(document::text) <= {DOCUMENT_BYTES}", name="document_bounded"
        ),
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="document_is_an_object"),
        sa.CheckConstraint("jsonb_typeof(entities) = 'array'", name="entities_are_a_list"),
        sa.CheckConstraint(_one_of("key_scheme", KEY_SCHEMES), name="key_scheme"),
        sa.CheckConstraint(_one_of("credential_shape", CREDENTIAL_SHAPES), name="credential_shape"),
        sa.CheckConstraint("ceiling_per_minute > 0", name="ceiling_per_minute_measured"),
        sa.CheckConstraint(
            "ceiling_per_day IS NULL OR ceiling_per_day > 0", name="ceiling_per_day_measured"
        ),
        sa.CheckConstraint("ceiling_cited ~ '^https://'", name="ceiling_cited"),
        sa.CheckConstraint(f"department ~ '{DEPARTMENT_PATTERN}'", name="department_shape"),
        sa.CheckConstraint(
            "(page_parameter IS NULL) = (page_size IS NULL)", name="paging_whole_or_none"
        ),
        sa.CheckConstraint("page_size IS NULL OR page_size > 0", name="page_size_positive"),
        sa.CheckConstraint(_one_of("state", STATES), name="state"),
        sa.CheckConstraint("revision > 0", name="revision_positive"),
        sa.CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_shape"),
        sa.CheckConstraint(
            "(state = 'unreviewed') = (reviewed_by IS NULL AND reviewed_at IS NULL)",
            name="a_decision_names_its_reviewer",
        ),
        sa.CheckConstraint(
            "reviewed_by IS NULL OR reviewed_by <> submitted_by",
            name="nobody_reviews_their_own",
        ),
        schema="ops",
    )

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER custom_connector_is_audited ON ops.custom_connector")
    op.execute("DROP FUNCTION ops.record_custom_connector()")
    # The policies and the grant go with the table.
    op.drop_table("custom_connector", schema="ops")
