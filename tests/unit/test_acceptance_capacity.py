"""The capacity acceptance checks: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the first check as the worker would: it
passes, leaves `ops.setting` and the ledger as they were, and leaves what the process holds as it
was. Then it is run against a product broken three ways, each the way it would break in practice:
bounds that refuse nothing, a reload that reads nothing, and budgets that ignore what was saved.
Each is a failed check with its own sentence. The cache half is not run without a cache, with its
own sentence, which is how the worker records it; the cache run is inside the application's
container, where the window check in `brain.ops.acceptance_checks` runs too.

The class check reads no database, so it is run here as the sizing check is, on a harness with no
connection, over the literal ledger fake from `test_capacity_ledger.py`: it passes and leaves no
key behind, and each property it names fails it with its own sentence when the product is broken
the way that property would break.

Task ids: M22.1.2, M22.4.1, M22.3.1, M22.3.2, M22.3.4
Task ids: M22.1.3, M22.1.4, M22.1.5, M22.2.1, M22.2.3, M22.1.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_capacity as capacity
from brain.ops import tuning
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.ops.admission import seed_budgets
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_capacity"

LEAVES = {
    "budgets_and_windows_are_rows_saved_within_bounds_and_audited": (
        "M22.1.2",
        "M22.4.1",
        "M22.1.1",
    ),
    "the_rate_limits_screen_lists_the_windows_refusing_now": ("M22.4.1",),
    "capacity_is_sized_for_the_busiest_minute_and_its_first_limit": (
        "M22.3.1",
        "M22.3.2",
        "M22.3.4",
    ),
    "three_classes_share_one_budget_and_give_way_in_order": (
        "M22.1.3",
        "M22.1.4",
        "M22.1.5",
        "M22.2.1",
        "M22.2.3",
    ),
}

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_capacity_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Each check names its leaves, and each is a leaf of the work breakdown. Delete this and a
    check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == LEAVES
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


def test_the_check_restates_the_route_s_authority_rather_than_importing_it() -> None:
    """`CHANGES_LIMITS` is held against the route's own constant from outside the check. Delete
    this and the route could move to another authority with the check asking the old one."""
    from brain.settings_routes import INSTALL_SETTING_AUTHORITY

    assert INSTALL_SETTING_AUTHORITY.value == capacity.CHANGES_LIMITS


def run_checks(
    url: str, checks: Sequence[Check], env: dict[str, str]
) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **env}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def settings_rows(url: str) -> int:
    from tests.fixtures.scratch_postgres import sql

    return int(sql(url, "SELECT count(*) FROM ops.setting")[0][0])


def saved_check() -> Check:
    return mine()["budgets_and_windows_are_rows_saved_within_bounds_and_audited"]


@pytest.mark.needs_db
def test_on_a_real_database_the_capacity_checks_pass_or_say_why_not_and_leave_nothing_behind() -> (
    None
):
    """**The checks as the worker runs them, against PostgreSQL at head, with no cache.** The rows
    check passes; the cache check is not run with its own sentence; `ops.setting`, the ledger and
    what this process holds are as they were. Delete this and a check that cannot pass on the
    real schema, or one that commits a saved limit to a client's install, reaches the owner's
    server first."""
    held = dict(tuning.held())
    with at_head("brain_acceptance_capacity") as url:
        before = (counts(url), settings_rows(url))
        outcomes = run_checks(url, tuple(mine().values()), {})
        after = (counts(url), settings_rows(url))

    assert outcomes == {
        "budgets_and_windows_are_rows_saved_within_bounds_and_audited": (PASSED, ""),
        "the_rate_limits_screen_lists_the_windows_refusing_now": (
            NOT_RUN,
            capacity.NO_CACHE_TO_ASK,
        ),
        "capacity_is_sized_for_the_busiest_minute_and_its_first_limit": (PASSED, ""),
        "three_classes_share_one_budget_and_give_way_in_order": (
            NOT_RUN,
            capacity.NO_CACHE_TO_ASK,
        ),
    }
    assert after == before
    assert dict(tuning.held()) == held


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("bounds", "a value outside the product's bounds was not refused"),
        ("reload", "the reload every process runs did not read back what was saved"),
        ("budgets", "the budgets admission reads did not carry the saved row"),
        ("unbudgeted", "a resource the product names has no global budget"),
        ("unbound", "a request past its global budget was not refused"),
    ],
)
def test_the_rows_check_fails_when_the_product_is_broken_where_it_proves(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Five breaks, each one line of the product: bounds that admit anything, a reload that
    reads an empty namespace, budgets that never lay a saved row over the seed, browser sessions
    left with no global row, and admission that lets browser sessions past their row. Each fails
    the check with its own sentence. Delete this and the check can pass with the property it names
    gone."""
    import brain.ops.admission as admission
    import brain.ops.install_settings as install_settings

    if broken == "bounds":
        monkeypatch.setattr(tuning, "problem", lambda name, raw: "")
    elif broken == "reload":

        async def nothing(session: Any) -> dict[str, int]:
            del session
            return {}

        monkeypatch.setattr(install_settings, "load_tuned", nothing)
    elif broken == "budgets":
        monkeypatch.setattr(tuning, "configured_budgets", lambda saved=None: seed_budgets())
    elif broken == "unbudgeted":
        configured = tuning.configured_budgets

        def without_browsers(saved: Any = None) -> Any:
            return tuple(
                one
                for one in configured(saved)
                if one.resource is not admission.Resource.BROWSER_SESSIONS
            )

        monkeypatch.setattr(tuning, "configured_budgets", without_browsers)
    else:
        decide = admission.decide

        def unbound(request: Any, budgets: Any, state: Any, **kwargs: Any) -> Any:
            if request.resource is admission.Resource.BROWSER_SESSIONS:
                state = admission.CapacityState()
            return decide(request, budgets, state, **kwargs)

        monkeypatch.setattr(admission, "decide", unbound)
    with at_head(f"brain_acceptance_capacity_{broken}") as url:
        outcome = run_checks(url, (saved_check(),), {})
    assert outcome[saved_check().name] == (FAILED, reason)


# --------------------------------------------------------------------------- the cache half
class HeldCache:
    """`tests.unit.test_limit_store.FakeClient`, which answers the window store's statements as
    Valkey does, with the key removal the harness's undoing calls."""

    def __init__(self) -> None:
        from tests.unit.test_limit_store import FakeClient

        self.client = FakeClient()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def delete(self, *names: str) -> int:
        gone = 0
        for one in names:
            gone += self.client.sets.pop(one, None) is not None
            gone += self.client.counters.pop(one, None) is not None
        return gone


def window_check() -> Check:
    return mine()["the_rate_limits_screen_lists_the_windows_refusing_now"]


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "outcome"),
    [
        ("", (PASSED, "")),
        ("unlisted", (FAILED, "the screen's reading did not list the window refusing now")),
        ("unnarrowed", (FAILED, "a reader of one department was shown a window refusing now")),
    ],
)
def test_the_window_check_passes_over_a_cache_and_fails_when_the_screen_misreads_it(
    monkeypatch: pytest.MonkeyPatch, broken: str, outcome: tuple[str, str]
) -> None:
    """**The cache check over a cache that answers as Valkey does, and every key it wrote gone
    afterwards.** Then with the screen's reading broken two ways: listing nothing, and ignoring
    the reader's grant. Delete this and the check can pass over a screen that never lists a
    refusing window, or one that lists it to a department's reader, and leave the check's own
    windows in the install's cache."""
    import brain.cache as cache
    import brain.console.installation as installation

    held = HeldCache()
    monkeypatch.setattr(cache, "make_client", lambda url: held)
    original = installation.throttled_now
    if broken == "unlisted":
        monkeypatch.setattr(installation, "throttled_now", lambda *a, **k: ())
    elif broken == "unnarrowed":

        def everyone(limits: Any, state: Any, reader: Any, *, now: datetime) -> Any:
            del reader
            from brain.core.entitlement import Capability, EntitlementSet, Grant
            from brain.core.scope import Scope

            wide = EntitlementSet(
                principal_id="u_everywhere",
                grants=(
                    Grant(
                        capability=Capability(value=capacity.READS_LIMITS),
                        scope=Scope.unrestricted(),
                    ),
                ),
            )
            return original(limits, state, wide, now=now)

        monkeypatch.setattr(installation, "throttled_now", everyone)
    env = {"BRAIN_VALKEY_URL": "redis://cache.invalid:6379/0"}
    with at_head(f"brain_acceptance_capacity_cache{broken}") as url:
        found = run_checks(url, (window_check(),), env)
    assert found[window_check().name] == outcome
    assert held.client.sets == {}
    assert held.client.counters == {}


# --------------------------------------------------------------------------- the sizing half
def sized() -> tuple[str, str]:
    """The sizing check's outcome and reason, as the run records them. It reads no database."""
    from brain.ops.acceptance import reason_for
    from brain.ops.acceptance_run import Harness

    one = mine()["capacity_is_sized_for_the_busiest_minute_and_its_first_limit"]
    # The check reads nothing through the harness, so it is handed one with no connection.
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(one.run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


def test_the_sizing_check_passes_on_what_the_capacity_route_is_sent() -> None:
    """The positive run. Delete this and the check can refuse the product's own sizings."""
    assert sized() == (PASSED, "")


@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("in_flight", "a sizing's in-flight figure is not Little's law of its inputs"),
        ("slots", "a sizing's slots are not its in-flight figure rounded up"),
        ("limit", "the first limit at ten and a hundred times is not named"),
    ],
)
def test_the_sizing_check_fails_when_the_screen_is_sent_figures_its_arithmetic_does_not_give(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks of what the route is sent: an in-flight figure that is not Little's law, slots
    not rounded up from it, and a first limit that names no scale. Delete this and the screen can
    show a sizing the admission budgets do not share with the check green."""
    import brain.install_routes as install_routes

    original = install_routes.capacity_plan

    def plan() -> Any:
        sizings, first_limit = original()
        one = sizings[0]
        if broken == "in_flight":
            sizings[0] = one.model_copy(update={"in_flight_at_peak": one.in_flight_at_peak + 1})
        elif broken == "slots":
            sizings[0] = one.model_copy(update={"slots_needed": one.slots_needed + 1})
        else:
            first_limit = "a day's total"
        return sizings, first_limit

    monkeypatch.setattr(install_routes, "capacity_plan", plan)
    assert sized() == (FAILED, reason)


# --------------------------------------------------------------------------- the class half
def classed(fake: Any) -> tuple[tuple[str, str], dict[str, dict[str, float]]]:
    """The class check's outcome over `fake` as the install's cache, and what it left in it."""
    import brain.cache as cache
    from brain.ops.acceptance import reason_for
    from brain.ops.acceptance_run import Harness

    one = mine()["three_classes_share_one_budget_and_give_way_in_order"]
    settings = settings_from({"BRAIN_VALKEY_URL": "redis://cache.invalid:6379/0"})
    # The check reads nothing through the harness's connection, so it is handed none.
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings, connection=None)  # type: ignore[arg-type]
    patch = pytest.MonkeyPatch()
    patch.setattr(cache, "make_client", lambda url: fake)
    try:
        asyncio.run(one.run(harness))
        outcome = (PASSED, "")
    except Exception as exc:
        outcome = reason_for(exc)
    finally:
        asyncio.run(harness.undo(sys.stderr))
        patch.undo()
    return outcome, fake.sets


def test_the_class_check_passes_over_a_cache_and_leaves_no_key_behind() -> None:
    """**The positive run, and every key it wrote removed by name.** Delete this and the check can
    refuse the product's own classes, or leave slots in the install's cache that a real upload is
    then counted against."""
    from tests.unit.test_capacity_ledger import LedgerFake

    outcome, left = classed(LedgerFake())

    assert outcome == (PASSED, "")
    assert left == {}


def _decided_as_batch() -> Any:
    import dataclasses

    from brain.core.lane import Lane
    from brain.gate.context import TrafficClass
    from brain.ops.admission import decide as original

    def as_batch(request: Any, *args: Any, **kwargs: Any) -> Any:
        batch = dataclasses.replace(request, traffic_class=TrafficClass.SYSTEM, lane=Lane.TASK)
        decision = original(batch, *args, **kwargs)
        return dataclasses.replace(decision, request=request)

    return as_batch


def _nobody_waiting_counted() -> Any:
    from brain.ops.admission import CapacityState
    from brain.ops.admission import decide as original

    def blind(request: Any, budgets: Any, state: Any, **kwargs: Any) -> Any:
        return original(request, budgets, CapacityState(used=state.used), **kwargs)

    return blind


@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("classes", "the doors' requests are not classed batch and interactive"),
        ("shares", "the three classes do not hold three shares of the one budget"),
        ("shed_batch", "batch work past its share was not queued with a position"),
        ("positions", "a second batch request was not given the next place in line"),
        ("one_class", "background work was not admitted past the batch share"),
        ("queued_person", "work a person waits for past the budget was not refused"),
        ("plan", "the shed plan did not name the classes deferred in order"),
        ("kept", "a slot or a place given back is still counted"),
        ("down", "the cache did not answer, so no slot was counted"),
    ],
)
def test_the_class_check_fails_with_its_own_sentence_when_a_property_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Each property the check names, broken the way it would break in the product: the doors'
    requests classed alike, two classes with one share, batch work refused rather than queued,
    the waiting not counted, one class's share applied to all, a person queued rather than told,
    a shed plan that names nothing, a give-back that frees nothing, and a cache that does not
    answer. Each fails with its own sentence, and the keys are removed either way. Delete this and
    the check can pass with the property it names gone."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    import brain.knowledge.uploads as uploads
    from brain.ops import admission, capacity_ledger
    from brain.ops.admission import WorkloadClass
    from tests.unit.test_capacity_ledger import LedgerFake

    fake = LedgerFake()
    if broken == "classes":
        monkeypatch.setattr(uploads, "reading_request", uploads.ingestion_request)
    elif broken == "shares":
        monkeypatch.setattr(
            admission,
            "CLASS_CEILING",
            {
                WorkloadClass.BATCH: 0.5,
                WorkloadClass.BACKGROUND: 0.5,
                WorkloadClass.INTERACTIVE: 1.0,
            },
        )
    elif broken == "shed_batch":
        monkeypatch.setattr(admission, "person_is_waiting", lambda traffic, lane: True)
    elif broken == "positions":
        monkeypatch.setattr(capacity_ledger, "decide", _nobody_waiting_counted())
    elif broken == "one_class":
        monkeypatch.setattr(capacity_ledger, "decide", _decided_as_batch())
    elif broken == "queued_person":
        monkeypatch.setattr(admission, "person_is_waiting", lambda traffic, lane: False)
    elif broken == "plan":
        monkeypatch.setattr(admission, "shed_plan", lambda budgets, state: ())
    elif broken == "kept":
        monkeypatch.setattr(capacity_ledger.CapacityLedger, "give_back", lambda self, hold: True)
    else:
        fake.raises = RedisConnectionError("down")

    outcome, left = classed(fake)

    assert outcome == (FAILED, reason)
    assert left == {}


def test_the_capacity_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_capacity") == [
        "budgets_and_windows_are_rows_saved_within_bounds_and_audited",
        "the_rate_limits_screen_lists_the_windows_refusing_now",
        "capacity_is_sized_for_the_busiest_minute_and_its_first_limit",
        "three_classes_share_one_budget_and_give_way_in_order",
    ]
