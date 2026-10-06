"""The install acceptance check that an agent reads only the connectors it is bound to.

M13.7.8 asks that an agent run call only the connectors bound to that agent, and that a call to any
other be refused by the gate even when the asking person could reach that source directly. M13.8.1
asks that the connector list compile into the ceiling through the one intersection.

**The agent that matters holds the source's reads and does not name it.** The neighbouring
readiness checks (`brain.ops.acceptance_checks_connectable`) ask an unbound agent that holds none
of the source's reads, which its capability ceiling refuses whether or not binding exists. This
check gives the second agent every read the bound one has, so the only difference between the two
is the connector list, and the only thing that can refuse it is the list compiled into its ceiling
(`brain.agents.binding.AN_AGENT_READS_ONLY_THE_SOURCES_IT_NAMES`).

**The walk.** A helpdesk made up for the check is connected from its form and read by the worker,
as the Freshdesk readiness check connects one. A person granted the ticket reads asks about the open
ticket and is answered from it. The same person asks through an agent naming Freshdesk and is
answered, and through an agent holding the same reads and naming nothing, and is told exactly what a
ticket that does not exist tells them. Then the three reaches are read as `/answer` computes them:
the person's holds the ticket read, the bound run's holds it, the other run's does not.

No socket is opened and no real key is held
(`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`).

Task ids: M13.7.8, M13.8.1
"""

from __future__ import annotations

import uuid
from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 423

A, _ = RESERVED_DEPARTMENTS

#: The helpdesk address the check connects. Never reached: the check's own helpdesk answers it.
HELPDESK: Final = "acceptance-binding.freshdesk.com"

# What the check says, one sentence for each way the property can fail.
THE_PERSON_WAS_NOT_ANSWERED: Final = (
    "a person granted the helpdesk's reads was not answered about its open ticket"
)
THE_BOUND_AGENT_WAS_NOT_ANSWERED: Final = "an agent bound to the helpdesk could not use it"
AN_UNBOUND_AGENT_HOLDING_THE_READS_WAS_ANSWERED: Final = (
    "an agent holding the helpdesk's reads but not bound to it was answered from it"
)
THE_UNBOUND_RUN_HELD_THE_READ: Final = (
    "a run through an agent not bound to the helpdesk held the helpdesk's read"
)


@check(
    leaves=("M13.7.8", "M13.8.1"),
    sentence=(
        "A helpdesk made up for the check is connected and a person granted its reads is answered "
        "about its open ticket. An agent naming it answers too. An agent holding the same reads "
        "and naming no connector is told what a missing ticket tells it, and its run reach holds "
        "no ticket read."
    ),
)
async def an_agent_reads_only_the_connectors_it_is_bound_to(h: Harness) -> None:
    from brain.connectors import freshdesk
    from brain.connectors.minimal_index import fresh_canary
    from brain.core.entitlement import Capability
    from brain.ops.acceptance_checks_connectable import (
        _answering,
        _asked,
        _from_the_console,
        _on_ask,
        _prose,
        _run_reaches,
        _served,
    )
    from brain.ops.acceptance_checks_skills import _an_agent
    from brain.ops.acceptance_checks_sources import OPEN, _Helpdesk

    await h.found_departments()
    subject, body = h.word(), fresh_canary("ACCEPTANCE")
    ticket = {
        "id": 900_000 + uuid.uuid4().int % 99_999,
        "subject": subject,
        "status": OPEN,
        "priority": 1,
        "company_id": 1,
        "requester_id": 1,
        "group_id": 1,
        "created_at": "2019-03-01T10:00:00Z",
        "updated_at": "2019-03-02T10:00:00Z",
        "due_by": "2019-03-08T10:00:00Z",
    }
    source = await _from_the_console(
        h,
        freshdesk.FRESHDESK,
        {freshdesk.DOMAIN_SETTING: HELPDESK, freshdesk.DEPARTMENT_SETTING: A},
        _Helpdesk(ticket, body=body),
    )
    scope = Scope.department(A)
    reads = (
        f"read:{freshdesk.TICKET}",
        f"read:{freshdesk.TICKET}.subject",
        f"read:{freshdesk.TICKET}.{freshdesk.LIVE_BODY_FIELD}",
    )
    app = await _answering(h, source)
    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=tuple((one, scope) for one in reads))
    owner = h.principal(A, "builder")
    await h.person(owner, department=A)
    settled = (await _served(h), app.state.tools)
    bound = await _an_agent(
        h,
        owner,
        capabilities=reads,
        named="_bound",
        scope=scope,
        connectors=(freshdesk.FRESHDESK,),
        settled=settled,
    )
    holding = await _an_agent(
        h, owner, capabilities=reads, named="_holding", scope=scope, settled=settled
    )

    asked = _asked(freshdesk.LIVE_BODY_FIELD, subject)
    if body not in _prose(await _on_ask(h, app, reader, asked)):
        raise CheckFailedError(THE_PERSON_WAS_NOT_ANSWERED)
    if body not in _prose(await _on_ask(h, app, reader, asked, agent=bound)):
        raise CheckFailedError(THE_BOUND_AGENT_WAS_NOT_ANSWERED)
    refused = await _on_ask(h, app, reader, asked, agent=holding)
    nothing = await _on_ask(
        h, app, reader, _asked(freshdesk.LIVE_BODY_FIELD, h.word()), agent=holding
    )
    if body in _prose(refused) or _prose(refused) != _prose(nothing):
        raise CheckFailedError(AN_UNBOUND_AGENT_HOLDING_THE_READS_WAS_ANSWERED)

    read = Capability(value=reads[1])
    person, through_bound, through_holding = await _run_reaches(h, reader, bound, holding)
    if not (person.holds(read, h.now) and through_bound.holds(read, h.now)):
        raise CheckFailedError(THE_BOUND_AGENT_WAS_NOT_ANSWERED)
    if through_holding.holds(read, h.now):
        raise CheckFailedError(THE_UNBOUND_RUN_HELD_THE_READ)
