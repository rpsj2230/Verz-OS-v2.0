"""Widen the audit action check constraint for `AuditAction.APPROVAL`.

No table, no column, no data. The twin of `0022`, which is the twin of `0007`, `0011` and
`0012`, and it is deliberately their copy rather than a new idea: the fifth time this
constraint has been widened, the fifth time in the same shape.

**Why a schema change at all.** `brain.tables.audit` renders the constraint from `AuditAction`
itself, so adding a member updates the model with no edit here and does not update a deployed
database. Without this migration the model and the migration chain disagree, which
`tests/unit/test_tables.py` reports immediately; without that test it would instead be a
perfectly valid `AuditEntry` that the database refuses on the first insert after deploy, and
that failure arrives as a write to the audit ledger failing, which is the worst place in this
system to discover a schema disagreement.

**Deploy order matters and it is one way round.** This must be applied before any code writes
`approval`. `brain.migrate` runs migrations at startup behind an advisory lock, so a single
deploy does the two in the right order; a rollback that reverts the code without reverting the
schema is safe, and one that reverts the schema without the code is not. The downgrade below
is honest about that.

**The substitution chains rather than restating the vocabulary.** `SUPERSEDES` maps `0022`'s
list to this one, because `0022` is what is in the database. Naming anything else would be a
second hand-maintained copy that stops matching the moment either changes.

**Adding the member moved no digest.** `compute_entry_hash` takes the action per entry and
`HASH_SCHEMA` is a literal, so an unused enum member is invisible to every hash already
written, and every chain already stored still verifies. The constraint is the only thing that
had to move.

**The downgrade is real and it can fail, which is correct.** Narrowing the list rejects the
migration if any row already carries `approval`, because recreating a check constraint
validates the rows already there, and an audit row cannot be deleted to make room: the ledger
is append-only and `brain.tables.audit` grants no DELETE on it. So a downgrade past this point
is only available to an installation where nobody has ever decided an approval, which is the
correct restriction rather than an oversight.

Task ids: none
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

#: Alphabetical, matching how `tables.identity.one_of` sorts, so the model and the migration
#: compare equal as text rather than only as meaning.
WITH_APPROVAL = (
    "action IN ('approval', 'break_glass', 'compose_change', 'deny', 'entity_merge', "
    "'grant', 'leash_change', 'publish', 'revoke')"
)
WITHOUT_APPROVAL = (
    "action IN ('break_glass', 'compose_change', 'deny', 'entity_merge', 'grant', "
    "'leash_change', 'publish', 'revoke')"
)

#: What this migration replaces: `0022`'s list, which is the one in the database.
SUPERSEDES: dict[str, str] = {WITHOUT_APPROVAL: WITH_APPROVAL}


def upgrade() -> None:
    # The bare name. Alembic applies `NAMING_CONVENTION["ck"]` on top, so passing the
    # already-prefixed `ck_audit_entry_action` renders `ck_audit_entry_ck_audit_entry_action`
    # and the DROP names a constraint that has never existed. 0007 learned this and every
    # migration in that sequence has copied it since.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITH_APPROVAL, schema="obs")


def downgrade() -> None:
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITHOUT_APPROVAL, schema="obs")
