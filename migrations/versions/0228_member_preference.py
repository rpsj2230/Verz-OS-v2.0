"""A person's own settings: whether they learn from them, where they are reached, and when not.

Five leaves of the member application each asked for one setting a person keeps about themselves and
nothing stored any of them: switching personal learning off (M40.4.1.4), which channel is primary
(M40.5.2.1), what each channel may tell them (M40.5.2.2), whether an envelope waits for them on the
console or on a Lark card (M40.5.2.3) and the hours digests and automations are held (M40.5.2.4).
`brain.member.connections` and `brain.member_activity` built the shapes and nothing could hold them.

**One table, a closed list of keys, one row for each.** `auth.member_preference` is a person, a
key and a document, so a sixth setting is a value in this list and a migration that widens the list,
not a column nobody can see the reason for. The key list is a check constraint the database holds;
what each value must look like is decided where it is written (`brain.member.preferences`), which is
the module that already refuses a primary channel nobody is bound on.

**Read by the application with `USING (true)`**, because the senders (`brain.tell_later`,
`brain.approval_cards`) ask about the person they are writing to and are not that person. **Written
only as the person**: an insert, an update and a delete each hold the row to the person the session
names, so one person cannot set another's preference, and no route reads another person's.

**Erased with the person**, which is why the application may delete: a preference is theirs and has
nothing a legal hold needs to keep.

**The downgrade** drops the table; its policies and grants go with it. Every person is then reached
as they were before: learning on, no primary, no preferences, the console and Lark card both, and no
quiet hours.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4

Revision ID: 0228
Revises: 0225
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0228"
down_revision = "0225"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: the person is a value, so a row can
#: outlive the directory row it names, and an erasure removes it by the column.
TABLES: tuple[str, ...] = ("auth.member_preference",)

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.member_preference`.
PRINCIPAL_ID_CHARS = 128
KEY_CHARS = 32

#: The settings a person may keep, on the day this ran. Held equal to
#: `brain.member.preferences.PreferenceKey` by a test.
KEYS: tuple[str, ...] = (
    "approval_route",
    "channel_notices",
    "learning_opt_out",
    "primary_channel",
    "quiet_hours",
)

PRINCIPAL = "current_setting('app.principal_id', true)"

KNOWN_KEY = "key IN (" + ", ".join(f"'{one}'" for one in KEYS) + ")"

RLS: tuple[str, ...] = (
    "ALTER TABLE auth.member_preference ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY member_preference_readable ON auth.member_preference
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY member_preference_set_by_the_person ON auth.member_preference
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY member_preference_changed_by_the_person ON auth.member_preference
        FOR UPDATE TO brain_app
        USING (principal_id = {PRINCIPAL})
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY member_preference_cleared_by_the_person ON auth.member_preference
        FOR DELETE TO brain_app
        USING (principal_id = {PRINCIPAL})
    """,
)

#: The value and its instant may change; the person and the key never do.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, DELETE ON auth.member_preference TO brain_app",
    "GRANT UPDATE (value, updated_at) ON auth.member_preference TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    op.create_table(
        "member_preference",
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("key", sa.String(KEY_CHARS), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("principal_id", "key"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        sa.CheckConstraint(KNOWN_KEY, name="key_known"),
        schema="auth",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the table.
    op.drop_table("member_preference", schema="auth")
