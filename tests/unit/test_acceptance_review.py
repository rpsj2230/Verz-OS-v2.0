"""The Resolution review screen's acceptance check: registered, passing on a real schema, and able
to fail.

Task ids: M14.6.4, M14.8.5
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_review"
REVIEWED = "a_waiting_pair_is_reviewed_and_decided_in_the_reviewers_name"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_review_check_is_listed() -> None:
    """The one check this module registers. Delete this and it can drop out of the page."""
    assert checks_in(MODULE) == [REVIEWED]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_review_check_passes_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and the review
    screen can stop showing or deciding pairs with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_review") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {REVIEWED: (PASSED, "")}
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, label: str, setup: Any) -> Any:
    setup(monkeypatch)
    with at_head(f"brain_acceptance_review_{label}") as url:
        outcome = run_checks(url, (mine()[REVIEWED],))
    return outcome[REVIEWED]


def _queue_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes
    from brain.resolution.review import review_page

    monkeypatch.setattr(routes, "review_page", lambda items, **kwargs: review_page([], **kwargs))


def _weights_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    import brain.resolution_routes as routes
    from brain.resolution.review import card_for

    def with_figures(item: Any) -> Any:
        card = card_for(item)
        return dataclasses.replace(
            card, lines=tuple(f"{one.field} {one.weight}" for one in item.evidence)
        )

    monkeypatch.setattr(routes, "card_for", with_figures)


def _reach_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes
    from brain.knowledge.columns import ColumnView

    def everything(reach: Any, record: Any, fields: Any, now: Any) -> Any:
        if fields is None:
            return None
        return ColumnView(entity=record.entity, values=dict(fields), locked=())

    monkeypatch.setattr(routes, "seen_by", everything)


def _refusal_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes
    from brain.core.errors import Absent

    def telling(asked: Any, reason: str) -> Absent:
        return Absent(reason, public_message=f"refused for {reason}")

    monkeypatch.setattr(routes, "_not_here", telling)


def _anybody_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes

    monkeypatch.setattr(routes, "may_review", lambda asked: True)


def _merge_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes

    async def said_so(*args: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(routes, "merge_reviewed", said_so)


def _decision_unwritten(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.resolution.review_store import StoredReviews

    async def nothing(self: Any, item_id: str, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(StoredReviews, "decide", nothing)


def _rejection_unwritten(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.resolution.review_store import StoredReviews
    from brain.tables.resolution_review import ReviewState

    kept = StoredReviews.decide

    async def merges_only(self: Any, item_id: str, **kwargs: Any) -> bool:
        if kwargs["state"] is ReviewState.REJECTED:
            return True
        return await kept(self, item_id, **kwargs)

    monkeypatch.setattr(StoredReviews, "decide", merges_only)


def _decided_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes

    monkeypatch.setattr(
        routes,
        "_decided_already",
        lambda: routes.ReviewDecidedView(item_id="x", state="merged", merged=True),
    )


BREAKS: dict[str, tuple[Any, str]] = {
    "queue_empty": (_queue_empty, "NOT_ON_THE_SCREEN"),
    "weights_shown": (_weights_shown, "NOT_IN_WORDS"),
    "reach_ignored": (_reach_ignored, "HALF_SHOWN"),
    "refusal_says_why": (_refusal_says_why, "NOT_ONE_404"),
    "anybody_reviews": (_anybody_reviews, "SHOWN_WITHOUT_AUTHORITY"),
    "merge_skipped": (_merge_skipped, "NOT_MERGED"),
    "decision_unwritten": (_decision_unwritten, "NOT_MERGED"),
    "rejection_unwritten": (_rejection_unwritten, "NOT_REJECTED"),
    "decided_twice": (_decided_twice, "DECIDED_TWICE"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_review_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: a waiting pair
    missing from the queue, evidence shown as figures, a pair shown to a reviewer reaching one
    half, a refusal that says why, a queue shown without the capability, a merge or a decision
    not stored in the reviewer's name, and a pair decided twice. Delete this and the check can
    pass with any of those properties gone."""
    import brain.ops.acceptance_checks_review as module

    setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, broken, setup) == (FAILED, getattr(module, reason))
