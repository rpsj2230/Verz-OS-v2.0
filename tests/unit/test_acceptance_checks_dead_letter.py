"""The dead-letter install check: registered, passing where a job was set aside, not run where none
was, and able to fail.

Task ids: M17.1.5
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_dead_letter"
LISTED = "a_job_set_aside_is_listed_to_those_who_may_see_it"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_names_its_leaf_and_stands_in_its_range() -> None:
    """Delete this and the check can close a leaf it does not exercise or collide on the page."""
    from brain.ops import acceptance_checks_dead_letter as module

    assert {name: one.leaves for name, one in mine().items()} == {LISTED: ("M17.1.5",)}
    assert checks_in(MODULE) == [LISTED]
    assert 2000 <= module.CHECK_ORDER <= 2099


def run_checks(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                tuple(mine().values()),
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def set_one_aside(url: str) -> None:
    from tests.fixtures.scratch_postgres import sql

    sql(
        url,
        "INSERT INTO ops.dead_letter (job_id, task, principal_id, traffic_class, reason,"
        " attempts, set_aside_at) VALUES ('7', 'brain.controls.run', 'system', 'system',"
        " 'quarantined_after_a_stop', 1, now())",
    )


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_with_no_job_set_aside_the_check_says_it_was_not_run() -> None:
    """Delete this and an install with nothing set aside, which is the healthy one, is recorded as
    passing a check that showed nothing."""
    from brain.ops.acceptance_checks_dead_letter import NO_JOB_HAS_BEEN_SET_ASIDE

    with at_head("brain_acceptance_dead_letter") as url:
        assert run_checks(url) == {LISTED: (NOT_RUN, NO_JOB_HAS_BEEN_SET_ASIDE)}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_with_a_job_set_aside_the_check_passes_and_leaves_nothing_behind() -> None:
    """The positive case. Delete this and the check can be satisfied by a list that shows nobody
    anything, or one that commits a reserved person to a client's install."""
    with at_head("brain_acceptance_dead_letter") as url:
        set_one_aside(url)
        before = counts(url)
        outcomes = run_checks(url)
        after = counts(url)

    assert outcomes == {LISTED: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_list_that_shows_a_stranger_the_job_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the check is satisfied by a list that withholds from nobody."""
    from brain import jobs_routes

    monkeypatch.setattr(jobs_routes, "may_see_job", lambda *_: True)
    monkeypatch.setattr(jobs_routes, "may_see", lambda *_: True)
    with at_head("brain_acceptance_dead_letter") as url:
        set_one_aside(url)
        assert run_checks(url) == {
            LISTED: (FAILED, "a reader with no grant was shown a job set aside for a person")
        }
