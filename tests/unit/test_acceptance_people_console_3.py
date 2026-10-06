"""The console's scope, approvals, elevation, review, own workspace and steward: install checks.

The database half runs the module as the worker does, with the install's issuer set: every check
passes and leaves nothing. Then each is shown failing with the product broken the way it would
plausibly break: a menu drawn from a role, installation screens offered at department scope, a
filter offering every department, an approval queued for nobody, an elevation of what is already
held, a review deciding outside its department, a workspace counting everybody's questions, and a
steward who is the administrator.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.5.6, M27.5.10, M27.7.29, M27.5.8, M27.15.63, M27.3.7, M27.9.3, M27.7.8, M27.7.9,
M27.7.28, M27.9.9
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_people_console_3 as third
from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_people_console_3"
MENU = "the_menu_follows_the_grants_and_never_the_role"
SCOPE = "a_department_reader_is_given_less_and_no_installation_screen"
FILTERS = "filters_offer_only_what_is_reached_and_refusals_say_no_why"
APPROVALS = "an_approval_waits_on_a_person_and_is_decided_once"
ELEVATION = "an_elevation_is_asked_for_given_and_lapses"
REVIEW = "a_department_lead_recertifies_what_their_people_hold"
WORKSPACE = "a_member_reads_their_own_workspace_and_no_administration"
STEWARD = "the_data_steward_holds_what_every_connected_source_declares"


def test_the_third_people_console_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [
        MENU,
        SCOPE,
        FILTERS,
        APPROVALS,
        ELEVATION,
        REVIEW,
        WORKSPACE,
        STEWARD,
    ]


def test_each_check_closes_the_leaves_its_flow_exercises() -> None:
    """Delete this and a check can lose or gain a leaf with the page showing the same rows."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        MENU: ("M27.5.6",),
        SCOPE: ("M27.5.10", "M27.7.29"),
        FILTERS: ("M27.5.8", "M27.15.63"),
        APPROVALS: ("M27.3.7", "M27.9.3"),
        ELEVATION: ("M27.7.8",),
        REVIEW: ("M27.7.9",),
        WORKSPACE: ("M27.7.28",),
        STEWARD: ("M27.9.9",),
    }


def test_the_installation_screens_are_the_ones_the_registry_withholds_from_a_department() -> None:
    """The screens the scope check expects to be absent, held against `brain.console.screens`
    rather than this module: the install group and the screens argued out of a department menu.
    Delete this and a screen moved into the install group is offered to departments unseen."""
    from brain.console.screens import SCREENS, WITHHELD_AT_DEPARTMENT_SCOPE, Group

    assert {one.key for one in SCREENS if one.group is Group.INSTALL} | set(
        WITHHELD_AT_DEPARTMENT_SCOPE
    ) == third.INSTALLATION_SCREENS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_people_3") as url:
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
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str, issuer: None) -> None:
    """**The module as the worker runs it.** Every check passes and nothing a check wrote is left.
    Delete this and a check that can never pass on a real schema, or one that commits a decision,
    an elevation or a steward, reaches the owner's server first."""
    before = counts(install)
    outcomes = run(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 8
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_menu_drawn_whatever_the_grants_fails_the_menu_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every screen permitted to everybody, as a menu built from a role would be. Delete this and
    M27.5.6 closes on a menu that never asked the grants."""
    from brain.console import screens

    monkeypatch.setattr(screens, "permitted", lambda read, entitlement, now=None: True)
    assert "no grant was offered" in failed(install, MENU)


@pytest.mark.needs_db
def test_installation_screens_offered_to_a_department_fail_the_scope_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every reader given the company console, whose menu holds the install's screens, whatever
    scope their grants are held in. Delete this and M27.5.10 closes on a department administrator
    offered the installation's screens."""
    from brain.console import department_console

    monkeypatch.setattr(
        department_console, "held_across_the_install", lambda found, entitlement, now=None: True
    )
    assert "department console" in failed(install, SCOPE)


@pytest.mark.needs_db
def test_a_filter_offering_every_department_fails_the_filters_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Scopes filter offering every department there is. Delete this and M27.5.8 closes on a
    dropdown that lists departments the reader cannot reach."""
    from brain import govern_routes

    monkeypatch.setattr(
        govern_routes, "departments_offered", lambda names, reach, now: tuple(names)
    )
    assert "cannot reach" in failed(install, FILTERS)


@pytest.mark.needs_db
def test_an_approval_queued_for_nobody_fails_the_approvals_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The queue reading nothing open. Delete this and M27.3.7 closes on an Approvals page that
    never showed what waits."""
    from brain.gate.suspension_store import ReachedSuspensions

    async def nothing(self: Any) -> tuple[()]:
        return ()

    monkeypatch.setattr(ReachedSuspensions, "open_suspensions", nothing)
    assert "approver only" in failed(install, APPROVALS)


@pytest.mark.needs_db
def test_an_elevation_of_what_is_held_fails_the_elevation_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filing waved through whatever the requester holds. Delete this and M27.7.8 closes on a
    request screen that files an elevation narrowing its requester."""
    from brain import govern_people_routes

    monkeypatch.setattr(govern_people_routes, "would_widen", lambda reach, capability, now: True)
    assert "already held" in failed(install, ELEVATION)


@pytest.mark.needs_db
def test_a_review_deciding_outside_its_department_fails_the_review_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every holding recertifiable by every reviewer, wherever its holder sits. Delete this and
    M27.7.9 closes on a review that lists and recertifies other departments' people."""
    from brain import govern_people_routes

    monkeypatch.setattr(govern_people_routes, "recertifiable", lambda grants, reach, now: grants)
    assert "lead's people" in failed(install, REVIEW)


@pytest.mark.needs_db
def test_a_workspace_counting_everybody_fails_the_workspace_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The questions count read for everybody rather than the reader. Delete this and M27.7.28
    closes on a page whose figures are not the reader's own."""
    from sqlalchemy import func, select

    from brain import mine_routes
    from brain.tables.adoption import QuestionAskedRow

    def everybody(principal_id: str, since: Any, until: Any) -> Any:
        return select(func.count()).select_from(QuestionAskedRow)

    monkeypatch.setattr(mine_routes, "questions_asked", everybody)
    assert "own questions" in failed(install, WORKSPACE)


@pytest.mark.needs_db
def test_a_steward_who_is_the_administrator_fails_the_steward_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The console naming whoever presses as the steward, whatever was typed. Delete this and
    M27.9.9 closes on data access that begins with the administrator by default."""
    from brain import data_steward_routes
    from brain.identity.data_steward import NamedSteward

    def the_caller(asked: Any, *, caller: str, minted: str) -> NamedSteward:
        return NamedSteward(principal_id=caller, display_name="", same_as_administrator=True)

    monkeypatch.setattr(data_steward_routes, "named_by", the_caller)
    assert "administrator" in failed(install, STEWARD)
