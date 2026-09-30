"""Reading a stored trace with the payload role the caller's own token carries.

Two sides of one role. The realm half is in `tests/unit/test_keycloak_realm.py`: the role is
declared, and it is the only realm role a console token can carry. This file is the application
half: `payload_roles_of` reads that role off a verified token and no other, reads the claim the
realm writes, and returns nothing that could carry a capability; and the route, against the trace
store at head, reads a trace for a person whose token carries the role, with the read on record
first, and answers everybody else as it answers a trace that does not exist, writing nothing.

Task ids: M32.1.2.4
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.api import API_PREFIX
from brain.identity.oidc import VerifiedClaims, assert_no_capability_from_claims
from brain.ops.tracing import MASKED_PAYLOADS, PAYLOAD_ROLE
from brain.trace_routes import (
    REALM_ACCESS_CLAIM,
    TRACE_READ_PATH,
    payload_roles_of,
)
from brain.trace_routes import router as trace_router

ROOT = Path(__file__).resolve().parents[2]

#: Far outside any plausible wall clock, for CLAUDE.md's reason about fixtures with dates.
AT = datetime(2999, 1, 1, tzinfo=UTC)


def claims(extra: dict[str, Any]) -> VerifiedClaims:
    from types import MappingProxyType

    return VerifiedClaims(
        issuer="https://issuer.invalid/realms/brain",
        subject="1f2e3d4c-0000-4000-8000-00000000000b",
        audience=("brain-api",),
        issued_at=AT,
        expires_at=AT,
        session_id="sess-1",
        key_id="k1",
        algorithm="RS256",
        verified_at=AT,
        claims=MappingProxyType(extra),
    )


# ------------------------------------------------------------------------ without a server
def test_the_payload_role_is_read_off_a_token_and_no_other_role_is() -> None:
    """`ONLY_THE_PAYLOAD_ROLE_IS_READ_OFF_A_SIGN_IN`: a token carrying the payload role beside
    others yields the payload role alone; one without it, or with the claim missing or misshapen,
    yields nothing; and the function's type cannot carry a capability. Delete this and a token
    could bring any Keycloak role into the application, or a malformed claim could raise on every
    request from somebody who holds no role at all."""
    held = claims({REALM_ACCESS_CLAIM: {"roles": [PAYLOAD_ROLE, "default-roles-brain", "admin"]}})
    assert payload_roles_of(held) == frozenset({PAYLOAD_ROLE})
    for without in (
        {REALM_ACCESS_CLAIM: {"roles": ["default-roles-brain", f"{PAYLOAD_ROLE}-readonly"]}},
        {REALM_ACCESS_CLAIM: {"roles": PAYLOAD_ROLE}},
        {REALM_ACCESS_CLAIM: [PAYLOAD_ROLE]},
        {"roles": [PAYLOAD_ROLE]},
        {},
    ):
        assert payload_roles_of(claims(without)) == frozenset(), without
    assert_no_capability_from_claims(payload_roles_of)


def test_the_claim_read_is_the_claim_the_realm_writes() -> None:
    """The one realm-role mapper in the realm writes the claim this module reads. Delete this and
    the realm and the application can name two different claims, and every holder of the role is
    refused with nothing anywhere saying why."""
    realm = json.loads((ROOT / "ops" / "keycloak" / "realm-export.json").read_text("utf-8"))
    written = [
        mapper["config"]["claim.name"]
        for scope in realm["clientScopes"]
        for mapper in scope.get("protocolMappers") or []
        if mapper.get("protocolMapper") == "oidc-usermodel-realm-role-mapper"
    ]
    assert written == [f"{REALM_ACCESS_CLAIM}.roles"]


# ------------------------------------------------------------------------- with a server
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_trace_routes") as url:
        yield url


TRACE = "trace-routes-read-1"


def _app(url: str) -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from brain.app import Settings, create_app
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_application_sessions
    from tests.fixtures.console_http import gate_wiring

    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(trace_router)
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    app.state.gate = gate_wiring({})
    app.state.db_sessions = make_application_sessions(make_app_engine(normalise_database_url(url)))
    return client


def _read(client: Any, *, role: bool, trace: str = TRACE, reason: str = "incident") -> Any:
    from tests.unit.test_api_routes import token_for

    extra: dict[str, object] = {"sid": "sess-1"}
    if role:
        extra[REALM_ACCESS_CLAIM] = {"roles": [PAYLOAD_ROLE]}
    token = token_for("u_wide", claims=extra)
    return client.post(
        f"{API_PREFIX}{TRACE_READ_PATH.format(trace_id=trace)}",
        json={"reason": reason},
        headers={"authorization": f"Bearer {token}"},
    )


def _reads(url: str, trace: str) -> int:
    from tests.fixtures.scratch_postgres import sql

    return int(sql(url, "SELECT count(*) FROM obs.trace_read WHERE trace_id = %s", trace)[0][0])


@pytest.mark.needs_db
def test_a_person_whose_token_carries_the_payload_role_reads_the_trace_after_its_row(
    head: str,
) -> None:
    """The positive case, end to end: a token carrying the role reads the stored graph, masked,
    and the read is on record against the person with their reason. Delete this and the route
    could refuse everybody, which every refusal test below would read as working."""
    from tests.fixtures.scratch_postgres import sql

    sql(
        head,
        "INSERT INTO obs.trace_step (trace_id, step, parent, kind, name, attributes, payload_in,"
        " payload_out) VALUES (%s, 0, NULL, 'request', 'answer', '{}'::jsonb, %s, %s)",
        TRACE,
        MASKED_PAYLOADS[0],
        MASKED_PAYLOADS[1],
    )
    client = _app(head)
    answered = _read(client, role=True)

    assert answered.status_code == 200, answered.text
    assert [one["kind"] for one in answered.json()["steps"]] == ["request"]
    assert answered.json()["steps"][0]["payload_out"] in MASKED_PAYLOADS
    assert sql(head, "SELECT actor, reason FROM obs.trace_read WHERE trace_id = %s", TRACE) == [
        ("u_wide", "incident")
    ]


@pytest.mark.needs_db
def test_without_the_role_a_trace_is_answered_like_one_that_does_not_exist(head: str) -> None:
    """`A_REFUSED_READ_AND_A_MISSING_TRACE_ARE_ONE_ANSWER`: a token without the role asking for a
    trace that exists gets the very answer a holder of the role gets for a trace that does not,
    and its refusal writes no row. Delete this and a person without the role could tell which
    requests were traced by asking, or leave a row saying they read what they never did."""
    from tests.fixtures.scratch_postgres import sql

    sql(
        head,
        "INSERT INTO obs.trace_step (trace_id, step, parent, kind, name, attributes, payload_in,"
        " payload_out) VALUES ('trace-routes-read-2', 0, NULL, 'request', 'answer', '{}'::jsonb,"
        " %s, %s) ON CONFLICT DO NOTHING",
        MASKED_PAYLOADS[0],
        MASKED_PAYLOADS[0],
    )
    client = _app(head)
    refused = _read(client, role=False, trace="trace-routes-read-2")
    missing = _read(client, role=True, trace="trace-routes-nothing-here")

    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]
    assert _reads(head, "trace-routes-read-2") == 0
    assert _reads(head, "trace-routes-nothing-here") == 1
