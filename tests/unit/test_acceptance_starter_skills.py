"""The starter skill check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would. Then it is run
against the product broken where it proves: furnishing that writes fewer than eight. A skill
furnished already approved is not a break that can be made, because `added` takes no state.

Task ids: M12.4.7
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

MODULE = "brain.ops.acceptance_checks_starter_skills"
NAME = "the_starter_skills_are_furnished_rehearsed_and_assigned"


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


def test_the_starter_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M12.4.7",)


@pytest.mark.needs_db
def test_on_a_real_database_the_eight_are_furnished_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it.** Delete this and furnishing, rehearsal or assignment of
    the starter library can stop working with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_starter_skills") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _furnishes_seven(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.ops.starter_skill_store as store
    from brain.tools import starter_skills

    monkeypatch.setattr(store, "STARTER_SKILLS", starter_skills.STARTER_SKILLS[:7])


BREAKS: dict[str, tuple[Any, str]] = {
    "seven": (_furnishes_seven, "NOT_FURNISHED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_starter_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Furnishing that leaves a starter out is found. Delete this and the check can pass with a
    library of seven."""
    import brain.ops.acceptance_checks_starter_skills as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_starter_skills_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
