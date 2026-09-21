"""Disabling a person and enabling them again: the control, its refusals, and its cascade (M1.2.3).

The first half drives the two routes over a store in memory that asks `may` as the real one does.
The second half builds the database to head and proves the sentence on real rows: a disable ends
the person's session, refuses their next request, and takes their grants out of the resolver's
answer; an enable gives the grants back and not the session. It skips without a server, and CI
always has one.

Task ids: M1.2.3
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain import principal_state_routes
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.global_surfaces import GOVERNANCE_CONTROL
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.identity.principal_state_store import PrincipalState, StateChange
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_session_routes import Directory

DISABLE = principal_state_routes.DISABLE_PATH
ENABLE = principal_state_routes.ENABLE_PATH

#: `u_admin` holds the grant decision everywhere, `u_narrow` in web only, `u_wide` nowhere.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=GOVERNANCE_CONTROL, scope=Scope.unrestricted()),),
    "u_narrow": (Grant(capability=GOVERNANCE_CONTROL, scope=Scope.department("web")),),
    "u_wide": (),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


@dataclass
class People:
    """A `principal_state_routes.PrincipalStateStore` in memory: id to (department, disabled_at)."""

    rows: dict[str, tuple[str | None, datetime | None]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def set_disabled(
        self,
        principal_id: str,
        *,
        disabled: bool,
        may: Callable[[str | None], bool],
        by: str,
        ent_hash: str,
        trace_id: str,
    ) -> PrincipalState | None:
        self.calls.append({"who": principal_id, "disabled": disabled, "by": by})
        found = self.rows.get(principal_id)
        if found is None or not may(found[0]):
            return None
        department, was = found
        if (was is not None) == disabled:
            return PrincipalState(principal_id, department, was, StateChange.ALREADY)
        at = datetime.now(UTC)
        self.rows[principal_id] = (department, at if disabled else None)
        return PrincipalState(
            principal_id, department, at if disabled else None, StateChange.CHANGED, at
        )


@pytest.fixture
def people() -> People:
    return People(rows={"u_web": ("web", None), "u_sales": ("sales", None)})


@pytest.fixture
def client(people: People) -> Iterator[TestClient]:
    app = create_app(Settings(env="development", database_url=""))
    app.include_router(principal_state_routes.router)
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
        app.state.principal_states = people
        yield c


def auth(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp']})}"}


def test_an_administrator_disables_and_enables_somebody_and_the_second_press_changes_nothing(
    client: TestClient, people: People
) -> None:
    """The positive case for every refusal below. Delete this and a route that refuses everything
    passes them, and a disable could be written twice for one act."""
    first = client.post(DISABLE, json={"principal_id": "u_web"}, headers=auth("u_admin"))
    again = client.post(DISABLE, json={"principal_id": "u_web"}, headers=auth("u_admin"))
    back = client.post(ENABLE, json={"principal_id": "u_web"}, headers=auth("u_admin"))

    assert first.status_code == 200, first.text
    assert first.json()["disabled"] is True and first.json()["outcome"] == "changed"
    assert again.json()["outcome"] == "already"
    assert back.json()["disabled"] is False and back.json()["outcome"] == "changed"
    assert people.rows["u_web"] == ("web", None)
    assert [call["by"] for call in people.calls] == ["u_admin"] * 3


def test_a_department_holder_disables_in_their_department_and_nobody_elsewhere(
    client: TestClient, people: People
) -> None:
    """`may_disable` over the person's row, under the store's lock. Delete this and a web grant of
    the decision disables somebody in sales, which is the company's whole staff list reachable
    from one department's authority."""
    inside = client.post(DISABLE, json={"principal_id": "u_web"}, headers=auth("u_narrow"))
    outside = client.post(DISABLE, json={"principal_id": "u_sales"}, headers=auth("u_narrow"))

    assert inside.status_code == 200
    assert outside.status_code == 404
    assert people.rows["u_sales"] == ("sales", None)


def test_a_caller_without_the_decision_is_refused_before_any_store_and_alike_for_nobody(
    client: TestClient, people: People
) -> None:
    """Delete this and a caller without the authority reaches the store, and a person who does not
    exist answers differently from one out of reach."""
    refused = client.post(DISABLE, json={"principal_id": "u_web"}, headers=auth("u_wide"))
    nobody = client.post(DISABLE, json={"principal_id": "u_ghost"}, headers=auth("u_admin"))

    assert refused.status_code == nobody.status_code == 404
    assert [call["who"] for call in people.calls] == ["u_ghost"]


def test_nobody_disables_themselves(client: TestClient, people: People) -> None:
    """Delete this and an administrator can end the session they are using and leave nobody to
    undo it, which `global_surfaces.disable_principal` refuses for the same reason."""
    answer = client.post(DISABLE, json={"principal_id": "u_admin"}, headers=auth("u_admin"))

    assert answer.status_code == 409
    assert answer.json()["message"] == principal_state_routes.NOBODY_DISABLES_THEMSELVES
    assert people.calls == []


# ---------------------------------------------------------------------------- the database


def test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants() -> None:
    """M1.2.3 on real rows, as the application role. A person with a grant and a live session is
    disabled through the store: the session row is ended for the disable with the administrator
    named in the ledger, a real authority refuses the token from that session, and the resolver
    answers no grant. Enabled again: the grant is back, the ended session stays ended. Delete this
    and the cascade can be decorative, or the enable can quietly revive a session nobody opened."""
    from tests.fixtures.scratch_postgres import admin_url

    admin_url()

    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.keycloak_tokens import keycloak_authority
    from brain.identity.oidc import TokenRefusedError
    from brain.identity.principal_directory import StoredDirectory
    from brain.identity.principal_state_store import StoredPrincipalStates
    from brain.identity.sign_in_binding import sign_in_bindings
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_entitlement_store import a_grant, a_principal
    from tests.unit.test_keycloak_tokens import NOW, SUBJECT, Clock, Idp, token
    from tests.unit.test_service_accounts import through_0095
    from tests.unit.test_session_store import ENV

    with through_0095("brain_ps_cascade") as url:
        a_principal(url, "u_joiner")
        a_grant(url, "u_joiner", "read:client.hours")

        async def go() -> tuple[Any, ...]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                await sign_in_bindings(sessions, env=ENV).bind(
                    SUBJECT, principal_id="u_joiner", bound_by="u_admin", now=NOW
                )
                authority = keycloak_authority(
                    directory=StoredDirectory(sessions), get=Idp().get, clock=Clock(), env=ENV
                )
                header = f"Bearer {token(sid='kc-live')}"
                before = await authority.authenticate(header, now=NOW)
                states = StoredPrincipalStates(sessions)
                disabled = await states.set_disabled(
                    "u_joiner",
                    disabled=True,
                    may=lambda department: department == "finance",
                    by="u_admin",
                    ent_hash="ab" * 16,
                    trace_id="trace-disable",
                )
                try:
                    await authority.authenticate(header, now=NOW)
                    refused = False
                except TokenRefusedError:
                    refused = True
                held_off = await StoredEntitlements(sessions).load("u_joiner", NOW)
                enabled = await states.set_disabled(
                    "u_joiner",
                    disabled=False,
                    may=lambda department: True,
                    by="u_admin",
                    ent_hash="",
                    trace_id="trace-enable",
                )
                held_on = await StoredEntitlements(sessions).load("u_joiner", NOW)
                return before, disabled, refused, held_off, enabled, held_on
            finally:
                await engine.dispose()

        before, disabled, refused, held_off, enabled, held_on = run(go)
        rows = sql(url, "SELECT id, end_reason FROM auth.session ORDER BY id")
        entries = sql(
            url,
            "SELECT actor_id, subject, trace_id FROM obs.audit_entry"
            " WHERE action = 'session_end' ORDER BY seq",
        )
        states = state_entries(url)

    assert before.principal.id == "u_joiner"
    assert disabled is not None and disabled.outcome is StateChange.CHANGED
    assert disabled.disabled_at is not None
    assert refused is True
    assert held_off.grants == ()
    assert enabled is not None and enabled.disabled_at is None
    # Binding a sign-in also writes the member's own grants, so the one written here is looked for.
    assert "read:client.hours" in [grant.capability.value for grant in held_on.grants]
    assert rows == [("kc-live", "principal_disabled")]
    assert entries == [("u_admin", "principal:u_joiner", "trace-disable")]
    assert [(e.actor_id, e.subject, e.trace_id, dict(e.details)) for e in states] == [
        ("u_admin", "principal:u_joiner", "trace-disable", {"change": "disabled"}),
        ("u_admin", "principal:u_joiner", "trace-enable", {"change": "enabled"}),
    ]
    assert all(e.recompute_hash() == e.entry_hash for e in states)


def state_entries(url: str) -> list[Any]:
    """The `principal_state` entries, oldest first, as `AuditEntry` so each can be re-hashed."""
    from brain.audit.ledger import AuditEntry
    from tests.fixtures.scratch_postgres import sql

    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry WHERE action = 'principal_state' ORDER BY seq",
    )
    names = ("seq", "at", "actor_id", "action", "subject", "ent_hash", "trace_id", "details")
    return [
        AuditEntry(**dict(zip((*names, "prev_hash", "entry_hash"), row, strict=True)))
        for row in rows
    ]


def test_the_trigger_writes_the_details_the_recorder_writes() -> None:
    """Delete this and the entry `0095b`'s trigger writes can drift from the one
    `AuditRecorder.principal_state` writes, so a chain held in memory and the database disagree
    about what an enable looks like."""
    from brain.audit.ledger import AuditChain
    from brain.audit.record import AuditRecorder, PrincipalStateChange
    from tests.unit.test_tables import VERSIONS, migration_module

    recorder = AuditRecorder(
        AuditChain(),
        actor_id="u_admin",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: datetime.now(UTC),
    )
    for change in PrincipalStateChange:
        entry = recorder.principal_state(principal_id="u_joiner", change=change)
        assert dict(entry.details) == {"change": change.value}
    body = migration_module(VERSIONS / "0095b_principal_state_audit.py").TRIGGER_FUNCTION
    for change in PrincipalStateChange:
        assert f"'{change.value}'" in body


def test_a_press_that_changes_nothing_and_a_statement_nobody_attributed_are_recorded_honestly() -> (
    None
):
    """Exactly one entry per change. Disabling somebody already disabled writes no entry, and a
    hand-written statement with no actor set is recorded as unattributed rather than refused.
    Delete this and a second press can append a second entry for one act, or a disable at a prompt
    at midnight can fail for want of a setting."""
    from tests.fixtures.scratch_postgres import admin_url

    admin_url()
    from brain.identity.principal_state_store import StoredPrincipalStates
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_entitlement_store import a_principal
    from tests.unit.test_service_accounts import through_0095

    with through_0095("brain_ps_once") as url:
        a_principal(url, "u_one")

        async def go() -> list[Any]:
            engine = app_engine(url)
            try:
                states = StoredPrincipalStates(make_session_factory(engine))
                return [
                    await states.set_disabled(
                        "u_one",
                        disabled=True,
                        may=lambda _department: True,
                        by="u_admin",
                        ent_hash="",
                        trace_id="",
                    )
                    for _ in range(2)
                ]
            finally:
                await engine.dispose()

        first, second = run(go)
        sql(url, "UPDATE auth.principal SET disabled_at = NULL WHERE id = 'u_one'")
        sql(url, "UPDATE auth.principal SET display_name = 'Renamed' WHERE id = 'u_one'")
        states = state_entries(url)

    assert first is not None and first.outcome is StateChange.CHANGED
    assert second is not None and second.outcome is StateChange.ALREADY
    assert [(e.actor_id, dict(e.details)) for e in states] == [
        ("u_admin", {"change": "disabled"}),
        ("unattributed", {"change": "enabled", "actor": "unattributed"}),
    ]


def test_the_organisation_page_says_whether_the_reader_may_disable_and_what_it_does() -> None:
    """The Departments page draws the control from this flag and confirms with this sentence.
    Delete this and the control can be offered to nobody, or confirmed with words the API never
    said."""
    from brain.govern_people_routes import OrganisationPage
    from brain.identity.principal_state_store import A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT

    fields = OrganisationPage.model_fields
    assert fields["may_disable"].default is False
    assert fields["disabling"].default == A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT
