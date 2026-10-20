"""A coordinating agent handing subtasks to specialist agents (M18.5.1, M18.5.3, M18.6.2).

Off because it is the first thing in the product that starts one agent from another. The weighing
of a plan (`orchestration_rehearsal`) starts nothing; this does: a person asks a coordinating
agent, a model proposes subtasks, and specialist agents are run, each at the asker's reach
narrowed by every agent on the way. It also sends the asker's words to a model provider to be split
up, and it spends a model call per subtask, so an installation decides to have it rather than
finding it on. What a coordinator may call and whether it may run specialists at the same time are
set by an administrator per agent, and are read whether the switch is on or not, so turning it off
never hides who was allowed to call whom.

Task ids: M18.5.1, M18.5.3, M18.6.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

MULTI_AGENT_COORDINATION: Final = Feature(
    name="multi_agent_coordination",
    title="Let a coordinating agent hand subtasks to specialist agents",
    what=(
        "An administrator of agents names, for an agent, the other agents it may hand a subtask "
        "to, and may let it run them at the same time. A person who asks a coordinating agent "
        "has the request split into subtasks by a model; the split is checked, weighed and run, "
        "each specialist at the asker's own access narrowed by both agents, and the results "
        "that match what each subtask promised are put together, with a stated gap where one "
        "did not. Specialists run one after another unless running them together was allowed "
        "and the estate has room."
    ),
    while_off=(
        "No agent hands work to another and nothing is sent to a model to be split up. Who an "
        "agent may call and whether it may run specialists together can still be read and set."
    ),
    read_by=("brain.coordination_routes:coordination_is_on",),
)
