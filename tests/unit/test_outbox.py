"""Outbound webhooks: what leaves the boundary, how it is signed, and what happens on failure.

Two rules carry most of this file. **An event is identifiers and a kind**, because a payload
that leaves the permission boundary is readable for ever by whoever holds the endpoint with
no re-check. And **delivery is at least once**, which is a guarantee stated rather than
improved: the subscriber deduplicates on the event id, and no arrangement on this side can
turn a webhook into exactly-once.

The signing tests are round trips through `brain.channels.webhook.verify` rather than
comparisons against a literal digest. That is deliberate: the claim being tested is that
outbound signing and inbound verification are one construction, and a literal would still
match after the two had drifted apart.

Task ids: M17.5.1, M17.5.2, M17.5.3
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from brain.channels.webhook import WebhookRefusedError, verify
from brain.connectors.throttle import CallOutcome, retry_delay
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops import outbox
from brain.ops.idempotency import OperationState
from brain.ops.limits import BACKOFF_AFTER_REFUSALS, MAX_BACKOFF_SECONDS
from brain.ops.outbox import (
    MANAGE_SUBSCRIBERS,
    MAX_DELIVERY_ATTEMPTS,
    MAX_IDENTIFIER_CHARS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    Delivery,
    DeliveryState,
    EventKind,
    OutboxError,
    OutboxEvent,
    Subscriber,
    assert_deliverable,
    backoff_is_engaged,
    deliveries_for,
    may_manage,
    plan_next,
    retry_window_seconds,
    serialise,
    signature_matches,
    signed_request,
)
from brain.ops.queue import MAX_ARGUMENT_CHARS
from brain.ops.secrets import SecretRef, VaultRole
from brain.tools.fetch import Fetchable

NOW = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
SECRET_REF = SecretRef(path="webhooks/creds/finance", role=VaultRole.APPLICATION)
SHARED_SECRET = "s_not_a_real_one"
PUBLIC_ENDPOINT = "https://hooks.example.com/brain"


class _Resolver:
    """Every address a name answers with, decided by the test rather than by DNS.

    A fake rather than the real resolver for the reason `brain.tools.fetch.Resolver` gives:
    the interesting cases are a name with one public and one private record, and a name that
    answers differently on the second lookup, and neither is reachable against real DNS.
    """

    def __init__(self, *addresses: str) -> None:
        self._addresses = addresses

    def resolve(self, host: str) -> Sequence[str]:
        return self._addresses


PUBLIC = _Resolver("93.184.216.34")
INTERNAL = _Resolver("169.254.169.254")


def an_event(**overrides: object) -> OutboxEvent:
    defaults: dict[str, object] = {
        "event_id": "ev_01J8Z",
        "kind": EventKind.AUTOMATION_RUN_FINISHED,
        "entity": "automation_run",
        "record_id": "run_2026_09_07",
        "occurred_at": NOW,
    }
    defaults.update(overrides)
    return OutboxEvent(**defaults)  # type: ignore[arg-type]


def a_subscriber(**overrides: object) -> Subscriber:
    defaults: dict[str, object] = {
        "subscriber_id": "sub_finance",
        "endpoint": PUBLIC_ENDPOINT,
        "secret_ref": SECRET_REF,
        "kinds": (EventKind.AUTOMATION_RUN_FINISHED,),
        "created_by": "u_weiling",
    }
    defaults.update(overrides)
    return Subscriber(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------- what leaves the boundary (M17.5.1)
def test_an_event_says_that_something_happened_and_which_record_it_happened_to() -> None:
    """The positive case, and the shape every refusal below is protecting. Without it, an
    `OutboxEvent` that refused everything would satisfy the whole of the rest of this
    section."""
    body = json.loads(serialise(an_event()))
    assert body["kind"] == EventKind.AUTOMATION_RUN_FINISHED.value
    assert body["entity"] == "automation_run"
    assert body["record_id"] == "run_2026_09_07"
    assert body["event_id"] == "ev_01J8Z"


def test_an_event_with_no_id_cannot_be_deduplicated_and_is_refused() -> None:
    """Delivery is at least once, so the id is the only thing a subscriber can drop a second
    copy on. Delete this and an event with an empty id is written, delivered twice, and the
    subscriber processes both."""
    with pytest.raises(OutboxError, match="deduplicated"):
        an_event(event_id="  ")


def test_an_attribute_long_enough_to_be_content_is_refused() -> None:
    """The queue's rule, asked for the third time and for the strictest reason: a job row and
    a checkpoint stay inside a database we operate, and this leaves the permission boundary
    completely. Delete this and a ticket body travels to whoever holds the endpoint."""
    assert MAX_IDENTIFIER_CHARS == MAX_ARGUMENT_CHARS
    with pytest.raises(OutboxError, match="content rather than a reference"):
        an_event(attributes={"note": "x" * (MAX_IDENTIFIER_CHARS + 1)})
    assert an_event(attributes={"note": "x" * MAX_IDENTIFIER_CHARS})


def test_an_attribute_on_the_permanent_denylist_is_refused() -> None:
    """`brain.core.projection` keeps these fields out of a projection we store. Sending one
    is worse than storing it, because there is no revocation and no retention on the far
    side. Delete this and `salary` can be attached to an event as an identifier."""
    with pytest.raises(OutboxError, match="denylist"):
        an_event(attributes={"salary": "84000"})


def test_an_attribute_that_is_a_container_is_refused_whatever_its_length() -> None:
    """A short list is where somebody puts records while meaning to put a reference, which
    is the rule `brain.ops.checkpoints` reached from the same direction. Checked at runtime
    although the annotation forbids it, because the call site that matters is the untyped
    one where a database row is unpacked into this."""
    with pytest.raises(OutboxError, match="container"):
        an_event(attributes={"ids": ["a", "b"]})


def test_an_event_carries_a_timezone_on_when_it_happened() -> None:
    """A subscriber orders on this, and delivery is unordered, so it is the only thing that
    can put two events back in sequence. Two naive timestamps from two hosts cannot be
    compared, which is the only thing the field is for."""
    with pytest.raises(OutboxError, match="timezone"):
        an_event(occurred_at=datetime(2026, 9, 7, 10, 0))


def test_reordering_the_attributes_does_not_change_the_bytes() -> None:
    """The bytes are what is signed. A serialisation that depended on mapping order would
    produce a different signature for the same event on a retry, and the subscriber would
    read it as a wrong secret."""
    forwards = serialise(an_event(attributes={"a": "1", "b": "2"}))
    backwards = serialise(an_event(attributes={"b": "2", "a": "1"}))
    assert forwards == backwards


# -------------------------------------------------------- signing (M17.5.2)
def _target() -> Fetchable:
    return assert_deliverable(a_subscriber(), PUBLIC)


def test_a_signed_request_is_one_the_inbound_verifier_accepts() -> None:
    """The strongest claim in this file: outbound signing and inbound verification are one
    construction, not two that happen to agree today. Asserting against a literal digest
    would still pass after the two had drifted, because the literal would have been copied
    from whichever side was changed last.

    Delete this and `signature_for` can be rewritten to sign the body alone, which every
    other test here would still pass."""
    request = signed_request(
        event=an_event(),
        subscriber=a_subscriber(),
        secret=SHARED_SECRET,
        sent_at=NOW,
        target=_target(),
    )
    verify(
        secret=SHARED_SECRET,
        signature=request.headers[SIGNATURE_HEADER],
        timestamp=request.headers[TIMESTAMP_HEADER],
        body=request.body,
        now=NOW,
    )


def test_the_signature_covers_the_send_time_so_a_captured_one_expires() -> None:
    """Without the timestamp inside the signed material, a signature captured from a proxy
    log verifies for ever and the receiver's window check stands on nothing: the attacker
    supplies a fresh timestamp and the signature still matches.

    Both halves are asserted. The same body signed at two moments gives two signatures, and
    a signature replayed with a fresh timestamp is refused."""
    request = signed_request(
        event=an_event(),
        subscriber=a_subscriber(),
        secret=SHARED_SECRET,
        sent_at=NOW,
        target=_target(),
    )
    later = signed_request(
        event=an_event(),
        subscriber=a_subscriber(),
        secret=SHARED_SECRET,
        sent_at=NOW + timedelta(seconds=1),
        target=_target(),
    )
    assert request.headers[SIGNATURE_HEADER] != later.headers[SIGNATURE_HEADER]

    replayed = str(int((NOW + timedelta(minutes=1)).timestamp()))
    with pytest.raises(WebhookRefusedError):
        verify(
            secret=SHARED_SECRET,
            signature=request.headers[SIGNATURE_HEADER],
            timestamp=replayed,
            body=request.body,
            now=NOW + timedelta(minutes=1),
        )


def test_a_body_changed_in_flight_does_not_verify() -> None:
    """What the signature is for. Delete this and the signature could be computed over
    something that is not the body, which is the failure that looks like it works because
    the request still arrives."""
    request = signed_request(
        event=an_event(),
        subscriber=a_subscriber(),
        secret=SHARED_SECRET,
        sent_at=NOW,
        target=_target(),
    )
    with pytest.raises(WebhookRefusedError):
        verify(
            secret=SHARED_SECRET,
            signature=request.headers[SIGNATURE_HEADER],
            timestamp=request.headers[TIMESTAMP_HEADER],
            body=request.body.replace(b"run_2026_09_07", b"run_2026_09_08"),
            now=NOW,
        )


def test_signatures_are_compared_in_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """`==` on a digest returns as soon as two bytes differ, so the time it takes says how
    much of a guess was right and a few thousand requests turn that into the signature.

    Asserted by watching the call rather than by reading the source, so that replacing
    `hmac.compare_digest` with `==` fails here. Delete this and the comparison can be
    rewritten to the obvious one with both behavioural assertions still green."""
    calls: list[tuple[str, str]] = []
    real = hmac.compare_digest

    def spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    assert signature_matches("abc", "abc")
    assert not signature_matches("abc", "abd")
    assert len(calls) == 2


def test_a_signed_request_carries_no_unsigned_copy_of_the_event_id() -> None:
    """An identifier in an unsigned header is a second copy of a signed value, and a
    subscriber that deduplicates on the unsigned copy is deduplicating on something the
    sender does not vouch for. Two headers, both of which the signature covers or is.

    Delete this and an `X-Brain-Event` header can be added as a convenience, which is
    exactly how a receiver ends up trusting it."""
    request = signed_request(
        event=an_event(),
        subscriber=a_subscriber(),
        secret=SHARED_SECRET,
        sent_at=NOW,
        target=_target(),
    )
    assert set(request.headers) == {TIMESTAMP_HEADER, SIGNATURE_HEADER}
    assert "ev_01J8Z" not in "".join(request.headers.values())
    assert b"ev_01J8Z" in request.body


def test_a_request_cannot_be_built_against_an_address_that_was_checked_for_something_else() -> None:
    """A `Fetchable` for another URL is a check made against something else, which is as
    useful as no check. Delete this and a delivery to one subscriber can carry the address
    that was cleared for another."""
    other = a_subscriber(subscriber_id="sub_other", endpoint="https://elsewhere.example.com/x")
    with pytest.raises(OutboxError, match="has not run against this one"):
        signed_request(
            event=an_event(),
            subscriber=other,
            secret=SHARED_SECRET,
            sent_at=NOW,
            target=_target(),
        )


def test_a_request_is_not_built_for_a_subscriber_that_did_not_ask_for_that_kind() -> None:
    """The last place a subscription is honoured. An inactive subscriber and one that takes
    other kinds are both refused here, so a fan-out bug cannot become a delivery."""
    with pytest.raises(OutboxError, match="does not take"):
        signed_request(
            event=an_event(kind=EventKind.APPROVAL_REQUESTED, entity="approval"),
            subscriber=a_subscriber(),
            secret=SHARED_SECRET,
            sent_at=NOW,
            target=_target(),
        )
    with pytest.raises(OutboxError, match="does not take"):
        signed_request(
            event=an_event(),
            subscriber=a_subscriber(active=False),
            secret=SHARED_SECRET,
            sent_at=NOW,
            target=_target(),
        )


def test_a_send_time_with_no_timezone_is_refused() -> None:
    """The signed timestamp is reproduced by the receiver from the header and compared
    against their clock. A naive one names a different instant on every host, so the window
    check either passes or fails by accident."""
    with pytest.raises(OutboxError, match="timezone"):
        signed_request(
            event=an_event(),
            subscriber=a_subscriber(),
            secret=SHARED_SECRET,
            sent_at=datetime(2026, 9, 7, 10, 0),
            target=_target(),
        )


# ------------------------------------------------- the subscriber (M17.5.3)
def test_a_subscriber_on_the_public_internet_is_deliverable() -> None:
    """The positive case for the address rule. Without it, an `assert_deliverable` that
    refused everything would pass every refusal test below and no webhook would ever be
    sent."""
    target = assert_deliverable(a_subscriber(), PUBLIC)
    assert target.url == PUBLIC_ENDPOINT
    assert target.address == "93.184.216.34"


def test_a_subscriber_that_resolves_inside_this_network_is_refused() -> None:
    """A subscriber endpoint is a URL a client typed, and this server sits inside their
    network. `169.254.169.254` is the cloud metadata endpoint that hands out instance
    credentials, and the damage is done by the connection rather than by the response."""
    with pytest.raises(OutboxError, match="may not be delivered to"):
        assert_deliverable(a_subscriber(), INTERNAL)


def test_a_plaintext_subscriber_endpoint_is_refused() -> None:
    """The signature and the identifiers travel over this. Anything on the path can read a
    plain http request and rewrite it, and the subscriber's verification would pass on the
    rewritten one only if the attacker also had the secret, which is not the point: the ids
    are readable either way."""
    with pytest.raises(OutboxError):
        assert_deliverable(a_subscriber(endpoint="http://hooks.example.com/brain"), PUBLIC)


def test_the_address_is_checked_at_delivery_and_not_when_the_row_was_written() -> None:
    """The reason the check is not in `Subscriber.__post_init__`. A name that answered
    publicly when somebody typed it into the console answers differently on any later
    lookup, and an outbox delivers to the same row for months.

    Constructing a subscriber whose name resolves internally therefore succeeds, and
    delivering to it fails. Delete this and the check migrates into the constructor, where
    it reads as "already checked" and stops being true the moment the record changes."""
    registered = a_subscriber()
    assert registered.endpoint == PUBLIC_ENDPOINT
    with pytest.raises(OutboxError):
        assert_deliverable(registered, INTERNAL)


def test_a_subscriber_that_subscribes_to_nothing_is_refused() -> None:
    """It receives nothing and reads in a console as a working subscription, which is the
    shape of every "why is this integration quiet" incident. Deactivating says the same
    thing where somebody can see it."""
    with pytest.raises(OutboxError, match="subscribes to nothing"):
        a_subscriber(kinds=())


def test_a_subscriber_that_lists_one_kind_twice_is_refused() -> None:
    """Delivery is per subscriber and per event, so a repeated kind means nothing and reads
    as though it might mean two deliveries."""
    with pytest.raises(OutboxError, match="twice"):
        a_subscriber(kinds=(EventKind.AUTOMATION_RUN_FINISHED, EventKind.AUTOMATION_RUN_FINISHED))


def test_a_subscriber_names_whoever_created_it() -> None:
    """The same rule as a write grant naming its granter. The question asked after a
    client's identifiers turned up somewhere unexpected is always who set this up, and a row
    holding only a URL cannot answer it."""
    with pytest.raises(OutboxError, match="names nobody"):
        a_subscriber(created_by=" ")


def test_the_secret_is_held_as_a_reference_and_never_as_a_value() -> None:
    """A subscriber row lives in the database and is read in the console. A shared secret in
    it is a credential in both. The reference is useless to anybody who cannot already reach
    the vault, which is what makes rotation a vault operation rather than a schema change."""
    assert isinstance(a_subscriber().secret_ref, SecretRef)
    assert not any(
        isinstance(value, str) and SHARED_SECRET in value for value in vars(a_subscriber()).values()
    )


def test_managing_subscriptions_needs_one_named_capability() -> None:
    """Named once, here, so the console that does not exist yet cannot check a different
    string. A screen checking `admin:webhooks` while the grants say `admin:webhook_subscriber`
    refuses everybody, and the fix somebody reaches for under pressure is to stop checking.

    The capability is built through `brain.core.entitlement.Capability`, so its own grammar
    is what validates the value rather than a regular expression written here."""
    assert MANAGE_SUBSCRIBERS.verb == "admin"
    holder = EntitlementSet(
        principal_id="p_weiling",
        grants=(Grant(capability=MANAGE_SUBSCRIBERS, scope=Scope.unrestricted()),),
    )
    other = EntitlementSet(
        principal_id="p_alice",
        grants=(Grant(capability=Capability(value="read:client"), scope=Scope.unrestricted()),),
    )
    assert may_manage(holder)
    assert not may_manage(other)


def test_two_subscriptions_to_one_endpoint_are_reported_as_a_gap() -> None:
    """Invisible from inside a single `Subscriber` and visible to the operator who is about
    to be told we are flapping. The receiver deduplicates on the event id, so the second
    copy is dropped and the sender looks broken rather than misconfigured."""
    findings = outbox.subscriber_gaps([a_subscriber(), a_subscriber(subscriber_id="sub_ops")])
    assert any("sub_finance" in f and "sub_ops" in f for f in findings)


def test_a_kind_nobody_takes_is_reported_rather_than_raised() -> None:
    """Not an error. It is the thing somebody wants to know before they go looking for why
    an integration is quiet, and an exception would make an ordinary configuration
    unloadable."""
    findings = outbox.subscriber_gaps([a_subscriber()])
    assert any(EventKind.APPROVAL_REQUESTED.value in f for f in findings)
    assert not any(EventKind.AUTOMATION_RUN_FINISHED.value in f for f in findings)


# ------------------------------------------- retry, backoff and the guarantee (M17.5.1)
def test_an_accepted_delivery_is_never_sent_again() -> None:
    """The positive case. A retry policy tested only by its refusals is satisfied by one
    that retries everything for ever, and a delivered event sent twice is the one duplicate
    the subscriber cannot be asked to absorb, because we caused it."""
    attempt = plan_next(Delivery(event_id="ev_1", subscriber_id="sub_finance"), CallOutcome.OK)
    assert attempt.delivery.state is DeliveryState.DELIVERED
    assert not attempt.deliver_again
    assert attempt.delivery.attempts == 1


def test_a_delivery_that_could_not_be_made_is_tried_again_after_a_wait() -> None:
    """The other positive case, and the whole of what "retry and backoff" means. A
    subscriber that was down comes back and the event is still delivered."""
    attempt = plan_next(
        Delivery(event_id="ev_1", subscriber_id="sub_finance"), CallOutcome.UNAVAILABLE
    )
    assert attempt.deliver_again
    assert attempt.delivery.attempts == 1
    assert attempt.delay_seconds > 0


def test_the_wait_is_the_platforms_own_backoff_rather_than_a_second_one() -> None:
    """Anchored against `brain.connectors.throttle.retry_delay` rather than against a
    number, so writing arithmetic here instead of delegating fails. That function already
    holds the case that gets missed: a refusal that stated no wait is not a refusal that
    said zero, and multiplying zero by any backoff gives a hot retry loop.

    Delete this and the delay can be replaced by a constant with every other retry test
    still green, because they only assert that it is positive."""
    delivery = Delivery(event_id="ev_1", subscriber_id="sub_finance", attempts=2)
    stated = plan_next(delivery, CallOutcome.QUOTA, retry_after_seconds=12.0)
    assert stated.delay_seconds == retry_delay(retry_after_seconds=12.0, consecutive_refusals=3)

    unstated = plan_next(delivery, CallOutcome.UNAVAILABLE)
    assert unstated.delay_seconds == retry_delay(retry_after_seconds=None, consecutive_refusals=3)
    assert unstated.delay_seconds == MAX_BACKOFF_SECONDS


def test_a_subscriber_that_refused_the_request_is_not_retried_at_all() -> None:
    """A 404 or a 410 will be a 404 or a 410 eight more times, at full cost. Retrying is the
    argument `brain.connectors.throttle.is_retryable` already makes about a rejection, and a
    subscriber that has been deleted should reach a person today rather than in
    thirty-five minutes."""
    attempt = plan_next(
        Delivery(event_id="ev_1", subscriber_id="sub_finance"), CallOutcome.REJECTED
    )
    assert attempt.delivery.state is DeliveryState.EXHAUSTED
    assert attempt.delivery.attempts == 1
    assert "repeating reproduces" in attempt.reason


def test_a_delivery_runs_out_of_attempts_rather_than_retrying_for_ever() -> None:
    """An uncapped retry is a worker permanently occupied by one dead subscriber. Parked
    rather than dropped: an event nobody was told about and nothing recorded is the failure
    an outbox exists to prevent."""
    last = Delivery(
        event_id="ev_1", subscriber_id="sub_finance", attempts=MAX_DELIVERY_ATTEMPTS - 1
    )
    attempt = plan_next(last, CallOutcome.UNAVAILABLE)
    assert attempt.delivery.state is DeliveryState.EXHAUSTED
    assert not attempt.deliver_again

    earlier = Delivery(
        event_id="ev_1", subscriber_id="sub_finance", attempts=MAX_DELIVERY_ATTEMPTS - 2
    )
    assert plan_next(earlier, CallOutcome.UNAVAILABLE).deliver_again


def test_the_attempt_cap_leaves_room_for_the_backoff_to_engage() -> None:
    """One of the two properties that fix `MAX_DELIVERY_ATTEMPTS`, anchored outside itself.
    `brain.ops.limits.backoff_seconds` hands back the measured wait for the first few
    refusals and only doubles after `BACKOFF_AFTER_REFUSALS`, so a cap at or below that
    number is a retry policy with no backoff in it and a docstring claiming there is one."""
    assert MAX_DELIVERY_ATTEMPTS > BACKOFF_AFTER_REFUSALS
    assert backoff_is_engaged()


def test_the_retry_window_outlasts_a_single_maximum_wait() -> None:
    """The second property. A cap that expires inside one backoff interval is a last attempt
    the worker never makes, and the failure looks like a subscriber that was never retried.
    Anchored to `MAX_BACKOFF_SECONDS`, which is the platform's own ceiling."""
    assert retry_window_seconds() > MAX_BACKOFF_SECONDS


def test_a_settled_delivery_is_not_attempted_again() -> None:
    """Both terminal states, because they fail differently. Sending a delivered event again
    is a duplicate we caused; re-attempting an exhausted one is a worker looping on the row
    a person was supposed to look at."""
    for state in (DeliveryState.DELIVERED, DeliveryState.EXHAUSTED):
        with pytest.raises(OutboxError, match="attempted again"):
            plan_next(
                Delivery(event_id="ev_1", subscriber_id="sub_finance", attempts=1, state=state),
                CallOutcome.OK,
            )


def test_the_guarantee_is_at_least_once_and_the_states_say_so() -> None:
    """`brain.ops.idempotency.OperationState` has an `UNKNOWN` because it promises
    exactly-once and has to be honest about not knowing. This machine has none, and that is
    the guarantee showing in the type: not knowing whether the subscriber processed a
    request already has an answer, which is to send it again and let them deduplicate.

    Delete this and an `UNKNOWN` can be added here, which would read as care and would
    actually be a delivery that stops for ever with nobody able to resolve it."""
    assert "unknown" not in {state.value for state in DeliveryState}
    assert OperationState.UNKNOWN in set(OperationState)
    assert "at least once" in outbox.DELIVERY_IS_AT_LEAST_ONCE


def test_fan_out_writes_one_row_per_subscriber_that_takes_the_kind() -> None:
    """One event to twelve subscribers is twelve rows that fail independently. Sharing a row
    would let one subscriber being down hold up the other eleven and make "which of them got
    it" unanswerable. Ordered, so two runs of a fan-out produce the same rows."""
    subscribers = [
        a_subscriber(subscriber_id="sub_z"),
        a_subscriber(subscriber_id="sub_a"),
        a_subscriber(subscriber_id="sub_inactive", active=False),
        a_subscriber(subscriber_id="sub_other_kind", kinds=(EventKind.APPROVAL_REQUESTED,)),
    ]
    rows = deliveries_for(an_event(), subscribers)
    assert [row.subscriber_id for row in rows] == ["sub_a", "sub_z"]
    assert all(row.event_id == "ev_01J8Z" for row in rows)
    assert all(row.state is DeliveryState.PENDING for row in rows)


def test_a_delivery_row_names_one_event_and_one_subscriber() -> None:
    """A row missing either is unroutable, and it is found by a worker that has already
    picked it up."""
    with pytest.raises(OutboxError, match="unroutable"):
        Delivery(event_id="", subscriber_id="sub_finance")
    with pytest.raises(OutboxError, match="unroutable"):
        Delivery(event_id="ev_1", subscriber_id=" ")
