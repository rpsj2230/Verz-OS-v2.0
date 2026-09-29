"""An artifact names the client it was produced for and the grants it drew on, and is superseded
or archived as a row of its own.

`0058` built `agent.artifact` with no state and said so: `supersede` and `archive` in
`brain.console.agent_output` returned new records and nothing stored one, so every row read as
current for ever. And an artifact had no client, so "the latest proposal for this client" had
nothing to be asked of, and no record of what its content needed, so a re-download could only ask
whether the requester was the person it was produced for, which stays true after their reach has
narrowed. This migration adds the three.

**`agent.artifact_change`**: one row when an artifact is superseded, naming its successor, and one
when it is archived. Keyed by the artifact and the state, so it is superseded at most once and
archived at most once. **SELECT and INSERT only, written in the session's own name**, `0149`'s
shape: what an artifact is now is its row with its changes folded over it, and the row that was
sent to somebody is never rewritten to say what happened to it afterwards.

**`agent.artifact.client_id`**, a canonical entity's id held by value and nullable, because most
artifacts are about no client. By value rather than a key into `er.canonical`, for `0058`'s reason
that the record of what was produced points at nothing; a merge forwards an entity rather than
removing it, and the store refuses an id that names no entity when it writes one.

**`agent.artifact.drew_on`**, the grants the producing run's reach held for what reached the
file, as a JSON list in `brain.core.entitlement.Grant`'s own shape, empty for the rows `0058`
wrote. A re-download asks whether the requester still holds each of them at least as widely.

**No ledger entry**, for `0058`'s reason: superseding or archiving an artifact changes nobody's
access, and the change row is itself the record of who did it and when.

**The downgrade drops the change table and the two columns.** The bytes stay in the bucket.

Written as 0153 over 0150 in #235, and replayed as 0194 over 0184, the head of origin/main on the
day; whoever lands it later re-points `down_revision` and nothing else.

Task ids: M39.5.1.5, M39.5.2.4, M39.8.5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0194"
down_revision = "0184"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.artifact_change",)

#: Widths and patterns copied for the reason `0009` gives about reading live code from a
#: migration, and held equal to `brain.tables.artifact` by `tests/unit/test_artifact_store.py`.
ARTIFACT_ID_CHARS = 64
ENTITY_ID_CHARS = 128
PRINCIPAL_ID_CHARS = 128
STATE_CHARS = 16
TRACE_ID_CHARS = 128
ENT_HASH_PATTERN = r"^[0-9a-f]{32}$"
#: `brain.console.agent_output.ArtifactState` less `current`, copied likewise.
STATES = "state IN ('archived', 'superseded')"
SUCCESSOR_IFF_SUPERSEDED = "(state = 'superseded') = (superseded_by IS NOT NULL)"

#: The two checks the columns carry, named as the model names them.
DREW_ON_CHECK = ("drew_on_is_a_list_of_grants", "jsonb_typeof(drew_on) = 'array'")
CLIENT_CHECK = ("client_id_present", "client_id IS NULL OR length(btrim(client_id)) > 0")

#: `0058`'s CREATE TABLE as it would read today, for the comparison with the model. Held to the
#: ALTERs the upgrade emits by `tests/unit/test_artifact_store.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "knowledge_items TEXT[] DEFAULT '{}' NOT NULL, CONSTRAINT pk_artifact PRIMARY KEY": (
        "knowledge_items TEXT[] DEFAULT '{}' NOT NULL, "
        f"client_id VARCHAR({ENTITY_ID_CHARS}), drew_on JSONB DEFAULT '[]'::jsonb NOT NULL, "
        "CONSTRAINT pk_artifact PRIMARY KEY"
    ),
    "CONSTRAINT ck_artifact_holds_bytes CHECK (bytes_stored > 0) )": (
        "CONSTRAINT ck_artifact_holds_bytes CHECK (bytes_stored > 0), "
        f"CONSTRAINT ck_artifact_{DREW_ON_CHECK[0]} CHECK ({DREW_ON_CHECK[1]}), "
        f"CONSTRAINT ck_artifact_{CLIENT_CHECK[0]} CHECK ({CLIENT_CHECK[1]}) )"
    ),
}

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.artifact_change ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY artifact_change_readable ON agent.artifact_change
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY artifact_change_made_in_the_sessions_name ON agent.artifact_change
        FOR INSERT TO brain_app
        WITH CHECK (changed_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a change is a new row.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.artifact_change TO brain_app",)


def upgrade() -> None:
    op.add_column(
        "artifact",
        sa.Column("client_id", sa.String(ENTITY_ID_CHARS), nullable=True),
        schema="agent",
    )
    op.add_column(
        "artifact",
        sa.Column(
            "drew_on",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        schema="agent",
    )
    for name, check in (DREW_ON_CHECK, CLIENT_CHECK):
        op.create_check_constraint(name, "artifact", check, schema="agent")
    op.create_index(
        "ix_artifact_agent_produced",
        "artifact",
        ["agent_id", "produced_at"],
        schema="agent",
    )
    op.create_index(
        "ix_artifact_client_kind_produced",
        "artifact",
        ["client_id", "kind", "produced_at"],
        schema="agent",
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )

    op.create_table(
        "artifact_change",
        sa.Column("artifact_id", sa.String(ARTIFACT_ID_CHARS), nullable=False),
        sa.Column("state", sa.String(STATE_CHARS), nullable=False),
        sa.Column("superseded_by", sa.String(ARTIFACT_ID_CHARS), nullable=True),
        sa.Column("changed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("entitlement_hash", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["agent.artifact.artifact_id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["agent.artifact.artifact_id"]),
        sa.CheckConstraint(STATES, name="state"),
        sa.CheckConstraint(SUCCESSOR_IFF_SUPERSEDED, name="successor_iff_superseded"),
        sa.CheckConstraint(
            "superseded_by IS NULL OR superseded_by <> artifact_id", name="not_its_own_successor"
        ),
        sa.CheckConstraint("length(btrim(changed_by)) > 0", name="attributed"),
        sa.CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        sa.CheckConstraint("length(btrim(trace_id)) > 0", name="traced"),
        sa.PrimaryKeyConstraint("artifact_id", "state"),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grant go with the table.
    op.drop_table("artifact_change", schema="agent")
    op.drop_index("ix_artifact_client_kind_produced", table_name="artifact", schema="agent")
    op.drop_index("ix_artifact_agent_produced", table_name="artifact", schema="agent")
    for name, _ in (CLIENT_CHECK, DREW_ON_CHECK):
        op.drop_constraint(name, "artifact", schema="agent", type_="check")
    op.drop_column("artifact", "drew_on", schema="agent")
    op.drop_column("artifact", "client_id", schema="agent")
