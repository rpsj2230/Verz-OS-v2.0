"""Every table the application's sessions read or write is granted to the role they run as.

The comparison is `brain.ops.application_privileges`: the migrations rendered offline on one side,
every use of a table in a module the application's sessions reach on the other. It is here, in
the invariants that run before every push, because the failure it prevents is silent until a
person opens a screen: `ops.control_run` shipped with policies and no grant, and four console
screens on a staging install answered every request with a 500.

**What it cannot see is stated, not implied.** See
`brain.ops.application_privileges.WHAT_THE_SOURCE_DOES_NOT_SAY`. Two tests below hold the reading
to a floor and to named shapes, so a change that quietly stopped the reader seeing anything fails
here rather than passing over an empty list.

Task ids: M27.9.7
"""

from __future__ import annotations

from collections import Counter

import pytest

from brain.ops.application_privileges import (
    NO_GRANT,
    USES_EXPLAINED,
    Catalogue,
    Mismatch,
    Use,
    migrations_catalogue,
    mismatches,
    reachable,
    stale,
    unexplained,
    uses,
)

#: The screens the staging install found failing, by the module whose statement failed.
FOUND_ON_STAGING: frozenset[str] = frozenset(
    {"brain.error_routes", "brain.jobs_routes", "brain.operate_routes", "brain.report_routes"}
)


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return migrations_catalogue()


@pytest.fixture(scope="module")
def found(catalogue: Catalogue) -> list[Use]:
    return uses(known=catalogue.tables)


@pytest.fixture(scope="module")
def reported(catalogue: Catalogue, found: list[Use]) -> list[Mismatch]:
    return mismatches(catalogue, found)


def test_every_table_the_applications_sessions_use_is_granted_and_admitted_to_its_role(
    reported: list[Mismatch],
) -> None:
    """No use the migrations do not serve, beyond the ones `USES_EXPLAINED` gives a reason for.

    Delete this and a route can read a table no migration grants `brain_app`, which passes every
    test built on a stub session and fails on the first install with `permission denied`."""
    assert [one.sentence() for one in unexplained(reported)] == []


def test_every_explained_use_is_still_one_the_comparison_reports(reported: list[Mismatch]) -> None:
    """An entry nothing matches any more is removed, so the list of reasons cannot outlive them.

    Delete this and an explanation written for a worker's write stays in place after the write
    moves onto the application's sessions, where it would excuse a real failure."""
    assert stale(reported) == []
    assert all(reason.strip() for reason in USES_EXPLAINED.values())


def test_the_comparison_finds_what_the_staging_install_found_on_the_migrations_before_0069(
    found: list[Use],
) -> None:
    """Rendered up to `0068`, the head before the grant, the four screens' reads of
    `ops.control_run` are reported as having no grant, and on the migrations as they are now they
    are not.

    Delete this and the comparison can stop detecting the one failure it was written for, with the
    invariant above green because it compares nothing."""
    before = migrations_catalogue(revision="0068")
    reported = {
        one.use.module
        for one in mismatches(before, found)
        if (one.use.table, one.use.privilege, one.missing)
        == ("ops.control_run", "SELECT", NO_GRANT)
    }
    assert reported >= FOUND_ON_STAGING
    now = migrations_catalogue()
    assert now.holds("brain_app", "ops.control_run", "SELECT")
    assert not now.holds("brain_app", "ops.control_run", "INSERT")


def test_the_reading_sees_the_shapes_the_application_writes_its_statements_in(
    found: list[Use],
) -> None:
    """A floor on what is read, and one named use for each shape the reader has to recognise.

    The floors are floors, measured at 933 uses of 60 tables on 2026-09-17 and set well below, so
    this fails when the reader stops seeing and not when a route is added. The named uses are an
    upsert built in two steps, a Core table rather than a model, a row lock, a SQL string, and the
    root the worker hands application sessions to.

    Delete this and a change that makes the reader see nothing, an import that stops registering
    the models say, leaves the invariant above green over an empty list."""
    assert len(found) > 600
    assert len({one.table for one in found}) > 45
    seen = Counter((one.module, one.table, one.privilege) for one in found)
    for expected in (
        ("brain.ops.setting_store", "ops.setting", "UPDATE"),
        ("brain.knowledge.chunk_store", "know.chunk", "INSERT"),
        ("brain.gate.suspension_store", "gate.suspension", "UPDATE"),
        ("brain.identity.administration_reconciliation", "obs.audit_entry", "SELECT"),
        ("brain.jobs_routes", "ops.control_run", "SELECT"),
    ):
        assert seen[expected], expected
    reach = reachable()
    assert {"brain.app", "brain.knowledge.chunk_store", "brain.estate_routes"} <= reach
