"""Offering one agent to several departments and named people (needs-rupash 201, question 1).

Off because it is a new way to widen who is shown an agent. The table behind it
(`agent.audience_extra`) and the roster's reading of it have existed since `0223`; what this
switch holds back is the control that writes to it from the agent's Profile. The owner has not
yet answered whether an agent's audience stays one choice (question 1, option A) or may name
several departments and people (option B), so the Profile reads what is stored whatever the
switch says and offers the add and remove controls only while it is on. Turning it on is the
owner's answer to that question, and turning it off again leaves every stored offer in place and
stops anyone adding or removing one.

Task ids: M27.11.13
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

AGENT_AUDIENCE_EXTRAS: Final = Feature(
    name="agent_audience_extras",
    title="Offer an agent to more departments and to named people",
    what=(
        "Whoever holds the lifecycle authority over an agent can offer it, from its Profile, to "
        "further departments and to named people beside its level, and withdraw the offer. An "
        "offer only makes the agent appear for those people and start for them: it never gives "
        "them anything the person asking could not already reach, and it is refused for a "
        "personal agent, which only its owner finds."
    ),
    while_off=(
        "The Profile shows who the agent is offered to and offers no way to change it. Offers "
        "already stored keep working, and nobody can add or withdraw one."
    ),
    read_by=("brain.agent_audience_routes:extras_are_on",),
)
