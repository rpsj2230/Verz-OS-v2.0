"""The install acceptance checks for capacity: budgets and windows as rows, and what refuses now.

Two checks, split where the install's parts split. The first is the database's: a budget and a
request window saved the way the Rate limits screen's route saves them, refused outside the
product's bounds, recorded in the audit ledger against who saved them, read back by the reload
every process runs, and deciding the queued upload's admission from the saved row rather than
the product's figure. The second is the cache's: a reserved person asked past the window in force
in the install's own cache, and the Rate limits screen's own reading of the live windows listing
them as refused now for a reader who may see every window and for nobody narrower.

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

Task ids: M22.1.2, M22.4.1
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
