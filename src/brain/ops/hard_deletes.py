"""The tables the application may hard-delete from, each with the reason a delete is the design.

Every other table retires its rows: `deleted_at`, `archived_at`, a superseding row or an end date.
A hard delete destroys the audit trail for the thing deleted, and the audit trail is the product.
That rule was held by `tests/unit/test_directory_role_grant.py`, which read **text**: lines that
begin with a quoted `GRANT`, and the `GRANTS` tuple of each migration module. It had two holes and
the second one was real. A migration that spells its grant as an f-string in a constant named
anything but `GRANTS` is invisible to both scans, and `0226` did exactly that: it gave the
application role `DELETE` on `obs.trace_step` through `GRANT = f"GRANT DELETE ON obs.trace_step
TO {APP_ROLE}"`, and the guard stayed green with six tables holding the privilege and five named.

**So the set is derived, not scanned.** `held_by_the_application` asks the catalogue that
`brain.ops.application_privileges` renders offline from the migrations themselves, which is the SQL
`alembic upgrade --sql` would print with every f-string, loop and constant already expanded, and
which follows role membership: a table `brain_app` can delete from through a role it is a member of
is a table it can delete from. Nothing here parses Python or matches a line.

**What is rejected.** Reading a live database with `has_table_privilege` is the stronger evidence
about the grant and needs a server the invariant suite does not have; the migrations are what
every install runs, so the rendered statements are the same fact without one. A deny list ("these
tables must never be deleted from") is rejected for the reason the whole system has no deny list:
the safe direction is a list of what is allowed, argued, and anything else refused.

**Each entry argues, and a new one needs the same argument.** A hard delete is allowed here only
where the row records no act by anybody that an audit would need, or where retention or erasure is
the product's own promise and a policy bounds the delete to the rows that promise covers. A table
that records what somebody did retires its rows, and the console names that act (retire, end,
disconnect, switch off, withdraw, detach or supersede) wherever it offers it.

Task ids: M27.15.52
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from brain.ops.application_privileges import APPLICATION_ROLE, Catalogue

#: The rule the set below is held to, stated so a test can name it.
A_TABLE_OUTSIDE_THE_DESIGNED_HARD_DELETES_GRANTS_THE_APPLICATION_NO_DELETE: Final = (
    "The application role holds DELETE on exactly the tables listed here, each with the reason a "
    "hard delete is the design. Every other table retires its rows."
)

#: Table to the reason it may be hard-deleted from. Qualified names, as the migrations spell them.
DESIGNED_HARD_DELETES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "auth.directory_role_grant": (
            "A role a directory group confers is removed when the person leaves the group. A "
            "tombstone column here would be a row that subtracts, which entitlements being "
            "additive only refuses, so revocation is the deletion of a grant, and the record "
            "that the directory once asserted the role is on the append-only ledger, which a "
            "delete here cannot reach (0006, 0109)."
        ),
        "obs.application_log": (
            "A log row records no change to anything and no act by anybody, so there is no audit "
            "trail for a hard delete to destroy; the audit chain is obs.audit_entry. Rows leave by "
            "age through the retention sweep and by volume through the log store's ceiling (0063)."
        ),
        "obs.trace_step": (
            "A trace step holds a whole question and answer in masked form and must expire at "
            "thirty days (M25.1.3). The delete is bounded by a row-level policy to steps older "
            "than the window by the database's own clock, so the application cannot remove a "
            "recent trace, and the sweep that asks is released only by a person (0226)."
        ),
        "auth.member_preference": (
            "A setting a person keeps for themselves, erased with them. It is nobody's audit trail "
            "and nothing else refers to it (0229)."
        ),
        "agent.artifact_share": (
            "A share is a reference from one person to an artifact they may already open, which "
            "only the sharer may withdraw. The artifact and the sharer's own copy stay exactly "
            "where they were (0230)."
        ),
        "agent.project_item": (
            "An entry on the list of a person's own project is a reference, and only the project's "
            "owner may take it out. The thread or file it names is untouched (0233)."
        ),
    }
)


def held_by_the_application(catalogue: Catalogue) -> frozenset[str]:
    """Every table the application role may delete from, directly or through a role it inherits."""
    return frozenset(
        table
        for table in sorted(catalogue.tables)
        if catalogue.holds(APPLICATION_ROLE, table, "DELETE")
    )
