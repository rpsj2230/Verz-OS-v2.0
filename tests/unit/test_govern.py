"""The governance surfaces held to what each may show, and to what it must never show.

Every test below hands over grants and rows and asks what comes back. Nothing here appoints
anybody to a role, because no function in the module can read an appointment, and a test that
passed a role in would be testing something that does not exist.

Six leaves are claimed and each is a disclosure decision rather than a page. A people row names
capabilities only to somebody who could have opened the Capabilities screen, and a subject
whose capabilities are withheld is indistinguishable from one holding none (M27.3.1). The six
roles and their holders are listed without anything anywhere mapping one to the other
(M27.3.3). The capability catalogue is disclosed whole and is never narrowed to what the reader
themselves holds (M27.3.4). A recertification round is filtered to the admin's own scope and
refuses a grant they could not have made or one of their own (M27.3.6). Revoking a grant leaves
the session it was read through standing, which is what the control is for, and the control
refuses identically for a session out of reach and a session that is not there (M27.3.8). A
friction row carries a shape and never the capability, the object or either of the counts, and
repeated runs collapse rather than publishing the number by repetition (M27.3.11).

Real `EntitlementSet`s, real `SubjectGrant`s, a real `SessionRegistry` and real
`DenialPattern`s built from a real `assess_denials` throughout. The revocation test in
particular runs `brain.identity.packs.revoke_capability` rather than deleting from a list,
because the claim being made is about what that function does and does not reach.

Task ids: M27.3.1, M27.3.3, M27.3.4, M27.3.6, M27.3.8, M27.3.11
"""

from __future__ import annotations

from dataclasses import fields, make_dataclass
from datetime import UTC, datetime, timedelta

import pytest

from brain.console import govern as govern_module
from brain.console.govern import (
    GOVERN_ROWS,
    GOVERN_SURFACE_COUNT,
    GOVERN_SURFACES,
    NAMES_THAT_WOULD_NAME_THE_THING,
    SESSION_CONTROL,
    VOCABULARY_SCREEN,
    Certification,
    Decision,
    FrictionRow,
    GovernError,
    GovernSurface,
    Placed,
    apply_round,
    catalogue,
    certify,
    end_one,
    friction,
    govern_gaps,
    may_certify,
    may_end,
    may_name_capabilities,
    open_sessions,
    owners,
    people,
    recertifiable,
    role_catalogue,
    role_holders,
    surface_for,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import SCREENS, Group, screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.identity.packs import SubjectGrant
from brain.identity.roles import ROLE_COUNT, Role, RoleGrant, role_capability_leaks
from brain.identity.sessions import Session, SessionRegistry
from brain.identity.teams import PrincipalSubject, principal_subject, team_subject
from brain.ops.denial_alerts import ALERT_TEXT, DenialPattern
from brain.ops.limits import DenialShape, assess_denials

#: A fixed moment, so an expiry test cannot pass because the machine's clock happened to sit
#: on the convenient side of a boundary. Everything below is built relative to it.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

#: Two departments, so a scoped reader has somewhere to be refused.
MAINTENANCE = "maintenance"
FINANCE = "finance"

#: The capabilities the rows below are written over.
NAME = "read:client.name"
CONTRACT_VALUE = "read:client.contract_value"
EVERY_CLIENT_FIELD = "read:client.*"


def holding(
    *capabilities: str,
    planes: tuple[Plane, ...] = (Plane.CONFIGURATION,),
    scope: Scope | None = None,
    principal_id: str = "u_reader",
) -> EntitlementSet:
    """A reader holding these capabilities in one scope, plus the plane grants named.

    Built here rather than taken from a fixture so a test can hold the tool's capability and
    not the plane, or hold the same capabilities in two different scopes, which is what most
    of the narrowing tests below vary.
    """
    where = scope if scope is not None else Scope(clauses=())
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id=principal_id, grants=tuple(grants))


def grant_of(
    capability: str,
    *,
    subject_id: str = "u_1",
    department: str = MAINTENANCE,
    granted_at: datetime = NOW - timedelta(days=30),
    not_after: datetime | None = None,
) -> SubjectGrant:
    """One real grant row, through `SubjectGrant`'s own validators."""
    return SubjectGrant(
        subject=principal_subject(subject_id),
        capability=Capability(value=capability),
        scope=Scope.department(department),
        granted_by="u_admin",
        reason="written for this test",
        granted_at=granted_at,
        not_after=not_after,
    )


def placed_grant(
    capability: str, *, department: str = MAINTENANCE, **kwargs: object
) -> Placed[SubjectGrant]:
    """One grant, paired with the row saying which department its subject sits in."""
    record = grant_of(capability, department=department, **kwargs)  # type: ignore[arg-type]
    return Placed(record=record, where={"department": department})


def session_of(
    session_id: str,
    *,
    principal_id: str = "u_1",
    opened_at: datetime = NOW - timedelta(minutes=5),
    idle: timedelta = timedelta(minutes=30),
) -> Session:
    """One sign-in, through `Session`'s own validators."""
    return Session(
        session_id=session_id,
        principal_id=principal_id,
        issuer="https://idp.example.invalid/realms/one",
        subject="sub-1",
        opened_at=opened_at,
        expires_at=opened_at + idle,
        absolute_expiry=opened_at + timedelta(hours=10),
    )


def placed_session(
    session_id: str, *, department: str = MAINTENANCE, **kwargs: object
) -> Placed[Session]:
    """One sign-in, paired with the row saying where its principal sits."""
    record = session_of(session_id, **kwargs)  # type: ignore[arg-type]
    return Placed(record=record, where={"department": department})


def pattern_of(
    *,
    subject_id: str = "u_probe",
    capability: str = CONTRACT_VALUE,
    denials: int = 40,
    distinct_targets: int = 9,
    department: str = MAINTENANCE,
) -> DenialPattern:
    """One run of denials, classified by the real `assess_denials`."""
    return DenialPattern(
        subject_id=subject_id,
        capability=Capability(value=capability),
        assessment=assess_denials(denials=denials, distinct_targets=distinct_targets),
        where={"department": department},
    )


# ------------------------------------------------------------------ the register of eighteen
def test_every_govern_screen_names_the_module_that_already_does_the_work() -> None:
    """Delete this and the register can drift from the screen registry, which is the whole
    value of it: a governance screen with no named owner is a screen the next person builds a
    second implementation behind, and an owner that does not import is a claim nobody checked.

    Asserted against `SCREENS` rather than against a list here, because the two lists agreeing
    is the property; a copy of the eighteen keys in this file would agree with itself."""
    from_registry = tuple(one.key for one in SCREENS if one.group is Group.GOVERN)

    assert tuple(one.key for one in GOVERN_SURFACES) == from_registry
    assert len(from_registry) == GOVERN_SURFACE_COUNT
    assert len(GOVERN_SURFACES) == GOVERN_SURFACE_COUNT
    assert govern_gaps() == ()


def test_the_owners_are_the_modules_and_not_the_joins() -> None:
    """Delete this and `owners` can start returning one entry per surface, which reads as
    fifteen dependencies being eighteen and tells a reader that three modules exist which do
    not."""
    found = owners()

    assert len(found) == len(set(found))
    assert "brain.console.reach_view" in found
    assert found.count("brain.console.reach_view") == 1
    assert surface_for("access_friction").owner == "brain.ops.denial_alerts"
    with pytest.raises(KeyError):
        surface_for("overview")


def test_a_surface_naming_a_module_that_does_not_import_is_reported() -> None:
    """Delete this and the register's owners are prose again. The check exists so that "this
    is already built in X" is verified on every run rather than on the day it was written."""
    broken = (
        *GOVERN_SURFACES[1:],
        GovernSurface(
            key="people",
            owner="brain.identity.packs_that_do_not_exist",
            shows="everything",
            never="nothing",
        ),
    )

    found = govern_gaps(surfaces=broken)

    assert len(found) == 1
    assert "packs_that_do_not_exist" in found[0]


def test_a_govern_screen_with_no_surface_is_reported() -> None:
    """Delete this and a screen can be added to the govern group with nothing saying which
    module it reads, which is the state in which somebody writes the second implementation."""
    found = govern_gaps(surfaces=GOVERN_SURFACES[:-1])

    assert len(found) == 1
    assert "audit" in found[0]


def test_a_surface_registered_twice_is_reported() -> None:
    """Delete this and two entries can claim one screen, so which module a reader is told
    owns it depends on which entry was read first."""
    found = govern_gaps(surfaces=(*GOVERN_SURFACES, GOVERN_SURFACES[0]))

    assert len(found) == 1
    assert "people" in found[0]


def test_a_surface_naming_a_screen_outside_the_govern_group_is_reported() -> None:
    """Delete this and the register can describe screens that are not governance screens,
    which makes the count of eighteen mean nothing and hides a missing entry behind a spare
    one."""
    stray = GovernSurface(
        key="overview", owner="brain.ops.telemetry", shows="everything", never="nothing"
    )

    found = govern_gaps(surfaces=(*GOVERN_SURFACES, stray))

    assert len(found) == 1
    assert "overview" in found[0]


def test_a_surface_that_does_not_say_what_it_must_never_show_is_refused() -> None:
    """Delete this and the second sentence becomes optional, which is the one a screen gets
    built without: what a surface shows is in the ticket and what it must not is not."""
    with pytest.raises(GovernError):
        GovernSurface(key="people", owner="brain.identity.packs", shows="everything", never=" ")
    with pytest.raises(GovernError):
        GovernSurface(key="people", owner=" ", shows="everything", never="nothing")


def test_a_row_type_that_counts_what_it_withheld_is_reported() -> None:
    """Delete this and a field called `hidden` can be added to a governance row to make a
    screen more useful, which publishes the size of what the reader may not see."""
    counting = make_dataclass("Counting", [("hidden", int)])

    found = govern_gaps(rows=[counting])

    assert len(found) == 1
    assert "Counting.hidden" in found[0]


def test_a_friction_row_that_carries_the_assessment_is_reported() -> None:
    """Delete this and the denial counts can be put back on the friction row under the name
    of the type that carries them, which is the leak the whole surface exists to avoid and
    the one the generic hidden-count check does not look for."""
    naming = make_dataclass("Naming", [("assessment", str), ("note", str)])

    found = govern_gaps(friction_row=naming)

    assert len(found) == 2
    assert {"assessment", "note"} <= NAMES_THAT_WOULD_NAME_THE_THING
    assert all("Naming." in one for one in found)


def test_a_mapping_from_a_role_to_a_capability_in_this_module_is_reported() -> None:
    """Delete this and a convenience mapping from a role to what it may see can be added here
    under a friendlier name. This module is not in the identity package, so the invariant
    suite's sweep over that package does not reach it, and the Roles surface is exactly where
    somebody would write one."""
    leaking = {"DEFAULTS": {Role.SUPER_ADMIN: Capability(value=NAME)}}

    found = govern_gaps(namespace=leaking)

    assert len(found) == 1
    assert "DEFAULTS" in found[0]


def test_nothing_in_this_module_maps_a_role_to_a_capability() -> None:
    """The positive half of the test above. Delete this and the check can be running over a
    namespace that never contained a leak, which passes for every module in the repository."""
    assert role_capability_leaks(vars(govern_module)) == []


# ------------------------------------------------------- the capability catalogue (M27.3.4)
def test_the_capability_catalogue_is_disclosed_whole_to_a_reader_granted_the_vocabulary() -> None:
    """M27.3.4. Delete this and the catalogue can start returning only what the reader holds,
    which is their own entitlement under a heading reading everything that can be granted at
    all, and an administrator then writes a grant for a capability the screen said did not
    exist.

    The reader here holds none of the vocabulary, so a filtered implementation returns an
    empty tuple and this fails."""
    vocabulary = [Capability(value=one) for one in ("read:invoice.amount", NAME, CONTRACT_VALUE)]
    reader = holding("read:capability")

    assert catalogue(vocabulary, reader) == (CONTRACT_VALUE, NAME, "read:invoice.amount")


def test_the_catalogue_is_not_narrowed_to_the_part_the_reader_already_holds() -> None:
    """M27.3.4. The sharper half: a reader holding one of the three still gets all three.
    Delete this and an implementation that intersected the vocabulary with the reader's own
    grants would pass the test above only if the reader held nothing, which is the fixture
    somebody changes."""
    vocabulary = [Capability(value=one) for one in ("read:invoice.amount", NAME, CONTRACT_VALUE)]
    reader = holding("read:capability", NAME)

    assert catalogue(vocabulary, reader) == (CONTRACT_VALUE, NAME, "read:invoice.amount")


def test_a_reader_without_the_vocabulary_grant_learns_nothing_about_the_vocabulary() -> None:
    """M27.3.4. Delete this and the catalogue is disclosed to anybody who reaches the console
    at all, which is the vocabulary handed to every department admin in the company."""
    vocabulary = [Capability(value=NAME)]

    assert catalogue(vocabulary, holding(NAME)) == ()
    assert catalogue(vocabulary, holding("read:capability", planes=(Plane.EXISTENCE,))) == ()
    assert not may_name_capabilities(holding(NAME))


def test_the_vocabulary_grant_is_the_capabilities_screens_own() -> None:
    """Delete this and `VOCABULARY_SCREEN` can be repointed at another screen, so the People
    screen's second column would be governed by whatever that screen requires. Compared
    against the registry, which is outside this module, rather than against itself."""
    assert screen(VOCABULARY_SCREEN).read.requires == Capability(value="read:capability")
    assert screen(VOCABULARY_SCREEN).read.plane is Plane.CONFIGURATION


# --------------------------------------------------------------- people and grants (M27.3.1)
def test_a_people_row_names_capabilities_only_to_a_reader_granted_the_vocabulary() -> None:
    """M27.3.1. Delete this and the People screen becomes a way of reading the capability
    vocabulary without the Capabilities screen's grant, which is the shortcut
    `brain.console.workspace.basis_for` refuses about money one surface over."""
    holdings = [placed_grant(NAME), placed_grant(CONTRACT_VALUE)]
    scoped = Scope.department(MAINTENANCE)

    both = holding("read:grant", "read:capability", scope=scoped)
    assert people(holdings, both, NOW) == (
        govern_module.PersonRow(subject="principal:u_1", capabilities=(CONTRACT_VALUE, NAME)),
    )

    listing_only = holding("read:grant", scope=scoped)
    assert people(holdings, listing_only, NOW) == (
        govern_module.PersonRow(subject="principal:u_1", capabilities=()),
    )


def test_a_subject_whose_capabilities_are_withheld_looks_like_one_holding_a_single_grant() -> None:
    """M27.3.1. The DENIED-equals-ABSENT half. Delete this and a field saying "withheld", or
    a row whose length varied with what was hidden, would tell the reader that this subject
    holds something they may not be told about, which is the disclosure the withholding was
    for.

    Two subjects with different numbers of grants produce identical rows apart from the id."""
    holdings = [
        placed_grant(NAME, subject_id="u_1"),
        placed_grant(NAME, subject_id="u_2"),
        placed_grant(CONTRACT_VALUE, subject_id="u_2"),
        placed_grant("read:invoice.amount", subject_id="u_2"),
    ]
    reader = holding("read:grant", scope=Scope.department(MAINTENANCE))

    rows = people(holdings, reader, NOW)

    assert [one.capabilities for one in rows] == [(), ()]
    assert {one.name for one in fields(govern_module.PersonRow)} == {"subject", "capabilities"}


def test_a_grant_over_a_department_the_reader_cannot_reach_is_not_listed() -> None:
    """M27.3.1. Delete this and the People screen shows every grant in the company to any
    department admin who can open it, which is the whole grant table read from a screen whose
    rows nobody thought were sensitive."""
    holdings = [
        placed_grant(NAME, subject_id="u_1", department=MAINTENANCE),
        placed_grant(NAME, subject_id="u_2", department=FINANCE),
    ]
    reader = holding("read:grant", scope=Scope.department(MAINTENANCE))

    assert [one.subject for one in people(holdings, reader, NOW)] == ["principal:u_1"]

    company_wide = holding("read:grant")
    assert [one.subject for one in people(holdings, company_wide, NOW)] == [
        "principal:u_1",
        "principal:u_2",
    ]


def test_a_lapsed_grant_is_not_a_holding() -> None:
    """M27.3.1. Delete this and the screen lists a grant that confers nothing as though it
    did, so a recertification round built from the same rows would confirm access that had
    already ended and an auditor would read the list as current."""
    live = placed_grant(NAME, subject_id="u_1")
    lapsed = Placed(
        record=grant_of(
            CONTRACT_VALUE,
            subject_id="u_2",
            granted_at=NOW - timedelta(days=40),
            not_after=NOW - timedelta(days=1),
        ),
        where={"department": MAINTENANCE},
    )
    reader = holding("read:grant", "read:capability", scope=Scope.department(MAINTENANCE))

    rows = people([live, lapsed], reader, NOW)

    assert rows == (govern_module.PersonRow(subject="principal:u_1", capabilities=(NAME,)),)


def test_a_people_row_and_its_capabilities_come_back_in_a_stable_order() -> None:
    """M27.3.1. Delete this and the screen's order follows whatever order the grant query
    returned, so two readings of an unchanged grant table are two different lists and an
    administrator comparing this week's against last week's sees movement that did not happen.

    Both orders are asserted, because they are two `sorted` calls and either can be dropped
    on its own: the subjects, and the capabilities inside one row."""
    holdings = [
        placed_grant("read:invoice.amount", subject_id="u_zeta"),
        placed_grant(NAME, subject_id="u_alpha"),
        placed_grant(CONTRACT_VALUE, subject_id="u_alpha"),
    ]
    reader = holding("read:grant", "read:capability", scope=Scope.department(MAINTENANCE))

    rows = people(holdings, reader, NOW)

    assert [one.subject for one in rows] == ["principal:u_alpha", "principal:u_zeta"]
    assert rows[0].capabilities == (CONTRACT_VALUE, NAME)


def test_one_capability_granted_twice_appears_once() -> None:
    """M27.3.1. Delete this and the row repeats a capability once per grant row behind it, so
    a reader counts the grants a subject holds of one thing without ever being shown one of
    them, which is the count rule broken by a list that looks merely untidy."""
    twice = [
        placed_grant(NAME, subject_id="u_1", granted_at=NOW - timedelta(days=30)),
        placed_grant(NAME, subject_id="u_1", granted_at=NOW - timedelta(days=2)),
    ]
    reader = holding("read:grant", "read:capability", scope=Scope.department(MAINTENANCE))

    assert people(twice, reader, NOW) == (
        govern_module.PersonRow(subject="principal:u_1", capabilities=(NAME,)),
    )


def test_a_team_holding_a_grant_is_a_row_like_any_other() -> None:
    """M27.3.1. Delete this and a team grant is silently dropped from the screen, so a reader
    reviewing what a department holds sees the individual grants and none of the team ones,
    which is the half of the grant table that reaches the most people."""
    team = Placed(
        record=SubjectGrant(
            subject=team_subject("web.design"),
            capability=Capability(value=NAME),
            scope=Scope.department(MAINTENANCE),
            granted_by="u_admin",
            reason="written for this test",
            granted_at=NOW - timedelta(days=5),
        ),
        where={"department": MAINTENANCE},
    )
    reader = holding("read:grant", "read:capability", scope=Scope.department(MAINTENANCE))

    assert people([team], reader, NOW) == (
        govern_module.PersonRow(subject="team:web.design", capabilities=(NAME,)),
    )


# -------------------------------------------------------------------------- roles (M27.3.3)
def test_the_role_catalogue_is_the_six_and_cannot_see_a_reader() -> None:
    """M27.3.3. Delete this and `role_catalogue` can grow an entitlement parameter, at which
    point what a role exists to do becomes a decision about the reader rather than product
    documentation, and the first thing anybody would filter it by is the reader's own role."""
    found = role_catalogue()

    assert len(found) == ROLE_COUNT
    assert tuple(one.role for one in found) == tuple(Role)
    assert all(one.exists_to.strip() for one in found)
    assert role_catalogue.__code__.co_argcount == 0


def test_role_holders_are_narrowed_by_the_readers_own_scope() -> None:
    """M27.3.3. Delete this and the Roles screen tells a department admin who administers
    every other department, which is a map of who to ask and who to impersonate."""
    here = Placed(record=role_grant("u_1", Role.MEMBER), where={"department": MAINTENANCE})
    elsewhere = Placed(record=role_grant("u_2", Role.MEMBER), where={"department": FINANCE})
    reader = holding("read:role", scope=Scope.department(MAINTENANCE))

    assert role_holders([here, elsewhere], reader, NOW) == (here,)
    assert role_holders([here, elsewhere], holding("read:role"), NOW) == (here, elsewhere)


def test_a_lapsed_deputy_is_absent_rather_than_shown_as_lapsed() -> None:
    """M27.3.3. Delete this and the screen lists somebody as holding a role they no longer
    hold. Greying the row out is the shape `role_surfaces` rejected for expired suspensions:
    it invites an act that will be refused, and here it invites a reader to trust a name."""
    standing = Placed(record=role_grant("u_1", Role.MEMBER), where={"department": MAINTENANCE})
    lapsed = Placed(
        record=RoleGrant(
            principal_id="u_2",
            role=Role.MEMBER,
            granted_by="u_sa",
            reason="written for this test",
            granted_at=NOW - timedelta(days=20),
            not_after=NOW - timedelta(days=1),
            deputy_of="u_1",
        ),
        where={"department": MAINTENANCE},
    )
    reader = holding("read:role", scope=Scope.department(MAINTENANCE))

    assert role_holders([standing, lapsed], reader, NOW) == (standing,)


def role_grant(principal_id: str, role: Role) -> RoleGrant:
    """One real role grant, through `RoleGrant`'s own validators."""
    return RoleGrant(
        principal_id=principal_id,
        role=role,
        granted_by="u_sa",
        reason="written for this test",
        granted_at=NOW - timedelta(days=100),
    )


# ------------------------------------------------------------------ access review (M27.3.6)
def test_a_grant_outside_the_admins_scope_is_not_in_their_round() -> None:
    """M27.3.6. Delete this and a recertification round widens the admin by showing: they
    learn a capability exists, that somebody holds it, and who, none of which was theirs to
    learn, and no grant was written anywhere for anybody to review."""
    mine = placed_grant(NAME, subject_id="u_1", department=MAINTENANCE)
    theirs = placed_grant(NAME, subject_id="u_2", department=FINANCE)
    admin = holding("approve:grant", NAME, scope=Scope.department(MAINTENANCE))

    assert recertifiable([mine, theirs], admin, NOW) == (mine,)


def test_an_admin_may_not_certify_a_grant_they_could_not_have_made() -> None:
    """M27.3.6. Delete this and a recertification becomes the original decision laundered
    through a process: somebody who could not have written the grant confirms it a year later
    and the round is what everybody points at afterwards.

    The sibling below is the positive half, without which a function refusing everything
    passes."""
    holding_row = placed_grant(CONTRACT_VALUE, subject_id="u_1")
    without = holding("approve:grant", NAME, scope=Scope.department(MAINTENANCE))
    with_it = holding("approve:grant", CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))

    assert not may_certify(holding_row, without, NOW)
    assert may_certify(holding_row, with_it, NOW)


def test_an_admin_without_the_rounds_own_capability_certifies_nothing() -> None:
    """M27.3.6. The other half of the pair: holding the capability a grant names is not being
    entitled to run the round. Delete this and anybody who happens to hold `read:client.name`
    can confirm everybody else's grant of it."""
    holding_row = placed_grant(NAME, subject_id="u_1")
    reader = holding(NAME, scope=Scope.department(MAINTENANCE))

    assert not may_certify(holding_row, reader, NOW)


def test_certify_refuses_what_the_listing_would_never_have_offered() -> None:
    """M27.3.6. Delete this and the check lives only in the listing, so a submitted decision
    is accepted for whatever row was posted rather than for the rows that were offered. A form
    is submitted by what arrives, not by what was rendered."""
    theirs = placed_grant(NAME, subject_id="u_2", department=FINANCE)
    admin = holding("approve:grant", NAME, scope=Scope.department(MAINTENANCE))

    with pytest.raises(GovernError):
        certify(theirs, admin, Decision.REMOVE, by="u_reader", at=NOW, now=NOW)

    mine = placed_grant(NAME, subject_id="u_1", department=MAINTENANCE)
    decided = certify(mine, admin, Decision.KEEP, by="u_reader", at=NOW, now=NOW)
    assert decided.decision is Decision.KEEP
    assert decided.holding is mine


def test_certifying_your_own_grant_is_refused_by_the_constructor() -> None:
    """M27.3.6. Delete this and an admin renews their own grant every year with nobody ever
    deciding. The refusal is in the constructor rather than in `certify`, so a hand-built
    certification cannot go around it, and this test builds one by hand for that reason."""
    mine = placed_grant(NAME, subject_id="u_admin")

    with pytest.raises(GovernError):
        Certification(holding=mine, decision=Decision.KEEP, by="u_admin", at=NOW)

    somebody_else = Certification(holding=mine, decision=Decision.KEEP, by="u_other", at=NOW)
    assert somebody_else.by == "u_other"
    assert isinstance(mine.record.subject, PrincipalSubject)


def test_a_certification_carrying_a_naive_instant_or_no_decider_is_refused() -> None:
    """M27.3.6. Delete this and a round can be recorded with nobody accountable for it, or
    with a timestamp that compares wrongly against the round's own boundary, which is how a
    decision lands in the wrong round and the previous one looks complete."""
    mine = placed_grant(NAME, subject_id="u_1")

    with pytest.raises(GovernError):
        Certification(holding=mine, decision=Decision.KEEP, by=" ", at=NOW)
    with pytest.raises(GovernError):
        Certification(
            holding=mine, decision=Decision.KEEP, by="u_admin", at=datetime(2027, 5, 4, 10, 0)
        )


def test_a_removal_deletes_the_row_and_a_keep_leaves_it() -> None:
    """M27.3.6. Delete this and a round can conclude without changing anything, or can write
    a negative row instead of deleting: there is no deny list in this system and revocation is
    the deletion of a grant."""
    kept = grant_of(NAME, subject_id="u_1")
    removed = grant_of(CONTRACT_VALUE, subject_id="u_1")
    admin = holding("approve:grant", EVERY_CLIENT_FIELD, scope=Scope.department(MAINTENANCE))
    decisions = [
        certify(
            Placed(record=kept, where={"department": MAINTENANCE}),
            admin,
            Decision.KEEP,
            by="u_reader",
            at=NOW,
            now=NOW,
        ),
        certify(
            Placed(record=removed, where={"department": MAINTENANCE}),
            admin,
            Decision.REMOVE,
            by="u_reader",
            at=NOW,
            now=NOW,
        ),
    ]

    remaining = apply_round(decisions, [kept, removed])

    assert remaining == (kept,)


def test_removing_a_narrow_grant_does_not_delete_the_wildcard_that_implies_it() -> None:
    """M27.3.6. Delete this and a round that removed `read:client.name` also removes the
    `read:client.*` grant somebody else wrote for a different reason, which is more access
    taken away than anybody asked for and no record of the second decision having been made.

    `revoke_capability` is what enforces this and `apply_round` calls it rather than filtering
    the rows itself; this is the test that the call is the real one."""
    narrow = grant_of(NAME, subject_id="u_1")
    wide = grant_of(EVERY_CLIENT_FIELD, subject_id="u_1")
    decision = Certification(
        holding=Placed(record=narrow, where={"department": MAINTENANCE}),
        decision=Decision.REMOVE,
        by="u_admin",
        at=NOW,
    )

    assert apply_round([decision], [narrow, wide]) == (wide,)


# ----------------------------------------------------------------------- sessions (M27.3.8)
def test_revoking_a_grant_does_not_close_the_session_it_was_read_through() -> None:
    """M27.3.8. The leaf's own sentence, proven with the real revocation and a real registry.
    Delete this and nothing anywhere says why the Sessions screen carries a control: somebody
    reads `revoke_capability`, sees the row disappear, and concludes the access is gone, while
    the person keeps working at their old reach for up to the ten hours a session may run.

    Both halves are asserted. The revocation removes the row and does not reach the registry,
    and then the control does."""
    from brain.identity.packs import revoke_capability

    grants = (grant_of(CONTRACT_VALUE, subject_id="u_1"),)
    live = placed_session("sess_1", principal_id="u_1")
    registry = SessionRegistry()
    registry.register(live.record)

    remaining = revoke_capability(
        grants, principal_subject("u_1"), Capability(value=CONTRACT_VALUE)
    )

    assert remaining == ()
    assert registry.live_for("u_1", NOW) == (live.record,)
    assert registry.not_before_for("u_1") is None

    admin = holding("read:session", "approve:grant", scope=Scope.department(MAINTENANCE))
    ended = end_one(registry, "sess_1", sessions=[live], entitlement=admin, now=NOW)

    assert ended == live.record
    assert registry.live_for("u_1", NOW) == ()
    assert registry.not_before_for("u_1") == NOW


def test_the_control_is_the_capability_that_takes_a_grant_away() -> None:
    """M27.3.8. Delete this and `SESSION_CONTROL` can be repointed at the capability that
    merely lists sessions, so anybody who could read the screen could end anybody's sign-in.
    Compared against the Access review screen's own requirement, which lives outside this
    module, rather than against itself."""
    assert screen("access_review").read.requires == SESSION_CONTROL
    assert screen("sessions").read.requires != SESSION_CONTROL


def test_a_reader_may_see_a_session_without_being_able_to_end_it() -> None:
    """M27.3.8. Delete this and the listing capability and the control capability collapse
    into one, so the Sessions screen hands the power to sign everybody out to every reader it
    was opened for."""
    live = placed_session("sess_1", principal_id="u_1")
    watcher = holding("read:session", scope=Scope.department(MAINTENANCE))

    assert open_sessions([live], watcher, NOW) == (live,)
    assert not may_end(live, watcher, NOW)

    registry = SessionRegistry()
    registry.register(live.record)
    assert end_one(registry, "sess_1", sessions=[live], entitlement=watcher, now=NOW) is None
    assert registry.live_for("u_1", NOW) == (live.record,)


def test_a_session_out_of_reach_and_a_session_that_is_not_there_are_one_answer() -> None:
    """M27.3.8. Delete this and the control becomes a way of asking which sessions exist: an
    id that is refused differently from an id that is unknown answers the question for anybody
    who can type one, which is the deep-link oracle with a button instead of an address."""
    elsewhere = placed_session("sess_finance", principal_id="u_2", department=FINANCE)
    admin = holding("read:session", "approve:grant", scope=Scope.department(MAINTENANCE))
    registry = SessionRegistry()
    registry.register(elsewhere.record)

    out_of_reach = end_one(
        registry, "sess_finance", sessions=[elsewhere], entitlement=admin, now=NOW
    )
    not_there = end_one(registry, "sess_nothing", sessions=[elsewhere], entitlement=admin, now=NOW)

    assert out_of_reach is None
    assert not_there is None
    assert registry.live_for("u_2", NOW) == (elsewhere.record,)


def test_a_lapsed_session_is_absent_from_the_listing_and_from_the_control() -> None:
    """M27.3.8. Delete this and the screen lists a sign-in that admits nothing, with a control
    beside it that would end nothing, and a reader takes the list for who is working now."""
    lapsed = placed_session("sess_old", principal_id="u_1", opened_at=NOW - timedelta(hours=9))
    admin = holding("read:session", "approve:grant", scope=Scope.department(MAINTENANCE))
    registry = SessionRegistry()
    registry.register(lapsed.record)

    assert not lapsed.record.is_live(NOW)
    assert open_sessions([lapsed], admin, NOW) == ()
    assert end_one(registry, "sess_old", sessions=[lapsed], entitlement=admin, now=NOW) is None


def test_a_session_in_another_department_is_not_listed() -> None:
    """M27.3.8. Delete this and the Sessions screen shows the whole company's sign-ins to any
    department admin, which is an attendance register nobody granted them."""
    here = placed_session("sess_here", principal_id="u_1", department=MAINTENANCE)
    there = placed_session("sess_there", principal_id="u_2", department=FINANCE)
    admin = holding("read:session", scope=Scope.department(MAINTENANCE))

    assert open_sessions([here, there], admin, NOW) == (here,)
    assert open_sessions([here, there], holding("read:session"), NOW) == (here, there)


# ---------------------------------------------------------------- access friction (M27.3.11)
def test_a_friction_row_says_the_shape_and_never_the_capability_or_the_counts() -> None:
    """M27.3.11. Delete this and the row can be built from `DenialAssessment.note`, which
    reads almost identically and quotes both counts: forty facts about things the reader may
    not see and nine about how many of them there are.

    The text is compared against `denial_alerts.ALERT_TEXT`, which lives outside this module,
    rather than against a copy in this file."""
    pattern = pattern_of(denials=40, distinct_targets=9)
    reader = holding(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))

    rows = friction([pattern], reader, NOW)

    assert len(rows) == 1
    assert rows[0].subject_id == "u_probe"
    assert rows[0].shape is DenialShape.ENUMERATION
    assert rows[0].text == ALERT_TEXT[DenialShape.ENUMERATION]
    assert rows[0].text != pattern.assessment.note
    assert {one.name for one in fields(FrictionRow)} == {"subject_id", "shape", "text"}
    assert CONTRACT_VALUE not in repr(rows[0])
    assert "40" not in repr(rows[0])
    assert "9" not in repr(rows[0])


def test_repeated_runs_of_one_shape_collapse_into_one_row() -> None:
    """M27.3.11. Delete this and the number of runs is published by repetition: three rows
    reading the same subject and the same shape say three, and no check that looks for a field
    holding a number would notice."""
    runs = [pattern_of(denials=40 + n, distinct_targets=9) for n in range(3)]
    reader = holding(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))

    assert len(friction(runs, reader, NOW)) == 1


def test_two_shapes_from_one_person_are_two_rows() -> None:
    """M27.3.11. The positive half of the collapse. Delete this and an implementation
    returning one row per subject passes the test above while hiding that somebody is both
    persistently blocked in one place and walking the estate in another, which are two
    different things to do about them."""
    reader = holding(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))
    runs = [
        pattern_of(denials=40, distinct_targets=9),
        pattern_of(denials=20, distinct_targets=1),
    ]

    rows = friction(runs, reader, NOW)

    assert {one.shape for one in rows} == {DenialShape.ENUMERATION, DenialShape.ACCESS_NEEDED}


def test_the_friction_rows_come_back_in_a_stable_order() -> None:
    """M27.3.11. Delete this and the order follows whatever order the audit query returned,
    so two readings of an unchanged denial log are two different lists. The rows are already
    collapsed by subject and shape, so the order they arrived in carries nothing and sorting
    discards nothing."""
    reader = holding(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))
    later = pattern_of(subject_id="u_zeta")
    earlier = pattern_of(subject_id="u_alpha")

    rows = friction([later, earlier], reader, NOW)

    assert [one.subject_id for one in rows] == ["u_alpha", "u_zeta"]


def test_a_reader_is_never_shown_the_run_of_denials_they_are_the_subject_of() -> None:
    """M27.3.11. Delete this and somebody watching whether they appear on the screen can
    measure the boundary of what exists by walking it: the row's arrival is the oracle, and it
    is one they can trigger themselves."""
    about_them = pattern_of(subject_id="u_reader")
    themselves = holding(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))

    assert friction([about_them], themselves, NOW) == ()
    assert len(friction([about_them], holding(CONTRACT_VALUE, principal_id="u_other"), NOW)) == 1


def test_somebody_who_does_not_reach_what_was_denied_is_told_nothing_about_it() -> None:
    """M27.3.11. Delete this and the friction screen tells a reader that a capability exists
    which they hold no grant over, and that somebody in another department is being refused
    on it, which is the alert model's own rule broken by a listing."""
    pattern = pattern_of(department=FINANCE)
    elsewhere = holding(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))
    unrelated = holding(NAME)

    assert friction([pattern], elsewhere, NOW) == ()
    assert friction([pattern], unrelated, NOW) == ()
    assert len(friction([pattern], holding(CONTRACT_VALUE, scope=Scope.department(FINANCE)), NOW))


def test_a_run_below_the_noticing_threshold_produces_no_row() -> None:
    """M27.3.11. Delete this and every mistyped client name becomes a row about a colleague,
    which is the screen everybody stops reading in the first week and is also a listing of
    ordinary behaviour attributed by name.

    This is the only test watching that filter, because `friction` asks the sentence table
    once rather than asking `is_worth_alerting` as well: two checks nothing can tell apart
    are one check written twice, and a mutation of either alone survived while both were
    there."""
    ordinary = pattern_of(denials=3, distinct_targets=1)
    reader = holding(CONTRACT_VALUE, scope=Scope.department(MAINTENANCE))

    assert ordinary.shape is DenialShape.ORDINARY
    assert friction([ordinary], reader, NOW) == ()


def test_every_alerting_shape_has_a_sentence_so_the_silence_is_a_guard() -> None:
    """M27.3.11. The sentence table is the whole of `friction`'s silence, so this is what
    makes that one check total. Delete it and a shape can be added with no sentence, at which
    point a whole class of friction vanishes from the screen without anything failing; or
    `ORDINARY` can be given one, at which point every mistyped client name becomes a row.

    `denial_alerts.digest` pins the same set for the alert path, and this is the reading that
    lets a screen ask the table instead of asking the classifier a second time."""
    alerting = {one for one in DenialShape if one is not DenialShape.ORDINARY}

    assert alerting == set(ALERT_TEXT)
    assert DenialShape.ORDINARY not in ALERT_TEXT


# ------------------------------------------------------------------------- the shared parts
def test_a_record_with_no_place_reaches_only_a_company_wide_reader() -> None:
    """Delete this and the default `where` fails open: a governance record that arrived with
    no department attached would satisfy a scoped grant and appear on a department admin's
    screen, which is the direction that costs something."""
    unplaced: Placed[SubjectGrant] = Placed(record=grant_of(NAME, subject_id="u_1"))
    scoped = holding("read:grant", scope=Scope.department(MAINTENANCE))

    assert unplaced.where == {}
    assert people([unplaced], scoped, NOW) == ()
    assert len(people([unplaced], holding("read:grant"), NOW)) == 1


def test_a_reader_whose_grant_names_several_departments_reaches_each_of_them() -> None:
    """Delete this and the narrowing can be written as an equality against one department,
    which works for every fixture in this file and refuses a person who sits in two teams."""
    here = placed_grant(NAME, subject_id="u_1", department=MAINTENANCE)
    there = placed_grant(NAME, subject_id="u_2", department=FINANCE)
    membership = Scope(
        clauses=(Clause(field="department", op=Op.IN, value=(MAINTENANCE, FINANCE)),)
    )
    reader = holding("read:grant", scope=membership)

    assert len(people([here, there], reader, NOW)) == 2


def test_the_row_types_carry_nothing_that_counts_what_was_withheld() -> None:
    """Delete this and a count of the rows a governance screen dropped can be added to any of
    the types a reader is handed, which is the subtraction disclosure the whole console is
    built to refuse."""
    assert govern_gaps(rows=GOVERN_ROWS) == ()
    assert set(GOVERN_ROWS) == {
        govern_module.PersonRow,
        FrictionRow,
        Certification,
        Placed,
    }
