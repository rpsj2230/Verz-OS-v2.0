"""A trace step may leave once it is thirty days old, and only then, by the retention sweep.

M25.1.3 asks that the payload store expire at thirty days, and M25.1.4 that the trace lifecycle do.
The window is declared (`brain.ops.tracing.RETENTION`, `brain.ops.retention.PAYLOAD_RETENTION_DAYS`)
and the daily retention sweep counts every step past it and reports it, and removed none: `0150`
gave the application role INSERT on `obs.trace_step` and nothing else, so the sweep's catalogue
question about the table (`PostgresSweeper.removal_rule`) answered "the application holds no
DELETE on it, and the migration that built it argues how its rows leave", every run, for ever.
`0150` argued how a trace is read and never how one leaves, so the one table holding a whole
question and answer in masked form was the one table nothing ever expired.

**The application role gains DELETE on `obs.trace_step`, bounded by a policy.** A grant alone would
let a compromised application delete any trace, which is the property `0150`'s write-only shape
exists to refuse, so the grant comes with the row-level policy that admits a delete only of a step
whose `recorded_at` is more than thirty days behind the database's own clock. A step from yesterday
is not removable by the application whoever asks and whatever it says. **The sweep is what asks**:
`PostgresSweeper.expire` removes what is past the window, not held under a legal hold, in a table
the role may delete from, and it is only released by a person (`ops.retention_release`), so a
step leaves on the thirty-first day after somebody has read what the sweep would remove and agreed.

**The policy reads the clock, not an argument.** The thirty is copied here for the reason `0009`
gives about reading live code from a migration, and held equal to
`brain.ops.tracing.RETENTION`'s by `tests/unit/test_trace_payload_expiry.py`. A later change to the
window is a migration that replaces this policy, which is the right size of act for shortening
the one clock that decides whether somebody's questions are still kept.

**No SELECT is granted.** The application still cannot read a step, and still reads one only by
taking `brain_trace_reader` after writing the row that says it did (`0150`). The delete policy
does not name a column the role cannot see: it is evaluated by the database, not by the role.

**The erasure queue now reaches a person's trace steps.** `brain.ops.erasure_store` decides whether
to delete from a table by the application role's DELETE grant, so a step whose request carries an
erased person's trace id is removed by an erasure rather than kept and said to be kept. The policy
bounds that too: an erasure removes a step only once it is also past the window, which leaves the
younger ones for the sweep, and says so in its report (`kept`), because an erasure that removed
what the policy forbids would be refused by the database and an erasure that said it had removed it
would be a lie.

**The downgrade** drops the policy and revokes the grant, putting `0150`'s write-only shape back.

Task ids: M25.1.3, M25.1.4

Revision ID: 0226
Revises: 0225
"""

from __future__ import annotations

from alembic import op

revision = "0226"
down_revision = "0225"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

#: How old a step must be before the application may delete it, in days. `0150` is where the
#: step's table is built; `brain.ops.tracing.RETENTION` is where the window is declared.
RETENTION_DAYS = 30

POLICY = f"""
CREATE POLICY trace_step_expired_removable ON obs.trace_step
    FOR DELETE TO {APP_ROLE}
    USING (recorded_at < now() - interval '{RETENTION_DAYS} days')
"""

GRANT = f"GRANT DELETE ON obs.trace_step TO {APP_ROLE}"
REVOKE = f"REVOKE DELETE ON obs.trace_step FROM {APP_ROLE}"


def upgrade() -> None:
    assert APP_ROLE in GRANT and "SELECT" not in GRANT
    op.execute(POLICY)
    op.execute(GRANT)


def downgrade() -> None:
    op.execute(REVOKE)
    op.execute("DROP POLICY trace_step_expired_removable ON obs.trace_step")
