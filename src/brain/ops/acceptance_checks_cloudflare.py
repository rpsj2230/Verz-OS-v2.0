"""The install acceptance check for Cloudflare: connected, indexed, read live, and a change held.

One check, because the leaf is one path. A Cloudflare account made up for the run is connected
inside the check's transaction through the store the Connectors screen's routes call, its zones and
each zone's DNS records are read by the worker's own `brain.ops.connector_sync_run.attempt` from
answers in Cloudflare's documented envelope, a record's content is asked for through the answer
lane with everything the answer route hands it built by the route's own functions, and a DNS change
is prepared by an agent under an Autonomous leash and followed through the gate, the approval queue
and a resume. So what is proved is what an install does, and nothing is restated.

**No socket is opened, no real token is held, and no change is sent.** Every call is answered by the
check's own `_Account`, which only ever reads: it has a `get` and nothing else, as every source
caller does, so the path a change would need is not there to take. The token each read leases is
minted for the check. See
`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

**The check steps aside where the install has Cloudflare connected.** Connecting a source that is
connected already is refused, and the owner's real connection is never moved. See
`A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY`.

**What it does not prove, said once.** An approved change is resumed with the connector's own
execution, which refuses and sends nothing: executing one waits for the owner
(`brain.connectors.cloudflare.A_DNS_CHANGE_WAITS_FOR_THE_OWNER_TO_ISSUE_A_WRITE_KEY`). A security
event has no question on Ask, so the check does not ask one.

Task ids: M11.7.3
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import _Keys, _Resolver, _search
from brain.ops.acceptance_checks_sources import _connect_and_read, _connection, _prose
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.ops.connector_sync_run import SourceAnswer

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: What the check says where the install has Cloudflare connected already.
A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Cloudflare connected already, so the check does not connect it again and "
    "does not ask about it"
)

__all__ = ["A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY"]

#: The agent the check prepares a change as, and the record type it changes.
AGENT: Final = "acceptance.dns_agent"
RECORD_TYPE: Final = "TXT"


# ------------------------------------------------------------------------ the helpers
def _envelope(result: Any) -> bytes:
    """Cloudflare's documented envelope around `result`, as one page of one."""
    info = (
        {"page": 1, "per_page": 50, "count": len(result), "total_count": len(result)}
        if isinstance(result, list)
        else None
    )
    body: dict[str, Any] = {"success": True, "errors": [], "messages": [], "result": result}
    if info is not None:
        body["result_info"] = {**info, "total_pages": 1}
    return json.dumps(body).encode("utf-8")


@dataclass
class _Account:
    """`SourceCaller` answering Cloudflare's zones, one zone's records and one record. No socket.

    It has `get` and nothing else, as every source caller has, so nothing here could send a change.
    """

    account: str
    zone: str
    record: str
    name: str
    content: str
    asked: list[str] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        path = url.split("?", 1)[0]
        record = {
            "id": self.record,
            "name": self.name,
            "type": RECORD_TYPE,
            "content": self.content,
            "proxied": False,
            "ttl": 1,
        }
        if path.endswith(f"/zones/{self.zone}/dns_records/{self.record}"):
            return SourceAnswer(status=200, headers={}, body=_envelope(record))
        if path.endswith(f"/zones/{self.zone}/dns_records"):
            return SourceAnswer(status=200, headers={}, body=_envelope([record]))
        if path.endswith("/zones"):
            zone = {
                "id": self.zone,
                "name": f"{self.name.split('.', 1)[-1]}",
                "status": "active",
                "account": {"id": self.account, "name": "Acceptance check"},
            }
            return SourceAnswer(status=200, headers={}, body=_envelope([zone]))
        return SourceAnswer(status=404, headers={}, body=b"{}")


async def _in(h: Harness, principal_id: str, department: str, *capabilities: str) -> None:
    """A reserved person in `department`, holding each capability there."""
    scope = Scope.department(department)
    await h.person(
        principal_id, department=department, grants=tuple((one, scope) for one in capabilities)
    )


# ------------------------------------------------ Cloudflare, connected, asked and changed
@check(
    leaves=("M11.7.3",),
    sentence=(
        "A Cloudflare account made up for the check is connected, its zones and each zone's DNS "
        "records are read by the worker into its index, a record's content is read live "
        "on Ask for a reader granted it and kept in no table, a reader without the grant is told "
        "what an absent record is told, and a DNS change an agent prepares is held for an approver "
        "in its department and sends nothing when approved."
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
    from brain.approval_routes import shown_card
    from brain.connectors import cloudflare
    from brain.connectors.minimal_index import fresh_canary
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Leash, LeashEntry, Route, govern, resume
    from brain.gate.suspension_store import ReachedSuspensions, at_reach, put_suspension
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks import _HeldLedger
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connector_store import live
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    name = cloudflare.CLOUDFLARE
    if (await h.execute(live(name))).scalar_one_or_none() is not None:
        raise CheckNotRunError(A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    state = SimpleNamespace(db_sessions=h.sessions)

    # Connected with the console's two settings, and read by the worker: zones, then records.
    canary = fresh_canary("ACCEPTANCE")
    account = _Account(
        account=secrets.token_hex(16),
        zone=secrets.token_hex(16),
        record=secrets.token_hex(16),
        name=f"{h.word().lower()}.example.com",
        content=canary,
    )
    settings = {cloudflare.ACCOUNT_SETTING: account.account, cloudflare.DEPARTMENT_SETTING: A}
    connection = _connection(h, name, settings)
    await _connect_and_read(h, connection, account, at=h.now)
    if not any(f"/zones/{account.zone}/dns_records?" in one for one in account.asked):
        raise CheckFailedError("the worker did not read a zone's records under the zone")

    # What the answer route builds, by its own functions, over the check's transaction.
    rules = await connected_questions_of(state)
    if name not in {rule.source for rule in rules}:
        raise CheckFailedError("a connected Cloudflare account contributed no question to Ask")
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    readers = row_readers(registry)
    if (name, cloudflare.DNS_RECORD) not in readers:
        raise CheckFailedError("the application registered no reader for Cloudflare's records")

    async def connected() -> Any:
        return ConnectedSources(
            {name: connection},
            keys=_Keys(),
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

    names = ("read:dns_record", "read:dns_record.name", "read:dns_record.type")
    operations, viewer = h.principal(A, "dns"), h.principal(A, "dnsviewer")
    await _in(h, operations, A, *names, "read:dns_record.content")
    await _in(h, viewer, A, *names)

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

    # A change, prepared by an agent whose leash says Autonomous, is held for a person.
    changer, approver, elsewhere = (
        h.principal(A, "dnsops"),
        h.principal(A, "dnsapprover"),
        h.principal(B, "dnsapprover"),
    )
    content = f"v={h.word().lower()}"
    await _in(h, changer, A, "write:dns_record", *names[1:], "read:dns_record.content")
    await _in(h, approver, A, "write:dns_record")
    await _in(h, elsewhere, B, "write:dns_record")
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
    policy = source_field_policies(registry)[(name, cloudflare.DNS_RECORD)]
    sent: list[str] = []

    def recorded(done: Any) -> Any:
        sent.append(done.tool.name)
        raise CheckFailedError("a DNS change was sent")

    calm = RiskAssessment(score=0, matched=())
    governed = govern(
        action,
        caller=reach,
        agent_ceiling=reach,
        policy=policy,
        leash=leash,
        assessment=calm,
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
    approving = await _console(h, approver, second_factor=True)
    queued = {
        one.id: one
        for one in await ReachedSuspensions(h.sessions, approving, h.now).open_suspensions()
    }
    stored = queued.get(held.id)
    card = None if stored is None else shown_card(stored, approving, h.now)
    if stored is None or card is None or content not in card.artefact:
        raise CheckFailedError("a held DNS change was not on its department's approval queue")
    outsider = await _console(h, elsewhere, second_factor=True)
    theirs = await ReachedSuspensions(h.sessions, outsider, h.now).suspension(held.id)
    if theirs is not None and shown_card(theirs, outsider, h.now) is not None:
        raise CheckFailedError("a held DNS change was shown to an approver in another department")

    # Approved, it is resumed with the connector's own execution, which sends nothing.
    asked = len(account.asked)
    try:
        resume(
            stored.approved_by(approver, h.now),
            caller=reach,
            agent_ceiling=reach,
            policy=policy,
            leash=leash,
            assessment=calm,
            trace_id=h.trace_id,
            now=h.now,
            execute=cloudflare.execute_dns_change,
            ledger=_HeldLedger(),
        )
    except cloudflare.DnsChangeWaitsForTheOwnerError:
        pass
    else:
        raise CheckFailedError("an approved DNS change was run before the owner decided")
    if len(account.asked) != asked or sent:
        raise CheckFailedError("an approved DNS change called Cloudflare")
    for tool in registry.names():
        definition = registry.get(tool).definition
        if definition.source == name and not definition.is_read_only():
            raise CheckFailedError("the install registers a Cloudflare tool that changes something")
