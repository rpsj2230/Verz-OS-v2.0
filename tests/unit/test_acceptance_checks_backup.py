"""The hosting and recovery install checks, passing on PostgreSQL at head and failing with the
product broken the way it would plausibly break.

The first half runs anywhere. The database half runs the module as the worker would: against an
install whose worker has never run the backup report, the report check ends not run rather than
failed, the other two pass, and nothing any of them wrote is left in a table the suite counts; then
each is shown failing when the thing it proves is broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M30.3.10, M30.6.10, M30.5.2, M30.6.9, M30.3.5
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_backup"
REPORT = "a_backup_older_than_its_recovery_point_is_recorded_and_said_once"
RETENTION = "the_retention_ladder_fits_inside_the_promised_window"
LANE = "a_question_is_measured_in_its_lane_and_counted_on_service_levels"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_the_three_checks_and_the_leaves_each_closes() -> None:
    """Delete this and a check can lose a leaf with the page showing the same row, and the leaf
    then closes on a check that never looked, or never closes."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (REPORT, ("M30.3.10", "M30.6.10")),
        (RETENTION, ("M30.3.5",)),
        (LANE, ("M30.5.2", "M30.6.9")),
    ]
    assert checks_in(MODULE) == [REPORT, RETENTION, LANE]


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The coordinator gave this package the keys 2300 to 2399, so two packages cannot share one.
    Delete this and a key outside the range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_backup as module

    assert 2300 <= module.CHECK_ORDER <= 2399


def test_the_report_check_is_held_on_a_real_room_and_a_real_aged_copy() -> None:
    """The alert is said to a room the check holds, over a listing the check made. Delete this
    and M30.3.10 and M30.6.10 close on an alert no chat ever showed."""
    import json
    from pathlib import Path

    held = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "proof-sweep-holds.json").read_text(
            encoding="utf-8"
        )
    )["held"]
    assert {"M30.3.10", "M30.6.10"} <= set(held)


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_backup") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing_and_the_report_waits_for_the_worker(
    install: str,
) -> None:
    """**The module as the worker runs it.** The retention and lane checks pass, the report check
    is not run because no worker has run the report, and nothing written is left behind. Delete
    this and a check that can never pass on a real schema, or one that leaves a setting row on the
    owner's install, reaches it first."""
    before = counts(install)

    outcomes = run_checks(install, registered((MODULE,)))

    assert outcomes[RETENTION] == (PASSED, "")
    assert outcomes[LANE] == (PASSED, "")
    assert outcomes[REPORT][0] == NOT_RUN and "no run of the backup report" in outcomes[REPORT][1]
    assert counts(install) == before


@pytest.mark.needs_db
def test_the_lane_check_fails_when_the_route_stops_counting_a_question(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the reading counting nothing, the question is not found in its lane and the check says
    so. Delete this and the Service levels screen can show a lane as unmeasured while the install
    answers questions in it."""
    from brain import report_routes

    real = report_routes.service_levels_for_reader

    async def nothing(*args: object, **kwargs: object) -> object:
        levels = await real(*args, **kwargs)  # type: ignore[arg-type]
        from dataclasses import replace

        return replace(levels, lanes=tuple(replace(one, requests=0) for one in levels.lanes))

    monkeypatch.setattr(report_routes, "service_levels_for_reader", nothing)

    outcome = run_checks(install, registered((MODULE,)))[LANE]

    assert outcome[0] == FAILED and "did not count" in outcome[1]


def test_the_retention_check_fails_when_the_ladder_outlives_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ladder whose horizon is past the promised window fails the check. Delete this and the
    retention check passes whatever the ladder says, so a certificate promises what a copy
    contradicts."""
    import asyncio

    from brain.ops import recovery
    from brain.ops.acceptance import CheckFailedError
    from brain.ops.acceptance_checks_backup import (
        the_retention_ladder_fits_inside_the_promised_window,
    )

    monkeypatch.setattr(
        recovery, "RETENTION_LADDER", recovery.Ladder(daily=30, weekly=5, monthly=2)
    )

    with pytest.raises(CheckFailedError):
        asyncio.run(the_retention_ladder_fits_inside_the_promised_window(None))  # type: ignore[arg-type]
