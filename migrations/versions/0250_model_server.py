"""The model server keeps its own measured peaks, and a passage and a document say how they were read.

Three small changes that belong to one piece of work (the model server, needs-rupash 119 and 120),
in one migration because the owner asked for one number for it.

**`ops.model_server_peak`** is a ring of the model server's measured memory peak for each batch it
serves, fifty to a part (`brain.tables.model_server` argues the shape). SELECT, INSERT and UPDATE
and never DELETE: the ring overwrites its oldest slot, so nothing grows and nothing is swept. Read
for whoever asks, because who may be shown it is the console's decision, made against the reader's
live grants before a statement is built.

**`know.chunk.parse_path` and `know.chunk.parse_engine`** record which reader produced a passage
(M7.7.9): the path, one of `layout`, `fallback` or `ocr`, which says what kind of evidence the text
is, and the engine's name, which says which program read it. Nullable, because every passage written
before this migration, and every passage the in-application reader writes, was read by neither: a
passage with no path is one the in-application text reader produced, and says so by saying nothing.
**Not defaulted to a path, for the reason a vector's model is not**: a column that said `layout` for
rows nobody recorded would be a claim about quality that nothing supports.

**`know.item.parse_notice`** is the one sentence an uploader can read about a document that was
read in part (M7.7.10): that a page was left out of the index because it could not be read
clearly, naming the page. Nullable and short, and a sentence from the product's own wording that
names a page number and nothing from the document.

**The downgrade** drops the table and the three columns. The passages and the items stay; they lose
only the record of how they were read, which is what the columns were.

Task ids: M7.2.1, M7.3.3, M7.7.9, M7.7.10

Revision ID: 0250
Revises: 0241
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0250"
down_revision = "0241"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: a peak is a fact about a machine.
TABLES: tuple[str, ...] = ("ops.model_server_peak",)

#: The columns this adds to `know.chunk`, which `0009` built, declared here for the reason `0024`'s
#: `ADDS_COLUMNS` gives: `tests/unit/test_search.py` compares the table `0009` builds with the
#: model column by column and exempts what a later migration says it added, so a column added
#: without saying so is a failure of that comparison and not a drift nobody sees.
ADDS_COLUMNS: tuple[str, ...] = ("parse_path", "parse_engine")

#: The column this adds to `know.item`, named for that table so the chunk comparison above is not
#: told about a column on a different one (the convention `0115` sets).
ITEM_COLUMNS_ADDED: tuple[str, ...] = ("parse_notice",)

APP_ROLE = "brain_app"

#: Widths and bounds held equal to `brain.tables.model_server`, `brain.knowledge.search` and
#: `brain.tables.knowledge`.
PART_CHARS = 16
MODEL_CHARS = 80
RING_SLOTS = 50
PATH_CHARS = 16
ENGINE_CHARS = 64
NOTICE_CHARS = 400

#: `brain.ops.model_server.Part` and `brain.knowledge.parse_paths.ParsePath` on the day this ran.
PARTS: tuple[str, ...] = ("embedding", "entities", "layout", "ocr", "tika")
PATHS: tuple[str, ...] = ("fallback", "layout", "ocr")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.model_server_peak ENABLE ROW LEVEL SECURITY",
    # Open to the application role: the figures describe a machine, and who is shown them is the
    # route's decision, so a second statement of it here would be a second place to be wrong.
    """
    CREATE POLICY model_server_peak_visible ON ops.model_server_peak
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

#: SELECT, INSERT and UPDATE, and never DELETE: the ring overwrites its own oldest slot.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT, UPDATE ON ops.model_server_peak TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "model_server_peak",
        sa.Column("part", sa.String(PART_CHARS), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("batch_no", sa.BigInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(MODEL_CHARS), nullable=False),
        sa.Column("items", sa.Integer(), nullable=False),
        sa.Column("request_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("anon_peak_mib", sa.Integer(), nullable=False),
        sa.Column("cache_peak_mib", sa.Integer(), nullable=False),
        sa.Column("cgroup_limit_mib", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("part", "slot"),
        sa.CheckConstraint(_one_of("part", PARTS), name="part"),
        sa.CheckConstraint(f"slot >= 0 AND slot < {RING_SLOTS}", name="slot_in_the_ring"),
        sa.CheckConstraint("batch_no >= 1", name="batch_is_counted_from_one"),
        sa.CheckConstraint("length(btrim(model)) > 0", name="model_present"),
        sa.CheckConstraint("items >= 0", name="items_not_negative"),
        sa.CheckConstraint("request_bytes >= 0", name="request_not_negative"),
        sa.CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        sa.CheckConstraint("anon_peak_mib >= 0", name="anonymous_not_negative"),
        sa.CheckConstraint("cache_peak_mib >= 0", name="cache_not_negative"),
        sa.CheckConstraint(
            "cgroup_limit_mib IS NULL OR cgroup_limit_mib > 0", name="limit_positive_when_known"
        ),
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.add_column(
        "chunk", sa.Column("parse_path", sa.String(PATH_CHARS), nullable=True), schema="know"
    )
    op.add_column(
        "chunk", sa.Column("parse_engine", sa.String(ENGINE_CHARS), nullable=True), schema="know"
    )
    op.create_check_constraint(
        "parse_path_is_a_path",
        "chunk",
        f"parse_path IS NULL OR {_one_of('parse_path', PATHS)}",
        schema="know",
    )
    # Both or neither, as two one-way constraints rather than one equality: the compatibility gate
    # (`brain.deployment.compatibility`) reads a restriction that begins `<new column> IS NULL OR`
    # as binding only rows the previous release cannot write, and an equality it cannot read is a
    # finding. Together they say exactly what the equality said.
    op.create_check_constraint(
        "parse_engine_follows_its_path",
        "chunk",
        "parse_path IS NULL OR parse_engine IS NOT NULL",
        schema="know",
    )
    op.create_check_constraint(
        "parse_path_follows_its_engine",
        "chunk",
        "parse_engine IS NULL OR parse_path IS NOT NULL",
        schema="know",
    )
    op.add_column(
        "item", sa.Column("parse_notice", sa.String(NOTICE_CHARS), nullable=True), schema="know"
    )


def downgrade() -> None:
    op.drop_column("item", "parse_notice", schema="know")
    # The bare names, with the type, so Alembic applies the naming convention to them as it did
    # when it created them. See 0007.
    op.drop_constraint("parse_path_follows_its_engine", "chunk", schema="know", type_="check")
    op.drop_constraint("parse_engine_follows_its_path", "chunk", schema="know", type_="check")
    op.drop_constraint("parse_path_is_a_path", "chunk", schema="know", type_="check")
    op.drop_column("chunk", "parse_engine", schema="know")
    op.drop_column("chunk", "parse_path", schema="know")
    # The policy, the grant and the constraints go with the table.
    op.drop_table("model_server_peak", schema="ops")
