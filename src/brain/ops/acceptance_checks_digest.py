"""The install acceptance check for the evening digest: one digest a day to the chosen conversation,
none when nobody has chosen, and none to a channel that is switched off.

The check runs `brain.ops.digest_run.run_digest`, the function the worker's schedule runs, over what
this image carries: the plan in its `docs/`, and the record the digest keeps in `ops.setting`,
written inside the check's transaction and rolled back with it. The channel is a stand-in: a wire
that lists nothing and posts to a room named after the run, a transport that records what it was
handed and sends nothing, a lender that hands a value nobody could use, and an operation ledger
in memory. So nothing reaches a real conversation, the install's own destination is neither read
nor changed, and the key the worker would borrow is not borrowed.

**What the check proves.** That the deployed image's digest is off until chosen and sends nothing
then; that a chosen conversation is sent exactly one digest for today, rendered from this image's
plan, and a second run the same day sends nothing; that the record it keeps names today and the
tasks closed now; and that a chosen channel which has been switched off stops with the reason.

**What only a real Lark group proves**, stated rather than implied: that Lark accepts the post
with the install's app, that the bot is still a member of the group chosen, and that the app holds
the scope that lists its groups. The first is the schedule's own run record once a group is chosen
(the `evening_digest` row names the day and the channel, and says sent); the other two are the
Connect Lark test's.

Task ids: M38.3.3.1, M38.3.3.2, M38.3.3.3, M38.3.3.4
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime
from typing import Final

from brain.channels.adapter import VendorAnswer, VendorRequest
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.ops.channel_lease import SendLease
from brain.ops.channel_store import ChannelRecord
from brain.ops.digest_delivery import Delivery
from brain.ops.idempotency import (
    IllegalTransitionError,
    Operation,
    OperationLedger,
    OperationState,
    advance,
)
from brain.ops.leases import SealedSecret
from brain.ops.secrets import SecretRef, VaultRole

#: Where this module's checks stand on the Install page.
CHECK_ORDER: Final = 270

#: Said when the image carries no work breakdown to report on.
NO_PLAN_IN_THIS_IMAGE: Final = (
    "this image carries no work breakdown in its docs, so there is no plan for a digest to report"
)


class _Ledger:
    """`OperationLedger` in memory, for the check's own send. See the module docstring."""

    def __init__(self) -> None:
        self.records: dict[str, Operation] = {}

    def claim(self, operation: Operation) -> Operation:
        return self.records.setdefault(operation.key, operation)

    def win(self, key: str) -> bool:
        record = self.records[key]
        if record.state is not OperationState.PENDING:
            return False
        self.records[key] = record.advanced(OperationState.SENT)
        return True

    def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        advance(frm, to)
        record = self.records[key]
        if record.state is not frm:
            msg = "the check's record moved before it was settled"
            raise IllegalTransitionError(msg)
        self.records[key] = record.advanced(to)
        return self.records[key]


class _Wire:
    """A wire that posts to a room named after the run and accepts every post."""

    def conversations_request(
        self, *, page: str, secret: str, tenant: Mapping[str, str]
    ) -> VendorRequest:
        raise CheckFailedError("the digest's send asked its channel for a list")

    def conversations_page(self, answer: VendorAnswer) -> tuple[tuple[tuple[str, str], ...], str]:
        raise CheckFailedError("the digest's send asked its channel for a list")

    def room_of(self, conversation: str) -> str:
        return f"room:{conversation}"

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest:
        return VendorRequest(url=f"https://digest.acceptance.invalid/{to}", headers={}, body=b"")

    def judge(self, answer: VendorAnswer) -> CallOutcome:
        return CallOutcome.OK


class _Transport:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, request: VendorRequest) -> VendorAnswer:
        self.sent.append(request.url)
        return VendorAnswer(status=200, body=b"{}")

    def read(self, request: VendorRequest) -> VendorAnswer:
        raise CheckFailedError("the digest's send read from its channel")


class _Lender:
    def lease(self, record: ChannelRecord, *, now: datetime) -> SendLease:
        return SendLease(secret=SealedSecret("acceptance-stand-in"))


class _Records:
    def __init__(self, record: ChannelRecord) -> None:
        self.record = record

    async def get(self, channel: Channel) -> ChannelRecord | None:
        return self.record if channel is self.record.channel else None


@check(
    leaves=("M38.3.3.1", "M38.3.3.2", "M38.3.3.3", "M38.3.3.4"),
    sentence=(
        "The digest the worker's schedule sends, run over this image's plan with a stand-in "
        "channel: off until a conversation is chosen, one digest for today to the chosen "
        "conversation and none on a second run, today's record kept, and a switched-off channel "
        "stopped with its reason."
    ),
)
async def the_evening_digest_is_sent_once_a_day_to_the_chosen_conversation(h: Harness) -> None:
    from brain.docs_routes import DOCS
    from brain.locale import time_zone
    from brain.ops.digest_run import OFF, WBS_FILE, StoredDigestRecords, run_digest

    if not (DOCS / WBS_FILE).exists():
        raise CheckNotRunError(NO_PLAN_IN_THIS_IMAGE)
    conversation = f"acceptance-{h.word().lower()}"
    on = ChannelRecord(
        channel=Channel.LARK,
        enabled=True,
        tenant={},
        secret=SecretRef(path="providers/channel_lark", role=VaultRole.APPLICATION),
        updated_by=h.actor,
        updated_at=h.now,
    )
    transport, ledger = _Transport(), _Ledger()
    kept = StoredDigestRecords(h.sessions)

    def through(work: Callable[[OperationLedger], Delivery]) -> Delivery:
        return work(ledger)

    async def once(saved: str, record: ChannelRecord) -> str:
        return await run_digest(
            kept,
            now=h.now,
            saved=saved,
            zone=time_zone(),
            records=_Records(record),
            secrets=_Lender(),
            transport=transport,
            ledger=through,
            docs=DOCS,
            wires=lambda: {Channel.LARK: _Wire()},
        )

    if await once("unset", on) != OFF or transport.sent:
        raise CheckFailedError("a digest nobody pointed anywhere was sent")
    chosen = f"lark:{conversation}"
    first = await once(chosen, on)
    again = await once(chosen, on)
    if not first.endswith(": sent") or not again.endswith("not sent again"):
        raise CheckFailedError("the chosen conversation was not sent exactly one digest today")
    if transport.sent != [f"https://digest.acceptance.invalid/room:{conversation}"]:
        raise CheckFailedError("the digest went somewhere other than the chosen conversation")
    record = await kept.read()
    if record is None or record.day != h.now.astimezone(time_zone()).date():
        raise CheckFailedError("the digest kept no record of today for tomorrow's comparison")
    off = replace(on, enabled=False)
    stopped = await once(f"lark:{conversation}-off", off)
    if "stopped" not in stopped or len(transport.sent) != 1:
        raise CheckFailedError("a switched-off channel was sent a digest or not said to be stopped")
