"""The install checks for what an agent's Profile offers beside its tools, passing on PostgreSQL at
head, leaving nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.11.12, M27.11.13, M27.11.14, M27.15.32
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_agent_profile"
OFFERS = "an_agent_is_offered_to_more_than_its_level_from_its_profile"
LEARNING = "an_agents_learning_is_paused_and_resumed_from_its_profile"
COMPUTER = "computer_use_is_not_offered_until_a_desktop_runner_exists"
SKILLS = "a_pinned_skill_no_run_could_use_is_said_so_on_the_profile"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        OFFERS: ("M27.11.13",),
        LEARNING: ("M27.11.14",),
        COMPUTER: ("M27.15.32",),
        SKILLS: ("M27.11.12",),
    }
    assert checks_in(MODULE) == [OFFERS, LEARNING, COMPUTER, SKILLS]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_agent_profile") as url:
        yield url


def _outcome(url: str, name: str) -> tuple[str, str]:
    return run_module(url, MODULE)[name]


def _failed(url: str, name: str) -> str:
    outcome, reason = _outcome(url, name)
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** Each passes and leaves no agent, person, grant, offer
    or pause behind. Delete this and a check that commits, or one that cannot pass on a real
    schema, reaches the owner's server first, and the console audit's row proof for the Profile's
    writes cites a test that does not exist."""
    before = counts(install)
    assert run_module(install, MODULE) == {
        OFFERS: (PASSED, ""),
        LEARNING: (PASSED, ""),
        COMPUTER: (PASSED, ""),
        SKILLS: (PASSED, ""),
    }
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_offer_accepted_with_the_switch_off_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A route that no longer asks the switch or the level. Delete this and M27.11.13 closes on an
    add route that widens an agent's audience on an install where nobody has answered the owner's
    question about it, or on a personal agent."""
    from brain import agent_audience_routes as routes

    monkeypatch.setattr(routes, "why_not_changeable", lambda record, *, switched_on: None)
    assert "while the switch was off" in _failed(install, OFFERS)


@pytest.mark.needs_db
def test_a_personal_agent_that_takes_an_offer_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A route that asks the switch and not the level. Delete this and a personal agent can be
    offered to a colleague through the Profile, which M39.10.3 exists to stop."""
    from brain import agent_audience_routes as routes
    from brain.knowledge.visibility import Visibility

    real = routes.why_not_changeable

    def only_the_switch(record: Any, *, switched_on: bool) -> str | None:
        if record.audience.level is Visibility.PERSONAL:
            return None
        return real(record, switched_on=switched_on)

    monkeypatch.setattr(routes, "why_not_changeable", only_the_switch)
    assert "personal agent was offered" in _failed(install, OFFERS)


@pytest.mark.needs_db
def test_a_member_who_is_told_who_an_agent_is_offered_to_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card that tells everybody who answers for the agent. Delete this and a colleague is told
    which people were offered a department's agent, and an agent offered to many reads differently
    from one offered to nobody."""
    from brain import agent_audience_routes as routes

    monkeypatch.setattr(routes, "answers_for", lambda record, asked: True)
    reason = _failed(install, OFFERS)
    assert (
        "was told who it is offered to" in reason or "read an offered agent differently" in reason
    )


@pytest.mark.needs_db
def test_an_offer_that_is_not_kept_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store that answers and writes nothing. Delete this and the card shows an offer made while
    the roster goes on hiding the agent from the people it was offered to."""
    from brain import agent_audience_routes as routes

    async def nothing(self: Any, **_: Any) -> None:
        return None

    monkeypatch.setattr(routes.StoredAudienceExtras, "add", nothing)
    assert "was not found by its members" in _failed(install, OFFERS)


@pytest.mark.needs_db
def test_a_pause_that_is_not_kept_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A switch that answers and writes nothing. Delete this and M27.11.14 closes on a Profile
    switch that reads paused and leaves every memory forming."""
    from brain.ops.learning_signal_store import StoredLearningPauses

    async def nothing(self: Any, **_: Any) -> None:
        return None

    monkeypatch.setattr(StoredLearningPauses, "set", nothing)
    assert "was not paused" in _failed(install, LEARNING)


@pytest.mark.needs_db
def test_an_agent_whose_steward_may_switch_its_learning_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A route that stops asking the lifecycle authority. Delete this and the agent's steward, who
    answers for it and does not decide what it keeps, switches its learning."""
    from brain import agent_lifecycle_routes as routes

    async def anybody(request: Any, agent_id: str, asked: Any, capability: Any) -> tuple[Any, Any]:
        store = routes.lifecycles_of(request)
        found = await store.agent(agent_id)
        if found is None:
            raise routes._no_agent_here(asked, "agent")
        return store, found

    monkeypatch.setattr(routes, "_actionable", anybody)
    assert "steward, who holds no authority, switched" in _failed(install, LEARNING)


@pytest.mark.needs_db
def test_computer_use_offered_with_no_runner_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A detail that offers computer use. Delete this and M27.15.32 closes on a Profile offering
    what nothing in the product can run."""
    from brain import agent_capability_routes as routes
    from brain.console.agent_behaviour import ComputerUse

    monkeypatch.setattr(
        routes, "computer_use", lambda: ComputerUse(offered=True, sentence="Use it.")
    )
    assert "offered while no desktop runner" in _failed(install, COMPUTER)


@pytest.mark.needs_db
def test_a_product_with_a_desktop_runner_is_not_run_rather_than_passed(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The day the runner module exists the check says a person has to ask again, and says it as not
    run. Delete this and the check goes on passing after the product has what it denies having."""
    import importlib.util

    # Held before it is replaced: the replacement answers for the runner's name and for no other.
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: real("json") if name.endswith("desktop") else real(name, *a, **k),
    )
    outcome, reason = _outcome(install, COMPUTER)
    assert outcome == NOT_RUN and "isolated desktop runner" in reason


@pytest.mark.needs_db
def test_a_skill_the_library_does_not_hold_that_is_not_said_so_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A standing that stops nothing. Delete this and M27.11.12 closes on a Profile that lists an
    unbacked skill as one a run uses."""
    from brain import agent_capability_routes as routes
    from brain.console.agent_behaviour import SkillStanding

    monkeypatch.setattr(routes, "skill_standing", lambda **_: SkillStanding(None))
    assert "was not said to change no run" in _failed(install, SKILLS)


@pytest.mark.needs_db
def test_an_approved_skill_that_is_said_to_change_no_run_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A standing that stops everything. Delete this and the sentence is satisfied by one that is
    said of every skill, which is a Profile telling people their skills do nothing."""
    from brain import agent_capability_routes as routes
    from brain.console.agent_behaviour import SkillStanding

    monkeypatch.setattr(routes, "skill_standing", lambda **_: SkillStanding("It is stopped."))
    assert "approved assigned skill was said" in _failed(install, SKILLS)
