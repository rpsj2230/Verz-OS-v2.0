"""Widen the audit action check constraint for `AuditAction.COMPOSE_CHANGE`.

No table, no column, no data. This is the same shape as `0007`, `0011` and `0012`, which
widened the channel vocabulary three times in a row, and it is deliberately their twin rather
than a new idea.

**Why a schema change at all, which is the part that surprises.** `brain.tables.audit` renders
the constraint from `AuditAction` itself, so adding a member updates the model with no edit
here. It does not update a deployed database. Without this migration the model and the
migration chain disagree, which `tests/unit/test_tables.py` reports immediately, and without
that test it would instead be a perfectly valid `AuditEntry` that the database refuses on the
first insert after deploy. That failure would arrive as a write to the audit ledger failing,
which is the worst place in this system to discover a schema disagreement.

**Deploy order matters here and it is one way round.** This migration must be applied before
any code writes `compose_change`. `brain.migrate` runs migrations at startup behind an
advisory lock, so a single deploy does the two in the right order; a rollback that reverts the
code without reverting the schema is safe, and one that reverts the schema without the code is
not. The downgrade below is honest about that.

**The substitution chains rather than restating the vocabulary.** `SUPERSEDES` maps `0002`'s
list to this one, because nothing has widened this constraint before: the channel sequence
declares its immediate predecessor for the same reason, and naming anything other than the
list actually in the database would be a second hand-maintained copy that stops matching the
moment either changes.

**Adding the member moved no digest, which is the question worth asking before touching an
audit chain at all.** `compute_entry_hash` takes the action per entry and `HASH_SCHEMA` is a
literal, so an unused enum member is invisible to every hash already written, and every chain
already stored still verifies. The constraint is the only thing that had to move.

**The downgrade is real and it can fail, which is correct.** Narrowing the list rejects the
migration if any row already carries `compose_change`, because recreating a check constraint
validates the rows already there. And an audit row cannot be deleted to make room: the ledger
is append-only by design and `brain.tables.audit` grants no DELETE on it. So a downgrade past
this point is only available to an installation that has never recorded a composition change,
which is the correct restriction rather than an oversight: the alternative is a downgrade that
deletes audit history to succeed.

Task ids: none
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

#: Alphabetical, matching how `tables.identity.one_of` sorts, so the model and the migration
#: compare equal as text rather than only as meaning.
WITH_COMPOSE = (
    "action IN ('break_glass', 'compose_change', 'deny', 'entity_merge', 'grant', "
    "'leash_change', 'publish', 'revoke')"
)
WITHOUT_COMPOSE = (
    "action IN ('break_glass', 'deny', 'entity_merge', 'grant', "
    "'leash_change', 'publish', 'revoke')"
)

#: What this migration replaces: `0002`'s list, which is the one in the database, because
#: nothing has widened this constraint before.
SUPERSEDES: dict[str, str] = {WITHOUT_COMPOSE: WITH_COMPOSE}


def upgrade() -> None:
    # The bare name. Alembic applies `NAMING_CONVENTION["ck"]` on top, so passing the
    # already-prefixed `ck_audit_entry_action` renders `ck_audit_entry_ck_audit_entry_action`
    # and the DROP names a constraint that has never existed. 0007 learned this and every
    # migration in that sequence has copied it since.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITH_COMPOSE, schema="obs")


def downgrade() -> None:
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITHOUT_COMPOSE, schema="obs")
