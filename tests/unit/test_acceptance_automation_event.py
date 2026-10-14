"""The install check for an automation a change starts, passing on PostgreSQL at head and failing
with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: the check passes
and leaves nothing. Then it is shown failing: a reach ignored so a record in another department
starts a run, and a pass that starts nothing at all.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M17.4.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.core.scope import Scope
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_automation_event import (
    A_RECORD_STARTED_TWO,
    A_REPEAT_LOOK_RAN,
    A_RUN_WAS_NOT_THEIRS,
    AN_OUTSIDER_RAN,
    CHECK_ORDER,
    NO_RUN_WAS_STARTED,
    THE_ARMING_MOVED,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_automation_event"
STARTS = "a_change_starts_one_run_as_an_owner_who_may_read_it"


def test_the_module_declares_one_check_closing_the_trigger_leaf() -> None:
    """Delete this and the check can lose M17.4.1 with the page showing the same row, and the leaf
    closes on a check that never looked at a change."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(STARTS, ("M17.4.1",))]
    assert checks_in(MODULE) == [STARTS]
    assert 1600 <= CHECK_ORDER <= 1699


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why the check failed is cut short on the Install page."""
    for sentence in (
        A_RECORD_STARTED_TWO,
        A_RUN_WAS_NOT_THEIRS,
        A_REPEAT_LOOK_RAN,
        AN_OUTSIDER_RAN,
        NO_RUN_WAS_STARTED,
        THE_ARMING_MOVED,
    ):
        assert len(sentence) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_automation_event") as url:
        yield url


def run_check(url: str) -> tuple[str, str]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    [one] = results
    return one.outcome, one.reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** It passes and nothing it wrote is left: no
    automation, no run, no record in the index. Delete this and a check that can never pass on a
    real schema, or one that leaves a listener behind, reaches the owner's server."""
    from tests.fixtures.scratch_postgres import sql

    before = counts(install)

    assert run_check(install) == (PASSED, "")
    assert counts(install) == before
    assert sql(install, "SELECT count(*) FROM agent.automation") == [(0,)]
    assert sql(install, "SELECT count(*) FROM proj.record WHERE source LIKE 'acceptance_%'") == [
        (0,)
    ]


@pytest.mark.needs_db
def test_a_reach_that_is_ignored_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pass reading every record as the owner's. A record in the other department then starts a
    run, and so does one for a person with no read of the kind. Delete this and M17.4.1 closes on a
    listener that tells a person about records they may not read."""
    from brain.ops import automation_event_store

    monkeypatch.setattr(
        automation_event_store, "row_scope_for", lambda *_a, **_k: Scope.unrestricted()
    )

    outcome, reason = run_check(install)

    assert outcome == FAILED
    assert reason in {A_RECORD_STARTED_TWO, AN_OUTSIDER_RAN}


@pytest.mark.needs_db
def test_a_pass_that_starts_nothing_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pass allowed no run. Delete this and the check passes against a listener that never
    starts anything, which is the positive case every refusal above is measured against."""
    from brain.ops import automation_event_store

    monkeypatch.setattr(automation_event_store, "allowance", lambda **_k: 0)

    assert run_check(install) == (FAILED, NO_RUN_WAS_STARTED)
