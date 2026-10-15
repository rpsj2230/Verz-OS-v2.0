"""The switch on showing personal agents to readers who hold the audit capability, for oversight.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until the owner has seen it on his install: it is a new list that tells a reader something they
were not told before, namely that another person's personal agent exists. It tells them that and
nothing it holds, and it offers them nothing to do with it
(`brain.agents.oversight.OVERSIGHT_OFFERS_THE_AGENT_TO_NOBODY`).

Task ids: M39.10.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

PERSONAL_AGENT_OVERSIGHT: Final = Feature(
    name="personal_agent_oversight",
    title="Show personal agents to people who hold the audit capability, for oversight",
    what=(
        "A person who holds the audit capability for agents is shown, on the Agents screen, which "
        "personal agents exist inside that capability: the agent's name, whose it is and "
        "whether it is running. They cannot open it, ask it or see what its owner connected to it."
    ),
    while_off=(
        "Nobody is shown another person's personal agent, as before. Each person still finds and "
        "uses their own, and the audit ledger still records every change to it."
    ),
    read_by=("brain.agent_oversight_routes:oversight_is_on",),
)
