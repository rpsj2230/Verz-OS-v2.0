"""The providers screen over HTTP: what it answers, who may switch a provider, what a check does.

Driven through the real application with the token machinery and the directory borrowed from
`tests/unit/test_api_routes.py` and `tests/unit/test_agent_routes.py`, as
`tests/unit/test_operate_routes.py` does. The executor on `app.state.models` is the real
`brain.models.calls.ModelCalls` over a ladder, an attempt log and transports held in memory, and
the database the switch writes to is a stub that keeps `ops.setting` rows by key, so the switch
reaches the same ladder the next plan reads.

Task ids: M27.8.8, M27.2.3
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Insert

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
from brain.models.adapter import Completion, SdkDriver, TransportStatusError
from brain.models.assembly import HOSTED_PROFILE, TOLD, LadderRung, RungSkip
from brain.models.calls import LadderState, ModelCalls
from brain.models.driver import DriverRequest, ModelDriver
from brain.models.evidence import Attempt
from brain.models.routing import Tier
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
    may_switch,
)
from brain.routing_routes import MATRIX_WRITE
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

#: The tables a rung save and a check touch, built from the models on a scratch server.
RUNG_TABLES = ("ops.routing_rung", "ops.model_attempt", "ops.setting")
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


#: `u_admin` reads, switches and manages credentials. `u_wide` reads and switches. `u_narrow`
#: reads. `u_elsewhere` holds all three scoped to one department. `u_prefix` holds read and write
#: with only the existence plane. `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": grants(
        (MODEL_READ, EVERYWHERE),
        (CONFIGURATION, EVERYWHERE),
        (MATRIX_WRITE, EVERYWHERE),
        (CREDENTIAL_AUTHORITY, EVERYWHERE),
    ),
    "u_wide": grants(
        (MODEL_READ, EVERYWHERE), (CONFIGURATION, EVERYWHERE), (MATRIX_WRITE, EVERYWHERE)
    ),
    "u_narrow": grants((MODEL_READ, EVERYWHERE), (CONFIGURATION, EVERYWHERE)),
    "u_elsewhere": grants(
        (MODEL_READ, Scope.department("finance")),
        (CONFIGURATION, EVERYWHERE),
        (MATRIX_WRITE, Scope.department("finance")),
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
    attempts: tuple[Attempt, ...] = ()
    held: frozenset[str] = frozenset({"anthropic", "moonshot"})
    answers: dict[str, Completion | BaseException] = field(default_factory=dict)
    sent: list[DriverRequest] = field(default_factory=list)
    attempt_rows: list[tuple[str, str]] = field(default_factory=list)
    finished: list[Finished] = field(default_factory=list)
    questions: list[Finished] = field(default_factory=list)

    async def current(self, now: datetime) -> LadderState:
        off = frozenset(
            key.removeprefix(f"{PROVIDER_NAMESPACE}.")
            for key, (value, _by) in self.settings.items()
            if value is False
        )
        return LadderState(rungs=self.rungs, switched_off=off, attempts=self.attempts)

    async def started(self, *, trace_id: str, rung_id: str, sequence: int, at: datetime) -> str:
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

    async def started(self, *, trace_id: str, rung_id: str, sequence: int, at: datetime) -> str:
        return await self.estate.started(
            trace_id=trace_id, rung_id=rung_id, sequence=sequence, at=at
        )

    async def finished(self, token: str, *, at: datetime, outcome: str, status: int | None) -> None:
        await self.estate.finished_attempt(token, at=at, outcome=outcome, status=status)


_ESTATE = Estate()


class SettingSession(AsyncSession):
    """Answers the two statements a switch makes: the upsert, and the namespace read."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(statement, Insert):
            params = statement.compile(dialect=DIALECT).params
            _ESTATE.settings[str(params["key"])] = (params["value"], str(params["updated_by"]))
            return None
        columns = [one["name"] for one in statement.column_descriptions]
        assert columns == ["key", "value_type", "value", "updated_by", "updated_at"], columns
        now = datetime.now(UTC)
        rows = [
            (key, SettingType.BOOLEAN.value, value, by, now)
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


def _service(estate: Estate) -> ModelService:
    drivers: dict[str, ModelDriver] = {
        one: SdkDriver(provider=one, transport=estate.transport(one))
        for one in ("anthropic", "moonshot", "openai")
    }
    return ModelService(
        calls=ModelCalls(
            ladder=estate,
            attempts=AttemptLog(estate),
            drivers=drivers,
            profile=lambda: HOSTED_PROFILE,
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
    assert held == {"anthropic": True, "openai": False, "moonshot": True, "local": None}
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
    assert view["told"] == CHECK_TOLD["answered"]
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
    """A provider whose rungs are left out is told the assembly's own reason, and a provider on no
    rung is told there is nothing to check.

    Delete this and a check on a keyless provider reports a provider outage."""
    keyless = call(client, "POST", "u_wide", f"{PROVIDERS}/openai/check").json()
    nowhere = call(client, "POST", "u_wide", f"{PROVIDERS}/local/check").json()

    assert (keyless["outcome"], keyless["told"]) == (RungSkip.NO_KEY.value, TOLD[RungSkip.NO_KEY])
    assert (nowhere["outcome"], nowhere["told"]) == ("no_rung", CHECK_TOLD["no_rung"])
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
                out = {"attempts": 1, "max_concurrency": 2, "timeout_seconds": 12, "enabled": False}
                back = {
                    "attempts": 1,
                    "max_concurrency": 2,
                    "timeout_seconds": 9.5,
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
        assert sent.timeout_seconds == 9.5
        assert sql(url, "SELECT rung_id::text, outcome FROM ops.model_attempt") == [(rung_id, "ok")]
