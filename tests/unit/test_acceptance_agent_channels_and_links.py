"""The agent channels check and the agent link check, passing on PostgreSQL at head and failing
with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M39.2.4.1, M39.2.4.2, M39.1.2.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any, Final, cast

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

CHANNELS_MODULE: Final = "brain.ops.acceptance_checks_agent_channels"
LINKS_MODULE: Final = "brain.ops.acceptance_checks_agent_links"
CHANNELS: Final = "a_surface_is_offered_only_if_it_can_carry_the_agent"
LINKS: Final = "a_link_to_an_agents_tab_lands_only_where_its_reader_may_open_it"


def test_each_module_names_the_leaves_it_proves() -> None:
    """Two modules, one check each, each closing its own leaves. Delete this and a check can lose a
    leaf with the page showing the same row, or start closing a leaf it does not prove."""
    from brain.ops import acceptance_checks_agent_channels as channels
    from brain.ops import acceptance_checks_agent_links as links

    assert [(one.name, one.leaves) for one in registered((CHANNELS_MODULE,))] == [
        (CHANNELS, ("M39.2.4.1", "M39.2.4.2"))
    ]
    assert [(one.name, one.leaves) for one in registered((LINKS_MODULE,))] == [
        (LINKS, ("M39.1.2.4",))
    ]
    assert checks_in(CHANNELS_MODULE) == [CHANNELS]
    assert checks_in(LINKS_MODULE) == [LINKS]
    assert 800 <= channels.CHECK_ORDER < links.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_channels_links") as url:
        yield url


def run_module(url: str, module: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((module,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**Both checks as the worker runs them.** Each passes and nothing it wrote is left. Delete
    this and a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install, CHANNELS_MODULE) == {CHANNELS: (PASSED, "")}
    assert run_module(install, LINKS_MODULE) == {LINKS: (PASSED, "")}
    assert counts(install) == before


def _everything_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import agent_routes

    monkeypatch.setattr(
        agent_routes,
        "offered_channels",
        lambda reach, capabilities, policy, now=None: tuple(one.channel for one in capabilities),
    )


def _everything_switchable(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import agent_lifecycle_routes
    from brain.agent_routes import declared_channels

    monkeypatch.setattr(
        agent_lifecycle_routes,
        "switchable_channels",
        lambda record, asked: frozenset(one.channel.value for one in declared_channels()),
    )


def _a_link_that_lands_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import agent_link_routes

    monkeypatch.setattr(
        agent_link_routes, "deep_link", lambda agent, tab: f"/agents/{agent}/{tab.value}?moved"
    )


def _a_refusal_that_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import agent_link_routes
    from brain.core.errors import Unresolved

    real = cast(Any, agent_link_routes).resolve

    def forbidding(link: str, reach: Any, **kwargs: Any) -> Any:
        found = real(link, reach, **kwargs)
        if found is None and link.endswith("/settings"):
            raise Unresolved("you may not open that tab")
        return found

    monkeypatch.setattr(agent_link_routes, "resolve", forbidding)


BREAKS: Final[dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str, str, str]]] = {
    "everything_offered": (
        _everything_offered,
        CHANNELS_MODULE,
        CHANNELS,
        "OFFERED_PAST_THE_CEILING",
    ),
    "everything_switchable": (
        _everything_switchable,
        CHANNELS_MODULE,
        CHANNELS,
        "SWITCHED_ON_PAST_THE_CEILING",
    ),
    "a_link_that_lands_elsewhere": (
        _a_link_that_lands_elsewhere,
        LINKS_MODULE,
        LINKS,
        "A_STEWARD_WAS_NOT_TAKEN_THERE",
    ),
    "a_refusal_that_says_why": (
        _a_refusal_that_says_why,
        LINKS_MODULE,
        LINKS,
        "THE_REFUSALS_DIFFER",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_each_check_fails_where_the_product_is_broken(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each failing with its own sentence: every surface offered to an agent that
    reaches something one cannot carry, every surface switchable, a link that lands at another
    address, and a refusal that says why. Delete this and either check can pass with any of those
    properties gone."""
    import importlib

    setup, module_name, name, reason = BREAKS[broken]
    setup(monkeypatch)
    module = importlib.import_module(module_name)
    assert run_module(install, module_name) == {name: (FAILED, getattr(module, reason))}
