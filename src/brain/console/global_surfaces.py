"""What a Super Admin is shown of the whole install, and the four acts only they perform.

Every screen in this group is company-wide by construction, which is what makes it the group
where a filter is most useful and a filter is most dangerous. A listing of every agent, skill,
knowledge item and connector is the estate; a listing narrowed by department is the estate plus
the answer to "which departments are there", and the second is a disclosure the rows were
carefully scoped to avoid. `brain.console.screens.offerable` already refuses to populate a
dropdown from a table, and this refuses the matching failure one level down: **a filter narrows
within what the reader may see and never widens it**, so `estate` applies the lens after the
visibility check and never before, which is
`brain.console.agent_output.visible_artifacts`' argument about its own filter arguments,
reached for a different surface and answered the same way.

**Almost none of the machinery is here.** The stop button is `brain.ops.halt`, the money is
`brain.ops.spend` and `brain.ops.budgets`, the publication request and its gate are
`brain.knowledge.visibility`, the role grant and its floor are `brain.identity.roles`,
disabling a leaver is `brain.identity.lifecycle.disable`, and the self-grant detection is
`brain.console.reads`. `Placed` is imported from `brain.console.govern` rather than written
again, because a governance record paired with the row its subject sits in is one idea and that
module has it. What is decided here is who may press each control and which rows each listing
shows.

**A role listing is not a reach and this group is where somebody would forget that.** Nothing
below reads a role to decide access. `confirm` produces a `RoleGrant`, which governs the
platform, and the permission to produce one is a capability the confirmer holds, which governs
data. The two are kept apart by `brain.identity.roles` and this module changes nothing about
that: `brain.console.screens.navigation` still takes an `EntitlementSet` and nothing else.

**One control capability, three surfaces, and it is `approve:grant` for the same reason each
time.** Confirming a nomination writes a role grant. Disabling a principal deletes every grant
they hold and ends the sessions those grants were read through. Both are the grant decision,
which is the capability the Access review screen already requires, so inventing
`admin:principal` for either would put a capability into the system from the rendering layer
where the administrator reviewing grants would never meet it. That is
`brain.console.govern.SESSION_CONTROL`'s argument, and `GOVERNANCE_CONTROL` is written out and
pinned against that screen by test rather than derived from it, so repointing either fails.

**Confirming a nomination you made, or one of yourself, is one person passing a gate alone.**
`brain.knowledge.visibility.approve_promotion` refuses the proposer, and
`brain.console.govern.Certification` refuses the subject, for the same reason in two places:
there is a proposal, there is an approval, and they are the same person twice. `Nomination`
refuses the second in its constructor and `confirm` refuses the first, and the split is
deliberate: a nominee nominating themselves is a value nobody should be able to build, and a
nominator confirming their own nomination depends on who is asking and cannot be known when the
object is made. `brain.console.govern.Certification` puts its refusal in the constructor on
exactly that distinction.

**A company figure moves when anybody works, so it follows the budget screen's grant.**
`brain.console.workspace.basis_for` is that rule already written down, and this asks it rather
than inventing a second answer. On the narrower basis the consumption is withheld and not
narrowed: a company total assembled from one reader's own rows is a confident figure that is
wrong, which is `brain.console.workspace.projection`'s decision and
`brain.ops.spend.A_REFUSAL_CARRIES_NO_FIGURE` in the reporting direction. There is no row for
everybody else and no percentage anywhere, because a share is the total divided by a figure the
reader was not shown.

**The kill switch is real and two of its axes are not, which is worth saying on the screen that
offers it.** `brain.ops.halt.ENFORCED_AXES` is `EVERYTHING` and `CONNECTOR`, because
`brain.ops.admission.decide` is handed a connector and nothing else, so a halt on a department,
an agent or a person is stored, in force, shown as in force, and refuses no request anywhere.
The global kill switch this leaf asks for is the one that works. `inert_axes` names the ones
that do not, read off that module's own set rather than restated, so the day a call site learns
an axis this stops reporting it without anybody editing this file.

**Two leaves under this heading are not claimed and each needs something that does not exist.**
M33.1.1.2 asks for all activity under the same department and person filters. The activity
record is the audit ledger, `brain.audit.view.AuditView` filters it to one reader, and
`AuditFilter` offers actors and not departments. That is not an omission in the filter: an
audit entry carries no department at all, `_scope_row` says so by listing the four fields a
grant's scope may be written against, and that module records rejecting the idea of passing
per-entry attributes in from outside. So the person axis is honourable today and the department
axis is not, and `activity_filter` refuses a department lens rather than dropping it silently,
which is `brain.console.screens.Screen.accepts`' rule: a filter that is quietly ignored leaves
the reader believing they are looking at one department while looking at all of them.

**M33.1.2.1 asks to publish and retire global agents, and until 2026-09-08 only retiring
existed.** `brain.agents.lifecycle` held enable, disable, archive and transfer_ownership, and
an agent is published company-wide by its `AgentAudience` reaching `Visibility.COMPANY`, which
nothing changed. This module reported that rather than half-building it, because writing an
agent state transition in a console module is a transition living outside the module that owns
transitions, which is the second implementation this repository refuses.

`lifecycle.publish` and `lifecycle.archive` are both there now, so the surface is two calls
and a listing, and neither transition is written here. What this module decides is the part
that is a console question: which agents a reader is offered the control for, and that is the
estate's own narrowing rather than a third rule. The authority is `lifecycle`'s own capability
and is deliberately not `GOVERNANCE_CONTROL`, because publishing widens who is told about an
agent and never what it reaches: `AUDIENCE_IS_NOT_AUTHORITY` is the distinction, and a console
that asked for the grant-writing capability here would be asserting the opposite.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock; `now`
is a parameter for the reason `brain.ops.limits` gives about policy that owns a client. No
console screen exists behind any of these, exactly as `brain.console.screens` says of its own
registry; what is claimed is the disclosure decision, which is the whole content of each.

Task ids: M33.1.1.1, M33.1.1.3, M33.1.1.4, M33.1.2.1, M33.1.2.2
Task ids: M33.1.2.3, M33.1.2.4, M33.1.2.5
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.agents.lifecycle import AGENT_PUBLICATION_CAPABILITY, PUBLICATION_LEVEL
from brain.agents.model import AgentRecord
from brain.audit.ledger import AuditEntry
from brain.console.govern import Placed
from brain.console.reads import StewardNotice, permitted, self_grants
from brain.console.screens import SCREENS, Axis, Lens, screen
from brain.console.workspace import Basis, basis_for
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Principal
from brain.core.scope import Scope
from brain.identity.lifecycle import Disablement, disable
from brain.identity.packs import CapabilityPack, PackAssignment, SubjectGrant
from brain.identity.roles import Role, RoleGrant, standing_super_admins
from brain.identity.sessions import SessionRegistry
from brain.identity.teams import TeamMembership
from brain.knowledge.visibility import (
    PROMOTION_CAPABILITY,
    Approval,
    PromotionProposal,
    approve_promotion,
)
from brain.ops.halt import ENFORCED_AXES, HALT_CAPABILITY, Halt, HaltScope, stop_everything
from brain.ops.jobs import hidden_count_fields
from brain.ops.spend import Actual, Dimension, spend_by, total_minor

# ------------------------------------------------------------------ written-down reasons
#: Why the lens is applied after the visibility check and not before.
A_FILTER_APPLIED_FIRST_IS_A_FILTER_WHOSE_RESULT_REVEALS_WHAT_IT_REMOVED: Final = (
    "Asking the estate for one department and getting nothing has to be the same answer as "
    "asking for a department that owns nothing, and that is true only if the reader's own "
    "narrowing has already happened. A listing that filtered first and checked afterwards "
    "would answer which departments hold agents, to anybody able to type a name into a query "
    "string, and every test asserting the rows are correct would still pass. The lens is "
    "therefore a parameter of the listing rather than a second function over its result."
)

#: Why the estate is four listings behind four separate grants.
EACH_KIND_IS_ITS_OWN_DISCLOSURE_AND_ITS_OWN_SCREEN: Final = (
    "Everything on one page is not everything under one grant. A reader who may see the "
    "connectors and not the knowledge library holds two different capabilities, and an "
    "estate that asked one question would either show them the library or hide the "
    "connectors. So the kind decides which registered screen's read governs the row, which "
    "is the same capability and plane they would need to open that screen directly, and a "
    "kind withheld and a kind with nothing in it produce an identical listing."
)

#: Why one capability governs nominations and disablement.
CONFIRMING_A_ROLE_AND_DISABLING_A_PRINCIPAL_ARE_BOTH_THE_GRANT_DECISION: Final = (
    "A confirmed nomination is a role grant written. A disabled principal is every grant "
    "they hold deleted and every session those grants were read through ended. Both are the "
    "authority to decide what somebody may reach, which is approve:grant, the capability the "
    "Access review screen already requires. A capability of this module's own would be a "
    "grant entering the system from the rendering layer, where the administrator who reviews "
    "grants would never meet it, and there would then be two answers to one question."
)

#: Why a nomination cannot be confirmed by the person who made it.
A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE: Final = (
    "brain.knowledge.visibility.approve_promotion refuses an approver who is the proposer and "
    "says why: self-approval leaves every record looking correct, because there is a "
    "proposal, there is an approval, and they are the same person twice. A role nomination is "
    "the same shape with a wider consequence, so the nominee is refused in the constructor, "
    "where a hand-built object cannot go around it, and the nominator is refused in confirm, "
    "because who is confirming is not known when the nomination is written."
)

#: Why a company figure is withheld rather than narrowed.
A_COMPANY_TOTAL_ASSEMBLED_FROM_ONE_READERS_ROWS_IS_CONFIDENTLY_WRONG: Final = (
    "Company consumption is everybody's spend, so a reader without the budget screen's grant "
    "cannot be shown a narrower version of it: their own rows under a heading reading company "
    "consumption is a number that looks like the answer and is not, which is worse than no "
    "number. brain.console.workspace.projection reaches the same conclusion about a month-end "
    "projection and returns None on the narrower basis, and this returns None for the same "
    "reason rather than inventing a partial figure."
)

#: Why the screen offering the stop button says which axes it does not cover.
A_HALT_ON_AN_AXIS_NOTHING_CONSULTS_IS_A_SCREEN_READING_STOPPED: Final = (
    "brain.ops.admission.decide is handed a resource, a lane, a traffic class and a "
    "connector, and no principal, department or agent, so a halt declared on one of those "
    "three is stored, reported as in force, rendered on a screen, and refuses nothing. The "
    "administrator stopping a compromised account is the last person in a position to go and "
    "read which call sites exist. ENFORCED_AXES is read rather than restated, so the day a "
    "call site learns an axis this stops naming it with no edit here."
)

#: Why the activity view refuses a department filter rather than ignoring it.
A_FILTER_SILENTLY_DROPPED_IS_WORSE_THAN_ONE_REFUSED: Final = (
    "An audit entry carries an action, a subject kind, a subject and an actor, and no "
    "department: brain.audit.view._scope_row lists those four and that module records "
    "rejecting the idea of supplying attributes from outside, because it would make an "
    "entry's visibility depend on a mapping the view cannot check. So a department lens over "
    "activity cannot be honoured, and honouring it by returning everything is the failure "
    "brain.console.screens.Screen.accepts names: the reader believes they are looking at one "
    "department and is looking at all of them."
)


class GlobalSurfaceError(Exception):
    """A company-wide surface was asked for something it must not do.

    Outside `brain.core.errors` for the reason `brain.console.govern.GovernError` gives: those
    five outcomes describe an answer to somebody asking a question, and this is a refusal to
    assemble an administrative surface or to perform a control. Nobody asking a question ever
    sees one.
    """


# ------------------------------------------------------------ the estate (M33.1.1.1)
class EstateKind(enum.StrEnum):
    """The four things a company-wide listing is made of. Exactly the leaf's list.

    Four members and no fifth for "everything", which is the member somebody adds so a caller
    can ask one question. A kind that meant every kind would be a row governed by no single
    screen's grant, and whichever grant it ended up asking for would be the widest.
    """

    AGENT = "agent"
    SKILL = "skill"
    KNOWLEDGE = "knowledge"
    CONNECTOR = "connector"


#: A lens narrowing nothing. A module-level singleton rather than a call in the signature,
#: which `Lens` being frozen makes safe and which the linter requires anyway.
NARROWS_NOTHING: Final = Lens()

#: Which registered screen's read governs each kind.
#:
#: Screen keys rather than capabilities written out, so a kind cannot drift from the screen a
#: reader would open to see the same rows: `estate` asks `brain.console.reads.permitted` about
#: that screen's own read, which is the tool's capability and the console plane together.
#: `brain.console.workspace.SPEND_OF_OTHERS_SCREEN` is the same construction for money.
ESTATE_SCREEN: Final[Mapping[EstateKind, str]] = MappingProxyType(
    {
        EstateKind.AGENT: "agents",
        EstateKind.SKILL: "skills",
        EstateKind.KNOWLEDGE: "library",
        EstateKind.CONNECTOR: "connectors",
    }
)


@dataclass(frozen=True)
class EstateRow:
    """One thing in the install, and the row that says where it sits.

    `where` is the pairing `brain.console.govern.Placed` makes for a governance record, made
    again here because an estate row is the record: a scope is a predicate over rows, and an
    agent id, a skill name and a connector slug are not rows. There is no field for a
    department read off the identifier, because an identifier that encodes a department is a
    convention this product cannot rely on across installs.

    No field is a count of anything, which `global_gaps` asks of the type rather than of
    whoever edits it next.
    """

    kind: EstateKind
    item_id: str
    where: Mapping[str, str] = MappingProxyType({})


def _in_reach(
    entitlement: EntitlementSet,
    capability: Capability,
    where: Mapping[str, str],
    now: datetime | None = None,
) -> bool:
    """Whether this reader holds `capability` in a scope admitting this row.

    `EntitlementSet.scope_for` followed by `Scope.matches`, which is the pair of public calls
    `brain.console.govern._in_reach` makes about a governance record,
    `brain.console.role_surfaces._may_approve` makes about an approver and
    `brain.console.agent_output.may_see` makes about an artifact. Two public calls rather than
    an intersection: `scope_for` decides what holding it means and refuses an expired
    principal, and `matches` decides whether the grant admits the place.
    """
    scope: Scope | None = entitlement.scope_for(capability, now)
    if scope is None:
        return False
    return scope.matches(dict(where))


def visible_estate(
    rows: Sequence[EstateRow],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[EstateRow, ...]:
    """Everything in the install this reader may know exists, in the order given (M33.1.1.1).

    Two checks per row and they are different questions. Whether this reader could open the
    screen the kind belongs to, which is the tool's capability and the console plane together;
    and whether their grant of that capability is in a scope that admits the row. A reader can
    pass the first and fail the second for one row and not another, which is the ordinary
    department case rather than an edge.

    See `EACH_KIND_IS_ITS_OWN_DISCLOSURE_AND_ITS_OWN_SCREEN`. A kind the reader holds nothing
    for contributes no rows and no heading, so a withheld kind and an empty one are one
    absence, which is `brain.console.workspace.tab_strip`'s rule about a tab.

    Order follows `rows`, for the reason `brain.console.screens.offerable` gives: the caller's
    order is usually meaningful and re-sorting discards it. One value comes back and there is
    nowhere in it for a count of what was left out.
    """
    return tuple(
        one
        for one in rows
        if permitted(screen(ESTATE_SCREEN[one.kind]).read, entitlement, now)
        and _in_reach(entitlement, screen(ESTATE_SCREEN[one.kind]).read.requires, one.where, now)
    )


def estate(
    rows: Sequence[EstateRow],
    entitlement: EntitlementSet,
    *,
    lens: Lens = NARROWS_NOTHING,
    kinds: Iterable[EstateKind] = (),
    now: datetime | None = None,
) -> tuple[EstateRow, ...]:
    """The estate, narrowed by department and by person, within what the reader sees (M33.1.1.1).

    **The lens is a parameter here rather than a second function**, and that is the whole
    disclosure argument. See
    `A_FILTER_APPLIED_FIRST_IS_A_FILTER_WHOSE_RESULT_REVEALS_WHAT_IT_REMOVED`. A `narrow_by`
    taking a list of rows is a function somebody eventually calls before `visible_estate`,
    and the estate becomes a way of asking which departments own anything.

    `Lens.department` and `Lens.person` are matched against the row's own `where`, which is
    the same mapping the reader's scope was matched against, so a filter can only ever pick
    out a subset of what the previous step already admitted. The other three axes are not
    honoured and are refused rather than dropped, on
    `A_FILTER_SILENTLY_DROPPED_IS_WORSE_THAN_ONE_REFUSED`: an estate row carries a department
    and an owner and nothing that answers a period or a model.

    Returns one value. There is no second one carrying what the filter removed, which is
    `brain.console.screens.navigation`'s rule and `role_surfaces.pending_for`'s.
    """
    unusable = lens.axes_used() - {Axis.DEPARTMENT, Axis.PERSON}
    if unusable:
        names = ", ".join(sorted(one.value for one in unusable))
        msg = (
            f"the estate cannot be narrowed by {names}; an estate row carries a department and "
            f"an owner and nothing else a filter could match. "
            f"{A_FILTER_SILENTLY_DROPPED_IS_WORSE_THAN_ONE_REFUSED}"
        )
        raise GlobalSurfaceError(msg)
    wanted = frozenset(kinds)
    return tuple(
        one
        for one in visible_estate(rows, entitlement, now)
        if (not wanted or one.kind in wanted)
        and (not lens.department or one.where.get("department") == lens.department)
        and (not lens.person or one.where.get("owner_id") == lens.person)
    )


# ----------------------------------------------------------------- activity (not claimed)
def activity_filter(lens: Lens) -> frozenset[str]:
    """The actor ids an activity view may be narrowed to, or a refusal.

    The half of "all activity with the same filters" that the ledger can honour. A person
    lens becomes an exact actor reference, which is what `brain.audit.view.AuditFilter.actors`
    takes and the only thing it takes: that model refuses anything that is not an identifier,
    because a substring filter over a ledger is a search engine over a permission map.

    A department lens is refused. See `A_FILTER_SILENTLY_DROPPED_IS_WORSE_THAN_ONE_REFUSED`.
    Returning everything would be the version somebody builds because it looks like it works.
    """
    if lens.department:
        msg = (
            f"activity cannot be narrowed by department: an audit entry carries an action, a "
            f"subject kind, a subject and an actor, and no department. "
            f"{A_FILTER_SILENTLY_DROPPED_IS_WORSE_THAN_ONE_REFUSED}"
        )
        raise GlobalSurfaceError(msg)
    return frozenset({lens.person}) if lens.person else frozenset()


# -------------------------------------------------- company budget and consumption (M33.1.1.3)
@dataclass(frozen=True)
class CompanyConsumption:
    """What the install spent, and how it divides (M33.1.1.3).

    A total and one breakdown, both from `brain.ops.spend`, so the company screen and an
    agent's front page cannot disagree about what a run cost. There is no share, no
    percentage and no rank: each is the same figure divided by a total, and two of them
    recover a figure the reader was never given on its own.

    There is no row for everybody else and no residual bucket, on
    `brain.console.workspace.AN_OTHERS_ROW_IS_EVERYBODY_ELSE_ADDED_UP`. The breakdown is
    complete because it is built on the wider basis or not at all.
    """

    spend_minor: int
    by_department: tuple[tuple[str, int], ...]


def company_consumption(
    actuals: Sequence[Actual],
    entitlement: EntitlementSet,
    *,
    since: datetime,
    until: datetime,
    now: datetime | None = None,
) -> CompanyConsumption | None:
    """The company's spend over one window, or `None` when it would be somebody else's
    (M33.1.1.3).

    `None` on the narrower basis, and withheld rather than narrowed. See
    `A_COMPANY_TOTAL_ASSEMBLED_FROM_ONE_READERS_ROWS_IS_CONFIDENTLY_WRONG`.
    `brain.console.workspace.basis_for` is what decides, which is the budget screen's own
    grant asked through `permitted`, so a reader sees the company total exactly when they
    could open the budget screen and read it there.

    Machine rows are counted. `brain.ops.spend` labels them rather than dropping them, and an
    automation running as a named principal spent the company's money whichever way the
    report eventually presents it; excluding them here would make this figure disagree with
    every other total in the system.

    Ordered by spend and then by department, so two readings of an unchanged ledger are the
    same list and a tie is not broken by whatever the mapping happened to iterate.
    """
    if basis_for(entitlement, now) is not Basis.EVERYONE:
        return None
    rows = tuple(one for one in actuals if since <= one.at <= until)
    totals = spend_by(rows, Dimension.DEPARTMENT)
    return CompanyConsumption(
        spend_minor=total_minor(rows),
        by_department=tuple(sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))),
    )


# ------------------------------------------------------------ the kill switch (M33.1.1.4)
#: The capability that stops everything.
#:
#: Written out rather than imported from `brain.ops.halt`, so a test can compare the two
#: against each other and against the Halt screen's own requirement: imported, the comparison
#: would be a constant against itself and repointing either would move both.
#: `brain.console.govern.SESSION_CONTROL` is pinned the same way.
KILL_SWITCH: Final = Capability(value="admin:halt")


def may_stop(entitlement: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may stop the whole install (M33.1.1.4).

    The capability and nothing else. No scope is matched against a row, and that absence is
    the statement: a halt on everything covers every department, so narrowing the check to a
    row would be asking whether they may stop a department they named, which is a different
    and currently inert control. `brain.ops.halt.ENFORCED_AXES` says why.
    """
    return entitlement.scope_for(KILL_SWITCH, now) is not None


def press_stop(
    entitlement: EntitlementSet,
    *,
    at: datetime,
    reason: str,
    now: datetime | None = None,
) -> Halt:
    """Stop everything, or refuse (M33.1.1.4).

    `brain.ops.halt.stop_everything` builds it, so both effects are carried and neither can
    be omitted by somebody in a hurry: a halt refusing new work while in-flight jobs keep
    writing is the first of the five lies that module names, and
    `effects=frozenset({REFUSE_NEW})` is a plausible thing to type.

    **No approval, no confirmation, no second signature.** Stopping is unilateral, which is
    `brain.ops.halt.THE_GUARDED_ACT_IS_RESUME_AND_NEVER_STOP`: a stop button with a
    confirmation step is one that can fail at the moment it is needed. The guarded act is
    resume, and that is that module's to guard.

    `declared_by` is the entitlement's own principal rather than a parameter, so a caller
    cannot pass one name in one argument and somebody else's reach in another and have the
    install halted on behalf of a person who was never asked. That is
    `brain.knowledge.visibility.approve_promotion`'s third check, made structural.

    Raises rather than returning `None`. A refusal here discloses nothing, because
    `brain.ops.halt.A_HALT_DISCLOSES_NOTHING_ABOUT_WHAT_ANYBODY_MAY_SEE` applies in both
    directions, and a stop button that silently does nothing is the worst control in the
    product.
    """
    if not may_stop(entitlement, now):
        msg = (
            f"{entitlement.principal_id!r} may not stop this install; the kill switch is "
            f"{KILL_SWITCH.value} and nothing else confers it"
        )
        raise GlobalSurfaceError(msg)
    return stop_everything(declared_by=entitlement.principal_id, at=at, reason=reason)


def inert_axes() -> tuple[HaltScope, ...]:
    """The halt scopes nothing consults, in declaration order (M33.1.1.4).

    Read off `brain.ops.halt.ENFORCED_AXES` rather than listed here. See
    `A_HALT_ON_AN_AXIS_NOTHING_CONSULTS_IS_A_SCREEN_READING_STOPPED`: a list written here
    would be a second statement of which axes work, and the day admission learns a principal
    this one would go on naming an axis that had started working.
    """
    return tuple(one for one in HaltScope if one not in ENFORCED_AXES)


# ------------------------------------------ department publication requests (M33.1.2.2)
def may_approve_publication(
    request: Placed[PromotionProposal],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this reader may decide this publication request (M33.1.2.2).

    Two conditions and they are different questions. The promotion capability in a scope
    admitting the row the item sits in, which is
    `brain.knowledge.visibility.PROMOTION_CAPABILITY` asked through `_in_reach` rather than a
    capability of this module's own. And that the reader is not the proposer, because
    `approve_promotion` refuses that and a queue offering a row it will refuse invites the
    attempt and then explains it, which is the shape `brain.console.role_surfaces` rejected
    for expired suspensions.
    """
    if entitlement.principal_id == request.record.proposer_id:
        return False
    return _in_reach(entitlement, PROMOTION_CAPABILITY, request.where, now)


def publication_queue(
    requests: Sequence[Placed[PromotionProposal]],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[Placed[PromotionProposal], ...]:
    """The publication requests this reader may decide (M33.1.2.2). No count of the rest.

    Filtered before it is rendered rather than rendered whole with the out-of-scope rows
    disabled, which is the version that gets built because it looks more informative. A
    disabled row is the request disclosed with a reason attached, and the request names an
    item, a department and a person who asked, which is three facts about work the reader was
    not admitted to.

    Order follows `requests`, which is usually oldest first and is information.
    """
    return tuple(one for one in requests if may_approve_publication(one, entitlement, now))


def approve_publication(
    request: Placed[PromotionProposal],
    entitlement: EntitlementSet,
    *,
    now: datetime,
) -> Approval:
    """Approve one department's request to publish company-wide (M33.1.2.2).

    `brain.knowledge.visibility.approve_promotion` performs it, unchanged and not
    reimplemented: it holds the three checks that make an approval mean anything, including
    the one this module cannot make, which is that the entitlement offered belongs to the
    approver named.

    `may_approve_publication` is asked here as well as by `publication_queue`, and that is
    not belt and braces: the listing decides what a screen offers and this decides what a
    submitted form may do, and a form is submitted by whatever was posted rather than by what
    was offered. That is `brain.console.govern.certify`'s argument in the same words because
    it is the same situation.
    """
    if not may_approve_publication(request, entitlement, now):
        msg = (
            f"{entitlement.principal_id!r} may not approve publication of "
            f"{request.record.item_id!r} over {dict(request.where)!r}"
        )
        raise GlobalSurfaceError(msg)
    return approve_promotion(
        request.record,
        approver_id=entitlement.principal_id,
        entitlement=entitlement,
        now=now,
    )


# ------------------------------------------------------ role nominations (M33.1.2.3)
#: The capability that confirms a nomination and disables a principal.
#:
#: The Access review screen's own requirement, written out here rather than derived from the
#: registry so a test can compare the two. See
#: `CONFIRMING_A_ROLE_AND_DISABLING_A_PRINCIPAL_ARE_BOTH_THE_GRANT_DECISION`.
GOVERNANCE_CONTROL: Final = Capability(value="approve:grant")


@dataclass(frozen=True)
class Nomination:
    """One person proposed for one role, by somebody who is not them (M33.1.2.3).

    **The self-nomination refusal is in the constructor.** A rule enforced only by the
    function that usually builds the object is one a hand-built object goes around, which is
    where `brain.console.govern.Certification` and `brain.console.reads.StewardNotice` both
    put their equivalent refusals. See `A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE`.

    Carries no grant and confers nothing. It is a proposal, and the `RoleGrant` that `confirm`
    returns is the first object in this flow that means anything, built through that model's
    own validators so a scope missing from a Department Admin nomination fails there rather
    than being invented here.
    """

    principal_id: str
    role: Role
    nominated_by: str
    reason: str
    at: datetime
    #: Required for the roles in `brain.identity.roles.SCOPE_REQUIRED`, refused for the
    #: others. Not checked here: `RoleGrant` is the one statement of that rule.
    scope: Scope | None = None

    def __post_init__(self) -> None:
        if not self.principal_id.strip() or not self.nominated_by.strip():
            msg = "a nomination naming nobody cannot be confirmed or reviewed"
            raise GlobalSurfaceError(msg)
        if not self.reason.strip():
            msg = (
                "a nomination with no reason is one nobody can review later, and the review "
                "is the only thing that ever removes an appointment that should not have been"
            )
            raise GlobalSurfaceError(msg)
        if self.at.tzinfo is None:
            msg = "a naive nomination time compares wrongly against an aware confirmation"
            raise GlobalSurfaceError(msg)
        if self.nominated_by == self.principal_id:
            msg = (
                f"{self.principal_id!r} nominated themselves for {self.role}. "
                f"{A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE}"
            )
            raise GlobalSurfaceError(msg)


def may_confirm(
    nomination: Nomination,
    entitlement: EntitlementSet,
    where: Mapping[str, str],
    now: datetime | None = None,
) -> bool:
    """Whether this reader may confirm this nomination (M33.1.2.3).

    Three conditions. The reader is not the nominee, the reader is not the nominator, and the
    reader holds `GOVERNANCE_CONTROL` in a scope admitting the row the nominee sits in. The
    first is already impossible to write into a `Nomination` for the nominator and is checked
    again for the confirmer, because a nominee and a confirmer are different fields and only
    one of them existed when the object was built.
    """
    if entitlement.principal_id in {nomination.principal_id, nomination.nominated_by}:
        return False
    return _in_reach(entitlement, GOVERNANCE_CONTROL, where, now)


def confirm(
    nomination: Nomination,
    entitlement: EntitlementSet,
    *,
    where: Mapping[str, str],
    at: datetime,
    now: datetime | None = None,
) -> RoleGrant:
    """Turn a confirmed nomination into the role grant it asked for (M33.1.2.3).

    The grant is built by `brain.identity.roles.RoleGrant`, so every rule about what a role
    grant may be is enforced by the one model that states them: a scope required for a
    Department Admin and refused for a Super Admin, a `not_after` after a `granted_at`, an
    identifier that is not itself a role name. None of those is repeated here, and a
    nomination that would produce an invalid grant fails in that constructor with that
    model's own message.

    `granted_by` is the confirmer and never the nominator, because the row that explains
    where a role came from should name the person who decided rather than the person who
    asked. The reason is the nomination's, carried across unchanged so the sentence somebody
    reviewing the grant reads is the one somebody wrote when proposing it.
    """
    if not may_confirm(nomination, entitlement, where, now):
        msg = (
            f"{entitlement.principal_id!r} may not confirm {nomination.principal_id!r} as "
            f"{nomination.role}. "
            f"{CONFIRMING_A_ROLE_AND_DISABLING_A_PRINCIPAL_ARE_BOTH_THE_GRANT_DECISION}"
        )
        raise GlobalSurfaceError(msg)
    return RoleGrant(
        principal_id=nomination.principal_id,
        role=nomination.role,
        scope=nomination.scope,
        granted_by=entitlement.principal_id,
        reason=nomination.reason,
        granted_at=at,
    )


# ------------------------------------------------------- disable a principal (M33.1.2.4)
#: Why publishing asks for the visibility capability and not the one that writes grants.
#:
#: A publication widens who is told about an agent and never what the agent reaches: the run
#: reach has no term for an audience, so a published agent hands nobody a row. Asking for
#: `GOVERNANCE_CONTROL` here would say the opposite, and it would refuse the person the leaf
#: names, since a super administrator deliberately not granted a department's data could not
#: publish that department's agent while publishing it lets them read none of it.
PUBLISHING_WIDENS_WHO_IS_TOLD_AND_NEVER_WHAT_IS_REACHED: Final = (
    "Publishing an agent moves its audience to the whole company and moves no reach at all. "
    "So the authority is the visibility capability that brain.agents.lifecycle owns, and not "
    "the capability that writes grants: asking for the second would make the audience a "
    "function of somebody's reach, which is the conflation AUDIENCE_IS_NOT_AUTHORITY refuses."
)


def may_publish(entitlement: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may move an agent's audience to the whole company (M33.1.2.1).

    One capability and no scope, because an audience is not a row: publishing does not happen
    somewhere, it happens to everybody at once, and a department-scoped grant over it would
    be a grant to publish company-wide within one department, which is not a thing.

    See `PUBLISHING_WIDENS_WHO_IS_TOLD_AND_NEVER_WHAT_IS_REACHED`. The steward rule is
    `lifecycle.publish`'s own and is not repeated here: it needs the record, this does not
    have one, and asking half the question in two places is how the two answers drift.
    """
    return entitlement.holds(AGENT_PUBLICATION_CAPABILITY, now)


def publishable(
    records: Sequence[AgentRecord],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[AgentRecord, ...]:
    """The agents this reader could publish, offered only where the control would work.

    Empty for a reader without the capability rather than a list they cannot act on, which is
    the shape `brain.console.role_surfaces` chose for expired suspensions: a queue offering a
    row it will refuse invites the attempt and then explains it.

    Already-company agents are absent, because `publish` is a no-op for them and an offer that
    changes nothing reads as an offer that does something. Archived ones are absent because
    `publish` refuses them: archived is terminal, and publishing one would put a thing nobody
    can start in front of everybody.

    The steward exclusion is applied here as well as in `publish`, and that is not a duplicate
    check: this decides what is offered and that decides what happens, which is the same pair
    `approve_publication` and its queue already keep.
    """
    if not may_publish(entitlement, now):
        return ()
    return tuple(
        one
        for one in records
        if one.audience.level is not PUBLICATION_LEVEL
        and one.archived_at is None
        and one.audience.owner_id != entitlement.principal_id
    )


def may_disable(
    entitlement: EntitlementSet,
    where: Mapping[str, str],
    now: datetime | None = None,
) -> bool:
    """Whether this reader may disable somebody sitting in this row (M33.1.2.4).

    `GOVERNANCE_CONTROL` in a scope admitting the row. See
    `CONFIRMING_A_ROLE_AND_DISABLING_A_PRINCIPAL_ARE_BOTH_THE_GRANT_DECISION`: disabling
    deletes every grant a person holds and ends the sessions those grants were read through,
    which is the grant decision taken all at once.
    """
    return _in_reach(entitlement, GOVERNANCE_CONTROL, where, now)


def disable_principal(
    principal: Principal,
    entitlement: EntitlementSet,
    *,
    where: Mapping[str, str],
    registry: SessionRegistry,
    at: datetime,
    grants: Sequence[SubjectGrant] = (),
    assignments: Sequence[PackAssignment] = (),
    packs: Mapping[str, CapabilityPack] | None = None,
    memberships: Sequence[TeamMembership] = (),
    now: datetime | None = None,
) -> Disablement:
    """Disable one principal from the console, or refuse (M33.1.2.4).

    `brain.identity.lifecycle.disable` does all three acts: deletes the grants, ends the
    sessions and bounds the principal. It is called and not reimplemented, and the reason is
    that module's own: a console that ended the sessions and forgot the floor would leave
    every token already minted working, and it would look correct in every test that held the
    registry.

    **Nobody may disable themselves.** Not because it is dangerous but because it is the one
    act in this group with no reviewer left afterwards: the person who could undo it is the
    person who just lost every grant they held. `brain.identity.roles.revoke_role` refuses to
    take the standing Super Admin count below its floor for the neighbouring reason, and this
    is the same failure reached from the principal's side rather than the role's.
    """
    if principal.id == entitlement.principal_id:
        msg = (
            f"{principal.id!r} is disabling themselves, which deletes the grants that would "
            "have let them undo it and ends the session they are reading this on"
        )
        raise GlobalSurfaceError(msg)
    if not may_disable(entitlement, where, now):
        msg = (
            f"{entitlement.principal_id!r} may not disable {principal.id!r} over "
            f"{dict(where)!r}. "
            f"{CONFIRMING_A_ROLE_AND_DISABLING_A_PRINCIPAL_ARE_BOTH_THE_GRANT_DECISION}"
        )
        raise GlobalSurfaceError(msg)
    return disable(
        principal,
        registry=registry,
        now=at,
        grants=grants,
        assignments=assignments,
        packs=packs,
        memberships=memberships,
    )


# --------------------------------------------------------- the self-grant path (M33.1.2.5)
def steward_for(
    role_grants: Sequence[RoleGrant],
    *,
    actor_id: str,
    now: datetime | None = None,
) -> str:
    """Who is told when somebody grants themselves something (M33.1.2.5).

    A standing Super Admin who is not the actor, lowest id first so two readings of an
    unchanged role table address the same person. `brain.identity.roles.standing_super_admins`
    decides who those are, so a deputy is not a steward: cover for annual leave is not
    ownership of the platform, and a notice whose only reader is a thirty-day appointment
    stops being read on a date nobody diarised.

    **Refuses rather than returning an empty string.** `brain.console.reads.StewardNotice`
    would refuse a notice addressed to nobody one frame later with a general message; this
    says which install state produced it, which is the one worth knowing: every standing
    Super Admin has granted themselves something, or there is only one and they are the
    actor.
    """
    holders = sorted(
        one.principal_id
        for one in standing_super_admins(role_grants, now)
        if one.principal_id != actor_id
    )
    if not holders:
        msg = (
            f"a self-grant by {actor_id!r} has no steward: no standing Super Admin remains who "
            "is not the actor, so the notice would be addressed to the person it is about"
        )
        raise GlobalSurfaceError(msg)
    return holders[0]


def self_grant_notices(
    entries: Iterable[AuditEntry],
    *,
    role_grants: Sequence[RoleGrant],
    now: datetime | None = None,
) -> tuple[StewardNotice, ...]:
    """One loud notice per self-grant, each addressed to somebody who is not its actor
    (M33.1.2.5).

    **The detection is `brain.console.reads.self_grants` and there is not a second one.** A
    self-grant is a GRANT entry whose subject names its own actor, read off the entry rather
    than declared by whoever wrote the grant path, which is that module's
    `THE_GRANT_THAT_MUST_NOT_BE_MISSED_IS_THE_ONE_NOBODY_DECLARES`. Nothing here inspects an
    action or a subject.

    **The steward is chosen per grant rather than once for the batch**, which is the one
    place this departs from `brain.console.reads.notices_for`. That function takes a single
    steward and refuses the whole batch if they are the actor of any entry, which is right
    when a caller has already decided who the steward is; here the steward is derived from the
    role table, so a batch containing a self-grant by every standing Super Admin in turn
    resolves to a different reader each time instead of failing as a whole.

    `StewardNotice` carries no capability and has no field that could suppress it, which is
    what makes this path loud, and that is enforced by the type rather than by this function.
    """
    return tuple(
        StewardNotice(
            steward_id=steward_for(role_grants, actor_id=one.principal_id, now=now),
            grant=one,
        )
        for one in self_grants(entries)
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of these surfaces is handed. Listed rather than discovered, following
#: `brain.console.govern.GOVERN_ROWS`: a type added here and not to this tuple is one the
#: checks below never see.
GLOBAL_ROWS: Final[tuple[type, ...]] = (EstateRow, CompanyConsumption, Nomination)


def global_gaps(
    *,
    rows: Sequence[type] = GLOBAL_ROWS,
    screen_by_kind: Mapping[EstateKind, str] = ESTATE_SCREEN,
    control: Capability = GOVERNANCE_CONTROL,
    kill_switch: Capability = KILL_SWITCH,
) -> tuple[str, ...]:
    """Everything about this group that would show somebody more than they hold, or stop
    nothing.

    Takes its inputs rather than reading the module's own constants, for the reason
    `brain.console.govern.govern_gaps` gives: a diagnostic that can only run against the
    healthy tree reports nothing today, so switching off any of its refusals changes nothing
    observable and every one of them survives a mutation.

    Four checks. A hidden count on any row; an estate kind whose screen is missing or names
    nothing the registry holds; a governance control that has come apart from the Access
    review screen's requirement; and a kill switch that is not the capability the Halt screen
    and `brain.ops.halt` both name.
    """
    gaps: list[str] = []
    registered = {one.key for one in SCREENS}

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )
    gaps.extend(
        f"the {one.value} kind names {screen_by_kind.get(one)!r}, which is not a registered "
        f"screen, so a row of that kind is governed by nothing. "
        f"{EACH_KIND_IS_ITS_OWN_DISCLOSURE_AND_ITS_OWN_SCREEN}"
        for one in EstateKind
        if screen_by_kind.get(one) not in registered
    )
    if control != screen("access_review").read.requires:
        gaps.append(
            f"the governance control is {control.value} and the Access review screen requires "
            f"{screen('access_review').read.requires.value}, so there are two answers to who "
            f"may decide what somebody reaches. "
            f"{CONFIRMING_A_ROLE_AND_DISABLING_A_PRINCIPAL_ARE_BOTH_THE_GRANT_DECISION}"
        )
    if kill_switch != HALT_CAPABILITY or kill_switch != screen("halt").read.requires:
        gaps.append(
            f"the kill switch is {kill_switch.value}, brain.ops.halt names "
            f"{HALT_CAPABILITY.value} and the Halt screen requires "
            f"{screen('halt').read.requires.value}; a console offering a button behind a "
            "capability nothing else recognises is a button that stops nothing"
        )

    return tuple(gaps)
