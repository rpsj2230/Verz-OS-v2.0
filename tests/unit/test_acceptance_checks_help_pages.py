"""The install checks for the help pages, each passing on PostgreSQL at head and failing with the
product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M34.4.1, M34.3.2.1, M34.3.1.1, M34.3.1.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_help_pages import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_help_pages"
PAGES = "help_pages_are_served_to_the_readers_of_their_screens"
SEES = "what_a_person_may_ask_about_and_what_is_done_is_said_plainly"


def test_the_module_names_each_leaf_in_one_check_inside_its_range() -> None:
    """Two checks, each closing its own leaves, in the assigned order range. Delete this and a
    leaf can move to a check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (PAGES, ("M34.4.1", "M34.3.2.1")),
        (SEES, ("M34.3.1.1", "M34.3.1.2")),
    ]
    assert checks_in(MODULE) == [PAGES, SEES]
    assert 2100 <= CHECK_ORDER <= 2199


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_help_pages") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
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


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing is left. Delete this and a
    check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_page_open_to_everybody_fails_the_pages_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen question removed from the help pages. Delete this and M34.3.2.1 and M34.4.1
    close on pages that describe a screen to somebody who may not open it."""
    from brain import help_routes

    monkeypatch.setattr(help_routes, "_may_open", lambda *args: True)
    assert "given to somebody" in _failed(install, PAGES) or _failed(install, PAGES)


@pytest.mark.needs_db
def test_a_page_that_names_departments_beyond_the_reach_fails_the_sees_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reach ignored in what a person is told they can ask about. Delete this and
    M34.3.1.1 closes on a page that lists what a person cannot reach."""
    from brain import help_routes

    def everything(slugs: Any, reach: Any, now: Any) -> list[str]:
        return list(slugs)

    monkeypatch.setattr(help_routes, "reachable_departments", everything)
    assert "departments" in _failed(install, SEES)
