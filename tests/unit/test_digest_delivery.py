"""Sending the evening digest: once, to a room, and whether or not anything happened.

`brain.ops.digest` computes the content and deliberately holds no channel. This is the one
call site it was shaped for, and the tests are about the three things that only become
questions once something is posted to a room every evening: sending it twice, not sending it
on a quiet day, and what happens when the channel says no.

Sending it twice is the one that moved: the digest goes through the same ledger every side
effect uses, so the tests hand it `tests.fixtures.operation_ledger.MemoryLedger` and deliver twice
into it, rather than handing it a register that says what a previous run did.

Task ids: M38.3.3.1, M38.3.3.4, M17.3.1
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from brain.core.field_policy import Classification
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.ops.digest import (
    NOTHING_CLOSED,
    BurnDown,
    DailyDigest,
    Forecast,
    Movement,
)
from brain.ops.digest_delivery import (
    DIGEST_TOOL,
    Delivery,
    DeliveryOutcome,
    DigestChannel,
    classification_of_a_digest,
    deliver_digest,
    digest_operation,
)
from brain.ops.idempotency import IdempotencyError, Operation, OperationState
from tests.fixtures.operation_ledger import MemoryLedger

DAY = date(2026, 9, 6)
CHAT = DigestChannel(channel=Channel.LARK, chat_id="oc_build_room")
OTHER_ROOM = DigestChannel(channel=Channel.LARK, chat_id="oc_other_room")

#: Whoever runs the digest. A value handed in, never assumed.
RUNNER = "svc_digest"


class _Sender:
    """Records what it was asked to send. What a test reads instead of a Lark chat."""

    def __init__(self, *, fails: bool = False) -> None:
        self.sent: list[tuple[ChannelPayload, str]] = []
        self._fails = fails

    def send(self, payload: ChannelPayload, *, to: str) -> None:
        if self._fails:
            raise RuntimeError("oc_build_room is archived and the bot was removed from it")
        self.sent.append((payload, to))


def _digest(*, closed: tuple[str, ...] = ("M1.1",)) -> DailyDigest:
    return DailyDigest(
        day=DAY,
        wave=2,
        movement=Movement(closed=closed, measured=True),
        burn_down=BurnDown(
            wave=2,
            name="Data",
            total=10,
            closed=len(closed),
            remaining=10 - len(closed),
            target=date(2026, 9, 30),
            days_to_target=24,
            days_of_history=0,
            rate_per_day=0.0,
            projected_finish=None,
            verdict=Forecast.NOT_FORECASTABLE,
            because="not enough history yet",
        ),
    )


def _deliver(
    digest: DailyDigest | None = None,
    *,
    channel: DigestChannel = CHAT,
    sender: _Sender | None = None,
    ledger: MemoryLedger | None = None,
) -> Delivery:
    return deliver_digest(
        digest or _digest(),
        channel=channel,
        sender=sender or _Sender(),
        ledger=ledger or MemoryLedger(),
        principal_id=RUNNER,
    )


# --------------------------------------------------------------- it is sent
def test_a_digest_reaches_the_room_it_was_configured_for() -> None:
    """The positive case. A delivery module that never delivered would satisfy every refusal
    below and quietly stop the feature working, and nobody notices a report that stopped
    arriving until somebody asks for it."""
    sender = _Sender()

    result = _deliver(sender=sender)

    assert result.outcome is DeliveryOutcome.SENT
    assert len(sender.sent) == 1
    assert sender.sent[0][1] == "oc_build_room"


def test_what_was_sent_is_what_the_digest_module_renders() -> None:
    """`digest.render` owns the wording. A second renderer for "the Lark version" is how the
    message people read stops matching the one the tests check, and the drift is invisible
    because both look right on their own."""
    result = _deliver()

    assert "Build digest for 2026-09-06" in result.body
    assert "M1.1" in result.body


# --------------------------------------------------------------- exactly once
def test_a_day_already_sent_is_not_sent_again() -> None:
    """**A scheduler fires twice.** It is restarted, its timer is edited by somebody testing
    it, or the host reboots. Each of those posts the digest again, and a room with the same
    message in it twice is one people learn to skip, which costs the whole feature rather
    than one evening.

    Delete this and every scheduler restart is a duplicate."""
    sender = _Sender()
    ledger = MemoryLedger()

    first = _deliver(sender=sender, ledger=ledger)
    again = _deliver(sender=sender, ledger=ledger)

    assert (first.outcome, again.outcome) == (DeliveryOutcome.SENT, DeliveryOutcome.ALREADY_SENT)
    assert len(sender.sent) == 1
    assert ledger.issued() == 1


def test_the_duplicate_check_happens_before_the_render() -> None:
    """Rendering is where the work is, and two renders of one day are two chances for the
    text to differ. Asserted by the body being absent from an already-sent outcome, which is
    only true if nothing was rendered.

    Delete this and the render moves out of the effect, which still prevents the duplicate
    send and does the work twice for nothing."""
    ledger = MemoryLedger()
    _deliver(ledger=ledger)

    result = _deliver(ledger=ledger)

    assert result.outcome is DeliveryOutcome.ALREADY_SENT
    assert result.body == ""


def test_the_same_day_in_a_different_room_is_a_different_digest() -> None:
    """The key is derived from both, because posting today's digest to a second channel is
    not a duplicate. Delete this and adding a channel silently sends nothing to it."""
    sender = _Sender()
    ledger = MemoryLedger()
    _deliver(channel=OTHER_ROOM, sender=sender, ledger=ledger)

    result = _deliver(sender=sender, ledger=ledger)

    assert result.outcome is DeliveryOutcome.SENT
    assert [to for _, to in sender.sent] == ["oc_other_room", "oc_build_room"]


def test_tomorrow_is_a_new_digest_and_the_same_day_is_the_same_one() -> None:
    """The day is the intent, the room an argument and the runner the principal.

    Delete this and a key that ignored the day would send the first evening's digest and nothing
    after, or a key that carried the content would send every retry whose render differed."""
    tomorrow = DailyDigest(day=DAY + timedelta(days=1), wave=2)
    today = digest_operation(_digest(), channel=CHAT, principal_id=RUNNER)

    assert digest_operation(_digest(closed=()), channel=CHAT, principal_id=RUNNER).key == today.key
    assert digest_operation(tomorrow, channel=CHAT, principal_id=RUNNER).key != today.key
    assert digest_operation(_digest(), channel=OTHER_ROOM, principal_id=RUNNER).key != today.key
    assert digest_operation(_digest(), channel=CHAT, principal_id="svc_other").key != today.key
    assert (today.connector, today.tool, today.intent_ref) == (
        Channel.LARK.value,
        DIGEST_TOOL,
        "digest.2026-09-06",
    )


def test_a_day_whose_earlier_attempt_nobody_knows_the_end_of_is_not_posted_again() -> None:
    """The channel raised on the first attempt, which may have posted before it raised. The
    record is left unknown, the second attempt with a working channel posts nothing, and says
    the attempt is unsettled rather than sent or refused.

    Delete this and a retry after a timeout posts the digest a second time into a room that may
    already hold it, which is `brain.ops.idempotency.UNKNOWN_IS_NOT_FAILED` in a chat."""
    ledger = MemoryLedger()
    refused = _deliver(sender=_Sender(fails=True), ledger=ledger)
    working = _Sender()

    again = _deliver(sender=working, ledger=ledger)

    assert refused.outcome is DeliveryOutcome.UNDELIVERED
    assert again.outcome is DeliveryOutcome.UNSETTLED
    assert working.sent == []
    key = digest_operation(_digest(), channel=CHAT, principal_id=RUNNER).key
    assert ledger.records[key].state is OperationState.UNKNOWN
    assert "read-back" in again.detail


def test_a_ledger_that_cannot_answer_is_raised_rather_than_reported_as_the_channel() -> None:
    """Nothing was sent and the channel said nothing, so the outcome is not the channel's.

    Delete this and a database outage reads in the scheduler's log as Lark refusing a digest,
    which sends somebody to the wrong system."""

    class Unreachable(MemoryLedger):
        def claim(self, operation: Operation) -> Operation:
            raise ConnectionError("the database is not answering")

    sender = _Sender()
    with pytest.raises(ConnectionError):
        _deliver(sender=sender, ledger=Unreachable())
    assert sender.sent == []


def test_a_key_held_by_another_intent_is_raised_and_not_reported_as_a_refusal() -> None:
    """Delete this and a collision in the ledger would be answered as the channel refusing."""

    class Forged(MemoryLedger):
        def claim(self, operation: Operation) -> Operation:
            return replace(operation, intent_ref="digest.1999-01-01")

    sender = _Sender()
    with pytest.raises(IdempotencyError):
        _deliver(sender=sender, ledger=Forged())
    assert sender.sent == []


# --------------------------------------------------------------- a quiet day still goes
def test_a_day_on_which_nothing_closed_is_still_delivered() -> None:
    """**The optimisation somebody will add here**, and the one `digest.py` already argues
    against: not sending when nothing happened.

    A digest that only arrives on busy days cannot report a stall, and a week of silence is
    then indistinguishable from a week nobody sent it. The reader cannot tell which, so they
    stop treating its absence as information.

    Delete this and "do not bother them, nothing happened" gets added, which reads as
    considerate and removes the only signal that matters."""
    result = _deliver(_digest(closed=()))

    assert result.outcome is DeliveryOutcome.SENT
    assert NOTHING_CLOSED in result.body


# --------------------------------------------------------------- the channel says no
def test_a_channel_that_refuses_does_not_lose_the_digest() -> None:
    """The digest is a record of what the plan did and it exists whether or not Lark accepted
    it. A scheduled job that raised on a transport error would lose the computation as well
    as the send, and the next evening has nothing to compare against.

    Delete this and a refused delivery becomes a traceback in a scheduler log."""
    result = _deliver(sender=_Sender(fails=True))

    assert result.outcome is DeliveryOutcome.UNDELIVERED
    assert "Build digest" in result.body, "the text that would have gone out is kept"


def test_a_refusal_records_the_kind_of_failure_and_never_its_message() -> None:
    """A transport exception stringifies whatever it failed on, and what it failed on here is
    a message naming every open task in the plan. The class name says enough to act on.

    Delete this and the digest's contents end up in whatever log records the failure, which
    is the one place nobody applied a classification to."""
    result = _deliver(sender=_Sender(fails=True))

    assert "RuntimeError" in result.detail
    assert "archived" not in result.detail
    assert "M1.1" not in result.detail


def test_the_four_outcomes_are_distinct_because_they_are_acted_on_differently() -> None:
    """ "The channel refused it", "it was already sent" and "an earlier attempt may have sent it"
    are all not-sent and are not the same fact. A scheduler treating them alike alerts on every
    restart, stays silent through an outage, or posts again over an attempt nobody knows the end
    of."""
    assert set(DeliveryOutcome) == {
        DeliveryOutcome.SENT,
        DeliveryOutcome.ALREADY_SENT,
        DeliveryOutcome.UNDELIVERED,
        DeliveryOutcome.UNSETTLED,
    }
    assert len(set(DeliveryOutcome)) == 4


# --------------------------------------------------------------- the audience
def test_the_digest_is_addressed_to_a_room_and_has_nowhere_to_name_a_person() -> None:
    """Everybody who reads it reads the same sentence, because it reports on the plan rather
    than answering anybody. A per-person send would be a broadcast with extra steps and would
    put a per-viewer render on a path that has no viewer.

    Delete this and a `viewer` argument gets added for an ephemeral digest, which is a
    per-person message that says the same thing to everybody."""
    assert set(DigestChannel.__dataclass_fields__) == {"channel", "chat_id"}
    assert "viewer" not in Delivery.__dataclass_fields__


def test_a_channel_with_no_chat_is_refused_rather_than_posting_nowhere() -> None:
    """An empty chat id sends into the void and reports success, which is the worst of the
    three outcomes because nobody investigates a delivery that said it worked."""
    with pytest.raises(ValueError, match="posts nowhere"):
        DigestChannel(channel=Channel.LARK, chat_id="  ")


def test_the_sensitivity_still_comes_from_the_module_that_computes_the_digest() -> None:
    """The digest names every open task, which is the shape of what is not built yet. That
    classification is decided where the content is decided, and re-declaring it here would be
    a second answer that drifts.

    Delete this and the constant gets copied, and the copy is the one a channel checks."""
    assert classification_of_a_digest() is Classification.INTERNAL
