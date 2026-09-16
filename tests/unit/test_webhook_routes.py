"""The Webhooks screen over HTTP: who may see and change subscribers, in what order, what is said.

Driven through the real application, with the token machinery imported from
`tests/unit/test_api_routes.py` for the reason `tests/unit/test_credential_routes.py` gives. The
rows are `Records`, an in-memory `brain.ops.webhook_store.WebhookRecords` that says whether it was
asked; the vault is `tests.unit.test_credentials.Vault`. The database half, that a write reaches
the rows and the ledger, is `tests/unit/test_webhook_store.py`.

Task ids: M27.8.12
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.ops.credentials import VaultState
from brain.ops.openbao import StaticVersion, VaultRefusedError, VaultUnreachableError
from brain.ops.outbox import MANAGE_SUBSCRIBERS, EventKind, Subscriber
from brain.ops.webhook_admin import TOLD, SigningSecrets, signing_secret_ref
from brain.ops.webhook_store import (
    ChangeLine,
    DeliveryLine,
    NoActiveSubscriberError,
    Registered,
    SubscriberTakenError,
)
from brain.tables.webhook_change import WebhookChange
from brain.webhook_routes import SECRET_PATH, SUBSCRIBERS_PATH, SWITCH_OFF_PATH, WEBHOOKS_PATH
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_credentials import AT, Vault

LISTING = f"{API_PREFIX}{WEBHOOKS_PATH}"
REGISTER = f"{API_PREFIX}{SUBSCRIBERS_PATH}"

WHOLE = Scope.unrestricted()
ONE_DEPARTMENT = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))

#: What each person holds here: nothing, the capability, and a different administration grant.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    "u_narrow": (Grant(capability=MANAGE_SUBSCRIBERS, scope=ONE_DEPARTMENT),),
    "u_wide": (Grant(capability=Capability(value="admin:credential"), scope=WHOLE),),
    "u_prefix": (),
    "u_admin": (Grant(capability=MANAGE_SUBSCRIBERS, scope=WHOLE),),
    "u_elsewhere": (),
}

#: A session carrying a second factor, which an `admin:` verb needs.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}

SECRET = "whsec-SIGNING-SENTINEL-0123456789abcdefABCDEF"
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


class HeldGrants:
    """A `brain.gate.resolve.EntitlementStore` over a mapping of grants."""

    def __init__(self, grants: Mapping[str, tuple[Grant, ...]]) -> None:
        self._grants = grants

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=self._grants[principal_id])


def wiring(grants: Mapping[str, tuple[Grant, ...]]) -> Any:
    """The gate over these grants, for any route test that needs a capability and nothing else."""
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER,
            audience=AUDIENCE,
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=HeldGrants(grants),
        cache=NoCache(),
    )


def headers(pid: str, claims: Mapping[str, object] | None = None) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=claims or SECOND_FACTOR)}"}


class NoDatabase:
    """A session factory that must never be asked."""

    def __call__(self) -> Any:
        raise AssertionError("a database session was opened")


def subscriber(subscriber_id: str = "billing_bridge", *, active: bool = True) -> Subscriber:
    return Subscriber(
        subscriber_id=subscriber_id,
        endpoint="https://hooks.example.test/brain",
        secret_ref=signing_secret_ref(subscriber_id),
        kinds=(EventKind.APPROVAL_REQUESTED,),
        created_by="u_admin",
        active=active,
    )


class Records:
    """`WebhookRecords` in memory: what is registered, every write asked for, and whether it was."""

    def __init__(self, registered: tuple[Registered, ...] = ()) -> None:
        self.registered_rows = list(registered)
        self.asked = 0
        self.writes: list[tuple[str, str, str]] = []
        self.taken = False
        self.secret_times: list[datetime | None] = []

    async def registered(self) -> tuple[Registered, ...]:
        self.asked += 1
        return tuple(self.registered_rows)

    async def register(
        self,
        subscriber: Subscriber,
        *,
        actor: str,
        at: datetime,
        trace_id: str,
        ent_hash: str,
        keep_secret: Callable[[], datetime | None],
    ) -> datetime | None:
        self.asked += 1
        if self.taken:
            raise SubscriberTakenError(subscriber.subscriber_id)
        written = keep_secret()
        self.writes.append(("register", subscriber.subscriber_id, actor))
        self.registered_rows.append(
            Registered(
                subscriber=subscriber,
                created_at=at,
                deactivated_at=None,
                last_delivered_at=None,
                deliveries=(),
                changes=(),
            )
        )
        return written

    async def replace_secret(
        self,
        subscriber_id: str,
        *,
        actor: str,
        at: datetime,
        trace_id: str,
        ent_hash: str,
        keep_secret: Callable[[], datetime | None],
    ) -> datetime | None:
        self.asked += 1
        if not any(
            one.subscriber.subscriber_id == subscriber_id and one.subscriber.active
            for one in self.registered_rows
        ):
            raise NoActiveSubscriberError(subscriber_id)
        written = keep_secret()
        self.writes.append(("replace", subscriber_id, actor))
        return written

    async def switch_off(self, subscriber_id: str, *, actor: str, at: datetime) -> None:
        self.asked += 1
        for index, one in enumerate(self.registered_rows):
            if one.subscriber.subscriber_id == subscriber_id and one.subscriber.active:
                self.registered_rows[index] = Registered(
                    subscriber=subscriber(subscriber_id, active=False),
                    created_at=one.created_at,
                    deactivated_at=at,
                    last_delivered_at=None,
                    deliveries=one.deliveries,
                    changes=one.changes,
                )
                self.writes.append(("switch_off", subscriber_id, actor))
                return
        raise NoActiveSubscriberError(subscriber_id)


def a_registered(subscriber_id: str = "billing_bridge") -> Registered:
    return Registered(
        subscriber=subscriber(subscriber_id),
        created_at=LONG_AGO,
        deactivated_at=None,
        last_delivered_at=None,
        deliveries=(
            DeliveryLine(
                kind=EventKind.APPROVAL_REQUESTED,
                state="exhausted",
                attempts=0,
                occurred_at=LONG_AGO,
                last_attempt_at=None,
                reason="not sent: refused",
            ),
        ),
        changes=(
            ChangeLine(
                change=WebhookChange.REGISTERED,
                changed_by="u_admin",
                changed_at=LONG_AGO,
                secret_written_at=AT,
            ),
        ),
    )


@pytest.fixture
def app() -> Iterator[FastAPI]:
    built: FastAPI = create_app(Settings(env="development"))
    yield built


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring(GRANTS)
        app.state.db_sessions = NoDatabase()
        yield c


def attach(app: FastAPI, records: Records, vault: Vault | None) -> None:
    app.state.webhook_records = records
    app.state.signing_secrets = SigningSecrets(vault)


def registration(**changed: object) -> dict[str, object]:
    body: dict[str, object] = {
        "subscriber_id": "new_bridge",
        "endpoint": "https://hooks.example.test/new",
        "kinds": [EventKind.OPERATION_SETTLED.value],
        "secret": SECRET,
    }
    body.update(changed)
    return body


def post(c: TestClient, pid: str, path: str, body: object = None, **kw: Any) -> Response:
    response: Response = c.post(path, headers=headers(pid, **kw), json=body)
    return response


def secret_path(subscriber_id: str) -> str:
    return API_PREFIX + SECRET_PATH.replace("{subscriber_id}", subscriber_id)


def switch_off_path(subscriber_id: str) -> str:
    return API_PREFIX + SWITCH_OFF_PATH.replace("{subscriber_id}", subscriber_id)


def without_trace(response: Response) -> dict[str, Any]:
    found = dict(response.json())
    found.pop("trace_id", None)
    return found


# ---------------------------------------------------------------------- who may


def test_a_reader_who_may_not_manage_is_shown_what_an_empty_install_shows_and_nothing_is_asked(
    app: FastAPI, client: TestClient
) -> None:
    """`brain.console.subscribers.A_READER_WHO_MAY_NOT_MANAGE_IS_SHOWN_WHAT_AN_EMPTY_INSTALL_SHOWS`,
    and the store and the vault not asked. The positive sibling is the manager's page. Delete this
    and the listing is read first and filtered after, so a broken install reads differently."""
    records, vault = Records((a_registered(),)), Vault(version=StaticVersion(written_at=AT))
    attach(app, records, vault)
    for pid in ("u_none", "u_narrow", "u_wide"):
        page = client.get(LISTING, headers=headers(pid))
        assert page.status_code == 200, pid
        body = page.json()
        assert (body["manageable"], body["subscribers"], body["findings"]) == (False, [], [])
    assert records.asked == 0 and vault.asked == []
    managed = client.get(LISTING, headers=headers("u_admin")).json()
    assert managed["manageable"] is True
    assert [one["subscriber_id"] for one in managed["subscribers"]] == ["billing_bridge"]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (REGISTER, registration()),
        (secret_path("billing_bridge"), {"secret": SECRET}),
        (switch_off_path("billing_bridge"), None),
    ],
)
def test_a_change_by_somebody_who_may_not_manage_is_refused_before_it_is_judged(
    app: FastAPI, client: TestClient, path: str, body: object
) -> None:
    """One refusal, the taxonomy's own, before the body is judged, the store asked or the vault
    written. Delete this and a stranger's malformed registration gets a 422 naming the fields, which
    confirms the surface and what it takes."""
    records, vault = Records((a_registered(),)), Vault()
    attach(app, records, vault)
    for pid in ("u_none", "u_wide"):
        refused = post(client, pid, path, body)
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    bad = post(client, "u_none", REGISTER, registration(subscriber_id="", secret=""))
    assert bad.status_code == 404
    assert records.writes == [] and vault.written == []


def test_a_password_only_session_holding_the_capability_changes_nothing(
    app: FastAPI, client: TestClient
) -> None:
    """The capability is an `admin:` verb, so `gate.admission` withholds it from a session with no
    second factor. Delete this and the capability can be respelled `write:` to make a form work."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    weak = post(client, "u_admin", REGISTER, registration(), claims={"amr": ["pwd"]})
    assert weak.status_code == 404
    assert records.writes == []
    assert post(client, "u_admin", REGISTER, registration()).status_code == 200
    assert MANAGE_SUBSCRIBERS.value.startswith("admin:")


# ------------------------------------------------------------------ what is shown


def test_a_manager_sees_where_each_subscriber_points_whether_its_secret_is_held_and_its_outcomes(
    app: FastAPI, client: TestClient
) -> None:
    """Every field the screen draws, from the store and the vault's metadata, and nothing that
    could be a secret or a record id. Delete this and a secret held reads as not held, or a
    delivery's record id rides out on the page."""
    attach(app, Records((a_registered(),)), Vault(version=StaticVersion(written_at=AT)))
    body = client.get(LISTING, headers=headers("u_admin")).json()
    [one] = body["subscribers"]
    assert one["endpoint"] == "https://hooks.example.test/brain"
    assert one["kinds"] == [EventKind.APPROVAL_REQUESTED.value]
    assert (one["active"], one["created_by"]) == (True, "u_admin")
    assert one["secret_held"] is True
    assert datetime.fromisoformat(one["secret_written_at"]) == AT
    assert [d["state"] for d in one["deliveries"]] == ["exhausted"]
    assert set(one["deliveries"][0]) == {
        "kind",
        "state",
        "attempts",
        "occurred_at",
        "last_attempt_at",
        "reason",
    }
    assert [c["change"] for c in one["changes"]] == ["registered"]
    assert body["vault"] == VaultState.READY.value
    assert body["kinds"] == [kind.value for kind in EventKind]
    assert body["inbound"]["channels"] and body["inbound"]["automation_path"].startswith(API_PREFIX)
    assert "secret_path" not in json.dumps(body) and "webhooks/" not in json.dumps(body)


@pytest.mark.parametrize(
    ("vault", "state"),
    [
        (None, VaultState.ABSENT),
        (Vault(fail=VaultUnreachableError("x")), VaultState.UNREACHABLE),
        (Vault(fail=VaultRefusedError("x", status=403)), VaultState.REFUSED),
    ],
)
def test_a_vault_that_cannot_be_asked_leaves_every_secret_unknown_rather_than_not_held(
    app: FastAPI, client: TestClient, vault: Vault | None, state: VaultState
) -> None:
    """None is not known, never not held, and the page says which vault problem it is. Delete this
    and a silent vault reads as a subscriber with no secret, which sends somebody to replace one."""
    attach(app, Records((a_registered(),)), vault)
    body = client.get(LISTING, headers=headers("u_admin")).json()
    assert [one["secret_held"] for one in body["subscribers"]] == [None]
    assert (body["vault"], body["vault_told"]) == (state.value, TOLD[state])


# -------------------------------------------------------------------- the writes


def test_a_registration_is_written_with_the_reader_as_its_creator_and_its_secret_kept(
    app: FastAPI, client: TestClient
) -> None:
    """The subscriber is written by the store, its secret at its own slot, its creator the person
    asking whatever the body says. Delete this and a registration writes a row with no secret, or
    a secret at the wrong slot, and answers 200."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    answered = post(client, "u_admin", REGISTER, registration())
    assert answered.status_code == 200
    body = answered.json()
    assert (body["subscriber_id"], body["change"]) == ("new_bridge", "registered")
    assert datetime.fromisoformat(body["secret_written_at"]) == AT
    assert records.writes == [("register", "new_bridge", "u_admin")]
    assert records.registered_rows[0].subscriber.created_by == "u_admin"
    assert records.registered_rows[0].subscriber.secret_ref.path == "webhooks/new_bridge"
    assert vault.written == [("webhooks/new_bridge", {"signing_secret": SECRET})]


def test_a_bad_registration_is_told_every_problem_and_nothing_is_written(
    app: FastAPI, client: TestClient
) -> None:
    """Delete this and a registration refused by the table after the vault was written reaches a
    person as a 500."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    refused = post(
        client,
        "u_admin",
        REGISTER,
        registration(subscriber_id="Bad-Id", endpoint="http://x", kinds=[], secret="short"),
    )
    assert refused.status_code == 422
    assert [(p["field"], p["code"]) for p in refused.json()["problems"]] == [
        ("subscriber_id", "not_an_id"),
        ("endpoint", "refused_address"),
        ("kinds", "none"),
        ("secret", "too_short"),
    ]
    assert records.asked == 0 and vault.written == []


def test_an_id_already_taken_is_a_problem_on_the_id(app: FastAPI, client: TestClient) -> None:
    """A field the person fixes, not a conflict they read about. Delete this and a taken id answers
    a 500 from the store's exception."""
    records = Records()
    records.taken = True
    attach(app, records, Vault())
    refused = post(client, "u_admin", REGISTER, registration())
    assert refused.status_code == 422
    assert [(p["field"], p["code"]) for p in refused.json()["problems"]] == [
        ("subscriber_id", "taken")
    ]


@pytest.mark.parametrize(
    ("vault", "status", "state"),
    [
        (None, 409, VaultState.ABSENT),
        (Vault(fail=VaultRefusedError("x", status=403)), 409, VaultState.REFUSED),
        (Vault(fail=VaultUnreachableError("x")), 503, VaultState.UNREACHABLE),
    ],
)
def test_a_vault_that_cannot_keep_the_secret_writes_nothing_and_says_which_problem(
    app: FastAPI, client: TestClient, vault: Vault | None, status: int, state: VaultState
) -> None:
    """No vault is refused before the store is asked; a vault that fails inside the store's
    transaction leaves nothing recorded. Delete this and a registration with no secret answers 200.
    """
    records = Records()
    attach(app, records, vault)
    for path, body in ((REGISTER, registration()),):
        answered = post(client, "u_admin", path, body)
        assert answered.status_code == status
        assert without_trace(answered) == {"message": TOLD[state]}
    assert records.writes == []


def test_replacing_a_secret_writes_the_new_one_and_a_switched_off_subscriber_is_refused(
    app: FastAPI, client: TestClient
) -> None:
    """Delete this and a rotation on a subscriber that is off writes a secret nothing will sign
    with, and answers 200."""
    records, vault = Records((a_registered(),)), Vault()
    attach(app, records, vault)
    replaced = post(client, "u_admin", secret_path("billing_bridge"), {"secret": SECRET})
    assert replaced.status_code == 200
    assert replaced.json()["change"] == "secret_replaced"
    assert vault.written == [("webhooks/billing_bridge", {"signing_secret": SECRET})]
    short = post(client, "u_admin", secret_path("billing_bridge"), {"secret": "x"})
    assert short.status_code == 422
    assert post(client, "u_admin", switch_off_path("billing_bridge")).status_code == 200
    again = post(client, "u_admin", secret_path("billing_bridge"), {"secret": SECRET})
    assert (again.status_code, without_trace(again)) == (404, {"message": Absent.public_message})
    assert len(vault.written) == 1


def test_switching_off_records_who_did_it_and_a_second_switch_off_is_refused(
    app: FastAPI, client: TestClient
) -> None:
    """Delete this and a second press moves the recorded instant to whoever clicked second, or an
    id with a slash in it reaches the store."""
    records = Records((a_registered(),))
    attach(app, records, Vault())
    first = post(client, "u_admin", switch_off_path("billing_bridge"))
    assert first.status_code == 200
    assert first.json()["change"] == "switched_off"
    assert records.writes == [("switch_off", "billing_bridge", "u_admin")]
    assert post(client, "u_admin", switch_off_path("billing_bridge")).status_code == 404
    assert post(client, "u_admin", switch_off_path("Not-An-Id")).status_code == 404
    assert len(records.writes) == 1


def test_no_response_body_and_no_log_line_carries_the_secret(
    app: FastAPI,
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every answer these routes give, a refused body included, read for the sentinel. The writes
    are proved to have happened, so a router that stored nothing cannot pass. Delete this and a
    refused registration echoes the secret it was sent."""
    caplog.set_level(logging.DEBUG)
    records, vault = Records((a_registered(),)), Vault()
    attach(app, records, vault)
    answers = [
        post(client, "u_admin", REGISTER, registration()),
        post(client, "u_admin", REGISTER, registration(subscriber_id="")),
        post(client, "u_admin", REGISTER, {"subscriber_id": 1, "secret": SECRET}),
        post(client, "u_none", REGISTER, registration()),
        post(client, "u_admin", secret_path("billing_bridge"), {"secret": SECRET}),
        post(client, "u_admin", secret_path("billing_bridge"), {"secret": SECRET + " x"}),
        client.get(LISTING, headers=headers("u_admin")),
    ]
    assert vault.written, "nothing was written, so the absence of the secret proves nothing"
    out = capsys.readouterr()
    for answered in answers:
        assert SECRET not in answered.text
        assert SECRET not in json.dumps(dict(answered.headers))
    assert SECRET not in out.out + out.err + caplog.text
