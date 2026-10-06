"""Which tools and connectors an agent carries once people attach and detach them on the install.

An agent's tools were its manifest's `allowed_tools`, sealed in its install. `brain.console.
agent_tabs` decided how attaching works (checked when it happens, by the person's own reach, a
refused attach and a thing they could never see refused alike, detach asking for nothing) and
wrote it over a `Composition` nothing stored. This module is the fold over stored presses and the
two decisions a press becomes. The person's half of the check is `agent_tabs.admitted`'s one line,
asked directly: a tool is not one of `Composition`'s pinned parts, and building an `Attachment` to
hand it would be a pinned version invented for a thing that has none.

**The agent's half of the check is its ceiling, and it is asked of the tool, not the person.** A
tool is attachable when the ceiling holds the capability it requires and its side effect is no
larger than the ceiling's largest, which is exactly what `brain.gate.catalogue.project` would keep
of it at run time; a tool the ceiling could never run is refused rather than attached and inert.
See `AN_ATTACH_IS_CHECKED_AGAINST_THE_CEILING_AND_THE_PERSON`.

**The newest press naming a tool decides it, and a tool nobody pressed on keeps its manifest's
word.** A tool the manifest requires cannot be detached, because an agent missing a required tool
is an agent every run of which fails.

**A connector is not a press kept here: it is the agent's own `connectors` column**, which
`brain.agents.binding.bound_capabilities` compiles into its ceiling and which nothing else reads to
decide connector access. Attaching one adds its name to that list and detaching removes it, so
there is one place an agent's connectors live and one intersection they reach a run through.
Rejected: a connector press as a row of `agent.tool_attachment`, which is what this module was
first written with, because it is a second store of the same fact and a second way for a run's
reach to be decided. See `A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`.

**A connector is attached only when the person attaching reaches what it would open.** What it
opens is read through `entitlement_ceiling` itself, the one function that applies
`bound_capabilities`: the declared capabilities the ceiling holds with the connector named and
does not hold without it. The person must hold every one, which is the tool check's person half
applied to a source. A connector that would open nothing is refused, because naming it changes
no run. This module is also the one place outside the model and the install that reads the list,
through `connectors_of`, because it is the one place that edits it;
`tests/unit/test_agent_binding.py` holds both to that.

**What a run carries is the fold, applied to the record before the ceiling is built.**
`brain.gate.roster.setup_of` builds a run's tool ceiling from the record's `allowed_tools`, so the
roster hands it the narrowed record and a detached tool is absent from every catalogue from the
next question on; the configuration hash moves with it, so no cached answer from before survives.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.agents.model import AgentRecord, entitlement_ceiling
from brain.console.agent_profile import at_most
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import ToolDefinition
from brain.tables.attachment import AttachmentPart

# ------------------------------------------------------------------ written-down reasons
AN_ATTACH_IS_CHECKED_AGAINST_THE_CEILING_AND_THE_PERSON: Final = (
    "A tool is attached only when the agent's ceiling holds the capability it requires and allows "
    "an effect that large, and the person attaching holds it too. The first stops a tool being "
    "attached that no run could call; the second stops a person handing an agent something they "
    "could not reach themselves."
)

A_PUBLISH_CHANGES_ONLY_THE_CONNECTORS_ITS_DRAFT_CHANGED: Final = (
    "An edit draft starts from the connectors the agent names now, and a publish applies the "
    "draft's own change to the list as it stands when it is published. A connector bound on the "
    "agent's page is therefore kept by a publish whose author never touched it, including one "
    "bound while the draft was open, and only a connector the author took out of the draft is "
    "unbound. Writing the draft's list over the agent's would unbind every page-bound connector "
    "on every publish, silently to the author, who never saw it go."
)

A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE: Final = (
    "A connector attached to an agent is a name in the agent's own connectors column, which "
    "bound_capabilities compiles into its ceiling. There is no second record of it: a press on "
    "a connector writes that column and nothing else, so one list decides which sources a run "
    "may reach, through the one intersection every ceiling goes through."
)

# ------------------------------------------------------------ what a refusal says
CANNOT_BE_ATTACHED: Final = (
    "That cannot be attached to this agent: it is outside what the agent may do, or outside what "
    "you may reach."
)
NOTHING_TO_ATTACH: Final = (
    "That connector cannot be attached to this agent: it would open nothing the agent may read, "
    "or something you may not reach."
)
A_REQUIRED_TOOL_STAYS: Final = "This agent cannot work without that tool, so it cannot be detached."
ALREADY_ATTACHED: Final = "That is already attached."
NOT_ATTACHED: Final = "That is not attached."


class AttachmentError(Exception):
    """A press that cannot be made. Its text is one of the sentences above."""


@dataclass(frozen=True)
class AttachmentChange:
    """One stored press: what it was on, which way, and the tools it moved."""

    agent_id: str
    part: AttachmentPart
    reference: str
    attached: bool
    tools: tuple[str, ...]
    at: datetime
    changed_by: str


def attached_tools(manifest: Iterable[str], changes: Sequence[AttachmentChange]) -> frozenset[str]:
    """The tools an agent carries: its manifest's, then every press in order, newest last."""
    carried = set(manifest)
    for one in sorted(changes, key=lambda change: change.at):
        if one.attached:
            carried.update(one.tools)
        else:
            carried.difference_update(one.tools)
    return frozenset(carried)


def narrowed(record: AgentRecord, changes: Sequence[AttachmentChange]) -> AgentRecord:
    """The record with the tools it carries now. The required ones always stay."""
    mine = [one for one in changes if one.agent_id == record.agent_id]
    if not mine:
        return record
    authority = record.authority
    carried = attached_tools(authority.allowed_tools, mine) | authority.required_tools
    # A copy of the authority with one field moved, so a field added to it later (the connectors
    # were, on 2026-10-06) is carried over rather than reset by a constructor that names fields.
    return record.model_copy(
        update={"authority": authority.model_copy(update={"allowed_tools": carried})}
    )


def within_ceiling(tool: ToolDefinition, record: AgentRecord) -> bool:
    """Whether a run of this agent could ever call this tool. See the reason above."""
    ceiling = entitlement_ceiling(record)
    return at_most(tool.side_effect, record.authority.max_side_effect) and ceiling.holds(
        Capability(value=tool.required_capability)
    )


def attachable(
    tool: ToolDefinition, record: AgentRecord, by: EntitlementSet, now: datetime
) -> bool:
    """Both halves of the check: the ceiling's, and the person's as `agent_tabs.admitted` asks."""
    if not within_ceiling(tool, record):
        return False
    return by.scope_for(Capability(value=tool.required_capability), now) is not None


def to_attach(
    reference: str,
    *,
    record: AgentRecord,
    carried: frozenset[str],
    registered: Sequence[ToolDefinition],
    by: EntitlementSet,
    now: datetime,
) -> tuple[str, ...]:
    """The tool an attach press moves, or a refusal in words that name nothing."""
    found = next((one for one in registered if one.name == reference), None)
    if found is None or not attachable(found, record, by, now):
        raise AttachmentError(CANNOT_BE_ATTACHED)
    if reference in carried:
        raise AttachmentError(ALREADY_ATTACHED)
    return (reference,)


def to_detach(reference: str, *, record: AgentRecord, carried: frozenset[str]) -> tuple[str, ...]:
    """The tool a detach press moves. Detaching asks nothing of the person, as `agent_tabs`
    argues; a required tool is refused."""
    if reference not in carried:
        raise AttachmentError(NOT_ATTACHED)
    if reference in record.authority.required_tools:
        raise AttachmentError(A_REQUIRED_TOOL_STAYS)
    return (reference,)


# ------------------------------------------------------------------------- connectors
def connectors_of(record: AgentRecord) -> tuple[str, ...]:
    """The connectors the agent names, which is the list a press edits and nothing decides from."""
    return record.authority.connectors


def with_connectors(record: AgentRecord, connectors: tuple[str, ...]) -> AgentRecord:
    """The record naming these connectors instead, every other field kept."""
    return record.model_copy(
        update={"authority": record.authority.model_copy(update={"connectors": connectors})}
    )


def opened_by(record: AgentRecord, connector: str) -> tuple[Capability, ...]:
    """The declared capabilities the agent's ceiling holds with this connector named and does not
    hold without it, read through `entitlement_ceiling` and nothing else. Empty for one it names
    already, and for a name no connector has, since naming either changes no ceiling. See
    `A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`."""
    named = connectors_of(record)
    before = entitlement_ceiling(record)
    after = entitlement_ceiling(with_connectors(record, (*named, connector)))
    return tuple(
        one for one in record.authority.capabilities if after.holds(one) and not before.holds(one)
    )


def connector_attachable(
    connector: str, record: AgentRecord, by: EntitlementSet, now: datetime
) -> bool:
    """Whether naming this connector opens something, all of which the person reaches."""
    opened = opened_by(record, connector)
    return bool(opened) and all(by.scope_for(one, now) is not None for one in opened)


def connectors_after_attach(
    connector: str, *, record: AgentRecord, by: EntitlementSet, now: datetime
) -> tuple[str, ...]:
    """The agent's connector list with this one added, or a refusal that names nothing.

    A name no connector has opens nothing, so it is refused in the sentence a connector the
    person may not reach gets, by the same check rather than a second list of names. See
    `A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`.
    """
    named = connectors_of(record)
    if connector in named:
        raise AttachmentError(ALREADY_ATTACHED)
    if not connector_attachable(connector, record, by, now):
        raise AttachmentError(NOTHING_TO_ATTACH)
    return (*named, connector)


def connectors_after_detach(connector: str, *, record: AgentRecord) -> tuple[str, ...]:
    """The agent's connector list with this one taken out. Asks nothing of the person."""
    named = connectors_of(record)
    if connector not in named:
        raise AttachmentError(NOT_ATTACHED)
    return tuple(one for one in named if one != connector)


def connectors_after_publish(
    current: Sequence[str], started: Sequence[str], drafted: Sequence[str]
) -> tuple[str, ...]:
    """The agent's connector list once an edit is published: the draft's own change, from the list
    it started with to the one it ends with, applied to the list as it stands now.

    So a publish takes away only what its author took out of the draft, and keeps a connector
    bound on the page before the draft started or while it was open. See
    `A_PUBLISH_CHANGES_ONLY_THE_CONNECTORS_ITS_DRAFT_CHANGED`.
    """
    removed = set(started) - set(drafted)
    kept = [one for one in current if one not in removed]
    added = [one for one in drafted if one not in started and one not in kept]
    return (*kept, *added)
