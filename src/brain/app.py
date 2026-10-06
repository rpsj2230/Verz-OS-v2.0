"""The FastAPI application.

Liveness and readiness are separate endpoints and the distinction is load-bearing.
Liveness answers "is this process alive"; readiness answers "can this process answer a
question correctly". A container that is up but cannot reach the database, the cache or
the secret store must fail readiness, because a half-connected instance does not refuse,
it answers from whatever it can still reach, which is how a permission-aware system
quietly starts returning wrong answers.

**The gate is built here, and three failures it can meet at startup are decided three ways.**
With a database, the lifespan builds `GateWiring` and `AutomationWiring` over the application's
own sessions. An install that cannot check a token at all, because `INSTALL_OIDC_ISSUER` is unset
or names an issuer no key set may be read from, leaves both None and reports `sign_in` as not
configured (`AN_INSTALL_THAT_CANNOT_CHECK_A_SIGN_IN_IS_UNREADY_RATHER_THAN_STOPPED`). An identity
provider that does not answer yet leaves the wiring built, reports `sign_in` not ready, and asks
again until it answers (`AN_IDENTITY_PROVIDER_NOT_YET_ANSWERING_IS_ASKED_AGAIN`). `sign_in` is
reported on readiness and never fails it (`SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS`).
And a login that could read past row-level security is not refused, because the sessions never
use it: see
`brain.session.THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS`, whose answer readiness
checks as `row_security`.

**Readiness names four parts whatever is configured: database, cache, vault and sign-in.** A
configured database, cache or vault decides the status and is asked again while the process runs;
sign-in and anything not configured are named and decide nothing. `brain.readiness` holds the
rules, and `parts` on the answer is what the console's Overview draws.

Task ids: M31.1.1.1, M31.1.1.2, M31.1.1.4, M31.1.1.5
Task ids: M31.1.3.1, M31.1.3.2, M31.1.3.3, M31.1.3.4, M31.1.3.5
Task ids: M31.1.1.3, M31.2.2.5, M31.4.1, M31.4.2
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, MutableMapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from typing import Final, Literal

import httpx
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from brain.agent_routes import every_agent, record_of
from brain.agents.model import AgentRecord
from brain.api import (
    ErrorBody,
    FailureBodyMiddleware,
    TimeoutMiddleware,
    bound_trace_id,
    refused_request,
    status_sentence,
    unexpected_failure,
)
from brain.api_routes import GateWiring, passage_search_for, second_factor_needed
from brain.attribution import trace_of_request
from brain.audit.ledger import TRACE_ID
from brain.automation_routes import AutomationWiring
from brain.cache import (
    AsyncValkeyClient,
    NoEntitlementCache,
    OwnedAsyncValkeyClient,
    PostgresVersionSource,
    ValkeyAnswerStore,
    ValkeyEntitlementCache,
    check_reachable_async,
    embedding_cache,
    make_async_client,
    make_client,
    retrieval_cache,
    source_epochs_cache,
)
from brain.channels.widget import allowed_origins
from brain.console_static import mount_console_entry, mount_console_fallback
from brain.core.errors import Absent, BrainError, Outcome, to_public
from brain.docs_routes import router as docs_router
from brain.escalation_told import keep_telling_expired_askers
from brain.firstrun import GRANTED_BY
from brain.gate.admission import SECOND_FACTOR_NEEDED_MESSAGE
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.finish import RequestRecorder
from brain.gate.resolve import EntitlementCache
from brain.gate.roster import AgentRoster
from brain.gate.rule_store import load_rules, rule_ids
from brain.gate.suspension_store import StoredSuspensions
from brain.gate.takeover_store import StoredTakeovers
from brain.identity.administration_reconciliation import (
    TRACE_PREFIX as RECONCILIATION_TRACE,
)
from brain.identity.administration_reconciliation import (
    reconcile_first_administrators,
    reconcile_member_grants,
    reconcile_super_admin_roles,
)
from brain.identity.bearer import TokenAuthority, log_refusal, refusal_headers
from brain.identity.first_administrator import FirstAdministrators
from brain.identity.group_sync import GroupSync, StoredGroupRules
from brain.identity.keycloak_tokens import http_get, keycloak_authority
from brain.identity.oidc import SIGN_IN_PROMPT, TokenRefusedError
from brain.identity.principal_directory import StoredDirectory
from brain.identity.principal_store import StoredPrincipals
from brain.identity.roles import IdentityError
from brain.identity.sign_in_binding import sign_in_bindings
from brain.install import InstallError, installed_name, value_of
from brain.knowledge.app_parse_budget import app_parse_gaps
from brain.knowledge.document_tools import KnowledgeCaches
from brain.knowledge.row_store import SessionRowSource
from brain.mailbox_read import keep_reading_the_mailbox
from brain.migrate import run_migrations
from brain.models.default_ladder import reconcile as reconcile_default_ladder
from brain.ops.admission import WorkloadClass
from brain.ops.artifact_store import artifacts_for
from brain.ops.automation_owner_store import StoredAutomations
from brain.ops.builtin_templates import sign_built_ins
from brain.ops.class_pools import keep_following
from brain.ops.connector_sync_store import ReadThroughSourceEpochs, StoredSourceEpochs
from brain.ops.credential_write_store import credential_writes_for
from brain.ops.credentials import credentials_at_start, keep_refreshing
from brain.ops.default_ladder_store import SessionLadderWriter
from brain.ops.install_settings import keep_holding
from brain.ops.install_settings import refresh as refresh_install_settings
from brain.ops.join_key_pepper import pepper_at_start
from brain.ops.ledger_export import KeptKeys, LedgerShipper, destination_here
from brain.ops.live_read_run import live_records_for
from brain.ops.log_store import start_log_store, stop_log_store
from brain.ops.matrix_gate_run import InstallMatrixGate
from brain.ops.model_service import (
    ModelService,
    held_providers,
    model_service_at_start,
)
from brain.ops.object_store import backup_objects, object_store_at_start
from brain.ops.openbao import OpenBaoVault
from brain.ops.pii import analyzer_address
from brain.ops.question_gap_store import GapRecorder
from brain.ops.question_store import QuestionRecorder
from brain.ops.replica_store import console_reads_for
from brain.ops.sandbox import sandbox_address
from brain.ops.secrets import VaultRole
from brain.ops.sensitive_read_store import SensitiveReadRecorder
from brain.ops.starter_store import furnish as furnish_install
from brain.ops.telemetry_store import TelemetryRecorder
from brain.ops.template_key import TemplateKeyState, keep_trying, template_key_at_start
from brain.ops.template_key import hold as hold_template_key
from brain.ops.tool_store import SessionSwitchSource, record_catalogue
from brain.ops.trace_sink import CountingTraceSink
from brain.ops.trace_store import Step, TraceRecorder
from brain.ops.usage_store import UsageRecorder
from brain.ops.vault_renewal import keep_renewing, renewer_at_start
from brain.ops.webhook_admin import signing_secrets_at_start
from brain.ops.webhook_delivery import SystemResolver
from brain.ops.website_probe import HttpsProber
from brain.readiness import (
    CACHE_PART,
    DATABASE_LOGIN_PART,
    DATABASE_PART,
    SIGN_IN_PART,
    VAULT_PART,
    ReadinessPart,
    Readings,
    issuer_answers,
    parts_of,
    vault_answers,
    vault_configured,
)
from brain.routers import ROUTERS
from brain.session import (
    check_login_row_security,
    check_reachable,
    check_row_security,
    dispose,
    make_app_engine,
    make_application_sessions,
)

# Re-exported, because tests, `console/scripts/export-openapi.py` and `brain.serve`'s history all
# import it from here. It is defined in `brain.settings`, which builds nothing when imported; a
# process that needs a setting and not the application imports that instead. See
# `brain.settings.SETTINGS_ARE_READ_WITHOUT_BUILDING_THE_APPLICATION`.
from brain.settings import Settings as Settings
from brain.tools.startup import build_registry
from brain.tools.website_check import WebsiteCheckTool

log = structlog.get_logger()


#: The grammar a trace id must satisfy to be accepted from a caller.
#:
#: The audit ledger's own, compiled once, imported rather than restated. A second spelling
#: here would admit ids the ledger then refuses, which is the failure this guard exists to
#: close: a request whose audit entry cannot be written.
TRACE_ID_RE = re.compile(TRACE_ID)

#: The readiness check that says whether this process can turn a token into a caller.
SIGN_IN_CHECK: Final = SIGN_IN_PART

#: The readiness check that says whether requests run as a role row-level security binds.
ROW_SECURITY_CHECK: Final = "row_security"

#: The readiness check for a configured cache. Named not configured when there is none.
CACHE_CHECK: Final = CACHE_PART

#: The readiness check for a configured secrets vault. Named not configured when there is none.
VAULT_CHECK: Final = VAULT_PART

#: The methods and headers a cross-origin caller may use. PUT and PATCH because two console
#: writes are one of each (`provider_routes`, `routing_routes`); no DELETE, because no route is one.
#: `x-upload-name` carries an uploaded file's name, which `brain.knowledge_routes` keeps out of
#: the URL.
CORS_METHODS: Final = ("GET", "POST", "PUT", "PATCH")
CORS_HEADERS: Final = ("authorization", "content-type", "x-trace-id", "x-upload-name")

#: Why the CORS allow list is two named settings, normalised, and never a wildcard.
CORS_ADMITS_THE_CONSOLE_AND_THE_WIDGET_AND_NOTHING_ELSE: Final = (
    "Only two kinds of page call this API from another origin: the console, when an install "
    "serves it from a second host, and a site embedding the widget. So the allow list is "
    "cors_origins and widget_origins and nothing else, each entry normalised by the widget's own "
    "origin rule and a wildcard refused in every environment, including development, because a "
    "development setting copied to a server is how a wildcard reaches production."
)

#: The wait before asking an identity provider that did not answer at startup again, and the most
#: that wait grows to. The ceiling is two of `oidc.JWKS_MIN_REFETCH`, so a realm that comes up is
#: noticed inside a minute and a realm that stays down is asked once a minute, not once a second.
KEY_PRIMING_FIRST_RETRY_SECONDS: Final = 2.0
KEY_PRIMING_MAX_RETRY_SECONDS: Final = 60.0

#: Why sign-in is named on readiness and never fails it.
SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS: Final = (
    "The compose health check, ops/deploy.sh and ops/watch-and-deploy.sh all treat anything but "
    "200 from /health/ready as a failed release. Measured on 2026-09-15, a deployed app "
    "container carried DATABASE_URL and VALKEY_URL and no INSTALL_OIDC_ISSUER, so a blocking "
    "sign_in check would have made its next deploy unhealthy and taken down with it every page "
    "that needs no sign-in: the build tracker, the status JSON, the owner's decision list and the "
    "setup wizard that is how the issuer gets set. The same coupling would take the whole "
    "application unhealthy whenever Keycloak restarts. So sign_in is under reported, which "
    "/health/ready shows and never counts. Nothing fails open for it: with no issuer the gate "
    "is not built and every route behind sign-in refuses, and with keys not yet fetched the key "
    "cache refuses a token it cannot check. The database, the cache and row_security stay "
    "blocking, because when they fail every read fails with them and the instance has nothing "
    "correct to serve."
)

#: Why a missing or unusable issuer does not stop the process.
AN_INSTALL_THAT_CANNOT_CHECK_A_SIGN_IN_IS_UNREADY_RATHER_THAN_STOPPED: Final = (
    "An unset INSTALL_OIDC_ISSUER, or one keycloak_tokens refuses to read keys for, is a "
    "configuration no retry cures. The process runs with no gate, so every route behind sign-in "
    "refuses, /health/ready names sign_in as not configured under reported, and the log says "
    "which setting. Stopping instead is the arrangement this lifespan already rejects for "
    "migrations, a restart loop that discards the reason on every cycle, and it would also take "
    "down liveness, the status page and the setup wizard, which are how an operator finds and "
    "fixes the setting. See SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS for why the name "
    "is reported and not counted."
)

#: Why an identity provider that does not answer at startup is retried rather than fatal.
AN_IDENTITY_PROVIDER_NOT_YET_ANSWERING_IS_ASKED_AGAIN: Final = (
    "On standard and full the realm is a container started beside this one, and it takes longer "
    "to import its realm than this process takes to boot, so a key set unreachable at startup is "
    "usually a race and not a fault. Stopping would turn every cold start into a restart loop "
    "timed against Keycloak. So the wiring is built anyway, sign_in is reported not ready while "
    "the key set has never been fetched, and a background task asks again with a growing wait "
    "until it answers, then reports sign_in ready. Until then a token is refused, because the "
    "key cache has nothing to check it against."
)

#: Why the endpoints `create_app` defines read their application from the request.
AN_ENDPOINT_NEVER_CLOSES_OVER_ITS_APPLICATION: Final = (
    "FastAPI keeps every endpoint and dependency it inspects in module-level caches of 4096 "
    "entries (fastapi.dependencies.models), holding the function itself. An endpoint defined "
    "inside create_app that closes over app therefore keeps that application, its engines and "
    "its routing table alive for as long as the cache does. A server builds one application and "
    "never notices. The test suite builds thousands, two cache entries each, so up to some two "
    "thousand stayed alive at once; measured on 2026-09-30, five route test files left 122, and "
    "in a full run one request took 504 seconds against a deadline of 30. So such an endpoint "
    "takes request: Request and reads request.app."
)


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    commit: str
    checks: dict[str, bool] = {}
    #: Components named and never counted. See `SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS`.
    reported: dict[str, bool] = {}
    #: Every part in one list, the four headline parts always present. See `brain.readiness`.
    parts: list[ReadinessPart] = []


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info("starting", env=settings.env, commit=settings.resolved_commit())
    # What a document read in this container may cost, and whether the door admits more than
    # that, said once where an operator reads it. See `brain.knowledge.app_parse_budget`.
    for finding in app_parse_gaps():
        log.warning("in-app parse budget", finding=finding)
    # The four handles attach here: the database pool (`db_engine`, `db_sessions`), Valkey
    # (`valkey`), the OpenBao client (`vault`) and the model registry (`models`). The first three
    # are named parts on readiness; the models are not, as a driver per provider is built whatever
    # is configured, so a part for them would always say ready. See `vault_at_start`.
    app.state.ready = {}
    # Named on readiness and never counted. See SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS.
    app.state.reported = {}
    # The blocking checks that can be asked again, each registered below beside its first answer.
    # See `brain.readiness.A_READING_IS_SHARED_SO_AN_ANONYMOUS_CALLER_CANNOT_AMPLIFY_IT`.
    readings = Readings()
    app.state.readings = readings
    # The secrets vault, and every provider key it holds loaded into this process's environment
    # before anything could call a model. In a thread, because the client blocks, and before the
    # database, because a key does not depend on one. With no vault named this asks nobody. See
    # `brain.ops.credentials`.
    app.state.credentials = await asyncio.to_thread(
        credentials_at_start, settings.vault_address, settings.vault_token
    )
    # Webhook subscribers' signing secrets, through the same two settings and asking the vault
    # nothing at start: a secret is written when somebody registers a subscriber. See
    # `brain.ops.webhook_admin`.
    app.state.signing_secrets = signing_secrets_at_start(
        settings.vault_address, settings.vault_token
    )
    # This process's own vault token, renewed by this process, because OpenBao renews a token
    # only for whoever presents it. See `brain.ops.vault_renewal`.
    renewer = renewer_at_start(settings.vault_address, settings.vault_token)
    # The one vault client the screens read through, under the application's role.
    app.state.vault = vault_at_start(settings.vault_address, settings.vault_token)
    # This install's template signing key, read from its write-once slot and minted there first
    # if the slot has never held one, onto `template_key` where the agent routes read it. A vault
    # that was sealed or silent is asked again every minute. See `brain.ops.template_key`.
    hold_template_key(
        app.state,
        await asyncio.to_thread(
            template_key_at_start, settings.vault_address, settings.vault_token
        ),
    )
    trying = (
        asyncio.create_task(
            keep_trying(
                lambda: asyncio.to_thread(
                    template_key_at_start, settings.vault_address, settings.vault_token
                ),
                lambda found: hold_template_key(app.state, found),
            )
        )
        if app.state.template_key_state is TemplateKeyState.UNREAD
        else None
    )
    # This install's join-key pepper, created in its write-once slot if the slot has never held one,
    # which is how an install made before the slot existed comes to hold one with nobody at the
    # server. Only made sure of here: the processes that hash join keys read it when they hash.
    # Never raises; a vault that was sealed or silent is asked again at the next start. See
    # `brain.ops.join_key_pepper`.
    await asyncio.to_thread(pepper_at_start, settings.vault_address, settings.vault_token)
    # A vault the install names decides readiness; one it does not name is shown as not
    # configured. See `brain.readiness.A_PART_NOBODY_CONFIGURED_IS_NAMED_AND_NEVER_COUNTED`.
    if vault_configured(settings.vault_address, settings.vault_token):

        async def vault_probe() -> bool:
            return await asyncio.to_thread(
                vault_answers, settings.vault_address, settings.vault_token
            )

        readings.probes[VAULT_CHECK] = vault_probe
        app.state.ready[VAULT_CHECK] = await vault_probe()
    renewing = asyncio.create_task(keep_renewing(renewer)) if renewer is not None else None
    # Every provider key this process uses, re-read when its slot's version moves, so a key
    # replaced in the vault is in use here within a minute and nothing is redeployed. See
    # `brain.ops.credentials.A_KEY_REPLACED_IN_THE_VAULT_IS_USED_WITHOUT_A_RESTART`.
    refreshing = (
        asyncio.create_task(keep_refreshing(app.state.credentials))
        if app.state.credentials.configured
        else None
    )
    # The saved settings, re-read every minute once they are first loaded below, so a value
    # changed on the Settings screen reaches every process and not only the one that saved it.
    # See `brain.ops.install_settings.A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER`.
    holding: asyncio.Task[None] | None = None
    # The request path's sessions, moved onto the interactive class's pool while this release's
    # class pooler runs and left on their own engine otherwise. See `brain.ops.class_pools`.
    following: asyncio.Task[None] | None = None
    # The email channel's mailbox, read every minute where the answer is made; it reads nothing
    # while the channel's record reads no mailbox. See `brain.mailbox_read`.
    reading: asyncio.Task[None] | None = None
    telling: asyncio.Task[None] | None = None

    if settings.run_migrations and not settings.database_url and settings.env != "development":
        # Loud on purpose. Skipping migrations because a variable was unset is exactly
        # how the deployed app came up healthy against an empty schema.
        log.error(
            "no database configured outside development; migrations skipped",
            env=settings.env,
            hint="set DATABASE_URL or BRAIN_DATABASE_URL",
        )
        app.state.ready["database_configured"] = False

    if settings.database_url and settings.run_migrations:
        # Before readiness, deliberately: the application must not answer a question
        # against a schema it does not match. Concurrency between replicas is handled by
        # an advisory lock inside run_migrations, not by hoping.
        try:
            # As the owner when the install names one, so the application's own login can be
            # `brain_app`. See
            # `brain.session.A_REQUEST_TRANSACTION_CAN_RESET_ITS_ROLE_TO_THE_LOGIN`.
            applied = await asyncio.to_thread(run_migrations, settings.owner_database_url())
            app.state.ready["migrations"] = True
            if applied:
                log.info("schema migrated", revisions=applied)
        except Exception:
            # Left unready rather than crashed, so the failure is visible on
            # /health/ready and in the logs instead of a container restart loop that
            # discards the traceback.
            log.exception("migrations failed")
            app.state.ready["migrations"] = False

    if settings.database_url:
        # The pool is attached after migrations, so a replica never serves against a
        # schema the migration is still changing.
        app.state.db_engine = make_app_engine(settings.database_url)
        # Every transaction as `brain_app`, whatever the URL logged in as. See
        # `brain.session.THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS`.
        app.state.db_sessions = make_application_sessions(app.state.db_engine)
        # Warnings and errors this process logs from here on are also kept, redacted and bounded,
        # for the Logs screen; standard output is unchanged. See `brain.ops.log_capture`.
        app.state.log_store = start_log_store(app.state.db_sessions, settings)
        engine = app.state.db_engine

        async def database_probe() -> bool:
            return await check_reachable(engine)

        readings.probes[DATABASE_PART] = database_probe
        app.state.ready[DATABASE_PART] = await database_probe()
        # Named and not counted: every install deployed before the migration login existed logs
        # in as the owner, and failing readiness for that would take each of them down on update.
        app.state.reported[DATABASE_LOGIN_PART] = await check_login_row_security(engine)
        # Before anything reads an installation value, because the setup wizard's answers
        # live in `ops.setting` and `brain.install.value_of` resolves them ahead of the
        # environment. A database that refuses is not a reason to stop: the values resolve
        # from the environment and then from their declared defaults exactly as they did
        # before the table had a reader. See `brain.ops.install_settings`.
        try:
            await refresh_install_settings(app.state.db_sessions)
        except Exception:
            log.exception("installation settings could not be loaded")
        holding = asyncio.create_task(keep_holding(app.state.db_sessions))
        following = asyncio.create_task(
            keep_following(
                app.state.db_sessions,
                url=settings.database_url,
                workload=WorkloadClass.INTERACTIVE,
                commit=settings.resolved_commit(),
            )
        )
        reading = asyncio.create_task(keep_reading_the_mailbox(app))
        # An asker whose handed-on question expired is told in their own chat, by this process
        # because the worker holds no channel's token. See `brain.escalation_told`.
        telling = asyncio.create_task(keep_telling_expired_askers(app))
        # An administrator appointed before a capability existed is granted it now, and one whose
        # capability was taken away is not given it back. After the migrations, under the
        # appointment's own lock, and never fatal: a missing capability is a screen that refuses,
        # and a process that will not start is every screen. See
        # `brain.identity.administration_reconciliation`.
        try:
            await reconcile_first_administrators(
                app.state.db_sessions,
                now=datetime.now(UTC),
                trace_id=f"{RECONCILIATION_TRACE}{uuid.uuid4().hex[:16]}",
            )
        except Exception:
            log.exception("first administrator could not be reconciled")
        # A sign-in bound before binding granted a workspace is granted one now, once per binding,
        # and one taken away is not given back. Its own attempt, so a failure in either leaves the
        # other done, and never fatal for the same reason. See
        # `brain.identity.administration_reconciliation.reconcile_member_grants`.
        try:
            await reconcile_member_grants(
                app.state.db_sessions,
                now=datetime.now(UTC),
                trace_id=f"{RECONCILIATION_TRACE}{uuid.uuid4().hex[:16]}",
            )
        except Exception:
            log.exception("member grants could not be reconciled")
        # A first administrator appointed before role grants existed is recorded as Super Admin,
        # once. See `administration_reconciliation.reconcile_super_admin_roles`.
        try:
            await reconcile_super_admin_roles(
                app.state.db_sessions,
                now=datetime.now(UTC),
                trace_id=f"{RECONCILIATION_TRACE}{uuid.uuid4().hex[:16]}",
            )
        except Exception:
            log.exception("super admin role could not be reconciled")
    else:
        app.state.db_engine = None
        app.state.db_sessions = None
    # Console pages that only display, read from `read_replica_url` when one is set and from
    # the primary otherwise. None without a primary. See `brain.ops.replica_store`.
    app.state.console_reads = console_reads_for(app.state.db_sessions, settings.read_replica_url)
    # Every credential kept from here on leaves a ledger entry through `ops.credential_write`.
    # Attached after the database because the record is a row in it, to the store built before it
    # because loading keys needs none; unchanged without a database. See
    # `brain.ops.credentials.A_CREDENTIAL_WRITE_LEAVES_A_LEDGER_ENTRY_AND_NEVER_THE_VALUE`.
    app.state.credentials = app.state.credentials.recording_to(
        credential_writes_for(app.state.db_sessions)
    )
    # The object store, connected once from the installation settings and the key in its backend's
    # vault slot, or the sentence saying why not. After the database, because a wizard's saved
    # answer outranks the environment file and is loaded above; in a thread, because the vault
    # client blocks. The backup bucket's reader and the artifact store are built over it, and a
    # process connected to nothing attaches no backup reader, which the recovery screen answers
    # in words. See `brain.ops.object_store`.
    app.state.object_store = await asyncio.to_thread(
        object_store_at_start, settings.vault_address, settings.vault_token
    )
    connected = app.state.object_store.backend
    app.state.backup_objects = None if connected is None else backup_objects(connected)
    app.state.artifacts = artifacts_for(app.state.db_sessions, app.state.object_store)
    app.state.artifact_source = None if app.state.artifacts is None else app.state.artifacts.every

    # Built and frozen here, and this is the first process that has ever built one. Every
    # rule in `brain.tools.registry` runs at registration and `freeze` runs the ones that
    # need the whole set, so a registry nobody constructs is a set of rules that has never
    # refused anything. See `brain.tools.startup`.
    #
    # It raises rather than degrading, which is the opposite of how everything else in this
    # lifespan handles a failure, and deliberately: an unreachable database leaves an
    # instance that answers what it can, whereas a catalogue that failed its own checks is
    # a set of tools nobody validated being offered to a model.
    # **The registry has row tools in it now, and until 2026-09-07 it could not.** This
    # paragraph used to explain why `tools=0` sat in the log beside `/health/ready` reporting
    # `{"tools": true}`: `build_registry` was called with no `records=`, because
    # `RowSource.rows` was synchronous and this application has an `AsyncEngine`, so nothing
    # could implement the protocol against the pool already here. The row plane is awaitable
    # now and `SessionRowSource` is that implementation, using this engine and adding no
    # second pool.
    #
    # A source only when there is a database. Without one there is nothing to read, and a row
    # tool present and unable to answer is worse than one missing: `brain.tools.startup`
    # argues it, and the short version is that a missing tool is a gap somebody notices and
    # an empty answer is a fact somebody believes.
    #
    # `ready["tools"]` is still True in both cases and still means "the catalogue is valid"
    # rather than "there is something in it". That is now a smaller overstatement than it
    # was, and it is still one: a lite install with no database registers nothing and reports
    # the same True. What would fix it is readiness knowing which profile it is in, which is
    # a change to what the check means rather than to this line.
    records = SessionRowSource(app.state.db_sessions) if app.state.db_sessions else None
    # The live reads a connected source's figure tools make (M11.7.1), kept on the state so the
    # answer lane's refreshes share their throttle, breakers and fetches in flight
    # (`brain.api_routes.live_records_of` finds this one).
    live = live_records_for(app.state.db_sessions or None, app.state.vault)
    if live is not None:
        app.state.live_records = live
    # The website check over HTTPS, to the address each hop was checked at (M12.4.4).
    website = WebsiteCheckTool(resolver=SystemResolver(), prober=HttpsProber())
    # The document plane's retrieval and embedding caches (M6.2.3, M6.2.4), only where a cache
    # is configured and there is a database to search. Their own synchronous client, as the
    # answer store has, closed below. See `brain.knowledge.document_tools.KnowledgeCaches`.
    app.state.knowledge_cache_client = None
    knowledge_caches = None
    if records is not None and settings.valkey_url:
        knowledge_client = make_client(settings.valkey_url)
        app.state.knowledge_cache_client = knowledge_client
        knowledge_caches = KnowledgeCaches(
            retrievals=retrieval_cache(knowledge_client),
            embeddings=embedding_cache(knowledge_client),
        )
    app.state.tools = build_registry(
        source=settings.tool_source,
        records=records,
        figures=live if records else None,
        website=website,
        caches=knowledge_caches,
    )
    app.state.ready["tools"] = True
    # Every call to a registered tool asks the switch table first, and each tool's catalogue row
    # is written so a stop has a row to name. Never fatal: a catalogue row a switch needs is
    # written by the switch itself. See `brain.tools.registry.ToolRegistry.govern`.
    if app.state.db_sessions:
        app.state.tools.govern(SessionSwitchSource(app.state.db_sessions))
        try:
            await record_catalogue(app.state.db_sessions, app.state.tools)
        except Exception:
            log.exception("tool catalogue could not be recorded")
    # The passage search the answer lane's model step reads through: the registered document
    # tool's own handler, so the reach is decided where the tool decides it. None without a row
    # source, which is a lane that abstains on a question no rule answers. See
    # `brain.api_routes.model_lane_of`.
    app.state.passage_search = passage_search_for(app.state.tools)
    log.info(
        "tool registry frozen",
        tools=len(app.state.tools),
        rows=records is not None,
    )

    # The answer lane's two remaining pieces, and both are decisions rather than plumbing.
    #
    # The rules are not read here. The answer route reads the rule table on every question,
    # for the asker's department and the whole install's, so a rule an administrator adds
    # answers the next question rather than the next restart (M6.5.1). See
    # `rule_store.A_RULE_ANSWERS_FROM_THE_NEXT_QUESTION`. `fast_path_rules` stays, empty, for
    # the rules a test or a check hands the lane directly.
    #
    # The sink records that a trace happened and drops the payload, because the only
    # destination available today is the application log and a post-redaction payload there is
    # readable by whoever can read logs, which is not who could read the records. See
    # `trace_sink.THE_LOG_IS_NOT_A_TRACE_STORE`. It is installed unconditionally, unlike the
    # rules, because a lane with no sink cannot compose at all. A run's masked trace graph goes to
    # the payload store through `TraceRecorder` among the recorders below (M24.3.4).
    app.state.trace_sink = CountingTraceSink()
    # The trace ledger, where `INSTALL_SERVICES` switched it on, is sent the same graph beside
    # the request (M32.1.2.6). Where and with which keys are asked on every send, so a ledger
    # switched on later, or keys a deploy handed over, are used without a restart.
    app.state.ledger_shipper = LedgerShipper(
        destination=partial(destination_here, settings.profile, settings.langfuse_host),
        keys=KeptKeys(app.state.vault, clock=wall_clock),
        clock=wall_clock,
    )
    app.state.request_recorders = request_recorders_for(
        app.state.db_sessions,
        environment=settings.env,
        ship=app.state.ledger_shipper.ship_beside,
    )
    # The stored agents `/answer` may select from, read once per question (M3.9.8).
    app.state.agent_roster = agent_roster_for(app.state.db_sessions)
    # The model driver, assembled once over this install's database: a driver per provider this
    # product can reach, sharing one HTTP client this lifespan closes. Which rungs answer is read
    # per call from the ladder, the provider switches and the keys this process holds, so a
    # switch or a key saved from the console takes effect without a restart. See
    # `brain.ops.model_service` and `brain.models.assembly`.
    # Where skill scripts run, or None where this install runs no sandbox (M12.2.9). No
    # installation switches it on until the sandbox overlay lands with its switch; until then
    # the set of switched services is empty and every skill with scripts is refused at the door.
    app.state.sandbox_address = sandbox_address(settings.sandbox_url, frozenset())
    # Every request to a third-party model is scrubbed of personal data on its way out, by the
    # rules and by the install's analyser where its profile deploys one (`brain.ops.egress`).
    app.state.models = model_service_at_start(
        app.state.db_sessions,
        analyser_address=analyzer_address(settings.profile, settings.presidio_url),
    )
    # The matrix gate a Routing screen change is run through before it takes traffic (M5.6.2).
    # Reads the state above at each change, so it asks the rules and registry of that moment.
    app.state.matrix_gate = InstallMatrixGate(app.state)
    # The default routing ladder: written by the wizard as it appoints, through this writer, and
    # reconciled here for an install that has been set up and whose ladder nobody has ever held.
    # After the installation settings and the vault's keys, because the profile and the held
    # keys name the provider; never fatal, because a missing ladder is a question that cannot
    # reach a model and a process that will not start is every screen. See
    # `brain.models.default_ladder`.
    app.state.default_ladder = None
    if app.state.db_sessions is not None:
        writer = SessionLadderWriter(app.state.db_sessions)
        app.state.default_ladder = writer
        try:
            now = datetime.now(UTC)
            written = await reconcile_default_ladder(
                writer,
                administrators=await FirstAdministrators(app.state.db_sessions).administrators(now),
                profile=value_of("INSTALL_MODEL_PROFILE"),
                held=held_providers(),
                actor=GRANTED_BY,
                trace_id=f"{RECONCILIATION_TRACE}{uuid.uuid4().hex[:16]}",
            )
            log.info("default ladder reconciled", outcome=written.value)
        except Exception as exc:
            log.warning("default ladder could not be reconciled", error=type(exc).__name__)
    # The starter set: one company-wide scope, the starter pack and the capability registry,
    # furnished at every start so an install set up before furnishing existed gets it on its next
    # deploy with no command. Unlike the ladder it waits on no wizard answer, because nothing it
    # writes is a company's choice; it writes nothing on a start after the first, and never puts
    # back a scope or pack somebody retired. Never fatal, for the ladder's reason. See
    # `brain.ops.starter_store.EVERY_START_FURNISHES_BECAUSE_NOTHING_FURNISHED_IS_AN_ANSWER`.
    if app.state.db_sessions is not None:
        try:
            furnished = await furnish_install(
                app.state.db_sessions,
                actor=GRANTED_BY,
                trace_id=f"{RECONCILIATION_TRACE}{uuid.uuid4().hex[:16]}",
            )
            log.info(
                "install furnished",
                first=furnished.first,
                registered=len(furnished.registered),
                scopes=list(furnished.scopes),
                packs=list(furnished.packs),
            )
        except Exception as exc:
            log.warning("install could not be furnished", error=type(exc).__name__)
        # The shipped templates, signed with the key this process read from its write-once slot
        # above, so the gallery offers them to install. A version already on file is kept, so a
        # start after the first writes nothing; never fatal, for furnishing's reason. See
        # `brain.ops.builtin_templates`.
        try:
            signed = await sign_built_ins(
                app.state.db_sessions,
                key=app.state.template_key,
                at=datetime.now(UTC),
                actor=GRANTED_BY,
                trace_id=f"{RECONCILIATION_TRACE}{uuid.uuid4().hex[:16]}",
            )
            log.info("built-in templates signed", written=len(signed))
        except Exception as exc:
            log.warning("built-in templates could not be signed", error=type(exc).__name__)
    # Approvals are read and decided on the database, whose trigger keeps each decision's ledger
    # entry. See `suspension_store_for`.
    app.state.suspensions = suspension_store_for(app.state.db_sessions)
    # Where the autonomy breaker reads when an agent's work was taken over (M8.3.5), through the
    # one function `0172` grants past the suspension policy. See `brain.gate.takeover_store`.
    app.state.takeovers = (
        StoredTakeovers(app.state.db_sessions) if app.state.db_sessions is not None else None
    )
    app.state.fast_path_rules = ()
    if app.state.db_sessions:
        try:
            # Counted once for the startup log, and never held: what a question is matched
            # against is read when it is asked. A table that cannot be read is said here too.
            standing = await load_rules(app.state.db_sessions)
            log.info("fast path rules standing", rules=len(standing), ids=rule_ids(standing))
        except Exception as exc:
            log.warning("fast path rules unavailable", error=type(exc).__name__)

    # The gate and the automation route, built only over a database: every store in both reads
    # it, and without one there is nothing a caller could be resolved against. The HTTP client
    # the realm's keys come through and the cache client are owned here and closed below.
    app.state.gate = None
    app.state.automation = None
    app.state.sign_in_bindings = None
    app.state.first_administrators = None
    app.state.key_client = None
    app.state.valkey = None
    # The answer cache `/answer`'s front half looks in, only where a cache is configured. With
    # none the CACHE step still runs and misses; see `brain.api_routes.caching_of`. Its own
    # synchronous client, because `brain.gate.answer_cache.AnswerStore` is synchronous.
    app.state.answer_store = None
    app.state.answer_client = None
    priming: asyncio.Task[None] | None = None
    if app.state.db_sessions is not None:
        app.state.key_client = key_set_client()
        if settings.valkey_url:
            cache_client = make_async_client(settings.valkey_url)
            app.state.valkey = cache_client
            answer_client = make_client(settings.valkey_url)
            app.state.answer_client = answer_client
            app.state.answer_store = ValkeyAnswerStore(answer_client)
            # The answer key's source epochs (M6.2.5), read through the cache on the answer
            # store's client, so a question costs no database read for them. Without a cache
            # `brain.api_routes.source_epochs_of` reads the counter itself, and with none it
            # keys on nothing because nothing is cached.
            app.state.source_epochs = ReadThroughSourceEpochs(
                StoredSourceEpochs(app.state.db_sessions), source_epochs_cache(answer_client)
            )

            async def cache_probe() -> bool:
                return await check_reachable_async(cache_client)

            readings.probes[CACHE_CHECK] = cache_probe
            app.state.ready[CACHE_CHECK] = await cache_probe()
        sessions = app.state.db_sessions

        async def row_security_probe() -> bool:
            return await check_row_security(sessions)

        readings.probes[ROW_SECURITY_CHECK] = row_security_probe
        app.state.ready[ROW_SECURITY_CHECK] = await row_security_probe()
        get = http_get(app.state.key_client)
        wired = wirings_for(
            app.state.db_sessions,
            get=get,
            cache=entitlement_cache_for(app.state.valkey),
            clock=wall_clock,
        )
        # Reported, never counted. See SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS.
        app.state.reported[SIGN_IN_CHECK] = False
        if wired is not None:
            app.state.gate, app.state.automation = wired
            # `wirings_for` has already refused an unset or unusable issuer, so this cannot raise.
            app.state.sign_in_bindings = sign_in_bindings(app.state.db_sessions)
            # Beside the bindings writer and never without it. See
            # `brain.setup_routes.NO_APPOINTMENT_WHERE_NOBODY_COULD_SIGN_IN_AFTER_IT`.
            app.state.first_administrators = FirstAdministrators(app.state.db_sessions)
            answered = await sign_in_answers(wired[0].authority, get, wall_clock)
            app.state.reported[SIGN_IN_CHECK] = answered
            priming = asyncio.create_task(
                keep_watching(
                    wired[0].authority, get, app.state.reported, wall_clock, answered=answered
                )
            )

    try:
        yield
    finally:
        # Drain before the socket closes. Uvicorn stops accepting first, so in-flight
        # requests finish against a live pool rather than a disposed one.
        log.info("shutting down")
        if renewing is not None:
            renewing.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renewing
        if refreshing is not None:
            refreshing.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await refreshing
        if holding is not None:
            holding.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await holding
        if following is not None:
            following.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await following
        if reading is not None:
            reading.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reading
        if telling is not None:
            telling.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await telling
        if trying is not None:
            trying.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await trying
        if priming is not None:
            priming.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await priming
        key_client: httpx.Client | None = getattr(app.state, "key_client", None)
        if key_client is not None:
            key_client.close()
        models: ModelService | None = getattr(app.state, "models", None)
        if models is not None:
            models.close()
        valkey: OwnedAsyncValkeyClient | None = getattr(app.state, "valkey", None)
        if valkey is not None:
            await valkey.aclose()
        # `ValkeyClient` declares no close, deliberately; the object that built it holds one.
        for held in ("answer_client", "knowledge_cache_client"):
            close_held = getattr(getattr(app.state, held, None), "close", None)
            if callable(close_held):
                close_held()
        console_reads = getattr(app.state, "console_reads", None)
        if console_reads is not None:
            await console_reads.close()
        store = getattr(app.state, "object_store", None)
        close_store = getattr(getattr(store, "backend", None), "close", None)
        if callable(close_store):
            close_store()
        # Before the engine goes, so what is waiting is written. See `brain.ops.log_store`.
        await stop_log_store(getattr(app.state, "log_store", None))
        await dispose(getattr(app.state, "db_engine", None))


def vault_at_start(address: str, token: str) -> OpenBaoVault | None:
    """The application's OpenBao client, or None when no vault is named or its address is not a
    URL. Never raises: a wrong address is readiness's `vault` part saying not ready, not a process
    that will not start. Constructing one asks the vault nothing."""
    if not address or not token:
        return None
    try:
        return OpenBaoVault(address, token, role=VaultRole.APPLICATION)
    except ValueError:
        return None


def key_set_client() -> httpx.Client:
    """The HTTP client the realm's key set is fetched through, owned by the lifespan.

    A function so a test can hand the lifespan a client over a mock transport and still have the
    lifespan be what closes it. Configured with nothing: `keycloak_tokens.http_get` passes the
    timeout and refuses redirects on every request, so a setting here would be a second place
    for either.
    """
    return httpx.Client()


def wall_clock() -> datetime:
    """The instant a key set is fetched at. The realm's keys are judged against real time."""
    return datetime.now(UTC)


def entitlement_cache_for(client: AsyncValkeyClient | None) -> EntitlementCache:
    """The cache `resolve` reads: Valkey when one is configured, and one holding nothing when not.

    See `brain.cache.AN_ABSENT_CACHE_IS_A_MISS_AND_NEVER_AN_ANSWER`.
    """
    if client is None:
        return NoEntitlementCache()
    return ValkeyEntitlementCache(client)


def wirings_for(
    sessions: async_sessionmaker[AsyncSession],
    *,
    get: Callable[[str], bytes],
    cache: EntitlementCache,
    clock: Callable[[], datetime],
    env: Mapping[str, str] | None = None,
) -> tuple[GateWiring, AutomationWiring] | None:
    """Both wirings over one set of sessions, or None when no token could ever be checked.

    Both or neither: `brain.automation_routes.calling_automation` reads the gate wiring as well
    as its own, so an automation wiring beside a missing gate would be a route that refuses for
    a reason nobody could see. None is logged with the reason, which names the setting and never
    a secret. See `AN_INSTALL_THAT_CANNOT_CHECK_A_SIGN_IN_IS_UNREADY_RATHER_THAN_STOPPED`.

    `env` is for tests. A deployed process passes nothing, and `brain.install` reads the issuer.
    """
    try:
        authority = keycloak_authority(
            directory=StoredDirectory(sessions),
            get=get,
            clock=clock,
            env=env,
            # Each interactive sign-in's groups, applied through the rules on the Roles screen.
            # See `brain.identity.group_sync`.
            memberships=GroupSync(StoredGroupRules(sessions), trace=trace_of_request),
        )
    except (InstallError, IdentityError) as exc:
        log.error("sign-in is not configured, so nothing behind it will answer", error=str(exc))
        return None
    gate = GateWiring(
        authority=authority,
        versions=PostgresVersionSource(sessions),
        store=StoredEntitlements(sessions),
        cache=cache,
    )
    automation = AutomationWiring(
        registrations=StoredAutomations(sessions), principals=StoredPrincipals(sessions)
    )
    return gate, automation


async def prime_keys(authority: TokenAuthority, clock: Callable[[], datetime]) -> bool:
    """Fetch the realm's key set once, off the event loop. True when it was fetched.

    On a worker thread, for the reason `bearer.A_KEY_FETCH_NEVER_HOLDS_THE_EVENT_LOOP` gives: the
    fetch blocks for up to its timeout, and the lifespan runs on the loop every request shares.
    The log names the exception class only.
    """
    try:
        await asyncio.to_thread(authority.keys.keys_for, authority.issuer, clock())
    except Exception as exc:
        log.warning("realm keys unavailable", issuer=authority.issuer, error=type(exc).__name__)
        return False
    log.info("realm keys fetched", issuer=authority.issuer)
    return True


async def sign_in_answers(
    authority: TokenAuthority, get: Callable[[str], bytes], clock: Callable[[], datetime]
) -> bool:
    """The key set is read and the issuer answers as itself, now. Off the event loop.

    See `brain.readiness.SIGN_IN_IS_TRUE_ONLY_WHILE_THE_ISSUER_ANSWERS_AS_ITSELF`.
    """
    if not await prime_keys(authority, clock):
        return False
    return await asyncio.to_thread(issuer_answers, get, authority.issuer)


async def keep_watching(
    authority: TokenAuthority,
    get: Callable[[str], bytes],
    ready: MutableMapping[str, bool],
    clock: Callable[[], datetime],
    *,
    answered: bool,
) -> None:
    """Ask whether sign-in answers for as long as the process runs, and say so each time.

    Soon and then less often while it does not answer, which is
    `AN_IDENTITY_PROVIDER_NOT_YET_ANSWERING_IS_ASKED_AGAIN`; once a minute while it does, so an
    issuer that stops answering is reported. The waits are read from the module on every pass, so
    a test can shorten them.
    """
    delay = KEY_PRIMING_MAX_RETRY_SECONDS if answered else KEY_PRIMING_FIRST_RETRY_SECONDS
    while True:
        await asyncio.sleep(delay)
        answered = await sign_in_answers(authority, get, clock)
        ready[SIGN_IN_CHECK] = answered
        if answered:
            delay = KEY_PRIMING_MAX_RETRY_SECONDS
        else:
            delay = min(delay * 2, KEY_PRIMING_MAX_RETRY_SECONDS)


def request_recorders_for(
    sessions: async_sessionmaker[AsyncSession] | None,
    *,
    environment: str,
    ship: Callable[[str, Sequence[Step]], None] | None = None,
) -> tuple[RequestRecorder, ...]:
    """What a finished request is recorded to on this process. See `brain.gate.finish`.

    The question recorder, the metadata ledger's recorder and the recorder of questions no
    connected source covers when there is a database, all bound to its sessions, and nothing when
    there is not. A process
    with no database has nowhere to keep a record and nowhere an adoption report could read
    one back from, so an in-memory recorder there would be a count that vanishes on restart
    and that no reader can reach. A function rather than two lines in `lifespan`, so which
    recorders a wired process installs is a claim a test can hold.
    """
    if sessions is None:
        return ()
    # The sensitive read recorder before the trace: it raises on a failed write, and the
    # measurements before it catch their own. See `brain.ops.sensitive_read_store`. The usage
    # recorder writes a request's cost and its skill uses (M27.12.5, M27.15.9), and catches its own
    # failures. The trace recorder writes the run's graph, masked, and catches its own (M24.3.4).
    return (
        QuestionRecorder(sessions),
        TelemetryRecorder(sessions),
        GapRecorder(sessions),
        UsageRecorder(sessions),
        SensitiveReadRecorder(sessions),
        TraceRecorder(sessions, environment=environment, ship=ship),
    )


def agent_roster_for(
    sessions: async_sessionmaker[AsyncSession] | None,
) -> AgentRoster | None:
    """How `/answer` reads the stored agents, or None on a process with no database.

    Every agent, as the Agents screen reads them; `brain.gate.roster.answer_roster` keeps the ones
    the person asking may run. A row that does not construct is left out, for
    `brain.agent_routes.record_of`'s reason.
    """
    if sessions is None:
        return None
    factory = sessions

    async def read() -> Sequence[AgentRecord]:
        async with factory() as session:
            rows = (await session.execute(every_agent())).scalars().all()
        return [one for one in (record_of(row) for row in rows) if one is not None]

    return read


def suspension_store_for(
    sessions: async_sessionmaker[AsyncSession] | None,
) -> StoredSuspensions | None:
    """What `app.state.suspensions` holds on this process. See `brain.approval_routes`.

    The store when there is a database, and nothing without one. The store needs nothing else,
    because the ledger entry a decision leaves is written by `gate.suspension`'s own trigger in
    the transaction that decides the row (`0083`), so it survives a restart exactly as the row
    does. A process without a database answers every approvals route in
    `brain.approval_routes.APPROVALS_ARE_NOT_KEPT_ON_THIS_PROCESS`.

    **This asked for a ledger writer as well until 2026-09-17, and none existed.** The only writer
    in the process was `brain.audit.ledger.AuditChain`, which a restart empties, so the lifespan
    passed none: first nothing was built and the Approvals screen answered every person on a
    staging install with a 500, then the reads were served and every decision was refused in
    words. This docstring said a writer for `obs.audit_entry` would arrive and be passed here. It
    was the wrong fix to wait for, because every persisted entry is written by a trigger on a row,
    and the parameter is gone rather than given a value.
    """
    if sessions is None:
        return None
    return StoredSuspensions(sessions)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    in_production = settings.env == "production"
    app = FastAPI(
        # The client's own, not ours. `brain.install` is the only reader; a literal here is a
        # product wearing one deployment's name, and it is the first thing an API consumer
        # sees. See `docs/repository-map.md`.
        title=installed_name(),
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if in_production else "/docs",
        # Turning off `/docs` without turning off `/openapi.json` closes the reading room
        # and leaves the catalogue on the doorstep. Production served the complete schema
        # unauthenticated: fourteen paths, every operation, every response model's field
        # names, and no security scheme described. `/docs` was correctly 404 the whole
        # time, which is what made it look handled.
        #
        # Nothing sensitive was behind those paths yet, because no route is behind the gate
        # yet. That is luck rather than design: the schema is generated from whatever is
        # mounted, so the first real endpoint would have published itself.
        openapi_url=None if in_production else "/openapi.json",
        redoc_url=None if in_production else "/redoc",
    )
    app.state.settings = settings
    app.state.ready = {}
    app.state.reported = {}
    app.state.readings = Readings()
    # Set to None rather than left unset, so "this process has no gate wiring" is a value a
    # route reads rather than an AttributeError it recovers from. `lifespan` builds it through
    # `wirings_for` when there is a database and an issuer: `keycloak_tokens.verify_rs256` is the
    # verifier, `StoredDirectory` finds the principal, and the entitlement store, version source
    # and cache sit beside them. Until then, and for good on a process with no database or no
    # issuer, every route under `API_PREFIX` refuses, which is what a missing authenticator has to
    # mean.
    app.state.gate = None
    # The same, for the sign-in bindings store `brain.sign_in_routes` reads. Built beside `gate`
    # in `lifespan`, because it writes at the issuer the gate validates against, and a process
    # without it refuses both routes alike.
    app.state.sign_in_bindings = None
    # The same, for the first administrator store `brain.setup_routes` appoints through. Built
    # beside `sign_in_bindings` in `lifespan`, so the appointment is offered only where the
    # finishing screen that follows it is.
    app.state.first_administrators = None
    # The same, for where approvals are read from and decided. See `suspension_store_for`.
    app.state.suspensions = None
    # The same, for where the autonomy breaker reads takeovers. Built beside `suspensions`.
    app.state.takeovers = None
    # The same, for an automation's registration and its owner's standing. Built beside `gate`
    # and never without it: see `wirings_for`.
    app.state.automation = None
    # The same, for where a credential is kept. `lifespan` builds it from the vault settings, and
    # a route reading None answers as an install with no vault. See `brain.credential_routes`.
    app.state.credentials = None
    # The same, for where a webhook subscriber's signing secret is kept. See `brain.webhook_routes`.
    app.state.signing_secrets = None
    # The same, for this install's template signing key and whether it is held. `lifespan` reads it
    # from the vault; a process that never did holds none, and every agent route says so. See
    # `brain.ops.template_key`.
    app.state.template_key = None
    app.state.template_key_state = TemplateKeyState.NO_VAULT
    # The same, for the object store and what is built over it: the backup bucket's reader and the
    # artifact store. A route reading None answers that nothing here looked. See
    # `brain.ops.object_store`.
    app.state.object_store = None
    app.state.backup_objects = None
    app.state.artifacts = None
    app.state.artifact_source = None

    # Registered first, which makes it innermost: Starlette inserts each new middleware at
    # the front of the stack, so the last one registered runs outermost. Inside `trace`
    # means the trace id is bound when a deadline fires, so the body of a timed-out response
    # carries the same id as the log line that recorded it.
    #
    # **Attached at all, which it was not until today.** `api.TimeoutMiddleware` existed,
    # was tested, and was mounted by nothing, so every request this application has ever
    # served ran without a deadline while M31.1.2.4 was closed and `request_timeout_seconds`
    # sat at 30.0 read by nobody. Behind a pooler with a fixed number of client slots, enough
    # held connections is an outage, which is the failure it was written to prevent.
    app.middleware("http")(TimeoutMiddleware(seconds=settings.request_timeout_seconds))

    # See CORS_ADMITS_THE_CONSOLE_AND_THE_WIDGET_AND_NOTHING_ELSE. `allowed_origins` raises on a
    # wildcard or a value that is not an origin; `brain.config.check` refuses both before this.
    admitted = allowed_origins((*settings.cors_origins, *settings.widget_origins))
    if admitted:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=sorted(admitted),
            allow_credentials=True,
            allow_methods=list(CORS_METHODS),
            allow_headers=list(CORS_HEADERS),
        )

    @app.middleware("http")
    async def trace(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """A trace id is minted before anything else runs, including identification.

        It has to exist before we know who is asking, or a request that fails during
        identification would have no id and could not be found in the ledger afterwards.

        **A caller may propose one and may not choose one.** `x-trace-id` is on the CORS
        allow list because correlating a request across a caller's own systems is a real
        thing to want. Until 2026-09-07 whatever arrived in that header was taken verbatim,
        bound to the log context for every line of the request, echoed back in the response
        and returned in `ErrorBody.trace_id`, with nothing checking it at all.

        That is not untidiness. `brain.audit.ledger.AuditEntry.trace_id` is pattern-validated
        to sixty-four characters of `[A-Za-z0-9_.-]`, so a caller sending anything outside
        that grammar chose an id under which **no audit entry for their own request can ever
        be written**. Making your own request unauditable should not be a header. The same
        value also reached the structured log unescaped, where a newline is a second log line
        somebody else wrote.

        So the header is accepted only when it satisfies the ledger's own grammar, imported
        rather than restated, and anything else is replaced by a minted id rather than
        rejected: refusing the request would turn a malformed header into an outage, and the
        caller loses nothing they were entitled to.

        `supplied` is bound alongside, because an id the caller chose is not evidence of
        anything. Two requests can carry one id if two callers pick the same string, and an
        auditor reading a trail needs to know which ids this system vouches for.
        """
        proposed = request.headers.get("x-trace-id") or ""
        supplied = bool(TRACE_ID_RE.fullmatch(proposed))
        trace_id = proposed if supplied else uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id, path=request.url.path, trace_id_supplied=supplied
        )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Caught here, inside the binding, rather than by an `Exception` handler: Starlette
            # runs that handler outermost, after this `finally` has cleared the trace id, and it
            # answered plain text with no reference. The traceback goes to the log under this
            # request's id; the body carries the id and a sentence. See
            # `brain.api.A_FAILURE_WITHOUT_A_SENTENCE_IS_A_FAILURE_NOBODY_CAN_REPORT`.
            log.exception("request raised and nothing handled it")
            response = unexpected_failure(trace_id)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["x-trace-id"] = trace_id
        response.headers["server-timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
        return response

    # Outside `trace`, which is registered just above and so sits inside this: a failing JSON
    # answer a route wrote for itself leaves `trace` with its `x-trace-id` set, and is given that
    # reference and a sentence here if it has neither. See `brain.api.FailureBodyMiddleware`.
    app.add_middleware(FailureBodyMiddleware)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        return response

    @app.exception_handler(BrainError)
    async def handle_brain_error(request: Request, exc: BrainError) -> JSONResponse:
        """Maps the taxonomy to a response, and is the only place an error becomes text.

        DENIED and ABSENT both leave here as 404 with the same body. A 403 on a hidden
        record would confirm the record exists, which is the leak the taxonomy exists to
        prevent.

        **The body is `api.ErrorBody`, and it used not to be.** That model calls itself "the
        only error shape, documented once and returned by everything" and this handler
        returned a bare dict, so the documented shape and the real one had never met. Two
        costs, and neither was hypothetical: the trace id was reachable only by a caller who
        knew to read a response header, so "quote this and the run can be found" was untrue
        of the thing a person is actually shown; and no endpoint declared the model, so the
        generated OpenAPI described no error shape at all and the console's typed client was
        typed against nothing.

        The trace id comes from the contextvar the `trace` middleware binds before anything
        else runs, which is the same value that middleware puts in `x-trace-id`. Read rather
        than minted here, so the body and the header cannot disagree, and defaulted to empty
        rather than invented if the middleware has not run.
        """
        status = {
            Outcome.DENIED: 404,
            Outcome.ABSENT: 404,
            Outcome.UNRESOLVED: 409,
            Outcome.DEGRADED: 503,
            Outcome.FAILED: 500,
        }[exc.outcome]
        log.warning("request failed", outcome=exc.outcome, detail=exc.detail)
        bound = structlog.contextvars.get_contextvars()
        # Read off the request, where `brain.api_routes.asking` put it before the route read
        # anything, so it is the same for every object this session asks about. See
        # `brain.gate.admission.A_REFUSAL_TO_A_WEAK_SIGN_IN_IS_ABOUT_THE_SESSION`.
        weak = exc.outcome in {Outcome.DENIED, Outcome.ABSENT} and second_factor_needed(request)
        body = ErrorBody(
            message=SECOND_FACTOR_NEEDED_MESSAGE if weak else to_public(exc),
            trace_id=str(bound.get("trace_id", "")),
            second_factor_needed=weak,
        )
        return JSONResponse(status_code=status, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def handle_refused_request(request: Request, exc: RequestValidationError) -> Response:
        """A body, query or path the route's model refused, as `ErrorBody` with its problems.

        FastAPI's own answer was `{"detail": [...]}`, which quoted every refused value and carried
        no `message`, so the console showed "Something went wrong." beside a form it could not
        mark. See `brain.api.A_REFUSED_BODY_IS_NOT_ECHOED`.
        """
        log.info("request refused before the route ran", path=request.url.path)
        return refused_request(exc.errors(), bound_trace_id(request))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        """An address or a method nothing serves, in a sentence, with the reference.

        A 404 says what `Absent` says, so an address that does not exist and a record that is
        refused are one answer; a 405 keeps its `Allow` header. The framework's `detail` is not
        used, because a route that raised one could have put anything in it.
        """
        message = (
            to_public(Absent()) if exc.status_code == 404 else status_sentence(exc.status_code)
        )
        body = ErrorBody(message=message, trace_id=bound_trace_id(request))
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(),
            headers=dict(exc.headers or {}),
        )

    @app.exception_handler(TokenRefusedError)
    async def handle_token_refused(request: Request, exc: TokenRefusedError) -> JSONResponse:
        """A credential that was not acceptable, in one sentence, whatever was wrong with it.

        Beside `handle_brain_error` rather than inside it, because the two answer different
        questions. That one maps an outcome of a question that was asked; this fires before
        any question exists, so there is no outcome to map and nothing about what exists to
        give away. Both return `api.ErrorBody`, so a client parses one shape.

        The reason is a closed enumeration and it goes to the log only. Telling the presenter
        that the key was unknown rather than the signature bad tells somebody forging a token
        which part to fix next, one attempt at a time. See
        `brain.identity.bearer.EVERY_REFUSAL_SAYS_THE_SAME_SENTENCE`.
        """
        log_refusal(exc, path=request.url.path)
        bound = structlog.contextvars.get_contextvars()
        body = ErrorBody(message=SIGN_IN_PROMPT, trace_id=str(bound.get("trace_id", "")))
        return JSONResponse(
            status_code=401, content=body.model_dump(), headers=dict(refusal_headers())
        )

    # The console, in two halves, and the order of the two calls is the whole of the design.
    # This one claims the root before `docs_router` registers its own `/`, because Starlette
    # takes the first route that matches; the other is at the bottom of this function. It
    # claims the root only when this tree carries a built bundle, so an image without one
    # keeps the build tracker's landing page and every behaviour it had. The runtime
    # configuration document is registered either way, because `npm run dev` proxies `/api`
    # to an application running from a checkout and a console that cannot read its issuer
    # cannot sign anybody in. These two lines are the only change in this file.
    # See `brain.console_static` for the argument for one image rather than two.
    mount_console_entry(app)

    app.include_router(docs_router)
    # Every other router, each one import line in `brain.routers` and mounted in the order of
    # their names, which is safe because no two of them answer one address: see that module.
    for router in ROUTERS:
        app.include_router(router)

    @app.get("/health/live", response_model=Health, tags=["health"])
    async def live() -> Health:
        """The process is running. Says nothing about whether it can answer anything."""
        return Health(status="ok", commit=settings.resolved_commit())

    @app.get("/health/ready", response_model=Health, tags=["health"])
    async def ready(request: Request, response: Response) -> Health:
        """Every dependency is reachable. Deployment gates on this, not on liveness.

        `checks` decide the status; `reported` are named beside them and decide nothing. See
        `SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS`. The application is the request's,
        never the enclosing `app`: see `AN_ENDPOINT_NEVER_CLOSES_OVER_ITS_APPLICATION`.
        """
        state = request.app.state
        await state.readings.refresh(state.ready)
        checks: dict[str, bool] = dict(state.ready)
        reported: dict[str, bool] = dict(getattr(state, "reported", {}))
        ok = all(checks.values()) if checks else True
        if not ok:
            response.status_code = 503
        return Health(
            status="ok" if ok else "degraded",
            commit=settings.resolved_commit(),
            checks=checks,
            reported=reported,
            parts=parts_of(checks, reported),
        )

    # The console's other half: the handler Starlette calls once the whole routing table has
    # been tried and nothing matched. It replaces `app.router.default` rather than registering
    # a route, and the difference is a method rather than a path: a catch-all route is a full
    # match for every GET, which beats the partial match that would have answered 405, so it
    # turned `GET /api/v1/answer?question=...` from refused into answered. Last, and not a
    # route: see `THE_FALLBACK_IS_REGISTERED_LAST_SO_IT_CANNOT_SHADOW_A_ROUTE`.
    mount_console_fallback(app)

    return app


app = create_app()
