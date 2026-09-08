"""The company-wide surfaces held to what each shows, and to what it must never show.

Seven leaves are claimed and each is a disclosure decision rather than a page. The estate is
four listings behind four screens' own grants, and the department and person filters narrow
within what the reader may already see and never before it (M33.1.1.1). Company consumption is
everybody's spend, so it follows the budget screen's grant and is withheld rather than narrowed
(M33.1.1.3). The kill switch is `brain.ops.halt.stop_everything`, behind the capability the
Halt screen requires, unilateral and with both effects, and the axes nothing consults are named
rather than left for an administrator to discover during an incident (M33.1.1.4). A department
publication request is approved through `brain.knowledge.visibility.approve_promotion`, from a
queue that carries no count of the requests withheld (M33.1.2.2). A role nomination cannot be
written by its own subject and cannot be confirmed by whoever made it (M33.1.2.3). Disabling a
principal is `brain.identity.lifecycle.disable`, refused for oneself (M33.1.2.4). And a
self-grant is detected by `brain.console.reads.self_grants` and notified to a steward who is
not the actor (M33.1.2.5).

Real `EntitlementSet`s, a real `SessionRegistry`, real `PromotionProposal`s, real `Actual`s and
real ledger entries throughout. The self-grant test in particular builds its entries through
`AuditChain.append` rather than constructing an `AuditEntry`, because the claim is about what
the detection reads off a written entry.

Two leaves under this heading are not claimed. All activity under the same filters needs a
department on an audit entry, which the ledger deliberately does not carry; publishing a global
agent needs an audience change, which `brain.agents.lifecycle` does not have.

Task ids: M33.1.1.1, M33.1.1.3, M33.1.1.4, M33.1.2.1, M33.1.2.2
Task ids: M33.1.2.3, M33.1.2.4, M33.1.2.5
"""

from __future__ import annotations

from dataclasses import make_dataclass
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.lifecycle import AGENT_PUBLICATION_CAPABILITY, archive, publish
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.audit.ledger import AuditAction, AuditChain
from brain.console.global_surfaces import (
    ESTATE_SCREEN,
    GOVERNANCE_CONTROL,
    KILL_SWITCH,
    CompanyConsumption,
    EstateKind,
    EstateRow,
    GlobalSurfaceError,
    Nomination,
    activity_filter,
    approve_publication,
    company_consumption,
    confirm,
    disable_principal,
    estate,
    global_gaps,
    inert_axes,
    may_approve_publication,
    may_confirm,
    may_disable,
    may_publish,
    may_stop,
    press_stop,
    publication_queue,
    publishable,
    self_grant_notices,
    steward_for,
    visible_estate,
)
from brain.console.govern import Placed
from brain.console.reads import Plane, plane_capability
from brain.console.screens import SCREENS, Axis, Lens, screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import TrafficClass
from brain.identity.roles import Role, RoleGrant
from brain.identity.sessions import Session, SessionRegistry
from brain.knowledge.visibility import (
    PROMOTION_CAPABILITY,
    PromotionProposal,
    Visibility,
    propose_promotion,
)
from brain.ops.halt import ENFORCED_AXES, HALT_CAPABILITY, Effect, HaltScope
from brain.ops.spend import Actual

#: A fixed moment. Everything below is relative to it, so a window test cannot pass because
#: the machine's clock happened to sit on the convenient side of a boundary.
NOW = datetime(2027, 6, 15, 11, 0, tzinfo=UTC)

MAINTENANCE = "maintenance"
FINANCE = "finance"

#: The four capabilities the estate screens require, read off the registry rather than
#: written out, so a repointed screen changes the fixture with it.
ESTATE_CAPABILITIES = tuple(
    screen(key).read.requires.value for key in sorted(set(ESTATE_SCREEN.values()))
)


def holding(
    *capabilities: str,
    principal_id: str = "u_admin",
    department: str = MAINTENANCE,
    planes: tuple[Plane, ...] = (Plane.CONFIGURATION,),
) -> EntitlementSet:
    """A reader holding these capabilities in one department, plus the plane grants named."""
    where = Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id=principal_id, grants=tuple(grants))


def a_row(
    kind: EstateKind,
    item_id: str,
    *,
    department: str = MAINTENANCE,
    owner_id: str = "u_owner",
) -> EstateRow:
    """One estate row and the place its subject sits."""
    return EstateRow(
        kind=kind, item_id=item_id, where={"department": department, "owner_id": owner_id}
    )


def super_admins(*ids: str) -> tuple[RoleGrant, ...]:
    """Standing Super Admin grants, through `RoleGrant`'s own validators."""
    return tuple(
        RoleGrant(
            principal_id=one,
            role=Role.SUPER_ADMIN,
            granted_by="u_first",
            reason="written for this test",
            granted_at=NOW - timedelta(days=300),
        )
        for one in ids
    )


def an_actual(
    *,
    principal_id: str = "u_1",
    department: str = MAINTENANCE,
    cost_minor: int = 100,
    at: datetime = NOW,
) -> Actual:
    """One real accounting row through its own validators."""
    return Actual(
        principal_id=principal_id,
        principal_kind=PrincipalKind.HUMAN,
        traffic=TrafficClass.HUMAN_INTERACTIVE,
        department=department,
        agent_id="a_1",
        model="a-model",
        lane=Lane.ANSWER,
        cost_minor=cost_minor,
        at=at,
    )


# ------------------------------------------------------------------- the estate
def test_the_estate_shows_each_kind_behind_its_own_screens_grant() -> None:
    """**M33.1.1.1.** Everything on one page is not everything under one grant. A reader
    holding the agents screen's capability and not the library's sees the agents and no
    knowledge, and a kind they hold nothing for produces no rows and no heading, so a withheld
    kind and an empty one are one absence.

    The positive half is the reader holding all four, which is what proves the listing works
    rather than that it refuses everything.

    Delete this and the estate asks one capability, which will be whichever is widest."""
    rows = [
        a_row(EstateKind.AGENT, "a_1"),
        a_row(EstateKind.SKILL, "s_1"),
        a_row(EstateKind.KNOWLEDGE, "k_1"),
        a_row(EstateKind.CONNECTOR, "c_1"),
    ]
    everything = holding(*ESTATE_CAPABILITIES, planes=(Plane.CONFIGURATION, Plane.EXISTENCE))
    agents_only = holding(
        screen("agents").read.requires.value, planes=(Plane.CONFIGURATION, Plane.EXISTENCE)
    )

    assert [one.item_id for one in visible_estate(rows, everything, NOW)] == [
        "a_1",
        "s_1",
        "k_1",
        "c_1",
    ]
    assert [one.item_id for one in visible_estate(rows, agents_only, NOW)] == ["a_1"]
    assert set(ESTATE_SCREEN) == set(EstateKind)


def test_the_estate_narrows_by_the_readers_scope_and_not_only_by_the_capability() -> None:
    """**M33.1.1.1.** Holding the capability is not holding it over this row. A reader whose
    grant is scoped to one department sees that department's rows and not another's, which is
    the ordinary case rather than an edge, and a check that asked only whether the capability
    existed would pass every test about which kinds appear.

    Delete this and `_in_reach` can drop the `Scope.matches` call."""
    rows = [
        a_row(EstateKind.AGENT, "a_maintenance", department=MAINTENANCE),
        a_row(EstateKind.AGENT, "a_finance", department=FINANCE),
    ]
    reader = holding(
        screen("agents").read.requires.value,
        department=MAINTENANCE,
        planes=(Plane.CONFIGURATION, Plane.EXISTENCE),
    )

    assert [one.item_id for one in visible_estate(rows, reader, NOW)] == ["a_maintenance"]


def test_the_console_plane_decides_as_well_as_the_tools_own_capability() -> None:
    """**M33.1.1.1, and the half a scope check alone cannot make.** `_in_reach` asks whether
    the reader holds the capability in a scope admitting the row, which is what an agent
    making the same call would need. `permitted` asks that and the plane the screen shows,
    which is what the console adds: existence, configuration and content are three different
    disclosures and `brain.console.reads` gives each its own grant.

    A reader holding `read:agent` and only the existence plane therefore sees no agent rows,
    because the Agents screen shows configuration, and the same reader sees the knowledge row
    because the Library screen shows existence. Without both halves the estate would be a way
    of reading a configuration screen with an existence grant.

    **This test exists because a mutation survived without it.** Every reader in the tests
    above is built holding both planes, so replacing the `permitted` call with True changed
    nothing any of them could observe: the fixture had made the guard unreachable.

    Delete this and the plane stops being consulted, and nothing notices."""
    rows = [a_row(EstateKind.AGENT, "a_1"), a_row(EstateKind.KNOWLEDGE, "k_1")]
    existence_only = holding(
        screen("agents").read.requires.value,
        screen("library").read.requires.value,
        planes=(Plane.EXISTENCE,),
    )
    both_planes = holding(
        screen("agents").read.requires.value,
        screen("library").read.requires.value,
        planes=(Plane.EXISTENCE, Plane.CONFIGURATION),
    )

    assert screen("agents").read.plane is Plane.CONFIGURATION
    assert screen("library").read.plane is Plane.EXISTENCE
    assert [one.item_id for one in visible_estate(rows, existence_only, NOW)] == ["k_1"]
    assert [one.item_id for one in visible_estate(rows, both_planes, NOW)] == ["a_1", "k_1"]


def test_a_filter_runs_after_the_visibility_check_and_never_before() -> None:
    """**M33.1.1.1, and the reason the lens is an argument rather than a second function.**
    Filtering by a department the reader may not see must answer exactly what filtering by a
    department that owns nothing answers, and that is true only if the visibility check has
    already happened.

    The positive half is a reader whose grant reaches both departments: they see two rows, and
    the same filter narrows them to one. Without that half, a filter that ignored its argument
    would pass every assertion above it, because a reader scoped to one department sees one
    row whether the filter runs or not.

    Delete this and `narrow_by(rows, lens=...)` appears, gets called first somewhere, and the
    estate becomes a way of asking which departments own anything."""
    rows = [
        a_row(EstateKind.AGENT, "a_maintenance", department=MAINTENANCE),
        a_row(EstateKind.AGENT, "a_finance", department=FINANCE),
    ]
    narrow = holding(
        screen("agents").read.requires.value,
        department=MAINTENANCE,
        planes=(Plane.CONFIGURATION, Plane.EXISTENCE),
    )
    both = EntitlementSet(
        principal_id="u_admin",
        grants=(
            Grant(capability=screen("agents").read.requires, scope=Scope.unrestricted()),
            Grant(capability=plane_capability(Plane.CONFIGURATION), scope=Scope.unrestricted()),
            Grant(capability=plane_capability(Plane.EXISTENCE), scope=Scope.unrestricted()),
        ),
    )

    unseen_department = estate(rows, narrow, lens=Lens(department=FINANCE), now=NOW)
    empty_department = estate(rows, narrow, lens=Lens(department="nobody_works_here"), now=NOW)

    assert unseen_department == empty_department == ()
    assert [one.item_id for one in estate(rows, both, now=NOW)] == ["a_maintenance", "a_finance"]
    assert [one.item_id for one in estate(rows, both, lens=Lens(department=FINANCE), now=NOW)] == [
        "a_finance"
    ]


def test_the_person_and_kind_filters_narrow_within_what_the_reader_may_see() -> None:
    """**M33.1.1.1.** The other two narrowings, proved to work rather than merely to be
    accepted. A filter that silently ignored its argument would pass every test written about
    what it must not disclose.

    Delete this and `lens.person` becomes decoration."""
    rows = [
        a_row(EstateKind.AGENT, "a_mine", owner_id="u_mine"),
        a_row(EstateKind.AGENT, "a_theirs", owner_id="u_theirs"),
        a_row(EstateKind.SKILL, "s_mine", owner_id="u_mine"),
    ]
    reader = holding(*ESTATE_CAPABILITIES, planes=(Plane.CONFIGURATION, Plane.EXISTENCE))

    by_person = estate(rows, reader, lens=Lens(person="u_mine"), now=NOW)
    by_kind = estate(rows, reader, kinds=[EstateKind.SKILL], now=NOW)

    assert [one.item_id for one in by_person] == ["a_mine", "s_mine"]
    assert [one.item_id for one in by_kind] == ["s_mine"]


def test_an_axis_the_estate_cannot_honour_is_refused_rather_than_dropped() -> None:
    """**M33.1.1.1.** An estate row carries a department and an owner and nothing that answers
    a period or a model. Honouring such a lens by returning everything is the failure
    `Screen.accepts` names: the reader believes they narrowed and did not.

    Asserted against `Axis` rather than a string, so a renamed axis fails here rather than
    stopping being checked.

    Delete this and a period filter returns the whole estate and looks like it worked."""
    rows = [a_row(EstateKind.AGENT, "a_1")]
    reader = holding(*ESTATE_CAPABILITIES, planes=(Plane.CONFIGURATION, Plane.EXISTENCE))

    with pytest.raises(GlobalSurfaceError, match="cannot be narrowed"):
        estate(rows, reader, lens=Lens(period="7d"), now=NOW)
    assert Axis.PERIOD in Lens(period="7d").axes_used()
    assert estate(rows, reader, lens=Lens(department=MAINTENANCE), now=NOW) != ()


def test_activity_cannot_be_narrowed_by_a_department_the_ledger_does_not_carry() -> None:
    """**Not a claim, and the reason M33.1.1.2 is not claimed.** An audit entry carries an
    action, a subject kind, a subject and an actor. `brain.audit.view._scope_row` lists those
    four and that module records rejecting per-entry attributes supplied from outside, so a
    department lens over activity cannot be honoured at all.

    The person half is honourable and is asserted working, so this is a statement about which
    of the two filters exists rather than about the surface being unbuilt.

    Delete this and a department filter over activity returns everything, which reads as the
    leaf being done."""
    with pytest.raises(GlobalSurfaceError, match="cannot be narrowed by department"):
        activity_filter(Lens(department=MAINTENANCE))

    assert activity_filter(Lens(person="u_1")) == frozenset({"u_1"})
    assert activity_filter(Lens()) == frozenset()


# ------------------------------------------------------- company budget and consumption
def test_company_consumption_is_withheld_rather_than_narrowed() -> None:
    """**M33.1.1.3.** A company total assembled from one reader's own rows is a confident
    figure that is wrong, which is worse than no figure. `basis_for` decides, which is the
    budget screen's own grant, so a reader sees the total exactly when they could open that
    screen and read it there.

    Both halves are needed: the refusal alone would pass for a function that always returns
    None.

    Delete this and the company screen shows a reader their own spend under a heading reading
    company consumption."""
    rows = [
        an_actual(principal_id="u_admin", cost_minor=100),
        an_actual(principal_id="u_other", department=FINANCE, cost_minor=250),
    ]
    reader = holding(screen("budget").read.requires.value)
    outsider = holding("read:client.name")

    seen = company_consumption(rows, reader, since=NOW - timedelta(days=1), until=NOW)
    assert seen == CompanyConsumption(
        spend_minor=350, by_department=((FINANCE, 250), (MAINTENANCE, 100))
    )
    assert company_consumption(rows, outsider, since=NOW - timedelta(days=1), until=NOW) is None


def test_the_company_total_reconciles_with_its_own_breakdown_and_carries_no_share() -> None:
    """**M33.1.1.3.** The breakdown is `brain.ops.spend.spend_by`, which buckets every row
    including those with no agent, so any two dimensions total to the same figure. That
    reconciliation is what somebody balancing an invoice needs, and a report that quietly
    dropped rows is one they cannot balance.

    No share, no percentage and no rank: two shares recover a total the reader was not shown
    on its own.

    Delete this and a `share` field arrives on the breakdown."""
    rows = [
        an_actual(department=MAINTENANCE, cost_minor=100),
        an_actual(department=MAINTENANCE, cost_minor=50),
        an_actual(department=FINANCE, cost_minor=250),
    ]
    reader = holding(screen("budget").read.requires.value)

    seen = company_consumption(rows, reader, since=NOW - timedelta(days=1), until=NOW)

    assert seen is not None
    assert seen.spend_minor == sum(amount for _, amount in seen.by_department)
    assert set(CompanyConsumption.__dataclass_fields__) == {"spend_minor", "by_department"}


def test_a_row_outside_the_window_is_not_counted() -> None:
    """**M33.1.1.3.** The window is applied before anything is totalled, so a figure quoted
    for a fortnight is a fortnight's. A filter that accepted the bounds and ignored them would
    pass every test above.

    Delete this and `since` and `until` become decoration on a total that is always
    everything."""
    rows = [
        an_actual(cost_minor=100, at=NOW),
        an_actual(cost_minor=999, at=NOW - timedelta(days=40)),
    ]
    reader = holding(screen("budget").read.requires.value)

    seen = company_consumption(rows, reader, since=NOW - timedelta(days=7), until=NOW)

    assert seen is not None
    assert seen.spend_minor == 100


# ------------------------------------------------------------------ the kill switch
def test_the_kill_switch_is_the_capability_halt_and_the_halt_screen_both_name() -> None:
    """**M33.1.1.4.** Pinned against `brain.ops.halt.HALT_CAPABILITY` and against the Halt
    screen's own requirement, which are two things outside this module rather than the
    constant compared with itself.

    Delete this and a console offers a button behind a capability nothing else recognises,
    which is a button that stops nothing."""
    assert KILL_SWITCH == HALT_CAPABILITY
    assert screen("halt").read.requires == KILL_SWITCH
    assert global_gaps(kill_switch=Capability(value="admin:stop")) != ()


def test_pressing_stop_carries_both_effects_and_needs_no_approval() -> None:
    """**M33.1.1.4.** `stop_everything` builds it, so refusing new work and signalling what is
    already running both happen: a halt with only the first is the screen reading stopped
    while in-flight jobs keep writing, which is the first of the five lies that module names.

    `declared_by` is the entitlement's own principal, so a caller cannot name one person and
    pass another's reach, and there is no approval parameter to omit.

    Delete this and `Halt(effects=frozenset({REFUSE_NEW}))` becomes a plausible thing to
    write here."""
    admin = holding(KILL_SWITCH.value)

    halt = press_stop(admin, at=NOW, reason="the connector is leaking rows")

    assert halt.scope is HaltScope.EVERYTHING
    assert halt.effects == frozenset({Effect.REFUSE_NEW, Effect.SIGNAL_RUNNING})
    assert halt.declared_by == "u_admin"
    assert halt.target == ""
    assert may_stop(admin, NOW)


def test_somebody_without_the_capability_cannot_stop_the_install() -> None:
    """**M33.1.1.4.** The refusal is loud rather than silent, because a halt discloses nothing
    about what anybody may read and a stop button that quietly does nothing is the worst
    control in the product.

    Delete this and `press_stop` halts for whoever calls it."""
    with pytest.raises(GlobalSurfaceError, match="may not stop"):
        press_stop(holding("read:run"), at=NOW, reason="a plausible sounding reason")

    assert not may_stop(holding("read:run"), NOW)


def test_the_axes_a_halt_cannot_reach_are_named_from_the_module_that_knows() -> None:
    """**M33.1.1.4.** `brain.ops.admission.decide` is handed a connector and nothing else, so
    a halt on a department, an agent or a person is stored, reported as in force and refuses
    nothing. The administrator stopping a compromised account is the last person able to go
    and read which call sites exist.

    Derived from `ENFORCED_AXES` rather than listed, so the day admission learns an axis this
    stops naming it with no edit here. Asserted as the complement rather than as three names,
    which is what makes that true.

    Delete this and the screen offering a person halt says nothing about it being inert."""
    assert set(inert_axes()) == set(HaltScope) - ENFORCED_AXES
    assert HaltScope.EVERYTHING not in inert_axes()
    assert HaltScope.PERSON in inert_axes()


# ----------------------------------------------------- department publication requests
def a_request(
    *,
    item_id: str = "k_1",
    proposer_id: str = "u_dept_admin",
    department: str = MAINTENANCE,
) -> Placed[PromotionProposal]:
    """One real publication request, paired with the row its item sits in."""
    proposal = propose_promotion(
        item_id=item_id,
        from_level=Visibility.DEPARTMENT,
        to_level=Visibility.COMPANY,
        proposer_id=proposer_id,
        owner_id="u_owner",
        review_by=NOW + timedelta(days=180),
        reason="the price list is needed company wide",
        now=NOW,
    )
    return Placed(record=proposal, where={"department": department})


def test_the_publication_queue_shows_only_what_this_reader_could_decide() -> None:
    """**M33.1.2.2.** Filtered before it is rendered rather than rendered whole with the
    out-of-scope rows disabled, which is the version that gets built because it looks more
    informative. A disabled row names an item, a department and a person who asked, which is
    three facts about work the reader was not admitted to.

    One value comes back and there is no second one carrying what was dropped.

    Delete this and the queue shows every department's requests to whoever can open it."""
    requests = [
        a_request(item_id="k_maintenance", department=MAINTENANCE),
        a_request(item_id="k_finance", department=FINANCE),
    ]
    reader = holding(PROMOTION_CAPABILITY.value, department=MAINTENANCE)

    seen = publication_queue(requests, reader, NOW)

    assert [one.record.item_id for one in seen] == ["k_maintenance"]
    assert isinstance(seen, tuple)


def test_a_reader_may_not_approve_the_request_they_made() -> None:
    """**M33.1.2.2.** `approve_promotion` refuses a proposer approving their own proposal, and
    a queue offering a row it will refuse invites the attempt and then explains it, which is
    the shape `brain.console.role_surfaces` rejected for expired suspensions. So it is dropped
    from the listing and refused by the control.

    Delete this and somebody's own request appears in their queue with a button that always
    fails."""
    mine = a_request(proposer_id="u_admin")
    reader = holding(PROMOTION_CAPABILITY.value)

    assert not may_approve_publication(mine, reader, NOW)
    assert publication_queue([mine], reader, NOW) == ()
    with pytest.raises(GlobalSurfaceError, match="may not approve"):
        approve_publication(mine, reader, now=NOW)


def test_an_approval_is_the_visibility_modules_own_and_carries_the_proposals_digest() -> None:
    """**M33.1.2.2, and the positive case.** The approval comes back from
    `brain.knowledge.visibility.approve_promotion`, unchanged: it carries the proposal's
    digest rather than a second copy of its fields, so an approval and the thing it approved
    cannot come apart.

    Asserted on the digest rather than on the approver id alone, because an `Approval` built
    here rather than there would carry the right approver and the wrong statement of what was
    approved.

    Delete this and a second approval type arrives in the console layer."""
    request = a_request()
    reader = holding(PROMOTION_CAPABILITY.value)

    approval = approve_publication(request, reader, now=NOW)

    assert approval.proposal_digest == request.record.digest()
    assert approval.approver_id == "u_admin"
    assert approval.to_level is Visibility.COMPANY


# ------------------------------------------------------------------ role nominations
def test_nobody_can_write_a_nomination_of_themselves() -> None:
    """**M33.1.2.3.** Refused in the constructor rather than in `confirm`, so a hand-built
    object cannot go around it, which is where `brain.console.govern.Certification` and
    `brain.console.reads.StewardNotice` both put their equivalent refusals.

    The positive sibling is the ordinary nomination, which proves the constructor accepts one.

    Delete this and self-nomination becomes a value that exists and is caught, or not, further
    down."""
    with pytest.raises(GlobalSurfaceError, match="nominated themselves"):
        Nomination(
            principal_id="u_1",
            role=Role.SUPER_ADMIN,
            nominated_by="u_1",
            reason="I would be good at it",
            at=NOW,
        )

    ordinary = Nomination(
        principal_id="u_1",
        role=Role.SUPER_ADMIN,
        nominated_by="u_admin",
        reason="second administrator, as the floor requires",
        at=NOW,
    )
    assert ordinary.principal_id == "u_1"
    assert ordinary.scope is None


def test_the_nominator_cannot_confirm_their_own_nomination() -> None:
    """**M33.1.2.3.** A gate one person passes alone is not a gate: there is a nomination,
    there is a confirmation, and they are the same person twice, which is exactly what
    `approve_promotion` refuses one module over. The nominee is refused too, for the same
    reason from the other side.

    Delete this and a Super Admin appoints another Super Admin unilaterally with a record that
    reads as though two people were involved."""
    nomination = Nomination(
        principal_id="u_1",
        role=Role.SUPER_ADMIN,
        nominated_by="u_admin",
        reason="second administrator, as the floor requires",
        at=NOW,
    )
    where = {"department": MAINTENANCE}

    assert not may_confirm(nomination, holding(GOVERNANCE_CONTROL.value), where, NOW)
    assert not may_confirm(
        nomination, holding(GOVERNANCE_CONTROL.value, principal_id="u_1"), where, NOW
    )
    with pytest.raises(GlobalSurfaceError, match="may not confirm"):
        confirm(nomination, holding(GOVERNANCE_CONTROL.value), where=where, at=NOW)


def test_a_confirmed_nomination_becomes_a_role_grant_naming_the_confirmer() -> None:
    """**M33.1.2.3, and the positive case.** The grant is built by
    `brain.identity.roles.RoleGrant`, so every rule about what a role grant may be is enforced
    where it is stated: a scope refused for a Super Admin, required for a Department Admin.
    Both directions are exercised here, because a `confirm` that dropped the scope would pass
    the first alone.

    `granted_by` is the confirmer, so the row explaining where a role came from names the
    person who decided rather than the person who asked.

    Delete this and the console assembles a role grant with its own idea of the rules."""
    where = {"department": MAINTENANCE}
    confirmer = holding(GOVERNANCE_CONTROL.value, principal_id="u_confirmer")

    grant = confirm(
        Nomination(
            principal_id="u_1",
            role=Role.SUPER_ADMIN,
            nominated_by="u_admin",
            reason="second administrator, as the floor requires",
            at=NOW,
        ),
        confirmer,
        where=where,
        at=NOW,
    )

    assert grant.role is Role.SUPER_ADMIN
    assert grant.granted_by == "u_confirmer"
    assert grant.reason == "second administrator, as the floor requires"
    assert grant.is_active(NOW)

    with pytest.raises(ValueError, match="needs a scope"):
        confirm(
            Nomination(
                principal_id="u_2",
                role=Role.DEPARTMENT_ADMIN,
                nominated_by="u_admin",
                reason="runs maintenance day to day",
                at=NOW,
            ),
            confirmer,
            where=where,
            at=NOW,
        )


def test_the_governance_control_is_the_access_review_screens_own_capability() -> None:
    """**M33.1.2.3, M33.1.2.4.** Confirming a role grant and disabling a principal are both
    the grant decision, so both are `approve:grant`, pinned against the screen rather than
    derived from it: derived, the comparison would be a constant against itself.

    Delete this and `admin:principal` arrives from the console layer, where the administrator
    reviewing grants would never meet it."""
    assert screen("access_review").read.requires == GOVERNANCE_CONTROL
    assert global_gaps(control=Capability(value="admin:principal")) != ()


# -------------------------------------------------------------- disable a principal
def test_disabling_a_principal_deletes_the_grants_and_ends_the_sessions() -> None:
    """**M33.1.2.4, and the positive case.** `brain.identity.lifecycle.disable` does all three
    acts and is called rather than reimplemented: a console that ended the sessions and forgot
    the logout floor would leave every token already minted working, and would look correct in
    every test that held the registry.

    Asserted on the floor as well as on the ended session, because the floor is the half a
    second implementation would omit.

    Delete this and the console grows its own disable."""
    leaver = Principal(
        id="u_leaver",
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="a leaver",
    )
    registry = SessionRegistry()
    registry.register(
        Session(
            session_id="s_1",
            principal_id="u_leaver",
            issuer="https://idp.example.invalid/realms/one",
            subject="idp-subject-1",
            opened_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(hours=1),
            absolute_expiry=NOW + timedelta(hours=2),
        )
    )

    done = disable_principal(
        leaver,
        holding(GOVERNANCE_CONTROL.value),
        where={"department": MAINTENANCE},
        registry=registry,
        at=NOW,
    )

    assert [one.session_id for one in done.ended_sessions] == ["s_1"]
    assert registry.get("s_1") is None
    assert registry.not_before_for("u_leaver") == NOW
    assert not done.principal.is_active(NOW)


def test_nobody_disables_themselves_and_nobody_disables_outside_their_scope() -> None:
    """**M33.1.2.4.** Two refusals. Disabling yourself deletes the grants that would have let
    you undo it and ends the session you are reading the screen on, which is the one act in
    this group with no reviewer left afterwards. And a reader whose grant is scoped to one
    department may not disable somebody in another, which is `may_disable` matching the scope
    against the row rather than checking the capability exists.

    Delete this and an administrator locks the install out of itself, or reaches across a
    department boundary that every listing respects."""
    self_target = Principal(
        id="u_admin",
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="the admin",
    )
    other = Principal(
        id="u_other",
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="somebody else",
    )
    admin = holding(GOVERNANCE_CONTROL.value, department=MAINTENANCE)

    with pytest.raises(GlobalSurfaceError, match="disabling themselves"):
        disable_principal(
            self_target,
            admin,
            where={"department": MAINTENANCE},
            registry=SessionRegistry(),
            at=NOW,
        )
    assert not may_disable(admin, {"department": FINANCE}, NOW)
    with pytest.raises(GlobalSurfaceError, match="may not disable"):
        disable_principal(
            other, admin, where={"department": FINANCE}, registry=SessionRegistry(), at=NOW
        )


# ------------------------------------------------------------------ the self-grant path
def _ledger_with(*grants: tuple[str, str]) -> AuditChain:
    """A chain carrying one GRANT entry per pair of (actor, subject id)."""
    chain = AuditChain()
    for actor, subject_id in grants:
        chain.append(
            action=AuditAction.GRANT,
            actor_id=actor,
            subject=f"principal:{subject_id}",
            ent_hash="0" * 32,
            trace_id="t_1",
            at=NOW,
            details={"capability": "read:client.name"},
        )
    return chain


def test_a_self_grant_is_detected_from_the_entry_and_a_steward_is_told() -> None:
    """**M33.1.2.5.** The detection is `brain.console.reads.self_grants` and nothing here
    inspects an action or a subject: a self-grant is a GRANT whose subject names its own
    actor, read off the entry rather than declared by whoever wrote the grant path.

    The steward is a standing Super Admin who is not the actor, so the notice reaches somebody
    who did not already know. A grant to somebody else produces no notice, which is the
    negative half and proves the detection is not simply notifying on every grant.

    Delete this and a second detection arrives, or the notice goes to the person it is
    about."""
    ledger = _ledger_with(("u_self", "u_self"), ("u_admin", "u_someone_else"))
    admins = super_admins("u_self", "u_admin", "u_steward")

    notices = self_grant_notices(ledger.entries, role_grants=admins, now=NOW)

    assert len(notices) == 1
    assert notices[0].grant.principal_id == "u_self"
    assert notices[0].steward_id == "u_admin"
    assert "u_self" in notices[0].render()
    assert "read:client.name" not in notices[0].render()


def test_the_steward_is_never_the_actor_and_a_deputy_is_never_the_steward() -> None:
    """**M33.1.2.5.** Loud means somebody else finds out. A notice addressed to the principal
    who performed the act tells nobody anything and passes every test that checks a
    notification was produced.

    A deputy is excluded because `standing_super_admins` excludes one: a notice whose only
    reader is a thirty-day appointment stops being read on a date nobody diarised. And an
    install where the only standing Super Admin is the actor is refused rather than notified
    into a void.

    Delete this and the steward becomes whoever is first in the role table."""
    deputy = RoleGrant(
        principal_id="u_deputy",
        role=Role.SUPER_ADMIN,
        granted_by="u_self",
        reason="cover for annual leave",
        granted_at=NOW - timedelta(days=1),
        not_after=NOW + timedelta(days=20),
        deputy_of="u_self",
    )

    assert steward_for(super_admins("u_self", "u_other"), actor_id="u_self", now=NOW) == "u_other"
    with pytest.raises(GlobalSurfaceError, match="no steward"):
        steward_for((*super_admins("u_self"), deputy), actor_id="u_self", now=NOW)
    with pytest.raises(GlobalSurfaceError, match="no steward"):
        self_grant_notices(
            _ledger_with(("u_self", "u_self")).entries,
            role_grants=super_admins("u_self"),
            now=NOW,
        )


# ------------------------------------------------------------------------- the diagnostic
def test_a_row_that_counts_what_it_hid_is_reported() -> None:
    """The check is on the shape of the types rather than on a rule somebody remembers,
    because the field that breaks it is added by whoever is making a screen better. Run
    against a constructed row so the refusal is exercised rather than asserted to be
    unreachable, and against the healthy set so the diagnostic is not simply always red.

    Delete this and `EstateRow.hidden_count` arrives with a plausible default."""
    counted = make_dataclass("Counted", [("item_id", str), ("hidden", int)])

    assert global_gaps() == ()
    assert any("Counted.hidden" in one for one in global_gaps(rows=(counted,)))
    assert any(
        "not a registered screen" in one
        for one in global_gaps(screen_by_kind={EstateKind.AGENT: "a_screen_nobody_registered"})
    )


def test_every_estate_screen_is_a_screen_this_console_registers() -> None:
    """The four keys are compared against `brain.console.screens.SCREENS` rather than assumed,
    because `screen()` raising is what would otherwise happen at render time on somebody
    else's install. A key that stopped existing would be a listing behind no grant.

    Delete this and a renamed screen turns a listing into a KeyError, or worse, into a
    listing nothing governs."""
    registered = {one.key for one in SCREENS}

    assert set(ESTATE_SCREEN.values()) <= registered
    assert len(set(ESTATE_SCREEN.values())) == len(EstateKind)


# --- guards a mutation found unreachable (M33.1.2.3) ------------------------------------------


def test_a_nomination_refuses_every_shape_of_missing_that_it_names() -> None:
    """**Found by mutating every `if` in the module rather than the ones somebody thought of.**
    `Nomination.__post_init__` refuses four things and the tests reached one: the
    self-nomination. The other three could each be deleted from the validator with the whole
    suite green, because every nomination built anywhere in these tests names two different
    people, carries a reason and carries an aware time.

    They are not decoration. A nomination naming nobody cannot be confirmed or reviewed. A
    nomination with no reason is one nobody can review later, and the review is the only thing
    that ever removes an appointment that should not have been made. A naive time compares
    wrongly against an aware confirmation, which is the bug that shows up once, in the hour
    around a daylight-saving change, in a record about who was made an administrator.

    Whitespace as well as empty for the two string fields, because `" "` is what arrives from
    a form and passes a bare falsiness check.

    Delete this and three of the four go back to being unreachable, which is how they got
    here."""

    def a_nomination(**changed: object) -> Nomination:
        fields: dict[str, object] = {
            "principal_id": "u_1",
            "role": Role.SUPER_ADMIN,
            "nominated_by": "u_2",
            "reason": "they run the department and have done for two years",
            "at": NOW,
        }
        fields.update(changed)
        return Nomination(**fields)  # type: ignore[arg-type]

    assert a_nomination().principal_id == "u_1"

    for nobody in ("", " "):
        with pytest.raises(GlobalSurfaceError, match="naming nobody"):
            a_nomination(principal_id=nobody)
        with pytest.raises(GlobalSurfaceError, match="naming nobody"):
            a_nomination(nominated_by=nobody)
        with pytest.raises(GlobalSurfaceError, match="no reason"):
            a_nomination(reason=nobody)

    with pytest.raises(GlobalSurfaceError, match="naive"):
        a_nomination(at=datetime(2027, 3, 9, 9, 0))


def test_holding_the_governance_control_nowhere_refuses_like_holding_it_elsewhere() -> None:
    """The fourth guard the mutation found: `scope_for` returning `None`, which is a reader who
    does not hold the capability at all, as opposed to one who holds it somewhere that does not
    admit the row. Both refuse, which is why nothing noticed; they are two answers to the
    helper and one answer to the reader, and that is why it is an early return rather than a
    `matches` on a scope that might be `None`.

    **Reached through `may_confirm` and not through the estate.** Two earlier attempts at this
    could not fire the branch: `visible_estate` asks `permitted` first, so a reader who does
    not hold the capability is refused before the scope is looked up, and an empty entitlement
    set fails the console-plane check even earlier. `may_confirm` and
    `may_approve_publication` are the two callers that ask nothing before it except a
    self-exclusion, so they are the only doors to it.

    Three readers, because a guard tested only by the absent case is satisfied by a function
    that refuses everybody.

    Delete this and `scope_for` can stop being asked, and a reader holding nothing is decided
    by whatever a `None` scope happens to do."""
    nomination = Nomination(
        principal_id="u_1",
        role=Role.SUPER_ADMIN,
        nominated_by="u_2",
        reason="they run the department and have done for two years",
        at=NOW,
    )
    where = {"department": MAINTENANCE}

    holds_nothing = EntitlementSet(principal_id="u_admin", grants=())
    holds_elsewhere = holding(GOVERNANCE_CONTROL.value, department=FINANCE)
    holds_here = holding(GOVERNANCE_CONTROL.value, department=MAINTENANCE)

    assert not may_confirm(nomination, holds_nothing, where, NOW)
    assert not may_confirm(nomination, holds_elsewhere, where, NOW)
    assert may_confirm(nomination, holds_here, where, NOW)


# --- publish and retire global agents (M33.1.2.1) ---------------------------------------------


def an_agent(
    agent_id: str = "a_triage",
    *,
    level: Visibility = Visibility.PERSONAL,
    owner_id: str = "u_owner",
    archived_at: datetime | None = None,
) -> AgentRecord:
    """One agent record, through its own validators, with the audience under the test's
    control because the audience is the field this surface is about."""
    return AgentRecord.model_validate(
        {
            "agent_id": agent_id,
            "display_name": "Support triage",
            "persona": "Answers support questions in the house voice.",
            "audience": AgentAudience(level=level, owner_id=owner_id),
            "authority": AgentAuthority(),
            "created_by": owner_id,
            "archived_at": archived_at,
        }
    )


def test_publishing_asks_for_the_visibility_capability_and_not_the_one_that_writes_grants() -> None:
    """**A publication widens who is told about an agent and never what the agent reaches.**
    The run reach has no term for an audience, so a published agent hands nobody a row, and
    asking for `GOVERNANCE_CONTROL` here would say the opposite.

    It would also refuse the person the leaf names: a super administrator deliberately not
    granted a department's data could not publish that department's agent, while publishing it
    lets them read none of it.

    Both directions, and the discriminating reader holds the grant-writing capability and not
    the visibility one, which is the mix-up this test exists to catch.

    Delete this and the console asks for the wrong capability, and the audience becomes a
    function of somebody's reach."""
    holds_visibility = holding(AGENT_PUBLICATION_CAPABILITY.value)
    holds_grants = holding(GOVERNANCE_CONTROL.value)

    assert may_publish(holds_visibility, NOW)
    assert not may_publish(holds_grants, NOW)
    assert not may_publish(EntitlementSet(principal_id="u_admin", grants=()), NOW)


def test_the_control_is_offered_only_for_agents_it_would_actually_move() -> None:
    """A queue offering a row it will refuse invites the attempt and then explains it, which
    is the shape `brain.console.role_surfaces` rejected for expired suspensions.

    Three exclusions and each is `lifecycle.publish`'s own refusal read one step earlier: an
    already-company agent, where publishing is a no-op and an offer that changes nothing reads
    as an offer that does something; an archived one, which is terminal, so publishing it
    would put a thing nobody can start in front of everybody; and the reader's own, because a
    gate one person passes alone is not a gate.

    Delete this and the surface offers a control for every agent and the refusals arrive one
    click later, which is the same information delivered worse."""
    mine = an_agent("a_mine", owner_id="u_admin")
    already = an_agent("a_already", level=Visibility.COMPANY)
    gone = an_agent("a_gone", archived_at=NOW - timedelta(days=1))
    ready = an_agent("a_ready")

    reader = holding(AGENT_PUBLICATION_CAPABILITY.value)
    offered = publishable([mine, already, gone, ready], reader, NOW)

    assert [one.agent_id for one in offered] == ["a_ready"]


def test_a_reader_without_the_capability_is_offered_nothing_rather_than_a_list() -> None:
    """The other half, and the one a fixture makes unreachable if every reader holds the
    capability. An empty tuple rather than the four rows greyed out: a control somebody cannot
    press, rendered beside three they also cannot press, is a list of agents disclosed to
    somebody with no grant over any of them.

    Asserted against the same records the test above admits one of, so the difference is the
    reader and nothing else.

    Delete this and the estate leaks through the publish control."""
    ready = an_agent("a_ready")
    reader = holding(GOVERNANCE_CONTROL.value)

    assert publishable([ready], reader, NOW) == ()
    assert publishable([ready], holding(AGENT_PUBLICATION_CAPABILITY.value), NOW) == (ready,)


def test_neither_transition_is_written_here_and_both_are_the_lifecycle_modules() -> None:
    """The structural claim the module docstring makes, asserted rather than described.

    An agent state transition written in a console module is a transition living outside the
    module that owns transitions, which is the second implementation this repository refuses,
    and it is why this leaf sat open for two days rather than being half-built. Both halves of
    M33.1.2.1 are `brain.agents.lifecycle`'s: `publish` moves the audience and `archive`
    retires.

    Read off the source rather than from the imports, because an import can be present while a
    function nearby does the work itself, which is exactly how a second implementation
    arrives.

    Delete this and somebody adds a three-line `set_audience` here on a Friday."""
    import inspect

    from brain.console import global_surfaces

    body = inspect.getsource(global_surfaces)

    assert "def publish(" not in body, "the transition is being written here"
    assert "def archive(" not in body, "the transition is being written here"
    assert publish.__module__ == "brain.agents.lifecycle"
    assert archive.__module__ == "brain.agents.lifecycle"
