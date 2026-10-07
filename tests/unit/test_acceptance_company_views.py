"""The install checks for the Super Admin's view of the company, each passing on PostgreSQL at head
and each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes and leaves nothing. Then each is shown failing: an estate that ignores the department or
person filter, shows one department to another's reader or answers a named department
differently from an empty one, and an activity read whose lens does not narrow.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M33.1.1.1, M33.1.1.2, M33.2.1.3, M33.2.1.4, M33.1.2.3, M33.3.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_company_views"
ESTATE = "the_company_estate_narrows_by_department_person_and_kind"
ACTIVITY = "the_company_activity_narrows_to_a_department_and_to_a_person"
HEAD = "a_departments_head_reads_its_pace_and_its_knowledge_coverage"
NOMINATION = "a_role_nomination_is_confirmed_only_by_a_third_person"
EXPORT = "a_member_exports_their_own_conversation_and_nobody_elses"


def test_the_module_declares_one_check_per_company_read() -> None:
    """Five checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (ESTATE, ("M33.1.1.1",)),
        (ACTIVITY, ("M33.1.1.2",)),
        (HEAD, ("M33.2.1.3", "M33.2.1.4")),
        (NOMINATION, ("M33.1.2.3",)),
        (EXPORT, ("M33.3.1.3",)),
    ]


def test_the_company_views_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [ESTATE, ACTIVITY, HEAD, NOMINATION, EXPORT]


def test_the_module_stands_inside_the_range_this_package_was_given() -> None:
    """Eight hundred to eight hundred and ninety-nine, which two packages share only by taking
    different numbers. Delete this and a later edit can land on another package's key."""
    from brain.ops import acceptance_checks_company_views as module

    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_company_views") as url:
        yield url


@pytest.fixture(autouse=True)
def a_currency_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install's currency, which a department's pace is withheld without
    (`brain.console_overview_figures_routes.cost_recorded_in`). Delete this and the head's check
    says it was not run on every machine with no currency set, which is the empty state."""
    monkeypatch.setenv("INSTALL_CURRENCY", "USD")


def run_views(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_every_company_view_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All five pass and nothing a check wrote is left: no
    department, person, agent, document, ledger entry or export record. Delete this and a check
    that can never pass on a real schema, or one that leaves an agent behind, reaches the owner's
    server."""
    before = counts(install)
    outcomes = run_views(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 5
    assert counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_views(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_an_estate_that_ignores_its_lens_or_its_readers_reach_fails_the_estate_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The department and person filters dropped, then the reader's reach dropped (a kind kept).
    Delete this and M33.1.1.1 closes on a list that shows every department to everybody, or
    ignores the filters."""
    from brain import company_routes
    from brain.console.global_surfaces import visible_estate

    def unfiltered(rows: Any, reach: Any, *, lens: Any, kinds: Any, now: Any) -> Any:
        return visible_estate(rows, reach, now)

    with monkeypatch.context() as patched:
        patched.setattr(company_routes, "estate", unfiltered)
        assert "naming a department" in _failed(install, ESTATE)

    def unreached(rows: Any, reach: Any, *, lens: Any, kinds: Any, now: Any) -> Any:
        return tuple(
            one
            for one in rows
            if (not kinds or one.kind in tuple(kinds))
            and (not lens.department or one.where.get("department") == lens.department)
            and (not lens.person or one.where.get("owner_id") == lens.person)
        )

    monkeypatch.setattr(company_routes, "estate", unreached)
    assert "another department's rows" in _failed(install, ESTATE)


@pytest.mark.needs_db
def test_an_activity_lens_that_narrows_nothing_or_a_screen_open_to_anybody_fails(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lens never applied to the ledger or to what it loads, then the Activity screen's read
    given to every reader. Delete this and M33.1.1.2 closes on a lens that shows everything or a
    screen anybody may read."""
    from brain import company_routes

    def unlensed(
        view: Any,
        *,
        criteria: Any,
        limit: int,
        cursor: Any,
        newest_first: bool,
        shows: Any,
        **_: Any,
    ) -> Any:
        return view.page(
            criteria, limit=limit, cursor=cursor, newest_first=newest_first, shows=shows
        )

    with monkeypatch.context() as patched:
        patched.setattr(company_routes, "company_activity", unlensed)
        # The statement narrows by the same people before the view decides again, so a lens
        # broken in both places is the one a reader would be shown everything through.
        patched.setattr(company_routes, "activity_filter", lambda *args, **kwargs: frozenset())
        assert "naming a department" in _failed(install, ACTIVITY)
    monkeypatch.setattr(company_routes, "permitted", lambda *args, **kwargs: True)
    assert "without the Activity screen" in _failed(install, ACTIVITY)


@pytest.mark.needs_db
def test_a_department_page_open_to_anybody_or_reading_no_spend_fails_the_head_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everybody made a head of everything, then the department's spend read as nought. Delete
    this and M33.2.1.3 and M33.2.1.4 close on a page any member may open, or a pace that is
    always nil."""
    from brain import department_view_routes

    async def everyone_leads(session: Any, principal_id: str) -> tuple[str, ...]:
        return ("acceptance_a", "acceptance_b", "acceptance_nobody")

    async def nothing_spent(*args: Any, **kwargs: Any) -> int:
        return 0

    with monkeypatch.context() as patched:
        patched.setattr(department_view_routes, "_headed", everyone_leads)
        assert "does not lead the department" in _failed(install, HEAD)
    monkeypatch.setattr(department_view_routes, "_spent", nothing_spent)
    assert "day spend" in _failed(install, HEAD)


@pytest.mark.needs_db
def test_a_nomination_anybody_may_confirm_fails_the_nomination_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The confirmation authority given to every reader, nominator and nominee included. Delete
    this and M33.1.2.3 closes on a gate one person can pass alone."""
    from brain.console import global_surfaces

    monkeypatch.setattr(global_surfaces, "may_confirm", lambda *args, **kwargs: True)
    assert "confirmed a nomination" in _failed(install, NOMINATION)


@pytest.mark.needs_db
def test_an_export_with_no_record_or_no_words_fails_the_export_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record never written, then the file built from no turns. Delete this and M33.3.1.3
    closes on an export nobody can trace, or one that carries nothing."""
    from brain import thread_routes

    class Unrecorded:
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        async def record_report(self, **kwargs: Any) -> Any:
            return None

    with monkeypatch.context() as patched:
        patched.setattr(thread_routes, "StoredExports", Unrecorded)
        assert "no record" in _failed(install, EXPORT)
    monkeypatch.setattr(thread_routes, "turns_shown", lambda *args, **kwargs: ())
    assert "own question" in _failed(install, EXPORT)
