"""The install checks for an agent's Profile and its whole life, passing on PostgreSQL at head,
leaving nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.11.15, M27.11.6, M27.15.29
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_agents"
PROFILE = "an_agents_profile_says_what_the_reference_page_does_not"
LIFE = "an_agent_moves_through_its_life_and_the_ledger_filters_by_it"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        PROFILE: ("M27.11.15",),
        LIFE: ("M27.11.6", "M27.15.29"),
    }
    assert checks_in(MODULE) == [PROFILE, LIFE]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_agents") as url:
        yield url


def _failed(url: str, name: str) -> str:
    outcome, reason = run_module(url, MODULE)[name]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** Each passes and leaves no agent, person, grant or
    ledger entry. Delete this and a check that commits, or one that cannot pass on a real schema,
    reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {PROFILE: (PASSED, ""), LIFE: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_agent_that_cannot_be_switched_off_fails_both_checks(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch-off press changing nothing. Delete this and M27.11.15 and M27.11.6 close on a
    page whose Disable button does nothing, which is what a regression in the domain move is."""
    from brain import agent_lifecycle_routes as routes

    monkeypatch.setattr(routes, "disable", lambda before, *, now: before)
    assert "switched off" in _failed(install, PROFILE)
    assert "switched off" in _failed(install, LIFE)


@pytest.mark.needs_db
def test_an_agent_that_cannot_be_retired_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retire press changing nothing. Delete this and M27.11.6 closes on an archive route that
    leaves an agent answering, the one move nothing undoes."""
    from brain import agent_lifecycle_routes as routes

    monkeypatch.setattr(routes, "archive", lambda before, *, now: before)
    assert "was not retired" in _failed(install, LIFE)


@pytest.mark.needs_db
def test_a_hand_over_to_a_steward_who_is_not_there_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transfer route that takes any name. Delete this and an agent can be handed to nobody
    and M27.11.6 still closes."""
    from brain import agent_lifecycle_routes as routes

    real = routes.StoredAgentLifecycles.live_principal

    async def anybody(self: routes.StoredAgentLifecycles, principal_id: str) -> object:
        return await real(self, principal_id.removesuffix(".nobody"))

    monkeypatch.setattr(routes.StoredAgentLifecycles, "live_principal", anybody)
    assert "does not exist" in _failed(install, LIFE)
