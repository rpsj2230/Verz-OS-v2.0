"""The dead-letter install check: registered, passing on an install that has set nothing aside
because it sets a job aside itself, not run where the queue is not there, able to fail, and
leaving nothing.

Task ids: M17.1.5
"""

from __future__ import annotations

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_checks_queue import held_by_the_queue, queued, run_checks

MODULE = "brain.ops.acceptance_checks_dead_letter"
LISTED = "a_job_set_aside_is_listed_to_those_who_may_see_it"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_checks(url, mine())


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.unit.test_acceptance import INSTALL

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def test_the_check_names_its_leaf_and_stands_in_its_range() -> None:
    """Delete this and the check can close a leaf it does not exercise or collide on the page."""
    from brain.ops import acceptance_checks_dead_letter as module

    assert {name: one.leaves for name, one in mine().items()} == {LISTED: ("M17.1.5",)}
    assert checks_in(MODULE) == [LISTED]
    assert 2000 <= module.CHECK_ORDER <= 2099


def test_the_dead_letter_page_carries_no_count_of_what_a_reader_may_not_see() -> None:
    """**The page's own shape.** Its fields, read off the model, name no count, total or hidden
    figure, so a reader refused every row is told no more than a reader of an install with none.
    Delete this and a count of the withheld rows can be added to the page and no check, which asks
    only about the rows, would notice."""
    from brain.jobs_routes import DeadLettersPage, DeadLetterView

    named = {*DeadLettersPage.model_fields, *DeadLetterView.model_fields}
    assert not {one for one in named if any(w in one for w in ("count", "total", "hidden", "more"))}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_before_the_worker_has_made_the_queue_the_check_says_it_was_not_run() -> None:
    """A database no worker has started on has no queue to set a job aside from. Delete this and
    a new install records a pass for a list it never read."""
    from brain.ops.acceptance_checks_queue import NO_QUEUE_IS_INSTALLED_HERE

    with at_head("brain_acceptance_dead_letter_absent") as url:
        assert run(url) == {LISTED: (NOT_RUN, NO_QUEUE_IS_INSTALLED_HERE)}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_an_install_that_set_nothing_aside_is_shown_the_listing_and_nothing_is_left() -> None:
    """**The healthy install, which used to be the one the check could not be asked on.** The check
    sets a job aside itself, reads it back as a holder and as a stranger, and passes, twice, with
    nothing left in the tables or in the queue. Delete this and the check goes back to waiting for
    a failure on the install, or leaves a job and a dead letter behind on every run."""
    with at_head("brain_acceptance_dead_letter") as url:
        queued(url)
        before = counts(url)
        first, second = run(url), run(url)
        after, left = counts(url), held_by_the_queue(url)

    assert first == second == {LISTED: (PASSED, "")}
    assert after == before
    assert left == (0, 0, 0)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_list_that_shows_a_stranger_the_job_fails_the_check_and_the_probe_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the check is satisfied by a list that withholds from nobody, or leaves what
    it set aside when it fails."""
    from brain import jobs_routes
    from brain.ops import acceptance_checks_dead_letter as module

    monkeypatch.setattr(jobs_routes, "may_see_job", lambda *_: True)
    monkeypatch.setattr(jobs_routes, "may_see", lambda *_: True)
    with at_head("brain_acceptance_dead_letter_stranger") as url:
        queued(url)
        outcome = run(url)
        left = held_by_the_queue(url)
    assert outcome == {LISTED: (FAILED, module.SHOWN_TO_A_STRANGER)}
    assert left == (0, 0, 0)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_list_that_shows_the_holder_nothing_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the check is satisfied by a list that shows nobody anything."""
    from brain import jobs_routes
    from brain.ops import acceptance_checks_dead_letter as module

    monkeypatch.setattr(jobs_routes, "may_see_job", lambda *_: False)
    monkeypatch.setattr(jobs_routes, "may_see", lambda *_: False)
    with at_head("brain_acceptance_dead_letter_holder") as url:
        queued(url)
        outcome = run(url)
    assert outcome == {LISTED: (FAILED, module.NOT_SHOWN_TO_THE_HOLDER)}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_job_set_aside_with_another_reason_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason the sweep wrote being another word than the one the check asked for. Delete this
    and the list is judged on a row whose facts nobody compared with what was written."""
    from brain.ops import acceptance_checks_dead_letter as module
    from brain.ops.queue import DriverQueue

    real = DriverQueue.keep_aside

    async def another(self: DriverQueue, job_id: str, reason: str, at: object) -> None:
        await real(self, job_id, "timed_out_every_attempt", at)  # type: ignore[arg-type]

    monkeypatch.setattr(DriverQueue, "keep_aside", another)
    with at_head("brain_acceptance_dead_letter_reason") as url:
        queued(url)
        outcome = run(url)
    assert outcome == {LISTED: (FAILED, module.SHOWN_WITHOUT_ITS_FACTS)}
