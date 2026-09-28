"""A test of one connection is an attempt of its own: `ops.connector_sync.outcome` gains `probed`.

**Why the attempt table and not a probe table of its own.** The Connectors screen reads a source's
health from its newest attempt (`brain.ops.connector_sync_store.latest_attempts`), and needs-rupash
107 asks for a test's result to be recorded on that health. A second table would be a second
answer to "how is this source", and the list would go on showing the last scheduled read after a
test had found the key refused. So a test is a row here, marked by its outcome, and the screen's
one statement sees it.

**Why a fourth outcome rather than one of the three.** `synced` says the source was read to the
end, which one call is not; `failed` adds to the failures in a row and so moves the schedule's
backoff, which a person pressing a button must not do; `quota` is a wait the source asked for. A
test is none of them, and `brain.ops.connector_sync.A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT` says
what its row carries instead: the health it found, one of the module's constant sentences, and the
schedule's own figures copied from the attempt before it. `failures_follow_the_outcome` names
`synced` and `failed` only, so it constrains a test's row not at all, which is the property.

**Widened, and the compatibility gate can see that it was.** Both predicates are `outcome IN (...)`,
which `brain.deployment.compatibility` orders, and the new list holds the old one, so the release
still running during a deploy writes nothing the database refuses. `SUPERSEDES` names the old text
for `tests/unit/test_tables.py`, which holds `0068`'s table against the model as amended.

**The downgrade** puts the three-word list back `NOT VALID`, for `0026`'s reason: a test recorded
under this release stays, and every write after the downgrade is held to the older list.

Task ids: M27.15.8
"""

from __future__ import annotations

from alembic import op

revision = "0142"
# Carried into migration train 2 on 0141 (People). Nothing after 0093 touches
# `ops.connector_sync`.
down_revision = "0141"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

SCHEMA = "ops"
TABLE = "connector_sync"

#: The bare constraint name; alembic applies the naming convention, for `0026`'s reason.
CONSTRAINT = "outcome"

#: `0068`'s list, and the list this release writes. Copied for `0009`'s reason about reading live
#: code from a migration, and held equal to `brain.tables.connector_sync.OUTCOMES` by a test.
NARROWER_OUTCOMES = "outcome IN ('failed', 'quota', 'synced')"
WIDENED_OUTCOMES = "outcome IN ('failed', 'probed', 'quota', 'synced')"

#: What this migration replaces, for `tests/unit/test_tables.py`'s `as_amended`.
SUPERSEDES: dict[str, str] = {NARROWER_OUTCOMES: WIDENED_OUTCOMES}


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, WIDENED_OUTCOMES, schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT, TABLE, NARROWER_OUTCOMES, schema=SCHEMA, postgresql_not_valid=True
    )
