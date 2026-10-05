"""Install acceptance checks for the install's own screens: what is running, the switches and
settings an administrator changes, the limits and capacity screens, the request's traffic class
and the furnishing every install receives once.

Each check calls the route the console page calls, as the reader that page serves, and over the
check's transaction: a FastAPI application holding the install's settings and the check's session
factory, a request over it, and an `Asking` made of a reserved person and the reach the gate
would admit for them on the console. Nothing is mounted and no token is minted, because what is
proved is what the route answers a reader with a given reach, which is the half of the request
the page depends on; the gate's own refusal of a token is proved by
`brain.ops.acceptance_checks_automation`. See `A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`.

**Nothing a route holds for the process outlives the check.** Saving a setting holds the saved
values in the process that served the save, which is right for a person and wrong for a check
whose rows are rolled back. The settings check therefore puts back what the process held as soon
as the route returns, and registers the same undoing with `Harness.removes` in case it never
returns. See `A_SETTING_THE_CHECK_SAVED_IS_NOT_HELD_AFTER_IT`.

**The release check never leaves the process.** The Version and updates route asks the release
list through the watch the application attached; the check attaches one whose transport is a
stand-in that records the address it was asked and answers a list naming one release, so the
switch is proved to reach the look without this install asking anything outside its network. See
`THE_RELEASE_LIST_IS_A_STAND_IN`.

Task ids: M27.1.6, M27.6.1, M27.15.51, M27.12.7, M27.7.27, M27.9.5
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import MISSING, dataclass, fields
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError

from brain.core.scope import Scope
from brain.deployment.release import APPLIED_REVISION_QUERY
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

    from brain.api_routes import Asking
    from brain.deployment.release_feed import ReleaseWatch
    from brain.settings import Settings

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 320

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a route is called as a function rather than through a mounted application.
A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT: Final = (
    "A console page is proved by the route it calls answering the reader it serves. The check "
    "calls that route function with the request and the asking the gate would hand it, the "
    "reach being the reserved person's grants admitted on the console channel, so what is "
    "decided is exactly what the route decides and nothing a token adds or removes."
)

#: Why the settings check puts back what the process holds.
A_SETTING_THE_CHECK_SAVED_IS_NOT_HELD_AFTER_IT: Final = (
    "Saving a setting holds the saved values in the process that served the save. The check's "
    "rows are rolled back, so the process running it puts back what it held as soon as the "
    "route answers, and again when the check ends whatever happened."
)

#: Why the release list the check's watch asks is a stand-in.
THE_RELEASE_LIST_IS_A_STAND_IN: Final = (
    "The Version and updates route asks the release list through the watch the application "
    "attached. The check attaches one whose transport records the address and answers a list "
    "naming one release, so the switch is shown reaching the look and nothing is asked outside "
    "the install's network."
)

#: Said when an install holds no signed built-in template, which needs its own signing key.
NO_TEMPLATE_IS_ON_FILE: Final = (
    "no built-in template is on file, which an install whose template signing key has not been "
    "kept in its vault yet does not sign; the application signs them on its next start after it"
)

#: Said when the process running the check has no cache to read the live windows from.
NO_CACHE_TO_ASK: Final = (
    "the process running this check was not given the cache address the application uses, so "
    "there are no live windows to read; the run inside the application's container can"
)

#: Said when nothing has furnished the database, which the application does on every start.
NOTHING_HAS_FURNISHED_THIS_DATABASE: Final = (
    "this database has no record of being furnished, which the application writes the first "
    "time it starts against it, so it has not been started by the application yet"
)

#: Said when the login the run connected as cannot read which revision the database is at.
THE_MIGRATION_LEVEL_IS_NOT_READABLE_HERE: Final = (
    "the login this check runs as cannot read which revision the database is at, so the level "
    "This install shows cannot be held against it here"
)

# ------------------------------------------------------------------------ the figures
#: The release the stand-in list names. Higher than any release the product will publish.
STAND_IN_RELEASE: Final = "v9999.0.0"

#: The setting the settings check saves: branding, which nothing outside a page reads.
SAVED_SETTING: Final = "INSTALL_ACCENT_COLOUR"

#: The two values the check saves in turn, so one of them differs from what is in force.
ACCENTS: Final = ("#2457a6", "#a62457")

#: The kinds of ledger subject a furnishing may write: the setting recording it, the company-wide
#: scope and the starter pack. A person, a grant, a department or anything else would be a row
#: one company's data could live in, which `brain.ops.starter_store` says it never writes.
FURNISHING_WRITES_ONLY: Final = frozenset({"setting", "scope", "pack"})

#: The authority a Features screen reader holds. Restated rather than imported, so a change to
#: the route's authority fails this check instead of moving with it.
SWITCHES_FEATURES: Final = "admin:feature"

#: The authority a Settings screen reader holds. Restated for the same reason.
CHANGES_SETTINGS: Final = "admin:install_setting"


# ------------------------------------------------------------------------ the helpers
@dataclass(frozen=True)
class Console:
    """An application holding what `brain.app.create_app` attaches that these routes read."""

    app: FastAPI

    def request(self, method: str = "GET") -> Request:
        from starlette.requests import Request

        return Request({"type": "http", "app": self.app, "headers": [], "method": method})


def console_for(h: Harness, settings: Settings | None = None) -> Console:
    """The application a console route reads its state from: settings and the check's sessions."""
    from fastapi import FastAPI

    app = FastAPI()
    app.state.settings = h.settings if settings is None else settings
    app.state.db_sessions = h.sessions
    return Console(app=app)


def screen_grants(key: str, scope: Scope | None = None) -> tuple[tuple[str, Scope], ...]:
    """What a reader of one console screen holds: its read capability and the configuration
    plane over the same scope, which is what `brain.console.reads.permitted` asks."""
    from brain.console.reads import Plane, admits, plane_capability_for
    from brain.console.screens import screen

    where = Scope.unrestricted() if scope is None else scope
    read = screen(key).read
    planes = [plane_capability_for(read, one).value for one in Plane if admits(one, read.plane)]
    return ((read.requires.value, where), (planes[0], where))


async def asking_as(h: Harness, principal_id: str, *, strong: bool = False) -> Asking:
    """What the gate hands a route for this reserved person signed in on the console.

    `strong` is a sign-in with a second factor, which is what an administrator's console session
    is: the gate withholds the admin and approve verbs from any weaker one
    (`brain.gate.admission.verbs_withheld`), so an administrator asked without it is refused.
    """
    from types import MappingProxyType

    from brain.api_routes import Asking
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.bearer import Caller
    from brain.identity.oidc import VerifiedClaims
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    now = datetime.now(UTC)
    claims = VerifiedClaims(
        issuer="acceptance",
        subject=principal_id,
        audience=(),
        issued_at=now,
        expires_at=now,
        session_id="acceptance",
        key_id="acceptance",
        algorithm="RS256",
        verified_at=now,
        claims=MappingProxyType({}),
    )
    assurance = Assurance.STRONG if strong else Assurance.AUTHENTICATED
    return Asking(
        caller=Caller(principal=person, claims=claims, assurance=assurance),
        reach=admit(await h.reach(principal_id), Channel.CONSOLE, assurance),
        channel=Channel.CONSOLE,
        now=now,
    )


@asynccontextmanager
async def traced(h: Harness, n: int) -> AsyncIterator[None]:
    """The trace id the application's middleware would bind for one write, under this run's."""
    import structlog

    with structlog.contextvars.bound_contextvars(trace_id=f"{h.trace_id}-c{n}"):
        yield


async def refused(call: Any) -> bool:
    """Whether a route call was refused as something this reader may not be told about."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


async def applied_revisions(h: Harness) -> list[str]:
    """The revision the install's database is at, read as the login the run connected as.

    The application role is not granted `alembic_version`, and every application session sets
    that role again when it begins, so the read steps back to the login inside a savepoint of the
    check's transaction and sets the application role again before it ends. A login that may not
    read the table either is `THE_MIGRATION_LEVEL_IS_NOT_READABLE_HERE`.
    """
    from sqlalchemy.exc import DBAPIError

    from brain.session import SET_APPLICATION_ROLE

    try:
        async with h.connection.begin_nested():
            await h.connection.execute(text("RESET ROLE"))
            found = await h.connection.execute(text(APPLIED_REVISION_QUERY))
            applied = [str(one) for one in found.scalars().all()]
            await h.connection.exec_driver_sql(SET_APPLICATION_ROLE)
            return applied
    except DBAPIError as exc:
        raise CheckNotRunError(THE_MIGRATION_LEVEL_IS_NOT_READABLE_HERE) from exc


async def settled(watch: ReleaseWatch) -> None:
    """Wait, a few seconds at most, for the look a page load started to finish."""
    for _ in range(500):
        if not watch.looking:
            return
        await asyncio.sleep(0.01)


async def setting_entries(h: Harness, key: str) -> list[tuple[str, dict[str, Any]]]:
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


# ------------------------------------------------------------ 1. traffic class (M27.1.6)
@check(
    leaves=("M27.1.6",),
    sentence=(
        "Every channel declares its traffic class, a request is opened at ingress only by naming "
        "one, and the install's request ledger refuses a row that names none: the column has no "
        "default and a row written without it is refused by the database, while the same row "
        "naming its class is kept."
    ),
)
async def a_request_s_traffic_class_is_declared_at_ingress_with_no_default(h: Harness) -> None:
    from brain.core.lane import Lane
    from brain.gate.context import Channel, open_trace, traffic_class_for
    from brain.ops.telemetry import Ingress, RequestStatus, open_request
    from brain.tables.telemetry import RequestTelemetryRow

    for channel in Channel:
        declared = traffic_class_for(channel)
        if open_trace(f"{h.trace_id}-{channel.value}", h.now, channel).traffic_class != declared:
            raise CheckFailedError("a request opened at ingress did not carry its channel's class")
    asked = inspect.signature(open_request).parameters["traffic_class"]
    if asked.default is not inspect.Parameter.empty or asked.kind is not asked.KEYWORD_ONLY:
        raise CheckFailedError("a request can be opened at ingress without naming its class")
    held = next(one for one in fields(Ingress) if one.name == "traffic_class")
    if held.default is not MISSING or held.default_factory is not MISSING:
        raise CheckFailedError("a request can be opened at ingress without naming its class")

    column = (
        await h.execute(
            text(
                "SELECT column_default, is_nullable FROM information_schema.columns"
                " WHERE table_schema = 'obs' AND table_name = 'request_telemetry'"
                " AND column_name = 'traffic_class'"
            )
        )
    ).one_or_none()
    if column is None or column[0] is not None or column[1] != "NO":
        raise CheckFailedError("the install's request ledger gives a request a class by default")

    await h.found_departments()
    asker = h.principal(A, "asker")
    await h.person(asker, department=A)
    row: dict[str, Any] = {
        "received_at": h.now,
        "trace_id": f"{h.trace_id}-ingress",
        "principal": asker,
        "entitlement_hash": "0" * 32,
        "lane": Lane.ANSWER.value,
        "cache_hit": False,
        "status": RequestStatus.ANSWERED.value,
        "duration_ms": 1.0,
    }
    async with h.sessions() as session:
        try:
            await session.execute(insert(RequestTelemetryRow).values(**row))
        except IntegrityError:
            await session.rollback()
        else:
            raise CheckFailedError("the install's request ledger kept a row naming no class")
    named = traffic_class_for(Channel.CONSOLE).value
    kept = await h.execute(
        insert(RequestTelemetryRow)
        .values(**row, traffic_class=named)
        .returning(RequestTelemetryRow.traffic_class)
    )
    if kept.scalar_one() != named:
        raise CheckFailedError("a request naming its class was not kept with it")


# ------------------------------------------------------ 2. what is running (M27.6.1)
@check(
    leaves=("M27.6.1",),
    sentence=(
        "A reserved reader of This install is told, by the route the page calls, the install "
        "size it was deployed at, the release or why it cannot be named, the database version "
        "this release expects as the one the install's database is at, and the models, storage "
        "and connector settings it runs with; a person without the screen is refused."
    ),
)
async def this_install_says_what_is_running_and_at_what_level(h: Harness) -> None:
    from brain.console.installation import DATABASE_VERSION_FACT, INSTALL_SIZE_FACT
    from brain.install_routes import install

    await h.found_departments()
    reader, other = h.principal(A, "install"), h.principal(A, "other")
    await h.person(reader, department=A, grants=screen_grants("install"))
    await h.person(other, department=A)
    console = console_for(h)
    if not await refused(install(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person who may not open This install was told what it holds")
    view = await install(console.request(), await asking_as(h, reader))
    facts = {one.name: one for one in view.facts}
    size = facts.get(INSTALL_SIZE_FACT)
    if size is None or size.value != h.settings.profile:
        raise CheckFailedError("This install did not name the size the install was deployed at")
    release = facts.get("release")
    if release is None or not (release.value or release.because):
        raise CheckFailedError("This install neither named the release nor said why it could not")
    level = facts.get(DATABASE_VERSION_FACT)
    applied = await applied_revisions(h)
    if level is None or not level.value or level.value not in applied:
        raise CheckFailedError("This install's database version is not the one the database is at")
    if not any(one.setting for one in view.facts):
        raise CheckFailedError("This install named none of the settings the install runs with")


# ------------------------------------ 3. the release check switched from the console (M27.15.51)
@check(
    leaves=("M27.15.51",),
    sentence=(
        "An administrator switches the release check on from the Features screen's route with the "
        "environment's switch off: the switch is audited under their name, Version and updates "
        "then asks the release list and names its release, while switched off it asked nothing; "
        "a person without the authority is refused both screens."
    ),
)
async def a_feature_switched_on_from_the_console_reaches_what_reads_it(h: Harness) -> None:
    from brain.deployment.release_feed import ReleaseWatch
    from brain.feature_routes import SwitchAsked, features, switch_feature
    from brain.install_routes import updates
    from brain.ops.features import RELEASE_CHECK

    await h.found_departments()
    admin, other = h.principal(A, "features"), h.principal(A, "other")
    await h.person(
        admin,
        department=A,
        grants=(
            (SWITCHES_FEATURES, Scope.unrestricted()),
            *screen_grants("updates"),
        ),
    )
    await h.person(other, department=A)
    asked: list[str] = []

    def stand_in(url: str) -> bytes:
        asked.append(url)
        return json.dumps(
            [{"tag_name": STAND_IN_RELEASE, "draft": False, "prerelease": False}]
        ).encode()

    console = console_for(h, h.settings.model_copy(update={"release_check": False}))
    watch = ReleaseWatch(fetch=stand_in)
    console.app.state.release_watch = watch
    stranger = await asking_as(h, other)
    if not await refused(features(console.request(), stranger)):
        raise CheckFailedError("a person without the authority was shown the Features screen")
    if not await refused(
        switch_feature(console.request("POST"), RELEASE_CHECK.name, SwitchAsked(on=True), stranger)
    ):
        raise CheckFailedError("a person without the authority switched a feature")

    async with traced(h, 1):
        await switch_feature(
            console.request("POST"),
            RELEASE_CHECK.name,
            SwitchAsked(on=False),
            await asking_as(h, admin, strong=True),
        )
    off = await updates(console.request(), await asking_as(h, admin, strong=True))
    await asyncio.sleep(0)
    if asked or watch.looking or off.unanswered is None:
        raise CheckFailedError("the release list was asked with the release check switched off")

    async with traced(h, 2):
        shown = await switch_feature(
            console.request("POST"),
            RELEASE_CHECK.name,
            SwitchAsked(on=True),
            await asking_as(h, admin, strong=True),
        )
    if not shown.on or shown.changed_by != admin:
        raise CheckFailedError("the Features screen did not show the switch on and who turned it")
    entries = await setting_entries(h, RELEASE_CHECK.key)
    if not entries or entries[-1][0] != admin:
        raise CheckFailedError("a feature switched from the console is not in the audit trail")
    listed = await features(console.request(), await asking_as(h, admin, strong=True))
    if not any(one.name == RELEASE_CHECK.name and one.on for one in listed.features):
        raise CheckFailedError("the Features screen did not list the release check as on")

    await updates(console.request(), await asking_as(h, admin, strong=True))
    await settled(watch)
    after = await updates(console.request(), await asking_as(h, admin, strong=True))
    if len(asked) != 1 or after.told is None or after.told.tag != STAND_IN_RELEASE:
        raise CheckFailedError("Version and updates did not ask the release list once switched on")


# ------------------------------------------------------- 4. settings after setup (M27.12.7)
@check(
    leaves=("M27.12.7",),
    sentence=(
        "An administrator saves the accent colour from the Settings screen's route after setup: "
        "the screen shows it saved, says when a saved value applies and that an environment "
        "value needs a restart, the save is audited under their name, a value the screen "
        "refuses is not saved, and a person without the authority is refused."
    ),
)
async def a_setting_is_saved_from_the_console_and_says_when_it_applies(h: Harness) -> None:
    from brain.console.configuration import (
        A_VALUE_SAVED_HERE_APPLIES_HERE_AT_ONCE_IN_THE_WORKER_WITHIN_A_MINUTE,
        AN_ENVIRONMENT_VALUE_CHANGES_ON_RESTART,
    )
    from brain.install import hold_saved, saved_values
    from brain.ops.install_settings import key_for
    from brain.settings_routes import SaveAsked, save_setting, settings

    before = dict(saved_values())
    h.removes(lambda: hold_saved(before))
    await h.found_departments()
    admin, other = h.principal(A, "settings"), h.principal(A, "other")
    await h.person(admin, department=A, grants=((CHANGES_SETTINGS, Scope.unrestricted()),))
    await h.person(other, department=A)
    console = console_for(h)
    if not await refused(settings(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person without the authority was shown the Settings screen")

    page = await settings(console.request(), await asking_as(h, admin, strong=True))
    rows = {one.name: one for group in page.groups for one in group.settings}
    current = rows[SAVED_SETTING].value
    wanted = ACCENTS[0] if current != ACCENTS[0] else ACCENTS[1]
    if rows[SAVED_SETTING].applies != (
        A_VALUE_SAVED_HERE_APPLIES_HERE_AT_ONCE_IN_THE_WORKER_WITHIN_A_MINUTE
    ):
        raise CheckFailedError("an editable setting does not say when a saved value applies")
    if not any(
        not one.editable and one.applies == AN_ENVIRONMENT_VALUE_CHANGES_ON_RESTART
        for one in rows.values()
    ):
        raise CheckFailedError("no setting read from the environment says it needs a restart")

    try:
        async with traced(h, 3):
            bad = await save_setting(
                console.request("PUT"),
                SAVED_SETTING,
                SaveAsked(value="not a colour"),
                await asking_as(h, admin, strong=True),
            )
        async with traced(h, 4):
            saved = await save_setting(
                console.request("PUT"),
                SAVED_SETTING,
                SaveAsked(value=wanted),
                await asking_as(h, admin, strong=True),
            )
    finally:
        hold_saved(before)
    if bad.status_code != 422:
        raise CheckFailedError("a value the Settings screen refuses was saved")
    shown = json.loads(bytes(saved.body))
    after = {one["name"]: one for group in shown["groups"] for one in group["settings"]}
    if saved.status_code != 200 or after[SAVED_SETTING]["value"] != wanted:
        raise CheckFailedError("the Settings screen did not show the value it saved")
    if after[SAVED_SETTING]["source"] != "saved":
        raise CheckFailedError("the Settings screen did not say the value is the saved one")
    entries = await setting_entries(h, key_for(SAVED_SETTING))
    if not entries or entries[-1][0] != admin:
        raise CheckFailedError("a setting saved from the console is not in the audit trail")
    if dict(saved_values()) != before:
        raise CheckFailedError("the check left the process holding a value it saved")


# ----------------------------------------------- 5. rate limits and capacity (M27.7.27)
@check(
    leaves=("M27.7.27",),
    sentence=(
        "A reserved reader of Rate limits and of Connections is answered by the routes those "
        "pages call: the ceilings and windows in force with what is throttled now, read from the "
        "install's own cache, and the memory, connections and pools against what the install "
        "size and its database declare; a person without either screen is refused both."
    ),
)
async def rate_limits_and_capacity_answer_their_readers(h: Harness) -> None:
    from brain.cache import make_client
    from brain.install_routes import capacity, limits
    from brain.ops.limit_store import make_store

    await h.found_departments()
    reader, other = h.principal(A, "limits"), h.principal(A, "other")
    both = dict.fromkeys((*screen_grants("limits"), *screen_grants("connections")))
    await h.person(reader, department=A, grants=tuple(both))
    await h.person(other, department=A)
    if not h.settings.valkey_url:
        raise CheckNotRunError(NO_CACHE_TO_ASK)
    console = console_for(h)
    # The windows the request path counts in, read from the install's own cache as the
    # application reads them; reading them changes none. See `brain.install_routes.limits`.
    console.app.state.throttle_source = make_store(make_client(h.settings.valkey_url)).live
    stranger = await asking_as(h, other)
    if not await refused(limits(console.request(), stranger)):
        raise CheckFailedError("a person who may not open Rate limits was shown it")
    if not await refused(capacity(console.request(), stranger)):
        raise CheckFailedError("a person who may not open Connections was shown it")

    shown = await limits(console.request(), await asking_as(h, reader))
    if not shown.windows:
        raise CheckFailedError("Rate limits did not show the request windows in force")
    if shown.throttled is None:
        raise CheckFailedError("Rate limits did not read what is throttled now from the cache")
    sized = await capacity(console.request(), await asking_as(h, reader))
    if sized.memory.profile != h.settings.profile:
        raise CheckFailedError("Connections did not size memory for the install's own size")
    if not sized.connections or not sized.sizings:
        raise CheckFailedError("Connections did not show connections and pools against the plan")


# ------------------------------------------------------------- 6. furnished once (M27.9.5)
@check(
    leaves=("M27.9.5",),
    sentence=(
        "The install was furnished once, by the product and recorded in the ledger, writing only "
        "its setting, scope and pack and no person or demo row: every capability the product "
        "declares is registered, furnishing again writes nothing, and every built-in template "
        "is on file signed under the product's name with its shipped content."
    ),
)
async def the_install_was_furnished_once_by_the_product(h: Harness) -> None:
    from brain.agents.catalogue import CATALOGUE
    from brain.agents.template import SYSTEM_PUBLISHER, content_digest
    from brain.firstrun import GRANTED_BY
    from brain.ops.starter import vocabulary
    from brain.ops.starter_store import FURNISHED_KEY, furnish

    entries = await setting_entries(h, FURNISHED_KEY)
    if not entries:
        raise CheckNotRunError(NOTHING_HAS_FURNISHED_THIS_DATABASE)
    if entries[0][0] != GRANTED_BY:
        raise CheckFailedError("this install's furnishing was not recorded as the product's")
    registered = set(
        (
            await h.execute(
                text("SELECT capability FROM gate.capability_registry WHERE deleted_at IS NULL")
            )
        )
        .scalars()
        .all()
    )
    if any(one.capability.value not in registered for one in vocabulary()):
        raise CheckFailedError("a capability the product declares is not registered")
    traced_by = (
        (
            await h.execute(
                text(
                    "SELECT DISTINCT split_part(subject, ':', 1) FROM obs.audit_entry"
                    " WHERE trace_id = (SELECT trace_id FROM obs.audit_entry"
                    " WHERE subject = :subject ORDER BY seq LIMIT 1)"
                ).bindparams(subject=f"setting:{FURNISHED_KEY}")
            )
        )
        .scalars()
        .all()
    )
    if set(traced_by) - FURNISHING_WRITES_ONLY:
        raise CheckFailedError("the furnishing wrote something that is not the product's own")
    again = await furnish(h.sessions, actor=h.actor, trace_id=f"{h.trace_id}-furnish")
    if not again.wrote_nothing:
        raise CheckFailedError("furnishing an install furnished already wrote something")

    on_file = {
        (str(template), str(version)): (str(digest), str(signed_by), bool(signature))
        for template, version, digest, signed_by, signature in (
            await h.execute(
                text(
                    "SELECT template_id, version, content_digest, signed_by, signature"
                    " FROM agent.template_version"
                )
            )
        ).all()
    }
    found = [
        (one, on_file.get((one.identity.template_id, str(one.identity.version))))
        for one in CATALOGUE
    ]
    if not any(held for _, held in found):
        raise CheckNotRunError(NO_TEMPLATE_IS_ON_FILE)
    for manifest, held in found:
        if held is None or not held[2]:
            raise CheckFailedError("a built-in template is not on file signed")
        # A version somebody published under a built-in's number is theirs and kept; one the
        # product signed carries exactly what it shipped. See `builtin_templates.is_built_in`.
        if held[1] == SYSTEM_PUBLISHER and held[0] != content_digest(manifest):
            raise CheckFailedError(
                "a built-in template signed by the product is not what it shipped"
            )
