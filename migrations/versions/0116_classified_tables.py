"""A price list held as classified rows: the table, its classification, and its rows.

**`know.classified_table`: one uploaded table (M7.7.3).** Keyed on the entity every capability is
written against, carrying the administrator's title, the column a question names a row by, the
classification as one JSON array, and which upload's rows are live. `brain.tables.classified_table`
argues why the classification is one array on this row rather than a row per column in
`gate.field_policy`. SELECT, INSERT and UPDATE; retired with `deleted_at` and never deleted, with
`0045`'s three policies, so a retired table can be neither read nor changed again.

**`know.classified_row`: every row of every upload.** Keyed on the entity, the upload's version
and the row's position, and written once. SELECT and INSERT only, so a price somebody quoted
from can never be edited after the fact. `USING (true)`: which of a row's columns a person may
read is a function of their grants, which no policy can see, and the row plane composes both
the column list and the row scope into the one statement that reads these rows.

**`know.record_classified_table` audits every change to what a table discloses.** A `setting`
entry under `setting:classified_table.<entity>`, saying whether the table was uploaded, uploaded
again, classified or retired. A change to the classification is a change to who may read a
column, so it is the entry an auditor asks for after a cost was seen by somebody it should not
have been; the rows themselves are values and are never copied into the ledger.

**The downgrade** drops the trigger, its function and both tables, rows first. The rows go with
them, which is the state before this release: no price list was held as rows.

Task ids: M7.5.1, M7.5.3, M7.7.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0116"
# The newest migration on origin/main when this was written.
down_revision = "0108"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("know.classified_table", "know.classified_row")

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to the model by `tests/unit/test_classified_tables.py`.
ENTITY_CHARS = 60
COLUMN_CHARS = 60
TITLE_CHARS = 200
PRINCIPAL_ID_CHARS = 128
#: `brain.core.envelope.OBJECT_NAME_PATTERN` and `brain.core.field_policy.NAME_PATTERN`, which are
#: one grammar today and are copied separately because they are two rules.
ENTITY_GRAMMAR = "^[a-z][a-z0-9_]*$"
NAME_GRAMMAR = "^[a-z][a-z0-9_]*$"

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON know.classified_table TO brain_app",
    "GRANT SELECT, INSERT ON know.classified_row TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE know.classified_table ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY classified_table_live ON know.classified_table
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY classified_table_insertable ON know.classified_table
        FOR INSERT TO brain_app
        WITH CHECK (deleted_at IS NULL)
    """,
    """
    CREATE POLICY classified_table_updatable ON know.classified_table
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "ALTER TABLE know.classified_row ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY classified_row_readable ON know.classified_row
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY classified_row_insertable ON know.classified_row
        FOR INSERT TO brain_app
        WITH CHECK (true)
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

_AUDIT_TEMPLATE = """
CREATE FUNCTION know.record_classified_table() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE__DECLARATIONS__BEGIN
    IF TG_OP = 'INSERT' THEN
        v_details := jsonb_build_object('change', 'uploaded');
    ELSIF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
        v_details := jsonb_build_object('change', 'retired');
    ELSIF NEW.version <> OLD.version THEN
        v_details := jsonb_build_object('change', 'uploaded_again');
    ELSIF NEW.columns IS DISTINCT FROM OLD.columns OR NEW.key_column <> OLD.key_column THEN
        v_details := jsonb_build_object('change', 'classified');
    ELSE
        RETURN NULL;
    END IF;
    v_action := 'setting';
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, NEW.updated_by);
    v_subject := 'setting:classified_table.' || NEW.entity;
    v_details := v_details || jsonb_build_object('source', 'classified_table');
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
"""

AUDIT_FUNCTION = _AUDIT_TEMPLATE.replace("__DECLARATIONS__", _DECLARATIONS).replace(
    "__APPEND__", _APPEND
)

AUDIT_TRIGGER = """
CREATE TRIGGER classified_table_is_audited
    AFTER INSERT OR UPDATE ON know.classified_table
    FOR EACH ROW EXECUTE FUNCTION know.record_classified_table()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "classified_table",
        sa.Column("entity", sa.String(ENTITY_CHARS), nullable=False),
        sa.Column("title", sa.String(TITLE_CHARS), nullable=False),
        sa.Column("key_column", sa.String(COLUMN_CHARS), nullable=False),
        sa.Column("columns", JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("updated_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("entity", name="pk_classified_table"),
        sa.CheckConstraint(f"entity ~ '{ENTITY_GRAMMAR}'", name="entity_is_a_name"),
        sa.CheckConstraint(f"key_column ~ '{NAME_GRAMMAR}'", name="key_column_is_a_name"),
        sa.CheckConstraint("length(btrim(title)) > 0", name="titled"),
        sa.CheckConstraint("jsonb_typeof(columns) = 'array'", name="columns_is_an_array"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint("length(btrim(created_by)) > 0", name="created_by_present"),
        sa.CheckConstraint("length(btrim(updated_by)) > 0", name="updated_by_present"),
        schema="know",
    )
    op.create_index(
        "ix_know_classified_table_deleted_at", "classified_table", ["deleted_at"], schema="know"
    )
    op.create_table(
        "classified_row",
        sa.Column("entity", sa.String(ENTITY_CHARS), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("fields", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("entity", "version", "position", name="pk_classified_row"),
        sa.CheckConstraint("jsonb_typeof(fields) = 'object'", name="fields_is_an_object"),
        sa.CheckConstraint("position >= 0", name="position_not_negative"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["entity"],
            ["know.classified_table.entity"],
            name="fk_classified_row_entity_classified_table",
            ondelete="RESTRICT",
        ),
        schema="know",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(AUDIT_FUNCTION)
    op.execute(AUDIT_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER classified_table_is_audited ON know.classified_table")
    op.execute("DROP FUNCTION know.record_classified_table()")
    op.drop_table("classified_row", schema="know")
    op.drop_index("ix_know_classified_table_deleted_at", "classified_table", schema="know")
    op.drop_table("classified_table", schema="know")
