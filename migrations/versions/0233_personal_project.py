"""A person's own project: a name, and the threads and files they put in it.

M40.7.7 asks that a person can group their own threads and uploaded files into a project, and that a
run inside it reads those files as project context. Nothing grouped anything.

**`agent.project` is one person's, and nobody else's, ever.** An id, the person, a name and when it
was made, and when they put it away. **`agent.project_item` is one thing in it**: a thread or a file,
named by its id, once. The thread and the file stay where they are (`chat.conversation` and
`know.item`), so a project is a list of references and never a copy: a file the person has since lost
the right to read is still on the list and is not read, because the reader asks the reach as it
stands when the run is made. **A project is context for a run and never memory**: nothing here is read
by the memory store, and a project put away stops being read.

**Read, written, changed and removed only by its owner**: every policy asks the person the session
names, and an item's policies ask it of the project the item belongs to, so there is no way to put a
thing in somebody else's project or to read a list of theirs. A project is put away by setting
`archived_at`, and an item is taken out by deleting it.

**The downgrade** drops both tables: no project exists, the threads and files they listed are where
they were, and no run reads project context.

Task ids: M40.7.7

Revision ID: 0233
Revises: 0232
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0233"
# Follows 0232, the personal skill table, so the two land in this order. Nothing here depends on
# anything after 0225.
down_revision = "0232"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. The items point at their project; the project, the thread and
#: the file are otherwise values.
TABLES: tuple[str, ...] = ("agent.project", "agent.project_item")

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.project`.
PRINCIPAL_ID_CHARS = 128
NAME_CHARS = 120
REF_CHARS = 128
KIND_CHARS = 16
KINDS: tuple[str, ...] = ("file", "thread")

PRINCIPAL = "current_setting('app.principal_id', true)"
OWNS_THE_PROJECT = (
    f"EXISTS (SELECT 1 FROM agent.project p WHERE p.id = project_id AND p.owner_id = {PRINCIPAL})"
)

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.project ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY project_seen_by_its_owner ON agent.project
        FOR SELECT TO brain_app
        USING (owner_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY project_made_by_its_owner ON agent.project
        FOR INSERT TO brain_app
        WITH CHECK (owner_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY project_changed_by_its_owner ON agent.project
        FOR UPDATE TO brain_app
        USING (owner_id = {PRINCIPAL})
        WITH CHECK (owner_id = {PRINCIPAL})
    """,
    "ALTER TABLE agent.project_item ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY project_item_seen_by_the_owner ON agent.project_item
        FOR SELECT TO brain_app
        USING ({OWNS_THE_PROJECT})
    """,
    f"""
    CREATE POLICY project_item_added_by_the_owner ON agent.project_item
        FOR INSERT TO brain_app
        WITH CHECK ({OWNS_THE_PROJECT})
    """,
    f"""
    CREATE POLICY project_item_taken_out_by_the_owner ON agent.project_item
        FOR DELETE TO brain_app
        USING ({OWNS_THE_PROJECT})
    """,
)

#: A project's name and its putting away may change; an item is added and taken out and never
#: changed. No project is ever deleted.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.project TO brain_app",
    "GRANT UPDATE (name, archived_at) ON agent.project TO brain_app",
    "GRANT SELECT, INSERT, DELETE ON agent.project_item TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    op.create_table(
        "project",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("name", sa.String(NAME_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(btrim(owner_id)) > 0", name="owner_present"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_present"),
        schema="agent",
    )
    op.create_index("ix_agent_project_owner_id", "project", ["owner_id"], schema="agent")
    op.create_table(
        "project_item",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(KIND_CHARS), nullable=False),
        sa.Column("ref", sa.String(REF_CHARS), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("project_id", "kind", "ref"),
        sa.ForeignKeyConstraint(["project_id"], ["agent.project.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{one}'" for one in KINDS) + ")", name="kind_known"
        ),
        sa.CheckConstraint("length(btrim(ref)) > 0", name="ref_present"),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The index, the policies and the grants go with the tables.
    op.drop_table("project_item", schema="agent")
    op.drop_table("project", schema="agent")
