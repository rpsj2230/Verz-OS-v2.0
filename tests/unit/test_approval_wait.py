"""The typical approval wait: the measurement, the Install page's facts, and the install check.

The pure half holds the median, the verdict through `locale.triggered`, the words and the facts the
Install page is given, including the case of nothing decided and of a database that could not be
asked. The database half runs the check as the worker would against a database at head, where the
view `0227` adds exists, and shows it failing with the measurement broken.

Task ids: M35.4.5, M35.3.2.2
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.console.installation import (
    NO_APPROVAL_HAS_BEEN_DECIDED,
    THE_APPROVAL_WAITS_COULD_NOT_BE_READ,
    Source,
    approval_wait_facts,
)
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.ops.approval_wait import push_is_wanted, typical_wait, worded
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)
MODULE = "brain.ops.acceptance_checks_approval_wait"
WAIT = "the_approval_wait_is_measured_and_push_is_reported"


def pairs(*hours: float) -> list[tuple[datetime, datetime]]:
    return [(NOW - timedelta(hours=one), NOW) for one in hours]


def test_the_typical_wait_is_the_median_and_not_the_mean_or_the_longest() -> None:
    """Six, five and one hours: the median is five, the mean four and the longest six. Delete this
    and one slow approval moves the figure that decides whether push is built."""
    assert typical_wait(pairs(6, 5, 1)) == timedelta(hours=5)
    assert typical_wait(pairs(1, 3)) == timedelta(hours=2)


def test_nothing_decided_is_unknown_and_never_a_wait_of_nothing() -> None:
    """Delete this and an install nobody has approved anything on reads as answering at once."""
    assert typical_wait([]) is None
    assert push_is_wanted(None) is False
    [fact] = approval_wait_facts(None)
    assert fact.source is Source.UNKNOWN and fact.because == NO_APPROVAL_HAS_BEEN_DECIDED


def test_a_decision_stamped_before_its_raising_counts_as_no_wait() -> None:
    """Delete this and clock skew between two writers drags the median below any real wait."""
    assert typical_wait([(NOW, NOW - timedelta(minutes=5))]) == timedelta(0)


def test_push_is_wanted_only_past_the_stated_hours() -> None:
    """Held on both sides of the line, the positive case beside the refusal. Delete this and push
    is reported due for a quiet install, or never."""
    assert push_is_wanted(timedelta(hours=4, minutes=1)) is True
    assert push_is_wanted(timedelta(hours=4)) is False
    assert push_is_wanted(timedelta(minutes=10)) is False


def test_a_wait_is_worded_as_a_person_reads_it() -> None:
    """Delete this and the Install page shows seconds."""
    assert worded(timedelta(hours=1, minutes=40)) == "1 hour 40 minutes"
    assert worded(timedelta(hours=2)) == "2 hours"
    assert worded(timedelta(seconds=20)) == "under a minute"


def test_the_install_page_is_given_the_wait_and_the_verdict_and_no_count() -> None:
    """Two measured facts, one saying push is worth building, and nothing numbering the approvals.
    Delete this and the figure shows without the sentence the owner asked for, or the sentence
    shows for a wait inside the hours."""
    due = approval_wait_facts(timedelta(hours=5))
    quiet = approval_wait_facts(timedelta(hours=1))
    assert [one.name for one in due] == [
        "typical approval wait",
        "push notifications for approvals",
    ]
    assert "now worth building" in due[1].value and "not needed yet" in quiet[1].value
    assert all(one.source is Source.MEASURED for one in (*due, *quiet))


def test_a_database_that_could_not_be_asked_is_unknown_with_its_reason() -> None:
    """Delete this and an install not upgraded to this release shows a wait of nothing."""
    [fact] = approval_wait_facts(None, readable=False)
    assert fact.source is Source.UNKNOWN and fact.because == THE_APPROVAL_WAITS_COULD_NOT_BE_READ


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_names_its_leaves_and_stands_in_its_range() -> None:
    """Delete this and the check can close leaves it does not exercise or collide on the page."""
    from brain.ops import acceptance_checks_approval_wait as module

    assert {name: one.leaves for name, one in mine().items()} == {WAIT: ("M35.4.5", "M35.3.2.2")}
    assert checks_in(MODULE) == [WAIT]
    assert 2000 <= module.CHECK_ORDER <= 2099


def run_checks(url: str, checks: tuple[Check, ...]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
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


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head**, where `0227`'s view
    exists. It passes and every table it wrote holds what it held before. Delete this and a check
    that cannot pass on the real schema, or one that commits an approval, reaches the owner."""
    with at_head("brain_acceptance_approval_wait") as url:
        before = counts(url)
        outcomes = run_checks(url, tuple(mine().values()))
        after = counts(url)

    assert outcomes == {WAIT: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("shortest", "the typical wait of three approvals was not their median"),
        ("never_due", "a typical wait past four hours did not report push as due"),
    ],
)
def test_the_check_fails_where_the_measurement_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Two breaks: a figure that is the shortest wait rather than the median, and a verdict that
    never fires. Delete this and the check is satisfied by a measurement that cannot tell a slow
    install from a quick one."""
    from brain.ops import approval_wait

    if broken == "shortest":
        monkeypatch.setattr(
            approval_wait,
            "typical_wait",
            lambda found: min((d - r for r, d in found), default=None),
        )
    else:
        monkeypatch.setattr(approval_wait, "push_is_wanted", lambda typical: False)
    with at_head("brain_acceptance_approval_wait") as url:
        assert run_checks(url, tuple(mine().values())) == {WAIT: (FAILED, reason)}
