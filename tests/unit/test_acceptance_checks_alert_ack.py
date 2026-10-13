"""The install check for acknowledging an incident, passing on PostgreSQL at head and failing with
the product broken the way it would plausibly break.

The pure half holds the module's place and the repeat rule. The database half runs the check as the
worker would against a database at head: it passes and leaves nothing, then each fault is shown to
fail it: a press open to a reader of one department, a second press that rewrites who
acknowledged, and an acknowledgement that hides the incident.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.45
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.alert_acknowledgement import notice_may_repeat
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_alert_ack"
CHECK = "an_incident_is_acknowledged_once_and_stops_its_repeat_notice"
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
EVERY = timedelta(hours=1)


def test_the_module_declares_its_one_check_for_its_one_leaf() -> None:
    """Delete this and the check can lose M27.15.45 with the Install page showing the same rows,
    and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(CHECK, ("M27.15.45",))]
    assert checks_in(MODULE) == [CHECK]


def test_an_acknowledged_alert_is_said_no_more_and_the_rest_after_their_interval() -> None:
    """Both halves of the rule, and the boundary. Delete this and a sender that asks the rule is
    satisfied by one that never repeats, or one that repeats after acknowledgement."""
    assert not notice_may_repeat(acknowledged=True, last_said=NOW - EVERY * 9, every=EVERY, now=NOW)
    assert notice_may_repeat(acknowledged=False, last_said=None, every=EVERY, now=NOW)
    assert notice_may_repeat(acknowledged=False, last_said=NOW - EVERY, every=EVERY, now=NOW)
    assert not notice_may_repeat(
        acknowledged=False, last_said=NOW - EVERY + timedelta(seconds=1), every=EVERY, now=NOW
    )


def test_a_repeat_interval_that_is_not_positive_is_refused() -> None:
    """A zero interval says an alert on every pass, which is a flood and not a repeat. Delete this
    and a misconfigured interval floods whoever is on call."""
    with pytest.raises(ValueError, match="positive"):
        notice_may_repeat(acknowledged=False, last_said=NOW, every=timedelta(0), now=NOW)


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_alert_ack") as url:
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
    [only] = results
    return only.outcome, only.reason


ALSO_WRITTEN = ("ops.alert_acknowledgement", "ops.connector_connection", "ops.connector_sync")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes, and no acknowledgement, connection or test
    is left. Delete this and a check that can never pass on a real schema, or that leaves an
    acknowledgement behind, reaches the owner's server."""
    before = _counts(install)
    assert run_check(install) == (PASSED, "")
    assert _counts(install) == before


@pytest.mark.needs_db
def test_a_press_open_to_a_reader_of_one_department_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The company-scope rule removed. Delete this and M27.15.45 closes on a control offered to a
    reader who holds the screen over one department."""
    from brain import incident_routes

    monkeypatch.setattr(incident_routes, "held_across_the_install", lambda *args: True)
    outcome, reason = run_check(install)
    assert outcome == FAILED and "one department" in reason


@pytest.mark.needs_db
def test_a_second_press_that_rewrites_who_acknowledged_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store answering with the last presser. Delete this and M27.15.45 closes on a record
    anybody can take over by pressing last."""
    from brain.ops import alert_acknowledgement

    real = alert_acknowledgement.acknowledge

    async def last_wins(session: Any, **kwargs: Any) -> Any:
        found = await real(session, **kwargs)
        return type(found)(
            kind=found.kind,
            subject=found.subject,
            since=found.since,
            by=kwargs["by"],
            at=found.at,
        )

    from brain import incident_routes

    monkeypatch.setattr(incident_routes, "acknowledge", last_wins)
    outcome, reason = run_check(install)
    assert outcome == FAILED and "rewrote" in reason
