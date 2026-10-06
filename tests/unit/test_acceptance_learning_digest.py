"""The weekly learning digest's acceptance check: registered, passing on a real schema, and able to
fail.

The pure half holds the module to its leaf and its page order. The database half runs the check as
the worker runs the suite, against PostgreSQL at head: it passes and leaves every table it wrote to
as it found it. Then the product is broken the way it would plausibly break, one property at a time,
by replacing the function the sender looks up, and the check fails with that property's sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.5.1
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import ROOT, at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_learning_digest"
WEEK = "a_persons_week_of_learning_is_told_once_with_its_undo"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_learning_digest_check_is_listed_for_its_one_leaf() -> None:
    """The one check this module registers, proving the leaf it was scoped to. Delete this and it
    can drop out of the page, or close a leaf it does not exercise."""
    assert checks_in(MODULE) == [WEEK]
    assert mine()[WEEK].leaves == ("M16.5.1",)
    assert MODULE in check_modules()


def test_the_checks_leaf_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so an id that moved reads as a correct claim. Delete this and a
    result can close the wrong leaf on the owner's tracker."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert set(mine()[WEEK].leaves) <= leaves


def test_the_check_removes_a_grant_the_memory_checks_show_a_memory_depends_on() -> None:
    """The memory the person may not recall is formed after this grant is removed from them, so
    the grant has to be one a stated memory records. Delete this and a renamed capability leaves
    the hidden memory recallable, and the reach half of the check proves nothing."""
    from brain.ops.acceptance_checks import KNOWLEDGE_READS
    from brain.ops.acceptance_checks_learning_digest import REMOVED

    assert REMOVED in KNOWLEDGE_READS


@pytest.mark.needs_db
def test_on_a_real_database_the_learning_digest_check_passes_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and the weekly
    digest can stop reaching people with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_learning_digest") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {WEEK: (PASSED, "")}
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, label: str, setup: Any) -> Any:
    setup(monkeypatch)
    with at_head(f"brain_acceptance_learning_digest_{label}") as url:
        outcome = run_checks(url, (mine()[WEEK],))
    return outcome[WEEK]


def _keyed_per_run(monkeypatch: pytest.MonkeyPatch) -> None:
    import itertools

    import brain.learning_told as told

    counter = itertools.count()
    monkeypatch.setattr(told, "intent_ref_for", lambda week: f"{week.key}.{next(counter)}")


def _no_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.learning_told as told

    monkeypatch.setattr(
        told, "digest_text", lambda digest, *, page, zone: "The system learnt from you this week."
    )


def _reach_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.learning_told as told
    from brain.memory.digest import Learning, WeeklyDigest, memory_item
    from brain.memory.formation import Recollection

    def everything(
        *, now: datetime, reader: Any, learnings: list[Learning], period: timedelta
    ) -> WeeklyDigest:
        return WeeklyDigest(
            reader_id=reader.principal_id,
            covers_from=now - period,
            covers_to=now,
            entries=tuple(
                memory_item(
                    one,
                    Recollection(formation=one.formation, scope=one.formation.scope, confidence=1),
                )
                for one in learnings
            ),
        )

    monkeypatch.setattr(told, "weekly_digest", everything)


def _empty_weeks_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.learning_told as told

    monkeypatch.setattr(told, "worth_sending", lambda digest: True)


BREAKS: dict[str, tuple[Any, str]] = {
    "keyed_per_run": (_keyed_per_run, "SENT_TWICE"),
    "no_undo": (_no_undo, "NOT_NAMED_WITH_UNDO"),
    "reach_ignored": (_reach_ignored, "NAMED_OUTSIDE_REACH"),
    "empty_weeks_sent": (_empty_weeks_sent, "SENT_WITH_NOTHING_LEARNT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_learning_digest_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: a week keyed so a
    second run sends again, a message with no undo in it, a week composed past the reader's reach,
    and an empty week sent. Delete this and the check can pass with any of those properties
    gone."""
    import brain.ops.acceptance_checks_learning_digest as module

    setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, broken, setup) == (FAILED, getattr(module, reason))
