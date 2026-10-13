"""The install checks for the plugin registry, each passing on PostgreSQL at head and failing with
the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M29.1.2, M29.1.3, M29.1.4, M29.1.5, M29.1.7, M29.1.12, M29.2.1, M29.2.2, M29.2.3, M29.2.6
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

MODULE = "brain.ops.acceptance_checks_plugin_registry"
MOVED = "a_plugin_is_recorded_and_moved_through_its_states"
INTERFACES = "plugin_interfaces_are_listed_with_their_contracts"
CONTRACT = "a_plugin_gets_the_callers_own_reach_and_nothing_unredacted"
WRITTEN = ("ops.plugin_install", "ops.plugin_version", "ops.setting")


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (MOVED, ("M29.2.1", "M29.2.2", "M29.2.3")),
        (
            INTERFACES,
            ("M29.1.2", "M29.1.3", "M29.1.4", "M29.1.5", "M29.1.7", "M29.1.12"),
        ),
        (CONTRACT, ("M29.2.6",)),
    ]
    assert checks_in(MODULE) == [MOVED, INTERFACES, CONTRACT]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_plugin_registry") as url:
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
    """**The module as the worker runs it.** All three pass and no plugin, version or switch is
    left. Delete this and a check that can never pass on a real schema, or that leaves a plugin
    or a switched feature on the owner's install, reaches it."""
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
def test_a_registry_that_ignores_its_switch_fails_the_lifecycle_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch read as always on. Delete this and M29.2.3 closes on a feature that ships on."""
    from brain import plugin_routes
    from brain.ops import acceptance_checks_plugin_registry as module

    async def always(_session: Any, _feature: Any) -> bool:
        return True

    monkeypatch.setattr(plugin_routes, "is_on", always)
    assert _failed(install, MOVED) == module.WRITES_ALLOWED_WITH_THE_SWITCH_OFF


@pytest.mark.needs_db
def test_a_registry_that_enables_on_arrival_fails_the_lifecycle_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lifecycle whose install returns an enabled record, which the registry refuses to store.
    Delete this and a plugin can arrive switched on with nothing in a run noticing, which is the
    one thing the lifecycle's shape exists to prevent."""
    from brain import plugin_routes
    from brain.ops import acceptance_checks_plugin_registry as module
    from brain.plugins import lifecycle

    real = lifecycle.install

    def enabled(*args: Any, **kwargs: Any) -> Any:
        return lifecycle.enable(real(*args, **kwargs), at=kwargs["at"])

    monkeypatch.setattr(plugin_routes, "install", enabled)
    assert _failed(install, MOVED) == module.A_MANIFEST_WAS_NOT_RECORDED


@pytest.mark.needs_db
def test_a_point_that_loses_its_contract_fails_the_interfaces_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A register naming a contract no module defines. Delete this and M29.1.2 to M29.1.12 close
    on interfaces that describe nothing."""
    import dataclasses

    from brain.ops import acceptance_checks_plugin_registry as module
    from brain.plugins import points

    broken = tuple(
        dataclasses.replace(one, contract="brain.connectors.contract:NoSuchThing")
        if one.name == "connector"
        else one
        for one in points.POINTS
    )
    import brain.plugin_routes as routes

    monkeypatch.setattr(routes, "POINTS", broken)
    assert _failed(install, INTERFACES) == module.AN_INTERFACE_HAS_NO_CONTRACT


@pytest.mark.needs_db
def test_a_plan_that_widens_the_reach_fails_the_contract_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan handing the plugin a wider reach than the caller's. Delete this and M29.2.6 closes
    on a contract that can be widened."""
    from brain import plugin_routes
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.ops import acceptance_checks_plugin_registry as module
    from brain.plugins import contract

    real = contract.plan_run

    def wider(manifest: Any, *, caller: EntitlementSet, now: Any) -> Any:
        run = real(manifest, caller=caller, now=now)
        extra = Grant(capability=Capability(value="read:payroll.total"), scope=Scope.unrestricted())
        widened = EntitlementSet(principal_id=caller.principal_id, grants=(*caller.grants, extra))
        return contract.PluginRun(plugin_id=run.plugin_id, point=run.point, reach=widened)

    monkeypatch.setattr(plugin_routes, "plan_run", wider)
    assert _failed(install, CONTRACT) == module.THE_REACH_WAS_NOT_THE_CALLERS


@pytest.mark.needs_db
def test_a_contract_that_stops_refusing_a_raw_type_fails_the_contract_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unredacted-type refusal removed. Delete this and a plugin that would be handed a value
    the gate has not walked is recorded."""
    from brain import plugin_routes
    from brain.ops import acceptance_checks_plugin_registry as module

    monkeypatch.setattr(plugin_routes, "assert_cannot_see_unredacted", lambda _manifest: None)
    assert _failed(install, CONTRACT) == module.AN_UNREDACTED_TYPE_WAS_ACCEPTED
