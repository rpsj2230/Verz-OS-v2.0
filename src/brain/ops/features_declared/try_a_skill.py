"""The switch on trying an approved skill from its card.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off because a try is a real run: it costs what any run costs, at the person's own reach, and it
puts a skill in front of a model that its agent was not assigned. Nothing about the skill's
approval changes, and a skill nobody approved is never tried.

Task ids: M40.7.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

TRY_A_SKILL: Final = Feature(
    name="try_a_skill",
    title="Let a person try an approved skill from its card",
    what=(
        "On the Skills page an approved skill has a Try it out control that opens a conversation "
        "on Ask with that skill offered to the agent the person chooses, for that conversation "
        "only. The run is the ordinary one, at the person's own reach narrowed by the agent's "
        "ceiling, metered like any other, and the skill is offered only if every tool it names is "
        "within that reach."
    ),
    while_off=(
        "Try it out is not offered, and a question that carries a skill to try is answered as an "
        "ordinary question."
    ),
    read_by=("brain.api_routes:trying_a_skill_is_on",),
)
