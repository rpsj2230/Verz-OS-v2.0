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

**An agent's configuration hash covers the whole record, the registry it runs over and the
install's own stored hash.** Any change to its authority, tier, model pin or persona, or to the
tools this process registered, is a different key, so an answer cached through yesterday's agent
is not served through today's. Hashing only the ceiling was rejected: a changed persona is a
different answer to the same words.

**The install's stored `effective_hash` is part of that key (M13.2.5).** The record holds the
ceiling, the persona and the connectors, but not the leash, which is a sealed path of the
manifest, and not the skills the agent is pinned to. Both are in the effective document the
install materialises, and every write that changes an install (a skill assigned, a prompt edited,
a draft published, an upgrade accepted) stores the new `effective_hash` with it. Until
2026-10-06 `setup_of` hashed the record alone, so a changed leash or an assigned skill left the
key where it was and the old answer was served through the new agent. The stored hash is read in
the same statement as the agent, so the record and the hash a question is keyed on are one
reading. Re-hashing the document here was rejected: it is a second implementation of
`materialise`, and the stored value is the one the builder and the Skills screen already compare
against. The record is still hashed beside it, because a channel, an audience or a disabled
agent moves the roster without moving the install.

**An agent not enabled on the request's channel is not in the roster either** (M13.7.4), for the
same reason and by the same construction: it is filtered out before `runnable_agent_ids` is
asked, so naming it on a channel it is not switched on for finds what a name nobody created finds,
and the person is answered by the default in the same words. Refusing it after selection was
rejected, because a refusal is a second path, and a second path is a second set of words that says
the agent exists. The home page's list (`brain.member_activity`) is deliberately not narrowed by
channel: it is the audience's answer, which this change does not move.

What is not here, stated: a selected agent runs with no skill pins on this route, because the
install rows the pins live on are not read yet; `brain.gate.model_lane.AgentRun` takes them.

Task ids: M3.9.8, M13.7.4, M13.2.5
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from pydantic import JsonValue

from brain.agents.model import AgentRecord, AgentViewer, runnable_agent_ids, tool_ceiling
from brain.agents.template import config_hash
from brain.console.workspace_capabilities import run_reach
from brain.core.entitlement import EntitlementSet
from brain.core.principal import Principal
from brain.gate.context import Channel
from brain.gate.front import AgentSetup


@dataclass(frozen=True)
class StoredAgents:
    """The stored agents one question reads, and the install hash each one was read with.

    `install_hashes` is keyed by agent id and holds only the agents that have an install row, so
    an agent with none is hashed on its record alone. It is read in the statement that reads the
    agent, never in a second one: two reads a moment apart could key an answer computed under
    one configuration on the hash of another.
    """

    records: Sequence[AgentRecord]
    install_hashes: Mapping[str, str] = field(default_factory=dict)


#: How `brain.app.lifespan` hands the route the stored agents: one read per question, so an agent
#: disabled a moment ago is not selectable on the next request.
AgentRoster = Callable[[], Awaitable[StoredAgents]]


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


def setup_of(
    record: AgentRecord, tool_names: Iterable[str], install_hash: str | None = None
) -> AgentSetup:
    """The front half's view of one stored agent: its tool ceiling, its hash and its tier.

    `install_hash` is the install's stored `effective_hash`, or None for an agent with no install
    row. It is a separate key in the hashed document rather than being folded into the record, so
    an agent that has none and one whose install hashes to the empty string cannot collide.
    """
    # A cast at pydantic's boundary: `model_dump(mode="json")` returns JSON values typed as Any.
    document = cast(
        dict[str, JsonValue],
        {
            "record": record.model_dump(mode="json"),
            "registry": sorted(set(tool_names)),
            "install": install_hash,
        },
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
    channel: Channel,
    default: Mapping[str, AgentSetup],
    tool_names: Iterable[str],
    install_hashes: Mapping[str, str] | None = None,
) -> AnswerRoster:
    """The default agent plus every stored agent this viewer may run on this channel.

    A stored agent whose id is the default's replaces it. The replacement can only narrow, since a
    stored agent answers at the caller's reach intersected with its ceiling.

    `channel` has no default: a caller that does not know which channel it is answering on cannot
    say which agents answer there. See `AN_AGENT_ANSWERS_ONLY_ON_THE_CHANNELS_ENABLED_FOR_IT`.
    """
    kept = [one for one in records if channel.value in one.channels]
    runnable = runnable_agent_ids(kept, viewer)
    usable = {one.agent_id: one for one in kept if one.agent_id in runnable}
    names = tuple(tool_names)
    hashes = install_hashes or {}
    stored = {
        agent_id: setup_of(one, names, hashes.get(agent_id)) for agent_id, one in usable.items()
    }
    agents = {**default, **stored}
    return AnswerRoster(agents=agents, records=usable)


def run_entitlement(caller: EntitlementSet, record: AgentRecord | None) -> EntitlementSet:
    """The reach an answer is computed at: the caller's, narrowed by the agent when one runs."""
    return caller if record is None else run_reach(caller, record)
