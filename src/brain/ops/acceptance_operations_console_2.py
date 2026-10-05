"""Install acceptance checks for operating the install from the console: what runs and waits, the
scheduled jobs, the tool catalogue and its switch, and a connected source's page, export and test.

Every check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`): an
application holding the check's sessions, and the asking the gate would hand the route for a
reserved person on the console, with a second factor for anybody pressing an administrator's
button.

**A run row is written as the worker writes it.** `ops.control_run` is the scheduler's record and
the application role only reads it, so the run rows these checks put on the Live runs and job
pages are written as the login the run connected as, inside a savepoint of the check's
transaction, and are rolled back with everything else. See
`A_RUN_ROW_IS_THE_WORKER_S_AND_IS_WRITTEN_AS_IT`.

**A connected source is a tenant made up for the check, and nothing reaches it.** The source is
Xero, connected through the store the Connectors screen's routes call, with a tenant id nothing
else holds and no key kept anywhere; the test of it is made by the worker's own pass,
`brain.ops.connector_probe_run.probe_on`, with a transport that answers from memory, so no
address is resolved and no request leaves the process. An install that has Xero connected
already is not run, because the check would be connecting over somebody's real connection. See
`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

Task ids: M27.2.2, M27.8.13, M27.15.47, M27.15.7, M27.15.36, M27.15.39
Task ids: M27.2.4, M27.12.2, M27.15.8
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.sql import Executable

    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.controls import Control

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 321

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a run row is written as the login.
A_RUN_ROW_IS_THE_WORKER_S_AND_IS_WRITTEN_AS_IT: Final = (
    "The scheduler's run record is written by the worker and only read by the application, so a "
    "check putting a run on the Live runs or a job's page writes it as the login the run "
    "connected as, inside a savepoint of its own transaction, and the row is rolled back with "
    "everything else the check wrote."
)

#: Said when Xero is connected on this install already.
A_SOURCE_IS_CONNECTED_HERE_ALREADY: Final = (
    "Xero is connected on this install, and the check connects a tenant of its own under the "
    "same name, so it would be writing over a real connection; it runs on an install without one"
)

#: Said when the run's login may not write the scheduler's run record.
THE_RUN_RECORD_IS_NOT_WRITABLE_HERE: Final = (
    "the login this check runs as may not write the scheduler's run record, so no run can be "
    "put on the page to be shown"
)

# ------------------------------------------------------------------------ the figures
#: The authorities the checks' administrators hold. Restated rather than imported, so a change
#: to a route's authority fails its check instead of moving with it.
CONTROLS_THE_SCHEDULE: Final = "admin:schedule"
SWITCHES_FEATURES: Final = "admin:feature"
SWITCHES_TOOLS: Final = "admin:tool"
CONNECTS_SOURCES: Final = "admin:connector"

#: The reason the tools check gives for switching its tool back on.
BACK_ON_BECAUSE: Final = "Checked by the install acceptance run and safe to run again"


# ------------------------------------------------------------------------ the helpers
async def as_login(h: Harness, *statements: Executable) -> None:
    """Statements run as the login the run connected as. See
    `A_RUN_ROW_IS_THE_WORKER_S_AND_IS_WRITTEN_AS_IT`."""
    from sqlalchemy.exc import DBAPIError

    from brain.session import SET_APPLICATION_ROLE

    try:
        async with h.connection.begin_nested():
            await h.connection.execute(text("RESET ROLE"))
            for one in statements:
                await h.connection.execute(one)
            await h.connection.exec_driver_sql(SET_APPLICATION_ROLE)
    except DBAPIError as exc:
        raise CheckNotRunError(THE_RUN_RECORD_IS_NOT_WRITABLE_HERE) from exc


def a_job() -> Control:
    """The first job the scheduler may run that deletes nothing, by the registry's order."""
    from brain.ops.schedule import DESTRUCTIVE, schedulable

    return next(one for one in schedulable() if one.name not in DESTRUCTIVE)


# ------------------------------------------------------- 1. live runs and the queue (M27.2.2)
@check(
    leaves=("M27.2.2",),
    sentence=(
        "A run of a scheduled job started by the worker and not finished is listed on Live runs, "
        "by the route that page calls, for a reader of running work; the queue lists every "
        "scheduled job for a reader of the queue; a person with neither is shown empty lists, "
        "the same as an install running nothing."
    ),
)
async def what_runs_and_what_waits_is_shown_to_its_readers(h: Harness) -> None:
    from brain.jobs_routes import jobs
    from brain.operate_routes import live_runs
    from brain.ops.schedule import schedulable
    from brain.tables.schedule import ControlRunRow

    await h.found_departments()
    watcher, other = h.principal(A, "runs"), h.principal(A, "other")
    both = dict.fromkeys((*screen_grants("runs"), *screen_grants("queue")))
    await h.person(watcher, department=A, grants=tuple(both))
    await h.person(other, department=A)
    job = a_job()
    started = datetime.now(UTC)
    await as_login(h, insert(ControlRunRow).values(name=job.name, started_at=started))

    console = console_for(h)
    shown = await live_runs(console.request(), await asking_as(h, watcher))
    if [one.control for one in shown.running if one.control == job.name] != [job.name]:
        raise CheckFailedError("Live runs did not list a run the worker started and not finished")
    hidden = await live_runs(console.request(), await asking_as(h, other))
    if hidden.running or hidden.waiting:
        raise CheckFailedError("Live runs showed a run to a person who may not see running work")

    queued = await jobs(console.request(), await asking_as(h, watcher))
    if {one.control for one in queued.jobs} != {one.name for one in schedulable()}:
        raise CheckFailedError("the queue did not list every scheduled job to its reader")
    if (await jobs(console.request(), await asking_as(h, other))).jobs:
        raise CheckFailedError("the queue listed a job to a person who may not see the queue")


# ------------------------------------------------- 2. a job controlled from the console (M27.8.13)
@check(
    leaves=("M27.8.13", "M27.15.47"),
    sentence=(
        "With pausing switched on from Features, an administrator pauses a scheduled job, asks "
        "for a run and resumes it through the Jobs routes, each audited under their name; the "
        "pause is a row the worker's schedule reads at every start; the job's page lists its "
        "past runs newest first and says what a job nothing can run needs; anybody else is "
        "refused."
    ),
)
async def a_job_is_paused_run_and_resumed_and_lists_its_runs(h: Harness) -> None:
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.jobs_routes import job_runs, jobs, pause_job, resume_job, run_job
    from brain.listing import ListAsked
    from brain.ops.features import SCHEDULE_CONTROL
    from brain.ops.schedule_control import paused_controls
    from brain.tables.schedule import ControlRunRow

    await h.found_departments()
    admin, reader = h.principal(A, "jobs"), h.principal(A, "reader")
    grants = (
        (CONTROLS_THE_SCHEDULE, Scope.unrestricted()),
        (SWITCHES_FEATURES, Scope.unrestricted()),
        *screen_grants("queue"),
    )
    await h.person(admin, department=A, grants=grants)
    await h.person(reader, department=A, grants=screen_grants("queue"))
    console = console_for(h)
    job = a_job()
    async with traced(h, 1):
        await switch_feature(
            console.request("POST"),
            SCHEDULE_CONTROL.name,
            SwitchAsked(on=True),
            await asking_as(h, admin, strong=True),
        )
    if not await refused(pause_job(console.request("POST"), job.name, await asking_as(h, reader))):
        raise CheckFailedError("a reader of the queue paused a job")

    async with traced(h, 2):
        paused = await pause_job(
            console.request("POST"), job.name, await asking_as(h, admin, strong=True)
        )
    if not paused.paused or paused.changed_by != admin:
        raise CheckFailedError("a job paused from the console was not held as paused")
    async with h.sessions() as session:
        read_at_start = await paused_controls(session)
        await session.commit()
    if job.name not in read_at_start:
        raise CheckFailedError("a pause is not a row the worker's schedule reads when it starts")
    async with traced(h, 3):
        asked_for = await run_job(
            console.request("POST"), job.name, await asking_as(h, admin, strong=True)
        )
    if asked_for.run_requested_at is None:
        raise CheckFailedError("a run asked for from the console was not recorded")
    listed = await jobs(console.request(), await asking_as(h, admin, strong=True))
    row = next((one for one in listed.jobs if one.control == job.name), None)
    if row is None or not row.paused or row.pause_changed_by != admin or not row.run_pending:
        raise CheckFailedError("the Jobs screen did not show the pause and the run asked for")
    if any(one.runnable == bool(one.needs) for one in listed.jobs):
        raise CheckFailedError("a job nothing can run did not say what it needs")
    async with traced(h, 4):
        resumed = await resume_job(
            console.request("POST"), job.name, await asking_as(h, admin, strong=True)
        )
    if resumed.paused:
        raise CheckFailedError("a job resumed from the console was still paused")
    entries = (
        await h.execute(
            text(
                "SELECT count(*) FROM obs.audit_entry WHERE actor_id = :actor"
                " AND subject LIKE 'setting:%' AND trace_id LIKE :trace"
            ).bindparams(actor=admin, trace=f"{h.trace_id}-c%")
        )
    ).scalar_one()
    if int(entries) < 4:
        raise CheckFailedError("a change to a job from the console is not in the audit trail")

    older, newer = datetime(2019, 3, 4, 9, tzinfo=UTC), datetime(2019, 3, 5, 9, tzinfo=UTC)
    await as_login(
        h,
        insert(ControlRunRow).values(
            name=job.name,
            started_at=older,
            finished_at=older + timedelta(seconds=1),
            outcome="failed",
            detail="ValueError: acceptance",
        ),
        insert(ControlRunRow).values(
            name=job.name,
            started_at=newer,
            finished_at=newer + timedelta(seconds=1),
            outcome="ok",
            detail="acceptance run",
        ),
    )
    runs = await job_runs(
        console.request(), job.name, await asking_as(h, reader), ListAsked(limit=200)
    )
    mine = [one for one in runs.items if one.started_at in (older, newer)]
    if [(one.outcome, one.failure_kind) for one in mine] != [
        ("ok", None),
        ("failed", "ValueError"),
    ]:
        raise CheckFailedError("a job's page did not list its past runs newest first")


# --------------------------------------------- 3. the tool catalogue and its switch (M27.15.7)
@check(
    leaves=("M27.15.7", "M27.15.36"),
    sentence=(
        "A Super Admin is shown every tool the install registers, each with its required "
        "capability, side effect and source, by the route the Tools tab calls; switching one off "
        "for the install there refuses every call to it at once, and switching it back on with a "
        "reason lets calls through; a person without the authority is refused."
    ),
)
async def every_tool_is_listed_and_one_switched_off_is_refused(h: Harness) -> None:
    from brain.ops.acceptance_checks_tools import SWITCHED, _called, _install_registry
    from brain.ops.tool_store import SessionSwitchSource
    from brain.tool_routes import ToolSwitchAsked, switch_tool, tools

    registry = _install_registry(h).govern(SessionSwitchSource(h.sessions))
    if not registry.has(SWITCHED):
        raise CheckFailedError("the install does not register the tool the check switches")
    await h.found_departments()
    admin, member, other = (h.principal(A, role) for role in ("tools", "member", "other"))
    await h.person(admin, department=A, grants=((SWITCHES_TOOLS, Scope.unrestricted()),))
    await h.person(member, department=A)
    await h.person(other, department=A)
    console = console_for(h)
    console.app.state.tools = registry
    if not await refused(tools(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person without the authority was shown the Tools tab")

    page = await tools(console.request(), await asking_as(h, admin, strong=True))
    listed = {one.name: one for one in page.tools}
    if not set(registry.names()) <= set(listed):
        raise CheckFailedError("the Tools tab did not list every tool the install registers")
    for name in registry.names():
        one = listed[name]
        if one.capability != registry.get(name).capability.value:
            raise CheckFailedError("a tool was listed without the capability it requires")
        if not one.side_effect or not one.source:
            raise CheckFailedError("a tool was listed without its side effect and source")

    if await _called(h, registry, await h.reach(member)):
        raise CheckFailedError("a tool nobody switched off refused a call")
    async with traced(h, 1):
        await switch_tool(
            console.request("POST"),
            SWITCHED,
            ToolSwitchAsked(on=False),
            await asking_as(h, admin, strong=True),
        )
    after = await tools(console.request(), await asking_as(h, admin, strong=True))
    shown = next(one for one in after.tools if one.name == SWITCHED)
    if shown.off_for_install is None or shown.off_for_install.switched_off_by != admin:
        raise CheckFailedError("the Tools tab did not show the tool off for the install")
    if await _called(h, registry, await h.reach(member)) is None:
        raise CheckFailedError("a tool switched off from the console still answered a call")
    async with traced(h, 2):
        await switch_tool(
            console.request("POST"),
            SWITCHED,
            ToolSwitchAsked(on=True, reason=BACK_ON_BECAUSE),
            await asking_as(h, admin, strong=True),
        )
    if await _called(h, registry, await h.reach(member)):
        raise CheckFailedError("a tool switched back on from the console still refused a call")


# ------------------------------------------------- 4. a connected source's page (M27.15.39)
@dataclass
class Answering:
    """A source transport answering every address with one status and an empty list, counted."""

    status: int
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        body = b'{"Invoices": [], "Contacts": []}' if self.status == 200 else b"{}"
        return SourceAnswer(status=self.status, headers={}, body=body)


async def connected_here(h: Harness, admin: str) -> None:
    """Xero connected through the Connectors screen's store, as `admin`, with a made-up tenant."""
    from brain.connectors.manifest import manifest_digest
    from brain.ops.acceptance_checks_connectors import SOURCE, _nothing_kept, _settings
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live

    if (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckNotRunError(A_SOURCE_IS_CONNECTED_HERE_ALREADY)
    settings = _settings()
    await StoredConnections(h.sessions).connect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(manifest_for(SOURCE, settings)),
        keep_key=_nothing_kept,
        actor=admin,
        trace_id=h.trace_id,
        ent_hash="0" * 32,
    )


@check(
    leaves=("M27.15.39",),
    sentence=(
        "With a Xero tenant made up for the check connected, the Connectors routes list it as "
        "connected apart from the sources available to connect, its export carries the "
        "declaration and its history and says no key is exported, and its drift says nothing "
        "changed; a person without the screen is refused all three."
    ),
)
async def a_connected_source_is_kept_apart_and_exported_without_a_key(h: Harness) -> None:
    from brain.connector_routes import connector_sources, declaration_drift, export_connector
    from brain.console.connector_detail import SourceStatus
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_connectors import SOURCE
    from brain.ops.connector_admin import NO_KEY_IS_EXPORTED

    await h.found_departments()
    admin, reader, other = (h.principal(A, role) for role in ("connects", "reader", "other"))
    await h.person(admin, department=A, grants=((CONNECTS_SOURCES, Scope.unrestricted()),))
    await h.person(reader, department=A, grants=screen_grants("connectors"))
    await h.person(other, department=A)
    await connected_here(h, admin)
    console = console_for(h)
    stranger = await asking_as(h, other)
    if not await refused(connector_sources(console.request(), stranger, ListAsked())):
        raise CheckFailedError("a person who may not open Connectors was shown its sources")
    if not await refused(export_connector(console.request(), SOURCE, stranger)):
        raise CheckFailedError("a person who may not open Connectors was given an export")

    page = await connector_sources(
        console.request(), await asking_as(h, reader), ListAsked(limit=200)
    )
    rows = {one.name: one for one in page.items}
    if rows.get(SOURCE) is None or rows[SOURCE].status is SourceStatus.NOT_CONNECTED:
        raise CheckFailedError("a connected source was not listed as connected")
    if not any(one.status is SourceStatus.NOT_CONNECTED for one in rows.values()):
        raise CheckFailedError("no source available to connect was listed apart from it")

    exported = await export_connector(console.request(), SOURCE, await asking_as(h, reader))
    if exported.credential != NO_KEY_IS_EXPORTED or exported.connection is None:
        raise CheckFailedError("a connection's export did not say that no key is exported")
    if exported.declaration is None or not exported.declaration.version:
        raise CheckFailedError("a connection's export did not carry its declaration")
    if not exported.history or exported.history[0].connected_by != admin:
        raise CheckFailedError("a connection's export did not carry its history")
    if exported.connection.settings.keys() - {"tenant_id"}:
        raise CheckFailedError("a connection's export carried more than the source's settings")

    drift = await declaration_drift(console.request(), SOURCE, await asking_as(h, reader))
    if drift.changed or not drift.known:
        raise CheckFailedError("a source connected under this release's declaration drifted")


# ------------------------------------- 5. a test of a source, and its health (M27.15.8)
@check(
    leaves=("M27.15.8", "M27.12.2", "M27.2.4"),
    sentence=(
        "A Xero tenant made up for the check is read by the worker's scheduled read and shown "
        "read on Connectors; Test connection pressed there makes one call through the worker's "
        "probe pass to a transport answering from memory, recorded on the source's health with "
        "no business rows returned; a test the source refuses shows it failing; anybody else is "
        "refused."
    ),
)
async def a_source_test_is_one_call_whose_health_is_shown(h: Harness) -> None:
    from brain.connector_routes import ask_probe, connector_probe, connector_sources
    from brain.console.connector_detail import SourceStatus
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_connectors import (
        SOURCE,
        _clock,
        _Keys,
        _no_wait,
        _Resolver,
    )
    from brain.ops.connector_probe import PROBE_SPACING
    from brain.ops.connector_probe_run import probe_on
    from brain.ops.connector_sync import ProbeVerdict, plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import attempt_row
    from brain.ops.connector_sync_store import read_live as live_rows

    await h.found_departments()
    admin, other = h.principal(A, "connects"), h.principal(A, "other")
    grants = dict.fromkeys(((CONNECTS_SOURCES, Scope.unrestricted()), *screen_grants("connectors")))
    await h.person(admin, department=A, grants=tuple(grants))
    await h.person(other, department=A)
    await connected_here(h, admin)
    console = console_for(h)
    if not await refused(ask_probe(console.request("POST"), SOURCE, await asking_as(h, other))):
        raise CheckFailedError("a person without the authority asked for a source's test")

    # M27.12.2: the worker's scheduled read, due by the plan the schedule asks, records its
    # health, and Connectors shows the source read.
    async with h.sessions() as session, session.begin():
        found = [one for one in await live_rows(session) if one.connection.connector == SOURCE]
    plan = plan_for(found[0].connection, last=None, now=datetime.now(UTC))
    if len(found) != 1 or plan.refused or not plan.due:
        raise CheckFailedError("the worker's schedule would not read a connected source")
    reader = Answering(status=200)
    read = await attempt(
        found[0],
        plan,
        previous=None,
        sessions=h.sessions,
        keys=_Keys(),
        caller=reader,
        resolver=_Resolver(),
        clock=_clock,
        sleep=_no_wait,
    )
    await h.execute(attempt_row(found[0].id, read))
    listed = await connector_sources(console.request(), await asking_as(h, admin), ListAsked())
    row = next(one for one in listed.items if one.name == SOURCE)
    if not reader.asked or row.status is not SourceStatus.CONNECTED or not row.health:
        raise CheckFailedError("a scheduled read of a source was not recorded on its health")
    if row.last_read_at is None:
        raise CheckFailedError("Connectors did not show when the schedule last read the source")

    async def pressed_and_probed(status: int, later: timedelta) -> tuple[Any, Answering]:
        """Test connection pressed, then the worker's pass `later` than now, as its clock reads."""
        async with traced(h, status):
            await ask_probe(console.request("POST"), SOURCE, await asking_as(h, admin, strong=True))
        waiting = await connector_probe(console.request(), SOURCE, await asking_as(h, admin))
        if not waiting.pending:
            raise CheckFailedError("a test asked for from the console did not wait for the worker")
        caller = Answering(status=status)
        await probe_on(
            sessions=h.sessions,
            now=datetime.now(UTC) + later,
            keys=_Keys(),
            caller=caller,
            resolver=_Resolver(),
            clock=lambda: datetime.now(UTC) + later,
        )
        return await connector_probe(console.request(), SOURCE, await asking_as(h, admin)), caller

    tested, caller = await pressed_and_probed(200, timedelta())
    if len(caller.asked) != 1:
        raise CheckFailedError("a test of a source made other than one call")
    if tested.pending or tested.verdict is not ProbeVerdict.ANSWERED or not tested.health:
        raise CheckFailedError("a source's test was not recorded on its health")
    if set(tested.model_dump()) - {
        "connector",
        "requested_at",
        "pending",
        "verdict",
        "tested_at",
        "health",
        "said",
        "confirm",
    }:
        raise CheckFailedError("a source's test returned more than its finding")
    shown = await connector_sources(console.request(), await asking_as(h, admin), ListAsked())
    row = next(one for one in shown.items if one.name == SOURCE)
    if row.status is not SourceStatus.CONNECTED:
        raise CheckFailedError("Connectors did not show a source whose test answered as connected")

    # The next test is spaced as the worker spaces two tests of one connection.
    declined, _ = await pressed_and_probed(401, PROBE_SPACING * 2)
    if declined.verdict is not ProbeVerdict.FAILED:
        raise CheckFailedError("a test the source refused was not recorded as failed")
    shown = await connector_sources(console.request(), await asking_as(h, admin), ListAsked())
    row = next(one for one in shown.items if one.name == SOURCE)
    if row.status is not SourceStatus.FAILING or not row.health:
        raise CheckFailedError("Connectors did not show a source whose test failed as failing")
