"""The enforcement install check: what it names, that it passes on the product as it is, and that
it fails for each way a run could stop being held to its envelope.

It needs no database: the driver's ledger is a quiet stand-in and nothing is written. Each failure
is one defect injected into the function the runner or the driver calls, and the check must fail
with its own sentence.

Task ids: M19.3.1, M19.3.2, M19.3.3, M19.3.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain.browsing import driver, wire
from brain.browsing.enforcer import Enforcement, Refusal, authorise
from brain.ops import acceptance_checks_browser_enforcement as module
from brain.ops.acceptance import PASSED, CheckFailedError, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_enforcement"
NAME = "a_browser_run_is_held_to_the_envelope_it_was_sealed_with"
HARNESS = SimpleNamespace(run="r1", trace_id="t-1", now=datetime(2999, 1, 1, 12, 0, tzinfo=UTC))


def run_it() -> None:
    asyncio.run(module.a_browser_run_is_held_to_the_envelope_it_was_sealed_with(HARNESS))  # type: ignore[arg-type]


def fails_with(sentence: str) -> None:
    with pytest.raises(CheckFailedError) as failed:
        run_it()
    assert failed.value.reason == sentence


def test_the_check_names_the_four_enforcement_leaves_and_sits_in_this_packages_range() -> None:
    """Delete this and the check can lose a leaf with the page showing the same row, or sit outside
    the keys this package was given, where it would collide with another package's."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (NAME, ("M19.3.1", "M19.3.2", "M19.3.3", "M19.3.4"))
    ]
    assert checks_in(MODULE) == [NAME]
    assert 2300 <= module.CHECK_ORDER <= 2399


def test_the_check_passes_on_the_product_as_it_is() -> None:
    """The positive case for every failure below. Delete this and a check that fails on a healthy
    product satisfies all of them."""
    run_it()


@pytest.mark.parametrize(
    "reason", ["unknown_reference", "origin_not_allowed", "not_in_envelope", "budget_spent"]
)
def test_a_runner_that_lets_one_refusal_through_fails_the_check(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """One refusal waved through at a time. Delete this and a runner that stopped refusing an
    invented reference, an undeclared origin, an undeclared verb or a second use passes."""
    real = authorise

    def lax(policy: Any, action: Any, snapshot: Any, spend: Any, **kw: Any) -> Enforcement:
        decision = real(policy, action, snapshot, spend, **kw)
        if decision.refusal is Refusal(reason):
            return Enforcement(allowed=True, spend=spend.plus(action.verb))
        return decision

    monkeypatch.setattr("brain.browsing.runner.authorise", lax)

    fails_with(module.A_REFUSAL_ENDS_THE_RUN_AND_IS_REPORTED)


def test_a_runner_that_refuses_everything_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sibling of the above. Delete this and a runner that refuses every instruction passes a
    check that asks only for refusals."""

    def never(policy: Any, action: Any, snapshot: Any, spend: Any, **kw: Any) -> Enforcement:
        return Enforcement(allowed=False, spend=spend, refusal=Refusal.NOT_IN_ENVELOPE)

    monkeypatch.setattr("brain.browsing.runner.authorise", never)

    fails_with(module.AN_INSIDE_RUN_WAS_REFUSED)


def test_a_replay_that_finds_nothing_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a driver that stopped replaying what the container reported passes, which
    leaves the control plane believing the container."""
    monkeypatch.setattr(driver, "recheck", lambda envelope, records, approval=None: ())

    fails_with(module.A_REFUSAL_ENDS_THE_RUN_AND_IS_REPORTED)


def test_a_start_line_carrying_another_digest_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a runner started on a digest the control plane never sealed passes."""
    real = wire.start_fields

    def other(*args: Any, **kw: Any) -> dict[str, Any]:
        return {**real(*args, **kw), "digest": "0" * 64}

    monkeypatch.setattr(wire, "start_fields", other)

    fails_with(module.THE_POLICY_IS_NOT_THE_ENVELOPES)


def test_a_policy_that_can_be_changed_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a policy a run could edit mid-run passes."""
    real = wire.policy_of

    def mutable(message: Any) -> Any:
        policy = real(message)
        return SimpleNamespace(envelope_digest=policy.envelope_digest, run_id=policy.run_id)

    monkeypatch.setattr(wire, "policy_of", mutable)

    fails_with(module.THE_POLICY_IS_NOT_THE_ENVELOPES)


def test_a_start_line_whose_parts_were_edited_and_is_accepted_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a runner that stopped re-deriving its digest from the parts it was sent,
    and so trusts a budget somebody raised on the way, passes."""
    real = wire.policy_of

    def lenient(message: Any) -> Any:
        try:
            return real(message)
        except wire.WireError:
            fields = dict(message.fields)
            fields["budget"] = [[verb, count - 5] for verb, count in fields["budget"]]
            return real(wire.decode(wire.encode(wire.Kind.START, **fields)))

    monkeypatch.setattr(wire, "policy_of", lenient)

    fails_with(module.THE_POLICY_IS_NOT_THE_ENVELOPES)


def test_a_policy_with_a_field_that_invites_a_reread_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the structural guard on `Policy` is a function nothing on an install asks."""
    from brain.browsing import enforcer

    monkeypatch.setattr(enforcer, "policy_gaps", lambda subject=enforcer.Policy: ("refreshed_at",))

    fails_with(module.THE_POLICY_IS_NOT_THE_ENVELOPES)


def test_an_envelope_that_does_not_wait_for_a_person_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check's write has to be a write that waits, or the approval it hands the run proves
    nothing. Delete this and an envelope that compiled the write away passes."""
    from brain.browsing.envelope import Envelope

    monkeypatch.setattr(Envelope, "awaits_approval", lambda self: False)

    fails_with(module.AN_INSIDE_RUN_WAS_REFUSED)


def test_a_policy_carrying_another_digest_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a runner whose policy names an envelope the control plane never sealed
    passes, which is the second check having nothing to compare."""
    from dataclasses import replace

    real = wire.policy_of
    monkeypatch.setattr(
        wire,
        "policy_of",
        lambda message: replace(real(message), envelope_digest="0" * 64, approved_digest=""),
    )

    fails_with(module.THE_POLICY_IS_NOT_THE_ENVELOPES)


def test_a_runner_that_never_performs_the_approved_write_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a runner that allows the click and then does nothing passes a check that
    asks whether the page was spared."""
    from types import SimpleNamespace as Issued

    monkeypatch.setattr(
        "brain.browsing.runner.issue_once", lambda ledger, operation, perform: Issued(issued=True)
    )

    fails_with(module.AN_INSIDE_RUN_WAS_REFUSED)


def test_a_runner_that_ends_on_another_reason_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a runner that ends a refused run without saying why, so the control plane
    cannot tell a breach from a stop, passes."""
    from brain.browsing import runner

    real = vars(runner)["_end"]
    monkeypatch.setattr(
        "brain.browsing.runner._end",
        lambda channel, reason: real(channel, reason.split(":")[0]),
    )

    fails_with(module.A_REFUSAL_ENDS_THE_RUN_AND_IS_REPORTED)


def test_a_runner_that_refuses_after_performing_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a runner that clicks and only then reports the click as refused passes: the
    page is changed and the record says it was not."""
    from brain.browsing import runner

    real = vars(runner)["_step"]

    def perform_then_refuse(
        policy: Any,
        message: Any,
        surfaces: Any,
        browser: Any,
        ledger: Any,
        spend: Any,
        current: Any,
        principal: Any,
    ) -> Any:
        decision, action, observed = real(
            policy, message, surfaces, browser, ledger, spend, current, principal
        )
        if decision.refusal is not None and message.fields["verb"] != "open":
            browser.act(action.verb, action.ref, "")
        return decision, action, observed

    monkeypatch.setattr("brain.browsing.runner._step", perform_then_refuse)

    fails_with(module.A_REFUSAL_ENDS_THE_RUN_AND_IS_REPORTED)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_enforcement") as url:
        yield url


@pytest.mark.needs_db
def test_the_check_passes_as_the_worker_runs_it_and_leaves_nothing(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The module as the worker runs it**, through the harness and over a migrated database.
    Delete this and a check that passes called directly but not through the harness, or one that
    writes a row, reaches the owner first."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    before = counts(install)

    assert run_checks(install, registered((MODULE,)))[NAME] == (PASSED, "")
    assert counts(install) == before
