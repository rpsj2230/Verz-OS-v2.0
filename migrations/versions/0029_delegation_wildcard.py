"""The SQL twin of the run reach narrows a parent's wildcard instead of dropping it.

`gate.delegated_reach` is `brain.core.scope_sql`'s copy of `EntitlementSet.intersect`, folded
over a parent reach and two ceilings, and its only consumer is the trigger `0028` installed,
which refuses a delegation row claiming more than it computes. It was written as a mirror of
the Python and it mirrored a defect in both directions. It read the capabilities a child may
hold off the parent's grants alone, so a parent holding `read:client.*` delegated through a
ceiling naming `read:client.name` computed nothing. And it took each grant's scope from that
grant alone, so a parent holding the wildcard in Web and the column in the gold tier computed
the column in gold clients of every department, losing the Web clause. The Python was repaired
on 2026-09-14, and this replaces the function with the one that agrees with it.

**A new migration rather than an edit to `0028`, because `0028` has been applied.** A database
at `0028` holds the old body whatever that file says afterwards, and alembic never runs a
revision twice, so an edit there would reach fresh installs and no deployed one.

**On a fresh install this changes nothing, and that is worth knowing rather than discovering.**
`0028` renders its statements from `brain.core.scope_sql` at the moment it runs, so a database
built from empty after this commit already receives the corrected function at `0028`, and the
`CREATE OR REPLACE` here writes the same body a second time. On a database that ran `0028`
before this commit, this is the statement that replaces it.

**The downgrade writes back the body `0028` installed, spelled out below and deliberately not
rendered from the module.** Every other statement in these migrations is imported from the
module owning the rule, because a copy goes stale. This one is meant to stay exactly as it
shipped: a database downgraded to `0028` is paired with the code of `0028`, whose `intersect`
it has to agree with, and rendering it from the module would make the downgrade a statement
that changes nothing. `tests/unit/test_delegation_sql.py` downgrades a live database, asserts
the old reach comes back, upgrades it again and asserts the new one does.

A database downgraded while the application stays on newer code computes a narrower reach than
the Python, so the trigger refuses a legitimate delegation through a wildcard. That is loud, and
it is the direction `brain.core.scope_sql` records as the affordable one for this copy to fail
in.

Task ids: M18.3.1
"""

from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

#: The function as it is now, rendered from the module that owns the rule, for the reason
#: `0028` gives: a literal here would be a second copy of a decision that goes stale.
from brain.core.scope_sql import DELEGATED_REACH_SQL  # noqa: E402 - after the revision identifiers, on purpose

#: `gate.delegated_reach` exactly as `0028` installed it, which is `DELEGATED_REACH_SQL` in
#: `brain.core.scope_sql` at commit 60087ad. Frozen on purpose; see the module docstring.
AS_0028_INSTALLED = """
CREATE OR REPLACE FUNCTION gate.delegated_reach(
    parent jsonb, agent_ceiling jsonb, subtask_ceiling jsonb, at timestamptz)
RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET timezone = 'UTC'
AS $reach$
    SELECT jsonb_build_object(
        'principal_id', parent ->> 'principal_id',
        'grants', coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'capability', g.value -> 'capability',
                'scope', jsonb_build_object('clauses', (
                    SELECT coalesce(jsonb_agg(DISTINCT c.value), '[]'::jsonb)
                    FROM jsonb_array_elements(
                        coalesce(g.value -> 'scope' -> 'clauses', '[]'::jsonb)
                        || narrowed.by_the_agent
                        || narrowed.by_the_subtask) AS c(value)
                ))
            ) ORDER BY g.ordinality)
            FROM jsonb_array_elements(coalesce(parent -> 'grants', '[]'::jsonb))
                 WITH ORDINALITY AS g(value, ordinality),
                 LATERAL (
                     SELECT gate.entitlement_scope_for(
                                agent_ceiling, g.value -> 'capability' ->> 'value', at)
                            AS by_the_agent,
                            gate.entitlement_scope_for(
                                subtask_ceiling, g.value -> 'capability' ->> 'value', at)
                            AS by_the_subtask
                 ) AS narrowed
            WHERE narrowed.by_the_agent IS NOT NULL
              AND narrowed.by_the_subtask IS NOT NULL
        ), '[]'::jsonb),
        'not_after', LEAST(
            (parent ->> 'not_after')::timestamptz,
            (agent_ceiling ->> 'not_after')::timestamptz,
            (subtask_ceiling ->> 'not_after')::timestamptz)
    )
$reach$
"""


def upgrade() -> None:
    op.execute(DELEGATED_REACH_SQL)


def downgrade() -> None:
    op.execute(AS_0028_INSTALLED)
