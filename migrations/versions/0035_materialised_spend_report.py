"""The spend report is materialised per day, keyed by department, with its age on record.

`brain.console.spend_view.spend_report` groups every accounting row a reader may see, one run
per row, and it is the heaviest report screen here: it is read over the whole retained history
and asked for in five dimensions. This is the view that stands in for that grouping, and the
table that says how old the view is. `0036` adds the function that rebuilds the one and writes
the other.

**A materialised view carries no row-level security, so its safety has to come from its shape.**
PostgreSQL applies no policy when a materialised view is read, and cannot be asked to: `ALTER
TABLE ... ENABLE ROW LEVEL SECURITY` is refused on one. `brain.ops.sweeps.sweep_rls` only
inspects `relkind = 'r'`, so nothing would report a view that was wider than its table either.
The argument for this one is two facts, and both are checked rather than asserted:

*The view is no wider than its table for the role that reads it.* `ops.spend_actual`'s read
policy for `brain_app` is `USING (true)`, for the reason `0034` gives, so the application
already reads every row this view summarises. The same role is granted SELECT here and nobody
else is. A test reads the table's policy back from the server, so a narrower policy arriving
later makes this argument false loudly.

*The reader's filter commutes with the grouping, because the filter's only input is a group
key.* `may_read_spend` admits a row by its department and by nothing else, and `department` is
in every group here. Summing within a department and then dropping the departments a reader may
not see gives exactly the figures that dropping the rows first and then summing gives, for every
dimension. A view keyed without the department, per model or per agent across the company,
would hand every reader the company's figure for that key, which is the subtraction
`A_TOTAL_OVER_ROWS_THE_READER_MAY_NOT_SEE_IS_A_SUBTRACTION` forbids arriving through a table.

**No row count.** The view sums cost and counts nothing, because a count of runs is a count of
activity, which `spend_view` rejected as a column beside each line for that reason.

**Machine traffic is grouped by its two inputs rather than decided here.** `principal_kind` and
`traffic` are group keys and `brain.ops.limits.is_automated` is asked of each summed row in
Python, so the lookup has one implementation. `DIMENSION_KEYS` is the one thing copied from
Python, which is `Actual.key_for`: a test pins its names to `brain.ops.spend.Dimension` and its
empty-agent key to `NO_AGENT`, and a second test compares the view against `spend_report` over
the same rows on a real server.

**Built `WITH NO DATA`, and not refreshed here.** A view nobody has refreshed has no row in
`ops.report_refresh`, and `brain.ops.spend_store.read_spend_daily` reads that absence as a report
that has never been built rather than as a company that spent nothing. A migration that
populated it would also be a data change inside a schema change, which
`brain.ops.migration_policy` refuses.

**The unique index is what lets a refresh leave readers alone.** `REFRESH MATERIALIZED VIEW
CONCURRENTLY` needs one, and without it every rebuild takes an exclusive lock on the screen it
exists to make fast.

The downgrade drops both and discards nothing that cannot be rebuilt: the view is derived from
`ops.spend_actual` and the refresh record describes only the view.

Task ids: M36.1.3.1, M36.1.3.2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. The view is not a table and is not in the metadata.
TABLES: tuple[str, ...] = ("ops.report_refresh",)

VIEW = "ops.spend_daily"

#: `brain.ops.spend.Actual.key_for`, as SQL, one entry per `brain.ops.spend.Dimension`.
#: Copied rather than rendered from the module, for the reason `0009` gives about its own
#: definitions, and pinned to the module by `tests/unit/test_spend_report_view.py`.
DIMENSION_KEYS: tuple[tuple[str, str], ...] = (
    ("principal", "a.principal_id"),
    ("department", "a.department"),
    ("agent", "coalesce(a.agent_id, '(no agent)')"),
    ("model", "a.model"),
    ("lane", "a.lane"),
)

CREATE_VIEW = """
CREATE MATERIALIZED VIEW ops.spend_daily AS
SELECT
    (a.at AT TIME ZONE 'UTC')::date AS day,
    a.department AS department,
    a.principal_kind AS principal_kind,
    a.traffic AS traffic,
    d.dimension AS dimension,
    d.key AS key,
    sum(a.cost_minor)::bigint AS cost_minor
FROM ops.spend_actual AS a
CROSS JOIN LATERAL (VALUES
    ('principal', a.principal_id),
    ('department', a.department),
    ('agent', coalesce(a.agent_id, '(no agent)')),
    ('model', a.model),
    ('lane', a.lane)
) AS d (dimension, key)
GROUP BY 1, 2, 3, 4, 5, 6
WITH NO DATA
"""

#: Every group key, so a concurrent refresh can match old rows to new ones.
UNIQUE_INDEX = """
CREATE UNIQUE INDEX uq_spend_daily_group
    ON ops.spend_daily (day, department, principal_kind, traffic, dimension, key)
"""

GRANTS: tuple[str, ...] = (
    "GRANT SELECT ON ops.report_refresh TO brain_app",
    "GRANT SELECT ON ops.spend_daily TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.report_refresh ENABLE ROW LEVEL SECURITY",
    # Read only. The one writer is `0036`'s function, which runs as the owner.
    """
    CREATE POLICY report_refresh_readable ON ops.report_refresh
        FOR SELECT TO brain_app
        USING (true)
    """,
)


def upgrade() -> None:
    assert all("INSERT" not in one and "UPDATE" not in one for one in GRANTS)

    op.create_table(
        "report_refresh",
        sa.Column("view_name", sa.String(64), primary_key=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("view_name IN ('ops.spend_daily')", name="view_name"),
        schema="ops",
    )
    op.execute(CREATE_VIEW)
    op.execute(UNIQUE_INDEX)
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The index goes with the view, and the policy with the table.
    op.execute("DROP MATERIALIZED VIEW ops.spend_daily")
    op.drop_table("report_refresh", schema="ops")
