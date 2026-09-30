"""The web process reads which handed-on questions expired, so each asker is told in their own chat.

`0168` built `gate.escalation` and its read policy: a handoff is read by the person who asked, the
person it was sent to, or the person named for its queue. The worker marks a handoff expired past
its deadline (`escalation_expiry`), and that was all that happened: the asker was told nothing in any
chat. The worker cannot tell them, by design: channel bot tokens are read under the application's
vault role and `ops/openbao/policies/worker.hcl` grants the worker none. So the web process tells
them, through `brain.tell_later`, and it has to know which handoffs expired across every asker,
which no one reader's policy admits.

**`gate.expired_handoffs` is `SECURITY DEFINER`, for one read and one reason**, as `0172`'s
`gate.takeover_instants` is. It returns, for each handoff that expired inside the window the caller
names, the handoff's id, who asked, the queue and when it expired, and nothing else: not the
question, not what was tried, not whom it was sent to. See
`brain.escalation_told.AN_EXPIRED_HANDOFF_IS_READ_FOR_ITS_ASKER_AND_NAMES_NOTHING_ELSE`. Both ends of
the window are parameters and the body reads no clock.

Its search path is pinned and every object is named with its schema. It is `STABLE`, and bounded by a
limit the caller passes, oldest first, so a backlog is told in order. EXECUTE is revoked from PUBLIC
and granted to `brain_app` alone, which `brain.deployment.compatibility` reads as a revoke on a
function this body created.

The downgrade drops the function, after which nothing tells an asker and the expiry is listed in the
web application as it was.

Task ids: M8.3.4

Revision ID: 0177
Revises: 0166
"""

from __future__ import annotations

from alembic import op

revision = "0177"
# The head of its branch, which carries #299's 0168 and #268's 0166. Re-pointed at whichever
# migration is the head when it lands: nothing here depends on anything later than 0168.
down_revision = "0166"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

FUNCTION = "gate.expired_handoffs(timestamptz, timestamptz, integer)"

CREATE_FUNCTION = """
CREATE FUNCTION gate.expired_handoffs(
    p_after timestamptz,
    p_until timestamptz,
    p_limit integer
)
RETURNS TABLE (
    escalation_id uuid,
    asker_id character varying,
    queue character varying,
    expired_at timestamptz
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, gate
AS $expired$
    SELECT e.id, e.asker_id, e.queue, e.expired_at
    FROM gate.escalation AS e
    WHERE e.expired_at IS NOT NULL
      AND e.expired_at > p_after
      AND e.expired_at <= p_until
    ORDER BY e.expired_at, e.id
    LIMIT greatest(p_limit, 0)
$expired$
"""

GRANTS: tuple[str, ...] = (
    f"REVOKE EXECUTE ON FUNCTION {FUNCTION} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {APP_ROLE}",
)


def upgrade() -> None:
    assert "now()" not in CREATE_FUNCTION.lower(), "the window is the caller's, not the clock's"
    op.execute(CREATE_FUNCTION)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FUNCTION}")
