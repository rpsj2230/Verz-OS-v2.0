"""The fast lane reads an uploaded table's rows as its own role, and that role reads nothing else.

M6.1.3 is that the fast lane reaches the tables it answers from and nothing else, enforced by the
database. `0001` created `brain_fastlane` for that and `0008` handed it `SELECT` on
`proj.record`, and then nothing read as it: every fast answer was read as `brain_app`, and since
the price lists people upload became the tables most fast answers come from, those rows sit in
`know.classified_row`, which the role could not reach anyway. So the lane now takes the role for
the transaction it reads in (`brain.knowledge.row_store.FastLaneRowSource`), and this migration
gives the role the one table in `know` it needs.

**One table, one verb, and the schema's usage only so the name resolves.** `USAGE ON SCHEMA know`
lets the role name an object in `know` and grants no table: `know.item`, `know.chunk` and
`know.classified_table` stay refused to it, which `tests/unit/test_fast_lane_role.py` asks the
database. `SELECT` on `know.classified_row` and nothing else: no INSERT, no UPDATE, no DELETE, no
`ALL TABLES IN SCHEMA`. `brain.ops.migration_policy` holds every later migration to that list.

**The policy mirrors the application's, because the narrowing is not in it.** `0116` reads the
rows `USING (true)`: which rows and which columns a person may see is the compiled projection and
predicate in the statement, under the asker's grants, and the table has no per-person column a
policy could read. A policy naming the role is still required, because row-level security returns
an empty table to a role no policy names, and a fast lane answering from nothing looks exactly
like a price list with nothing in it.

**Which table and which upload are live is still read as the application.** The lane is built
per question from `know.classified_table` (`brain.ops.classification_store.classified_lane_of`),
and that read is configuration, like the rule rows `brain.gate.rule_store` loads: what the lane
may ask, not what it answers from. Only the rows an answer is taken from are read as the role.

Revises `0163`, the memory confirmation migration of the branch this is stacked on (#255), in the
order the migration queue lands.

Task ids: M6.1.3

Revision ID: 0162
Revises: 0163
"""

from __future__ import annotations

from alembic import op

revision = "0162"
down_revision = "0163"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. None here.
TABLES: tuple[str, ...] = ()

FAST_ROLE = "brain_fastlane"

#: What the role is given, and all of it.
GRANTS: tuple[str, ...] = (
    "GRANT USAGE ON SCHEMA know TO brain_fastlane",
    "GRANT SELECT ON know.classified_row TO brain_fastlane",
)

#: Without this the grant returns an empty table under row-level security.
POLICIES: tuple[str, ...] = (
    """
    CREATE POLICY classified_row_fastlane_read ON know.classified_row
        FOR SELECT TO brain_fastlane
        USING (true)
    """,
)

#: The upgrade undone, in the reverse order.
DOWNGRADE: tuple[str, ...] = (
    "DROP POLICY classified_row_fastlane_read ON know.classified_row",
    "REVOKE SELECT ON know.classified_row FROM brain_fastlane",
    "REVOKE USAGE ON SCHEMA know FROM brain_fastlane",
)


def upgrade() -> None:
    assert all(FAST_ROLE in statement for statement in (*GRANTS, *POLICIES))
    assert not any(
        verb in statement
        for statement in GRANTS
        for verb in ("INSERT", "UPDATE", "DELETE", "ALL", "TRUNCATE")
    )
    for statement in (*GRANTS, *POLICIES):
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
