"""The agent-configuration install checks: registered, passing on PostgreSQL, able to fail.

The pure half holds the module to its leaves and its place in the run. The database half builds
PostgreSQL to head once, runs the checks as the worker would, and then breaks the product one part
at a time and shows each check failing with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M39.2.4.4
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

MODULE = "brain.ops.acceptance_checks_agent_config"
GROUP = "an_agent_is_installed_into_a_group_chat_and_taken_out_again"
FAILING = "a_failing_automation_is_paused_and_its_steward_is_told"

WRITTEN = (
    "ops.channel_room",
    "agent.group_install",
    "agent.agent",
    "agent.template_instance",
    "agent.template_version",
    "auth.principal",
    "gate.capability_grant",
    "gate.department",
    "obs.audit_entry",
)


def test_the_module_declares_each_check_naming_the_leaf_it_proves() -> None:
    """Each check names its own leaf and no other. Delete this and a check can lose its leaf with
    the Install page showing the same row, or close a leaf it does not prove."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        GROUP: ("M39.2.4.4",),
        FAILING: ("M39.6.2.3",),
    }
    assert checks_in(MODULE) == [GROUP, FAILING]
    from brain.ops import acceptance_checks_agent_config as module

    assert 880 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_agent_config") as url:
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
def test_the_group_install_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and nothing it wrote is left. Delete this and
    a check that can never pass on a real schema, or one that commits, reaches the owner's
    server."""
    before = held(install)
    assert run_mine(install) == {GROUP: (PASSED, ""), FAILING: (PASSED, "")}
    assert held(install) == before


@pytest.mark.needs_db
def test_an_install_that_accepts_a_surface_with_no_groups_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule asking whether a surface declares group installation answering yes for every
    surface. Delete this and the check closes M39.2.4.4 on an install installing an agent into a
    surface that has no group to install it into."""
    from brain.console import agent_tabs

    monkeypatch.setattr(agent_tabs, "group_installable", lambda capabilities: True)
    outcome, reason = run_mine(install)[GROUP]
    assert outcome == FAILED
    assert "surface with no groups" in reason


@pytest.mark.needs_db
def test_a_store_that_installs_nothing_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store answering that no room could take the agent. Delete this and the check closes
    M39.2.4.4 on an install whose group install never lands."""
    from brain.ops.group_install_store import StoredGroupInstalls

    async def nothing(self: Any, **_: Any) -> None:
        return None

    monkeypatch.setattr(StoredGroupInstalls, "install", nothing)
    outcome, reason = run_mine(install)[GROUP]
    assert outcome == FAILED
    assert "could not install it" in reason


def test_the_failing_automation_check_names_its_leaf_and_the_leaf_stays_held() -> None:
    """The check names M39.6.2.3 and the leaf is in the proof sweep's holds, because the failure it
    pauses on is handed to the decision rather than produced by a run. Delete this and the leaf
    closes on a pass over a failure nobody's automation made."""
    import json

    from tests.unit.test_acceptance import ROOT

    held_leaves = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text(encoding="utf-8"))
    assert "M39.6.2.3" in held_leaves["held"]


@pytest.mark.needs_db
def test_the_failing_automation_check_passes_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** The pause decision, its record and the steward's read
    pass and nothing is left. Delete this and a check that can never pass on a real schema reaches
    the owner's server."""
    from tests.fixtures.scratch_postgres import sql

    tables = ("agent.automation", "agent.automation_schedule", "agent.agent")
    before = [sql(install, f"SELECT count(*) FROM {one}") for one in tables]  # noqa: S608
    assert run_mine(install)[FAILING] == (PASSED, "")
    assert [sql(install, f"SELECT count(*) FROM {one}") for one in tables] == before  # noqa: S608


@pytest.mark.needs_db
def test_a_pause_that_does_not_name_the_agents_steward_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure pause building its notice for somebody else. Delete this and the check closes
    M39.6.2.3 on a pause that tells the wrong person, or nobody."""
    from brain.console import agent_automations

    original = agent_automations.failure_pause

    def for_someone_else(automation: Any, **kwargs: Any) -> Any:
        return original(automation, **{**kwargs, "owner_id": "somebody_else"})

    monkeypatch.setattr("brain.ops.automation_run.failure_pause", for_someone_else)
    outcome, reason = run_mine(install)[FAILING]
    assert outcome == FAILED
    assert "not addressed to the agent's steward" in reason


@pytest.mark.needs_db
def test_a_threshold_of_none_fails_the_check(install: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure pause never pausing. Delete this and the check closes M39.6.2.3 on an install
    whose failing automations keep running."""
    monkeypatch.setattr("brain.ops.automation_run.failure_pause", lambda automation, **_: None)
    outcome, reason = run_mine(install)[FAILING]
    assert outcome == FAILED
    assert "did not pause" in reason
