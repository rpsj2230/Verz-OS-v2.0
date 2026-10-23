"""Install checks for how long the install keeps what it holds, and for taking your own words out.

Four leaf groups of M25 were built and wired on main and no check on an install named them: the
retention policy per class of data (its ledger, its backups and the limit it states about them),
the daily sweep's report reaching every store, the first run being a dry run that a person
releases, and a person exporting their own conversation. Each check is the route the console page
calls, asked as the reader the leaf names, over the install's own database in the check's
rolled-back transaction.

**The policy is read from the route a person reads it from, and compared with things outside
itself.** The ledger's window is asserted to be longer than every other bounded window and not
less than three years, and a class is asserted present for every member of `DataClass`: a check
that read `HORIZONS` and compared it with `HORIZONS` would pass whatever the policy said. See
`A_POLICY_CHECK_THAT_READS_ITS_OWN_ANSWER_PROVES_NOTHING`.

**The report is the install's own, and a dry run is made by the real sweep.** The check reads the
newest report the worker wrote and says NOT RUN when none has been written, because an install
that has not yet had its first daily run has nothing to show and the check must not write one for
it. The dry-run check runs `retention.sweep` with `report_only=True` over the install's stores
through the same PostgreSQL executor the worker uses, on a connection of its own that can read
and, in this mode, removes nothing; it records that report in the check's transaction, releases
the sweep through the route, and reads the ledger entry the database's trigger wrote. See
`A_DRY_RUN_IS_MADE_BY_THE_REAL_SWEEP_IN_REPORT_ONLY_MODE`.

**An install that has already released its sweep is not shown the state it is past.** A release
may be live on a real install, and the route refuses a second one. The check says NOT RUN with the
sentence to act on rather than failing, or withdrawing the owner's release to make room.

Task ids: M25.1.1, M25.1.2, M25.1.5, M25.2.3, M25.3.1, M25.4.1
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2100

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a policy check does not compare the policy with itself.
A_POLICY_CHECK_THAT_READS_ITS_OWN_ANSWER_PROVES_NOTHING: Final = (
    "The ledger's window is held against every other bounded window and against a floor of "
    "three years, and the classes against the enum of every class, so a policy that lost a class "
    "or shortened the ledger fails here, which a comparison with the policy's own table would not."
)

#: Why the dry run is the real sweep in its report-only mode.
A_DRY_RUN_IS_MADE_BY_THE_REAL_SWEEP_IN_REPORT_ONLY_MODE: Final = (
    "The report released after is made by `retention.sweep` over the install's own tables with "
    "`report_only` set, which counts and removes nothing, so a release is shown after a report "
    "that is what a worker's first run writes and not after one the check composed."
)

#: Why the dry run's connection is the owner's and read-only.
THE_SWEEP_IS_COUNTED_AS_THE_WORKER_COUNTS_IT: Final = (
    "The worker counts the stores as the database owner (`Settings.owner_database_url`), because "
    "the application's login is not granted the catalogue and every store, so a check that "
    "counted as the application could only say it could not count. The check opens the same login "
    "and sets the session read-only before the sweep is handed it, so a report-only run that "
    "tried to remove or record anything would be refused by the database rather than trusted."
)

# ------------------------------------------------------------------------ the figures
#: What the Retention screen asks of a reader who may release the sweep. Restated rather than
#: imported, so a change to a route's authority fails its check instead of moving with it.
RELEASES_THE_SWEEP: Final = "admin:retention"

#: The least the metadata ledger is kept, in days. Three years: a financial year still open and
#: the two before it, which is what a dispute about what the system did is about.
LEDGER_FLOOR_DAYS: Final = 3 * 365

#: What the Retention screen says about a backup, as the sentence a person is told: the words it
#: must hold.
BACKUP_LIMIT_WORDS: Final = ("backup", "rotates out")

# ----------------------------------------------------------------------- the sentences
NO_REPORT_YET: Final = (
    "the worker has not written a retention report on this install yet, which its daily run does "
    "once it has run; this check reads that report and never writes one for it"
)
THE_SWEEP_IS_RELEASED_HERE: Final = (
    "the retention sweep is already released on this install, so a release cannot be shown from "
    "the report-only state; withdraw it from the Retention screen and the check runs"
)
THE_SWEEP_CANNOT_COUNT_HERE: Final = (
    "the retention sweep could not count this install's stores from the process running the "
    "check, so a report-only run could not be made here"
)


# ------------------------------------------------------------------------- 1. the policy
@check(
    leaves=("M25.1.1", "M25.1.2", "M25.2.3"),
    sentence=(
        "The Retention screen's controls name a window or a lifetime and a reason for every class "
        "of data the install holds, keep the metadata ledger longer than any other bounded class "
        "and for at least three years, give the backups a window of their own, and say in words "
        "that a backup taken before an erasure holds the data until it rotates out; a person "
        "without the screen is refused."
    ),
)
async def retention_is_declared_per_class_and_a_backup_states_its_limit(h: Harness) -> None:
    from brain.erasure_routes import retention_controls
    from brain.ops.retention import DataClass, Lifetime

    await h.found_departments()
    reader, nobody = h.principal(A, "retention"), h.principal(A, "nobody")
    await h.person(reader, department=A, grants=screen_grants("retention"))
    await h.person(nobody, department=A)
    if not await refused(retention_controls(await asking_as(h, nobody))):
        raise CheckFailedError("a person without the Retention screen was shown the policy")

    controls = await retention_controls(await asking_as(h, reader))
    kept = {one.data_class: one for one in controls.kept}
    if set(kept) != {one.value for one in DataClass}:
        raise CheckFailedError("the Retention screen did not state a policy for every class")
    if any(not one.because.strip() for one in controls.kept):
        raise CheckFailedError("a class of data was kept for no stated reason")
    windows = {
        name: one.days for name, one in kept.items() if one.lifetime == Lifetime.FIXED_WINDOW.value
    }
    if any(days is None or days < 1 for days in windows.values()):
        raise CheckFailedError("a class kept for a fixed window did not say how long")

    ledger = windows.get(DataClass.METADATA_LEDGER.value)
    others = [days for name, days in windows.items() if name != DataClass.METADATA_LEDGER.value]
    if (
        ledger is None
        or ledger < LEDGER_FLOOR_DAYS
        or any(days >= ledger for days in others if days)
    ):
        raise CheckFailedError("the metadata ledger was not kept longer than every other window")
    if DataClass.BACKUP.value not in windows:
        raise CheckFailedError("backups were given no window of their own")
    lowered = controls.erasing.lower()
    if not all(words in lowered for words in BACKUP_LIMIT_WORDS):
        raise CheckFailedError("the erasure screen did not state that a backup keeps the data")


# ------------------------------------------------------------- 2. the report reaches every store
@check(
    leaves=("M25.1.5",),
    sentence=(
        "The newest retention report the worker wrote is shown to the Retention screen's reader "
        "with a line for every store the install holds, each store it did not reach saying why, "
        "and nothing a report line names is a person; a reader of one department is shown no "
        "report."
    ),
)
async def the_retention_report_reaches_every_store_and_says_why_it_did_not(h: Harness) -> None:
    from brain.ops.retention import Store
    from brain.retention_routes import retention_report

    await h.found_departments()
    admin, narrow = h.principal(A, "retention"), h.principal(A, "narrow")
    await h.person(admin, department=A, grants=screen_grants("retention"))
    await h.person(narrow, department=A, grants=screen_grants("retention", Scope.department(A)))
    console = console_for(h)

    shown = await retention_report(console.request(), await asking_as(h, admin))
    if shown.report is None:
        raise CheckNotRunError(NO_REPORT_YET)
    held_back = await retention_report(console.request(), await asking_as(h, narrow))
    if held_back.report is not None:
        raise CheckFailedError("a reader of one department was shown the estate's report")

    lines = {one.store for one in shown.report.stores}
    if lines != {one.value for one in Store}:
        raise CheckFailedError("the retention report did not name every store")
    for line in shown.report.stores:
        if not line.reached and not line.unreached_because.strip():
            raise CheckFailedError("a store the sweep did not reach did not say why")
        if line.reached and line.unreached_because:
            raise CheckFailedError("a store the sweep reached carried a reason it was not")
    if shown.report.complete == any(not one.reached for one in shown.report.stores):
        raise CheckFailedError("the report said it was complete beside a store it did not reach")


# ------------------------------------------------------------------ 3. a dry run then a release
@check(
    leaves=("M25.4.1",),
    sentence=(
        "A retention sweep run in report-only mode over the install's stores removes nothing and "
        "says so, the sweep is released by the administrator who read that report and a ledger "
        "entry records the release, a second release and a release by a reader without the "
        "authority are refused, and withdrawing it puts the sweep back to reporting."
    ),
)
async def a_dry_run_removes_nothing_until_a_person_releases_the_sweep(h: Harness) -> None:
    from brain.ops.retention import RetentionReport, sweep
    from brain.ops.retention_store import (
        PostgresSweeper,
        released_controls,
        report_document,
    )
    from brain.retention_routes import ReleaseBody, release, retention_report, withdraw
    from brain.tables.retention import RetentionReportRow

    await h.found_departments()
    admin, reader = h.principal(A, "retention_admin"), h.principal(A, "retention_reader")
    await h.person(
        admin,
        department=A,
        grants=((RELEASES_THE_SWEEP, Scope.unrestricted()), *screen_grants("retention")),
    )
    await h.person(reader, department=A, grants=screen_grants("retention"))
    async with h.sessions() as session:
        already = bool(await released_controls(session, now=datetime.now(UTC)))
    if already:
        raise CheckNotRunError(THE_SWEEP_IS_RELEASED_HERE)

    made = await _dry_run(h, PostgresSweeper, sweep)
    if not isinstance(made, RetentionReport) or not made.report_only:
        raise CheckFailedError("the sweep run in report-only mode did not say it was one")
    if made.removed != 0:
        raise CheckFailedError("a report-only sweep removed something")
    document = report_document(made)
    async with h.sessions() as session:
        report_id = (
            await session.execute(
                insert(RetentionReportRow)
                .values(
                    at=made.at,
                    report_only=True,
                    complete=made.complete,
                    stores=document["stores"],
                    holds=document["holds"],
                    findings=document["findings"],
                )
                .returning(RetentionReportRow.id)
            )
        ).scalar_one()
        await session.commit()

    console = console_for(h)
    read = await retention_report(console.request(), await asking_as(h, admin, strong=True))
    if read.report is None or read.report.report_id != report_id or read.report.released:
        raise CheckFailedError("the report read before releasing was not the one to be released")
    if read.report.removed != 0:
        raise CheckFailedError("the report read before releasing showed something removed")

    body = ReleaseBody(after_report=report_id)
    if not await refused(
        release(console.request("POST"), body, await asking_as(h, reader, strong=True))
    ):
        raise CheckFailedError("a reader without the authority released the sweep")
    async with traced(h, 1):
        done = await release(console.request("POST"), body, await asking_as(h, admin, strong=True))
    if done.after_report != report_id:
        raise CheckFailedError("the release did not name the report it came after")
    async with h.sessions() as session:
        if not await released_controls(session, now=datetime.now(UTC)):
            raise CheckFailedError("a release was recorded and the sweep was still not released")
    entries = (
        await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry"
                " WHERE subject = :subject ORDER BY seq"
            ).bindparams(subject=f"retention:{done.release_id}")
        )
    ).all()
    if len(entries) != 1 or entries[0][0] != admin or _change(entries[0][1]) != "released":
        raise CheckFailedError("a release of the sweep left no ledger entry in its releaser's name")
    if not await refused_in_words(
        release(console.request("POST"), body, await asking_as(h, admin, strong=True))
    ):
        raise CheckFailedError("a second release was accepted beside a live one")
    async with traced(h, 2):
        await withdraw(console.request("POST"), await asking_as(h, admin, strong=True))
    async with h.sessions() as session:
        if await released_controls(session, now=datetime.now(UTC)):
            raise CheckFailedError("withdrawing the release left the sweep released")


def _change(details: Any) -> str:
    found = details if isinstance(details, dict) else json.loads(details)
    return str(found.get("change", ""))


async def refused_in_words(call: Any) -> bool:
    """Whether a route call was refused with a sentence saying what to fix, as a release is."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent as why:
        return bool(getattr(why, "public_message", None))
    return False


async def _dry_run(h: Harness, executor: Any, sweep: Any) -> Any:
    """The real sweep over this install's tables, report-only, on a connection of its own."""
    import psycopg

    from brain.db import libpq_conninfo

    # The owner's login, as the worker reads it (`Settings.owner_database_url`): counting a store
    # needs the catalogue and every store's table, which the application's login is not granted
    # on an install that names it in `database_url`. Held read-only, so a sweep that is asked to
    # count cannot remove or write whatever it is handed.
    # See `THE_SWEEP_IS_COUNTED_AS_THE_WORKER_COUNTS_IT`.
    url = h.settings.owner_database_url()

    def run() -> Any:
        with psycopg.connect(libpq_conninfo(url), prepare_threshold=None) as conn:
            conn.read_only = True
            return sweep(executor(conn, holds=()), now=datetime.now(UTC), report_only=True)

    try:
        return await asyncio.to_thread(run)
    except (psycopg.Error, OSError) as exc:
        raise CheckNotRunError(THE_SWEEP_CANNOT_COUNT_HERE) from exc


# ------------------------------------------------------------------------ 4. your own words out
@check(
    leaves=("M25.3.1",),
    sentence=(
        "A member of acceptance_a asks a question, exports that conversation from the Ask page's "
        "route and is handed their own turns in order, a record of the export is kept in their "
        "name before it is handed over, and a member of acceptance_b naming the same conversation "
        "is refused."
    ),
)
async def a_person_exports_their_own_conversation_and_it_is_recorded(h: Harness) -> None:
    import structlog

    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_checks_chat import uploaded
    from brain.ops.acceptance_threads import _asking, _web, asked_on_the_web
    from brain.ops.data_export_store import StoredExports
    from brain.thread_routes import export_my_thread

    await h.found_departments()
    table = await uploaded(h)
    member, other = h.principal(A, "member"), h.principal(B, "member")
    await h.person(member, department=A, grants=table.reads(A, held=False))
    await h.person(other, department=B, grants=_in(B, "read:knowledge"))
    app = await _web(h)
    question = table.asking(table.open_column)
    _, thread = await asked_on_the_web(h, app, member, question, None, 1)
    if thread is None:
        raise CheckFailedError("an answered question was kept in no thread")

    from brain.ops.acceptance_threads import _request

    structlog.contextvars.bind_contextvars(trace_id=h.trace_id)
    h.removes(lambda: structlog.contextvars.unbind_contextvars("trace_id"))
    before = await StoredExports(h.sessions).taken_by(member, limit=50)
    if not await refused(export_my_thread(_request(app), await _asking(h, other), thread)):
        raise CheckFailedError("a person exported a conversation that is somebody else's")
    if await StoredExports(h.sessions).taken_by(other, limit=50):
        raise CheckFailedError("a refused export was recorded as taken")

    taken = await export_my_thread(_request(app), await _asking(h, member), thread)
    document = json.loads(bytes(taken.body).decode())
    exported = json.loads(document["document"])
    turns = [one["text"] for one in exported["turns"]]
    if len(turns) != 2 or turns[0] != question or table.seen not in turns[1]:
        raise CheckFailedError("an export did not hold the person's own turns in order")
    after = await StoredExports(h.sessions).taken_by(member, limit=50)
    digest = hashlib.sha256(document["document"].encode("utf-8")).hexdigest()
    if len(after) != len(before) + 1 or after[0].document_digest != digest:
        raise CheckFailedError("an export was handed over with no record of it")
    if after[0].requested_by != member or after[0].reason_reference != f"thread/{thread}":
        raise CheckFailedError("an export's record did not name who took it and of what")
