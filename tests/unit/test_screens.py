"""The screen registry held to the five rules that stop it becoming a second permission model.

A menu is where a permission model gets a second opinion. It is the first thing anybody builds,
it is easiest to build from a role, and a menu built from roles disagrees with the gate in the
one direction nobody notices: the screen looks permitted and the tool behind it refuses.

The five leaves claimed here are the console security ones this module implements rather than
the screens it declares. The menu is computed from grants and never from a role (M27.5.6); it
publishes no count of what it withheld (M27.5.7); a filter dropdown is intersected with what
the caller already reaches (M27.5.8); every screen can be narrowed to a department and to a
person (M27.5.9); and a screen leaves a department's menu only when somebody has written down
what it would disclose there (M27.5.10). The screens themselves are declared and not built,
which `brain.console.screens` says in its own words and `unregistered_tools` says in figures.

**M27.5.10 changed meaning on 2026-09-09 and the tests below are where that is visible.** The
leaf reads "screens whose subject is the installation are not offered at department scope", and
five screens sat behind it on the argument that at a department's scope each was either empty
or a leak. The owner overruled the scoping: a department admin gets every screen the
requirements call for. Empty is not a reason to withhold a screen, because a scoped surface
that shows no rows has disclosed nothing and a missing menu heading has; a leak is. One screen
is left, and the test for it checks the argument against the module whose rows it cites rather
than taking the argument on trust.

Real `EntitlementSet`s throughout, and real `Screen`s wherever the registry is not itself the
thing under test. A test that stood a fixture in for either would be checking this module
against an agreement it had made with itself.

Task ids: M27.5.6, M27.5.7, M27.5.8, M27.5.9, M27.5.10
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.console import screens as screens_module
from brain.console.installation import _limit_row
from brain.console.reads import CONSOLE_CAPABILITY_PREFIX, ConsoleRead, Plane, plane_capability
from brain.console.screens import (
    EVERYWHERE,
    NOT_AT_DEPARTMENT_SCOPE,
    ONLY_THE_SCREENS,
    SCREEN_COUNT,
    SCREENS,
    WITHHELD_AT_DEPARTMENT_SCOPE,
    Axis,
    Disclosure,
    Group,
    Lens,
    Screen,
    for_department,
    grouped,
    navigation,
    offerable,
    screen,
    screen_gaps,
    unregistered_tools,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.roles import Role
from brain.ops.limits import Limit, LimitScope

REPO = Path(__file__).resolve().parents[2]

#: One rate limit, so the argument for withholding that screen can be checked against the row
#: form it cites rather than believed. A principal's own ceiling, which is the case
#: `A_RATE_LIMIT_NAMES_ITS_SUBJECT_AND_A_SUBJECT_IS_OFTEN_A_PERSON` is about.
A_LIMIT = Limit(
    scope=LimitScope.PRINCIPAL,
    subject="u_busy",
    period="minute",
    limit=30,
    window_seconds=60.0,
)

#: Inside the bound every entitlement below carries, and outside it. Both are after the day
#: this was written, so a `now` that is dropped on the way down rather than passed falls back
#: to a real clock that is inside the bound, and the expiry test fails rather than passing for
#: the wrong reason.
BEFORE_THE_BOUND = datetime(2027, 1, 1, tzinfo=UTC)
AFTER_THE_BOUND = datetime(2027, 6, 1, tzinfo=UTC)


def holding(
    *capabilities: str,
    planes: tuple[Plane, ...] = (Plane.CONTENT,),
    not_after: datetime | None = None,
) -> EntitlementSet:
    """A caller holding these capabilities company-wide, plus the plane grants named.

    Both halves are needed for a screen to be permitted: the tool's own capability and the
    console plane. Built here rather than taken from a fixture so a test can hold one and not
    the other, which is the case `permitted` exists for.
    """
    grants = [
        Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
    ]
    grants += [Grant(capability=plane_capability(one), scope=Scope(clauses=())) for one in planes]
    return EntitlementSet(principal_id="u_test", grants=tuple(grants), not_after=not_after)


def every_capability(not_after: datetime | None = None) -> EntitlementSet:
    """Somebody granted every capability the registry names, at the widest plane."""
    return holding(*[one.read.requires.value for one in SCREENS], not_after=not_after)


def a_screen(key: str, *, axes: frozenset[Axis]) -> Screen:
    """One screen built by a test, for handing to a diagnostic that reads the registry.

    The registry cannot produce the shapes two of those checks look for: `_screen` folds the
    required axes into every entry, and a literal tuple does not hold one key twice by
    accident. Building the broken shape here is what makes those branches watchable.
    """
    return Screen(
        key=key,
        title=key.replace("_", " ").title(),
        group=Group.OPERATE,
        read=ConsoleRead(
            screen=key,
            tool=f"console.{key}",
            requires=Capability(value="read:run"),
            plane=Plane.EXISTENCE,
        ),
        axes=axes,
        intended_for=frozenset({Role.SUPER_ADMIN}),
        purpose="a screen a test built so that a diagnostic has something to report on",
    )


# --- the menu is computed from grants and never from a role (M27.5.6) ------------------------


def test_the_menu_is_computed_from_grants_and_never_from_a_role() -> None:
    """**M27.5.6, and the rule this registry could most easily undo.** `brain.identity.roles`
    opens with "no role implies a capability, including Super Admin". A registry keyed by role
    breaks that in the least visible place: the menu shows the screen because of the role, the
    tool behind it refuses because of the grant, and the person reads a broken console rather
    than a boundary.

    Asserted on the signature rather than on behaviour, because behaviour can be right today
    and a parameter added tomorrow is what makes it wrong. The parameter list is pinned whole,
    so a name nobody thought to forbid is caught as well as the five that are.

    Delete this and `navigation(entitlement, role=...)` is a natural-looking convenience."""
    taken = inspect.signature(navigation).parameters

    assert list(taken) == ["entitlement", "now"]
    for forbidden in ("role", "roles", "is_admin", "super_admin", "override"):
        assert forbidden not in taken, forbidden


def test_a_screen_a_role_was_designed_for_stays_shut_to_somebody_holding_no_grant() -> None:
    """The behaviour beside the signature. Every screen names the roles it was drawn for, and a
    caller reaches none of them without grants: `intended_for` is documentation and nothing
    consults it.

    The positive half is the discriminating one. The same caller with the grants sees the whole
    registry, so this is not passing because `navigation` returns nothing to anybody.

    Delete this and `intended_for` can be wired into `navigation` with the signature check
    still green, because a set of roles could be derived from the entitlement rather than
    taken as a parameter."""
    assert all(one.intended_for for one in SCREENS)

    nothing = EntitlementSet(principal_id="u_test", grants=())

    assert navigation(nothing) == ()
    assert len(navigation(every_capability())) == SCREEN_COUNT


def test_a_screen_needs_the_console_plane_as_well_as_the_tools_own_capability() -> None:
    """Two grants, conjunctively. The tool's capability is what an agent making the same call
    would need; the plane is what the console adds. A caller holding every capability in the
    registry and no console grant reaches nothing, which is what makes the plane a grant
    somebody made rather than a label on a screen.

    The existence-only caller's menu is named rather than counted, so widening the plane check
    to admit configuration fails here with the screens it wrongly admitted.

    Delete this and `permitted` can be reduced to the capability check, and an auditor granted
    existence starts reading the two content screens."""
    no_plane = holding(*[one.read.requires.value for one in SCREENS], planes=())
    existence_only = holding(
        *[one.read.requires.value for one in SCREENS], planes=(Plane.EXISTENCE,)
    )

    assert navigation(no_plane) == ()
    assert {one.key for one in navigation(existence_only)} == {
        "access_friction",
        "artifacts",
        "knowledge_coverage",
        "library",
        "overview",
        "questions",
    }


def test_a_menu_is_empty_once_the_callers_entitlement_has_expired() -> None:
    """An expired principal holds nothing, whatever the grant table still says, and the menu
    has to ask at the moment of the request rather than at the moment the set was built. The
    clock is a parameter here for the reason `brain.ops.limits` gives about policy that owns a
    client.

    Both bounds are in the future, so a `now` dropped on the way to `permitted` falls back to a
    real clock inside the bound and this fails rather than passing by accident.

    Delete this and `navigation` stops passing `now` down, and a contractor's console keeps
    working after their last day."""
    bounded = every_capability(not_after=BEFORE_THE_BOUND)

    assert len(navigation(bounded)) == SCREEN_COUNT
    assert navigation(bounded, AFTER_THE_BOUND) == ()
    assert for_department(bounded, AFTER_THE_BOUND) == ()


def test_the_menu_comes_back_in_registry_order_because_that_order_is_the_menu() -> None:
    """The order inside a group is the order somebody reads the menu in, which is why the
    registry is a tuple and not a mapping. A menu re-sorted by key would put Activity above
    Company overview and read as an index rather than as a console.

    The three-screen case discriminates: alphabetical would be audit, budget, overview, and the
    order the capabilities were granted in would be another again.

    **The sections are flattened and compared too, because a sort inside `grouped` survived a
    mutation run otherwise.** The menu the reader sees is the grouped one, so keeping the order
    in `navigation` and losing it one call later is the same failure with a longer path to it.
    The registry is written in group order, so the flattened sections are the registry exactly,
    and a group reordered in the enum fails here as well.

    Delete this and the registry can become a dict, and the menu order becomes whatever the
    renderer sorted by."""
    granted = holding("read:budget", "read:audit", "read:overview")

    assert [one.key for one in navigation(every_capability())] == [one.key for one in SCREENS]
    assert [one.key for one in navigation(granted)] == ["overview", "audit", "budget"]

    sections = grouped(navigation(every_capability()))

    assert [one.key for _, inside in sections for one in inside] == [one.key for one in SCREENS]


def test_screen_gaps_reports_a_navigation_that_could_be_told_who_is_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The signature check inside the diagnostic, watched. Patching `navigation` for one that
    takes a role is how this test says what the broken module would look like without requiring
    one, which is the technique `test_console_reads` reached for on the same shape of check.

    Delete this and the check inside `screen_gaps` can be removed with every other test in this
    file still green, because they all call the diagnostic on a healthy module."""

    def told_who_is_asking(
        entitlement: EntitlementSet, role: Role, now: Any = None
    ) -> tuple[Screen, ...]:
        return SCREENS

    monkeypatch.setattr(screens_module, "navigation", told_who_is_asking)

    gaps = screens_module.screen_gaps()

    assert any("a screen can appear because of who somebody is" in one for one in gaps), gaps


# --- no count of what the menu withheld (M27.5.7) --------------------------------------------


def test_the_menu_returns_the_screens_and_no_second_value() -> None:
    """**M27.5.7.** "Three more sections" is a count of things this person may not see, and a
    count is the disclosure by subtraction the whole system is built to refuse.

    Asserted three ways, because the interesting failure is a second value appearing rather
    than a wrong count. The annotation the diagnostic compares against is pinned to the class
    it names, the live annotation is pinned to that constant, and the value that comes back is
    checked for being screens and nothing else. Pinning the constant to `Screen.__name__` is
    what stops this comparing a constant against itself, which would be green for every value
    the constant could hold.

    Delete this and `tuple[tuple[Screen, ...], int]` passes the diagnostic by moving the
    constant with it, and "and 12 more" becomes a reasonable-looking menu affordance."""
    assert f"tuple[{Screen.__name__}, ...]" == ONLY_THE_SCREENS
    assert str(inspect.signature(navigation).return_annotation) == ONLY_THE_SCREENS

    menu = navigation(holding("read:overview", "read:audit"))

    assert [type(one) for one in menu] == [Screen, Screen]


def test_screen_gaps_reports_a_navigation_that_hands_back_a_count_beside_the_screens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the same guard, watched. The check compares against the one annotation
    that is correct rather than searching for the words that would be wrong, because the list
    of ways to spell "and also the hidden count" is open and the list of acceptable return
    types has one entry.

    Delete this and the return check can go, and the next return type is whatever somebody
    needed for a badge on the menu."""

    def with_a_count(
        entitlement: EntitlementSet, now: Any = None
    ) -> tuple[tuple[Screen, ...], int]:
        return SCREENS, 0

    monkeypatch.setattr(screens_module, "navigation", with_a_count)

    gaps = screens_module.screen_gaps()

    assert any("a description of what it withheld" in one for one in gaps), gaps


def test_an_empty_section_is_absent_rather_than_shown_empty() -> None:
    """A heading reading Govern with nothing under it tells the reader there are governance
    screens they may not open, which is the same subtraction in a different shape.

    The positive half: a caller who reaches one screen in a group gets that group with the
    screen in it, and a caller who reaches everything gets all four headings, so this is not
    passing because `grouped` returns nothing.

    Delete this and the renderer iterates `Group` and prints four headings whatever the caller
    holds."""
    sections = grouped(navigation(holding("read:overview")))

    assert [group for group, _ in sections] == [Group.OPERATE]
    assert [one.key for _, inside in sections for one in inside] == ["overview"]

    assert [group for group, _ in grouped(navigation(every_capability()))] == list(Group)
    assert grouped(()) == ()


def test_a_department_menu_carries_no_heading_for_the_screens_it_leaves_out() -> None:
    """The two rules meeting. `grouped` drops a section with nothing left in it, so a screen
    withheld from a department's menu cannot leave a heading behind announcing the screens
    under it.

    A department admin now reaches all four headings, because three of the four Install screens
    are theirs. The discriminating case is therefore a caller whose only Install grant is the
    one withheld screen: their department menu has no Install heading, and their general menu
    does.

    Delete this and the department console grows a heading with nothing under it, which is the
    count of hidden things written as a word instead of as a number."""
    everything = every_capability()

    assert [group for group, _ in grouped(for_department(everything))] == list(Group)

    only_the_withheld = holding("read:rate_limit")

    assert [group for group, _ in grouped(navigation(only_the_withheld))] == [Group.INSTALL]
    assert grouped(for_department(only_the_withheld)) == ()


# --- a filter list is itself a listing (M27.5.8) ---------------------------------------------


def test_a_filter_offers_only_the_values_the_caller_can_already_reach() -> None:
    """**M27.5.8, and the disclosure everybody forgets.** Every screen here can be narrowed by
    department, so every screen carries a dropdown of departments. Populated from the table it
    names every department in the company, on a screen whose rows were carefully scoped, and
    nobody reviewing the rows would think to look at the filter.

    The three orders differ on purpose, and none of them is alphabetical. The caller's order is
    preserved because it is usually meaningful, most recent or most used, and re-sorting would
    discard it. Returning the reachable values instead of the intersection, and sorting the
    answer, both fail here rather than passing on lists that happened to agree.

    Delete this and the dropdown is populated with select name from department."""
    offered = offerable(["sales", "finance", "maintenance"], ["maintenance", "sales"])

    assert offered == ("sales", "maintenance")


def test_a_filter_invents_no_option_and_reports_no_count_of_what_it_dropped() -> None:
    """The two failures either side of the intersection. A value the caller reaches but the
    screen never offered must not be added, and the count of what was dropped must not come
    back beside the values: a dropdown reading "3 of 47" is the subtraction in a control nobody
    reviews.

    The positive sibling is above. Without it, a function returning an empty tuple for
    everything passes this, and a console with no working filters passes both.

    Delete this and `offerable` grows a second return value the first time somebody wants to
    show that a filter was narrowed."""
    assert offerable(["maintenance"], ["maintenance", "finance"]) == ("maintenance",)
    assert offerable([], ["sales"]) == ()
    assert offerable(["sales"], []) == ()

    assert str(inspect.signature(offerable).return_annotation) == "tuple[str, ...]"


# --- every screen narrows to a department and to a person (M27.5.9) --------------------------


def test_every_screen_can_be_narrowed_to_a_department_and_to_a_person() -> None:
    """**M27.5.9, as the owner stated it: everything filterable by department and by person.**
    It is a property of every screen rather than a page of its own, and it is only true if the
    filter is the same object everywhere.

    The two axes are named as enum members rather than taken from `EVERYWHERE`, and
    `EVERYWHERE` is pinned to them separately. Asserting `EVERYWHERE <= one.axes` on its own is
    the constant compared against itself: emptying the constant empties both sides, `_screen`
    then folds nothing into any entry, and the whole registry passes. That mutation survived
    the first version of this file.

    Delete this and the thirty-fifth screen ships with `axes={Axis.PERIOD}` and the shared
    filter silently does nothing on it."""
    assert frozenset({Axis.DEPARTMENT, Axis.PERSON}) == EVERYWHERE

    for one in SCREENS:
        assert Axis.DEPARTMENT in one.axes, one.key
        assert Axis.PERSON in one.axes, one.key


def test_the_lens_can_narrow_on_every_axis_the_vocabulary_has() -> None:
    """One vocabulary shared by every screen, and a lens that can express all of it. The
    mapping inside `axes_used` is written out by hand, so an axis added to the enum and to the
    lens and forgotten there is a filter the reader sets and no screen ever refuses: silently
    dropped, which is the failure `accepts` exists to prevent.

    The field names and the axis values are compared as sets, so a sixth axis with no field and
    a sixth field with no axis both fail here.

    Delete this and a new axis reaches `accepts` as one no lens reports using, and every screen
    accepts a narrowing it cannot honour."""
    assert {one.name for one in dataclass_fields(Lens)} == {one.value for one in Axis}

    narrowed = {
        Axis.DEPARTMENT: Lens(department="maintenance"),
        Axis.PERSON: Lens(person="u_ann"),
        Axis.AGENT: Lens(agent="a_reporter"),
        Axis.CONNECTOR: Lens(connector="hubspot"),
        Axis.PERIOD: Lens(period="7d"),
    }

    assert set(narrowed) == set(Axis)
    for axis, lens in narrowed.items():
        assert lens.axes_used() == frozenset({axis}), axis

    assert Lens().axes_used() == frozenset()
    assert Lens(department="   ").axes_used() == frozenset()


def test_a_screen_refuses_a_lens_it_cannot_honour_and_accepts_one_it_can() -> None:
    """A filter silently dropped is worse than one refused: the reader believes they are
    looking at one agent and is looking at all of them.

    Capacity is the discriminating screen. It carries the two axes every screen has and nothing
    else, so a lens narrowing by agent is refused there and accepted on Live runs, which
    declares that axis.

    Delete this and `accepts` becomes decoration, and a lens carrying an axis a screen does not
    know about narrows nothing while the control shows it selected."""
    connections = screen("connections")
    runs = screen("runs")

    assert connections.accepts(Lens(department="maintenance", person="u_ann")) is True
    assert connections.accepts(Lens(agent="a_reporter")) is False

    assert runs.accepts(Lens(agent="a_reporter", connector="hubspot")) is True
    assert runs.accepts(Lens()) is True


def test_screen_gaps_reports_a_screen_that_cannot_be_narrowed_to_a_department(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The registry check, watched. `_screen` folds the two required axes into every entry, so
    the branch cannot fire on the real registry and would be a diagnostic reporting on this
    module rather than on anything anybody could hand it. Patching the registry is how it
    becomes watchable, and both are kept because they say different things: the test above is
    about the screens as they are, and this is what the check would report if one were built by
    hand.

    Delete this and the check goes back to being a branch nothing can reach."""
    monkeypatch.setattr(
        screens_module, "SCREENS", (a_screen("lonely", axes=frozenset({Axis.PERSON})),)
    )

    gaps = screens_module.screen_gaps()

    assert [one for one in gaps if one.startswith("lonely cannot be filtered by")], gaps
    assert any("['department']" in one for one in gaps), gaps


def test_screen_gaps_reports_a_screen_registered_under_a_key_another_already_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other registry check, watched the same way. Two entries under one key means one of
    them is unreachable through `screen`, and the one that answers is whichever was written
    first, which is not a decision anybody made.

    Delete this and a copied registry entry keeps its key, the copy is dead, and the menu shows
    both."""
    twice = a_screen("overview", axes=EVERYWHERE)
    monkeypatch.setattr(screens_module, "SCREENS", (twice, twice))

    gaps = screens_module.screen_gaps()

    assert [one for one in gaps if one.startswith("overview is registered twice")], gaps


# --- a screen leaves a department's menu only with an argument (M27.5.10) --------------------


def test_a_department_admin_is_offered_every_screen_but_the_one_that_would_disclose() -> None:
    """**M27.5.10, as the owner decided it on 2026-09-09.** The leaf says screens whose subject
    is the installation are not offered at department scope, and the reading that put five
    screens behind it conflated "empty at that scope" with "a leak at that scope". Only the
    second is a reason: a screen that renders empty has said the rows this reader may see are
    none, and withholding it instead is the subtraction disclosure.

    The withheld key is written out here rather than read from `WITHHELD_AT_DEPARTMENT_SCOPE`,
    which is derived from the same list the function reads: taking it from there would pass for
    any list at all. The constant is then pinned against the difference.

    The positive half is the decision. Thirty-three of the thirty-four screens are a department
    admin's, including the four that used to be withheld, so this is not passing because
    `for_department` returns everything either.

    Delete this and the four screens the owner asked for go back behind a flag, or the one that
    cannot be rendered at that scope joins them with no argument written down."""
    everything = every_capability()

    ours = {one.key for one in navigation(everything)}
    theirs = {one.key for one in for_department(everything)}

    assert ours - theirs == {"limits"}
    assert set(WITHHELD_AT_DEPARTMENT_SCOPE) == ours - theirs
    assert len(theirs) == 33
    assert {"install", "recovery", "connections", "staff_sources"} <= theirs
    assert {"people", "usage", "halt", "audit", "agents"} <= theirs


def test_for_department_can_only_narrow_the_menu_navigation_gave_it() -> None:
    """It is a menu decision and not an authorisation: a caller holding `read:rate_limit`
    reaches that screen by its address whatever this returns, because the tool decides that and
    `installation.throttled_now` narrows the rows. What it must never do is return a screen
    `navigation` withheld.

    Asserted over three callers, one of whose only grant is for the screen this drops, so the
    empty answer is one of the cases rather than the only one.

    Delete this and a filter written as a difference could be inverted into a union, which
    would put the withheld screen into exactly the menu it was taken out of."""
    for held in (every_capability(), holding("read:overview"), holding("read:rate_limit")):
        assert set(for_department(held)) <= set(navigation(held))

    assert for_department(holding("read:rate_limit")) == ()
    assert [one.key for one in navigation(holding("read:rate_limit"))] == ["limits"]

    assert [one.key for one in for_department(holding("read:backup"))] == ["recovery"]


def test_a_screen_is_withheld_only_by_naming_the_disclosure_the_row_form_and_the_fix() -> None:
    """The shape that replaced the flag. A screen cannot leave a department's menu without
    somebody answering three questions, and the middle one is the load-bearing one: naming the
    row form means a reviewer can open that module, read the row a grant's scope is matched
    against, and disagree.

    The rate limits argument is checked against the module it cites rather than taken on trust.
    `brain.ops.limits.LimitScope` really has no department member, so a department-scoped grant
    really does match no throttling row, and that is what makes this the one screen that cannot
    be rendered at a department's scope.

    Delete this and a `Disclosure` can be written with three empty strings, which is
    `company_wide=True` with more typing."""
    assert [one.screen for one in NOT_AT_DEPARTMENT_SCOPE] == ["limits"]

    assert "department" not in {one.value for one in LimitScope}
    assert set(_limit_row(A_LIMIT)) == {"scope", "subject"}
    assert Scope.department("maintenance").matches(_limit_row(A_LIMIT)) is False

    for one in NOT_AT_DEPARTMENT_SCOPE:
        assert one.screen in {other.key for other in SCREENS}
        for sentence in (one.discloses, one.row_form, one.offered_when):
            assert len(sentence.split()) >= 8, one.screen

    with pytest.raises(ValueError, match="a flag with a longer name"):
        Disclosure(
            screen="install",
            discloses="it is about the deployment",
            row_form="there is no row",
            offered_when="never",
        )


def test_screen_gaps_reports_a_screen_withheld_from_a_department_that_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check that keeps the withheld list and the registry in step. A `Disclosure` naming a
    key nothing registers is an argument about a screen nobody can open, and the screen it was
    written for is being offered with nothing saying so.

    Patched rather than provoked on the real list, which agrees with the registry, so the branch
    is watchable at all.

    Delete this and renaming a screen key silently offers the one screen that cannot be
    rendered at a department's scope."""
    monkeypatch.setattr(
        screens_module,
        "NOT_AT_DEPARTMENT_SCOPE",
        (
            Disclosure(
                screen="rate_limits",
                discloses="the same sentence the real entry carries, about a key nobody holds",
                row_form="a row form named at the length the constructor insists on here",
                offered_when="a screen by this name exists, which is the point of the check",
            ),
        ),
    )

    gaps = screens_module.screen_gaps()

    assert [one for one in gaps if one.startswith("rate_limits is withheld")], gaps


# --- the registry keeps its own shape --------------------------------------------------------


def test_there_is_one_screen_for_every_screen_the_work_breakdown_names() -> None:
    """The module's opening claim, checked against the record rather than asserted. The console
    had four pages and the work breakdown named eighteen; both were lists somebody wrote down.
    They agree now, and this is what keeps them agreeing.

    Every group of M27 is counted, not only the four about screens, because a task id is
    positional: `M27.2.x` means the second group of M27 and nothing anchors it to a name. A
    group inserted rather than appended repoints all of them, which happened here on 2026-09-07
    and is why `CLAUDE.md` has a paragraph about it. Counting the whole module fails loudly on
    that edit instead of quietly counting four groups that have moved.

    Delete this and the registry and the work breakdown drift, and the tracker counts screens
    that were never declared while the console declares screens the tracker never named."""
    module = next(
        one
        for one in json.loads((REPO / "docs" / "wbs.json").read_text(encoding="utf-8"))["modules"]
        if one["id"] == "M27"
    )

    per_group: dict[str, int] = {}
    for leaf in module["leaf_ids"]:
        group = leaf.rsplit(".", 1)[0]
        per_group[group] = per_group.get(group, 0) + 1

    assert per_group == {
        "M27.1": 6,  # telemetry, which is not a screen
        "M27.2": 8,  # operate
        "M27.3": 18,  # govern
        "M27.4": 4,  # report
        "M27.5": 10,  # console security: five leaves in reads.py and the five claimed here
        "M27.6": 4,  # install
    }

    counted = {group: sum(1 for one in SCREENS if one.group is group) for group in Group}

    assert counted == {
        Group.OPERATE: per_group["M27.2"],
        Group.GOVERN: per_group["M27.3"],
        Group.REPORT: per_group["M27.4"],
        Group.INSTALL: per_group["M27.6"],
    }
    assert sum(counted.values()) == SCREEN_COUNT


def test_every_screen_is_registered_once_and_the_count_is_pinned() -> None:
    """The count is compared against a figure written here rather than against the registry it
    was computed from, which is the trap this repository fell into three times in one
    afternoon: `len(SCREENS) == len(SCREENS)` is green for every value it could hold.

    The tools are pinned as well as the keys, because two screens sharing a tool means one of
    them audits under the other's name.

    **And the constant is asserted to be a literal, which a comparison cannot do.** A mutation
    replacing `SCREEN_COUNT: Final = 34` with `len(SCREENS)` survived every assertion below,
    because the derived value equals the pin today and a test comparing two numbers cannot see
    where one of them came from. A pin that is computed from the registry it guards is the
    trap this docstring already warns about, arriving by a route the same docstring did not
    close: not `len(SCREENS) == len(SCREENS)` written out, but written once and read twice.

    So the declaration is read out of the source, the way
    `tests/invariants/test_single_implementation.py` reads its call sites: nothing else can
    tell a figure somebody committed to from one the code worked out.

    Delete this and a screen lost in a merge is noticed when somebody goes looking for it."""
    keys = [one.key for one in SCREENS]

    assert len(keys) == len(set(keys))
    assert len(SCREENS) == SCREEN_COUNT == 34
    assert len({one.read.tool for one in SCREENS}) == 34

    declared = ast.parse(Path(screens_module.__file__).read_text(encoding="utf-8"))
    pins = [
        node
        for node in ast.walk(declared)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "SCREEN_COUNT"
    ]

    assert len(pins) == 1, "one declaration, so there is one figure to disagree with"
    assert isinstance(pins[0].value, ast.Constant), (
        "SCREEN_COUNT is a number somebody wrote down. Computed from SCREENS it guards "
        "nothing, because the registry it is checked against is the registry it came from"
    )


def test_a_screen_is_found_by_its_key_and_an_unknown_key_is_refused() -> None:
    """A lookup rather than the mapping exported directly, because the registry's order is
    information and a mapping invites somebody to iterate it for the menu.

    The refusal is the sibling of the lookup and neither is useful alone: a function that
    raises for everything passes the second half and breaks every screen.

    Delete this and `screen` can return the first entry for any key at all, and every deep link
    opens the company overview."""
    found = screen("recovery")

    assert found.key == "recovery"
    assert found.read.tool == "console.recovery"
    assert found is next(one for one in SCREENS if one.key == "recovery")

    with pytest.raises(KeyError, match="no screen named"):
        screen("not_a_screen")


def test_a_screen_wired_to_another_screens_read_cannot_be_constructed() -> None:
    """A read carries the screen name into the audit row. Wired to the wrong one, every access
    to this screen is recorded against another, and the ledger says a person opened a page they
    never did.

    The sibling is the whole registry: every entry wires a read that audits itself, which is
    the state this constructor exists to keep.

    Delete this and a copied registry entry keeps the read it was copied from."""
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

    for one in SCREENS:
        assert one.read.screen == one.key


def test_a_screen_with_no_axes_and_a_screen_with_no_purpose_are_both_refused() -> None:
    """A screen nobody can filter shows everything it has to whoever opens it, and no shared
    filter can do anything about that. A screen with no sentence behind it is a word in a menu
    somebody has to guess the meaning of, and the guessing is done by whoever has to explain
    the console to a client.

    Both are the constructor refusing an entry that is still being written, which is the state
    in which both look reasonable.

    Delete this and `axes=frozenset()` and `purpose=""` are what an entry looks like while
    somebody is still deciding, and they ship."""
    read = ConsoleRead(
        screen="mine",
        tool="console.mine",
        requires=Capability(value="read:run"),
        plane=Plane.EXISTENCE,
    )

    def built(axes: frozenset[Axis], purpose: str) -> Screen:
        return Screen(
            key="mine",
            title="Mine",
            group=Group.OPERATE,
            read=read,
            axes=axes,
            intended_for=frozenset({Role.SUPER_ADMIN}),
            purpose=purpose,
        )

    with pytest.raises(ValueError, match="declares no axes"):
        built(frozenset(), "a screen nobody can narrow")

    with pytest.raises(ValueError, match="no purpose sentence"):
        built(EVERYWHERE, "   ")

    assert built(EVERYWHERE, "a screen that says what it is for").key == "mine"


def test_no_screen_leans_on_the_console_grant_instead_of_a_grant_over_what_it_reads() -> None:
    """A screen whose requirement is one of the three plane capabilities would be reachable by
    anybody trusted with the console, and the plane would be doing the work the tool's own
    grant should.

    Refused by `ConsoleRead` at construction, so this asserts the registry has none of them
    rather than re-testing the constructor, which `test_console_reads` holds.

    Delete this and a screen added with `read:console.content` looks correct and is open to
    every console user."""
    for one in SCREENS:
        assert not one.read.requires.value.startswith(CONSOLE_CAPABILITY_PREFIX), one.key

    with pytest.raises(ValueError, match="rather than a grant over what it reads"):
        ConsoleRead(
            screen="sneaky",
            tool="console.sneaky",
            requires=plane_capability(Plane.CONTENT),
            plane=Plane.CONTENT,
        )


def test_the_stop_screen_is_the_only_one_that_is_not_a_read() -> None:
    """Every other screen requires a read or an approval. The stop button requires `admin:`,
    because pressing it changes the system rather than describing it, and a console where the
    one destructive control sits behind a read grant is a console where anybody who can look
    can also stop the company.

    Delete this and `admin:halt` is softened to `read:halt` the first time somebody cannot see
    the screen they were told to press."""
    verbs = {one.key: one.read.requires.verb for one in SCREENS}

    assert sorted(key for key, verb in verbs.items() if verb == "admin") == ["halt"]
    assert {verb for key, verb in verbs.items() if key != "halt"} == {"read", "approve"}


def test_a_screen_designed_for_an_auditor_never_reads_the_content_plane() -> None:
    """`brain.identity.roles` says an auditor reads the metadata plane end to end, including
    Super Admin activity, and never the content. `intended_for` is documentation, so nothing
    enforces that at runtime, and a registry marking the memory viewer for auditors would be
    documentation contradicting the role it names.

    Both sets are named so the loop cannot be vacuous: some screens do name the auditor, and
    some screens are on the content plane.

    Delete this and Learning review is marked for auditors during a review round, and the
    console says a screen was designed for them that their role exists to keep them out of."""
    for one in SCREENS:
        if Role.AUDITOR in one.intended_for:
            assert one.read.plane is not Plane.CONTENT, one.key

    assert {one.key for one in SCREENS if Role.AUDITOR in one.intended_for} == {
        "access_friction",
        "audit",
        "capabilities",
        "exports",
        "people",
        "roles",
        "scopes",
    }
    assert {one.key for one in SCREENS if one.read.plane is Plane.CONTENT} == {"learning", "memory"}


def test_every_screen_explains_itself_in_a_sentence() -> None:
    """A menu entry with no sentence behind it is a word somebody has to guess the meaning of.

    The tool name is pinned to the key in the same pass, because a screen whose tool belongs to
    another screen is the audit row naming the wrong page, one layer further down than the
    constructor's own check.

    Delete this and half the registry ships with a three-word purpose, which the constructor
    allows because it only refuses an empty one."""
    for one in SCREENS:
        assert len(one.purpose.split()) >= 8, one.key
        assert one.title
        assert one.read.tool == f"console.{one.key}"


def test_screen_gaps_is_quiet_about_the_registry_as_it_stands() -> None:
    """The baseline for the four watched checks above, and on its own it proves nothing: an
    empty tuple is what a diagnostic returns whether its checks are there or not.

    Delete this and a real gap in the registry has no test that would notice it at all."""
    assert screen_gaps() == ()
    assert screen_gaps([one.read.tool for one in SCREENS]) == ()


def test_screen_gaps_reports_a_screen_wired_to_a_tool_no_registry_holds() -> None:
    """The check that takes an argument rather than reading a registry, so it can be exercised
    with the broken wiring, which is the only interesting case. A screen whose tool nobody
    registered has a capability check in front of a call that cannot be made, and that reads to
    the person as a permission problem.

    Delete this and the console ships screens wired to tools that do not exist, and the failure
    arrives as a refusal rather than as a missing tool."""
    every_tool = [one.read.tool for one in SCREENS]

    gaps = screen_gaps([one for one in every_tool if one != "console.halt"])

    assert [one for one in gaps if one.startswith("halt is wired to console.halt")], gaps
    assert len(gaps) == 1


def test_the_tools_these_screens_name_are_all_still_unwritten() -> None:
    """**The honest gap, asserted so it cannot be forgotten quietly.** The screens are declared
    before the tools behind them exist, deliberately, so the shape of the console can be argued
    about before thirty-four tools are written. Every one of them is unregistered today, which
    is why this module claims no screen leaf.

    Kept apart from `screen_gaps` because this one is expected to be red for a while, and a
    diagnostic that is red for a month is one somebody switches off.

    Delete this and the gap stops being visible, and the day the first console tool is written
    nobody notices that the other thirty-three are still declarations."""
    assert len(unregistered_tools([])) == SCREEN_COUNT
    assert unregistered_tools([one.read.tool for one in SCREENS]) == ()
    assert unregistered_tools(["console.overview"]) == tuple(
        one.read.tool for one in SCREENS if one.key != "overview"
    )


def test_the_registry_answers_each_thing_the_owner_asked_for() -> None:
    """The five named requirements, each pinned to a key and a group so that renaming one is a
    failure rather than a silent removal: a company overview, all activity, budget and spend, a
    global stop, and the staff-source choice.

    Asserted by key and by group rather than by title, because a title is copy and will be
    edited, while a key is an address other code holds.

    Delete this and a refactor drops one of the five and nothing says so until it is asked for
    again."""
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
