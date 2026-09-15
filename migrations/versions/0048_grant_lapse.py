"""The resolver says when the reach it returned stops being true, so a cache cannot outlive a grant.

`brain.gate.resolve` caches a reach for sixty seconds under a key carrying `grants_version`, and a
version moves only when a row is written. A grant whose own `not_after` passes is not a write, so
until this migration a reach cached a second before a grant lapsed kept serving that grant for up
to a minute afterwards. `gate.resolve_entitlements` filtered the lapsed grant out on the next load
and returned no dates, so nothing on the application side could know when to stop trusting the
entry. That was measured and recorded in b53eace and 07fb96b.

**The rows a principal holds are now answered by one function, and both documents are read off
it.** `gate.held_grants` is the body `0003` wrote inside the resolver: the direct grants and the
pack members, with every way a grant stops counting (retired, lapsed, its pack retired, its
principal disabled or deleted). `gate.resolve_entitlements` is replaced to aggregate over it and
returns exactly the document it returned before, and `gate.entitlements_with_lapse` is that
document with the earliest `not_after` among the same rows added as `next_grant_lapse`. See
`ONE_ROW_SET_AND_TWO_READINGS_OF_IT`.

Rejected: a sibling function with its own copy of the four predicates. It is the cheaper
migration and it is the drift `0003` exists to prevent. Its failure is quiet and in the wrong
direction: a sibling that forgot a pack's `deleted_at` would report nothing wrong, and one that
missed a live grant's date would hand the cache a lifetime longer than the reach is true for.

Rejected: adding the key to `gate.resolve_entitlements` itself. It is one function instead of
three, and it breaks the rolling deploy `brain.deployment.compatibility` describes: the previous
release validates the document with `extra="forbid"`, so for the length of the swap every load
would fail and every request would be refused. The function the previous release calls keeps
its signature, its return type and its answer; only the new store calls the new function.

**The replacement edits a function every grant write's audit trigger calls**, which `0047`
declined to do for a feature of a different table. Here the change is to the resolver's own
answer and nowhere else would hold it; `tests/unit/test_grant_lapse.py` builds `0003`, reads a
seeded company's answers, upgrades to this revision and reads them again, and requires them equal,
then downgrades and requires them equal a third time.

**`next_grant_lapse` is strictly after `p_now` or null**, because the rows it is read off already
exclude a grant whose `not_after` is not after `p_now`. The principal's own `not_after` is not
folded into it: that date is already on the document and `EntitlementSet.is_expired` judges it.

Task ids: M1.4.4, M3.3.1

Revision ID: 0048
Revises: 0047
"""

from __future__ import annotations

from typing import Final

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

APP_ROLE = "brain_app"

#: Why the rows are a function of their own, read by both documents.
ONE_ROW_SET_AND_TWO_READINGS_OF_IT: Final = (
    "What a principal holds at an instant is decided in gate.held_grants alone. The resolver's "
    "document and the lapse beside it are both read off those rows, so the earliest lapse cannot "
    "count a grant the reach does not hold or miss one it does."
)

# The body `0003` wrote inside the resolver, lifted out whole. The casts are there because a
# `RETURNS TABLE` column must match exactly, and `capability` is varchar(200) in `0002`.
HELD_GRANTS = """
CREATE FUNCTION gate.held_grants(p_principal_id text, p_now timestamptz)
RETURNS TABLE (capability text, scope jsonb, not_after timestamptz)
LANGUAGE sql
STABLE
AS $$
    SELECT g.capability::text, g.scope, g.not_after
    FROM gate.capability_grant g
    JOIN auth.principal pr ON pr.id = g.principal_id
    WHERE g.principal_id = p_principal_id
      AND g.deleted_at IS NULL
      AND (g.not_after IS NULL OR g.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
    UNION ALL
    SELECT member.capability::text, a.scope, a.not_after
    FROM gate.capability_pack_assignment a
    JOIN gate.capability_pack k
      ON k.id = a.pack_id
     AND k.deleted_at IS NULL
    JOIN auth.principal pr ON pr.id = a.principal_id
    CROSS JOIN LATERAL unnest(k.capabilities) AS member(capability)
    WHERE a.principal_id = p_principal_id
      AND a.deleted_at IS NULL
      AND (a.not_after IS NULL OR a.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
$$
"""

# The same document `0003` builds, over the rows above.
RESOLVER_OVER_HELD_GRANTS = """
CREATE OR REPLACE FUNCTION gate.resolve_entitlements(p_principal_id text, p_now timestamptz)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
    SELECT jsonb_build_object(
        'principal_id', p_principal_id,
        'not_after', (
            SELECT to_jsonb(pr.not_after)
            FROM auth.principal pr
            WHERE pr.id = p_principal_id
              AND pr.deleted_at IS NULL
        ),
        'grants', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'capability', jsonb_build_object('value', held.capability),
                    'scope', held.scope
                )
                ORDER BY held.capability, held.scope::text
            )
            FROM gate.held_grants(p_principal_id, p_now) AS held
        ), '[]'::jsonb)
    )
$$
"""

# The resolver's document and the earliest lapse among the rows it was built from. One STABLE
# function, so both readings see one snapshot.
WITH_LAPSE = """
CREATE FUNCTION gate.entitlements_with_lapse(p_principal_id text, p_now timestamptz)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
    SELECT gate.resolve_entitlements(p_principal_id, p_now) || jsonb_build_object(
        'next_grant_lapse', (
            SELECT to_jsonb(min(held.not_after))
            FROM gate.held_grants(p_principal_id, p_now) AS held
        )
    )
$$
"""

# `0003`'s resolver, restated for the downgrade for the reason `0003` gives for copying grammars:
# this file keeps describing the database it leaves behind.
RESOLVER_AS_0003_WROTE_IT = """
CREATE OR REPLACE FUNCTION gate.resolve_entitlements(p_principal_id text, p_now timestamptz)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
    SELECT jsonb_build_object(
        'principal_id', p_principal_id,
        'not_after', (
            SELECT to_jsonb(pr.not_after)
            FROM auth.principal pr
            WHERE pr.id = p_principal_id
              AND pr.deleted_at IS NULL
        ),
        'grants', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'capability', jsonb_build_object('value', held.capability),
                    'scope', held.scope
                )
                ORDER BY held.capability, held.scope::text
            )
            FROM (
                SELECT g.capability, g.scope
                FROM gate.capability_grant g
                JOIN auth.principal pr ON pr.id = g.principal_id
                WHERE g.principal_id = p_principal_id
                  AND g.deleted_at IS NULL
                  AND (g.not_after IS NULL OR g.not_after > p_now)
                  AND pr.deleted_at IS NULL
                  AND pr.disabled_at IS NULL
                UNION ALL
                SELECT member.capability, a.scope
                FROM gate.capability_pack_assignment a
                JOIN gate.capability_pack k
                  ON k.id = a.pack_id
                 AND k.deleted_at IS NULL
                JOIN auth.principal pr ON pr.id = a.principal_id
                CROSS JOIN LATERAL unnest(k.capabilities) AS member(capability)
                WHERE a.principal_id = p_principal_id
                  AND a.deleted_at IS NULL
                  AND (a.not_after IS NULL OR a.not_after > p_now)
                  AND pr.deleted_at IS NULL
                  AND pr.disabled_at IS NULL
            ) AS held
        ), '[]'::jsonb)
    )
$$
"""

#: The functions this migration creates, in creation order. `downgrade` drops them in reverse.
FUNCTIONS: tuple[str, ...] = (
    "gate.held_grants(text, timestamptz)",
    "gate.entitlements_with_lapse(text, timestamptz)",
)

#: Named per function, as `0003` grants the resolver, rather than left to PUBLIC's default.
GRANTS: tuple[str, ...] = (
    "GRANT EXECUTE ON FUNCTION gate.held_grants(text, timestamptz) TO brain_app",
    "GRANT EXECUTE ON FUNCTION gate.entitlements_with_lapse(text, timestamptz) TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    op.execute(HELD_GRANTS)
    op.execute(RESOLVER_OVER_HELD_GRANTS)
    op.execute(WITH_LAPSE)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The resolver goes back first, so nothing live reads `gate.held_grants` when it is dropped.
    op.execute(RESOLVER_AS_0003_WROTE_IT)
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
