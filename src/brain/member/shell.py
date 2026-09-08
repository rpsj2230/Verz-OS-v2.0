"""How a member gets in, and why a member surface cannot reach a governance one.

The member application is a second front end over the same system, and the reason to build
one is not that administrators want a tidier console. It is that most people in a company
should never see the governance surfaces at all, and hiding them from a menu is not the same
as not serving them.

**A menu is not a boundary, and the leaf that matters here says so out loud.** M40.1.2.2 asks
for no administrative surface reachable by URL guessing, enforced server side. A member
application that omits the admin navigation and serves `/people` to whoever types it is a
menu, and a menu is defeated by curiosity. So the enforcement here is structural and there
are three parts to it, none of which is a list of forbidden paths.

**One. The decision is `brain.console.reads.permitted`, the same function the console uses.**
Not a second check written for members, because a second permission function is a second
place for the rule to be subtly wrong and the wrong one is the one on the surface nobody
audits. `member_navigation` and `serve` both call it, so what the menu offers and what the
server will hand over are the same predicate rather than two that have to be kept in step.
`menu_and_route_agree` asserts that, because the failure worth catching is the reverse: a
screen the menu hides and the router serves.

**Two. The two registries are disjoint by construction, checked against the whole console
registry rather than against a list of paths.** `A_LIST_OF_FORBIDDEN_PATHS_IS_ONE_ROUTE_AWAY
_FROM_BEING_INCOMPLETE` is the argument: a denylist of admin routes is correct on the day it
is written and wrong the next time somebody adds a screen, and nothing fails when it goes
stale. `MemberScreen` refuses at construction a key, a tool or a required capability that any
console screen already carries, so the check reads the console registry as it stands and
covers the thirty-fifth screen the day it is added. **A member capability is one whose noun
is `member`**, which is what makes "administrative surface" a property rather than a list:
an administrative screen is one gated on a capability a governance screen is gated on.

**Three. `serve` has no way to reach the console registry.** It resolves an exact key against
`MEMBER_SCREENS` and returns `MemberScreen | None`, an annotation `boundary_gaps` pins, and
it takes no parameter through which a registry, a role or an override could arrive. So a
guessed path is not refused, it is unresolvable: the router has nothing to resolve it to. The
test drives that from the console registry itself, asking `serve` for every console screen
key while holding every console capability there is, which is the strongest form of the
claim: **somebody holding every administrative grant in the system still cannot reach a
governance screen through this router.**

What this is not. It is not a claim that a process cannot mount both routers. It cannot be:
whoever wires the application decides that, and if the console router is mounted then the
console's own `permitted` decides those paths, which is the enforcement working rather than
failing. The claim is narrower and is the one the leaf asks for: the member surface resolves
to member screens or to nothing, whatever is typed at it.

**DENIED and ABSENT are the same answer here, and that is why `serve` returns `None` twice.**
A member screen that exists and is not permitted, and a path that names nothing, come back
identically. A refusal that distinguished them would let somebody enumerate the member
surface by watching which paths answer differently.

**Sign-in has no second directory and no second claim mapping.** `sign_in` calls
`brain.identity.oidc.principal_for` and `brain.identity.sessions.open_session` and does
nothing else, which is the whole of M40.1.1.1: the web application signs in the way every
other caller does. The principal id comes from the directory keyed on issuer and subject,
never from the token, so a member and the same person on Lark resolve to one principal
because both routes ask the same question of the same table. `one_principal` refuses a
disagreement rather than picking one, following `brain.channels.binding`'s reading that
"somebody is taking over an account" and "somebody made a mistake" look identical.

**Rejected: a member-scoped `EntitlementSet` assembled here.** The obvious shortcut for a
member surface is to narrow the caller's grants to the ones a member screen needs and pass
that around. It is a second reach, computed outside the one intersection this repository
allows, and it would be wrong in the direction nobody notices: too wide, once, in a refactor.
The entitlement handed to `serve` is the caller's own and this module never builds one.

**Rejected: a password reset of our own.** M40.1.1.4 asks for recovery to be the identity
provider's, and the honest way to build that is to have nowhere to put a credential.
`credential_gaps` reads the surface's signatures and its own types for a credential-shaped
name, so the refusal survives somebody adding a helpful form field.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter throughout, as in every module this one reads.

Task ids: M40.1.1.1, M40.1.1.2, M40.1.1.3, M40.1.1.4, M40.1.1.5
Task ids: M40.1.2.1, M40.1.2.2, M40.1.2.4
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from typing import Any, Final

from brain.console.reads import ConsoleRead, Plane, permitted
from brain.console.screens import SCREENS, Screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.context import Channel
from brain.gate.ingress import Binding
from brain.identity.oidc import PrincipalDirectory, UnmappedSubject, VerifiedClaims, principal_for
from brain.identity.sessions import (
    SESSION_ABSOLUTE_MAX,
    SESSION_IDLE,
    Session,
    SessionRegistry,
    open_session,
)

# ------------------------------------------------------------------ written-down reasons
#: Why the member surface is not enforced by the shape of its navigation.
A_MENU_IS_NOT_A_BOUNDARY_AND_THE_SERVER_DECIDES_EVERY_PATH: Final = (
    "Leaving the administrative sections out of a member menu changes what somebody is "
    "offered and changes nothing about what the server will hand over when they type the "
    "path. The menu and the route are therefore the same predicate here, "
    "brain.console.reads.permitted, called by member_navigation and by serve, and "
    "menu_and_route_agree asserts they cannot disagree. The failure that matters is the "
    "reverse of the obvious one: a screen the menu hides and the router still serves."
)

#: Why the boundary is not a denylist of administrative paths.
A_LIST_OF_FORBIDDEN_PATHS_IS_ONE_ROUTE_AWAY_FROM_BEING_INCOMPLETE: Final = (
    "A list of administrative routes the member application must refuse is correct on the "
    "day somebody writes it and silently wrong the next time a screen is added, and nothing "
    "fails when it goes stale. So the rule is stated the other way round and read off the "
    "console registry as it stands: a member screen may not carry a key, a tool or a "
    "required capability that any console screen carries, which covers the screen added "
    "tomorrow without anybody remembering this file exists."
)

#: What makes a surface administrative, stated as a property rather than as a list.
AN_ADMINISTRATIVE_SURFACE_IS_ONE_A_GOVERNANCE_SCREEN_IS_GATED_ON: Final = (
    "An administrative screen is not one whose title sounds administrative. It is one "
    "reached by holding a capability the console gates a governance screen on, so that is "
    "the definition used: every member screen requires a capability whose noun is member, "
    "no console screen requires one of those, and no member screen requires one the console "
    "requires. Both halves are checked, because a rule asserted in one direction is "
    "satisfied by a registry that is empty on the other side."
)

#: Why a guessed path and a refused one look the same.
AN_UNRESOLVABLE_PATH_AND_A_REFUSED_ONE_ARE_THE_SAME_ANSWER: Final = (
    "serve returns None for a path that names no member screen and for a member screen this "
    "caller may not open, and the two are indistinguishable on purpose. A router that said "
    "not found for one and forbidden for the other would let anybody map the member surface "
    "by typing at it, which is the enumeration DENIED equals ABSENT exists to refuse."
)

#: Why the credential rules are enforced by having nowhere to put one.
WE_HOLD_NO_CREDENTIAL_AND_THERE_IS_NOWHERE_HERE_TO_PUT_ONE: Final = (
    "Password reset and recovery are the identity provider's, and the way that survives a "
    "future contributor is not a paragraph saying so. It is that no function in this "
    "package takes a password, a reset token or a one-time code, and no type here has a "
    "field for one, which credential_gaps reads off the signatures and the field lists. A "
    "handoff names where to go and performs nothing."
)

#: Why the disclosure line is computed rather than written.
THE_DISCLOSURE_LINE_IS_READ_OFF_THE_GRANTS_AND_NEVER_WRITTEN_BY_HAND: Final = (
    "A sentence telling somebody what they can see is worth nothing unless it is the same "
    "answer the gate would give, and a hand-written one is right on the day it is written. "
    "disclosure_line takes an entitlement set and nothing else: there is no parameter it "
    "could receive text through, which is what disclosure_gaps checks, so the line is wrong "
    "only if the grants are wrong, and then it is wrong in the direction that is visible."
)

#: Why a disagreement between the two identities is refused rather than resolved.
ONE_PERSON_IS_ONE_PRINCIPAL_AND_THE_DIRECTORY_IS_WHAT_SAYS_SO: Final = (
    "The web identity is the principal the directory returns for an issuer and a subject; "
    "the channel identity is the principal a binding names, and a binding is minted inside "
    "a session that already resolved one. Both routes therefore end at the same directory "
    "row, and a disagreement between them is not a case to resolve. The two readings are "
    "somebody taking over an account and somebody making a mistake, they look identical "
    "from here, and picking either silently is how the wrong one goes unnoticed."
)


class MemberShellError(Exception):
    """A member surface was asked for something that is not this person's.

    Outside `brain.core.errors` for the reason `brain.console.own_things.OwnThingsError`
    gives about itself: those five outcomes describe an answer given to somebody who asked
    a question, and this is a refusal to operate a control on a personal screen.
    """


# --------------------------------------------------------------------------- the registry
#: The capability noun every member screen is gated on, and no console screen is.
#:
#: One noun rather than one per screen, because the check that matters is a set comparison
#: against the console's own requirements and a namespace makes that comparison exact. A
#: grant of `read:member.*` is therefore the whole member surface, which is deliberate: the
#: member surface is what somebody gets for having an account.
MEMBER_CAPABILITY_NOUN: Final = "member"

#: The only return annotation `serve` may carry. See `boundary_gaps`.
#:
#: Pinned because the interesting edit is not somebody deleting the check inside `serve`. It
#: is somebody widening the return type to `Screen | MemberScreen | None` so that one router
#: can serve both, at which point the member router resolves an administrative path and
#: every test below still passes.
ONLY_A_MEMBER_SCREEN: Final = "MemberScreen | None"

#: Parameter names on `serve` that would let a path resolve to something else.
NAMES_THAT_WOULD_REOPEN_THE_ROUTER: Final[frozenset[str]] = frozenset(
    {
        "allow",
        "console",
        "extra",
        "is_admin",
        "override",
        "registry",
        "role",
        "roles",
        "screens",
        "super_admin",
    }
)

#: Parameter and field names that would mean this package holds a credential.
NAMES_THAT_WOULD_BE_A_CREDENTIAL: Final[frozenset[str]] = frozenset(
    {
        "client_secret",
        "current_password",
        "new_password",
        "otp",
        "passphrase",
        "password",
        "recovery_code",
        "reset_token",
        "secret",
        "security_answer",
        "totp",
    }
)


def member_capability(field: str) -> Capability:
    """The capability one member screen is gated on.

    Built here rather than written out at each registry entry, so every member screen sits
    in the one noun the boundary check compares against. A screen that spelled its own
    capability could sit outside that namespace and still look like a member screen.
    """
    return Capability(value=f"read:{MEMBER_CAPABILITY_NOUN}.{field}")


@dataclass(frozen=True)
class MemberScreen:
    """One screen in the member application, refused if it is a governance screen wearing a coat.

    Carries a `ConsoleRead` for the same reason `brain.console.screens.Screen` does: a screen
    is a read of a tool at a plane, and this module refuses to be a second way of saying what
    one of those is. What it adds is the three refusals that make the two registries disjoint,
    and every one of them is computed from `SCREENS` rather than from a list written here.
    """

    key: str
    title: str
    read: ConsoleRead
    #: One sentence, for the menu and for whoever has to explain the surface to somebody.
    purpose: str

    def __post_init__(self) -> None:
        if not self.key.strip():
            msg = "a member screen with no key is one no path can resolve to"
            raise ValueError(msg)
        if not self.title.strip():
            msg = f"{self.key} has no title, so the menu entry is a blank line"
            raise ValueError(msg)
        if not self.purpose.strip():
            msg = f"{self.key} has no purpose sentence, so the menu entry explains nothing"
            raise ValueError(msg)
        if self.read.screen != self.key:
            msg = (
                f"{self.key} is wired to a read that audits itself as {self.read.screen!r}, "
                "so the audit row names a screen nobody can navigate to"
            )
            raise ValueError(msg)
        # The collision loop runs before the noun check, and the order was the other way
        # round until a mutation showed why it matters. With the noun check first, every
        # capability a console screen requires is refused by it (none of them is in the
        # member noun), so the capability-collision branch below could not be reached by any
        # input and switching it off changed no test. Reversed, each guard has inputs only it
        # refuses: `read:grant` collides with a console screen, `read:unicorn` collides with
        # nothing and is refused for its noun.
        for governance in SCREENS:
            if governance.key == self.key:
                msg = (
                    f"{self.key} is also a console screen key, so one router's path is the "
                    f"other's. {A_LIST_OF_FORBIDDEN_PATHS_IS_ONE_ROUTE_AWAY_FROM_BEING_INCOMPLETE}"
                )
                raise ValueError(msg)
            if governance.read.tool == self.read.tool:
                msg = (
                    f"{self.key} is wired to {self.read.tool}, which the console screen "
                    f"{governance.key} reads through, so a member screen and a governance "
                    "screen are the same call with two names in front of it"
                )
                raise ValueError(msg)
            if governance.read.requires == self.read.requires:
                msg = (
                    f"{self.key} requires {self.read.requires.value}, which gates the "
                    f"console screen {governance.key}. "
                    f"{AN_ADMINISTRATIVE_SURFACE_IS_ONE_A_GOVERNANCE_SCREEN_IS_GATED_ON}"
                )
                raise ValueError(msg)
        if self.read.requires.noun != MEMBER_CAPABILITY_NOUN:
            msg = (
                f"{self.key} requires {self.read.requires.value}, whose noun is not "
                f"{MEMBER_CAPABILITY_NOUN!r}. "
                f"{AN_ADMINISTRATIVE_SURFACE_IS_ONE_A_GOVERNANCE_SCREEN_IS_GATED_ON}"
            )
            raise ValueError(msg)


def _member_screen(key: str, title: str, plane: Plane, purpose: str) -> MemberScreen:
    """One registry entry, with the tool and the capability derived from the key.

    Derived rather than spelled out three times per entry, because the three have to agree
    and a repeated list is a list with a typo in it. `Screen` in the console does the same
    with the two axes every screen carries.
    """
    return MemberScreen(
        key=key,
        title=title,
        read=ConsoleRead(
            screen=key,
            tool=f"{MEMBER_CAPABILITY_NOUN}.{key}",
            requires=member_capability(key),
            plane=plane,
        ),
        purpose=purpose,
    )


#: Every screen the member application has. The order is the order of the menu.
#:
#: Five, against the console's thirty-four, which is M40.1.2.1's "much shorter" as a fact
#: rather than as an aspiration. A tuple rather than a mapping, following `SCREENS`: the
#: order is information and a mapping would leave it to whatever the renderer sorted by.
#:
#: **Three of these five were named `approvals`, `connections` and `sessions` first, and the
#: registry refused to build.** Those are console screen keys, and a member router serving
#: them would have been one path resolving to two different screens depending on which
#: application was mounted, which is the collision this whole module is about. The refusal
#: fired at import, before a test existed, which is what a construction-time check is for.
MEMBER_SCREENS: Final[tuple[MemberScreen, ...]] = (
    _member_screen(
        "home",
        "Home",
        Plane.CONTENT,
        "What you asked this month, what you can call, and what has been learnt about you. "
        "Every row on it is yours; see brain.console.own_things.",
    ),
    _member_screen(
        "envelopes",
        "Waiting for you",
        Plane.CONTENT,
        "Envelopes waiting on your answer, each one saying what will happen before you "
        "answer it, and what happens if you do not, which is nothing.",
    ),
    _member_screen(
        "accounts",
        "Connected accounts",
        Plane.CONFIGURATION,
        "The accounts you have connected and the ones your department connected for you. "
        "Connecting one never widens what you may see.",
    ),
    _member_screen(
        "channels",
        "Where to reach you",
        Plane.CONFIGURATION,
        "Which channels you are reachable on, which one is primary, where approvals should "
        "go, and the hours when only an approval may interrupt you.",
    ),
    _member_screen(
        "devices",
        "Signed in",
        Plane.CONFIGURATION,
        "Every device currently signed in as you, when each signed in and when it will be "
        "signed out, with the control to end one now.",
    ),
)

#: How many member screens exist, so a test can pin it and a person can quote it.
#:
#: Pinned rather than computed at the call site, for `SCREEN_COUNT`'s reason: the interesting
#: failure is a screen disappearing in a refactor, and `len(MEMBER_SCREENS) ==
#: len(MEMBER_SCREENS)` would not notice. The test relates it to the console registry rather
#: than to itself, which is the discipline CLAUDE.md records about constants.
MEMBER_SCREEN_COUNT: Final = 5


def member_screen(key: str) -> MemberScreen:
    """One member screen by key, or a failure naming it.

    A lookup rather than the tuple exported as a mapping, following `brain.console.screens.
    screen`: the registry's order is information and a mapping invites somebody to iterate
    it for the menu.
    """
    for one in MEMBER_SCREENS:
        if one.key == key:
            return one
    msg = f"no member screen named {key!r}"
    raise KeyError(msg)


def member_navigation(
    entitlement: EntitlementSet, now: datetime | None = None
) -> tuple[MemberScreen, ...]:
    """The menu this member sees (M40.1.2.1). Grants only, and no count of the rest.

    `permitted` rather than a check written here, which is the first of the three parts of
    the boundary: the member surface and the console are decided by one function, so there
    is no member permission model to drift away from the console's.

    Returns one value, for `brain.console.screens.navigation`'s reason. A second one
    carrying what was withheld would be a count of things this person may not see.
    """
    return tuple(one for one in MEMBER_SCREENS if permitted(one.read, entitlement, now))


def serve(
    path: str, entitlement: EntitlementSet, now: datetime | None = None
) -> MemberScreen | None:
    """What the member router hands back for a path (M40.1.2.2), or nothing.

    **The whole of the URL-guessing argument is in what this cannot do.** It resolves an
    exact key against `MEMBER_SCREENS`, which holds no governance screen because
    `MemberScreen` refuses one at construction, and it has no parameter through which a
    registry, a role or an override could arrive. A path naming a console screen is not
    refused here, it is unresolvable: there is nothing to resolve it to.

    `None` twice over, and the two are the same answer on purpose. See
    `AN_UNRESOLVABLE_PATH_AND_A_REFUSED_ONE_ARE_THE_SAME_ANSWER`.
    """
    for one in MEMBER_SCREENS:
        if one.key == path:
            return one if permitted(one.read, entitlement, now) else None
    return None


def menu_and_route_agree(
    entitlement: EntitlementSet,
    now: datetime | None = None,
    *,
    menu: Callable[..., Sequence[MemberScreen]] = member_navigation,
    route: Callable[..., MemberScreen | None] = serve,
) -> tuple[str, ...]:
    """Every member screen the menu and the router disagree about (M40.1.2.2).

    Both directions, and the second is the one worth having. A screen offered in the menu
    and refused by the router is a broken console, which somebody reports. A screen the menu
    hides and the router serves is the defect this leaf is about, and nobody reports it
    because nobody sees it.

    **Takes the two functions as well as the entitlement**, and it took only the entitlement
    first. That version could never report anything: it called this module's own
    `member_navigation` and `serve`, which agree by construction, so both branches below were
    unreachable and switching either off changed nothing any test could see. That is the
    defect CLAUDE.md's mutation discipline is written about, arriving in a diagnostic rather
    than in a guard. Defaulted, so the deployment check is still a call with no arguments.
    """
    offered = set(menu(entitlement, now))
    gaps: list[str] = []
    for one in MEMBER_SCREENS:
        served = route(one.key, entitlement, now) is not None
        if served and one not in offered:
            gaps.append(
                f"{one.key} is served by its path and is not in this caller's menu, so the "
                f"menu is decorative. {A_MENU_IS_NOT_A_BOUNDARY_AND_THE_SERVER_DECIDES_EVERY_PATH}"
            )
        if one in offered and not served:
            gaps.append(
                f"{one.key} is in this caller's menu and its own path refuses it, so the "
                "member reads a broken application rather than a permission boundary"
            )
    return tuple(gaps)


def router_gaps(route: Callable[..., Any] = serve) -> tuple[str, ...]:
    """Anything about the router's own shape that would let a path resolve elsewhere.

    Two checks, both read off a signature rather than out of a body, because a body check is
    removable by the person adding the feature and a signature change is not. That is
    `brain.identity.oidc.assert_no_capability_from_claims`' argument about the same problem.

    Takes the function for `disclosure_gaps`' reason, which is the reason every diagnostic in
    this package takes its input: called on `serve` this is the deployment check, and called
    on a function that breaks the rule it is a test that can fail.

    The return annotation is compared against the one correct value rather than searched for
    words that would be wrong, following `brain.console.screens.screen_gaps`: the list of
    ways to spell "and also a console screen" is open and the list of acceptable return types
    has one entry.
    """
    gaps: list[str] = []

    returns = str(inspect.signature(route).return_annotation)
    if returns != ONLY_A_MEMBER_SCREEN:
        gaps.append(
            f"{route.__name__} returns {returns} rather than {ONLY_A_MEMBER_SCREEN}, so one "
            "router can resolve a path to a governance screen and every other check passes"
        )

    taken = set(inspect.signature(route).parameters)
    gaps.extend(
        f"{route.__name__} takes {name}, so a path can resolve to something other than a "
        f"member screen. {A_LIST_OF_FORBIDDEN_PATHS_IS_ONE_ROUTE_AWAY_FROM_BEING_INCOMPLETE}"
        for name in sorted(taken & NAMES_THAT_WOULD_REOPEN_THE_ROUTER)
    )

    return tuple(gaps)


def boundary_gaps(
    registry: Sequence[MemberScreen] = MEMBER_SCREENS,
    governance: Sequence[Screen] = SCREENS,
    entitlement: EntitlementSet | None = None,
) -> tuple[str, ...]:
    """Everything that would let the member router reach a governance surface (M40.1.2.2).

    Takes both registries rather than reading the module's own, for `own_gaps`' reason: a
    diagnostic exercised only against the healthy tree cannot be shown to fire, so switching
    off any refusal below would change nothing observable. Calling it with no arguments is
    the deployment check and calling it with a constructed registry is the test.

    Six checks. The first two are `router_gaps`, which holds `serve` to its shape; the next
    three are the disjointness, stated against whatever console registry is handed in so that
    the answer covers screens nobody has written yet. The sixth is M40.1.2.1's "much
    shorter", which is a boundary property and not a taste: a member registry the size of the
    console's is one that has grown administrative screens.
    """
    gaps: list[str] = [*router_gaps()]

    keys = {one.key for one in governance}
    tools = {one.read.tool for one in governance}
    requirements = {one.read.requires for one in governance}
    for one in registry:
        if one.key in keys:
            gaps.append(f"{one.key} is a console screen key as well as a member path")
        if one.read.tool in tools:
            gaps.append(f"{one.key} reads through {one.read.tool}, which a console screen uses")
        if one.read.requires in requirements:
            gaps.append(
                f"{one.key} requires {one.read.requires.value}, which gates a console screen. "
                f"{AN_ADMINISTRATIVE_SURFACE_IS_ONE_A_GOVERNANCE_SCREEN_IS_GATED_ON}"
            )

    # The other direction, and it is not the same check. The three above ask whether a member
    # screen has taken something of the console's; this asks whether a console screen has
    # taken the member namespace, which would make the noun stop separating them.
    gaps.extend(
        f"the console screen {one.key} requires {one.read.requires.value}, so the member "
        f"noun no longer tells a member surface from a governance one. "
        f"{AN_ADMINISTRATIVE_SURFACE_IS_ONE_A_GOVERNANCE_SCREEN_IS_GATED_ON}"
        for one in governance
        if one.read.requires.noun == MEMBER_CAPABILITY_NOUN
    )

    if len(registry) >= len(governance):
        gaps.append(
            f"the member application has {len(registry)} screens against the console's "
            f"{len(governance)}, and a member surface that size has grown governance screens"
        )

    if entitlement is not None:
        gaps.extend(menu_and_route_agree(entitlement))

    return tuple(gaps)


# --------------------------------------------------------------------------- signing in
@dataclass(frozen=True)
class MemberSignIn:
    """A member who is signed in: one principal and one session, and nothing else.

    No entitlement set. The reach is resolved where every other caller's is, and a member
    sign-in that carried one would be a second place a reach is assembled, computed outside
    the one intersection this repository allows.
    """

    principal_id: str
    session: Session

    def __post_init__(self) -> None:
        if self.principal_id != self.session.principal_id:
            msg = (
                f"this sign-in names {self.principal_id!r} and its session belongs to "
                f"{self.session.principal_id!r}, so the audit trail and the session would "
                "disagree about who is here"
            )
            raise ValueError(msg)


def sign_in(
    claims: VerifiedClaims,
    directory: PrincipalDirectory,
    *,
    now: datetime,
    second_factor: bool = False,
) -> MemberSignIn | UnmappedSubject:
    """Sign a member in through the identity provider the channels already use (M40.1.1.1).

    Two calls and no third. `principal_for` is the directory lookup every caller makes and
    `open_session` is the session policy every session gets, so the member application adds
    no identity of its own: no second directory, no member-only claim mapping, no principal
    assembled from a token.

    **The principal id is the directory's and never the token's subject**, which is the
    property M40.1.1.2 rests on. Both routes into this system, a browser and a bound
    channel, end at the same directory row, so the same person is one principal without
    anything having to reconcile two.

    `UnmappedSubject` passes straight through rather than becoming an exception, following
    `principal_for`: a valid token from somebody nobody has onboarded is a normal event with
    an instruction attached, and no session is opened for it.
    """
    found = principal_for(claims, directory, now=now)
    if isinstance(found, UnmappedSubject):
        return found
    session = open_session(
        claims=claims,
        principal=found,
        now=now,
        second_factor=second_factor,
    )
    return MemberSignIn(principal_id=found.id, session=session)


def one_principal(sign_in_result: MemberSignIn, binding: Binding) -> str:
    """The one principal this person is, or a refusal (M40.1.1.2).

    Refused rather than resolved when the two disagree. See
    `ONE_PERSON_IS_ONE_PRINCIPAL_AND_THE_DIRECTORY_IS_WHAT_SAYS_SO`: the readings are a
    takeover and a mistake, they are indistinguishable from here, and picking one silently
    is how the wrong one goes unnoticed.

    Returns the id rather than a boolean, so a caller that wanted to check gets the value it
    would have gone on to use, and there is no version of this where somebody compares and
    then reads the wrong one of the two.
    """
    if binding.principal_id != sign_in_result.principal_id:
        msg = (
            f"a {binding.channel.value} binding names a different principal from this "
            f"sign-in. {ONE_PERSON_IS_ONE_PRINCIPAL_AND_THE_DIRECTORY_IS_WHAT_SAYS_SO}"
        )
        raise MemberShellError(msg)
    return sign_in_result.principal_id


def bound_channels(principal_id: str, bindings: Iterable[Binding]) -> tuple[Channel, ...]:
    """Every channel this principal is bound on, in the order the bindings arrive.

    Order preserved rather than sorted, following `brain.console.screens.offerable`: the
    caller's order is usually meaningful, most recently bound first, and re-sorting discards
    it. Duplicates are dropped, because `brain.channels.binding` keeps one live binding per
    principal per channel and two here would mean the caller handed in a revoked one.
    """
    found: list[Channel] = []
    for one in bindings:
        if one.principal_id == principal_id and one.channel not in found:
            found.append(one.channel)
    return tuple(found)


# ------------------------------------------------------------- session policy and devices
#: How long a member session survives with nothing happening on it (M40.1.1.3).
#:
#: The identity package's own value rather than a number repeated here. A member console
#: with its own idle window would be a second session policy, and the one that drifts is the
#: one on the surface most people use.
IDLE_TIMEOUT: Final = SESSION_IDLE

#: The longest a member session may live however often it is refreshed (M40.1.1.3).
MAXIMUM_SESSION: Final = SESSION_ABSOLUTE_MAX

#: What a member is told about both, in one sentence, computed from the two above.
#:
#: Rendered rather than written out, for the reason the disclosure line is: a sentence
#: quoting thirty minutes stays green after somebody changes the constant to sixty.
SESSION_POLICY_SENTENCE: Final = (
    f"You are signed out after {int(IDLE_TIMEOUT.total_seconds() // 60)} minutes of "
    f"inactivity, and after {int(MAXIMUM_SESSION.total_seconds() // 3600)} hours whatever "
    "you are doing."
)

#: What somebody is told when they try to end a device that is not on their account.
#:
#: One sentence for both cases, following `brain.gate.ingress.UNRECOGNISED_PROMPT`. A member
#: who typed somebody else's session id must not learn from the wording whether it exists,
#: because "no such device" for one id and "not yours" for another is a lookup service.
NO_SUCH_DEVICE_ON_THIS_ACCOUNT: Final = "There is no such device signed in on your account."


@dataclass(frozen=True)
class Device:
    """One live sign-in as this person sees it (M40.1.1.3).

    Carries no address, no user agent and no location. Those are the fields a device list
    grows first and each of them is a fact about somebody's whereabouts sitting on a screen
    that anyone borrowing an unlocked laptop can read. The session id is enough to end one,
    which is what the list is for.
    """

    session_id: str
    opened_at: datetime
    idle_expires_at: datetime
    absolute_expiry: datetime
    second_factor: bool
    #: True for the session reading the list, so nobody signs themselves out looking for
    #: the other one.
    is_this_one: bool


def devices(
    registry: SessionRegistry,
    *,
    principal_id: str,
    now: datetime,
    current_session_id: str = "",
) -> tuple[Device, ...]:
    """Every device currently signed in as this person, newest first (M40.1.1.3).

    `SessionRegistry.live_for` rather than a scan written here, so the definition of live is
    the session module's own and a device cannot appear on this list after it has expired.

    Newest first, which is the one place in this package the caller's order is not kept: a
    device list is read to find the one you do not recognise, and that is the most recent.
    """
    found = registry.live_for(principal_id, now)
    return tuple(
        Device(
            session_id=one.session_id,
            opened_at=one.opened_at,
            idle_expires_at=one.expires_at,
            absolute_expiry=one.absolute_expiry,
            second_factor=one.second_factor,
            is_this_one=one.session_id == current_session_id,
        )
        for one in sorted(found, key=lambda one: (one.opened_at, one.session_id), reverse=True)
    )


def end_device(
    registry: SessionRegistry,
    *,
    principal_id: str,
    session_id: str,
    now: datetime,
) -> Session:
    """End one of this person's own devices (M40.1.1.3), or refuse without saying why.

    **The ownership check is the whole of this function and it does not exist in the
    registry.** `SessionRegistry.end_session` takes an id and ends whatever it names, which
    is right for an administrator on the console's sessions screen and wrong for a form on a
    member's own page: a member with somebody else's session id would sign that person out.

    Both refusals carry `NO_SUCH_DEVICE_ON_THIS_ACCOUNT` and there is deliberately no way to
    tell them apart, so the control cannot be used to find out whether a session id is real.
    """
    found = registry.get(session_id)
    if found is None or found.principal_id != principal_id:
        raise MemberShellError(NO_SUCH_DEVICE_ON_THIS_ACCOUNT)
    registry.end_session(session_id, now)
    # The session found a line above is returned rather than the registry's own answer, which
    # is `Session | None` and cannot be None here. A branch for that None would read as a
    # guard and could never fire, which is the shape `tests/invariants/
    # test_guards_that_can_fire.py` exists to refuse.
    return found


# ---------------------------------------------------------------- recovery is theirs, not ours
#: What a member is told when they cannot get in. It performs nothing and promises nothing.
RECOVERY_COPY: Final = (
    "Passwords and second factors are handled by your organisation's sign-in service. "
    "The Brain never sees them and cannot reset one."
)

#: The path the account-management page sits at, relative to the token issuer.
#:
#: Keycloak's account console, which is what this repository's `ops/` realm configures, and
#: it is a constant rather than an assumption because an installation brokering a different
#: provider changes one value. `recovery_handoff` refuses an issuer that is not https,
#: because the one thing this handoff must not do is send somebody to type a password over
#: a transport nobody checked.
ACCOUNT_PATH: Final = "/account"


@dataclass(frozen=True)
class RecoveryHandoff:
    """Where to go to reset a password, and the statement that we cannot (M40.1.1.4).

    Two strings and no verbs. There is no `send_reset_email`, no `verify_code` and no field
    that could hold one; see `WE_HOLD_NO_CREDENTIAL_AND_THERE_IS_NOWHERE_HERE_TO_PUT_ONE`.
    """

    destination: str
    copy: str = RECOVERY_COPY


def recovery_handoff(issuer: str) -> RecoveryHandoff:
    """Where the identity provider handles recovery (M40.1.1.4). We do not.

    The issuer is the one from a verified token rather than a value configured twice, so the
    page somebody is sent to is the provider that actually signed them in.

    Refuses a blank issuer, including one that is only whitespace, because a form field
    arrives as a space rather than as nothing and `"".strip()` and `" ".strip()` are the
    same emptiness. Refuses a non-https issuer, because a handoff is an instruction to go
    and type a password somewhere.
    """
    trimmed = issuer.strip()
    if not trimmed:
        msg = "a recovery handoff with no issuer sends somebody nowhere"
        raise ValueError(msg)
    if not trimmed.startswith("https://"):
        msg = (
            f"issuer {trimmed!r} is not https, and this handoff tells somebody to go there "
            "and type a password"
        )
        raise ValueError(msg)
    return RecoveryHandoff(destination=f"{trimmed.rstrip('/')}{ACCOUNT_PATH}")


def credential_gaps(
    surface: Sequence[Callable[..., Any]] = (),
    types: Sequence[type] = (),
) -> tuple[str, ...]:
    """Anything in this package that could hold a credential (M40.1.1.4).

    Both halves, because they fail differently. A function taking a password is somebody
    adding a reset endpoint; a type with a `secret` field is somebody storing what a form
    posted. Neither is caught by the other.

    Takes its inputs for `own_gaps`' reason, and the defaults are empty rather than this
    module's own surface so that a caller has to say what it is checking. `MEMBER_SURFACE`
    and `MEMBER_TYPES` below are what the test and the deployment check hand it.
    """
    gaps: list[str] = []
    for one in surface:
        gaps.extend(
            f"{one.__name__} takes {name}, so this package handles a credential. "
            f"{WE_HOLD_NO_CREDENTIAL_AND_THERE_IS_NOWHERE_HERE_TO_PUT_ONE}"
            for name in sorted(
                set(inspect.signature(one).parameters) & NAMES_THAT_WOULD_BE_A_CREDENTIAL
            )
        )
    for kind in types:
        if not is_dataclass(kind):
            gaps.append(f"{kind.__name__} is not a dataclass, so its fields were not read")
            continue
        gaps.extend(
            f"{kind.__name__} has a {one.name} field, so this package stores a credential. "
            f"{WE_HOLD_NO_CREDENTIAL_AND_THERE_IS_NOWHERE_HERE_TO_PUT_ONE}"
            for one in fields(kind)
            if one.name in NAMES_THAT_WOULD_BE_A_CREDENTIAL
        )
    return tuple(gaps)


# ------------------------------------------------------------------- the disclosure line
#: What somebody with no live grant is told. It names nothing that exists.
#:
#: "You cannot see anything yet" rather than a list of what they are missing, because a list
#: of what somebody may not reach is a directory of what the company has.
NOTHING_DISCLOSED_YET: Final = (
    "You have not been given access to anything yet. Ask your department administrator."
)

#: How the line opens. Separate from the nouns so a test can assert the sentence changes
#: with the grants rather than matching a prefix that never moves.
DISCLOSURE_PREFIX: Final = "You can see: "


def disclosure_line(entitlement: EntitlementSet, now: datetime | None = None) -> str:
    """The sentence telling this member what they can see (M40.1.2.4), read off their grants.

    **Nothing here is written by hand and there is no parameter it could be written through.**
    See `THE_DISCLOSURE_LINE_IS_READ_OFF_THE_GRANTS_AND_NEVER_WRITTEN_BY_HAND`, and
    `disclosure_gaps`, which reads this signature for one.

    Nouns rather than whole capability strings, because the field-level ones would make the
    line unreadable and a person's question is which kinds of thing they reach. Each noun is
    re-asked through `scope_for`, so an expired entitlement discloses nothing rather than
    listing what it used to hold: `scope_for` returns None for every capability once the set
    is past `not_after`, which is the check this would otherwise have to remember.

    No count, in either direction. Not of what is listed and not of what is not, because a
    line saying "and 4 more" is the subtraction disclosure `CLAUDE.md` names.
    """
    nouns = sorted(
        {
            one.capability.noun
            for one in entitlement.grants
            if entitlement.scope_for(one.capability, now) is not None
        }
    )
    if not nouns:
        return NOTHING_DISCLOSED_YET
    return f"{DISCLOSURE_PREFIX}{', '.join(nouns)}."


#: Parameter names that would let the disclosure line be supplied rather than computed.
NAMES_THAT_WOULD_HAND_WRITE_THE_LINE: Final[frozenset[str]] = frozenset(
    {
        "copy",
        "line",
        "message",
        "override",
        "sentence",
        "summary",
        "text",
        "wording",
    }
)


def disclosure_gaps(line: Callable[..., str] = disclosure_line) -> tuple[str, ...]:
    """Anything that would let the entitlement line say something the grants do not (M40.1.2.4).

    Takes the function rather than reading the module's own, so the check can be shown to
    fire against a function that breaks it. That is `own_gaps`' argument and it is the
    difference between a diagnostic and a decoration.
    """
    taken = set(inspect.signature(line).parameters)
    return tuple(
        f"{line.__name__} takes {name}, so the line a member reads can be supplied rather "
        f"than computed. {THE_DISCLOSURE_LINE_IS_READ_OFF_THE_GRANTS_AND_NEVER_WRITTEN_BY_HAND}"
        for name in sorted(taken & NAMES_THAT_WOULD_HAND_WRITE_THE_LINE)
    )


# --------------------------------------------------------------------------- what to check
#: Every function this module offers a member, for `credential_gaps`.
#:
#: Listed rather than discovered, following `brain.console.own_things.PERSONAL_SURFACE`: a
#: function added here and not to this tuple is one the check never sees.
MEMBER_SURFACE: Final[tuple[Callable[..., Any], ...]] = (
    sign_in,
    one_principal,
    bound_channels,
    devices,
    end_device,
    recovery_handoff,
    disclosure_line,
    serve,
    member_navigation,
)

#: Every type this module hands a member, for `credential_gaps`.
MEMBER_TYPES: Final[tuple[type, ...]] = (
    MemberScreen,
    MemberSignIn,
    Device,
    RecoveryHandoff,
)


def shell_gaps(entitlement: EntitlementSet | None = None) -> tuple[str, ...]:
    """Everything wrong with this module's own shape, in one call. The deployment check.

    Three diagnostics rather than one, because each is about a different rule and a caller
    debugging one does not want the other two's findings mixed into it. This is the entry
    point that runs all three against what this module actually ships, which is the thing
    none of them does on its own: each takes its inputs so that it can be exercised against
    a broken one.
    """
    return (
        *boundary_gaps(MEMBER_SCREENS, SCREENS, entitlement),
        *credential_gaps(MEMBER_SURFACE, MEMBER_TYPES),
        *disclosure_gaps(disclosure_line),
    )
