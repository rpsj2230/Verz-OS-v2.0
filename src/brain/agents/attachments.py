"""Which tools an agent carries once people have attached and detached them on the install.

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
word.** A connector press moves every tool of that source it names, so a connector attached and one
of its tools then detached leaves that tool detached. A tool the manifest requires cannot be
detached, because an agent missing a required tool is an agent every run of which fails.

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

from brain.agents.model import AgentAuthority, AgentRecord, entitlement_ceiling
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

# ------------------------------------------------------------ what a refusal says
CANNOT_BE_ATTACHED: Final = (
    "That cannot be attached to this agent: it is outside what the agent may do, or outside what "
    "you may reach."
)
NOTHING_TO_ATTACH: Final = "Nothing of that connector can be attached to this agent."
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
    return record.model_copy(
        update={
            "authority": AgentAuthority(
                scope=authority.scope,
                capabilities=authority.capabilities,
                allowed_tools=carried,
                required_tools=authority.required_tools,
                max_side_effect=authority.max_side_effect,
            )
        }
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
    part: AttachmentPart,
    reference: str,
    *,
    record: AgentRecord,
    carried: frozenset[str],
    registered: Sequence[ToolDefinition],
    by: EntitlementSet,
    now: datetime,
) -> tuple[str, ...]:
    """The tools an attach press moves, or a refusal in words that name nothing."""
    if part is AttachmentPart.TOOL:
        found = next((one for one in registered if one.name == reference), None)
        if found is None or not attachable(found, record, by, now):
            raise AttachmentError(CANNOT_BE_ATTACHED)
        if reference in carried:
            raise AttachmentError(ALREADY_ATTACHED)
        return (reference,)
    moving = tuple(
        sorted(
            one.name
            for one in registered
            if one.source == reference
            and one.name not in carried
            and attachable(one, record, by, now)
        )
    )
    if not moving:
        raise AttachmentError(NOTHING_TO_ATTACH)
    return moving


def to_detach(
    part: AttachmentPart,
    reference: str,
    *,
    record: AgentRecord,
    carried: frozenset[str],
    registered: Sequence[ToolDefinition],
) -> tuple[str, ...]:
    """The tools a detach press moves. Detaching asks nothing of the person, as `agent_tabs`
    argues; a required tool is refused."""
    names: tuple[str, ...]
    if part is AttachmentPart.TOOL:
        names = (reference,) if reference in carried else ()
    else:
        names = tuple(
            sorted(
                one.name for one in registered if one.source == reference and one.name in carried
            )
        )
    if not names:
        raise AttachmentError(NOT_ATTACHED)
    if set(names) & record.authority.required_tools:
        raise AttachmentError(A_REQUIRED_TOOL_STAYS)
    return names
