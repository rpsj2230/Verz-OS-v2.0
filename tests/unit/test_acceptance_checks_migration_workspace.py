"""The install checks for running a migration from another system, each passing on PostgreSQL at
head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M37.1.1.1, M37.1.1.2, M37.1.1.3, M37.1.3.2, M37.1.3.3, M37.1.4.1, M37.1.4.2, M37.1.4.3,
M37.1.4.4, M37.7.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_migration_workspace"
REGISTER = "a_register_is_kept_and_what_is_outstanding_in_it_is_said"
PERIOD = "a_period_keeps_criteria_agreed_first_and_surfaces_disagreements"
CUTOVER = "a_cutover_is_not_complete_while_a_gated_act_is_unrecorded"
WRITTEN = ("ops.migration_record", "ops.setting")


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (REGISTER, ("M37.1.1.1", "M37.1.1.2", "M37.1.1.3")),
        (PERIOD, ("M37.1.3.2", "M37.1.3.3")),
        (CUTOVER, ("M37.1.4.1", "M37.1.4.2", "M37.1.4.3", "M37.1.4.4", "M37.7.5")),
    ]
    assert checks_in(MODULE) == [REGISTER, PERIOD, CUTOVER]


def test_the_gated_acts_the_check_restates_are_the_ones_the_package_gates_on() -> None:
    """Restated so a change fails the check, and compared with the package so a change to the
    package fails here. Delete this and the check can pass over a gate that grew or lost an act."""
    from brain.migration.checklist import CUTOVER_GATED_ACTS
    from brain.ops.acceptance_checks_migration_workspace import THE_GATED_ACTS

    assert sorted(THE_GATED_ACTS) == sorted(CUTOVER_GATED_ACTS)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_migration_workspace") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN})  # noqa: S608
    return both


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass and no version or switch is left behind.
    Delete this and a check that can never pass on a real schema, or that leaves rows in a table
    nothing can delete from, reaches the owner's install."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_register_that_names_nothing_outstanding_fails_the_register_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finding for an item nothing decided removed. Delete this and M37.1.1.2 closes on a
    register that lets a cutover decide an item by omission."""
    from brain.migration import inventory
    from brain.ops import acceptance_checks_migration_workspace as module

    monkeypatch.setattr(inventory, "undecided", lambda *_a, **_k: ())
    assert _failed(install, REGISTER) == module.THE_UNDECIDED_ITEM_WAS_NOT_NAMED


@pytest.mark.needs_db
def test_a_register_that_is_never_agreed_fails_the_register_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unmapped-permission finding removed. Delete this and M37.1.1.3 closes on a register that
    maps a permission by assumption on the day of the cutover."""
    from brain.migration import inventory
    from brain.ops import acceptance_checks_migration_workspace as module

    monkeypatch.setattr(inventory, "unmapped", lambda *_a, **_k: ())
    assert _failed(install, REGISTER) == module.THE_UNMAPPED_PERMISSION_WAS_NOT_NAMED


@pytest.mark.needs_db
def test_a_period_that_accepts_a_late_threshold_fails_the_period_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal of a threshold agreed after the period began removed. Delete this and M37.1.3.3
    closes on criteria that describe the result they were meant to judge."""
    from brain.migration import parallel
    from brain.ops import acceptance_checks_migration_workspace as module

    monkeypatch.setattr(parallel.Period, "__post_init__", lambda _self: None)
    assert _failed(install, PERIOD) == module.A_LATE_CRITERION_WAS_SAVED


@pytest.mark.needs_db
def test_a_period_that_never_surfaces_a_disagreement_fails_the_period_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disagreements read as none. Delete this and M37.1.3.2 closes on a log that hides what
    the two systems answered differently."""
    from brain.migration import parallel
    from brain.ops import acceptance_checks_migration_workspace as module

    monkeypatch.setattr(parallel, "disagreements", lambda _log: ())
    assert _failed(install, PERIOD) == module.A_DISAGREEMENT_WAS_NOT_SURFACED


@pytest.mark.needs_db
def test_a_cutover_gate_that_lets_a_completion_through_fails_the_cutover_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gated acts read as all recorded. Delete this and M37.7.5 closes on a cutover that can be
    reported complete with a grant nobody withdrew."""
    from brain.migration import decommission
    from brain.ops import acceptance_checks_migration_workspace as module

    monkeypatch.setattr(decommission, "security_acts_outstanding", lambda _record: ())
    assert _failed(install, CUTOVER) == module.A_COMPLETION_WAS_ALLOWED


@pytest.mark.needs_db
def test_a_completion_that_survives_an_edit_fails_the_cutover_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A save that keeps the earlier completion. Delete this and M37.1.4.1 closes on a cutover that
    was changed after it was reported and still reads as reported."""
    from brain import migration_routes
    from brain.ops import acceptance_checks_migration_workspace as module
    from brain.ops import migration_record_store

    real = migration_record_store.save

    async def keeping(session: Any, kind: Any, body: dict[str, Any], *, by: str) -> None:
        previous = await migration_record_store.newest(session, kind)
        carried = {} if previous is None else previous.body.get("reported_complete")
        if carried and "reported_complete" not in body:
            body = {**body, "reported_complete": carried}
        await real(session, kind, body, by=by)

    monkeypatch.setattr(migration_routes.migration_record_store, "save", keeping)
    assert _failed(install, CUTOVER) == module.A_COMPLETION_SURVIVED_AN_EDIT
