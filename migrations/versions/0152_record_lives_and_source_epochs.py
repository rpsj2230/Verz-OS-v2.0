"""A record the source returns is a new live row, a source has an epoch, and a read keeps its place.

Three changes, for four leaves, and each is the smallest the leaf needs.

**`proj.record` is unique over its live rows, and its primary key is a minted `id`.** Since this
release a read of everything a source holds retires the rows it no longer returned, with when that
was noticed (M11.8.11), and a record the source later returns is a new live row while the retired
one stays as it was retired. Until now `(source, entity, source_id)` was the primary key over every
row, retired ones included, so that second row could not be written and a record retired wrongly
(a page the source skipped) would have been absent for good. `0045`'s update policy already makes
a retirement final, and it is not touched. `brain.tables.projection` argues the shape and what was
rejected. The column is added with a default the database mints per row, so every row already here
is given one, and the unique index is built over columns the dropped key already held unique over
every row, so neither can refuse a row the table holds.

**`proj.source_epoch`: how many times a source's rows have changed** (M11.8.4). One row a source,
advanced in the transaction that changed the rows, read into the answer cache's key. The shape
`gate.policy_epoch` has: created on first use, readable and advanceable by the application, whose
acceptance checks drive the worker's own writes, and never deletable. See
`brain.tables.projection.SourceEpochRow`.

**`ops.connector_sync.read_state`: where reading a source stood when an attempt ended** (M11.4.6,
M11.4.8). Nullable, so every row already here and every test of a connection holds none, and the
worker reads the newest row that holds one. See `brain.tables.connector_sync`.

**What the previous release sees during the swap, said out loud.** Its worker's upsert names
`ON CONFLICT (source, entity, source_id)`, and after this migration no unique index over exactly
those columns admits every row, so a page it writes in the window between this migration and its
container stopping is refused by the database. The attempt fails, is recorded as failed, and the
next attempt is the new release's, which names the index with its predicate. Nothing is lost: a
page not written is read again. `brain.deployment.compatibility` says in its own words that a
removed `ON CONFLICT` target is a fact about the previous release's code that it cannot see, and
that is exactly this. Rejected: two releases, the index first and the key second. The first
release could not write a returned record's new row, so the retirement this one ships would be
final for a record a skipped page retired wrongly, which is why `brain.ops.connector_sync` retired
nothing at all until now.

**The downgrade puts the old key back and fails loudly where it cannot.** A record retired and
returned has two rows under one triple, and the old primary key refuses them; PostgreSQL says so
and the downgrade stops, rather than removing a retired row to make room, which would delete the
record of a deletion.

Revises `0150`, the head of main when this was written.

Task ids: M11.4.6, M11.4.8, M11.8.4, M11.8.11

Revision ID: 0152
Revises: 0150
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0152"
down_revision = "0150"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("proj.source_epoch",)

APP_ROLE = "brain_app"

#: `brain.tables.projection.LIVE` and `LIVE_RECORD_INDEX`, copied for the reason `0008` gives:
#: a migration describes the database it built. `tests/unit/test_projection.py` holds them equal.
LIVE = "deleted_at IS NULL"
LIVE_RECORD_INDEX = "ux_record_live"

#: `brain.core.envelope.OBJECT_NAME_PATTERN`, copied for the same reason.
SOURCE_IS_A_NAME = "source ~ '^[a-z][a-z0-9_]*$'"

RLS: tuple[str, ...] = (
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

#: No DELETE: a counter that could be removed could start again under an answer it invalidated.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT, UPDATE ON proj.source_epoch TO brain_app",)


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

    # A record's lives: a minted key for every row, and the triple unique among live rows only.
    op.add_column(
        "record",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        schema="proj",
    )
    op.create_index(
        LIVE_RECORD_INDEX,
        "record",
        ["source", "entity", "source_id"],
        unique=True,
        schema="proj",
        postgresql_where=sa.text(LIVE),
    )
    op.drop_constraint("pk_record", "record", schema="proj", type_="primary")
    op.create_primary_key("pk_record", "record", ["id"], schema="proj")

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
    op.drop_constraint("pk_record", "record", schema="proj", type_="primary")
    # The natural key `0008` built.
    op.create_primary_key("pk_record", "record", ["source", "entity", "source_id"], schema="proj")
    op.drop_index(LIVE_RECORD_INDEX, table_name="record", schema="proj")
    op.drop_column("record", "id", schema="proj")
