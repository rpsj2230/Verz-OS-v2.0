"""The team and personal agent check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would. Then it is run
against the product broken where it proves: a team agent made by a person with no authority, an
agent listed to somebody who does not own it, and a builder that refuses a person their own agent.

Task ids: M39.10.1, M39.10.2, M39.10.3, M39.10.6
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

MODULE = "brain.ops.acceptance_checks_agent_kinds"
NAME = "a_person_makes_their_own_agent_and_a_team_one_needs_an_admin"


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


def test_the_agent_kinds_check_is_listed_with_the_leaves_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M39.10.1", "M39.10.2", "M39.10.3", "M39.10.6")


@pytest.mark.needs_db
def test_on_a_real_database_the_kinds_are_made_as_their_makers_may_and_nothing_is_left() -> None:
    """**The check as the worker runs it.** Delete this and a member's own agent, an
    administrator's team agent and the refusals between them can stop working with nothing on an
    install saying so."""
    with at_head("brain_acceptance_agent_kinds") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _anybody_makes_a_team_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    monkeypatch.setattr(routes, "_reaches", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(routes, "refusal_for", lambda *_args, **_kwargs: None)


def _a_team_agent_is_refused_in_the_wrong_words(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    monkeypatch.setattr(routes, "refusal_for", lambda *_args, **_kwargs: None)


def _every_agent_is_listed_to_everybody(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_routes as routes

    monkeypatch.setattr(
        routes,
        "visible_agent_ids",
        lambda records, _viewer: frozenset(one.agent_id for one in records),
    )


def _the_builder_is_never_opened_to_a_person(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    async def never(_sessions: object) -> bool:
        return False

    monkeypatch.setattr(routes, "personal_agents_on", never)


BREAKS: dict[str, tuple[Any, str]] = {
    "anybody_makes_a_team_agent": (_anybody_makes_a_team_agent, "TEAM_MADE_BY_A_MEMBER"),
    "wrong_words": (_a_team_agent_is_refused_in_the_wrong_words, "TEAM_REFUSAL_NOT_SAID"),
    "listed_to_everybody": (_every_agent_is_listed_to_everybody, "LISTED_TO_ANOTHER"),
    "builder_never_opened": (_the_builder_is_never_opened_to_a_person, "PERSONAL_NOT_OFFERED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_agent_kinds_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found, in its own words. Delete this and the check
    can pass over a team agent anybody makes, one listed to everybody, or a builder that is shut."""
    import brain.ops.acceptance_checks_agent_kinds as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_agent_kinds_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
