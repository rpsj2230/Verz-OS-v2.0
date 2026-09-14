"""The database copy of the delegation containment rule asks both sides, as the Python does.

`gate.narrowing_refusals` is the check the delegation trigger `0028` installed runs against a
row. It matched a child's grants to its parent's on the exact capability string, and once
`EntitlementSet.intersect` began narrowing a wildcard that failed in the permissive direction: a
parent reaching `read:client.name` only in Web's gold clients passed a child holding
`read:client.*` in Web, which reaches the name column in every tier of Web. The Python original,
`brain.orchestration.delegation.narrowing_refusals`, was made exact on 2026-09-14, and this
replaces the function with the one that agrees with it.

**A new migration rather than an edit to `0028`, because `0028` has been applied.** A database
at `0028` holds the old body whatever that file says afterwards, and alembic never runs a
revision twice.

**On a fresh install this changes nothing.** `0028` renders its statements from
`brain.core.scope_sql` when it runs, so a database built from empty after this commit already
receives the corrected function, and the `CREATE OR REPLACE` here writes the same body again. On
a database that ran `0028` before this commit, this is the statement that replaces it.

**The downgrade writes back the body that shipped, spelled out below and deliberately not
rendered from the module**, for the reason `0029` gives about its own: a database downgraded is
paired with the older code, and rendering the body from the module would make the downgrade a
statement that changes nothing.

A database downgraded while the application stays on newer code runs the permissive copy, and
the trigger admits a child that kept a wildcard its parent only reached narrowly. So do not
downgrade past this revision without downgrading the application.

Task ids: M18.3.2
"""

from __future__ import annotations

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

#: The function as it is now, rendered from the module that owns the rule.
from brain.core.scope_sql import NARROWING_REFUSALS_SQL  # noqa: E402 - after the revision identifiers, on purpose

#: `gate.narrowing_refusals` exactly as it shipped before this revision, which is
#: `NARROWING_REFUSALS_SQL` in `brain.core.scope_sql` at commit 77c7313. Frozen on purpose; see
#: the module docstring.
AS_SHIPPED_BEFORE = """CREATE OR REPLACE FUNCTION gate.narrowing_refusals(child jsonb, parent jsonb)
RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET timezone = 'UTC'
AS $refusals$
    SELECT coalesce(array_agg(finding ORDER BY finding), ARRAY[]::text[])
    FROM (
        SELECT 'the child names principal ' || coalesce(child ->> 'principal_id', '?')
               || ' and the parent names ' || coalesce(parent ->> 'principal_id', '?')
               || '; narrowing keeps the caller''s id, so this row was not produced by '
               || 'narrowing that caller''s reach' AS finding
        WHERE child ->> 'principal_id' IS DISTINCT FROM parent ->> 'principal_id'
        UNION ALL
        SELECT (g.value -> 'capability' ->> 'value')
               || ' is held by the child and by no grant of the parent''s'
        FROM jsonb_array_elements(child -> 'grants') AS g(value)
        WHERE NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(parent -> 'grants') AS p(value)
            WHERE p.value -> 'capability' ->> 'value'
                  = g.value -> 'capability' ->> 'value')
        UNION ALL
        SELECT (g.value -> 'capability' ->> 'value')
               || ' is scoped in the child without every clause the parent''s grant '
               || 'carried, and scopes compose by conjunction only, so a dropped clause '
               || 'is rows the parent could not see'
        FROM jsonb_array_elements(child -> 'grants') AS g(value)
        WHERE EXISTS (
            SELECT 1 FROM jsonb_array_elements(parent -> 'grants') AS p(value)
            WHERE p.value -> 'capability' ->> 'value'
                  = g.value -> 'capability' ->> 'value')
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(parent -> 'grants') AS p(value)
            WHERE p.value -> 'capability' ->> 'value'
                  = g.value -> 'capability' ->> 'value'
              AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(
                    coalesce(p.value -> 'scope' -> 'clauses', '[]'::jsonb)) AS wanted(value)
                WHERE NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(
                        coalesce(g.value -> 'scope' -> 'clauses', '[]'::jsonb)) AS held(value)
                    WHERE held.value = wanted.value)))
        UNION ALL
        SELECT 'the child expires at ' || coalesce(child ->> 'not_after', 'never')
               || ' and the parent at ' || (parent ->> 'not_after')
               || '; a delegated run outliving the reach it came from is a grant with a '
               || 'later expiry than the one it was cut from'
        WHERE parent ->> 'not_after' IS NOT NULL
          AND (child ->> 'not_after' IS NULL
               OR (child ->> 'not_after')::timestamptz
                  > (parent ->> 'not_after')::timestamptz)
    ) AS refusals
$refusals$
"""


def upgrade() -> None:
    op.execute(NARROWING_REFUSALS_SQL)


def downgrade() -> None:
    op.execute(AS_SHIPPED_BEFORE)
