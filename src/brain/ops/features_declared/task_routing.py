"""The switch on a task started with no agent being matched to what each agent is for.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off because it changes who answers. Today a question that names no agent is answered by the person
asking, at their own reach, unless one of three fixed words routes it; with this on, a question
that shares at least two words with what one agent is for (its name and its instruction) is
answered by that agent, still at the reach of the person asking narrowed by the agent's ceiling. An
install may want to see how its agents are described before they begin to catch questions.

Task ids: M40.7.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

TASK_ROUTING: Final = Feature(
    name="task_routing",
    title="Send a task started with no agent to the agent whose purpose it matches",
    what=(
        "A question that names no agent is matched to the agents the person may call. If it shares "
        "at least two distinct words with what exactly one of them is for, taken from its name "
        "and its instruction, that agent answers, at the person's own reach narrowed by the "
        "agent's ceiling. If two agents fit equally, or none does, the question is answered as "
        "it is today."
    ),
    while_off=(
        "A question that names no agent is answered as before: by the person asking, through every "
        "tool the install registered, unless the fixed keywords send it to an agent."
    ),
    read_by=("brain.api_routes:task_routing_is_on",),
)
