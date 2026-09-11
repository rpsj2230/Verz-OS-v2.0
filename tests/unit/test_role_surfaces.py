"""The six role surfaces held to the rule that a role never decides what anybody sees.

Every test below is written the way the module is: it hands over grants and asks what comes
back. Nothing here appoints anybody, because nothing in the module can read an appointment,
and a test that passed a role in would be testing a function that does not exist.

Five leaves are claimed. A department admin's console is the same computation as a Super
Admin's with narrower grants, and a narrower scope changes the rows and never the menu
(M33.2.1.1). An auditor reaches no content, both because they hold no content-plane grant and
because no screen they were granted shows content, and both halves are asserted (M33.4.1.4). A
connector administrator reaches no agent and no knowledge screen, at any plane, because
`Capability.covers` decides and their grants cover none of it (M33.5.1.4). An approver is
offered the suspensions they could have performed themselves and no count of the rest
(M33.6.1.1), and an expired one is absent rather than shown as expired (M33.6.1.4).

Real `EntitlementSet`s, real `Screen`s from the registry and real `SuspendedAction`s built
from a real `Action` throughout. A queue test that built its own suspension type would be
checking `pending_for` against an agreement this file had made with itself, which is the trap
`CLAUDE.md` names about a producer and a consumer either side of a value.

Task ids: M33.2.1.1, M33.4.1.4, M33.5.1.4, M33.6.1.1, M33.6.1.4
"""

from __future__ import annotations

from dataclasses import fields, make_dataclass
from datetime import UTC, datetime, timedelta

import pytest

from brain.console import role_surfaces as surfaces_module
from brain.console.reads import Plane, plane_capability
from brain.console.role_surfaces import (
    AGENT_AND_KNOWLEDGE_NOUNS,
    COUNTING_FIELDS,
    ONLY_THE_QUEUE,
    Surface,
    agent_and_knowledge,
    department_surface,
    designed_for,
    expiring_within,
    pending_for,
    surface,
    surface_gaps,
)
from brain.console.screens import SCREENS, WITHHELD_AT_DEPARTMENT_SCOPE, Screen, screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Clause, Op, Scope
from brain.gate.leash import Action, ApprovalState, SuspendedAction, render_artefact
from brain.identity.packs import assert_no_role_in_resolution
from brain.identity.roles import IdentityError, Role

#: A fixed moment, so an expiry test cannot pass because the machine's clock happened to sit
#: on the convenient side of a boundary. Everything below is built relative to it.
NOW = datetime(2027, 3, 1, 9, 0, tzinfo=UTC)

#: The department a scoped grant and a matching row both name.
MAINTENANCE = "maintenance"

#: The capability the queue tests suspend an action under, and one nobody in them holds.
STATUS = "write:ticket.status"
INVOICE = "write:invoice.total"


def holding(
    *capabilities: str,
    planes: tuple[Plane, ...] = (Plane.CONTENT,),
    scope: Scope | None = None,
) -> EntitlementSet:
    """A caller holding these capabilities in one scope, plus the plane grants named.

    Both halves decide whether a screen is permitted: the tool's own capability and the
    console plane. Built here rather than taken from a fixture so a test can hold one and not
    the other, and so the scope can be varied while the capabilities stay identical, which is
    what M33.2.1.1 is about.
    """
    where = scope if scope is not None else Scope(clauses=())
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id="u_test", grants=tuple(grants))


def as_documented(
    role: Role, *, planes: tuple[Plane, ...], scope: Scope | None = None
) -> EntitlementSet:
    """Somebody granted exactly what the registry documents this role's screens as needing.

    The registry's `intended_for` is documentation, so this builds the holding a company
    would plausibly write for somebody in that role. It is an input to the tests and never an
    authority: what comes back is decided by the grants this produces.
    """
    return holding(
        *[one.read.requires.value for one in designed_for(role)],
        planes=planes,
        scope=scope,
    )


def every_capability(
    *, planes: tuple[Plane, ...] = (Plane.CONTENT,), scope: Scope | None = None
) -> EntitlementSet:
    """Somebody granted every capability the registry names, at the planes given."""
    return holding(*[one.read.requires.value for one in SCREENS], planes=planes, scope=scope)


def keys(screens: tuple[Screen, ...]) -> tuple[str, ...]:
    """Screen keys, for an assertion a reader can check against the registry by eye."""
    return tuple(one.key for one in screens)


def a_suspension(
    ident: str,
    capability: str,
    *,
    row: dict[str, str] | None = None,
    raised_at: datetime = NOW,
    window: timedelta = timedelta(hours=4),
    state: ApprovalState = ApprovalState.PENDING,
) -> SuspendedAction:
    """One real suspension, built through the real `Action` and its real digest.

    `brain.gate.leash` computes the artefact and the digest, and both are produced here the
    way `suspend` produces them rather than stubbed, so a test cannot be satisfied by a
    `SuspendedAction` that the gate would never have written.
    """
    action = Action(
        agent_id="agent_test",
        tool=ToolDefinition(
            name="ticket.update_status",
            description="a tool a test built so that a suspension has something real behind it",
            entity="ticket",
            required_capability=capability,
            side_effect=SideEffect.WRITE,
        ),
        target="ticket",
        touched_fields=("status",),
        row=row if row is not None else {},
        args={"status": "closed"},
    )
    return SuspendedAction(
        id=ident,
        trace_id="trace_test",
        action=action,
        principal_id="u_asker",
        ent_hash="e" * 32,
        artefact=render_artefact(action),
        action_digest=action.digest(),
        raised_at=raised_at,
        expires_at=raised_at + window,
        state=state,
    )


def in_maintenance() -> Scope:
    """A scope naming one department, which the rows below either match or do not."""
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=MAINTENANCE),))


# --- a surface is computed from grants and never from a role ---------------------------------


def test_a_surface_is_computed_from_grants_and_never_from_a_role() -> None:
    """**The rule this whole module could most easily undo.** `brain.identity.roles` opens
    with "no role implies a capability, including Super Admin", and
    `brain.identity.packs.assert_no_role_in_resolution` is the repository's statement of it.
    Every function here that answers "what does this person reach" is held to it, by the same
    check rather than by a copy of it.

    Asserted over all four rather than over `surface` alone, because the one that would grow a
    role parameter first is the queue: an approval queue keyed by the Approver role is the
    natural thing to write and it is wrong in both directions.

    Delete this and a `role` argument can be added to any of the four, the menu starts
    agreeing with the appointment instead of the grant, and the tool behind each screen
    refuses for a reason the person reading the console cannot see."""
    for resolver in (surface, department_surface, pending_for, expiring_within):
        assert_no_role_in_resolution(resolver)
    assert surface_gaps() == ()


def test_the_gaps_report_names_a_function_that_could_be_told_who_is_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check above passes because the signatures are right, which is also what it would
    do if the check were doing nothing. This points it at a function that does take a role and
    proves it fires.

    Delete this and `surface_gaps` can stop consulting the signatures at all with the suite
    green, because the true case and the vacuous case look identical from outside.

    Delete this and the first check in `surface_gaps` is asserted only by its own success."""

    def told_who_is_asking(
        entitlement: EntitlementSet, role: Role, now: datetime | None = None
    ) -> Surface:
        return surface(entitlement, now)

    monkeypatch.setattr(surfaces_module, "surface", told_who_is_asking)
    gaps = surface_gaps()
    assert len(gaps) == 1
    assert "told_who_is_asking" in gaps[0]
    with pytest.raises(IdentityError):
        assert_no_role_in_resolution(told_who_is_asking)


def test_the_registry_documents_no_screen_for_a_member_and_a_member_reaches_one_anyway() -> None:
    """**The strongest available proof that `intended_for` is not consulted.** No screen in
    the registry names `Role.MEMBER`, so a surface computed from the documentation would be
    empty for every member of staff in the company. A member holding `read:memory` and the
    content plane reaches the memory screen regardless, because `surface` reads grants.

    Both halves are needed. The first alone is a fact about the registry; the second alone
    would pass if `designed_for` were consulted and happened to agree.

    Delete this and `designed_for` can be wired into `surface` as a first filter, which would
    look like a sensible narrowing and would silently empty the console for everybody who is
    not an administrator."""
    assert designed_for(Role.MEMBER) == ()
    reached = surface(holding("read:memory", planes=(Plane.CONTENT,)))
    assert keys(reached.screens) == ("memory",)


def test_a_surface_may_not_offer_a_screen_the_planes_it_carries_do_not_admit() -> None:
    """A `Surface` is built by `surface` from one entitlement, so its two fields agree by
    construction. Built by hand they need not, and a surface listing the memory screen beside
    the existence plane is a menu offering something the console grant refuses.

    Delete this and `Surface.__post_init__` can be emptied, and a caller assembling one from
    two sources gets a menu whose entries fail when clicked, which is the exact failure
    `brain.console.screens` refuses for roles arriving in a different shape."""
    with pytest.raises(ValueError, match="admits it"):
        Surface(screens=(screen("memory"),), planes=(Plane.EXISTENCE,))
    allowed = Surface(screens=(screen("memory"),), planes=(Plane.CONTENT,))
    assert keys(allowed.screens) == ("memory",)


# --- M33.4.1.4: explicit absence of any content access ---------------------------------------


def test_an_auditor_holds_no_content_plane_and_reaches_no_content_screen() -> None:
    """**M33.4.1.4, and the leaf that asks for a test by name.** An auditor reads the metadata
    plane end to end and never a record. Both halves of that absence are asserted: they hold
    no content-plane capability, so `reaches_content` is False, and no screen in their surface
    shows content, so `content_screens` is empty.

    The seven screens are named so the absence is not the absence of everything. A surface
    with nothing in it would satisfy a content check written any way at all.

    Delete this and the one property the Auditor role exists for is asserted nowhere, and an
    auditor granted `read:memory` during an investigation keeps it silently."""
    auditor = as_documented(Role.AUDITOR, planes=(Plane.EXISTENCE, Plane.CONFIGURATION))
    view = surface(auditor)
    assert keys(view.screens) == (
        "people",
        "roles",
        "capabilities",
        "scopes",
        "exports",
        "access_friction",
        "audit",
    )
    assert view.reaches_content is False
    assert view.content_screens == ()
    assert Plane.CONTENT not in view.planes


def test_an_auditor_granted_the_content_plane_still_reaches_no_content_screen() -> None:
    """**The strong form, and the half a plane check alone would miss.** Give the same auditor
    the content plane and nothing about their screens changes, because none of the screens
    they were granted shows content. The absence is a property of what they hold rather than
    of which plane was withheld, so it survives somebody widening the plane grant in a hurry.

    `reaches_content` flips to True and that is correct and is asserted: they do now hold
    content access, and the console would show it the moment a content capability was written.

    Delete this and `content_screens` can be reimplemented as "empty when the content plane is
    absent", which is true of this entitlement and false of the system."""
    wider = as_documented(
        Role.AUDITOR, planes=(Plane.EXISTENCE, Plane.CONFIGURATION, Plane.CONTENT)
    )
    view = surface(wider)
    assert view.reaches_content is True
    assert view.content_screens == ()


def test_a_content_screen_appears_for_whoever_is_granted_one() -> None:
    """The positive sibling. Both assertions above are about emptiness, and a
    `content_screens` that returned nothing at all would satisfy every one of them.

    Two content screens exist in the registry and a caller granted both reaches both, at the
    content plane and not below it.

    Delete this and the auditor's absence is proved by a function that cannot find anything,
    which is a guard tested only by its refusals."""
    reader = holding("read:learning", "read:memory", planes=(Plane.CONTENT,))
    view = surface(reader)
    assert keys(view.content_screens) == ("learning", "memory")
    assert view.reaches_content is True

    narrower = holding("read:learning", "read:memory", planes=(Plane.CONFIGURATION,))
    assert surface(narrower).content_screens == ()


# --- M33.5.1.4: no agent or knowledge access by virtue of the role ----------------------------


def test_a_connector_administrator_reaches_no_agent_and_no_knowledge_screen() -> None:
    """**M33.5.1.4.** Credential custody is the widest operational trust in the install and
    none of it is a reason to read a document, an agent's memory or what the system learned.
    Somebody granted what a connector administrator needs reaches the connector screen and
    nothing in the agent or knowledge surface.

    Asserted at the content plane, which is the widest, so the absence cannot be explained by
    a narrow plane grant. What stops them is `Capability.covers`: `read:connector` covers no
    agent and no knowledge capability, and there is nothing else to appeal to.

    Delete this and the connector administrator's grants can be widened to cover the agent
    surface with nothing failing, which is the failure the role exists to prevent."""
    custodian = as_documented(Role.CONNECTOR_ADMIN, planes=(Plane.CONTENT,))
    view = surface(custodian)
    assert keys(view.screens) == ("connectors",)
    assert agent_and_knowledge(view) == ()


def test_the_agent_and_knowledge_screens_are_reached_by_whoever_holds_their_capabilities() -> None:
    """The positive sibling. `agent_and_knowledge` returning nothing for everybody would
    satisfy the test above, and the whole registry is what says it does not.

    Delete this and the connector administrator's absence is proved by a selector that selects
    nothing, and the nouns constant could be emptied without a failure."""
    everybody = every_capability()
    assert keys(agent_and_knowledge(surface(everybody))) == (
        "knowledge_coverage",
        "agents",
        "skills",
        "library",
        "learning",
        "memory",
        "artifacts",
    )


def test_every_agent_and_knowledge_noun_is_one_some_screen_actually_requires() -> None:
    """The constant asserted against something outside itself, which is the rule `CLAUDE.md`
    states after three authors were caught comparing a constant with itself in one afternoon.

    A noun in this set that no screen requires selects nothing and reads as a screen that was
    checked. A screen missing from the set is agent or knowledge access that the connector
    administrator's test above would not have looked at.

    Delete this and a typo in `AGENT_AND_KNOWLEDGE_NOUNS` makes the selector quieter, which
    makes both tests above pass more easily."""
    required = {one.read.requires.noun for one in SCREENS}
    named_by_hand = {
        "agent",
        "skill",
        "document",
        "memory",
        "learning",
        "knowledge_coverage",
        "artifact",
    }
    assert required >= AGENT_AND_KNOWLEDGE_NOUNS
    assert named_by_hand == AGENT_AND_KNOWLEDGE_NOUNS


def test_the_registry_documents_no_agent_or_knowledge_screen_for_the_connector_administrator() -> (
    None
):
    """The documentation agrees with the grants, which is worth asserting because the two are
    written by different people at different times and nothing else compares them.

    This is a statement about `Screen.intended_for` and decides nothing. If it ever
    disagreed, the registry would be describing a role the entitlements do not support, and
    the person reading the console would be told they were designed for a screen they cannot
    open.

    Delete this and a screen can be marked as intended for the connector administrator while
    M33.5.1.4 says the opposite, with both records green."""
    documented = designed_for(Role.CONNECTOR_ADMIN)
    assert keys(documented) == ("connectors",)
    assert all(one.read.requires.noun not in AGENT_AND_KNOWLEDGE_NOUNS for one in documented)


# --- M33.2.1.1: everything within their scope, same shape as the Super Admin view -------------


def test_a_narrower_scope_changes_the_rows_and_never_the_menu() -> None:
    """**M33.2.1.1, and the half that surprises people.** A department admin's console is not
    a smaller menu; it is the same menu showing fewer rows. `EntitlementSet.scope_for` returns
    the scope a grant carries rather than None, so a department-scoped grant permits exactly
    the screens an unrestricted one does.

    The same capabilities are granted twice, once unrestricted and once inside one department,
    and the two surfaces are identical. The scope is asserted to be different, so the test
    cannot pass because both sides were built the same way.

    Delete this and a scope check can be added to `permitted` that drops screens rather than
    rows, and a department admin's console loses entries with no message explaining it."""
    wide = every_capability()
    narrow = every_capability(scope=in_maintenance())
    assert keys(surface(wide).screens) == keys(surface(narrow).screens)
    assert len(surface(narrow).screens) > 1
    required = Capability(value="read:audit")
    assert wide.scope_for(required) != narrow.scope_for(required)


def test_a_department_surface_is_the_same_computation_minus_what_it_would_disclose() -> None:
    """The other half of M33.2.1.1: same shape, one subtraction, no second registry. Both are
    the same type carrying the same planes.

    **This asserted five dropped screens until 2026-09-10 and now asserts one.** It read
    `not one.company_wide`, a boolean on the screen set on the argument that at a department's
    scope each of the five was "either empty or a leak". Those are two different things and
    only the second is a reason: a screen that renders empty has told the reader that the rows
    they may see are none, which is what every scoped surface here does, while taking it out of
    the menu is the subtraction disclosure, because a missing heading says there is something
    you may not have. The owner overruled the flag in item 38 and the derivation runs the other
    way now: every screen is offered unless a `Disclosure` names what a department-scoped
    reader would learn.

    Asserted against `WITHHELD_AT_DEPARTMENT_SCOPE`, which is derived from those disclosures,
    so withholding a sixth screen means writing the three sentences rather than editing a set
    here. The difference is still asserted to be non-empty, so a `department_surface` that
    returned everything fails rather than satisfying a subset check.

    Delete this and a department registry can be introduced beside the main one, and the two
    drift in the direction where a department admin sees a screen the install's own menu does
    not offer."""
    narrow = every_capability(scope=in_maintenance())
    whole = surface(narrow)
    scoped = department_surface(narrow)
    withheld = set(WITHHELD_AT_DEPARTMENT_SCOPE)

    assert scoped.screens == tuple(one for one in whole.screens if one.key not in withheld)
    assert scoped.planes == whole.planes
    dropped = set(keys(whole.screens)) - set(keys(scoped.screens))
    assert dropped == withheld
    assert dropped, "a subtraction of nothing would satisfy a subset check"


def test_the_gaps_report_a_department_menu_offering_what_the_grants_do_not_reach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fourth check in `surface_gaps`, pointed at a `for_department` that offers a screen
    the caller's grants do not reach. That is what a second registry would look like from
    outside: not a missing screen, an extra one.

    Delete this and the subset check is exercised only by entitlements that satisfy it, which
    is the vacuous case again."""
    narrow = holding("read:audit", planes=(Plane.CONFIGURATION,))
    assert surface_gaps(narrow) == ()

    def a_registry_of_its_own(
        entitlement: EntitlementSet, now: datetime | None = None
    ) -> tuple[Screen, ...]:
        return (screen("recovery"),)

    monkeypatch.setattr(surfaces_module, "for_department", a_registry_of_its_own)
    gaps = surface_gaps(narrow)
    assert len(gaps) == 1
    assert "second registry" in gaps[0]


# --- M33.6.1.1: pending approvals within their own entitlement --------------------------------


def test_an_approver_is_offered_only_what_they_could_have_performed_themselves() -> None:
    """**M33.6.1.1.** An approver may not wave through an action they could not perform. The
    filter is their own grants, on both counts the gate checks: the capability, and the scope
    against the row the action targets.

    Three suspensions and one of them survives. The one they hold nothing for is refused by
    the capability; the one in another department is refused by the scope, which is the case
    that passes if somebody compares capability strings and forgets the row. The one that is
    theirs is returned, so the filter is not simply refusing everything.

    Delete this and the queue can be filtered by the Approver role, or by the capability
    alone, and an approver in maintenance is handed finance's actions to sign off."""
    approver = holding(STATUS, planes=(Plane.CONFIGURATION,), scope=in_maintenance())
    mine = a_suspension("s_mine", STATUS, row={"department": MAINTENANCE})
    not_granted = a_suspension("s_other_capability", INVOICE, row={"department": MAINTENANCE})
    elsewhere = a_suspension("s_other_scope", STATUS, row={"department": "finance"})

    queue = pending_for(approver, (mine, not_granted, elsewhere), NOW)
    assert tuple(one.id for one in queue) == ("s_mine",)


def test_a_decided_suspension_leaves_the_queue_and_the_rest_stay() -> None:
    """A queue is what is waiting on a person, and something already approved or rejected is
    not. `SuspendedAction.is_open` is the single statement of that and `pending_for` asks it
    rather than comparing the state itself.

    Delete this and the state check can go, and an approver is shown their own decisions back
    as though they still needed making."""
    approver = holding(STATUS, planes=(Plane.CONFIGURATION,), scope=in_maintenance())
    waiting = a_suspension("s_waiting", STATUS, row={"department": MAINTENANCE})
    approved = a_suspension(
        "s_approved", STATUS, row={"department": MAINTENANCE}, state=ApprovalState.APPROVED
    )
    rejected = a_suspension(
        "s_rejected", STATUS, row={"department": MAINTENANCE}, state=ApprovalState.REJECTED
    )
    queue = pending_for(approver, (waiting, approved, rejected), NOW)
    assert tuple(one.id for one in queue) == ("s_waiting",)


def test_the_queue_returns_the_suspensions_and_nothing_saying_how_many_it_withheld() -> None:
    """ "Four of nineteen awaiting you" tells an approver that fifteen actions exist which they
    may not see, in departments they have no business knowing about. The queue returns one
    value, and `Surface` carries no field a count could live on.

    The return annotation is compared against the one that is correct rather than searched for
    words that would be wrong, for the reason `brain.console.screens.screen_gaps` gives: the
    ways to spell "and also the hidden count" are open and the acceptable types are one.

    Delete this and a second return value or a `hidden` field can be added, and the console's
    hardest rule is broken by a feature that reads as helpfulness."""
    approver = holding(STATUS, planes=(Plane.CONFIGURATION,), scope=in_maintenance())
    mine = a_suspension("s_mine", STATUS, row={"department": MAINTENANCE})
    elsewhere = a_suspension("s_other_scope", STATUS, row={"department": "finance"})
    queue = pending_for(approver, (mine, elsewhere), NOW)
    assert isinstance(queue, tuple)
    assert all(isinstance(one, SuspendedAction) for one in queue)
    assert pending_for.__annotations__["return"] == ONLY_THE_QUEUE
    assert surface_gaps() == ()


def test_the_gaps_report_a_queue_that_returns_more_than_the_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The third check in `surface_gaps`, exercised by moving the annotation it compares
    against. Without this the check passes because the annotation is right, which is also what
    it would do if it compared the annotation with itself.

    Delete this and `ONLY_THE_QUEUE` can be repointed at whatever `pending_for` happens to
    return, which is the constant-against-itself failure `CLAUDE.md` records three times."""
    monkeypatch.setattr(surfaces_module, "ONLY_THE_QUEUE", "tuple[SuspendedAction, int]")
    gaps = surface_gaps()
    assert len(gaps) == 1
    assert "withheld" in gaps[0]


@pytest.mark.parametrize("name", COUNTING_FIELDS)
def test_the_gaps_report_every_name_a_count_could_arrive_on_a_surface_under(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each name in `COUNTING_FIELDS`, exercised. A blocklist whose members are never tested
    is one where a typo makes the check quieter and nothing goes red, which is exactly how a
    guard stops guarding.

    A surface is stood up carrying the offending field so that the check has something to
    find. `Surface` itself carries two fields and neither is on the list.

    This proves the check fires and it cannot prove the list is right, because the parameters
    are the list: misspell a member and the parameter is misspelled with it, and both sides
    move together. `test_the_names_a_count_could_arrive_under_are_a_reviewed_list` is the
    copy that does not move, and the two are only useful together.

    Delete this and a member of the list stops being exercised at all, and the branch is
    watched by whichever spelling somebody happened to write a test for."""
    carrying = make_dataclass("Carrying", [("screens", "tuple"), (name, "tuple")], frozen=True)
    monkeypatch.setattr(surfaces_module, "Surface", carrying)
    gaps = surface_gaps()
    assert len(gaps) == 1
    assert f"Surface carries {name}" in gaps[0]
    assert {one.name for one in fields(Surface)} == {"screens", "planes"}


def test_the_names_a_count_could_arrive_under_are_a_reviewed_list() -> None:
    """The blocklist asserted against a copy outside the module, which is the only thing it
    can be asserted against: unlike `AGENT_AND_KNOWLEDGE_NOUNS`, no registry holds these
    names and there is nothing to derive them from.

    **Found by mutation, and it is the failure `CLAUDE.md` names.** Renaming `withheld` to
    `withhold` survived the parametrised test above, because that test takes its parameters
    from the constant it is checking, so the mutated spelling arrived on both sides and the
    row read as a guard that was never watching.

    Writing the list twice is the cost. It buys the property that widening or narrowing what
    a surface may not carry is a change to two files and a decision somebody reviewed.

    Delete this and `COUNTING_FIELDS` can be quietly emptied one member at a time, and every
    test above still passes because each one asks the constant what it should contain."""
    reviewed = (
        "hidden",
        "withheld",
        "total",
        "count",
        "remaining",
        "denied",
        "others",
        "more",
    )
    assert reviewed == COUNTING_FIELDS


def test_the_gaps_report_a_number_on_a_surface_whatever_it_is_called() -> None:
    """The way this rule actually gets broken is not somebody adding `hidden`; it is somebody
    adding a number called something reasonable beside a shorter list, and the reader
    subtracting. The shape is checked as well as the name.

    Delete this and `offered: int` lands on `Surface` past a blocklist that was only ever
    looking for the words somebody would not have used."""
    counting = make_dataclass("Counting", [("screens", "tuple"), ("offered", "int")], frozen=True)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(surfaces_module, "Surface", counting)
        gaps = surface_gaps()
    assert len(gaps) == 1
    assert "which is a number" in gaps[0]


def test_holding_the_approver_role_puts_nothing_in_the_queue() -> None:
    """`brain.identity.roles.approver_mismatches` exists because the Approver role and an
    approve capability disagree silently in both directions. A queue keyed by the role would
    offer actions to somebody who cannot perform them, and the refusal would arrive at the
    moment they pressed approve.

    Asserted as an absence of the parameter rather than as a behaviour, because a behaviour
    test would pass against a function that consulted a role and happened to get this case
    right. There is nowhere for a role to arrive.

    Delete this and `pending_for` can grow a role argument, and the queue becomes the second
    permission model this system spends most of its design refusing."""
    assert "role" not in pending_for.__annotations__
    assert_no_role_in_resolution(pending_for)
    nothing_granted = holding(planes=(Plane.CONFIGURATION,))
    mine = a_suspension("s_mine", STATUS, row={"department": MAINTENANCE})
    assert pending_for(nothing_granted, (mine,), NOW) == ()


# --- M33.6.1.4: timeout visibility and expiry behaviour ---------------------------------------


def test_an_expired_suspension_is_absent_from_the_queue_rather_than_shown_as_expired() -> None:
    """**M33.6.1.4.** An expired approval cannot be granted, so listing it invites the attempt
    and then explains the refusal. It is absent, and the queue says nothing about it having
    been there.

    Asserted at both sides of the boundary from one suspension, so the test cannot pass
    because the item was never in the queue at all: the same object is offered before its
    expiry and gone after it.

    Delete this and a lapsed approval sits in the queue looking actionable, and the window
    that `brain.gate.leash` enforces is invisible to the only person who could act on it."""
    approver = holding(STATUS, planes=(Plane.CONFIGURATION,), scope=in_maintenance())
    lapsing = a_suspension(
        "s_lapsing", STATUS, row={"department": MAINTENANCE}, window=timedelta(hours=2)
    )
    assert tuple(one.id for one in pending_for(approver, (lapsing,), NOW)) == ("s_lapsing",)
    after = NOW + timedelta(hours=3)
    assert pending_for(approver, (lapsing,), after) == ()


def test_the_deadline_view_runs_over_this_approvers_own_queue_and_not_the_whole_table() -> None:
    """Timeout visibility is what an approver needs and it is also the shape that leaks. A
    deadline view reading every suspension would answer "is anything about to expire" for
    actions in departments this person may not see, which is the queue's own rule broken by
    something that looks like a courtesy.

    Three suspensions expire inside the hour and only the one this approver could act on comes
    back. The fourth is theirs and expires later, so the window is doing work rather than
    returning the queue unchanged.

    Delete this and `expiring_within` can be reimplemented over the raw sequence, and an
    approver learns that finance has an action lapsing at four o'clock."""
    approver = holding(STATUS, planes=(Plane.CONFIGURATION,), scope=in_maintenance())
    soon = a_suspension(
        "s_soon", STATUS, row={"department": MAINTENANCE}, window=timedelta(minutes=30)
    )
    elsewhere = a_suspension(
        "s_elsewhere", STATUS, row={"department": "finance"}, window=timedelta(minutes=30)
    )
    not_granted = a_suspension(
        "s_not_granted", INVOICE, row={"department": MAINTENANCE}, window=timedelta(minutes=30)
    )
    later = a_suspension(
        "s_later", STATUS, row={"department": MAINTENANCE}, window=timedelta(hours=3)
    )

    every_one = (soon, elsewhere, not_granted, later)
    within_the_hour = expiring_within(approver, every_one, timedelta(hours=1), NOW)
    assert tuple(one.id for one in within_the_hour) == ("s_soon",)
    assert tuple(one.id for one in pending_for(approver, every_one, NOW)) == ("s_soon", "s_later")


def test_the_deadline_view_offers_nothing_once_the_window_has_passed() -> None:
    """The boundary itself. A suspension expiring exactly at the deadline is inside the
    window, and one expiring after it is not; both are in the approver's queue either way, so
    the difference is the window and nothing else.

    Delete this and the comparison can be inverted or made strict with the test above still
    passing, because thirty minutes is inside an hour under either reading."""
    approver = holding(STATUS, planes=(Plane.CONFIGURATION,), scope=in_maintenance())
    at_the_edge = a_suspension(
        "s_edge", STATUS, row={"department": MAINTENANCE}, window=timedelta(hours=1)
    )
    past_it = a_suspension(
        "s_past", STATUS, row={"department": MAINTENANCE}, window=timedelta(hours=1, minutes=1)
    )
    both = (at_the_edge, past_it)
    assert tuple(one.id for one in pending_for(approver, both, NOW)) == ("s_edge", "s_past")
    inside = expiring_within(approver, both, timedelta(hours=1), NOW)
    assert tuple(one.id for one in inside) == ("s_edge",)
