"""The peak load run's install check: registered, passing on a real schema, and able to fail.

The check drives a short bounded run through the peak test's own driver against the answer route's
own function, as a reserved person, with a stand-in for the model, keeps its result as the
command would and reads it back, so the database half is the whole of it: PostgreSQL at head, run
as the worker runs it. It passes and leaves every table it wrote as it was. Then the product is
broken where the check proves it, each the way it would break in practice: a bounded run recorded
as the stated peak, a driver that sends one request after another, a row that is not read back as
it was kept, a command that refuses nothing and a command that refuses everything. Each is a
failed check with its own sentence.

Task ids: M22.3.3
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_load_peak as load_check
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_load_peak"
NAME = "a_short_peak_run_is_driven_judged_and_kept_and_leaves_nothing"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """One check naming the load test's leaf, which is a leaf of the work breakdown. Delete this
    and the check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M22.3.3",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert "M22.3.3" in {one for module in wbs["modules"] for one in module["leaf_ids"]}


def test_the_short_run_gives_each_lane_the_requests_a_95th_percentile_needs() -> None:
    """The arrivals the check plans, drawn the way the run draws them. Delete this and a change to
    the seed or the mix leaves one lane with fewer than twenty requests, so the check fails on a
    day nothing in the install changed, or passes having measured nothing."""
    from brain.core.lane import Lane
    from brain.ops import load_peak

    profile = load_peak.Profile(
        questions={Lane.FAST: ("a",), Lane.ANSWER: ("b",)},
        people=1,
        arrivals_per_second=load_check.SHORT_RUN_ARRIVALS_PER_SECOND,
        seconds=load_check.SHORT_RUN_SECONDS,
        max_requests=load_check.SHORT_RUN_REQUESTS,
        mix={Lane.ANSWER: load_check.SHORT_RUN_MIX, Lane.FAST: load_check.SHORT_RUN_MIX},
    )
    drawn = load_peak.arrivals(profile)
    assert len(drawn) == load_check.SHORT_RUN_REQUESTS
    for lane in (Lane.FAST, Lane.ANSWER):
        assert sum(1 for _, shape in drawn if shape.lane is lane) >= (
            load_peak.MINIMUM_REQUESTS_FOR_A_P95
        )


def run_check(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
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
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    it wrote to, the settings and the request ledger among them, holds what it held before. Delete
    this and a check that cannot pass on the real schema, or one that commits a run's row or its
    requests to a client's install, reaches the owner's server first."""
    with at_head("brain_acceptance_load_peak") as url:
        before = counts(url)
        outcomes = run_check(url, tuple(mine().values()))
        after = counts(url)

    assert outcomes == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("peak", "a run of eighty requests was recorded as the stated peak"),
        ("sequential", "the run's requests were sent one after another, not together"),
        ("unread", "the run's row was not read back from the install as it was kept"),
        ("lax", "the command did not refuse a run that broke one of its rules"),
        ("strict", "the command refused a run that met every condition"),
    ],
)
def test_the_check_fails_where_the_run_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Five breaks, each the way it happens: a bounded run recorded as the peak test, a driver that
    waits for each reply before the next send, a row the install cannot give back, a command that
    refuses nothing and one that refuses everything. Each fails with its own sentence. Delete this
    and the check is satisfied by a run that reports the peak held having sent eighty requests."""
    from brain.ops import load_peak, load_run_store

    if broken == "peak":
        monkeypatch.setattr(load_peak, "at_stated_peak", lambda *_: True)
    elif broken == "sequential":
        real = load_peak.drive_measured

        async def one_at_a_time(*args: Any, **kwargs: Any) -> load_peak.Measured:
            got = await real(*args, **kwargs)
            return load_peak.Measured(
                samples=got.samples, most_in_flight=1, not_sent=0, seconds_run=got.seconds_run
            )

        monkeypatch.setattr(load_peak, "drive_measured", one_at_a_time)
    elif broken == "unread":

        async def nothing(session: Any) -> tuple[Any, ...]:
            return ()

        monkeypatch.setattr(load_run_store, "read_runs", nothing)
    elif broken == "lax":
        monkeypatch.setattr(load_peak, "refusals_before_a_run", lambda **_: ())
    else:
        monkeypatch.setattr(load_peak, "refusals_before_a_run", lambda **_: ("no",))
    with at_head("brain_acceptance_load_peak") as url:
        assert run_check(url, tuple(mine().values())) == {NAME: (FAILED, reason)}


def test_the_load_peak_check_is_listed_in_its_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]
