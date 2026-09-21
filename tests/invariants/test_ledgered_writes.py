"""Writing a budget version or a pack assignment leaves a ledger entry, read off the migrations.

The owner's console architecture (§3.4, rows I3, B3 and C2) says budget versions and capability
packs "have audit triggers like every other console write", and `brain.tables.budget` said the
budget's did not exist. A test over one trigger's SQL would pass for as long as that one migration
stood, and go on passing after a later migration dropped the trigger or granted the application a
write the trigger does not fire on. So this reads the schema the migrations leave behind, through
`brain.ops.application_privileges.migrations_catalogue`, which renders every migration offline in
order: **for every write the application role may make to either table, a trigger that fires on it
appends to `obs.audit_entry`**.

Task ids: M24.3.7
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from brain.ops.application_privileges import (
    APPLICATION_ROLE,
    Catalogue,
    migrations_catalogue,
)

#: The tables whose every write the owner asked to be ledgered, by M24.3.7's sentence.
LEDGERED: Final[tuple[str, ...]] = ("ops.budget_version", "gate.capability_pack_assignment")

#: The writes that could change what either table says.
WRITES: Final[tuple[str, ...]] = ("INSERT", "UPDATE", "DELETE")

#: An append to the ledger, however a trigger body spells it: `0003` merges, a copy may insert.
APPENDS: Final = re.compile(r"\b(?:INSERT|MERGE)\s+INTO\s+obs\.audit_entry\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return migrations_catalogue()


def appending_triggers(catalogue: Catalogue, table: str, write: str) -> list[str]:
    return [body for body in catalogue.fired_by(table, write) if APPENDS.search(body)]


def test_every_write_the_application_may_make_to_a_budget_or_a_pack_assignment_is_ledgered(
    catalogue: Catalogue,
) -> None:
    """**The invariant M24.3.7 names.** Delete this and a budget ceiling can be raised, or a pack
    handed to somebody, with the ledger saying nothing, which is the gap `brain.tables.budget`
    recorded until `0098`, and a later migration granting the application an UPDATE the trigger
    does not fire on would reopen it with every other test green."""
    unledgered = [
        (table, write)
        for table in LEDGERED
        for write in WRITES
        if catalogue.holds(APPLICATION_ROLE, table, write)
        and not appending_triggers(catalogue, table, write)
    ]
    assert unledgered == []


def test_the_application_can_write_both_tables_so_the_invariant_is_not_vacuous(
    catalogue: Catalogue,
) -> None:
    """The positive sibling. The invariant above is satisfied by a schema in which the application
    may write neither table, so this holds that it may insert into both, and that the insert is
    exactly the write a ledgering trigger fires on. Delete this and the invariant passes on the day
    a migration renames a table and the loop above checks two names nothing writes."""
    for table in LEDGERED:
        assert table in catalogue.tables, table
        assert catalogue.holds(APPLICATION_ROLE, table, "INSERT"), table
        assert appending_triggers(catalogue, table, "INSERT"), table


def test_a_trigger_that_does_not_append_is_not_mistaken_for_one_that_does(
    catalogue: Catalogue,
) -> None:
    """`ops.budget_version` also carries `0031`'s ordering and refusal triggers, which fire on the
    same writes and append nothing. Delete this and the pattern can be loosened until any trigger
    body counts, and the invariant is then satisfied by the triggers that refuse an amendment."""
    bodies = catalogue.fired_by("ops.budget_version", "INSERT")
    assert len(bodies) > len(appending_triggers(catalogue, "ops.budget_version", "INSERT"))
