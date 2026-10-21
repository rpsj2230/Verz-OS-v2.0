"""The skill reuse check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, with a stand-in
model answering in the process that keeps what it is sent. Then it is run against the product
broken where it proves: the needs rule never refusing, the rule applied with its switch ignored, and
an agent's run handed no pins.

Task ids: M12.3.3, M12.4.10
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_skill_runs import hosted, run_checks  # noqa: F401

MODULE = "brain.ops.acceptance_checks_skill_reuse"
NAME = "a_skill_is_reused_by_two_agents_and_refused_where_unservable"


@contextmanager
def at_head_laddered(name: str) -> Iterator[str]:
    """PostgreSQL at head with the ladder the setup wizard writes, as the model checks run on."""
    from tests.unit.test_acceptance_models import laddered

    with at_head(name) as url:
        laddered(url)
        yield url


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_reuse_check_is_listed_with_the_leaves_it_proves() -> None:
    """Delete this and the check can drop out of the module, or lose a leaf, and the sweep that
    closes tasks from the install's results reads a check that no longer proves what it did."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M12.3.3", "M12.4.10")


@pytest.mark.needs_db
def test_on_a_real_database_one_skill_reaches_two_agents_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it.** Delete this and the reuse of a skill can stop working
    with nothing on the owner's install saying so."""
    with at_head_laddered("brain_acceptance_skill_reuse") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _no_needs_check(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.console.skill_library as library
    from brain.console.skill_library import Missing

    monkeypatch.setattr(library, "missing_for", lambda skill, record, registry: Missing())


def _switch_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.skill_routes as routes

    async def never(session: Any, one: Any) -> bool:
        return False

    monkeypatch.setattr(routes, "is_on", never)


def _always_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.skill_routes as routes

    async def always(session: Any, one: Any) -> bool:
        return True

    monkeypatch.setattr(routes, "is_on", always)


def _no_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    import brain.api_routes as api_routes

    kept = api_routes.agent_run_of

    async def pinless(state: Any, agent: Any, registry: Any, trying: Any = None) -> Any:
        run = await kept(state, agent, registry, trying)
        return None if run is None else dataclasses.replace(run, pins=(), library=())

    monkeypatch.setattr(api_routes, "agent_run_of", pinless)


BREAKS: dict[str, tuple[Any, str]] = {
    "no_needs_check": (_no_needs_check, "NEEDS_NOT_REFUSED"),
    "switch_ignored": (_switch_ignored, "NEEDS_NOT_REFUSED"),
    "always_checked": (_always_checked, "SWITCH_NOT_READ"),
    "no_pins": (_no_pins, "NO_CARD"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_reuse_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each failing with its own sentence: the needs never checked, the switch
    ignored, the rule applied while the switch is off, and a run handed no pins. Delete this and
    the check can pass with the refusal unreachable or the reused skill reaching no run."""
    import brain.ops.acceptance_checks_skill_reuse as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head_laddered(f"brain_acceptance_skill_reuse_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
