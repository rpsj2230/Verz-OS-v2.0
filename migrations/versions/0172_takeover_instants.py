"""The autonomy breaker reads when an agent's work was taken over, and nothing else about it.

`brain.gate.abstain.AutonomyBreaker` lowers an agent's rung on one target by one step once a person
has taken its work over three times inside seven days (M8.3.5). The takeovers are rows of
`gate.suspension` with the verdict `taken_over`, which `0083` records, and `0042`'s policy admits a
reader to a row only when it runs as them, when they decided it, or when it is pending and they may
approve it. **So the breaker could not be fed under the reach of the person the agent is working
for**: every takeover somebody else decided is outside their policy, and the rung their next action
is held to would be computed from the takeovers they happened to decide, which is a lens seeing a
different agent depending on who looks through it.

**`gate.takeover_instants` is `SECURITY DEFINER`, for one read and one reason**, as `0040`'s
`know.items_for_review` is for the review sweep. It returns the instants at which this agent's
action on this target was taken over inside the window the caller names, and nothing else: no
person, no action, no artefact, no reason. See
`brain.gate.takeover_store.A_TAKEOVER_INSTANT_SAYS_WHEN_AND_NAMES_NOTHING` for why that discloses
nothing a caller of the agent could not already infer from the rung it is held to. Both ends of the
window are parameters and the body reads no clock, so the instant a decision is taken is the
caller's, as `brain.gate.leash.decide`'s `now` is, and a test can pin it.

Its search path is pinned and every object is named with its schema, the arrangement `0040` makes.
It is `STABLE` so a replica may serve it, and bounded by a limit the caller passes, newest first,
because the breaker needs three and the agent's page shows a week.

**EXECUTE is revoked from `PUBLIC` and granted to `brain_app` alone.** `0036` and `0040` left
`PUBLIC` its default grant because `brain.deployment.compatibility` read every REVOKE as a narrowing
of the previous release, and said the revoke belonged back once the gate was taught why. It is
taught here: a REVOKE on a function the same body creates removes nothing the previous release
could call, which is `A_REVOKE_ON_A_FUNCTION_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING`.

**A partial index on the taken-over rows**, by agent and decision time, so the read on every leash
decision is an index scan over the few rows that can ever count rather than a scan of every
suspension ever raised. `CREATE INDEX` on an existing table is additive; the model declares it.

The downgrade drops the function and the index, after which the breaker has nothing to read and
`brain.gate.takeover_store` answers every agent with an empty standing.

Task ids: M8.3.5

Revision ID: 0172
Revises: 0166
"""

from __future__ import annotations

from alembic import op

revision = "0172"
<<<<<<< HEAD
# Stacked after #268's 0166 on this branch, as the train lands them. Re-pointed at whichever
# migration is the head when it lands: nothing here depends on a table a later migration builds.
=======
# The head of origin/main when this was written. Re-pointed at whichever migration is the head
# when it lands: nothing here depends on a table a later migration builds.
>>>>>>> origin/M8/w2-takeover
down_revision = "0166"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

#: `brain.audit.record.ApprovalVerdict.TAKEN_OVER`, copied for `0009`'s reason about reading live
#: code from a migration and held equal to it by a test.
TAKEN_OVER = "taken_over"

FUNCTION = (
    "gate.takeover_instants(character varying, character varying, timestamptz, timestamptz, "
    "integer)"
)

CREATE_FUNCTION = """
CREATE FUNCTION gate.takeover_instants(
    p_agent character varying,
    p_target character varying,
    p_after timestamptz,
    p_until timestamptz,
    p_limit integer
)
RETURNS TABLE (taken_over_at timestamptz)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, gate
AS $takeovers$
    SELECT s.decided_at
    FROM gate.suspension AS s
    WHERE s.verdict = 'taken_over'
      AND s.agent_id = p_agent
      AND s.action ->> 'target' = p_target
      AND s.decided_at > p_after
      AND s.decided_at <= p_until
    ORDER BY s.decided_at DESC
    LIMIT greatest(p_limit, 0)
$takeovers$
"""

INDEX = "ix_suspension_taken_over"

CREATE_INDEX = (
    f"CREATE INDEX {INDEX} ON gate.suspension (agent_id, decided_at) WHERE verdict = '{TAKEN_OVER}'"
)

GRANTS: tuple[str, ...] = (
    f"REVOKE EXECUTE ON FUNCTION {FUNCTION} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {APP_ROLE}",
)


def upgrade() -> None:
    assert f"s.verdict = '{TAKEN_OVER}'" in CREATE_FUNCTION
    assert "now()" not in CREATE_FUNCTION.lower(), "the window is the caller's, not the clock's"
    op.execute(CREATE_INDEX)
    op.execute(CREATE_FUNCTION)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FUNCTION}")
    op.execute(f"DROP INDEX gate.{INDEX}")
