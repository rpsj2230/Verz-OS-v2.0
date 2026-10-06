"""The install acceptance check for an agent run that asks for a write: held, and sent by nobody.

One check, over the product's own pieces end to end, inside the check's transaction. A helpdesk made
up for the run is connected as the Connectors route connects one and read as the worker reads it, so
a ticket is in the index. An agent of acceptance_a is installed with its leash at Assisted on
tickets and the helpdesk's read and its reply among its tools, and its **real run**
(`brain.gate.runtime.AgentRuntime`, over the registry the application builds and the row tools it
registers) is driven with a scripted model that asks to reply to that ticket, twice, and then
answers.

**What is proved is what the run does with a write a model asked for, and what it does not do.**
The reply the model asked for is held for a person: one pending suspension, in the asker's name,
whose action is the Freshdesk reply tool with the words whole, in the helpdesk's department, which
the connection supplies and the model never names. Asking for the same reply a second time holds no
second. The model is told it is held and is told nothing of who decides, why, in which department or
which suspension. And nothing was sent: the worker's run of approved actions, with the helpdesk's
own writer and the reply key made available, finds nothing to send while the suspension is pending
and sends the reply once, to the connection's helpdesk, after a person in the department
approves it.

**The ticket is read at the run's reach, by the entity's own row tool, before anything is
prepared.** The scripted model asks for a ticket the helpdesk has, so the check does not prove the
refusal for a ticket the reader cannot see; that is `tests/unit/test_runtime_side_effects.py`, over
fakes, and a refusal is only evidence about a real reader when the same reader answers the positive
case, which this check does.

**No socket is opened and no real key is held.** The helpdesk is `acceptance_freshdesk_reply._Desk`,
the keys are made up per slot, and the operation ledger is the in-memory one the other write checks
use. What only a real helpdesk proves (that Freshdesk accepts the post and lists the reply) is the
owner's to see on his own helpdesk once he gives the reply key.

**The check does not run where Freshdesk is connected already**, for the sources check's reason.

Task ids: M13.7.6
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.models.driver import DriverMessage, DriverResponse

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 397

A, _ = RESERVED_DEPARTMENTS

# What the check says, one sentence for each way the property can fail.
FRESHDESK_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Freshdesk connected already, so the check does not connect a helpdesk of "
    "its own beside it"
)
THE_AGENT_HAS_NO_STANDING: Final = (
    "the check's agent was installed and the worker read no standing for it"
)
THE_APPLICATION_REGISTERED_NO_REPLY: Final = (
    "the application's registry holds no tool that asks for a reply to a ticket, beside the row "
    "tool that reads one"
)
A_RUN_HELD_NOTHING: Final = "an agent's run asked to reply to a ticket held no action for a person"
A_RUN_HELD_THE_WRONG_ACTION: Final = (
    "the action an agent's run held was not the reply it asked for, with its words, in the "
    "helpdesk's department, in the asker's name"
)
A_RUN_HELD_ONE_REPLY_MORE_THAN_ONCE: Final = (
    "an agent's run held the same reply for a person more than once"
)
A_MODEL_WAS_TOLD_WHO_DECIDES: Final = (
    "a model whose reply was held was told more than that it is held"
)
A_RUN_SENT_BEFORE_A_PERSON_DECIDED: Final = (
    "a reply an agent's run asked for was sent before a person approved it"
)
THE_APPROVED_REPLY_WAS_NOT_SENT_ONCE: Final = (
    "an approved reply an agent's run held was not posted once to the helpdesk and read back"
)

#: Words a model must not be told after its reply is held, which are facts about who decides.
THE_APPROVERS_WORD: Final = "approv"


@dataclass
class _Scripted:
    """An `AnswerModel` replying from a script and keeping every conversation it was shown."""

    replies: list[str]
    shown: list[tuple[DriverMessage, ...]] = field(default_factory=list)

    async def complete(self, messages: Sequence[DriverMessage], **kwargs: Any) -> DriverResponse:
        from brain.models.driver import DriverResponse, TokenUsage

        del kwargs
        self.shown.append(tuple(messages))
        return DriverResponse(
            deployment_id="acceptance",
            model="acceptance",
            text=self.replies.pop(0) if self.replies else '{"answer": "done"}',
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            finish_reason="stop",
        )


class _NoPassages:
    """The passage search of a lane whose agent reads no passage, which is never asked."""

    async def passages(self, question: str, *, entitlement: EntitlementSet, now: Any) -> Any:
        from brain.core.envelope import TypedResult
        from brain.knowledge.document_tools import KnowledgePassage

        del question, entitlement, now
        return TypedResult[KnowledgePassage](records=(), source="")


@check(
    leaves=("M13.7.6",),
    sentence=(
        "An installed agent's own run, asked by a person in acceptance_a to reply to a ticket of a "
        "helpdesk made up for the check, holds exactly one reply for a person however often the "
        "model asks, tells the model only that it is held, and sends nothing: the worker's run "
        "finds nothing to send while it is pending and posts it once, after a person approves."
    ),
)
async def an_agents_run_holds_the_reply_it_asks_for_and_sends_nothing(h: Harness) -> None:
    from brain.agents.template import LeashRung, ManifestGuardrails
    from brain.api_routes import RunToolCaller, policy_of
    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.connectors import freshdesk
    from brain.core.envelope import SideEffect
    from brain.gate.abstain import SearchScope
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.model_lane import ModelLane
    from brain.gate.runtime import AgentRuntime
    from brain.gate.runtime_effects import ConnectorSideEffects
    from brain.gate.suspension_store import StoredSuspensions
    from brain.knowledge.row_store import SessionRowSource
    from brain.models.metering import Meter
    from brain.ops.acceptance_checks import _HeldLedger
    from brain.ops.acceptance_checks_connectors import _Resolver
    from brain.ops.acceptance_checks_sources import _connect_and_read, _connection
    from brain.ops.acceptance_freshdesk_reply import HELPDESK, _Desk, _Leases
    from brain.ops.acceptance_workspace import installed_agent, stored_agent
    from brain.ops.approved_runs import (
        ApprovedRun,
        ConnectorWrites,
        Ran,
        StoredStandings,
        run_approved,
    )
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    if (await h.execute(live(freshdesk.FRESHDESK))).scalar_one_or_none() is not None:
        raise CheckNotRunError(FRESHDESK_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    # A helpdesk made up for the run, connected and read, so its ticket is in the index.
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

    # The people: one who asks, and one who may approve, each in the helpdesk's department.
    scope = Scope.department(A)
    write = freshdesk.REPLY_CAPABILITY
    see = f"read:{freshdesk.TICKET}.{freshdesk.REPLY_FIELD}"
    reads = (f"read:{freshdesk.TICKET}", f"read:{freshdesk.TICKET}.subject")
    asker, approver = h.principal(A, "runasker"), h.principal(A, "runapprover")
    await h.person(asker, department=A, grants=tuple((one, scope) for one in (write, see, *reads)))
    await h.person(approver, department=A, grants=((write, scope), (see, scope)))
    read_tool = f"{freshdesk.FRESHDESK}.read_{freshdesk.TICKET}"
    agent = await installed_agent(
        h,
        asker,
        capabilities=(write, see, *reads),
        allowed_tools=(freshdesk.TICKET_REPLY_TOOL.name, read_tool),
        connectors=(freshdesk.CONNECTOR_NAME,),
        suffix="_run",
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

    # The application's registry over the check's own rows, and the real run over it.
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    if not registry.has(freshdesk.TICKET_REPLY_TOOL.name) or not registry.has(read_tool):
        raise CheckFailedError(THE_APPLICATION_REGISTERED_NO_REPLY)
    asking = await h.reach(asker)

    async def reach_now(now: Any) -> EntitlementSet:
        return await StoredEntitlements(h.sessions).load(asker, now)

    async def not_halted() -> str:
        return ""

    store = StoredSuspensions(h.sessions)
    runtime = AgentRuntime(
        record=await stored_agent(h, agent),
        asker=asking,
        registry=registry,
        leash=standing.leash,
        tools=RunToolCaller(registry),
        policy_for=policy_of(registry),
        reach_now=reach_now,
        halted=not_halted,
        assessment=RiskAssessment(score=0, matched=()),
        side_effects=ConnectorSideEffects(
            suspensions=store, connections=StoredConnections(h.sessions).connected
        ),
    )
    words = f"Thank you for waiting. Reference {h.word()} & {h.word()}."
    asked = json.dumps(
        {
            "tool": freshdesk.TICKET_REPLY_TOOL.name,
            "arguments": {
                freshdesk.TICKET_KEY: str(ticket["id"]),
                freshdesk.REPLY_ARGUMENT: words,
            },
        }
    )
    model = _Scripted([asked, asked, '{"answer": "I have asked for that reply."}'])
    await runtime.drafted(
        "Please reply to the customer on the refund ticket.",
        lane=ModelLane(search=_NoPassages(), model=model),
        scope=SearchScope(),
        sink=CountingTraceSink(),
        now=h.now,
        meter=Meter(),
        trace_id=h.trace_id,
        started=lambda: None,
    )

    # One reply held, as the asker's, in the helpdesk's department, with the words whole.
    waiting = [
        one
        for one in await store.reading_as(await h.reach(approver), h.now).open_suspensions()
        if one.action.agent_id == agent
    ]
    if not waiting:
        raise CheckFailedError(A_RUN_HELD_NOTHING)
    if len(waiting) > 1:
        raise CheckFailedError(A_RUN_HELD_ONE_REPLY_MORE_THAN_ONCE)
    [held] = waiting
    # Judged field by field and not against the preparer's own output, which a broken preparer
    # would match whatever it built.
    action = held.action
    if (
        action.tool.name != freshdesk.TICKET_REPLY_TOOL.name
        or action.agent_id != agent
        or action.args != {freshdesk.REPLY_FIELD: words}
        or action.row != {freshdesk.DEPARTMENT_SETTING: A, freshdesk.TICKET_KEY: str(ticket["id"])}
        or held.principal_id != asker
        or action.digest() != held.action_digest
    ):
        raise CheckFailedError(A_RUN_HELD_THE_WRONG_ACTION)

    # The model was told it is held, and nothing of who decides or what it is filed as.
    told = [str(convo[-1].content) for convo in model.shown[1:3]]
    about_who_decides = (held.id, A, str(ticket["id"]), asker, approver, THE_APPROVERS_WORD)
    if len(set(told)) != 1 or any(
        one.casefold() in told[0].casefold() for one in about_who_decides
    ):
        raise CheckFailedError(A_MODEL_WAS_TOLD_WHO_DECIDES)

    # Nothing is sent while it waits, and once a person approves it the worker sends it once.
    leases, ledger = _Leases(allows=True), _HeldLedger()

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

    async def worker() -> ApprovedRun:
        return await run_approved(
            h.sessions,
            now=h.now,
            executors=(writes,),
            standings=standings,
            reaches=StoredEntitlements(h.sessions),
            ledger=ledger,
        )

    waited = await worker()
    if desk.sent or waited.outcomes:
        raise CheckFailedError(A_RUN_SENT_BEFORE_A_PERSON_DECIDED)
    await take_decision(
        store,
        held.id,
        await h.reach(approver),
        DecisionAsked(verdict=DecidableVerdict.APPROVED),
        trace_id=h.trace_id,
        now=h.now,
    )
    sent = await worker()
    again = await worker()
    if (
        dict(sent.outcomes) != {Ran.DONE: 1}
        or len(desk.sent) != 1
        or [one.get("body_text") for one in desk.conversations] != [words]
        or dict(again.outcomes) not in ({}, {Ran.ALREADY_RAN: 1})
    ):
        raise CheckFailedError(THE_APPROVED_REPLY_WAS_NOT_SENT_ONCE)
