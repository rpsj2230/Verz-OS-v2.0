"""Where the skills a run of an automation through an agent would be offered are read.

An automation names the tools it may use and does not name skills: a run carries the skills the
agent has attached, approved and left unchanged on the day it starts, narrowed to those whose
tools its owner's reach allows. A card that says what an automation may use has to say that, and
three routes say it (the form that writes one, the agent's own Automations tab and the Automations
module's page), so the one question "which skills would a run be offered" is asked here and in no
second place.

**It is the answer lane's own question.** `StoredAutomationSkills` goes through
`brain.escalation_routes.offered_skills`, which builds the run `/answer` builds
(`brain.api_routes.agent_run_of`) and asks `brain.gate.model_lane.skills_offered`, so a card and a
run read one set of pins, one library and one filter. Rejected: reading the agent's pins and the
library here and filtering them, which is a second copy of the rule that an unapproved or moved
skill is never offered, and the copy that goes stale first.

**The reach is the caller's, and the caller passes it as an automation is admitted.** `skills_
offered` narrows whatever it is handed by the agent's ceiling, so this module computes nothing: a
reader asking about their own automation hands their reach admitted at read, and a reader asking
about somebody else's is not told a list read at a reach that is not theirs (the routes decide
that and never ask).

**It is a module of its own to break an import cycle, and the cycle is the reason it is not
inside `brain.automation_authoring_routes`.** That module reaches `brain.agent_lifecycle_routes`,
which reaches `brain.automation_schedule_routes`, which now needs this.

Task ids: M39.9.2.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from fastapi import Request

from brain.agents.model import AgentRecord
from brain.core.entitlement import EntitlementSet
from brain.tools.skills import SkillCard, offered_cards


@runtime_checkable
class AutomationSkills(Protocol):
    """Where the skills a run through an agent would be offered are read.

    `StoredAutomationSkills` is the one the product uses. Anything else a route finds on
    `app.state.automation_skills` stands in for it, as every other store here does, so a test can
    say what an agent offers without a database.
    """

    async def offered(
        self, agent: AgentRecord, *, reach: EntitlementSet, now: datetime
    ) -> tuple[SkillCard, ...]: ...


class StoredAutomationSkills:
    """`AutomationSkills` over the install's own skill pins and library."""

    def __init__(self, request: Request) -> None:
        self._request = request

    async def offered(
        self, agent: AgentRecord, *, reach: EntitlementSet, now: datetime
    ) -> tuple[SkillCard, ...]:
        # Imported here for the reason `brain.escalation_routes` imports its siblings here: it
        # serves routes of its own, and importing it at the top would draw the channels with it.
        from brain.escalation_routes import offered_skills

        return offered_cards(await offered_skills(self._request, agent, caller=reach, now=now))


def skills_of(request: Request) -> AutomationSkills:
    """`app.state.automation_skills` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "automation_skills", None)
    if isinstance(found, AutomationSkills):
        return found
    return StoredAutomationSkills(request)
