"""The recording and refusal install checks: what each names, passing on PostgreSQL, not run without
an object store, and made to fail with the product broken the way it plausibly would.

The database half builds PostgreSQL at head and runs the module as the worker does. Without an
object store (this database has none) the recording check is **not run** after its first half has
passed, and a test hands it a store that is a dictionary to show the second half passing too. Each
check is then run against a product broken in the one place a property of its sentence rests on.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M19.6.5, M19.6.6, M19.9.9, M19.9.11
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_checks_browser_records as module
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_records"
RECORDING = "a_browser_recording_is_kept_and_removed_when_its_time_has_passed"
LIMITS = "browser_sessions_are_limited_and_a_halt_stops_a_run"


def test_the_module_declares_the_two_checks_and_the_leaves_each_closes() -> None:
    """Delete this and a check can lose a leaf with the page showing the same row, or sit outside
    the keys this package was given."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (RECORDING, ("M19.6.6", "M19.9.11")),
        (LIMITS, ("M19.6.5", "M19.9.9")),
    ]
    assert checks_in(MODULE) == [RECORDING, LIMITS]
    assert 2300 <= module.CHECK_ORDER <= 2399


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_records") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


class Memory:
    """An object store backend that keeps what it is handed. `forgetful` refuses to delete."""

    def __init__(self, *, forgetful: bool = False) -> None:
        self.held: dict[tuple[str, str], bytes] = {}
        self.forgetful = forgetful

    def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self.held[(bucket, key)] = body

    def get_object(self, bucket: str, key: str) -> bytes:
        return self.held[(bucket, key)]

    def delete_object(self, bucket: str, key: str) -> None:
        if not self.forgetful:
            self.held.pop((bucket, key), None)

    def list_objects(self, bucket: str, prefix: str) -> Iterator[str]:
        return iter([key for (name, key) in self.held if name == bucket and key.startswith(prefix)])


def connected(monkeypatch: pytest.MonkeyPatch, backend: Memory) -> Memory:
    from brain.ops import object_store

    def start(*args: Any, **kw: Any) -> object_store.ObjectStore:
        return object_store.ObjectStore(backend=backend, prefix="install-a")  # type: ignore[arg-type]

    monkeypatch.setattr(object_store, "object_store_at_start", start)
    return backend


# ------------------------------------------------------------------ on an install
@pytest.mark.needs_db
def test_the_recording_check_is_not_run_without_a_store_and_the_limits_check_passes(
    install: str,
) -> None:
    """**The module as the worker runs it.** With no object store the recording check has shown its
    first half and says in a sentence that it could not show the second, and the limits check
    passes and leaves nothing behind. Delete this and a store-less install either passes a check it
    could not make or fails one it cannot pass."""
    before = counts(install)

    outcomes = run_checks(install, registered((MODULE,)))

    assert outcomes[RECORDING] == (NOT_RUN, module.NO_STORE_IS_CONNECTED)
    assert outcomes[LIMITS] == (PASSED, "")
    assert counts(install) == before


@pytest.mark.needs_db
def test_with_a_store_connected_the_recording_check_passes_on_it_and_leaves_nothing(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive case for the second half, on a dictionary standing in for the bucket. The
    prefix is the install's, and what the check wrote is gone afterwards. Delete this and the half
    that touches the install's own store is never run by any test."""
    store = connected(monkeypatch, Memory())

    outcome = run_checks(install, registered((MODULE,)))[RECORDING]

    assert outcome == (PASSED, "")
    assert store.held == {} or all(key.startswith("install-a/") for _, key in store.held)
    assert not any("acceptance-" in key for _, key in store.held)


@pytest.mark.needs_db
def test_a_store_that_keeps_what_it_is_told_to_delete_fails_the_recording_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a pass that reports a removal the store never made is believed."""
    connected(monkeypatch, Memory(forgetful=True))

    outcome = run_checks(install, registered((MODULE,)))[RECORDING]

    assert outcome[0] == FAILED and "not removed" in outcome[1]


@pytest.mark.needs_db
def test_a_pass_that_removes_nothing_fails_the_recording_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the pass always reporting only, the first half says so. Delete this and a retention
    pass that never removes anything is the one this check believes."""
    from brain.browsing import recording_sweep

    real = recording_sweep.sweep

    async def only_reports(*a: Any, **kw: Any) -> Any:
        return await real(*a, **{**kw, "report_only": True})

    monkeypatch.setattr(recording_sweep, "sweep", only_reports)

    outcome = run_checks(install, registered((MODULE,)))[RECORDING]

    assert outcome[0] == FAILED and "not removed" in outcome[1]


@pytest.mark.needs_db
def test_a_pass_that_ignores_a_hold_fails_the_recording_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a retention pass that removes a recording a legal hold names passes."""
    from brain.browsing import recording_sweep

    monkeypatch.setattr(recording_sweep, "runs_held", lambda holds, askers, runs: frozenset())

    outcome = run_checks(install, registered((MODULE,)))[RECORDING]

    assert outcome[0] == FAILED


@pytest.mark.needs_db
def test_a_counter_that_counts_nothing_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the per-site and per-agent limits are proved by decisions nothing feeds."""
    from brain.browsing import driver
    from brain.browsing.concurrency import SessionCounts

    async def nothing(session: object, registry: object) -> SessionCounts:
        return SessionCounts()

    monkeypatch.setattr(driver, "held_counts", nothing)

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED and "full was admitted" in outcome[1]


@pytest.mark.needs_db
def test_a_run_that_ignores_the_halt_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a run that never asks the halt between instructions passes, so the stop
    button stops only the sessions that have not started."""
    from brain.browsing import driver

    monkeypatch.setattr(driver, "stopped_now", lambda halts: False)

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED and "between two instructions" in outcome[1]


@pytest.mark.needs_db
def test_a_session_admitted_while_halted_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a driver that stops asking the halt before a new session passes."""
    from brain.browsing import concurrency, driver
    from brain.ops.halt import NOTHING_HALTED

    real = concurrency.may_open

    def ignoring(*a: Any, **kw: Any) -> Any:
        return real(*a, **{**kw, "halts": NOTHING_HALTED})

    monkeypatch.setattr(driver, "may_open", ignoring)

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED and "could not say it was running" in outcome[1]


# ------------------------------------------------------------ each statement of the checks
@pytest.mark.needs_db
def test_a_report_that_misses_what_is_due_fails_the_recording_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a report-only pass that finds nothing, which is the one a person reads
    before releasing the sweep, is believed because the real pass still removes."""
    from brain.browsing import recording_sweep
    from brain.browsing.recording import Removal

    real = recording_sweep.sweep

    async def blind_report(*a: Any, **kw: Any) -> Any:
        found = await real(*a, **kw)
        return found if not kw["report_only"] else recording_sweep.Swept(Removal(), False)

    monkeypatch.setattr(recording_sweep, "sweep", blind_report)

    outcome = run_checks(install, registered((MODULE,)))[RECORDING]

    assert outcome[0] == FAILED and "exactly one recording due" in outcome[1]


@pytest.mark.needs_db
def test_a_report_only_pass_that_removes_fails_the_recording_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and report-only mode that deletes is the one thing the check does not notice."""
    from brain.browsing import recording_sweep

    real = recording_sweep.sweep

    async def always_removes(*a: Any, **kw: Any) -> Any:
        return await real(*a, **{**kw, "report_only": False})

    monkeypatch.setattr(recording_sweep, "sweep", always_removes)

    outcome = run_checks(install, registered((MODULE,)))[RECORDING]

    assert outcome[0] == FAILED and "report-only mode removed" in outcome[1]


@pytest.mark.needs_db
def test_a_pass_that_removes_a_recording_inside_its_window_fails_the_recording_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a pass that removes too much, a recording still inside its window, passes
    as long as the one it should have removed is gone."""
    from brain.browsing import recording_sweep

    real = recording_sweep.sweep

    async def greedy(sessions: Any, backend: Any, *, now: Any, report_only: bool) -> Any:
        found = await real(sessions, backend, now=now, report_only=report_only)
        if not report_only:
            for key in list(backend.list_objects("recordings", "browser-runs/")):
                backend.delete_object("recordings", key)
        return found

    monkeypatch.setattr(recording_sweep, "sweep", greedy)

    outcome = run_checks(install, registered((MODULE,)))[RECORDING]

    assert outcome[0] == FAILED and "inside its window or under a hold" in outcome[1]


def refusing_once(monkeypatch: pytest.MonkeyPatch, change: Any) -> None:
    from brain.browsing import driver

    real = driver.room_for
    asked = {"times": 0}

    def room_for(*a: Any, **kw: Any) -> Any:
        asked["times"] += 1
        return change(asked["times"], real, a, kw)

    monkeypatch.setattr(driver, "room_for", room_for)


@pytest.mark.needs_db
def test_a_made_up_target_with_no_room_for_its_first_session_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a driver that refuses every session passes, because every later question
    only looks for a refusal."""
    from brain.browsing.concurrency import SessionDecision

    def refuse_the_first(times: int, real: Any, a: Any, kw: Any) -> Any:
        found = real(*a, **kw)
        if times == 1:
            return SessionDecision(
                admitted=False, admission=found.admission, over=(), reason="no room"
            )
        return found

    refusing_once(monkeypatch, refuse_the_first)

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED and "no room for its first session" in outcome[1]


@pytest.mark.needs_db
def test_a_global_budget_nothing_enforces_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a driver that stops counting browser sessions against the global budget
    passes while a site and an agent are still limited."""
    from brain.ops.admission import CapacityState

    def ignore_the_budget(times: int, real: Any, a: Any, kw: Any) -> Any:
        return real(*a, **{**kw, "state": CapacityState()})

    refusing_once(monkeypatch, ignore_the_budget)

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED and "global budget" in outcome[1]


@pytest.mark.needs_db
def test_a_refusal_that_does_not_say_what_is_full_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a person turned away is told only that there was no room."""
    from dataclasses import replace

    def say_nothing(times: int, real: Any, a: Any, kw: Any) -> Any:
        return replace(found, reason="no room") if (found := real(*a, **kw)).over else found

    refusing_once(monkeypatch, say_nothing)

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED and "was not told which site and agent" in outcome[1]


@pytest.mark.needs_db
def test_a_halted_run_that_leaves_no_recording_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a stop that loses the transcript of what the run did before it was stopped
    passes."""
    from brain.browsing import driver

    monkeypatch.setattr(driver, "write", lambda backend, recording: ())

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED and "left no recording" in outcome[1]


@pytest.mark.needs_db
def test_a_halted_run_that_leaves_its_session_open_fails_the_limits_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a stop that never closes the session leaves the site and the agent counted
    as full for ever."""
    from brain.browsing.driver import DatabaseLedger

    async def never_closes(self: DatabaseLedger, *, run_id: str, at: Any, recording: Any) -> None:
        return None

    monkeypatch.setattr(DatabaseLedger, "closed", never_closes)

    outcome = run_checks(install, registered((MODULE,)))[LIMITS]

    assert outcome[0] == FAILED
