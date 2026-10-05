"""The install acceptance checks for Cloudflare: read live, and a DNS change held, allowed and sent.

Two checks, because the leaf has two halves an install must show apart. The first connects a
Cloudflare account made up for the run inside the check's transaction, through the store the
Connectors screen's routes call; reads its zones and each zone's DNS records with the worker's own
`brain.ops.connector_sync_run.attempt` from answers in Cloudflare's documented envelope; asks for a
record's content through the answer lane, with everything the answer route hands it built by the
route's own functions; and then follows a DNS change an agent prepares under an Autonomous leash
through the gate, the approval queue and the decision route's own `take_decision` on an install
that has not allowed DNS changes: the card says so, and approved, nothing is sent. The second does
the same on an install that has given the grant's key, and the approved change is sent once with
that key, read back with the read key, and not sent again when resumed a second time.

**No socket is opened and no real token is held.** Every call is answered by the check's own
`_Account`, which reads with `get`, takes a change with `send` and applies it to the record it
answers with, so a read-back reads what was sent. Every key the checks lease is minted for them,
the grant's key only where the check has allowed it. See
`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

**The checks step aside where the install has Cloudflare connected.** Connecting a source that is
connected already is refused, and the owner's real connection is never moved. See
`A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY`.

**What they do not prove, said once.** A security event has no question on Ask, so no check asks
one. And nothing in the product resumes an approved action by itself yet: the checks resume it
through `brain.ops.connector_write_run.send_approved`, which is what the agent runtime will call.

**They are also the install's proof that a connector reads by default and writes only on a
separate, deliberate grant (M11.2.4).** The first finds no Cloudflare tool that changes anything
registered and an approved change sending nothing without the grant's key; the second sees the
change sent with that key and never the read key. A connector that wrote with the key it reads
with, or wrote on an install that never gave the grant, fails one of them.

Task ids: M11.7.3, M11.2.4
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import _Resolver, _search
from brain.ops.acceptance_checks_sources import _connect_and_read, _connection, _prose
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.core.field_policy import FieldPolicy
    from brain.gate.answer import Answered
    from brain.gate.leash import Leash, SuspendedAction
    from brain.ops.connector_lease import LeaseOutcome
    from brain.ops.connector_store import Connection
    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.secrets import SecretRef
    from brain.tools.registry import ToolRegistry

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 320

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: What a check says where the install has Cloudflare connected already.
A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Cloudflare connected already, so the check does not connect it again and "
    "does not ask about it"
)

__all__ = ["A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY"]

#: The agent the checks prepare a change as, and the record type it changes.
AGENT: Final = "acceptance.dns_agent"
RECORD_TYPE: Final = "TXT"

#: What the checks read with and what they send with: the read capabilities, and the one a change
#: needs, each held in the record's department.
READS: Final = ("read:dns_record", "read:dns_record.name", "read:dns_record.type")
WRITES: Final = "write:dns_record"


# ------------------------------------------------------------------------ the helpers
def _envelope(result: Any) -> bytes:
    """Cloudflare's documented envelope around `result`, as one page of one."""
    body: dict[str, Any] = {"success": True, "errors": [], "messages": [], "result": result}
    if isinstance(result, list):
        body["result_info"] = {
            "page": 1,
            "per_page": 50,
            "count": len(result),
            "total_count": len(result),
            "total_pages": 1,
        }
    return json.dumps(body).encode("utf-8")


@dataclass
class _Account:
    """`SourceWriter` answering Cloudflare's zones, one zone's records and one record. No socket.

    `send` takes a change to the one record and applies it, so the record answered afterwards is
    the record as changed. Every call is noted by its address and the key it carried, and a key is
    only ever compared, never shown.
    """

    account: str
    zone: str
    record: str
    name: str
    content: str
    ttl: int = 1
    proxied: bool = False
    asked: list[str] = field(default_factory=list)
    read_with: list[str] = field(default_factory=list)
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    def _record(self) -> dict[str, Any]:
        return {
            "id": self.record,
            "name": self.name,
            "type": RECORD_TYPE,
            "content": self.content,
            "proxied": self.proxied,
            "ttl": self.ttl,
        }

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.asked.append(url)
        path = url.split("?", 1)[0]
        if path.endswith(f"/zones/{self.zone}/dns_records/{self.record}"):
            self.read_with.append(str(headers.get("Authorization", "")))
            return SourceAnswer(status=200, headers={}, body=_envelope(self._record()))
        if path.endswith(f"/zones/{self.zone}/dns_records"):
            return SourceAnswer(status=200, headers={}, body=_envelope([self._record()]))
        if path.endswith("/zones"):
            zone = {
                "id": self.zone,
                "name": f"{self.name.split('.', 1)[-1]}",
                "status": "active",
                "account": {"id": self.account, "name": "Acceptance check"},
            }
            return SourceAnswer(status=200, headers={}, body=_envelope([zone]))
        return SourceAnswer(status=404, headers={}, body=b"{}")

    def send(
        self, method: str, url: str, *, address: str, headers: Any, body: bytes, max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.sent.append((method, url, str(headers.get("Authorization", ""))))
        if not url.endswith(f"/zones/{self.zone}/dns_records/{self.record}"):
            return SourceAnswer(status=404, headers={}, body=b"{}")
        change = json.loads(body)
        self.content = str(change.get("content", self.content))
        self.ttl = int(change.get("ttl", self.ttl))
        self.proxied = bool(change.get("proxied", self.proxied))
        return SourceAnswer(status=200, headers={}, body=_envelope(self._record()))


@dataclass
class _Lease:
    """`KeyLease` over a key made up for the check, or over none."""

    given: str | None = field(repr=False)

    def key(self) -> str:
        from brain.ops.connector_sync_run import ConnectorKeyAbsentError

        if self.given is None:
            raise ConnectorKeyAbsentError("no key is kept for this grant")
        return self.given

    def user(self) -> str:
        from brain.ops.connector_sync import NO_KEY
        from brain.ops.connector_sync_run import ConnectorKeyAbsentError

        # A Cloudflare token is one key, so its slot keeps no user beside it (M11.6.1).
        raise ConnectorKeyAbsentError(NO_KEY)

    def close(self, now: datetime) -> LeaseOutcome:
        from brain.ops.connector_lease import LeaseOutcome

        del now
        return LeaseOutcome.NONE


@dataclass
class _Leases:
    """`ConnectorKeys` handing a key minted for the check per slot, and none for the grant's slot
    unless the check allowed the write."""

    allows: bool
    given: dict[str, str] = field(default_factory=dict, repr=False)

    def lease(self, ref: SecretRef, *, now: datetime) -> _Lease:
        from brain.connectors.cloudflare import CLOUDFLARE, DNS_CHANGES
        from brain.ops.credentials import connector_write_slot

        del now
        if ref.path == connector_write_slot(CLOUDFLARE, DNS_CHANGES.name).path and not self.allows:
            return _Lease(None)
        return _Lease(self.given.setdefault(ref.path, secrets.token_hex(16)))


async def _in(h: Harness, principal_id: str, department: str, *capabilities: str) -> None:
    """A reserved person in `department`, holding each capability there."""
    scope = Scope.department(department)
    await h.person(
        principal_id, department=department, grants=tuple((one, scope) for one in capabilities)
    )


@dataclass(frozen=True)
class _Connected:
    """A made-up account connected and read, the registry the application builds, and the policy."""

    account: _Account
    connection: Connection
    registry: ToolRegistry
    policy: FieldPolicy


async def _connected(h: Harness, content: str) -> _Connected:
    """Connect a made-up account as the Connectors route does, and read it as the worker does."""
    from brain.api_routes import source_field_policies
    from brain.connectors import cloudflare
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.connector_store import live
    from brain.tools.startup import build_registry

    name = cloudflare.CLOUDFLARE
    if (await h.execute(live(name))).scalar_one_or_none() is not None:
        raise CheckNotRunError(A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    account = _Account(
        account=secrets.token_hex(16),
        zone=secrets.token_hex(16),
        record=secrets.token_hex(16),
        name=f"{h.word().lower()}.example.com",
        content=content,
    )
    settings = {cloudflare.ACCOUNT_SETTING: account.account, cloudflare.DEPARTMENT_SETTING: A}
    connection = _connection(h, name, settings)
    await _connect_and_read(h, connection, account, at=h.now)
    if not any(f"/zones/{account.zone}/dns_records?" in one for one in account.asked):
        raise CheckFailedError("the worker did not read a zone's records under the zone")
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    policy = source_field_policies(registry)[(name, cloudflare.DNS_RECORD)]
    return _Connected(account=account, connection=connection, registry=registry, policy=policy)


@dataclass(frozen=True)
class _Approved:
    """A change held, queued, shown to its approver, approved, and read at its runner's reach."""

    suspension: SuspendedAction
    reach: EntitlementSet
    leash: Leash
    unsent_because: str


async def _approved_change(
    h: Harness, source: _Connected, leases: _Leases, *, content: str
) -> _Approved:
    """An agent's change under an Autonomous leash, held for a person, approved by one in A.

    Held by `govern` and never run by it; stored as the gate stores it; shown on the queue to an
    approver in the record's department with what the card says about sending it, and to nobody in
    another; approved through the decision route's own `take_decision`.
    """
    from brain.approval_routes import DecidableVerdict, DecisionAsked, shown_card, take_decision
    from brain.connectors import cloudflare
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Leash, LeashEntry, Route, govern
    from brain.gate.suspension_store import (
        ReachedSuspensions,
        StoredSuspensions,
        at_reach,
        put_suspension,
    )
    from brain.ops.acceptance_checks import _HeldLedger
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connector_write_run import unsent_because

    account = source.account
    changer, approver, elsewhere = (
        h.principal(A, "dnsops"),
        h.principal(A, "dnsapprover"),
        h.principal(B, "dnsapprover"),
    )
    await _in(h, changer, A, WRITES, *READS[1:], "read:dns_record.content")
    await _in(h, approver, A, WRITES)
    await _in(h, elsewhere, B, WRITES)
    reach = await h.reach(changer)
    change = cloudflare.DnsChange(
        record=cloudflare.DNS_RECORD_LISTING.source_id(account.zone, account.record),
        name=account.name,
        record_type=RECORD_TYPE,
        content=content,
    )
    action = cloudflare.prepare_dns_change(change, agent_id=AGENT, department=A)
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id=AGENT,
                target=cloudflare.DNS_RECORD,
                scope=Scope.department(A),
                rung=AutonomyTier.AUTONOMOUS,
            ),
        )
    )
    sent: list[str] = []

    def recorded(done: Any) -> Any:
        sent.append(done.tool.name)
        raise CheckFailedError("a DNS change was sent")

    governed = govern(
        action,
        caller=reach,
        agent_ceiling=reach,
        policy=source.policy,
        leash=leash,
        assessment=RiskAssessment(score=0, matched=()),
        trace_id=h.trace_id,
        now=h.now,
        simulate=recorded,
        execute=recorded,
        ledger=_HeldLedger(),
        suspension_id=f"acceptance.{uuid.uuid4().hex}",
    )
    held = governed.suspension
    if governed.route is not Route.SUSPEND or held is None or sent:
        raise CheckFailedError("a DNS change under an Autonomous leash was not held for a person")
    async with h.sessions() as session:
        await at_reach(session, reach, h.now)
        await put_suspension(session, held)
        await session.commit()

    def unsent(tool: str) -> str:
        return unsent_because(tool, lambda connector, grant: leases.allows)

    approving = await _console(h, approver, second_factor=True)
    queued = {
        one.id: one
        for one in await ReachedSuspensions(h.sessions, approving, h.now).open_suspensions()
    }
    stored = queued.get(held.id)
    card = None if stored is None else shown_card(stored, approving, h.now, unsent=unsent)
    if stored is None or card is None or content not in card.artefact:
        raise CheckFailedError("a held DNS change was not on its department's approval queue")
    outsider = await _console(h, elsewhere, second_factor=True)
    theirs = await ReachedSuspensions(h.sessions, outsider, h.now).suspension(held.id)
    if theirs is not None and shown_card(theirs, outsider, h.now) is not None:
        raise CheckFailedError("a held DNS change was shown to an approver in another department")
    store = StoredSuspensions(h.sessions)
    await take_decision(
        store,
        held.id,
        approving,
        DecisionAsked(verdict=DecidableVerdict.APPROVED),
        trace_id=h.trace_id,
        now=h.now,
    )
    approved = await store.reading_as(reach, h.now).suspension(held.id)
    if approved is None or approved.decided_by != approver:
        raise CheckFailedError(
            "an approved DNS change was not recorded as approved by its approver"
        )
    return _Approved(
        suspension=approved, reach=reach, leash=leash, unsent_because=card.unsent_because
    )


def _send(h: Harness, source: _Connected, leases: _Leases, done: _Approved, ledger: Any) -> Any:
    """`brain.ops.connector_write_run.send_approved` over the check's account and keys."""
    from brain.gate.injection import RiskAssessment
    from brain.ops.connector_write_run import send_approved

    return send_approved(
        done.suspension,
        connection=source.connection,
        keys=leases,
        caller=source.account,
        resolver=_Resolver(),
        clock=lambda: h.now,
        reach=done.reach,
        agent_ceiling=done.reach,
        policy=source.policy,
        leash=done.leash,
        assessment=RiskAssessment(score=0, matched=()),
        trace_id=h.trace_id,
        ledger=ledger,
    )


# ------------------------------------------------ 1. read live, and a change held and not sent
@check(
    leaves=("M11.7.3", "M11.2.4"),
    sentence=(
        "A Cloudflare account made up for the check is connected and its DNS records indexed; a "
        "record's content is read live on Ask for a reader granted it and kept in no table, and "
        "one without the grant is told what an absent record is told. By default nothing writes: "
        "no Cloudflare tool changes anything, and an agent's DNS change is held, its card says so, "
        "and approved it sends nothing."
    ),
)
async def cloudflare_is_read_live_and_a_dns_change_waits_for_a_person(h: Harness) -> None:
    from brain.api_routes import (
        connected_questions_of,
        covered_at,
        field_policies,
        row_readers,
        source_field_policies,
    )
    from brain.connectors import cloudflare
    from brain.connectors.minimal_index import fresh_canary
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.ops.acceptance_checks import _HeldLedger
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connector_write_run import WriteOutcome
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink

    name = cloudflare.CLOUDFLARE
    canary = fresh_canary("ACCEPTANCE")
    source = await _connected(h, canary)
    account, registry = source.account, source.registry
    leases = _Leases(allows=False)
    state = SimpleNamespace(db_sessions=h.sessions)

    # What the answer route builds, by its own functions, over the check's transaction.
    rules = await connected_questions_of(state)
    if name not in {rule.source for rule in rules}:
        raise CheckFailedError("a connected Cloudflare account contributed no question to Ask")
    readers = row_readers(registry)
    if (name, cloudflare.DNS_RECORD) not in readers:
        raise CheckFailedError("the application registered no reader for Cloudflare's records")

    async def connected() -> Any:
        return ConnectedSources(
            {name: source.connection},
            keys=leases,
            caller=account,
            resolver=_Resolver(),
            clock=lambda: h.now,
        )

    live_records = SourceRecords(connected=connected, clock=lambda: h.now)

    async def ask(principal_id: str, question: str) -> Answered:
        person = await StoredPrincipals(h.sessions).live_principal(principal_id)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        reach: EntitlementSet = await _console(h, principal_id, second_factor=False)
        return await answer_lane(
            question,
            origin=Origin(trace_id=h.trace_id, principal=person, channel=Channel.CONSOLE),
            recorders=(),
            rules=rules,
            readers=readers,
            entitlement=reach,
            policies=field_policies(registry),
            reachable_sources=covered_at(registry, reach, h.now),
            sink=CountingTraceSink(),
            now=h.now,
            clock=lambda: h.now,
            live=live_records,
            source_policies=source_field_policies(registry),
        )

    def asking(field_name: str, slot: str) -> str:
        return QUESTION_SHAPES[0].format(label=label_of(field_name), slot=slot)

    operations, viewer = h.principal(A, "dns"), h.principal(A, "dnsviewer")
    await _in(h, operations, A, *READS, "read:dns_record.content")
    await _in(h, viewer, A, *READS)

    # The type from the index; the content from Cloudflare, by the record's own call, while asked.
    typed = await ask(operations, asking("type", account.name))
    if typed.composed is None or RECORD_TYPE not in _prose(typed):
        raise CheckFailedError("a connected DNS record was not answered on Ask from its index")
    one_record = f"/zones/{account.zone}/dns_records/{account.record}"
    before = sum(one_record in url for url in account.asked)
    told = await ask(operations, asking("content", account.name))
    if told.composed is None or canary not in _prose(told):
        raise CheckFailedError("a DNS record's content was not read live for a reader granted it")
    if sum(one_record in url for url in account.asked) <= before:
        raise CheckFailedError("a DNS record's content was not read from Cloudflare when asked")
    withheld = await ask(viewer, asking("content", account.name))
    nobody = await ask(viewer, asking("content", f"{h.word().lower()}.example.com"))
    if canary in _prose(withheld) or withheld.composed is not None:
        raise CheckFailedError("a DNS record's content was told to a reader not granted it")
    if _prose(withheld) != _prose(nobody):
        raise CheckFailedError("withheld content was told apart from a record that is not there")
    if await _search(h, canary):
        raise CheckFailedError("a DNS record's content read live was found in a table")

    # A change on an install that has not allowed DNS changes: held, said so, approved, not sent.
    done = await _approved_change(h, source, leases, content=f"v={h.word().lower()}")
    if done.unsent_because != cloudflare.THIS_INSTALL_HAS_NOT_ALLOWED_DNS_CHANGES:
        raise CheckFailedError("an approver was not told this install has not allowed DNS changes")
    report = _send(h, source, leases, done, _HeldLedger())
    if report.outcome is not WriteOutcome.NOT_ALLOWED or account.sent:
        raise CheckFailedError(
            "an approved DNS change was sent on an install that had not allowed it"
        )
    for tool in registry.names():
        definition = registry.get(tool).definition
        if definition.source == name and not definition.is_read_only():
            raise CheckFailedError("the install registers a Cloudflare tool that changes something")


# ------------------------------------------------ 2. allowed: sent once, read back as approved
@check(
    leaves=("M11.7.3", "M11.2.4"),
    sentence=(
        "On an install that has given Cloudflare's DNS change key, a separate grant from the read "
        "key, a change an agent prepares is approved by a person in its department, sent once with "
        "that key and never the read key, read back with the read key holding what was approved, "
        "and resuming the approval again sends nothing."
    ),
)
async def an_allowed_dns_change_is_sent_once_and_read_back(h: Harness) -> None:
    from brain.connectors import cloudflare
    from brain.ops.acceptance_checks import _HeldLedger
    from brain.ops.connector_write_run import WriteOutcome
    from brain.ops.credentials import connector_key_slot, connector_write_slot

    source = await _connected(h, f"v={h.word().lower()}")
    account = source.account
    leases = _Leases(allows=True)
    content = f"v={h.word().lower()}"
    done = await _approved_change(h, source, leases, content=content)
    if done.unsent_because:
        raise CheckFailedError("an approver was told DNS changes are not allowed where they are")
    ledger = _HeldLedger()
    report = _send(h, source, leases, done, ledger)
    write_key = leases.given.get(connector_write_slot(cloudflare.CLOUDFLARE, "dns_changes").path)
    read_key = leases.given.get(connector_key_slot(cloudflare.CLOUDFLARE).path)
    if report.outcome is not WriteOutcome.DONE or account.content != content:
        raise CheckFailedError("an allowed DNS change was not sent and read back as approved")
    ((method, url, sent_with),) = account.sent
    one_record = f"/zones/{account.zone}/dns_records/{account.record}"
    if method != "PATCH" or not url.endswith(one_record) or sent_with != f"Bearer {write_key}":
        raise CheckFailedError("an allowed DNS change was not sent with the grant's own key")
    if not account.read_with or account.read_with[-1] != f"Bearer {read_key}":
        raise CheckFailedError("an allowed DNS change was not read back with the read key")
    seen = report.for_reader(done.reach, source.policy, h.now)
    if [one.get("content") for one in seen] != [content]:
        raise CheckFailedError("the change read back was not told to the person it ran for")
    again = _send(h, source, leases, done, ledger)
    if again.outcome is not WriteOutcome.ALREADY_SENT or len(account.sent) != 1:
        raise CheckFailedError("an approved DNS change was sent twice")
