"""The install checks for the people side of the staff list, each passing on PostgreSQL at head and
each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head with the staff
source held at Lark, as an install that has chosen one has it: every check passes and leaves
nothing, the held settings included. Then each is shown failing: Sync now writing no request or
offered to a reader who may not press it, People saying nothing about where the list puts a
person, a join made when it takes something, a join that leaves the list's person listed, and
departments managed on People that the sync still places.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test
does.

Task ids: M1.10.2, M1.6.13, M1.10.4, M1.10.5, M1.6.19
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_people import (
    NO_SOURCE_THE_WORKER_READS,
    NO_STAFF_LIST_IS_READ,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_people"
SYNC = "sync_now_asks_the_worker_for_the_scheduled_staff_sync"
PEOPLE = "people_says_where_the_staff_list_puts_each_person"
JOIN = "a_work_email_joins_the_list_person_only_where_nothing_is_lost"
FIRST = "the_first_administrator_adds_a_work_email_and_the_duplicate_goes"
DEPARTMENTS = "departments_managed_on_people_are_not_the_staff_sync_s"

#: What an install that has chosen Lark has saved, as the Staff sources screen leaves it.
LARK = {"INSTALL_STAFF_SOURCE": "lark", "INSTALL_STAFF_SOURCE_LOCATION": "larksuite.com"}


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Five checks, each closing its own leaf. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (SYNC, ("M1.10.2",)),
        (PEOPLE, ("M1.6.13",)),
        (JOIN, ("M1.10.4",)),
        (FIRST, ("M1.10.5",)),
        (DEPARTMENTS, ("M1.6.19",)),
    ]


def test_the_people_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [SYNC, PEOPLE, JOIN, FIRST, DEPARTMENTS]


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why a check was not run is cut short on the Install page."""
    assert len(NO_SOURCE_THE_WORKER_READS) <= REASON_CHARS
    assert len(NO_STAFF_LIST_IS_READ) <= REASON_CHARS


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The owner's coordinator gave this package the keys 600 to 699, so two packages cannot
    share a key and a later page order cannot be decided by a tie. Delete this and a key outside
    the range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_people as module

    assert 600 <= module.CHECK_ORDER <= 699


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_people") as url:
        yield url


@pytest.fixture
def lark() -> Iterator[None]:
    """The install has chosen Lark: held for the run, put back after it."""
    from brain.install import hold_saved

    before = hold_saved(LARK)
    yield
    hold_saved(before)


def run_people(url: str, *names: str) -> dict[str, tuple[str, str]]:
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
ALSO_WRITTEN = ("auth.staff_member", "ops.setting", "ops.control_run")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_every_people_check_passes_on_an_install_and_leaves_nothing(
    install: str, lark: None
) -> None:
    """**The module as the worker runs it.** All five pass and nothing a check wrote is left: no
    person, roster row, request, run row or setting, and the setting the departments check held is
    put back. Delete this and a check that can never pass on a real schema, or one that leaves the
    install managing its departments on People, reaches the owner's server."""
    from brain.install import saved_values

    before = _counts(install)
    held = dict(saved_values())
    outcomes = run_people(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 5
    assert _counts(install) == before
    assert dict(saved_values()) == held


@pytest.mark.needs_db
def test_an_install_with_no_source_the_worker_reads_says_so_instead_of_failing(
    install: str,
) -> None:
    """**An install states what the checks depend on.** With no staff source chosen, Sync now, the
    People list and the departments check are not run, in a sentence, while the work email checks,
    which need no source, still pass. Delete this and a check assuming the empty state fails on an
    install that has not chosen a list, or one that has chosen one is passed on an empty one."""
    outcomes = run_people(install)
    assert outcomes[SYNC][0] == NOT_RUN and outcomes[SYNC][1] == NO_SOURCE_THE_WORKER_READS
    assert outcomes[PEOPLE] == (NOT_RUN, NO_STAFF_LIST_IS_READ)
    assert outcomes[DEPARTMENTS] == (NOT_RUN, NO_STAFF_LIST_IS_READ)
    assert outcomes[JOIN] == (PASSED, "")
    assert outcomes[FIRST] == (PASSED, "")


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_people(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_sync_now_that_writes_no_request_or_is_offered_to_anybody_fails_the_sync_check(
    install: str, lark: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A press that records nothing for the worker, then the button given to a reader who may only
    open the page. Delete this and M1.10.2 closes on a button the worker never hears, or one any
    reader of Staff sources may press."""
    from brain import staff_source_routes

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    with monkeypatch.context() as patched:
        patched.setattr(staff_source_routes, "request_run", nothing)
        assert "left no run request" in _failed(install, SYNC)
    monkeypatch.setattr(staff_source_routes, "_may_sync", lambda asked: True)
    assert "may only open Staff sources pressed" in _failed(install, SYNC)


@pytest.mark.needs_db
def test_people_that_names_nobody_or_filters_on_nothing_fails_the_people_check(
    install: str, lark: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list's standing dropped from People, then a person's page that never says why. Delete
    this and M1.6.13 closes on a People page that shows no status, or a suspended person who is
    refused with no reason."""
    from brain import directory_routes

    with monkeypatch.context() as patched:
        patched.setattr(directory_routes, "standings_by_person", lambda rows: {})
        assert "did not say where the staff list puts" in _failed(install, PEOPLE)
    monkeypatch.setattr(directory_routes, "kept_out_sentence", lambda standing: None)
    assert "did not say in words why" in _failed(install, PEOPLE)


@pytest.mark.needs_db
def test_a_join_made_where_it_takes_something_or_never_made_fails_the_join_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decision joining without asking, joining a person who signs in on their own, and never
    joining. Delete this and M1.10.4 closes on a join that retires somebody who had been given
    something, or who would be locked out, or on one that never joins at all."""
    from brain import directory_routes
    from brain.identity.work_email import Joining, decide

    def unasked(*, has_email: bool, holder: Any, confirmed: bool) -> Joining:
        if holder is not None and not holder.signs_in:
            return Joining.JOINED
        return decide(has_email=has_email, holder=holder, confirmed=confirmed)

    def locking_out(*, has_email: bool, holder: Any, confirmed: bool) -> Joining:
        if holder is not None and holder.signs_in:
            return Joining.JOINED
        return decide(has_email=has_email, holder=holder, confirmed=confirmed)

    def never(*, has_email: bool, holder: Any, confirmed: bool) -> Joining:
        return (
            Joining.BOUND
            if holder is not None
            else Joining.ALREADY
            if has_email
            else decide(has_email=has_email, holder=holder, confirmed=confirmed)
        )

    with monkeypatch.context() as patched:
        patched.setattr(directory_routes, "decide", unasked)
        assert "without a question" in _failed(install, JOIN)
    with monkeypatch.context() as patched:
        patched.setattr(directory_routes, "decide", locking_out)
        assert "signs in on their own was joined" in _failed(install, JOIN)
    monkeypatch.setattr(directory_routes, "decide", never)
    # Binding an address somebody holds is refused by the database's own unique index, so a
    # product that never joins fails the check by that, which is a failure all the same.
    assert _failed(install, JOIN)


@pytest.mark.needs_db
def test_a_join_that_leaves_the_lists_person_listed_fails_the_first_administrator_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retirement of the list's person made to change nothing. Delete this and M1.10.5 closes
    on an administrator who still has a second, duplicate person on People."""
    from brain import directory_routes
    from brain.identity import work_email

    with monkeypatch.context() as patched:
        patched.setattr(
            directory_routes,
            "retiring",
            lambda principal_id: work_email.retiring("nobody"),
        )
        assert "is still listed beside" in _failed(install, FIRST)


@pytest.mark.needs_db
def test_a_sync_that_places_under_people_or_a_move_refused_fails_the_departments_check(
    install: str, lark: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sync's own question answering that it places people even on an install managing
    departments on People. Delete this and M1.6.19 closes on a sync that puts everybody back
    where the list says."""
    from brain.identity import departments_from

    monkeypatch.setattr(departments_from, "the_list_places_people", lambda *args, **kwargs: True)
    assert "placed the person it made" in _failed(install, DEPARTMENTS)
