"""The shared start check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, with the model
scripted so no provider is asked. Then it is run against the product broken where it proves: a
shared start that names every tool, one that is shared with the switch off, and one that is built
from every tool of the registry and not those a person is offered.

Task ids: M3.7.2
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

MODULE = "brain.ops.acceptance_checks_shared_start"
NAME = "the_shared_start_names_only_what_everybody_holds"


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


def test_the_shared_start_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M3.7.2",)


@pytest.mark.needs_db
def test_on_a_real_database_the_start_is_shared_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it.** Delete this and the shared start can stop being shared,
    or start naming a tool a person lacks, with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_shared_start") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _names_every_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.ops.shared_start as shared

    def everything(registry: Any) -> frozenset[str]:
        return frozenset(registry.names())

    monkeypatch.setattr(shared, "universal_tools", everything)


def _shared_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.ops.shared_start as shared
    from brain.gate.shared_start import universal_tools

    async def always(sessions: Any, registry: Any) -> frozenset[str]:
        del sessions
        return universal_tools(registry)

    monkeypatch.setattr(shared, "universal_when_on", always)


BREAKS: dict[str, tuple[Any, str]] = {
    "names_every_tool": (_names_every_tool, "NOTHING_WAS_SHARED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_shared_start_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """A universal set holding every tool is found. Delete this and the check can pass over a
    shared start that tells a person of tools they cannot use."""
    import brain.ops.acceptance_checks_shared_start as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_shared_start_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_a_start_shared_while_the_switch_is_off_is_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reader that shares whatever the switch says is found by the first thing the check asks.

    Delete this and a switch nothing reads passes."""
    import brain.ops.acceptance_checks_shared_start as module

    _shared_when_off(monkeypatch)
    with at_head("brain_acceptance_shared_start_off") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, module.SHARED_WITH_THE_SWITCH_OFF)
