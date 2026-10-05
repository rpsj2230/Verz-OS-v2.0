"""Sending an approved connector write: with its own key, once, and read back before it is done.

Driven over Cloudflare's DNS change, the one write a shipped connector declares, with a recorded
account that applies what it is sent to the one record it answers for, a stand-in vault handing a
made-up key per slot, and the leash's own `govern` and approval. Nothing here opens a socket.

Task ids: M11.7.3
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from brain.connectors import cloudflare
from brain.connectors.cloudflare import DNS_CHANGE_TOOL, DNS_RECORD, DnsChange
from brain.connectors.contract import ConnectorContractError
from brain.connectors.manifest import manifest_digest
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import Governed, Leash, LeashEntry, SuspendedAction, govern
from brain.ops.acceptance_checks import _HeldLedger
from brain.ops.connectable import manifest_for
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import ConnectorKeyAbsentError, SourceAnswer
from brain.ops.connector_write_run import (
    MAY_HAVE_BEEN_SENT,
    NOT_SENT,
    READ_BACK_DIFFERS,
    SENT_ALREADY,
    SENT_AND_READ_BACK,
    SOURCE_REFUSED_THE_CHANGE,
    WRITE_KEY_UNREADABLE,
    WriteOutcome,
    WriteReport,
    send_approved,
    unsent_because,
)
from brain.ops.credentials import connector_key_slot, connector_write_slot
from brain.ops.secrets import SecretRef, SecretsUnavailableError
from tests.fixtures.cassettes.cloudflare import RECORD, ZONE
from tests.unit.test_cloudflare import INDEXED, console_settings

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
DEPARTMENT: Final = "operations"
AGENT: Final = "agent.dns"
WRITE_PATH: Final = connector_write_slot(cloudflare.CLOUDFLARE, "dns_changes").path
READ_PATH: Final = connector_key_slot(cloudflare.CLOUDFLARE).path
KEYS: Final = {READ_PATH: "READ-KEY-SENTINEL", WRITE_PATH: "WRITE-KEY-SENTINEL"}
CONTENT: Final = "192.0.2.10"
POLICY: Final = FieldPolicy(
    rules=tuple(
        FieldRule.of(DNS_RECORD, name, f"read:dns_record.{name}", Classification.INTERNAL)
        for name in ("name", "type", "content", "ttl", "proxied", "zone_id", "department")
    )
)
CALM: Final = RiskAssessment(score=0, matched=())


def holding(principal: str, *capabilities: str) -> EntitlementSet:
    scope = Scope.department(DEPARTMENT)
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=one), scope=scope) for one in capabilities),
    )


READS: Final = (
    "read:dns_record",
    "read:dns_record.name",
    "read:dns_record.type",
    "read:dns_record.ttl",
    "read:dns_record.proxied",
)
OPERATOR: Final = holding("u_operator", "write:dns_record", *READS, "read:dns_record.content")
CEILING: Final = holding(AGENT, "write:dns_record", *READS, "read:dns_record.content")
LEASH: Final = Leash(
    entries=(
        LeashEntry(
            agent_id=AGENT,
            target=DNS_RECORD,
            scope=Scope.department(DEPARTMENT),
            rung=AutonomyTier.AUTONOMOUS,
        ),
    )
)


# ------------------------------------------------------------------ the stand-ins
@dataclass
class Lease:
    given: str | None
    failure: SecretsUnavailableError | None = None
    closed: list[datetime] = field(default_factory=list)

    def key(self) -> str:
        if self.failure is not None:
            raise self.failure
        if self.given is None:
            raise ConnectorKeyAbsentError("no key is kept here")
        return self.given

    def close(self, now: datetime) -> LeaseOutcome:
        self.closed.append(now)
        return LeaseOutcome.REVOKED


@dataclass
class Keys:
    """A key per slot, the write key only when the install allowed the write."""

    allows: bool = True
    unreadable: bool = False
    leases: list[tuple[str, Lease]] = field(default_factory=list)

    def lease(self, ref: SecretRef, *, now: datetime) -> Lease:
        del now
        if ref.path == WRITE_PATH and self.unreadable:
            one = Lease(None, failure=SecretsUnavailableError("the vault did not answer"))
        elif ref.path == WRITE_PATH and not self.allows:
            one = Lease(None)
        else:
            one = Lease(KEYS[ref.path])
        self.leases.append((ref.path, one))
        return one


@dataclass
class Account:
    """Cloudflare's one record: read with `get`, changed with `send`, each call noted by its key."""

    applies: bool = True
    refuses: int | None = None
    record: dict[str, Any] = field(
        default_factory=lambda: {
            "id": RECORD,
            "name": "www.example.com",
            "type": "A",
            "content": "192.0.2.1",
            "ttl": 1,
            "proxied": False,
        }
    )
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)

    def _answer(self) -> SourceAnswer:
        body = {"success": True, "errors": [], "messages": [], "result": self.record}
        return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode("utf-8"))

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        self.calls.append(("GET", url, headers["Authorization"]))
        return self._answer()

    def send(
        self,
        method: str,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        del address, max_bytes
        self.calls.append((method, url, headers["Authorization"]))
        change = json.loads(body)
        self.sent.append(change)
        if self.refuses is not None:
            return SourceAnswer(status=self.refuses, headers={}, body=b"{}")
        if self.applies:
            self.record = {**self.record, **change}
        return self._answer()


class Public:
    def resolve(self, host: str) -> list[str]:
        del host
        return ["104.16.132.229"]


def connection() -> Connection:
    settings = console_settings()
    return Connection(
        connector=cloudflare.CLOUDFLARE,
        settings=settings,
        digest=manifest_digest(manifest_for(cloudflare.CLOUDFLARE, settings)),
        connected_by="u_admin",
        connected_at=NOW,
    )


def approved(*, content: str = CONTENT, approve: bool = True, **changed: Any) -> SuspendedAction:
    """A DNS change an agent prepared under an Autonomous leash, held by the gate, and approved."""
    change = DnsChange(
        record=INDEXED, name="www.example.com", record_type="A", content=content, **changed
    )
    governed: Governed[Any] = govern(
        cloudflare.prepare_dns_change(change, agent_id=AGENT, department=DEPARTMENT),
        caller=OPERATOR,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=LEASH,
        assessment=CALM,
        trace_id="t-dns",
        now=NOW,
        simulate=lambda action: pytest.fail("a held change was simulated"),
        execute=lambda action: pytest.fail("a held change was run by the gate"),
        ledger=_HeldLedger(),
    )
    held = governed.suspension
    assert held is not None
    return held.approved_by("u_approver", NOW) if approve else held


def send(
    suspension: SuspendedAction, account: Account, keys: Keys, ledger: Any = None
) -> WriteReport:
    return send_approved(
        suspension,
        connection=connection(),
        keys=keys,
        caller=account,
        resolver=Public(),
        clock=lambda: NOW,
        reach=OPERATOR,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=LEASH,
        assessment=CALM,
        trace_id="t-send",
        ledger=_HeldLedger() if ledger is None else ledger,
    )


ONE_RECORD: Final = f"{cloudflare.BASE_URL}/zones/{ZONE}/dns_records/{RECORD}"


# ------------------------------------------------------------------ with and without the grant
def test_without_the_grants_key_an_approved_change_is_not_sent_and_not_tried() -> None:
    """**`brain.ops.connector_write_run.WITHOUT_ITS_KEY_A_WRITE_IS_NOT_TRIED`.** On an install that
    has not given the DNS change key, an approved change is reported not allowed in the grant's own
    words, nothing is sent or read, and the operation ledger records nothing; so once the key is
    given the same approval is sent. Delete this and an approval taken before the write was allowed
    is remembered as a send that failed, or is sent with no key of its own."""
    account, ledger = Account(), _HeldLedger()
    change = approved()

    held = send(change, account, Keys(allows=False), ledger)
    later = send(change, account, Keys(allows=True), ledger)

    assert (held.outcome, held.told) == (
        WriteOutcome.NOT_ALLOWED,
        cloudflare.THIS_INSTALL_HAS_NOT_ALLOWED_DNS_CHANGES,
    )
    assert later.outcome is WriteOutcome.DONE
    assert [method for method, _, _ in account.calls] == ["PATCH", "GET"]


def test_with_the_grant_a_change_is_sent_with_its_own_key_and_read_back_with_the_read_key() -> None:
    """**The positive case.** One PATCH of exactly the fields the change set, to the record's own
    address, carrying the write key; then one GET of the record carrying the read key, which finds
    it holding what was approved, so the change is reported done and every lease is given back.
    Delete this and a change can be sent with the read key, read back with the write key, or
    reported done from the send's own answer."""
    account, keys = Account(), Keys()

    report = send(approved(), account, keys)

    assert (report.outcome, report.told) == (WriteOutcome.DONE, SENT_AND_READ_BACK)
    assert account.calls == [
        ("PATCH", ONE_RECORD, f"Bearer {KEYS[WRITE_PATH]}"),
        ("GET", ONE_RECORD, f"Bearer {KEYS[READ_PATH]}"),
    ]
    assert account.sent == [{"name": "www.example.com", "type": "A", "content": CONTENT}]
    assert all(one.closed == [NOW] for _, one in keys.leases)
    assert report.differs == ()


def test_an_approval_resumed_twice_is_sent_once() -> None:
    """**Sent once.** The same approval resumed a second time over the same operation ledger finds
    its key already won, sends nothing and says so. Delete this and a retried request sends a DNS
    change twice."""
    account, ledger = Account(), _HeldLedger()
    change = approved()

    first = send(change, account, Keys(), ledger)
    second = send(change, account, Keys(), ledger)

    assert first.outcome is WriteOutcome.DONE
    assert (second.outcome, second.told) == (WriteOutcome.ALREADY_SENT, SENT_ALREADY)
    assert [method for method, _, _ in account.calls] == ["PATCH", "GET"]


def test_a_record_read_back_otherwise_is_reported_failed_naming_the_fields() -> None:
    """**`A_WRITE_IS_DONE_ONLY_WHEN_READ_BACK_AS_APPROVED`.** The source answers the change and the
    record read back still holds the old content: the change is reported failed, naming `content`
    and no value, and the positive sibling is the test above, where the same read finds it done.
    Delete this and a change the source dropped is reported done."""
    account = Account(applies=False)

    report = send(approved(ttl=300, proxied=True), account, Keys())

    assert (report.outcome, report.told) == (WriteOutcome.FAILED, READ_BACK_DIFFERS)
    assert report.differs == ("content", "proxied", "ttl")
    assert CONTENT not in report.told and "192.0.2.1" not in report.told


def test_a_change_the_source_refuses_is_failed_and_is_not_sent_again() -> None:
    """A 403 from the source is reported failed and not read back, and the leash's ledger holds the
    attempt as not known, so resuming it again sends nothing and says it may have reached the
    source. Delete this and a refused change is retried into a duplicate, or reported done."""
    account, ledger = Account(refuses=403), _HeldLedger()
    change = approved()

    refused = send(change, account, Keys(), ledger)
    again = send(change, account, Keys(), ledger)

    assert (refused.outcome, refused.told) == (WriteOutcome.FAILED, SOURCE_REFUSED_THE_CHANGE)
    assert (again.outcome, again.told) == (WriteOutcome.ALREADY_SENT, MAY_HAVE_BEEN_SENT)
    assert [method for method, _, _ in account.calls] == ["PATCH"]


def test_an_unapproved_change_is_not_sent() -> None:
    """The leash's own rule, through this path: an approval not given resumes nothing. Delete this
    and a pending change is sent because its key was held."""
    account = Account()

    report = send(approved(approve=False), account, Keys())

    assert (report.outcome, report.told) == (WriteOutcome.NOT_SENT, NOT_SENT)
    assert account.calls == []


def test_a_write_key_the_vault_cannot_hand_over_sends_nothing_and_is_not_called_disallowed() -> (
    None
):
    """A vault that did not answer is not an install that has not allowed the write: the change is
    reported failed in its own words and nothing is sent. Delete this and an outage tells an
    approver the install never allowed DNS changes."""
    account = Account()

    report = send(approved(), account, Keys(unreadable=True))

    assert (report.outcome, report.told) == (WriteOutcome.FAILED, WRITE_KEY_UNREADABLE)
    assert account.calls == []


def test_a_tool_no_grant_sends_is_refused_before_any_key_is_asked_for() -> None:
    """Only a declared grant's tool reaches a write key. Delete this and any approved action could
    be sent with Cloudflare's DNS key."""
    keys = Keys()
    change = approved()
    tool = DNS_CHANGE_TOOL.model_copy(update={"name": "cloudflare.purge_cache"})
    other = change.model_copy(update={"action": change.action.model_copy(update={"tool": tool})})

    with pytest.raises(ConnectorContractError):
        send(other, Account(), keys)
    assert keys.leases == []


# ------------------------------------------------------------------ who is told what
def test_the_record_read_back_is_told_at_the_readers_reach_and_denied_reads_as_absent() -> None:
    """The report's record is redacted at the reader's reach: the person the change ran for sees
    the content read back, a reader holding no grant over the record is handed exactly what a
    report whose record was never found hands anybody. Delete this and a report tells a reader
    outside the zones' department what a DNS record holds."""
    report = send(approved(), Account(), Keys())
    nobody = holding("u_elsewhere")

    seen = report.for_reader(OPERATOR, POLICY, NOW)
    hidden = report.for_reader(nobody, POLICY, NOW)
    never = WriteReport(outcome=WriteOutcome.FAILED, told=READ_BACK_DIFFERS)

    assert [one["content"] for one in seen] == [CONTENT]
    assert hidden == never.for_reader(nobody, POLICY, NOW) == []


def test_an_approver_is_told_a_change_will_not_be_sent_only_when_the_vault_says_so() -> None:
    """The card's sentence: the grant's own words when its key is not held, nothing when it is,
    nothing when the vault could not say, and nothing for a tool no grant sends. Delete this and
    an approver is told the install never allowed DNS changes during a vault outage, or is not
    told on an install that did not."""
    said = cloudflare.THIS_INSTALL_HAS_NOT_ALLOWED_DNS_CHANGES

    assert unsent_because(DNS_CHANGE_TOOL.name, lambda connector, grant: False) == said
    assert unsent_because(DNS_CHANGE_TOOL.name, lambda connector, grant: True) == ""
    assert unsent_because(DNS_CHANGE_TOOL.name, lambda connector, grant: None) == ""
    assert unsent_because("ticket.update_status", lambda connector, grant: False) == ""
