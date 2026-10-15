"""Starting a new agent's draft from a description in the person's own words (M20.5.3).

Off because it makes one model call on a person's behalf at the moment they start a draft, sending
what they wrote to the model provider this install uses, and it starts a draft they did not ask to
start by name. With it off the draft is started the way it always was and the co-author is asked
for changes from the Write step, which is where the same call can still be made.

Task ids: M20.5.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

DESCRIBE_AN_AGENT: Final = Feature(
    name="describe_an_agent",
    title="Start an agent's draft from a description",
    what=(
        "A person who may build agents can describe the agent they want in their own words. The "
        "product starts a draft of their own, asks the model for the agent's name, instructions, "
        "skills and connectors, and shows each suggestion beside what the draft holds now. Nothing "
        "is written into the draft until they take the suggestions they choose, and the draft is "
        "then checked, rehearsed and published like any other. What the agent may reach is never "
        "suggested."
    ),
    while_off=(
        "An agent's draft is started from scratch or from a template, and the co-author is asked "
        "for changes from the Write step. Nothing is sent to a model provider when a draft is "
        "started."
    ),
    read_by=("brain.builder.describe_switch:describe_is_on",),
)
