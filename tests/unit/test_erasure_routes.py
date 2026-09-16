"""What the Retention and erasure screen needs beside the report, over HTTP.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py`. What is under test is who is told they may act, what each act is
said to do, and that the two lists nothing records are sentences. The write routes themselves are
`tests/unit/test_retention_routes.py`'s.

**The authorities are spelled out here rather than imported**, so a repointed capability in
`brain.retention_routes` is a failure in this file rather than a constant compared with itself.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditAction
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.erasure_routes import (
    ERASURES_ARE_NOT_RECORDED,
    EXPORTS_ARE_NOT_RECORDED,
    HOLDING,
    LIFTING,
    RELEASING,
    WITHDRAWING,
)
from brain.identity.bearer import TokenAuthority
from brain.ops import erasure
from brain.ops.retention import HORIZONS
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

CONTROLS = f"{API_PREFIX}/govern/retention/controls"

RETENTION_READ = Capability(value="read:retention_policy")
RELEASE = Capability(value="admin:retention")
HOLD = Capability(value="admin:legal_hold")
CONFIGURATION = plane_capability(Plane.CONFIGURATION)


def _everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


#: `u_admin` may read and do both. `u_narrow` may read and release. `u_wide` may read and hold.
#: `u_elsewhere` may read and do neither. `u_prefix` holds both authorities over one department
#: only, which is not an authority over everything. `u_none` holds both authorities and not the
#: screen, and must learn nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": _everywhere(RETENTION_READ, CONFIGURATION, RELEASE, HOLD),
    "u_narrow": _everywhere(RETENTION_READ, CONFIGURATION, RELEASE),
    "u_wide": _everywhere(RETENTION_READ, CONFIGURATION, HOLD),
    "u_elsewhere": _everywhere(RETENTION_READ, CONFIGURATION),
    "u_prefix": (
        *_everywhere(RETENTION_READ, CONFIGURATION),
        Grant(capability=RELEASE, scope=Scope.department("web")),
        Grant(capability=HOLD, scope=Scope.department("web")),
    ),
    "u_none": _everywhere(RELEASE, HOLD),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


@pytest.fixture
def client() -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        yield c


#: A session with a second factor. `brain.gate.admission` withholds every `admin:` capability
#: from a password-only sign-in, so without it no authority here would ever be held.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


def get(c: TestClient, pid: str, *, second_factor: bool = True) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR if second_factor else None)
    response: Response = c.get(CONTROLS, headers={"authorization": f"Bearer {token}"})
    return response


def test_each_authority_draws_its_own_controls_and_neither_draws_the_other(
    client: TestClient,
) -> None:
    """Releasing and holding are two authorities, each held over everything, and each flag
    follows its own. A department-scoped grant of both is neither.

    Delete this and one flag could follow the other authority, drawing a release button for
    somebody who may only place holds, or a department's grant could draw a control over every
    store in the company."""
    flags = {
        pid: (get(client, pid).json()["may_release"], get(client, pid).json()["may_hold"])
        for pid in ("u_admin", "u_narrow", "u_wide", "u_elsewhere", "u_prefix")
    }

    assert flags == {
        "u_admin": (True, True),
        "u_narrow": (True, False),
        "u_wide": (False, True),
        "u_elsewhere": (False, False),
        "u_prefix": (False, False),
    }


def test_a_password_only_session_is_drawn_no_retention_control(client: TestClient) -> None:
    """The flags are the retention module's authorities as the gate admitted them, and the gate
    withholds an `admin:` capability from a sign-in with no second factor. Delete this and a flag
    computed from the raw grants would draw controls the write route then refuses."""
    body = get(client, "u_admin", second_factor=False).json()

    assert (body["may_release"], body["may_hold"]) == (False, False)


def test_a_caller_who_may_not_open_the_screen_learns_nothing_about_what_they_could_do(
    client: TestClient,
) -> None:
    """Holding both authorities without the screen is refused like holding nothing, so the
    refusal says nothing about the authorities. Delete this and the flags could be answered to
    anybody, which tells a caller which retention powers they hold on a screen they may not
    open."""
    refused = get(client, "u_none")
    admitted = get(client, "u_elsewhere")

    assert refused.status_code == 404
    assert "may_release" not in refused.text
    assert admitted.status_code == 200


def test_every_act_is_described_in_the_words_a_confirmation_shows(client: TestClient) -> None:
    """The four sentences travel, each about its own act. Delete this and a confirmation could be
    drawn with no consequence, which `docs/admin-console.md` refuses for a destructive action."""
    body = get(client, "u_admin").json()

    assert body["releasing"] == RELEASING
    assert body["withdrawing"] == WITHDRAWING
    assert body["holding"] == HOLDING
    assert body["lifting"] == LIFTING
    assert "removes" in RELEASING and "hold" in RELEASING
    assert "removes nothing" in WITHDRAWING
    assert "lifted" in HOLDING and "lifted" in LIFTING


def test_the_export_log_and_the_deletion_queue_are_sentences_while_nothing_records_either(
    client: TestClient,
) -> None:
    """Held against the two facts outside this module that make the sentences true: the audit
    vocabulary has no export action, and nothing in the erasure module implements the eraser.
    The day either changes this goes red, which is the day the page should show a list.

    Delete this and the sentences outlive the facts behind them, telling an administrator nothing
    is recorded on the day something is."""
    body = get(client, "u_admin").json()

    assert body["exports"] == EXPORTS_ARE_NOT_RECORDED
    assert body["erasures"] == ERASURES_ARE_NOT_RECORDED
    assert not any("export" in one.value for one in AuditAction)
    implementations = [
        name
        for name, value in vars(erasure).items()
        if isinstance(value, type)
        and value is not erasure.StoreEraser
        and callable(getattr(value, "erase", None))
    ]
    assert implementations == []


def test_how_long_each_kind_of_thing_is_kept_is_every_declared_horizon(client: TestClient) -> None:
    """Delete this and the table could drop a class, and a report line naming that class would
    have nothing on the page saying what it means."""
    kept = get(client, "u_elsewhere").json()["kept"]

    assert [one["data_class"] for one in kept] == [one.data_class.value for one in HORIZONS]
    assert all(one["because"].strip() for one in kept)
