"""The Webhooks screen's store against a real database: every write reaches its rows and what is
delivered.

`docs/admin-console.md` asks that a control be followed to the row it writes, the record it leaves
and the behaviour it changes. Registering leaves a subscriber row naming its creator and an
`ops.webhook_change` row; replacing a secret leaves a change row; switching off leaves the
deactivation and a change row naming who did it. The behaviour is the fan-out: a subscriber switched
off is no longer given a delivery when an event is written. A vault that refuses inside the
transaction leaves none of it. Each change also reaches the hash-chained ledger from `0059`'s
trigger, which `tests/unit/test_console_control_audit.py` holds, and
`brain.ops.webhook_store.A_CHANGE_IS_ATTRIBUTED_HERE_AND_CHAINED_BY_A_TRIGGER` says how.

It needs the full migration chain, which a server with pgvector builds, and skips without one; CI
has one.

Task ids: M27.8.12, M27.15.44
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.audit.ledger import AuditChain
from brain.ops.outbox import EventKind, OutboxEvent, Subscriber, deliveries_for
from brain.ops.outbox_store import subscribers
from brain.ops.webhook_admin import signing_secret_ref
from brain.ops.webhook_store import NoActiveSubscriberError, StoredWebhooks, SubscriberTakenError
from brain.session import make_session_factory
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credential_writes import entries

LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
WRITTEN = datetime(2019, 3, 4, 9, 0, 5, tzinfo=UTC)


@contextmanager
def through_head(database: str) -> Iterator[str]:
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the webhook tables need the whole chain, which CI's server builds")
        yield url


def with_store[T](url: str, work: Callable[[StoredWebhooks], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(StoredWebhooks(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def a_subscriber(subscriber_id: str = "billing_bridge") -> Subscriber:
    return Subscriber(
        subscriber_id=subscriber_id,
        endpoint="https://hooks.example.test/brain",
        secret_ref=signing_secret_ref(subscriber_id),
        kinds=(EventKind.APPROVAL_REQUESTED,),
        created_by="u_admin",
    )


def kept() -> datetime:
    return WRITTEN


def test_registering_replacing_and_switching_off_reach_the_rows_and_the_fan_out() -> None:
    """M27.8.12's proof that the three controls reach the system, in one database. Delete this and
    each of them can be false in production while the route tests stay green."""
    with through_head("brain_webhook_writes") as url:

        async def register(store: StoredWebhooks) -> Any:
            return await store.register(
                a_subscriber(),
                actor="u_admin",
                at=LONG_AGO,
                trace_id="trace-register",
                ent_hash="a" * 32,
                keep_secret=kept,
            )

        assert with_store(url, register) == WRITTEN

        async def replace(store: StoredWebhooks) -> Any:
            return await store.replace_secret(
                "billing_bridge",
                actor="u_other",
                at=LONG_AGO,
                trace_id="trace-replace",
                ent_hash="b" * 32,
                keep_secret=kept,
            )

        with_store(url, replace)

        [(created_by, secret_path, deactivated)] = sql(
            url,
            "SELECT created_by, secret_path, deactivated_at FROM ops.webhook_subscriber"
            " WHERE subscriber_id = 'billing_bridge'",
        )
        assert (created_by, secret_path, deactivated) == (
            "u_admin",
            "webhooks/billing_bridge",
            None,
        )

        async def switch(store: StoredWebhooks) -> None:
            await store.switch_off("billing_bridge", actor="u_third", at=LONG_AGO)

        with_store(url, switch)
        with pytest.raises(NoActiveSubscriberError):
            with_store(url, switch)
        changes = sql(
            url,
            "SELECT change, changed_by, secret_written_at IS NOT NULL FROM ops.webhook_change"
            " ORDER BY change",
        )
        assert changes == [
            ("registered", "u_admin", True),
            ("secret_replaced", "u_other", True),
            ("switched_off", "u_third", False),
        ]

        async def fan_out(store: StoredWebhooks) -> Any:
            engine = app_engine(url)
            try:
                async with make_session_factory(engine)() as session, session.begin():
                    return await subscribers(session)
            finally:
                await engine.dispose()

        event = OutboxEvent(
            event_id="evt-1",
            kind=EventKind.APPROVAL_REQUESTED,
            entity="approval",
            record_id="a1",
            occurred_at=LONG_AGO,
        )
        assert deliveries_for(event, with_store(url, fan_out)) == ()

        async def listed(store: StoredWebhooks) -> Any:
            return await store.registered()

        [one] = with_store(url, listed)
        assert one.subscriber.active is False
        assert {change.change.value for change in one.changes} == {
            "registered",
            "secret_replaced",
            "switched_off",
        }


def test_a_vault_that_refuses_inside_the_transaction_leaves_no_subscriber_and_no_record() -> None:
    """Delete this and the subscriber row commits before the vault is asked, and a subscriber with
    no secret is registered."""
    with through_head("brain_webhook_refused") as url:

        def refuses() -> datetime | None:
            raise RuntimeError("the vault refused")

        async def register(store: StoredWebhooks) -> Any:
            return await store.register(
                a_subscriber(),
                actor="u_admin",
                at=LONG_AGO,
                trace_id="trace-register",
                ent_hash="a" * 32,
                keep_secret=refuses,
            )

        with pytest.raises(RuntimeError):
            with_store(url, register)
        assert sql(url, "SELECT count(*) FROM ops.webhook_subscriber") == [(0,)]
        assert sql(url, "SELECT count(*) FROM ops.webhook_change") == [(0,)]

        async def ok(store: StoredWebhooks) -> Any:
            return await store.register(
                a_subscriber(),
                actor="u_admin",
                at=LONG_AGO,
                trace_id="trace-register",
                ent_hash="a" * 32,
                keep_secret=kept,
            )

        with_store(url, ok)
        with pytest.raises(SubscriberTakenError):
            with_store(url, ok)


def test_switched_back_on_and_a_given_up_delivery_replayed_once_reach_the_rows() -> None:
    """M27.15.44 against the real policies. A switched-off subscriber is switched back on and the
    change names who; one that is on is refused. A delivery given up after its attempts is put back
    to pending with one attempt left and the change names it; the same delivery given up again is
    refused a second replay by the unique index, and the list offers it no second one. Each reaches
    the hash-chained ledger through `0059`'s trigger naming its own author, and the replayed event's
    id stays in the change row and out of the ledger. Delete this and either policy, the index, the
    list's offer or the ledger entry can be wrong with every route test green."""
    from brain.ops.outbox import MAX_DELIVERY_ATTEMPTS
    from brain.ops.webhook_store import (
        NoSwitchedOffSubscriberError,
        NothingToReplayError,
        replay_handle,
    )

    with through_head("brain_webhook_switch_on_and_replay") as url:

        async def register(store: StoredWebhooks) -> Any:
            return await store.register(
                a_subscriber(),
                actor="u_admin",
                at=LONG_AGO,
                trace_id="trace-register",
                ent_hash="a" * 32,
                keep_secret=kept,
            )

        with_store(url, register)

        async def off(store: StoredWebhooks) -> None:
            await store.switch_off("billing_bridge", actor="u_admin", at=LONG_AGO)

        async def on(store: StoredWebhooks) -> None:
            await store.switch_on("billing_bridge", actor="u_other", at=WRITTEN)

        with_store(url, off)
        with_store(url, on)
        with pytest.raises(NoSwitchedOffSubscriberError):
            with_store(url, on)
        [(deactivated,)] = sql(
            url,
            "SELECT deactivated_at FROM ops.webhook_subscriber"
            " WHERE subscriber_id = 'billing_bridge'",
        )
        assert deactivated is None

        sql(
            url,
            "INSERT INTO ops.outbox_event (event_id, kind, entity, record_id, occurred_at)"
            " VALUES ('evt-given-up', 'approval.requested', 'approval', 'a1', now())",
        )
        sql(
            url,
            "INSERT INTO ops.outbox_delivery (event_id, subscriber_id, attempts, state, due_at,"
            " last_attempt_at, last_reason) VALUES ('evt-given-up', 'billing_bridge',"
            " 8, 'exhausted', now(), now(), 'refused')",
        )
        assert MAX_DELIVERY_ATTEMPTS == 8
        handle = replay_handle("evt-given-up", "billing_bridge")

        async def listed(store: StoredWebhooks) -> Any:
            return await store.registered()

        [before] = with_store(url, listed)
        assert [one.replay for one in before.deliveries] == [handle]

        async def replay(store: StoredWebhooks) -> None:
            await store.replay("billing_bridge", handle, actor="u_third", at=WRITTEN)

        with_store(url, replay)
        [(state, attempts)] = sql(
            url,
            "SELECT state, attempts FROM ops.outbox_delivery WHERE event_id = 'evt-given-up'",
        )
        assert (state, attempts) == ("pending", MAX_DELIVERY_ATTEMPTS - 1)
        sql(url, "UPDATE ops.outbox_delivery SET state = 'exhausted', attempts = 8")
        with pytest.raises(NothingToReplayError):
            with_store(url, replay)

        [again] = with_store(url, listed)
        [given_up_twice] = again.deliveries
        assert given_up_twice.state == "exhausted"
        assert given_up_twice.replay is None
        changes = sql(
            url,
            "SELECT change, changed_by, event_id FROM ops.webhook_change"
            " WHERE change IN ('switched_on', 'replayed') ORDER BY change",
        )
        assert changes == [
            ("replayed", "u_third", "evt-given-up"),
            ("switched_on", "u_other", None),
        ]
        ledger = [
            (one.actor_id, one.subject, dict(one.details))
            for one in entries(url)
            if one.action.value == "webhook"
        ]
        chain = entries(url)

    assert ledger[-2:] == [
        ("u_other", "webhook:billing_bridge", {"change": "switched_on"}),
        ("u_third", "webhook:billing_bridge", {"change": "replayed"}),
    ]
    assert all("evt-given-up" not in str(one.details) for one in chain)
    assert AuditChain(chain).verify() is None
