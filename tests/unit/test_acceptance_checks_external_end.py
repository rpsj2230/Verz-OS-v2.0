"""The external person install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M1.8.1
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_external_end"
ENDS = "an_external_person_stops_on_their_end_date"


def test_the_module_declares_its_leaf_and_runs_before_the_roll_ups_that_read_it() -> None:
    """One check closing M1.8.1, placed before the roll-up that waits for it. Delete this and the
    check can lose its leaf with the page showing the same row, or sit after the roll-up, which
    then never sees it."""
    from brain.ops import acceptance_checks_external_end as module
    from brain.ops import acceptance_checks_jml_roll_up as roll_up

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(ENDS, ("M1.8.1",))]
    assert checks_in(MODULE) == [ENDS]
    assert module.CHECK_ORDER < roll_up.CHECK_ORDER
    assert roll_up.CLAUSES["an external person stops on their end date"] == ("M1.8.1",)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_external_end") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str) -> str:
    outcome, reason = run(url)[ENDS]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_end_date_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and no person, grant or session is left. Delete
    this and a check that cannot pass on a real schema, or one that commits a contractor, ships."""
    before = counts(install)
    assert run(install) == {ENDS: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_reach_that_drops_the_end_date_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resolver's answer is read without the person's end date, so the set holds what it was
    given for ever. Delete this and M1.8.1 closes on a contractor who goes on holding their grant
    after they have gone."""
    from brain.gate import entitlement_store

    real = entitlement_store.entitlements_from

    def without_the_end(payload: Any) -> Any:
        return real(payload).model_copy(update={"not_after": None})

    monkeypatch.setattr(entitlement_store, "entitlements_from", without_the_end)
    assert "still held a grant after their end date" in _failed(install)


@pytest.mark.needs_db
def test_a_session_that_outlives_the_end_date_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session opened as though the engagement ran for another month. Delete this and M1.8.1
    closes on a contractor whose sign-in outlasts their engagement."""
    from datetime import timedelta

    from brain.identity import sessions

    real = sessions.open_session

    def a_month_longer(*, claims: Any, principal: Any, now: datetime, **kwargs: Any) -> Any:
        longer = principal.model_copy(update={"not_after": now + timedelta(days=30)})
        return real(claims=claims, principal=longer, now=now, **kwargs)

    monkeypatch.setattr(sessions, "open_session", a_month_longer)
    assert "outlived their end date" in _failed(install)


@pytest.mark.needs_db
def test_a_form_that_takes_a_contractor_with_no_end_date_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The form's body no longer asks the principal type whether the engagement is bounded. Delete
    this and M1.8.1 closes on a form that saves a contractor nobody will ever have to remove."""
    from brain import directory_routes

    monkeypatch.setattr(directory_routes, "Principal", lambda **kwargs: None)
    assert "the form took a contractor" in _failed(install)


@pytest.mark.needs_db
def test_a_table_that_keeps_a_contractor_with_no_end_date_fails_the_check(
    install: str, issuer: None
) -> None:
    """The table's own constraint is dropped. Delete this and M1.8.1 closes on a database that
    would keep an unbounded contractor if any writer other than the form sent one."""
    from tests.fixtures.scratch_postgres import sql

    [(name, definition)] = sql(
        install,
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'auth.principal'::regclass "
        "AND pg_get_constraintdef(oid) LIKE '%contractor%' "
        "AND pg_get_constraintdef(oid) LIKE '%not_after IS NOT NULL%'",
    )
    sql(install, f'ALTER TABLE auth.principal DROP CONSTRAINT "{name}"')
    try:
        assert "kept a contractor with no end date" in _failed(install)
    finally:
        sql(install, f'ALTER TABLE auth.principal ADD CONSTRAINT "{name}" {definition}')


@pytest.mark.needs_db
def test_a_person_who_stays_active_after_their_end_date_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The principal is judged active at any instant. Delete this and M1.8.1 closes on a chat
    binding that goes on resolving to a person whose engagement has ended."""
    from brain.core.principal import Principal

    monkeypatch.setattr(Principal, "is_active", lambda self, now=None: True)
    assert "active after their end date" in _failed(install)
