"""The providers screen over HTTP: what it answers, who may switch a provider, what a check does.

Driven through the real application with the token machinery and the directory borrowed from
`tests/unit/test_api_routes.py` and `tests/unit/test_agent_routes.py`, as
`tests/unit/test_operate_routes.py` does. The executor on `app.state.models` is the real
`brain.models.calls.ModelCalls` over a ladder, an attempt log and transports held in memory, and
the database the switch writes to is a stub that keeps `ops.setting` rows by key, so the switch
reaches the same ladder the next plan reads.

Task ids: M27.8.8, M27.2.3, M5.7.1
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import TextClause, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Insert

from brain import provider_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.scope import Scope
from brain.credential_routes import CREDENTIAL_AUTHORITY
from brain.gate.finish import Finished, ModelCallOutcome
from brain.identity.bearer import TokenAuthority
from brain.install import hold_saved, value_of
from brain.models.adapter import Completion, SdkDriver, TransportStatusError
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE, TOLD, LadderRung, RungSkip
from brain.models.calls import LadderState, ModelCalls
from brain.models.default_ladder import DEFAULT_MODELS, LOCAL_COMPLETION_MODEL
from brain.models.disclosure import TOLD as CATEGORY_TOLD
from brain.models.driver import DriverRequest, ModelDriver
from brain.models.evidence import Attempt
from brain.models.registry import ProviderKind, ProviderRecord
from brain.models.routing import Tier
from brain.ops.credentials import TOLD as VAULT_TOLD
from brain.ops.matrix_gate import GateVerdict
from brain.ops.model_service import (
    PROVIDER_NAMESPACE,
    ModelService,
    SessionAttempts,
    SessionLadder,
)
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.ops.telemetry_store import TelemetryRecorder
from brain.provider_routes import (
    CHECK_MAX_OUTPUT_TOKENS,
    CHECK_PROMPT,
    CHECK_TOLD,
    KEY_REFUSED_STATUSES,
    PROFILE_SETTING,
    answered_told,
    default_model_told,
    may_switch,
    refused_keys,
)
from brain.routing_routes import MATRIX_WRITE
from brain.settings_routes import INSTALL_SETTING_AUTHORITY
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.config import SettingType
from tests.fixtures.http_client import Response
from tests.fixtures.scratch_postgres import engine, modelled, run, sql
from tests.unit.test_agent_routes import Directory
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

PROVIDERS = f"{API_PREFIX}/models/providers"
PROFILE = f"{API_PREFIX}/models/profile"

#: The tables a rung save and a check touch, built from the models on a scratch server.
RUNG_TABLES = (
    "ops.routing_rung",
    "ops.model_attempt",
    "ops.setting",
    "ops.model_provider",
    "ops.routing_change",
    # Read with the ladder since 0108: the tier rows, the residency constraints, the rings.
    "ops.routing_tier",
    "ops.residency_constraint",
    "ops.provider_health",
)
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MODEL_READ = screen("models").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
EXISTENCE = plane_capability(Plane.EXISTENCE)
EVERYWHERE = Scope.unrestricted()

#: A session carrying a second factor, as a literal for the reason `test_routing_routes` gives: an
#: `admin:` verb is withheld from a password-only session, and every write here is one.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}

#: A reply no response may carry. If it appears in a body, the check returned what the model said.
REPLY = "REPLY-CANARY-7QX2P"


def grants(*held: tuple[Capability, Scope]) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=scope) for one, scope in held)


#: `u_admin` reads, switches, manages credentials and holds the installation settings, which is
#: the super administrator's authority. `u_wide` reads and switches. `u_narrow` reads.
#: `u_elsewhere` holds all of them scoped to one department. `u_prefix` holds read and write with
#: only the existence plane. `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": grants(
        (MODEL_READ, EVERYWHERE),
        (CONFIGURATION, EVERYWHERE),
        (MATRIX_WRITE, EVERYWHERE),
        (CREDENTIAL_AUTHORITY, EVERYWHERE),
        (INSTALL_SETTING_AUTHORITY, EVERYWHERE),
    ),
    "u_wide": grants(
        (MODEL_READ, EVERYWHERE), (CONFIGURATION, EVERYWHERE), (MATRIX_WRITE, EVERYWHERE)
    ),
    "u_narrow": grants((MODEL_READ, EVERYWHERE), (CONFIGURATION, EVERYWHERE)),
    "u_elsewhere": grants(
        (MODEL_READ, Scope.department("finance")),
        (CONFIGURATION, EVERYWHERE),
        (MATRIX_WRITE, Scope.department("finance")),
        (INSTALL_SETTING_AUTHORITY, Scope.department("finance")),
    ),
    "u_prefix": grants(
        (MODEL_READ, EVERYWHERE), (EXISTENCE, EVERYWHERE), (MATRIX_WRITE, EVERYWHERE)
    ),
    "u_none": (),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


# ------------------------------------------------------------------- the installed estate


def rung(provider: str, *, tier: Tier = Tier.MAIN, position: int = 0) -> LadderRung:
    return LadderRung(
        rung_id=f"{tier.value}-{position}",
        tier=tier,
        position=position,
        deployment_id=f"{provider}-{tier.value}-{position}",
        provider=provider,
        model=f"{provider}-model",
        attempts=1,
        timeout_seconds=12.0,
        max_concurrency=2,
        enabled=True,
    )


@dataclass
class Estate:
    """What the stub database and the stub providers hold, shared by the ladder and the session."""

    rungs: tuple[LadderRung, ...] = (
        rung("anthropic"),
        rung("moonshot", position=1),
        rung("openai", tier=Tier.HEAVY),
    )
    settings: dict[str, tuple[Any, str]] = field(default_factory=dict)
    #: The installation values saved under `install.`, by key: the value and who saved it.
    installed: dict[str, tuple[str, str]] = field(default_factory=dict)
    attempts: tuple[Attempt, ...] = ()
    #: Providers added from the console, as the registry rows the ladder read carries.
    providers: tuple[ProviderRecord, ...] = ()
    held: frozenset[str] = frozenset({"anthropic", "moonshot"})
    answers: dict[str, Completion | BaseException] = field(default_factory=dict)
    sent: list[DriverRequest] = field(default_factory=list)
    attempt_rows: list[tuple[str, str]] = field(default_factory=list)
    finished: list[Finished] = field(default_factory=list)
    questions: list[Finished] = field(default_factory=list)
    attributed: list[str] = field(default_factory=list)

    async def current(self, now: datetime) -> LadderState:
        off = frozenset(
            key.removeprefix(f"{PROVIDER_NAMESPACE}.")
            for key, (value, _by) in self.settings.items()
            if value is False
        )
        return LadderState(
            rungs=self.rungs, switched_off=off, attempts=self.attempts, providers=self.providers
        )

    async def started(
        self,
        *,
        trace_id: str,
        rung_id: str,
        sequence: int,
        at: datetime,
        categories: tuple[str, ...] = (),
    ) -> str:
        self.attempt_rows.append((rung_id, "started"))
        return str(len(self.attempt_rows))

    async def finished_attempt(
        self, token: str, *, at: datetime, outcome: str, status: int | None
    ) -> None:
        self.attempt_rows.append((token, outcome))

    def transport(self, provider: str) -> Any:
        def send(request: DriverRequest) -> Completion:
            self.sent.append(request)
            answer = self.answers.get(provider, Completion(text=REPLY, finish_reason="stop"))
            if isinstance(answer, BaseException):
                raise answer
            return answer

        return send


class AttemptLog:
    def __init__(self, estate: Estate) -> None:
        self.estate = estate

    async def started(
        self,
        *,
        trace_id: str,
        rung_id: str,
        sequence: int,
        at: datetime,
        categories: tuple[str, ...] = (),
    ) -> str:
        return await self.estate.started(
            trace_id=trace_id, rung_id=rung_id, sequence=sequence, at=at
        )

    async def finished(self, token: str, *, at: datetime, outcome: str, status: int | None) -> None:
        await self.estate.finished_attempt(token, at=at, outcome=outcome, status=status)


_ESTATE = Estate()


class SettingSession(AsyncSession):
    """Answers the statements a switch makes: the attribution, the upsert and the namespace read."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(statement, TextClause) and str(statement).startswith("SELECT set_config"):
            # The three settings `brain.attribution.attribute` makes before the write (M24.3.1).
            _ESTATE.attributed.append(str(statement.compile().params["name"]))
            return None
        if isinstance(statement, Insert):
            params = statement.compile(dialect=DIALECT).params
            if "key" in params:
                _ESTATE.settings[str(params["key"])] = (params["value"], str(params["updated_by"]))
                return None
            # `brain.ops.install_settings.save` inserts a list of rows, so its names are numbered.
            for index in range(len([name for name in params if name.startswith("key_m")])):
                _ESTATE.installed[str(params[f"key_m{index}"])] = (
                    str(params[f"value_m{index}"]),
                    str(params[f"updated_by_m{index}"]),
                )
            return None
        columns = [one["name"] for one in statement.column_descriptions]
        if columns == ["key", "value_type", "value"]:
            # `brain.ops.install_settings.load`, reading back what was saved.
            return _Rows(
                [
                    (key, SettingType.STRING.value, value)
                    for key, (value, _by) in sorted(_ESTATE.installed.items())
                ]
            )
        assert columns == ["key", "value_type", "value", "updated_by", "updated_at"], columns
        now = datetime.now(UTC)
        rows = [
            # A price row holds an object (M27.12.5); every switch holds a boolean.
            (key, SettingType.JSON.value if isinstance(value, dict) else "boolean", value, by, now)
            for key, (value, by) in sorted(_ESTATE.settings.items())
        ]
        return _Rows(rows)

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _Rows:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class Ledger(TelemetryRecorder):
    """The ledger's recorder, keeping what it is handed instead of writing it."""

    def __init__(self) -> None:
        pass

    async def finished(self, request: Finished) -> None:
        _ESTATE.finished.append(request)


class Questions:
    """A recorder that is not the ledger's, which a check must never reach."""

    async def finished(self, request: Finished) -> None:
        _ESTATE.questions.append(request)


@pytest.fixture
def estate() -> Iterator[Estate]:
    global _ESTATE
    _ESTATE = Estate()
    yield _ESTATE


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


def _service(estate: Estate, profile: Callable[[], str] = lambda: HOSTED_PROFILE) -> ModelService:
    drivers: dict[str, ModelDriver] = {
        one: SdkDriver(provider=one, transport=estate.transport(one))
        for one in ("anthropic", "moonshot", "openai")
    }
    return ModelService(
        calls=ModelCalls(
            ladder=estate,
            attempts=AttemptLog(estate),
            drivers=drivers,
            profile=profile,
            held=lambda: estate.held,
            clock=lambda: datetime.now(UTC),
        ),
        client=httpx.Client(),
    )


@pytest.fixture
def client(estate: Estate) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=SettingSession)
        app.state.models.close()
        app.state.models = _service(estate)
        app.state.request_recorders = (Questions(), Ledger())
        yield c


def call(c: TestClient, method: str, pid: str, path: str, body: object = None) -> Response:
    response: Response = c.request(
        method,
        path,
        headers={"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"},
        json=body,
    )
    return response


# ------------------------------------------------------------------------------ the read


def test_a_reader_is_shown_every_provider_and_every_rung_as_the_next_call_will_see_them(
    client: TestClient, estate: Estate
) -> None:
    """The rung with no key is left out with the sentence saying what to do, the two with keys
    answer, nothing has been called so nothing is measured, and a reader who cannot switch is
    told so. No environment variable name appears anywhere.

    Delete this and the screen can say a rung answers that the executor leaves out, or draw a
    provider healthy that nothing has called."""
    body = call(client, "GET", "u_narrow", PROVIDERS)

    assert body.status_code == 200
    view = body.json()
    assert [one["provider"] for one in view["providers"]] == [
        *(one.slug for one in PROVIDER_SLOTS),
        "local",
    ]
    held = {one["provider"]: one["key_held"] for one in view["providers"]}
    assert held == {
        "anthropic": True,
        "openai": False,
        "moonshot": True,
        "deepseek": False,
        "local": None,
    }
    assert all(one["switched_on"] for one in view["providers"])
    assert all(one["credential"] is None for one in view["providers"])
    rungs = {one["deployment_id"]: one for one in view["rungs"]}
    assert rungs["anthropic-main-0"]["answers"] is True
    assert rungs["openai-heavy-0"]["answers"] is False
    assert rungs["openai-heavy-0"]["skipped_because"] == RungSkip.NO_KEY.value
    assert rungs["openai-heavy-0"]["told"] == TOLD[RungSkip.NO_KEY]
    assert {one["measured"] for one in view["rungs"]} == {False}
    assert {one["state"] for one in view["rungs"]} == {"closed"}
    assert view["editable"] is False
    assert view["vault"] is None
    for one in PROVIDER_SLOTS:
        assert one.env_var not in body.text


def test_a_rung_its_attempts_opened_is_drawn_open_and_measured(
    client: TestClient, estate: Estate
) -> None:
    """Delete this and the screen's health can come from somewhere other than the attempts."""
    now = datetime.now(UTC)
    estate.attempts = tuple(
        Attempt(deployment_id="moonshot-main-1", finished_at=now, outcome="provider_error")
        for _ in range(3)
    )

    rungs = {
        one["deployment_id"]: one
        for one in call(client, "GET", "u_narrow", PROVIDERS).json()["rungs"]
    }

    assert rungs["moonshot-main-1"]["state"] == "open"
    assert rungs["moonshot-main-1"]["measured"] is True
    assert rungs["moonshot-main-1"]["live_failed"] == 3
    assert rungs["anthropic-main-0"]["measured"] is False


def test_the_vaults_answer_is_served_only_to_a_reader_who_may_manage_credentials(
    client: TestClient, estate: Estate
) -> None:
    """Delete this and the models screen serves what the credentials route refuses to everybody
    without `admin:credential`."""
    managed = call(client, "GET", "u_admin", PROVIDERS).json()
    unmanaged = call(client, "GET", "u_wide", PROVIDERS).json()

    assert managed["vault"] == "absent"
    assert managed["vault_told"]
    assert {one["provider"]: one["credential"] is not None for one in managed["providers"]} == {
        "anthropic": True,
        "openai": True,
        "moonshot": True,
        "deepseek": True,
        "local": False,
    }
    assert unmanaged["vault"] is None
    assert all(one["credential"] is None for one in unmanaged["providers"])


@pytest.mark.parametrize("pid", ["u_none", "u_elsewhere", "u_prefix"])
def test_a_reader_whose_basis_is_not_everybodys_is_refused_identically(
    client: TestClient, estate: Estate, pid: str
) -> None:
    """Delete this and a department-scoped reader is shown which providers every department's
    questions go to."""
    refused = call(client, "GET", pid, PROVIDERS)

    assert refused.status_code == 404
    assert refused.json()["message"] == call(client, "GET", "u_none", PROVIDERS).json()["message"]


# ---------------------------------------------------------------------------- the switch


def test_switching_a_provider_off_takes_its_rungs_out_of_the_next_plan_at_once(
    client: TestClient, estate: Estate
) -> None:
    """The row, and the behaviour in the same response: the switch is kept under the provider's key
    with who switched it, the answer is the plan read afterwards, and a call made next is not sent
    there.

    Delete this and a switch can be written and read by nothing."""
    switched = call(client, "PUT", "u_wide", f"{PROVIDERS}/moonshot", {"on": False})

    assert switched.status_code == 200
    assert estate.settings == {"provider.moonshot": (False, "u_wide")}
    # Who, at what reach, in which request, set before the write for the setting's ledger entry.
    assert estate.attributed == [ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING]
    view = switched.json()
    moonshot = next(one for one in view["providers"] if one["provider"] == "moonshot")
    assert moonshot["switched_on"] is False
    assert moonshot["switched_by"] == "u_wide"
    rungs = {one["deployment_id"]: one for one in view["rungs"]}
    assert rungs["moonshot-main-1"]["skipped_because"] == RungSkip.SWITCHED_OFF.value
    assert rungs["anthropic-main-0"]["answers"] is True
    assert view["editable"] is True

    checked = call(client, "POST", "u_wide", f"{PROVIDERS}/moonshot/check").json()
    assert checked["outcome"] == RungSkip.SWITCHED_OFF.value
    assert estate.sent == []


@pytest.mark.parametrize("pid", ["u_narrow", "u_elsewhere", "u_none"])
def test_a_switch_is_refused_without_the_write_held_over_everything_and_writes_nothing(
    client: TestClient, estate: Estate, pid: str
) -> None:
    """Delete this and a department-scoped matrix grant redirects every department's questions."""
    refused = call(client, "PUT", pid, f"{PROVIDERS}/moonshot", {"on": False})

    assert refused.status_code == 404
    assert estate.settings == {}


def test_a_provider_the_product_cannot_call_is_refused_like_a_caller_who_may_not_switch(
    client: TestClient, estate: Estate
) -> None:
    """Delete this and the refusal for a name that does not exist differs from the refusal for a
    caller who may not switch, and a switch row for a provider nothing reads can be written."""
    unknown = call(client, "PUT", "u_wide", f"{PROVIDERS}/somebody_else", {"on": False})
    unauthorised = call(client, "PUT", "u_narrow", f"{PROVIDERS}/moonshot", {"on": False})

    assert unknown.status_code == unauthorised.status_code == 404
    assert estate.settings == {}


def test_the_write_capability_must_be_held_unrestricted_and_the_positive_case_holds() -> None:
    """Delete this and `may_switch` can be relaxed to `holds`, which a scoped grant satisfies."""
    now = datetime.now(UTC)
    assert may_switch(EntitlementSet(principal_id="u_wide", grants=GRANTS["u_wide"]), now)
    assert not may_switch(
        EntitlementSet(principal_id="u_elsewhere", grants=GRANTS["u_elsewhere"]), now
    )
    assert not may_switch(EntitlementSet(principal_id="u_narrow", grants=GRANTS["u_narrow"]), now)


# ------------------------------------------------------------------ where answers are made


@pytest.fixture
def chosen(client: TestClient, estate: Estate) -> Iterator[None]:
    """The executor reading the profile through `value_of`, as the lifespan builds it, with this
    process's saved values starting at the local profile and put back afterwards."""
    app: Any = client.app
    app.state.models = _service(estate, profile=lambda: value_of(PROFILE_SETTING))
    before = hold_saved({PROFILE_SETTING: LOCAL_PROFILE})
    yield
    hold_saved(before)


def test_where_answers_are_made_is_saved_by_the_super_administrator_ledgered_and_planned_at_once(
    client: TestClient, estate: Estate, chosen: None
) -> None:
    """The installation row is written under the profile's key with who saved it, attributed for
    its ledger entry, held by this process, and the plan answered with already sends to the
    online providers the local profile had left out.

    Delete this and the owner's only way to let questions reach an online provider after setup is
    a shell on the server, which is the state his install was found in on 2026-09-28."""
    before = call(client, "GET", "u_admin", PROVIDERS).json()
    assert before["profile"] == LOCAL_PROFILE
    assert before["profile_editable"] is True
    assert {one["skipped_because"] for one in before["rungs"]} == {RungSkip.LOCAL_PROFILE.value}

    chose = call(client, "PUT", "u_admin", PROFILE, {"profile": HOSTED_PROFILE})

    assert chose.status_code == 200
    assert estate.installed == {"install.model_profile": (HOSTED_PROFILE, "u_admin")}
    assert estate.attributed == [ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING]
    assert value_of(PROFILE_SETTING) == HOSTED_PROFILE
    view = chose.json()
    assert view["profile"] == HOSTED_PROFILE
    rungs = {one["deployment_id"]: one for one in view["rungs"]}
    assert rungs["anthropic-main-0"]["answers"] is True
    assert rungs["openai-heavy-0"]["skipped_because"] == RungSkip.NO_KEY.value


@pytest.mark.parametrize("pid", ["u_wide", "u_elsewhere", "u_narrow", "u_none"])
def test_where_answers_are_made_is_refused_without_the_setting_authority_over_everything(
    client: TestClient, estate: Estate, chosen: None, pid: str
) -> None:
    """Every administrator short of the installation setting authority held over everything is
    refused as a caller who may not read the screen is, and nothing is written or held. The
    reader who may switch providers is not offered the control either.

    Delete this and whoever may switch a provider, or holds the authority for one department,
    can send every department's questions off the server."""
    refused = call(client, "PUT", pid, PROFILE, {"profile": HOSTED_PROFILE})

    assert refused.status_code == 404
    assert refused.json()["message"] == call(client, "GET", "u_none", PROVIDERS).json()["message"]
    assert estate.installed == {}
    assert estate.attributed == []
    assert value_of(PROFILE_SETTING) == LOCAL_PROFILE
    assert call(client, "GET", "u_wide", PROVIDERS).json()["profile_editable"] is False


def test_a_profile_that_is_neither_of_the_two_is_refused_and_nothing_is_written(
    client: TestClient, estate: Estate, chosen: None
) -> None:
    """Delete this and a typed value such as "online" is saved, read by the executor as local
    because it is not hosted, and shown by the Settings screen as a profile nobody offered."""
    refused = call(client, "PUT", "u_admin", PROFILE, {"profile": "online"})

    assert refused.status_code == 422
    assert estate.installed == {}
    assert value_of(PROFILE_SETTING) == LOCAL_PROFILE


def test_the_local_profile_tells_the_administrator_where_the_control_is() -> None:
    """Delete this and the sentence beside every skipped step goes back to naming "the setup
    settings", which no screen offers after setup, which is what the owner was told on
    2026-09-28."""
    told = TOLD[RungSkip.LOCAL_PROFILE]

    assert "Where answers are made" in told
    assert "Models and health" in told
    assert "setup" not in told


# ----------------------------------------------------------------------------- the check


def test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question(
    client: TestClient, estate: Estate
) -> None:
    """One fixed sentence, a small output ceiling, one attempt row, and a ledger row carrying the
    tokens under the person who pressed it. The model's reply is not in the response.

    Delete this and a check can call a provider without metering it, count as a question on the
    usage screen, or hand an administrator whatever the model said."""
    estate.answers["anthropic"] = Completion(
        text=REPLY, finish_reason="stop", input_tokens=12, output_tokens=2, served_model="claude-x"
    )

    checked = call(client, "POST", "u_wide", f"{PROVIDERS}/anthropic/check")

    assert checked.status_code == 200
    view = checked.json()
    assert view["answered"] is True
    assert view["outcome"] == "answered"
    assert view["told"] == answered_told("claude-x", default_model=False)
    assert "claude-x" in view["told"]
    assert view["default_model"] is False
    assert (view["served_by"], view["model"]) == ("anthropic-main-0", "claude-x")
    assert (view["tokens_in"], view["tokens_out"]) == (12, 2)
    assert REPLY not in checked.text
    (sent,) = estate.sent
    assert [one.content for one in sent.messages] == [CHECK_PROMPT]
    assert sent.max_output_tokens == CHECK_MAX_OUTPUT_TOKENS
    assert [one[1] for one in estate.attempt_rows] == ["started", "ok"]
    (finished,) = estate.finished
    assert finished.outcome == ModelCallOutcome(answered=True)
    assert finished.lane is Lane.ANSWER
    assert finished.origin.principal.id == "u_wide"
    assert finished.origin.trace_id == view["trace_id"]
    assert finished.model_usage is not None
    assert (finished.model_usage.tokens_in, finished.model_usage.tokens_out) == (12, 2)
    assert estate.questions == []


def test_a_check_that_fails_says_how_in_the_checks_words_and_is_still_recorded(
    client: TestClient, estate: Estate
) -> None:
    """Delete this and a provider error reaches the administrator as a 500, and the attempt that
    failed never reaches the ledger that the breaker and the fallback figure read."""
    estate.answers["moonshot"] = TransportStatusError(503)

    view = call(client, "POST", "u_wide", f"{PROVIDERS}/moonshot/check").json()

    assert view["answered"] is False
    assert view["outcome"] == "provider_error"
    assert view["status"] == 503
    assert view["told"] == CHECK_TOLD["provider_error"]
    (finished,) = estate.finished
    assert finished.outcome == ModelCallOutcome(answered=False)
    assert finished.model_usage is not None
    assert finished.model_usage.calls == 1


def test_a_check_with_nothing_to_call_says_why_and_calls_nothing(
    client: TestClient, estate: Estate
) -> None:
    """A provider whose steps are left out is told the assembly's own reason, and so is a provider
    no step names whose default model cannot be called here: the install's own server, with no
    address, is told so and which model the test would have used.

    Delete this and a check on a keyless provider reports a provider outage."""
    keyless = call(client, "POST", "u_wide", f"{PROVIDERS}/openai/check").json()
    nowhere = call(client, "POST", "u_wide", f"{PROVIDERS}/local/check").json()

    assert (keyless["outcome"], keyless["told"]) == (RungSkip.NO_KEY.value, TOLD[RungSkip.NO_KEY])
    assert keyless["default_model"] is False
    assert nowhere["outcome"] == RungSkip.NO_INFERENCE_SERVER.value
    assert nowhere["told"] == default_model_told(
        TOLD[RungSkip.NO_INFERENCE_SERVER], LOCAL_COMPLETION_MODEL
    )
    assert (nowhere["default_model"], nowhere["model"]) == (True, LOCAL_COMPLETION_MODEL)
    assert estate.sent == []
    assert all(one.model_usage is None for one in estate.finished)


def test_a_check_on_a_provider_whose_rungs_are_all_out_of_rotation_says_so_and_calls_nothing(
    client: TestClient, estate: Estate
) -> None:
    """Delete this and a provider an administrator took out of rotation is reported as resting
    behind an open breaker, which sends them to wait for a cooldown that will never help."""
    estate.rungs = (replace(rung("anthropic"), enabled=False),)

    view = call(client, "POST", "u_wide", f"{PROVIDERS}/anthropic/check").json()

    assert (view["outcome"], view["told"]) == ("out_of_rotation", CHECK_TOLD["out_of_rotation"])
    assert estate.sent == []


@pytest.mark.parametrize("pid", ["u_narrow", "u_elsewhere", "u_none"])
def test_a_check_is_refused_without_the_write_held_over_everything_and_sends_nothing(
    client: TestClient, estate: Estate, pid: str
) -> None:
    """A check costs money and names the person who pressed it. Delete this and anybody who can
    read the screen can spend on every provider."""
    refused = call(client, "POST", pid, f"{PROVIDERS}/anthropic/check")

    assert refused.status_code == 404
    assert estate.sent == []
    assert estate.finished == []


def test_a_provider_no_step_names_is_checked_through_its_default_model_and_says_which(
    client: TestClient, estate: Estate
) -> None:
    """The owner's case on 2026-09-28: OpenAI holds a key and no step names it. The check is sent
    to its default model, planned as a step would be, metered and on the ledger under the person
    who pressed it, and says in words which model answered and that it was the default. No
    attempt row is written, because it would name a step that does not exist.

    Delete this and Test on a provider whose key was just saved answers that there is nothing to
    check, which is what the owner was told."""
    estate.rungs = (rung("anthropic"),)
    estate.held = frozenset({"anthropic", "openai"})
    default = DEFAULT_MODELS["openai"][Tier.MAIN]

    checked = call(client, "POST", "u_wide", f"{PROVIDERS}/openai/check")

    assert checked.status_code == 200
    view = checked.json()
    assert (view["answered"], view["outcome"], view["default_model"]) == (True, "answered", True)
    (sent,) = estate.sent
    assert sent.model == default
    assert [one.content for one in sent.messages] == [CHECK_PROMPT]
    assert view["model"] == default
    assert view["told"] == answered_told(default, default_model=True)
    assert default in view["told"]
    assert REPLY not in checked.text
    assert estate.attempt_rows == []
    (finished,) = estate.finished
    assert finished.origin.principal.id == "u_wide"
    assert finished.model_usage is not None
    assert finished.model_usage.calls == 1
    assert estate.questions == []


def test_a_provider_with_a_step_is_checked_through_the_step_and_not_its_default(
    client: TestClient, estate: Estate
) -> None:
    """The sibling of the default path: a provider a step names is sent to that step's model.

    Delete this and the default model can replace a step's own, so a Test reports a model the
    failover matrix never sends a question to."""
    estate.held = frozenset({"anthropic", "moonshot", "openai"})

    view = call(client, "POST", "u_wide", f"{PROVIDERS}/openai/check").json()

    (sent,) = estate.sent
    assert sent.model == "openai-model"
    assert view["default_model"] is False
    assert [one[1] for one in estate.attempt_rows] == ["started", "ok"]


def test_a_default_model_check_asks_the_switch_first_and_sends_nothing_when_it_is_off(
    client: TestClient, estate: Estate
) -> None:
    """The added step is assembled like any other, so a provider switched off is not sent the
    sentence, and the answer says it is off and which model would have been used.

    Delete this and the default path becomes a way past the switch that exists to stop text
    reaching a provider."""
    estate.rungs = (rung("anthropic"),)
    estate.held = frozenset({"anthropic", "openai"})
    call(client, "PUT", "u_wide", f"{PROVIDERS}/openai", {"on": False})

    view = call(client, "POST", "u_wide", f"{PROVIDERS}/openai/check").json()

    assert view["outcome"] == RungSkip.SWITCHED_OFF.value
    default = DEFAULT_MODELS["openai"][Tier.MAIN]
    assert view["told"] == default_model_told(TOLD[RungSkip.SWITCHED_OFF], default)
    assert estate.sent == []


def test_an_added_provider_with_no_model_named_is_told_there_is_nothing_to_test_with(
    client: TestClient, estate: Estate
) -> None:
    """A provider added from the console with no model listed has no default to test, and is
    told to add a step rather than sent a guess.

    Delete this and the no-model branch can send the check to a model nobody named."""
    estate.providers = (
        ProviderRecord(
            slug="acme_llm",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            label="Acme",
            base_url="https://llm.example.test/v1",
        ),
    )

    view = call(client, "POST", "u_wide", f"{PROVIDERS}/acme_llm/check").json()

    assert (view["outcome"], view["told"]) == ("no_model", CHECK_TOLD["no_model"])
    assert view["default_model"] is False
    assert estate.sent == []


@pytest.mark.parametrize("status", sorted(KEY_REFUSED_STATUSES))
def test_a_refused_key_is_said_plainly_and_not_as_a_stopped_request(
    client: TestClient, estate: Estate, status: int
) -> None:
    """A 401 or 403 is the provider refusing the key, and the answer says so in those words.

    Delete this and a refused key reads as a request the provider turned down for some other
    reason, and the administrator checks the model name instead of the key."""
    estate.answers["anthropic"] = TransportStatusError(status)

    view = call(client, "POST", "u_wide", f"{PROVIDERS}/anthropic/check").json()

    assert (view["answered"], view["outcome"], view["status"]) == (False, "key_refused", status)
    assert view["told"] == CHECK_TOLD["key_refused"]
    assert "refused the key" in view["told"]


def test_a_request_the_provider_turned_down_for_another_reason_is_not_a_refused_key(
    client: TestClient, estate: Estate
) -> None:
    """The sibling: a 400 stops the chain and is not the key.

    Delete this and every 4xx is reported as a bad key, which sends the administrator to replace
    a key that works."""
    estate.answers["anthropic"] = TransportStatusError(400)

    view = call(client, "POST", "u_wide", f"{PROVIDERS}/anthropic/check").json()

    assert (view["outcome"], view["status"]) == ("stopped", 400)
    assert view["told"] == CHECK_TOLD["stopped"]


def test_the_latest_word_per_step_decides_whether_its_key_was_refused() -> None:
    """Built from rows as the statement returns them, in finishing order: a step refused and then
    answered is not refused, a step refused last is, and an unfinished row says nothing.

    Delete this and one refusal marks a step for as long as it is in the window, after the key
    was replaced and answered."""
    early = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
    later = datetime(2019, 3, 4, 9, 5, tzinfo=UTC)
    rows = [
        ("refused-then-answered", early, 401),
        ("refused-then-answered", later, None),
        ("answered-then-refused", early, None),
        ("answered-then-refused", later, 403),
        ("turned-down", later, 400),
        ("unfinished", None, 401),
    ]

    assert refused_keys(rows) == frozenset({"answered-then-refused"})


#: The words the owner asked never to see on the Models screen or in a check's answer.
JARGON = re.compile(r"\b(rungs?|ladders?|tiers?|lanes?|slots?)\b", re.IGNORECASE)

#: A file path a sentence points an operator at, which is a name and not a word on the screen.
PATH = re.compile(r"\S+/\S+")


def test_no_sentence_a_check_or_the_providers_screen_can_show_uses_internal_jargon() -> None:
    """Every sentence the check answers with and every reason a step is left out, including the
    two built with a model's name, and the vault's and the data categories' sentences the screen
    shows beside them.

    Delete this and rung, ladder, tier, lane or slot can come back in the next sentence somebody
    writes, which is what the owner found on 2026-09-28."""
    sentences = [
        *CHECK_TOLD.values(),
        *TOLD.values(),
        *VAULT_TOLD.values(),
        *CATEGORY_TOLD.values(),
        answered_told("gpt-5-mini", default_model=True),
        answered_told("gpt-5-mini", default_model=False),
        default_model_told(CHECK_TOLD["key_refused"], "gpt-5-mini"),
    ]

    found = [one for one in sentences if JARGON.search(PATH.sub("", one))]

    assert sentences
    assert found == []


# ------------------------------------------------------------- a rung saved, then walked


def test_a_rung_saved_on_the_routing_screen_is_the_rung_the_next_call_walks(estate: Estate) -> None:
    """End to end against a real server: the Routing screen's PATCH takes a rung out of rotation and
    a check finds nothing in rotation to send to; the PATCH puts it back with a new timeout and the
    check is sent with that timeout, leaving an attempt row that names the rung.

    This is the behaviour a rung save had no proof of, because nothing read `ops.routing_rung`
    before the executor did. Delete this and the executor can go back to planning from a ladder read
    once at start, after which a rung saved on the Routing screen changes its row and no call until
    a restart."""
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
    with modelled("brain_test_provider_routes_rung_save", RUNG_TABLES) as url:
        rung_id = str(uuid.uuid4())
        sql(
            url,
            "INSERT INTO ops.routing_rung (id, tier, scope, position, role, deployment_id, "
            "provider, model, attempts, timeout_seconds, max_concurrency, enabled) VALUES "
            "(%s, 'main', '{}'::jsonb, 0, 'primary', 'anthropic-main-0', 'anthropic', "
            "'anthropic-model', 1, 12, 4, true)",
            rung_id,
        )
        bound = engine(url)
        sessions = async_sessionmaker(bound, expire_on_commit=False)
        app: FastAPI = create_app(Settings(env="development", database_url=""))
        edit = f"{API_PREFIX}/routing/rungs/{rung_id}"
        check = f"{PROVIDERS}/anthropic/check"
        try:
            with TestClient(app, raise_server_exceptions=False, backend_options=options) as c:
                app.state.gate = _wiring()
                app.state.db_sessions = sessions
                app.state.console_reads = None
                app.state.models.close()
                app.state.models = ModelService(
                    calls=ModelCalls(
                        ladder=SessionLadder(sessions),
                        attempts=SessionAttempts(sessions),
                        drivers={
                            "anthropic": SdkDriver(
                                provider="anthropic", transport=estate.transport("anthropic")
                            )
                        },
                        profile=lambda: HOSTED_PROFILE,
                        held=lambda: frozenset({"anthropic"}),
                        clock=lambda: datetime.now(UTC),
                    ),
                    client=httpx.Client(),
                )
                app.state.request_recorders = (Ledger(),)
                # The gate passes each save: this is the save reaching the next call, and the
                # gate's own run is `tests/unit/test_matrix_gate.py`'s.
                app.state.matrix_gate = _PassingGate()
                out = {"attempts": 1, "max_concurrency": 2, "timeout_seconds": 12, "enabled": False}
                # Above the answer budget: the one step is the last, which is given the rest of
                # the budget when its own figure is less, and the saved figure would not show.
                back = {
                    "attempts": 1,
                    "max_concurrency": 2,
                    "timeout_seconds": 30.5,
                    "enabled": True,
                }
                taken_out = call(c, "PATCH", "u_wide", edit, out)
                while_out = call(c, "POST", "u_wide", check).json()
                put_back = call(c, "PATCH", "u_wide", edit, back)
                once_back = call(c, "POST", "u_wide", check).json()
        finally:
            run(bound.dispose)

        assert (taken_out.status_code, put_back.status_code) == (200, 200)
        assert while_out["outcome"] == "out_of_rotation"
        assert once_back["answered"] is True
        (sent,) = estate.sent
        assert sent.timeout_seconds == 30.5
        assert sql(url, "SELECT rung_id::text, outcome FROM ops.model_attempt") == [(rung_id, "ok")]
        assert sql(url, "SELECT status FROM ops.routing_change ORDER BY decided_at") == [
            ("applied",),
            ("applied",),
        ]


class _PassingGate:
    """A `brain.ops.matrix_gate_run.MatrixGate` that lets every change take traffic."""

    async def decide(self, change: object, *, now: object, new_rung_id: str) -> GateVerdict:
        return GateVerdict(may_apply=True, failing=(), reasons=(), quality_share=None)


def test_a_step_whose_key_the_provider_refused_is_marked_until_a_later_call_answers(
    estate: Estate,
) -> None:
    """End to end against a real server: a check the provider answers with 401 leaves an attempt
    row with that status, the next read marks the step's key refused even though its breaker is
    closed and measured, and a check that answers afterwards clears the mark.

    Delete this and the screen goes back to drawing a provider that refuses the key as working,
    because a refused key is not ill health and the breaker never moves for it."""
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
    with modelled("brain_test_provider_routes_key_refused", RUNG_TABLES) as url:
        rung_id = str(uuid.uuid4())
        sql(
            url,
            "INSERT INTO ops.routing_rung (id, tier, scope, position, role, deployment_id, "
            "provider, model, attempts, timeout_seconds, max_concurrency, enabled) VALUES "
            "(%s, 'main', '{}'::jsonb, 0, 'primary', 'anthropic-main-0', 'anthropic', "
            "'anthropic-model', 1, 12, 4, true)",
            rung_id,
        )
        bound = engine(url)
        sessions = async_sessionmaker(bound, expire_on_commit=False)
        app: FastAPI = create_app(Settings(env="development", database_url=""))
        check = f"{PROVIDERS}/anthropic/check"
        try:
            with TestClient(app, raise_server_exceptions=False, backend_options=options) as c:
                app.state.gate = _wiring()
                app.state.db_sessions = sessions
                app.state.console_reads = None
                app.state.models.close()
                app.state.models = ModelService(
                    calls=ModelCalls(
                        ladder=SessionLadder(sessions),
                        attempts=SessionAttempts(sessions),
                        drivers={
                            "anthropic": SdkDriver(
                                provider="anthropic", transport=estate.transport("anthropic")
                            )
                        },
                        profile=lambda: HOSTED_PROFILE,
                        held=lambda: frozenset({"anthropic"}),
                        clock=lambda: datetime.now(UTC),
                    ),
                    client=httpx.Client(),
                )
                app.state.request_recorders = (Ledger(),)
                estate.answers["anthropic"] = TransportStatusError(401)
                refused = call(c, "POST", "u_wide", check).json()
                while_refused = call(c, "GET", "u_wide", PROVIDERS).json()
                estate.answers.pop("anthropic")
                answered = call(c, "POST", "u_wide", check).json()
                once_answered = call(c, "GET", "u_wide", PROVIDERS).json()
        finally:
            run(bound.dispose)

        assert (refused["outcome"], answered["outcome"]) == ("key_refused", "answered")
        (step,) = while_refused["rungs"]
        assert (step["key_refused"], step["measured"], step["state"]) == (True, True, "closed")
        (after,) = once_answered["rungs"]
        assert after["key_refused"] is False
        assert sql(url, "SELECT status_code FROM ops.model_attempt ORDER BY finished_at") == [
            (401,),
            (None,),
        ]


# ------------------------------------------------------------------------------ the prices
PRICES = f"{API_PREFIX}/models/prices"

#: A price for the anthropic rung's model, in minor units of the install's currency per million.
SONNET_PRICE = {
    "provider": "anthropic",
    "model": "anthropic-model",
    "input_minor_per_million": "300",
    "output_minor_per_million": "0.075",
}


@pytest.fixture
def in_sgd(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install counts in SGD. Read by the route through `brain.locale.currency`."""
    monkeypatch.setattr(provider_routes, "install_currency", lambda: "SGD")


def test_a_reader_is_shown_each_model_on_the_ladder_with_its_price_and_whether_it_is_costed(
    client: TestClient, estate: Estate, in_sgd: None
) -> None:
    """A model priced in the install's currency is costed, a model with no price is not and says
    so with no figure, a price in another currency is shown and not costed, and a model priced and
    not on the ladder is listed as such.

    What breaks if this is deleted: an administrator cannot see which models' calls leave no cost,
    and an install nobody priced looks as though it records every call."""
    estate.settings["model_price.anthropic"] = (
        {
            "anthropic-model": {
                "input_minor_per_million": "300",
                "output_minor_per_million": "1500",
                "currency": "SGD",
            },
            "retired-model": {
                "input_minor_per_million": "1",
                "output_minor_per_million": "2",
                "currency": "SGD",
            },
        },
        "u_admin",
    )
    estate.settings["model_price.moonshot"] = (
        {
            "moonshot-model": {
                "input_minor_per_million": "5",
                "output_minor_per_million": "6",
                "currency": "EUR",
            }
        },
        "u_admin",
    )

    shown = call(client, "GET", "u_narrow", PRICES)

    assert shown.status_code == 200
    body = shown.json()
    assert body["currency"] == "SGD"
    rows = {(one["provider"], one["model"]): one for one in body["models"]}
    assert rows[("anthropic", "anthropic-model")] == {
        "provider": "anthropic",
        "model": "anthropic-model",
        "on_ladder": True,
        "input_minor_per_million": "300",
        "output_minor_per_million": "1500",
        "currency": "SGD",
        "costed": True,
    }
    assert rows[("openai", "openai-model")]["costed"] is False
    assert rows[("openai", "openai-model")]["input_minor_per_million"] is None
    assert rows[("moonshot", "moonshot-model")]["costed"] is False
    assert rows[("moonshot", "moonshot-model")]["currency"] == "EUR"
    assert rows[("anthropic", "retired-model")]["on_ladder"] is False
    assert list(rows) == sorted(rows)


def test_the_prices_are_refused_to_a_reader_who_cannot_read_the_models_screen(
    client: TestClient, in_sgd: None
) -> None:
    """What breaks if this is deleted: the prices are one address away from a caller the screen
    refuses."""
    assert call(client, "GET", "u_none", PRICES).status_code == 404
    assert call(client, "GET", "u_elsewhere", PRICES).status_code == 404


def test_a_price_is_set_by_the_switch_holder_attributed_and_kept_in_the_installs_currency(
    client: TestClient, estate: Estate, in_sgd: None
) -> None:
    """The row is the provider's, holding the model's price as text in SGD, written with who set
    it after the attribution the setting's ledger entry reads, and the answer is every model with
    this one now costed.

    What breaks if this is deleted: the Models screen's price is written nowhere, or written with
    no writer on the ledger, or in no currency."""
    answered = call(client, "PUT", "u_wide", PRICES, SONNET_PRICE)

    assert answered.status_code == 200
    assert estate.settings == {
        "model_price.anthropic": (
            {
                "anthropic-model": {
                    "input_minor_per_million": "300",
                    "output_minor_per_million": "0.075",
                    "currency": "SGD",
                }
            },
            "u_wide",
        )
    }
    assert estate.attributed == [ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING]
    rows = {(one["provider"], one["model"]): one for one in answered.json()["models"]}
    assert rows[("anthropic", "anthropic-model")]["costed"] is True


@pytest.mark.parametrize("pid", ["u_narrow", "u_elsewhere", "u_none"])
def test_a_price_is_refused_without_the_write_held_over_everything_and_writes_nothing(
    client: TestClient, estate: Estate, in_sgd: None, pid: str
) -> None:
    """What breaks if this is deleted: a department-scoped grant sets what every department's
    calls are costed at."""
    assert call(client, "PUT", pid, PRICES, SONNET_PRICE).status_code == 404
    assert estate.settings == {}


def test_a_price_for_a_provider_the_product_cannot_call_is_refused_like_no_authority(
    client: TestClient, estate: Estate, in_sgd: None
) -> None:
    """What breaks if this is deleted: a price row is kept under a name no call can ever carry."""
    refused = call(client, "PUT", "u_wide", PRICES, {**SONNET_PRICE, "provider": "nobody"})
    assert refused.status_code == 404
    assert estate.settings == {}


def test_a_price_before_the_install_has_a_currency_is_refused_and_writes_nothing(
    client: TestClient, estate: Estate, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the currency still `XXX` the write is a 422 whose sentence sends the administrator to
    Settings, and nothing is kept.

    What breaks if this is deleted: a price set in no currency is costed later in whichever one is
    chosen, a figure off by the exchange rate with nothing on it saying so."""
    monkeypatch.setattr(provider_routes, "install_currency", lambda: "XXX")

    refused = call(client, "PUT", "u_wide", PRICES, SONNET_PRICE)

    assert refused.status_code == 422
    assert [one["message"] for one in refused.json()["problems"]] == [
        provider_routes.A_PRICE_NEEDS_THE_INSTALLS_CURRENCY
    ]
    assert estate.settings == {}


@pytest.mark.parametrize("figure", ["-1", "abc", "0.0000001", "1e12"])
def test_a_price_that_is_not_a_bounded_figure_is_refused_and_writes_nothing(
    client: TestClient, estate: Estate, in_sgd: None, figure: str
) -> None:
    """What breaks if this is deleted: a negative or unbounded price reaches the store, and a
    request is costed below nought or at a slipped digit."""
    body = {**SONNET_PRICE, "input_minor_per_million": figure}
    assert call(client, "PUT", "u_wide", PRICES, body).status_code == 422
    assert estate.settings == {}
