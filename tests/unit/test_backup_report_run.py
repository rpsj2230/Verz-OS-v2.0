"""The daily backup report: what a read of the bucket records, and what is said and to whom.

Every collaborator is a stand-in the runner is handed, as in `test_digest_run.py`: the channel's
record, its wire, the borrowed key, the transport, the operation ledger and the bucket's listing.
The recording of the report is replaced by a list, because writing a setting needs a database and
the install check (`acceptance_checks_backup`) is where that half runs.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M30.3.10, M30.6.10
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.channels.adapter import VendorAnswer, VendorRequest
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.ops import backup_report_run as module
from brain.ops.backup_manifest import MANIFEST_SUFFIX
from brain.ops.backup_report_run import (
    NOBODY_TOLD,
    BackupReport,
    alerts_text,
    deliver_alerts,
    report_of,
)
from brain.ops.channel_lease import SendLease
from brain.ops.channel_store import ChannelRecord
from brain.ops.digest_delivery import DigestChannel
from brain.ops.idempotency import OperationLedger
from brain.ops.leases import SealedSecret
from brain.ops.recovery import Severity
from brain.ops.secrets import SecretRef, VaultRole
from tests.fixtures.operation_ledger import MemoryLedger

NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
FINISHED = datetime(2999, 6, 1, 2, 4, tzinfo=UTC)
ROOM = DigestChannel(channel=Channel.LARK, chat_id="oc_room")


def a_manifest(finished: datetime = FINISHED, **changes: Any) -> list[tuple[str, str]]:
    """One database copy as the nightly taker writes it, as the pair a bucket listing hands over."""
    document: dict[str, Any] = {
        "backup_id": f"database-{finished:%Y%m%dT%H%M%SZ}",
        "coverage": "database",
        "method": "full",
        "destination": "s3://backups",
        "started_at": (finished - timedelta(minutes=4)).isoformat(),
        "finished_at": finished.isoformat(),
        "recoverable_to": finished.isoformat(),
        "size_bytes": 4_194_304,
    }
    document.update(changes)
    return [(f"database-{finished:%Y%m%d}{MANIFEST_SUFFIX}", json.dumps(document))]


class Wire:
    def room_of(self, conversation: str) -> str:
        return f"room:{conversation}"

    def conversations_request(self, **_: object) -> VendorRequest:
        raise AssertionError("sending never lists")

    def conversations_page(self, answer: VendorAnswer) -> tuple[tuple[tuple[str, str], ...], str]:
        raise AssertionError("sending never lists")

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest:
        return VendorRequest(url=f"https://vendor.invalid/{to}", headers={}, body=text.encode())

    def judge(self, answer: VendorAnswer) -> CallOutcome:
        return CallOutcome.OK


class Transport:
    def __init__(self) -> None:
        self.sent: list[VendorRequest] = []

    def send(self, request: VendorRequest) -> VendorAnswer:
        self.sent.append(request)
        return VendorAnswer(status=200, body=b"{}")

    def read(self, request: VendorRequest) -> VendorAnswer:
        raise AssertionError("sending never reads")


class Records:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    async def get(self, channel: Channel) -> ChannelRecord:
        return ChannelRecord(
            channel=Channel.LARK,
            enabled=self.enabled,
            tenant={"app_id": "cli_x", "platform": "larksuite.com", "bot_id": "ou_bot"},
            secret=SecretRef(path="providers/channel_lark", role=VaultRole.APPLICATION),
            updated_by="u_admin",
            updated_at=NOW,
        )


class Lender:
    def lease(self, record: ChannelRecord, *, now: datetime) -> SendLease:
        return SendLease(secret=SealedSecret("stand-in"))


class Sender:
    """Records what it is asked to send, and refuses when told to."""

    def __init__(self, *, fails: bool = False) -> None:
        self.bodies: list[str] = []
        self.fails = fails

    def send(self, payload: object, *, to: str, body: str) -> None:
        if self.fails:
            raise RuntimeError("the room oc_room refused: some detail that must not be kept")
        self.bodies.append(body)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[BackupReport]:
    kept: list[BackupReport] = []

    async def keep(sessions: object, report: BackupReport) -> None:
        kept.append(report)

    monkeypatch.setattr(module, "record_report", keep)
    return kept


def run(
    listing: Callable[[], list[tuple[str, str]]] | None,
    *,
    unread: str = "",
    saved: str = "lark:oc_room",
    ledger: MemoryLedger | None = None,
    transport: Transport | None = None,
    enabled: bool = True,
    now: datetime = NOW,
    profile: str = "lite",
) -> str:
    held = ledger if ledger is not None else MemoryLedger()

    def through(work: Callable[[OperationLedger], tuple[int, int]]) -> tuple[int, int]:
        return work(held)

    return asyncio.run(
        module.run_backup_report(
            sessions=None,  # type: ignore[arg-type]
            listing=listing,
            unread=unread,
            profile=profile,
            now=now,
            saved=saved,
            records=Records(enabled),
            secrets=Lender(),
            transport=transport if transport is not None else Transport(),
            ledger=through,
            wires=lambda: {Channel.LARK: Wire()},
        )
    )


# ------------------------------------------------------------------------ the report
def test_a_recent_database_copy_is_inside_the_recovery_point_and_the_gaps_are_named() -> None:
    """The positive case and the honest one: the database copy taken ten hours ago is inside a lite
    install's day and the coverages nothing copies are alerted as having no copy at all. Delete
    this and a report that alerted on everything, or on nothing, satisfies the aged test below."""
    report = report_of(a_manifest(), profile="lite", now=NOW)

    by = {one.coverage: one for one in report.coverages}
    assert by["database"].within_objective and by["database"].newest == FINISHED
    assert not by["object_store"].within_objective and by["object_store"].newest is None
    assert {one.coverage.value for one in report.alerts if one.coverage} == {
        "object_store",
        "configuration",
    }
    assert report.was_read and report.unreadable_records == 0


def test_a_copy_older_than_the_recovery_point_is_an_alert_naming_the_coverage_and_the_age() -> None:
    """M30.3.10. The newest database copy is thirty hours old against a day. Delete this and the
    one alert the leaf asks for is never raised from a real manifest."""
    report = report_of(a_manifest(), profile="lite", now=FINISHED + timedelta(hours=30))

    aged = [
        one
        for one in report.alerts
        if one.coverage is not None and one.coverage.value == "database"
    ]
    assert len(aged) == 1 and aged[0].severity is Severity.BACKUP_AGED
    assert "behind" in aged[0].text and "86400s" in aged[0].text


def test_a_manifest_that_cannot_be_read_is_counted_and_never_dropped() -> None:
    """Delete this and one truncated manifest vanishes from the report, so the report is confident
    about a bucket it only half read."""
    listing = [*a_manifest(), (f"broken{MANIFEST_SUFFIX}", "{not json")]

    report = report_of(listing, profile="lite", now=NOW)

    assert report.unreadable_records == 1


def test_the_recorded_value_names_coverages_and_ages_and_nothing_a_backup_holds() -> None:
    """Delete this and the report row, which any reader of the Recovery screen may see, could
    carry a path, a destination or a key."""
    report = report_of(a_manifest(destination="s3://secret-bucket/x"), profile="lite", now=NOW)

    value = json.dumps(report.as_value())

    assert "secret-bucket" not in value and "s3://" not in value
    assert json.loads(value)["coverages"][0]["coverage"] == "database"


# ------------------------------------------------------------------------ the run
def test_the_report_is_recorded_and_the_alert_is_said_once_a_day_to_the_chosen_room(
    recorded: list[BackupReport],
) -> None:
    """M30.6.10. Two runs the same day record twice and post once, to the room's own address, and
    the next day says it again. Delete this and a restarted worker posts the morning's alert at
    noon, or an alert that still holds is said once and never again."""
    ledger, transport = MemoryLedger(), Transport()
    later = FINISHED + timedelta(hours=30)

    first = run(lambda: a_manifest(), ledger=ledger, transport=transport, now=later)
    again = run(lambda: a_manifest(), ledger=ledger, transport=transport, now=later)
    tomorrow = run(
        lambda: a_manifest(),
        ledger=ledger,
        transport=transport,
        now=later + timedelta(days=1),
    )

    assert len(recorded) == 3 and all(one.alerts for one in recorded)
    assert [one.url for one in transport.sent] == ["https://vendor.invalid/room:oc_room"] * 2
    assert "1 message sent" in first and "1 message sent" in again and "1 message sent" in tomorrow
    assert b"Backup alerts:" in transport.sent[0].body
    assert b"behind" in transport.sent[0].body


def test_a_run_with_nothing_to_say_records_the_report_and_sends_nothing(
    recorded: list[BackupReport],
) -> None:
    """Delete this and a clean install posts an empty alert every morning."""
    fully = [
        *a_manifest(),
        *[
            (
                f"{kind}-20{MANIFEST_SUFFIX}",
                json.dumps(
                    {
                        "backup_id": f"{kind}-1",
                        "coverage": kind,
                        "method": "full",
                        "destination": "s3://backups",
                        "started_at": (FINISHED - timedelta(minutes=4)).isoformat(),
                        "finished_at": FINISHED.isoformat(),
                        "recoverable_to": FINISHED.isoformat(),
                        "size_bytes": 10,
                    }
                ),
            )
            for kind in ("object_store", "configuration")
        ],
    ]
    transport = Transport()

    said = run(lambda: fully, transport=transport)

    assert said.startswith("recorded:") and transport.sent == []
    assert len(recorded) == 1 and recorded[0].alerts == ()


def test_with_no_conversation_chosen_the_report_is_kept_and_nobody_is_told(
    recorded: list[BackupReport],
) -> None:
    """Delete this and an install nobody configured either posts alerts somewhere nobody chose or
    loses the report with the message."""
    transport = Transport()

    said = run(
        lambda: a_manifest(), saved="unset", transport=transport, now=FINISHED + timedelta(hours=30)
    )

    assert NOBODY_TOLD in said and transport.sent == [] and len(recorded) == 1


def test_a_bucket_that_cannot_be_read_is_recorded_as_unread_and_raises_no_alert(
    recorded: list[BackupReport],
) -> None:
    """Delete this and an install with no object store connected reports that it has no copies,
    which is a claim about a bucket nobody read."""
    transport = Transport()

    said = run(None, unread="no object store is connected", transport=transport)

    assert "not read" in said and "no object store is connected" in said
    assert not recorded[0].was_read and recorded[0].alerts == ()
    assert transport.sent == []


def test_a_bucket_that_raises_is_recorded_as_unread_by_the_type_of_the_error(
    recorded: list[BackupReport],
) -> None:
    """Delete this and one timeout loses the day's report, so the check that exists to say it ran
    is the thing that did not."""

    def broken() -> list[tuple[str, str]]:
        raise TimeoutError("the store at https://internal.example answered slowly")

    said = run(broken)

    assert "TimeoutError" in said and "internal.example" not in said
    assert not recorded[0].was_read


def test_a_channel_that_refuses_is_counted_and_the_report_is_still_kept(
    recorded: list[BackupReport],
) -> None:
    """Delete this and a refused send raises into the schedule, which loses the report's record of
    having run."""
    sender = Sender(fails=True)

    result = deliver_alerts(
        report_of(a_manifest(), profile="lite", now=FINISHED + timedelta(hours=30)).alerts,
        day="2999-06-02",
        channel=ROOM,
        sender=sender,
        ledger=MemoryLedger(),
        principal_id="svc",
    )

    assert result == (0, 1)


def test_the_message_names_the_severity_and_the_text_and_no_more() -> None:
    """Delete this and the message could carry a field `Alert` was never meant to hold."""
    report = report_of(a_manifest(), profile="lite", now=NOW)

    text = alerts_text(report.alerts)

    assert text.startswith("Backup alerts:\n- ")
    assert all(one.text in text for one in report.alerts)


def test_an_alert_that_arrives_later_the_same_day_is_still_said(
    recorded: list[BackupReport],
) -> None:
    """The key carries which alerts there are, so a second message goes out when the set changes
    and none when it does not. Delete this and one alert at breakfast silences every other fault
    found that day, which is the check going quiet at the moment it has most to say."""
    ledger, transport = MemoryLedger(), Transport()
    later = FINISHED + timedelta(hours=30)
    object_store = [
        (
            f"object_store-20{MANIFEST_SUFFIX}",
            json.dumps(
                {
                    "backup_id": "object_store-1",
                    "coverage": "object_store",
                    "method": "full",
                    "destination": "s3://backups",
                    "started_at": (later - timedelta(minutes=4)).isoformat(),
                    "finished_at": later.isoformat(),
                    "recoverable_to": later.isoformat(),
                    "size_bytes": 10,
                }
            ),
        )
    ]

    run(lambda: a_manifest(), ledger=ledger, transport=transport, now=later)
    run(lambda: a_manifest(), ledger=ledger, transport=transport, now=later)
    changed = run(
        lambda: [*a_manifest(), *object_store], ledger=ledger, transport=transport, now=later
    )

    assert len(transport.sent) == 2 and "1 message sent" in changed
