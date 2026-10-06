"""Install acceptance checks for the operations screens that keep the install's own things: the
object store, moving data out, the application log, who is told what, and the backups.

Every check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`), and
every one of them asks the refusal beside the answer: a guard proved only by what it shows is
satisfied by a screen that shows everybody everything.

**The object store is connected exactly as the application connects it.** Storage and Backup and
recovery read the store the lifespan attached, and the check's application has no lifespan, so
the check calls `brain.ops.object_store.object_store_at_start` with the run's settings and
attaches what it returns the way `brain.app` does. Nothing is written to the store and no object
is fetched beyond the backup records the Recovery route itself reads. An install whose process
builds no store is a Storage screen that says so per bucket, which the check accepts, and a
Recovery screen with nothing to show, which is a check that cannot run here rather than a pass.
See `THE_STORE_IS_CONNECTED_AS_THE_APPLICATION_CONNECTS_IT`.

**A webhook's signing secret is kept by a stand-in, and nothing reaches the vault.** Registering a
subscriber writes its secret to the vault, which a rolled-back transaction does not undo. The
Subscribers check is about who is told what and how that stops, so the registration goes through
the Webhooks route with a keeper that records the id and keeps nothing; the vault write is
`brain.ops.webhook_admin.SigningSecrets`' own, proved where it is. See
`THE_VAULT_IS_LEFT_AS_THE_CHECK_FOUND_IT`.

**What a report page exports is not here.** A report page builds its export in the browser from
what it shows (`console/src/pages/reports/reportParts.tsx`), so its half of M27.15.48 is proved by
the browser harness and this module proves the log's, which the server writes.

Task ids: M27.8.15, M27.8.16, M27.15.48, M27.8.11, M27.7.12, M27.7.26
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_operations_console import (
    Console,
    asking_as,
    console_for,
    refused,
    screen_grants,
    setting_entries,
    traced,
)
from brain.ops.acceptance_run import Harness
from brain.ops.webhook_admin import SigningSecrets

if TYPE_CHECKING:
    from brain.ops.object_store import ObjectStore

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 323

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the check builds the object store itself.
THE_STORE_IS_CONNECTED_AS_THE_APPLICATION_CONNECTS_IT: Final = (
    "Storage and Backup and recovery read the object store the application attached when it "
    "started. The check's application has no start, so it connects with the run's settings "
    "through the function the application calls and attaches the result the same way, and the "
    "screens are read over the store this install actually has."
)

#: Why the subscriber's signing secret is kept by a stand-in.
THE_VAULT_IS_LEFT_AS_THE_CHECK_FOUND_IT: Final = (
    "Registering a subscriber keeps its signing secret in the vault, which the check's rolled-back "
    "transaction cannot undo. The registration goes through the Webhooks route with a keeper that "
    "records the id and keeps nothing, so the check proves who is told what and how it stops, and "
    "leaves the vault as it found it."
)

#: Said when the process running the check reads no backup bucket.
NO_BACKUP_BUCKET_IS_READ_HERE: Final = (
    "the process running this check builds no connection to the object store, so the Recovery "
    "screen has nothing to read the backups from; the run inside the application's container, "
    "which connects to the store, can"
)

# ------------------------------------------------------------------------ the figures
#: The authorities the checks' people hold. Restated rather than imported, so a change to a
#: route's authority fails its check instead of moving with it.
MANAGES_STORAGE: Final = "admin:storage"
TAKES_EXPORTS: Final = "admin:export"
READS_THE_LOG: Final = "admin:application_log"
MANAGES_NOTIFICATIONS: Final = "admin:notification"
MANAGES_SUBSCRIBERS: Final = "admin:webhook_subscriber"

#: The audit kinds the exporter may read: the two the check's own people and grants are written
#: under, so the export's window holds entries the exporter may read whatever else the install did.
EXPORTED_KINDS: Final = ("principal", "grant")

#: The reference an export is taken under. A ticket's shape, as the form asks.
MATTER: Final = "ACCEPTANCE-1"

#: The event the log check's row is kept under: a name no module emits, so a search finds it alone.
LOG_EVENT: Final = "acceptance.log_export_check"

#: The relay the notifications check saves. Reserved names, so nothing is ever sent anywhere.
RELAY_HOST: Final = "smtp.example.com"
RELAY_SENDER: Final = "acceptance@example.com"

#: The webhook the subscribers check registers. A reserved name, and nothing is delivered to it.
WEBHOOK_ENDPOINT: Final = "https://hooks.example.com/acceptance"


# ------------------------------------------------------------------------ the helpers
async def store_as_the_application_builds_it(h: Harness) -> ObjectStore:
    """The object store `brain.app`'s lifespan would attach, built in a thread as it builds it."""
    from brain.ops.object_store import object_store_at_start

    return await asyncio.to_thread(
        object_store_at_start, h.settings.vault_address, h.settings.vault_token
    )


def with_store(console: Console, store: ObjectStore) -> Console:
    """The console application with the store and the backup reader attached as `brain.app` does."""
    from brain.ops.object_store import backup_objects

    console.app.state.object_store = store
    connected = store.backend
    console.app.state.backup_objects = None if connected is None else backup_objects(connected)
    return console


def log_grants(scope: Scope) -> tuple[tuple[str, Scope], ...]:
    """What a reader of the Logs screen holds over `scope`: the log's authority and the plane its
    read asks, which `brain.log_routes.may_read_application_log` asks of both.

    Built from `brain.log_routes.LOG_READ` rather than through `screen_grants`, because the log's
    read is declared in its route module and not among the console's registered screens.
    """
    from brain.console.reads import Plane, admits, plane_capability_for
    from brain.log_routes import LOG_READ

    planes = [
        plane_capability_for(LOG_READ, one).value for one in Plane if admits(one, LOG_READ.plane)
    ]
    return ((READS_THE_LOG, scope), (planes[0], scope))


class KeptNowhere(SigningSecrets):
    """A signing-secret keeper that records whose secret it was handed and keeps none.

    See `THE_VAULT_IS_LEFT_AS_THE_CHECK_FOUND_IT`.
    """

    def __init__(self) -> None:
        super().__init__(None)
        self.handed: list[str] = []

    @property
    def configured(self) -> bool:
        return True

    def keep(self, subscriber_id: str, secret: str, *, actor: str) -> datetime | None:
        del secret, actor
        self.handed.append(subscriber_id)
        return datetime.now(UTC)


def subscriber_id_for(h: Harness) -> str:
    """A subscriber id belonging to this run, in the shape the Webhooks route accepts."""
    return "acceptance_" + hashlib.sha256(h.trace_id.encode()).hexdigest()[:16]


# ------------------------------------------------------------- 1. storage (M27.8.15)
@check(
    leaves=("M27.8.15",),
    sentence=(
        "An administrator holding the storage authority over everything is shown, by the Storage "
        "route, every bucket this product keeps with how long it keeps what and why, none of them "
        "readable by the public, and each either counted or saying why it was not; a holder of the "
        "authority over one department and a person without it are refused."
    ),
)
async def the_storage_screen_shows_every_bucket_and_what_it_keeps(h: Harness) -> None:
    from brain.ops.storage import BUCKETS
    from brain.storage_routes import storage

    await h.found_departments()
    admin, narrow, other = (
        h.principal(A, "storage"),
        h.principal(A, "storage-a"),
        h.principal(A, "other"),
    )
    await h.person(admin, department=A, grants=((MANAGES_STORAGE, Scope.unrestricted()),))
    await h.person(narrow, department=A, grants=((MANAGES_STORAGE, Scope.department(A)),))
    await h.person(other, department=A)
    console = with_store(console_for(h), await store_as_the_application_builds_it(h))

    shown = await storage(console.request(), await asking_as(h, admin, strong=True))
    if [one.name for one in shown.buckets] != [one.name for one in BUCKETS]:
        raise CheckFailedError("Storage did not show every bucket this product keeps")
    if any(one.public_read for one in shown.buckets):
        raise CheckFailedError("Storage showed a bucket the public may read")
    if any(not one.retention_reason.strip() for one in shown.buckets):
        raise CheckFailedError("Storage showed a bucket without the reason for how long it keeps")
    for asker in (narrow, other):
        if not await refused(storage(console.request(), await asking_as(h, asker, strong=True))):
            raise CheckFailedError("Storage answered a person without the authority over all")


# ----------------------------------------------------- 2. import and export (M27.8.16)
@check(
    leaves=("M27.8.16",),
    sentence=(
        "An administrator who may take exports and read the audit trail takes an export of the "
        "audit trail through the Import and export screen's route, under a reason and a "
        "reference, and is handed the document once and then shown the export among their own; "
        "a reader of the audit trail without the export authority is shown what can move, may "
        "not take one and is shown no exports."
    ),
)
async def an_export_is_taken_from_the_console_and_listed_as_the_takers(h: Harness) -> None:
    from brain.audit.view import CAPABILITY_BY_KIND
    from brain.data_transfer_routes import ExportAsked, data_transfer, take_export
    from brain.ops.export import ExportReason

    await h.found_departments()
    exporter, reader = h.principal(A, "exporter"), h.principal(A, "auditor")
    kinds = tuple((CAPABILITY_BY_KIND[one].value, Scope.unrestricted()) for one in EXPORTED_KINDS)
    await h.person(
        exporter,
        department=A,
        grants=((TAKES_EXPORTS, Scope.unrestricted()), *screen_grants("audit"), *kinds),
    )
    await h.person(reader, department=A, grants=(*screen_grants("audit"), *kinds))
    console = console_for(h)
    body = ExportAsked(
        data_set="audit_trail",
        reason=ExportReason.INTERNAL_INVESTIGATION.value,
        reason_reference=MATTER,
        since=h.now - timedelta(minutes=5),
        until=datetime.now(UTC),
    )

    listed = await data_transfer(console.request(), await asking_as(h, reader, strong=True))
    if not listed.catalogue or listed.exportable or listed.exports:
        raise CheckFailedError(
            "Import and export offered an export to a reader who may not take one"
        )
    if not await refused(
        take_export(console.request("POST"), body, await asking_as(h, reader, strong=True))
    ):
        raise CheckFailedError("a reader without the export authority took an export")

    async with traced(h, 1):
        answer = await take_export(
            console.request("POST"), body, await asking_as(h, exporter, strong=True)
        )
    if answer.status_code != 200:
        raise CheckFailedError("an export taken from the console was not handed over")
    taken = json.loads(bytes(answer.body))
    if not taken["document"] or taken["export"]["entries"] < 1:
        raise CheckFailedError("an export from the console handed over no document")
    mine = await data_transfer(console.request(), await asking_as(h, exporter, strong=True))
    if not mine.exportable or [one.export_id for one in mine.exports][:1] != [
        taken["export"]["export_id"]
    ]:
        raise CheckFailedError("the export just taken was not listed among the taker's own")


# ----------------------------------------------------------- 3. the log's export (M27.15.48)
@check(
    leaves=("M27.15.48",),
    sentence=(
        "A row kept in the application log is in the export the Logs screen's route writes for "
        "an administrator holding the log under a second factor, searched by its event, with no "
        "count of anything; an administrator of one department and a person without the log are "
        "refused the export."
    ),
)
async def the_log_exports_what_its_reader_could_page_to(h: Harness) -> None:
    from brain.log_routes import LogExport, LogOrder, export_logs
    from brain.ops.log_capture import Captured, LogLevel
    from brain.ops.log_store import row_values
    from brain.tables.application_log import ApplicationLogRow

    await h.found_departments()
    admin, narrow, other = (
        h.principal(A, "log"),
        h.principal(A, "log-a"),
        h.principal(A, "other"),
    )
    await h.person(admin, department=A, grants=log_grants(Scope.unrestricted()))
    await h.person(
        narrow,
        department=A,
        grants=log_grants(Scope.department(A)),
    )
    await h.person(other, department=A)
    at = datetime.now(UTC) - timedelta(seconds=30)
    await h.execute(
        insert(ApplicationLogRow).values(
            **row_values(
                Captured(
                    level=LogLevel.WARNING,
                    event=LOG_EVENT,
                    origin="brain.ops.acceptance_operations_console_4:1",
                    at=at,
                    last_at=at,
                    repeats=1,
                    trace_id=None,
                    error_type=None,
                    fields={"check": "acceptance"},
                )
            )
        )
    )
    console = console_for(h)

    async def exported(principal_id: str) -> LogExport:
        return await export_logs(
            console.request(),
            await asking_as(h, principal_id, strong=True),
            level=None,
            event=LOG_EVENT,
            start=at - timedelta(minutes=1),
            end=datetime.now(UTC),
            order=LogOrder.NEWEST,
        )

    found = await exported(admin)
    lines = found.document.strip().splitlines()
    if len(lines) != 2 or LOG_EVENT not in lines[1]:
        raise CheckFailedError("the log's export did not hold the one row its search finds")
    if found.cut_off:
        raise CheckFailedError("the log's export said it was cut off over one row")
    for asker in (narrow, other):
        if not await refused(exported(asker)):
            raise CheckFailedError("the log was exported for a person without it over everything")


# ------------------------------------------------- 4. notifications and email (M27.8.11)
@check(
    leaves=("M27.8.11",),
    sentence=(
        "An administrator of notifications is shown every notice this product composes, switches "
        "one off from the Notifications route and is then shown it off and who switched it, "
        "recorded in the audit trail, and saves the mail relay and is shown it saved with no "
        "password on the page; a holder of the authority over one department and a person "
        "without it are refused."
    ),
)
async def a_notice_is_switched_off_and_the_relay_saved_from_the_console(h: Harness) -> None:
    from brain.notification_routes import (
        NoticeSwitchAsked,
        NoticeView,
        RelayAsked,
        notifications,
        save_email,
        switch_notice,
    )
    from brain.ops.mail import Security
    from brain.ops.notices import NOTICE_NAMESPACE, NOTICES

    await h.found_departments()
    admin, narrow, other = (
        h.principal(A, "notices"),
        h.principal(A, "notices-a"),
        h.principal(A, "other"),
    )
    await h.person(admin, department=A, grants=((MANAGES_NOTIFICATIONS, Scope.unrestricted()),))
    await h.person(narrow, department=A, grants=((MANAGES_NOTIFICATIONS, Scope.department(A)),))
    await h.person(other, department=A)
    console = console_for(h)
    for asker in (narrow, other):
        if not await refused(
            notifications(console.request(), await asking_as(h, asker, strong=True))
        ):
            raise CheckFailedError("Notifications answered a person without the authority")

    page = await notifications(console.request(), await asking_as(h, admin, strong=True))
    if [one.kind for one in page.notices] != [one.kind.value for one in NOTICES]:
        raise CheckFailedError("Notifications did not show every notice this product composes")
    one = next(notice for notice in NOTICES if notice.switchable)
    async with traced(h, 1):
        switched = await switch_notice(
            console.request("POST"),
            one.kind.value,
            NoticeSwitchAsked(on=False),
            await asking_as(h, admin, strong=True),
        )
    if not isinstance(switched, NoticeView) or switched.on:
        raise CheckFailedError("a notice switched off from the console was not off")
    again = await notifications(console.request(), await asking_as(h, admin, strong=True))
    shown = next(notice for notice in again.notices if notice.kind == one.kind.value)
    if shown.on or shown.changed_by != admin:
        raise CheckFailedError("Notifications did not show the notice off and who switched it")
    recorded = await setting_entries(h, f"{NOTICE_NAMESPACE}.{one.kind.value}")
    if admin not in [actor for actor, _ in recorded]:
        raise CheckFailedError("switching a notice off was not recorded under who switched it")

    relay = RelayAsked(
        host=RELAY_HOST,
        port=587,
        security=Security.STARTTLS.value,
        sender=RELAY_SENDER,
        username="acceptance",
    )
    async with traced(h, 2):
        saved = await save_email(
            console.request("POST"), relay, await asking_as(h, admin, strong=True)
        )
    if saved.status_code != 200:
        raise CheckFailedError("the relay saved from the console was not saved")
    after = await notifications(console.request(), await asking_as(h, admin, strong=True))
    if not after.email.configured or after.email.host != RELAY_HOST:
        raise CheckFailedError("Notifications did not show the relay as saved")
    if after.email.changed_by != admin:
        raise CheckFailedError("Notifications did not show who saved the relay")


# ------------------------------------------------------------- 5. subscribers (M27.7.12)
@check(
    leaves=("M27.7.12",),
    sentence=(
        "A webhook subscriber registered through the Webhooks route is listed by the Subscribers "
        "route with what it is told about and who set it up, and after it is switched off it is "
        "listed as off; a person who may not manage subscribers is shown what an install with "
        "none is shown."
    ),
)
async def a_subscriber_is_told_what_it_asked_for_until_switched_off(
    h: Harness,
) -> None:
    from brain.govern_people_routes import subscribers_page
    from brain.ops.outbox import EventKind
    from brain.webhook_routes import RegistrationAsked, register, switch_off

    await h.found_departments()
    admin, other = h.principal(A, "webhooks"), h.principal(A, "other")
    await h.person(admin, department=A, grants=((MANAGES_SUBSCRIBERS, Scope.unrestricted()),))
    await h.person(other, department=A)
    console = console_for(h)
    keeper = KeptNowhere()
    console.app.state.signing_secrets = keeper
    subscriber = subscriber_id_for(h)
    kind = next(iter(EventKind)).value

    async with traced(h, 1):
        answer = await register(
            console.request("POST"),
            RegistrationAsked(
                subscriber_id=subscriber,
                endpoint=WEBHOOK_ENDPOINT,
                kinds=[kind],
                secret=secrets.token_urlsafe(32),
            ),
            await asking_as(h, admin, strong=True),
        )
    if answer.status_code != 200 or keeper.handed != [subscriber]:
        raise CheckFailedError("a subscriber registered from the console was not registered")
    listed = await subscribers_page(console.request(), await asking_as(h, admin, strong=True))
    mine = [one for one in listed.items if one.subscriber_id == subscriber]
    if len(mine) != 1 or mine[0].kinds != [kind] or mine[0].created_by != admin:
        raise CheckFailedError("Subscribers did not list a subscriber with what it is told")
    if not mine[0].active or not listed.stopping:
        raise CheckFailedError("Subscribers did not show the subscriber on and how to stop it")
    hidden = await subscribers_page(console.request(), await asking_as(h, other, strong=True))
    if hidden.items or hidden.findings:
        raise CheckFailedError("Subscribers listed subscribers to a person who may not manage them")

    async with traced(h, 2):
        await switch_off(
            console.request("POST"), subscriber, await asking_as(h, admin, strong=True)
        )
    after = await subscribers_page(console.request(), await asking_as(h, admin, strong=True))
    stopped = [one for one in after.items if one.subscriber_id == subscriber]
    if len(stopped) != 1 or stopped[0].active:
        raise CheckFailedError("a subscriber switched off was still listed as told")


# ---------------------------------------------------- 6. backup and recovery (M27.7.26)
@check(
    leaves=("M27.7.26",),
    sentence=(
        "A reader of Backup and recovery is shown, by the Recovery route over the backup bucket "
        "this install's process reads, the copies kept and the last verified restore with every "
        "backup record read, and how a rehearsal is done; a person without the screen is refused."
    ),
)
async def the_recovery_screen_reads_this_installs_backups(h: Harness) -> None:
    from brain.install_routes import recovery

    await h.found_departments()
    reader, other = h.principal(A, "recovery"), h.principal(A, "other")
    await h.person(reader, department=A, grants=screen_grants("recovery"))
    await h.person(other, department=A)
    console = with_store(console_for(h), await store_as_the_application_builds_it(h))
    if not await refused(recovery(console.request(), await asking_as(h, other, strong=True))):
        raise CheckFailedError("Backup and recovery answered a person without the screen")
    if console.app.state.backup_objects is None:
        raise CheckNotRunError(NO_BACKUP_BUCKET_IS_READ_HERE)

    shown = await recovery(console.request(), await asking_as(h, reader, strong=True))
    if shown.rehearsal is None:
        raise CheckFailedError("Backup and recovery did not say how a rehearsal is done")
    if shown.panel is None:
        raise CheckFailedError(
            "Backup and recovery read nothing from the bucket this process reads"
        )
    if not shown.panel.copies:
        raise CheckFailedError("Backup and recovery showed no copies")
    if shown.panel.unreadable:
        raise CheckFailedError("Backup and recovery found backup records it could not read")
