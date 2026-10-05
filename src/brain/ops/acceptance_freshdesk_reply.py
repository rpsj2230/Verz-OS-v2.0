"""The install acceptance check for a reply to a Freshdesk ticket: approved, sent, read back.

One check, over the product's own pieces end to end, inside the check's transaction. A helpdesk
made up for the run is connected as the Connectors route connects one and read as the worker reads
it. An agent of acceptance_a is installed with its leash at Assisted on tickets, and a reply it
prepares is decided by the gate at the requester's reach and the agent's stored ceiling, held, and
approved by a person in the helpdesk's department through the decision route's own `take_decision`.

**Then the worker sends it, not the check.** The worker's run of approved actions
(`brain.ops.approved_runs.run_approved`, M13.7.6) is made with `ConnectorWrites`, its executor for
every connector write, which calls `brain.ops.connector_write_run.send_approved`. On an install that
has not given the reply key the run sends nothing and leaves the approval standing; once the key is
given the next run posts the reply once with that key, reads the ticket's conversations back with
the read key, and reports it done only when one of them is a public reply holding the approved
words; a third run sends nothing.

**No socket is opened and no real key is held.** The helpdesk is the check's own `_Desk`, which
answers the ticket list, the ticket's conversations and a reply, and posts what it is sent; the keys
are made up per slot. The operation ledger is the in-memory one the Cloudflare check uses, because
the install's is on an autocommit connection and would keep the check's rows after its transaction
is rolled back. What only a real helpdesk proves (that Freshdesk accepts the post with an agent's
key and lists the reply among the ticket's conversations) is the owner's to see on his own
helpdesk once he gives the reply key.

**The check does not run where Freshdesk is connected already**, for the sources check's reason:
it connects a helpdesk of its own and would otherwise stand beside the install's real one.

Task ids: M11.8.12
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.connector_lease import LeaseOutcome
    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.secrets import SecretRef

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 396

A, _ = RESERVED_DEPARTMENTS

#: The helpdesk address the check connects. Reserved for documentation, and never reached: the
#: check's own `_Desk` answers it.
HELPDESK: Final = "acceptance-check.freshdesk.com"

# What the check says, one sentence for each way the property can fail.
FRESHDESK_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Freshdesk connected already, so the check does not connect a helpdesk of "
    "its own beside it"
)
THE_AGENT_HAS_NO_STANDING: Final = (
    "the check's agent was installed and the worker read no standing for it"
)
A_REPLY_WAS_NOT_HELD: Final = "a reply an agent prepared was not held for a person"
A_REPLY_WAS_SENT_WITHOUT_ITS_KEY: Final = (
    "a reply was sent, or not left waiting, on an install that has not given the reply key"
)
A_REPLY_WAS_NOT_SENT_AND_READ_BACK: Final = (
    "an approved reply was not posted once with the reply key and read back as a public reply"
)
A_REPLY_WAS_SENT_TWICE: Final = "an approved reply was sent a second time"


@dataclass
class _Desk:
    """`SourceWriter` answering one ticket, its conversations and a reply to it. No socket."""

    ticket: dict[str, Any]
    conversations: list[dict[str, Any]] = field(default_factory=list)
    read_with: list[str] = field(default_factory=list)
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        path = url.split("?", 1)[0]
        if path.endswith(f"/api/v2/tickets/{self.ticket['id']}/conversations"):
            self.read_with.append(str(headers.get("Authorization", "")))
            return SourceAnswer(
                status=200, headers={}, body=json.dumps(self.conversations).encode()
            )
        if path.endswith("/api/v2/tickets"):
            return SourceAnswer(status=200, headers={}, body=json.dumps([self.ticket]).encode())
        return SourceAnswer(status=404, headers={}, body=b"{}")

    def send(
        self, method: str, url: str, *, address: str, headers: Any, body: bytes, max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.sent.append((method, url, str(headers.get("Authorization", ""))))
        if not url.endswith(f"/api/v2/tickets/{self.ticket['id']}/reply"):
            return SourceAnswer(status=404, headers={}, body=b"{}")
        text = str(json.loads(body)["body"]).replace("<br>", "\n")
        posted = {
            "id": len(self.conversations) + 1,
            "ticket_id": self.ticket["id"],
            "body_text": text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"),
            "incoming": False,
            "private": False,
        }
        self.conversations.append(posted)
        return SourceAnswer(status=201, headers={}, body=json.dumps(posted).encode())


@dataclass
class _Lease:
    given: str | None = field(repr=False)

    def key(self) -> str:
        from brain.ops.connector_sync_run import ConnectorKeyAbsentError

        if self.given is None:
            raise ConnectorKeyAbsentError("no key is kept for this grant")
        return self.given

    def user(self) -> str:
        from brain.ops.connector_sync import NO_KEY
        from brain.ops.connector_sync_run import ConnectorKeyAbsentError

        raise ConnectorKeyAbsentError(NO_KEY)

    def close(self, now: datetime) -> LeaseOutcome:
        from brain.ops.connector_lease import LeaseOutcome

        del now
        return LeaseOutcome.NONE


@dataclass
class _Leases:
    """A key made up per slot, and none for the reply grant's slot until the check allows it."""

    allows: bool = False
    given: dict[str, str] = field(default_factory=dict, repr=False)

    def lease(self, ref: SecretRef, *, now: datetime) -> _Lease:
        from brain.connectors.freshdesk import FRESHDESK, TICKET_REPLIES
        from brain.ops.credentials import connector_write_slot

        del now
        if (
            ref.path == connector_write_slot(FRESHDESK, TICKET_REPLIES.name).path
            and not self.allows
        ):
            return _Lease(None)
        return _Lease(self.given.setdefault(ref.path, secrets.token_hex(16)))


@check(
    leaves=("M11.8.12",),
    sentence=(
        "A reply an agent prepares to a ticket on a helpdesk made up for the check is held for a "
        "person and approved in the helpdesk's department; the worker's run sends nothing until "
        "the reply key is given, then posts it once with that key, reads it back with the read key "
        "as a public reply holding the approved words, and a further run sends nothing."
    ),
)
async def an_approved_ticket_reply_is_posted_once_and_read_back(h: Harness) -> None:
    from brain.agents.template import LeashRung, ManifestGuardrails
    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.connectors import freshdesk
    from brain.core.envelope import SideEffect
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.injection import AutonomyTier
    from brain.gate.leash import Route, decide, route_for, suspend
    from brain.gate.suspension_store import StoredSuspensions, put_suspension
    from brain.ops.acceptance_checks import _HeldLedger
    from brain.ops.acceptance_checks_connectors import _Resolver
    from brain.ops.acceptance_checks_sources import _connect_and_read, _connection
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.approved_runs import (
        ApprovedRun,
        ConnectorWrites,
        Ran,
        StoredStandings,
        assessment_of,
        policy_of,
        run_approved,
    )
    from brain.ops.connector_store import live
    from brain.ops.connector_sync_run import authorization
    from brain.ops.credentials import connector_key_slot, connector_write_slot

    if (await h.execute(live(freshdesk.FRESHDESK))).scalar_one_or_none() is not None:
        raise CheckNotRunError(FRESHDESK_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    # A helpdesk made up for the run, connected and read.
    ticket = {
        "id": 900_000 + uuid.uuid4().int % 99_999,
        "subject": h.word(),
        "status": 2,
        "priority": 1,
        "company_id": 1,
        "requester_id": 1,
        "group_id": 1,
        "created_at": "2019-03-01T10:00:00Z",
        "updated_at": "2019-03-02T10:00:00Z",
        "due_by": "2019-03-08T10:00:00Z",
    }
    desk = _Desk(ticket)
    connection = _connection(
        h,
        freshdesk.FRESHDESK,
        {freshdesk.DOMAIN_SETTING: HELPDESK, freshdesk.DEPARTMENT_SETTING: A},
    )
    await _connect_and_read(h, connection, desk, at=h.now)

    # The people, and an agent whose leash holds a ticket reply for a person.
    write = freshdesk.REPLY_CAPABILITY
    see = f"read:{freshdesk.TICKET}.{freshdesk.REPLY_FIELD}"
    asker, approver = h.principal(A, "replier"), h.principal(A, "replyapprover")
    scope = Scope.department(A)
    await h.person(asker, department=A, grants=((write, scope), (see, scope)))
    await h.person(approver, department=A, grants=((write, scope),))
    agent = await installed_agent(
        h,
        asker,
        capabilities=(write, see),
        allowed_tools=(freshdesk.TICKET_REPLY_TOOL.name,),
        suffix="_reply",
        scope=scope,
        guardrails=ManifestGuardrails(
            max_side_effect=SideEffect.WRITE,
            leash=(LeashRung(target=freshdesk.TICKET, scope=scope, rung=AutonomyTier.ASSISTED),),
        ),
    )
    standings = StoredStandings(h.sessions)
    standing = await standings.standing(agent, h.now)
    if standing is None:
        raise CheckFailedError(THE_AGENT_HAS_NO_STANDING)

    # The reply, prepared, decided at the requester's reach, held and approved.
    words = f"Thank you for waiting. Reference {h.word()} & {h.word()}."
    action = freshdesk.prepare_ticket_reply(
        freshdesk.TicketReply(ticket=str(ticket["id"]), body=words),
        agent_id=agent,
        department=A,
    )
    asking = await h.reach(asker)
    decision = decide(
        action,
        caller=asking,
        agent_ceiling=standing.ceiling,
        policy=policy_of(action),
        leash=standing.leash,
        assessment=assessment_of(action),
        now=h.now,
    )
    if route_for(decision) is not Route.SUSPEND:
        raise CheckFailedError(A_REPLY_WAS_NOT_HELD)
    held = suspend(
        action,
        decision,
        principal_id=asker,
        trace_id=h.trace_id,
        now=h.now,
        suspension_id=f"acceptance_{h.run}_reply",
    )
    store = StoredSuspensions(h.sessions)
    async with store.holding(asking, h.now) as rows:
        await put_suspension(rows.session, held)
    await take_decision(
        store,
        held.id,
        await h.reach(approver),
        DecisionAsked(verdict=DecidableVerdict.APPROVED),
        trace_id=h.trace_id,
        now=h.now,
    )

    # The worker's run, with the executor it runs every connector write with.
    leases, ledger = _Leases(allows=False), _HeldLedger()

    async def connected() -> list[Any]:
        return [connection]

    writes = ConnectorWrites(
        connections=connected,
        keys=leases,
        caller=desk,
        resolver=_Resolver(),
        clock=lambda: h.now,
        declarations={freshdesk.FRESHDESK: freshdesk.CONNECTOR},
    )

    async def once() -> ApprovedRun:
        return await run_approved(
            h.sessions,
            now=h.now,
            executors=(writes,),
            standings=standings,
            reaches=StoredEntitlements(h.sessions),
            ledger=ledger,
        )

    unkeyed = await once()
    if dict(unkeyed.outcomes) != {Ran.NOT_ALLOWED: 1} or desk.sent:
        raise CheckFailedError(A_REPLY_WAS_SENT_WITHOUT_ITS_KEY)
    leases.allows = True
    sent = await once()
    scheme = freshdesk.FreshdeskReading().key_scheme()
    write_key = leases.given.get(connector_write_slot(freshdesk.FRESHDESK, "ticket_replies").path)
    read_key = leases.given.get(connector_key_slot(freshdesk.FRESHDESK).path)
    posted = [one.get("body_text") for one in desk.conversations]
    if (
        dict(sent.outcomes) != {Ran.DONE: 1}
        or write_key is None
        or read_key is None
        or [(method, by) for method, _, by in desk.sent]
        != [("POST", authorization(scheme, write_key))]
        or desk.read_with[-1:] != [authorization(scheme, read_key)]
        or posted != [words]
    ):
        raise CheckFailedError(A_REPLY_WAS_NOT_SENT_AND_READ_BACK)
    again = await once()
    if len(desk.sent) != 1 or dict(again.outcomes) not in ({}, {Ran.ALREADY_RAN: 1}):
        raise CheckFailedError(A_REPLY_WAS_SENT_TWICE)
