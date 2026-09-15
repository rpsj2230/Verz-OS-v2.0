"""The application role can retire a soft-deleted row, and a retired row stays hidden and retired.

**What was wrong, measured on 2026-09-15.** 0002, 0003, 0004, 0005 and 0008 gave every
soft-deleted table one `FOR ALL` policy, `USING (deleted_at IS NULL) WITH CHECK (true)`, and 0002
argued that the explicit `WITH CHECK (true)` is what lets an UPDATE set `deleted_at`. It is not.
PostgreSQL's table of the policies applied by command type says that an UPDATE which needs read
access to the row, meaning any UPDATE whose WHERE or RETURNING names a column, checks the **new**
row against the USING expression of every SELECT and ALL policy on the table, and not only
against the UPDATE policy's WITH CHECK. A retired row fails `deleted_at IS NULL`, so as
`brain_app` every one of these tables refused `UPDATE ... SET deleted_at = ... WHERE id = ...`
with "new row violates row-level security policy". Revoking a grant, which is how this system
revokes anything, and retiring a sign-in binding were both impossible through the application.
The one retirement that got through was an UPDATE with no WHERE clause at all, which retires
every row in the table. Nothing under `src` retired anything yet, which is why nobody saw it.

**Splitting the policy per command does not fix it on its own, and that was measured too.** See
`A_SEPARATE_READ_POLICY_STILL_CHECKS_THE_NEW_ROW`. The rule is about SELECT policies, and a
`FOR SELECT USING (deleted_at IS NULL)` beside a `FOR UPDATE ... WITH CHECK (true)` is refused
exactly as the `FOR ALL` was.

**So the read policy admits one retired row: the one the running statement retired.** See
`A_RETIRED_ROW_IS_VISIBLE_ONLY_TO_THE_STATEMENT_THAT_RETIRED_IT`. The read is
`deleted_at IS NULL OR deleted_at = statement_timestamp()`; the update policy's USING stays
`deleted_at IS NULL`, so a retired row can never be touched again, and its WITH CHECK repeats
the read, so a retirement is always stamped with the instant of the statement that made it and
nothing can be retired into the past or the future. Every other restriction the old policies
carried is carried into all three unchanged: `chat.conversation` still restricts to the
session's principal on the read, the insert and both halves of the update.

What that costs, said out loud:

- A retirement writes `statement_timestamp()` and not `now()`. Inside a transaction `now()` is
  the instant the transaction began, and a retirement stamped with it is refused, loudly, with
  the same row-level security error. That is the failure direction wanted: a wrong stamp cannot
  land quietly.
- A reading statement can see a retired row whose stamp equals its own start instant. That
  needs another session to have begun a retiring statement in the same microsecond and
  committed it before this statement took its snapshot, which is not a window anybody can aim
  at, and the reader's other restrictions still apply to whatever it could see.

Three cheaper shapes were rejected.

- **A `SECURITY DEFINER` retire function per table.** It works, and it bypasses the policy
  entirely, so `chat.conversation` and `know.chunk` would each need their restriction written a
  second time inside the function. A second copy of who may see a row is a second place for it
  to be wrong, and the permissive copy is the one that ships.
- **`transaction_timestamp()` in place of the statement's.** It keeps `now()` working, and it
  leaves a retired row readable for the rest of the transaction that retired it: a conversation
  deleted and then listed in the same request would still be listed.
- **`FOR SELECT USING (true)`.** Retired rows become readable everywhere. 0019 does exactly this
  for `gate.fast_path_rule` and argues why for that one table; see `RETIRED_ROWS_STAY_READABLE`.

**No DELETE policy.** The `FOR ALL` policies covered DELETE, and no role holds a DELETE grant on
any of these tables, so leaving DELETE with no policy changes nothing a role can do and puts the
refusal in two places rather than one. PostgreSQL denies what no policy admits.
`auth.directory_role_grant`, the one table with a DELETE grant, has no `deleted_at` and is not
touched.

**`gate.fast_path_rule` is here for its update policy only.** 0019 wrote it `USING (true)`, so a
retired rule could be edited back to live, and "which rule answered that question in March" is
only answerable if a retirement is final. Its read policy stays unconditional.

**`know.chunk` is 0046 rather than a row here**, because building it needs pgvector. Every table
here is buildable without it, so this migration runs, and its test runs, on a development server
that lacks the extension; 0046 is proven where the extension exists, which is CI.

**The downgrade puts back the `FOR ALL` policies exactly as they were**, including the defect.

Task ids: none

Revision ID: 0045
Revises: 0044
"""

from __future__ import annotations

from typing import Final

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

#: Why the fix is not only a per-command split.
A_SEPARATE_READ_POLICY_STILL_CHECKS_THE_NEW_ROW: Final = (
    "An UPDATE whose WHERE or RETURNING names a column needs read access to the row, and "
    "PostgreSQL then checks the new row against the USING of every SELECT and ALL policy as "
    "well as against the UPDATE policy's WITH CHECK. A read policy of deleted_at IS NULL "
    "therefore refuses the very update that sets deleted_at, whichever command it is written "
    "for, and WITH CHECK (true) on the update policy does not reach it."
)

#: Why the read policy admits a retired row at all, and which one.
A_RETIRED_ROW_IS_VISIBLE_ONLY_TO_THE_STATEMENT_THAT_RETIRED_IT: Final = (
    "The read policy admits deleted_at = statement_timestamp(), so the retiring statement's "
    "own new row passes the read check PostgreSQL applies to it, and no later statement, "
    "including the next one in the same transaction, can read the row. A retirement must "
    "therefore be stamped with statement_timestamp(); now() is refused."
)

#: The disjunct every read and update policy on a retirable table carries.
RETIRED_BY_THIS_STATEMENT: Final = "deleted_at = statement_timestamp()"

#: Tables whose retired rows stay readable, and the migration that argues it.
RETIRED_ROWS_STAY_READABLE: Final[dict[str, str]] = {
    "gate.fast_path_rule": (
        "0019: which rule answered a question in March is asked after a wrong answer, and a "
        "fast-lane answer had no model in it to explain itself afterwards"
    ),
}

RLS: tuple[str, ...] = (
    "DROP POLICY principal_live ON auth.principal",
    """
    CREATE POLICY principal_live ON auth.principal
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY principal_insertable ON auth.principal
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY principal_updatable ON auth.principal
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY principal_identity_live ON auth.principal_identity",
    """
    CREATE POLICY principal_identity_live ON auth.principal_identity
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY principal_identity_insertable ON auth.principal_identity
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY principal_identity_updatable ON auth.principal_identity
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY capability_grant_live ON gate.capability_grant",
    """
    CREATE POLICY capability_grant_live ON gate.capability_grant
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY capability_grant_insertable ON gate.capability_grant
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY capability_grant_updatable ON gate.capability_grant
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY capability_pack_live ON gate.capability_pack",
    """
    CREATE POLICY capability_pack_live ON gate.capability_pack
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY capability_pack_insertable ON gate.capability_pack
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY capability_pack_updatable ON gate.capability_pack
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY capability_pack_assignment_live ON gate.capability_pack_assignment",
    """
    CREATE POLICY capability_pack_assignment_live ON gate.capability_pack_assignment
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY capability_pack_assignment_insertable ON gate.capability_pack_assignment
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY capability_pack_assignment_updatable ON gate.capability_pack_assignment
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY field_policy_live ON gate.field_policy",
    """
    CREATE POLICY field_policy_live ON gate.field_policy
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY field_policy_insertable ON gate.field_policy
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY field_policy_updatable ON gate.field_policy
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY scope_live ON gate.scope",
    """
    CREATE POLICY scope_live ON gate.scope
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY scope_insertable ON gate.scope
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY scope_updatable ON gate.scope
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY department_live ON gate.department",
    """
    CREATE POLICY department_live ON gate.department
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY department_insertable ON gate.department
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY department_updatable ON gate.department
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY team_live ON gate.team",
    """
    CREATE POLICY team_live ON gate.team
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY team_insertable ON gate.team
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY team_updatable ON gate.team
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY routing_tier_live ON ops.routing_tier",
    """
    CREATE POLICY routing_tier_live ON ops.routing_tier
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY routing_tier_insertable ON ops.routing_tier
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY routing_tier_updatable ON ops.routing_tier
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY routing_rung_live ON ops.routing_rung",
    """
    CREATE POLICY routing_rung_live ON ops.routing_rung
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY routing_rung_insertable ON ops.routing_rung
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY routing_rung_updatable ON ops.routing_rung
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY capability_registry_live ON gate.capability_registry",
    """
    CREATE POLICY capability_registry_live ON gate.capability_registry
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY capability_registry_insertable ON gate.capability_registry
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY capability_registry_updatable ON gate.capability_registry
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY setting_live ON ops.setting",
    """
    CREATE POLICY setting_live ON ops.setting
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY setting_insertable ON ops.setting
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY setting_updatable ON ops.setting
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY record_live ON proj.record",
    """
    CREATE POLICY record_live ON proj.record
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY record_insertable ON proj.record
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY record_updatable ON proj.record
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "DROP POLICY conversation_owner ON chat.conversation",
    """
    CREATE POLICY conversation_owner ON chat.conversation
        FOR SELECT TO brain_app
        USING (
            (deleted_at IS NULL OR deleted_at = statement_timestamp())
            AND principal_id = current_setting('app.principal_id', true)
        )
    """,
    """
    CREATE POLICY conversation_insertable ON chat.conversation
        FOR INSERT TO brain_app
        WITH CHECK (
            principal_id = current_setting('app.principal_id', true)
        )
    """,
    """
    CREATE POLICY conversation_updatable ON chat.conversation
        FOR UPDATE TO brain_app
        USING (
            deleted_at IS NULL
            AND principal_id = current_setting('app.principal_id', true)
        )
        WITH CHECK (
            (deleted_at IS NULL OR deleted_at = statement_timestamp())
            AND principal_id = current_setting('app.principal_id', true)
        )
    """,
    "DROP POLICY fast_path_rule_retirable ON gate.fast_path_rule",
    """
    CREATE POLICY fast_path_rule_retirable ON gate.fast_path_rule
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
)

#: The policies 0002, 0003, 0004, 0005, 0008 and 0019 wrote, put back exactly, broken as they
#: were. Named `DOWNGRADE_` so the replay in `tests/invariants/test_soft_delete_invariants.py`
#: reads it as history rather than as the schema.
DOWNGRADE_RLS: tuple[str, ...] = (
    "DROP POLICY principal_updatable ON auth.principal",
    "DROP POLICY principal_insertable ON auth.principal",
    "DROP POLICY principal_live ON auth.principal",
    """
    CREATE POLICY principal_live ON auth.principal
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY principal_identity_updatable ON auth.principal_identity",
    "DROP POLICY principal_identity_insertable ON auth.principal_identity",
    "DROP POLICY principal_identity_live ON auth.principal_identity",
    """
    CREATE POLICY principal_identity_live ON auth.principal_identity
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY capability_grant_updatable ON gate.capability_grant",
    "DROP POLICY capability_grant_insertable ON gate.capability_grant",
    "DROP POLICY capability_grant_live ON gate.capability_grant",
    """
    CREATE POLICY capability_grant_live ON gate.capability_grant
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY capability_pack_updatable ON gate.capability_pack",
    "DROP POLICY capability_pack_insertable ON gate.capability_pack",
    "DROP POLICY capability_pack_live ON gate.capability_pack",
    """
    CREATE POLICY capability_pack_live ON gate.capability_pack
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY capability_pack_assignment_updatable ON gate.capability_pack_assignment",
    "DROP POLICY capability_pack_assignment_insertable ON gate.capability_pack_assignment",
    "DROP POLICY capability_pack_assignment_live ON gate.capability_pack_assignment",
    """
    CREATE POLICY capability_pack_assignment_live ON gate.capability_pack_assignment
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY field_policy_updatable ON gate.field_policy",
    "DROP POLICY field_policy_insertable ON gate.field_policy",
    "DROP POLICY field_policy_live ON gate.field_policy",
    """
    CREATE POLICY field_policy_live ON gate.field_policy
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY scope_updatable ON gate.scope",
    "DROP POLICY scope_insertable ON gate.scope",
    "DROP POLICY scope_live ON gate.scope",
    """
    CREATE POLICY scope_live ON gate.scope
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY department_updatable ON gate.department",
    "DROP POLICY department_insertable ON gate.department",
    "DROP POLICY department_live ON gate.department",
    """
    CREATE POLICY department_live ON gate.department
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY team_updatable ON gate.team",
    "DROP POLICY team_insertable ON gate.team",
    "DROP POLICY team_live ON gate.team",
    """
    CREATE POLICY team_live ON gate.team
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY routing_tier_updatable ON ops.routing_tier",
    "DROP POLICY routing_tier_insertable ON ops.routing_tier",
    "DROP POLICY routing_tier_live ON ops.routing_tier",
    """
    CREATE POLICY routing_tier_live ON ops.routing_tier
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY routing_rung_updatable ON ops.routing_rung",
    "DROP POLICY routing_rung_insertable ON ops.routing_rung",
    "DROP POLICY routing_rung_live ON ops.routing_rung",
    """
    CREATE POLICY routing_rung_live ON ops.routing_rung
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY capability_registry_updatable ON gate.capability_registry",
    "DROP POLICY capability_registry_insertable ON gate.capability_registry",
    "DROP POLICY capability_registry_live ON gate.capability_registry",
    """
    CREATE POLICY capability_registry_live ON gate.capability_registry
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY setting_updatable ON ops.setting",
    "DROP POLICY setting_insertable ON ops.setting",
    "DROP POLICY setting_live ON ops.setting",
    """
    CREATE POLICY setting_live ON ops.setting
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY record_updatable ON proj.record",
    "DROP POLICY record_insertable ON proj.record",
    "DROP POLICY record_live ON proj.record",
    """
    CREATE POLICY record_live ON proj.record
        FOR ALL TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (true)
    """,
    "DROP POLICY conversation_updatable ON chat.conversation",
    "DROP POLICY conversation_insertable ON chat.conversation",
    "DROP POLICY conversation_owner ON chat.conversation",
    """
    CREATE POLICY conversation_owner ON chat.conversation
        FOR ALL TO brain_app
        USING (
            deleted_at IS NULL
            AND principal_id = current_setting('app.principal_id', true)
        )
        WITH CHECK (
            principal_id = current_setting('app.principal_id', true)
        )
    """,
    "DROP POLICY fast_path_rule_retirable ON gate.fast_path_rule",
    """
    CREATE POLICY fast_path_rule_retirable ON gate.fast_path_rule
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all("DELETE" not in statement for statement in RLS)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_RLS:
        op.execute(statement)
