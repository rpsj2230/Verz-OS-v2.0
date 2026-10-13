"""The outbox install check: registered, passing on a real schema, and able to fail.

The database half registers a subscriber, writes events and attempts their delivery as the worker
would, then reads the rows back; it passes and leaves nothing. Then the product is broken where the
check proves it: a wait that never grows, a signature made with the wrong secret, and an attempt
asked for twice that sends twice.

Task ids: M17.5.1, M17.5.2, M17.5.3
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_webhook_lane"
LANE = "a_delivery_is_retried_signed_sent_once_and_managed"
WRITTEN_HERE = (
    "ops.webhook_subscriber",
    "ops.outbox_event",
    "ops.outbox_delivery",
    "ops.operation",
)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_names_the_leaves_it_proves_and_every_one_is_a_leaf() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        LANE: ("M17.5.1", "M17.5.2", "M17.5.3")
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {"M17.5.1", "M17.5.2", "M17.5.3"} <= leaves


def test_the_webhook_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [LANE]


def test_the_module_stands_inside_its_assigned_order_range() -> None:
    """Delete this and two modules can claim one place on the Install page."""
    from brain.ops import acceptance_checks_webhook_lane as module

    assert 2000 <= module.CHECK_ORDER <= 2099


def test_the_two_delivery_leaves_are_held_because_the_wire_is_made_up() -> None:
    """The check answers for the receiver and signs with a made-up secret, so the sweep must not
    close the delivery leaves on its pass alone. Delete this and M17.5.1 or M17.5.2 can close on a
    receiver the install never reached."""
    holds = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text(encoding="utf-8"))
    assert {"M17.5.1", "M17.5.2"} <= set(holds["held"])


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
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_HERE
    }


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes and every table
    it wrote holds what it held before. Delete this and a check that cannot pass on the real
    schema, or one that commits a subscriber to a client's install, reaches the owner's server."""
    with at_head("brain_acceptance_webhook_lane") as url:
        before = (counts(url), written(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))

    assert outcomes == {LANE: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("flat_wait", "the wait between refused deliveries did not grow"),
        ("wrong_secret", "a delivery was not signed so that its receiver can verify it"),
        ("sends_twice", "asking again for an attempt already made sent it a second time"),
    ],
)
def test_the_check_fails_where_the_product_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, each the way it happens: a retry that waits the same every time, which is a
    hot loop against a receiver already struggling; a signature made over a different secret, which
    every receiver refuses and reads as a wrong key; and a delivery whose key is new on every ask,
    so a worker that crashed after sending sends again. Delete this and the check is satisfied by
    a dispatcher that does none of the three."""
    from brain.ops import outbox, outbox_store

    if broken == "flat_wait":
        real_plan = outbox.plan_next

        def flat(*args: Any, **kwargs: Any) -> Any:
            found = real_plan(*args, **kwargs)
            return type(found)(delivery=found.delivery, delay_seconds=1.0, reason=found.reason)

        monkeypatch.setattr(outbox_store, "plan_next", flat)
    elif broken == "wrong_secret":
        real_signed = outbox.signed_request
        monkeypatch.setattr(
            outbox_store,
            "signed_request",
            lambda **kw: real_signed(**{**kw, "secret": kw["secret"] + "x"}),
        )
    else:
        counter = iter(range(10_000))
        real_operation = outbox_store.delivery_operation

        def fresh(delivery: Any, subscriber: Any) -> Any:
            from brain.ops.idempotency import Intent, operation_for

            real = real_operation(delivery, subscriber)
            return operation_for(
                Intent(principal_id=real.principal_id, intent_ref=f"again-{next(counter)}"),
                connector=real.connector,
                tool=real.tool,
            )

        monkeypatch.setattr(outbox_store, "delivery_operation", fresh)
    with at_head("brain_acceptance_webhook_lane") as url:
        assert run_checks(url, tuple(mine().values())) == {LANE: (FAILED, reason)}
