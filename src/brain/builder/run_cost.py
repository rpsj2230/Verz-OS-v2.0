"""What one run of a draft would cost, and when that is more than its department allows (M20.5.2).

M20.5.2 asks that publishing an agent whose median rehearsed run costs more than its department's
per-run ceiling be held until the department admin approves it, and that the publish record show
the cost. This is the two numbers and the comparison, and nothing that reads a table or a clock.

**The cost is priced by the estimator a real run is admitted by, and it is an estimate, said so.**
`brain.ops.spend.estimate` prices a request from its lane, tier, tool calls and retrieval, and a
real run's pre-flight uses it, so a figure from anywhere else would be a second cost model that
disagreed with the pre-flight by whatever its author chose
(`brain.builder.rehearse.A_COST_THE_REHEARSAL_INVENTS_IS_A_SECOND_COST_MODEL`). The one input a
form cannot know is the number of tool calls, which a rehearsal measures, and **no rehearsal on
this install runs a model yet** (`brain.agent_builder_routes.A_REHEARSAL_RUNS_NO_MODEL_YET`), so
there is nothing measured to take it from. The run priced here is the largest one the agent's own
manifest allows: a question answered at the agent's tier that calls every tool it may call once. It
is a function of the manifest alone, which is what lets the publish record show the same figure for
a version years later with nothing stored beside it, and it is an upper bound and not a median,
because the questions a rehearsal would ask all price alike until a run can tell them apart. The
day a rehearsal measures tool calls, `rehearsed_run_cost` takes them as an argument and the median
is of those; nothing about the hold changes. See `A_PRICED_RUN_IS_NOT_A_MEASURED_ONE`.

**The ceiling is the department's per-run budget, and none set is no hold.** A department's
`BudgetPeriod.RUN` row (`brain.ops.budgets`) is the ceiling, read in force at the instant of the
publish, in the same minor units the estimate is in. A department with no such row has said
nothing about a run's cost, so there is nothing to exceed and nothing is held; inventing a default
ceiling would hold every publish on an install nobody had configured, which is a gate people learn
to wave through. At or below the ceiling is not held: the ceiling is a limit, and a cost equal to
it is within it.

**Held means a second person, the one the rest of the publish gate already asks for.** A held
publish waits as a widening does: the author cannot approve it, and the person who can is
somebody holding the install authority over the agent's department row, which is the department's
administrator. See `brain.agent_builder_routes`. It is not a refusal and it is not a block: the
agent publishes the moment the right person agrees, so what the hold buys is a pair of eyes on a
cost, not a veto.

Task ids: M20.5.2
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from brain.agents.template import TemplateManifest
from brain.core.lane import Lane
from brain.models.routing import Tier
from brain.ops.spend import NO_CORRECTION, CostInputs, Estimate, SpendError, estimate

#: Why the figure is a priced run and not a measured one.
A_PRICED_RUN_IS_NOT_A_MEASURED_ONE: Final = (
    "A rehearsal on this install runs no model, so no run has yet told the estimator how many tool "
    "calls a question needs. The cost shown is the estimator's for a question answered at the "
    "agent's tier that calls every tool the agent may call once: an upper bound that is a function "
    "of the agent's manifest alone, so the same figure can be read back from a published version. "
    "It is called a cost of a rehearsed run because that is what the gate compares and what the "
    "record shows, and it is called an estimate everywhere a person reads it."
)

#: The lane a published agent's question is priced under: somebody is waiting for the answer.
RUN_LANE: Final = Lane.ANSWER

#: What a person is told when their publish is held for its cost. Names the department's own
#: ceiling and the agent's own cost, and nothing about any other department.
HELD_FOR_ITS_COST: Final = (
    "This agent costs more per run than your department allows, so a department administrator "
    "has to agree before it is published. Nothing is lost: it publishes as soon as they do."
)


@dataclass(frozen=True)
class CostHold:
    """A publish that costs more per run than its department allows, with both figures."""

    department: str
    cost_minor: int
    ceiling_minor: int


def run_cost(tier: Tier, tools_allowed: int) -> Estimate:
    """What one run at this tier calling this many tools would cost, priced as a real run is.

    See the module docstring. An agent that allows no tool is priced as a question answered with
    none.
    """
    return estimate(
        CostInputs(lane=RUN_LANE, tier=tier, tool_calls=tools_allowed), correction=NO_CORRECTION
    )


def rehearsed_run_cost(manifest: TemplateManifest) -> Estimate:
    """The cost of the largest run a manifest allows, from its tier and the tools it names.

    The manifest and not the settled record, because the record's tools are the install's bound
    names and the same manifest binds to a different number on a different install, while the
    publish record reads this figure back from the stored version alone. See
    `A_PRICED_RUN_IS_NOT_A_MEASURED_ONE`.
    """
    return run_cost(manifest.tier, len(manifest.authority.allowed_tools))


def cost_of_document(document: Mapping[str, object]) -> int | None:
    """The cost in minor units a stored version's flat document prices at, or None when it names no
    tier this install can price.

    What the publish record reads back, so a publish made before anybody asked shows the same
    figure the gate would have compared. None rather than nought for a document that does not
    parse: nought is a cost.
    """
    tier = document.get("tier")
    tools = document.get("authority.allowed_tools")
    if not isinstance(tier, str) or not isinstance(tools, list):
        return None
    try:
        return run_cost(Tier(tier), len(tools)).minor
    except (ValueError, SpendError):
        return None


def cost_hold(
    manifest: TemplateManifest, *, department: str | None, ceiling_minor: int | None
) -> CostHold | None:
    """The hold this publish is under, or None when it is not.

    None for an agent that belongs to no department, because a per-run ceiling is a department's,
    and for a department that has set none. Otherwise the estimate against the ceiling, strictly
    greater held.
    """
    if not department or ceiling_minor is None:
        return None
    cost = rehearsed_run_cost(manifest).minor
    if cost <= ceiling_minor:
        return None
    return CostHold(department=department, cost_minor=cost, ceiling_minor=ceiling_minor)
