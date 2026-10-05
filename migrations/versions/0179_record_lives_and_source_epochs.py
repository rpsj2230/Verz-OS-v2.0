"""A retired record is remembered, a returned one serves again, a source has an epoch, a read keeps its place.

Three changes, for four leaves, and each is the smallest the leaf needs.

**`proj.record_retired`: a projected row as it stood when its source stopped returning it**
(M11.8.11). Since this release a complete read of everything a source holds retires the live rows
it no longer returned: one statement stamps each row's `deleted_at` with `statement_timestamp()`,
which `0045`'s policy already lets the application write and which hides the row from every read
at its role, and copies the row into this table with that instant as `noticed_at`. A record the
source returns afterwards is served again from its own row, because the new release's upsert clears
`deleted_at` on a row a sync retired (one whose `deleted_at` is a `noticed_at` here) and on no
other; the copy here is never touched again, so the retirement stays as it was. The application's
role may read and insert these rows, and no more. See `brain.tables.projection.RetiredRecordRow`.

**`proj.record` is not changed in shape, and that is the point.** The previous release's upserts
name `ON CONFLICT (source, entity, source_id)`, the primary key, and keep working through the deploy.
Its upsert updates only a live row, so a record the source returns in the window between this
migration and the previous release's container stopping stays hidden until the new release's next
read revives it: that is failing closed, and nothing is lost, because the record is read again.
Rejected, and measured by "The previous release runs on the new schema" on 2026-09-29: a minted key
with the triple unique over live rows only, under which every write the previous release made was
refused for the length of the deploy.

**`proj.source_epoch`: how many times a source's rows have changed** (M11.8.4). One row a source,
advanced in the transaction that changed the rows, read into the answer cache's key. The shape
`gate.policy_epoch` has: created on first use, readable and advanceable by the application, whose
acceptance checks drive the worker's own writes, and never deletable. See
`brain.tables.projection.SourceEpochRow`.

**`ops.connector_sync.read_state`: where reading a source stood when an attempt ended** (M11.4.6,
M11.4.8). Nullable, so every row already here and every test of a connection holds none, and the
worker reads the newest row that holds one. See `brain.tables.connector_sync`.

**The downgrade removes the retirement history with its table.** A record retired by this release
keeps its retired row in `proj.record`, which the previous schema understands; what goes is the
copy, and with it which retirements a sync made, so a downgrade leaves those rows retired for good
under `0045`'s rule, which is the previous release's behaviour.

Revises `0171`, the head of main when this was renumbered from `0152` on 2026-10-05.

Task ids: M11.4.6, M11.4.8, M11.8.4, M11.8.11

Revision ID: 0179
Revises: 0171
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0179"
down_revision = "0171"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("proj.record_retired", "proj.source_epoch")

APP_ROLE = "brain_app"

#: `brain.core.envelope.OBJECT_NAME_PATTERN`, copied for the same reason.
SOURCE_IS_A_NAME = "source ~ '^[a-z][a-z0-9_]*$'"

#: `brain.core.projection.MAX_PROJECTED_FIELDS` as `brain.tables.projection` renders its cap, and
#: `FIELDS_IS_AN_OBJECT`, copied for `0008`'s reason; `tests/unit/test_projection.py` holds the
#: table this builds equal to the model's.
FIELDS_IS_AN_OBJECT = "jsonb_typeof(fields) = 'object'"
FIELDS_WITHIN_THE_CAP = "jsonb_array_length(jsonb_path_query_array(fields, '$.keyvalue()')) <= 12"
ENTITY_IS_A_NAME = "entity ~ '^[a-z][a-z0-9_]*$'"

RLS: tuple[str, ...] = (
    "ALTER TABLE proj.record_retired ENABLE ROW LEVEL SECURITY",
    # A retirement is read and written by the application, and never changed or removed: there is
    # no UPDATE or DELETE grant for a policy to admit.
    """
    CREATE POLICY record_retired_readable ON proj.record_retired
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY record_retired_insertable ON proj.record_retired
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    "ALTER TABLE proj.source_epoch ENABLE ROW LEVEL SECURITY",
    # Every source's epoch is read on every cached question and is about nobody, so the policy
    # admits every row, as `gate.policy_epoch`'s does.
    """
    CREATE POLICY source_epoch_visible ON proj.source_epoch
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

#: No DELETE on either: a counter that could be removed could start again under an answer it
#: invalidated, and a retirement that could be changed or removed is not a record of one.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON proj.record_retired TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON proj.source_epoch TO brain_app",
)


def _create_record_retired() -> None:
    op.create_table(
        "record_retired",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("entity", sa.String(60), nullable=False),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("local_id", sa.String(128), nullable=True),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("noticed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_record_retired"),
        sa.CheckConstraint(SOURCE_IS_A_NAME, name="source_is_a_name"),
        sa.CheckConstraint(ENTITY_IS_A_NAME, name="entity_is_a_name"),
        sa.CheckConstraint(FIELDS_IS_AN_OBJECT, name="fields_is_an_object"),
        sa.CheckConstraint(FIELDS_WITHIN_THE_CAP, name="fields_within_the_cap"),
        schema="proj",
    )
    op.create_index(
        "ix_record_retired_record",
        "record_retired",
        ["source", "entity", "source_id", "noticed_at"],
        schema="proj",
    )


def _create_source_epoch() -> None:
    op.create_table(
        "source_epoch",
        sa.Column("source", sa.String(60), primary_key=True, nullable=False),
        sa.Column("epoch", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(SOURCE_IS_A_NAME, name="source_is_a_name"),
        sa.CheckConstraint("epoch >= 1", name="epoch_counts_a_change"),
        schema="proj",
    )


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)

    _create_record_retired()
    _create_source_epoch()
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.add_column(
        "connector_sync",
        sa.Column("read_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_column("connector_sync", "read_state", schema="ops")
    # The policy and the grant belong to the table and go with it.
    op.drop_table("source_epoch", schema="proj")
    op.drop_index("ix_record_retired_record", table_name="record_retired", schema="proj")
    op.drop_table("record_retired", schema="proj")
