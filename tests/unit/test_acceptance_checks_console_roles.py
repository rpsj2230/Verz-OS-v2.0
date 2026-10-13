"""The install checks for the clauses of roles and administration that had none, passing on
PostgreSQL at head, leaving nothing, and failing with the product broken the way it would
plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.3
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_roles"
FLOOR = "the_floor_of_two_super_admins_holds_and_a_deputy_has_no_deputy"
WRITES = "a_console_write_names_the_writers_real_reach_and_trace"
LIBRARY = "a_library_reader_without_a_grant_sees_an_item_and_cannot_open_it"
ACCESS = "the_access_view_lists_exactly_what_the_resolver_gives"


def test_every_check_of_the_module_names_the_composite_leaf() -> None:
    """The four checks and the one leaf each closes. Delete this and a clause can lose M27.15.3,
    or the composite can close with a clause nobody checks."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == dict.fromkeys(
        (FLOOR, WRITES, LIBRARY, ACCESS), ("M27.15.3",)
    )
    assert checks_in(MODULE) == [FLOOR, WRITES, LIBRARY, ACCESS]


def test_the_other_checks_that_prove_a_clause_name_the_leaf_too() -> None:
    """The self-grant notice, the deputy's thirty days and the data steward are proved by checks
    written for narrower leaves, and each now names M27.15.3. Delete this and the composite closes
    on four clauses of seven."""
    named = {one.name for one in registered() if "M27.15.3" in one.leaves}
    assert {
        "a_steward_is_named_and_told_of_access_somebody_gave_themselves",
        "a_department_admin_appoints_a_deputy_for_thirty_days_at_most",
        "the_data_steward_holds_what_every_connected_source_declares",
    } <= named


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_roles") as url:
        yield url


@pytest.fixture(autouse=True)
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def _failed(url: str, name: str) -> str:
    outcome, reason = run_module(url, MODULE)[name]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** Each passes and leaves no role, grant or ledger
    entry, whatever Super Admins the install holds. Delete this and a check that commits the
    retirement of the install's own Super Admins reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == dict.fromkeys(
        (FLOOR, WRITES, LIBRARY, ACCESS), (PASSED, "")
    )
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_library_that_lets_a_reader_open_what_they_may_not_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read of knowledge that admits everybody. Delete this and M27.15.3 closes on a console where
    seeing that a document exists is seeing what it says."""
    from brain.knowledge.lifecycle import Authority

    monkeypatch.setattr(Authority, "may_read", lambda self, item: True)
    assert "could open a document" in _failed(install, LIBRARY)


@pytest.mark.needs_db
def test_a_console_write_that_names_no_reach_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write attributed to the placeholder reach. Delete this and M27.15.3 closes on a ledger
    that cannot say at what reach anything was done."""
    monkeypatch.setattr("brain.govern_routes.attribution", lambda asked: ())
    outcome, reason = run_module(install, MODULE)[WRITES]
    assert outcome == FAILED, reason


@pytest.mark.needs_db
def test_an_access_page_that_forgets_a_grant_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A page that lists only packs. Delete this and M27.15.3 closes on an Access view that
    disagrees with what the person reaches."""
    from brain import directory_routes

    real = directory_routes.HeldView

    def only_packs(**kwargs: object) -> object:
        made = real(**kwargs)  # type: ignore[arg-type]
        return made.model_copy(
            update={"capabilities": [] if made.kind == "grant" else made.capabilities}
        )

    monkeypatch.setattr(directory_routes, "HeldView", only_packs)
    assert "Access page" in _failed(install, ACCESS)
