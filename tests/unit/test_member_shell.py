"""Getting into the member application, and the claim that it cannot reach a governance one.

The file is written around one property and the rest follows from it. **A member router
resolves to a member screen or to nothing, whatever is typed at it** (M40.1.2.2), and the
test that says so is driven from `brain.console.screens.SCREENS` rather than from a list of
paths written here, so it covers the thirty-fifth console screen the day somebody adds one.
The entitlement it uses holds every capability every console screen requires and all three
plane capabilities, which makes it the strongest form of the claim: somebody holding every
administrative grant in the system still gets `None` from the member router.

Around that sit the three refusals `MemberScreen` makes at construction, the agreement
between the menu and the router (M40.1.2.1, M40.1.2.2), the sign-in path that has no
directory of its own (M40.1.1.1, M40.1.1.2), the session policy and the device list with the
control that refuses somebody else's session (M40.1.1.3), the absence of anywhere to put a
credential (M40.1.1.4), and the entitlement line computed from the grants (M40.1.2.4).

M40.1.1.5 is a test rather than a function, and it is the one below about a person who has
only ever used a chat channel: they sign in on the web, both routes resolve to one principal,
and the entitlement resolved for each is the same set.

Real `Session`s through a real `SessionRegistry`, real `EntitlementSet`s, real `Screen`s from
the console registry. The directory is a dictionary behind the protocol, which is what that
protocol is for.

Task ids: M40.1.1.1, M40.1.1.2, M40.1.1.3, M40.1.1.4, M40.1.1.5
Task ids: M40.1.2.1, M40.1.2.2, M40.1.2.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType

import pytest

from brain.console.reads import ConsoleRead, Plane, plane_capability
from brain.console.screens import SCREENS, Axis, Group, Screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.ingress import Binding
from brain.identity.oidc import UnmappedSubject, VerifiedClaims
from brain.identity.roles import Role
from brain.identity.sessions import (
    SESSION_ABSOLUTE_MAX,
    SESSION_IDLE,
    Session,
    SessionRegistry,
)
from brain.member.shell import (
    DISCLOSURE_PREFIX,
    IDLE_TIMEOUT,
    MAXIMUM_SESSION,
    MEMBER_SCREEN_COUNT,
    MEMBER_SCREENS,
    MEMBER_SURFACE,
    MEMBER_TYPES,
    NOTHING_DISCLOSED_YET,
    SESSION_POLICY_SENTENCE,
    Device,
    MemberScreen,
    MemberShellError,
    RecoveryHandoff,
    bound_channels,
    boundary_gaps,
    credential_gaps,
    devices,
    disclosure_gaps,
    disclosure_line,
    end_device,
    member_capability,
    member_navigation,
    member_screen,
    menu_and_route_agree,
    one_principal,
    recovery_handoff,
    router_gaps,
    serve,
    shell_gaps,
    sign_in,
)

#: A fixed moment, so a window test cannot pass because the machine's clock sat on the
#: convenient side of a boundary.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

ME = "u_me"
THEM = "u_them"
ISSUER = "https://id.example.test/realms/brain"

#: An opaque identity-provider subject. Deliberately nothing like the principal id, because
#: the property under test is that the principal comes from the directory and not the token.
MY_SUBJECT = "1f2e3d4c-0000-4000-8000-000000000001"


# ------------------------------------------------------------------------- fixtures
class Directory:
    """A dictionary behind `PrincipalDirectory`, keyed the way the real one is."""

    def __init__(self, rows: dict[tuple[str, str], Principal]) -> None:
        self._rows = rows

    def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        return self._rows.get((issuer, subject))


def person(principal_id: str = ME) -> Principal:
    return Principal(
        id=principal_id,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="A Member",
        primary_department="maintenance",
    )


def claims(*, subject: str = MY_SUBJECT, session_id: str | None = "sid-me") -> VerifiedClaims:
    return VerifiedClaims(
        issuer=ISSUER,
        subject=subject,
        audience=("brain",),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        session_id=session_id,
        key_id="kid-1",
        algorithm="RS256",
        verified_at=NOW,
        claims=MappingProxyType({}),
    )


def directory(principal_id: str = ME) -> Directory:
    return Directory({(ISSUER, MY_SUBJECT): person(principal_id)})


def entitlement(*values: str, principal_id: str = ME) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted()) for one in values
        ),
    )


#: Every plane, so a screen is never refused for want of one when the point is the capability.
ALL_PLANES: tuple[str, ...] = tuple(plane_capability(one).value for one in Plane)


def every_member_grant(principal_id: str = ME) -> EntitlementSet:
    return entitlement(
        *(one.read.requires.value for one in MEMBER_SCREENS),
        *ALL_PLANES,
        principal_id=principal_id,
    )


def every_console_grant(principal_id: str = ME) -> EntitlementSet:
    """Every capability every governance screen is gated on, plus all three planes.

    This is the entitlement of somebody who administers the whole installation, and the
    routing test below hands it to the member router on purpose: a boundary that only holds
    for people with nothing is not a boundary.
    """
    return entitlement(
        *sorted({one.read.requires.value for one in SCREENS}),
        *ALL_PLANES,
        principal_id=principal_id,
    )


def session_for(principal_id: str, *, session_id: str, opened: datetime = NOW) -> Session:
    return Session(
        session_id=session_id,
        principal_id=principal_id,
        issuer=ISSUER,
        subject=MY_SUBJECT,
        opened_at=opened,
        expires_at=opened + SESSION_IDLE,
        absolute_expiry=opened + SESSION_ABSOLUTE_MAX,
    )


def binding_for(principal_id: str, channel: Channel = Channel.LARK) -> Binding:
    return Binding(
        channel=channel,
        identity_hash="0" * 64,
        principal_id=principal_id,
        bound_at=NOW - timedelta(days=30),
    )


def governance_screen(key: str, *, capability: str, tool: str = "console.made_up") -> Screen:
    """A console screen built for a test, so the disjointness checks have something to find.

    Constructed rather than taken from `SCREENS`, because the interesting input to
    `boundary_gaps` is a console registry that collides with the member one, and no such
    registry exists in the tree today. That is the whole reason the function takes both.
    """
    return Screen(
        key=key,
        title="Made up",
        group=Group.GOVERN,
        read=ConsoleRead(
            screen=key,
            tool=tool,
            requires=Capability(value=capability),
            plane=Plane.CONFIGURATION,
        ),
        axes=frozenset({Axis.DEPARTMENT, Axis.PERSON}),
        intended_for=frozenset({Role.SUPER_ADMIN}),
        purpose="A screen invented for a test.",
    )


# ------------------------------------------------- M40.1.2.2 the boundary, exhaustively
def test_no_console_screen_is_reachable_through_the_member_router() -> None:
    """**The leaf, driven from the console registry rather than from a list of paths.**

    Every key in `SCREENS` is offered to `serve` by somebody holding every capability every
    governance screen requires and all three planes, which is the administrator of the whole
    installation. Every one comes back `None`, because the member registry has nothing to
    resolve those paths to and `serve` cannot see any other registry.

    Driven from `SCREENS` on purpose: a test listing `people`, `roles`, `audit` would be
    correct today and silently incomplete the next time a screen is added, which is the
    failure `A_LIST_OF_FORBIDDEN_PATHS_IS_ONE_ROUTE_AWAY_FROM_BEING_INCOMPLETE` names.

    Delete this and the member router can grow a fallthrough, a prefix match or a second
    registry, and every other test in this file still passes."""
    administrator = every_console_grant()

    assert len(SCREENS) > 30, "the console registry was not read, so the loop proves nothing"
    for one in SCREENS:
        assert serve(one.key, administrator, NOW) is None, one.key


def test_the_member_router_still_serves_its_own_screens_to_somebody_who_holds_them() -> None:
    """The positive half, without which the test above is satisfied by a `serve` that returns
    `None` for everything.

    Delete this and the boundary can be enforced by a router that works for nobody."""
    member = every_member_grant()

    served = [one.key for one in MEMBER_SCREENS if serve(one.key, member, NOW) is not None]

    assert served == [one.key for one in MEMBER_SCREENS]


def test_a_member_screen_cannot_take_a_console_screens_key() -> None:
    """**Found by the guard before a test existed.** The first version of the registry named
    its screens `approvals`, `connections` and `sessions`, which are all console keys, and the
    module failed to import.

    Refused at construction rather than reported by a diagnostic, because a diagnostic runs
    when somebody calls it and a constructor runs whenever the registry is built.

    Delete this and one path resolves to two different screens depending on which application
    happens to be mounted."""
    with pytest.raises(ValueError, match="console screen key"):
        MemberScreen(
            key="approvals",
            title="Waiting",
            read=ConsoleRead(
                screen="approvals",
                tool="member.approvals",
                requires=member_capability("approvals"),
                plane=Plane.CONTENT,
            ),
            purpose="A member screen taking a console key.",
        )


def test_a_member_screen_cannot_read_through_a_tool_a_console_screen_uses() -> None:
    """A distinct key with the same tool behind it is the same call with two names in front
    of it, and the audit row would name whichever screen was asked first.

    Delete this and the two registries can be disjoint by key and identical by data path."""
    with pytest.raises(ValueError, match="console screen"):
        MemberScreen(
            key="home",
            title="Home",
            read=ConsoleRead(
                screen="home",
                tool="console.people",
                requires=member_capability("home"),
                plane=Plane.CONTENT,
            ),
            purpose="A member screen reading through a governance tool.",
        )


def test_a_member_screen_cannot_be_gated_on_a_capability_a_console_screen_is_gated_on() -> None:
    """**The definition of administrative, enforced.** A screen requiring `read:grant` is an
    administrative surface however it is titled, because the grant that opens it is the grant
    that opens the console's own people screen.

    Delete this and a member surface can be built out of governance capabilities, which is
    the boundary defeated without any path colliding at all."""
    with pytest.raises(ValueError, match="which gates the console screen people"):
        MemberScreen(
            key="home",
            title="Home",
            read=ConsoleRead(
                screen="home",
                tool="member.home",
                requires=Capability(value="read:grant"),
                plane=Plane.CONTENT,
            ),
            purpose="A member screen gated on a governance capability.",
        )


def test_a_member_screen_must_be_gated_on_a_capability_in_the_member_noun() -> None:
    """**A mutation moved this test and reordered the module.** The capability check above
    used a capability the console also requires, so with the noun check running first, that
    check refused the input and the collision branch below it could not be reached by
    anything: switching it off changed no test.

    This one uses a capability no console screen requires, which is the only input the noun
    check refuses on its own. Between the two, each guard has an input only it catches.

    Delete this and a member screen can be gated on any capability at all, as long as no
    console screen happens to use it, which is the boundary reduced to a coincidence."""
    with pytest.raises(ValueError, match="not 'member'"):
        MemberScreen(
            key="home",
            title="Home",
            read=ConsoleRead(
                screen="home",
                tool="member.home",
                requires=Capability(value="read:unicorn"),
                plane=Plane.CONTENT,
            ),
            purpose="A member screen gated on a capability outside the member noun.",
        )


def test_a_member_screen_needs_a_key_a_title_and_a_purpose_that_are_not_whitespace() -> None:
    """A space is what a form field sends when somebody fills nothing in, and `" "` passes
    every bare falsiness check. All three are tested with a space rather than with an empty
    string, because the empty string is the case somebody remembers.

    Delete this and a screen with a blank title reaches the menu as an empty row that still
    resolves and still serves."""
    for field in ("key", "title", "purpose"):
        values = {"key": "home", "title": "Home", "purpose": "Why."}
        values[field] = " "
        with pytest.raises(ValueError, match=r"no key|no title|no purpose"):
            MemberScreen(
                key=values["key"],
                title=values["title"],
                read=ConsoleRead(
                    screen=values["key"],
                    tool="member.home",
                    requires=member_capability("home"),
                    plane=Plane.CONTENT,
                ),
                purpose=values["purpose"],
            )


def test_a_screen_wired_to_a_read_that_audits_a_different_screen_is_refused() -> None:
    """The audit row would name a screen nobody can navigate to, so the trail of who opened
    what stops matching the application.

    Delete this and a copied registry entry keeps the read of the one it was copied from."""
    with pytest.raises(ValueError, match="audits itself"):
        MemberScreen(
            key="home",
            title="Home",
            read=ConsoleRead(
                screen="envelopes",
                tool="member.home",
                requires=member_capability("home"),
                plane=Plane.CONTENT,
            ),
            purpose="A screen whose read names another screen.",
        )


def test_a_path_naming_nothing_and_a_screen_this_person_may_not_open_answer_identically() -> None:
    """DENIED equals ABSENT at the router. A member holding nothing gets the same answer for
    a real member screen as for a path that names nothing at all, so the surface cannot be
    mapped by typing at it.

    Delete this and `serve` can grow a not-found that differs from a forbidden, which is an
    enumeration of the member application for anybody with a browser."""
    holds_nothing = entitlement()

    assert serve("home", holds_nothing, NOW) is None
    assert serve("nothing_like_a_screen", holds_nothing, NOW) is None
    assert serve("nothing_like_a_screen", every_member_grant(), NOW) is None


def test_the_menu_and_the_router_never_disagree_about_a_member_screen() -> None:
    """Both directions, over a partial entitlement so that the two answers are not both yes.

    The direction that matters is a screen the menu hides and the router serves, which is
    the whole meaning of "enforced server side": if hiding it from the menu were the
    enforcement, this would be the state nobody could detect.

    Delete this and `member_navigation` and `serve` can be given different predicates by two
    people editing the same file a week apart."""
    partial = entitlement(
        MEMBER_SCREENS[0].read.requires.value,
        plane_capability(Plane.CONTENT).value,
    )

    assert menu_and_route_agree(partial, NOW) == ()
    offered = {one.key for one in member_navigation(partial, NOW)}
    assert offered == {MEMBER_SCREENS[0].key}
    for one in MEMBER_SCREENS:
        assert (serve(one.key, partial, NOW) is not None) == (one.key in offered)


def test_the_agreement_check_reports_a_menu_and_a_router_that_do_disagree() -> None:
    """**The test for the test, and it changed the function.** The first version of
    `menu_and_route_agree` read this module's own `member_navigation` and `serve`, which
    agree by construction, so neither of its branches could ever fire and switching either
    off changed nothing observable.

    Both directions are constructed here. A router that serves what the menu hides is the
    defect the leaf is about; a menu offering what the router refuses is the visible half.

    Delete this and the diagnostic goes back to being a pair of unreachable branches that
    read like a check."""
    holds_nothing = entitlement()

    serves_everything = menu_and_route_agree(
        holds_nothing,
        NOW,
        route=lambda key, *_: member_screen(key),
    )
    offers_everything = menu_and_route_agree(
        every_member_grant(),
        NOW,
        menu=lambda *_: MEMBER_SCREENS,
        route=lambda *_: None,
    )

    assert any("menu is decorative" in one for one in serves_everything)
    assert any("broken application" in one for one in offers_everything)


def test_the_router_shape_check_reports_a_route_that_could_resolve_anything() -> None:
    """`router_gaps` exercised against a function that breaks both of its rules, so the
    clean answer for `serve` is not the answer of a check that always returns empty.

    The return annotation is the one worth constructing: a router typed to return a console
    screen as well as a member one is how a single router comes to serve both, and no test
    that only calls `serve` would notice.

    Delete this and the two shape checks are asserted only against a function that satisfies
    them, which proves nothing about the checks."""

    def loose(path: str, entitlement: EntitlementSet, registry: object = None) -> object:
        return registry or path or entitlement

    found = router_gaps(loose)

    assert any("rather than MemberScreen | None" in one for one in found)
    assert any("takes registry" in one for one in found)
    assert router_gaps(serve) == ()


def test_boundary_gaps_reports_a_console_registry_that_collides_with_the_member_one() -> None:
    """The diagnostic exercised against a broken input, which is the only state it has
    anything to say about.

    Three collisions, one per rule: a console screen taking a member key, one taking a member
    tool, and one gated on a member capability. The third is the one worth constructing,
    because it is the direction the constructor cannot refuse: `MemberScreen` checks itself
    against the console registry, and nothing stops the console taking the member namespace.

    Delete this and `boundary_gaps` is only ever called on a healthy tree, where switching
    off any of its refusals changes nothing observable."""
    collides = (
        governance_screen("home", capability="read:grant", tool="console.home"),
        governance_screen("elsewhere", capability="read:role", tool="member.home"),
        governance_screen("also", capability="read:member.home", tool="console.also"),
    )

    found = boundary_gaps(MEMBER_SCREENS, collides)

    assert any("console screen key" in one for one in found)
    assert any("which a console screen uses" in one for one in found)
    assert any("member noun no longer tells" in one for one in found)


def test_a_member_registry_the_size_of_the_console_is_reported() -> None:
    """M40.1.2.1's "much shorter" as a boundary property rather than as taste. A member
    surface with as many screens as the console has grown governance screens, whatever the
    keys say.

    Delete this and the registry can grow to thirty-four entries one at a time."""
    found = boundary_gaps(MEMBER_SCREENS, SCREENS[:3])

    assert any("has grown governance screens" in one for one in found)


def test_the_member_application_ships_with_no_gaps_at_all() -> None:
    """The deployment check, and the one every constant above is really asserted through: a
    mutation to `ONLY_A_MEMBER_SCREEN`, to `MEMBER_CAPABILITY_NOUN` or to the parameter list
    makes this fail, because those are read rather than compared against themselves.

    Delete this and the diagnostics exist and nothing runs them."""
    assert shell_gaps(every_member_grant()) == ()


# -------------------------------------------------- M40.1.2.1 shorter, and shares nothing
def test_the_member_menu_is_much_shorter_than_the_console_and_shares_no_screen_with_it() -> None:
    """The count is related to the console registry rather than to itself, which is the
    discipline CLAUDE.md records: a test asserting `MEMBER_SCREEN_COUNT == len(MEMBER_SCREENS)`
    is green for every value the constant could hold.

    Delete this and the two registries can converge until the member application is the
    console with a different stylesheet."""
    assert len(MEMBER_SCREENS) == MEMBER_SCREEN_COUNT
    assert len(SCREENS) >= MEMBER_SCREEN_COUNT * 4
    assert {one.key for one in MEMBER_SCREENS} & {one.key for one in SCREENS} == set()
    assert {one.read.tool for one in MEMBER_SCREENS} & {one.read.tool for one in SCREENS} == set()


def test_a_member_screen_is_found_by_key_and_an_unknown_one_is_a_failure() -> None:
    """The lookup, and the refusal beside it, so a caller asking for a screen that does not
    exist finds out rather than receiving something plausible.

    Delete this and `member_screen` can return the first entry for any key."""
    assert member_screen("home").key == "home"
    with pytest.raises(KeyError, match="no member screen"):
        member_screen("people")


# ------------------------------------------------------ M40.1.1.1 and M40.1.1.2 signing in
def test_a_member_signs_in_as_the_principal_the_directory_names_and_never_as_the_token() -> None:
    """**The property every identity claim in this module rests on.** The subject on the
    token is an opaque provider identifier and the principal id is this company's, and the
    session that comes back carries the second.

    Without it, a member application that keyed on `sub` would create a second identity for
    the same person, and every "their own" surface would show them nothing.

    Delete this and the sign-in can assemble a principal out of claims, which
    `principal_for` exists to refuse."""
    signed = sign_in(claims(), directory(), now=NOW)

    assert not isinstance(signed, UnmappedSubject)
    assert signed.principal_id == ME
    assert signed.principal_id != MY_SUBJECT
    assert signed.session.principal_id == ME
    assert signed.session.subject == MY_SUBJECT


def test_a_valid_token_for_somebody_nobody_has_onboarded_opens_no_session() -> None:
    """A real person with a real token who is not on file is a normal event, and the wrong
    answer is a session for an empty principal.

    Delete this and a stranger with a valid token holds a live session with an unmapped
    identity behind it."""
    signed = sign_in(claims(subject="somebody-else"), directory(), now=NOW)

    assert isinstance(signed, UnmappedSubject)
    assert signed.subject == "somebody-else"
    assert signed.prompt


def test_a_sign_in_naming_one_principal_cannot_carry_another_persons_session() -> None:
    """The audit trail and the session would disagree about who is here, and every row
    written under the sign-in would be filed against the wrong person.

    Delete this and a `MemberSignIn` assembled by hand from two half-right values passes."""
    from brain.member.shell import MemberSignIn

    with pytest.raises(ValueError, match="disagree about who is here"):
        MemberSignIn(principal_id=THEM, session=session_for(ME, session_id="sid-me"))


def test_a_binding_naming_another_principal_is_refused_rather_than_resolved() -> None:
    """M40.1.1.2. The two readings are a takeover and a mistake, they are indistinguishable
    from here, and picking either silently is how the wrong one goes unnoticed.

    Delete this and a chat account bound to somebody else resolves quietly to whichever of
    the two identities the code happened to read first."""
    signed = sign_in(claims(), directory(), now=NOW)
    assert not isinstance(signed, UnmappedSubject)

    with pytest.raises(MemberShellError, match="different principal"):
        one_principal(signed, binding_for(THEM))


def test_the_web_and_the_channel_resolve_to_the_one_principal() -> None:
    """The positive half, without which the refusal above is satisfied by a function that
    refuses everything.

    Delete this and `one_principal` can raise unconditionally."""
    signed = sign_in(claims(), directory(), now=NOW)
    assert not isinstance(signed, UnmappedSubject)

    assert one_principal(signed, binding_for(ME)) == ME


def test_the_channel_list_holds_only_this_persons_bindings_and_no_duplicates() -> None:
    """A member's own page listing somebody else's bound channel is a disclosure about that
    person, and a channel listed twice is a revoked binding the caller handed in.

    Delete this and the reachability page shows the company's Lark accounts."""
    bindings = (
        binding_for(ME, Channel.LARK),
        binding_for(THEM, Channel.EMAIL),
        binding_for(ME, Channel.LARK),
        binding_for(ME, Channel.EMAIL),
    )

    assert bound_channels(ME, bindings) == (Channel.LARK, Channel.EMAIL)
    assert bound_channels(THEM, bindings) == (Channel.EMAIL,)


# --------------------------------------------- M40.1.1.5 a channel-only person signs in
def test_a_channel_only_person_signs_in_on_the_web_and_holds_the_same_entitlement() -> None:
    """**The leaf, which is a test and not a function** (M40.1.1.5).

    Somebody whose only contact with the system has been a chat channel signs in on the web
    for the first time. The binding names a principal; the sign-in resolves a principal
    through the directory; `one_principal` agrees they are one. The entitlement store is
    keyed on that id and nothing else, so the reach the web sees is the identical set, hash
    included.

    The hash is compared rather than the grants, because `ent_hash` is what the answer cache
    and the audit trail key on: two sets that hash differently are two people as far as
    everything downstream is concerned, whatever their grants look like.

    Delete this and the two routes can drift into two identities, which shows up as a
    long-standing chat user signing in on the web and finding an empty account."""
    only_ever_on_lark = binding_for(ME, Channel.LARK)
    store = {ME: entitlement("read:client.name", "read:ticket.status")}

    reach_on_the_channel = store[only_ever_on_lark.principal_id]

    signed = sign_in(claims(), directory(), now=NOW)
    assert not isinstance(signed, UnmappedSubject)
    reach_on_the_web = store[one_principal(signed, only_ever_on_lark)]

    assert reach_on_the_web.ent_hash() == reach_on_the_channel.ent_hash()
    assert reach_on_the_web.grants == reach_on_the_channel.grants


# --------------------------------------------- M40.1.1.3 session policy and the device list
def test_the_member_session_policy_is_the_identity_packages_own_windows() -> None:
    """Related to the constants they come from rather than to the numbers in the sentence,
    which is the trap CLAUDE.md records: a test asserting the sentence says thirty minutes
    stays green after somebody changes the window to sixty.

    Delete this and the member console acquires a session policy of its own, which is the
    one people actually use."""
    assert IDLE_TIMEOUT is SESSION_IDLE
    assert MAXIMUM_SESSION is SESSION_ABSOLUTE_MAX
    assert str(int(SESSION_IDLE.total_seconds() // 60)) in SESSION_POLICY_SENTENCE
    assert str(int(SESSION_ABSOLUTE_MAX.total_seconds() // 3600)) in SESSION_POLICY_SENTENCE


def test_a_device_list_shows_this_persons_live_sessions_newest_first() -> None:
    """Newest first because the list is read to find the sign-in you do not recognise, and
    only this person's because a device list is a list of somewhere somebody is.

    Delete this and the page shows the company's open sessions in whatever order a
    dictionary happened to hold them."""
    registry = SessionRegistry()
    registry.register(session_for(ME, session_id="sid-old", opened=NOW - timedelta(minutes=20)))
    registry.register(session_for(ME, session_id="sid-new", opened=NOW - timedelta(minutes=1)))
    registry.register(session_for(THEM, session_id="sid-them", opened=NOW))

    found = devices(registry, principal_id=ME, now=NOW, current_session_id="sid-new")

    assert [one.session_id for one in found] == ["sid-new", "sid-old"]
    assert [one.is_this_one for one in found] == [True, False]
    assert all(isinstance(one, Device) for one in found)


def test_a_device_carries_no_address_and_no_location() -> None:
    """A device list grows those fields first, and each is a fact about somebody's
    whereabouts on a page anybody borrowing an unlocked laptop can read.

    Delete this and the next person to make the list friendlier adds an IP column."""
    named = set(Device.__dataclass_fields__)

    assert named == {
        "session_id",
        "opened_at",
        "idle_expires_at",
        "absolute_expiry",
        "second_factor",
        "is_this_one",
    }


def test_a_member_cannot_end_a_device_belonging_to_somebody_else() -> None:
    """**The guard that does not exist in the registry.** `SessionRegistry.end_session` takes
    an id and ends whatever it names, which is right for an administrator and wrong for a
    form on a member's own page.

    The assertion is on the effect and not on the message, because both refusals here carry
    the same words on purpose: a member typing somebody else's session id must not learn from
    the wording whether it exists.

    Delete this and a member with a colleague's session id signs that colleague out."""
    registry = SessionRegistry()
    registry.register(session_for(THEM, session_id="sid-them"))

    with pytest.raises(MemberShellError):
        end_device(registry, principal_id=ME, session_id="sid-them", now=NOW)

    still_there = registry.get("sid-them")
    assert still_there is not None
    assert still_there.is_live(NOW)


def test_ending_a_device_that_does_not_exist_says_what_ending_somebody_elses_says() -> None:
    """The other half of the disclosure decision. Two different sentences would turn the
    control into a service that answers whether a session id is real.

    Delete this and the refusals can diverge, which nothing else in this file would notice."""
    registry = SessionRegistry()
    registry.register(session_for(THEM, session_id="sid-them"))

    with pytest.raises(MemberShellError) as absent:
        end_device(registry, principal_id=ME, session_id="sid-nothing", now=NOW)
    with pytest.raises(MemberShellError) as denied:
        end_device(registry, principal_id=ME, session_id="sid-them", now=NOW)

    assert str(absent.value) == str(denied.value)


def test_a_member_can_end_their_own_device_and_it_stops_being_live() -> None:
    """The positive half. A guard tested only by its refusals is satisfied by a function that
    refuses everything, and this control's whole purpose is the stolen laptop.

    Delete this and `end_device` can be made to raise unconditionally."""
    registry = SessionRegistry()
    registry.register(session_for(ME, session_id="sid-me"))

    ended = end_device(registry, principal_id=ME, session_id="sid-me", now=NOW)

    assert ended.session_id == "sid-me"
    assert registry.get("sid-me") is None
    assert devices(registry, principal_id=ME, now=NOW) == ()


# ---------------------------------------------------- M40.1.1.4 recovery is the provider's
def test_nothing_in_the_member_surface_takes_or_stores_a_credential() -> None:
    """The whole of the leaf, stated as an absence that a check can read.

    Delete this and a helpful password field arrives on the member profile, and the module
    docstring saying recovery is the provider's remains true and stops describing the code."""
    assert credential_gaps(MEMBER_SURFACE, MEMBER_TYPES) == ()


def test_the_credential_check_finds_a_parameter_and_a_field_it_should_refuse() -> None:
    """The test for the test. `credential_gaps` asserted over a healthy surface proves
    nothing about a check that always answers empty, which is the shape that has produced
    almost every surviving mutation in this repository.

    Both halves, because they fail differently: a function taking a password is somebody
    adding a reset endpoint, and a type with a `secret` field is somebody storing what a form
    posted.

    Delete this and the check above can be satisfied by a function that returns `()`."""
    from dataclasses import dataclass

    def reset(*, password: str) -> str:
        return password

    @dataclass(frozen=True)
    class Stored:
        reset_token: str

    found = credential_gaps((reset,), (Stored,))

    assert any("takes password" in one for one in found)
    assert any("reset_token field" in one for one in found)


def test_the_credential_check_says_so_when_it_was_handed_something_it_cannot_read() -> None:
    """A type whose fields cannot be listed is reported rather than skipped, because a silent
    skip is a check that passes for the one input it could not examine.

    Delete this and handing `credential_gaps` a plain class makes it answer clean."""

    class NotADataclass:
        password = "x"

    assert any("not a dataclass" in one for one in credential_gaps((), (NotADataclass,)))


def test_a_recovery_handoff_refuses_an_issuer_that_is_blank_or_insecure() -> None:
    """A space rather than only an empty string, because a space is what a configuration
    field sends when somebody clears it and `" "` passes a bare falsiness check. And http
    rather than https, because this handoff is an instruction to go and type a password.

    Delete this and the recovery link points at nothing, or at something in the clear."""
    for issuer in ("", " ", "   "):
        with pytest.raises(ValueError, match="no issuer"):
            recovery_handoff(issuer)
    with pytest.raises(ValueError, match="not https"):
        recovery_handoff("http://id.example.test/realms/brain")


def test_a_recovery_handoff_points_at_the_provider_that_signed_this_person_in() -> None:
    """The positive half, and it pins where the destination comes from: the issuer on the
    verified token rather than a value configured a second time.

    Delete this and the handoff can be a constant that is right for one installation."""
    handoff = recovery_handoff(ISSUER + "/")

    assert isinstance(handoff, RecoveryHandoff)
    assert handoff.destination == ISSUER + "/account"
    assert "cannot reset" in handoff.copy


# ------------------------------------------------------ M40.1.2.4 the entitlement line
def test_the_entitlement_line_changes_when_the_grants_change() -> None:
    """The leaf asks for a line rendered from the real entitlement set, and the only way to
    show that is two sets and two different lines.

    Delete this and the line can be a constant that reads plausibly for everybody."""
    narrow = disclosure_line(entitlement("read:ticket.status"), NOW)
    wide = disclosure_line(entitlement("read:ticket.status", "read:invoice.amount"), NOW)

    assert narrow.startswith(DISCLOSURE_PREFIX)
    assert narrow == f"{DISCLOSURE_PREFIX}ticket."
    assert wide == f"{DISCLOSURE_PREFIX}invoice, ticket."
    assert narrow != wide


def test_an_expired_entitlement_discloses_nothing_rather_than_what_it_used_to_hold() -> None:
    """`scope_for` returns None for every capability once the set is past `not_after`, and
    the line reads that rather than the grant tuple, so somebody whose access ended sees the
    same sentence as somebody who never had any.

    Delete this and a contractor's last page lists everything they could see yesterday."""
    ended = EntitlementSet(
        principal_id=ME,
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
        ),
        not_after=NOW - timedelta(minutes=1),
    )

    assert disclosure_line(ended, NOW) == NOTHING_DISCLOSED_YET
    assert disclosure_line(entitlement(), NOW) == NOTHING_DISCLOSED_YET


def test_the_entitlement_line_carries_no_count_of_anything() -> None:
    """A line ending "and 4 more" is a count of things this person may not see, which is the
    subtraction disclosure the whole system refuses.

    Delete this and the line grows a helpful summary of what was left out."""
    line = disclosure_line(entitlement("read:ticket.status", "read:invoice.amount"), NOW)

    assert not any(character.isdigit() for character in line)
    assert "more" not in line
    assert "hidden" not in line


def test_the_entitlement_line_cannot_be_handed_in() -> None:
    """ "Never hand-written" as a signature property rather than as a promise, and the check
    exercised against a function that breaks it, so it is not satisfied by one that answers
    empty for everything.

    Delete this and the line acquires an override parameter for a design that wanted
    friendlier words, and it stops being the answer the gate would give."""

    def written(entitlement: EntitlementSet, text: str = "") -> str:
        return text or str(entitlement.principal_id)

    assert disclosure_gaps(disclosure_line) == ()
    assert any("takes text" in one for one in disclosure_gaps(written))
