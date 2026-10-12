"""The install checks for an agent's own run, each passing on PostgreSQL at head and each failing
with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes and leaves nothing. Then each is shown failing: the bounds never reached, a run nobody
records, a result steering a model that is not counted, a grant the run never looks at again, and a
channel the agent answers on whether or not it was switched on.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M13.7.2, M13.8.2, M13.7.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_runtime"
BOUNDS = "an_agent_run_stops_at_the_bound_it_reached_and_says_which"
LAPSE = "a_run_is_judged_again_at_its_next_tool_call"
CHANNELS = "an_agent_answers_only_where_it_was_switched_on"


def test_the_module_declares_a_check_for_each_leaf_it_proves() -> None:
    """Three checks, each closing its own leaf. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (BOUNDS, ("M13.7.2",)),
        (LAPSE, ("M13.8.2",)),
        (CHANNELS, ("M13.7.4",)),
    ]
    assert checks_in(MODULE) == [BOUNDS, LAPSE, CHANNELS]


def test_the_ceilings_the_check_holds_a_bound_to_are_the_loops_own_documented_figures() -> None:
    """Written out in the check and held here against the product's own defaults, so the figure
    in one place cannot drift from the figure in the other without a test saying so. Delete this
    and the check's ceilings can stop describing the loop it is asking about."""
    from brain.gate.runtime import DEFAULT_MAX_TOOL_CALLS, DEFAULT_MAX_TURNS
    from brain.ops import acceptance_checks_runtime as module

    assert (module.AT_MOST_TURNS, module.AT_MOST_TOOL_CALLS) == (
        DEFAULT_MAX_TURNS,
        DEFAULT_MAX_TOOL_CALLS,
    )
    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_runtime") as url:
        yield url


@pytest.fixture(autouse=True)
def a_signed_in_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the chat check needs to bind a person: an issuer and a redirect, as the suite's own
    database test sets them. Delete this and the channel check says it was not run everywhere."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_runtime(url: str, *names: str) -> dict[str, tuple[str, str]]:
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


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_runtime(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_runtime_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass and nothing a check wrote is left: no
    agent, document, run row or binding. Delete this and a check that can never pass on a real
    schema, or one that leaves a run behind, reaches the owner's server."""
    before = counts(install)
    outcomes = run_runtime(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_loop_that_never_reaches_its_bound_fails_the_bounds_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bound never reached. Delete this and M13.7.2 closes on a loop that can run for ever."""
    from brain.gate.runtime import AgentRuntime

    monkeypatch.setattr(AgentRuntime, "_bound_reached", lambda self, run, bounds: None)
    assert "turn bound" in _failed(install, BOUNDS)


@pytest.mark.needs_db
def test_a_run_nobody_records_fails_the_bounds_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run log written to nothing. Delete this and M13.7.2 closes on a stop that is never
    recorded with the reason it was reached."""
    from brain.ops.agent_run_store import StoredAgentRuns

    async def nothing(self: Any, run: Any) -> None:
        return None

    monkeypatch.setattr(StoredAgentRuns, "record", nothing)
    assert "recorded exactly once" in _failed(install, BOUNDS)


@pytest.mark.needs_db
def test_a_result_steering_a_model_that_is_not_counted_fails_the_bounds_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The steering assessment reading every result as innocent. Delete this and M13.7.2 closes on
    a run that never counts what tried to steer it."""
    from brain.gate import runtime
    from brain.gate.injection import RiskAssessment

    monkeypatch.setattr(runtime, "assess", lambda text: RiskAssessment(score=0, matched=()))
    assert "was not counted" in _failed(install, BOUNDS)


@pytest.mark.needs_db
def test_a_run_that_keeps_the_reach_it_started_with_fails_the_lapse_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resolver answering with the first reach it ever gave. Delete this and M13.8.2 closes on
    a run that keeps using a capability from the moment it was revoked."""
    from brain.gate.entitlement_store import StoredEntitlements

    original = StoredEntitlements.load
    first: dict[str, Any] = {}

    async def frozen(self: Any, principal_id: str, now: Any) -> Any:
        if principal_id not in first:
            first[principal_id] = await original(self, principal_id, now)
        return first[principal_id]

    monkeypatch.setattr(StoredEntitlements, "load", frozen)
    assert "after the grant lapsed" in _failed(install, LAPSE)


@pytest.mark.needs_db
def test_an_agent_that_answers_on_every_channel_fails_the_channel_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The roster asked as if every question came from the web. Delete this and M13.7.4 closes on
    an agent that answers on a channel nobody switched on."""
    from brain import api_routes
    from brain.gate.context import Channel
    from brain.gate.roster import answer_roster as original

    def web_only(*args: Any, **kwargs: Any) -> Any:
        return original(*args, **{**kwargs, "channel": Channel.CONSOLE})

    monkeypatch.setattr(api_routes, "answer_roster", web_only)
    assert "answered for differently" in _failed(install, CHANNELS)
