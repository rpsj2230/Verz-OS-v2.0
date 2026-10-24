"""The evening digest, sent: the build's plan as this image carries it, compared with yesterday's
record, rendered once and posted once to the conversation the install chose (M38.3.3).

Everything the message says was decided before this module: `brain.ops.digest` builds it as
content and argues every line, `brain.ops.digest_delivery` sends it once per day and room through
the operation ledger, and `brain.ops.digest_destination` says where it goes. This is the call
site `brain.ops.digest` was shaped for and nothing more: read the plan, read yesterday's record,
build, send, and keep today's record for tomorrow.

**The plan is what this image was built from.** `docs/status.json` is baked at image build from
the commits (`brain.status`), `docs/wbs.json` is the work breakdown, and `docs/wave-windows.json`
is the wave windows `docs/wbs/render.js` computed, written beside the tracker so the target
dates are the schedule's and never recomputed here
(`brain.ops.digest.THE_TARGET_DATE_IS_THE_SCHEDULES_AND_IS_NEVER_COMPUTED_HERE`). The closed set
therefore moves when a release deploys, and "closed today" is what closed since the record the
last digest kept, which on a day with no deploy is nothing, said as nothing.

**Yesterday is a record this module keeps, in `ops.setting` under `digest.record`.** The closed
set the last digest saw and each day's newly closed ids, a month of them, for the burn-down's
rate. A setting rather than a table, for `brain.ops.setting_store`'s argument: it is one value
somebody's worker writes and the next run reads, and the row says who wrote it and when. It is
written only after the digest is sent or found already sent, so a day whose send failed is
compared again tomorrow rather than lost from the count.

**It is sent through the wire of the channel the install chose, with the secret borrowed for the
send.** `brain.ops.channel_lease` lends the worker the channel's secret through a token minted
for the one send and revoked in a `finally`; `WireSender` builds the vendor request with the
chosen channel's own wire and judges the answer with it. Nothing here names Lark: a channel whose
wire can list conversations can carry the digest (`ConversationLister`).

**Off, stopped and sent are three different reports.** Off is nobody having chosen; stopped says
why the chosen channel cannot carry it now, in `brain.ops.digest_destination`'s words; sent names
the day and the channel and never the content, because a run record is read by whoever reads the
Scheduled jobs screen.

Task ids: M38.3.3.1, M38.3.3.2, M38.3.3.3, M38.3.3.4
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.channels.adapter import ChannelTransport, VendorAnswer, VendorRequest, channel_wires
from brain.connectors.throttle import CallOutcome
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.ops.channel_lease import ChannelSecretLeases
from brain.ops.channel_store import ChannelRecord
from brain.ops.digest import (
    DailyDigest,
    DayClosed,
    Plan,
    WaveWindow,
    daily_digest,
    plan_from_wave_reports,
)
from brain.ops.digest_delivery import Delivery, DeliveryOutcome, DigestChannel, deliver_digest
from brain.ops.digest_destination import ConversationLister, connected_problem, destination_of
from brain.ops.idempotency import OperationLedger
from brain.ops.setting_store import put, read_namespace
from brain.tables.audit import attributed_to
from brain.tables.config import SettingType

# ------------------------------------------------------------------------ the figures
#: Who the digest's operation and its record are written as.
DIGEST_PRINCIPAL: Final = "worker.evening_digest"

#: The reach the record's write is attributed at: none, since nobody asked for it.
NO_REACH: Final = "0" * 32

#: Where yesterday's record is kept.
RECORD_NAMESPACE: Final = "digest"
RECORD_KEY: Final = "digest.record"
RECORD_DESCRIPTION: Final = (
    "What the last evening digest saw: the closed set and each day's newly closed tasks, for the "
    "next digest's movement and burn-down."
)

#: How many days of newly closed tasks the record keeps for the burn-down's rate.
HISTORY_DAYS: Final = 30

#: The three files the plan is read from, under the image's `docs/`.
STATUS_FILE: Final = "status.json"
WBS_FILE: Final = "wbs.json"
WINDOWS_FILE: Final = "wave-windows.json"

#: What an off digest says.
OFF: Final = "the evening digest is off: nobody has chosen where it goes"


class DigestRunError(Exception):
    """The digest could not be put together from what the image carries."""


# ------------------------------------------------------------------------ the record
@dataclass(frozen=True)
class DigestRecord:
    """What the last digest saw, kept for the next one."""

    day: date
    closed: frozenset[str]
    history: tuple[DayClosed, ...] = ()

    def as_value(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "closed": sorted(self.closed),
            "history": [
                {"day": one.day.isoformat(), "closed": sorted(one.closed)} for one in self.history
            ],
        }

    @classmethod
    def of(cls, value: object) -> DigestRecord | None:
        """The record a stored value holds, or None for one that is not a record."""
        if not isinstance(value, Mapping):
            return None
        try:
            return cls(
                day=date.fromisoformat(str(value["day"])),
                closed=frozenset(str(one) for one in value["closed"]),
                history=tuple(
                    DayClosed(
                        day=date.fromisoformat(str(one["day"])),
                        closed=frozenset(str(leaf) for leaf in one["closed"]),
                    )
                    for one in value.get("history", ())
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None


def next_record(previous: DigestRecord | None, plan: Plan, today: date) -> DigestRecord:
    """Today's record: the closed set now, and what closed since the last day before today.

    A second run on the same day replaces today's history entry rather than adding another, so a
    re-run cannot count a day twice in the burn-down's rate.
    """
    if previous is None:
        return DigestRecord(day=today, closed=plan.closed)
    earlier = tuple(one for one in previous.history if one.day < today)
    today_before = frozenset().union(*(one.closed for one in previous.history if one.day == today))
    since = previous.closed - today_before if previous.day == today else previous.closed
    kept = tuple(one for one in earlier if one.day > today - timedelta(days=HISTORY_DAYS))
    newly = DayClosed(day=today, closed=frozenset(plan.closed - since))
    return DigestRecord(day=today, closed=plan.closed, history=(*kept, newly))


# ------------------------------------------------------------------------ the plan
def plan_of(docs: Path) -> tuple[Plan, int, Mapping[int, WaveWindow]]:
    """The plan, the current wave and the wave windows, from the files the image carries."""
    from brain.status import load_wbs
    from brain.wave_report import report_for, wave_numbers

    wbs_path = docs / WBS_FILE
    if not wbs_path.exists():
        msg = "this image carries no work breakdown, so there is no plan to report on"
        raise DigestRunError(msg)
    wbs = load_wbs(wbs_path)
    status_path = docs / STATUS_FILE
    status: dict[str, Any] = (
        json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    )
    closed = set(status.get("done_task_ids", []))
    commits: list[dict[str, str]] = status.get("recent", [])
    plan = plan_from_wave_reports(
        report_for(wbs, number, closed, commits) for number in wave_numbers(wbs)
    )
    windows: dict[int, WaveWindow] = {}
    windows_path = docs / WINDOWS_FILE
    if windows_path.exists():
        raw = json.loads(windows_path.read_text(encoding="utf-8")).get("windows", {})
        for wave, window in raw.items():
            windows[int(wave)] = WaveWindow(
                wave=int(wave),
                start=date.fromisoformat(window["start"]),
                end=date.fromisoformat(window["end"]),
            )
    return plan, int(status.get("current_wave") or 0), windows


def compose(
    plan: Plan,
    *,
    wave: int,
    windows: Mapping[int, WaveWindow],
    previous: DigestRecord | None,
    today: date,
) -> DailyDigest:
    """Today's digest over yesterday's record. A first run says it has nothing to compare."""
    yesterday = previous if previous is not None and previous.day < today else None
    return daily_digest(
        plan=plan,
        windows=windows,
        history=() if previous is None else previous.history,
        wave=wave,
        today=today,
        previously_closed=None if yesterday is None else yesterday.closed,
    )


# ------------------------------------------------------------------------ the send
@runtime_checkable
class DigestWire(ConversationLister, Protocol):
    """A channel wire that can carry the digest: it lists conversations, names the room one of
    them is posted to, builds the send and judges the answer. `brain.channels.lark.LarkWire`."""

    def room_of(self, conversation: str) -> str: ...

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest: ...

    def judge(self, answer: VendorAnswer) -> CallOutcome: ...


class DigestSendRefusedError(Exception):
    """The channel did not accept the digest. The outcome is the wire's own judgement."""


@dataclass(frozen=True)
class WireSender:
    """`brain.ops.digest_delivery.DigestSender` over the chosen channel's own wire."""

    wire: DigestWire
    record: ChannelRecord
    secret: str
    transport: ChannelTransport
    now: datetime

    def send(self, payload: ChannelPayload, *, to: str, body: str) -> None:
        del payload  # The digest's classification is checked by the delivery; the body is text.
        request = self.wire.request_for(
            to=self.wire.room_of(to),
            text=body,
            secret=self.secret,
            tenant=self.record.tenant,
            now=self.now,
        )
        outcome = self.wire.judge(self.transport.send(request))
        if outcome is not CallOutcome.OK:
            raise DigestSendRefusedError(outcome.value)


#: How a send reaches the operation ledger: a connection of its own in autocommit mode.
LedgerRunner = Callable[[Callable[[OperationLedger], Delivery]], Delivery]


class ChannelRecordReader(Protocol):
    async def get(self, channel: Channel) -> ChannelRecord | None: ...


class DigestRecords(Protocol):
    """Where yesterday's record is kept. `StoredDigestRecords` over `ops.setting`."""

    async def read(self) -> DigestRecord | None: ...

    async def write(self, record: DigestRecord) -> None: ...


class StoredDigestRecords:
    """`DigestRecords` over the `digest.record` row of `ops.setting`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def read(self) -> DigestRecord | None:
        async with self.sessions() as session:
            held = await read_namespace(session, RECORD_NAMESPACE)
        one = held.get(RECORD_KEY)
        return None if one is None else DigestRecord.of(one.value)

    async def write(self, record: DigestRecord) -> None:
        """Keep today's record, attributed to the digest before the write so `0059`'s trigger
        records the setting's change as the digest's, at no reach, for today's run."""
        async with self.sessions() as session, session.begin():
            for statement in attributed_to(
                actor_id=DIGEST_PRINCIPAL,
                ent_hash=NO_REACH,
                trace_id=f"evening-digest-{record.day.isoformat()}",
            ):
                await session.execute(statement)
            await put(
                session,
                RECORD_KEY,
                value_type=SettingType.JSON,
                value=record.as_value(),
                description=RECORD_DESCRIPTION,
                updated_by=DIGEST_PRINCIPAL,
            )


async def run_digest(
    kept: DigestRecords,
    *,
    now: datetime,
    saved: str,
    zone: ZoneInfo,
    records: ChannelRecordReader,
    secrets: ChannelSecretLeases,
    transport: ChannelTransport,
    ledger: LedgerRunner,
    docs: Path,
    wires: Callable[[], Mapping[Channel, object]] = channel_wires,
) -> str:
    """One evening's digest: off, stopped with its reason, or sent once to the chosen place."""
    chosen = destination_of(saved)
    if chosen is None:
        return OFF
    record = await records.get(chosen.channel)
    wire = wires().get(chosen.channel)
    problem = connected_problem(record, secret_held=True)
    if problem or record is None or not isinstance(wire, DigestWire):
        return f"the evening digest stopped: {problem or 'this channel cannot carry it'}"
    today = now.astimezone(zone).date()
    plan, wave, windows = plan_of(docs)
    previous = await kept.read()
    digest = compose(plan, wave=wave, windows=windows, previous=previous, today=today)
    lease = secrets.lease(record, now=now)
    try:
        secret = lease.secret()
        if secret is None:
            return f"the evening digest stopped: {lease.failure}"
        sender = WireSender(wire=wire, record=record, secret=secret, transport=transport, now=now)
        room = DigestChannel(channel=chosen.channel, chat_id=chosen.conversation)
        delivery = await asyncio.to_thread(
            ledger,
            lambda held: deliver_digest(
                digest, channel=room, sender=sender, ledger=held, principal_id=DIGEST_PRINCIPAL
            ),
        )
    finally:
        lease.close(now)
    if delivery.outcome in (DeliveryOutcome.SENT, DeliveryOutcome.ALREADY_SENT):
        await kept.write(next_record(previous, plan, today))
    said = {
        DeliveryOutcome.SENT: "sent",
        DeliveryOutcome.ALREADY_SENT: "already sent today, not sent again",
        DeliveryOutcome.UNDELIVERED: "not delivered: the channel refused it",
        DeliveryOutcome.UNSETTLED: "not sent again: an earlier attempt's end is not known",
    }[delivery.outcome]
    return f"the evening digest for {today.isoformat()} on {chosen.channel.value}: {said}"


# ------------------------------------------------------------------ what the schedule calls
def run_evening_digest_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> str:
    """`run_digest` over this install: its saved destination and zone, its channel records, the
    worker's vault, the channel's own wire over HTTPS, and a ledger connection in autocommit
    mode opened for the one send, as `brain.channel_routes.ledger_of` opens one."""
    import psycopg

    from brain.channel_routes import HttpsTransport
    from brain.db import libpq_conninfo
    from brain.docs_routes import DOCS
    from brain.install import value_of
    from brain.locale import time_zone
    from brain.ops.channel_lease import worker_channel_secrets
    from brain.ops.channel_store import StoredChannels
    from brain.ops.digest_destination import DESTINATION_SETTING
    from brain.ops.operation_store import PostgresOperationLedger
    from brain.session import make_app_engine, make_session_factory

    def ledger(work: Callable[[OperationLedger], Delivery]) -> Delivery:
        with psycopg.connect(
            libpq_conninfo(database_url), autocommit=True, prepare_threshold=None
        ) as conn:
            return work(PostgresOperationLedger(conn))

    async def run() -> str:
        engine = make_app_engine(database_url)
        try:
            sessions = make_session_factory(engine)
            return await run_digest(
                StoredDigestRecords(sessions),
                now=now,
                saved=value_of(DESTINATION_SETTING),
                zone=time_zone(),
                records=StoredChannels(sessions),
                secrets=worker_channel_secrets(vault_address, vault_token),
                transport=HttpsTransport(),
                ledger=ledger,
                docs=DOCS,
            )
        finally:
            await engine.dispose()

    return asyncio.run(run(), loop_factory=loop_factory)
