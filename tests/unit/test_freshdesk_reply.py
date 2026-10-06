"""A reply to a Freshdesk ticket: held for a person, sent once with its own key, read back by text.

The reply is checked before anything is prepared, prepared as an action whose card is the reply the
customer would get, held for a person whatever the leash says, and sent through
`brain.ops.connector_write_run.send_approved` to the connection's own helpdesk with the reply key,
then read back among the ticket's conversations with the read key. A recorded helpdesk answers
every call and posts what it is sent; nothing here opens a socket.

Task ids: M11.8.12
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from brain.connectors import freshdesk
from brain.connectors.contract import ConnectorContractError
from brain.connectors.freshdesk import (
    CONVERSATION,
    REPLY_CAPABILITY,
    THIS_INSTALL_HAS_NOT_ALLOWED_TICKET_REPLIES,
    TICKET,
    TICKET_REPLIES,
    TICKET_REPLY_TOOL,
    TicketReply,
    TicketReplyWrites,
    prepare_ticket_reply,
    ticket_reply_of,
)
from brain.connectors.manifest import manifest_digest
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import Governed, Leash, LeashEntry, Route, SuspendedAction, govern
from brain.ops.acceptance_checks import _HeldLedger
from brain.ops.connectable import manifest_for
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import ConnectorKeyAbsentError, SourceAnswer, authorization
from brain.ops.connector_write_run import (
    READ_BACK_DIFFERS,
    READ_BACK_UNKNOWN,
    SENT_ALREADY,
    SENT_AND_READ_BACK,
    WriteOutcome,
    WriteReport,
    send_approved,
)
from brain.ops.credentials import connector_key_slot, connector_write_slot
from brain.ops.secrets import SecretRef
from brain.tools.startup import field_policy_for

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
DOMAIN: Final = "example.freshdesk.com"
DEPARTMENT: Final = "support"
AGENT: Final = "agent.support"
TICKET_ID: Final = "4242"
WRITE_PATH: Final = connector_write_slot(freshdesk.FRESHDESK, TICKET_REPLIES.name).path
READ_PATH: Final = connector_key_slot(freshdesk.FRESHDESK).path
KEYS: Final = {READ_PATH: "READ-KEY-SENTINEL", WRITE_PATH: "WRITE-KEY-SENTINEL"}
SCHEME: Final = freshdesk.FreshdeskReading().key_scheme()
TEXT: Final = "Thank you for waiting.\nThe refund went out today & should arrive by Friday."
POLICY: Final = field_policy_for(TICKET, source=freshdesk.FRESHDESK)
CALM: Final = RiskAssessment(score=0, matched=())


def holding(principal: str, *capabilities: str) -> EntitlementSet:
    scope = Scope.department(DEPARTMENT)
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=one), scope=scope) for one in capabilities),
    )


REPLY_READ: Final = f"read:{TICKET}.{freshdesk.REPLY_FIELD}"
SUPPORT: Final = holding("u_support", REPLY_CAPABILITY, REPLY_READ)
CEILING: Final = holding(AGENT, REPLY_CAPABILITY, REPLY_READ)
AUTONOMOUS: Final = Leash(
    entries=(
        LeashEntry(
            agent_id=AGENT,
            target=TICKET,
            scope=Scope.department(DEPARTMENT),
            rung=AutonomyTier.AUTONOMOUS,
        ),
    )
)


# ------------------------------------------------------------------ the stand-ins
@dataclass
class Lease:
    given: str | None

    def key(self) -> str:
        if self.given is None:
            raise ConnectorKeyAbsentError("no key is kept here")
        return self.given

    def user(self) -> str:
        raise AssertionError("a Freshdesk key is one key")

    def close(self, now: datetime) -> LeaseOutcome:
        del now
        return LeaseOutcome.REVOKED


@dataclass
class Keys:
    allows: bool = True

    def lease(self, ref: SecretRef, *, now: datetime) -> Lease:
        del now
        if ref.path == WRITE_PATH and not self.allows:
            return Lease(None)
        return Lease(KEYS[ref.path])


@dataclass
class Helpdesk:
    """One ticket's conversations: read with `get`, replied to with `send`, each call noted."""

    posts: bool = True
    private: bool = False
    conversations: list[dict[str, Any]] = field(default_factory=list)
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        self.calls.append(("GET", url.split("?", 1)[0], headers["Authorization"]))
        body = json.dumps(self.conversations).encode("utf-8")
        return SourceAnswer(status=200, headers={}, body=body)

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
        self.calls.append((method, url.split("?", 1)[0], headers["Authorization"]))
        reply = json.loads(body)
        self.sent.append(reply)
        posted = {
            "id": 9000 + len(self.conversations),
            "ticket_id": int(TICKET_ID),
            "body": reply["body"],
            "body_text": reply["body"].replace("<br>", "\n").replace("&amp;", "&"),
            "incoming": False,
            "private": self.private,
        }
        if self.posts:
            self.conversations.append(posted)
        return SourceAnswer(status=201, headers={}, body=json.dumps(posted).encode("utf-8"))


class Public:
    def resolve(self, host: str) -> list[str]:
        del host
        return ["104.16.132.229"]


def connection(domain: str = DOMAIN) -> Connection:
    settings = {freshdesk.DOMAIN_SETTING: domain, freshdesk.DEPARTMENT_SETTING: DEPARTMENT}
    return Connection(
        connector=freshdesk.FRESHDESK,
        settings=settings,
        digest=manifest_digest(manifest_for(freshdesk.FRESHDESK, settings)),
        connected_by="u_admin",
        connected_at=NOW,
    )


def held(text: str = TEXT, *, approve: bool = True) -> SuspendedAction:
    """A reply an agent prepared under an Autonomous leash, held by the gate, and approved."""
    action = prepare_ticket_reply(
        TicketReply(ticket=TICKET_ID, body=text), agent_id=AGENT, department=DEPARTMENT
    )
    governed: Governed[Any] = govern(
        action,
        caller=SUPPORT,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=AUTONOMOUS,
        assessment=CALM,
        trace_id="t-reply",
        now=NOW,
        simulate=lambda one: pytest.fail("a held reply was simulated"),
        execute=lambda one: pytest.fail("a held reply was sent by the gate"),
        ledger=_HeldLedger(),
    )
    assert governed.route is Route.SUSPEND
    suspension = governed.suspension
    assert suspension is not None
    return suspension.approved_by("u_approver", NOW) if approve else suspension


def send(
    suspension: SuspendedAction,
    desk: Helpdesk,
    keys: Keys | None = None,
    ledger: Any = None,
    to: Connection | None = None,
) -> WriteReport:
    return send_approved(
        suspension,
        connection=connection() if to is None else to,
        keys=Keys() if keys is None else keys,
        caller=desk,
        resolver=Public(),
        clock=lambda: NOW,
        reach=SUPPORT,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=AUTONOMOUS,
        assessment=CALM,
        trace_id="t-send",
        ledger=_HeldLedger() if ledger is None else ledger,
    )


REPLY_URL: Final = f"https://{DOMAIN}/api/v2/tickets/{TICKET_ID}/reply"
CONVERSATIONS_URL: Final = f"https://{DOMAIN}/api/v2/tickets/{TICKET_ID}/conversations"


# ------------------------------------------------------------------ the reply itself
@pytest.mark.parametrize(
    ("ticket", "body"),
    [
        ("12a", "Hello"),
        ("../1", "Hello"),
        (TICKET_ID, "   "),
        (TICKET_ID, "x" * (freshdesk.MAX_REPLY_CHARS + 1)),
        (TICKET_ID, "Hello\x00there"),
        (TICKET_ID, "Hello‮there"),
    ],
)
def test_a_reply_that_is_not_a_tickets_id_and_printable_text_is_refused(
    ticket: str, body: str
) -> None:
    """A ticket id that is not digits, an empty or overlong reply, and characters a helpdesk would
    hide or reorder are refused before anything is prepared. Delete this and a reply can be laid
    into an address as a path, or carry text the approver cannot see."""
    with pytest.raises(ConnectorContractError):
        TicketReply(ticket=ticket, body=body)


def test_a_reply_at_the_limit_is_accepted_and_sent_as_escaped_html_with_its_line_breaks() -> None:
    """The positive sibling: the longest reply is accepted, and the body Freshdesk is sent has its
    markup escaped and each line break a `<br>`. Delete this and the refusals above are satisfied by
    a constructor that refuses everything, or an approved `<script>` is posted as markup."""
    TicketReply(ticket=TICKET_ID, body="x" * freshdesk.MAX_REPLY_CHARS)
    reply = TicketReply(ticket=TICKET_ID, body="Hi <b>there</b>\nSee you & bye\n")
    assert reply.html() == "Hi &lt;b&gt;there&lt;/b&gt;<br>See you &amp; bye"


def test_the_prepared_action_is_the_reply_the_customer_gets_in_the_helpdesks_department() -> None:
    """The card an approver reads is built from the action, so the text travels whole; the row
    carries the ticket and the department an approver's grant is matched against; and the tool is
    the sensitive write the gate caps at Assisted. Delete this and an approver can approve a
    summary of a reply, in a department nobody's grant names."""
    action = prepare_ticket_reply(
        TicketReply(ticket=TICKET_ID, body=f"  {TEXT}  "), agent_id=AGENT, department=DEPARTMENT
    )
    assert action.tool == TICKET_REPLY_TOOL
    assert TICKET_REPLY_TOOL.sensitive is True
    assert action.args == {freshdesk.REPLY_FIELD: TEXT}
    assert action.row == {freshdesk.DEPARTMENT_SETTING: DEPARTMENT, freshdesk.TICKET_KEY: TICKET_ID}
    with pytest.raises(ConnectorContractError):
        prepare_ticket_reply(
            TicketReply(ticket=TICKET_ID, body=TEXT), agent_id=AGENT, department="Not A Slug"
        )


def test_an_action_that_is_not_a_reply_is_never_read_as_one() -> None:
    """Delete this and the reply key can be handed an action of another tool that happens to carry
    a body and a ticket."""
    action = held().action
    other = action.model_copy(
        update={"tool": TICKET_REPLY_TOOL.model_copy(update={"name": "freshdesk.close_ticket"})}
    )
    assert ticket_reply_of(action) == TicketReply(ticket=TICKET_ID, body=TEXT)
    with pytest.raises(ConnectorContractError):
        ticket_reply_of(other)


def test_a_reply_is_held_for_a_person_even_under_an_autonomous_leash() -> None:
    """**A reply to a customer is never sent by an agent on its own.** The tool is sensitive, so
    the gate caps it at Assisted whatever rung the leash gives. Delete this and an agent trusted to
    run unattended on tickets writes to customers with nobody reading first."""
    suspension = held(approve=False)
    assert suspension.action.tool.name == TICKET_REPLY_TOOL.name


def test_the_call_goes_to_the_connections_helpdesk_and_never_to_an_address_the_action_names() -> (
    None
):
    """The address comes from the connection's settings. Delete this and a reply prepared with a
    ticket id like an address could send the reply key somewhere the read key never goes."""
    action = held().action
    call = TicketReplyWrites().call_for(action, settings=connection().settings)
    assert (call.operation.base_url, call.operation.operation.path) == (
        f"https://{DOMAIN}",
        "/api/v2/tickets/{id}/reply",
    )
    assert dict(call.arguments) == {"id": TICKET_ID}
    assert call.entity == CONVERSATION and call.source_id == TICKET_ID
    other = TicketReplyWrites().call_for(
        action, settings=connection("other.freshdesk.com").settings
    )
    assert other.operation.base_url == "https://other.freshdesk.com"


@pytest.mark.parametrize(
    ("found", "named"),
    [
        (
            {"body_text": f"  {TEXT.replace(chr(10), '  ')} ", "private": False, "incoming": False},
            (),
        ),
        ({"body_text": "Thank you", "private": False, "incoming": False}, ("reply",)),
        ({"body_text": TEXT, "private": True, "incoming": False}, ("public_reply",)),
        ({"body_text": TEXT, "private": False, "incoming": True}, ("public_reply",)),
        ({"body_text": TEXT}, ("public_reply",)),
    ],
)
def test_a_conversation_holds_the_reply_only_as_a_public_reply_with_the_same_words(
    found: dict[str, Any], named: tuple[str, ...]
) -> None:
    """The same words, white space aside, as a public reply from the helpdesk: a private note, a
    customer's own message, or a conversation that does not say which, does not hold it. Delete
    this and a private note with the approved text is reported as the customer having been told."""
    assert TicketReplyWrites().differs(held().action, found) == named


# ------------------------------------------------------------------ sent and read back
def test_an_approved_reply_is_posted_with_the_reply_key_and_read_back_with_the_read_key() -> None:
    """**The positive case.** One POST of the escaped reply to the ticket's reply address with the
    reply key, then one GET of the ticket's conversations with the read key, which finds the reply
    among an earlier one, so it is reported done naming only the reply. Delete this and a reply can
    be sent with the read key or reported done from the send's own answer."""
    earlier = {
        "id": 1,
        "ticket_id": int(TICKET_ID),
        "body_text": "We are looking into it.",
        "incoming": False,
        "private": False,
    }
    desk = Helpdesk(conversations=[earlier])

    report = send(held(), desk)

    assert (report.outcome, report.told) == (WriteOutcome.DONE, SENT_AND_READ_BACK)
    assert desk.calls == [
        ("POST", REPLY_URL, authorization(SCHEME, KEYS[WRITE_PATH])),
        ("GET", CONVERSATIONS_URL, authorization(SCHEME, KEYS[READ_PATH])),
    ]
    assert desk.sent == [{"body": TicketReply(ticket=TICKET_ID, body=TEXT).html()}]
    assert report.found is not None
    assert [one.model_dump().get("conversation_id") for one in report.found.records] == [9001]


def test_an_approved_reply_resumed_twice_is_posted_once() -> None:
    """**Posted once.** Delete this and a retried run writes the same reply to a customer twice."""
    desk, ledger = Helpdesk(), _HeldLedger()
    reply = held()

    first = send(reply, desk, ledger=ledger)
    second = send(reply, desk, ledger=ledger)

    assert first.outcome is WriteOutcome.DONE
    assert (second.outcome, second.told) == (WriteOutcome.ALREADY_SENT, SENT_ALREADY)
    assert [method for method, _, _ in desk.calls] == ["POST", "GET"]


EARLIER: Final = {
    "id": 1,
    "ticket_id": int(TICKET_ID),
    "body_text": "We are looking into it.",
    "incoming": False,
    "private": False,
}


@pytest.mark.parametrize(
    ("posts", "private", "before", "told", "differs"),
    [
        (False, False, [], READ_BACK_UNKNOWN, ()),
        (False, False, [EARLIER], READ_BACK_DIFFERS, ("reply",)),
        (True, True, [], READ_BACK_DIFFERS, ("public_reply",)),
    ],
)
def test_a_reply_not_found_as_a_public_reply_is_reported_failed(
    posts: bool, private: bool, before: list[dict[str, Any]], told: str, differs: tuple[str, ...]
) -> None:
    """The helpdesk answered the send and the ticket holds no public reply with the words. Posted
    nothing on a ticket with no conversations, nothing is read back at all and it is not known;
    posted nothing beside an earlier reply, that reply is judged and differs by its words; posted
    a private note, it differs by being private. All three are failed, naming fields and no text.
    Delete this and a reply the customer never received is reported sent."""
    desk = Helpdesk(posts=posts, private=private, conversations=[dict(one) for one in before])

    report = send(held(), desk)

    assert (report.outcome, report.told) == (WriteOutcome.FAILED, told)
    assert report.differs == differs
    assert "refund" not in report.told


def test_without_the_reply_key_an_approved_reply_is_not_sent_and_the_approver_is_told_why() -> None:
    """On an install that has not given the reply key, the approved reply is not allowed in the
    grant's own words and nothing reaches the helpdesk; once the key is given the same approval is
    sent. Delete this and a reply is sent with the read key, or an approval is lost."""
    desk, ledger, reply = Helpdesk(), _HeldLedger(), held()

    refused = send(reply, desk, Keys(allows=False), ledger)
    later = send(reply, desk, Keys(allows=True), ledger)

    assert (refused.outcome, refused.told) == (
        WriteOutcome.NOT_ALLOWED,
        THIS_INSTALL_HAS_NOT_ALLOWED_TICKET_REPLIES,
    )
    assert later.outcome is WriteOutcome.DONE
    assert [method for method, _, _ in desk.calls] == ["POST", "GET"]


def test_the_connector_declares_the_reply_grant_and_its_read_back() -> None:
    """The grant is on the declaration, off until its key is given, and the conversations the
    read-back needs are a live entity with a manifest tool. Delete this and the reply can be held
    and approved on an install where nothing could ever send it."""
    assert freshdesk.CONNECTOR.writes == (TICKET_REPLIES,)
    assert TICKET_REPLIES.tools == (TICKET_REPLY_TOOL.name,)
    assert CONVERSATION in freshdesk.FreshdeskLiveLookup().entities()
    # The read-back is a live lookup and never a tool an agent is offered.
    names = {one.name for one in manifest_for(freshdesk.FRESHDESK, connection().settings).tools}
    assert not any("repl" in one for one in names)


# ------------------------------------------------------------------ the field a reply writes
def test_the_reply_is_classified_by_its_grant_and_a_caller_without_its_read_is_refused() -> None:
    """**`A_FIELD_A_WRITE_CREATES_IS_CLASSIFIED_BY_THE_GRANT_THAT_WRITES_IT`.** The reply's field
    is no field a ticket record holds, so the read classification does not name it and Ask never
    offers it; the grant names it behind `read:ticket.reply`, and the policy an action is decided
    under carries both. A caller holding the write and not that read is refused by the mask check
    rather than held. Delete this and a reply is either withheld on every install or held for a
    caller who may not see what it says."""
    from brain.gate.leash import CheckName, decide
    from brain.tools.startup import classification_for

    read = classification_for(TICKET, source=freshdesk.FRESHDESK)
    assert read is not None and freshdesk.REPLY_FIELD not in {one.column for one in read.rules}
    rule = POLICY.rule_for(TICKET, freshdesk.REPLY_FIELD)
    assert rule is not None and rule.required_capability.value == REPLY_READ
    assert POLICY.rule_for(TICKET, "status") is not None
    action = held().action
    blind = holding("u_blind", REPLY_CAPABILITY)
    refused = decide(
        action,
        caller=blind,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=AUTONOMOUS,
        assessment=CALM,
        now=NOW,
    )
    assert not refused.permitted
    assert [one.name for one in refused.checks if not one.permits] == [CheckName.MASK]


def test_a_grant_that_classifies_one_field_twice_is_refused() -> None:
    """Delete this and two rules for one field reach the policy, where the second silently
    replaces the first or the policy refuses to build on every install."""
    from dataclasses import replace

    from brain.connectors.ask import each_behind_its_own
    from brain.connectors.declaration import DeclarationError

    twice = each_behind_its_own(TICKET, (freshdesk.REPLY_FIELD,)) * 2
    with pytest.raises(DeclarationError):
        replace(TICKET_REPLIES, fields=twice)


def test_a_grants_fields_reach_only_the_entity_and_source_they_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grant that writes on two entities contributes each rule to its own entity's policy only,
    and a source that declares nothing contributes nothing. Delete this and a field one write
    creates on one record kind is treated as classified on every other kind the source has."""
    from dataclasses import replace
    from types import SimpleNamespace

    import brain.connectors.declaration as declaration
    from brain.connectors.ask import each_behind_its_own

    both = replace(
        TICKET_REPLIES,
        fields=(
            *each_behind_its_own(TICKET, (freshdesk.REPLY_FIELD,)),
            *each_behind_its_own("contact", ("note",)),
        ),
    )
    monkeypatch.setattr(
        declaration, "shipped", lambda: {freshdesk.FRESHDESK: SimpleNamespace(writes=(both,))}
    )
    assert [one.field for one in declaration.written_fields(freshdesk.FRESHDESK, TICKET)] == [
        freshdesk.REPLY_FIELD
    ]
    assert [one.field for one in declaration.written_fields(freshdesk.FRESHDESK, "contact")] == [
        "note"
    ]
    assert declaration.written_fields("nobody", TICKET) == ()
