"""The unattended-approval install check: registered, passing on PostgreSQL at head, leaving
nothing, and failing where the product is broken the way it would plausibly break.

Task ids: M17.4.5
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_unattended_approval"
HOLD = "a_step_an_unattended_run_holds_waits_for_a_person_and_expires"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_names_its_leaf_and_its_sentences_fit_a_result() -> None:
    """Delete this and the check can close a leaf it does not exercise, or one of its reasons is
    cut short on the Install page."""
    from brain.ops import acceptance_checks_unattended_approval as module

    assert {name: one.leaves for name, one in mine().items()} == {HOLD: ("M17.4.5",)}
    assert checks_in(MODULE) == [HOLD]
    sentences = [
        value
        for name, value in vars(module).items()
        if name.isupper() and isinstance(value, str) and name != "CHECK_ORDER"
    ]
    assert len(sentences) >= 9
    assert all(len(one) <= REASON_CHARS for one in sentences)


def run_checks(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                tuple(mine().values()),
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_check_passes_and_leaves_nothing() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and a hold that
    cannot be raised on a real schema, or one the check leaves behind, reaches the owner's
    server."""
    with at_head("brain_acceptance_unattended_approval") as url:
        before = counts(url)
        outcome = run_checks(url)
        after = counts(url)
    assert outcome == {HOLD: (PASSED, "")}
    assert after == before


def _the_window_is_not_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import automation_hold

    monkeypatch.setattr(automation_hold, "approval_refusals", lambda run, steps: ())


def _a_lapsed_hold_is_never_a_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import automation_hold

    monkeypatch.setattr(automation_hold, "expire", lambda step, *, raised_at, now: None)


def _a_decided_hold_is_a_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import automation_hold
    from brain.orchestration.unattended import ApprovalStep, expire

    def without_the_decision(held: Any, *, automation_id: str, step_id: str, now: Any) -> Any:
        step = ApprovalStep(
            step_id=step_id, automation_id=automation_id, window=held.expires_at - held.raised_at
        )
        return expire(step, raised_at=held.raised_at, now=now)

    monkeypatch.setattr(automation_hold, "stopped_for_want_of_approval", without_the_decision)


def _every_window_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import automation_hold

    monkeypatch.setattr(
        automation_hold, "approval_refusals", lambda run, steps: ("a window is always too long",)
    )


def _the_maximum_is_not_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import automation_hold
    from brain.orchestration.unattended import approval_refusals as real

    def cadence_only(run: Any, steps: Any) -> tuple[str, ...]:
        return tuple(one for one in real(run, steps) if "the platform maximum is" not in one)

    monkeypatch.setattr(automation_hold, "approval_refusals", cadence_only)


def _another_department_is_the_approver(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import acceptance_checks_governance_2 as governance

    real = governance._two_people

    async def same(h: Any) -> tuple[str, str, str]:
        asker, approver, _ = await real(h)
        return asker, approver, approver

    monkeypatch.setattr(governance, "_two_people", same)


def _the_approval_is_never_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import approval_routes

    real = approval_routes.take_decision

    async def sometimes(store: Any, suspension_id: str, *args: Any, **kwargs: Any) -> Any:
        if "_fresh_" in suspension_id:
            return None
        return await real(store, suspension_id, *args, **kwargs)

    monkeypatch.setattr(approval_routes, "take_decision", sometimes)


BREAKS: dict[str, tuple[Any, str]] = {
    "window_unchecked": (_the_window_is_not_checked, "A_WINDOW_AS_LONG_AS_THE_GAP_WAS_ALLOWED"),
    "never_a_stop": (_a_lapsed_hold_is_never_a_stop, "NOBODY_ANSWERING_DID_NOT_STOP_THE_RUN"),
    "decided_is_a_stop": (_a_decided_hold_is_a_stop, "A_DECIDED_HOLD_WAS_A_STOP"),
    "declared_window_refused": (_every_window_is_refused, "THE_DECLARED_WINDOW_WAS_REFUSED"),
    "maximum_not_enforced": (_the_maximum_is_not_enforced, "A_WINDOW_PAST_THE_MAXIMUM_WAS_ALLOWED"),
    "other_department_shown": (
        _another_department_is_the_approver,
        "ANOTHER_DEPARTMENT_WAS_SHOWN_THE_HOLD",
    ),
    "approval_not_taken": (_the_approval_is_never_taken, "A_DECIDED_HOLD_WAS_A_STOP"),
}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: a window nobody checks,
    a maximum nobody enforces, a declared window refused, another department shown the card, a hold
    that was never approved, a lapsed hold that never counts as a stop, and a decided hold that
    does. Delete this and the check can pass with any of those properties gone."""
    import brain.ops.acceptance_checks_unattended_approval as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_unattended_{broken}") as url:
        outcome = run_checks(url)
    assert outcome[HOLD][0] == FAILED
    assert outcome[HOLD][1] == getattr(module, reason)
