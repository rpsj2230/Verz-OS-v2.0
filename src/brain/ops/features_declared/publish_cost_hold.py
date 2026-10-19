"""Holding a publish whose run costs more than its department allows for a second person (M20.5.2).

Off because it changes who must agree before an agent is published, and it needs a department to
have set a per-run ceiling to mean anything: with the switch off a publish goes exactly as it did,
and the publish record still shows what one run of each version costs. The comparison, and why the
figure is a priced run and not a measured one, are in `brain.builder.run_cost`.

Task ids: M20.5.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

PUBLISH_COST_HOLD: Final = Feature(
    name="publish_cost_hold",
    title="Hold an agent that costs more than its department allows",
    what=(
        "Publishing an agent to a department whose per-run ceiling is below what one run of the "
        "agent costs waits for that department's administrator, who is somebody other than the "
        "author. The agent publishes the moment they agree. A department with no per-run ceiling "
        "holds nothing."
    ),
    while_off=(
        "Publishing is not held for its cost. The publish record still shows what one run of each "
        "version costs, and a publish already waiting for its cost can still be approved."
    ),
    read_by=("brain.agent_builder_routes:cost_hold_is_on",),
)
