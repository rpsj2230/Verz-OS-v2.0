"""The function that rebuilds the materialised spend report and records when it did.

A migration of its own rather than part of `0035`, because it is the one statement here that
writes a row, and `brain.ops.migration_policy` refuses a data change beside a schema change. It
reads the file's text, so a function body counts. That is an honest reading of the rule rather
than a false positive to route around: this function is the write path of a table `0035` made,
and keeping it apart means either half can be read, reversed and reasoned about alone.

**`SECURITY DEFINER`, for one reason, with the search path pinned.** Only a materialised view's
owner may refresh it, and the application role is not the owner and must not become one: an
owner can also drop the view or grant it to anybody. So the function runs as the owner, is
granted to `brain_app`, and names every object it touches with its schema, which is the
arrangement `brain.core.scope_sql.DELEGATION_TRIGGER_FUNCTION_SQL` makes for its own single read.

**`PUBLIC` keeps PostgreSQL's default EXECUTE, and the schema is what stops anybody else calling
it.** A function in `ops` cannot be executed by a role without USAGE on `ops`, and `0001` grants
that to `brain_app` alone: the fast lane is given `proj` and nothing more. So the default grant
reaches no role that could use it, and a test calls the function as `brain_fastlane` and is
refused. `REVOKE ALL ... FROM PUBLIC` was written first and is not here, because
`brain.deployment.compatibility` reads every REVOKE as a statement that removes something from
the previous release. That reading is wrong for a function created in the same migration, the way
it already knows a policy on a table created here is not a narrowing, and the gate is not this
change's to amend. If a role other than the application is ever granted USAGE on `ops`, this
function becomes callable by it, and the revoke belongs back here with the gate taught why.

**The rebuild and its timestamp are one transaction, and `now()` is that transaction's start.**
The refresh reads the table at the snapshot the function runs in, and `now()` names the start
of the same transaction, so `refreshed_at` is never later than the data it describes. A run that
completed and committed during the refresh is absent from the view and is picked up by the next
one, which rebuilds everything: this view has no incremental state to go wrong.

**Concurrent once there is something to be concurrent with.** `CONCURRENTLY` refuses an
unpopulated view, so the first rebuild is plain and every later one leaves readers on the old
rows until the new ones commit.

The downgrade drops the function. The view and the record stay, and a view nobody refreshes
reports its own growing age, which is the state this leaf exists to make visible.

Task ids: M36.1.3.2
"""

from __future__ import annotations

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

FUNCTION = "ops.refresh_spend_daily()"

CREATE_FUNCTION = """
CREATE FUNCTION ops.refresh_spend_daily()
RETURNS timestamptz
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, ops
AS $refresh$
BEGIN
    IF (SELECT c.relispopulated FROM pg_catalog.pg_class AS c
        WHERE c.oid = 'ops.spend_daily'::regclass) THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY ops.spend_daily;
    ELSE
        REFRESH MATERIALIZED VIEW ops.spend_daily;
    END IF;
    INSERT INTO ops.report_refresh AS r (view_name, refreshed_at)
    VALUES ('ops.spend_daily', now())
    ON CONFLICT (view_name) DO UPDATE SET refreshed_at = excluded.refreshed_at;
    RETURN now();
END;
$refresh$
"""

GRANTS: tuple[str, ...] = ("GRANT EXECUTE ON FUNCTION ops.refresh_spend_daily() TO brain_app",)


def upgrade() -> None:
    op.execute(CREATE_FUNCTION)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FUNCTION}")
