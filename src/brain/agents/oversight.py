"""Which personal agents a reader holding the audit capability may be shown, for oversight.

A personal agent is found, opened and used by its owner and by nobody else
(`brain.agents.model.visible_to`), and that stays true here. The owner's direction on needs item 173
(2026-10-12) also asks that a reader who holds the audit capability for it may be shown it, **for
oversight**: so that somebody who answers for what the install's agents are can say that a personal
agent exists, whose it is and whether it is running, without being able to ask it anything. This
module is that and nothing else.

**Oversight is a second view and never a second audience.** The tempting design was to widen
`visible_to` so that an auditor's roster listed personal agents too. It would have been one line,
and it would have made "who may see the agent" and "who may use it" the same answer, which is
exactly the conflation `brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY` exists to refuse: an auditor
who saw a personal agent in the picker could select it, ask it, open its workspace and read its
settings. So the roster, the workspace, `/answer` and every other listing keep asking
`visible_agent_ids`, which still answers the owner alone, and this is a separate list that names an
agent and offers nothing to do with it. See `OVERSIGHT_OFFERS_THE_AGENT_TO_NOBODY`.

**It tells the reader that the agent exists and nothing about what it holds.** Its identifier, its
name, whose it is and its lifecycle word. Not its persona, its connectors, what its owner connected
to it, its channels, its conversations or its runs: what a person connected to their own agent is
their own, and the ledger (`brain.audit.view`) is where an auditor reads what changed, under the
audit capability and its own rules. See `OVERSIGHT_NAMES_THE_AGENT_AND_NOTHING_IT_HOLDS`.

**The audit capability is the existing one, asked of the existing question.** `read:audit.agent`,
evaluated in the scope the reader's grant carries by `brain.audit.view.may_audit`, asked of an entry
about the agent that its owner made. A company-wide grant therefore covers every personal agent, and
a grant scoped to the people a department places covers the agents those people own. No capability
was invented for this, and a reader who holds none is shown nothing, which is also what an install
with no personal agents shows (see `OVERSIGHT_SAYS_NOTHING_TO_A_READER_WITHOUT_THE_CAPABILITY`).

**The reader's own agents are not listed here**: they are on their roster, and a list of an
auditor's own agents under a heading about other people's would be a second place to look for them.

**Nothing is counted.** The functions return the agents and there is no field a total, or a number
of agents the reader may not be shown, could be put in. An agent outside the reader's audit reach is
absent, which is what an agent that was never made is.

Rejected: listing personal agents to an auditor through the roster with a flag, which is the
widening above; and a table of "overseen" agents kept beside the agent table, which is a second
copy of who owns what that would drift from the first.

Task ids: M39.10.3
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.agents.model import AgentRecord, AgentState
from brain.audit.ledger import AuditAction
from brain.audit.view import may_audit
from brain.core.entitlement import EntitlementSet
from brain.knowledge.visibility import Visibility

# ------------------------------------------------------------------ written-down reasons
#: Why oversight is a list of its own and not a wider audience.
OVERSIGHT_OFFERS_THE_AGENT_TO_NOBODY: Final = (
    "An auditor is told that a personal agent exists, whose it is and whether it runs. They are "
    "not offered it: it is not in their roster, they cannot open its workspace, select it or ask "
    "it, because who may see an agent and who may use it are different questions and widening the "
    "first to answer an oversight need would have widened the second."
)

#: What oversight names, and what it leaves with the owner.
OVERSIGHT_NAMES_THE_AGENT_AND_NOTHING_IT_HOLDS: Final = (
    "The view names the agent, its owner and its lifecycle word. What its owner connected to it, "
    "what it was told and what it did are the owner's own, and the audit ledger, under its own "
    "rules, is where an auditor reads what changed."
)

#: Why a reader without the capability is shown the same as an install with no personal agents.
OVERSIGHT_SAYS_NOTHING_TO_A_READER_WITHOUT_THE_CAPABILITY: Final = (
    "A reader outside the audit reach of every personal agent is answered the empty list, with the "
    "status and the shape an install with no personal agents gets, so the answer cannot be used to "
    "find out whether a person has made one."
)

#: The ledger entries an agent's own changes are recorded as: its lifecycle and its owner. The
#: capability is asked of the entries an auditor would read about the agent.
AGENT_ACTIONS: Final[tuple[AuditAction, ...]] = (AuditAction.AGENT, AuditAction.AGENT_OWNER)

#: The kind of subject an agent is in the ledger.
AGENT_SUBJECT: Final = "agent"


@dataclass(frozen=True)
class OverseenAgent:
    """One personal agent as oversight tells of it: whose, its name, and whether it runs."""

    agent_id: str
    display_name: str
    owner_id: str
    state: AgentState


def overseen(
    records: Iterable[AgentRecord], reader: EntitlementSet, now: datetime
) -> tuple[OverseenAgent, ...]:
    """The personal agents, other people's, that this reader's audit reach covers.

    In display name and then id order, so two readings of an unchanged estate are one list and the
    order says nothing about when an agent was made. Another person's, because the reader's own are
    on their roster. See `OVERSIGHT_OFFERS_THE_AGENT_TO_NOBODY`.
    """
    found = [
        one
        for one in records
        if one.audience.level is Visibility.PERSONAL
        and one.audience.owner_id != reader.principal_id
        and may_audit(
            reader,
            subject_kind=AGENT_SUBJECT,
            subject_id=one.agent_id,
            actions=AGENT_ACTIONS,
            now=now,
            actor_id=one.audience.owner_id,
        )
    ]
    return tuple(
        OverseenAgent(
            agent_id=one.agent_id,
            display_name=one.display_name,
            owner_id=one.audience.owner_id,
            state=one.state,
        )
        for one in sorted(found, key=lambda one: (one.display_name, one.agent_id))
    )
