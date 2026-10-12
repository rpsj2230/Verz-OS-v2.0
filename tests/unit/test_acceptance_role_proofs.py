"""The elevation-chain and permission-sync install checks: registered, passing, able to fail.

The pure half holds the module to its leaves and its place in the run. The database half builds
PostgreSQL to head once, runs the checks as the worker would, and then breaks the product one part
at a time (the trigger that writes the second chain; the rule that says what a source's
declarations support) and shows each check failing with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M33.7.1.3, M33.5.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_role_proofs"
CHAIN = "an_elevation_is_written_to_its_own_chain_beside_the_main_ledger"
CLAIM = "every_connectors_permission_sync_claim_is_one_it_can_support"

#: The two tables the chain check writes to inside its rolled-back transaction.
WRITTEN = (
    "obs.elevation_entry",
    "obs.audit_entry",
    "gate.elevation_request",
    "gate.break_glass_notice",
    "auth.principal",
    "gate.capability_grant",
)


def test_the_module_declares_each_check_naming_the_leaf_it_proves() -> None:
    """Each check names its own leaf and no other. Delete this and a check can lose its leaf with
    the Install page showing the same row, or start closing a leaf it does not prove."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        CHAIN: ("M33.7.1.3",),
        CLAIM: ("M33.5.1.3",),
    }
    assert checks_in(MODULE) == [CHAIN, CLAIM]
    from brain.ops import acceptance_checks_role_proofs as module

    assert 880 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_role_proofs") as url:
        yield url


def run_mine(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def held(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** Both pass, and nothing either wrote is left in a
    table. Delete this and a check that can never pass on a real schema, or one that commits,
    reaches the owner's server."""
    before = held(install)
    assert run_mine(install) == {CHAIN: (PASSED, ""), CLAIM: (PASSED, "")}
    assert held(install) == before


@pytest.mark.needs_db
def test_an_install_whose_approval_writes_no_second_chain_fails_the_chain_check(
    install: str,
) -> None:
    """The trigger that appends an approval to the elevation chain switched off. Delete this and
    the check closes M33.7.1.3 on an install whose second chain never moves, which is the one
    thing the separation is for."""
    from tests.fixtures.scratch_postgres import sql

    sql(install, "ALTER TABLE gate.elevation_request DISABLE TRIGGER elevation_request_is_chained")
    try:
        outcome, reason = run_mine(install)[CHAIN]
    finally:
        sql(
            install,
            "ALTER TABLE gate.elevation_request ENABLE TRIGGER elevation_request_is_chained",
        )
    assert outcome == FAILED
    assert "was not written to the elevation chain once" in reason


def _nothing_is_supported(*_: Any) -> frozenset[Any]:
    return frozenset()


@pytest.mark.needs_db
def test_a_source_claiming_what_its_declarations_cannot_support_fails_the_claim_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule saying what a source's tools and projections support answering with nothing, so
    every claim (even the claim of none) is one the declarations cannot back. Delete this and the
    check closes M33.5.1.3 whatever the rule says, which would let a console report a source as
    permission-aware on its say-so."""
    from brain.ops import acceptance_checks_role_proofs as module

    monkeypatch.setattr(module, "implementable_permission_sync", _nothing_is_supported)
    outcome, reason = run_mine(install)[CLAIM]
    assert outcome == FAILED
    assert "cannot support" in reason


@pytest.mark.needs_db
def test_an_elevation_chain_the_application_may_edit_fails_the_chain_check(install: str) -> None:
    """The application's role given the right to update the chain and the trigger that refuses an
    amendment switched off, which is the two walls the product builds. Delete this and the check
    closes M33.7.1.3 on a second chain that is a name and not an immutable record."""
    from tests.fixtures.scratch_postgres import sql

    table = "obs.elevation_entry"
    sql(install, f"GRANT UPDATE ON {table} TO brain_app")
    sql(install, f"ALTER TABLE {table} DISABLE TRIGGER elevation_entry_refuses_amendment")
    try:
        outcome, reason = run_mine(install)[CHAIN]
    finally:
        sql(install, f"ALTER TABLE {table} ENABLE TRIGGER elevation_entry_refuses_amendment")
        sql(install, f"REVOKE UPDATE ON {table} FROM brain_app")
    assert outcome == FAILED
    assert "could be changed or removed" in reason
