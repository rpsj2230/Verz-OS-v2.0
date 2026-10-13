"""A person hands an artifact to a colleague, and asks for an agent they cannot yet run.

Two leaves of the member application each built a decision and had nowhere to keep what it decided:
`brain.member_library.share` admits one artifact to one colleague who already reaches it (M40.3.3.3),
and `brain.member_activity.request_agent` addresses a request for an agent to the department that
answers for it (M40.2.2.5). Neither had a table.

**`agent.artifact_share` holds no permission.** An artifact, the person who shared it, the colleague
and an instant: a row that puts the artifact on the colleague's page and admits them to nothing,
because `brain.member_library.open_share` asks `may_download` of the colleague as they are at the
moment of the read and never consults the row for an answer. A share to oneself is refused by the
table. A person sharing the same artifact with the same colleague twice is one row.
**Read by the two people it names**, written by the sharer, and withdrawn by the sharer, which is the
only delete the application has.

**`agent.agent_request` is a record that somebody asked.** No decision, no approver and no answer
column: asking is not deciding, so a request cannot be approved by filling in a field, and what the
department does about it is a change to the agent's audience made where those are made. One row for
each person and agent, so asking again changes nothing. **Read by the application with
`USING (true)`** for `0101`'s reason: the routes narrow it, to the asker's own and to a department's
leads, and a row names an agent the asker could already see.

**The application may not update either.** Insert, and for a share delete; a request never leaves.

**The downgrade** drops both tables, which is the state before: nothing was kept. A share vanishes
and no artifact is affected, and a request vanishes and no access is.

Task ids: M40.3.3.3, M40.2.2.5

Revision ID: 0230
Revises: 0229
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0230"
# Linked behind 0229, the other migration of this package. The coordinator re-points it at
# whichever migration is the head when the train is assembled; nothing here depends on 0229.
down_revision = "0229"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: an artifact, an agent and a person are
#: values, so a row outlives an artifact that aged out and a person leaving.
TABLES: tuple[str, ...] = ("agent.artifact_share", "agent.agent_request")

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.member_share`.
PRINCIPAL_ID_CHARS = 128
ARTIFACT_ID_CHARS = 128
AGENT_ID_CHARS = 128
DEPARTMENT_CHARS = 60

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.artifact_share ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY artifact_share_seen_by_its_two_people ON agent.artifact_share
        FOR SELECT TO brain_app
        USING (shared_by = {PRINCIPAL} OR shared_with = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY artifact_share_made_by_the_sharer ON agent.artifact_share
        FOR INSERT TO brain_app
        WITH CHECK (shared_by = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY artifact_share_withdrawn_by_the_sharer ON agent.artifact_share
        FOR DELETE TO brain_app
        USING (shared_by = {PRINCIPAL})
    """,
    "ALTER TABLE agent.agent_request ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY agent_request_readable ON agent.agent_request
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY agent_request_made_by_the_asker ON agent.agent_request
        FOR INSERT TO brain_app
        WITH CHECK (requested_by = {PRINCIPAL})
    """,
)

#: A share may be withdrawn; neither table is ever updated, and a request never leaves.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, DELETE ON agent.artifact_share TO brain_app",
    "GRANT SELECT, INSERT ON agent.agent_request TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "artifact_share",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("artifact_id", sa.String(ARTIFACT_ID_CHARS), nullable=False),
        sa.Column("shared_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("shared_with", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "shared_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "artifact_id", "shared_by", "shared_with", name="uq_artifact_share_one_each"
        ),
        sa.CheckConstraint("shared_by <> shared_with", name="not_with_oneself"),
        sa.CheckConstraint("length(btrim(artifact_id)) > 0", name="artifact_present"),
        sa.CheckConstraint("length(btrim(shared_by)) > 0", name="sharer_present"),
        sa.CheckConstraint("length(btrim(shared_with)) > 0", name="colleague_present"),
        schema="agent",
    )
    op.create_index(
        "ix_agent_artifact_share_shared_with", "artifact_share", ["shared_with"], schema="agent"
    )
    op.create_table(
        "agent_request",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("requested_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("department", sa.String(DEPARTMENT_CHARS), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("agent_id", "requested_by", name="uq_agent_request_one_each"),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint("length(btrim(requested_by)) > 0", name="asker_present"),
        sa.CheckConstraint("length(btrim(department)) > 0", name="department_present"),
        schema="agent",
    )
    op.create_index(
        "ix_agent_agent_request_department", "agent_request", ["department"], schema="agent"
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The indexes, the policies and the grants go with the tables.
    op.drop_table("agent_request", schema="agent")
    op.drop_table("artifact_share", schema="agent")
