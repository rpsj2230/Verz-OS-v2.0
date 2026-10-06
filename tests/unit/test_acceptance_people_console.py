"""The Govern screens' install checks: each passing on PostgreSQL at head, and each failing.

The database half runs the module as the worker does, with the install's issuer set, and every
check passes and leaves nothing behind. Then each is shown failing with the product broken the way
it would plausibly break: a grant written wider than the grantor's scope, a department retired from
under a live grant, a pack's capability removed on its own, a role holder shown to everybody, a
structure change nobody is recorded as making.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.3.2, M27.11.1, M27.15.22, M27.7.3, M27.7.7, M27.15.20, M27.15.24, M27.11.3, M27.7.5,
M27.15.19
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_people_console as console_checks
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_people_console"
STRUCTURE = "departments_teams_and_scopes_are_shaped_from_the_console"
GRANTS = "a_capability_is_granted_and_removed_within_the_grantor_s_scope"
PACKS = "a_pack_is_written_assigned_and_removed_only_whole"
ROLES = "roles_are_appointed_over_a_scope_and_shown_where_holders_sit"
BY_HAND = "a_person_added_by_hand_signs_in_and_holds_their_grant"


def test_the_people_console_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [STRUCTURE, GRANTS, PACKS, ROLES, BY_HAND]


def test_each_check_closes_the_leaves_its_flow_exercises() -> None:
    """Delete this and a check can lose or gain a leaf with the page showing the same rows, so a
    leaf closes on a check that never drove its route."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        STRUCTURE: ("M27.11.1", "M27.3.2", "M27.15.22"),
        GRANTS: ("M27.7.3", "M27.7.7"),
        PACKS: ("M27.15.24", "M27.15.20", "M27.11.3"),
        ROLES: ("M27.7.5", "M27.11.3"),
        BY_HAND: ("M27.15.19",),
    }


def test_the_capabilities_granted_are_ones_an_administrator_holds_and_one_nobody_does() -> None:
    """The checks grant what an administrator is granted at appointment, and test a wider grant
    with a capability no administrator holds. Held against `brain.identity.first_administrator`
    rather than against this module's own constants: delete this and a change to what an
    administrator holds turns the grant check's refusal into a refusal of everything."""
    from brain.identity.first_administrator import GRANTED_AT_APPOINTMENT

    assert console_checks.GRANTED in GRANTED_AT_APPOINTMENT
    assert set(console_checks.PACK_SECOND) <= set(GRANTED_AT_APPOINTMENT)
    assert set(console_checks.PACK_FIRST) < set(console_checks.PACK_SECOND)
    assert console_checks.NOBODY_HERE_HOLDS not in GRANTED_AT_APPOINTMENT


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_people") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str, *names: str) -> dict[str, tuple[str, str]]:
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    return run_check(url, checks)


def failed(url: str, name: str) -> str:
    [(outcome, reason)] = run(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_people_console_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """**The module as the worker runs it.** Every check passes and nothing a check wrote is left.
    Delete this and a check that can never pass on a real schema, or one that commits a grant,
    reaches the owner's server first."""
    before = counts(install)
    outcomes = run(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 5
    assert counts(install) == before


@pytest.mark.needs_db
def test_the_hand_added_person_is_not_run_beside_a_staff_list(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An install reading a staff list refuses the addition, which the check sees and then says it
    was not run. Delete this and M27.15.19 closes on an install where nobody can be added by hand,
    or reads red there when nothing is wrong."""
    monkeypatch.setenv("INSTALL_STAFF_SOURCE", "lark")
    assert run(install, BY_HAND) == {BY_HAND: (NOT_RUN, console_checks.A_STAFF_LIST_IS_READ_HERE)}


def _break(monkeypatch: pytest.MonkeyPatch, target: Any, name: str, value: Any) -> None:
    monkeypatch.setattr(target, name, value)


@pytest.mark.needs_db
def test_a_grant_written_wider_than_the_grantor_fails_the_grant_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`write_grant` waving every proposal through, as a route asking no authority would. Delete
    this and M27.7.7 closes on a check a grant over another department passes."""
    from brain import govern_routes

    monkeypatch.setattr(govern_routes, "write_grant", lambda proposed, reach, now: proposed)
    assert "wider" in failed(install, GRANTS)


@pytest.mark.needs_db
def test_a_department_retired_from_under_a_grant_fails_the_structure_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No grant ever holding a retirement back. Delete this and M27.15.22 closes on a check a
    department retired under a live grant passes."""
    from brain import govern_people_routes

    monkeypatch.setattr(govern_people_routes, "holds_retirement_back", lambda scope, **_: False)
    assert "live grant" in failed(install, STRUCTURE)


@pytest.mark.needs_db
def test_a_pack_capability_removed_unnamed_fails_the_pack_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The removal refusing a pack's capability with the ordinary sentence, as it did before
    M27.15.20. Delete this and that leaf closes on a refusal that names nothing."""
    from brain import govern_routes

    monkeypatch.setattr(govern_routes, "pack_shown", lambda *args: None)
    assert "naming it" in failed(install, PACKS)


@pytest.mark.needs_db
def test_a_role_holder_shown_to_everybody_fails_the_roles_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every holder shown to every reader of Roles. Delete this and M27.7.5 closes on a holder
    listing that narrows nothing."""
    from brain import govern_role_routes

    monkeypatch.setattr(govern_role_routes, "role_holders", lambda placed, reach, now: placed)
    assert "outside their department" in failed(install, ROLES)


@pytest.mark.needs_db
def test_a_person_added_outside_the_adders_department_fails_the_by_hand_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`may_add_person` admitting anybody. Delete this and M27.15.19 closes on a check that never
    saw the addition bounded by where the adder governs."""
    from brain import directory_routes

    monkeypatch.setattr(directory_routes, "may_add_person", lambda reach, **_: True)
    assert "does not govern" in failed(install, BY_HAND)
