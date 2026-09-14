"""The plugin registry tables, with row-level security on both.

`brain.tables.plugin` holds the argument for the shape and `brain.plugins.lifecycle` the rules.
What is here is two tables, their policies, and one trigger.

**`ops.plugin_version` takes SELECT and INSERT and nothing else.** It is every manifest this
install has run, and a manifest that could be edited under its version string would let a
rollback return to a document nobody ran.

**`ops.plugin_install` takes SELECT, INSERT and UPDATE, and no DELETE.** A removed plugin is a
row with `removed_at` set, admitted only on a disabled row by a check constraint. The first
version of this migration granted DELETE instead, and `tests/unit/test_directory_role_grant.py`
refused it, because the directory role grant is meant to stay the one DELETE in the system.

**Nothing arrives enabled, by two routes out of `ABSENT`.** A plugin never seen arrives by an
INSERT, and the insert policy admits only `installed`. A plugin removed and coming back arrives
by an UPDATE of its retired row, and `plugin_install_returns_switched_off` refuses that update
unless the row it writes is `installed`. The trigger reads `OLD`, which a policy cannot, and that
is the whole reason it is a trigger. `brain.plugins.lifecycle.TRANSITIONS` has no edge from
`ABSENT` to `ENABLED`, and these two are that absence held by the database.

**`USING (true)` on the reads is not an absence of a permission check.** Who may be told about a
plugin is `brain.plugins.lifecycle.state_of`'s decision, against the reader's live entitlements,
and it collapses a refusal into `ABSENT`. `0025` makes the same point about its own reads.

**The downgrade drops both tables and the function**, the install table first because it points
at the version table. On a live install it forgets every plugin, which is the state before this
migration.

Task ids: M29.2.2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

TABLES: tuple[str, ...] = ("ops.plugin_version", "ops.plugin_install")

APP_ROLE = "brain_app"

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.plugin_version TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON ops.plugin_install TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.plugin_version ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY plugin_version_readable ON ops.plugin_version
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY plugin_version_appendable ON ops.plugin_version
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.plugin_install ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY plugin_install_readable ON ops.plugin_install
        FOR SELECT TO brain_app
        USING (true)
    """,
    # Nothing arrives enabled: the only row an insert may write is one switched off.
    """
    CREATE POLICY plugin_install_arrives_switched_off ON ops.plugin_install
        FOR INSERT TO brain_app
        WITH CHECK (state = 'installed' AND removed_at IS NULL)
    """,
    """
    CREATE POLICY plugin_install_movable ON ops.plugin_install
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

# `RAISE EXCEPTION USING MESSAGE` rather than a format string, for the reason `0002` gives.
RETURNS_SWITCHED_OFF_FUNCTION = """
CREATE FUNCTION ops.plugin_install_returns_switched_off() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.removed_at IS NOT NULL AND NEW.removed_at IS NULL AND NEW.state <> 'installed' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'plugin ' || OLD.plugin_id || ' was removed and comes back as '
                      || NEW.state || '; a plugin returns installed and is enabled separately',
            ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$
"""

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER plugin_install_returns_switched_off
        BEFORE UPDATE ON ops.plugin_install
        FOR EACH ROW EXECUTE FUNCTION ops.plugin_install_returns_switched_off()
    """,
)

#: Named so `downgrade` drops exactly what `upgrade` created.
FUNCTIONS: tuple[str, ...] = ("ops.plugin_install_returns_switched_off()",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "plugin_version",
        sa.Column("plugin_id", sa.String(80), primary_key=True),
        sa.Column("version", sa.String(64), primary_key=True),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column(
            "first_run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("jsonb_typeof(manifest) = 'object'", name="manifest_object"),
        sa.CheckConstraint(
            "manifest ->> 'plugin_id' = plugin_id AND manifest ->> 'version' = version",
            name="manifest_is_this_version",
        ),
        schema="ops",
    )
    op.create_table(
        "plugin_install",
        sa.Column("plugin_id", sa.String(80), primary_key=True),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("point", sa.String(80), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("plugin_id ~ '^[a-z][a-z0-9_-]{0,79}$'", name="plugin_id_shape"),
        sa.CheckConstraint(
            "point IN ('channel_adapter', 'connector', 'field_classifier', 'model_provider', "
            "'notification_sink', 'skill', 'template')",
            name="point_takes_a_plugin",
        ),
        sa.CheckConstraint("state IN ('disabled', 'enabled', 'installed')", name="state"),
        sa.CheckConstraint(
            "cardinality(history) >= 1 AND version = ANY (history)",
            name="running_version_is_in_history",
        ),
        sa.CheckConstraint("jsonb_typeof(manifest) = 'object'", name="manifest_object"),
        sa.CheckConstraint(
            "manifest ->> 'plugin_id' = plugin_id AND manifest ->> 'version' = version "
            "AND manifest ->> 'point' = point",
            name="manifest_is_this_install",
        ),
        sa.CheckConstraint(
            "removed_at IS NULL OR state = 'disabled'", name="removed_only_when_disabled"
        ),
        sa.ForeignKeyConstraint(
            ["plugin_id", "version"],
            ["ops.plugin_version.plugin_id", "ops.plugin_version.version"],
        ),
        schema="ops",
    )
    op.execute(RETURNS_SWITCHED_OFF_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The trigger goes with the table; the function does not, so it follows.
    op.drop_table("plugin_install", schema="ops")
    op.drop_table("plugin_version", schema="ops")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION {function}")
