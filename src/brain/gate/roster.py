"""The agents `/answer` may select for one person, and the reach a selected agent answers at.

`brain.gate.select.select_agent` has decided by name since it was written, and `/answer` handed it
one agent, the person asking through every registered tool, so a name typed in the picker could
only ever select that one. This module is the roster read on that route: the stored agents the
person may use, each turned into the `AgentSetup` the front half keys the cache and projects the
catalogue from, beside the default agent that is always there.

**Which agents is `brain.agents.model.runnable_agent_ids`' answer and nobody else's.** Visible to
this person and enabled, the same set the home page lists as callable. An agent they may not use
is simply not in the roster, so `select_agent` receives its name and finds nothing, which is the
path a name that never existed takes: DENIED and ABSENT are one selection by construction, and
nothing here writes a second check that could disagree.

**A selected agent answers at `E(caller) ∩ agent_ceiling` and never at the caller's reach.**
`run_entitlement` hands back `brain.console.workspace_capabilities.run_reach`, which calls the one
intersection the platform has; there is no arithmetic here, and the default agent, which is the
person asking, answers at their own reach. The cache is still keyed on the caller's reach hash:
the agent's configuration hash is in the same key, and the two together fix the run reach.

**An agent's configuration hash covers the whole record and the registry it runs over.** Any
change to its authority, tier, model pin or persona, or to the tools this process registered,
is a different key, so an answer cached through yesterday's agent is not served through today's.
Hashing only the ceiling was rejected: a changed persona is a different answer to the same words.

What is not here, stated: a selected agent runs with no skill pins on this route, because the
install rows the pins live on are not read yet; `brain.gate.model_lane.AgentRun` takes them.

Task ids: M3.9.8
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import JsonValue

from brain.agents.model import AgentRecord, AgentViewer, runnable_agent_ids, tool_ceiling
from brain.agents.template import config_hash
from brain.console.workspace_capabilities import run_reach
from brain.core.entitlement import EntitlementSet
from brain.core.principal import Principal
from brain.gate.front import AgentSetup

#: How `brain.app.lifespan` hands the route the stored agents: one read per question, so an agent
#: disabled a moment ago is not selectable on the next request.
AgentRoster = Callable[[], Awaitable[Sequence[AgentRecord]]]


def viewer_for(principal: Principal) -> AgentViewer:
    """The person, as an audience question is asked about them: their primary department.

    `brain.agent_routes.viewer_of` delegates here, so the roster a person is shown and the roster
    `/answer` selects from are decided about the same viewer.
    """
    department = principal.primary_department
    return AgentViewer(
        principal_id=principal.id,
        departments=frozenset({department}) if department else frozenset(),
    )


def setup_of(record: AgentRecord, tool_names: Iterable[str]) -> AgentSetup:
    """The front half's view of one stored agent: its tool ceiling, its hash and its tier."""
    # A cast at pydantic's boundary: `model_dump(mode="json")` returns JSON values typed as Any.
    document = cast(
        dict[str, JsonValue],
        {"record": record.model_dump(mode="json"), "registry": sorted(set(tool_names))},
    )
    return AgentSetup(
        ceiling=tool_ceiling(record), config_hash=config_hash(document), tier=record.tier
    )


@dataclass(frozen=True)
class AnswerRoster:
    """Every agent this person may be answered by on this request, and the records behind them.

    `records` holds the stored agents only; the default agent has no record because it is the
    person asking. `visible` is what `select_agent` is handed.
    """

    agents: Mapping[str, AgentSetup]
    records: Mapping[str, AgentRecord]

    @property
    def visible(self) -> frozenset[str]:
        return frozenset(self.agents)


def answer_roster(
    records: Iterable[AgentRecord],
    viewer: AgentViewer,
    *,
    default: Mapping[str, AgentSetup],
    tool_names: Iterable[str],
) -> AnswerRoster:
    """The default agent plus every stored agent this viewer may run.

    A stored agent whose id is the default's replaces it. The replacement can only narrow, since a
    stored agent answers at the caller's reach intersected with its ceiling.
    """
    kept = list(records)
    runnable = runnable_agent_ids(kept, viewer)
    usable = {one.agent_id: one for one in kept if one.agent_id in runnable}
    names = tuple(tool_names)
    agents = {**default, **{agent_id: setup_of(one, names) for agent_id, one in usable.items()}}
    return AnswerRoster(agents=agents, records=usable)


def run_entitlement(caller: EntitlementSet, record: AgentRecord | None) -> EntitlementSet:
    """The reach an answer is computed at: the caller's, narrowed by the agent when one runs."""
    return caller if record is None else run_reach(caller, record)
