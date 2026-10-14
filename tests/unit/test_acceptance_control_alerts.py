"""The alert that a mechanism has not run: its acceptance check is registered, passes on a real
schema, says it was not run while the feature ships off, and fails where the product is broken.

The pure half holds the module to its leaf and its page order. The database half runs the check as
the worker runs the suite, against PostgreSQL at head, with the feature switched on by replacing
the function that reads it: the check passes and leaves every table it wrote to as it found it.
Then the product is broken one property at a time and the check fails with that property's
sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M17.7.2
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import ROOT, at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_control_alerts"
ALERT = "a_mechanism_that_has_not_run_is_told_to_whoever_holds_the_alert"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_control_alert_check_is_listed_for_its_one_leaf() -> None:
    """The one check this module registers, proving the leaf it was scoped to. Delete this and it
    can drop out of the page, or close a leaf it does not exercise."""
    assert checks_in(MODULE) == [ALERT]
    assert mine()[ALERT].leaves == ("M17.7.2",)
    assert MODULE in check_modules()


def test_the_checks_leaf_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so an id that moved reads as a correct claim. Delete this and a
    result can close the wrong leaf on the owner's tracker."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert set(mine()[ALERT].leaves) <= leaves


def switched_on(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.control_not_run_told as told

    async def on(_: Any) -> bool:
        return True

    monkeypatch.setattr(told, "control_alerts_are_on", on)


@pytest.mark.needs_db
def test_while_the_feature_ships_off_the_check_says_it_was_not_run_and_writes_nothing() -> None:
    """**The state every install is in until somebody switches it on.** The check says in words why
    it asked nothing, rather than passing. Delete this and a feature nobody switched on reads as a
    passing check, or fails the install's suite."""
    import brain.ops.acceptance_checks_control_alerts as module

    with at_head("brain_acceptance_control_alerts_off") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {ALERT: (NOT_RUN, module.THE_ALERTS_ARE_SWITCHED_OFF)}
    assert after == before


@pytest.mark.needs_db
def test_on_a_real_database_the_control_alert_check_passes_and_nothing_is_left_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and the alert
    can stop reaching people with nothing on the owner's install saying so."""
    switched_on(monkeypatch)
    with at_head("brain_acceptance_control_alerts") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {ALERT: (PASSED, "")}
    assert after == before


def _everyone_told(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.control_not_run_told as told

    monkeypatch.setattr(told, "may_be_told", lambda reach, severity, now: True)


def _keyed_per_run(monkeypatch: pytest.MonkeyPatch) -> None:
    import itertools

    import brain.control_not_run_told as told

    counter = itertools.count()
    monkeypatch.setattr(told, "intent_ref_for", lambda late: f"{late.name}.{next(counter)}")


def _says_what_it_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.control_not_run_told as told

    monkeypatch.setattr(told, "control_text", lambda late, *, now, link="": late.overdue.text)


def _always_emailed(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.control_not_run_told as told

    monkeypatch.setattr(told, "no_chat_lately", lambda *a, **k: True)


def _never_emailed(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.control_not_run_told as told

    monkeypatch.setattr(told, "no_chat_lately", lambda *a, **k: False)


BREAKS: dict[str, tuple[Any, str]] = {
    "everyone_told": (_everyone_told, "TOLD_SOMEBODY_WHO_COULD_NOT_ACT"),
    "keyed_per_run": (_keyed_per_run, "SENT_TWICE"),
    "says_what_it_guards": (_says_what_it_guards, "NAMED_WHAT_IT_GUARDS"),
    "always_emailed": (_always_emailed, "EMAILED_WHILE_SOMEBODY_WAS_IN_CHAT"),
    "never_emailed": (_never_emailed, "NOT_EMAILED_WITH_NOBODY_IN_CHAT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_control_alert_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: everybody told whether
    or not they can act, a key that moves every run, a sentence saying what the mechanism guards,
    the email sent beside a chat, and no email with nobody in a chat. Delete this and the check can
    pass with any of those properties gone."""
    import brain.ops.acceptance_checks_control_alerts as module

    setup, reason = BREAKS[broken]
    switched_on(monkeypatch)
    setup(monkeypatch)
    with at_head(f"brain_acceptance_control_alerts_{broken}") as url:
        outcome = run_checks(url, (mine()[ALERT],))
    assert outcome[ALERT] == (FAILED, getattr(module, reason))
