"""The template withdrawal check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would. Then it is run
against the product broken where it proves: a withdrawal that hides nothing, one a department's
installer may make, an upgrade offered for a withdrawn version, and an import that takes the id of
a template this release ships.

Task ids: M27.15.35
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_template_withdrawal"
NAME = "a_withdrawn_version_is_not_offered_and_agents_stay_pinned"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def test_the_template_withdrawal_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M27.15.35",)


@pytest.mark.needs_db
def test_on_a_real_database_a_version_is_withdrawn_and_returned_and_nothing_is_left() -> None:
    """**The check as the worker runs it.** Delete this and a withdrawal that is accepted and hides
    nothing, or one that moves an installed agent, reaches an install with nothing saying so."""
    with at_head("brain_acceptance_template_withdrawal") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _withdrawing_hides_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_routes as routes

    async def nothing_is_withdrawn(_session: Any) -> Any:
        return frozenset(), frozenset()

    monkeypatch.setattr(routes, "withheld_in", nothing_is_withdrawn)


def _a_departments_installer_may_withdraw(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.template_withdrawal_routes as routes

    monkeypatch.setattr(routes, "may_manage", lambda _asked: True)


def _an_upgrade_is_offered_for_a_withdrawn_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_upgrade_routes as routes

    monkeypatch.setattr(routes, "withdrawn_keys", lambda _newest: frozenset())


def _a_shipped_id_may_be_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.template_withdrawal_routes as routes

    monkeypatch.setattr(routes, "may_take_the_name", lambda _manifest, _held: True)


BREAKS: dict[str, tuple[Any, str]] = {
    "withdrawing_hides_nothing": (_withdrawing_hides_nothing, "STILL_OFFERED"),
    "a_departments_installer_may_withdraw": (
        _a_departments_installer_may_withdraw,
        "WITHDRAWN_BY_A_DEPARTMENTS_INSTALLER",
    ),
    "an_upgrade_is_offered": (
        _an_upgrade_is_offered_for_a_withdrawn_version,
        "OFFERED_TO_AN_UPGRADE",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_template_withdrawal_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found, in its own words. Delete this and the check
    can pass over a withdrawal that hides nothing, an installer who may withdraw for the company,
    or an upgrade offered for a version nobody may install."""
    import brain.ops.acceptance_checks_template_withdrawal as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_template_withdrawal_{broken}"[:60]) as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
