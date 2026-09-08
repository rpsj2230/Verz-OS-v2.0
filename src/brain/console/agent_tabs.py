"""The controls on an agent's capabilities tab: attaching, adding, enabling and pruning.

`brain.console.workspace_capabilities` is the reading half of that tab and says so: it
computes rows at `E_run(caller, agent)` and offers nothing to press. This is the acting half,
and every leaf in it is a place where a read rule and a write rule meet. A read rule decides
what a person is shown. A write rule decides what they may bind to an agent that other people
will then run. The two are usually written by different hands and the seam between them is
where a surface stops agreeing with itself.

**Nothing here computes a reach.** `run_reach` is the console's one route into
`EntitlementSet.intersect`, through `brain.console.reads.audience`, and a second arithmetic
here would be a second place for the platform's central rule to be subtly wrong.
`brain.console.workspace.intersections_in` is run over this module's own source by
`agent_tab_gaps` and again by its test suite, so the absence is a check rather than a habit.

**An attach-time capability check is a check that goes stale, and it is safe here for exactly
one reason.** M39.2.1.2 asks for the check to be performed at attach time, which is a claim
about *when*, and the obvious worry is what happens to an attachment whose capability the
agent or the person later loses. Nothing happens to it, and nothing needs to: an `Attachment`
is a reference and a pin, it confers no reach, and every run recomputes
`E(caller) intersect agent_ceiling` in `brain.gate.leash.decide` and
`brain.ops.automation.flow_reach`. A capability that has gone is absent from the intersection,
so `brain.gate.catalogue.project` never describes the tool and the attachment is a dead row
rather than a live grant. What does *not* survive the loss is the disclosure half: an
attachment made while a grant was held stays on the composition after it lapses, so the read
path re-asks the same question. `admitted` is that re-ask, and it returns what survived and no
count of the rest. See `AN_ATTACH_TIME_CHECK_GOES_STALE_AND_ONLY_THE_DISCLOSURE_HALF_MATTERS`.

**Attach is guarded and detach is not**, which is `brain.ops.halt.
THE_GUARDED_ACT_IS_RESUME_AND_NEVER_STOP` at this level. Requiring a capability to remove an
attachment means an attachment nobody can remove on the day the grant behind it lapses, which
is the failure arriving at the moment somebody is trying to make it stop.

**A skill's description is the router prompt, so it is behaviour and not documentation.** The
model picks a skill from `brain.tools.skills.SkillCard`, which carries a name, a version and a
description and deliberately has nowhere to put a body. An empty or vague description
therefore silently changes which skill runs, and it does so with every test green.
`brain.tools.registry.ToolRegistry.validate` already makes exactly this argument for tools,
in these words: two tools described identically are "chosen between by position rather than by
meaning". `router_collisions` is that rule lifted to skills, and it is enforced in
`register_skill`, where a skill joins the router's menu, rather than where a chip is rendered.
See `A_DESCRIPTION_IS_THE_ONLY_THING_THE_ROUTER_READS`.

Rejected: enforcing it in `brain.tools.registry`. That module is the *tool* registry, and the
first thing `brain.tools.skills` says is that a skill is not a tool and must never be
grantable like one. A skill rule in there would be that distinction undone in the one file
whose job is to keep it. Rejected also: enforcing it in `Skill`'s own validators, which is the
tidiest place and is wrong for a different reason: a `SKILL.md` that arrives from outside the
company should be readable and reviewable even when its description is useless, and refusing
it at parse time would refuse the review rather than the attachment.

**Two figures here are mostly somebody else's afternoon.** A per-skill invocation count and a
per-item retrieval count both accumulate from everybody who ran the agent, so a reader seeing
"invoked 40 times" who invoked it twice is reading thirty-eight of somebody else's. That is
`brain.console.workspace.A_FIGURE_THAT_MOVES_WHEN_SOMEBODY_ELSE_WORKS_IS_THEIR_ACTIVITY`
exactly, so the basis comes from `brain.console.agent_output.basis_over` against the usage
screen, which is the screen those figures could be read on anyway. No capability is invented
for a tab.

**Adding to an agent's knowledge is not the same as the agent reaching it.** M39.2.3.2 offers
three routes and only one of them changes what the agent draws on. An upload and a link
extraction add an item, and whether this agent reaches it is decided by the predicate, which
is why `plan_addition` returns whether it does: the alternative is the bug where somebody
uploads a document to an agent's knowledge tab, the agent keeps saying it does not know, and
nothing anywhere said the predicate did not match. Widening the predicate is the third route
and is the only one that changes reach, and it can only ever widen what the agent draws on
from a set the caller already reaches, never what anybody may read. See
`ADDING_AN_ITEM_IS_NOT_THE_SAME_AS_REACHING_IT`.

**A rendering profile is derived and has no override.** M39.2.4.3 says chosen automatically,
and the reason it must stay that way is `brain.channels.adapter.assert_can_send`: a configured
profile is a way of declaring a capability the adapter does not have, and the refusal then
arrives at the send rather than at the configuration. `rendering_profile` takes capabilities
and nothing else, and `agent_tab_gaps` reports a parameter named like an override.

**Group installation needed a `Feature` member, and now that member gates a code path.**
`brain.console.workspace_capabilities` recorded M39.2.4.4 as blocked because
`brain.channels.adapter.Feature` had no member for it, and objected that adding one with
nothing behind it would be a capability an adapter declares and nothing honours. That
objection is answered rather than ignored: `Feature.GROUP_INSTALL` exists and
`install_to_group` refuses on any surface that does not declare it. **No adapter declares it**,
so the console offers group installation nowhere today, which is the honest state rather than
an omission: none of the six adapters has a path for the conversation reference a vendor hands
back, and inventing support a channel does not have is the failure that member was withheld to
avoid.

Rejected: an entitlement on a group install. Installing an agent into a room is not a grant to
the room. Every answer there is still computed at `brain.channels.room.floor`, which is the
intersection of everybody present, and a `GroupInstall` that carried a reach would be a second
answer to what a room may see with nothing saying which one won. See
`INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM`.

Scope: domain logic. Nothing here opens a connection, fetches a URL, renders anything or reads
a clock; `now` is a parameter for the reason `brain.ops.limits` gives about policy that owns a
client. In particular the link route takes an item that has already been fetched, because the
address check belongs to `brain.knowledge.uploads.receive_link` and a second copy of it is the
one that forgets to re-check every redirect.

**Nothing here is a screen.** There is no capabilities tab in this repository and no route
behind one, exactly as `brain.console.screens` says of its own registry. What is built is the
domain layer such a tab would call, and the leaves claimed are the ones where the decision is
the whole content.

Task ids: M39.2.1.2, M39.2.2.1, M39.2.2.3, M39.2.2.4, M39.2.2.5
Task ids: M39.2.3.2, M39.2.3.4, M39.2.3.5, M39.2.4.1, M39.2.4.3, M39.2.4.4
"""

from __future__ import annotations

import enum
import inspect
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.agents.model import AgentRecord
from brain.channels.adapter import ChannelCapabilities, Feature
from brain.console.agent_output import basis_over
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.workspace import Attachment, Basis, Composition, Part, intersections_in
from brain.console.workspace_capabilities import (
    NAMES_THAT_WOULD_BE_A_REPOSITORY,
    KnowledgeScope,
    attach_skill,
    matching,
    offered_channels,
    run_reach,
)
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.field_policy import FieldPolicy
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.knowledge.item import KnowledgeItem, VerificationState, badge
from brain.ops.jobs import hidden_count_fields
from brain.tools.skills import ImportedSkill, Skill, SkillState, SourceKind

# ------------------------------------------------------------------ written-down reasons
#: Why a check made once, at attach time, is enough.
AN_ATTACH_TIME_CHECK_GOES_STALE_AND_ONLY_THE_DISCLOSURE_HALF_MATTERS: Final = (
    "An attachment is a reference and a pin and confers no reach, so a capability lost after "
    "it was made cannot widen anything: every run recomputes E(caller) intersect "
    "agent_ceiling in brain.gate.leash.decide and brain.ops.automation.flow_reach, and a "
    "capability that has gone is absent from the intersection, so the tool is never described "
    "to a model and the attachment is a dead row. What does not survive the loss is the "
    "disclosure half, because the attachment stays on the composition, so the read path asks "
    "the same question again through admitted rather than trusting the answer from the day it "
    "was attached."
)

#: Why removing an attachment asks for nothing.
THE_GUARDED_ACT_IS_ATTACH_AND_NEVER_DETACH: Final = (
    "Requiring a capability to detach means an attachment nobody can remove on the day the "
    "grant behind it lapses, which is the failure arriving exactly when somebody is trying to "
    "make it stop. Attaching binds a source to an agent other people run and is guarded; "
    "detaching narrows what the agent is assembled from and can always be done."
)

#: Why an attach refusal never says which of the two things went wrong.
AN_ATTACH_THAT_REFUSES_DIFFERENTLY_SAYS_WHAT_EXISTS: Final = (
    "Two things can be wrong with an attach: the thing is not one this person could reach at "
    "all, and it is one they could reach and their grants do not admit. Answering those "
    "differently turns the attach control into a way of asking which connectors are installed "
    "here, which is brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER one "
    "surface along. The requirement mapping is built at the caller's own reach, so both cases "
    "arrive as an absent key, and the refusal names what the caller typed and never the "
    "capability."
)

#: Why an approved state is not the same as a runnable skill.
AN_APPROVED_STATE_IS_NOT_AN_EXECUTABLE_SKILL: Final = (
    "brain.tools.skills.ImportedSkill.is_executable is approved, by somebody named, and "
    "unchanged since, and the third clause is the one a chip loses: a row edited in place "
    "still says APPROVED while its digest no longer matches the approval. A chip reading "
    "approved for a skill nobody has read is worse than no chip, so the review state is "
    "derived from is_executable rather than copied off the state column, and a skill that "
    "has moved since approval reads as changed rather than as either approved or pending."
)

#: Why the router prompt is the description and nothing else.
A_DESCRIPTION_IS_THE_ONLY_THING_THE_ROUTER_READS: Final = (
    "brain.tools.skills.SkillCard carries a name, a version and a description and has nowhere "
    "to put a body, which is the whole point of progressive disclosure. So the description is "
    "not documentation about a skill, it is the input a model chooses on, and a vague one "
    "changes which skill runs with every test still green. "
    "brain.tools.registry.ToolRegistry.validate makes the same argument for tools and refuses "
    "two that share a description, because the model then chooses between them by position "
    "rather than by meaning."
)

#: Why adding an item is not the same as the agent being able to use it.
ADDING_AN_ITEM_IS_NOT_THE_SAME_AS_REACHING_IT: Final = (
    "An upload and a link extraction add an item to the knowledge layer. Whether this agent "
    "draws on it is decided by the predicate and by nothing about the act of adding, so an "
    "item that does not match is added and never reached. Reporting that is the difference "
    "between a person seeing why the agent still says it does not know and a person repeating "
    "the upload. Widening the predicate is the third route and the only one that changes what "
    "is reached without adding anything."
)

#: Why a widened predicate widens nothing anybody may read.
A_WIDER_PREDICATE_IS_STILL_NARROWER_THAN_THE_READER: Final = (
    "A knowledge predicate narrows a set the caller already reaches: matching is handed the "
    "reader's own items and can only return a subset of them. So dropping a clause widens "
    "what the agent draws on and cannot widen what anybody may read, and an unrestricted "
    "predicate means this agent narrows nothing of its own rather than that it reaches "
    "everything. That is the same argument brain.agents.model.AgentAuthority makes about its "
    "scope, and it is why widening needs no approval while an upload's visibility does."
)

#: Why a per-item count here is not the per-document learning that was refused.
A_PER_ITEM_COUNT_IS_A_REPORT_AND_NEVER_A_RANKING_INPUT: Final = (
    "brain.knowledge.quality rejected recording principal, item and outcome so that a "
    "per-document boost could be learned, because a boost formed from one caller's reach is "
    "applied to the next caller's ordering, which is one person's view of what exists leaking "
    "into another's results. Nothing here feeds ranking. These counts are read by a person "
    "deciding what to prune, they are computed over the reader's own visible items, and the "
    "basis says whose activity they are. A retrieval of an item this reader cannot see "
    "contributes to no figure they are shown."
)

#: Why a rendering profile cannot be configured.
A_CONFIGURED_PROFILE_DECLARES_A_CAPABILITY_THE_ADAPTER_LACKS: Final = (
    "A profile chosen by hand is a way of saying a surface can render cards when its adapter "
    "says it cannot, and brain.channels.adapter.assert_can_send then refuses at the send "
    "rather than at the configuration, which reads to everybody as the feature being broken. "
    "rendering_profile takes capabilities and nothing else, so there is no parameter an "
    "override could arrive through and no second opinion about what a surface can do."
)

#: Why a group install carries no reach.
INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM: Final = (
    "An answer in a shared conversation is computed at brain.channels.room.floor, which is "
    "the intersection of everybody present, and it is recomputed for every answer because "
    "membership moves. A GroupInstall that carried an entitlement would be a second answer to "
    "what a room may see, written once at install time and stale by the first joiner, and the "
    "permissive copy is the one people read. The record names the agent, the channel and the "
    "room, and has nowhere to put a reach."
)


class AgentTabError(Exception):
    """A control on this tab was described in a shape that would bind the wrong thing.

    Outside `brain.core.errors` for the reason `brain.console.workspace.WorkspaceError` gives
    about itself: those five outcomes describe an answer given to somebody asking a question,
    and this is a refusal to configure an agent. Nobody asking a question ever sees one.
    """


# ------------------------------------------------- attaching and detaching (M39.2.1.2)
def attach(
    composition: Composition,
    one: Attachment,
    *,
    by: EntitlementSet,
    requires: Mapping[str, Capability],
    now: datetime | None = None,
) -> Composition:
    """Bind one thing to one agent, with the capability check made here (M39.2.1.2).

    `by` is the person's own reach and deliberately not `E_run(caller, agent)`. Attaching is
    a configuration act performed by a person, so the question is whether *they* may reach
    the thing they are binding. Checking at the run reach instead would refuse an owner
    attaching a source their agent's ceiling excludes, which is a configuration that does
    nothing rather than a configuration that is unsafe, and M39.2.1.4 already has a state for
    it: a connector the agent asks for and cannot use is shown as requested.

    `requires` says what reaching each thing needs, and it is handed in rather than looked up
    because that is a question the connector registry and the screen registry answer. It is
    built at this caller's reach, so a thing they could never see is an absent key and is
    refused in the same words as one their grants do not admit. See
    `AN_ATTACH_THAT_REFUSES_DIFFERENTLY_SAYS_WHAT_EXISTS`.

    A duplicate is refused by `Composition` rather than here, and its refusal is allowed to
    propagate rather than being wrapped, for the reason `brain.tools.registry.ToolRegistry.
    register` gives about letting the redaction contract's own refusal through: wrapping it
    would make a rule of the composition look like an opinion of this tab.
    """
    wanted = requires.get(one.ref)
    if wanted is None or by.scope_for(wanted, now) is None:
        # One message for both, and it names the reference the caller typed and never the
        # capability: naming the capability would say what the thing needs, which is a fact
        # about a grant on a refusal read by somebody who may not know the grant exists.
        msg = (
            f"{one.ref!r} cannot be attached to {one.part} by {by.principal_id}. "
            f"{AN_ATTACH_THAT_REFUSES_DIFFERENTLY_SAYS_WHAT_EXISTS}"
        )
        raise AgentTabError(msg)
    return Composition(agent_id=composition.agent_id, attachments=(*composition.attachments, one))


def detach(composition: Composition, part: Part, ref: str) -> Composition:
    """Unbind one thing, asking for nothing (M39.2.1.2).

    No capability, on purpose. See `THE_GUARDED_ACT_IS_ATTACH_AND_NEVER_DETACH`.

    Refuses a detach of something that is not attached, because a no-op that reads as an
    action leaves a ledger saying somebody removed a thing that was never there, and M39.1.1.3
    writes every add and remove to that ledger. The same refusal `brain.console.agent_output.
    archive` makes about withdrawing an artifact twice.
    """
    kept = tuple(
        one for one in composition.attachments if not (one.part is part and one.ref == ref)
    )
    if len(kept) == len(composition.attachments):
        msg = (
            f"{ref!r} is not attached to {part} on {composition.agent_id!r}, so removing it "
            "would record a change that did not happen"
        )
        raise AgentTabError(msg)
    return Composition(agent_id=composition.agent_id, attachments=kept)


def admitted(
    attachments: Sequence[Attachment],
    *,
    by: EntitlementSet,
    requires: Mapping[str, Capability],
    now: datetime | None = None,
) -> tuple[Attachment, ...]:
    """The attachments this reader's grants still admit, in the order given.

    The attach-time check asked again on the read path, which is the half of
    `AN_ATTACH_TIME_CHECK_GOES_STALE_AND_ONLY_THE_DISCLOSURE_HALF_MATTERS` that a run does not
    do for us: a run recomputes its reach and never sees the lost capability, while a
    composition keeps rendering the row.

    A filter and never a count. It returns what survived and does not report how much did
    not, which is `brain.knowledge.item.retrievable`'s shape and for the same reason: the
    difference between the two numbers is the thing a reader may not learn by subtraction.
    """
    return tuple(
        one
        for one in attachments
        if one.ref in requires and by.scope_for(requires[one.ref], now) is not None
    )


# --------------------------------------------------------- skills on the agent (M39.2.2)
#: The screen the review queue lives behind, named by key rather than by capability for the
#: reason `brain.console.workspace.SPEND_OF_OTHERS_SCREEN` is: a capability spelled again here
#: is a grant an administrator reviewing the screen registry would never see.
SKILL_SCREEN: Final = "skills"

#: What a reader needs to see a skill at all, read off the registry rather than restated.
SKILL_CAPABILITY: Final[Capability] = screen(SKILL_SCREEN).read.requires

#: Where the review queue is addressed, derived from the screen key so a rename moves both.
REVIEW_ROUTE_PREFIX: Final = f"/{SKILL_SCREEN}/review/"

#: The screen whose grant decides whether a count on this tab may be everybody's.
#:
#: The usage screen, because that is where "what was consumed, by person and by agent" is
#: read, and an invocation count is exactly that figure narrowed to one skill. A tab may not
#: be a shortcut past a screen's grant, so a reader sees everybody's counts precisely when
#: they could open that screen and read them there.
USAGE_OF_OTHERS_SCREEN: Final = "usage"


class Review(enum.StrEnum):
    """What a skill chip says about the review behind it (M39.2.2.1).

    Four members, and the fourth is the one that matters. `brain.tools.skills.SkillState` has
    three, and none of them distinguishes a skill that was approved from one that was approved
    and then edited: the state column still reads APPROVED while `is_executable` is false. See
    `AN_APPROVED_STATE_IS_NOT_AN_EXECUTABLE_SKILL`.
    """

    #: Approved, by somebody named, and unchanged since. The only state that can be attached.
    APPROVED = "approved"
    #: Imported and waiting for a person.
    PENDING = "pending"
    #: A person read it and said no.
    REJECTED = "rejected"
    #: The row says approved and the bytes have moved since. Nobody has read what is there.
    CHANGED = "changed"


def review_state(imported: ImportedSkill) -> Review:
    """The one review state a chip may carry, derived rather than copied (M39.2.2.1).

    `is_executable` is asked first for the positive case, so approved means runnable here and
    nowhere else in this module has to remember the three clauses behind it. REJECTED is read
    off the state column because a rejection is a decision about the skill rather than about
    particular bytes, which is why `ImportedSkill._decided` records no digest for one.
    """
    if imported.is_executable():
        return Review.APPROVED
    if imported.state is SkillState.REJECTED:
        return Review.REJECTED
    if imported.state is SkillState.APPROVED:
        return Review.CHANGED
    return Review.PENDING


@dataclass(frozen=True)
class SkillChip:
    """One skill on an agent: version, source and review state (M39.2.2.1).

    `digest` is here beside `version` and the pair is not redundant. The version is the number
    an author types and the digest is what a pin is over: `brain.console.
    workspace_capabilities.attach_skill` writes the approved digest into the attachment, so a
    chip carrying only the version string cannot be compared against what the agent is
    actually pinned to, and the comparison is the whole question when a skill has moved.

    No count of anything, which `agent_tab_gaps` asks of the type rather than of whoever edits
    it next.
    """

    name: str
    version: str
    source: SourceKind
    #: Where it came from, in the source's own spelling: `owner/repo`, an https URL, or an
    #: uploaded file name. A fact about the skill the reader is already looking at.
    location: str
    review: Review
    #: The digest of what is there now, which is what an attachment pins.
    digest: str


def chip_for(imported: ImportedSkill) -> SkillChip:
    """One chip, computed from the imported skill and from nothing else."""
    return SkillChip(
        name=imported.skill.name,
        version=imported.skill.version,
        source=imported.source.kind,
        location=imported.source.location,
        review=review_state(imported),
        digest=imported.skill.digest(),
    )


def chips_for(skills: Iterable[ImportedSkill]) -> tuple[SkillChip, ...]:
    """Chips for these skills, in name order (M39.2.2.1).

    Every skill handed in, unapproved ones included, which is the difference between this and
    `brain.tools.skills.offered_cards`: that function answers what a *model* may be shown and
    withholds an unapproved skill because a card teaches the model the procedure exists. This
    answers what a person configuring the agent is shown, and hiding a rejected skill from
    them is how the same skill gets imported again next month.

    Sorted by name so two readings of an unchanged library are the same list.
    """
    return tuple(chip_for(one) for one in sorted(skills, key=lambda one: one.skill.name))


class Control(enum.StrEnum):
    """What the tab offers beside a chip. Three, and there is no fourth (M39.2.2.3).

    There is deliberately nothing meaning "approve". Approval is a decision made by a named
    person in the review queue, against the bytes they read, and a control on an agent's
    configuration tab that granted one would be the review happening wherever somebody
    happened to be standing.
    """

    #: The skill is runnable and may be bound to this agent.
    ATTACH = "attach"
    #: It is not, and this reader can open the queue where somebody decides.
    REVIEW = "review"
    #: It is not, and this reader cannot open that queue either.
    NOTHING = "nothing"


def review_route(skill_name: str) -> str:
    """The address of one skill's place in the review queue (M39.2.2.3)."""
    if not skill_name.strip():
        msg = "a route to the review of no skill is not an address"
        raise AgentTabError(msg)
    return f"{REVIEW_ROUTE_PREFIX}{skill_name}"


@dataclass(frozen=True)
class SkillOffer:
    """A chip and the one control offered beside it (M39.2.2.3).

    One control rather than a set of booleans, so there is no state in which a route to the
    review queue and an attach button are offered together. That pairing is the whole failure
    the leaf names: the attach button is the one people press.
    """

    chip: SkillChip
    control: Control
    #: Non-empty exactly when the control is REVIEW.
    route: str = ""

    def __post_init__(self) -> None:
        if (self.control is Control.REVIEW) != bool(self.route):
            msg = (
                f"{self.chip.name!r} is offered {self.control.value} with route "
                f"{self.route!r}; a route belongs to the review control and to no other, and "
                "a control with a route that is not a review is an attach with a link on it"
            )
            raise AgentTabError(msg)


def offer_for(imported: ImportedSkill, reader: EntitlementSet, now: Any = None) -> SkillOffer:
    """What this reader is offered for this skill (M39.2.2.3).

    **An unapproved skill is never offered an attach control, whatever the reader holds.**
    That is the leaf, and it is the first branch rather than a condition folded into a later
    one, so no grant can reach past it. A person with every capability in the deployment still
    gets a route to the queue, because the queue is where a named person reads the bytes and
    `brain.tools.skills.pin_skill` refuses anything else.

    The route is offered only where the review screen is, asked of `brain.console.reads.
    permitted` against that screen's own read rather than of a capability invented here. A
    link somebody bounces off is a worse answer than no link.
    """
    chip = chip_for(imported)
    if chip.review is Review.APPROVED:
        return SkillOffer(chip=chip, control=Control.ATTACH)
    if permitted(screen(SKILL_SCREEN).read, reader, now):
        return SkillOffer(chip=chip, control=Control.REVIEW, route=review_route(chip.name))
    return SkillOffer(chip=chip, control=Control.NOTHING)


# ---------------------------------------- the description convention (M39.2.2.5)
#: Words that appear in almost every description and distinguish none of them.
#:
#: Data rather than a rule about values, following `brain.console.workspace.
#: NAMES_THAT_WOULD_BE_AN_INLINE_COPY`: the failure arrives as a description made of filler
#: and the skill's own name, and no rule about shape catches that. "use" and "when" are in
#: here despite being the router convention's own opening words, precisely because they are:
#: "use when hosting expiry" is a description that has said nothing.
ROUTING_FILLER: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "procedure",
        "skill",
        "that",
        "the",
        "this",
        "to",
        "use",
        "used",
        "using",
        "when",
        "with",
    }
)

#: A word for the purpose of comparing two descriptions. Letters and digits, so that
#: punctuation and case cannot make two identical prompts look different to this check.
_WORD_RE: Final = re.compile(r"[a-z0-9]+")


def folded(text: str) -> str:
    """One description in the form two of them are compared in.

    The folding `brain.tools.registry.ToolRegistry.validate` applies to a tool's description,
    restated here rather than imported because that method inlines it, and pinned against it
    by test: "Reads a client" and "reads a client." are one description to the reader that
    matters, which is a model.
    """
    return " ".join(text.lower().split()).rstrip(".")


def _content_words(text: str, filler: frozenset[str]) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower())) - filler


def _name_words(name: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(name.lower().replace("-", " ").replace("_", " ")))


def description_refusals(
    skill: Skill, *, filler: frozenset[str] = ROUTING_FILLER
) -> tuple[str, ...]:
    """Why this description cannot be the router prompt. Empty when it can (M39.2.2.5).

    Two refusals, and both are about routing rather than about prose.

    *A description that adds no word the name does not already carry.* "Use for hosting
    expiry" beside `hosting-expiry` gives the model the name twice, so the choice between that
    skill and its neighbour is made on the name alone, which is the failure the convention
    exists to prevent. Filler is dropped first, because otherwise every description passes by
    contributing the word "the".

    *A description carrying a line break.* A card is one line in the list a router reads, so a
    description that spans lines either breaks that list or is truncated at the first newline
    by whoever renders it, and a prompt truncated at an unknown point routes on half a
    sentence.

    **What this cannot check is whether the description says when to choose this skill over
    the one beside it**, which is the whole of the convention and needs a reader. What it does
    check is the two ways a description gives the router nothing at all, plus the collision in
    `router_collisions`, which is where the real failure shows up: the router's failure mode
    is a tie, and a tie is a property of a pair rather than of one description.
    """
    gaps: list[str] = []
    if not (_content_words(skill.description, filler) - _name_words(skill.name)):
        gaps.append(
            f"{skill.name!r} is described as {skill.description!r}, which adds no word its "
            f"own name does not already carry. {A_DESCRIPTION_IS_THE_ONLY_THING_THE_ROUTER_READS}"
        )
    if "\n" in skill.description or "\r" in skill.description:
        gaps.append(
            f"{skill.name!r} has a description spanning lines; a card is one line in the list "
            "a router reads, so this is truncated at an unknown point by whoever renders it"
        )
    return tuple(gaps)


def router_collisions(skills: Sequence[Skill]) -> tuple[str, ...]:
    """Skills a router would choose between by position rather than by meaning (M39.2.2.5).

    The rule `brain.tools.registry.ToolRegistry.validate` applies to tools, lifted to skills
    and in the same words, because it is the same failure one layer up: two things described
    identically are picked between by whichever the list happened to hold first.

    A property of a pair, which is why it cannot be checked when one skill is parsed and has
    to be checked where a skill joins a set. Reported for every colliding group at once rather
    than the first, for the reason `ToolRegistry.freeze` gives: a build that reveals one
    problem per run takes an afternoon.
    """
    by_description: dict[str, list[str]] = {}
    for one in sorted(skills, key=lambda skill: skill.name):
        by_description.setdefault(folded(one.description), []).append(one.name)
    return tuple(
        f"skills {names} share the description {text!r}; the model chooses between them by "
        "position rather than by meaning"
        for text, names in sorted(by_description.items())
        if len(names) > 1
    )


def register_skill(
    composition: Composition,
    imported: ImportedSkill,
    *,
    alongside: Sequence[Skill],
    by: EntitlementSet,
    now: datetime | None = None,
) -> Composition:
    """Put one approved skill on the router's menu for this agent (M39.2.2.5, M39.2.1.2).

    The enforcement point for the description convention, and it is here rather than at the
    chip because this is where a skill starts being chosen between. Three refusals in order,
    and the order is the argument: the convention first, because a description that routes
    nothing is a defect in the skill; the collision second, because it is a defect in the
    *set* and its message names both members; and the approval last, through
    `brain.console.workspace_capabilities.attach_skill`, which is `pin_skill`'s refusal and
    not a second opinion about a review.

    `alongside` is the skills already on this agent, and the new one is checked against them
    rather than against every skill in the library: the router reads one agent's cards, so a
    collision with a skill some other agent holds is not a collision anybody experiences.

    The capability check is `attach`'s and is made once. `SKILL_CAPABILITY` is the review
    screen's own, because a skill's reach is its tools' and the tools are checked at run time
    by `brain.gate.catalogue`, so the only question at attach time is whether this person may
    see the skill at all.
    """
    refusals = (
        *description_refusals(imported.skill),
        *router_collisions([*alongside, imported.skill]),
    )
    if refusals:
        msg = f"{imported.skill.name!r} cannot join this agent's skills:\n  " + "\n  ".join(
            refusals
        )
        raise AgentTabError(msg)
    one = attach_skill(composition.agent_id, imported)
    return attach(
        composition,
        one,
        by=by,
        requires={one.ref: SKILL_CAPABILITY},
        now=now,
    )


# ------------------------------------------- what an attachment has been used for (M39.2.2.4)
def usage_basis(entitlement: EntitlementSet, now: Any = None) -> Basis:
    """Whose counts this reader may be shown on this tab.

    `brain.console.agent_output.basis_over` against the usage screen, rather than a second
    rule written here. `brain.console.workspace.basis_for` is the same rule pinned to the
    budget screen, and a test holds the three together.
    """
    return basis_over(USAGE_OF_OTHERS_SCREEN, entitlement, now)


def _counted(
    at: datetime,
    principal_id: str,
    *,
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> bool:
    """Whether one event is inside this window and on this side of this basis.

    One function for both tallies below, because "the window and the basis are applied
    identically" is the rule and two copies of it is where the two figures start disagreeing.
    `brain.console.workspace.headline` states the same rule for spend and messages.
    """
    return since <= at <= until and (basis is Basis.EVERYONE or principal_id == caller_id)


@dataclass(frozen=True)
class SkillInvocation:
    """One run of one skill, as much of it as this tab needs.

    Not `brain.tools.run_skill.RunOutcome`, which is a runner's self-report about a process
    and carries no principal, no agent and no skill name. Not `brain.knowledge.quality.
    RetrievalEvent` either, whose absences are its design. Four fields, because a count per
    skill needs the skill, the window needs the instant, and the basis needs the principal.
    """

    agent_id: str
    skill_name: str
    principal_id: str
    at: datetime


@dataclass(frozen=True)
class SkillUse:
    """One skill and how often it was invoked (M39.2.2.4).

    A name and a number. No share and no rank: each of those is this figure divided by a
    total, and a total the reader was not shown is a total they can recover from two of these,
    which is `brain.console.workspace.CallerSpend`'s argument unchanged.
    """

    skill_name: str
    invocations: int


@dataclass(frozen=True)
class SkillUsage:
    """What this agent's attached skills have been used for, and which have not (M39.2.2.4).

    Both halves from one function, for the reason `brain.console.workspace_capabilities.
    connector_strip` gives about a row and its overflow: a caller computing them separately
    computes them over different sets, and the unused list stops being the complement of the
    used one, which is exactly the list somebody prunes from.

    `basis` is carried rather than left implicit. A reader shown their own counts with no
    label reads them as the agent's, and would prune a skill the department uses daily.
    """

    agent_id: str
    basis: Basis
    #: Attached skills that were invoked, heaviest first.
    used: tuple[SkillUse, ...]
    #: Attached skills with no invocation in the window. The pruning list.
    unused: tuple[str, ...]


def skill_usage(
    agent_id: str,
    invocations: Sequence[SkillInvocation],
    *,
    attached: Iterable[str],
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> SkillUsage:
    """Invocation counts per attached skill, and the ones with none (M39.2.2.4).

    Only attached skills are counted and only attached skills are listed, so an invocation of
    something this agent no longer carries contributes to no figure. That is not tidiness: a
    row for a detached skill would be a row about a configuration the reader is not looking
    at, and the count beside it would be the only place it appeared.

    Ordered by invocations and then by name, so two readings of an unchanged ledger are the
    same list; ordering by count alone leaves ties to whatever the mapping iterated.
    """
    names = frozenset(attached)
    tally = dict.fromkeys(names, 0)
    for one in invocations:
        if one.agent_id != agent_id or one.skill_name not in names:
            continue
        if _counted(
            one.at, one.principal_id, caller_id=caller_id, basis=basis, since=since, until=until
        ):
            tally[one.skill_name] += 1
    return SkillUsage(
        agent_id=agent_id,
        basis=basis,
        used=tuple(
            SkillUse(skill_name=name, invocations=count)
            for name, count in sorted(tally.items(), key=lambda pair: (-pair[1], pair[0]))
            if count
        ),
        unused=tuple(sorted(name for name, count in tally.items() if not count)),
    )


# ------------------------------------------------------ knowledge on the agent (M39.2.3)
class AddRoute(enum.StrEnum):
    """The three ways something reaches an agent's knowledge (M39.2.3.2).

    Exactly the three the leaf names, and the enum is the list rather than a comment beside
    one. They are not variations on each other: two add an item and leave the predicate
    alone, and the third changes the predicate and adds nothing.
    """

    #: A file somebody sent. `brain.knowledge.uploads.receive_upload` is the door.
    UPLOAD = "upload"
    #: A link, fetched and taken at the same door. `receive_link` is that path.
    LINK = "link"
    #: No new item at all: the agent is told to draw on more of what is already there.
    PREDICATE = "predicate"


#: The two routes that add an item. Derived, so a fourth route is one edit.
ITEM_ROUTES: Final[frozenset[AddRoute]] = frozenset({AddRoute.UPLOAD, AddRoute.LINK})


@dataclass(frozen=True)
class Addition:
    """One thing added to an agent's knowledge, and whether the agent reaches it (M39.2.3.2).

    `reached` is the field this type exists for. See
    `ADDING_AN_ITEM_IS_NOT_THE_SAME_AS_REACHING_IT`.
    """

    route: AddRoute
    item_id: str
    #: Whether this agent's predicate reaches what was added.
    reached: bool


def plan_addition(scope: KnowledgeScope, item: KnowledgeItem, route: AddRoute) -> Addition:
    """What adding this item by this route does for this agent (M39.2.3.2).

    Takes the item rather than a file or an address, and there is no parameter a URL could
    arrive through. The address check belongs to `brain.knowledge.uploads.receive_link`, which
    reuses `brain.tools.fetch` whole rather than reproducing it, and the part a second copy
    always leaves out is re-running the rules on every redirect. `agent_tab_gaps` reports a
    parameter here named like a repository, using the same list
    `brain.console.workspace_capabilities.capabilities_gaps` applies to the skill attach path.

    Refuses `PREDICATE`, because widening adds no item and an `Addition` for one would carry
    an item id nothing produced. `widen` is that route.
    """
    if route not in ITEM_ROUTES:
        msg = (
            f"{route.value} adds no item, so there is nothing for {item.item_id!r} to be. "
            "Widening a predicate is widen, which returns a scope rather than an addition"
        )
        raise AgentTabError(msg)
    return Addition(
        route=route,
        item_id=item.item_id,
        reached=bool(matching(scope, [item])),
    )


def widen(scope: KnowledgeScope, *, drop: Iterable[str]) -> KnowledgeScope:
    """The same agent's predicate with these clauses removed (M39.2.3.2).

    Widening only. Clauses are dropped and none is added, so the result admits everything the
    original admitted and possibly more, and the "more" is still bounded by the reader's own
    items: see `A_WIDER_PREDICATE_IS_STILL_NARROWER_THAN_THE_READER`. An unrestricted result
    is allowed and means this agent narrows nothing of its own.

    Refuses a field the scope does not carry, because dropping a clause that is not there is a
    no-op that reads as an action, and the person who asked has been told they widened
    something. The same refusal `detach` makes.
    """
    wanted = frozenset(drop)
    carried = frozenset(clause.field for clause in scope.predicate.clauses)
    missing = sorted(wanted - carried)
    if missing:
        msg = (
            f"{scope.agent_id!r} has no clause on {missing}, so dropping it widens nothing "
            "and tells whoever asked that it did"
        )
        raise AgentTabError(msg)
    return KnowledgeScope(
        agent_id=scope.agent_id,
        predicate=Scope(
            clauses=tuple(
                clause for clause in scope.predicate.clauses if clause.field not in wanted
            )
        ),
    )


@dataclass(frozen=True)
class SliceHealth:
    """Coverage and staleness for exactly this agent's slice (M39.2.3.4).

    Every figure is a count of what was shown. `matched` is `preview_count`'s number and
    carries its argument unchanged: a small figure means the predicate is narrow, or the
    corpus is small, or most of it is out of this reader's reach, and those are
    indistinguishable by design.

    Three states and no fourth, because `matching` drops superseded and archived items
    through `brain.knowledge.item.retrievable` before anything is counted. The three therefore
    sum to `matched`, which is a property a test holds rather than a coincidence.
    """

    agent_id: str
    #: Items this reader can see that this agent's predicate reaches.
    matched: int
    #: Of those, verified by a named person and not yet due for review.
    verified: int
    #: Of those, verified and past the review date somebody set.
    stale: int
    #: Of those, nobody has vouched for.
    unverified: int

    @property
    def coverage(self) -> float | None:
        """The verified share of this slice, or `None` when the slice is empty.

        `None` rather than nought, because nought is a measurement and an empty slice is the
        absence of one: rendering "0 per cent covered" for an agent whose predicate matches
        nothing this reader can see is an alarm about a corpus rather than about coverage.
        `brain.knowledge.quality.signal` withholds a rate on the same grounds.
        """
        return None if not self.matched else self.verified / self.matched

    @property
    def staleness(self) -> float | None:
        """The share that is verified and overdue, or `None` when the slice is empty."""
        return None if not self.matched else self.stale / self.matched


def slice_health(
    scope: KnowledgeScope, items: Sequence[KnowledgeItem], *, now: datetime
) -> SliceHealth:
    """How well covered this agent's own slice is, as of `now` (M39.2.3.4).

    Over `matching`, so the slice is this agent's predicate applied to the items the reader
    can already see, and never the corpus. The verdict per item is
    `brain.knowledge.item.badge`'s rather than a comparison written here, so an item is
    described the same way on this tab as beside the answer it is cited in; a second reading
    of a review date is a document that is due on one screen and current on another.
    """
    counts = dict.fromkeys(VerificationState, 0)
    reached = matching(scope, items)
    for one in reached:
        counts[badge(one, now=now).state] += 1
    return SliceHealth(
        agent_id=scope.agent_id,
        matched=len(reached),
        verified=counts[VerificationState.VERIFIED],
        stale=counts[VerificationState.DUE],
        unverified=counts[VerificationState.UNVERIFIED],
    )


@dataclass(frozen=True)
class ItemRetrieval:
    """One item retrieved by one run of this agent, for one person.

    Deliberately not `brain.knowledge.quality.RetrievalEvent`, which carries no reference and
    no principal and says in its own docstring that those absences are the design: that record
    measures our ranking and is aggregated across callers. This one names an item and a person
    because a per-item count read on a console is a different thing from a ranking signal, and
    the difference is argued in `A_PER_ITEM_COUNT_IS_A_REPORT_AND_NEVER_A_RANKING_INPUT`.
    """

    agent_id: str
    item_id: str
    principal_id: str
    at: datetime


@dataclass(frozen=True)
class ItemUse:
    """One knowledge item and how often this agent drew on it (M39.2.3.5)."""

    item_id: str
    retrievals: int


@dataclass(frozen=True)
class ItemUsage:
    """What this agent reached for and what it never touched (M39.2.3.5).

    Both halves from one function, for the same reason `SkillUsage` carries both: the never
    list is only meaningful as the complement of the other, and two calls over two different
    sets produce two lists that do not add up.

    Every id in either half is an item this reader can already see and this agent's predicate
    reaches, because that is what the function is handed. A retrieval of anything else
    contributes to no figure here, which is the whole of the disclosure argument.
    """

    agent_id: str
    basis: Basis
    #: The items drawn on most, heaviest first.
    most_retrieved: tuple[ItemUse, ...]
    #: Items in this agent's slice with no retrieval in the window.
    never_retrieved: tuple[str, ...]


def item_usage(
    agent_id: str,
    retrievals: Sequence[ItemRetrieval],
    *,
    within: Sequence[KnowledgeItem],
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> ItemUsage:
    """Which of this agent's items it used and which it never did (M39.2.3.5).

    `within` is this agent's slice as this reader may see it, which is `matching`'s own
    output. Passing the whole corpus would make the never list a list of everything that
    exists, and passing a set the reader cannot see would make it a disclosure; the one
    correct input is the one the coverage figure is computed over, so the two agree.

    Ordered by retrievals and then by id, so two readings of an unchanged log are the same
    list.
    """
    ids = frozenset(one.item_id for one in within)
    tally = dict.fromkeys(ids, 0)
    for one in retrievals:
        if one.agent_id != agent_id or one.item_id not in ids:
            continue
        if _counted(
            one.at, one.principal_id, caller_id=caller_id, basis=basis, since=since, until=until
        ):
            tally[one.item_id] += 1
    return ItemUsage(
        agent_id=agent_id,
        basis=basis,
        most_retrieved=tuple(
            ItemUse(item_id=item_id, retrievals=count)
            for item_id, count in sorted(tally.items(), key=lambda pair: (-pair[1], pair[0]))
            if count
        ),
        never_retrieved=tuple(sorted(item_id for item_id, count in tally.items() if not count)),
    )


# ------------------------------------------------------- channels on the agent (M39.2.4)
class RenderProfile(enum.StrEnum):
    """How an answer is laid out on one surface, derived from what that surface can do.

    Three, and each is the widest layout the surface can actually deliver. There is no member
    meaning "rich" or "default": a default is the value a surface gets when nobody decided,
    and every one of these is decided by an adapter's own declaration.
    """

    #: Structured and actionable. Needs `Feature.CARDS`.
    CARD = "card"
    #: A body with files beside it. Needs `Feature.ATTACHMENTS` and no cards.
    ATTACHMENT = "attachment"
    #: Text, which every surface here can carry.
    PLAIN = "plain"


def rendering_profile(capabilities: ChannelCapabilities) -> RenderProfile:
    """The profile for one channel, chosen from its capabilities alone (M39.2.4.3).

    Takes capabilities and nothing else, which is the whole of "chosen automatically". See
    `A_CONFIGURED_PROFILE_DECLARES_A_CAPABILITY_THE_ADAPTER_LACKS`.

    Cards before attachments because a card is the richer layout and a surface declaring both
    should get it; the ordering is stated here rather than left to whichever branch was
    written first, since the two are not mutually exclusive and `brain.channels.lark` declares
    both.
    """
    if capabilities.supports(Feature.CARDS):
        return RenderProfile.CARD
    if capabilities.supports(Feature.ATTACHMENTS):
        return RenderProfile.ATTACHMENT
    return RenderProfile.PLAIN


@dataclass(frozen=True)
class ChannelRow:
    """One channel this agent may be enabled on, and whether it is (M39.2.4.1).

    There is no field saying why a channel is absent, and no count of the channels that are.
    A channel this run could not carry produces no row at all rather than a disabled one: a
    disabled row would say the deployment has that surface and that this agent's widest reach
    is too sensitive for it, which are two facts about the ceiling on a row read by somebody
    who may not know either.
    """

    channel: Channel
    #: Whether the install has this channel switched on for this agent.
    enabled: bool
    #: How an answer is laid out here. Derived; see `rendering_profile`.
    profile: RenderProfile
    #: Whether this surface can take an install into a shared conversation (M39.2.4.4).
    group_installable: bool


def channel_rows(
    caller: EntitlementSet,
    record: AgentRecord,
    capabilities: Sequence[ChannelCapabilities],
    policy: FieldPolicy,
    *,
    enabled: Iterable[Channel],
    now: datetime | None = None,
) -> tuple[ChannelRow, ...]:
    """The channel rows this caller sees for this agent, in declared order (M39.2.4.1).

    Takes the caller and the record rather than a reach, and computes `E_run(caller, agent)`
    with `brain.console.workspace_capabilities.run_reach`. That is a safety property rather
    than a convenience: a function taking a ready-made reach can be handed the caller's own,
    which would offer channels above the agent's ceiling, and the mistake would be invisible
    at the call site. Nothing is intersected here; `run_reach` is the console's one route into
    the platform's one intersection.

    The offer itself is `offered_channels`, which is M39.2.4.2 and already argued: a channel is
    offered when it can carry the most sensitive thing this run could return, asked of the
    channel's own `may_carry`.
    """
    switched_on = frozenset(enabled)
    reach = run_reach(caller, record)
    offered = frozenset(offered_channels(reach, capabilities, policy, now))
    return tuple(
        ChannelRow(
            channel=one.channel,
            enabled=one.channel in switched_on,
            profile=rendering_profile(one),
            group_installable=group_installable(one),
        )
        for one in capabilities
        if one.channel in offered
    )


def enable(rows: Sequence[ChannelRow], channel: Channel) -> tuple[Channel, ...]:
    """The enabled set after switching one channel on (M39.2.4.1).

    Refuses a channel with no row, which is every channel this run could not carry and every
    channel this deployment does not have, in one refusal. Answering those differently would
    make the enable control a way of asking which adapters are configured here.

    Returns the enabled channels rather than mutating a row, because a row is what a reader
    was shown and the enabled set is what the install holds; writing the answer back onto the
    row would make the two one value that has to be recomputed to stay true.
    """
    found = next((one for one in rows if one.channel is channel), None)
    if found is None:
        msg = (
            f"{channel} is not a channel this agent may be enabled on, so switching it on "
            "would record a binding nothing can deliver"
        )
        raise AgentTabError(msg)
    return tuple(
        sorted(
            {one.channel for one in rows if one.enabled} | {channel},
            key=lambda one: one.value,
        )
    )


# ------------------------------------------------------ group installation (M39.2.4.4)
#: Field names on a group install that would make it a grant. See
#: `INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM`. Names rather than a rule about values,
#: because the failure arrives as a field somebody adds to save a lookup at send time.
NAMES_THAT_WOULD_BE_A_GRANT: Final[frozenset[str]] = frozenset(
    {"entitlement", "grants", "capabilities", "reach", "ceiling", "scope", "envelope"}
)


def group_installable(capabilities: ChannelCapabilities) -> bool:
    """Whether this surface can take an install into a shared conversation (M39.2.4.4).

    The adapter's own declaration and no inference from anything else. A surface that has
    rooms is not necessarily a surface with an install path for one, and guessing is how
    `brain.channels.adapter.Feature` says a wrong `EPHEMERAL` gets declared.
    """
    return capabilities.supports(Feature.GROUP_INSTALL)


@dataclass(frozen=True)
class GroupInstall:
    """One agent installed into one shared conversation (M39.2.4.4).

    Three fields and no fourth. There is no entitlement, no ceiling and no envelope, which is
    `INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM` expressed as a shape rather than as a
    rule somebody keeps, and `agent_tab_gaps` reports one if a later edit adds it.
    """

    agent_id: str
    channel: Channel
    #: The conversation's own identifier on that surface. Never a person, never a reach.
    room_ref: str

    def __post_init__(self) -> None:
        if not self.agent_id.strip() or not self.room_ref.strip():
            msg = "a group install naming no agent or no conversation cannot be delivered to"
            raise AgentTabError(msg)


def install_to_group(
    agent_id: str, capabilities: ChannelCapabilities, room_ref: str, *, rows: Sequence[ChannelRow]
) -> GroupInstall:
    """Install this agent into one shared conversation, where the channel supports it.

    Two refusals. The surface must declare `Feature.GROUP_INSTALL`, which is the code path
    that member was added for, and the channel must already be enabled for this agent: a
    group install on a channel the agent does not answer on is a binding that delivers
    nothing, and it reads to everybody as the feature being broken.

    What this does not do is decide what may be said there. That is
    `brain.channels.room.plan`, computed at the floor of everybody present, recomputed for
    every answer because membership moves, and it is not this function's to pre-empt.
    """
    if not group_installable(capabilities):
        msg = (
            f"{capabilities.channel} does not declare group installation, so an agent "
            "installed there would have no conversation to be reached in"
        )
        raise AgentTabError(msg)
    if not any(one.channel is capabilities.channel and one.enabled for one in rows):
        msg = (
            f"{agent_id!r} is not enabled on {capabilities.channel}, so installing it into a "
            "conversation there would bind something that answers nothing"
        )
        raise AgentTabError(msg)
    return GroupInstall(agent_id=agent_id, channel=capabilities.channel, room_ref=room_ref)


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this tab is handed. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`: a type added to the tab and not to this tuple is a type
#: the checks below never see.
AGENT_TAB_SURFACE: Final[tuple[type, ...]] = (
    SkillChip,
    SkillOffer,
    SkillUse,
    SkillUsage,
    Addition,
    SliceHealth,
    ItemUse,
    ItemUsage,
    ChannelRow,
    GroupInstall,
)

#: Parameter names on a profile that would let somebody choose one. See
#: `A_CONFIGURED_PROFILE_DECLARES_A_CAPABILITY_THE_ADAPTER_LACKS`.
NAMES_THAT_WOULD_OVERRIDE_A_PROFILE: Final[frozenset[str]] = frozenset(
    {"profile", "override", "prefer", "preferred", "force", "style", "template", "layout"}
)


def agent_tab_gaps(
    *,
    surface: Sequence[type] = AGENT_TAB_SURFACE,
    install_type: type = GroupInstall,
    profile: Callable[..., object] = rendering_profile,
    addition: Callable[..., object] = plan_addition,
    removal: Callable[..., object] = detach,
    source: str | None = None,
) -> tuple[str, ...]:
    """Everything about these controls that would bind or show more than somebody holds.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason: a diagnostic that can only be run against the healthy tree has nothing to report
    on today's data, so switching off any of its refusals changes nothing observable and every
    one of them survives. Calling it with no arguments is the deployment check and calling it
    with a constructed type is the test. `brain.console.workspace.workspace_gaps` and
    `brain.ops.starter.starter_gaps` make the same argument about their own parameters.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{install_type.__name__}.{name} would make an install a grant. "
        f"{INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM}"
        for name in getattr(install_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_A_GRANT
    )

    chosen = set(inspect.signature(profile).parameters)
    gaps.extend(
        f"{getattr(profile, '__name__', 'the profile')} takes {name}. "
        f"{A_CONFIGURED_PROFILE_DECLARES_A_CAPABILITY_THE_ADAPTER_LACKS}"
        for name in sorted(chosen & NAMES_THAT_WOULD_OVERRIDE_A_PROFILE)
    )

    taken = set(inspect.signature(addition).parameters)
    gaps.extend(
        f"{getattr(addition, '__name__', 'the addition path')} takes {name}, so a link is "
        "fetched here rather than at the one door that re-checks the address on every redirect"
        for name in sorted(taken & NAMES_THAT_WOULD_BE_A_REPOSITORY)
    )

    guarded = set(inspect.signature(removal).parameters)
    gaps.extend(
        f"{getattr(removal, '__name__', 'the detach path')} takes {name}. "
        f"{THE_GUARDED_ACT_IS_ATTACH_AND_NEVER_DETACH}"
        for name in sorted(guarded & {"by", "entitlement", "reach", "requires"})
    )

    text = inspect.getsource(sys.modules[__name__]) if source is None else source
    gaps.extend(
        f"line {line} intersects two entitlement sets, and run_reach is the console's one "
        "route into the intersection the whole platform rests on"
        for line in intersections_in(text)
    )

    return tuple(gaps)
