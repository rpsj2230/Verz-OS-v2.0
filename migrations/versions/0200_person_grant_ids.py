"""A person's History reads which grants were theirs, removed ones included, through one function.

`0003`'s trigger ledgers a capability grant and a pack assignment under `grant:<id>`, with the
capability or the pack in the details and never the person, because the entry is about the grant.
A person's History tab asks the ledger for `principal:<id>` and so never showed a capability given
to them or taken away, only the role grants `0102` files under the person. Finding a person's grant
entries needs the ids of that person's grants, and the application role cannot read a removed one:
`0045`'s `capability_grant_live` shows a row only while `deleted_at` is null, which is right for
every reader that decides access and leaves the History blind to every removal.

**`gate.grant_ids_of` is `SECURITY DEFINER`, for one read and one reason**, as `0177`'s
`gate.expired_handoffs` is. It returns the ids of one person's capability grants and pack
assignments, live or removed, and nothing else: no capability, no scope, no dates, no actor. What
was granted is read back off the ledger entries those ids name, through `brain.audit.view.AuditView`,
so the reader's own audit reach still decides every entry. The caller is
`brain.audit_routes.audit_history`, and it calls this only after the People screen's own
`nameable` has admitted the reader to that person, so the function is never asked about somebody
the reader could not be shown.

Its search path is pinned and every object is named with its schema. It is `STABLE`, ordered by id
and bounded by a limit the caller passes. EXECUTE is revoked from PUBLIC and granted to `brain_app`
alone, which `brain.deployment.compatibility` reads as a revoke on a function this body created.

Rejected: changing `0003`'s trigger to name the person in the details. It reaches only entries
written after it, so every grant made before it would still be missing from History, which is the
whole of every install's history on the day it ships.

The downgrade drops the function, after which a person's History shows role grants alone again.

Task ids: M33.4.1.2

Revision ID: 0200
Revises: 0187
"""

from __future__ import annotations

from alembic import op

revision = "0200"
# The head of main on the day. Re-pointed at whichever migration is the head when it lands:
# nothing here depends on anything after 0045.
down_revision = "0196"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

FUNCTION = "gate.grant_ids_of(text, integer)"

CREATE_FUNCTION = """
CREATE FUNCTION gate.grant_ids_of(
    p_principal text,
    p_limit integer
)
RETURNS TABLE (
    grant_id uuid
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, gate
AS $grants$
    SELECT g.grant_id
    FROM (
        SELECT c.id AS grant_id FROM gate.capability_grant AS c WHERE c.principal_id = p_principal
        UNION ALL
        SELECT a.id FROM gate.capability_pack_assignment AS a WHERE a.principal_id = p_principal
    ) AS g
    ORDER BY g.grant_id
    LIMIT greatest(p_limit, 0)
$grants$
"""

GRANTS: tuple[str, ...] = (
    f"REVOKE EXECUTE ON FUNCTION {FUNCTION} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {APP_ROLE}",
)


def upgrade() -> None:
    op.execute(CREATE_FUNCTION)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FUNCTION}")
