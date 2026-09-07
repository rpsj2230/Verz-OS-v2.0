"""The console's screens, held to the four ways a screen registry becomes a permission model.

The console had four pages and the work breakdown named eighteen, and both were lists somebody
wrote down. `brain.console.screens` states a screen as a capability, a plane and a set of axes,
which turns four hand-answered questions into computed ones: what appears in the menu, what a
department admin sees, what a filter may offer, and which screens are missing.

Every test here is about the registry not quietly becoming the thing it replaced: a second
place where access is decided, which would decide it differently from the gate.

Task ids: none
"""

from __future__ import annotations

import inspect

import pytest

from brain.console.reads import CONSOLE_CAPABILITY_PREFIX, ConsoleRead, Plane, plane_capability
from brain.console.screens import (
    EVERYWHERE,
    SCREEN_COUNT,
    SCREENS,
    Axis,
    Group,
    Lens,
    Screen,
    for_department,
    grouped,
    navigation,
    offerable,
    screen,
    screen_gaps,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.roles import Role


def holding(*capabilities: str, planes: tuple[Plane, ...] = (Plane.CONTENT,)) -> EntitlementSet:
    """A caller holding these capabilities company-wide, plus the plane grants named.

    Both halves are needed for a screen to be permitted: the tool's own capability and the
    console plane. Built here rather than imported so a test can hold one and not the other,
    which is the case `permitted` exists for.
    """
    grants = [
        Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
    ]
    grants += [Grant(capability=plane_capability(one), scope=Scope(clauses=())) for one in planes]
    return EntitlementSet(principal_id="u_test", grants=tuple(grants))


def every_capability() -> EntitlementSet:
    return holding(*[one.read.requires.value for one in SCREENS])


# --- the registry is not a second permission model -----------------------------------------


def test_the_menu_is_computed_from_grants_and_never_from_a_role() -> None:
    """**The rule this registry could most easily undo.** `brain.identity.roles` opens with
    "no role implies a capability, including Super Admin". A registry keyed by role breaks that
    in the least visible place: the menu shows the screen because of the role, the tool behind
    it refuses because of the grant, and the person reads a broken console rather than a
    boundary.

    Asserted against the signature rather than the behaviour, because behaviour can be correct
    today and a parameter added tomorrow is what makes it wrong. `Screen.intended_for` exists
    and is documentation; this is what stops it becoming an authorisation.

    Delete this and `navigation(entitlement, role=...)` is a natural-looking convenience."""
    taken = set(inspect.signature(navigation).parameters)

    for forbidden in ("role", "roles", "is_admin", "super_admin", "override"):
        assert forbidden not in taken, forbidden

    assert not screen_gaps()


def test_a_role_alone_opens_nothing() -> None:
    """The behaviour beside the signature. A caller whose only distinction is being intended
    for every screen sees none of them, because `intended_for` is read by nobody.

    The positive half is the discriminating one: the same caller with the grants sees the
    screens, so this is not passing because `navigation` returns nothing.

    Delete this and `intended_for` can be wired into `navigation` with the signature check
    still green, because a set of roles could be read off the entitlement."""
    assert all(Role.SUPER_ADMIN in one.intended_for for one in SCREENS if one.company_wide)

    nothing = EntitlementSet(principal_id="u_test", grants=())
    assert navigation(nothing) == ()

    assert len(navigation(every_capability())) == SCREEN_COUNT


def test_a_screen_needs_the_plane_as_well_as_the_capability() -> None:
    """Both grants, conjunctively. A caller holding every tool capability and no console plane
    reaches nothing, which is what makes the plane a real grant rather than a label.

    Delete this and `permitted` can be reduced to the capability check, and an auditor granted
    existence starts reading content."""
    no_plane = holding(*[one.read.requires.value for one in SCREENS], planes=())

    assert navigation(no_plane) == ()

    existence_only = holding(
        *[one.read.requires.value for one in SCREENS], planes=(Plane.EXISTENCE,)
    )
    reached = {one.key for one in navigation(existence_only)}
    assert reached
    assert all(screen(key).read.plane is Plane.EXISTENCE for key in reached)


def test_a_screen_cannot_require_a_plane_capability() -> None:
    """A screen whose requirement is the console grant itself would be reachable by anybody
    trusted with the console, and the plane would be doing the work the tool's grant should.

    Refused by `ConsoleRead` at construction, so this asserts the registry has none rather
    than that the constructor works, which `test_console_reads` already holds.

    Delete this and a screen added with `read:console.content` looks correct and is open to
    every console user."""
    for one in SCREENS:
        assert not one.read.requires.value.startswith(CONSOLE_CAPABILITY_PREFIX), one.key

    with pytest.raises(ValueError, match="plane capability"):
        ConsoleRead(
            screen="sneaky",
            tool="console.sneaky",
            requires=plane_capability(Plane.CONTENT),
            plane=Plane.CONTENT,
        )


# --- the menu does not leak what it withheld -----------------------------------------------


def test_the_menu_says_nothing_about_the_screens_it_withheld() -> None:
    """A count of hidden sections is a count of things this person may not see, which is the
    disclosure by subtraction `CLAUDE.md` names as the easiest way to break DENIED-equals-
    ABSENT. `navigation` returns one value.

    The two callers are compared for shape rather than for length, because the interesting
    failure is a second value appearing, not a wrong count.

    Delete this and "and 12 more" is a reasonable-looking menu affordance."""
    wide = navigation(every_capability())
    narrow = navigation(holding("read:overview"))

    assert isinstance(wide, tuple)
    assert isinstance(narrow, tuple)
    assert all(isinstance(one, Screen) for one in wide + narrow)
    assert len(narrow) < len(wide)


def test_an_empty_section_is_not_shown_as_an_empty_section() -> None:
    """A heading reading Govern with nothing under it tells the reader there are governance
    screens they may not open, which is the same subtraction in a different shape.

    The positive half: a caller who reaches one screen in a group gets that group, so this is
    not passing because `grouped` returns nothing.

    Delete this and the renderer iterates `Group` and prints four headings whatever the
    caller holds."""
    one_group = navigation(holding("read:overview"))
    sections = grouped(one_group)

    assert [group for group, _ in sections] == [Group.OPERATE]
    assert all(inside for _, inside in sections)

    assert len(grouped(navigation(every_capability()))) == len(Group)


def test_a_filter_list_offers_only_what_the_caller_can_already_reach() -> None:
    """**The disclosure everybody forgets.** Every screen here can be narrowed by department,
    so every screen carries a dropdown of departments. Populated from the table it names every
    department in the company, on a screen whose rows were carefully scoped, and nobody
    reviewing the rows would look at the filter.

    `offerable` returns the values and no count of what it dropped, and it preserves the
    caller's order, which is usually meaningful.

    Delete this and the dropdown is populated with `SELECT name FROM department`."""
    offered = offerable(["maintenance", "finance", "sales"], reachable=["sales", "maintenance"])

    assert offered == ("maintenance", "sales")
    assert "finance" not in offered

    assert offerable([], reachable=["sales"]) == ()
    assert offerable(["sales"], reachable=[]) == ()


# --- the owner's five specific requirements ------------------------------------------------


def test_every_screen_can_be_narrowed_to_a_department_and_to_a_person() -> None:
    """The requirement as stated: everything filterable by department and person. It is a
    property of every screen rather than a page of its own, and it is only true if the filter
    is the same object everywhere.

    Asserted over the whole registry, so a screen added later cannot opt out by omission.

    Delete this and the thirty-fifth screen ships with `axes={Axis.PERIOD}` and the shared
    filter silently does nothing on it."""
    for one in SCREENS:
        assert one.axes >= EVERYWHERE, one.key


def test_a_screen_refuses_a_filter_it_cannot_honour() -> None:
    """A filter silently dropped is worse than one refused: the reader believes they are
    looking at one agent and are looking at all of them.

    Delete this and `accepts` becomes decoration, and a lens carrying an axis a screen does
    not know about narrows nothing while the control shows it selected."""
    connections = screen("connections")

    assert connections.accepts(Lens(department="maintenance", person="u_ann")) is True
    assert connections.accepts(Lens(agent="a_reporter")) is False

    runs = screen("runs")
    assert runs.accepts(Lens(agent="a_reporter", connector="hubspot")) is True
    assert runs.accepts(Lens()) is True


def test_the_registry_answers_each_thing_the_owner_asked_for() -> None:
    """The five named requirements, each pinned to a screen key so that renaming one is a
    failure rather than a silent removal: a company overview, all activity, budget and spend,
    a global stop, and the staff-source choice.

    Asserted by key and by group rather than by title, because a title is copy and will be
    edited, while a key is an address other code holds.

    Delete this and a refactor drops one of the five and nothing says so until it is asked
    for again."""
    for key, group in (
        ("overview", Group.OPERATE),
        ("audit", Group.GOVERN),
        ("budget", Group.REPORT),
        ("halt", Group.OPERATE),
        ("staff_sources", Group.GOVERN),
    ):
        assert screen(key).group is group

    assert screen("halt").read.requires == Capability(value="admin:halt")
    assert Axis.PERIOD in screen("budget").axes


def test_the_stop_screen_is_the_only_one_that_is_not_a_read() -> None:
    """Every other screen requires a `read:` capability. The stop button requires `admin:`,
    because pressing it changes the system rather than describing it, and a console where the
    one destructive control sits behind a read grant is a console where anybody who can look
    can also stop the company.

    Delete this and `admin:halt` is softened to `read:halt` the first time somebody cannot
    see the screen."""
    verbs = {one.key: one.read.requires.value.split(":", 1)[0] for one in SCREENS}

    assert verbs["halt"] == "admin"
    assert sorted(key for key, verb in verbs.items() if verb == "admin") == ["halt"]
    assert {verb for key, verb in verbs.items() if key != "halt"} <= {"read", "approve"}


# --- a department admin is not a smaller super admin ----------------------------------------


def test_a_department_admin_does_not_get_the_screens_about_the_installation() -> None:
    """Narrower rows are handled by the scope. What the scope does not handle is a screen whose
    subject is the deployment: the backup, the release, the connection budget. Narrowed to a
    department each is either empty, which is confusing, or unnarrowed, which is a leak.

    The positive half matters more than the negative: a department admin still gets most of the
    console, so this is not passing because `for_department` returns little.

    Delete this and either the install screens appear in a department menu or somebody removes
    them by hand from the renderer, where the next screen will be forgotten."""
    everything = every_capability()

    theirs = {one.key for one in for_department(everything)}
    ours = {one.key for one in navigation(everything)}

    assert theirs < ours
    assert "recovery" not in theirs
    assert "connections" not in theirs
    assert "install" not in theirs

    assert "people" in theirs
    assert "usage" in theirs
    assert "halt" in theirs
    assert len(theirs) > len(ours) / 2


def test_for_department_narrows_a_menu_and_never_widens_one() -> None:
    """It is a menu decision and not an authorisation: a caller reaches a screen by its address
    on the strength of their grants whatever this returns. What it must never do is return a
    screen `navigation` withheld.

    Delete this and a filter written as a difference could be inverted into a union, which
    would put the install screens into exactly the menu they were removed from."""
    for held in (every_capability(), holding("read:overview"), holding("read:backup")):
        assert set(for_department(held)) <= set(navigation(held))


# --- the registry keeps its own shape -------------------------------------------------------


def test_every_screen_is_registered_once_and_the_count_is_pinned() -> None:
    """The count is a constant compared against the registry rather than against itself, which
    is the trap this repository fell into three times in one afternoon: a test asserting
    `len(SCREENS) == len(SCREENS)` is green for every value it could hold.

    Delete this and a screen lost in a merge is noticed when somebody looks for it."""
    keys = [one.key for one in SCREENS]

    assert len(keys) == len(set(keys))
    assert len(SCREENS) == SCREEN_COUNT == 34
    assert len({one.read.tool for one in SCREENS}) == SCREEN_COUNT


def test_a_screen_whose_read_audits_a_different_screen_cannot_be_constructed() -> None:
    """A read carries the screen name into the audit row. Wired to the wrong one, every access
    to this screen is recorded against another, and the ledger says a person opened a page they
    never did.

    Delete this and a copied registry entry keeps the tool it was copied from."""
    with pytest.raises(ValueError, match="audits itself"):
        Screen(
            key="mine",
            title="Mine",
            group=Group.OPERATE,
            read=ConsoleRead(
                screen="somebody_elses",
                tool="console.mine",
                requires=Capability(value="read:run"),
                plane=Plane.EXISTENCE,
            ),
            axes=EVERYWHERE,
            intended_for=frozenset({Role.SUPER_ADMIN}),
            purpose="a screen wired to another screen's read",
        )


def test_a_screen_with_no_axes_cannot_be_constructed() -> None:
    """A screen nobody can filter shows everything it has to whoever opens it, and no shared
    filter can do anything about it.

    Delete this and `axes=frozenset()` is what an entry looks like while somebody is still
    deciding, and it ships."""
    with pytest.raises(ValueError, match="declares no axes"):
        Screen(
            key="mine",
            title="Mine",
            group=Group.OPERATE,
            read=ConsoleRead(
                screen="mine",
                tool="console.mine",
                requires=Capability(value="read:run"),
                plane=Plane.EXISTENCE,
            ),
            axes=frozenset(),
            intended_for=frozenset({Role.SUPER_ADMIN}),
            purpose="a screen nobody can narrow",
        )


def test_every_screen_explains_itself() -> None:
    """A menu entry with no sentence behind it is a word somebody has to guess the meaning of,
    and the person guessing is usually the one who has to explain the console to a client.

    Delete this and half the registry ships with `purpose=""` because the constructor allows
    it."""
    for one in SCREENS:
        assert len(one.purpose.split()) >= 8, one.key
        assert one.title
        assert one.read.tool.startswith("console.")
