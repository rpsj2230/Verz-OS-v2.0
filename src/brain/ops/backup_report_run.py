"""The daily backup report: read the copies, record what was found, and say so once to the room
the install chose.

`brain.ops.recovery.alerts` decided when a backup is too old or a rehearsal did not verify, and
`brain.console.recovery_view.panel` decided how to describe the whole position, and nothing called
either on a schedule: the job `backup_exposure` said it was waiting for "a record of each backup
taken", the alert had no channel, and an install whose nightly copy had stopped for a month
showed nothing anywhere until somebody opened the Recovery screen and read it. This is the call
site, and it is deliberately only a call site.

**What is recorded is the report, and it is recorded whether or not anybody is told.** One row in
`ops.setting` under `backup.report`, replaced each run: when it was read, the profile, the
panel's one-word answer, each coverage's newest copy and how far behind it leaves the install,
whether a rehearsal is owed, how many records could not be read, and each alert's severity,
coverage and text. A setting rather than a table, for the argument `brain.ops.digest_run` makes
for its own record: it is one value the worker writes and the next reader reads, and the row says
who wrote it and when. An install that has never been able to read its backups records that, with
the sentence saying why, rather than recording nothing: **the report row is what separates "the
check ran and found a bucket it could not read" from "the check never ran"**, and the second is
the failure this exists to catch.

**The alert is sent to the conversation the evening digest goes to, and that choice is a
question.** Needs-rupash item 231 asks whether alerts want a room of their own. Until it is
answered the digest's conversation is the one place an administrator has already chosen and
checked a connected channel can post to (`brain.ops.digest_destination`), so using it needs no
new setting and invents no address. If nobody has chosen one, the report is recorded and nothing
is sent, and the run says so.

**One message a day for the set, through the operation ledger.** The key is the day and which
alerts there are, so a worker restarted at noon does not post the morning's message again, a new
alert arriving the same afternoon is still said, and an alert that still holds tomorrow is said
again tomorrow, which is the point of a daily check: a copy that has been missing for a week is a
copy somebody should be told is missing on each of those days. See `brain.ops.digest_delivery`
for the idempotency this reuses.

**The text names the kind of fault and the age and never what a backup holds.** `Alert.text` is
composed by `brain.ops.recovery` from coverages, ages and a backup's identifier, and this module
adds only the severity word and the room's own framing.

Rejected: sending to people holding the operations alert capability. That needs a channel per
person, and a chat binding keeps no address to send to (`brain.ops.notices`, approval request).
Rejected: raising the report as a ledger entry. It is a reading of a bucket, not an act by a
person, and the ledger records acts.

Task ids: M30.3.10, M30.6.10
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.channels.adapter import ChannelTransport, channel_wires
from brain.connectors.throttle import CallOutcome
from brain.console.recovery_view import panel as recovery_panel
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.ops.backup_manifest import read_drills, read_manifests
from brain.ops.channel_lease import ChannelSecretLeases
from brain.ops.digest_delivery import DigestChannel, DigestSender
from brain.ops.digest_destination import connected_problem, destination_of
from brain.ops.digest_run import ChannelRecordReader, DigestWire, WireSender
from brain.ops.idempotency import (
    Disposition,
    Intent,
    Operation,
    OperationLedger,
    issue_once,
    operation_for,
)
from brain.ops.recovery import Alert, alerts
from brain.ops.setting_store import put, read_namespace
from brain.tables.audit import attributed_to
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons
#: Why the report is recorded when nothing is sent.
A_REPORT_THAT_IS_ONLY_SENT_CANNOT_SHOW_THE_CHECK_RAN: Final = (
    "A check whose only output is a message says nothing on the days it has nothing to say, and "
    "silence is also what a check that stopped looks like. The report is kept every run, so the "
    "Recovery screen and an install check can read when it last ran and what it found."
)

#: Why an unreadable bucket is a finding and not a quiet run.
AN_UNREAD_BUCKET_IS_RECORDED_AS_UNREAD: Final = (
    "A backup bucket this process could not read is not a bucket with nothing in it. The report "
    "records that it was not read and why, in the connection's own words, and raises no alert "
    "that claims there are no copies."
)

# ------------------------------------------------------------------------ the figures
#: Who the report's row and the alert's operation are written as.
REPORT_PRINCIPAL: Final = "worker.backup_report"

#: The reach the row's write is attributed at: none, since nobody asked for it.
NO_REACH: Final = "0" * 32

REPORT_NAMESPACE: Final = "backup"
REPORT_KEY: Final = "backup.report"
REPORT_DESCRIPTION: Final = (
    "What the daily backup report found: each coverage's newest copy, the position in one word, "
    "and every alert, as of the instant it was read."
)

#: The tool an alert's operation is recorded under.
ALERT_TOOL: Final = "backup.alert"

#: What a run says when nobody has chosen where alerts go.
NOBODY_TOLD: Final = "recorded, and nobody was told: no conversation has been chosen for alerts"

T = TypeVar("T")


# ------------------------------------------------------------------------ the report
@dataclass(frozen=True)
class CoverageFinding:
    """One coverage's newest copy and how far behind it leaves the install."""

    coverage: str
    newest: datetime | None
    exposure_seconds: float | None
    within_objective: bool


@dataclass(frozen=True)
class BackupReport:
    """What one read of the backup bucket found, or why there was nothing to find."""

    at: datetime
    profile: str
    #: The sentence saying why the bucket was not read, or empty when it was.
    unread: str
    answer: str = ""
    coverages: tuple[CoverageFinding, ...] = ()
    drill_due: bool = False
    unreadable_records: int = 0
    alerts: tuple[Alert, ...] = ()

    @property
    def was_read(self) -> bool:
        return not self.unread

    def as_value(self) -> dict[str, Any]:
        """The row's value. Names a coverage and an age and never a record."""
        return {
            "at": self.at.isoformat(),
            "profile": self.profile,
            "read": self.was_read,
            "unread": self.unread,
            "answer": self.answer,
            "drill_due": self.drill_due,
            "unreadable_records": self.unreadable_records,
            "coverages": [
                {
                    "coverage": one.coverage,
                    "newest": None if one.newest is None else one.newest.isoformat(),
                    "exposure_seconds": one.exposure_seconds,
                    "within_objective": one.within_objective,
                }
                for one in self.coverages
            ],
            "alerts": [
                {"severity": one.severity.name, "coverage": one.coverage, "text": one.text}
                for one in self.alerts
            ],
        }


def unread_report(*, at: datetime, profile: str, why: str) -> BackupReport:
    """A report that says the bucket was not read. See `AN_UNREAD_BUCKET_IS_RECORDED_AS_UNREAD`."""
    return BackupReport(at=at, profile=profile, unread=why)


def report_of(listing: Sequence[tuple[str, str]], *, profile: str, now: datetime) -> BackupReport:
    """The report over one listing of the backup bucket's manifests and drill records."""
    backups, bad_manifests = read_manifests(listing)
    verifications, bad_drills = read_drills(listing)
    panel = recovery_panel(
        backups=backups,
        verifications=verifications,
        profile=profile,
        now=now,
        unreadable=(*bad_manifests, *bad_drills),
    )
    return BackupReport(
        at=now,
        profile=profile,
        unread="",
        answer=panel.assurance.value,
        coverages=tuple(
            CoverageFinding(
                coverage=one.coverage.value,
                newest=None if one.newest is None else one.newest.recoverable_to,
                exposure_seconds=one.measured_exposure_seconds,
                within_objective=one.within_objective,
            )
            for one in panel.copies
        ),
        drill_due=panel.drill_is_due,
        unreadable_records=len(panel.unreadable),
        alerts=alerts(backups=backups, verifications=verifications, profile=profile, now=now),
    )


# ------------------------------------------------------------------------ the record
async def record_report(sessions: async_sessionmaker[AsyncSession], report: BackupReport) -> None:
    """Keep this run's report, attributed to the report before the write so `0059`'s trigger
    records the setting's change as the worker's, at no reach, for this day's run."""
    async with sessions() as session, session.begin():
        for statement in attributed_to(
            actor_id=REPORT_PRINCIPAL,
            ent_hash=NO_REACH,
            trace_id=f"backup-report-{report.at.date().isoformat()}",
        ):
            await session.execute(statement)
        await put(
            session,
            REPORT_KEY,
            value_type=SettingType.JSON,
            value=report.as_value(),
            description=REPORT_DESCRIPTION,
            updated_by=REPORT_PRINCIPAL,
        )


async def recorded_report(session: AsyncSession) -> Mapping[str, Any] | None:
    """The last report's value, or None when none has been recorded on this install."""
    held = await read_namespace(session, REPORT_NAMESPACE)
    one = held.get(REPORT_KEY)
    if one is None or not isinstance(one.value, Mapping):
        return None
    return one.value


# ------------------------------------------------------------------------ the send
def alerts_text(found: Sequence[Alert]) -> str:
    """What the room reads for a day's alerts: one message, the worst first as `alerts` sorts."""
    lines = [f"- {one.severity.name.lower().replace('_', ' ')}: {one.text}" for one in found]
    return "Backup alerts:\n" + "\n".join(lines)


def alerts_operation(
    found: Sequence[Alert], *, day: str, channel: DigestChannel, principal_id: str
) -> Operation:
    """The operation one set of alerts to one room on one day is.

    The key carries a short digest of which alerts there are, so a restart does not say the same
    set twice and a new alert arriving the same day is still said. One message for the set rather
    than one per alert, because an install with a known gap (the object store has no copy) would
    otherwise post a line per gap every day to a room people read.
    """
    which = sorted(
        f"{one.severity.name}.{'all' if one.coverage is None else one.coverage.value}"
        for one in found
    )
    held = hashlib.sha256("|".join(which).encode("utf-8")).hexdigest()[:12]
    return operation_for(
        Intent(principal_id=principal_id, intent_ref=f"backup.alerts.{day}.{held}"),
        connector=channel.channel.value,
        tool=ALERT_TOOL,
        arguments={"chat_id": channel.chat_id},
    )


def deliver_alerts(
    found: Sequence[Alert],
    *,
    day: str,
    channel: DigestChannel,
    sender: DigestSender,
    ledger: OperationLedger,
    principal_id: str,
) -> tuple[int, int]:
    """Say the day's alerts once. Returns messages sent and messages not sent, one or the other.

    A refused send is counted as not sent and does not raise: the report exists whether or not
    the channel took the alert, and a job that died on a transport error would lose the report's
    record of having run. A ledger failure is raised, because that is not the channel refusing.
    An alert said earlier today counts as told: it is the duplicate guard working.
    """
    if not found:
        return 0, 0
    refused: list[str] = []

    def post(_: Operation) -> CallOutcome:
        try:
            sender.send(ChannelPayload(label=""), to=channel.chat_id, body=alerts_text(found))
        except Exception as exc:
            # The class name and never the message: a transport error quotes what it sent.
            refused.append(type(exc).__name__)
            raise
        return CallOutcome.OK

    operation = alerts_operation(found, day=day, channel=channel, principal_id=principal_id)
    try:
        issued = issue_once(ledger, operation, post)
    except Exception:
        if not refused:
            raise
        return 0, 1
    told = issued.issued or (
        issued.resumption is not None and issued.resumption.disposition is Disposition.DONE
    )
    return (1, 0) if told else (0, 1)


#: How a send reaches the operation ledger: a connection of its own in autocommit mode.
LedgerRunner = Callable[[Callable[[OperationLedger], T]], T]


async def run_backup_report(
    *,
    sessions: async_sessionmaker[AsyncSession],
    listing: Callable[[], Sequence[tuple[str, str]]] | None,
    unread: str,
    profile: str,
    now: datetime,
    saved: str,
    records: ChannelRecordReader,
    secrets: ChannelSecretLeases,
    transport: ChannelTransport,
    ledger: LedgerRunner[tuple[int, int]],
    wires: Callable[[], Mapping[Channel, object]] = channel_wires,
) -> str:
    """One day's report: read, record, and say each alert once to the chosen conversation.

    `listing` is None when the bucket cannot be read at all, and `unread` then says why; a
    listing that raises is the same finding with the exception's type as the reason.
    """
    if listing is None:
        report = unread_report(at=now, profile=profile, why=unread)
    else:
        try:
            listed = await asyncio.to_thread(lambda: tuple(listing()))
        except Exception as exc:
            report = unread_report(
                at=now,
                profile=profile,
                why=f"the backup bucket did not answer ({type(exc).__name__})",
            )
        else:
            report = report_of(listed, profile=profile, now=now)
    await record_report(sessions, report)
    if not report.was_read:
        return f"the backup bucket was not read, and that is recorded: {report.unread}"
    summary = f"{report.answer}; {len(report.alerts)} alert(s)"
    if not report.alerts:
        return f"recorded: {summary}"
    chosen = destination_of(saved)
    if chosen is None:
        return f"{NOBODY_TOLD}: {summary}"
    record = await records.get(chosen.channel)
    wire = wires().get(chosen.channel)
    problem = connected_problem(record, secret_held=True)
    if problem or record is None or not isinstance(wire, DigestWire):
        return f"recorded, and not sent: {problem or 'this channel cannot carry it'}: {summary}"
    lease = secrets.lease(record, now=now)
    try:
        secret = lease.secret()
        if secret is None:
            return f"recorded, and not sent: {lease.failure}: {summary}"
        sender = WireSender(wire=wire, record=record, secret=secret, transport=transport, now=now)
        room = DigestChannel(channel=chosen.channel, chat_id=chosen.conversation)
        sent, not_sent = await asyncio.to_thread(
            ledger,
            lambda held: deliver_alerts(
                report.alerts,
                day=now.date().isoformat(),
                channel=room,
                sender=sender,
                ledger=held,
                principal_id=REPORT_PRINCIPAL,
            ),
        )
    finally:
        lease.close(now)
    where = chosen.channel.value
    return f"recorded: {summary}; {sent} message sent and {not_sent} not sent to {where}"


# ------------------------------------------------------------------ what the schedule calls
def run_backup_report_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    profile: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> str:
    """`run_backup_report` over this install: its object store, saved destination, channel
    records, the worker's vault, the channel's own wire over HTTPS, and a ledger connection in
    autocommit mode opened for the sends, as `brain.ops.digest_run.run_evening_digest_now` does."""
    import psycopg

    from brain.channel_routes import HttpsTransport
    from brain.db import libpq_conninfo
    from brain.install import value_of
    from brain.ops.channel_lease import worker_channel_secrets
    from brain.ops.channel_store import StoredChannels
    from brain.ops.digest_destination import DESTINATION_SETTING
    from brain.ops.object_store import backup_objects, object_store_at_start
    from brain.ops.operation_store import PostgresOperationLedger
    from brain.session import make_app_engine, make_session_factory

    store = object_store_at_start(vault_address, vault_token)

    def ledger(work: Callable[[OperationLedger], tuple[int, int]]) -> tuple[int, int]:
        with psycopg.connect(
            libpq_conninfo(database_url), autocommit=True, prepare_threshold=None
        ) as conn:
            return work(PostgresOperationLedger(conn))

    async def run() -> str:
        engine = make_app_engine(database_url)
        try:
            sessions = make_session_factory(engine)
            return await run_backup_report(
                sessions=sessions,
                listing=None if store.backend is None else backup_objects(store.backend),
                unread=store.unconnected,
                profile=profile,
                now=now,
                saved=value_of(DESTINATION_SETTING),
                records=StoredChannels(sessions),
                secrets=worker_channel_secrets(vault_address, vault_token),
                transport=HttpsTransport(),
                ledger=ledger,
            )
        finally:
            await engine.dispose()

    return asyncio.run(run(), loop_factory=loop_factory)
