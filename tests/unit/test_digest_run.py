"""The evening digest, sent: off, stopped, sent once per day, and yesterday's record kept.

Every collaborator is a stand-in the runner is handed: the channel's record, its wire, the borrowed
key, the transport, the operation ledger and the record store. The plan is read from the
repository's own `docs/wbs.json` and `docs/wave-windows.json`, beside a status file written here.

Task ids: M38.3.3.1, M38.3.3.2, M38.3.3.3, M38.3.3.4
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from brain.channels.adapter import VendorAnswer, VendorRequest
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.ops.channel_lease import SendLease
from brain.ops.channel_store import ChannelRecord
from brain.ops.digest import DayClosed, Plan
from brain.ops.digest_delivery import Delivery
from brain.ops.digest_run import (
    HISTORY_DAYS,
    OFF,
    DigestRecord,
    DigestWire,
    next_record,
    plan_of,
    run_digest,
)
from brain.ops.idempotency import OperationLedger
from brain.ops.leases import SealedSecret
from brain.ops.secrets import SecretRef, VaultRole
from tests.fixtures.operation_ledger import MemoryLedger

ROOT = Path(__file__).resolve().parents[2]
ZONE = ZoneInfo("Asia/Singapore")
#: 18:00 in Singapore on a day no clock will reach.
EVENING = datetime(2999, 3, 1, 10, 0, tzinfo=UTC)
TODAY = date(2999, 3, 1)


def a_record(*, enabled: bool = True) -> ChannelRecord:
    return ChannelRecord(
        channel=Channel.LARK,
        enabled=enabled,
        tenant={"app_id": "cli_x", "platform": "larksuite.com", "bot_id": "ou_bot"},
        secret=SecretRef(path="providers/channel_lark", role=VaultRole.APPLICATION),
        updated_by="u_admin",
        updated_at=EVENING,
    )


class Wire:
    """A `DigestWire` that posts to `room:<id>` and answers what the test says."""

    def __init__(self, outcome: CallOutcome = CallOutcome.OK) -> None:
        self.outcome = outcome

    def conversations_request(
        self, *, page: str, secret: str, tenant: Mapping[str, str]
    ) -> VendorRequest:
        raise AssertionError("sending never lists")

    def conversations_page(self, answer: VendorAnswer) -> tuple[tuple[tuple[str, str], ...], str]:
        raise AssertionError("sending never lists")

    def room_of(self, conversation: str) -> str:
        return f"room:{conversation}"

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest:
        return VendorRequest(url=f"https://vendor.invalid/{to}", headers={}, body=text.encode())

    def judge(self, answer: VendorAnswer) -> CallOutcome:
        return self.outcome


class Transport:
    def __init__(self) -> None:
        self.sent: list[VendorRequest] = []

    def send(self, request: VendorRequest) -> VendorAnswer:
        self.sent.append(request)
        return VendorAnswer(status=200, body=b"{}")

    def read(self, request: VendorRequest) -> VendorAnswer:
        raise AssertionError("sending never reads")


class Records:
    def __init__(self, record: ChannelRecord | None) -> None:
        self.record = record

    async def get(self, channel: Channel) -> ChannelRecord | None:
        return self.record


class Kept:
    """`DigestRecords` in memory."""

    def __init__(self, record: DigestRecord | None = None) -> None:
        self.record = record
        self.writes = 0

    async def read(self) -> DigestRecord | None:
        return self.record

    async def write(self, record: DigestRecord) -> None:
        self.record = record
        self.writes += 1


#: What the stand-in lender hands a send. Not a credential: nothing reads it.
KEPT_VALUE = "stand-in"


class Lender:
    def __init__(self, value: str | None = KEPT_VALUE) -> None:
        self.secret = value
        self.leases: list[SendLease] = []

    def lease(self, record: ChannelRecord, *, now: datetime) -> SendLease:
        one = (
            SendLease(secret=SealedSecret(self.secret))
            if self.secret is not None
            else SendLease(failure="the channel's secret is not in the vault")
        )
        self.leases.append(one)
        return one


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    shutil.copy(ROOT / "docs" / "wbs.json", tmp_path / "wbs.json")
    shutil.copy(ROOT / "docs" / "wave-windows.json", tmp_path / "wave-windows.json")
    (tmp_path / "status.json").write_text(
        json.dumps({"done_task_ids": ["M0.1.2"], "current_wave": 2, "recent": []}),
        encoding="utf-8",
    )
    return tmp_path


def run(
    docs: Path,
    *,
    saved: str = "lark:oc_1",
    record: ChannelRecord | None = None,
    wire: object | None = None,
    kept: Kept | None = None,
    lender: Lender | None = None,
    transport: Transport | None = None,
    ledger: MemoryLedger | None = None,
    now: datetime = EVENING,
    missing: bool = False,
) -> str:
    held = ledger if ledger is not None else MemoryLedger()

    def through(work: Callable[[OperationLedger], Delivery]) -> Delivery:
        return work(held)

    return asyncio.run(
        run_digest(
            kept if kept is not None else Kept(),
            now=now,
            saved=saved,
            zone=ZONE,
            records=Records(None if missing else (a_record() if record is None else record)),
            secrets=lender if lender is not None else Lender(),
            transport=transport if transport is not None else Transport(),
            ledger=through,
            docs=docs,
            wires=lambda: {Channel.LARK: Wire() if wire is None else wire},
        )
    )


def test_off_until_chosen_sends_nothing_and_borrows_nothing(docs: Path) -> None:
    """Delete this and an install nobody configured posts the build's open tasks somewhere."""
    lender, transport = Lender(), Transport()

    said = run(docs, saved="unset", lender=lender, transport=transport)

    assert said == OFF and lender.leases == [] and transport.sent == []


def test_the_chosen_conversation_gets_one_digest_a_day_and_the_record_is_kept(docs: Path) -> None:
    """**The leaf.** Sent once, to the chosen conversation's room, with the key borrowed for the
    send and given back; asked again the same day, not sent again; and today's record kept only
    after the send. Delete this and a restarted worker posts twice, or the record is kept for a
    digest that never left."""
    ledger, transport, kept, lender = MemoryLedger(), Transport(), Kept(), Lender()

    first = run(docs, ledger=ledger, transport=transport, kept=kept, lender=lender)
    again = run(docs, ledger=ledger, transport=transport, kept=kept, lender=Lender())

    assert first == "the evening digest for 2999-03-01 on lark: sent"
    assert again == "the evening digest for 2999-03-01 on lark: already sent today, not sent again"
    assert [one.url for one in transport.sent] == ["https://vendor.invalid/room:oc_1"]
    assert b"Build digest for 2999-03-01" in transport.sent[0].body
    assert kept.record is not None and kept.record.day == TODAY
    assert kept.record.closed == frozenset({"M0.1.2"})
    assert lender.leases[0].secret() is None, "the lease was not closed after the send"


def test_the_next_day_is_a_new_digest_to_the_same_place(docs: Path) -> None:
    """Delete this and the day's key could be something that repeats, and the second evening's
    digest is refused as already sent."""
    ledger, transport, kept = MemoryLedger(), Transport(), Kept()
    run(docs, ledger=ledger, transport=transport, kept=kept)

    said = run(docs, ledger=ledger, transport=transport, kept=kept, now=EVENING + timedelta(days=1))

    assert said.endswith(": sent") and len(transport.sent) == 2


def test_a_chosen_channel_that_is_off_or_unkeyed_stops_and_says_why(docs: Path) -> None:
    """Delete this and a switched-off channel is sent to anyway, or the run records a success for
    a digest that never left."""
    transport, kept = Transport(), Kept()

    off = run(docs, record=a_record(enabled=False), transport=transport, kept=kept)
    gone = run(docs, missing=True, transport=transport, kept=kept)
    unkeyed = run(docs, lender=Lender(None), transport=transport, kept=kept)

    assert off == "the evening digest stopped: This channel is switched off."
    assert gone == "the evening digest stopped: This channel is not connected."
    assert unkeyed == "the evening digest stopped: the channel's secret is not in the vault"
    assert transport.sent == [] and kept.writes == 0


def test_a_channel_that_refuses_the_digest_keeps_no_record(docs: Path) -> None:
    """Delete this and a refused day is recorded as seen, and tomorrow's digest omits what closed
    today."""
    kept = Kept()

    said = run(docs, wire=Wire(CallOutcome.REJECTED), kept=kept)

    assert said.endswith("not delivered: the channel refused it")
    assert kept.writes == 0


def test_a_channel_whose_wire_cannot_carry_a_digest_is_stopped() -> None:
    """Delete this and the webhook channel, which lists no conversations, is sent a digest."""
    assert not isinstance(object(), DigestWire)
    assert isinstance(Wire(), DigestWire)


def test_the_record_adds_what_closed_since_the_last_day_and_forgets_after_a_month() -> None:
    """Delete this and the burn-down's rate counts a re-run twice, or grows without bound."""
    plan = Plan(closed=frozenset({"a", "b", "c"}))
    first = next_record(None, Plan(closed=frozenset({"a"})), TODAY - timedelta(days=1))
    today = next_record(first, plan, TODAY)
    rerun = next_record(today, plan, TODAY)

    assert today.history == (DayClosed(day=TODAY, closed=frozenset({"b", "c"})),)
    assert rerun.history == today.history
    old = DigestRecord(
        day=TODAY - timedelta(days=1),
        closed=frozenset({"a"}),
        history=(DayClosed(day=TODAY - timedelta(days=HISTORY_DAYS + 1)),),
    )
    assert next_record(old, plan, TODAY).history == (
        DayClosed(day=TODAY, closed=frozenset({"b", "c"})),
    )
    assert DigestRecord.of(today.as_value()) == today
    assert DigestRecord.of({"day": "not a day"}) is None


def test_the_plan_is_read_from_the_images_files_and_the_windows_are_the_schedules(
    docs: Path,
) -> None:
    """Delete this and the digest could report on a wave the status page does not, or with no
    target dates because the windows file is never read."""
    plan, wave, windows = plan_of(docs)

    assert wave == 2 and "M0.1.2" in plan.closed
    written = json.loads((ROOT / "docs" / "wave-windows.json").read_text(encoding="utf-8"))
    assert {str(one) for one in windows} == set(written["windows"])
    assert windows[2].start.isoformat() == written["windows"]["2"]["start"]


def test_the_windows_file_is_what_render_js_writes_now() -> None:
    """Delete this and the committed windows drift from the schedule, which CI's tracker job also
    catches only when it runs `render.js`."""
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on this machine; CI's tracker job runs render.js")
    before = (ROOT / "docs" / "wave-windows.json").read_text(encoding="utf-8")
    subprocess.run([node, "docs/wbs/render.js"], cwd=ROOT, check=True, capture_output=True)
    assert (ROOT / "docs" / "wave-windows.json").read_text(encoding="utf-8") == before
