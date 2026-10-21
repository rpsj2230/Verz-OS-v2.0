"""What a coordinating agent may call, whether it may fan out, and how its runs went.

Three tables for the first thing in the product that starts one agent from another.

**`agent.agent_callee`, M18.5.1.** An agent an administrator allowed another agent to hand a subtask
to. Directional, a row per link, and the row stays when the link is withdrawn (`removed_by`,
`removed_at`, once), `agent.audience_extra`'s shape. It is configuration and not reach: nothing that
decides what a run may touch reads it, so linking two agents grants nobody anything.

**`agent.agent_fanout`, M18.6.2.** An agent an administrator let run its specialists at the same
time. A live row is the grant; an agent with none runs its specialists one after another. It is a
table and not a column on `agent.agent`, which templates, upgrades and the builder rewrite.

**`ops.coordinated_run`, M18.6.2.** How a coordinating agent's run went: parallel or in turn, why
not parallel from a closed list, and one object per child with its status, depth, reach hash and
cost. No request, no objective, no result value. Written once in the session's own name and never
edited, so the reason a run was not parallel is still there when somebody asks.

**Nothing here narrows what the previous release writes.** All three tables are new, and the
switch that gates running a plan ships off.

**No ledger entry of their own.** `agent.audience_extra` has none either: the rows are themselves
the dated record of who allowed what, and a trigger on each is a ledger action and subject kind this
leaf does not need.

The downgrade drops the tables. The links, the fan-out grants and the kept runs are lost, which is
the state before this.

Task ids: M18.5.1, M18.6.2

Revision ID: 0272
Revises: 0261
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0272"
down_revision = "0261"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: an agent and a person are values, so a
#: link, a grant and a kept run outlive both.
TABLES: tuple[str, ...] = ("agent.agent_callee", "agent.agent_fanout", "ops.coordinated_run")

APP_ROLE = "brain_app"
PRINCIPAL = "current_setting('app.principal_id', true)"

#: Held equal to `brain.tables.agent_coordination` and `brain.tables.coordinated_run`.
AGENT_ID_CHARS = 60
PRINCIPAL_ID_CHARS = 128
RUN_ID_CHARS = 128
WHY_CHARS = 32

#: `brain.orchestration.coordinator.Mode` and `Why`, on the day this ran.
MODES: tuple[str, ...] = ("parallel", "sequential")
WHYS: tuple[str, ...] = ("fan_out_not_enabled", "gate_declined", "no_room", "wave_over_the_cap")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


def _array_within(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} <@ ARRAY[{listed}]::character varying[]"


RLS: tuple[str, ...] = (
    "ALTER TABLE agent.agent_callee ENABLE ROW LEVEL SECURITY",
    # Read by the screen for whoever answers for the agent and by the run that asks who it may call;
    # who is told is decided where it is shown.
    """
    CREATE POLICY agent_callee_readable ON agent.agent_callee
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY agent_callee_added_in_the_sessions_name ON agent.agent_callee
        FOR INSERT TO brain_app
        WITH CHECK (added_by = {PRINCIPAL} AND removed_at IS NULL)
    """,
    f"""
    CREATE POLICY agent_callee_withdrawn_in_the_sessions_name ON agent.agent_callee
        FOR UPDATE TO brain_app
        USING (removed_at IS NULL)
        WITH CHECK (removed_by = {PRINCIPAL})
    """,
    "ALTER TABLE agent.agent_fanout ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY agent_fanout_readable ON agent.agent_fanout
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY agent_fanout_enabled_in_the_sessions_name ON agent.agent_fanout
        FOR INSERT TO brain_app
        WITH CHECK (enabled_by = {PRINCIPAL} AND removed_at IS NULL)
    """,
    f"""
    CREATE POLICY agent_fanout_withdrawn_in_the_sessions_name ON agent.agent_fanout
        FOR UPDATE TO brain_app
        USING (removed_at IS NULL)
        WITH CHECK (removed_by = {PRINCIPAL})
    """,
    "ALTER TABLE ops.coordinated_run ENABLE ROW LEVEL SECURITY",
    # Read by the screen for whoever may weigh a plan; who may is decided where it is shown.
    """
    CREATE POLICY coordinated_run_readable ON ops.coordinated_run
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY coordinated_run_written_in_the_sessions_name ON ops.coordinated_run
        FOR INSERT TO brain_app
        WITH CHECK (asked_by = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.agent_callee TO brain_app",
    "GRANT UPDATE (removed_by, removed_at) ON agent.agent_callee TO brain_app",
    "GRANT SELECT, INSERT ON agent.agent_fanout TO brain_app",
    "GRANT UPDATE (removed_by, removed_at) ON agent.agent_fanout TO brain_app",
    # SELECT and INSERT, and never UPDATE or DELETE.
    "GRANT SELECT, INSERT ON ops.coordinated_run TO brain_app",
)


def _removal_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("removed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    op.create_table(
        "agent_callee",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("coordinator_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("callee_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("added_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        *_removal_columns(),
        sa.CheckConstraint("length(btrim(coordinator_id)) > 0", name="coordinator_present"),
        sa.CheckConstraint("length(btrim(callee_id)) > 0", name="callee_present"),
        sa.CheckConstraint("coordinator_id <> callee_id", name="an_agent_does_not_call_itself"),
        sa.CheckConstraint("length(btrim(added_by)) > 0", name="added_by_present"),
        sa.CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        schema="agent",
    )
    op.create_index(
        "uq_agent_callee_one_live_row_per_link",
        "agent_callee",
        ["coordinator_id", "callee_id"],
        unique=True,
        schema="agent",
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_table(
        "agent_fanout",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("enabled_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "enabled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        *_removal_columns(),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint("length(btrim(enabled_by)) > 0", name="enabled_by_present"),
        sa.CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        schema="agent",
    )
    op.create_index(
        "uq_agent_fanout_one_live_row_per_agent",
        "agent_fanout",
        ["agent_id"],
        unique=True,
        schema="agent",
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_table(
        "coordinated_run",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(RUN_ID_CHARS), nullable=False),
        sa.Column("coordinator_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("asked_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column(
            "why",
            sa.ARRAY(sa.String(WHY_CHARS)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("children", postgresql.JSONB(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint(_one_of("mode", MODES), name="mode"),
        sa.CheckConstraint(_array_within("why", WHYS), name="why_is_a_known_reason"),
        sa.CheckConstraint(
            "(mode = 'parallel') = (cardinality(why) = 0)",
            name="parallel_has_no_reason_not_to_be",
        ),
        sa.CheckConstraint("length(btrim(run_id)) > 0", name="run_present"),
        sa.CheckConstraint("length(btrim(coordinator_id)) > 0", name="coordinator_present"),
        sa.CheckConstraint("length(btrim(asked_by)) > 0", name="an_actor_asked"),
        sa.CheckConstraint("jsonb_typeof(children) = 'array'", name="children_are_a_list"),
        sa.CheckConstraint("total_minor >= 0", name="cost_not_negative"),
        schema="ops",
    )
    op.create_index("ix_coordinated_run_by_start", "coordinated_run", ["started_at"], schema="ops")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the tables.
    op.drop_table("coordinated_run", schema="ops")
    op.drop_table("agent_fanout", schema="agent")
    op.drop_table("agent_callee", schema="agent")
