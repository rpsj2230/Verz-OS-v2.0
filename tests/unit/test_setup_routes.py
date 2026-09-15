"""The setup wizard's appointment route appoints the first administrator once, in e81c8b9's order,
and a fresh install then reaches a signed-in administrator through HTTP alone.

Three halves. The route through `TestClient` with an in-memory store, the settings confirmation
without a server, and the lifespan's wiring against a realm over a mock transport. Then one test
on a real database, skipped without `DATABASE_URL`, that goes appointment, `/setup/sign-in` with a
token signed by the test key through the lifespan's own key set client, and `/me`, driven through
`httpx.ASGITransport` for the reason `tests/unit/test_app_wiring.py` gives.

The setup code is minted five minutes before the wall clock, because both setup routes read it
and the window is an hour.

Task ids: M42.5.6, M42.5.10, M42.5.14
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.identity.first_administrator import (
    ADMINISTRATION,
    AppointmentRefusal,
    FirstAdministratorRefusedError,
    FirstAdministrators,
)
from brain.identity.roles import Role, RoleGrant
from brain.ops.leases import SealedSecret
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.setup_routes import APPOINTMENT_PATH, NOT_GIVEN, PRINCIPAL_PREFIX, unkept
from brain.setup_wizard import StepId, apply_install, settings_from, step_for
from brain.sign_in_routes import FINISH_PATH
from tests.fixtures.http_client import Response
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_app_wiring import Realm, wired_app
from tests.unit.test_keycloak_tokens import ISSUER, token
from tests.unit.test_setup_wizard import (
    ADMIN_ANSWERS,
    COMPANY_ANSWERS,
    HOSTED_ANSWERS,
    INSIDE,
    LOCAL_ANSWERS,
    SECRET,
    SOURCE_ANSWERS,
    WRONG,
    an_enrolment,
    answered,
)
from tests.unit.test_sign_in_routes import audited

#: The installer's own Keycloak subject. Opaque, as a `sub` is.
INSTALLER = "9a8b7c6d-0000-4000-8000-0000000000cc"

EVERY_SCREEN: Mapping[StepId, Mapping[str, str]] = {
    StepId.COMPANY: COMPANY_ANSWERS,
    StepId.ADMINISTRATOR: ADMIN_ANSWERS,
    StepId.STAFF_SOURCE: SOURCE_ANSWERS,
    StepId.MODEL_PROVIDER: LOCAL_ANSWERS,
}


@dataclass
class Store:
    """An `Appointer` in memory: counts what it has appointed, and can lose a race."""

    held: int = 0
    beaten: bool = False
    appointed: list[tuple[RoleGrant, str, str]] = field(default_factory=list)

    async def administrators(self, now: datetime) -> int:
        del now
        return self.held

    async def appoint(self, grant: RoleGrant, *, display_name: str, trace_id: str = "") -> None:
        if self.beaten or self.held:
            raise FirstAdministratorRefusedError(AppointmentRefusal.ALREADY_ADMINISTERED)
        self.appointed.append((grant, display_name, trace_id))
        self.held += 1


def body(
    *,
    code: str = SECRET,
    answers: Mapping[StepId, Mapping[str, str]] = EVERY_SCREEN,
    skipped: tuple[StepId, ...] = (StepId.CONNECTIONS,),
    **extra: object,
) -> dict[str, Any]:
    return {
        "setup_code": code,
        "answers": {key.value: dict(values) for key, values in answers.items()},
        "skipped": [one.value for one in skipped],
        **extra,
    }


@pytest.fixture
def carried(monkeypatch: pytest.MonkeyPatch) -> Mapping[str, str]:
    """The running install carrying exactly what the answered draft sets."""
    values = settings_from(answered())
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def minted_settings(**more: Any) -> Settings:
    """A setup code minted five minutes ago by the real clock."""
    minted = datetime.now(UTC) - timedelta(minutes=5)
    return Settings(
        env="development", setup_secret=SealedSecret(SECRET), setup_issued_at=minted, **more
    )


@contextmanager
def serving(store: Store | None, *, with_code: bool = True) -> Iterator[TestClient]:
    app = create_app(minted_settings() if with_code else Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.first_administrators = store
        yield c


def appointing(c: TestClient, sent: Mapping[str, Any]) -> Response:
    response: Response = c.post(APPOINTMENT_PATH, json=dict(sent))
    return response


def refusal(answer: Response) -> dict[str, Any]:
    """One refusal body with the per-request trace id taken out, its presence asserted."""
    found = dict(answer.json())
    assert "trace_id" in found
    found["trace_id"] = "<per request>"
    return found


#: The one refusal before the answers, as a finished install gives it.
def nothing_here() -> dict[str, Any]:
    with serving(Store(held=1)) as c:
        return refusal(appointing(c, body()))


# ------------------------------------------------------------------------------ the route


def test_the_setup_code_holder_appoints_the_first_administrator_and_is_sent_to_finish(
    carried: Mapping[str, str],
) -> None:
    """The positive case the refusals below need. Delete this and a route that refuses everybody
    passes every other test here, and no install ever gets an administrator."""
    del carried
    store = Store()
    with serving(store) as c:
        answer = appointing(c, body())

    assert answer.status_code == 200
    view = answer.json()
    assert view["finish_path"] == FINISH_PATH
    assert view["principal_id"].startswith(PRINCIPAL_PREFIX)
    assert len(view["principal_id"]) > len(PRINCIPAL_PREFIX) + 16
    [(grant, name, trace_id)] = store.appointed
    assert (grant.principal_id, grant.role) == (view["principal_id"], Role.SUPER_ADMIN)
    assert name == ADMIN_ANSWERS["full_name"]
    assert trace_id == answer.headers["x-trace-id"]


@pytest.mark.parametrize("code", [WRONG, "", "x" * 64])
def test_a_wrong_or_missing_setup_code_is_refused_as_nothing_here_and_appoints_nobody(
    carried: Mapping[str, str], code: str
) -> None:
    """A wrong code, a blank one and a plausible one, each refused exactly as a finished install
    is. Delete this and the appointment either admits whoever finds the address or tells them
    whether their code was right."""
    del carried
    store = Store()
    with serving(store) as c:
        answer = appointing(c, body(code=code, answers={}, skipped=()))

    assert answer.status_code == 404
    assert refusal(answer) == nothing_here()
    assert store.appointed == []


def test_an_install_with_no_setup_code_has_no_appointment(carried: Mapping[str, str]) -> None:
    """An install whose environment names no setup code refuses the right code the one way.
    Delete this and a development machine or a long-finished install could be appointed on."""
    del carried
    store = Store()
    with serving(store, with_code=False) as c:
        answer = appointing(c, body())

    assert (answer.status_code, refusal(answer)) == (404, nothing_here())
    assert store.appointed == []


def test_a_finished_install_refuses_the_right_code_and_says_nothing_about_the_answers(
    carried: Mapping[str, str],
) -> None:
    """An install that has an administrator refuses the right code with unfinished answers in the
    same one body, so nothing about screens or settings is told. Delete this and a finished
    install answers its wizard again."""
    del carried
    store = Store(held=1)
    with serving(store) as c:
        answer = appointing(c, body(answers={}, skipped=()))

    assert (answer.status_code, refusal(answer)) == (404, nothing_here())
    assert "problems" not in answer.json()
    assert store.appointed == []


def test_a_second_appointment_is_refused_naming_nobody_and_so_is_one_that_lost_a_race(
    carried: Mapping[str, str],
) -> None:
    """The first appointment lands and a second with the same code is refused without naming the
    first administrator; an appointment whose count read zero and whose write found one already
    is the same refusal. Delete this and the setup code appoints as many administrators as it is
    presented for."""
    del carried
    store = Store()
    with serving(store) as c:
        first = appointing(c, body())
        second = appointing(c, body())
    raced = Store(beaten=True)
    with serving(raced) as c:
        lost = appointing(c, body())

    appointed = first.json()["principal_id"]
    assert (first.status_code, second.status_code, lost.status_code) == (200, 404, 404)
    assert refusal(second) == refusal(lost) == nothing_here()
    assert appointed not in second.text
    assert len(store.appointed) == 1
    assert raced.appointed == []


def test_problems_with_the_answers_are_told_by_screen_and_field_and_appoint_nobody(
    carried: Mapping[str, str],
) -> None:
    """A blank company name is told against its field with the wizard's own key, a screen never
    answered and a required screen skipped are told against the screen, and nobody is appointed.
    Delete this and an install with half its answers is appointed, or refused with nothing a
    person can act on."""
    del carried
    store = Store()
    blank = {**COMPANY_ANSWERS, "company_name": " "}
    with serving(store) as c:
        bad_field = appointing(c, body(answers={**EVERY_SCREEN, StepId.COMPANY: blank}))
        unanswered = appointing(
            c,
            body(answers={k: v for k, v in EVERY_SCREEN.items() if k is not StepId.STAFF_SOURCE}),
        )
        skipped = appointing(
            c,
            body(
                answers={k: v for k, v in EVERY_SCREEN.items() if k is not StepId.ADMINISTRATOR},
                skipped=(StepId.CONNECTIONS, StepId.ADMINISTRATOR),
            ),
        )

    blank_key = step_for(StepId.COMPANY).questions[0].field.errors["blank"]
    assert (bad_field.status_code, bad_field.json()) == (
        422,
        {"problems": [{"step": "company", "field": "company_name", "key": blank_key}]},
    )
    assert (unanswered.status_code, unanswered.json()) == (
        422,
        {"problems": [{"step": "staff_source", "field": "", "key": NOT_GIVEN}]},
    )
    assert (skipped.status_code, skipped.json()) == (
        422,
        {"problems": [{"step": "administrator", "field": "", "key": NOT_GIVEN}]},
    )
    assert store.appointed == []


def test_a_setting_the_running_install_does_not_carry_is_named_and_appoints_nobody(
    carried: Mapping[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A company name the environment file does not carry, and a required setting it does not set
    at all, are named back and nobody is appointed. Delete this and the wizard closes over answers
    kept nowhere, which is `APPOINTING_IS_THE_LAST_WRITE`'s failure."""
    del carried
    store = Store()
    monkeypatch.setenv("INSTALL_COMPANY_NAME", "Another Company")
    monkeypatch.delenv("INSTALL_OIDC_REDIRECT_URIS")
    with serving(store) as c:
        answer = appointing(c, body())

    assert (answer.status_code, answer.json()) == (
        409,
        {"unkept": ["INSTALL_COMPANY_NAME", "INSTALL_OIDC_REDIRECT_URIS"]},
    )
    assert "Another Company" not in answer.text
    assert store.appointed == []


def test_a_principal_named_in_the_request_is_refused_and_appoints_nobody(
    carried: Mapping[str, str],
) -> None:
    """See `THE_SERVER_CHOOSES_WHO_IS_APPOINTED`. Delete this and the holder of the setup code can
    appoint a member of staff the directory already holds as the widest role."""
    del carried
    store = Store()
    with serving(store) as c:
        answer = appointing(c, body(principal_id="u_somebody"))

    assert answer.status_code == 422
    assert store.appointed == []


def test_a_process_with_no_first_administrator_store_refuses_every_caller_alike(
    carried: Mapping[str, str],
) -> None:
    """With no store the right code and a wrong one get the same fault. Delete this and a process
    with no database or no issuer tells a stranger whether their code was right."""
    del carried
    with serving(None) as c:
        right, wrong = appointing(c, body()), appointing(c, body(code=WRONG))

    assert (right.status_code, wrong.status_code) == (500, 500)
    assert refusal(right) == refusal(wrong)


# ----------------------------------------------------------------- the settings, no server


def test_a_provider_key_is_carried_only_when_its_slot_holds_that_same_key() -> None:
    """A hosted install's key is kept only when the key loaded from its slot is the same one; an
    unloaded slot and a different key are both named by the slot's path, never by the key. Delete
    this and an install is appointed over a provider key nothing will ever use."""
    draft = answered(hosted=True)
    applied = apply_install(
        draft, an_enrolment(), SECRET, principal_id="u_first", administrators=0, now=INSIDE
    )
    slot = next(one for one in PROVIDER_SLOTS if one.slug == HOSTED_ANSWERS["model_provider"])
    running = dict(applied.settings)

    unloaded = unkept(applied, running)
    other = unkept(applied, {**running, slot.env_var: "j" * 40})
    same = unkept(applied, {**running, slot.env_var: HOSTED_ANSWERS["provider_key"]})

    assert (unloaded, other, same) == ((slot.path,), (slot.path,), ())
    assert all(HOSTED_ANSWERS["provider_key"] not in name for name in (*unloaded, *other))


def test_a_local_install_is_carried_when_every_setting_matches_and_not_when_one_differs() -> None:
    """The settings half on its own: a match is nothing unkept, one difference is exactly that
    name. Delete this and the confirmation can pass everything or refuse everything with the route
    tests still green on their one environment."""
    applied = apply_install(
        answered(), an_enrolment(), SECRET, principal_id="u_first", administrators=0, now=INSIDE
    )
    running = dict(applied.settings)

    assert unkept(applied, running) == ()
    assert unkept(applied, {**running, "INSTALL_PRODUCT_NAME": "Other"}) == (
        "INSTALL_PRODUCT_NAME",
    )


# ------------------------------------------------------------------------------ the wiring


def test_the_appointment_is_served_by_the_application() -> None:
    """`create_app` mounts the router itself. Held by what the path answers, for the reason
    `test_app_wiring` gives about the sign-in routes: this FastAPI does not list an included
    router's paths on `app.routes`, an unmounted path is the framework's `{"detail": ...}` 404,
    and only a mounted route answers a process with no store in `ErrorBody`. Delete this and the
    router can go unmounted, which is how every setup route before it shipped."""
    with TestClient(create_app(Settings(env="development")), raise_server_exceptions=False) as c:
        served = c.post(APPOINTMENT_PATH, json=body())
        nowhere = c.post(f"{APPOINTMENT_PATH}-not-mounted", json=body())

    assert served.status_code == 500
    assert set(served.json()) == {"message", "trace_id"}
    assert nowhere.status_code == 404
    assert "message" not in nowhere.json()


def test_the_lifespan_builds_the_store_only_where_the_finishing_screen_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a database and an issuer the store is `FirstAdministrators` over the sessions the app
    serves through; with no usable issuer there is no bindings writer and no store. Delete this
    and a process that cannot sign anybody in appoints an administrator nobody can ever be."""
    served = Realm()
    monkeypatch.setattr("brain.app.key_set_client", served.client)
    monkeypatch.setattr("brain.app.run_migrations", lambda _url: [])

    monkeypatch.setenv("INSTALL_OIDC_ISSUER", ISSUER)
    app = wired_app()
    with TestClient(app):
        built = app.state.first_administrators
        sessions = app.state.db_sessions
        writer = app.state.sign_in_bindings
    monkeypatch.delenv("INSTALL_OIDC_ISSUER")
    unwired = wired_app()
    with TestClient(unwired):
        none = (unwired.state.first_administrators, unwired.state.sign_in_bindings)

    assert isinstance(built, FirstAdministrators)
    assert built.sessions is sessions
    assert writer is not None
    assert none == (None, None)


# ------------------------------------------------------------------------------ end to end


def signed(subject: str) -> dict[str, str]:
    issued = int(time.time())
    return {
        "authorization": (
            f"Bearer {token(sub=subject, sid='sess-installer', iat=issued, exp=issued + 300)}"
        )
    }


def test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone(
    carried: Mapping[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end on a real database with nothing wired by hand: before anything, the installer's
    token is refused at `/me`; the appointment route appoints; a second appointment is refused;
    `/setup/sign-in` binds the installer's token, verified against the key set the lifespan
    fetched, to the principal the appointment returned; and `/me` then answers 200 as that
    administrator, who holds every administration capability and no other. Delete this and the
    three routes can each pass alone while an install still cannot get from the wizard to a
    signed-in person, which is where every real install was before this route."""
    del carried
    served = Realm()
    monkeypatch.setenv("INSTALL_OIDC_ISSUER", ISSUER)
    monkeypatch.setattr("brain.app.key_set_client", served.client)

    with audited("brain_setup_routes_end_to_end") as url:
        app = create_app(minted_settings(database_url=url, run_migrations=False, valkey_url=""))

        async def walk() -> dict[str, Any]:
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://brain") as c:
                    before = await c.get(f"{API_PREFIX}/me", headers=signed(INSTALLER))
                    appointed = await c.post(APPOINTMENT_PATH, json=body())
                    again = await c.post(APPOINTMENT_PATH, json=body())
                    principal_id = appointed.json().get("principal_id", "")
                    finished = await c.post(
                        FINISH_PATH,
                        headers=signed(INSTALLER),
                        json={"setup_code": SECRET, "principal_id": principal_id},
                    )
                    me = await c.get(f"{API_PREFIX}/me", headers=signed(INSTALLER))
            return {
                "before": before.status_code,
                "appointed": appointed.status_code,
                "again": again.status_code,
                "principal_id": principal_id,
                "finished": (finished.status_code, finished.json().get("outcome")),
                "me": (me.status_code, me.json().get("principal_id")),
            }

        walked = run(walk)
        granted = sql(
            url,
            "SELECT capability FROM gate.capability_grant WHERE principal_id = %s"
            " ORDER BY capability",
            walked["principal_id"],
        )

    assert (walked["before"], walked["appointed"], walked["again"]) == (401, 200, 404)
    assert walked["finished"] == (200, "bound")
    assert walked["me"] == (200, walked["principal_id"])
    assert [str(row[0]) for row in granted] == sorted(ADMINISTRATION)
