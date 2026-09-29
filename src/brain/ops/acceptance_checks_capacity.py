"""The install acceptance checks for capacity: budgets and windows as rows, refusals now, sizing,
and the three workload classes sharing one budget in the install's cache.

Four checks, split where the install's parts split. The first is the database's: a budget and a
request window saved the way the Rate limits screen's route saves them, refused outside the
product's bounds, recorded in the audit ledger against who saved them, read back by the reload
every process runs, and deciding the queued upload's admission from the saved row rather than
the product's figure. The second is the cache's: a reserved person asked past the window in force
in the install's own cache, and the Rate limits screen's own reading of the live windows listing
them as refused now for a reader who may see every window and for nobody narrower. The third is
the Capacity screen's: what its route is sent about sizing at the busiest minute and the first
limit reached at scale, held to the arithmetic it claims. The fourth is the capacity ledger's:
the queued upload's batch request, a background one and the single upload's interactive one taking
and queueing slots of one budget in the install's own cache, refused as capacity only past the
whole of it, the shed plan naming the classes deferred, and every slot given back.

**Nothing a check saves is held by the process running it.** The route holds what it saved at
once, which is right for a person and wrong for a check: the worker or application running the
checks would then answer real requests at the check's figures until its next reload. So the
checks read the saved rows back through the reload's own reader and hand them to the functions
that decide, as `saved=`, and never to `brain.ops.tuning.hold`. See
`A_CHECK_NEVER_CHANGES_WHAT_THE_PROCESS_HOLDS`.

**The rows are uncommitted, so no other process can read them.** A saved knob is an `ops.setting`
row inside the check's transaction, which is rolled back when it ends; a real administrator saving
the same knob during the check waits for it, for
`brain.ops.acceptance_run.A_CHECK_HOLDS_THE_INSTALL_S_WRITE_LOCKS_FOR_SECONDS`' reason and
bound.

**The window check writes the install's cache, under a subject only it holds.** The asker is a
reserved principal named for the run, the windows it fills are registered with `h.removes`, and
reading the live windows reads every window the cache holds and changes none, which is what the
screen does when it is opened. See
`brain.ops.acceptance.WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`.

**The class check takes slots under a namespace only it holds.** `brain.ops.capacity_ledger` keys
every slot by a namespace, and the check's is named for its run, so no real upload is ever counted
against what it takes, queued behind it or refused by it, and its keys are registered with
`h.removes`. Its budget is the install's document-job row with a limit of its own, for
`CHECK_BUDGET`'s reason.

Task ids: M22.1.2, M22.4.1, M22.3.1, M22.3.2, M22.3.4
Task ids: M22.1.3, M22.1.4, M22.1.5, M22.2.1, M22.2.3
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from functools import partial
from typing import Any, Final, cast

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import SET_UP_REACH, Harness

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the checks hand what they saved to the deciding functions rather than hold it.
A_CHECK_NEVER_CHANGES_WHAT_THE_PROCESS_HOLDS: Final = (
    "The route holds a saved value at once, and a check that did the same would have the process "
    "running it answer real requests at the check's figures until its next reload. So the check "
    "reads its uncommitted rows back through the reload's own reader and passes them to the "
    "functions that decide, and the process's held values are the same after the check as before."
)

#: Said when the process running the check has no cache to ask.
NO_CACHE_TO_ASK: Final = (
    "the process running this check was not given the cache address the application uses, so "
    "there is no window to fill; the run inside the application's container can"
)

# ------------------------------------------------------------------------ the figures
#: The authority the route asks before it saves. Restated rather than imported, so a change to
#: the route's authority fails this check instead of moving with it.
CHANGES_LIMITS: Final = "admin:install_setting"

#: The capability the Rate limits screen reads with.
READS_LIMITS: Final = "read:rate_limit"

#: The limit the class check gives its own copy of the document-job budget. Ten, so the three
#: shares are five, eight and ten and every step between them can be seen; the install's own
#: figure may be as low as one, where all three shares are the same slot and there is nothing
#: between the classes to show.
CHECK_BUDGET: Final = 10

#: The window knob and the budget knob the first check saves.
WINDOW_KNOB: Final = "person_per_minute"
BUDGET_KNOB: Final = "document_jobs"


# ------------------------------------------------------------------------ the helpers
def _other_than(current: int, lowest: int, highest: int) -> int:
    """An in-bounds value different from what is in force, so saving it is a visible change."""
    return lowest if current != lowest else min(highest, lowest + 1)


async def _setting_entries(h: Harness, key: str) -> list[tuple[str, dict[str, Any]]]:
    """The actor and details of every ledger entry about one setting in the check's transaction."""
    rows = (
        await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry"
                " WHERE subject = :subject ORDER BY seq"
            ).bindparams(subject=f"setting:{key}")
        )
    ).all()
    return [
        (str(actor), details if isinstance(details, dict) else json.loads(details))
        for actor, details in rows
    ]


# ------------------------------------------------ 1. saved within bounds, audited, deciding
@check(
    leaves=("M22.1.2", "M22.4.1"),
    sentence=(
        "A person holding the Settings authority saves a request window and a document budget as "
        "the Rate limits screen's route does: values outside the product's bounds are refused, "
        "each save is in the audit ledger under their name, the reload every process runs reads "
        "both back, and the queued upload's admission is decided by the saved budget."
    ),
)
async def budgets_and_windows_are_rows_saved_within_bounds_and_audited(h: Harness) -> None:
    from brain.knowledge.uploads import admit_ingestion
    from brain.ops.admission import CapacityState, Resource, WorkloadClass, seed_budgets
    from brain.ops.install_settings import read_tuned
    from brain.ops.limits import LimitScope, request_limits
    from brain.ops.tuning import (
        KNOB_BY_NAME,
        TuningRefusedError,
        configured_budgets,
        held,
        per_minute,
        problem,
        save,
        value,
    )
    from brain.settings_routes import may_configure
    from brain.tables.audit import attributed_to

    before = dict(held())
    await h.found_departments()
    admin = h.principal(A, "tuner")
    reader = h.principal(A, "reader")
    await h.person(admin, department=A, grants=((CHANGES_LIMITS, Scope.unrestricted()),))
    await h.person(reader, department=A, grants=((READS_LIMITS, Scope.unrestricted()),))
    if not may_configure(await h.reach(admin), h.now):
        raise CheckFailedError("the route's own question refused the Settings authority")
    if may_configure(await h.reach(reader), h.now):
        raise CheckFailedError("the route's own question admitted a reader of the screen alone")

    window, budget = KNOB_BY_NAME[WINDOW_KNOB], KNOB_BY_NAME[BUDGET_KNOB]
    async with h.sessions() as session:
        first = await read_tuned(session)
        await session.commit()
    if first is None:
        raise CheckFailedError("the reload every process runs could not read the saved limits")
    wanted = {
        window.name: _other_than(value(window.name, first), window.lowest, window.highest),
        budget.name: _other_than(value(budget.name, first), budget.lowest, budget.highest),
    }

    # Outside the bounds, of an unknown knob, or not a whole number: refused before a write.
    for name, refused in (
        (window.name, window.lowest - 1),
        (window.name, window.highest + 1),
        (budget.name, budget.highest + 1),
        ("acceptance_knob", 1),
    ):
        if not problem(name, refused):
            raise CheckFailedError("a value outside the product's bounds was not refused")
        try:
            async with h.sessions() as session:
                await save(session, name, refused, updated_by=admin)
                await session.commit()
        except TuningRefusedError:
            continue
        raise CheckFailedError("a value outside the product's bounds was written")
    if problem(window.name, 2.5) == "" or problem(window.name, True) == "":
        raise CheckFailedError("a value that is not a whole number was not refused")

    # Saved as the route saves: inside the attribution, one transaction, the saver named.
    async with h.sessions() as session:
        for statement in attributed_to(actor_id=admin, ent_hash=SET_UP_REACH, trace_id=h.trace_id):
            await session.execute(statement)
        for name, amount in wanted.items():
            await save(session, name, amount, updated_by=admin)
        await session.commit()

    async with h.sessions() as session:
        saved = await read_tuned(session)
        await session.commit()
    if saved is None or any(saved.get(name) != amount for name, amount in wanted.items()):
        raise CheckFailedError("the reload every process runs did not read back what was saved")
    for key in (window.key, budget.key):
        entries = await _setting_entries(h, key)
        if not entries or entries[-1][0] != admin:
            raise CheckFailedError("a saved limit is not in the audit ledger under who saved it")

    # In force: the window a request is counted in, and the budget the upload is admitted by.
    counted = request_limits(
        principal_id=admin,
        channel=f"acceptance.{h.run}",
        principal_per_minute=per_minute(LimitScope.PRINCIPAL, saved),
    )
    if counted[0].limit != wanted[window.name]:
        raise CheckFailedError("a request would not be counted against the saved window")
    rows = {one.budget_key: one for one in configured_budgets(saved)}
    row = rows[(Resource.DOCUMENT_JOBS, "")]
    if row.limit != wanted[budget.name] or row.source != "saved":
        raise CheckFailedError("the budgets admission reads did not carry the saved row")
    seed = next(one for one in seed_budgets() if one.budget_key == row.budget_key)

    def starts_now(limit_row: Any, running: int) -> bool:
        return admit_ingestion(
            trace_id=h.trace_id,
            budgets=(limit_row,),
            state=CapacityState(used={(Resource.DOCUMENT_JOBS, ""): running}),
            depth=0,
            now=h.now,
        ).starts_now

    # The largest number running at which one more upload still starts under the saved row, and
    # the smallest at which it waits: the two figures differ exactly where the rows differ.
    share = row.ceiling_for(WorkloadClass.BATCH)
    if not starts_now(row, share - 1) or starts_now(row, share):
        raise CheckFailedError("the queued upload's admission did not follow the saved budget")
    if seed.ceiling_for(WorkloadClass.BATCH) != share and starts_now(seed, share) == starts_now(
        row, share
    ):
        raise CheckFailedError("the queued upload was admitted the same under both budgets")

    if dict(held()) != before:
        raise CheckFailedError("the check changed what the process running it holds")


# ------------------------------------------------------ 2. the screen lists what refuses now
@check(
    leaves=("M22.4.1",),
    sentence=(
        "A reserved person asked past the window in force in the install's own cache is listed as "
        "refused now by the Rate limits screen's reading of the live windows, for a reader who may "
        "see every window, and not for a reader whose grant is one department's."
    ),
)
async def the_rate_limits_screen_lists_the_windows_refusing_now(h: Harness) -> None:
    from brain.cache import make_client
    from brain.console.installation import throttled_now
    from brain.ops.limit_store import make_store, refusals_key, render_key
    from brain.ops.limits import LimitScope, request_limits
    from brain.ops.tuning import per_minute

    if not h.settings.valkey_url:
        raise CheckNotRunError(NO_CACHE_TO_ASK)
    await h.found_departments()
    asker = h.principal(A, "asker")
    everywhere, narrow = h.principal(A, "screen"), h.principal(B, "screen")
    await h.person(everywhere, department=A, grants=((READS_LIMITS, Scope.unrestricted()),))
    await h.person(narrow, department=B, grants=((READS_LIMITS, Scope.department(B)),))

    client = make_client(h.settings.valkey_url)
    store = make_store(client)
    allowed = per_minute(LimitScope.PRINCIPAL)
    limits = request_limits(
        principal_id=asker,
        channel=f"acceptance.{h.run}.limits",
        channel_per_minute=allowed * 4,
    )
    # Only this run's own subjects: see WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME.
    h.removes(
        partial(
            cast(Any, client).delete, *[render_key(one.key) for one in limits], refusals_key(asker)
        )
    )
    start = time.time()
    for n in range(allowed + 1):
        asked = await asyncio.to_thread(
            store.check_and_record,
            now=datetime.fromtimestamp(start + n * 0.01).astimezone(),
            limits=limits,
            caller=asker,
        )
        if asked.degraded:
            raise CheckFailedError("the cache did not answer, so every window failed open")
        if asked.allowed != (n < allowed):
            raise CheckFailedError("the window in force did not refuse exactly past its allowance")

    now = datetime.fromtimestamp(start + (allowed + 1) * 0.01).astimezone()
    live, state = await asyncio.to_thread(store.live, now)
    listed = throttled_now(live, state, await h.reach(everywhere), now=now)
    mine = [one for one in listed if one.subject == asker]
    if len(mine) != 1 or mine[0].scope != LimitScope.PRINCIPAL.value:
        raise CheckFailedError("the screen's reading did not list the window refusing now")
    if mine[0].limit != allowed or mine[0].retry_after_seconds <= 0:
        raise CheckFailedError("the listed window did not carry its allowance and when to ask")
    if any(
        one.subject == asker for one in throttled_now(live, state, await h.reach(narrow), now=now)
    ):
        raise CheckFailedError("a reader of one department was shown a window refusing now")


# ------------------------------------------ 3. sized for the busiest minute, first limit named
@check(
    leaves=("M22.3.1", "M22.3.2", "M22.3.4"),
    sentence=(
        "The Capacity screen's figures, as its route builds them: every sizing is a rate at the "
        "busiest minute with the in-flight figure worked by Little's law, the slots it needs and "
        "where the rate came from, and the first limit reached at ten and at a hundred times "
        "today's volume is named."
    ),
)
async def capacity_is_sized_for_the_busiest_minute_and_its_first_limit(h: Harness) -> None:
    import math

    from brain.install_routes import capacity_plan
    from brain.ops.admission import little_law_concurrency

    del h
    sizings, first_limit = capacity_plan()
    if not sizings:
        raise CheckFailedError("the Capacity screen is sent no sizing")
    for one in sizings:
        if one.peak_per_second <= 0 or one.service_seconds <= 0:
            raise CheckFailedError("a sizing is not stated as a rate at its busiest minute")
        worked = little_law_concurrency(one.peak_per_second, one.service_seconds)
        if not math.isclose(one.in_flight_at_peak, worked):
            raise CheckFailedError("a sizing's in-flight figure is not Little's law of its inputs")
        if one.slots_needed != max(1, math.ceil(worked)):
            raise CheckFailedError("a sizing's slots are not its in-flight figure rounded up")
        if not one.reason.strip():
            raise CheckFailedError("a sizing does not say where its busiest minute came from")
    if len({one.name for one in sizings}) != len(sizings):
        raise CheckFailedError("two sizings share a name, so the screen cannot tell them apart")
    if "10x" not in first_limit or "100x" not in first_limit:
        raise CheckFailedError("the first limit at ten and a hundred times is not named")


# ------------------------------------ 4. three classes share one budget in the install's cache
@check(
    leaves=("M22.1.3", "M22.1.4", "M22.1.5", "M22.2.1", "M22.2.3"),
    sentence=(
        "In the install's cache, under the check's own namespace: batch work is admitted to its "
        "share of one document budget and then queued with a position and an expected wait, "
        "background work is admitted further, work a person waits for fills the budget and is "
        "then refused as capacity while batch still queues, the shed plan names the classes in "
        "the order they give way, and every slot is given back."
    ),
)
async def three_classes_share_one_budget_and_give_way_in_order(h: Harness) -> None:
    import dataclasses
    from datetime import UTC

    from brain.cache import make_client
    from brain.core.errors import Denied
    from brain.core.lane import Lane
    from brain.gate.context import TrafficClass
    from brain.knowledge.uploads import ingestion_request, reading_request
    from brain.ops import admission
    from brain.ops.capacity_ledger import Hold, keys_for, make_ledger
    from brain.ops.tuning import configured_budgets

    if not h.settings.valkey_url:
        raise CheckNotRunError(NO_CACHE_TO_ASK)
    key = (admission.Resource.DOCUMENT_JOBS, "")
    row = next(one for one in configured_budgets() if one.budget_key == key)
    budget = dataclasses.replace(row, limit=CHECK_BUDGET)
    budgets = (budget,)
    client = make_client(h.settings.valkey_url)
    ledger = make_ledger(client, namespace=f"acceptance.{h.run}")
    # Only this run's own keys: see WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME.
    h.removes(partial(cast(Any, client).delete, *keys_for(ledger.namespace, (key,))))

    batch = ingestion_request(h.trace_id)
    person = reading_request(h.trace_id)
    background = admission.AdmissionRequest(
        trace_id=h.trace_id,
        lane=Lane.TASK,
        traffic_class=TrafficClass.AUTOMATION,
        resource=admission.Resource.DOCUMENT_JOBS,
    )
    classes = (batch.workload_class, background.workload_class, person.workload_class)
    if classes != (
        admission.WorkloadClass.BATCH,
        admission.WorkloadClass.BACKGROUND,
        admission.WorkloadClass.INTERACTIVE,
    ):
        raise CheckFailedError("the doors' requests are not classed batch and interactive")
    now = datetime.now(tz=UTC)
    held: list[Hold] = []

    async def take(asked: Any) -> Any:
        taken = await asyncio.to_thread(ledger.admit, asked, budgets, now=now)
        if taken.degraded:
            raise CheckFailedError("the cache did not answer, so no slot was counted")
        if taken.hold is not None:
            held.append(taken.hold)
        return taken.decision

    shares = [budget.ceiling_for(one) for one in admission.SHED_ORDER]
    if not shares[0] < shares[1] < shares[2] == budget.limit:
        raise CheckFailedError("the three classes do not hold three shares of the one budget")
    for _ in range(shares[0]):
        if not (await take(batch)).admitted:
            raise CheckFailedError("batch work was refused or queued inside its share")
    first, second = await take(batch), await take(batch)
    if first.verdict is not admission.Verdict.QUEUED or first.queue is None:
        raise CheckFailedError("batch work past its share was not queued with a position")
    if first.queue.position != 1 or first.queue.expected_wait_seconds <= 0:
        raise CheckFailedError("batch work past its share was not queued with a position")
    if second.queue is None or second.queue.position != 2:
        raise CheckFailedError("a second batch request was not given the next place in line")
    if second.queue.expected_wait_seconds < first.queue.expected_wait_seconds:
        raise CheckFailedError("a second batch request was not given the next place in line")

    for _ in range(shares[1] - shares[0]):
        if not (await take(background)).admitted:
            raise CheckFailedError("background work was not admitted past the batch share")
    if (await take(background)).verdict is not admission.Verdict.QUEUED:
        raise CheckFailedError("background work past its own share was not queued")

    for _ in range(shares[2] - shares[1]):
        if not (await take(person)).admitted:
            raise CheckFailedError("work a person waits for was not admitted to the whole budget")
    refused = await take(person)
    if refused.verdict is not admission.Verdict.SHED or not refused.retry_after_seconds:
        raise CheckFailedError("work a person waits for past the budget was not refused")
    error = refused.as_error()
    if not isinstance(error, admission.CapacityRefused) or isinstance(error, Denied):
        raise CheckFailedError("work a person waits for past the budget was not refused")
    if refused.log_record()["refusal_kind"] != admission.RefusalKind.CAPACITY.value:
        raise CheckFailedError("work a person waits for past the budget was not refused")
    if (await take(batch)).verdict is not admission.Verdict.QUEUED:
        raise CheckFailedError("batch work was not still queued while a person was refused")

    state = await asyncio.to_thread(ledger.counts, budgets, now=now)
    named = [one.workload_class for one in admission.shed_plan(budgets, state)]
    if named != list(admission.SHED_ORDER):
        raise CheckFailedError("the shed plan did not name the classes deferred in order")

    for one in held:
        await asyncio.to_thread(ledger.give_back, one)
    after = await asyncio.to_thread(ledger.counts, budgets, now=now)
    if after.used_for(key) or after.queued_for(key):
        raise CheckFailedError("a slot or a place given back is still counted")
    again = await take(batch)
    if not again.admitted:
        raise CheckFailedError("a slot or a place given back is still counted")
    await asyncio.to_thread(ledger.give_back, held[-1])
