"""The install checks for the console's reports and its long lists, each passing on PostgreSQL at
head and each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes and leaves nothing. Then each is shown failing: the landing screen counting everybody for a
reader of their own work, a usage grant read as reaching every department, the gaps shown to
anybody, the canaries' runs shown without the grant, an erasure filed by a reader without the
authority, and a list that ignores the page size or a bulk ending that ends what it may not.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.2.1, M27.7.14, M27.7.18, M27.7.19, M27.7.24, M27.8.6
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

MODULE = "brain.ops.acceptance_operations_console_3"
LANDING = "the_landing_screen_counts_honestly_for_its_reader"
USAGE = "usage_and_adoption_count_the_departments_a_reader_may_see"
GAPS = "a_question_nothing_answered_is_shown_to_its_department_s_reader"
CANARIES = "the_permission_canaries_last_run_is_shown_to_their_reader"
ERASURE = "an_erasure_is_filed_and_waits_in_the_deletion_queue"
LISTS = "a_long_list_pages_searches_sorts_and_acts_on_several"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Six checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (LANDING, ("M27.2.1",)),
        (USAGE, ("M27.7.14",)),
        (GAPS, ("M27.7.18",)),
        (CANARIES, ("M27.7.19",)),
        (ERASURE, ("M27.7.24",)),
        (LISTS, ("M27.8.6",)),
    ]


def test_the_operations_console_3_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [LANDING, USAGE, GAPS, CANARIES, ERASURE, LISTS]


def test_the_reports_read_grants_are_the_screens_own() -> None:
    """The capabilities the checks' readers hold, held against the screens that read them. Delete
    this and a renamed screen capability fails every report check on every install, with nothing
    wrong in the product."""
    from brain.console.screens import screen
    from brain.ops import acceptance_operations_console_3 as reports

    assert screen("usage").read.requires.value == reports.READS_USAGE
    assert screen("questions").read.requires.value == reports.READS_QUESTIONS
    assert screen("quality").read.requires.value == reports.READS_EVALUATION


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_ops_console_3") as url:
        yield url


def run_ops(url: str, *names: str) -> dict[str, tuple[str, str]]:
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


#: What these checks write beyond the suite's list.
ALSO_WRITTEN = ("ops.question_asked", "ops.question_gap", "ops.erasure_request")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_every_report_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All six pass and nothing a check wrote is left: no
    question, gap, token row, canary run, erasure or sign-in. Delete this and a check that can
    never pass on a real schema, or one that leaves an erasure queued, reaches the owner's
    server first."""
    before = _counts(install)
    outcomes = run_ops(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 6
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_ops(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_figures_counted_over_everybody_for_every_reader_fail_the_landing_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The landing screen's figures counted over everybody whatever the reader holds. Delete this
    and M27.2.1 closes on a screen whose counting is not honest."""
    from brain import console_overview_figures_routes as figures
    from brain.console.workspace import Basis

    monkeypatch.setattr(figures, "usage_basis", lambda reach, now: Basis.EVERYONE)
    assert "their own requests" in _failed(install, LANDING)


@pytest.mark.needs_db
def test_a_usage_grant_read_as_every_department_fails_the_usage_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adoption and usage reading any grant as reaching every department. Delete this and
    M27.7.14 closes on a report that shows one department's activity to another."""
    from brain.console import adoption_view, spend_view

    monkeypatch.setattr(spend_view, "may_read_spend", lambda *args, **kwargs: True)
    monkeypatch.setattr(adoption_view, "may_read_spend", lambda *args, **kwargs: True)
    assert "a reader of another" in _failed(install, USAGE)


@pytest.mark.needs_db
def test_gaps_shown_to_anybody_fail_the_questions_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every department's gaps counted whatever the grant's scope. Delete this and M27.7.18
    closes on a report that shows a department's unanswered questions to the administrator of
    another."""
    from brain.adoption import connector_demand as real
    from brain.console import questions_view

    def every_department(unanswered: Any, reachable: Any) -> Any:
        return real(unanswered, frozenset(one.department for one in unanswered))

    monkeypatch.setattr(questions_view, "connector_demand", every_department)
    assert "a reader of another" in _failed(install, GAPS)


@pytest.mark.needs_db
def test_canary_runs_shown_without_the_grant_fail_the_quality_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quality screen's grant ignored. Delete this and M27.7.19 closes on a screen that shows
    the permission canaries' findings to anybody."""
    from brain.console import quality_view

    monkeypatch.setattr(quality_view, "may_read_canary_runs", lambda *args, **kwargs: True)
    assert "without the grant" in _failed(install, CANARIES)


@pytest.mark.needs_db
def test_an_erasure_anybody_may_file_fails_the_erasure_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The erasure authority given to every reader of the screen. Delete this and M27.7.24 closes
    on a queue anybody may put a person's data into."""
    from brain import erasure_routes

    monkeypatch.setattr(erasure_routes, "may_erase", lambda reach, now: True)
    assert "without the authority filed" in _failed(install, ERASURE)


@pytest.mark.needs_db
def test_a_list_that_ignores_its_page_size_fails_the_list_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listing handing back every row whatever was asked. Delete this and M27.8.6 closes on a
    list that does not page."""
    from brain import listing

    def whole(self: Any, rows: Any) -> Any:
        return listing.Paged(items=tuple(rows), next_cursor=None)

    monkeypatch.setattr(listing.Plan, "page", whole)
    assert "paged" in _failed(install, LISTS)
