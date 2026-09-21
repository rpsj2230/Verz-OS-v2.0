"""An external person must carry an end date, and on it every grant, session and binding stops.

M1.8.1 names four things and each is decided in a different place, so this file holds them side by
side rather than trusting that four modules agree. Saving: `Principal` refuses a contractor or a
partner with no `not_after`, and so does `auth.principal`'s check constraint. On the date: the
reach the resolver hands the gate carries the date and holds nothing from it on; the bearer finds
nobody for a token whose person has ended, so a session in their hand is refused; and a chat
binding, which names only a principal, resolves through that same reach and so reaches nothing.

The last test builds the database to head and proves the saving half and the session half on real
rows. It skips without a server, and CI always has one.

Task ids: M1.8.1
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, Table

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.ingress import Binding, ChannelEvent, identity_hash, resolve
from brain.gate.resolve import resolve as resolve_reach
from brain.identity.oidc import TokenRefusal, TokenRefusedError
from brain.tables.identity import BOUNDED_EMPLOYMENTS, PrincipalRow

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
ENDS = datetime(2999, 6, 30, 17, 0, tzinfo=UTC)
BEFORE = ENDS - timedelta(minutes=1)
ON = ENDS
READ = Capability(value="read:client.hours")


def external(employment: Employment, not_after: datetime | None) -> Principal:
    return Principal(
        id="c_0447",
        kind=PrincipalKind.HUMAN,
        employment=employment,
        display_name="Contracted Person",
        not_after=not_after,
    )


@pytest.mark.parametrize("employment", [Employment.CONTRACTOR, Employment.PARTNER])
def test_an_external_person_cannot_be_constructed_without_an_end_date(
    employment: Employment,
) -> None:
    """The saving half, on the type every path builds. Delete this and a contractor with no end
    date is a valid object, which is the unbounded engagement the type calls the commonest rot."""
    with pytest.raises(ValidationError):
        external(employment, None)
    assert external(employment, ENDS).not_after == ENDS


def test_staff_need_no_end_date_and_the_table_names_both_external_kinds() -> None:
    """The sibling of the refusal, and the table's copy of it. Delete this and a guard refusing
    everybody without a date passes the test above, or the constraint can forget the partner."""
    assert external(Employment.STAFF, None).not_after is None
    assert set(BOUNDED_EMPLOYMENTS) == {Employment.CONTRACTOR, Employment.PARTNER}
    table = PrincipalRow.__table__
    assert isinstance(table, Table)
    [rendered] = [
        str(c.sqltext)
        for c in table.constraints
        if isinstance(c, CheckConstraint) and "not_after" in str(c.sqltext)
    ]
    assert "'contractor'" in rendered and "'partner'" in rendered
    assert "not_after IS NOT NULL" in rendered


class OneReach:
    """An `EntitlementStore` answering the external person's grant, with their end date on it."""

    async def load(self, principal_id: str, at: datetime) -> EntitlementSet:
        return EntitlementSet(
            principal_id=principal_id,
            grants=(Grant(capability=READ, scope=Scope.unrestricted()),),
            not_after=ENDS,
        )


class OneVersion:
    async def grants_version(self, principal_id: str) -> int:
        return 1


class NoCache:
    async def get(self, key: str) -> EntitlementSet | None:
        return None

    async def set(self, key: str, value: EntitlementSet, ttl_seconds: int) -> None:
        return None


def reach_at(principal_id: str, at: datetime) -> EntitlementSet:
    resolved = asyncio.run(
        resolve_reach(
            principal_id, versions=OneVersion(), store=OneReach(), cache=NoCache(), now=at
        )
    )
    return resolved.entitlements


def test_every_grant_holds_until_the_end_date_and_nothing_from_it() -> None:
    """The grant half, through the gate's resolver. Delete this and the date can be dropped between
    the store and the reach, and a contractor keeps every grant after their contract ends."""
    assert reach_at("c_0447", BEFORE).scope_for(READ, BEFORE) is not None
    assert reach_at("c_0447", ON).scope_for(READ, ON) is None


def test_a_chat_binding_reaches_nothing_on_the_end_date() -> None:
    """The binding half. A binding names a principal and nothing else, so what it can do is that
    principal's reach at the moment of the message. Delete this and a binding could carry a reach
    of its own that the end date never reaches."""
    event = ChannelEvent(
        channel=Channel.TELEGRAM,
        external_id="update-1",
        channel_identity="+10000000000",
        text="how many hours are left?",
        received_at=ON,
    )
    binding = Binding(
        channel=Channel.TELEGRAM,
        identity_hash=identity_hash(Channel.TELEGRAM, "+10000000000"),
        principal_id="c_0447",
        bound_at=BEFORE - timedelta(days=30),
    )
    found = resolve(event, {binding.identity_hash: binding})

    assert found is not None
    assert reach_at(found.principal_id, BEFORE).scope_for(READ, BEFORE) is not None
    assert reach_at(found.principal_id, ON).scope_for(READ, ON) is None


def test_a_session_token_is_refused_on_the_end_date_through_the_real_bearer() -> None:
    """The session half. Delete this and a token minted during the engagement keeps working after
    it, for as long as the session lives, which is up to ten hours."""
    from brain.identity.keycloak_tokens import keycloak_authority
    from tests.unit.test_keycloak_tokens import ISSUER, NOW, SUBJECT, Clock, Idp, token

    ends = NOW + timedelta(minutes=2)

    class Directory:
        async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
            if issuer != ISSUER or subject != SUBJECT:
                return None
            return external(Employment.CONTRACTOR, ends)

    authority = keycloak_authority(
        directory=Directory(), get=Idp().get, clock=Clock(), env={"INSTALL_OIDC_ISSUER": ISSUER}
    )
    header = f"Bearer {token(sid='kc-contract')}"

    before = asyncio.run(authority.authenticate(header, now=NOW))
    with pytest.raises(TokenRefusedError) as after:
        asyncio.run(authority.authenticate(header, now=ends + timedelta(seconds=30)))

    assert before.principal.id == "c_0447"
    assert after.value.reason is TokenRefusal.NO_PRINCIPAL


def test_the_database_refuses_an_external_row_without_a_date_and_ends_its_reach_on_it() -> None:
    """Both halves on real rows, as the application role: an undated contractor insert is refused
    by the constraint, and a dated one's grant comes back from the resolver carrying the date, held
    before it and not on it. Delete this and the constraint can be dropped by a later migration
    with the type still refusing, which is the one path, a hand-written statement, that skips it."""
    from tests.fixtures.scratch_postgres import admin_url

    admin_url()
    import psycopg

    from brain.gate.entitlement_store import StoredEntitlements
    from brain.session import make_session_factory
    from tests.fixtures.retirable import retirable
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_entitlement_store import a_grant, a_principal

    with retirable("brain_m181_end_date") as url:
        with pytest.raises(psycopg.errors.CheckViolation):
            a_principal(url, "c_undated", employment="contractor", not_after=None)
        a_principal(url, "c_dated", employment="contractor", not_after=ENDS)
        a_grant(url, "c_dated", READ.value)

        async def go() -> EntitlementSet:
            engine = app_engine(url)
            try:
                return await StoredEntitlements(make_session_factory(engine)).load(
                    "c_dated", BEFORE
                )
            finally:
                await engine.dispose()

        loaded = run(go)
        undated = sql(url, "SELECT count(*) FROM auth.principal WHERE id = 'c_undated'")

    assert undated == [(0,)]
    assert loaded.not_after == ENDS
    assert loaded.scope_for(READ, BEFORE) is not None
    assert loaded.scope_for(READ, ON) is None
