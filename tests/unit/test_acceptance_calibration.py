"""The weekly fit's acceptance check: registered, passing on a real schema, and able to fail.

Task ids: M14.3.5, M14.4.2, M14.4.4, M14.8.3
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_calibration"
FIT = "a_fit_is_shown_as_drift_promoted_by_name_and_scored_with"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_calibration_check_is_listed() -> None:
    """The one check this module registers. Delete this and it can drop out of the page."""
    assert checks_in(MODULE) == [FIT]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_calibration_check_passes_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and the weekly
    fit can stop reaching a reviewer with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_calibration") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {FIT: (PASSED, "")}
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, label: str, setup: Any) -> Any:
    setup(monkeypatch)
    with at_head(f"brain_acceptance_calibration_{label}") as url:
        outcome = run_checks(url, (mine()[FIT],))
    return outcome[FIT]


def _uen_unmeasured(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses
    from types import MappingProxyType

    import brain.resolution.calibration_store as store
    from brain.resolution.calibration import export
    from brain.resolution.cascade import Feature

    def against(model: Any, **kwargs: Any) -> Any:
        made = export(model, **kwargs)
        weights = {**made.weights, Feature.UEN: -1.0}
        return dataclasses.replace(made, weights=MappingProxyType(weights))

    monkeypatch.setattr(store, "export", against)


def _no_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes

    async def none(sessions: Any) -> None:
        return None

    monkeypatch.setattr(routes, "candidate", none)


def _anybody_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes

    monkeypatch.setattr(routes, "may_review", lambda asked: True)


def _promote_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.resolution_routes as routes

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(routes, "promote_fit", nothing)


BREAKS: dict[str, tuple[Any, str]] = {
    "uen_unmeasured": (_uen_unmeasured, "NOT_FITTED"),
    "no_candidate": (_no_candidate, "NO_DRIFT_SHOWN"),
    "anybody_reviews": (_anybody_reviews, "SHOWN_WITHOUT_AUTHORITY"),
    "promote_skipped": (_promote_skipped, "NOT_PROMOTED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_calibration_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: a fit that does not
    measure what agreed, a fit never shown to a reviewer, the weights shown to anybody, and a
    promote that puts nothing in force. Delete this and the check can pass with any of those
    properties gone."""
    import brain.ops.acceptance_checks_calibration as module

    setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, broken, setup) == (FAILED, getattr(module, reason))
