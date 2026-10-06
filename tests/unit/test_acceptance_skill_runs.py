"""The skill run check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, with a
stand-in model answering in the process that keeps what it is sent. Then it is run against the
product broken where it proves: an agent's run handed no pins, as `/answer` did until 2026-10-06,
a card carrying the skill's body, a run offered every approved skill rather than its own, and an
agent's level ignored.

Task ids: M27.12.1
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

MODULE = "brain.ops.acceptance_checks_skill_runs"
NAME = "an_agents_run_reads_its_assigned_skills_and_its_level"


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
def hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted profile, so the stand-in may be asked; no provider's key is needed for it."""
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")


def at_head_laddered(name: str) -> Any:
    """PostgreSQL at head with the ladder the setup wizard writes, as the routing checks run on."""
    from contextlib import contextmanager

    from tests.unit.test_acceptance_models import laddered

    @contextmanager
    def made() -> Any:
        with at_head(name) as url:
            laddered(url)
            yield url

    return made()


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_skill_run_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim M12.2.8, whose on-demand
    half it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M27.12.1",)


@pytest.mark.needs_db
def test_on_a_real_database_an_agent_s_run_shows_its_skill_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it.** Delete this and an assigned skill can stop reaching
    the model with nothing on the owner's install saying so."""
    with at_head_laddered("brain_acceptance_skill_runs") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _no_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    import brain.api_routes as api_routes

    kept = api_routes.agent_run_of

    async def pinless(state: Any, agent: Any, registry: Any) -> Any:
        run = await kept(state, agent, registry)
        return None if run is None else dataclasses.replace(run, pins=(), library=())

    monkeypatch.setattr(api_routes, "agent_run_of", pinless)


def _body_on_the_card(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.gate.model_lane as model_lane
    from brain.tools.skills import SkillCard

    def carded(skills: Any) -> Any:
        return tuple(
            SkillCard(
                name=one.skill.name,
                description=f"{one.skill.description} {one.skill.body}",
                version=one.skill.version,
            )
            for one in skills
        )

    monkeypatch.setattr(model_lane, "offered_cards", carded)


def _every_approved_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.gate.model_lane as model_lane

    def everything(agent: Any, *, caller: Any, now: Any) -> Any:
        del caller, now
        return tuple(one.imported for one in agent.library)

    monkeypatch.setattr(model_lane, "skills_offered", everything)


def _level_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.gate.model_lane as model_lane

    kept = model_lane.routing_for
    monkeypatch.setattr(model_lane, "routing_for", lambda messages, tier: kept(messages, None))


BREAKS: dict[str, tuple[Any, str]] = {
    "no_pins": (_no_pins, "NO_CARD"),
    "body_on_the_card": (_body_on_the_card, "BODY_SENT"),
    "every_approved_skill": (_every_approved_skill, "UNASSIGNED_SENT"),
    "level_ignored": (_level_ignored, "NOT_ITS_LEVEL"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_skill_run_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each failing with its own sentence: no pins read, the body sent with the card,
    every approved skill offered, and the agent's level ignored. Delete this and the check can
    pass with an assigned skill reaching nothing."""
    import brain.ops.acceptance_checks_skill_runs as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head_laddered(f"brain_acceptance_skill_runs_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
