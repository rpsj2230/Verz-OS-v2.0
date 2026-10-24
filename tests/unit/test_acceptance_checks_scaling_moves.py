"""The install check for the Capacity screen's scaling moves, passing on PostgreSQL at head and
failing with the product broken, and the pure half that holds the moves to the trigger table.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M36.1.1.4, M36.1.4.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.install_routes import (
    A_DECISION_NOT_A_MEASUREMENT,
    NOT_MEASURED_READS_IN_FLIGHT,
    NOT_MEASURED_REPORT_LATENCY,
    scaling_moves,
)
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_scaling_moves import CHECK_ORDER
from brain.ops.scaling import TRIGGERS
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_scaling_moves"
MOVES = "each_scaling_move_says_when_it_is_due_and_what_it_cannot_say"
LOADS = "counted_reads_and_reports_make_their_scaling_moves_due_or_not"


def test_the_module_names_its_leaves_in_one_check_inside_its_range() -> None:
    """One check, two leaves, in the builder's assigned order range. Delete this and a leaf can
    move to a check that never looked at it, or two packages can share one order number."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (MOVES, ("M36.1.1.4", "M36.1.4.3")),
        (LOADS, ("M36.1.2.4", "M36.1.3.3")),
    ]
    assert checks_in(MODULE) == [MOVES, LOADS]
    assert 2100 <= CHECK_ORDER <= 2199


def test_every_declared_trigger_is_served_as_one_move() -> None:
    """The route's lines are the trigger table's, one each, in its order. Delete this and a
    trigger added to the table is never shown, which is the state this change ends."""
    served = scaling_moves("full")
    assert [(one.move, one.observable) for one in served] == [
        (one.move.value, one.observable.value) for one in TRIGGERS
    ]


def test_a_move_nothing_measures_has_no_flag_and_the_ledger_and_host_moves_do() -> None:
    """Console reads, report time and the resilience decision carry no due flag; the ledger and
    the host do. Delete this and an unmeasured move can be served as not due, which sends the
    owner away believing nothing is wrong."""
    by_observable = {one.observable: one for one in scaling_moves("full")}
    for unmeasured in (
        "console_reads_in_flight",
        "report_p95_ms",
        "single_host_failure_is_acceptable",
    ):
        assert by_observable[unmeasured].due is None
        assert by_observable[unmeasured].measured is None
    assert by_observable["retained_window_days"].due is True
    assert by_observable["profile_does_not_fit"].due is not None
    said = {NOT_MEASURED_READS_IN_FLIGHT, NOT_MEASURED_REPORT_LATENCY, A_DECISION_NOT_A_MEASUREMENT}
    assert {
        by_observable[one].said for one in by_observable if by_observable[one].due is None
    } == said
    assert all(len(one) <= REASON_CHARS * 4 for one in said)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_scaling_moves") as url:
        yield url


def run_module(url: str) -> dict[str, tuple[str, str]]:
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
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** It passes and nothing is left. Delete this and a
    check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {MOVES: (PASSED, ""), LOADS: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_unmeasured_move_served_as_not_due_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report move served as not due where nothing measured it. Delete this and the check
    passes a screen that tells the owner an unmeasured report is fast."""
    from brain import install_routes

    real = install_routes.scaling_moves

    def optimistic(profile: str, load: Any = None) -> Any:
        return [
            one.model_copy(update={"due": False}) if one.observable == "report_p95_ms" else one
            for one in real(profile, load)
        ]

    monkeypatch.setattr(install_routes, "scaling_moves", optimistic)
    outcomes = run_module(install)
    assert outcomes[MOVES][0] == FAILED
    assert "flag" in outcomes[MOVES][1]


@pytest.mark.needs_db
def test_a_screen_that_ignores_what_was_counted_fails_the_load_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route asked as though nothing had been counted. Delete this and the leaves close on a
    Capacity screen that says 'not measured' however busy the console is."""
    from brain import install_routes
    from brain.ops.read_load import Reading

    real = install_routes.scaling_moves

    def deaf(profile: str, load: Any = None) -> Any:
        return real(profile, Reading(None, None, 0))

    monkeypatch.setattr(install_routes, "scaling_moves", deaf)
    outcomes = run_module(install)
    assert outcomes[LOADS][0] == FAILED
    assert "did not make" in outcomes[LOADS][1]


def test_a_measured_reading_makes_its_moves_due_or_not_and_names_the_process() -> None:
    """Reads beyond the headroom make the replica due and inside it do not; a p95 over the
    threshold makes views due and under it does not; each sentence says whose window it is.
    Delete this and a measured move is served as unmeasured, or the sentence claims the install."""
    from brain.install_routes import (
        READS_ARE_INSIDE_THE_HEADROOM,
        READS_ARE_OVER_THE_HEADROOM,
        REPORTS_ARE_INSIDE_THE_THRESHOLD,
        REPORTS_ARE_OVER_THE_THRESHOLD,
    )
    from brain.ops.read_load import Reading

    quiet = {one.observable: one for one in scaling_moves("full", Reading(None, None, 0))}
    headroom = quiet["console_reads_in_flight"].threshold
    assert headroom is not None and headroom >= 1
    threshold = quiet["report_p95_ms"].threshold
    assert threshold == 8000.0

    def served(reads: int, p95: float) -> dict[str, Any]:
        return {one.observable: one for one in scaling_moves("full", Reading(reads, p95, 30))}

    over = served(int(headroom) + 1, 8001.0)
    assert (over["console_reads_in_flight"].due, over["report_p95_ms"].due) == (True, True)
    assert over["console_reads_in_flight"].said == READS_ARE_OVER_THE_HEADROOM
    assert over["report_p95_ms"].said == REPORTS_ARE_OVER_THE_THRESHOLD
    inside = served(int(headroom), 8000.0)
    assert (inside["console_reads_in_flight"].due, inside["report_p95_ms"].due) == (False, False)
    assert inside["console_reads_in_flight"].said == READS_ARE_INSIDE_THE_HEADROOM
    assert inside["report_p95_ms"].said == REPORTS_ARE_INSIDE_THE_THRESHOLD
    assert over["console_reads_in_flight"].measured == float(int(headroom) + 1)
    for line in (READS_ARE_OVER_THE_HEADROOM, REPORTS_ARE_INSIDE_THE_THRESHOLD):
        assert "this web process" in line.lower()


def test_a_profile_with_no_sizing_reads_no_reads_against_a_headroom_it_does_not_have() -> None:
    """The standard profile has no capacity sizing, so reads in flight are served with no
    threshold and no flag however many were counted. Delete this and a count is held against a
    headroom nobody worked out, and the load check fails on an install it cannot judge instead of
    saying it was not run."""
    from brain.ops.read_load import Reading

    standard = {one.observable: one for one in scaling_moves("standard", Reading(50, None, 0))}
    reads = standard["console_reads_in_flight"]
    assert (reads.threshold, reads.measured, reads.due) == (None, None, None)
    assert reads.said == NOT_MEASURED_READS_IN_FLIGHT
