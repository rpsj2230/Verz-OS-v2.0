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

from brain.access_request_routes import router as access_request_router
from brain.agent_about_routes import router as agent_about_router
from brain.agent_model_routes import router as agent_model_router
from brain.agent_routes import every_agent, record_of
from brain.agent_routes import router as agent_router
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
from brain.api_routes import router as api_router
from brain.approval_routes import router as approval_router
from brain.artifact_routes import router as artifact_router
from brain.attribution import trace_of_request
from brain.audit.ledger import TRACE_ID
from brain.audit_routes import router as audit_router
from brain.automation_gallery_routes import router as automation_gallery_router
from brain.automation_routes import AutomationWiring
from brain.automation_routes import router as automation_router
from brain.automation_schedule_routes import router as automation_schedule_router
from brain.cache import (
    AsyncValkeyClient,
    NoEntitlementCache,
    OwnedAsyncValkeyClient,
    PostgresVersionSource,
    ValkeyAnswerStore,
    ValkeyEntitlementCache,
    check_reachable_async,
    make_async_client,
    make_client,
)
from brain.channels.widget import allowed_origins
from brain.classification_routes import router as classification_router
from brain.compliance_routes import router as compliance_router
from brain.connector_routes import router as connector_router
from brain.console_static import mount_console_entry, mount_console_fallback
from brain.core.errors import Absent, BrainError, Outcome, to_public
from brain.credential_routes import router as credential_router
from brain.data_steward_routes import router as data_steward_router
from brain.data_transfer_routes import router as data_transfer_router
from brain.docs_routes import router as docs_router
from brain.erasure_routes import router as erasure_router
from brain.error_routes import router as error_router
from brain.estate_routes import router as estate_router
from brain.feature_routes import router as feature_router
from brain.firstrun import GRANTED_BY
from brain.gate.admission import SECOND_FACTOR_NEEDED_MESSAGE
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.finish import RequestRecorder
from brain.gate.resolve import EntitlementCache
from brain.gate.roster import AgentRoster
from brain.gate.rule_store import load_rules, rule_ids
from brain.gate.suspension_store import StoredSuspensions
from brain.govern_pack_routes import router as govern_pack_router
from brain.govern_people_routes import router as govern_people_router
from brain.govern_role_routes import router as govern_role_router
from brain.govern_routes import router as govern_router
from brain.group_rule_routes import router as group_rule_router
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
from brain.install_routes import router as install_router
from brain.jobs_routes import router as jobs_router
from brain.knowledge.row_store import SessionRowSource
from brain.lark_connect_routes import router as lark_connect_router
from brain.log_routes import router as log_router
from brain.migrate import run_migrations
from brain.mine_routes import router as mine_router
from brain.model_health_routes import router as model_health_router
from brain.models.default_ladder import reconcile as reconcile_default_ladder
from brain.navigation_routes import router as navigation_router
from brain.notification_routes import router as notification_router
from brain.operate_routes import router as operate_router
from brain.ops.artifact_store import artifacts_for
from brain.ops.automation_owner_store import StoredAutomations
from brain.ops.credential_write_store import credential_writes_for
from brain.ops.credentials import credentials_at_start, keep_refreshing
from brain.ops.default_ladder_store import SessionLadderWriter
from brain.ops.install_settings import refresh as refresh_install_settings
from brain.ops.log_store import start_log_store, stop_log_store
from brain.ops.matrix_gate_run import InstallMatrixGate
from brain.ops.model_service import (
    ModelService,
    held_providers,
    model_service_at_start,
)
from brain.ops.object_store import backup_objects, object_store_at_start
from brain.ops.openbao import OpenBaoVault
from brain.ops.question_gap_store import GapRecorder
from brain.ops.question_store import QuestionRecorder
from brain.ops.replica_store import console_reads_for
from brain.ops.secrets import VaultRole
from brain.ops.sensitive_read_store import SensitiveReadRecorder
from brain.ops.starter_store import furnish as furnish_install
from brain.ops.telemetry_store import TelemetryRecorder
from brain.ops.trace_sink import CountingTraceSink
from brain.ops.vault_renewal import keep_renewing, renewer_at_start
from brain.ops.webhook_admin import signing_secrets_at_start
from brain.principal_state_routes import router as principal_state_router
from brain.prompt_routes import router as prompt_router
from brain.provider_registry_routes import router as provider_registry_router
from brain.provider_routes import router as provider_router
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
from brain.record_access_routes import router as record_access_router
from brain.report_routes import router as report_router
from brain.requirement_check_routes import router as requirement_check_router
from brain.retention_routes import router as retention_router
from brain.routing_routes import router as routing_router
from brain.service_account_routes import router as service_account_router
from brain.session import (
    check_login_row_security,
    check_reachable,
    check_row_security,
    dispose,
    make_app_engine,
    make_application_sessions,
)
from brain.session_routes import router as session_router

# Re-exported, because tests, `console/scripts/export-openapi.py` and `brain.serve`'s history all
# import it from here. It is defined in `brain.settings`, which builds nothing when imported; a
# process that needs a setting and not the application imports that instead. See
# `brain.settings.SETTINGS_ARE_READ_WITHOUT_BUILDING_THE_APPLICATION`.
from brain.settings import Settings as Settings
from brain.settings_routes import router as settings_router
from brain.setup_routes import router as setup_router
from brain.setup_staff_routes import router as setup_staff_router
from brain.sign_in_routes import router as sign_in_router
from brain.skill_routes import router as skill_router
from brain.staff_source_routes import router as staff_source_router
from brain.storage_routes import router as storage_router
from brain.tools.startup import build_registry
from brain.vault_routes import router as vault_router
from brain.webhook_routes import router as webhook_router

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
CORS_METHODS: Final = ("GET", "POST", "PUT", "PATCH")
CORS_HEADERS: Final = ("authorization", "content-type", "x-trace-id")

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
    app.state.tools = build_registry(source=settings.tool_source, records=records)
    app.state.ready["tools"] = True
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
    # The rules are read once. A rule set fetched per request would put a database round trip
    # in front of the lane whose entire purpose is answering without one, and refreshing on a
    # timer would give two answers to one question inside a minute with nothing saying which
    # rule set produced either. So a rule added or retired takes effect at the next restart,
    # and the count below is where somebody wondering why their new rule does nothing finds
    # out. See `rule_store.A_RULE_SET_THAT_CHANGES_MID_FLIGHT_GIVES_TWO_ANSWERS_TO_ONE_QUESTION`.
    #
    # The sink records that a trace happened and drops the payload, because the only
    # destination available today is the application log and a post-redaction payload there is
    # readable by whoever can read logs, which is not who could read the records. See
    # `trace_sink.THE_LOG_IS_NOT_A_TRACE_STORE`. It is installed unconditionally, unlike the
    # rules, because a lane with no sink cannot compose at all.
    app.state.trace_sink = CountingTraceSink()
    app.state.request_recorders = request_recorders_for(app.state.db_sessions)
    # The stored agents `/answer` may select from, read once per question (M3.9.8).
    app.state.agent_roster = agent_roster_for(app.state.db_sessions)
    # The model driver, assembled once over this install's database: a driver per provider this
    # product can reach, sharing one HTTP client this lifespan closes. Which rungs answer is read
    # per call from the ladder, the provider switches and the keys this process holds, so a
    # switch or a key saved from the console takes effect without a restart. See
    # `brain.ops.model_service` and `brain.models.assembly`.
    app.state.models = model_service_at_start(app.state.db_sessions)
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
    # Approvals are read and decided on the database, whose trigger keeps each decision's ledger
    # entry. See `suspension_store_for`.
    app.state.suspensions = suspension_store_for(app.state.db_sessions)
    app.state.fast_path_rules = ()
    if app.state.db_sessions:
        try:
            app.state.fast_path_rules = await load_rules(app.state.db_sessions)
        except Exception as exc:
            # A rule table that cannot be read is an empty rule set, not a dead process. The
            # lane abstains for every question, which is the same answer it gives when no rule
            # matches, and the log line says which of the two this is. Refusing to start would
            # take down `/records` and `/me` as well, over configuration that only one route
            # reads.
            log.warning("fast path rules unavailable", error=type(exc).__name__)
    log.info(
        "fast path rules loaded",
        rules=len(app.state.fast_path_rules),
        ids=rule_ids(app.state.fast_path_rules),
        refreshes="on restart",
    )

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
        close_answers = getattr(getattr(app.state, "answer_client", None), "close", None)
        if callable(close_answers):
            close_answers()
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
    # The sensitive read recorder last: it raises on a failed write, and the measurements before
    # it catch their own. See `brain.ops.sensitive_read_store`.
    return (
        QuestionRecorder(sessions),
        TelemetryRecorder(sessions),
        GapRecorder(sessions),
        SensitiveReadRecorder(sessions),
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
    # The same, for an automation's registration and its owner's standing. Built beside `gate`
    # and never without it: see `wirings_for`.
    app.state.automation = None
    # The same, for where a credential is kept. `lifespan` builds it from the vault settings, and
    # a route reading None answers as an install with no vault. See `brain.credential_routes`.
    app.state.credentials = None
    # The same, for where a webhook subscriber's signing secret is kept. See `brain.webhook_routes`.
    app.state.signing_secrets = None
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
    # Mounted here and nowhere else. An unmounted router is the failure this repository keeps
    # finding, and the timeout middleware three paragraphs up is the most recent one.
    app.include_router(api_router)
    # Who can see a record, for somebody who can already see it. See `brain.record_access_routes`.
    app.include_router(record_access_router)
    # The routing matrix. A second router rather than more routes on the first, because the
    # rules differ: `api_routes` answers about entities, where the name itself is enumerable,
    # and this one answers about the model chain, where it is not. Both take the same
    # `asking` dependency, which `api_routes` declares once and this imports.
    app.include_router(routing_router)
    # Field-level classification. A third router for the reason there is a second: the rules
    # differ again. This one answers about the policy over a document's columns rather than
    # about its rows, it takes no session because there is nothing stored to read, and its
    # write verb is `admin` rather than `write` because what it governs is what other people
    # may see. The same `asking` dependency, imported rather than re-declared.
    app.include_router(classification_router)
    # The agent roster and one agent's workspace. A fourth router because the refusal differs
    # again: who may see an agent is its audience rather than a capability, and a hidden agent
    # and a missing one are one answer. The same `asking` dependency, imported.
    app.include_router(agent_router)
    # One agent's About tab, which reads the agent's automations and so cannot sit on the
    # workspace's router without an import cycle. The same audience and the same one 404.
    app.include_router(agent_about_router)
    # The approvals queue and one approval's card. A fifth router because the refusal differs
    # again: who is offered an approval is `pending_for` over the action's own row, and an
    # approval out of reach, decided, lapsed or missing is one answer. GET only; see the module.
    app.include_router(approval_router)
    # The endpoint an automation step calls. A sixth router because the caller differs: it
    # authenticates an automation's credential rather than a person's token, and runs as the
    # automation's owner. It does not take `asking`, and `asking` does not take its credential.
    app.include_router(automation_router)
    # The automation gallery on an agent's Automations tab, and its one confirmed install. Its own
    # router because the write is: an `admin:` authority asked before the agent is read, a
    # confirmation recomputed on the server, and a row whose trigger writes the ledger entry.
    app.include_router(automation_gallery_router)
    # An agent's installed automations, their runs, and the confirmed start and stop. Its own
    # router for the gallery's reason: an authority asked before anything is read, a confirmation
    # recomputed on the server, and a row whose trigger writes the ledger entry.
    app.include_router(automation_schedule_router)
    # Binding a Keycloak subject to a principal. A seventh router because it has two callers:
    # an administrator over everything under the prefix, through `asking`, and the setup
    # wizard's finishing screen at /setup/sign-in, which takes the setup code and a verified
    # token and no `asking`, and closes once anybody signs in. See `brain.sign_in_routes`.
    app.include_router(sign_in_router)
    # The setup wizard's appointment, which runs `apply_install` and appoints the first
    # administrator the finishing screen above then signs in. An eighth router because its caller
    # holds the setup code and no token at all. See `brain.setup_routes`.
    app.include_router(setup_router)
    # The wizard's staff list screen: what to register, where to sign in, and one read of the
    # list, each behind the setup code the appointment asks for. See `brain.setup_staff_routes`.
    app.include_router(setup_staff_router)
    # Setting a credential, and seeing which are held. Beside the wizard because the wizard's
    # provider key is kept through the same store, and a router of its own because its subject is
    # the one value no other route may carry: it writes into the vault, answers that a secret is
    # held and when, and is built on `brain.api.NoEchoRoute` so not even a refused body is
    # repeated. See `brain.credential_routes`.
    app.include_router(credential_router)
    # The Secrets vault screen: the seal, every slot, each source's leases and the audit log's
    # shipping. Read only, under the credentials route's capability. See `brain.vault_routes`.
    app.include_router(vault_router)
    # The Requirement checks screen: the register's rows by area and what a person saw each do on
    # this install, recorded. See `brain.requirement_check_routes`.
    app.include_router(requirement_check_router)
    # The five install screens. A ninth router because what it answers about is the deployment
    # rather than the company's data: no name to guess, no row belonging to anybody, and no
    # session on four of the five. The same `asking` dependency, imported. See
    # `brain.install_routes`.
    app.include_router(install_router)
    # The three Report screens: service levels, spend and adoption. A router of its own because
    # the decision differs again and in the opposite direction to the matrix's: none of these
    # checks a capability at all, because the module that owns each screen narrows it row by
    # row and a check here would be the first half of that predicate in a second copy. See
    # `brain.report_routes`.
    app.include_router(report_router)
    # The retention report and the four writes that decide whether the sweep acts. A router of
    # its own because two of its writes are the only way a deletion is approved or suspended:
    # every write needs its authority over everything, and the report is shown whole to a
    # company-wide reader and to nobody else. See `brain.retention_routes`.
    app.include_router(retention_router)
    # What the Retention screen needs beside the report: who may act, what each act does in the
    # words a confirmation shows, the export log, and the erasure queue with its one write, which
    # files a request the worker's queue carries out. See `brain.erasure_routes`.
    app.include_router(erasure_router)
    # The Artifacts screen. A list only when something attached records what an agent produced,
    # and a sentence saying nothing does until then. See `brain.artifact_routes`.
    app.include_router(artifact_router)
    # My workspace, the member screen `home`: what the person asking has asked, kept and been
    # given, gated on the member grant and on nothing administrative. See `brain.mine_routes`.
    app.include_router(mine_router)
    # The four Govern screens, and the two writes over a grant. A router of its own because
    # what it answers about is the permission system itself: whether a screen opens is
    # `brain.console.reads.permitted` rather than a bare capability, so an existence-only
    # reader is refused a configuration screen, and the two writes defer entirely to
    # `brain.console.scoped_authority` and `brain.console.govern`. See `brain.govern_routes`.
    app.include_router(govern_router)
    # Assigning a capability pack, and the Approver misconfiguration flag on the Roles screen.
    # Every grant a pack means goes through the same authority a single grant does. See
    # `brain.govern_pack_routes`.
    app.include_router(govern_pack_router)
    # Who holds each role, and appointing, deputising and removing one. See
    # `brain.govern_role_routes`.
    app.include_router(govern_role_router)
    # Which identity-provider group confers which role, on the Roles screen, and what the sync
    # has written from them. See `brain.group_rule_routes`.
    app.include_router(group_rule_router)
    # The Skills screen, SCREEN 6 of `docs/screens.html`. A router of its own because what it
    # answers about is neither a grant nor an agent: it is the skill library, its review queue and
    # the procedures the agents a reader may see are pinned to. Its three writes add a skill,
    # decide about one as somebody other than who added it, and assign an approved one through
    # `attach_skill`, each asking its `admin:` authority first. See `brain.skill_routes`.
    app.include_router(skill_router)
    # The connectors screen. A router of its own because what it answers about is which outside
    # systems this company reads, where the name itself is the disclosure: the list is narrowed
    # by the reader's own grant and a refusal names nothing. Connecting and disconnecting a source
    # are its two writes, under `admin:connector` over that source, and what connecting does not do
    # yet is served beside the list. See `brain.connector_routes`.
    app.include_router(connector_router)
    # Connect Lark: the steps, a read-only test and switching its uses on. See
    # `brain.lark_connect_routes`.
    app.include_router(lark_connect_router)
    # The Staff sources screen and the trial run behind it. A router of its own because it
    # refuses nobody on its listing: a source sits at `brain.console.govern.NOWHERE`, so the
    # answer for a reader who reaches none of them is the empty page rather than the refusal
    # the four govern screens make, and refusing instead would let a caller read off whether
    # somebody else holds a capability. See `brain.staff_source_routes`.
    app.include_router(staff_source_router)
    # The Audit screen, the Govern section's last item in `docs/screens.html`. A router of its own
    # because what it reads is the ledger, where every row is decided one at a time by
    # `brain.audit.view.AuditView` and a page is filled from what survives. See
    # `brain.audit_routes`.
    app.include_router(audit_router)
    # Sessions and sign-in links, beside People in Govern, and the two controls that end a session
    # and unlink an account. See `brain.session_routes`.
    app.include_router(session_router)
    # The Knowledge, Learning and Memory screens. A router of its own because all three are the
    # estate-wide reads `brain.console.govern_estate` decides, and all three stand on a store
    # that is empty on every install today: each response says which of its facts has no source
    # rather than drawing an empty table that reads as a company with nothing in it. No write.
    # See `brain.estate_routes`.
    app.include_router(estate_router)
    # Live runs and Models and health, the two Operate screens `docs/screens.html` draws beside
    # the overview. A router of its own because its two refusals differ from every router above:
    # live runs narrows row by row and refuses nobody, and the models answer is whole-install and
    # refuses a reader who could not see everybody's. See `brain.operate_routes`.
    app.include_router(operate_router)
    # Models and providers: every provider this install can call, switched on and off behind
    # `admin:routing_matrix` over everything, the ladder as the next call will walk it with each
    # rung's measured health, and a metered check. See `brain.provider_routes`.
    app.include_router(provider_router)
    # The provider registry: terms and lane overrides recorded, an OpenAI-compatible provider
    # added with its key written to the vault first, and the register exported. See
    # `brain.provider_registry_routes`.
    app.include_router(provider_registry_router)
    # An agent's pinned provider and model, tried before its tier. See `brain.agent_model_routes`.
    app.include_router(agent_model_router)
    # A tier's window and headroom, and residency constraints. See `brain.model_health_routes`.
    app.include_router(model_health_router)
    # Departments and teams, Elevation, Access review and Subscribers, beside People in Govern. A
    # router of its own because one of its four is the only write that records a review decision,
    # and two of its screens say what the install does not store rather than drawing an empty
    # list. See `brain.govern_people_routes`.
    app.include_router(govern_people_router)
    # Scheduled jobs beside Live runs: how each job last went, and pause, resume and run now as
    # rows the worker's tick reads. Read for everybody and narrowed per job; the controls need
    # `admin:schedule` over everything and the `schedule_control` feature. See `brain.jobs_routes`.
    app.include_router(jobs_router)
    # Errors: the failed jobs and failed requests the database keeps, each behind the decision
    # that already says who may see it, and a field saying the process log is kept nowhere the
    # console can read. See `brain.error_routes`.
    app.include_router(error_router)
    # Logs: the warnings and errors this install kept, redacted on their way in, searchable and
    # paged, behind `admin:application_log` over everything. See `brain.log_routes`.
    app.include_router(log_router)
    # Features: which genuinely new features this install has switched on, and the switch, behind
    # `admin:feature` over everything. See `brain.feature_routes` and `brain.ops.features`.
    app.include_router(feature_router)
    # Prompts: the system instructions every agent is given, shown and never edited, and each
    # agent's own instructions, edited as a local change to its template. See
    # `brain.prompt_routes`.
    app.include_router(prompt_router)
    # Webhooks: every subscriber, where it points, whether its signing secret is held and its
    # recent outcomes, and registering, replacing a secret and switching off behind
    # `admin:webhook_subscriber`. Built on `NoEchoRoute`, because two of its writes carry a
    # secret. See `brain.webhook_routes`.
    app.include_router(webhook_router)
    # Notifications: every notice this product composes, who is told what and whether anything
    # sends it, the switch that stops one, and the email relay with its password in the vault and
    # a test message, behind `admin:notification` over everything. See
    # `brain.notification_routes`.
    app.include_router(notification_router)
    # Storage: the buckets the product keeps, each one's retention and why, and where the store
    # is, behind `admin:storage` over everything. Never an object's name. See
    # `brain.storage_routes`.
    app.include_router(storage_router)
    # Settings, under Install: every installation value with where it came from, and branding
    # saved, behind `admin:install_setting` over everything. See `brain.settings_routes`.
    app.include_router(settings_router)
    # Import and export: what the code can move and whether an install can move it now, and the
    # audit trail export, recorded in the ledger before the document is handed over. See
    # `brain.data_transfer_routes`.
    app.include_router(data_transfer_router)
    # Which console a reader is given: the company console, or a department's with the menu
    # SCREEN 2 draws narrowed to what they hold. Decided from grants at the admitted reach, so
    # the shell renders an answer rather than a permission check of its own. See
    # `brain.navigation_routes`.
    app.include_router(navigation_router)
    # The data steward: who every read of the company's data begins with, and naming one on an
    # install whose setup named nobody, behind `admin:data_steward` over everything. See
    # `brain.data_steward_routes` and `brain.identity.data_steward`.
    app.include_router(data_steward_router)
    # Service accounts: an integration registered at its owner's reach, a key shown once, and both
    # taken away, behind `admin:credential`. See `brain.service_account_routes`.
    app.include_router(service_account_router)
    # Disabling a person and enabling them again, from the Departments and teams screen, behind the
    # grant decision in a scope admitting their row. See `brain.principal_state_routes`.
    app.include_router(principal_state_router)
    # Asking for access: one constant reply to the asker, and the owner's own list, which is how
    # a request is delivered. See `brain.access_request_routes`.
    app.include_router(access_request_router)
    # The Compliance screen: a sensitive topic's named person and the referrals routed to them, the
    # processing register per connector, and breach cases with the PDPA clock, behind
    # `admin:compliance` over everything. See `brain.compliance_routes`.
    app.include_router(compliance_router)

    @app.get("/health/live", response_model=Health, tags=["health"])
    async def live() -> Health:
        """The process is running. Says nothing about whether it can answer anything."""
        return Health(status="ok", commit=settings.resolved_commit())

    @app.get("/health/ready", response_model=Health, tags=["health"])
    async def ready(response: Response) -> Health:
        """Every dependency is reachable. Deployment gates on this, not on liveness.

        `checks` decide the status; `reported` are named beside them and decide nothing. See
        `SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS`.
        """
        await app.state.readings.refresh(app.state.ready)
        checks: dict[str, bool] = dict(app.state.ready)
        reported: dict[str, bool] = dict(getattr(app.state, "reported", {}))
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
