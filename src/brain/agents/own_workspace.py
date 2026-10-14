"""A person's own Google account on their personal agent: who may attach it, and what attaching is.

The owner's direction on needs item 173 (2026-10-12) is that a person connects their own Google
account (mail, calendar, documents) to their personal agent, that what it reads is that person's
own, and that no colleague, administrator or other agent can ask for it. The reading was already
built (`brain.ops.google_workspace_live.WorkspacePassages`, M11.7.6): each question is read with
the asker's own consent and told to the asker alone. What was missing was the agent's half, and it
was missing in a specific way: a connector is attached to an agent by the connector administrator
(needs-rupash 178 A), so a person who made their own agent could not give it their own mailbox, and
the generic attach refused the Google connector anyway, because it opens nothing the agent's
capabilities name. This module is the decision that fills the gap and nothing wider.

**Attaching is naming the connector, and the read follows from the name.** The agent's own
connector list is where every connector an agent carries lives
(`brain.agents.attachments.A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`), and a personal
agent that names a connector of its owner's own accounts carries that connector's read in its
ceiling (`brain.agents.model.own_reads`). So there is one fact to write, and the page, the ceiling
and the ledger cannot disagree about it. Rejected: also writing the read into the agent's
capabilities, which is a second record of the same attachment.

**The owner attaches their own account to their own agent, and nobody else attaches anything.**
`brain.agents.model.visible_to` answers only the owner for a personal agent, so anybody else is
answered as for an agent that was never made. The connector administrator is deliberately not
given this: attaching somebody's mailbox to an agent is not a connector decision, it is the person's
own, and an administrator's press could never be the person's consent. The consent itself is a
separate act the person makes at Google from My workspace, and this attaches nothing without it
being possible: **an account the person has not been given access to is refused**, because nothing
would ever be read from it.

**A team agent never carries one**, whoever asks, and says so in a sentence that holds under every
answer to needs item 189: how a team agent may use mail at all is the owner's question, and until he
answers it a team agent has no person's own account. See
`brain.agents.model.A_TEAM_AGENT_NEVER_CARRIES_A_PERSONS_OWN_WORKSPACE`.

**Detaching asks nothing but ownership**, and is available with the switch off: a person who wants
their own account off their agent is never held up by a setting.

Task ids: M39.10.4, M39.10.5
"""

from __future__ import annotations

from typing import Final

from brain.agents.model import AgentRecord
from brain.knowledge.visibility import Visibility

# ------------------------------------------------------------------ written-down reasons
#: Why the owner and nobody else attaches it.
A_PERSONS_OWN_ACCOUNT_IS_ATTACHED_BY_THAT_PERSON_TO_THEIR_OWN_AGENT: Final = (
    "A person's own Google account is attached by that person, to an agent only they can use. "
    "An administrator's press is never a person's consent and a colleague cannot see the agent, "
    "so the owner is the one person who is asked, and everybody else is answered as for an agent "
    "that was never made."
)

#: The connector a person's own Google account is.
CONNECTOR: Final = "google_workspace"

# ------------------------------------------------------------------ what a refusal says
#: Said for a team agent, to somebody who can see it. It names no person and no mailbox.
A_TEAM_AGENT_CARRIES_NO_ONES_OWN_ACCOUNT: Final = (
    "Nothing was attached: a team agent never carries one person's own Google account. Attach "
    "yours to an agent that only you can use."
)

#: Said when the person has not been given access, or Google Workspace is not connected. One
#: sentence for both, because the person cannot tell the two apart and the difference is not theirs.
NOT_OFFERED_TO_YOU: Final = (
    "Nothing was attached: your own Google account is not available to you yet. Ask your "
    "administrator whether Google Workspace is connected and whether you have been given access."
)

#: Said while the switch is off.
NOT_SWITCHED_ON: Final = (
    "Nothing was attached: attaching your own Google account to your agent is not switched on for "
    "this company yet."
)

ALREADY_ATTACHED: Final = "Your own Google account is already attached to this agent."
NOT_ATTACHED: Final = "Your own Google account is not attached to this agent."
THE_AGENT_MOVED: Final = (
    "This agent changed after you opened it, so nothing was changed. Look again and choose."
)

#: What the ledger entry for the connector added or taken carries.
ATTACHED_REASON: Final = "own_workspace_attached"
DETACHED_REASON: Final = "own_workspace_detached"


def is_personal(record: AgentRecord) -> bool:
    """Whether this is an agent only its owner can use."""
    return record.audience.level is Visibility.PERSONAL


def owns(record: AgentRecord, principal_id: str) -> bool:
    """Whether this is a personal agent and this person is its owner."""
    return is_personal(record) and record.audience.owner_id == principal_id


def is_attached(record: AgentRecord) -> bool:
    """Whether the agent names the person's own account. A team agent's name for it is inert, so
    it is not attached however it is named."""
    return is_personal(record) and CONNECTOR in record.authority.connectors


def attach_refusal(record: AgentRecord, *, offered: bool, switched_on: bool) -> str | None:
    """Why this agent may not have the owner's own account attached now, or None when it may.

    The caller has already established that they own the agent, so this is the agent's and the
    person's standing and nothing about who is asking. Order is the order a person would fix them
    in: a team agent cannot be mended, a switch is the company's, and access is the administrator's.
    """
    if not is_personal(record):
        return A_TEAM_AGENT_CARRIES_NO_ONES_OWN_ACCOUNT
    if is_attached(record):
        return ALREADY_ATTACHED
    if not switched_on:
        return NOT_SWITCHED_ON
    if not offered:
        return NOT_OFFERED_TO_YOU
    return None


def detach_refusal(record: AgentRecord) -> str | None:
    """Why the owner's own account cannot be taken off this agent, or None when it can."""
    return None if is_attached(record) else NOT_ATTACHED


def after_attach(record: AgentRecord) -> tuple[str, ...]:
    """The agent's connector list with the person's own account added."""
    return (*record.authority.connectors, CONNECTOR)


def after_detach(record: AgentRecord) -> tuple[str, ...]:
    """The agent's connector list with the person's own account taken out."""
    return tuple(one for one in record.authority.connectors if one != CONNECTOR)
