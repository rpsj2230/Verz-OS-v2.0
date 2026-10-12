"""The company-wide publication check: registered, passing on a real schema, and able to fail.

Task ids: M33.1.2.1, M13.8.4
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

MODULE = "brain.ops.acceptance_checks_publication"
NAME = "a_second_person_publishes_an_agent_company_wide_and_retires_it"
ONLY = "only_the_company_visibility_holder_publishes_and_retires"


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


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_publication_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or close a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME, ONLY]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M33.1.2.1",)
    assert mine()[ONLY].leaves == ("M13.8.4",)


@pytest.mark.needs_db
def test_on_a_real_database_a_second_person_publishes_and_retires_and_nothing_is_kept() -> None:
    """**The check as the worker runs it.** Delete this and publishing an agent to the company can
    stop working, or start working for its steward alone, with nothing on the install saying so."""
    with at_head("brain_acceptance_publication") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _steward_may_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_lifecycle_routes as routes
    from brain.agents.lifecycle import PUBLICATION_LEVEL
    from brain.agents.model import AgentAudience

    def anybody(record: Any, *, publisher: Any, now: Any) -> Any:
        del publisher, now
        audience = AgentAudience(level=PUBLICATION_LEVEL, owner_id=record.audience.owner_id)
        return record.model_copy(update={"audience": audience})

    monkeypatch.setattr(routes, "publish", anybody)


def _lifecycle_publishes(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_lifecycle_routes as routes

    monkeypatch.setattr(routes, "may_publish", lambda reach, now: True)


def _nothing_written(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_lifecycle_routes as routes

    async def kept(self: Any, before: Any, after: Any, **rest: Any) -> bool:
        del self, before, after, rest
        return True

    monkeypatch.setattr(routes.StoredAgentLifecycles, "widen", kept)


BREAKS: dict[str, tuple[Any, str]] = {
    "steward_may_publish": (_steward_may_publish, "STEWARD_PUBLISHED"),
    "lifecycle_publishes": (_lifecycle_publishes, "LIFECYCLE_PUBLISHED"),
    "nothing_written": (_nothing_written, "NOT_OFFERED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_publication_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Three breaks: a steward publishing alone, the lifecycle authority publishing, and a
    publication that says it happened and wrote nothing. Delete this and the check can pass with
    the second person or the write gone."""
    import brain.ops.acceptance_checks_publication as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_publication_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_on_a_real_database_only_the_visibility_holder_publishes_and_retires() -> None:
    """**The second check as the worker runs it.** Delete this and M13.8.4 closes on a check that
    can never pass on a real schema, or that leaves an agent behind on the owner's install."""
    with at_head("brain_acceptance_publication_only") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[ONLY],))
        after = counts(url)
    assert outcome == {ONLY: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
def test_the_check_fails_where_a_department_administrator_may_publish_company_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The visibility authority given to every reader, in the route and in the move it writes.
    Delete this and M13.8.4 closes on a publication any administrator of a department may make."""
    import brain.ops.acceptance_checks_publication as module

    _lifecycle_publishes(monkeypatch)
    _steward_may_publish(monkeypatch)
    with at_head("brain_acceptance_publication_only_broken") as url:
        outcome = run_checks(url, (mine()[ONLY],))
    assert outcome[ONLY] == (FAILED, module.A_DEPARTMENT_ADMIN_PUBLISHED)
