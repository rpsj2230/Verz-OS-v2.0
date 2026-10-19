"""What an agent's Profile says about skills and computer use, said only where it is true.

Three sentences on the Profile used to be typed in the page: that an assigned skill "changes no
answer today", that learning has "no single switch", and that computer use is "not offered".
Each was true on the day it was written and each describes something the code decides, so each
had already drifted or would. `brain.gate.model_lane.skills_offered` has read a pinned skill
since M27.12.1, which made the first sentence false; the learning pause had a route and no
button; and "not offered" was a constant of the page rather than a fact about the install. This
module says each of them from the thing that decides it, and `brain.agent_capability_routes`
sends the answer, so the page holds no sentence that can go on being right for the wrong reason.

**A skill is said to change a run only where the run path would offer it.** `skills_offered`
offers a pinned skill when it is in the library, approved, unmoved since it was approved, and
every tool it names is inside the run's reach. The reach is the caller's narrowed by the agent,
which is per person and per request, so a Profile cannot decide the last clause. What it can
decide is the upper bound the agent itself sets: a skill naming a tool the ceiling does not
allow is never offered to anybody, and one that is not approved or not in the library is never
offered either. `skill_standing` returns the first of those that applies as a sentence, and None
for a skill nothing about the agent stops, which the page does not describe as certain to run.
It reads `brain.console.agent_tabs.Review` for the approval half and `brain.console.
agent_profile.ToolRow.within_ceiling` for the tools, which is `brain.gate.catalogue.project`'s own
comparison, so this is neither a second reading of approval nor of the ceiling. See
`A_SKILL_IS_SAID_NOT_TO_CHANGE_A_RUN_ONLY_WHERE_NO_RUN_COULD_OFFER_IT`. Rejected: running
`skills_offered` for the reader, which would put the reader's own reach into a sentence about the
agent and tell two readers different things about one assignment.

**Computer use is offered when an isolated desktop runner is part of the product, and not before.**
The product has a browser runner (`brain.browsing`), which drives a sealed browser from a
declared envelope, and nothing that controls a desktop's screen, keyboard and mouse. Letting an
agent act on a desktop is a larger step than browsing: the policy that makes browsing survivable
(a declared origin, a sealed sandbox, a credential the model never reads) has no counterpart for
a whole desktop. So `isolated_desktop_runner_exists` asks whether the runner's module is in the
product, by import machinery and not by a constant, and the Profile offers nothing until it is,
saying in a sentence that it is not offered. The day somebody adds the module the answer changes
and a test of the page's refusal fails, which is the prompt to build the per-agent switch beside
it. See `COMPUTER_USE_IS_NOT_OFFERED_UNTIL_AN_ISOLATED_DESKTOP_RUNNER_EXISTS`. Rejected: a
disabled switch with an apology, which teaches a person there is a switch to find.

**Nothing here is a count of anything, and nothing here reads a person.** The figures are
sentences about one agent's own configuration, so none can be a count of what a reader was not
shown.

Scope: domain logic. Nothing here opens a connection or reads a clock.

Task ids: M27.11.12, M27.15.32
"""

from __future__ import annotations

import importlib.util
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from brain.agents.model import AgentAuthority
from brain.console.agent_profile import tool_rows
from brain.console.agent_tabs import Review
from brain.core.envelope import ToolDefinition

# ------------------------------------------------------------------ written-down reasons

#: Why a sentence says a skill does not change a run, and when it says nothing.
A_SKILL_IS_SAID_NOT_TO_CHANGE_A_RUN_ONLY_WHERE_NO_RUN_COULD_OFFER_IT: Final = (
    "A run offers a pinned skill that is in the library, approved, unmoved and whose every tool "
    "is inside the run's reach. The last clause is per person, so the Profile says a skill does "
    "not change a run only where the agent itself stops every run: it is not in the library, a "
    "person has not approved the text that is there, or it names a tool the agent's ceiling "
    "does not let it call. For any other skill it says nothing, and never that it will run."
)

#: Why the Profile offers no computer use until a runner is part of the product.
COMPUTER_USE_IS_NOT_OFFERED_UNTIL_AN_ISOLATED_DESKTOP_RUNNER_EXISTS: Final = (
    "Acting on a desktop is a larger step than browsing. The refusals that make browsing "
    "survivable (a declared origin, a sealed sandbox, a credential the model never reads) have "
    "no counterpart for a whole screen, keyboard and mouse. So the Profile offers computer use "
    "only once an isolated desktop runner is part of the product, and says in a sentence that it "
    "is not offered until then, rather than showing a switch that does nothing."
)

# --------------------------------------------------------------------------- the skills

#: What each reason a skill is not read by a run is, as a sentence about this agent.
NOT_IN_THE_LIBRARY: Final = (
    "This skill is not in the skill library, so no run uses it. Add it to the library, then "
    "assign it again."
)
WAITING_FOR_REVIEW: Final = "A person has not reviewed this skill yet, so no run uses it."
REJECTED_IN_REVIEW: Final = "A person rejected this skill in review, so no run uses it."
CHANGED_AFTER_APPROVAL: Final = (
    "This skill's text changed after it was approved, so no run uses it until a person reads it "
    "again."
)
NAMES_A_TOOL_THE_AGENT_MAY_NOT_CALL: Final = (
    "This skill names a tool this agent may not call, so no run uses it. The agent's permissions "
    "decide which tools it may call."
)

#: What each review state says when the skill is stopped by its review.
_BY_REVIEW: Final[dict[Review, str]] = {
    Review.PENDING: WAITING_FOR_REVIEW,
    Review.REJECTED: REJECTED_IN_REVIEW,
    Review.CHANGED: CHANGED_AFTER_APPROVAL,
}


@dataclass(frozen=True)
class SkillStanding:
    """Whether anything about the agent stops every run from using one assigned skill.

    `because` is the sentence when something does, and None when nothing about the agent does:
    that is not a claim that a run will use it, which is also decided by the person asking.
    """

    because: str | None

    @property
    def stopped(self) -> bool:
        """Whether no run of this agent could use the skill."""
        return self.because is not None


def usable_tools(authority: AgentAuthority, registered: Iterable[ToolDefinition]) -> frozenset[str]:
    """Every tool a run of this agent could call: the ceiling's own comparison over a registry.

    `brain.console.agent_profile.tool_rows` decides it, and it is `brain.gate.catalogue.project`'s
    comparison, held to it by that module's own test, so a tool the registry does not hold and one
    above the largest side effect are both absent here as they are from a run's catalogue.
    """
    return frozenset(one.name for one in tool_rows(authority, registered) if one.within_ceiling)


def skill_standing(
    *, review: Review | None, tools: Sequence[str], usable: Collection[str]
) -> SkillStanding:
    """The first thing that stops every run from using this skill, or nothing.

    `review` is None for a pinned skill the library holds no row for, which `skills_offered`
    never offers. `usable` is every tool the agent's ceiling lets a run call, so a skill
    naming one outside it is stopped for everybody. See
    `A_SKILL_IS_SAID_NOT_TO_CHANGE_A_RUN_ONLY_WHERE_NO_RUN_COULD_OFFER_IT`.
    """
    if review is None:
        return SkillStanding(NOT_IN_THE_LIBRARY)
    if review is not Review.APPROVED:
        return SkillStanding(_BY_REVIEW[review])
    if not set(tools) <= set(usable):
        return SkillStanding(NAMES_A_TOOL_THE_AGENT_MAY_NOT_CALL)
    return SkillStanding(None)


# ------------------------------------------------------------------------ computer use

#: The module an isolated desktop runner would be. It is not in the product, and the answer to
#: whether it is comes from asking the import machinery, never from this constant's say-so.
DESKTOP_RUNNER_MODULE: Final = "brain.browsing.desktop"

#: What the Profile says about computer use while no runner exists.
COMPUTER_USE_NOT_OFFERED: Final = (
    "Not offered. This product has no isolated desktop runner, so an agent cannot control a "
    "computer's screen, keyboard or mouse, and there is no switch for it. It is offered here "
    "only once one exists. Until then an agent acts only through actions the product checks first."
)

#: What the Profile says once a runner is part of the product and a per-agent switch is not.
COMPUTER_USE_RUNNER_PRESENT: Final = (
    "An isolated desktop runner is part of this product. Offering it to one agent is not built "
    "yet, so no agent can use it."
)


def isolated_desktop_runner_exists(module: str = DESKTOP_RUNNER_MODULE) -> bool:
    """Whether the isolated desktop runner's module is part of the product.

    `importlib.util.find_spec` finds a module without running it. A module whose parent package
    is missing raises, which is the same answer as a module that is absent.
    """
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


@dataclass(frozen=True)
class ComputerUse:
    """Whether the Profile offers computer use, and the sentence it says either way.

    `offered` is False until a runner exists and stays False after it does until a per-agent
    switch is built, so a page cannot draw a switch for something that has nowhere to write.
    """

    offered: bool
    sentence: str


def computer_use(*, runner_exists: bool | None = None) -> ComputerUse:
    """What the Profile says about computer use, from whether a runner is part of the product."""
    exists = isolated_desktop_runner_exists() if runner_exists is None else runner_exists
    return ComputerUse(
        offered=False, sentence=COMPUTER_USE_RUNNER_PRESENT if exists else COMPUTER_USE_NOT_OFFERED
    )
