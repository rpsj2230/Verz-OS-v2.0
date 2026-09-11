"""What each of the six roles sees, computed the only way this system permits: from grants.

The question "what does an Auditor see" has an obvious answer and it is the wrong one. The
obvious answer is a table keyed by role, because that is how the requirement is written down
and how everybody discusses it. `brain.identity.roles` opens with "no role implies a
capability, including Super Admin", and `brain.identity.packs.assert_no_role_in_resolution`
refuses a resolver that can even see a role, so the table would be this system's central rule
undone in the place it is least visible: the screen appears because of the role and the tool
behind it refuses because of the grant.

**So a role surface is not a surface for a role.** It is the set of screens whose required
capability a person holds, computed for that person by the same `brain.console.screens.
navigation` everybody else goes through. "The Auditor's surface" names the shape a company's
auditor usually ends up with, and nothing here can produce it without being handed grants.
`surface` takes an `EntitlementSet` and nothing else, and `surface_gaps` runs
`assert_no_role_in_resolution` over it so a role parameter cannot be added quietly.

**Rejected: a function answering what somebody else would see.** `what_would_an_auditor_see`
is the natural next request and it is a directory of what other people reach: two of them
subtracted is the disclosure by subtraction `CLAUDE.md` names, and it arrives dressed as a
help feature. `designed_for` reads `Screen.intended_for`, which `brain.console.screens`
already declares to be documentation and never an authorisation, and it returns screens
rather than anybody's reach. Nothing that decides consults it, which is asserted rather than
promised: a caller holding a capability no role was documented for reaches its screen anyway.

**The Auditor is the sharp case and it is an absence, not a rule.** An auditor reads the
metadata plane end to end, including a Super Admin's activity, and never a record. That
absence is the absence of a content-plane grant, which is a fact about their entitlement.
**Rejected: a second notion of "metadata only".** `brain.console.reads.Plane` already orders
existence, configuration and content and already gives each its own capability; a boolean
here called `metadata_only` would be a fourth plane with worse arithmetic, and the day
somebody granted an auditor a content capability the boolean would still say metadata only.

**The Connector Admin is the same absence pointed the other way.** Credential custody is not
access to what the credential unlocks. Holding every connector capability the registry names
reaches the connector screens and reaches no agent and no knowledge screen, because a
connector grant does not cover those capabilities and `Capability.covers` is what decides.
Appointing somebody to the role adds nothing, and the reason it adds nothing is that no code
path here can read a role.

**The Approver's surface is a queue, and the filter is their own reach.** Not the Approver
role: `brain.identity.roles.approver_mismatches` exists because holding the role and holding
an approve capability disagree silently in both directions. An approver may not wave through
what they could not do themselves, so a suspension is offered when the approver holds the
capability its action requires, in a scope matching the row it targets. That is the same two
public calls `brain.gate.leash`'s own capability check makes, on the approver's set instead of
the caller's, and it is deliberately not a third implementation of `E(caller) ∩ ceiling`.

**The queue counts nothing it withheld and shows nothing that has lapsed.** A queue reading
"4 of 19 awaiting you" tells an approver that fifteen actions exist which they may not see,
which is fifteen facts about other departments. `expiring_within` runs over the queue this
approver already has rather than over every suspension, so a deadline cannot become a way to
learn that something else is about to expire. **Rejected: keeping expired suspensions in the
queue greyed out.** An expired approval cannot be granted, `SuspendedAction.is_open` says so,
and a queue that lists one invites the attempt and then explains the refusal.

**A department admin is the same computation with narrower grants.** A scope narrows the rows
a screen shows and never the menu it appears in: `EntitlementSet.scope_for` returns a scope
rather than None, so the screen is permitted either way. `department_surface` drops the
screens whose subject is the installation, by calling `for_department`, and there is no
department registry and no second code path. `surface_gaps` fails if one appears.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in `brain.console.reads`.

**Most of what M33 asks for is a screen and there are no screens.** `unregistered_tools([])`
returns all thirty-five, so a leaf reading "their own memory with a delete control" needs a
tool that does not exist and is not claimed below however well the menu behaves. M33.5.1.3,
"set permission-sync capability per connector", is a connector's credential custody rather
than a console surface and is not claimed here either; `brain.identity.staff_source` argues
the same decision one layer earlier and declines it for the mirror reason.

Task ids: M33.2.1.1, M33.4.1.4, M33.5.1.4, M33.6.1.1, M33.6.1.4
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import Final

from brain.console.reads import Plane, admits, planes_reachable
from brain.console.screens import SCREENS, Group, Screen, for_department, grouped, navigation
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.leash import SuspendedAction
from brain.identity.packs import assert_no_role_in_resolution
from brain.identity.roles import IdentityError, Role

#: Why there is no registry keyed by role in this module.
A_SURFACE_COMPUTED_FROM_A_ROLE_IS_THE_ONE_THING_THIS_SYSTEM_REFUSES: Final = (
    "brain.identity.roles opens with the rule that no role implies a capability, including "
    "Super Admin, and brain.identity.packs.assert_no_role_in_resolution refuses a resolver "
    "that can even see one. A surface computed from a role puts that rule back the wrong way "
    "round in the least visible place: the screen appears because of the appointment and the "
    "tool behind it refuses because of the grant. surface takes an EntitlementSet and there "
    "is no parameter a role could arrive through."
)

#: Why nothing here answers what somebody else would see.
A_SURFACE_FOR_A_ROLE_NOBODY_HOLDS_IS_A_DIRECTORY_OF_WHAT_YOU_CANNOT_REACH: Final = (
    "Two surfaces subtracted is a list of the screens somebody else may open, which is the "
    "disclosure by subtraction the whole design refuses, arriving as a help feature. A "
    "surface is computed for the grants it is handed and for nothing else. designed_for "
    "returns the registry's own documentation about who a screen was drawn for, which is "
    "product data a reader of the source already has, and never a person's reach."
)

#: Why the auditor's absence of content is a missing grant rather than a rule.
AN_AUDITOR_READS_THE_METADATA_PLANES_BECAUSE_NOBODY_GRANTED_THEM_CONTENT: Final = (
    "brain.console.reads.Plane already orders existence, configuration and content and gives "
    "each its own capability. The auditor's absence of content access is the absence of the "
    "content-plane grant, which is a fact about their entitlement that survives somebody "
    "editing this module. A boolean called metadata_only would be a fourth plane with worse "
    "arithmetic, and it would still read metadata only on the day a content grant was written."
)

#: Why the connector administrator reaches no agent and no knowledge screen.
CUSTODY_OF_A_CREDENTIAL_IS_NOT_ACCESS_TO_WHAT_IT_UNLOCKS: Final = (
    "A connector administrator installs sources and binds credential references, which is "
    "the widest operational trust in the install and none of it is a reason to read a "
    "document, an agent's memory or what the system has learned. Nothing grants those by "
    "virtue of the appointment, because Capability.covers decides and read:connector covers "
    "no agent and no knowledge capability. The role adds nothing because no path here reads "
    "a role at all."
)

#: Why the approval queue is filtered by the approver's own grants.
AN_APPROVER_MAY_NOT_WAVE_THROUGH_WHAT_THEY_COULD_NOT_DO_THEMSELVES: Final = (
    "brain.identity.roles.approver_mismatches exists because the Approver role and an "
    "approve capability disagree silently in both directions, so a queue filtered by the "
    "role would offer actions to somebody who cannot perform them and hide actions from "
    "somebody who can. The filter is whether the approver holds the capability the action "
    "requires, in a scope that matches the row it targets, which is the pair of public calls "
    "brain.gate.leash makes about the caller, asked here about the approver."
)

#: Why the queue publishes no count and drops what has lapsed.
A_QUEUE_THAT_COUNTS_WHAT_IT_WITHHELD_IS_A_CENSUS_OF_OTHER_DEPARTMENTS: Final = (
    "Four of nineteen awaiting you tells an approver that fifteen actions exist which they "
    "may not see, and the fifteen are somebody else's work. The queue returns the "
    "suspensions and there is no second value. An expired suspension is absent rather than "
    "shown as expired, because SuspendedAction.is_open already says it cannot be granted and "
    "listing it invites the attempt."
)

#: Why a department admin needs no registry of their own.
A_NARROWER_SCOPE_CHANGES_THE_ROWS_AND_NEVER_THE_MENU: Final = (
    "EntitlementSet.scope_for returns the scope a grant carries rather than None, so a "
    "department-scoped grant permits exactly the screens an unrestricted one does and shows "
    "fewer rows on each. A department surface is therefore the same computation, minus the "
    "screens whose subject is the installation. A second registry for departments would be a "
    "place for the two to disagree, and the disagreement would read as a missing feature."
)

#: The only return annotation `pending_for` may carry. See `surface_gaps`.
ONLY_THE_QUEUE: Final = "tuple[SuspendedAction, ...]"

#: Field names on `Surface` that would publish what a caller was not offered. Names as well
#: as the shape below, because a field called `withheld` carrying the screens themselves is
#: worse than a count and would pass a check that only looked for a number.
COUNTING_FIELDS: Final[tuple[str, ...]] = (
    "hidden",
    "withheld",
    "total",
    "count",
    "remaining",
    "denied",
    "others",
    "more",
)

#: The annotation of a field that is a count whatever it is called, checked alongside the
#: names above. The way this rule actually gets broken is not somebody adding `hidden`; it is
#: somebody adding `offered` as a number next to a shorter list, and the reader subtracting.
#: A surface carries screens and planes, and neither of those is ever a number.
A_COUNT_IS_A_NUMBER: Final = "int"

#: The capability nouns that make a screen part of the agent surface or the knowledge
#: surface. Nouns rather than screen keys, because the question M33.5.1.4 asks is about what
#: a grant confers and a grant names a capability; `Capability.noun` is where that lives.
#:
#: Asserted against the registry rather than against itself: every noun here is required by
#: some screen, and `agent_and_knowledge` is non-empty for a caller who holds them.
AGENT_AND_KNOWLEDGE_NOUNS: Final[frozenset[str]] = frozenset(
    {
        "agent",
        "skill",
        "document",
        "memory",
        "learning",
        "knowledge_coverage",
        "artifact",
    }
)


@dataclass(frozen=True)
class Surface:
    """One caller's console: the screens they reach and the planes they hold.

    Two fields, and the absent third is the point. There is no `hidden`, no `withheld` and
    no `total`, so there is nowhere for a count of what somebody may not see to be carried;
    see `A_QUEUE_THAT_COUNTS_WHAT_IT_WITHHELD_IS_A_CENSUS_OF_OTHER_DEPARTMENTS`, which is the
    same rule `brain.console.screens.navigation` keeps by returning one value.

    `planes` is carried rather than recomputed by whoever wants it, because the auditor's
    whole property is a statement about the planes and a reader holding the screens alone
    would have to go back to the entitlement to ask.
    """

    screens: tuple[Screen, ...]
    planes: tuple[Plane, ...]

    def __post_init__(self) -> None:
        for one in self.screens:
            if not any(admits(held, one.read.plane) for held in self.planes):
                msg = (
                    f"{one.key} shows the {one.read.plane.name.lower()} plane and this "
                    "surface holds no plane that admits it, so the menu offers a screen the "
                    "console grant refuses"
                )
                raise ValueError(msg)

    def sections(self) -> tuple[tuple[Group, tuple[Screen, ...]], ...]:
        """The menu in its four sections, empty ones dropped. `grouped` does the dropping."""
        return grouped(self.screens)

    @property
    def reaches_content(self) -> bool:
        """Whether this caller holds the content plane at all.

        Asked of the planes rather than of the screens, because a caller can hold the
        content plane and happen to hold no capability for a screen that uses it, and that
        is still content access: the next grant of `read:memory` opens it with nothing
        further being decided.
        """
        return Plane.CONTENT in self.planes

    @property
    def content_screens(self) -> tuple[Screen, ...]:
        """The screens in this surface that show the content plane.

        This caller's own screens, never anybody else's, so it discloses nothing they did
        not already have. Empty is the auditor's case and it is asserted both ways: no
        content screen and no content plane.
        """
        return tuple(one for one in self.screens if one.read.plane is Plane.CONTENT)


def surface(entitlement: EntitlementSet, now: datetime | None = None) -> Surface:
    """What this caller reaches. Grants only, and there is no role parameter.

    Delegates the screen decision to `brain.console.screens.navigation` rather than filtering
    `SCREENS` again here, because a second copy of "which screens is this person permitted"
    is a second place for the plane check to be forgotten. See
    `A_SURFACE_COMPUTED_FROM_A_ROLE_IS_THE_ONE_THING_THIS_SYSTEM_REFUSES`, and `surface_gaps`,
    which runs `brain.identity.packs.assert_no_role_in_resolution` over this signature.
    """
    return Surface(
        screens=navigation(entitlement, now),
        planes=planes_reachable(entitlement, now),
    )


def department_surface(entitlement: EntitlementSet, now: datetime | None = None) -> Surface:
    """The same surface for somebody administering one department rather than the install.

    The same computation, minus the screens whose subject is the deployment. The narrowing
    that makes a department admin's console theirs is the scope on their grants, which shows
    fewer rows on the same screens; see
    `A_NARROWER_SCOPE_CHANGES_THE_ROWS_AND_NEVER_THE_MENU`.

    Note what this is not, in the words `for_department` uses: it is not an authorisation. A
    caller holding `read:backup` reaches the backup screen by its address whatever this
    returns. This decides what is worth putting in a menu.
    """
    return Surface(
        screens=for_department(entitlement, now),
        planes=planes_reachable(entitlement, now),
    )


def designed_for(role: Role) -> tuple[Screen, ...]:
    """Which screens the registry says were drawn for this role. Documentation. Never access.

    `Screen.intended_for` is documentation in `brain.console.screens`' own words and is never
    consulted by anything that decides. This is the reader for it, and it exists so that
    "who was this screen for" has an answer that is visibly not an authorisation: it takes a
    role and returns screens, it never sees an `EntitlementSet`, and no function that decides
    anything calls it.

    That separation is asserted rather than promised. A caller holding a capability for a
    screen documented for nobody they resemble still reaches it, because `surface` reads the
    grants; the test for that is the positive half, and without it this function is one
    refactor away from becoming the role table this module exists to refuse.
    """
    return tuple(one for one in SCREENS if role in one.intended_for)


def agent_and_knowledge(view: Surface) -> tuple[Screen, ...]:
    """The screens in this surface that are agent access or knowledge access (M33.5.1.4).

    Selected by the capability noun each screen requires rather than by a list of screen
    keys, because the leaf asks what a role confers and a grant names a capability. A list
    of keys would be a second registry that stops agreeing with the first the day a screen
    is added.
    """
    return tuple(one for one in view.screens if one.read.requires.noun in AGENT_AND_KNOWLEDGE_NOUNS)


def _may_approve(
    suspension: SuspendedAction,
    entitlement: EntitlementSet,
    now: datetime,
) -> bool:
    """Whether this approver may decide this suspension, on both counts.

    Open, and within their own reach. The reach half is `scope_for` followed by
    `Scope.matches` against the target's own row, which is what
    `brain.gate.leash._capability_check` asks about the caller: holding `write:ticket.status`
    in maintenance is not holding it in finance, and an approver in finance must not be
    offered a maintenance ticket because the capability strings match.
    """
    if not suspension.is_open(now):
        return False
    required = Capability(value=suspension.action.tool.required_capability)
    scope = entitlement.scope_for(required, now)
    if scope is None:
        return False
    return scope.matches(dict(suspension.action.row))


def pending_for(
    entitlement: EntitlementSet,
    suspensions: Sequence[SuspendedAction],
    now: datetime,
) -> tuple[SuspendedAction, ...]:
    """The approvals this person may decide (M33.6.1.1). Their reach, and no count of the rest.

    Filtered by what the approver holds and never by the Approver role. See
    `AN_APPROVER_MAY_NOT_WAVE_THROUGH_WHAT_THEY_COULD_NOT_DO_THEMSELVES` for why the role
    would be the wrong filter in both directions, and
    `A_QUEUE_THAT_COUNTS_WHAT_IT_WITHHELD_IS_A_CENSUS_OF_OTHER_DEPARTMENTS` for why one value
    comes back.

    Order follows `suspensions` rather than being sorted here, for the reason `offerable`
    gives: the caller's order is usually meaningful and re-sorting discards it.
    """
    return tuple(one for one in suspensions if _may_approve(one, entitlement, now))


def expiring_within(
    entitlement: EntitlementSet,
    suspensions: Sequence[SuspendedAction],
    within: timedelta,
    now: datetime,
) -> tuple[SuspendedAction, ...]:
    """What in this approver's own queue lapses inside `within` (M33.6.1.4).

    Computed over `pending_for` rather than over every suspension, deliberately. A deadline
    view that read the whole table would answer "is anything about to expire" for actions the
    approver may not see, which is the queue's own disclosure rule broken by a feature that
    looks like a courtesy.

    An already expired suspension is in neither result. `SuspendedAction.is_open` is the
    single statement of what may still be decided, and this asks it rather than comparing
    `expires_at` a second time.
    """
    deadline = now + within
    return tuple(
        one for one in pending_for(entitlement, suspensions, now) if one.expires_at <= deadline
    )


def surface_gaps(entitlement: EntitlementSet | None = None) -> tuple[str, ...]:
    """Everything about this module that would let a surface show more than it should.

    Four checks. The first three hold this module to its own shape and would otherwise be
    review comments that survive as long as the reviewer remembers them; the fourth is about
    an entitlement handed in, which is why it takes an argument rather than inventing one.
    """
    gaps: list[str] = []

    # Reused rather than reimplemented. `assert_no_role_in_resolution` is the repository's
    # statement of this rule and it already refuses every spelling a role could arrive under;
    # a second signature check here would be a second place for the list to fall behind.
    for resolver in (surface, department_surface, pending_for, expiring_within):
        try:
            assert_no_role_in_resolution(resolver)
        except IdentityError as refused:
            gaps.append(str(refused))

    for field in fields(Surface):
        if field.name in COUNTING_FIELDS:
            gaps.append(
                f"Surface carries {field.name}, so a menu can publish how much it withheld "
                "and the reader learns the size of what they may not see"
            )
        # `field.type` is the annotation as written, because this module carries
        # `from __future__ import annotations` and every annotation in it is therefore a
        # string. Compared rather than resolved: resolving would import the names a future
        # annotation refers to, which is the cost that import is there to avoid.
        if str(field.type) == A_COUNT_IS_A_NUMBER:
            gaps.append(
                f"Surface carries {field.name}, which is a number, and the only number a "
                "surface could hold is how many screens are on the other side of it"
            )

    returns = str(pending_for.__annotations__.get("return", ""))
    if returns != ONLY_THE_QUEUE:
        gaps.append(
            f"pending_for returns {returns} rather than {ONLY_THE_QUEUE}, and the only other "
            "thing it could usefully return is a description of what it withheld"
        )

    if entitlement is not None:
        whole = set(surface(entitlement).screens)
        narrowed = set(department_surface(entitlement).screens)
        if not narrowed <= whole:
            offered = sorted(one.key for one in narrowed - whole)
            gaps.append(
                f"a department surface offers {offered}, which the same grants do not reach "
                "at the install's scope, so there is a second registry for departments"
            )

    return tuple(gaps)
