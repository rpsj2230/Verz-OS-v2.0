"""Budget ceilings at every level, as versions nobody may edit, with row-level security on.

`brain.ops.budgets` holds the rules and `brain.tables.budget` the argument for the shape. What is
here is the table, one policy pair, and two triggers: one refusing every amendment and one
refusing a version that does not follow the last.

**Append-only three times over, and only the third holds against an administrator.** The
application role is granted SELECT and INSERT. Row-level security admits a read and an insert and
nothing else, so an UPDATE or a DELETE by that role is refused for want of a policy. And a
statement trigger raises for every role, the owner and a superuser included. `0002` makes the
same arrangement for `obs.audit_entry` and says why the trigger is the layer that matters: it is
the one that survives somebody connecting as `postgres` with a good reason.

**The ordering trigger is BEFORE INSERT and per row**, because it has to read the row being
inserted and refuse it before it exists. It refuses a first version other than one, a later
version other than the last plus one, and an effective-from that is not strictly after the last.
Two concurrent writers can both pass it, because each reads the table before the other commits,
and the unique index on the natural key is what refuses the second of them.

**`USING (true)` on the read is not an absence of a permission check.** Who may see a budget is
decided by whoever reads it against their live entitlements; a ceiling row carries a level, a
subject and a figure and no field a predicate here could read. `0025` makes the same point.

**The downgrade is real, and on a live install it discards the history of every ceiling.** That
is the state before this migration and nothing else refers to the table, so it succeeds; it is
said here because it is exactly what nobody downgrading a release in a hurry would want without
knowing.

Task ids: M21.1.5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

TABLES: tuple[str, ...] = ("ops.budget_version",)

APP_ROLE = "brain_app"

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.budget_version TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.budget_version ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY budget_version_readable ON ops.budget_version
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY budget_version_appendable ON ops.budget_version
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

# `RAISE EXCEPTION USING MESSAGE` rather than a format string, for the reason `0002` gives: the
# message is built by concatenation, so there is no placeholder for a value to be mistaken for.
APPEND_ONLY_FUNCTION = """
CREATE FUNCTION ops.budget_version_is_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'ops.budget_version is append-only; ' || tg_op || ' is refused',
        ERRCODE = 'restrict_violation',
        HINT = 'a ceiling is changed by appending its next version, never by editing one';
END;
$$
"""

FOLLOWS_FUNCTION = """
CREATE FUNCTION ops.budget_version_follows_the_last() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_version integer;
    v_from timestamptz;
BEGIN
    SELECT b.version, b.effective_from INTO v_version, v_from
      FROM ops.budget_version b
     WHERE b.level = NEW.level AND b.subject = NEW.subject AND b.period = NEW.period
     ORDER BY b.version DESC
     LIMIT 1;

    IF v_version IS NULL AND NEW.version <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the first version of a ceiling is 1, not ' || NEW.version,
            ERRCODE = 'check_violation';
    END IF;
    IF v_version IS NOT NULL AND NEW.version <> v_version + 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'version ' || NEW.version || ' does not follow version ' || v_version,
            ERRCODE = 'check_violation';
    END IF;
    IF v_version IS NOT NULL AND NEW.effective_from <= v_from THEN
        RAISE EXCEPTION USING
            MESSAGE = 'version ' || NEW.version
                      || ' takes effect no later than the version before it',
            ERRCODE = 'check_violation',
            HINT = 'two versions effective at one instant cannot be ordered';
    END IF;
    RETURN NEW;
END;
$$
"""

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER budget_version_follows
        BEFORE INSERT ON ops.budget_version
        FOR EACH ROW EXECUTE FUNCTION ops.budget_version_follows_the_last()
    """,
    """
    CREATE TRIGGER budget_version_refuses_amendment
        BEFORE UPDATE ON ops.budget_version
        FOR EACH STATEMENT EXECUTE FUNCTION ops.budget_version_is_append_only()
    """,
    """
    CREATE TRIGGER budget_version_refuses_removal
        BEFORE DELETE ON ops.budget_version
        FOR EACH STATEMENT EXECUTE FUNCTION ops.budget_version_is_append_only()
    """,
    """
    CREATE TRIGGER budget_version_refuses_truncation
        BEFORE TRUNCATE ON ops.budget_version
        FOR EACH STATEMENT EXECUTE FUNCTION ops.budget_version_is_append_only()
    """,
)

#: Named so `downgrade` drops exactly what `upgrade` created.
FUNCTIONS: tuple[str, ...] = (
    "ops.budget_version_follows_the_last()",
    "ops.budget_version_is_append_only()",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "budget_version",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("ceiling_minor", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(128), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "alert_fractions",
            postgresql.ARRAY(sa.Double()),
            nullable=False,
            server_default=sa.text("'{}'::double precision[]"),
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("level IN ('agent', 'company', 'department', 'user')", name="level"),
        sa.CheckConstraint("period IN ('day', 'month', 'run')", name="period"),
        sa.CheckConstraint("length(btrim(subject)) >= 1", name="subject_present"),
        sa.CheckConstraint("ceiling_minor >= 1", name="ceiling_is_something"),
        sa.CheckConstraint("version >= 1", name="versions_start_at_one"),
        sa.CheckConstraint("length(btrim(author)) >= 1", name="author_present"),
        sa.CheckConstraint("length(reason) <= 2000", name="reason_is_a_sentence"),
        sa.CheckConstraint(
            "0 < ALL (alert_fractions) AND 1 > ALL (alert_fractions)",
            name="alerts_below_the_ceiling",
        ),
        sa.UniqueConstraint("level", "subject", "period", "version"),
        schema="ops",
    )
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(FOLLOWS_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The triggers and policies go with the table; the functions do not, so they follow it.
    op.drop_table("budget_version", schema="ops")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION {function}")
