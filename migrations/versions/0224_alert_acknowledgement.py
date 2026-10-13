"""Who acknowledged an alert, and when, so that its repeat notice can stop (M27.15.45).

`ops.alert_acknowledgement`, one row per alert instance somebody has acknowledged. An alert has no
row of its own on this install: what is degraded is read off the worker's last attempt at each
source, and an incident is identified by what it is about and the instant it began. So the key is
that pair (`kind`, `subject`, `since`), and a source that recovers and fails again begins a new
incident that has not been acknowledged. `brain.tables.alert_acknowledgement` holds the argument
for each column.

**SELECT and INSERT only, written in the session's own name**, `0211`'s shape. The first person to
acknowledge an incident is the one the row names; a second press finds the row there and writes
nothing, so who and when can never be rewritten. Nothing updates a row and nothing deletes one.

**No ledger entry of its own.** Acknowledging changes nobody's access and no configuration. The row
is its own record of who and when, which is all the question asks.

The downgrade drops the table. An incident whose acknowledgement was lost is shown as not
acknowledged, and the repeat notice resumes, which is the safe direction.

Task ids: M27.15.45

Revision ID: 0224
Revises: 0223
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0224"
# The plan's number, after 0223. Re-pointed at whichever migration is the head when it lands.
down_revision = "0223"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: the subject is a source's name and the
#: person is a value, so an acknowledgement outlives both a connection and a person leaving.
TABLES: tuple[str, ...] = ("ops.alert_acknowledgement",)

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.alert_acknowledgement`.
SUBJECT_CHARS = 128
PRINCIPAL_ID_CHARS = 128
KIND_CHARS = 16

#: `brain.tables.alert_acknowledgement.AlertKind`, on the day this ran.
KINDS: tuple[str, ...] = ("incident",)

PRINCIPAL = "current_setting('app.principal_id', true)"


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.alert_acknowledgement ENABLE ROW LEVEL SECURITY",
    # Read by the screen for whoever may be told of the incident; who may be told is decided where
    # it is shown, as `ops.budget_stop`'s is.
    """
    CREATE POLICY alert_acknowledgement_readable ON ops.alert_acknowledgement
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY alert_acknowledgement_written_in_the_sessions_name ON ops.alert_acknowledgement
        FOR INSERT TO brain_app
        WITH CHECK (acknowledged_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.alert_acknowledgement TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "alert_acknowledgement",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(KIND_CHARS), nullable=False),
        sa.Column("subject", sa.String(SUBJECT_CHARS), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint(_one_of("kind", KINDS), name="kind"),
        sa.CheckConstraint("length(btrim(subject)) > 0", name="subject_present"),
        sa.CheckConstraint("length(btrim(acknowledged_by)) > 0", name="a_person_acknowledged"),
        sa.UniqueConstraint("kind", "subject", "since", name="uq_alert_one_acknowledgement"),
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grant go with the table.
    op.drop_table("alert_acknowledgement", schema="ops")
