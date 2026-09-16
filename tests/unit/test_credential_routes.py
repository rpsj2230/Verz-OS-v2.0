"""Setting a credential over HTTP, and listing which are held: who may, in what order, and that
nothing sent ever comes back out.

Driven through the real application, with the token machinery, the directory and the key source
imported from `tests/unit/test_api_routes.py` for the reason `test_routing_routes` gives: what is
under test is a capability, and a second copy of a token builder is a second place for a token to
be minted subtly differently. The vault is `tests/unit/test_credentials.Vault`, attached to
`app.state.credentials` after the lifespan has run, with an environment of its own so no test
writes to the process that runs the suite.

**M27.8.7 is `test_no_response_body_and_no_log_line_carries_the_credential`.** It drives every
answer this router can give with one sentinel value, reads every body, every header, standard
output, standard error and the standard library's log records, and finds the sentinel in none of
them, and it proves the write happened, so a router that logged nothing and stored nothing could
not pass it.

Task ids: M27.8.7
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX, KEPT_ERROR_KEYS
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.credential_routes import (
    CREDENTIAL_AUTHORITY,
    CREDENTIALS_PATH,
    CredentialKeptView,
    SlotView,
)
from brain.ops.credentials import (
    KEY_FIELD,
    SLOTS,
    TOLD,
    Credentials,
    InUse,
    VaultState,
    told_in_use,
)
from brain.ops.openbao import StaticVersion, VaultRefusedError, VaultUnreachableError
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_credentials import AT, KEY, Vault

LISTING = f"{API_PREFIX}{CREDENTIALS_PATH}"
ANTHROPIC = f"{LISTING}/providers/anthropic"

WHOLE = Scope.unrestricted()
ONE_DEPARTMENT = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))

#: What each person holds here. `u_narrow` holds the capability over one department and
#: `u_wide` holds a different administration capability over everything, which are the two
#: near misses a route checking "holds an admin: grant" or "holds this one somewhere" would pass.
CREDENTIAL_GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    "u_narrow": (Grant(capability=CREDENTIAL_AUTHORITY, scope=ONE_DEPARTMENT),),
    "u_wide": (Grant(capability=Capability(value="admin:routing_matrix"), scope=WHOLE),),
    "u_prefix": (),
    "u_admin": (Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),),
    "u_elsewhere": (),
}

#: A session carrying a second factor, as a literal for the reason `test_routing_routes` gives.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


class CredentialGrants:
    """A `brain.gate.resolve.EntitlementStore` over `CREDENTIAL_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=CREDENTIAL_GRANTS[principal_id])


class NoDatabase:
    """A session factory that must never be asked, so a test can prove no table was touched."""

    def __call__(self) -> Any:
        raise AssertionError("a database session was opened")


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=CredentialGrants(),
        cache=NoCache(),
    )


@pytest.fixture
def app() -> Iterator[FastAPI]:
    built: FastAPI = create_app(Settings(env="development"))
    yield built


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = NoDatabase()
        yield c


def holding(app: FastAPI, vault: Vault | None, **more: Any) -> dict[str, str]:
    """Attach a store over `vault` with an environment of its own, and return that environment."""
    env: dict[str, str] = {}
    app.state.credentials = Credentials(vault, environ=env, **more)
    return env


def headers(pid: str, claims: Mapping[str, object] | None = None) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=claims or SECOND_FACTOR)}"}


def put(c: TestClient, pid: str, *, path: str = ANTHROPIC, body: Any = None, **kw: Any) -> Response:
    sent = {"value": KEY} if body is None else body
    response: Response = c.put(path, headers=headers(pid, **kw), json=sent)
    return response


def listed(c: TestClient, pid: str) -> Response:
    response: Response = c.get(LISTING, headers=headers(pid))
    return response


def without_trace(response: Response) -> dict[str, Any]:
    found = dict(response.json())
    assert "trace_id" in found
    found.pop("trace_id")
    return found


# ---------------------------------------------------------------------- who may
def test_a_caller_holding_nothing_is_told_credentials_are_not_there_on_both_routes(
    app: FastAPI, client: TestClient
) -> None:
    """The taxonomy's own sentence, and one refusal for both routes. A refusal saying "you may not
    set credentials" confirms the surface exists and what it is for. Delete this and the write grows
    its own sentence, and a reader and a writer can be told apart off the response."""
    vault = Vault()
    holding(app, vault)
    write, read = put(client, "u_none"), listed(client, "u_none")

    assert (write.status_code, read.status_code) == (404, 404)
    assert without_trace(write) == without_trace(read) == {"message": Absent.public_message}
    assert vault.written == [] and vault.asked == []


def test_a_grant_over_one_department_or_another_admin_grant_is_not_a_grant_to_set_a_key(
    app: FastAPI, client: TestClient
) -> None:
    """A provider key is sent with every question anybody asks, so a grant over one department is
    a grant to change what every other department's questions go out with. The positive sibling is
    `u_admin`, so a route that refuses everybody fails here. Delete this and `holds` replaces the
    test of held over everything, which reads as the same thing in review."""
    vault = Vault()
    holding(app, vault)

    assert put(client, "u_narrow").status_code == 404
    assert put(client, "u_wide").status_code == 404
    assert listed(client, "u_narrow").status_code == 404
    assert vault.written == []
    assert put(client, "u_admin").status_code == 200
    assert listed(client, "u_admin").status_code == 200


def test_a_password_only_session_holding_the_capability_cannot_set_a_credential(
    app: FastAPI, client: TestClient
) -> None:
    """The capability carries the admin verb, so `gate.admission` withholds it from a session with
    no second factor. Nothing here implements that and nothing here may route around it, and the way
    it would be routed around is a capability spelled `write:`. Delete this and that spelling reads
    as making the capability match what the screen does."""
    vault = Vault()
    holding(app, vault)

    weak = put(client, "u_admin", claims={"amr": ["pwd"]})
    assert weak.status_code == 404
    assert vault.written == []
    assert put(client, "u_admin").status_code == 200
    assert CREDENTIAL_AUTHORITY.value.startswith("admin:")


@pytest.mark.parametrize(
    "vault",
    [None, Vault(fail=VaultUnreachableError("x")), Vault(fail=VaultRefusedError("x", status=403))],
)
def test_a_caller_who_may_not_manage_credentials_cannot_tell_what_the_vault_is_doing(
    app: FastAPI, client: TestClient, vault: Vault | None
) -> None:
    """The capability is asked before the vault is. A caller refused on an install with no vault,
    a silent one and a refusing one gets one body, and the vault is never asked. Delete this and
    the check moves below the vault's, and a stranger reads the state of the install off a 409, a
    503 and a 404."""
    holding(app, vault)
    refused = put(client, "u_none")
    assert (refused.status_code, without_trace(refused)) == (
        404,
        {"message": Absent.public_message},
    )
    if vault is not None:
        assert vault.written == [] and vault.asked == []


def test_a_slot_that_does_not_exist_is_the_same_refusal_and_nothing_is_written(
    app: FastAPI, client: TestClient
) -> None:
    """A closed list of slots, and a name outside it is the refusal every other failure before the
    vault gets. Delete this and a path such as `connectors/creds` reaches the store, which then
    relies on the vault client's prefix refusal alone."""
    vault = Vault()
    holding(app, vault)
    for path in (f"{LISTING}/providers/nobody", f"{LISTING}/connectors/xero"):
        refused = put(client, "u_admin", path=path)
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    assert vault.written == []


# -------------------------------------------------------------------- the write
def test_setting_a_key_writes_the_slot_and_answers_that_it_is_held_and_when(
    app: FastAPI, client: TestClient
) -> None:
    """The positive case the refusals need, followed to where it lands: the vault holds the value
    under the field start-up reads, this process's environment holds it, and the answer carries the
    slot, that it is held, the vault's time, and what that means for the other processes. Delete
    this and a route that refuses everybody passes the rest of the file."""
    vault = Vault()
    env = holding(app, vault)

    answer = put(client, "u_admin", body={"value": f"{KEY}\n"})

    assert answer.status_code == 200
    assert answer.json() == {
        "slot": "providers/anthropic",
        "held": True,
        "set_at": AT.isoformat().replace("+00:00", "Z"),
        "in_use": "here",
        "told": told_in_use(SLOTS["providers/anthropic"], InUse.HERE),
    }
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    assert env == {"ANTHROPIC_API_KEY": KEY}
    assert set(CredentialKeptView.model_fields) == {"slot", "held", "set_at", "in_use", "told"}


def test_a_key_the_environment_file_outranks_is_kept_and_said_not_to_be_in_use_yet(
    app: FastAPI, client: TestClient
) -> None:
    """The staging install's case. The environment set the variable before the vault was asked,
    and will on every start, so the key is written, this process is not handed it, and the answer
    names the line to remove. Delete this and the console reports a rotation as in use while the
    file's key goes on being sent."""
    vault = Vault()
    env = holding(app, vault, outranking=frozenset({"ANTHROPIC_API_KEY"}))
    env["ANTHROPIC_API_KEY"] = "sk-from-the-file"

    answer = put(client, "u_admin")

    assert answer.status_code == 200
    assert answer.json()["in_use"] == "outranked"
    assert "Remove ANTHROPIC_API_KEY" in answer.json()["told"]
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    assert env == {"ANTHROPIC_API_KEY": "sk-from-the-file"}


def test_a_bad_paste_is_told_by_code_and_in_words_and_nothing_is_written(
    app: FastAPI, client: TestClient
) -> None:
    """Validation before the write, with an error that says what to do. Delete this and a key with
    a space in it replaces a working one and every question fails as unauthenticated."""
    vault = Vault()
    env = holding(app, vault)

    answer = put(client, "u_admin", body={"value": f"{KEY} {KEY}"})

    assert answer.status_code == 422
    [problem] = answer.json()["problems"]
    assert (problem["field"], problem["code"]) == ("value", "not_one_piece")
    assert "Copy it again" in problem["message"]
    assert (vault.written, env) == ([], {})


def test_an_install_with_no_vault_is_told_so_in_words_and_no_table_is_touched(
    app: FastAPI, client: TestClient
) -> None:
    """`brain.tables.config` refuses a secret in a table, and this keeps that refusal: the database
    session factory raises if it is opened at all. The sentence names the two settings. Delete this
    and a fallback to `ops.setting` for an install without a vault reads as helpful."""
    env = holding(app, None)

    answer = put(client, "u_admin")

    assert answer.status_code == 409
    assert without_trace(answer) == {
        "slot": "providers/anthropic",
        "vault": "absent",
        "message": TOLD[VaultState.ABSENT],
    }
    assert answer.json()["trace_id"] == answer.headers["x-trace-id"]
    assert env == {}


@pytest.mark.parametrize(
    ("raised", "status", "state"),
    [
        (VaultUnreachableError("did not answer"), 503, VaultState.UNREACHABLE),
        (VaultRefusedError("refused", status=403), 409, VaultState.REFUSED),
    ],
)
def test_a_silent_vault_and_a_refusing_one_are_answered_apart_and_neither_is_in_use(
    app: FastAPI, client: TestClient, raised: Exception, status: int, state: VaultState
) -> None:
    """A silent vault is a source that could not be reached, which is a 503 in this taxonomy; a
    refusal is a state of the install, a 409. Each carries the sentence for its state, and this
    process is handed nothing. Delete this and a key that was never stored is put to use here."""
    env = holding(app, Vault(fail=raised))

    answer = put(client, "u_admin")

    assert answer.status_code == status
    assert without_trace(answer) == {
        "slot": "providers/anthropic",
        "vault": state.value,
        "message": TOLD[state],
    }
    assert env == {}


def test_a_body_in_the_wrong_shape_is_refused_without_repeating_what_was_sent(
    app: FastAPI, client: TestClient
) -> None:
    """FastAPI's own 422 quotes the input it refused, which for this route is the credential. Each
    body puts the sentinel somewhere the model refuses it, and the answer keeps the location and the
    type and drops the input. The positive half is the location, so an answer emptied of everything
    would fail. Delete this and the router can be mounted without `NoEchoRoute`."""
    vault = Vault()
    holding(app, vault)

    for body, where in (
        ({"value": KEY, "extra": KEY}, ["body", "extra"]),
        ({"value": [KEY]}, ["body", "value"]),
        ({"valu": KEY}, ["body", "value"]),
    ):
        refused = put(client, "u_admin", body=body)
        assert refused.status_code == 422
        assert KEY not in refused.text
        errors = refused.json()["detail"]
        assert where in [one["loc"] for one in errors]
        assert all(set(one) <= set(KEPT_ERROR_KEYS) for one in errors)
    assert vault.written == []


# ------------------------------------------------------------------ the listing
def test_the_listing_says_which_slots_hold_a_key_and_when_and_carries_no_field_for_one(
    app: FastAPI, client: TestClient
) -> None:
    """Every slot, in path order, each held with the vault's time. Asserted over the whole body
    and against the view's own fields, so a field added later is checked here. Delete this and the
    one read the console has for "is a key held" is unchecked."""
    holding(app, Vault(version=StaticVersion(written_at=AT)))

    answer = listed(client, "u_admin")

    assert answer.status_code == 200
    body = answer.json()
    assert (body["vault"], body["told"]) == ("ready", TOLD[VaultState.READY])
    assert [one["slot"] for one in body["slots"]] == sorted(SLOTS)
    assert all(one["held"] is True for one in body["slots"])
    assert {one["set_at"] for one in body["slots"]} == {AT.isoformat().replace("+00:00", "Z")}
    assert set(SlotView.model_fields) == {"slot", "description", "held", "set_at"}


@pytest.mark.parametrize(
    ("vault", "state"),
    [
        (None, VaultState.ABSENT),
        (Vault(fail=VaultUnreachableError("x")), VaultState.UNREACHABLE),
        (Vault(fail=VaultRefusedError("x", status=403)), VaultState.REFUSED),
    ],
)
def test_a_listing_the_vault_cannot_answer_says_why_and_calls_no_slot_empty(
    app: FastAPI, client: TestClient, vault: Vault | None, state: VaultState
) -> None:
    """Not known is not "not held". Every slot is listed with `held` null and the vault's state in
    words. Delete this and an unreachable vault lists every slot empty, and somebody pastes a key
    into a vault that is down."""
    holding(app, vault)

    body = listed(client, "u_admin").json()

    assert (body["vault"], body["told"]) == (state.value, TOLD[state])
    assert [one["slot"] for one in body["slots"]] == sorted(SLOTS)
    assert all(one["held"] is None and one["set_at"] is None for one in body["slots"])


# --------------------------------------------------------------------- M27.8.7
def test_no_response_body_and_no_log_line_carries_the_credential(
    app: FastAPI,
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every answer this router gives, driven with one sentinel: kept, outranked, a bad paste, a
    body in the wrong shape, no vault, a silent vault, a refusing vault, a caller refused, and the
    listing afterwards. Every body and every header is searched, and so is everything logged,
    through standard output where structlog writes and through the standard library's records.

    **The positive half is what makes it a test.** The vault holds the sentinel afterwards, the
    kept line names the slot and the actor, and the refusals were logged, so a router that stored
    nothing and logged nothing would fail. Delete this and M27.8.7 has no test: every other test
    here looks at one answer, and a leak is in the answer nobody looked at."""
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    seen: list[str] = []

    def record(response: Response) -> Response:
        seen.append(response.text)
        seen.extend(f"{name}: {value}" for name, value in response.headers.items())
        return response

    kept = Vault()
    holding(app, kept)
    assert record(put(client, "u_admin")).status_code == 200
    holding(app, Vault(), outranking=frozenset({"ANTHROPIC_API_KEY"}))
    assert record(put(client, "u_admin")).status_code == 200
    assert record(put(client, "u_admin", body={"value": f"{KEY} x"})).status_code == 422
    assert record(put(client, "u_admin", body={"value": KEY, "also": KEY})).status_code == 422
    holding(app, None)
    assert record(put(client, "u_admin")).status_code == 409
    holding(app, Vault(fail=VaultUnreachableError("did not answer")))
    assert record(put(client, "u_admin")).status_code == 503
    holding(app, Vault(fail=VaultRefusedError("refused", status=403)))
    assert record(put(client, "u_admin")).status_code == 409
    assert record(put(client, "u_none")).status_code == 404
    holding(app, Vault(version=StaticVersion(written_at=AT)))
    assert record(listed(client, "u_admin")).status_code == 200

    written = capsys.readouterr()
    logged = "\n".join([written.out, written.err, caplog.text])
    assert KEY not in "\n".join(seen)
    assert KEY not in logged
    assert kept.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    kept_lines = [line for line in logged.splitlines() if "credential kept" in line]
    assert len(kept_lines) == 2, logged
    assert all("providers/anthropic" in one and "u_admin" in one for one in kept_lines)
    assert "credential refused" in logged
    assert logged.count("credential not kept") == 3


# ----------------------------------------------------------------------- wiring
def test_both_routes_are_served_by_the_application() -> None:
    """`create_app` mounts the router itself. Held by what an unsigned request is answered, for the
    reason `test_setup_routes` gives: an unmounted path is the framework's bare 404, and only a
    mounted route under the prefix asks for a credential first. Delete this and the router can go
    unmounted with every test above green, because they would all be answered 404."""
    with TestClient(create_app(Settings(env="development")), raise_server_exceptions=False) as c:
        listing = c.get(LISTING)
        writing = c.put(ANTHROPIC, json={"value": KEY})
        nowhere = c.put(f"{LISTING}-not-mounted/providers/anthropic", json={"value": KEY})

    assert (listing.status_code, writing.status_code) == (401, 401)
    assert nowhere.status_code == 404
    assert KEY not in writing.text


def test_the_lifespan_builds_the_store_from_the_two_vault_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifespan hands `credentials_at_start` exactly the two settings and attaches what comes
    back. Delete this and the store can be built from nothing, so every install answers "no vault"
    whatever its environment file says, and the wizard's 409 comes back on an install that has
    one."""
    asked: list[tuple[str, str]] = []
    built = Credentials(Vault())

    def at_start(address: str, token: str) -> Credentials:
        asked.append((address, token))
        return built

    monkeypatch.setattr("brain.app.credentials_at_start", at_start)
    app = create_app(
        Settings(env="development", vault_address="http://vault:8200", vault_token="a-token")
    )
    with TestClient(app):
        attached = app.state.credentials

    assert asked == [("http://vault:8200", "a-token")]
    assert attached is built


def test_the_vault_token_is_not_in_the_settings_representation() -> None:
    """`Settings` is rendered whole into a log line at start-up and into any traceback carrying it.
    Delete this and the token is printed on every start of every install that runs a vault."""
    shown = repr(
        Settings(env="development", vault_address="http://vault:8200", vault_token="hvs.X")
    )
    assert "hvs.X" not in shown
    assert "http://vault:8200" in shown
