"""Letting what an agent learns change the instructions it is given (M16.7.1).

Off because it is a new way for an agent's configuration to change: until it is on, learning
proposes and people decide exactly as they do now, and nothing the agent learns is written into what
the agent is. `brain.learned_instruction_store` is the one writer, and it refuses while this is off.
Giving back what was learned is never behind this switch, for the reason
`brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED` gives: a switch turned off
must not leave a person unable to undo what it let in.

Task ids: M16.7.1
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

AGENT_LEARNED_CHANGES: Final = Feature(
    name="agent_learned_changes",
    title="Let what an agent learns change its instructions",
    what=(
        "A change to an agent's instructions that its own learning proposed, and that a named "
        "person approved, is written into the agent and marked as the agent's own learning, so it "
        "can be listed and given back apart from anything an administrator set. A change never "
        "replaces instructions somebody set on that agent."
    ),
    while_off=(
        "Nothing the agent learns is written into its instructions. Instructions an earlier "
        "approval wrote are still marked as learned and can still be listed and given back."
    ),
    read_by=(
        "brain.learned_instruction_store:apply_learned_instructions",
        "brain.learned_instruction_store:learning_may_change_instructions",
    ),
)
