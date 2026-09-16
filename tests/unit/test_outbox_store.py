"""The outbox worker, held to its refusals without a server and to its locks with one.

Two halves, drawn where `tests/unit/test_delegation_sql.py` draws them. The first needs no
server: what one attempt does with a subscriber that has gone away, an address that resolves
inside, a vault that is down, a sender that says nothing and a key the operation ledger already
holds, and what is written back. The
second runs `0030` for real in a database this file creates, and asks PostgreSQL what the claim
does with two workers and what the policies do with the application role.

**The second half is the only evidence about the claim.** `FOR UPDATE SKIP LOCKED` rendered into
a string proves that SQLAlchemy can spell it; two sessions claiming the same rows prove that
neither waits and neither takes the other's.

The database is built by `tests/fixtures/scratch_postgres.py`, which says why it is stamped
at `0029` rather than built from empty.

Task ids: M17.5.1, M17.5.3, M27.8.12
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.throttle import CallOutcome, classify
from brain.ops.idempotency import OperationState
from brain.ops.outbox import (
    Attempt,
    Delivery,
    DeliveryState,
    EventKind,
    OutboxEvent,
    SignedRequest,
    Subscriber,
)
from brain.ops.outbox_store import (
    A_REDIRECT_IS_NOT_A_DELIVERY,
    DELIVERY_CONNECTOR,
    DELIVERY_TOOL,
    Claimed,
    OutboxStoreError,
    SendResult,
    SigningSecretAbsentError,
    attempt_one,
    claim_due,
    deactivate_subscriber,
    delivery_operation,
    delivery_outcome,
    dispatch_due,
    last_delivered,
    record_attempt,
    record_event,
    register_subscriber,
    subscriber_from,
    subscribers,
)
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.tables.outbox import WebhookSubscriberRow
from tests.fixtures.operation_ledger import MemoryLedger
from tests.fixtures.scratch_postgres import (
    built,
    engine,
    migrate,
    modelled,
    present,
    run,
    secured,
    shape,
    sql,
)

#: Far outside any plausible wall clock. `tests/unit/test_scope_and_capability.py` records why a
#: fixture dated near today is a clock that goes off.
NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
SECRET_REF = SecretRef(path="webhooks/sub_finance", role=VaultRole.WORKER)
SHARED_SECRET = "s_not_a_real_one_but_long_enough_to_be_one"
ENDPOINT = "https://hooks.example.com/brain"


class _Resolver:
    """Every address a name answers with, decided by the test rather than by DNS."""

    def __init__(self, *addresses: str) -> None:
        self._addresses = addresses

    def resolve(self, host: str) -> Sequence[str]:
        return self._addresses


PUBLIC = _Resolver("93.184.216.34")
INTERNAL = _Resolver("169.254.169.254")


class _Keys:
    """Hands out one signing secret and records the order of everything it is asked to do."""

    def __init__(self, events: list[str], *, down: bool = False, empty: bool = False) -> None:
        self.events = events
        self._down = down
        self._empty = empty

    def signing_secret(self, ref: SecretRef) -> str:
        if self._down:
            msg = "the vault is not answering"
            raise SecretsUnavailableError(msg)
        self.events.append("read")
        if self._empty:
            raise SigningSecretAbsentError(ref.path)
        return SHARED_SECRET


class _Sender:
    """Answers every request with one result and records what it was handed, and when."""

    def __init__(self, result: SendResult, events: list[str]) -> None:
        self.result = result
        self.events = events
        self.requests: list[SignedRequest] = []

    def send(self, request: SignedRequest) -> SendResult:
        self.events.append("send")
        self.requests.append(request)
        return self.result


def an_event(event_id: str = "ev_1") -> OutboxEvent:
    return OutboxEvent(
        event_id=event_id,
        kind=EventKind.AUTOMATION_RUN_FINISHED,
        entity="automation_run",
        record_id="run_1",
        occurred_at=NOW,
    )


def a_subscriber(subscriber_id: str = "sub_finance", *, active: bool = True) -> Subscriber:
    return Subscriber(
        subscriber_id=subscriber_id,
        endpoint=ENDPOINT,
        secret_ref=SECRET_REF,
        kinds=(EventKind.AUTOMATION_RUN_FINISHED,),
        created_by="u_weiling",
        active=active,
    )


def claimed(*, active: bool = True, attempts: int = 0) -> Claimed:
    return Claimed(
        delivery=Delivery(event_id="ev_1", subscriber_id="sub_finance", attempts=attempts),
        event=an_event(),
        subscriber=a_subscriber(active=active),
    )


def attempt(
    result: SendResult,
    *,
    active: bool = True,
    resolver: _Resolver = PUBLIC,
    down: bool = False,
    empty: bool = False,
    attempts: int = 0,
    ledger: MemoryLedger | None = None,
) -> tuple[Attempt, list[str], _Sender]:
    events: list[str] = []
    sender = _Sender(result, events)
    made = run(
        lambda: attempt_one(
            claimed(active=active, attempts=attempts),
            now=NOW,
            sender=sender,
            signing_keys=_Keys(events, down=down, empty=empty),
            resolver=resolver,
            ledger=MemoryLedger() if ledger is None else ledger,
        )
    )
    return made, events, sender


# ------------------------------------------------------------- what a sender reports
def test_a_send_result_that_says_nothing_is_refused_rather_than_read_as_delivered() -> None:
    """**The fail-open one call away.** `classify` with no status and no failure flag answers
    OK, which is asserted here as the outside fact the refusal exists for, so the refusal is
    held to the classifier rather than to its own constant. A sender that caught an exception
    and returned an empty result would otherwise mark the delivery delivered and nobody would
    be told again.

    Delete this and an empty result from a broken sender reads as a subscriber that accepted."""
    assert classify() is CallOutcome.OK

    with pytest.raises(OutboxStoreError):
        SendResult()


def test_a_send_result_with_a_status_or_a_failure_is_accepted() -> None:
    """The positive half. A `SendResult` that refused everything would satisfy the test above
    and make every delivery raise.

    Delete this and the refusal above could be satisfied by a type nobody can construct."""
    assert SendResult(status=204).status == 204
    assert SendResult(timed_out=True).timed_out
    assert SendResult(connection_failed=True).connection_failed


# ------------------------------------------------------------------- one attempt
def test_an_accepted_request_is_delivered_on_its_first_attempt() -> None:
    """The ordinary case, and the one every refusal below protects.

    Delete this and a dispatcher that parked everything would pass every other test here."""
    made, events, sender = attempt(SendResult(status=200))

    assert made.delivery.state is DeliveryState.DELIVERED
    assert made.delivery.attempts == 1
    assert len(sender.requests) == 1
    assert sender.requests[0].address == "93.184.216.34"
    assert events == ["read", "send"]


def test_a_server_error_is_retried_later_with_one_attempt_counted() -> None:
    """A 503 is a subscriber that may recover, so the delivery stays pending with a wait.

    Delete this and a dispatcher that exhausted on the first 5xx would lose every event sent
    during somebody's deploy."""
    made, _, _ = attempt(SendResult(status=503))

    assert made.delivery.state is DeliveryState.PENDING
    assert made.delivery.attempts == 1
    assert made.delay_seconds > 0


def test_a_timeout_is_retried_rather_than_read_as_a_status() -> None:
    """A request that timed out has no status, and the flag is what the classifier reads.

    Delete this and a dispatcher that dropped `timed_out` on the way to `classify` would read
    every timeout as delivered, which is the empty-result failure from the other door."""
    made, _, _ = attempt(SendResult(timed_out=True))

    assert made.delivery.state is DeliveryState.PENDING
    assert made.delivery.attempts == 1


def test_a_refused_connection_is_retried_rather_than_read_as_a_status() -> None:
    """The second flag, separately, because the two are passed separately.

    Delete this and `connection_failed` could be dropped with every other test green."""
    made, _, _ = attempt(SendResult(connection_failed=True))

    assert made.delivery.state is DeliveryState.PENDING


def test_a_client_error_exhausts_the_delivery_at_once() -> None:
    """A 410 will be a 410 eight more times. `plan_next` exhausts it and this is the wiring.

    Delete this and a status passed to the classifier wrongly would go unnoticed."""
    made, _, _ = attempt(SendResult(status=410))

    assert made.delivery.state is DeliveryState.EXHAUSTED
    assert made.delivery.attempts == 1


def test_a_stated_retry_after_reaches_the_backoff() -> None:
    """A subscriber that says when to come back is taken at its word, up to the ceiling.

    Delete this and `retry_after_seconds` could be dropped between the result and `plan_next`,
    so a subscriber asking for an hour is retried in seconds."""
    stated, _, _ = attempt(SendResult(status=429, retry_after_seconds=120.0))
    unstated, _, _ = attempt(SendResult(status=429))

    assert stated.delay_seconds == 120.0
    assert stated.delay_seconds != unstated.delay_seconds


def test_a_deactivated_subscriber_is_parked_and_nothing_is_sent() -> None:
    """**No attempt counted, no secret borrowed, no request made.** A subscriber switched off
    after the delivery was written is a refusal on this side, and counting it as an attempt
    would send somebody to look at the subscriber's server.

    Delete this and a deactivated subscriber goes on receiving events until the cap runs out."""
    made, events, sender = attempt(SendResult(status=200), active=False)

    assert made.delivery.state is DeliveryState.EXHAUSTED
    assert made.delivery.attempts == 0
    assert sender.requests == []
    assert events == []


def test_an_address_that_resolves_inside_the_network_is_parked_and_nothing_is_sent() -> None:
    """The per-delivery address rule, wired in. `169.254.169.254` is the metadata endpoint.

    Delete this and a subscriber whose name was repointed after registration makes this server
    connect to its own infrastructure, with a signature on the request."""
    made, events, sender = attempt(SendResult(status=200), resolver=INTERNAL)

    assert made.delivery.state is DeliveryState.EXHAUSTED
    assert made.delivery.attempts == 0
    assert sender.requests == []
    assert "read" not in events


def test_the_secret_is_read_before_the_request_leaves_and_nothing_sent_carries_it() -> None:
    """The order is read then send, and the request the sender is handed holds a signature and
    never the secret it was computed with, in its body or in any header.

    Delete this and a sender handed the secret beside the request holds a live credential for as
    long as the slowest subscriber takes to answer."""
    _, events, sender = attempt(SendResult(status=200))

    assert events.index("read") < events.index("send")
    sent = sender.requests[0]
    assert SHARED_SECRET.encode() not in sent.body
    assert all(SHARED_SECRET not in value for value in sent.headers.values())


def test_a_subscriber_whose_secret_the_vault_does_not_hold_is_parked_and_nothing_is_sent() -> None:
    """The vault answered that this one slot is empty: that subscriber's fault, parked with no
    attempt counted, and a sentence saying where to fix it.

    Delete this and one subscriber registered before its secret was written stops every other
    subscriber's delivery, because the absence would stop the batch as an outage does."""
    made, _, sender = attempt(SendResult(status=200), empty=True)

    assert made.delivery.state is DeliveryState.EXHAUSTED
    assert made.delivery.attempts == 0
    assert sender.requests == []
    assert "Webhooks screen" in made.reason


def test_a_redirect_is_a_refusal_and_not_an_acceptance() -> None:
    """A 3xx exhausts the delivery. `classify` reads it as OK, asserted here as the outside fact
    the refusal exists for, so the test is held to the classifier rather than to its own constant.

    Delete this and a subscriber whose server redirects is marked delivered for every event it
    never received."""
    assert classify(status=302) is CallOutcome.OK
    assert delivery_outcome(SendResult(status=302)) is CallOutcome.REJECTED
    assert delivery_outcome(SendResult(status=299)) is CallOutcome.OK
    assert delivery_outcome(SendResult(status=400)) is CallOutcome.REJECTED
    assert "redirect" in A_REDIRECT_IS_NOT_A_DELIVERY

    made, _, _ = attempt(SendResult(status=308))
    assert made.delivery.state is DeliveryState.EXHAUSTED


# -------------------------------------------------------- the door every request goes through
def test_every_request_is_made_through_the_operation_ledger_and_settled_there() -> None:
    """One attempt, one record, moved to sent before the request and to succeeded after it.

    Delete this and a dispatcher that called the sender beside the ledger rather than inside
    `issue_once` would still deliver, and a worker dying after the subscriber accepted would send
    the event again with nothing recording that the first request had left."""
    ledger = MemoryLedger()
    made, _, sender = attempt(SendResult(status=200), ledger=ledger)

    key = delivery_operation(claimed().delivery, a_subscriber()).key
    assert made.delivery.state is DeliveryState.DELIVERED
    assert len(sender.requests) == 1
    assert ledger.moves == [(key, OperationState.SENT), (key, OperationState.SUCCEEDED)]
    record = ledger.records[key]
    assert (record.connector, record.tool) == (DELIVERY_CONNECTOR, DELIVERY_TOOL)
    assert record.principal_id == a_subscriber().created_by


def test_an_attempt_an_earlier_worker_sent_and_the_subscriber_accepted_is_not_sent_again() -> None:
    """**The duplicate this side can avoid.** A worker died after the ledger recorded the
    acceptance and before the delivery row committed, so the row is still pending at the same
    count. The next worker finds the attempt's key succeeded, records the delivery and sends
    nothing.

    Delete this and every crash in that window is a second copy of an event the subscriber
    already has, which the ledger knew and was not asked."""
    ledger = MemoryLedger()
    key = delivery_operation(claimed().delivery, a_subscriber()).key
    attempt(SendResult(status=200), ledger=ledger)
    assert ledger.records[key].state is OperationState.SUCCEEDED

    made, events, sender = attempt(SendResult(status=200), ledger=ledger)

    assert sender.requests == []
    assert "send" not in events
    assert made.delivery.state is DeliveryState.DELIVERED
    assert made.delivery.attempts == 1
    assert "nothing was sent again" in made.reason


def test_an_attempt_sent_and_never_settled_counts_and_the_next_goes_under_its_own_key() -> None:
    """A worker died between the request leaving and the answer being recorded. This pass sends
    nothing under that key, counts the attempt as unanswered and leaves the delivery pending, and
    the attempt after it is a key the ledger has never seen, so it is sent.

    Delete this and either the unknown attempt is sent again under its own key, which is the
    door refusing nothing, or the delivery is stuck for ever on a key that can never be won."""
    ledger = MemoryLedger()
    first = delivery_operation(claimed().delivery, a_subscriber())
    ledger.claim(first)
    ledger.win(first.key)

    made, _, sender = attempt(SendResult(status=200), ledger=ledger)

    assert sender.requests == []
    assert made.delivery.state is DeliveryState.PENDING
    assert made.delivery.attempts == 1
    assert made.delay_seconds > 0

    retried, _, again = attempt(SendResult(status=200), ledger=ledger, attempts=1)
    assert len(again.requests) == 1
    assert retried.delivery.state is DeliveryState.DELIVERED


def test_a_retry_after_a_server_error_is_sent_again_under_a_key_of_its_own() -> None:
    """Attempt one answered 503 and settled its key; attempt two is a new key and is sent.

    Delete this and a key per delivery rather than per attempt passes every other test here, and
    the first 503 any subscriber returns is the last request it is ever sent."""
    ledger = MemoryLedger()
    first, _, sent_first = attempt(SendResult(status=503), ledger=ledger)
    second, _, sent_second = attempt(SendResult(status=200), ledger=ledger, attempts=1)

    assert len(sent_first.requests) == 1
    assert len(sent_second.requests) == 1
    assert first.delivery.state is DeliveryState.PENDING
    assert second.delivery.state is DeliveryState.DELIVERED
    assert len(ledger.records) == 2


def test_one_event_to_two_subscribers_is_two_keys_and_both_are_sent() -> None:
    """The subscriber is part of the key, so the second subscriber's first attempt is not the
    first subscriber's.

    Delete this and a key built from the event alone delivers each event to whichever subscriber
    the claim happened to reach first, and to nobody else."""
    ledger = MemoryLedger()
    events: list[str] = []
    sender = _Sender(SendResult(status=200), events)

    async def both() -> None:
        for subscriber_id in ("sub_finance", "sub_sales"):
            subscriber = replace(a_subscriber(), subscriber_id=subscriber_id)
            await attempt_one(
                Claimed(
                    delivery=Delivery(event_id="ev_1", subscriber_id=subscriber_id),
                    event=an_event(),
                    subscriber=subscriber,
                ),
                now=NOW,
                sender=sender,
                signing_keys=_Keys(events),
                resolver=PUBLIC,
                ledger=ledger,
            )

    run(both)

    assert len(sender.requests) == 2
    assert len(ledger.records) == 2


def test_the_same_attempt_derives_the_same_key_and_the_next_attempt_another() -> None:
    """Derived from the row, never minted: the key for an attempt is a function of the event, the
    subscriber, who set it up and the attempt number.

    Delete this and a key that drew on anything else would be a new key on every pass, which is
    the door letting through exactly the repeat it exists to stop."""
    first = Delivery(event_id="ev_1", subscriber_id="sub_finance")
    one = delivery_operation(first, a_subscriber())
    two = delivery_operation(first, a_subscriber())
    later = delivery_operation(replace(first, attempts=1), a_subscriber())

    assert one.key == two.key
    assert later.key != one.key


def test_a_vault_that_cannot_issue_stops_the_batch_rather_than_parking_the_delivery() -> None:
    """An outage in the vault is not the subscriber's failure, so nothing is written for it.

    Delete this and a handler that caught the outage and parked the delivery would exhaust a
    day of events over an incident in somebody else's system."""
    events: list[str] = []
    sender = _Sender(SendResult(status=200), events)

    with pytest.raises(SecretsUnavailableError):
        run(
            lambda: attempt_one(
                claimed(),
                now=NOW,
                sender=sender,
                signing_keys=_Keys(events, down=True),
                resolver=PUBLIC,
                ledger=MemoryLedger(),
            )
        )
    assert sender.requests == []


# ------------------------------------------------------------ rows into domain values
def test_a_subscriber_row_is_active_exactly_when_it_has_no_deactivation_instant() -> None:
    """The producer, from a raw row, rather than a `Subscriber` built with the answer already set.

    Delete this and `subscriber_from` could read every row as active, so a switched-off
    subscriber keeps receiving events with the console saying it is off."""
    row = WebhookSubscriberRow(
        subscriber_id="sub_finance",
        endpoint=ENDPOINT,
        secret_path=SECRET_REF.path,
        secret_role=SECRET_REF.role.value,
        kinds=[EventKind.AUTOMATION_RUN_FINISHED.value],
        created_by="u_weiling",
        deactivated_at=None,
    )
    assert subscriber_from(row).active

    row.deactivated_at = NOW
    assert not subscriber_from(row).active


def test_an_event_read_in_another_time_zone_is_the_same_bytes_as_the_one_written() -> None:
    """The producer, from a raw row whose instant came back in a session zone eight hours east:
    the event it reads serialises exactly as the event that was written.

    Delete this and one event is different bytes on two workers whose database sessions have
    different time zones, which a receiver comparing or storing bodies sees as two events."""
    from datetime import timedelta as hours
    from datetime import timezone

    from brain.ops.outbox import serialise
    from brain.ops.outbox_store import event_from
    from brain.tables.outbox import OutboxEventRow

    east = timezone(hours(hours=8))
    row = OutboxEventRow(
        event_id="ev_1",
        kind=EventKind.AUTOMATION_RUN_FINISHED.value,
        entity="automation_run",
        record_id="run_1",
        occurred_at=NOW.astimezone(east),
        attributes={},
    )

    assert serialise(event_from(row)) == serialise(an_event())


# ----------------------------------------------------------- refusals before the SQL
class _Recording(AsyncSession):
    """A session that records statements and answers with a fixed row count."""

    def __init__(self, *, rowcount: int = 1) -> None:
        self.statements: list[Any] = []
        self.added: list[Any] = []
        self._rowcount = rowcount

    async def execute(self, statement: Any, params: Any = None, **_: Any) -> Any:
        self.statements.append(statement)
        return _Answer(self._rowcount)

    def add(self, instance: Any, _warn: bool = True) -> None:
        self.added.append(instance)

    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        return None


class _Answer:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount

    def all(self) -> list[Any]:
        return []


def test_a_claim_of_no_rows_is_refused() -> None:
    """A claim of zero holds a transaction open to claim nothing.

    Delete this and a worker configured with a limit of zero ticks for ever and sends nothing,
    looking from outside exactly like an outbox with nothing in it."""
    with pytest.raises(OutboxStoreError):
        run(lambda: claim_due(_Recording(), now=NOW, limit=0))
    run(lambda: claim_due(_Recording(), now=NOW, limit=1))


def test_a_claim_at_a_naive_instant_is_refused() -> None:
    """A naive instant compares wrongly against every `due_at` in the table.

    Delete this and a caller passing `datetime.now()` claims rows by an offset nobody chose."""
    with pytest.raises(OutboxStoreError):
        run(lambda: claim_due(_Recording(), now=NOW.replace(tzinfo=None), limit=1))


def test_a_claim_locks_the_delivery_rows_and_skips_what_another_worker_holds() -> None:
    """The statement's lock clause, read off the statement object rather than its rendering.

    The live test below is the evidence that the lock does what it says; this is what names
    which half broke when it fails, because a missing `OF` and a missing `SKIP LOCKED` fail
    the live test the same way.

    Delete this and the claim could lock the event and subscriber rows too, which serialises
    two workers delivering two different events to one subscriber."""
    session = _Recording()
    run(lambda: claim_due(session, now=NOW, limit=5))
    lock = session.statements[0]._for_update_arg

    assert lock is not None
    assert lock.skip_locked
    assert [one.name for one in lock.of] == ["outbox_delivery"]


def _values(statement: Any) -> dict[str, Any]:
    return {column.key: value.value for column, value in statement._values.items()}


def test_an_attempt_writes_the_instant_it_was_made() -> None:
    """A delivery that was attempted says when, and the check constraint refuses it otherwise.

    Delete this and `last_attempt_at` could be left unwritten, which the database would refuse
    on the first delivery and which nothing without a server would notice."""
    session = _Recording()
    before = Delivery(event_id="ev_1", subscriber_id="sub_finance")
    after = Attempt(
        delivery=Delivery(
            event_id="ev_1", subscriber_id="sub_finance", attempts=1, state=DeliveryState.DELIVERED
        ),
        delay_seconds=0.0,
        reason="accepted on attempt 1",
    )
    run(lambda: record_attempt(session, before, after, now=NOW))

    written = _values(session.statements[0])
    assert written["last_attempt_at"] == NOW
    assert written["attempts"] == 1
    assert written["state"] == DeliveryState.DELIVERED.value


def test_a_parked_delivery_records_no_attempt_instant() -> None:
    """A delivery stopped on this side was never sent, so it carries no instant of sending.

    Delete this and the console says when a request went to a deactivated subscriber, which it
    never did."""
    session = _Recording()
    before = Delivery(event_id="ev_1", subscriber_id="sub_finance")
    parked = Attempt(
        delivery=Delivery(
            event_id="ev_1", subscriber_id="sub_finance", state=DeliveryState.EXHAUSTED
        ),
        delay_seconds=0.0,
        reason="not sent",
    )
    run(lambda: record_attempt(session, before, parked, now=NOW))

    assert "last_attempt_at" not in _values(session.statements[0])


def test_a_row_somebody_else_moved_is_refused_rather_than_overwritten() -> None:
    """No row matched the state and count it was claimed at, so something else moved it.

    Delete this and a second writer silently overwrites a delivered row back to pending."""
    before = Delivery(event_id="ev_1", subscriber_id="sub_finance")
    after = Attempt(
        delivery=Delivery(event_id="ev_1", subscriber_id="sub_finance", attempts=1),
        delay_seconds=1.0,
        reason="x",
    )

    with pytest.raises(OutboxStoreError):
        run(lambda: record_attempt(_Recording(rowcount=0), before, after, now=NOW))


def test_a_subscriber_arriving_switched_off_is_not_registered() -> None:
    """A switched-off registration is a subscription that receives nothing and looks working.

    Delete this and the insert policy is the only refusal, with a message about a policy."""
    with pytest.raises(OutboxStoreError):
        run(lambda: register_subscriber(_Recording(), a_subscriber(active=False)))

    session = _Recording()
    run(lambda: register_subscriber(session, a_subscriber()))
    assert len(session.added) == 1


def test_a_second_deactivation_is_refused_rather_than_moving_the_instant() -> None:
    """The instant is the record of when it stopped. Refused when no active row matched.

    Delete this and whoever clicks second moves the record of when a subscription ended."""
    with pytest.raises(OutboxStoreError):
        run(lambda: deactivate_subscriber(_Recording(rowcount=0), "sub_finance", at=NOW))
    run(lambda: deactivate_subscriber(_Recording(rowcount=1), "sub_finance", at=NOW))


# ------------------------------------------------------- what only a server can answer
TABLES = ("ops.webhook_subscriber", "ops.outbox_event", "ops.outbox_delivery")


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    """A database of this file's own, built through `0030`, dropped afterwards."""
    with built("brain_outbox_store_check", "0030") as url:
        yield url


@pytest.fixture
def empty(server: str) -> str:
    """The outbox emptied, so one test's rows are not another test's claim."""
    sql(server, "TRUNCATE ops.outbox_delivery, ops.outbox_event, ops.webhook_subscriber")
    return server


async def _seed(url: str, *, subscribers_: Sequence[Subscriber], event: OutboxEvent) -> None:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session, session.begin():
            for one in subscribers_:
                await register_subscriber(session, one)
            await record_event(session, event, subscribers_)
    finally:
        await made.dispose()


def test_two_workers_claim_different_deliveries_and_neither_waits_for_the_other(empty: str) -> None:
    """**The claim's whole reason for being written this way**, measured with two sessions.

    The first worker claims one delivery and holds its transaction open. The second, with a
    lock timeout of two seconds, claims everything it can. It must return at once with the
    other two and never the first's: without `SKIP LOCKED` it waits on the locked row and the
    lock timeout raises, and without the lock at all it takes the first worker's delivery too.

    Delete this and a claim that serialises every worker, or one that sends an event twice
    from two live workers, passes every test in this file."""
    trio = [a_subscriber(f"sub_{n}") for n in (1, 2, 3)]
    run(lambda: _seed(empty, subscribers_=trio, event=an_event("ev_race")))

    async def race() -> tuple[set[str], set[str]]:
        made = engine(empty)
        try:
            maker = async_sessionmaker(made)
            async with maker() as first, first.begin():
                held = await claim_due(first, now=NOW, limit=1)
                async with maker() as second, second.begin():
                    await second.execute(text("SET LOCAL lock_timeout = '2s'"))
                    rest = await claim_due(second, now=NOW, limit=10)
                return (
                    {one.delivery.subscriber_id for one in held},
                    {one.delivery.subscriber_id for one in rest},
                )
        finally:
            await made.dispose()

    held, rest = run(race)
    assert len(held) == 1
    assert len(rest) == 2
    assert held.isdisjoint(rest)
    assert held | rest == {"sub_1", "sub_2", "sub_3"}


def test_a_claim_takes_only_pending_deliveries_that_are_due(empty: str) -> None:
    """Three rows and one answer: due and pending is claimed; not yet due, and already settled
    but long past due, are not.

    Delete this and a claim that dropped either half of its WHERE clause would resend settled
    deliveries or send retries before their wait was up."""
    trio = [a_subscriber(f"sub_{n}") for n in ("due", "later", "done")]
    run(lambda: _seed(empty, subscribers_=trio, event=an_event("ev_due")))
    sql(
        empty,
        "UPDATE ops.outbox_delivery SET due_at = %s WHERE subscriber_id = 'sub_later'",
        NOW + timedelta(hours=1),
    )
    sql(
        empty,
        "UPDATE ops.outbox_delivery SET state = 'delivered', attempts = 1, last_attempt_at = %s, "
        "due_at = %s WHERE subscriber_id = 'sub_done'",
        NOW - timedelta(days=1),
        NOW - timedelta(days=1),
    )
    sql(empty, "UPDATE ops.outbox_delivery SET due_at = %s WHERE subscriber_id = 'sub_due'", NOW)

    async def claim() -> list[str]:
        made = engine(empty)
        try:
            async with async_sessionmaker(made)() as session, session.begin():
                claimed_now = await claim_due(session, now=NOW, limit=10)
                return [one.delivery.subscriber_id for one in claimed_now]
        finally:
            await made.dispose()

    assert run(claim) == ["sub_due"]


def test_a_dispatched_delivery_is_written_back_with_its_attempt(empty: str) -> None:
    """End to end against the server, as the application role, with a fake on the wire.

    Delete this and every row-writing test in this file is a test of a statement object that
    PostgreSQL has never been shown."""
    run(lambda: _seed(empty, subscribers_=[a_subscriber()], event=an_event("ev_sent")))
    events: list[str] = []

    async def dispatch() -> tuple[tuple[Attempt, ...], dict[str, datetime]]:
        made = engine(empty)
        try:
            maker = async_sessionmaker(made)
            async with maker() as session, session.begin():
                await session.execute(text("SET LOCAL ROLE brain_app"))
                settled = await dispatch_due(
                    session,
                    await claim_due(session, now=NOW, limit=10),
                    now=NOW,
                    sender=_Sender(SendResult(status=202), events),
                    signing_keys=_Keys(events),
                    resolver=PUBLIC,
                    ledger=MemoryLedger(),
                )
            async with maker() as session:
                return settled, await last_delivered(session)
        finally:
            await made.dispose()

    settled, delivered = run(dispatch)
    assert [one.delivery.state for one in settled] == [DeliveryState.DELIVERED]
    assert sql(
        empty,
        "SELECT state, attempts, last_attempt_at FROM ops.outbox_delivery "
        "WHERE event_id = 'ev_sent'",
    ) == [("delivered", 1, NOW)]
    assert delivered == {"sub_finance": NOW}


def test_a_worker_holding_a_stale_count_cannot_overwrite_the_row(empty: str) -> None:
    """The WHERE clause on the write, against a row whose count moved underneath it.

    Delete this and the attempt count in the WHERE clause could be dropped with no test
    noticing, because every other write here is made by the worker that claimed the row."""
    run(lambda: _seed(empty, subscribers_=[a_subscriber()], event=an_event("ev_stale")))
    sql(
        empty,
        "UPDATE ops.outbox_delivery SET attempts = 1, last_attempt_at = %s "
        "WHERE event_id = 'ev_stale'",
        NOW,
    )
    stale = Delivery(event_id="ev_stale", subscriber_id="sub_finance", attempts=0)
    moved = Attempt(
        delivery=Delivery(event_id="ev_stale", subscriber_id="sub_finance", attempts=1),
        delay_seconds=30.0,
        reason="retry",
    )

    async def write() -> None:
        made = engine(empty)
        try:
            async with async_sessionmaker(made)() as session, session.begin():
                await record_attempt(session, stale, moved, now=NOW)
        finally:
            await made.dispose()

    with pytest.raises(OutboxStoreError):
        run(write)


def test_the_application_role_cannot_move_a_settled_delivery(empty: str) -> None:
    """The UPDATE policy reads the row before the change. A delivered row is history.

    The sibling half is in the same test: a pending row is moved by the same role, so a
    policy that refused every update fails here rather than passing.

    Delete this and a hand-written UPDATE by the application can reopen a delivered event."""
    pair = [a_subscriber("sub_open"), a_subscriber("sub_settled")]
    run(lambda: _seed(empty, subscribers_=pair, event=an_event("ev_policy")))
    sql(
        empty,
        "UPDATE ops.outbox_delivery SET state = 'delivered', attempts = 1, last_attempt_at = %s "
        "WHERE subscriber_id = 'sub_settled'",
        NOW,
    )

    with psycopg.connect(empty) as conn:
        conn.execute("SET ROLE brain_app")
        settled = conn.execute(
            "UPDATE ops.outbox_delivery SET state = 'pending' WHERE subscriber_id = 'sub_settled'"
        ).rowcount
        open_ = conn.execute(
            "UPDATE ops.outbox_delivery SET due_at = due_at WHERE subscriber_id = 'sub_open'"
        ).rowcount
        conn.rollback()

    assert settled == 0
    assert open_ == 1


def test_the_application_role_may_append_an_event_and_may_not_amend_one(empty: str) -> None:
    """SELECT and INSERT and nothing else. The insert is the positive half.

    Delete this and an UPDATE grant added to the event table would let one id name two
    different facts on two attempts."""
    with psycopg.connect(empty) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute(
            "INSERT INTO ops.outbox_event (event_id, kind, entity, record_id, occurred_at) "
            "VALUES ('ev_role', 'operation.settled', 'operation', 'op_1', %s)",
            (NOW,),
        )
        conn.commit()
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE ops.outbox_event SET record_id = 'op_2' WHERE event_id = 'ev_role'"
            )
        conn.rollback()


def test_a_subscriber_is_switched_off_once_and_stays_off(empty: str) -> None:
    """Registered and deactivated through the store as the application role, then refused a
    second deactivation by the store.

    Delete this and deactivation is one way only in a docstring."""

    async def switch_off() -> tuple[Subscriber, ...]:
        made = engine(empty)
        try:
            maker = async_sessionmaker(made)
            async with maker() as session, session.begin():
                await session.execute(text("SET LOCAL ROLE brain_app"))
                await register_subscriber(session, a_subscriber())
            async with maker() as session, session.begin():
                await session.execute(text("SET LOCAL ROLE brain_app"))
                await deactivate_subscriber(session, "sub_finance", at=NOW)
            async with maker() as session, session.begin():
                await session.execute(text("SET LOCAL ROLE brain_app"))
                with pytest.raises(OutboxStoreError):
                    await deactivate_subscriber(session, "sub_finance", at=NOW + timedelta(days=1))
            async with maker() as session:
                return await subscribers(session)
        finally:
            await made.dispose()

    found = run(switch_off)
    assert [(one.subscriber_id, one.active) for one in found] == [("sub_finance", False)]
    assert sql(empty, "SELECT deactivated_at FROM ops.webhook_subscriber") == [(NOW,)]


def test_the_store_refuses_a_second_deactivation_even_on_a_connection_policies_do_not_bind(
    empty: str,
) -> None:
    """Run as the table owner, which row-level security does not bind, so the store's own WHERE
    clause is the only thing matching an active row. The test above runs as the application
    role, where the policy refuses the second write too, and so could not tell the two apart.

    Delete this and the WHERE clause can go, and a maintenance script run as the owner moves the
    instant a subscription ended to whenever the script ran."""

    async def twice() -> None:
        made = engine(empty)
        try:
            maker = async_sessionmaker(made)
            async with maker() as session, session.begin():
                await register_subscriber(session, a_subscriber())
                await deactivate_subscriber(session, "sub_finance", at=NOW)
            async with maker() as session, session.begin():
                with pytest.raises(OutboxStoreError):
                    await deactivate_subscriber(session, "sub_finance", at=NOW + timedelta(days=1))
        finally:
            await made.dispose()

    run(twice)
    assert sql(empty, "SELECT deactivated_at FROM ops.webhook_subscriber") == [(NOW,)]


def test_the_application_role_cannot_update_a_deactivated_subscriber(empty: str) -> None:
    """The UPDATE policy, past the store: a switched-off row matches nothing, an active one does.

    Delete this and a hand-written UPDATE by the application can switch a subscriber back on,
    which is a new decision about where data goes made without anybody's name on it."""
    run(
        lambda: _seed(
            empty,
            subscribers_=[a_subscriber("sub_on"), a_subscriber("sub_off")],
            event=an_event("ev_sub_policy"),
        )
    )
    sql(
        empty,
        "UPDATE ops.webhook_subscriber SET deactivated_at = %s WHERE subscriber_id = 'sub_off'",
        NOW,
    )

    with psycopg.connect(empty) as conn:
        conn.execute("SET ROLE brain_app")
        off = conn.execute(
            "UPDATE ops.webhook_subscriber SET deactivated_at = NULL "
            "WHERE subscriber_id = 'sub_off'"
        ).rowcount
        on = conn.execute(
            "UPDATE ops.webhook_subscriber SET endpoint = endpoint WHERE subscriber_id = 'sub_on'"
        ).rowcount
        conn.rollback()

    assert off == 0
    assert on == 1


def test_the_application_role_may_schedule_a_delivery_only_before_it_is_attempted(
    empty: str,
) -> None:
    """The INSERT policy, past the store: a row written already delivered is refused, a pending
    row with no attempts is written.

    Delete this and a delivery can be inserted as delivered, so an event is recorded as sent to a
    subscriber that was never sent anything."""
    run(lambda: _seed(empty, subscribers_=[a_subscriber()], event=an_event("ev_first")))
    sql(
        empty,
        "INSERT INTO ops.outbox_event (event_id, kind, entity, record_id, occurred_at) "
        "VALUES ('ev_second', 'operation.settled', 'operation', 'op_1', %s)",
        NOW,
    )
    insert = (
        "INSERT INTO ops.outbox_delivery "
        "(event_id, subscriber_id, attempts, state, last_attempt_at) "
        "VALUES ('ev_second', 'sub_finance', %s, %s, %s)"
    )

    with psycopg.connect(empty) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(insert, (1, "delivered", NOW))
        conn.rollback()
        conn.execute("SET ROLE brain_app")
        conn.execute(insert, (0, "pending", None))
        conn.commit()


def test_last_delivered_counts_only_deliveries_that_were_accepted(empty: str) -> None:
    """One subscriber accepted a delivery yesterday; another failed an attempt today. Only the
    first is in the answer, at yesterday.

    Delete this and a failed attempt reads on the console as the last successful delivery, which
    is the quiet integration looking healthy."""
    pair = [a_subscriber("sub_ok"), a_subscriber("sub_failing")]
    run(lambda: _seed(empty, subscribers_=pair, event=an_event("ev_last")))
    sql(
        empty,
        "UPDATE ops.outbox_delivery SET state = 'delivered', attempts = 1, last_attempt_at = %s "
        "WHERE subscriber_id = 'sub_ok'",
        NOW - timedelta(days=1),
    )
    sql(
        empty,
        "UPDATE ops.outbox_delivery SET attempts = 1, last_attempt_at = %s "
        "WHERE subscriber_id = 'sub_failing'",
        NOW,
    )

    async def read() -> dict[str, datetime]:
        made = engine(empty)
        try:
            async with async_sessionmaker(made)() as session:
                return await last_delivered(session)
        finally:
            await made.dispose()

    assert run(read) == {"sub_ok": NOW - timedelta(days=1)}


def test_row_level_security_is_on_for_every_outbox_table(server: str) -> None:
    """`brain.ops.sweeps.sweep_rls` asks the same question of a whole database. This asks it of
    the three tables `0030` builds.

    Delete this and a table created without its ENABLE statement is found by CI only."""
    assert secured(server, TABLES) == dict.fromkeys(TABLES, True)


def test_the_migration_builds_exactly_what_the_models_declare(server: str) -> None:
    """Every constraint by name and definition, every index and every column, compared between
    the database `0030` built and one built from `brain.tables.outbox` directly.

    **This is the test that found the names doubled.** Alembic applies the naming convention on
    top of whatever name a migration passes, so `ck_outbox_event_kind` written out in full
    arrived as `ck_outbox_event_ck_outbox_event_kind`, and one of them was truncated at
    PostgreSQL's sixty-three characters. Every other test passed against that database.

    Delete this and the migration and the models can disagree about a constraint's name, which
    is the one thing a later migration dropping it has to get right."""
    with modelled("brain_outbox_store_modelled", TABLES) as from_models:
        assert shape(server, TABLES) == shape(from_models, TABLES)


def test_the_migration_comes_down_and_goes_back_up() -> None:
    """Upgrade, downgrade and upgrade again, in a database of its own.

    Asked of the tables themselves after each step rather than of alembic's version table,
    because a downgrade that recorded itself and dropped nothing would leave the version right
    and the tables standing.

    Delete this and a downgrade that drops the tables in the wrong order, which the foreign keys
    refuse, is found on the day somebody needs to roll a release back."""
    with built("brain_outbox_store_round_trip", "0030") as url:
        assert present(url, TABLES) == set(TABLES)
        migrate("brain_outbox_store_round_trip", "downgrade", "0029")
        assert present(url, TABLES) == set()
        migrate("brain_outbox_store_round_trip", "upgrade", "0030")
        assert present(url, TABLES) == set(TABLES)
