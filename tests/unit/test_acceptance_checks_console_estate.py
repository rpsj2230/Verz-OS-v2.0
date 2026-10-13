"""The install checks for what the install knows, passing on PostgreSQL at head, leaving nothing,
and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.7.20, M27.2.5
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_estate"
LIBRARY = "the_library_lists_every_department_with_each_items_reach"
COVERAGE = "a_head_is_shown_how_fresh_what_their_department_knows_is"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        LIBRARY: ("M27.7.20",),
        COVERAGE: ("M27.2.5",),
    }
    assert checks_in(MODULE) == [LIBRARY, COVERAGE]


def test_the_freshness_the_check_expects_is_the_document_horizons() -> None:
    """The three ages the coverage check verifies documents at sit inside the bands the document
    horizon draws, one in each. Delete this and a changed horizon fails the check on every install
    for a reason in the check."""
    from datetime import timedelta

    from brain.gate.provenance import DOCUMENT_HORIZON
    from brain.ops.acceptance_checks_console_estate import STALE_AGO, VERIFIED_AGO

    assert VERIFIED_AGO["live"] < DOCUMENT_HORIZON.live_for
    assert DOCUMENT_HORIZON.live_for < VERIFIED_AGO["ageing"] < DOCUMENT_HORIZON.stale_after
    assert DOCUMENT_HORIZON.stale_after + timedelta(days=30) < STALE_AGO


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_estate") as url:
        yield url


def _failed(url: str, name: str) -> str:
    outcome, reason = run_module(url, MODULE)[name]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** They pass and leave no person, grant, document or
    ledger entry. Delete this and a check that commits, or one that cannot pass on a real schema,
    reaches the owner's server first."""
    from tests.fixtures.scratch_postgres import sql

    before = counts(install)
    assert run_module(install, MODULE) == {LIBRARY: (PASSED, ""), COVERAGE: (PASSED, "")}
    assert counts(install) == before
    assert int(sql(install, "SELECT count(*) FROM know.item")[0][0]) == 0


@pytest.mark.needs_db
def test_a_library_that_lists_every_department_to_everybody_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A library whose rows are never narrowed to the reader's department. Delete this and
    M27.7.20 closes on a screen that tells a department's reader what the others hold."""
    from brain import estate_routes

    def everything(items: object, entitlement: object, now: object = None) -> tuple[object, ...]:
        from brain.console.govern_estate import LibraryRow

        return tuple(
            LibraryRow(
                item_id=one.record.item_id,
                level=one.record.visibility.level,
                kind=one.record.kind,
            )
            for one in items  # type: ignore[attr-defined]
        )

    monkeypatch.setattr(estate_routes, "library_rows", everything)
    assert "another's" in _failed(install, LIBRARY)


@pytest.mark.needs_db
def test_a_coverage_that_counts_everything_stale_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Freshness judged on a horizon that makes everything old. Delete this and M27.2.5 closes on
    a screen that counts a document verified last week as stale."""
    from datetime import timedelta

    from brain.console import scoped_authority
    from brain.gate.provenance import StalenessHorizon

    monkeypatch.setattr(
        scoped_authority,
        "DOCUMENT_HORIZON",
        StalenessHorizon(live_for=timedelta(seconds=1), stale_after=timedelta(seconds=2)),
    )
    assert "band" in _failed(install, COVERAGE)
