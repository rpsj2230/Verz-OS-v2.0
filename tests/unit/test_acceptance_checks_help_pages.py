"""The install checks for the help pages, each passing on PostgreSQL at head and failing with the
product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M34.4.1, M34.3.2.1, M34.3.1.1, M34.3.1.2, M37.5.2.2, M37.5.2.3
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
LADDER = "every_alert_has_steps_and_a_ladder_ending_at_the_supplier"


def test_the_module_names_each_leaf_in_one_check_inside_its_range() -> None:
    """Three checks, each closing its own leaves, in the assigned order range. Delete this and a
    leaf can move to a check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (PAGES, ("M34.4.1", "M34.3.2.1")),
        (SEES, ("M34.3.1.1", "M34.3.1.2")),
        (LADDER, ("M37.5.2.2", "M37.5.2.3")),
    ]
    assert checks_in(MODULE) == [PAGES, SEES, LADDER]
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
def test_every_check_passes_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass and nothing is left. Delete this and a
    check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
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


@pytest.mark.needs_db
def test_a_runbook_with_no_ladder_fails_the_ladder_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The escalation taken off the alert page. Delete this and M37.5.2.3 closes on a page that
    ends at the person on call, which is the page every install had before the ladder was shown."""
    from brain import help_routes

    monkeypatch.setattr(help_routes, "escalation_rungs", lambda contact=None: [])
    assert "escalation" in _failed(install, LADDER)


@pytest.mark.needs_db
def test_a_ladder_that_shows_a_placeholder_as_a_contact_fails_the_ladder_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unset sentence replaced by the setting's own placeholder. Delete this and M37.5.2.3
    closes on a page that offers `unset` as the way to reach the supplier."""
    from brain import help_routes

    monkeypatch.setattr(help_routes, "NO_SUPPLIER_CONTACT_ENTERED", "unset")
    assert "did not say so" in _failed(install, LADDER)


@pytest.mark.needs_db
def test_a_ladder_cut_short_fails_the_ladder_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supplier rung dropped, leaving the owner's. Delete this and M37.5.2.3 closes on a
    ladder that stops short of the only rung outside the company."""
    from brain import help_routes

    whole = help_routes.escalation_rungs
    monkeypatch.setattr(help_routes, "escalation_rungs", lambda contact=None: whole(contact)[:1])
    assert "escalation" in _failed(install, LADDER)


@pytest.mark.needs_db
def test_a_contact_that_is_not_shown_fails_the_ladder_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step that reaches the supplier written without the contact. Delete this and M37.5.2.3
    closes on a last rung that tells nobody how to reach anyone."""
    from brain.ops import alerting

    monkeypatch.setattr(alerting, "supplier_step", lambda contact, ladder=None: "Ask somebody.")
    assert "last rung" in _failed(install, LADDER)
