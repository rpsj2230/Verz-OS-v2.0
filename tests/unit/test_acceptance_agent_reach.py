"""The agent reach check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a table
uploaded into acceptance_a, two agents of acceptance_a with different ceilings, reserved people
bound in Lark, and every question asked on the web and in Lark. Then it is run against the product
broken where it proves: an agent's run taken at the person's reach alone, at the agent's ceiling
alone, and an agent run for somebody outside its audience. Each fails with its own sentence.

Task ids: M13.7.5, M13.1.3
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_agent_reach"
NAME = "asking_through_an_agent_is_answered_at_the_narrower_reach"


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


@pytest.fixture(autouse=True)
def an_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The issuer and address the full run hands the worker, which the chat channel's gate needs."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_agent_reach_check_is_listed_with_the_leaves_it_proves() -> None:
    """Delete this and the check can drop out of the module, or close a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M13.7.5", "M13.1.3")


@pytest.mark.needs_db
def test_on_a_real_database_an_agent_narrows_both_ways_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it.** Delete this and an agent can answer past its ceiling
    or past its asker with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_agent_reach") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _the_caller_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.gate.roster as roster

    monkeypatch.setattr(roster, "run_reach", lambda caller, record: caller)


def _the_ceiling_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.gate.roster as roster
    from brain.agents.model import entitlement_ceiling

    def ceiling(caller: Any, record: Any) -> Any:
        # The agent's own grants, held as the person: what an agent lending its reach would be.
        return entitlement_ceiling(record).model_copy(update={"principal_id": caller.principal_id})

    monkeypatch.setattr(roster, "run_reach", ceiling)


def _audience_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agents.model as model

    monkeypatch.setattr(model, "visible_to", lambda audience, viewer: True)


BREAKS: dict[str, tuple[Any, str]] = {
    "caller_alone": (_the_caller_alone, "WIDER_THAN_THE_AGENT"),
    "ceiling_alone": (_the_ceiling_alone, "WIDER_THAN_THE_ASKER"),
    "audience_ignored": (_audience_ignored, "AUDIENCE_IS_AUTHORITY"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_agent_reach_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Three breaks: a run taken at the person's reach and the agent's ceiling ignored, a run
    taken at the agent's ceiling and the person's reach ignored (M13.7.5), and an agent run for
    a person outside its audience (M13.1.3). Delete this and the check can pass with the
    intersection or the audience gone."""
    import brain.ops.acceptance_checks_agent_reach as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_agent_reach_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
