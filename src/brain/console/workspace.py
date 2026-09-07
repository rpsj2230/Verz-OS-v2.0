"""Inside one agent: what it is assembled from, what its front page may say, and to whom.

The roster answers "which agents are there". This answers the question asked immediately
afterwards and nobody has a place for: open one, and see what it is made of and what it has
been costing. `brain.agents.model` holds the record, `brain.agents.template` holds the
install and its overlay, `brain.ops.spend` holds the money. None of them says what a person
may be shown when those are put on one page together, and that is the only question here.

**An agent is a lens, so its workspace is read through the caller and never through the
agent.** `E_run(caller, agent) = E(caller) ∩ agent_ceiling`. Two people opening the same
agent see different workspaces, and neither sees anything the ceiling excludes. Nothing in
this module computes that intersection: `brain.gate.leash` and `brain.ops.automation`
already call the one `EntitlementSet.intersect` there is, `brain.console.reads.audience` is
the console's own call into it, and a third would be a third place for the central rule to
be subtly wrong. `workspace_gaps` parses this module's own source through `intersections_in`
and reports any such call, so the absence is a check rather than a habit. See
`THE_WORKSPACE_NARROWS_NOTHING_AND_IS_HANDED_A_REACH`.

**A tab strip is where DENIED and ABSENT come apart, and it does so in words rather than in
digits.** A heading reading Memory with nothing under it is a count of hidden things spelled
out: it tells the reader this agent has a memory they may not read. So a tab the caller
cannot read and a tab with nothing in it are one absence, `tab_strip` takes both and returns
one value, and there is nowhere in the return for a total. This is `screens.grouped`'s rule
about empty sections applied one level down, and `screens.navigation`'s rule about a second
return value applied unchanged.

**A deep link is the same disclosure with a URL in front of it.** M39.1.2.4 wants an alert to
point at the exact place, which means an address for every tab, which means an address a
person can also type. A link that says "not found" for an agent that does not exist and
"forbidden" for one they may not see has disclosed the agent. `resolve` answers `None` to
every one of the five ways it can fail and carries no field a reason could be put in. See
`A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE`.

**Cost on the front page is a disclosure surface, and the giveaway is that the figure moves
when somebody else works.** An agent shared by a department accumulates spend from everybody
who uses it, so "£40 this month" read by somebody who spent £10 is a statement about the
other £30. The line drawn here is that the front page may not be a shortcut past a screen's
grant: a reader sees everybody's figures exactly when they could open the budget screen and
read them there, and otherwise sees their own. `basis_for` asks `brain.console.reads.
permitted` about that screen's own read rather than inventing a capability for the front
page. See `A_FIGURE_THAT_MOVES_WHEN_SOMEBODY_ELSE_WORKS_IS_THEIR_ACTIVITY`.

**The projection is the sharpest case of it and is withheld rather than narrowed.** A
projection to month end needs spend to date against the agent's ceiling. The ceiling belongs
to nobody, as `brain.ops.budgets` says, and is safe to show; the spend to date is everybody
who ran the agent, and the headroom is that subtraction already performed. Narrowing the
projection to the reader's own spend would produce a confident figure that is wrong, which is
worse than no figure, so `projection` returns `None` on the narrower basis instead. That is
`brain.ops.spend.A_REFUSAL_CARRIES_NO_FIGURE` in the reporting direction.

**Five of the ten parts an agent is composed of are not in its template at all**, which is
why the divergence flag is smaller than it looks: channels, memory, automations, availability
and the knowledge predicate are supplied by the install, so an instance cannot diverge from
its template on any of them. A sixth, the leash, is in the manifest and sealed, so it cannot
diverge either. `PARTS_THAT_CAN_DIVERGE` is the four that are left, derived rather than
listed, so the day `SEALED_PATHS` changes this changes with it.

**Rejected: a second diff between an instance and its template.** `brain.agents.upgrade`
already walks `MANIFEST_PATHS` and produces the three columns M13.4.3 asks for, with the
overlay's own owner on each row. What was missing was not a diff, it was the map from a
manifest path to the part of the composition it supplies, which is one mapping and is here.
M39.1.1.5 wants that diff rendered side by side and is not claimed: the rows exist and no
screen renders them.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock;
`now` is a parameter for the reason `brain.ops.limits` gives about policy that owns a client.

**This declares the surface and builds none of it.** There is no console screen behind any of
the thirty-four `brain.console.screens` declares, and there is none behind this either. The
four ranges M39.1.3.2 asks a selector for are declared as `Range`; the selector is a control
and is not claimed. Nor are the header, the right pane and the keyboard map: each is a
rendered thing, and a leaf claimed for a type nobody renders would have the traceability
sweep counting a page nobody can open.

Task ids: M39.1.1.1, M39.1.1.2, M39.1.1.4, M39.1.2.2, M39.1.2.4, M39.1.3.1, M39.1.3.3, M39.1.3.4
"""

from __future__ import annotations

import ast
import enum
import inspect
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from brain.agents.model import AgentRecord
from brain.agents.template import MANIFEST_PATHS, SEALED_PATHS, TemplateInstance
from brain.chat.turns import Turn, TurnKind
from brain.console.reads import ConsoleRead, Plane, permitted
from brain.console.screens import SCREENS, screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.ops.budgets import DAYS_IN_BUDGET_MONTH, Allowance
from brain.ops.jobs import hidden_count_fields
from brain.ops.spend import Actual, Dimension, spend_by, total_minor

# ------------------------------------------------------------------ written-down reasons
#: Why no function here intersects two entitlement sets.
THE_WORKSPACE_NARROWS_NOTHING_AND_IS_HANDED_A_REACH: Final = (
    "E_run(caller, agent) = E(caller) intersect agent_ceiling is computed in one place, by "
    "EntitlementSet.intersect, which brain.gate.leash.decide and ops.automation.flow_reach "
    "both call and neither reimplements. A workspace that worked out its own reach would be "
    "a third copy of the central rule, and the copy that is subtly wrong is the one in "
    "production. Everything here is handed a reach and filters at it, and intersections_in "
    "reads this module's own source so that the absence is checked rather than remembered."
)

#: Why a tab with nothing in it is not shown as empty.
A_TAB_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS: Final = (
    "A heading reading Memory above an empty pane tells the reader this agent has a memory "
    "they may not read, which is the disclosure by subtraction spelled out instead of "
    "counted. A tab the caller holds no grant for and a tab with nothing in it are "
    "therefore one absence: tab_strip takes both and returns the tabs, and there is no "
    "second value beside them for what it left out."
)

#: Why every refusal on a deep link is the same refusal.
A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE: Final = (
    "An address for every tab is an address a person can type as well as follow, and five "
    "things can be wrong with one: the link is malformed, the tab is not a tab, the agent "
    "is not one this person may see, the tab is one they hold no grant for, and the tab is "
    "empty. Answering those differently turns the address bar into a way of asking which "
    "agents exist. resolve answers None to all five and Landing has no field a reason "
    "could be written into."
)

#: Why an attachment is a reference and never a copy of the thing.
AN_ATTACHMENT_IS_A_REFERENCE_AND_A_COPY_IS_A_FORK: Final = (
    "A skill copied onto an agent stops being the skill in the library the moment either "
    "changes, and nothing says which of the two a run used. Worse, a copy is a copy of a "
    "body somebody approved, so brain.tools.skills.is_executable answers about the original "
    "while the agent runs the duplicate. Attachment carries a reference and a version and "
    "has no field a body, a document or a payload could arrive in."
)

#: Why a version that can move is refused outright.
A_PIN_THAT_MOVES_IS_NOT_A_PIN: Final = (
    "latest, main, head and a bare star all read as a version and all resolve to whatever "
    "is there on the day the run happens, so the review that approved the attachment "
    "approved a moment rather than a thing. brain.tools.skills.SkillSource refuses a branch "
    "for the same reason and in the same words, and this refuses the same set of spellings "
    "one level up, where the attachment rather than the import is being written."
)

#: Why the front page's figures follow a screen's grant rather than a new one.
A_FIGURE_THAT_MOVES_WHEN_SOMEBODY_ELSE_WORKS_IS_THEIR_ACTIVITY: Final = (
    "Spend, runs and messages on a shared agent accumulate from everybody who used it, so a "
    "headline figure read by one person is mostly a statement about the others: forty pounds "
    "seen by somebody who spent ten is thirty pounds of somebody else's afternoon. The front "
    "page may not be a shortcut past a screen's grant, so a reader sees everybody's figures "
    "exactly when they could open the budget screen and read them there, and otherwise sees "
    "their own. No capability is invented for the front page, because a new capability is a "
    "second answer to a question the screen registry already answers."
)

#: Why there is no row for everybody the reader may not name.
AN_OTHERS_ROW_IS_EVERYBODY_ELSE_ADDED_UP: Final = (
    "Attribution per caller is what makes one heavy user visible, and the obvious way to "
    "keep the column totalling correctly is a final row reading other. That row is the "
    "spend of every person the reader may not be told about, which is the subtraction "
    "disclosure with a label on it, and two readings of it a week apart are that group's "
    "activity over the week. by_caller returns the callers it may name and no remainder."
)

#: Why a projection is withheld rather than computed on the narrower basis.
A_PROJECTION_IS_MADE_OF_EVERYBODY_ELSES_SPEND: Final = (
    "A projection to month end is spend to date extrapolated against the agent's own "
    "ceiling. The ceiling belongs to nobody and is safe to show; the spend to date is every "
    "person who ran the agent, and the headroom beside it is that subtraction already "
    "performed. Projecting the reader's own spend against a shared ceiling would produce a "
    "confident figure that is wrong, which is worse than no figure, so the projection is "
    "absent on the narrower basis rather than narrowed."
)

#: Why the divergence flag covers four parts and not ten.
A_DIVERGENCE_FLAG_ONLY_FIRES_ON_WHAT_THE_TEMPLATE_SUPPLIES: Final = (
    "Five of the ten parts are not in a manifest at all: channels, memory, automations, "
    "availability and the knowledge predicate are decided by the install, so there is "
    "nothing for an instance to disagree with. The leash is in the manifest and is sealed, "
    "so an overlay may not carry it and it cannot diverge either. Four parts are left, and "
    "they are derived from MANIFEST_PATHS and SEALED_PATHS rather than listed, so a change "
    "to either moves this without anybody remembering to."
)


class WorkspaceError(Exception):
    """A workspace was described in a shape that would show somebody the wrong thing.

    Outside `brain.core.errors` for the reason `brain.agents.model.AgentError` gives about
    itself: those five outcomes describe an answer given to a person asking a question, and
    this is a refusal to assemble a surface. Nobody asking a question ever sees one.
    """


# ------------------------------------------------------------- the composition (M39.1.1)
class Part(enum.StrEnum):
    """The ten things an agent is composed of (M39.1.1.1).

    Exactly the ten the work breakdown names, and the enum is the list rather than a comment
    beside one: a part nothing enumerates is a part the workspace has no tab, no diff row and
    no divergence flag for, and it goes missing without anything failing.
    """

    PERSONA = "persona"
    KNOWLEDGE = "knowledge"
    CONNECTORS = "connectors"
    SKILLS = "skills"
    CHANNELS = "channels"
    AVAILABILITY = "availability"
    LEASH = "leash"
    MODEL_POLICY = "model_policy"
    MEMORY = "memory"
    AUTOMATIONS = "automations"


class Supply(enum.StrEnum):
    """How a part reaches an agent, which is what decides whether it can be pinned.

    Four rather than two, because the two obvious ones do not fit the ten. A predicate is
    not a reference: `brain.knowledge.visibility` narrows by matching a scope, and there is
    no item to pin a version of. A rung is neither: `brain.gate.leash` holds entries keyed by
    agent and target, and pinning a version of a supervision decision means nothing.
    """

    #: A field on the agent record. `COLUMN_FIELD` names which.
    COLUMN = "column"
    #: A `brain.core.scope.Scope`. See M39.2.3.1: a predicate, never a document list.
    PREDICATE = "predicate"
    #: A reference to something with its own life and its own version. See `Attachment`.
    PINNED = "pinned"
    #: A rung per target, held by `brain.gate.leash` rather than by the agent.
    RUNG = "rung"


#: How each part reaches an agent. Exhaustive over `Part`, checked by `workspace_gaps`.
#:
#: Written as data rather than derived from anything, because the classification is an
#: argument about each part rather than a fact about its name, and a derivation would be
#: that argument hidden inside a rule.
SUPPLY: Mapping[Part, Supply] = MappingProxyType(
    {
        Part.PERSONA: Supply.COLUMN,
        Part.MODEL_POLICY: Supply.COLUMN,
        Part.AVAILABILITY: Supply.COLUMN,
        Part.KNOWLEDGE: Supply.PREDICATE,
        Part.CONNECTORS: Supply.PINNED,
        Part.SKILLS: Supply.PINNED,
        Part.CHANNELS: Supply.PINNED,
        Part.MEMORY: Supply.PINNED,
        Part.AUTOMATIONS: Supply.PINNED,
        Part.LEASH: Supply.RUNG,
    }
)

#: Which field of `AgentRecord` supplies each column part.
#:
#: Named rather than assumed, and checked against `AgentRecord.model_fields` rather than
#: against a list here: a column part naming a field the record does not have is a workspace
#: rendering a blank where a person expects the agent's own decision.
COLUMN_FIELD: Mapping[Part, str] = MappingProxyType(
    {
        Part.PERSONA: "persona",
        Part.MODEL_POLICY: "tier",
        Part.AVAILABILITY: "audience",
    }
)

#: The parts an attachment can be written for. Derived, so adding a pinned part is one edit.
PINNED_PARTS: Final[frozenset[Part]] = frozenset(
    part for part, supply in SUPPLY.items() if supply is Supply.PINNED
)

#: Field names that would make an attachment a copy. See
#: `AN_ATTACHMENT_IS_A_REFERENCE_AND_A_COPY_IS_A_FORK`. Names rather than a rule about
#: values, because the failure arrives as a field somebody adds to save a lookup.
NAMES_THAT_WOULD_BE_AN_INLINE_COPY: Final[frozenset[str]] = frozenset(
    {"body", "content", "document", "inline", "payload", "script", "source_text", "text"}
)

#: Versions that resolve to whatever is there on the day. See `A_PIN_THAT_MOVES_IS_NOT_A_PIN`.
MOVING_PINS: Final[frozenset[str]] = frozenset({"latest", "main", "master", "head", "*", "current"})


@dataclass(frozen=True)
class Attachment:
    """One thing attached to an agent: which part, which thing, which version (M39.1.1.2).

    Three fields and no fourth. There is no body, no document and no payload, which is
    `AN_ATTACHMENT_IS_A_REFERENCE_AND_A_COPY_IS_A_FORK` expressed as a shape rather than as
    a rule somebody keeps, and `workspace_gaps` reports one if a later edit adds it.
    """

    part: Part
    #: What is attached, by its own identifier: a connector name, a skill name, a channel.
    ref: str
    #: The exact version of it. A digest, a semantic version or an integer, as a string,
    #: because the three kinds of thing pinned here spell a version three different ways and
    #: a type that admitted only one of them would be a type five parts cannot use.
    version: str

    def __post_init__(self) -> None:
        if self.part not in PINNED_PARTS:
            msg = (
                f"{self.part} is supplied as {SUPPLY[self.part].value} and cannot be "
                "attached; an attachment of it would be a second copy of a thing the record "
                "already carries, and which of the two a run used would be unanswerable"
            )
            raise WorkspaceError(msg)
        if not self.ref.strip():
            msg = f"an attachment to {self.part} names nothing, so nothing can be resolved"
            raise WorkspaceError(msg)
        if not self.version.strip():
            msg = (
                f"attachment {self.ref!r} carries no version, so what a run used is whatever "
                f"was there at the time. {A_PIN_THAT_MOVES_IS_NOT_A_PIN}"
            )
            raise WorkspaceError(msg)
        if self.version.strip().lower() in MOVING_PINS:
            msg = (
                f"attachment {self.ref!r} is pinned to {self.version!r}. "
                f"{A_PIN_THAT_MOVES_IS_NOT_A_PIN}"
            )
            raise WorkspaceError(msg)


@dataclass(frozen=True)
class Composition:
    """What one agent is assembled from, as this reader may see it (M39.1.1.1).

    Carries the attachments handed in and nothing about the ones that were not. An
    attachment outside the reader's reach and an attachment nobody made produce the same
    workspace, which is `brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER`
    one level in.
    """

    agent_id: str
    attachments: tuple[Attachment, ...] = ()

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            msg = "a composition of no agent is not a composition"
            raise WorkspaceError(msg)
        seen: set[tuple[Part, str]] = set()
        for one in self.attachments:
            key = (one.part, one.ref)
            if key in seen:
                msg = (
                    f"{one.ref!r} is attached to {one.part} twice, so which version a run "
                    "resolves is whichever the reader iterated first"
                )
                raise WorkspaceError(msg)
            seen.add(key)

    def attached_to(self, part: Part) -> tuple[Attachment, ...]:
        """The attachments for one part, in the order they were given."""
        return tuple(one for one in self.attachments if one.part is part)

    @property
    def pinned_parts(self) -> frozenset[Part]:
        """The parts this reader can see something attached for."""
        return frozenset(one.part for one in self.attachments)


def compose(record: AgentRecord, attachments: Iterable[Attachment] = ()) -> Composition:
    """One agent's composition, at whatever reach produced `attachments` (M39.1.1.1).

    Takes the record for its id and reads nothing else off it, because the parts the record
    supplies are supplied by being on it: `COLUMN_FIELD` says which field each is, and there
    is no copying of a persona into a workspace object that could then disagree with the row.
    """
    return Composition(agent_id=record.agent_id, attachments=tuple(attachments))


def record_columns(record: AgentRecord) -> Mapping[Part, object]:
    """The parts the record itself supplies, read off it by `COLUMN_FIELD`.

    Returns the values rather than the names, so a caller rendering the header has the
    agent's own decisions without a second lookup, and so that a field renamed on the record
    fails here rather than rendering an empty pane.
    """
    return MappingProxyType({part: getattr(record, field) for part, field in COLUMN_FIELD.items()})


# ---------------------------------------------------------------- divergence (M39.1.1.4)
#: Which composition part each manifest path supplies.
#:
#: The keys are `brain.agents.template.MANIFEST_PATHS`, so this cannot name a path the
#: manifest does not have, and `workspace_gaps` refuses a path that is in neither this nor
#: `PATHS_THAT_ARE_NOT_COMPOSITION`.
PART_OF_PATH: Mapping[str, Part] = MappingProxyType(
    {
        "persona": Part.PERSONA,
        "connectors": Part.CONNECTORS,
        "skills": Part.SKILLS,
        "tier": Part.MODEL_POLICY,
        "guardrails.leash": Part.LEASH,
    }
)

#: Manifest paths that are not composition at all, declared rather than left out.
#:
#: Identity is the agent's name and lineage, authority is its ceiling, and the golden set and
#: the placeholders are the template's own apparatus. None of the four is a thing the agent
#: is assembled from, and saying so here is what lets `workspace_gaps` insist the two sets
#: cover `MANIFEST_PATHS` exactly. A path that fell out of both would be a divergence nothing
#: flags, which is the failure this pair exists to make impossible.
PATHS_THAT_ARE_NOT_COMPOSITION: Final[frozenset[str]] = frozenset(
    {
        "authority.allowed_tools",
        "authority.capabilities",
        "authority.required_tools",
        "authority.scope",
        "golden_set",
        "guardrails.max_side_effect",
        "identity.display_name",
        "identity.published_by",
        "identity.summary",
        "identity.template_id",
        "identity.version",
        "placeholders",
    }
)

#: The parts no template supplies, so no instance can diverge on them.
PARTS_NO_TEMPLATE_SUPPLIES: Final[frozenset[Part]] = frozenset(Part) - frozenset(
    PART_OF_PATH.values()
)

#: The parts a divergence flag can actually fire on. See
#: `A_DIVERGENCE_FLAG_ONLY_FIRES_ON_WHAT_THE_TEMPLATE_SUPPLIES`. Derived from both of the
#: template module's own tuples, so sealing a sixth path removes a part from here.
PARTS_THAT_CAN_DIVERGE: Final[frozenset[Part]] = frozenset(
    part for path, part in PART_OF_PATH.items() if path not in SEALED_PATHS
)


def divergent_parts(instance: TemplateInstance) -> frozenset[Part]:
    """The parts this install has edited that its template supplies (M39.1.1.4).

    Read off `instance.overlay`, which is the same place `brain.agents.upgrade._diff` reads
    what was claimed locally, and deliberately not off `overlay_owners`: that module records
    why, and the short version is that an ownership row is metadata a bad write can forge
    while the overlay is the value a run actually uses.

    A path outside `PART_OF_PATH` is not a divergence of the composition. It may still be a
    local edit worth reviewing, which is `brain.agents.upgrade.review`'s job and not this
    one's; the flag here is per part because the workspace is arranged by part.
    """
    return frozenset(PART_OF_PATH[path] for path in instance.overlay if path in PART_OF_PATH)


# ------------------------------------------------------------------ the tab strip (M39.1.2)
class Tab(enum.StrEnum):
    """The seven tabs of an agent's workspace, in the order M39.1.2.2 lists them."""

    CONVERSATIONS = "conversations"
    AUTOMATIONS = "automations"
    PEOPLE = "people"
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    ARTIFACTS = "artifacts"
    SETTINGS = "settings"


#: The audit row a tab's read names itself as. A prefix rather than a bare tab name, because
#: `screens.SCREENS` already holds a screen called `people` and an audit row that could mean
#: either is an audit row nobody can follow.
TAB_SCREEN_PREFIX: Final = "agent_workspace."

#: The only return annotation `tab_strip` may carry. The same construction
#: `screens.ONLY_THE_SCREENS` uses, and for the same reason: the list of ways to spell "and
#: also what I hid" is open and the list of acceptable return types has one entry.
ONLY_THE_TABS: Final = "tuple[WorkspaceTab, ...]"


@dataclass(frozen=True)
class WorkspaceTab:
    """One tab: what reading it needs, and what it is for.

    `read` is a `ConsoleRead` for the reason every screen's is: a tab's content is a tool
    call at the caller's own reach, and this module refuses to be a second way of saying
    what one of those is.
    """

    tab: Tab
    read: ConsoleRead
    #: One sentence, so somebody explaining the workspace has words to use.
    purpose: str

    def __post_init__(self) -> None:
        expected = f"{TAB_SCREEN_PREFIX}{self.tab.value}"
        if self.read.screen != expected:
            msg = (
                f"the {self.tab} tab is wired to a read that audits itself as "
                f"{self.read.screen!r} rather than {expected!r}, so the audit row names a "
                "place nobody can navigate to"
            )
            raise WorkspaceError(msg)
        if not self.purpose.strip():
            msg = f"the {self.tab} tab has no purpose sentence, so its heading explains nothing"
            raise WorkspaceError(msg)


def _tab(tab: Tab, tool: str, capability: str, plane: Plane, purpose: str) -> WorkspaceTab:
    return WorkspaceTab(
        tab=tab,
        read=ConsoleRead(
            screen=f"{TAB_SCREEN_PREFIX}{tab.value}",
            tool=tool,
            requires=Capability(value=capability),
            plane=plane,
        ),
        purpose=purpose,
    )


#: Every tab, in the order of the strip. A tuple rather than a mapping, because the order is
#: information: it is the order somebody reads the strip in.
#:
#: **Every capability here is one a screen already requires**, which `workspace_gaps` checks
#: against `screens.SCREENS`. A tab needing a capability no screen names would be a new grant
#: invented by a tab, reachable from a workspace and from nowhere an administrator reviews.
TABS: Final[tuple[WorkspaceTab, ...]] = (
    _tab(
        Tab.CONVERSATIONS,
        "console.questions",
        "read:question",
        Plane.CONTENT,
        "What was asked of this agent and what it answered, at the reader's own reach.",
    ),
    _tab(
        Tab.AUTOMATIONS,
        "console.queue",
        "read:queue",
        Plane.CONFIGURATION,
        "What this agent runs on a schedule, what it last did and what is next.",
    ),
    _tab(
        Tab.PEOPLE,
        "console.people",
        "read:grant",
        Plane.CONFIGURATION,
        "Who can find and start this agent, which is discovery and never authority.",
    ),
    _tab(
        Tab.KNOWLEDGE,
        "console.library",
        "read:document",
        Plane.EXISTENCE,
        "What this agent draws on, as a predicate rather than as a list of documents.",
    ),
    _tab(
        Tab.MEMORY,
        "console.memory",
        "read:memory",
        Plane.CONTENT,
        "What this agent has been told to remember, and every change to it.",
    ),
    _tab(
        Tab.ARTIFACTS,
        "console.artifacts",
        "read:artifact",
        Plane.EXISTENCE,
        "What this agent produced, with what each was built from and when it goes.",
    ),
    _tab(
        Tab.SETTINGS,
        "console.agents",
        "read:agent",
        Plane.CONFIGURATION,
        "The agent's own decisions: persona, model policy, ceiling and leash.",
    ),
)

#: How many tabs there are, pinned so a test can hold it and a person can quote it. Pinned
#: rather than computed at the call site, for the reason `screens.SCREEN_COUNT` is.
TAB_COUNT: Final = 7


def tab(key: Tab) -> WorkspaceTab:
    """One tab by its key, or a failure naming it."""
    for one in TABS:
        if one.tab is key:
            return one
    msg = f"no tab named {key!r}"
    raise KeyError(msg)


def tab_strip(
    entitlement: EntitlementSet,
    *,
    populated: Iterable[Tab] = (),
    now: Any = None,
) -> tuple[WorkspaceTab, ...]:
    """The strip this caller sees on this agent: permitted and not empty (M39.1.2.2).

    Two conditions and one answer. A tab the caller holds no grant for and a tab with
    nothing in it are the same absence, which is
    `A_TAB_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS`, and the conjunction is what
    makes them indistinguishable rather than merely both hidden.

    `populated` is handed in rather than worked out here, because what is in a tab is seven
    different questions of seven different modules, and a function that asked all seven
    would be the second data path `brain.console.reads` exists to refuse.

    Returns one value. A second one carrying what was withheld would be the count this
    module is built not to publish, and `workspace_gaps` reads this signature to say so.
    """
    has_something = frozenset(populated)
    return tuple(
        one for one in TABS if one.tab in has_something and permitted(one.read, entitlement, now)
    )


# ----------------------------------------------------------------- deep links (M39.1.2.4)
#: The address every tab has. One prefix, so a link is recognisable as one before it is
#: parsed and a malformed link is refused rather than half-read.
DEEP_LINK_PREFIX: Final = "/agents/"

#: An agent and a tab, which is what a workspace address addresses.
_LINK_SEGMENTS: Final = 2


@dataclass(frozen=True)
class Landing:
    """Where a deep link lands: one agent, one tab, and nothing about why not.

    **No field could carry a reason.** No `refused`, no `because`, no `state`. A refusal that
    said which of the five things was wrong would answer the question the address bar was
    being used to ask. See `A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE`.
    """

    agent_id: str
    tab: WorkspaceTab


def deep_link(agent_id: str, key: Tab) -> str:
    """The address of one tab of one agent (M39.1.2.4)."""
    if not agent_id.strip():
        msg = "a deep link to no agent is not an address"
        raise WorkspaceError(msg)
    return f"{DEEP_LINK_PREFIX}{agent_id}/{key.value}"


def resolve(
    link: str,
    entitlement: EntitlementSet,
    *,
    visible_agents: Iterable[str],
    populated: Iterable[Tab] = (),
    now: Any = None,
) -> Landing | None:
    """Where this link lands for this caller, or `None` (M39.1.2.4).

    `None` for all five failures, and the sameness is the point rather than a convenience:
    a malformed link, an unknown tab, an agent outside this person's audience, a tab they
    hold no grant for and a tab with nothing in it are one answer. See
    `A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE`.

    `visible_agents` is `brain.agents.model.visible_agent_ids`' own output, so the audience
    question is answered by the module that owns it and not re-derived from an id's shape.
    """
    if not link.startswith(DEEP_LINK_PREFIX):
        return None
    parts = link[len(DEEP_LINK_PREFIX) :].split("/")
    # An address is an agent and a tab. A third segment addresses something that does not
    # exist here and a shorter one names no tab, and both are the same answer as the rest.
    if len(parts) != _LINK_SEGMENTS:
        return None
    agent_id, wanted = parts
    if agent_id not in frozenset(visible_agents):
        return None
    for one in tab_strip(entitlement, populated=populated, now=now):
        if one.tab.value == wanted:
            return Landing(agent_id=agent_id, tab=one)
    return None


# ------------------------------------------------------------ cost on the front page (M39.1.3)
class Range(enum.StrEnum):
    """The four windows the front page offers.

    The three fixed lengths and month to date, which is the odd one and the reason this is
    not a number of days: a month to date window shortens to nothing on the first of the
    month, and a figure that resets while a budget does not is the figure somebody reads as
    a fall in spend.
    """

    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"
    NINETY_DAYS = "90d"
    MONTH_TO_DATE = "mtd"


#: How long each fixed range is. Month to date is absent deliberately: it has no length.
#:
#: The middle one is `brain.ops.budgets.DAYS_IN_BUDGET_MONTH` rather than a thirty written
#: here, and the longest is three of them. A month range that did not agree with the month a
#: budget is divided into would put a figure beside a ceiling the figure was not measured
#: against, and the two numbers would look comparable.
RANGE_DAYS: Mapping[Range, int] = MappingProxyType(
    {
        Range.SEVEN_DAYS: timedelta(weeks=1).days,
        Range.THIRTY_DAYS: DAYS_IN_BUDGET_MONTH,
        Range.NINETY_DAYS: 3 * DAYS_IN_BUDGET_MONTH,
    }
)


#: The one month whose successor is in the next year.
_DECEMBER: Final = 12


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month_start(now: datetime) -> datetime:
    start = _month_start(now)
    if start.month == _DECEMBER:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def window(one: Range, now: datetime) -> tuple[datetime, datetime]:
    """The instants one range covers, inclusive at both ends.

    A naive `now` is refused rather than assumed to be UTC, for the reason
    `brain.ops.spend.Actual` refuses one: a window boundary computed against a naive instant
    lands in the wrong day at either end, by however many hours the host happens to sit from
    UTC, and neither direction announces itself.
    """
    if now.tzinfo is None:
        msg = "a range computed from a naive instant is wrong by the host's offset from UTC"
        raise WorkspaceError(msg)
    if one is Range.MONTH_TO_DATE:
        return _month_start(now), now
    return now - timedelta(days=RANGE_DAYS[one]), now


class Basis(enum.StrEnum):
    """Whose figures a reader is being shown. Two, and the narrower one is the default.

    There is deliberately no third member meaning "the department's" or "everybody, rounded".
    A middle basis is the one that reads as a compromise and is a disclosure: a figure
    aggregated over a group the reader cannot enumerate still moves when one of them works.
    """

    #: The reader's own rows through this agent.
    OWN = "own"
    #: Every row, for a reader who could read them on the budget screen anyway.
    EVERYONE = "everyone"


#: The screen whose grant decides whether the front page may show everybody's figures.
#:
#: A screen key rather than a capability written out here, so that the front page cannot
#: drift from the screen: `basis_for` asks `permitted` about that screen's own read, which is
#: both the tool's capability and the console plane, exactly as opening the screen would be.
SPEND_OF_OTHERS_SCREEN: Final = "budget"


def basis_for(entitlement: EntitlementSet, now: Any = None) -> Basis:
    """Whose figures this caller may be shown on an agent's front page (M39.1.3.1).

    Asked of `brain.console.reads.permitted` against the budget screen's own read rather
    than of a capability invented here. See
    `A_FIGURE_THAT_MOVES_WHEN_SOMEBODY_ELSE_WORKS_IS_THEIR_ACTIVITY`: a front page that had
    its own grant would be a way of reading a screen's contents without the screen's grant,
    and the reviewer approving one would never see the other.
    """
    return (
        Basis.EVERYONE
        if permitted(screen(SPEND_OF_OTHERS_SCREEN).read, entitlement, now)
        else Basis.OWN
    )


def _in_window(at: datetime, since: datetime, until: datetime) -> bool:
    return since <= at <= until


def visible_actuals(
    agent_id: str,
    actuals: Sequence[Actual],
    *,
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> tuple[Actual, ...]:
    """The accounting rows this reader may be shown for this agent, in the order given.

    Three filters and no fourth: this agent, this window, and on the narrower basis this
    person. Machine rows are kept, because `brain.ops.spend` labels them rather than dropping
    them and what a report does with the label is that report's decision; an automation
    running as a named principal is that principal's spend here as it is there.
    """
    return tuple(
        row
        for row in actuals
        if row.agent_id == agent_id
        and _in_window(row.at, since, until)
        and (basis is Basis.EVERYONE or row.principal_id == caller_id)
    )


@dataclass(frozen=True)
class Headline:
    """The three figures on an agent's front page, and whose they are (M39.1.3.1).

    `basis` is carried rather than left implicit, and that is honesty rather than
    decoration: a figure whose meaning is unstated is read as the total, so a reader seeing
    their own spend with no label would read it as the agent's. Saying "these are yours"
    discloses nothing about anybody else, because the existence of other people is not a
    secret; the amounts are.

    No field here is a count of what was left out, which `workspace_gaps` asks of the type
    rather than of whoever edits it next.
    """

    agent_id: str
    basis: Basis
    spend_minor: int
    runs: int
    messages: int


def headline(
    agent_id: str,
    *,
    caller_id: str,
    basis: Basis,
    actuals: Sequence[Actual] = (),
    turns: Sequence[Turn] = (),
    since: datetime,
    until: datetime,
) -> Headline:
    """Spend, runs and messages for one agent, at one basis, over one window (M39.1.3.1).

    Spend is `brain.ops.spend.total_minor` over the rows this reader may see rather than a
    sum written here, so the front page and the budget screen cannot disagree about what a
    run cost.

    **`turns` are the agent's own and this cannot check that**, because `brain.chat.turns.
    Turn` carries a principal and an instant and no agent id, so the attribution has to
    happen before the call. What is checked here is the half that discloses: the window and
    the basis are applied to the turns exactly as they are to the accounting rows, so a
    message count cannot become the back door to the figure the spend refused.
    """
    rows = visible_actuals(
        agent_id, actuals, caller_id=caller_id, basis=basis, since=since, until=until
    )
    said = tuple(
        one
        for one in turns
        if _in_window(one.at, since, until)
        and (basis is Basis.EVERYONE or one.principal_id == caller_id)
        and one.kind is not TurnKind.ANSWER
    )
    return Headline(
        agent_id=agent_id,
        basis=basis,
        spend_minor=total_minor(rows),
        runs=len(rows),
        messages=len(said),
    )


@dataclass(frozen=True)
class CallerSpend:
    """One person's spend through one agent (M39.1.3.3).

    A principal and an amount. No share, no rank and no percentage: each of those is the
    same figure divided by a total, and a total the reader was not shown is a total they can
    recover from two of these.
    """

    principal_id: str
    spend_minor: int


def by_caller(
    agent_id: str,
    *,
    caller_id: str,
    basis: Basis,
    actuals: Sequence[Actual] = (),
    since: datetime,
    until: datetime,
) -> tuple[CallerSpend, ...]:
    """Spend attributed per caller, heaviest first (M39.1.3.3).

    Grouped by `brain.ops.spend.spend_by`, which is the function the budget screen uses, so
    that a heavy user is the same heavy user on both surfaces.

    **There is no row for everybody else**, on either basis. See
    `AN_OTHERS_ROW_IS_EVERYBODY_ELSE_ADDED_UP`. On the narrower basis this returns the
    reader's own row and nothing else, which is a list of one rather than a list of one and
    a remainder, and the difference is that the second is a number.

    Ordered by spend and then by principal, so two readings of an unchanged ledger are the
    same list; ordering by spend alone leaves ties to whatever the mapping iterated.
    """
    rows = visible_actuals(
        agent_id, actuals, caller_id=caller_id, basis=basis, since=since, until=until
    )
    totals = spend_by(rows, Dimension.PRINCIPAL)
    return tuple(
        CallerSpend(principal_id=principal, spend_minor=spent)
        for principal, spent in sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
    )


@dataclass(frozen=True)
class Projection:
    """Where this agent's month ends up against its own ceiling (M39.1.3.4).

    Three figures and a derived verdict. `spent_minor` is everybody's, which is why this
    type is only ever built on the wider basis, and why there is no field naming a caller:
    a projection attributed to somebody would be a projection of their afternoon.
    """

    agent_id: str
    spent_minor: int
    projected_minor: int
    ceiling_minor: int

    @property
    def over_ceiling(self) -> bool:
        """Whether the month ends above the agent's own budget if nothing changes."""
        return self.projected_minor > self.ceiling_minor


def projection(
    agent_id: str,
    *,
    allowance: Allowance,
    basis: Basis,
    now: datetime,
) -> Projection | None:
    """The month-end projection, or `None` when it would be somebody else's spend.

    `None` on the narrower basis, and withheld rather than narrowed. See
    `A_PROJECTION_IS_MADE_OF_EVERYBODY_ELSES_SPEND`: `Allowance.spent_minor` is every run of
    this agent by anybody, and a projection of the reader's own spend against a ceiling
    everybody shares is a confident figure that is wrong.

    Rounded up, once, as `brain.ops.budgets.MONEY_IS_COUNTED_IN_MINOR_UNITS` requires, and
    over the real calendar month rather than a fixed thirty days: the thirty in that module
    turns a monthly allowance into a daily one and is not a claim about how long March is.
    """
    if basis is not Basis.EVERYONE:
        return None
    if now.tzinfo is None:
        msg = "a projection computed from a naive instant runs off the end of the wrong month"
        raise WorkspaceError(msg)
    elapsed = (now - _month_start(now)).total_seconds()
    whole = (_next_month_start(now) - _month_start(now)).total_seconds()
    spent = allowance.spent_minor
    projected = spent if elapsed <= 0 else math.ceil(spent * whole / elapsed)
    return Projection(
        agent_id=agent_id,
        spent_minor=spent,
        projected_minor=projected,
        ceiling_minor=allowance.row.ceiling_minor,
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this surface is handed. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`: a type added to the workspace and not to this tuple is
#: a type the checks below never see.
WORKSPACE_SURFACE: Final[tuple[type, ...]] = (
    Attachment,
    Composition,
    WorkspaceTab,
    Landing,
    Headline,
    CallerSpend,
    Projection,
)


def intersections_in(source: str) -> tuple[int, ...]:
    """The lines of `source` that intersect two entitlement sets, by line number.

    Parsed rather than searched for the word, because this module's own docstring says
    `intersect` several times and a text search would report itself. `ast` sees a call and a
    comment identically, which is the difference that matters.

    Takes source rather than reading this file, so that the interesting case, a module that
    does compute its own reach, is one a test can hand it. That is the argument
    `brain.ops.starter.starter_gaps` records having learned from a mutation that survived.
    """
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if isinstance(called, ast.Attribute) and called.attr == "intersect":
            found.append(node.lineno)
    return tuple(found)


def workspace_gaps(
    *,
    supply: Mapping[Part, Supply] = SUPPLY,
    columns: Mapping[Part, str] = COLUMN_FIELD,
    composition_paths: Mapping[str, Part] = PART_OF_PATH,
    other_paths: Iterable[str] = PATHS_THAT_ARE_NOT_COMPOSITION,
    paths: Sequence[str] = MANIFEST_PATHS,
    tabs: Sequence[WorkspaceTab] = TABS,
    surface: Sequence[type] = WORKSPACE_SURFACE,
    attachment_type: type = Attachment,
    ranges: Sequence[Range] = tuple(Range),
    source: str | None = None,
) -> tuple[str, ...]:
    """Everything about this workspace that would show somebody more than they hold.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason: a diagnostic that can only be run against the healthy tree has nothing to report
    on today's data, so switching off any of its refusals changes nothing observable and
    every one of them survives. Calling it with no arguments is the deployment check and
    calling it with a constructed set is the test. `brain.ops.starter.starter_gaps` and
    `brain.ops.connections.undeclared_clients` both make the same argument about their own
    parameters.
    """
    gaps: list[str] = []

    taken = set(inspect.signature(tab_strip).parameters)
    for forbidden in ("role", "roles", "is_admin", "super_admin", "override"):
        if forbidden in taken:
            gaps.append(
                f"tab_strip takes {forbidden}, so a tab can appear because of who somebody "
                "is rather than what they hold, and the pane behind it will be empty"
            )

    returns = str(inspect.signature(tab_strip).return_annotation)
    if returns != ONLY_THE_TABS:
        gaps.append(
            f"tab_strip returns {returns} rather than {ONLY_THE_TABS}, and the only other "
            "thing it could usefully return is a description of what it withheld"
        )

    for part in Part:
        if part not in supply:
            gaps.append(
                f"{part} has no supply, so nothing says whether it can be pinned and an "
                "attachment for it would be accepted or refused by accident"
            )
    for part, field_name in columns.items():
        if field_name not in AgentRecord.model_fields:
            gaps.append(
                f"{part} is a column supplied by {field_name!r}, which AgentRecord does not "
                "have, so the workspace renders a blank where the agent's own decision goes"
            )

    rest = frozenset(other_paths)
    for path in paths:
        in_map = path in composition_paths
        in_rest = path in rest
        if in_map and in_rest:
            gaps.append(
                f"{path!r} is both a composition path and not one, so whether an overlay of "
                "it raises a divergence flag depends on which set is read first"
            )
        if not in_map and not in_rest:
            gaps.append(
                f"{path!r} is in neither set, so a local edit to it raises no divergence "
                "flag and is not declared as something that should not raise one"
            )

    required = {one.read.requires for one in SCREENS}
    seen: set[Tab] = set()
    for one in tabs:
        if one.tab in seen:
            gaps.append(f"the {one.tab} tab is registered twice, so one of the two is unreachable")
        seen.add(one.tab)
        if one.read.requires not in required:
            gaps.append(
                f"the {one.tab} tab requires {one.read.requires.value}, which no screen "
                "requires, so a workspace grants a reach no screen an administrator reviews "
                "would show"
            )

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{attachment_type.__name__}.{name} would let an attachment carry a copy rather "
        f"than a reference. {AN_ATTACHMENT_IS_A_REFERENCE_AND_A_COPY_IS_A_FORK}"
        for name in getattr(attachment_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_AN_INLINE_COPY
    )

    for one_range in ranges:
        if one_range is not Range.MONTH_TO_DATE and one_range not in RANGE_DAYS:
            gaps.append(
                f"{one_range.value} has no length, so selecting it raises at the moment "
                "somebody asks for a figure rather than when the range was added"
            )

    text = inspect.getsource(sys.modules[__name__]) if source is None else source
    gaps.extend(
        f"line {line} intersects two entitlement sets. "
        f"{THE_WORKSPACE_NARROWS_NOTHING_AND_IS_HANDED_A_REACH}"
        for line in intersections_in(text)
    )

    return tuple(gaps)
