"""The setup wizard's appointment route appoints the first administrator once, in e81c8b9's order,
and a fresh install then reaches a signed-in administrator through HTTP alone.

Three halves. The route through `TestClient` with an in-memory store, the one confirmation left
without a server, and the lifespan's wiring against a realm over a mock transport. Then one test
on a real database, skipped without `DATABASE_URL`, that goes appointment, `/setup/sign-in` with a
token signed by the test key through the lifespan's own key set client, and `/me`, driven through
`httpx.ASGITransport` for the reason `tests/unit/test_app_wiring.py` gives.

**The provider key is kept in the vault now**, through `tests/unit/test_credentials.Vault`
attached as the process's store, and M27.8.7's half on this route is
`test_no_appointment_answer_and_no_log_line_carries_the_provider_key_or_the_setup_code`.

**The `carried` fixture removes every setting the wizard collects from the environment**, so the
whole file now runs against an install that carries none of them. Before 2026-09-16 it set them
all, because the route refused an appointment whose answers the environment did not already
match. What replaced that is in `brain.ops.install_settings`.

The setup code is minted five minutes before the wall clock, because both setup routes read it
and the window is an hour.

Task ids: M42.5.6, M42.5.10, M42.5.14, M27.8.7
"""

from __future__ import annotations

import logging
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
from brain.install import BY_NAME, hold_saved, saved_values, value_of
from brain.ops.credentials import KEY_FIELD, Credentials
from brain.ops.install_settings import key_for
from brain.ops.install_settings import refresh as refresh_install_settings
from brain.ops.leases import SealedSecret
from brain.ops.openbao import VaultRefusedError, VaultUnreachableError
from brain.session import make_session_factory
from brain.setup_routes import (
    APPOINTMENT_PATH,
    NOT_GIVEN,
    PRINCIPAL_PREFIX,
    NotKeptReason,
    ProviderKeyKept,
    keep_provider_key,
    slot_for,
)
from brain.setup_wizard import StepId, apply_install, settings_from, step_for
from brain.sign_in_routes import FINISH_PATH
from tests.fixtures.http_client import Response
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_app_wiring import Realm, wired_app
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credentials import KEY, Vault
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

#: Every screen, with a hosted provider whose key is the sentinel nothing else could contain.
HOSTED: Mapping[StepId, Mapping[str, str]] = {
    **EVERY_SCREEN,
    StepId.MODEL_PROVIDER: {**HOSTED_ANSWERS, "provider_key": KEY},
}

#: The variable the hosted provider's key is read as, from the slot rather than a literal.
VARIABLE = "ANTHROPIC_API_KEY"


@dataclass
class Store:
    """An `Appointer` in memory: counts what it has appointed, and can lose a race.

    It keeps the settings it was handed as well, because the route's job is now to hand them
    over rather than to compare them, and a store that dropped them would let a route that
    never passed them pass every test here.
    """

    held: int = 0
    beaten: bool = False
    appointed: list[tuple[RoleGrant, str, str]] = field(default_factory=list)
    kept: list[Mapping[str, str]] = field(default_factory=list)

    async def administrators(self, now: datetime) -> int:
        del now
        return self.held

    async def appoint(
        self,
        grant: RoleGrant,
        *,
        display_name: str,
        trace_id: str = "",
        settings: Mapping[str, str] | None = None,
    ) -> None:
        if self.beaten or self.held:
            raise FirstAdministratorRefusedError(AppointmentRefusal.ALREADY_ADMINISTERED)
        self.appointed.append((grant, display_name, trace_id))
        self.kept.append(dict(settings or {}))
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


@pytest.fixture(autouse=True)
def carried(monkeypatch: pytest.MonkeyPatch) -> Iterator[Mapping[str, str]]:
    """An install carrying **none** of the wizard's settings, in the environment or saved.

    The opposite of what this fixture was before 2026-09-16, and the change is the point of it.
    The route used to require the running install to already carry every value the person typed,
    so every test here had to set them first; the route now writes them, so the fixture's job is
    to prove there was nothing there to read. It also puts `brain.install`'s saved values back,
    because those live on the module and a test that left one set would configure the next.
    """
    values = settings_from(answered())
    for name in values:
        monkeypatch.delenv(name, raising=False)
    # And the provider key, so a key in the shell running the suite cannot carry an appointment
    # that the install under test does not.
    monkeypatch.delenv(VARIABLE, raising=False)
    before = hold_saved({})
    yield values
    hold_saved(before)


def minted_settings(**more: Any) -> Settings:
    """A setup code minted five minutes ago by the real clock."""
    minted = datetime.now(UTC) - timedelta(minutes=5)
    return Settings(
        env="development", setup_secret=SealedSecret(SECRET), setup_issued_at=minted, **more
    )


@contextmanager
def serving(
    store: Store | None, *, with_code: bool = True, credentials: Credentials | None = None
) -> Iterator[TestClient]:
    app = create_app(minted_settings() if with_code else Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.first_administrators = store
        if credentials is not None:
            app.state.credentials = credentials
        yield c


@dataclass
class Watching(Store):
    """A `Store` that records what the vault held at the moment it was asked to appoint."""

    vault: Vault = field(default_factory=Vault)
    held_when_appointed: list[list[tuple[str, dict[str, str]]]] = field(default_factory=list)

    async def appoint(
        self,
        grant: RoleGrant,
        *,
        display_name: str,
        trace_id: str = "",
        settings: Mapping[str, str] | None = None,
    ) -> None:
        self.held_when_appointed.append(list(self.vault.written))
        await super().appoint(
            grant, display_name=display_name, trace_id=trace_id, settings=settings
        )


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
    """The positive case the refusals below need, over an install whose environment carries none
    of these settings: the appointment lands, the answers are handed to the store to write beside
    it, and this process resolves them afterwards without being restarted.

    Delete this and a route that refuses everybody passes every other test here, and no install
    ever gets an administrator."""
    store = Store()
    with serving(store) as c:
        before = value_of("INSTALL_COMPANY_NAME")
        answer = appointing(c, body())
        after = value_of("INSTALL_COMPANY_NAME")

    assert before == BY_NAME["INSTALL_COMPANY_NAME"].default
    assert after == COMPANY_ANSWERS["company_name"]
    assert store.kept == [dict(carried)]
    assert dict(saved_values()) == dict(carried)
    assert answer.status_code == 200
    view = answer.json()
    assert view["finish_path"] == FINISH_PATH
    assert view["provider_key"] == ProviderKeyKept.NOT_ASKED
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


def test_a_hosted_install_with_a_vault_keeps_the_key_before_anybody_is_appointed(
    carried: Mapping[str, str],
) -> None:
    """The case the old 409 stood in for. The key is written to its slot under the field start-up
    reads, the vault already holds it at the moment `appoint` is called, this process is handed it
    afterwards, and the finishing screen is told it is in use. Nothing had to be set in the
    environment first.

    Delete this and the wizard can go back to refusing a key the environment does not carry, or
    write the key after the door has closed, where a vault that refuses leaves an install nobody
    can finish."""
    del carried
    env: dict[str, str] = {}
    store = Watching()
    with serving(store, credentials=Credentials(store.vault, environ=env)) as c:
        answer = appointing(c, body(answers=HOSTED))

    assert answer.status_code == 200
    assert answer.json()["provider_key"] == ProviderKeyKept.IN_USE
    assert store.vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    assert store.held_when_appointed == [[("providers/anthropic", {KEY_FIELD: KEY})]]
    assert env == {VARIABLE: KEY}
    assert len(store.appointed) == 1


def test_a_key_the_environment_file_outranks_is_kept_and_the_finish_is_told_so(
    carried: Mapping[str, str],
) -> None:
    """The owner's staging install, where the key was set in the environment by hand. It is written
    to the vault all the same, this process is not handed it, and the finishing screen is told the
    file's value wins until its line is removed. Delete this and that install finishes believing
    the key it typed is the one in use."""
    del carried
    env = {VARIABLE: "sk-set-by-hand"}
    vault = Vault()
    outranked = Credentials(vault, outranking=frozenset({VARIABLE}), environ=env)
    with serving(Store(), credentials=outranked) as c:
        answer = appointing(c, body(answers=HOSTED))

    assert (answer.status_code, answer.json()["provider_key"]) == (200, ProviderKeyKept.OUTRANKED)
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    assert env == {VARIABLE: "sk-set-by-hand"}


@pytest.mark.parametrize(
    ("raised", "reason"),
    [
        (VaultUnreachableError("did not answer"), NotKeptReason.VAULT_UNREACHABLE),
        (VaultRefusedError("refused", status=403), NotKeptReason.VAULT_REFUSED),
    ],
)
def test_a_vault_that_is_silent_or_refuses_appoints_nobody_and_says_which(
    carried: Mapping[str, str], raised: Exception, reason: NotKeptReason
) -> None:
    """Nobody is appointed, so the wizard stays open to be sent again once the vault is fixed, and
    the reason says which fix. Delete this and a key that was never stored is followed by a closed
    wizard and an install that cannot answer a question."""
    del carried
    env: dict[str, str] = {}
    store = Store()
    with serving(store, credentials=Credentials(Vault(fail=raised), environ=env)) as c:
        answer = appointing(c, body(answers=HOSTED))

    assert (answer.status_code, answer.json()) == (
        409,
        {"unkept": ["providers/anthropic"], "variables": [VARIABLE], "reason": reason},
    )
    assert store.appointed == []
    assert env == {}
    assert dict(saved_values()) == {}


def test_a_key_with_a_space_inside_it_appoints_nobody_and_nothing_reaches_the_vault(
    carried: Mapping[str, str],
) -> None:
    """The store judges the paste before it writes, and the wizard's own checks do not look inside
    a key, so this is where a bad copy is caught. Delete this and a broken key is written, the
    install is appointed over it, and the first question fails as unauthenticated."""
    del carried
    vault = Vault()
    store = Store()
    spaced = {**HOSTED, StepId.MODEL_PROVIDER: {**HOSTED_ANSWERS, "provider_key": f"{KEY} {KEY}"}}
    with serving(store, credentials=Credentials(vault, environ={})) as c:
        answer = appointing(c, body(answers=spaced))

    assert (answer.status_code, answer.json()["reason"]) == (409, NotKeptReason.NOT_A_KEY)
    assert vault.written == []
    assert store.appointed == []


def test_an_install_with_no_vault_is_told_so_and_appoints_nobody(
    carried: Mapping[str, str],
) -> None:
    """The 409 that is left, named by the slot's path, the variable and the reason, and never by
    the key. Delete this and an install with no vault is appointed over a key nothing will ever
    read, which is the belief `A_PROVIDER_KEY_IS_KEPT_BEFORE_THE_DOOR_CLOSES` is about."""
    del carried
    store = Store()
    with serving(store) as c:
        answer = appointing(c, body(answers=HOSTED))

    assert (answer.status_code, answer.json()) == (
        409,
        {
            "unkept": ["providers/anthropic"],
            "variables": [VARIABLE],
            "reason": NotKeptReason.NO_VAULT,
        },
    )
    assert KEY not in answer.text
    assert store.appointed == []
    assert dict(saved_values()) == {}


def test_an_install_with_no_vault_finishes_when_its_environment_already_carries_that_key(
    carried: Mapping[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling of the 409, and how an install that runs no vault still finishes: its
    environment already carries the same key, which it will read on every start. Delete this and
    such an install can never be appointed, because nothing else could keep the key for it."""
    del carried
    monkeypatch.setenv(VARIABLE, KEY)
    store = Store()
    with serving(store) as c:
        answer = appointing(c, body(answers=HOSTED))

    assert answer.status_code == 200
    assert answer.json()["provider_key"] == ProviderKeyKept.FROM_ENVIRONMENT
    assert len(store.appointed) == 1


def test_a_key_is_not_handed_to_this_process_by_an_appointment_that_was_refused(
    carried: Mapping[str, str],
) -> None:
    """The key is written before `appoint`, which is the order that keeps a refused vault from
    closing the wizard. The cost is stated in the route: an appointment that then loses the race
    has written a key. What it must not do is hand that key to this process, where it would be a
    key nobody was appointed to choose. Delete this and the hand-over can move above `appoint`."""
    del carried
    env: dict[str, str] = {}
    vault = Vault()
    with serving(Store(beaten=True), credentials=Credentials(vault, environ=env)) as c:
        lost = appointing(c, body(answers=HOSTED))

    assert (lost.status_code, refusal(lost)) == (404, nothing_here())
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    assert env == {}


def test_no_appointment_answer_and_no_log_line_carries_the_provider_key_or_the_setup_code(
    carried: Mapping[str, str],
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M27.8.7 on the wizard's path. Every answer the appointment gives a hosted install, driven
    with the sentinel key: kept, outranked, silent, refusing, no vault, a bad paste, a key over the
    wizard's length cap, a body in the wrong shape carrying the key, and a setup code over its cap.
    Every body and header is searched, and so is standard output and the standard library's log.

    **The positive half:** the vault holds the key afterwards, the kept line and the refusals were
    logged. And the setup code is searched for too, because before `NoEchoRoute` a code over its
    cap came back in the 422 that refused it. Delete this and a leak in the answer nobody looked at
    ships, on the one screen a stranger with the address can reach."""
    del carried
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    seen: list[str] = []

    def record(response: Response) -> int:
        seen.append(response.text)
        seen.extend(f"{name}: {value}" for name, value in response.headers.items())
        return response.status_code

    kept = Vault()
    too_long = {
        **HOSTED,
        StepId.MODEL_PROVIDER: {**HOSTED_ANSWERS, "provider_key": KEY + "k" * 1000},
    }
    wrong_shape = body(answers=HOSTED)
    wrong_shape["answers"]["model_provider"] = KEY
    long_code = f"{SECRET}{KEY}{'c' * 200}"

    with serving(Store(), credentials=Credentials(kept, environ={})) as c:
        assert record(appointing(c, body(answers=HOSTED))) == 200
    outranked = Credentials(Vault(), outranking=frozenset({VARIABLE}), environ={})
    with serving(Store(), credentials=outranked) as c:
        assert record(appointing(c, body(answers=HOSTED))) == 200
    for failing in (VaultUnreachableError("x"), VaultRefusedError("x", status=403)):
        with serving(Store(), credentials=Credentials(Vault(fail=failing), environ={})) as c:
            assert record(appointing(c, body(answers=HOSTED))) == 409
    with serving(Store()) as c:
        assert record(appointing(c, body(answers=HOSTED))) == 409
    spaced = {**HOSTED, StepId.MODEL_PROVIDER: {**HOSTED_ANSWERS, "provider_key": f"{KEY} x"}}
    with serving(Store(), credentials=Credentials(Vault(), environ={})) as c:
        assert record(appointing(c, body(answers=spaced))) == 409
        assert record(appointing(c, body(answers=too_long))) == 422
        assert record(appointing(c, wrong_shape)) == 422
        assert record(appointing(c, body(answers=HOSTED, code=long_code))) == 422

    written = capsys.readouterr()
    logged = "\n".join([written.out, written.err, caplog.text])
    everything = "\n".join([*seen, logged])
    assert KEY not in everything
    assert SECRET not in everything
    assert kept.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    assert "credential kept" in logged
    assert "appointment refused" in logged


def test_a_setting_the_environment_does_not_carry_no_longer_refuses_the_appointment(
    carried: Mapping[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling of the 409, and the whole point of this change. An environment that carries a
    different company name and no redirect URI at all was a 409 until 2026-09-16; it is now an
    appointment, and the saved answers win over the file afterwards.

    Delete this and the settings can go back to being confirmed against the environment, with the
    positive test above still green because its fixture leaves the environment empty."""
    store = Store()
    monkeypatch.setenv("INSTALL_COMPANY_NAME", "Another Company")
    with serving(store) as c:
        answer = appointing(c, body())
        resolved = value_of("INSTALL_COMPANY_NAME")

    assert answer.status_code == 200
    assert resolved == COMPANY_ANSWERS["company_name"]
    assert store.kept == [dict(carried)]


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


def test_with_no_vault_a_key_is_accepted_only_when_the_environment_carries_that_same_key() -> None:
    """Compared in constant time, and an unset variable and a different key are both the same
    refusal. Held on the function rather than through the route, so the three environments are
    asked of one draft. Delete this and an install with no vault is appointed over a key nothing
    will ever use, or refused over the one its environment does carry."""
    draft = answered(hosted=True)
    applied = apply_install(
        draft, an_enrolment(), SECRET, principal_id="u_first", administrators=0, now=INSIDE
    )
    slot = slot_for(applied)
    assert slot is not None
    none = Credentials(None)

    async def ask(env: Mapping[str, str]) -> NotKeptReason | None:
        return await keep_provider_key(slot, applied, none, trace_id="t", env=env)

    unset = run(lambda: ask({}))
    other = run(lambda: ask({VARIABLE: "j" * 40}))
    same = run(lambda: ask({VARIABLE: HOSTED_ANSWERS["provider_key"]}))

    assert (slot.path, slot.provider.env_var) == ("providers/anthropic", VARIABLE)
    assert (unset, other, same) == (NotKeptReason.NO_VAULT, NotKeptReason.NO_VAULT, None)


def test_a_local_install_has_no_key_to_keep_whatever_its_environment_or_vault_say() -> None:
    """The sibling: an install that keeps every question on its own hardware carries no key, so
    there is no slot, the vault is never asked, and the finish is told nothing was asked for.

    Delete this and a local install can be refused for a vault it does not need."""
    applied = apply_install(
        answered(), an_enrolment(), SECRET, principal_id="u_first", administrators=0, now=INSIDE
    )

    assert applied.settings
    assert slot_for(applied) is None


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


def read_back(url: str) -> dict[str, str]:
    """What a process that never served the appointment loads from this install's table.

    Its own engine and its own session factory, which is what makes it evidence about a
    different process rather than about the one that has the values in memory already.
    """

    async def go() -> dict[str, str]:
        engine = app_engine(url)
        try:
            return dict(await refresh_install_settings(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


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
    administrator, who holds every administration capability and no other.

    **And the wizard is completed with values the environment does not carry**, which is the half
    added on 2026-09-16: `carried` removes every one of them, the appointment is not refused for
    it, the answers are in `ops.setting` afterwards, and a session factory that never saw the
    write loads them back and resolves them through `value_of`.

    Delete this and the three routes can each pass alone while an install still cannot get from
    the wizard to a signed-in person, which is where every real install was before this route,
    or the settings can be written to a table nothing reads."""
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
        keys = sql(url, "SELECT key FROM ops.setting WHERE deleted_at IS NULL ORDER BY key")
        hold_saved({})
        elsewhere = read_back(url)

    assert (walked["before"], walked["appointed"], walked["again"]) == (401, 200, 404)
    assert walked["finished"] == (200, "bound")
    assert walked["me"] == (200, walked["principal_id"])
    assert [str(row[0]) for row in granted] == sorted(ADMINISTRATION)
    assert [str(row[0]) for row in keys] == sorted(key_for(name) for name in carried)
    assert elsewhere == dict(carried)
    assert value_of("INSTALL_COMPANY_NAME", {}) == COMPANY_ANSWERS["company_name"]
