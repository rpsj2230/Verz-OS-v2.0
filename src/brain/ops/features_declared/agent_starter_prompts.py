"""The switch on an agent offering three starter prompts when it is opened.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until an install has agents whose skills carry example tasks worth offering. The prompts are
the example tasks the skills pinned to the agent carry, and only those a run at this person's reach
through this agent could carry out, so nothing is offered that could not be answered; the switch is
about the owner seeing the examples his authors wrote before they are shown to everybody.

Task ids: M40.7.8
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

AGENT_STARTER_PROMPTS: Final = Feature(
    name="agent_starter_prompts",
    title="Offer three starter prompts when a person opens an agent",
    what=(
        "Choosing an agent on Ask shows up to three questions to start with, taken from the "
        "example tasks of the approved skills pinned to that agent. A prompt is shown only when "
        "every tool it needs and every department's knowledge it reads is within what the person "
        "can reach through that agent."
    ),
    while_off=("Choosing an agent shows no starter prompts. Nothing else about the agent changes."),
    read_by=("brain.member_starter_routes:starters_are_on",),
)
