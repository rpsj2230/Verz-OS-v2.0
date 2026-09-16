"""A plane grant counts only over the scope it is held in, measured against the defect that said so.

**What was measured on 2026-09-17.** Wiring an install, an agent granted the first administrator
`read:member.*` and `read:console.content`, both scoped to that person's own things, so that My
workspace would open. It did, and so did the agent Conversations tab and the staff source trial
read, both of which show company content. `brain.console.reads.permitted` asked whether a plane
grant existed and never where it was held, so a content plane held over one person's own things
opened the content plane of every screen whose tool capability that person held over everything.

The first tests below reproduce that reach exactly: `OVERSIGHT` over everything, which is what an
appointment writes, and the two grants the agent added over the person's own things. Each refusal
has a sibling holding the same plane over the scope the screen reads in, because a guard tested
only by its refusals is satisfied by a `permitted` that refuses everybody.

Real `EntitlementSet`s, the real registries and the real deciders throughout: `tab_strip`,
`resolve` and `may_trial` are the functions a route calls, so a test here that passed while the
route still opened the screen would be testing a function nothing serves.

Task ids: M27.5.4
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.console.own_things import own_scope
from brain.console.reads import (
    MEMBER_NOUN,
    ConsoleRead,
    Plane,
    member_plane_capability,
    permitted,
    plane_capability,
    plane_capability_for,
)
from brain.console.screens import SCREENS, navigation
from brain.console.staff_source_view import TRIAL_READ, may_trial
from brain.console.workspace import TABS, Tab, deep_link, resolve, tab, tab_strip
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.first_administrator import OVERSIGHT
from brain.identity.sign_in_binding import MEMBER_SURFACE
from brain.identity.sign_in_binding import own_scope as binding_own_scope
from brain.knowledge.visibility import Visibility
from brain.knowledge.visibility import scope_for as visibility_scope
from brain.member.shell import MEMBER_SCREENS, member_navigation, member_screen, serve

#: Far from any wall clock, for the reason `tests/unit/test_scope_and_capability.py` gives.
NOW = datetime(2999, 1, 1, tzinfo=UTC)

ADMINISTRATOR = "u_first"
AGENT = "support_triage"
MAINTENANCE = Scope.department("maintenance")
FINANCE = Scope.department("finance")

#: The grant the install agent wrote to open My workspace, spelled out rather than derived.
MEMBER_WILDCARD = "read:member.*"
CONSOLE_CONTENT = "read:console.content"


def own_things(principal_id: str = ADMINISTRATOR) -> Scope:
    """What "their own things" meant in the measured grants: the personal visibility scope."""
    return visibility_scope(Visibility.PERSONAL, owner_id=principal_id)


def grants(*capabilities: str, scope: Scope) -> tuple[Grant, ...]:
    return tuple(Grant(capability=Capability(value=one), scope=scope) for one in capabilities)


def reach(*held: tuple[Grant, ...], principal_id: str = ADMINISTRATOR) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id, grants=tuple(one for group in held for one in group)
    )


def measured(content_over: Scope) -> EntitlementSet:
    """The first administrator as measured, with the content plane held over `content_over`."""
    return reach(
        grants(*OVERSIGHT, scope=Scope.unrestricted()),
        grants(MEMBER_WILDCARD, scope=own_things()),
        grants(CONSOLE_CONTENT, scope=content_over),
    )


# ------------------------------------------------------------------- the measured defect
def test_a_content_plane_held_over_ones_own_things_opens_no_conversations_tab() -> None:
    """**The first half of the defect as measured.** The Conversations tab reads `read:question`
    at the content plane; the first administrator holds `read:question` over everything and the
    content plane over their own things, so the tab would show every conversation with the agent.
    Refused through the read, the strip and the deep link, which are the three ways a route asks.

    Delete this and `permitted` can go back to asking whether a plane grant exists anywhere."""
    conversations = tab(Tab.CONVERSATIONS)
    reader = measured(content_over=own_things())

    assert permitted(conversations.read, reader, NOW) is False
    assert tab_strip(reader, populated=[Tab.CONVERSATIONS], now=NOW) == ()
    link = deep_link(AGENT, Tab.CONVERSATIONS)
    landed = resolve(link, reader, visible_agents=[AGENT], populated=[Tab.CONVERSATIONS], now=NOW)
    assert landed is None


def test_the_same_reader_holding_the_content_plane_over_everything_opens_the_tab() -> None:
    """The sibling. The same grants with the content plane over everything, which is the scope
    `read:question` is held in, open the tab on every route. Delete this and the refusal above is
    satisfied by a `permitted` that refuses every content read."""
    conversations = tab(Tab.CONVERSATIONS)
    reader = measured(content_over=Scope.unrestricted())

    assert permitted(conversations.read, reader, NOW) is True
    assert tab_strip(reader, populated=[Tab.CONVERSATIONS], now=NOW) == (conversations,)
    link = deep_link(AGENT, Tab.CONVERSATIONS)
    landed = resolve(link, reader, visible_agents=[AGENT], populated=[Tab.CONVERSATIONS], now=NOW)
    assert landed is not None
    assert landed.tab == conversations


def test_a_content_plane_held_over_ones_own_things_opens_no_staff_source_trial() -> None:
    """**The second half.** The trial names who a staff source would add and who has gone missing,
    which is a statement about people, and `TRIAL_READ` is the Staff sources read at the content
    plane. A source sits nowhere, so its capability is held over everything or not at all, and a
    content plane held over one person's own things must not stand in for one held over that.

    Delete this and the trial opens for anybody trusted with configuration who was also given a
    personal workspace, which is every administrator an install wires up."""
    reader = measured(content_over=own_things())

    assert permitted(TRIAL_READ, reader, NOW) is False
    assert may_trial(reader, NOW) is False


def test_the_same_reader_holding_the_content_plane_over_everything_may_trial_a_source() -> None:
    """The sibling: the content plane over everything opens the trial. Delete this and a
    `may_trial` that refused every reader passes the test above."""
    reader = measured(content_over=Scope.unrestricted())

    assert permitted(TRIAL_READ, reader, NOW) is True
    assert may_trial(reader, NOW) is True


# ------------------------------------------------------------------------- the class
def test_a_plane_held_over_a_department_opens_a_read_held_in_that_department_and_no_wider() -> None:
    """**The rule, rather than the two screens it was found on.** A read is made over the scope
    its tool capability is held in, so a plane counts when it is held over a scope containing that
    one. Maintenance's plane opens Maintenance's read; it does not open a read held in Finance or
    over everything, which is a department's plane standing in for the company's.

    Delete this and the fix can be written for the personal scope alone, and the same defect is
    open to every department head holding a plane over their department."""
    read = tab(Tab.CONVERSATIONS).read

    def holding(question_over: Scope, plane_over: Scope) -> EntitlementSet:
        return reach(
            grants("read:question", scope=question_over),
            grants(CONSOLE_CONTENT, scope=plane_over),
        )

    assert permitted(read, holding(MAINTENANCE, MAINTENANCE), NOW) is True
    assert permitted(read, holding(MAINTENANCE, Scope.unrestricted()), NOW) is True
    assert permitted(read, holding(FINANCE, MAINTENANCE), NOW) is False
    assert permitted(read, holding(Scope.unrestricted(), MAINTENANCE), NOW) is False


def test_a_wider_plane_admits_a_narrower_read_only_over_the_scope_it_is_held_in() -> None:
    """The planes still nest, and the nesting is decided per plane, each over its own scope. A
    content plane held over everything admits a configuration read held over everything even when
    the configuration plane is held over one department; a configuration plane over everything
    never admits a content read, whatever scope the content plane is not held in.

    Delete this and the scope check can be applied to the requested plane only, so a reader whose
    configuration plane is narrow is refused a listing their content plane already discloses."""
    agents = ConsoleRead(
        screen="agents",
        tool="console.agents",
        requires=Capability(value="read:agent"),
        plane=Plane.CONFIGURATION,
    )
    wide_content_narrow_configuration = reach(
        grants("read:agent", scope=Scope.unrestricted()),
        grants(plane_capability(Plane.CONFIGURATION).value, scope=MAINTENANCE),
        grants(plane_capability(Plane.CONTENT).value, scope=Scope.unrestricted()),
    )
    narrow_everything = reach(
        grants("read:agent", scope=Scope.unrestricted()),
        grants(plane_capability(Plane.CONFIGURATION).value, scope=MAINTENANCE),
        grants(plane_capability(Plane.CONTENT).value, scope=MAINTENANCE),
    )

    wide_configuration_narrow_content = reach(
        grants("read:agent", scope=Scope.unrestricted()),
        grants(plane_capability(Plane.CONFIGURATION).value, scope=Scope.unrestricted()),
        grants(plane_capability(Plane.CONTENT).value, scope=MAINTENANCE),
    )
    agent_content = ConsoleRead(
        screen="agents",
        tool="console.agents",
        requires=Capability(value="read:agent"),
        plane=Plane.CONTENT,
    )

    assert permitted(agents, wide_content_narrow_configuration, NOW) is True
    assert permitted(agents, narrow_everything, NOW) is False
    assert permitted(agents, wide_configuration_narrow_content, NOW) is True
    assert permitted(agent_content, wide_configuration_narrow_content, NOW) is False


def test_every_console_screen_refuses_planes_held_over_ones_own_things_and_opens_on_wider() -> None:
    """Over the whole registry rather than two screens. Every screen's own capability held over
    everything and every console plane held over one person's own things opens no screen at all;
    the same planes over everything open every one of them.

    Delete this and a screen whose read is decided somewhere other than `permitted` can keep the
    defect while the two screens it was measured on are fixed."""
    capabilities = sorted({one.read.requires.value for one in SCREENS})
    planes = [plane_capability(one).value for one in Plane]

    narrow = reach(
        grants(*capabilities, scope=Scope.unrestricted()),
        grants(*planes, scope=own_things()),
    )
    wide = reach(
        grants(*capabilities, scope=Scope.unrestricted()),
        grants(*planes, scope=Scope.unrestricted()),
    )

    assert navigation(narrow, NOW) == ()
    assert navigation(wide, NOW) == SCREENS


# ------------------------------------------------------------ the member surface's planes
MEMBER_PLANES: tuple[str, ...] = (
    "read:member.existence",
    "read:member.configuration",
    "read:member.content",
)


def test_the_member_surface_has_three_planes_of_its_own_under_the_member_noun() -> None:
    """Spelled out rather than compared with `member_plane_capability` against itself. Three
    capabilities, none of them the console's, and all of them covered by the member wildcard, so a
    grant of `read:member.*` is the whole member surface as `brain.member.shell` says it is.

    Delete this and the member planes can be renamed into the console namespace, which is the
    coupling that made a content plane the way to open My workspace."""
    assert tuple(member_plane_capability(one).value for one in Plane) == MEMBER_PLANES
    assert not {plane_capability(one).value for one in Plane} & set(MEMBER_PLANES)
    wildcard = Capability(value=MEMBER_WILDCARD)
    assert all(wildcard.covers(Capability(value=one)) for one in MEMBER_PLANES)
    assert MEMBER_NOUN == "member"


def test_a_member_read_is_decided_by_member_planes_and_a_console_read_by_console_planes() -> None:
    """`plane_capability_for` over one read of each surface, at every plane. Delete this and the
    choice can be made by something other than the requirement's noun, which is the one property
    `brain.member.shell` holds both registries to."""
    home = member_screen("home").read
    conversations = tab(Tab.CONVERSATIONS).read

    for plane in Plane:
        assert plane_capability_for(home, plane) == member_plane_capability(plane)
        assert plane_capability_for(conversations, plane) == plane_capability(plane)


def test_a_console_plane_over_everything_opens_no_member_screen() -> None:
    """**Changed on 2026-09-17, and the change is the point.** Every member screen's capability and
    every console plane over everything opened every member screen until that day; it opens none
    now, and the same capabilities with the member planes open every one.

    Delete this and a console content grant goes back to being the way to open a personal page,
    which is how one came to be written over a person's own things."""
    capabilities = [one.read.requires.value for one in MEMBER_SCREENS]
    console_planes = reach(
        grants(*capabilities, scope=Scope.unrestricted()),
        grants(*(plane_capability(one).value for one in Plane), scope=Scope.unrestricted()),
    )
    member_planes = reach(
        grants(*capabilities, scope=Scope.unrestricted()),
        grants(*MEMBER_PLANES, scope=Scope.unrestricted()),
    )

    assert member_navigation(console_planes, NOW) == ()
    assert serve("home", console_planes, NOW) is None
    assert member_navigation(member_planes, NOW) == MEMBER_SCREENS


def test_a_member_plane_over_everything_opens_no_console_screen_tab_or_trial() -> None:
    """The other direction, held over everything so no scope can be what refuses it. Every
    console screen's capability over everything with the member surface over everything opens no
    screen, no tab and no trial; with the console planes instead it opens all three.

    Delete this and a member plane can be admitted for a console read, and binding a sign-in
    becomes a way to reach company content."""
    capabilities = sorted({one.read.requires.value for one in SCREENS})
    member = reach(
        grants(*capabilities, scope=Scope.unrestricted()),
        grants(MEMBER_WILDCARD, *MEMBER_PLANES, scope=Scope.unrestricted()),
    )
    console = reach(
        grants(*capabilities, scope=Scope.unrestricted()),
        grants(*(plane_capability(one).value for one in Plane), scope=Scope.unrestricted()),
    )
    every_tab = [one.tab for one in TABS]

    assert navigation(member, NOW) == ()
    assert tab_strip(member, populated=every_tab, now=NOW) == ()
    assert may_trial(member, NOW) is False
    assert navigation(console, NOW) == SCREENS
    assert tab_strip(console, populated=every_tab, now=NOW) == TABS
    assert may_trial(console, NOW) is True


def test_a_read_cannot_lean_on_a_member_plane_instead_of_a_grant_over_what_it_reads() -> None:
    """`ConsoleRead` refused the console's planes as a requirement and now refuses the member
    surface's too, with a member screen's own capability as the sibling that still builds. Delete
    this and a member screen keyed `content` requires `read:member.content`, and the plane grant
    alone opens it."""
    for plane in MEMBER_PLANES:
        with pytest.raises(ValueError, match="rather than a grant over what it reads"):
            ConsoleRead(
                screen="content",
                tool="member.content",
                requires=Capability(value=plane),
                plane=Plane.CONTENT,
            )

    built = ConsoleRead(
        screen="home",
        tool="member.home",
        requires=Capability(value="read:member.home"),
        plane=Plane.CONTENT,
    )
    assert built.requires.noun == MEMBER_NOUN


# ------------------------------------------------------------------ what a binding grants
def test_the_grant_a_binding_writes_is_the_member_surface_and_nothing_administrative() -> None:
    """`sign_in_binding` must not import the console, so its grant is written out there and held
    here to the two registries: it covers every member screen and every member plane, and no
    console screen's capability and no console plane. Its scope is the same predicate
    `brain.console.own_things` calls a person's own things.

    Delete this and the binding can grant a wider capability, or a scope that is not theirs, with
    every other test in this file still green."""
    assert Capability(value=MEMBER_WILDCARD) == MEMBER_SURFACE
    for member in MEMBER_SCREENS:
        assert MEMBER_SURFACE.covers(member.read.requires), member.key
    assert all(MEMBER_SURFACE.covers(Capability(value=one)) for one in MEMBER_PLANES)
    for console in SCREENS:
        assert not MEMBER_SURFACE.covers(console.read.requires), console.key
    assert not any(MEMBER_SURFACE.covers(plane_capability(one)) for one in Plane)
    assert binding_own_scope("u_joiner") == own_scope("u_joiner")
    assert not binding_own_scope("u_joiner").is_unrestricted()


def test_an_ordinary_person_holding_what_a_binding_writes_opens_their_workspace_alone() -> None:
    """The owner's goal without a database. Exactly the member grant over one's own things opens
    every member screen, and no console screen, no workspace tab and no trial.

    Delete this and the database test below is the only statement of it, and it is skipped on
    every machine without a server."""
    person = reach(
        (Grant(capability=MEMBER_SURFACE, scope=own_scope("u_joiner")),), principal_id="u_joiner"
    )

    assert member_navigation(person, NOW) == MEMBER_SCREENS
    assert navigation(person, NOW) == ()
    assert tab_strip(person, populated=[one.tab for one in TABS], now=NOW) == ()
    assert may_trial(person, NOW) is False


def test_a_first_administrator_given_their_workspace_opens_it_and_still_no_content() -> None:
    """The measured reach with the hand grant of `read:console.content` taken out, which is what an
    appointment and a binding write now. My workspace opens; the Conversations tab, the trial and
    every console screen at the content plane stay shut; every screen whose read an appointment
    grants opens.

    Delete this and giving the first administrator a workspace can quietly reopen the content
    screens, or close the administrative ones, and the install that found this finds it again."""
    administrator = reach(
        grants(*OVERSIGHT, scope=Scope.unrestricted()),
        (Grant(capability=MEMBER_SURFACE, scope=own_scope(ADMINISTRATOR)),),
    )
    opened = {one.key for one in navigation(administrator, NOW)}
    expected = {
        one.key
        for one in SCREENS
        if one.read.plane < Plane.CONTENT and one.read.requires.value in OVERSIGHT
    }

    assert member_navigation(administrator, NOW) == MEMBER_SCREENS
    assert permitted(tab(Tab.CONVERSATIONS).read, administrator, NOW) is False
    assert may_trial(administrator, NOW) is False
    assert expected
    assert opened == expected


# ---------------------------------------------------------------------- the database
#: The subject bound for the ordinary person in the database tests below.
JOINER_SUBJECT = "s-joiner"
JOINER = "u_joiner"
BINDER = "u_admin"


def bound(url: str, subject: str, principal_id: str) -> str:
    """Bind a subject as `BINDER` through the real writer, and say what came of it."""
    from brain.identity.sign_in_binding import sign_in_bindings
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_api_routes import ISSUER
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_setup_wizard import INSIDE

    async def go() -> str:
        engine = app_engine(url)
        try:
            writer = sign_in_bindings(
                make_session_factory(engine), env={"INSTALL_OIDC_ISSUER": ISSUER}
            )
            outcome = await writer.bind(
                subject, principal_id=principal_id, bound_by=BINDER, now=INSIDE
            )
            return outcome.value
        finally:
            await engine.dispose()

    return run(go)


def reconciled(url: str, trace: str) -> tuple[str, ...]:
    from brain.identity.administration_reconciliation import reconcile_member_grants
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_setup_wizard import INSIDE

    async def go() -> tuple[str, ...]:
        engine = app_engine(url)
        try:
            return await reconcile_member_grants(
                make_session_factory(engine), now=INSIDE, trace_id=trace
            )
        finally:
            await engine.dispose()

    return run(go)


def member_rows(url: str, principal_id: str) -> list[tuple[object, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(
        url,
        "SELECT id, scope, granted_by, reason FROM gate.capability_grant"
        " WHERE principal_id = %s AND capability = %s AND deleted_at IS NULL",
        principal_id,
        MEMBER_WILDCARD,
    )


def test_a_freshly_bound_ordinary_person_opens_my_workspace_and_no_administrative_screen() -> None:
    """**The owner's goal, end to end on PostgreSQL.** A live person holding nothing is bound to a
    sign-in by somebody else. Their reach, read back through the one resolver, holds the member
    surface over their own things under the id derived from the binding, the grant trigger records
    it under the binder, and that reach opens every member screen, My workspace first, and no
    console screen, no workspace tab and no trial.

    Delete this and binding can stop granting anything, grant it under another author or scope, or
    grant something wider, and every pure test above still passes."""
    from brain.identity.sign_in_binding import MEMBER_GRANT_REASON, member_grant_id
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_principal
    from tests.unit.test_first_administrator import audited, reach_of
    from tests.unit.test_setup_wizard import INSIDE

    with audited("brain_plane_bound") as url:
        a_principal(url, JOINER)
        outcome = bound(url, JOINER_SUBJECT, JOINER)
        [(binding_id,)] = sql(
            url,
            "SELECT id FROM auth.principal_identity WHERE principal_id = %s AND deleted_at IS NULL",
            JOINER,
        )
        rows = member_rows(url, JOINER)
        entries = sql(
            url,
            "SELECT actor_id FROM obs.audit_entry"
            " WHERE action = 'grant' AND subject = %s AND details ->> 'capability' = %s",
            f"grant:{member_grant_id(binding_id)}",
            MEMBER_WILDCARD,
        )
        person = reach_of(url, JOINER)

    assert outcome == "bound"
    [(grant_id, scope, granted_by, reason)] = rows
    assert grant_id == member_grant_id(binding_id)
    assert Scope.model_validate(scope) == own_scope(JOINER)
    assert (granted_by, reason) == (BINDER, MEMBER_GRANT_REASON)
    assert entries == [(BINDER,)]
    assert person.scope_for(MEMBER_SURFACE, INSIDE) == own_scope(JOINER)
    assert permitted(member_screen("home").read, person, INSIDE) is True
    assert member_navigation(person, INSIDE) == MEMBER_SCREENS
    assert navigation(person, INSIDE) == ()
    assert all(permitted(one.read, person, INSIDE) is False for one in TABS)
    assert may_trial(person, INSIDE) is False


def test_a_member_grant_taken_away_is_not_given_back_by_a_retry_or_a_start_for_that_binding() -> (
    None
):
    """See `A_MEMBER_GRANT_TAKEN_AWAY_IS_NOT_GIVEN_BACK_FOR_THE_SAME_BINDING`, against the real
    policy that hides the retired row. The member grant is revoked; a retry of the same binding and
    a start both write nothing; a new binding after the old one is retired is a new grant.

    Delete this and the id can stop being derived from the binding, and a revocation of somebody's
    workspace lasts until the next restart."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_principal
    from tests.unit.test_first_administrator import audited

    with audited("brain_plane_revoked") as url:
        a_principal(url, JOINER)
        assert bound(url, JOINER_SUBJECT, JOINER) == "bound"
        sql(
            url,
            "UPDATE gate.capability_grant SET deleted_at = now()"
            " WHERE principal_id = %s AND capability = %s",
            JOINER,
            MEMBER_WILDCARD,
        )
        retried = bound(url, JOINER_SUBJECT, JOINER)
        started = reconciled(url, "startup.reconcile.revoked")
        after_revocation = member_rows(url, JOINER)
        sql(
            url,
            "UPDATE auth.principal_identity SET deleted_at = now() WHERE principal_id = %s",
            JOINER,
        )
        rebound = bound(url, "s-joiner-again", JOINER)
        after_rebinding = member_rows(url, JOINER)

    assert (retried, started, after_revocation) == ("already_bound", (), [])
    assert rebound == "bound"
    assert len(after_rebinding) == 1


def test_a_binding_made_before_bindings_granted_a_workspace_is_granted_one_at_a_start_once() -> (
    None
):
    """**Reconciling existing bindings.** A binding whose member grant was never written, which is
    every binding before this release and is made here by removing the row the writer now adds, is
    granted it at the next start, attributed to the start with a reason of its own under the start's
    trace, and a second start grants nothing. A principal already holding a live member grant of
    their own keeps it, a principal no longer live is not granted anything, and neither is one whose
    only binding was retired before the start.

    Delete this and the first administrator on every existing install keeps a workspace that
    refuses them, and the grant written by hand to get round that is the one that opened company
    content."""
    from brain.identity.administration_reconciliation import (
        MEMBER_RECONCILED_BY,
        MEMBER_RECONCILED_REASON,
    )
    from brain.identity.sign_in_binding import member_grant_id
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_grant, a_principal
    from tests.unit.test_first_administrator import audited

    with audited("brain_plane_reconciled") as url:
        for principal_id, subject in (
            (JOINER, JOINER_SUBJECT),
            ("u_holder", "s-holder"),
            ("u_leaver", "s-leaver"),
            ("u_unlinked", "s-unlinked"),
        ):
            a_principal(url, principal_id)
            assert bound(url, subject, principal_id) == "bound"
        # Removed as the owner the fixture connects as, so the bindings look as a binding made
        # before this release does: bound, and holding no member grant.
        sql(url, "DELETE FROM gate.capability_grant WHERE capability = %s", MEMBER_WILDCARD)
        a_grant(url, "u_holder", MEMBER_WILDCARD)
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = 'u_leaver'")
        sql(
            url,
            "UPDATE auth.principal_identity SET deleted_at = now()"
            " WHERE principal_id = 'u_unlinked'",
        )
        first = reconciled(url, "startup.reconcile.first")
        second = reconciled(url, "startup.reconcile.second")
        [(binding_id,)] = sql(
            url,
            "SELECT id FROM auth.principal_identity WHERE principal_id = %s AND deleted_at IS NULL",
            JOINER,
        )
        joiner = member_rows(url, JOINER)
        holder = member_rows(url, "u_holder")
        leaver = member_rows(url, "u_leaver")
        unlinked = member_rows(url, "u_unlinked")
        entries = sql(
            url,
            "SELECT actor_id, trace_id FROM obs.audit_entry"
            " WHERE action = 'grant' AND subject = %s ORDER BY seq",
            f"grant:{member_grant_id(binding_id)}",
        )

    assert (first, second) == ((JOINER,), ())
    [(grant_id, scope, granted_by, reason)] = joiner
    assert grant_id == member_grant_id(binding_id)
    assert Scope.model_validate(scope) == own_scope(JOINER)
    assert (granted_by, reason) == (MEMBER_RECONCILED_BY, MEMBER_RECONCILED_REASON)
    # The first entry is the binder's, for the row removed above to stand in for a binding made
    # before this release; the ledger keeps it, which a real one of those would not have.
    assert [actor for actor, _ in entries] == [BINDER, MEMBER_RECONCILED_BY]
    assert entries[-1] == (MEMBER_RECONCILED_BY, "startup.reconcile.first")
    [(_, holder_scope, holder_by, _)] = holder
    assert Scope.model_validate(holder_scope).is_unrestricted()
    assert holder_by == "u_seed"
    assert leaver == []
    assert unlinked == []


def test_every_start_asks_for_the_member_grants_to_be_reconciled() -> None:
    """A reconciliation nothing calls is a control that is correct, documented and never run, which
    is the shape this repository keeps finding. Read off the lifespan's own source as a call, so a
    comment naming the function cannot satisfy it.

    Delete this and the call can be dropped from the start, and every binding made before this
    release keeps a workspace that refuses its person."""
    import ast
    import inspect

    from brain import app as application

    tree = ast.parse(inspect.getsource(application.lifespan))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "reconcile_first_administrators" in called, "the lifespan was not what was read"
    assert "reconcile_member_grants" in called
