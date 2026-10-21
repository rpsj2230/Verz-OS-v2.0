"""The install checks for a coordinating agent, each passing on PostgreSQL at head and failing with
the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M18.1.2, M18.1.4, M18.3.4, M18.3.5, M18.5.1, M18.5.2, M18.5.3, M18.6.2, M18.7.1
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

MODULE = "brain.ops.acceptance_checks_coordination"
CONFIG = "an_agent_is_told_who_it_may_call_and_whether_to_fan_out"
RUN = "a_plan_runs_its_specialists_at_a_narrowed_reach"
WRITTEN = (
    "agent.agent_callee",
    "agent.agent_fanout",
    "ops.coordinated_run",
    "ops.fanout_gate",
)


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (CONFIG, ("M18.5.1", "M18.6.2")),
        (
            RUN,
            ("M18.1.2", "M18.1.4", "M18.3.4", "M18.3.5", "M18.5.2", "M18.5.3", "M18.7.1"),
        ),
    ]
    assert checks_in(MODULE) == [CONFIG, RUN]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_coordination") as url:
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
    """**The module as the worker runs it.** Both pass and no link, grant, run or decision is left.
    Delete this and a check that can never pass on a real schema, or that leaves rows in tables
    nothing can delete from, reaches the owner's install."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_link_that_is_not_written_fails_the_configuration_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's write removed. Delete this and M18.5.1 closes on an allow-list nothing keeps."""
    from brain.agents import coordination_store
    from brain.ops import acceptance_checks_coordination as module

    async def nothing(*_a: Any, **_k: Any) -> bool:
        return True

    monkeypatch.setattr(coordination_store, "add_callee", nothing)
    assert _failed(install, CONFIG) == module.NOT_TOLD_TO_THE_ADMINISTRATOR


@pytest.mark.needs_db
def test_a_fan_out_that_is_always_granted_fails_the_run_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fan-out read as always on. Delete this and M18.6.2 closes on a switch that does nothing."""
    from brain.agents import coordination_store
    from brain.ops import acceptance_checks_coordination as module

    async def always(*_a: Any, **_k: Any) -> bool:
        return True

    monkeypatch.setattr(coordination_store, "fan_out_enabled", always)
    assert _failed(install, RUN) == module.THE_REASON_WAS_NOT_KEPT


@pytest.mark.needs_db
def test_a_reach_that_is_not_narrowed_fails_the_run_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fold replaced by the asker's own reach. Delete this and M18.5.2 closes on specialists
    that read what their coordinator was there to take away."""
    from brain.ops import acceptance_checks_coordination as module
    from brain.orchestration import coordinator

    monkeypatch.setattr(coordinator, "chain_reach", lambda caller, _hops: caller)
    assert _failed(install, RUN) == module.A_CHILD_REACHED_TOO_MUCH


@pytest.mark.needs_db
def test_a_run_that_is_not_kept_fails_the_run_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run's write removed. Delete this and M18.6.2 closes on a reason nothing keeps."""
    from brain.ops import acceptance_checks_coordination as module
    from brain.ops import coordinated_run_store

    async def nothing(*_a: Any, **_k: Any) -> bool:
        return True

    monkeypatch.setattr(coordinated_run_store, "keep", nothing)
    assert _failed(install, RUN) == module.THE_REASON_WAS_NOT_KEPT
