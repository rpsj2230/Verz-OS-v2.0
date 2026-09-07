"""Inside one agent: what it may reach, what you may reach through it, and what it remembers.

Four surfaces that share one failure. Every one of them puts a fact about *the agent* next to
a fact about *this reader* on the same screen, and every one of them is a heading away from
saying the wrong one.

**Two questions, and the whole group exists because they get collapsed.**

- *What can this agent do at all?* That is `agent_ceiling`, a property of the agent, the same
  for every person who opens the page.
- *What can it do for me?* That is `E_run(caller, agent) = E(caller) intersect agent_ceiling`,
  a property of the pair, different for every reader.

Collapsing them costs trust rather than data, in both directions. A reader who sees the
ceiling and reads it as their own reach believes the agent will do something it will refuse.
A reader who sees only their own reach and reads it as the ceiling believes the agent cannot
do a thing it does for their colleague every day. So the two are **different types with
different constructors and fixed headings**, and neither carries a field the other's value
could be written into. `AvailabilityBlock` has nowhere to put a capability; `CeilingBlock`
takes no entitlement it could narrow by; `RunPreview` cannot be built without a real
`Invocation`. `reach_view_gaps` reads the signatures rather than trusting the bodies.

**Does showing a caller the ceiling breach DENIED-equals-ABSENT? Yes, filtered; no, whole.**

The honest answer is that it depends on who is reading, and the surface therefore shows one of
exactly two things and never a third.

Shown to a reader who does not hold the grant over the capability vocabulary, a ceiling list
is the rule broken in the permission vocabulary rather than the data vocabulary. `CLAUDE.md`'s
worked example is a retrieval answer that discloses which products exist; a ceiling naming
`read:client.contract_value` discloses that contract values exist and that somebody reaches
them. Same disclosure, different noun.

Shown to a reader who *does* hold it, it breaches nothing, and the reason is that the grant is
itself the decision. `brain.console.screens` already registers a Capabilities screen requiring
`read:capability`, described as everything that can be granted at all. A ceiling is a subset of
that vocabulary, so it needs no new grant and no new argument: somebody already decided this
reader may learn what exists. `CEILING_DISCLOSURE` is that capability, written out here and
pinned against the screen by test rather than read off it, so that repointing it fails.

**What is not available is the tempting middle.** Showing the reader the part of the ceiling
they themselves hold is `E_run` wearing the ceiling's heading, which is the collapse this group
exists to prevent, and it is worse than either honest option because nothing on the screen says
it happened. The ceiling is disclosed whole or replaced by `brain.core.redaction.render_lock`,
never narrowed. See `A_CEILING_FILTERED_TO_THE_READER_IS_THE_COLLAPSE_WEARING_A_CEILING_LABEL`.

The withheld rendering carries no count, no "and others" and no message of this module's own.
A count is the subtraction rule broken directly, and a lock that varied by reader or by reason
would be a side channel two people could read by comparing screens, which is why `render_lock`
takes no arguments and is reused here rather than restated.

**The preview is the real gate or it is nothing.** A worked preview that estimated what a
person's run would return would be a second implementation of projection, consulted by the one
audience that cannot check it: an administrator deciding whether somebody has enough access.
`run_preview` therefore calls `brain.gate.invoke.invoke`, whose `ProjectedCatalogue` cannot be
constructed outside `brain.gate.catalogue.project`, so a `RunPreview` holding an `Invocation`
is proof the projection ran rather than a promise that it did. There is no parameter here a
tool list could arrive through and `reach_view_gaps` says so.

Previewing somebody else's run is reading their grants, so it needs the grant that reading
grants needs. `PREVIEW_DISCLOSURE` is the People screen's own capability, for the same reason
the ceiling's is the Capabilities screen's: one vocabulary, not a private one for this module.

**The leash matrix is per operation, and every cell is looked up rather than inherited.**
`brain.gate.leash.Leash` has no per-agent default, deliberately, and a matrix that filled an
unconfigured cell from its neighbour would put that default back at the rendering layer, where
it would look like the table working. Every cell calls `rung_for` on its own composed target,
so an agent autonomous on `client.read` is still SHADOW on `client.write`.

Rejected: a rung per target rather than per operation. It is one column instead of three and it
is what the leash table looks like at a glance, and it makes reading a record and writing to it
one decision, which is the distinction `SideEffect` exists to keep.

**Raising a rung is a gated change and evidence never decides it.** `brain.memory.tiers` puts
`Change.LEASH_INCREASE` at `Tier.GATED` and `may_promote` refuses to promote anything gated by
agreement, so this module does not get to invent a promotion rule that agreement satisfies:
`may_raise` reads that classification rather than restating it, and the approver is a person
named on the evidence rather than a verdict this function reaches. Lowering needs no evidence
at all, which is the asymmetry a fail-safe direction has to have.

**A memory viewer is a disclosure surface and its text is the disclosure.** `Learning` and
`MemoryItem` carry no statement on purpose: a learning record holding what was said would be a
second transcript under the record's permissions rather than the conversation's. The statement
lives in `mem.persistent` and `mem.adaptive` under the capability tags it was formed with, and
those tags *are* its permission. So `readable` computes `may_recall` itself and pairs the text
with the `Recollection` that admitted it. It does not accept a recollection, because a
signature taking one is a signature that can be handed a verdict somebody else reached, which
is the argument `brain.memory.review.agent_memory` makes about computing its own intersection.

A revision diff renders both sides, so it is shown only when the reader passed `may_recall` on
both, and a reader who may see the newer revision and not the older is told nothing about the
older at all. That is the sharpest edge on this surface: a diff is the one control that puts
two people's memories side by side.

**Nothing here writes, applies, approves or deletes.** No memory is edited, no rung moved, no
proposal approved, no learning frozen anywhere but in the value returned. `now` is a parameter
throughout and nothing opens a connection, for the reason `brain.ops.limits` gives about policy
that owns a client being untestable at the boundary that is always wrong.

**A breaker returns the record of what tripped it, never a bare yes.** `breaker_trips` hands
back a `CircuitBreak` or `None`, so a caller cannot learn that a rung should fall without also
holding the metric that says why. A bool would let the demotion be written and the reason
dropped, which is the state a rung goes straight back up from. And a tripped breaker goes to
the bottom rung rather than one step down: a step down leaves the agent acting while whatever
tripped it is still true, and the rung then walks down over hours.

**One leaf of these twenty is deliberately not built here**, and it is the memory viewer's
direct edit and direct delete by the owner. Delete already exists as
`brain.memory.review.delete`, which writes a mark rather than removing a row and is claimed by
its own leaf; edit does not exist anywhere, and `brain.tables.memory` grants SELECT and INSERT
only on both memory tables, so an edit is a migration and a tool rather than a function on a
console module. Building half of it here would put a write path on a surface whose whole
argument is that the console holds nothing of its own.

**And nothing here claims a screen exists.** There is no console screen behind any of this, in
this repository or anywhere else; `brain.console.screens` says the same about its own registry
and for the same reason. What is built is the domain layer four screens would read.

Task ids: M39.3.1.1, M39.3.1.2, M39.3.1.3, M39.3.1.4, M39.3.1.5
Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5
Task ids: M39.4.1.1, M39.4.1.2, M39.4.1.3, M39.4.1.5
Task ids: M39.4.2.1, M39.4.2.2, M39.4.2.3, M39.4.2.4, M39.4.2.5
"""

from __future__ import annotations

import difflib
import enum
import inspect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Final

from brain.agents.model import (
    AUDIENCE_IS_NOT_AUTHORITY,
    AgentRecord,
    AgentViewer,
    entitlement_ceiling,
    tool_ceiling,
    visible_to,
)
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import SideEffect
from brain.core.redaction import render_lock
from brain.core.scope import Op, Scope
from brain.gate.catalogue import SIDE_EFFECT_ORDER
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.invoke import Invocation, InvocationRefusedError, invoke
from brain.gate.leash import Leash
from brain.memory.correction import Correction, Demotion, Supersession
from brain.memory.digest import Learning, MemoryItem, memory_item
from brain.memory.formation import MemoryKind, Recollection, may_recall
from brain.memory.signals import Signal
from brain.memory.tiers import (
    PROMOTION_AGREEMENT,
    Change,
    Occurrence,
    Tier,
    blast_radius,
    may_promote,
)
from brain.ops.halt import MINIMUM_REASON
from brain.tools.registry import ToolRegistry

# ------------------------------------------------------------------ written-down reasons

#: Why the ceiling is shown whole or not at all, and never narrowed to the reader.
A_CEILING_FILTERED_TO_THE_READER_IS_THE_COLLAPSE_WEARING_A_CEILING_LABEL: Final = (
    "Showing a reader the part of the ceiling they themselves hold produces E_run with the "
    "ceiling's heading on it. It is the most attractive option on this screen, because it "
    "discloses nothing and looks like a ceiling, and it is the worst: the two questions this "
    "surface exists to keep apart become one value and nothing anywhere says so. A reader "
    "then believes the agent cannot do a thing it does for their colleague every day, and "
    "the belief is unfalsifiable from the screen. So the ceiling is the agent's own set or "
    "it is a lock, and there is no third rendering."
)

#: Why the disclosure grant is the capability vocabulary's own.
THE_GRANT_OVER_THE_VOCABULARY_IS_THE_DECISION_ALREADY_MADE: Final = (
    "A ceiling naming read:client.contract_value tells a reader that contract values exist "
    "and that somebody reaches them, which is the retrieval leak CLAUDE.md names, restated "
    "in the permission vocabulary rather than the data vocabulary. What makes it admissible "
    "is not that a ceiling is configuration: it is that somebody granted this reader the "
    "capability the Capabilities screen requires, which is the decision that they may learn "
    "what can be granted at all. A ceiling is a subset of that, so it needs the same grant "
    "and no new argument, and a reader without it gets a lock."
)

#: Why the preview cannot be an estimate.
AN_ESTIMATED_PREVIEW_IS_A_SECOND_PROJECTOR_NOBODY_CAN_CHECK: Final = (
    "A preview that worked out what somebody's run would return would be a second "
    "implementation of catalogue projection, read by the one audience with no way to check "
    "it: an administrator deciding whether a person has enough access. When the two drifted, "
    "the screen would be the confident one. So the preview runs the gate: invoke returns an "
    "Invocation carrying a ProjectedCatalogue, which cannot be constructed outside project, "
    "and holding one is proof the projection ran rather than a promise that it did."
)

#: Why every cell of the leash matrix is looked up rather than inherited.
A_MATRIX_THAT_FILLS_A_BLANK_CELL_PUTS_THE_DEFAULT_BACK: Final = (
    "Leash has no per-agent default and its docstring argues at length against one: a "
    "default lets trust earned on cheap targets spend itself on expensive ones, invisibly, "
    "because it looks like configuration working. A matrix that filled an unconfigured cell "
    "from the row it sits in would put that default back at the rendering layer, where it "
    "would look like the table working instead. Every cell calls rung_for on its own target."
)

#: Why raising a rung cannot be earned by evidence alone.
A_RUNG_RISE_IS_A_GATED_CHANGE_AND_AGREEMENT_IS_NOT_WHAT_IT_WAITS_FOR: Final = (
    "brain.memory.tiers classifies a leash increase as tier three and may_promote refuses "
    "to promote anything gated by agreement, because three people repeating a pattern is not "
    "a person deciding somebody may be trusted further. This module reads that "
    "classification rather than restating it, so clean runs and an agreement rate are the "
    "evidence a named approver looked at and never the thing that decides. Lowering takes no "
    "evidence at all, which is the asymmetry a fail-safe direction has to have."
)

#: Why the statement is paired with the recollection that admitted it.
THE_STATEMENT_IS_THE_DISCLOSURE_AND_ITS_TAGS_ARE_ITS_PERMISSION: Final = (
    "Learning and MemoryItem carry no statement, because a learning record holding what was "
    "said would be a second transcript under the record's permissions rather than the "
    "conversation's. The statement itself lives under the capability tags it was formed "
    "with, and those tags are its permission, so text shown behind a passed may_recall is "
    "the memory under its own terms. readable therefore computes the recall verdict and "
    "will not accept one: a signature taking a Recollection can be handed a verdict somebody "
    "else reached, and the caller who reaches it wrongly is the surface, every time."
)

#: Why a diff needs both sides to have been admitted.
A_DIFF_IS_TWO_DISCLOSURES_AND_THE_OLDER_ONE_IS_THE_ONE_NOBODY_CHECKS: Final = (
    "A revision diff renders the superseded statement as well as the current one, and the "
    "superseded one was formed under its own tags, which may be wider. A reader admitted to "
    "the newer memory is not thereby admitted to the older, so a diff is produced only when "
    "may_recall passed on both. When it did not, there is no diff and no note saying a "
    "revision was withheld: that note is the count, with the number left off."
)

#: Why the freeze has no per-tier control.
A_FREEZE_WITH_AN_EXCEPTION_IS_NOT_A_FREEZE: Final = (
    "The control asked for is one control that stops all learning during an incident, and "
    "the value of it is that the person pressing it does not have to know which tiers matter "
    "at the moment they are least able to work it out. A per-tier freeze is the same button "
    "with a decision attached, and the decision is made under exactly the conditions that "
    "make it wrong. So freeze takes no tier, and thaw carries a stated reason at "
    "brain.ops.halt's own minimum, which is that module's rule: stopping is free and "
    "restarting is the act that needs a person to have written down why."
)


# ------------------------------------------------------------------- the two disclosures

#: The capability that admits a reader to the agent's whole ceiling.
#:
#: The Capabilities screen's own requirement, written out here rather than read off
#: `brain.console.screens` so that a test can compare the two. Derived, the comparison would
#: be a constant against itself and repointing either would move both.
CEILING_DISCLOSURE: Final = Capability(value="read:capability")

#: The capability that admits a reader to a preview of somebody else's run.
#:
#: The People screen's requirement, on the same terms. Previewing what a person's run would
#: return is reading what that person holds, which is the disclosure `read:grant` governs.
PREVIEW_DISCLOSURE: Final = Capability(value="read:grant")

#: The heading over the block about who may find and start the agent.
AVAILABILITY_HEADING: Final = "Who can use this agent"

#: The heading over the block about what any run of it may reach.
CEILING_HEADING: Final = "The most this agent can ever reach"

#: The heading over one person's worked preview.
PREVIEW_HEADING: Final = "What this person's run would return"

#: What a preview says when the run would not start.
#:
#: One sentence for every reason a run is refused, on `brain.gate.leash.REFUSAL_NOTICE`'s
#: argument: a notice that varied by cause is a side channel two readers could compare. It
#: says nothing about the agent's ceiling either, so a preview is not a way to ask the ceiling
#: question one capability at a time.
PREVIEW_RETURNS_NOTHING: Final = "This person's run of this agent would return nothing."


@dataclass(frozen=True)
class AvailabilityBlock:
    """Who may find and start this agent. Discovery, and never authority.

    **There is no capability, entitlement, ceiling or tool on this type**, and that absence is
    the enforcement rather than the docstring above it: a renderer cannot put a capability
    under this heading because there is nowhere to hold one. `brain.agents.model` keeps the
    same separation one layer down, where `AgentViewer` carries no entitlement.

    `copy` is `AUDIENCE_IS_NOT_AUTHORITY` itself and not a second wording of it. Two
    statements of one rule is one statement that gets edited and one that does not.
    """

    agent_id: str
    #: The audience level's name, as `brain.knowledge.visibility.Visibility` spells it.
    level: str
    #: The steward, who at the personal level is the whole audience.
    owner_id: str
    #: Empty except at the department level, as `AgentAudience` requires.
    department: str
    #: Whether the person reading this block is themselves in the audience.
    reader_is_included: bool
    heading: str = AVAILABILITY_HEADING
    copy: str = AUDIENCE_IS_NOT_AUTHORITY


@dataclass(frozen=True)
class CeilingBlock:
    """The widest entitlement any run of this agent may reach.

    A property of the agent. Two readers holding this block's disclosure capability and
    nothing else in common see the same value, which is the property `reach_view_gaps` cannot
    check and a test does.

    `capabilities` is the agent's own set or it is empty and `locked` is True. It is never a
    narrowed set: see `A_CEILING_FILTERED_TO_THE_READER_IS_THE_COLLAPSE_WEARING_A_CEILING_LABEL`.
    There is no field for how many were withheld, because there is nothing to withhold: the
    ceiling is shown or it is not.
    """

    agent_id: str
    #: The ceiling's capabilities in one order, or empty when locked.
    capabilities: tuple[str, ...]
    #: Where the ceiling narrows rows, as the agent declares it. Locked with the rest.
    scope: Scope | None
    #: The largest side effect any run may have, or None when locked.
    max_side_effect: SideEffect | None
    locked: bool
    heading: str = CEILING_HEADING

    def render(self) -> tuple[str, ...]:
        """What a reader sees: the capabilities, or one lock string and nothing else.

        `render_lock` rather than a sentence of this module's own, because a lock that varied
        by field, by reason or by reader would be readable by two people comparing screens,
        and that function takes no arguments so it cannot vary by anything.
        """
        if self.locked:
            return (render_lock(),)
        return self.capabilities


@dataclass(frozen=True)
class RunPreview:
    """What one named person's run of this agent would return, run through the real gate.

    `invocation` is `None` when the run would not start, and `notice` is then
    `PREVIEW_RETURNS_NOTHING` for every reason it could have been refused.

    **There is no field here a tool list could be written into.** The names a reader sees come
    off `Invocation.reachable`, which came off a `ProjectedCatalogue`, which cannot be built
    outside `brain.gate.catalogue.project`. See
    `AN_ESTIMATED_PREVIEW_IS_A_SECOND_PROJECTOR_NOBODY_CAN_CHECK`.
    """

    subject_id: str
    agent_id: str
    invocation: Invocation | None
    notice: str = ""
    heading: str = PREVIEW_HEADING

    def reaches(self) -> tuple[str, ...]:
        """The tool names this run would have, in the projection's own order."""
        return () if self.invocation is None else self.invocation.reachable

    def rung(self) -> AutonomyTier | None:
        """The strictest rung the run would be held to, or None when it would not start."""
        return None if self.invocation is None else self.invocation.ceiling_rung


def availability_block(record: AgentRecord, reader: AgentViewer) -> AvailabilityBlock:
    """The audience block for one agent (M39.3.1.1).

    Takes a record and a viewer and nothing else. There is no entitlement parameter, so this
    function could not consult authority if a later edit wanted it to, which is the shape
    `brain.agents.model.audience_scope` uses for the same rule one layer down.

    `reader_is_included` is `visible_to`, the same predicate `select_agent` skips an agent on.
    Computed rather than restated so an audience this block calls visible is an audience that
    would actually route.
    """
    return AvailabilityBlock(
        agent_id=record.agent_id,
        level=record.audience.level.value,
        owner_id=record.audience.owner_id,
        department=record.audience.department,
        reader_is_included=visible_to(record.audience, reader),
    )


def ceiling_block(
    record: AgentRecord,
    reader: EntitlementSet,
    now: datetime | None = None,
) -> CeilingBlock:
    """The ceiling block for one agent (M39.3.1.2).

    `reader` decides one thing and one thing only: whether the ceiling is disclosed at all.
    It never narrows what is disclosed. Two readers who both hold `CEILING_DISCLOSURE` see the
    same block whatever else they hold, and that is the property a test pins, because it is
    the one no signature can prove.

    The capabilities come from `brain.agents.model.entitlement_ceiling`, which is the right
    hand side of `E_run`'s intersection, so the block shows the same object the gate narrows
    by rather than a list assembled here from the record.
    """
    if reader.scope_for(CEILING_DISCLOSURE, now) is None:
        return CeilingBlock(
            agent_id=record.agent_id,
            capabilities=(),
            scope=None,
            max_side_effect=None,
            locked=True,
        )
    ceiling = entitlement_ceiling(record)
    return CeilingBlock(
        agent_id=record.agent_id,
        capabilities=tuple(sorted(grant.capability.value for grant in ceiling.grants)),
        scope=record.authority.scope,
        max_side_effect=record.authority.max_side_effect,
        locked=False,
    )


def run_reach(caller: EntitlementSet, record: AgentRecord) -> EntitlementSet:
    """`E_run(caller, agent) = E(caller) intersect agent_ceiling`, for the pair block.

    One line, calling `EntitlementSet.intersect`, which is the platform's single
    implementation and the same one `brain.gate.leash.decide` and
    `brain.ops.automation.flow_reach` call. A second would be a second place for the
    central rule to be subtly wrong, and the wrong copy is the one on a screen somebody
    trusts.

    Note the direction: the agent's declaration is a ceiling and never a grant, so a caller
    holding nothing comes out holding nothing however wide the ceiling is.
    """
    return caller.intersect(entitlement_ceiling(record))


def run_preview(
    *,
    record: AgentRecord,
    subject_id: str,
    subject_entitlement: EntitlementSet,
    previewer: EntitlementSet,
    registry: ToolRegistry,
    leash: Leash,
    assessment: RiskAssessment,
    now: datetime,
    row: dict[str, str] | None = None,
    universal: frozenset[str] = frozenset(),
) -> RunPreview | None:
    """What this person's run would return, computed by the gate (M39.3.1.4, M39.3.1.5).

    `None` when the previewer may not ask. Not a refusal object and not an empty preview: a
    reader who may not ask about somebody's grants learns nothing about whether that person
    has any, which is the same answer `select_agent` gives for an agent somebody cannot see.

    Every argument after `subject_entitlement` is passed straight to
    `brain.gate.invoke.invoke`. There is no argument here that could supply a tool list, a
    catalogue or an estimate, and `reach_view_gaps` reads this signature for one.

    `InvocationRefusedError` becomes `PREVIEW_RETURNS_NOTHING` rather than its own message.
    The exception says which tools failed to resolve, which is the ceiling question answered
    one capability at a time by a person who was refused the ceiling block.
    """
    if previewer.scope_for(PREVIEW_DISCLOSURE, now) is None:
        return None

    try:
        invocation = invoke(
            principal_id=subject_id,
            agent_id=record.agent_id,
            registry=registry,
            entitlement=subject_entitlement,
            ceiling=tool_ceiling(record),
            leash=leash,
            assessment=assessment,
            now=now,
            row=row,
            universal=universal,
        )
    except InvocationRefusedError:
        return RunPreview(
            subject_id=subject_id,
            agent_id=record.agent_id,
            invocation=None,
            notice=PREVIEW_RETURNS_NOTHING,
        )

    return RunPreview(subject_id=subject_id, agent_id=record.agent_id, invocation=invocation)


# --------------------------------------------------------------------- the leash matrix


class Operation(enum.StrEnum):
    """The three things a rung is set for, kept on separate rungs.

    Named from `brain.core.envelope.SideEffect` rather than invented, and `OPERATION_EFFECT`
    is the mapping. A vocabulary of its own here would be a second way of saying what a tool
    does, and the two would disagree about `draft` first.
    """

    READ = "read"
    DRAFT = "draft"
    WRITE = "write"


#: What each operation does to the world, in the vocabulary the tool registry already uses.
OPERATION_EFFECT: Final[dict[Operation, SideEffect]] = {
    Operation.READ: SideEffect.NONE,
    Operation.DRAFT: SideEffect.DRAFT,
    Operation.WRITE: SideEffect.WRITE,
}

#: The effects whose rung may not rise on one approver.
#:
#: Money, because it moves money, and send, because a message that has left the building
#: cannot be recalled and neither can the reply to it. Written out rather than derived from
#: `SIDE_EFFECT_ORDER`, on `brain.memory.tiers.CHANGES_WHAT_ANYBODY_MAY_SEE`'s argument:
#: derived, this and the order would agree by construction and a test comparing them would be
#: comparing a value against itself. `reach_view_gaps` checks the two against each other.
IRREVERSIBLE: Final[frozenset[SideEffect]] = frozenset({SideEffect.SEND, SideEffect.MONEY})

#: How many consecutive clean runs a rise needs evidence of.
#:
#: Anchored against `brain.memory.tiers.PROMOTION_AGREEMENT` rather than chosen: a rung rise is
#: a tier-three change and a procedural shortcut is tier two, so the evidence bar for the first
#: cannot be below the bar for the second. Three is the floor that relation puts on it and this
#: sits above it, because a clean run is cheaper evidence than an independent occurrence: a run
#: nobody complained about is one observation, where an occurrence is a conversation.
MINIMUM_CLEAN_RUNS: Final = 10

#: The share of an agent's drafts a person has to have accepted unchanged.
#:
#: Nine in ten. Below that the person reviewing is doing the work, and a rung rise then moves
#: the review rather than removing it. Stated as a share so it does not move with volume: an
#: agent that ran a thousand times is not more trustworthy for having been corrected a hundred.
MINIMUM_AGREEMENT_RATE: Final = 0.9


class LeashError(Exception):
    """A matrix, an evidence record or a rung move that cannot mean what it says."""


@dataclass(frozen=True)
class LeashCell:
    """One rung, for one entity and one operation. The unit the matrix is made of."""

    entity: str
    operation: Operation
    rung: AutonomyTier
    #: The target this cell asked the leash about, kept so a reader can check the lookup.
    target: str

    @property
    def effect(self) -> SideEffect:
        return OPERATION_EFFECT[self.operation]


@dataclass(frozen=True)
class LeashMatrix:
    """Every cell for one agent, in entity order then operation order.

    Holds cells and no defaults. `rung` raises for a cell that was never built rather than
    returning `MISSING_ENTRY_RUNG`, because a matrix answering for an entity it was not asked
    about is a matrix that has grown the fallback the leash refuses to have.
    """

    agent_id: str
    cells: tuple[LeashCell, ...]

    def rung(self, entity: str, operation: Operation) -> AutonomyTier:
        for cell in self.cells:
            if cell.entity == entity and cell.operation is operation:
                return cell.rung
        msg = (
            f"{self.agent_id} has no cell for {entity}.{operation.value}; a matrix that "
            "answered for an entity it was not built for would be the per-agent default "
            "brain.gate.leash refuses to have, moved to the surface that renders it"
        )
        raise LeashError(msg)


def leash_matrix(
    leash: Leash,
    agent_id: str,
    *,
    entities: Sequence[str],
    row: Mapping[str, str] | None = None,
    operations: Sequence[Operation] = tuple(Operation),
) -> LeashMatrix:
    """The rung for every entity and operation, each looked up on its own (M39.3.2.1).

    `entities` are bare entity names. A name already carrying a dot is refused rather than
    used, because `brain.gate.leash.TARGET` admits one dot and composing a second produces a
    target no entry can ever match, which would render as a grid of SHADOW that looks like a
    cautious configuration rather than like a broken one.

    Every cell calls `rung_for` on its own composed target and none is copied from a
    neighbour. See `A_MATRIX_THAT_FILLS_A_BLANK_CELL_PUTS_THE_DEFAULT_BACK`.
    """
    where = dict(row or {})
    cells: list[LeashCell] = []
    for entity in entities:
        if "." in entity:
            msg = (
                f"{entity!r} already names an operation, and composing another produces a "
                "target no leash entry can match, which renders as a grid of SHADOW that "
                "reads like a careful configuration rather than a broken one"
            )
            raise LeashError(msg)
        for operation in operations:
            target = f"{entity}.{operation.value}"
            cells.append(
                LeashCell(
                    entity=entity,
                    operation=operation,
                    rung=leash.rung_for(agent_id, target, where),
                    target=target,
                )
            )
    return LeashMatrix(agent_id=agent_id, cells=tuple(cells))


@dataclass(frozen=True)
class PromotionEvidence:
    """What a person looked at before raising a rung, and who that person was.

    All three parts are required and none of them decides: see
    `A_RUNG_RISE_IS_A_GATED_CHANGE_AND_AGREEMENT_IS_NOT_WHAT_IT_WAITS_FOR`. The approver is
    named here so that the history carries a person rather than a threshold that was met.
    """

    clean_runs: int
    agreement_rate: float
    approver_id: str
    #: Required for an irreversible effect, and distinct from the first. Empty otherwise.
    second_approver_id: str = ""

    def __post_init__(self) -> None:
        if not self.approver_id.strip():
            msg = (
                "evidence with no named approver records a threshold being met and not a "
                "person deciding, which is what a tier-three change waits for"
            )
            raise LeashError(msg)
        if self.clean_runs < 0:
            msg = "a negative count of clean runs is not evidence of anything"
            raise LeashError(msg)
        if not 0.0 <= self.agreement_rate <= 1.0:
            msg = f"{self.agreement_rate} is not a share, so it says nothing about agreement"
            raise LeashError(msg)
        if self.second_approver_id and self.second_approver_id == self.approver_id:
            msg = (
                "the second approver is the first, so one person approved twice and the "
                "boundary this rung sits behind has one signature on it"
            )
            raise LeashError(msg)

    def meets_the_bar(self) -> bool:
        """Whether the evidence itself clears both thresholds. Says nothing about approval."""
        return (
            self.clean_runs >= MINIMUM_CLEAN_RUNS and self.agreement_rate >= MINIMUM_AGREEMENT_RATE
        )


@dataclass(frozen=True)
class CircuitBreak:
    """Why a rung fell, with the metric that tripped it attached.

    Named `CircuitBreak` rather than `Demotion` because `brain.memory.correction.Demotion` is
    a memory the source contradicted, and two things called a demotion in one system is one
    word that stops meaning anything.

    Refuses an unnamed metric. A rung that fell for no reason anybody can show is a rung
    somebody puts straight back.
    """

    metric: str
    measured: float
    threshold: float
    at: datetime

    def __post_init__(self) -> None:
        if not self.metric.strip():
            msg = (
                "a circuit break with no metric shows a person a rung that fell and nothing "
                "they could act on, so the rung goes back up on the next complaint"
            )
            raise LeashError(msg)
        if self.at.tzinfo is None:
            msg = "a naive break time compares wrongly against an aware one"
            raise LeashError(msg)

    def render(self) -> str:
        """The sentence beside the rung. Names the metric and both figures, never a record."""
        return f"{self.metric} measured {self.measured} against a threshold of {self.threshold}"


class Watch(enum.StrEnum):
    """Which way a metric has to move to be bad. Two members and no default.

    An agreement rate is bad when it falls and an error count is bad when it rises, and a
    breaker that assumed either would be silently inert for half the metrics anybody wires to
    it. Inert is the worst failure available here, because a breaker that never trips looks
    exactly like a system behaving well.
    """

    FALLS_BELOW = "falls_below"
    RISES_ABOVE = "rises_above"


#: Where a tripped breaker puts the rung.
#:
#: The bottom, not one step down. A step down leaves the agent still acting while whatever
#: tripped the breaker is still true, and the next measurement trips it again, so the rung
#: walks down over hours while the thing it was measuring keeps happening. `AutonomyTier`
#: names the bottom rather than a literal zero, so a member added below it moves this with it.
DEMOTED_TO: Final = AutonomyTier.SHADOW


def breaker_trips(
    *,
    watch: Watch,
    metric: str,
    measured: float,
    threshold: float,
    at: datetime,
) -> CircuitBreak | None:
    """Whether one measurement trips the breaker, and the record of it if so (M39.3.2.3).

    Returns the `CircuitBreak` rather than a bool, so a caller cannot learn that a rung
    should fall without also holding the metric that says why. A bool would let the demotion
    be written and the reason dropped, which is the state
    `CircuitBreak.__post_init__` refuses one field at a time.

    The comparison is strict on both sides, so a metric sitting exactly on its threshold does
    not trip. A threshold is the worst acceptable value rather than the best unacceptable one,
    and a breaker that fired at equality would fire on the day somebody set the threshold to
    what they had just measured.
    """
    tripped = measured < threshold if watch is Watch.FALLS_BELOW else measured > threshold
    if not tripped:
        return None
    return CircuitBreak(metric=metric, measured=measured, threshold=threshold, at=at)


def may_raise(
    *,
    was: AutonomyTier,
    proposed: AutonomyTier,
    evidence: PromotionEvidence | None,
    effect: SideEffect,
) -> bool:
    """Whether a rung may move from `was` to `proposed` (M39.3.2.2, M39.3.2.4).

    **Decides nothing about the change itself.** A rung rise is `Change.LEASH_INCREASE`, which
    `brain.memory.tiers` puts at `Tier.GATED`, and a gated change is approved by a person. What
    this reports is whether the evidence that person is looking at meets the bar and whether
    the boundary the target sits behind has the signatures it requires.

    Lowering or holding is always true and takes no evidence: the fail-safe direction cannot
    be the one with paperwork on it, or an incident is the moment somebody discovers they
    cannot turn something down.

    An irreversible effect needs a second, distinct approver. `PromotionEvidence` refuses two
    identical ones at construction, so the only failure reachable here is an absent one.
    """
    if proposed <= was:
        return True
    if blast_radius(Change.LEASH_INCREASE) is not Tier.GATED:
        # The premise everything below rests on, checked rather than assumed. Loud rather
        # than a quiet False, because a False here would present as evidence never being
        # good enough, and somebody would go looking at the thresholds.
        msg = (
            "a leash increase is no longer a gated change, so the rule that a person must "
            "approve one is not written down anywhere this function can read, and the "
            "thresholds below would be deciding a trust increase on their own"
        )
        raise LeashError(msg)
    if evidence is None:
        return False
    if not evidence.meets_the_bar():
        return False
    if effect in IRREVERSIBLE:
        return bool(evidence.second_approver_id)
    return True


@dataclass(frozen=True)
class RungChange:
    """One move of one rung, with the evidence that moved it attached (M39.3.2.5).

    A promotion carries `PromotionEvidence` and a demotion carries `CircuitBreak`, and the
    constructor refuses the other way round. An entry whose evidence does not match its
    direction is a history that reads as though somebody was promoted for failing.
    """

    at: datetime
    entity: str
    operation: Operation
    was: AutonomyTier
    became: AutonomyTier
    evidence: PromotionEvidence | CircuitBreak

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            msg = "a naive change time compares wrongly against an aware one"
            raise LeashError(msg)
        if self.became == self.was:
            msg = (
                f"{self.entity}.{self.operation.value} did not move, and a history of "
                "non-moves buries the two that did"
            )
            raise LeashError(msg)
        rose = self.became > self.was
        if rose and not isinstance(self.evidence, PromotionEvidence):
            msg = (
                f"{self.entity}.{self.operation.value} rose on a circuit break, so the "
                "history says somebody was trusted further for having failed"
            )
            raise LeashError(msg)
        if not rose and not isinstance(self.evidence, CircuitBreak):
            msg = (
                f"{self.entity}.{self.operation.value} fell on promotion evidence, so the "
                "history shows no metric for a rung that dropped and nobody can act on it"
            )
            raise LeashError(msg)

    @property
    def is_promotion(self) -> bool:
        return self.became > self.was


def rung_history(changes: Iterable[RungChange]) -> tuple[RungChange, ...]:
    """Every move, oldest first, with nothing dropped (M39.3.2.5).

    Oldest first because a reviewer works forwards: a demotion is read against what raised the
    rung in the first place, and newest-first puts the answer above the question.

    Ties break on entity and operation so two moves in one instant order the same way on every
    reading, for the reason `brain.memory.review._most_confident_first` fixes its ties.
    """
    return tuple(sorted(changes, key=lambda one: (one.at, one.entity, one.operation.value)))


# ----------------------------------------------------------------------- memory, visible


class Provenance(enum.StrEnum):
    """Where a memory came from, which is the split a viewer has to keep.

    Two members and no third. A memory is something somebody stated or something the system
    worked out, and the reason the split matters on a screen is that the second is a guess
    presented in the same typeface as the first.
    """

    #: Somebody stated it. `MemoryKind.PERSISTENT`, which stays until contradicted.
    CURATED = "curated"
    #: The system worked it out. `MemoryKind.ADAPTIVE`, which decays.
    EXTRACTED = "extracted"


#: Which kind is which provenance. `MemoryKind.SESSION` is deliberately absent: it lives in a
#: cache keyed by thread, dies with the conversation and is in neither table, so a viewer
#: showing one would be showing something nobody can go back and look at.
PROVENANCE_OF_KIND: Final[dict[MemoryKind, Provenance]] = {
    MemoryKind.PERSISTENT: Provenance.CURATED,
    MemoryKind.ADAPTIVE: Provenance.EXTRACTED,
}


class MemoryViewError(Exception):
    """A memory a viewer cannot honestly render."""


def provenance_of(kind: MemoryKind) -> Provenance:
    """Curated or extracted, refusing the kind that is neither (M39.4.1.2).

    Refuses `SESSION` rather than folding it into either. A session memory promoted to
    persistent is a real operation `MemoryKind` exists to record, and a viewer that quietly
    called an unpromoted session memory curated would be showing a conversation's working as
    though somebody had stated it.
    """
    found = PROVENANCE_OF_KIND.get(kind)
    if found is None:
        msg = (
            f"{kind.value} is in neither memory table, so a viewer has nothing to show and "
            "nothing anybody could go back to; it lives in a cache and dies with the thread"
        )
        raise MemoryViewError(msg)
    return found


@dataclass(frozen=True)
class MemoryText:
    """One memory in its own words, paired with the recollection that admitted them.

    The pairing is the point. `seen` is the verdict `may_recall` reached about this reader,
    and it is on the value rather than checked before building it, so a renderer holding a
    `MemoryText` is holding the reason it may show the text.
    """

    memory_id: str
    provenance: Provenance
    statement: str
    seen: Recollection


def readable(
    learning: Learning,
    statement: str,
    reader: EntitlementSet,
    *,
    now: datetime,
    where: Mapping[str, object] | None = None,
) -> MemoryText | None:
    """This memory as readable text, when the reader may have it (M39.4.1.1).

    `None` means no, and no is the whole answer: nothing here reports that text was withheld,
    because "there is something I know and will not say" is a fact about what exists.

    Computes the recall verdict rather than accepting one. See
    `THE_STATEMENT_IS_THE_DISCLOSURE_AND_ITS_TAGS_ARE_ITS_PERMISSION`.

    Refuses an empty statement instead of rendering a blank row, because a viewer whose whole
    purpose is that memory is not an opaque store must not have a way of showing an opaque one.
    """
    if not statement.strip():
        msg = (
            f"{learning.memory_id} has no statement, and a blank row in a viewer built to "
            "show memory as text is the opaque store with a heading on it"
        )
        raise MemoryViewError(msg)
    seen = may_recall(
        learning.formation,
        reader,
        now=now,
        where=where,
        formed_confidence=learning.formed_confidence,
    )
    if seen is None:
        return None
    return MemoryText(
        memory_id=learning.memory_id,
        provenance=provenance_of(learning.formation.kind),
        statement=statement,
        seen=seen,
    )


@dataclass(frozen=True)
class SplitMemoryView:
    """Curated and extracted memory, side by side and never merged (M39.4.1.2).

    Two tuples rather than one list with a column, because the reason for the split is that
    the two carry different weight, and a single list sorted by confidence puts a guess above
    a statement the moment the guess is fresh.

    No count on either side and none of the whole, per
    `brain.memory.digest.A_COUNT_BESIDE_A_FILTERED_LISTING_IS_A_SUBTRACTION`.
    """

    reader_id: str
    curated: tuple[MemoryText, ...]
    extracted: tuple[MemoryText, ...]


def split_memory(
    entries: Sequence[tuple[Learning, str]],
    reader: EntitlementSet,
    *,
    now: datetime,
    where: Mapping[str, object] | None = None,
) -> SplitMemoryView:
    """Everything this reader may have, split by where it came from (M39.4.1.2).

    Each entry is a learning and its statement. The statement is handed in rather than read
    off the learning because `Learning` deliberately does not carry one, and inventing a field
    for it here would put the transcript back on the record that refuses to hold it.

    A session memory in the input raises rather than being dropped: dropping it silently would
    make a viewer that is missing half a conversation look like a viewer that is complete.
    """
    curated: list[MemoryText] = []
    extracted: list[MemoryText] = []
    for learning, statement in entries:
        text = readable(learning, statement, reader, now=now, where=where)
        if text is None:
            continue
        if text.provenance is Provenance.CURATED:
            curated.append(text)
        else:
            extracted.append(text)
    return SplitMemoryView(
        reader_id=reader.principal_id,
        curated=tuple(curated),
        extracted=tuple(extracted),
    )


@dataclass(frozen=True)
class Revision:
    """One step in a memory's history, with the diff and the trigger that caused it.

    `diff` is empty when the reader was not admitted to both sides, and nothing on this value
    says which side was withheld. See
    `A_DIFF_IS_TWO_DISCLOSURES_AND_THE_OLDER_ONE_IS_THE_ONE_NOBODY_CHECKS`.
    """

    memory_id: str
    replaced_id: str | None
    at: datetime
    #: Unified diff lines, oldest side first. Empty when both sides were not readable.
    diff: tuple[str, ...]
    #: What caused the change, in the closed signal vocabulary, when a correction recorded it.
    trigger: Signal | None
    #: Which correction was written, when one was. Never a removal: `Correction` has two
    #: members and `brain.memory.correction` argues there is no third.
    correction: Correction | None


def _diff_lines(before: str, after: str) -> tuple[str, ...]:
    """A unified diff of two statements, without the file headers.

    `difflib` from the standard library rather than a dependency, and the headers are dropped
    because they would name two empty files, which reads like a bug in the viewer.
    """
    return tuple(
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if not line.startswith(("---", "+++"))
    )


def revisions(
    chain: Sequence[tuple[Learning, str]],
    reader: EntitlementSet,
    *,
    now: datetime,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
    where: Mapping[str, object] | None = None,
) -> tuple[Revision, ...]:
    """The history of one memory, oldest first, with a diff per step (M39.4.1.3).

    A revision appears when the reader may read the memory it is about. Its diff appears when
    the reader may read the memory it replaced as well, and when they may not there is no diff
    and no note: the note would be the count with the number left off.

    The trigger comes from a `Supersession` or a `Demotion` and never from this module's own
    reading of the two statements. A viewer that inferred why something changed by comparing
    text would be a classifier deciding what a correction meant.
    """
    readable_text: dict[str, str] = {}
    for learning, statement in chain:
        text = readable(learning, statement, reader, now=now, where=where)
        if text is not None:
            readable_text[learning.memory_id] = text.statement

    by_superseded = {one.superseded_id: one for one in supersessions}
    demoted = {one.memory_id: one for one in demotions}

    found: list[Revision] = []
    for learning, _ in chain:
        if learning.memory_id not in readable_text:
            continue
        previous = learning.replaced_id
        both = previous is not None and previous in readable_text
        supersession = by_superseded.get(previous) if previous is not None else None
        demotion = demoted.get(learning.memory_id)

        trigger: Signal | None = None
        correction: Correction | None = None
        if supersession is not None:
            trigger = supersession.prompted_by
            correction = Correction.SUPERSEDED
        elif demotion is not None:
            correction = Correction.DEMOTED

        found.append(
            Revision(
                memory_id=learning.memory_id,
                replaced_id=previous,
                at=learning.formation.formed_at,
                diff=(
                    _diff_lines(readable_text[previous], readable_text[learning.memory_id])
                    if both and previous is not None
                    else ()
                ),
                trigger=trigger,
                correction=correction,
            )
        )
    return tuple(sorted(found, key=lambda one: (one.at, one.memory_id)))


@dataclass(frozen=True)
class SeparateMemoryView:
    """What the agent learnt and what the system knows about the person, kept apart.

    Two tuples and no merge. A learning that is both the agent's and the person's appears in
    both, rather than being assigned to whichever list was built first: assigning it makes one
    list incomplete, and the reader cannot tell which.

    No count on either, and no field that could hold one.
    """

    reader_id: str
    agent_id: str
    subject_id: str
    per_agent: tuple[MemoryItem, ...]
    per_person: tuple[MemoryItem, ...]


def separate_memory(
    *,
    now: datetime,
    caller: EntitlementSet,
    record: AgentRecord,
    subject_id: str,
    learnings: Sequence[Learning],
    where: Mapping[str, object] | None = None,
) -> SeparateMemoryView:
    """Per-agent and per-person memory, shown separately (M39.4.1.5).

    The per-agent side is read at `E_run(caller, agent)`, by `run_reach`, because a tab
    showing what the agent knows rather than what this caller may be told is the one place a
    lens would stop applying. The per-person side is read at the caller's own reach, because
    it is not the agent's memory and narrowing it by the agent's ceiling would hide a memory
    from its own subject for a reason that has nothing to do with them.

    Both sides go through `may_recall`, so a memory formed from somebody else's conversation
    is absent from both unless the caller reaches what it was formed from.
    """
    run = run_reach(caller, record)
    per_agent = [one for one in learnings if one.agent_id == record.agent_id]
    per_person = [one for one in learnings if one.formation.principal_id == subject_id]
    return SeparateMemoryView(
        reader_id=caller.principal_id,
        agent_id=record.agent_id,
        subject_id=subject_id,
        per_agent=_rows(per_agent, run, now=now, where=where),
        per_person=_rows(per_person, caller, now=now, where=where),
    )


def _rows(
    learnings: Sequence[Learning],
    reader: EntitlementSet,
    *,
    now: datetime,
    where: Mapping[str, object] | None,
) -> tuple[MemoryItem, ...]:
    """The rows this reader may see, built by `brain.memory.digest.memory_item`.

    Through that constructor rather than assembled here, so a row on this surface says the
    same thing about a learning as a row in the weekly digest or the review queue.
    """
    found: list[MemoryItem] = []
    for learning in learnings:
        seen = may_recall(
            learning.formation,
            reader,
            now=now,
            where=where,
            formed_confidence=learning.formed_confidence,
        )
        if seen is not None:
            found.append(memory_item(learning, seen))
    return tuple(sorted(found, key=lambda one: (-one.confidence, one.learned_at, one.memory_id)))


# --------------------------------------------------------------------- learning, per agent


@dataclass(frozen=True)
class LearningState:
    """Which tiers this agent learns at, and whether it is currently frozen.

    `declared` is what somebody configured. `frozen_at` is an incident. The two are separate
    fields because a freeze must not be recorded by emptying the declaration: an agent thawed
    afterwards would come back learning at nothing, which looks like the freeze having worked.
    """

    agent_id: str
    declared: frozenset[Tier]
    frozen_at: datetime | None = None
    frozen_by: str = ""

    @property
    def is_frozen(self) -> bool:
        return self.frozen_at is not None


def active_tiers(state: LearningState) -> tuple[Tier, ...]:
    """The tiers this agent is learning at right now, lowest first (M39.4.2.1).

    `Tier.GATED` is dropped even when it is declared, and that is the honest reading rather
    than a convenience: a gated change waits for a person and nothing in this system can
    approve one, so an agent is never learning at tier three. Showing it as active would tell
    a reader the agent widens access by itself.

    A frozen agent is learning at nothing, which is the whole of what the freeze does.
    """
    if state.is_frozen:
        return ()
    return tuple(sorted(tier for tier in state.declared if tier is not Tier.GATED))


def freeze(state: LearningState, *, at: datetime, by: str) -> LearningState:
    """Stop all learning for this agent (M39.4.2.5).

    **No tier parameter, and the absence is the control.** See
    `A_FREEZE_WITH_AN_EXCEPTION_IS_NOT_A_FREEZE`. `reach_view_gaps` reads this signature.

    Takes no reason, on `brain.ops.halt`'s rule: stopping is the free act and restarting is
    the one that carries the risk, so the paperwork is on `thaw`.

    Freezing an already-frozen agent keeps the first freeze. The second would move the record
    of when learning actually stopped, which is the question asked afterwards.
    """
    if not by.strip():
        msg = "a freeze by nobody leaves no one accountable for having stopped it"
        raise LeashError(msg)
    if at.tzinfo is None:
        msg = "a naive freeze time compares wrongly against an aware one"
        raise LeashError(msg)
    if state.is_frozen:
        return state
    return LearningState(
        agent_id=state.agent_id,
        declared=state.declared,
        frozen_at=at,
        frozen_by=by,
    )


def thaw(state: LearningState, *, by: str, reason: str) -> LearningState:
    """Start this agent learning again, with a stated reason.

    The reason is required to `brain.ops.halt.MINIMUM_REASON`, imported rather than restated:
    two minimums for the same kind of sentence is one of them being shorter, and the shorter
    one is the one somebody uses during an incident.

    `declared` survives untouched, which is why the freeze did not empty it.
    """
    if not by.strip():
        msg = "a thaw by nobody leaves no one accountable for restarting learning"
        raise LeashError(msg)
    if len(reason.strip()) < MINIMUM_REASON:
        msg = (
            f"{reason!r} is not a reason to start an agent learning again; the next reader "
            "needs to know whether what caused the freeze was fixed or overridden"
        )
        raise LeashError(msg)
    return LearningState(agent_id=state.agent_id, declared=state.declared)


@dataclass(frozen=True)
class TierOneRow:
    """One automatic change, with the control that undoes it (M39.4.2.2).

    **No approver, no decision, no approved_at, and no queue.** A tier-one change has already
    taken effect and putting it in front of somebody to approve is asking about a decision
    that was made by not needing one. `reach_view_gaps` refuses a field that would.

    `control_writes` is `brain.memory.digest.Correction`, which has two members and no third,
    so the one thing this control cannot express is a removal.
    """

    memory_id: str
    change: Change
    control_writes: Correction
    learned_at: datetime


@dataclass(frozen=True)
class TierTwoRow:
    """One proposed rule, its shadow evidence, and whether the promote control is live.

    `evidence` is signal kinds and nothing else. Occurrences carry conversation ids, and a
    row listing them would tell an administrator whose conversations produced a rule, which is
    `brain.memory.digest.EVIDENCE_NAMES_WHAT_WAS_NOTICED_AND_NEVER_WHOSE_CONVERSATION_IT_WAS`.
    `promote_ready` is `brain.memory.tiers.may_promote`'s answer, so the count stays where the
    counting rule is and only the verdict crosses to the screen.
    """

    memory_id: str
    change: Change
    evidence: tuple[Signal, ...]
    promote_ready: bool
    learned_at: datetime


@dataclass(frozen=True)
class TierThreeRouting:
    """Where one gated change went, and how a reader gets back here (M39.4.2.4).

    Carries a department and a key, never a URL: a link built here would be a second opinion
    about how this console is addressed, and the one place it is wrong is an email.
    """

    memory_id: str
    department: str
    back_to: str


#: How a tier-three routing points back at the agent it came from. A key, not an address.
BACK_LINK: Final = "agent:{agent_id}/learning"


def tier_one_rows(
    learnings: Sequence[Learning],
    *,
    agent_id: str,
) -> tuple[TierOneRow, ...]:
    """Every automatic change this agent made, newest first (M39.4.2.2).

    Newest first, which is the opposite of the review queue and for the opposite reason: these
    have already happened, so the one somebody wants to undo is the one that just changed an
    answer they were reading.

    `control_writes` is `SUPERSEDED` when there is an earlier memory to restore and `DEMOTED`
    when there is not, which is the same rule `brain.memory.digest.undo` applies, read off the
    same field rather than decided again here.
    """
    found = [
        one for one in learnings if one.agent_id == agent_id and one.proposal.tier is Tier.AUTOMATIC
    ]
    return tuple(
        TierOneRow(
            memory_id=one.memory_id,
            change=one.proposal.change,
            control_writes=(Correction.SUPERSEDED if one.replaced_id else Correction.DEMOTED),
            learned_at=one.formation.formed_at,
        )
        for one in sorted(
            found, key=lambda one: (-one.formation.formed_at.timestamp(), one.memory_id)
        )
    )


def tier_two_rows(
    learnings: Sequence[Learning],
    *,
    agent_id: str,
    occurrences: Mapping[str, Sequence[Occurrence]] | None = None,
    now: datetime,
    agreement: int = PROMOTION_AGREEMENT,
) -> tuple[TierTwoRow, ...]:
    """Every proposed rule, with its evidence and whether it may be promoted (M39.4.2.3).

    `occurrences` maps a memory id to the occurrences counted for it. Absent, the promote
    control is not live, which is the correct default: a rule with no recorded agreement has
    none, and defaulting the other way would make a missing lookup read as consensus.

    The counting is `brain.memory.tiers.may_promote`'s, so independence stays defined in one
    place and this surface only carries the verdict across.
    """
    counted = occurrences or {}
    found = [
        one for one in learnings if one.agent_id == agent_id and one.proposal.tier is Tier.PROMOTED
    ]
    rows: list[TierTwoRow] = []
    for one in sorted(found, key=lambda one: (one.formation.formed_at, one.memory_id)):
        seen = counted.get(one.memory_id, ())
        rows.append(
            TierTwoRow(
                memory_id=one.memory_id,
                change=one.proposal.change,
                evidence=tuple(sorted(one.evidence)),
                promote_ready=may_promote(one.proposal, list(seen), now=now, agreement=agreement),
                learned_at=one.formation.formed_at,
            )
        )
    return tuple(rows)


def tier_three_routing(
    learnings: Sequence[Learning],
    *,
    agent_id: str,
) -> tuple[TierThreeRouting, ...]:
    """Where each gated change goes, and the way back (M39.4.2.4).

    Routed by the department the learning's own scope names. A gated change whose scope names
    no department is refused rather than routed: the only queue left is everybody's, and a
    scope widening in everybody's queue is a scope widening nobody owns.

    Nothing here approves, applies or queues anything. It says which queue a change belongs in
    and how a reader gets back to the agent, which is the whole of the leaf.
    """
    routed: list[TierThreeRouting] = []
    for one in learnings:
        if one.agent_id != agent_id or one.proposal.tier is not Tier.GATED:
            continue
        department = _department_of(one.formation.scope)
        if not department:
            msg = (
                f"{one.memory_id} is a gated change whose scope names no department, so the "
                "only queue left is everybody's, and a scope widening in everybody's queue "
                "is a scope widening nobody owns"
            )
            raise MemoryViewError(msg)
        routed.append(
            TierThreeRouting(
                memory_id=one.memory_id,
                department=department,
                back_to=BACK_LINK.format(agent_id=agent_id),
            )
        )
    return tuple(routed)


def _department_of(scope: Scope) -> str:
    """The one department a scope names, or an empty string.

    Equality clauses only, which is `brain.memory.formation._place_of`'s rule and holds here
    for the same reason: a scope saying "department in (a, b)" names two queues and not one,
    and picking either would be this module deciding where somebody's access change is
    reviewed.
    """
    for clause in scope.clauses:
        if clause.field == "department" and clause.op is Op.EQ and isinstance(clause.value, str):
            return clause.value
    return ""


# ------------------------------------------------------------------------------ the gaps


#: Field names that would put a count of hidden things on a block or a listing here.
#:
#: The same failure `brain.memory.digest.COUNTING_FIELD_NAMES` names, restated for the shapes
#: in this module rather than imported, because the words somebody reaches for differ by
#: surface: a ceiling block grows `withheld` and `hidden`, where a listing grows `total`.
COUNTING_NAMES: Final[frozenset[str]] = frozenset(
    {
        "count",
        "hidden",
        "hidden_count",
        "more",
        "of_total",
        "remaining",
        "showing",
        "total",
        "withheld",
    }
)


def reach_view_gaps() -> tuple[str, ...]:
    """Everything about this module that would let a screen say the wrong one of two things.

    Seven checks. Every one of them is a review comment that would otherwise survive exactly
    as long as the reviewer remembers it, and every one is about a specific edit somebody
    would make for a good reason.
    """
    gaps: list[str] = []

    # 1. The ceiling narrowed by the reader. The single most likely edit on this surface,
    # because it looks like a privacy improvement and produces the collapse.
    taken = set(inspect.signature(ceiling_block).parameters)
    for forbidden in ("caller", "narrow", "intersect", "run", "e_run", "filtered"):
        if forbidden in taken:
            gaps.append(
                f"ceiling_block takes {forbidden}, so the ceiling can be computed at "
                "somebody's own reach and the screen shows E_run under the ceiling's heading"
            )

    # 2. The availability block growing a reach. It is the block a person opens when asking
    # "why can they not do this", and the answer is on the other block.
    audience_fields = {one.name for one in fields(AvailabilityBlock)}
    for forbidden in ("capabilities", "capability", "ceiling", "entitlement", "tools", "reach"):
        if forbidden in audience_fields:
            gaps.append(
                f"AvailabilityBlock carries {forbidden}, so discovery and authority are one "
                "block again and the copy on it is contradicted by the field beside it"
            )

    # 3. The preview taking something it could answer from instead of running the gate.
    preview_taken = set(inspect.signature(run_preview).parameters)
    for forbidden in ("tools", "catalogue", "estimate", "expected", "sample", "assume"):
        if forbidden in preview_taken:
            gaps.append(
                f"run_preview takes {forbidden}, so a preview can be answered without the "
                "gate and the screen is a second projector nobody can check"
            )

    # 4. The freeze growing an exception.
    freeze_taken = set(inspect.signature(freeze).parameters)
    for forbidden in ("tier", "tiers", "only", "except_", "keep"):
        if forbidden in freeze_taken:
            gaps.append(
                f"freeze takes {forbidden}, so the one control during an incident is a "
                "decision about which learning matters, made when it cannot be made well"
            )

    # 5. Every shape here, against the counting names.
    for model in (
        AvailabilityBlock,
        CeilingBlock,
        RunPreview,
        LeashMatrix,
        SplitMemoryView,
        SeparateMemoryView,
        TierTwoRow,
    ):
        for one in fields(model):
            if one.name in COUNTING_NAMES:
                gaps.append(
                    f"{model.__name__} carries {one.name}, which beside a filtered value is "
                    "the number of things this reader may not see"
                )

    # 6. The two-approver set against the effect order it was written from. Written out rather
    # than derived so that this comparison is not a value against itself; checked here so the
    # two cannot drift apart in silence.
    from_order = frozenset(SIDE_EFFECT_ORDER[SIDE_EFFECT_ORDER.index(SideEffect.SEND) :])
    if from_order != IRREVERSIBLE:
        gaps.append(
            "the effects needing two approvers are no longer the ones at or above SEND in "
            "SIDE_EFFECT_ORDER, so a rung over an irreversible target can rise on one "
            "signature or a reversible one needs two for no reason"
        )

    # 7. The headings, which are what the reader actually reads. Distinct, or the two
    # questions are one question with two paragraphs under it.
    headings = (AVAILABILITY_HEADING, CEILING_HEADING, PREVIEW_HEADING)
    if len(set(headings)) != len(headings):
        gaps.append(
            "two blocks share a heading, so a reader has no way to tell which question the "
            "value under it answers, which is the whole failure this surface is built around"
        )

    return tuple(gaps)
