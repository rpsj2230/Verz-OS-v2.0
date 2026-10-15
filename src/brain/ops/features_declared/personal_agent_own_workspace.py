"""The switch on attaching a person's own Google account to their personal agent.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until the owner has done the Google steps on needs item 173 and watched it on his install: it
lets a person's agent read that person's own mail, calendar and documents, which is the first thing
an agent does that reads one person's private correspondence. It is separate from
`personal_agents` because making an agent and giving it a mailbox are different decisions, and an
install may want the first long before the second.

Task ids: M39.10.4
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

PERSONAL_AGENT_OWN_WORKSPACE: Final = Feature(
    name="personal_agent_own_workspace",
    title="Let a person attach their own Google account to their personal agent",
    what=(
        "The owner of a personal agent may attach their own Google account (mail, calendar and "
        "documents) to it, from the agent's page, when the company has connected Google Workspace "
        "and given them access to it. The agent then reads that person's own account with that "
        "person's own consent, for them alone. No colleague, administrator or other agent can ask "
        "for it, and a team agent never carries one."
    ),
    while_off=(
        "A personal agent cannot have a Google account attached. One that already has stays "
        "attached and can still be detached, and a person's own account is still read for their "
        "own questions on Ask as before."
    ),
    read_by=("brain.agent_own_workspace_routes:own_workspace_is_on",),
)
