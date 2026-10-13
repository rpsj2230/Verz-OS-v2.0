"""An agent's steward and administrators may read who used it, when, and how each run ended.

`ops.agent_run` (`0188`) was readable by the person a run was for and by nobody else, which was
right until the owner decided on needs item 121 (2026-10-13, option B) that on an agent's page its
owner and administrators also see that other people's conversations happened: who, when, and
whether the agent failed, never the question or the answer. The table holds none of the last two
(counts and names from closed lists), so widening who may read its rows widens nothing about what
anybody said.

**A second select policy, and no table, column or grant.** A row is readable when its agent is the
one `app.overseen_agent` names and that agent is not a personal one. The route that names the agent
has already decided who may be told, as `app.approvable` is decided by `EntitlementSet.holds` and
not by SQL: the agent's steward, and a holder of the lifecycle authority over its row. The policy is
the second wall for what that decision cannot be allowed to reach: a row of an agent the session
cannot see is not read because the agent does not exist to this session, and a personal agent's
rows are never read this way because what a personal agent did is its owner's alone. Policies are
alternatives, so `0188`'s own-rows policy is untouched and a person still reads their own runs
whatever this is set to.

**The setting names one agent.** It is a single id and not a list, so a session cannot be told to
read two agents' runs at once by accident, and an unset setting reads no row but the person's own.

**The downgrade drops the policy.** Nothing else changed.

Task ids: M39.11.1

Revision ID: 0224
Revises: 0223
"""

from __future__ import annotations

from alembic import op

revision = "0224"
# main's head at the time of writing. Re-pointed at whichever migration is the head when it lands.
down_revision = "0223"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

OVERSEEN = "current_setting('app.overseen_agent', true)"

POLICY = f"""
CREATE POLICY agent_run_overseen ON ops.agent_run
    FOR SELECT TO brain_app
    USING (
        agent_id = {OVERSEEN}
        AND EXISTS (
            SELECT 1 FROM agent.agent a
             WHERE a.id = ops.agent_run.agent_id
               AND a.visibility <> 'personal'
        )
    )
"""


def upgrade() -> None:
    op.execute(POLICY)


def downgrade() -> None:
    op.execute("DROP POLICY agent_run_overseen ON ops.agent_run")
