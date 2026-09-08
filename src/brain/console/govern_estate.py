"""Six governance screens that widen a per-agent view to the whole estate, and what widening
costs.

`brain.console.reach_view` answers what one agent may reach, what it has learnt and what it
remembers. `brain.console.agent_output` answers what one agent produced. `brain.tools.review`
answers what is waiting to be read. Every one of those is built, argued about and tested, and
every one of them is scoped to a single agent or a single queue. The six governance leaves
here are the same questions asked of everything at once, and **the widening is the disclosure
rather than the rows**.

**Two of the leaves say "across every department" and that is the dangerous phrase.** A
library or a learning review that shows every department is a company-wide read wearing a
screen's name. The rule that already exists for exactly this is
`brain.console.workspace.Basis`, generalised by `brain.console.agent_output.basis_over`, and
the rule it states is that a figure or a listing may not be a shortcut past the screen that
would otherwise show it. Here the thing being shortcut is the department itself: grouping a
listing by department publishes which departments have items in it, which is the Scopes and
departments screen's content. So `DEPARTMENT_SPAN_SCREEN` is that screen, `spans_departments`
asks `basis_over` about it, and the grouping is **withheld on the narrower basis rather than
narrowed**, which is `brain.console.workspace.projection`'s decision about a figure made of
everybody's spend. A grouping showing four departments under a heading reading every
department is a completeness claim the reader cannot check.

The rows themselves are not withheld. They are narrowed by
`brain.console.govern._in_reach`, which is the one narrowing four surfaces in that module
share, imported rather than restated for the reason `brain.console.scoped_authority` gives
about the predicate form of the same rule.

**A cross-agent listing is assembled agent by agent and never by dropping the agent filter.**
`brain.console.agent_output.visible_artifacts` requires an `agent_id` and says in its own
docstring why there is no value meaning every agent: a listing that could be asked for the
whole estate is the global pile with an optional filter on it, and the filter is the thing
that gets omitted. A governance screen over the estate is precisely that request, so it is
answered by asking the per-agent function once per agent the reader may already see, with the
audience decided by `brain.agents.model.visible_agent_ids` rather than re-derived here. The
same construction serves the leash matrix and the rung history. See
`AN_ESTATE_LISTING_IS_ASSEMBLED_FROM_WHAT_THE_READER_CAN_ALREADY_SEE`.

**An artifact of an agent the reader cannot see is still theirs.** `may_see` admits an
artifact whose caller is the reader, because the only person who knows what it was for must
be able to find it again. Across the estate that branch would be lost by iterating visible
agents alone, so the agents the reader's own artifacts name are added to the set. That
discloses an agent id they cannot otherwise see, and it is not a disclosure: they ran it.

**A summary computed over a wider list than the one below it is "showing 3 of 47".**
`brain.tools.review.summarise` counts whatever it is handed, and a screen that counted the
whole queue while listing the reader's slice would publish the difference. So `skill_queue`
returns the entries and the summary from one call over one narrowed tuple, and there is no
way to obtain the second without the first. See
`A_SUMMARY_OVER_A_WIDER_LIST_THAN_THE_LISTING_IS_A_SUBTRACTION`.

**A library row carries the level and never the predicate.** `brain.knowledge.visibility`
turns a level into a `Scope`, and that predicate names a department or an owner id: it is a
row of the Scopes screen with a document's name in front of it. The level is one of three
words and is a fact about the item, which is what the leaf's "per-item visibility scope"
means to somebody reading the screen. So `LibraryRow` has no field a predicate could go in and
`estate_gaps` reports one, which is `brain.console.govern.FrictionRow`'s construction.

**Tier three is the only one of the three learning tiers that names a department**, so it is
the only one the span decision applies to. `TierOneRow` and `TierTwoRow` carry a memory id, a
change, evidence kinds and an instant, and none of those says where anybody sits;
`TierThreeRouting` carries the department a gated change was routed to, and a list of those
across the estate is the routing table for every access decision in the company.

**The undo control is per row and there is no bulk one.** A tier-one change has already taken
effect and `TierOneRow.control_writes` is what undoing it would write, per row. An undo-all on
a review spanning departments is one click applying corrections in departments the reader
cannot see, and its blast radius is unreadable at the moment somebody presses it.
`LearningReview` has nowhere to put one and `estate_gaps` refuses a field that would.

**A memory viewer over every subject is a directory of what the system knows about people.**
`brain.memory.review` already decided that a department view shows the organisation and not
the people in it, and `brain.console.reach_view` calls a diff the sharpest edge on the memory
surface because it puts two revisions side by side. Across subjects it would put two people
side by side. So `subject_memory` requires a subject id with no value meaning everybody, which
is `visible_artifacts`' construction, and `estate_gaps` reads the signatures in this module
for a parameter a list of subjects could arrive through.

**Nothing here computes a reach.** `brain.core.entitlement.EntitlementSet.intersect` has one
implementation and the console's routes into it are `brain.console.reads.audience` and
`brain.console.workspace_capabilities.run_reach`; `reach_view.separate_memory` already calls
the second on the caller's behalf. There is no `.intersect(` in this module and
`tests/invariants/test_single_implementation.py` pins the call sites, so the absence is
checked rather than intended.

**Rejected: recomputing the per-agent rows here.** Every listing below takes rows the owning
module produced. `leash_matrix` looks every cell up rather than inheriting one, `tier_two_rows`
asks `may_promote` for the verdict, `revisions` decides a diff from two admissions, and
`visible_artifacts` drops expired rows before it filters anything. A function here that rebuilt
any of that would be the second implementation this repository refuses, and the copy that
drifts is the one on the screen an administrator reads.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in every sibling in this package. Nothing writes: the undo control is a
`Correction` the row already carries and pressing it is somebody else's module.

**No console screen exists behind any of these six**, exactly as `brain.console.screens`,
`brain.console.govern`, `brain.console.workspace` and `brain.console.agent_output` each say of
their own. What is claimed is the widening decision, which is the half a screen cannot supply.

Task ids: M27.3.12, M27.3.13, M27.3.14
Task ids: M27.3.15, M27.3.16, M27.3.17
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.agent_output import Artifact, basis_over, visible_artifacts
from brain.console.govern import Placed, _in_reach
from brain.console.reach_view import (
    LeashMatrix,
    PromotionEvidence,
    Revision,
    RungChange,
    SplitMemoryView,
    TierOneRow,
    TierThreeRouting,
    TierTwoRow,
    revisions,
    rung_history,
    split_memory,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.workspace import Basis
from brain.core.entitlement import EntitlementSet
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.memory.correction import Demotion, Supersession
from brain.memory.digest import Learning
from brain.ops.jobs import hidden_count_fields
from brain.tools.review import QueueEntry, QueueSummary, summarise

# ------------------------------------------------------------------ written-down reasons
#: Why a listing that spans departments needs the grant over the departments themselves.
A_LISTING_GROUPED_BY_DEPARTMENT_PUBLISHES_THE_DEPARTMENTS: Final = (
    "Two of these leaves ask for a view across every department, and the rows are not the "
    "disclosure: a reader's own grant already decides which items they see. What the heading "
    "adds is the grouping, and a grouping is the list of departments that have something in "
    "it, which is the Scopes and departments screen's content reached from a screen about "
    "documents. brain.console.workspace.Basis is the rule for exactly this and says a listing "
    "may not be a shortcut past the screen that would otherwise show it, so the grouping "
    "needs that screen's grant and nothing here invents a second one."
)

#: Why a grouping is withheld on the narrower basis rather than shown short.
A_LISTING_HEADED_EVERY_DEPARTMENT_AND_SHOWING_FOUR_IS_A_CLAIM_NOBODY_CAN_CHECK: Final = (
    "Narrowing the grouping is the option that looks like a privacy improvement and is worse "
    "than either honest one: the heading still says every department, the reader has no way "
    "to tell that it is four of nine, and nothing on the screen says so. That is "
    "brain.console.workspace.projection's argument about a confident figure that is wrong "
    "being worse than no figure, reached here about a list rather than a number. So the "
    "grouping is absent on the narrower basis and the rows below it are unchanged."
)

#: Why an estate listing is built agent by agent.
AN_ESTATE_LISTING_IS_ASSEMBLED_FROM_WHAT_THE_READER_CAN_ALREADY_SEE: Final = (
    "brain.console.agent_output.visible_artifacts requires an agent id and has no value "
    "meaning every agent, in its own words because a listing that could be asked for the "
    "whole estate is the global pile with an optional filter on it and the filter is the "
    "thing that gets omitted. A governance screen over the estate is that request, so it is "
    "answered by asking the per-agent function once per agent the reader may already see. "
    "The audience is brain.agents.model.visible_agent_ids' answer, handed in rather than "
    "re-derived from a record's shape, which is brain.console.workspace.resolve's rule."
)

#: Why the reader's own output survives an agent they cannot see.
AN_ARTIFACT_OF_AN_AGENT_YOU_CANNOT_SEE_IS_STILL_YOURS: Final = (
    "brain.console.agent_output.may_see admits an artifact whose caller is the reader, "
    "because refusing that would mean the only person who knows what the artifact was for is "
    "the one person who cannot find it again. Iterating visible agents alone loses that "
    "branch the day an agent's audience narrows, so the agents the reader's own artifacts "
    "name are added to the set. The row then carries an agent id they could not otherwise "
    "see, which discloses nothing: they ran it."
)

#: Why the queue and its summary come back from one call.
A_SUMMARY_OVER_A_WIDER_LIST_THAN_THE_LISTING_IS_A_SUBTRACTION: Final = (
    "brain.tools.review.summarise counts whatever it is handed, and the natural screen "
    "computes the summary from the whole queue because that is the number somebody wants and "
    "lists the reader's own slice because that is what they may see. The difference between "
    "the two is the count of skills waiting that this reader may not read, published without "
    "anybody writing a number down. So one call returns both, over one narrowed tuple, and "
    "there is no way to obtain the summary without the list it counts."
)

#: Why a library row carries a level and never a predicate.
A_VISIBILITY_PREDICATE_NAMES_A_DEPARTMENT_AND_AN_OWNER: Final = (
    "brain.knowledge.visibility.scope_for turns a level into a Scope, and that predicate is "
    "owner_id = u_1 or department = finance: a row of the Scopes screen with a document's "
    "name in front of it. The level is one of three words and is a fact about the item, which "
    "is what per-item visibility scope means to somebody reading the screen. So the row "
    "carries the level and there is no field a predicate could go in, which is the shape "
    "brain.console.govern.FrictionRow uses rather than a rule somebody remembers."
)

#: Why the span decision applies to tier three and to neither of the others.
TIER_THREE_IS_THE_ONLY_LEARNING_ROW_THAT_NAMES_A_DEPARTMENT: Final = (
    "A tier-one row is a memory id, a change, the correction its control would write and an "
    "instant; a tier-two row adds signal kinds and a verdict. Neither says where anybody "
    "sits, so neither is a cross-department disclosure however many agents it is gathered "
    "from. brain.console.reach_view.TierThreeRouting carries the department a gated change "
    "was routed to, and a list of those across the estate is the routing table for every "
    "access decision in the company, which is the thing the span decision is about."
)

#: Why there is no control that undoes a page of tier-one changes at once.
AN_UNDO_ALL_ACROSS_DEPARTMENTS_HAS_AN_UNREADABLE_BLAST_RADIUS: Final = (
    "A tier-one change has already taken effect and TierOneRow.control_writes is what undoing "
    "one would write. A control that undid the page is one click applying corrections in "
    "departments the reader cannot enumerate, at a moment when what it will touch is exactly "
    "what the screen has been careful not to tell them. brain.console.reach_view.freeze makes "
    "the mirror argument about the control that stops learning: the fail-safe direction is "
    "the one with no options on it, and this is the direction with options and no reading."
)

#: Why a memory viewer is per subject and there is no listing of subjects.
A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE: Final = (
    "brain.memory.review already decided that a department view shows the organisation and "
    "not the people in it, and brain.console.reach_view calls a revision diff the sharpest "
    "edge on the memory surface because it puts two versions of one memory side by side. "
    "Across subjects it puts two people side by side, and the listing that arrives first is "
    "the one naming whose memory there is something to read. So the subject is required, "
    "there is no value meaning everybody, and no signature here takes a list of them."
)

#: Why the approver on a promotion row follows the People screen's grant.
NAMING_WHO_TRUSTED_AN_AGENT_FURTHER_IS_NAMING_A_PERSON: Final = (
    "A promotion carries PromotionEvidence, which names the approver so that the history "
    "records a person deciding rather than a threshold being met. Across the estate that "
    "column is a list of who trusted which agent with what, which is a fact about "
    "colleagues rather than about agents. It is the People screen's disclosure, so it takes "
    "that screen's grant, which is brain.console.govern.may_name_capabilities' construction "
    "one surface over. A demotion names nobody, so a withheld approver and a demotion are "
    "the same empty string."
)


class EstateError(Exception):
    """An estate listing was asked for something that would show the wrong person a row.

    Outside `brain.core.errors` for the reason `brain.console.govern.GovernError` gives about
    itself: those five outcomes describe an answer given to somebody asking a question, and
    this is a refusal to assemble an administrative surface.
    """


# --------------------------------------------------------------- the one span decision
#: The screen whose grant decides whether a governance listing may be grouped by department.
#:
#: A screen key rather than a capability written out, so nothing here can drift from the
#: registry, which is `brain.console.govern.VOCABULARY_SCREEN`'s construction and
#: `brain.console.agent_output.ARTIFACTS_SCREEN`'s. See
#: `A_LISTING_GROUPED_BY_DEPARTMENT_PUBLISHES_THE_DEPARTMENTS`.
DEPARTMENT_SPAN_SCREEN: Final = "scopes"


def spans_departments(entitlement: EntitlementSet, now: datetime | None = None) -> Basis:
    """Whether this reader may be shown a listing grouped by department.

    `brain.console.agent_output.basis_over` against the Scopes and departments screen.
    `brain.console.workspace.basis_for` is the same rule against the budget screen and
    `basis_over` is the general form of it, written when a second surface needed one; this is
    the third application and it invents nothing. See
    `A_LISTING_GROUPED_BY_DEPARTMENT_PUBLISHES_THE_DEPARTMENTS`.

    `Basis.EVERYONE` and `Basis.OWN` rather than a third member meaning "the departments you
    reach", for the reason that enum gives about a middle basis: a listing aggregated over a
    group the reader cannot enumerate is still a statement about that group.
    """
    return basis_over(DEPARTMENT_SPAN_SCREEN, entitlement, now)


# ------------------------------------------------- agents and leash state (M27.3.12)
#: The screen whose grant decides whether a person may be named beside a rung change.
PROMOTION_APPROVER_SCREEN: Final = "people"


def leash_estate(
    matrices: Sequence[LeashMatrix],
    *,
    visible: Iterable[str],
) -> tuple[LeashMatrix, ...]:
    """Every agent's leash matrix that this reader may already see (M27.3.12).

    Narrowed by the audience rather than by a grant, and the two are different questions:
    `brain.agents.model` decides who may see that an agent exists and says in its own words
    that audience is not authority. A matrix for an agent the reader cannot see would disclose
    the agent through its configuration, which is
    `brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` broken by a table.

    `visible` is `brain.agents.model.visible_agent_ids`' own output, handed in so the audience
    question is answered by the module that owns it and not re-derived from an id's shape,
    which is `brain.console.workspace.resolve`'s construction.

    Every cell inside a matrix was looked up on its own by
    `brain.console.reach_view.leash_matrix`, which refuses to fill a blank cell from its
    neighbour. Nothing here touches a cell: an estate view that filled one would put the
    per-agent default back at exactly the layer that module says it must not be.

    Order follows `matrices`. One value comes back and there is nowhere in it for a count of
    the agents this reader was not shown.
    """
    seen = frozenset(visible)
    return tuple(one for one in matrices if one.agent_id in seen)


def rung_estate(
    changes: Mapping[str, Sequence[RungChange]],
    *,
    visible: Iterable[str],
) -> tuple[tuple[str, tuple[RungChange, ...]], ...]:
    """Every promotion and demotion, by agent, for the agents this reader may see (M27.3.12).

    Kept per agent rather than flattened into one chronological run, and the ordering inside
    each is `brain.console.reach_view.rung_history`'s rather than one written here. That
    function orders oldest first because a reviewer works forwards and a demotion is read
    against what raised the rung in the first place, and a flat estate-wide history would
    interleave two agents' arguments and lose both.

    Agents come back sorted by id, so two readings of an unchanged history are the same page.
    An agent with no changes is absent rather than present and empty, which is
    `brain.console.screens.grouped`'s rule about a section with nothing in it.
    """
    seen = frozenset(visible)
    return tuple(
        (agent_id, rung_history(changes[agent_id]))
        for agent_id in sorted(seen & frozenset(changes))
        if changes[agent_id]
    )


def approver_of(
    change: RungChange,
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> str:
    """Who approved this rung rise, when this reader may be told (M27.3.12).

    Empty for a demotion and empty when the reader may not be told, and the sameness is the
    point: `brain.console.reach_view.CircuitBreak` names a metric and no person, so a rung
    that fell has no approver to withhold, and a withheld approver is therefore
    indistinguishable from a change that never had one. See
    `NAMING_WHO_TRUSTED_AN_AGENT_FURTHER_IS_NAMING_A_PERSON`.

    Asked of the People screen's own read through `brain.console.reads.permitted` rather than
    of a capability invented for this column, which is
    `brain.console.govern.may_name_capabilities`' construction: a surface with its own
    capability is a way of reading one screen's contents without that screen's grant.
    """
    if not isinstance(change.evidence, PromotionEvidence):
        return ""
    if not permitted(screen(PROMOTION_APPROVER_SCREEN).read, entitlement, now):
        return ""
    return change.evidence.approver_id


# ------------------------------------------------------- skills and templates (M27.3.13)
@dataclass(frozen=True)
class SkillQueue:
    """What is waiting to be read, and the summary of exactly that (M27.3.13).

    Two fields that must be computed together, which is why they arrive together. See
    `A_SUMMARY_OVER_A_WIDER_LIST_THAN_THE_LISTING_IS_A_SUBTRACTION`: the failure is not a
    field somebody adds, it is two correct functions called over two different lists by a
    renderer doing the obvious thing.

    `summary` is `brain.tools.review.QueueSummary`, which carries counts and deliberately no
    names, because a skill's name describes a procedure somebody wants to run and that is a
    fact about what a team is doing. The counts are of the rows immediately below it.
    """

    entries: tuple[QueueEntry, ...]
    summary: QueueSummary


def skill_queue(
    entries: Sequence[Placed[QueueEntry]],
    entitlement: EntitlementSet,
    now: datetime,
) -> SkillQueue:
    """The skills waiting for this reader, with the summary of that list (M27.3.13).

    Narrowed by the Skills screen's own capability against the row each submission sits in,
    then summarised over what is left. The order of those two steps is the whole decision:
    summarising first and narrowing afterwards produces a number nobody could have derived
    from the page and a page nobody could have derived the number from, and the difference is
    how many skills are waiting that this reader may not read.

    `brain.tools.review.summarise` does the counting, so a stale entry is stale by that
    module's `STALE_AFTER` rather than by a threshold repeated here, and an edit is an edit
    because `diff_skills` said so.

    Order follows `entries`, which `brain.tools.review.pending` has already sorted oldest
    first: that is the one ordering nobody can game by caring more, and re-sorting here would
    discard it.
    """
    required = screen("skills").read.requires
    kept = tuple(one.record for one in entries if _in_reach(entitlement, required, one.where, now))
    return SkillQueue(entries=kept, summary=summarise(kept, now))


# -------------------------------------------------------- the knowledge library (M27.3.14)
#: Field names that would put a visibility predicate back on a library row.
#:
#: Restated here rather than imported, for the reason
#: `brain.console.govern.NAMES_THAT_WOULD_NAME_THE_THING` is restated: the word somebody
#: reaches for differs by surface, and the field that breaks this one is called `scope` or
#: `department` rather than `hidden`.
NAMES_THAT_WOULD_BE_A_PREDICATE: Final[frozenset[str]] = frozenset(
    {"clauses", "department", "owner", "owner_id", "predicate", "scope", "where"}
)


@dataclass(frozen=True)
class LibraryItem:
    """One knowledge item as the library screen is handed it.

    The visibility rather than the level, because `KnowledgeVisibility` is the one object that
    keeps a level and the identifiers it needs in step, and a caller passing a bare level
    would be passing the half that cannot build a predicate. What comes back to a reader is
    `LibraryRow`, which carries neither.
    """

    item_id: str
    visibility: KnowledgeVisibility


@dataclass(frozen=True)
class LibraryRow:
    """One item on the library screen: that it exists, and how wide it reaches (M27.3.14).

    Two fields and no third. There is no scope, no predicate, no department and no owner,
    which is `A_VISIBILITY_PREDICATE_NAMES_A_DEPARTMENT_AND_AN_OWNER` expressed as a shape
    rather than as a rule somebody remembers, and `estate_gaps` reports one if a later edit
    adds it.

    No content either. The Library screen is the existence plane in
    `brain.console.screens`' own registry, so a row says a document is there and never what is
    in it, and there is nowhere here for a title or a body.
    """

    item_id: str
    level: Visibility


def library_rows(
    items: Sequence[Placed[LibraryItem]],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[LibraryRow, ...]:
    """Every knowledge item this reader may know exists, with how wide it reaches (M27.3.14).

    Narrowed by the Library screen's own capability against the row the item sits in, which is
    the place question, and deliberately not by the item's own visibility scope, which is the
    reach question. The two are different and conflating them is the failure
    `brain.console.govern.may_certify` was found to have on 2026-09-08: a record is placed
    somewhere and it also confers something somewhere, and the check that was missing asked
    only about the first.

    Here the second is not a check at all, it is the column: the level is what the screen is
    for. A reader admitted to the row learns that a document exists in a department they
    already reach and how widely it is published, and neither of those is a fact about
    anybody else's reach.

    Order follows `items`, and there is no count of the ones left out.
    """
    required = screen("library").read.requires
    return tuple(
        LibraryRow(item_id=one.record.item_id, level=one.record.visibility.level)
        for one in items
        if _in_reach(entitlement, required, one.where, now)
    )


def departments_represented(
    items: Sequence[Placed[LibraryItem]],
    entitlement: EntitlementSet,
    *,
    basis: Basis,
    now: datetime | None = None,
) -> tuple[str, ...] | None:
    """The departments a library listing may be grouped by, or `None` (M27.3.14).

    **Withheld on the narrower basis rather than narrowed.** See
    `A_LISTING_HEADED_EVERY_DEPARTMENT_AND_SHOWING_FOUR_IS_A_CLAIM_NOBODY_CAN_CHECK`. That is
    `brain.console.workspace.projection`'s shape, and the argument transfers exactly: a
    grouping shown short under a heading claiming completeness is a confident answer that is
    wrong, which is worse than no answer.

    `basis` is handed in rather than computed here, which is `storage_summary`'s construction
    and the reason is the same: a caller renders several things at one basis and computing it
    per call would let two of them disagree inside one page. `spans_departments` is where it
    comes from.

    On the wider basis the departments come from the rows this reader may see, so the grouping
    can never name a department none of their rows sits in. The reader has therefore learnt
    nothing from the grouping that the rows did not already tell them, which is what makes it
    safe to show at all.

    Sorted, so two readings of an unchanged library are the same grouping.
    """
    if basis is not Basis.EVERYONE:
        return None
    required = screen("library").read.requires
    found = {
        one.where["department"]
        for one in items
        if "department" in one.where and _in_reach(entitlement, required, one.where, now)
    }
    return tuple(sorted(found))


# ---------------------------------------------------------- the learning review (M27.3.15)
#: Field names that would put a control over a page of learning changes on the review.
NAMES_THAT_WOULD_BE_A_BULK_CONTROL: Final[frozenset[str]] = frozenset(
    {"apply_all", "undo_all", "revert_all", "accept_all", "reject_all", "bulk"}
)


@dataclass(frozen=True)
class LearningReview:
    """What the system has inferred across the estate, with the tiers kept apart (M27.3.15).

    Four fields. `basis` is carried rather than left implicit, which is
    `brain.console.workspace.Headline`'s argument: a listing whose meaning is unstated is read
    as the whole of it, so a reader shown their own reach with no label reads it as the
    company's.

    `tier_three` is `None` on the narrower basis and never a shortened list; see
    `TIER_THREE_IS_THE_ONLY_LEARNING_ROW_THAT_NAMES_A_DEPARTMENT`.

    There is no bulk control and nowhere to put one; see
    `AN_UNDO_ALL_ACROSS_DEPARTMENTS_HAS_AN_UNREADABLE_BLAST_RADIUS`. Each tier-one row carries
    its own `control_writes`, which is a `brain.memory.correction.Correction` with two members
    and no third, so the one thing the control cannot express is a removal.
    """

    basis: Basis
    tier_one: tuple[TierOneRow, ...]
    tier_two: tuple[TierTwoRow, ...]
    #: Where each gated change was routed. `None` when the reader may not be grouped by
    #: department, which is not the same as no gated change existing.
    tier_three: tuple[TierThreeRouting, ...] | None


def learning_review(
    *,
    basis: Basis,
    visible: Iterable[str],
    tier_one: Mapping[str, Sequence[TierOneRow]],
    tier_two: Mapping[str, Sequence[TierTwoRow]],
    tier_three: Mapping[str, Sequence[TierThreeRouting]],
) -> LearningReview:
    """The three tiers across the estate, separated, with tier three withheld or whole
    (M27.3.15).

    Each mapping is what `brain.console.reach_view.tier_one_rows`, `tier_two_rows` and
    `tier_three_routing` returned for one agent, keyed by that agent. They are handed in
    rather than computed because those functions hold the decisions: tier one is newest first
    because the row somebody wants to undo is the one that just changed an answer they were
    reading, tier two carries `may_promote`'s verdict so the counting stays where the counting
    rule is, and tier three refuses a gated change whose scope names no department because the
    only queue left would be everybody's.

    Agents are visited in sorted order, so the review is the same page twice. Within an agent
    the owning function's order is kept, which is why the tiers are gathered rather than
    re-sorted: re-sorting tier one by memory id would discard the recency that makes the undo
    control findable.

    **The tiers are three tuples and never one list with a tier column.** A single list sorted
    by anything puts a proposal that is waiting for a person next to a change that has already
    happened, and the control beside them means different things. That is
    `brain.console.reach_view.SplitMemoryView`'s argument about curated and extracted memory,
    which is the same failure one surface over.
    """
    seen = sorted(frozenset(visible))
    ones: list[TierOneRow] = []
    twos: list[TierTwoRow] = []
    threes: list[TierThreeRouting] = []
    for agent_id in seen:
        ones.extend(tier_one.get(agent_id, ()))
        twos.extend(tier_two.get(agent_id, ()))
        threes.extend(tier_three.get(agent_id, ()))
    return LearningReview(
        basis=basis,
        tier_one=tuple(ones),
        tier_two=tuple(twos),
        tier_three=tuple(threes) if basis is Basis.EVERYONE else None,
    )


# --------------------------------------------------------------- artifacts (M27.3.16)
def artifact_estate(
    entries: Sequence[Artifact],
    reader: EntitlementSet,
    now: datetime,
    *,
    visible_agents: Iterable[str],
) -> tuple[Artifact, ...]:
    """What was produced across the estate, as this reader may see it (M27.3.16).

    **Assembled agent by agent and never by dropping the agent filter.** See
    `AN_ESTATE_LISTING_IS_ASSEMBLED_FROM_WHAT_THE_READER_CAN_ALREADY_SEE`.
    `brain.console.agent_output.visible_artifacts` is called once per agent and does all the
    deciding: it drops artifacts past their horizon before it filters anything, so an artifact
    that aged out and one that never existed produce the same row, and it asks `may_see`,
    which is where provenance and retention already meet the reader.

    **The agents the reader's own artifacts name are added to the set.** See
    `AN_ARTIFACT_OF_AN_AGENT_YOU_CANNOT_SEE_IS_STILL_YOURS`. Without that, a person's own
    output disappears the day an agent's audience narrows, and `may_see`'s first branch would
    be unreachable from this surface.

    Newest first with ties broken by id, which is `visible_artifacts`' own ordering restated
    over the assembled list rather than a second opinion about it: the per-agent calls each
    return a sorted run and concatenating sorted runs is not sorted.

    One value. There is nowhere in it for a count of the agents or the artifacts this reader
    was not shown, and the provenance on each row is
    `brain.console.agent_output.provenance_for`'s job at the moment one is opened.
    """
    mine = {one.agent_id for one in entries if one.caller_id == reader.principal_id}
    found: list[Artifact] = []
    for agent_id in sorted(frozenset(visible_agents) | mine):
        found.extend(visible_artifacts(entries, reader, now, agent_id=agent_id))
    return tuple(sorted(found, key=lambda one: (one.at, one.artifact_id), reverse=True))


# ------------------------------------------------------------- the memory viewer (M27.3.17)
@dataclass(frozen=True)
class SubjectMemory:
    """What is remembered about one person, and every revision of it (M27.3.17).

    One subject, named on the value, so a renderer holding this cannot be holding two people's
    memories and not know it. See `A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE`.

    `memory` is `brain.console.reach_view.SplitMemoryView`, which keeps curated and extracted
    apart because a single list sorted by confidence puts a guess above a statement the moment
    the guess is fresh. `history` is that module's `Revision`, whose diff is empty when the
    reader was not admitted to both sides and which carries no note saying so.
    """

    subject_id: str
    memory: SplitMemoryView
    history: tuple[Revision, ...]


def subject_memory(
    *,
    subject_id: str,
    entries: Sequence[tuple[Learning, str]],
    reader: EntitlementSet,
    now: datetime,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
    where: Mapping[str, object] | None = None,
) -> SubjectMemory:
    """One person's memory and its change history, at this reader's reach (M27.3.17).

    **`subject_id` is required and there is no value meaning everybody**, which is
    `brain.console.agent_output.visible_artifacts`' construction and the same argument: a
    viewer that could be asked for every subject is the directory with an optional filter on
    it, and the filter is what gets omitted. `estate_gaps` reads the signatures in this module
    for a parameter a list of subjects could arrive through.

    Both halves go through `brain.console.reach_view`, which computes `may_recall` itself
    rather than accepting a verdict, so a memory formed from somebody else's conversation is
    absent from both unless this reader reaches what it was formed from. Nothing here re-reads
    a tag or re-decides an admission.

    `entries` are the learnings and their statements, filtered here to the ones formed about
    this subject. The statement is handed in beside each learning because `Learning`
    deliberately does not carry one, and inventing a field for it would put the transcript
    back on the record that refuses to hold it.
    """
    if not subject_id.strip():
        msg = (
            "a memory viewer with no subject is a listing of what the system knows about "
            f"everybody. {A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE}"
        )
        raise EstateError(msg)
    theirs = [
        (learning, statement)
        for learning, statement in entries
        if learning.formation.principal_id == subject_id
    ]
    return SubjectMemory(
        subject_id=subject_id,
        memory=split_memory(theirs, reader, now=now, where=where),
        history=revisions(
            theirs,
            reader,
            now=now,
            supersessions=supersessions,
            demotions=demotions,
            where=where,
        ),
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of these surfaces is handed. Listed rather than discovered, following
#: `brain.console.govern.GOVERN_ROWS`: a type added here and not to this tuple is a type the
#: checks below never see.
ESTATE_ROWS: Final[tuple[type, ...]] = (SkillQueue, LibraryRow, LearningReview, SubjectMemory)

#: The functions whose signatures are read for a parameter that would widen them.
ESTATE_SIGNATURES: Final[tuple[Callable[..., object], ...]] = (
    artifact_estate,
    departments_represented,
    leash_estate,
    library_rows,
    rung_estate,
    skill_queue,
    subject_memory,
)

#: Parameter names by which a listing here could be asked for everybody at once.
NAMES_THAT_WOULD_ASK_FOR_EVERYBODY: Final[frozenset[str]] = frozenset(
    {"all_agents", "all_subjects", "everybody", "every_agent", "subjects", "unfiltered"}
)


def estate_gaps(
    *,
    rows: Sequence[type] = ESTATE_ROWS,
    library_row: type = LibraryRow,
    review_type: type = LearningReview,
    signatures: Sequence[Callable[..., object]] = ESTATE_SIGNATURES,
    span_screen: str = DEPARTMENT_SPAN_SCREEN,
    approver_screen: str = PROMOTION_APPROVER_SCREEN,
) -> tuple[str, ...]:
    """Everything about these six that would show somebody more than they hold.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason `brain.console.govern.govern_gaps` gives about itself: a diagnostic that can only
    run against the healthy tree has nothing to report on today's data, so switching off any
    of its refusals changes nothing observable and every one of them survives. Calling it with
    no arguments is the deployment check and calling it with a constructed set is the test.

    Five checks. The last is the one that would otherwise be a review comment: a listing here
    growing a parameter that asks for the whole estate at once, which is how the per-agent
    rule dies.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )
    gaps.extend(
        f"{library_row.__name__}.{name} puts a visibility predicate on a library row. "
        f"{A_VISIBILITY_PREDICATE_NAMES_A_DEPARTMENT_AND_AN_OWNER}"
        for name in getattr(library_row, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_A_PREDICATE
    )
    gaps.extend(
        f"{review_type.__name__}.{name} is a control over a page of changes. "
        f"{AN_UNDO_ALL_ACROSS_DEPARTMENTS_HAS_AN_UNREADABLE_BLAST_RADIUS}"
        for name in getattr(review_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_A_BULK_CONTROL
    )

    for key, what in ((span_screen, "the department span"), (approver_screen, "a promotion's")):
        try:
            screen(key)
        except KeyError:
            gaps.append(
                f"{what} grant is pinned against a screen named {key!r} that the registry "
                "does not have, so the decision rests on a capability nobody registered"
            )

    for one in signatures:
        taken = set(inspect.signature(one).parameters)
        gaps.extend(
            f"{one.__name__} takes {name}, so this listing can be asked for the whole estate "
            f"at once. {AN_ESTATE_LISTING_IS_ASSEMBLED_FROM_WHAT_THE_READER_CAN_ALREADY_SEE}"
            for name in sorted(taken & NAMES_THAT_WOULD_ASK_FOR_EVERYBODY)
        )

    return tuple(gaps)


#: How many surfaces are claimed here, so a test can pin it and a person can quote it.
#:
#: Pinned rather than computed, for the reason `brain.console.govern.GOVERN_SURFACE_COUNT` is,
#: and checked against this module's own `Task ids:` lines rather than against a tuple in it,
#: so the constant cannot agree with itself.
ESTATE_COUNT: Final = 6
