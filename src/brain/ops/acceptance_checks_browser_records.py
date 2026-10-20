"""Install acceptance checks for what a browser run leaves behind and what stops one: its recording,
the sessions it holds open, and the halt.

**The first check keeps a recording the way the schedule does and removes it the same way.** A
transcript is written under the install's prefix by the code the driver calls at run end, aged past
its window, and the pass the retention schedule runs (`brain.browsing.recording_sweep.sweep`)
removes it, keeps the one a legal hold names and counts the one it cannot date. That half uses a
bucket the check holds. The second half does it again on the install's own object store, with the
objects the check writes under run ids of its own and a listing that shows the sweep only those,
because a check must not remove a person's real recording that has simply come due. An install
with no object store connected is **not run** for that half, in one sentence.

**The second check is about refusal.** A session past the global budget, past a site's limit or past
an agent's is refused with a sentence that names what is full; a halt refuses a new session; and a
halt raised while a run is in flight stops it between two instructions with its session closed and
its recording kept. It uses the product's own runner with a page the check holds, as the check at
`CHECK_ORDER` 2301 does (`A_RUNNER_IN_THE_PROCESS_IS_THE_RUNNER_AND_THE_PAGE_IS_A_STAND_IN`).

Everything either check writes to the database is in the check's transaction and rolled back with
it.

Task ids: M19.6.5, M19.6.6, M19.9.9, M19.9.11
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after the browser module's (2301, 2302).
CHECK_ORDER: Final = 2303

A, _ = RESERVED_DEPARTMENTS

NO_STORE_IS_CONNECTED: Final = (
    "This install connects no object store, so the recording sweep was shown on a bucket the "
    "check holds and not on the install's own."
)


@dataclass
class _Scoped:
    """A backend that shows the sweep only the check's own runs.

    The sweep lists a bucket by prefix, and a real bucket may hold a real recording that has come
    due. The check is about the sweep's decisions, so it hands the sweep a view in which only the
    runs it wrote exist, and deletes through to the same store.
    """

    inner: Any
    runs: frozenset[str]

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.inner.put_object(bucket_name, key, body, content_type)

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return bytes(self.inner.get_object(bucket_name, key))

    def delete_object(self, bucket_name: str, key: str) -> None:
        self.inner.delete_object(bucket_name, key)

    def list_objects(self, bucket_name: str, prefix: str) -> Any:
        return iter(
            [
                key
                for key in self.inner.list_objects(bucket_name, prefix)
                if any(f"/{run}/" in key for run in self.runs)
            ]
        )


def _put_aged(backend: Any, run: str, age_days: int, h: Harness) -> str:
    """Write a one-line transcript for `run` as though its run began `age_days` ago."""
    from brain.browsing.recording import Direction, record, write
    from brain.browsing.wire import Kind, encode

    started = h.now - timedelta(days=age_days)
    stub = record(
        run,
        started,
        (
            (Direction.TO_RUNNER, encode(Kind.STOP)),
            (Direction.FROM_RUNNER, encode(Kind.ENDED, reason="stopped")),
        ),
        (),
        keep_pictures=frozenset(),
    )
    return write(backend, stub)[0]


async def _hold_on(h: Harness, run: str) -> None:
    """A legal hold naming one run's session, placed in the check's transaction."""
    from sqlalchemy import text

    await h.execute(
        text(
            "INSERT INTO obs.legal_hold (id, reason_code, subjects, actors, all_subjects, "
            "placed_at, placed_by) VALUES (:id, 'acceptance', ARRAY[:subject]::varchar[], "
            "'{}'::varchar[], false, :at, :by)"
        ).bindparams(
            id=f"hold-{h.run}", subject=f"session:{run}", at=h.now - timedelta(days=1), by=h.actor
        )
    )


# ------------------------------------------------------------------ 1. the recording
@check(
    leaves=("M19.6.6", "M19.9.11"),
    sentence=(
        "A browser recording is written under the install's object-store prefix at the end of a "
        "run, the retention schedule removes the ones past their window, keeps the one a legal "
        "hold names and counts the one it cannot date, and does the same on this install's own "
        "object store."
    ),
)
async def a_browser_recording_is_kept_and_removed_when_its_time_has_passed(h: Harness) -> None:
    from brain.browsing.recording_sweep import Under, sweep
    from brain.ops.retention import RECORDING_RETENTION_DAYS
    from brain.ops.storage import ObjectKind, bucket_for

    bucket = bucket_for(ObjectKind.BROWSER_RUN_RECORDING).name
    old, fresh, held = (f"acceptance-{h.run}-{one}" for one in ("old", "fresh", "held"))
    mine = frozenset({old, fresh, held})
    await h.found_departments()
    await _hold_on(h, held)

    async def pass_over(backend: Any) -> None:
        past = RECORDING_RETENTION_DAYS + 3
        keys = {
            run: _put_aged(backend, run, age, h)
            for run, age in ((old, past), (fresh, 1), (held, past))
        }
        view = _Scoped(backend, mine)
        report = await sweep(h.sessions, view, now=h.now, report_only=True)
        if len(report.found.due) != 1 or report.found.held != 1:
            raise CheckFailedError(
                "the retention pass did not find exactly one recording due and one held"
            )
        if keys[old] not in set(view.list_objects(bucket, "browser-runs/")):
            raise CheckFailedError("the retention pass in report-only mode removed a recording")
        await sweep(h.sessions, view, now=h.now, report_only=False)
        remaining = set(view.list_objects(bucket, "browser-runs/"))
        if keys[old] in remaining:
            raise CheckFailedError("a recording past its window was not removed by the pass")
        if keys[fresh] not in remaining or keys[held] not in remaining:
            raise CheckFailedError("a recording inside its window or under a hold was removed")
        for key in (keys[fresh], keys[held]):
            backend.delete_object(bucket, key)

    await pass_over(_Memory())

    from brain.ops.object_store import key_prefix, object_store_at_start

    store = await asyncio.to_thread(
        object_store_at_start, h.settings.vault_address, h.settings.vault_token
    )
    if store.backend is None:
        raise CheckNotRunError(NO_STORE_IS_CONNECTED)
    real = Under(store.backend, key_prefix(bucket, store.prefix))
    h.removes(partial(_forget, real, bucket, mine))
    await pass_over(real)


def _forget(backend: Any, bucket: str, runs: frozenset[str]) -> None:
    """Remove whatever the check left for its runs, if the pass did not."""
    for key in list(backend.list_objects(bucket, "browser-runs/")):
        if any(f"/{run}/" in key for run in runs):
            backend.delete_object(bucket, key)


class _Memory:
    """A bucket that keeps what it is handed."""

    def __init__(self) -> None:
        self._held: dict[tuple[str, str], bytes] = {}

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self._held[(bucket_name, key)] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self._held[(bucket_name, key)]

    def delete_object(self, bucket_name: str, key: str) -> None:
        self._held.pop((bucket_name, key), None)

    def list_objects(self, bucket_name: str, prefix: str) -> Any:
        return iter([key for (name, key) in self._held if name == bucket_name])


# ------------------------------------------------------------------ 2. refusal and the halt
@check(
    leaves=("M19.6.5", "M19.9.9"),
    sentence=(
        "A browser session past the global budget, a website's limit or an agent's is refused with "
        "a sentence naming what is full, a halt refuses a new session, and a halt raised while a "
        "run is in flight stops it between two instructions with its session closed."
    ),
)
async def browser_sessions_are_limited_and_a_halt_stops_a_run(h: Harness) -> None:
    from brain.browsing.concurrency import Axis
    from brain.browsing.driver import (
        DatabaseLedger,
        ReadOnlyActor,
        RunDeps,
        held_counts,
        prepare_run,
        room_for,
        run_envelope,
    )
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.sessions import BROWSE_SURFACE, surface_scope
    from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
    from brain.gate.injection import AutonomyTier
    from brain.gate.suspension_store import StoredSuspensions
    from brain.ops.acceptance_checks_browser import (
        STAND_IN_ORIGIN,
        InProcessRunner,
        StandInPage,
        _Link,
    )
    from brain.ops.admission import CapacityState, Resource, seed_budgets
    from brain.ops.halt import NOTHING_HALTED, HaltState

    await h.found_departments()
    asker = h.principal(A, "browser_limits")
    target = Target(
        name=f"acceptance_{h.run}_limits",
        origins=frozenset({STAND_IN_ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=STAND_IN_ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=BROWSE_SURFACE,
                reads=("number",),
            ),
        ),
    )
    await h.person(asker, department=A, grants=((BROWSE_SURFACE.value, surface_scope(target)),))
    asking = await h.reach(asker)
    registry = TargetRegistry(targets=(target,))
    agent = f"acceptance_{h.run}_agent"
    store = StoredSuspensions(h.sessions)
    budgets = tuple(one for one in seed_budgets() if one.resource is Resource.BROWSER_SESSIONS)
    ledger = DatabaseLedger(h.sessions, asker)

    async def envelope_for(name: str) -> Any:
        async with store.holding(asking, h.now) as rows:
            return await prepare_run(
                rows.session,
                plan(
                    PlanRequest(
                        goal=Goal(text="Read the check's invoices", asked_by=asker),
                        target=target.name,
                        surfaces=("invoices",),
                    ),
                    registry,
                ),
                target,
                run_id=f"acceptance_{h.run}_{name}",
                agent_id=agent,
                reach=asking,
                ceiling=AutonomyTier.AUTONOMOUS,
                trace_id=h.trace_id,
                now=h.now,
            )

    async def room(*, state: CapacityState | None = None, halts: HaltState = NOTHING_HALTED) -> Any:
        async with h.sessions() as session:
            counts = await held_counts(session, registry)
        return room_for(
            target,
            agent_id=agent,
            trace_id=h.trace_id,
            budgets=budgets,
            state=state or CapacityState(),
            counts=counts,
            now=h.now,
            halts=halts,
        )

    first = await envelope_for("first")
    if not (await room()).admitted:
        raise CheckFailedError("a made-up target had no room for its first session")

    full = CapacityState(used={(Resource.BROWSER_SESSIONS, ""): budgets[0].limit})
    over_all = await room(state=full)
    if over_all.admitted or "browser" not in over_all.reason.lower():
        raise CheckFailedError("a session past the global budget was admitted or not told why")

    await ledger.opened(run_id=first.run_id, trace_id=h.trace_id, at=h.now)
    over_site = await room()
    if over_site.admitted or {axis for axis, _ in over_site.over} != {Axis.AGENT, Axis.DOMAIN}:
        raise CheckFailedError("a session on a site and an agent that were full was admitted")
    if STAND_IN_ORIGIN not in over_site.reason or "agent" not in over_site.reason:
        raise CheckFailedError("a refused session was not told which site and agent were full")
    await ledger.closed(run_id=first.run_id, at=h.now + timedelta(seconds=1), recording=None)

    stopped = await room(halts=HaltState.unknown())
    if stopped.admitted or not stopped.admission.halted:
        raise CheckFailedError(
            "a new session was admitted while the system could not say it was running"
        )

    # A halt raised while a run is in flight. The page records how far the run got.
    second = await envelope_for("second")
    runner = InProcessRunner(StandInPage())

    async def connect() -> _Link:
        return _Link(runner)

    def halts() -> HaltState:
        return HaltState.unknown() if runner.page.navigated else NOTHING_HALTED

    result = await run_envelope(
        second,
        target,
        approval=None,
        deps=RunDeps(
            connect=connect,
            ledger=ledger,
            actor=ReadOnlyActor(second),
            clock=lambda: h.now,
            halts=halts,
            backend=_Memory(),
        ),
        trace_id=h.trace_id,
    )
    if not result.started or result.actions != 1 or result.findings:
        raise CheckFailedError("a run was not stopped between two instructions by a halt")
    if not result.keys or result.digest is None:
        raise CheckFailedError("a run stopped by a halt left no recording")
    if (await room()).over:
        raise CheckFailedError("a run stopped by a halt left its session counted as open")
