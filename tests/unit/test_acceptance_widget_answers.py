"""The widget's model-written answer check: registered, passing on a real schema, able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, the model a
stand-in answering in the process. Then it is run against the product broken where it proves: a
model asked with the switch off, a cap that is never held, a model sent a tool, an answer whose cost
is not written, and a cap that stops the model before it is used.

Task ids: M10.7.6, M10.7.7, M10.7.8
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_widget_answers"
NAME = "the_widget_writes_from_public_passages_under_a_daily_cap"


@pytest.fixture(autouse=True)
def _a_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install's currency, which a cost is counted in and a cap is a figure of."""
    monkeypatch.setenv("INSTALL_CURRENCY", "USD")
    # The hosted profile, so the stand-in is planned. No provider key is held.
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")


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


def test_the_widget_answers_check_is_listed_with_the_leaves_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M10.7.6", "M10.7.7", "M10.7.8")


@pytest.mark.needs_db
def test_on_a_real_database_the_widget_writes_and_stops_at_its_cap_and_leaves_nothing() -> None:
    """**The check as the worker runs it.** Delete this and the widget's model answers, their cost
    and the cap that stops them can stop working with nothing on an install saying so."""
    with at_head("brain_acceptance_widget_answers") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _ignores_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.widget_answers as answers

    async def always(_sessions: object) -> bool:
        return True

    monkeypatch.setattr(answers, "model_answers_on", always)


def _never_holds_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.widget_answers as answers

    async def nothing_spent(_session: object, _now: object) -> int:
        return 0

    monkeypatch.setattr(answers, "spent_today", nothing_spent)


def _writes_no_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.widget_answers as answers

    async def silent(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(answers, "_written", silent)


def _forgets_the_passage(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.widget_answers as answers
    from brain.models.driver import DriverMessage, Role

    def question_only(question: str, _passages: Any) -> Any:
        return (DriverMessage(role=Role.USER, content=question),)

    monkeypatch.setattr(answers, "messages_for", question_only)


BREAKS: dict[str, tuple[Any, str]] = {
    "ignores_the_switch": (_ignores_the_switch, "ASKED_WITH_THE_SWITCH_OFF"),
    "never_holds_the_cap": (_never_holds_the_cap, "CAP_NOT_HELD"),
    "writes_no_cost": (_writes_no_cost, "COST_NOT_ON_THE_LEDGER"),
    "forgets_the_passage": (_forgets_the_passage, "NOT_WRITTEN_FROM_THE_PASSAGES"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_widget_answers_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found, in its own words. Delete this and the check
    can pass over a switch nothing reads, a cap nothing counts, or a model shown no passage."""
    import brain.ops.acceptance_checks_widget_answers as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_widget_answers_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_an_install_with_no_currency_set_is_told_the_check_cannot_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no currency a cost has no unit and a cap no meaning, so the check says it did not run
    rather than passing or failing. Delete this and an install that has set no currency reads a
    pass or a failure about a cap it could not have."""
    monkeypatch.setenv("INSTALL_CURRENCY", "XXX")
    with at_head("brain_acceptance_widget_answers_no_currency") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME][0] == NOT_RUN
