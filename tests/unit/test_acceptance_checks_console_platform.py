"""The install checks for the platform screens, passing on PostgreSQL at head, leaving nothing, and
failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.44
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_platform"
WEBHOOKS = "a_subscriber_is_switched_on_again_and_a_delivery_replayed_once"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {WEBHOOKS: ("M27.15.44",)}
    assert checks_in(MODULE) == [WEBHOOKS]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_platform") as url:
        yield url


def _failed(url: str, name: str) -> str:
    outcome, reason = run_module(url, MODULE)[name]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** They pass and leave no person, grant, ledger entry,
    subscriber or delivery. Delete this and a check that commits, or one that cannot pass on a real
    schema, reaches the owner's server first."""
    from tests.fixtures.scratch_postgres import sql

    before = counts(install)
    held = [
        int(sql(install, f"SELECT count(*) FROM {table}")[0][0])  # noqa: S608
        for table in ("ops.webhook_subscriber", "ops.outbox_delivery", "ops.outbox_event")
    ]
    assert run_module(install, MODULE) == {WEBHOOKS: (PASSED, "")}
    assert counts(install) == before
    assert held == [
        int(sql(install, f"SELECT count(*) FROM {table}")[0][0])  # noqa: S608
        for table in ("ops.webhook_subscriber", "ops.outbox_delivery", "ops.outbox_event")
    ]


@pytest.mark.needs_db
def test_a_delivery_replayed_twice_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replay that never closes. Delete this and M27.15.44 closes on a screen that sends one
    given-up delivery again every time somebody presses the button."""
    from brain.ops import webhook_store

    async def always(self: object, *args: object, **kwargs: object) -> None:
        del self, args, kwargs

    monkeypatch.setattr(webhook_store.StoredWebhooks, "replay", always, raising=False)
    assert _failed(install, WEBHOOKS)


@pytest.mark.needs_db
def test_a_switch_on_that_is_not_on_the_record_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A switch on written with no change to show for it. Delete this and M27.15.44 closes on a
    screen that turns a subscriber back on with nobody's name on the record."""
    from brain.ops import webhook_store

    async def silently(self: object, subscriber_id: str, *, actor: str, at: object) -> None:
        del self, subscriber_id, actor, at

    monkeypatch.setattr(webhook_store.StoredWebhooks, "switch_on", silently, raising=False)
    assert _failed(install, WEBHOOKS)
