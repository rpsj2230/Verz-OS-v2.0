"""A principal's reach is loaded from the one resolver in the database, at the caller's instant,
as the application role, and an answer that is not a reach is a failure and never an empty set.

The first half reads resolver answers into sets and needs no server. The second builds `0002` and
`0003` in a database of its own and drives `brain.gate.entitlement_store.StoredEntitlements` as
the application role. It is stamped at `0001`, because `0001` creates pgvector and everything else
it leaves is what `tests.fixtures.scratch_postgres.fresh` makes by hand, and it skips when there is
no server, as every file using that fixture does.

Task ids: none
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg
import pytest
from sqlalchemy import text

from brain.cache import PostgresVersionSource
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Clause, Op, Scope
from brain.gate.entitlement_store import (
    PRINCIPAL_SETTING,
    EntitlementStoreError,
    StoredEntitlements,
    entitlements_from,
)
from brain.gate.resolve import Resolved, resolve
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import drop, fresh, migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine

#: Far outside any plausible wall clock, on purpose. See CLAUDE.md on a fixture with a date in it.
NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)
READ_PRICES = "read:price_list"
READ_NAMES = "read:client.name"
WEB_ONLY = Scope(clauses=(Clause(field="sku", op=Op.PREFIX, value="WEB-"),))


# ------------------------------------------------------------------------ the answer


def test_a_resolver_answer_is_the_reach_it_describes() -> None:
    """The positive case for both refusals below. Delete it and a reader that raises on every
    answer passes them, and no reach is ever loaded."""
    answer = {
        "principal_id": "u_reader",
        "not_after": "2999-01-01T00:00:00+00:00",
        "grants": [
            {"capability": {"value": READ_PRICES}, "scope": WEB_ONLY.model_dump(mode="json")}
        ],
    }

    reach = entitlements_from(answer)

    assert reach.principal_id == "u_reader"
    assert reach.not_after == datetime(2999, 1, 1, tzinfo=UTC)
    assert reach.scope_for(Capability(value=READ_PRICES), LONG_AGO) == WEB_ONLY


def test_a_resolver_answer_that_is_not_an_object_is_the_stores_failure() -> None:
    """A null from the resolver is a fault, and it is refused as this store's own error rather
    than whatever `dict(None)` raises. Delete this and the guard can go, and the error that
    reaches the log names a Python builtin instead of the resolver."""
    with pytest.raises(EntitlementStoreError, match="NoneType"):
        entitlements_from(None)


def test_a_grant_that_does_not_construct_fails_the_whole_reach_rather_than_being_dropped() -> None:
    """A dropped grant would be a reach one grant smaller than the database holds, served as
    though it were whole, and a wholly malformed answer would be an empty set. Delete this and a
    malformed answer can narrow somebody's access with nothing anywhere reporting it."""
    answer = {
        "principal_id": "u_reader",
        "not_after": None,
        "grants": [{"capability": {"value": "not a capability"}, "scope": {"clauses": []}}],
    }

    with pytest.raises(EntitlementStoreError, match="u_reader"):
        entitlements_from(answer)


# ------------------------------------------------------------------------ the database


@contextmanager
def resolver(database: str) -> Iterator[str]:
    """A fresh database holding `auth.principal`, the grant tables and the resolver."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0001")
        migrate(database, "upgrade", "0003")
        yield scratch
    finally:
        drop(database)


def with_store[T](url: str, work: Callable[[StoredEntitlements], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(StoredEntitlements(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def loaded(url: str, principal_id: str, now: datetime = NOW) -> EntitlementSet:
    return with_store(url, lambda store: store.load(principal_id, now))


def a_principal(
    url: str, principal_id: str, *, employment: str = "staff", not_after: datetime | None = None
) -> None:
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department,"
        " not_after) VALUES (%s, 'human', %s, %s, 'finance', %s)",
        principal_id,
        employment,
        f"Person {principal_id}",
        not_after,
    )


def scope_json(scope: Scope | None) -> str:
    return json.dumps((scope or Scope.unrestricted()).model_dump(mode="json"))


def a_grant(
    url: str,
    principal_id: str,
    capability: str,
    *,
    scope: Scope | None = None,
    not_after: datetime | None = None,
) -> None:
    sql(
        url,
        "INSERT INTO gate.capability_grant"
        " (principal_id, capability, scope, granted_by, reason, not_after)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        principal_id,
        capability,
        scope_json(scope),
        "u_seed",
        "a test granted it",
        not_after,
    )


def a_pack(url: str, principal_id: str, *capabilities: str) -> None:
    [(pack_id,)] = sql(
        url,
        "INSERT INTO gate.capability_pack (name, description, capabilities)"
        " VALUES (%s, %s, %s) RETURNING id",
        "pricing",
        "a pack a test assigned",
        list(capabilities),
    )
    sql(
        url,
        "INSERT INTO gate.capability_pack_assignment"
        " (principal_id, pack_id, scope, granted_by, reason) VALUES (%s, %s, %s, %s, %s)",
        principal_id,
        pack_id,
        scope_json(None),
        "u_seed",
        "a test assigned it",
    )


def revoke(url: str, principal_id: str, capability: str) -> None:
    sql(
        url,
        "UPDATE gate.capability_grant SET deleted_at = now()"
        " WHERE principal_id = %s AND capability = %s",
        principal_id,
        capability,
    )


def test_the_store_connects_as_the_application_role() -> None:
    """Delete this and every test below can pass on a superuser connection, which bypasses the
    policies the store is meant to be read under."""
    with resolver("brain_es_role") as url:

        async def work(store: StoredEntitlements) -> str:
            async with store.sessions() as session:
                return str((await session.execute(text("SELECT current_user"))).scalar_one())

        assert with_store(url, work) == "brain_app"


def test_direct_grants_and_pack_members_are_the_reach_with_scopes_and_expiry_intact() -> None:
    """The positive case for everything below, through the store and not around it. Delete it and
    a store that loads nothing for anybody passes every refusal in this file."""
    with resolver("brain_es_loads") as url:
        a_principal(url, "u_reader", employment="contractor", not_after=NOW)
        a_grant(url, "u_reader", READ_PRICES, scope=WEB_ONLY)
        a_pack(url, "u_reader", READ_NAMES)
        reach = loaded(url, "u_reader", LONG_AGO)

    assert reach.principal_id == "u_reader"
    assert reach.not_after == NOW
    assert reach.scope_for(Capability(value=READ_PRICES), LONG_AGO) == WEB_ONLY
    assert reach.holds(Capability(value=READ_NAMES), LONG_AGO)


def test_a_revoked_grant_is_gone_on_the_next_load_and_the_rest_stay() -> None:
    """Revocation is the deletion of a grant and nothing else. Delete this and a store reading a
    retired row passes, and the only way left to take access away would be a deny list, which this
    system must never have."""
    with resolver("brain_es_revoked") as url:
        a_principal(url, "u_reader")
        a_grant(url, "u_reader", READ_PRICES)
        a_grant(url, "u_reader", READ_NAMES)
        before = loaded(url, "u_reader")
        revoke(url, "u_reader", READ_PRICES)
        after = loaded(url, "u_reader")

    assert before.holds(Capability(value=READ_PRICES), NOW)
    assert not after.holds(Capability(value=READ_PRICES), NOW)
    assert after.holds(Capability(value=READ_NAMES), NOW)


def test_a_grant_is_judged_expired_at_the_callers_instant() -> None:
    """`load` hands the resolver the caller's now. Delete this and the store can ask at the
    database's clock, which decides a grant ending in 2500 at a moment no caller named: held for a
    caller asking in 2999, which is exactly when it must not be."""
    ends = datetime(2500, 1, 1, tzinfo=UTC)
    with resolver("brain_es_instant") as url:
        a_principal(url, "u_reader")
        a_grant(url, "u_reader", READ_PRICES, not_after=ends)
        earlier = loaded(url, "u_reader", LONG_AGO)
        later = loaded(url, "u_reader", NOW)

    assert earlier.holds(Capability(value=READ_PRICES), LONG_AGO)
    assert not later.holds(Capability(value=READ_PRICES), LONG_AGO)


def test_a_disabled_principal_and_a_stranger_hold_nothing_and_neither_is_a_failure() -> None:
    """Holding nothing is the resolver's answer for both, and a successful read. Delete this and a
    store that raised for either would make a stranger's request a fault, which the stranger can
    tell apart from a colleague who holds nothing."""
    with resolver("brain_es_nobody") as url:
        a_principal(url, "u_disabled")
        a_grant(url, "u_disabled", READ_PRICES)
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = %s", "u_disabled")
        disabled = loaded(url, "u_disabled")
        stranger = loaded(url, "u_stranger")

    assert disabled == EntitlementSet(principal_id="u_disabled")
    assert stranger == EntitlementSet(principal_id="u_stranger")


#: `0002`'s grant policy, narrowed to the principal the transaction names.
NARROWED_TO_THE_READER: tuple[str, ...] = (
    "DROP POLICY capability_grant_live ON gate.capability_grant",
    "CREATE POLICY capability_grant_live ON gate.capability_grant FOR ALL TO brain_app"
    " USING (deleted_at IS NULL AND principal_id = current_setting('app.principal_id', true))"
    " WITH CHECK (true)",
)


def test_the_store_still_loads_under_a_policy_that_narrows_grants_to_the_principal_named() -> None:
    """The transaction is told whose grants it is reading. Delete this and that setting can go
    with every other test green, and the first policy to read it makes every reach in the company
    silently empty. The second connection proves the replacement policy narrows at all, without
    which the load proves nothing."""
    with resolver("brain_es_narrowed") as url:
        a_principal(url, "u_reader")
        a_grant(url, "u_reader", READ_PRICES)
        for statement in NARROWED_TO_THE_READER:
            sql(url, statement)
        reach = loaded(url, "u_reader")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET ROLE brain_app")
            conn.execute("SELECT set_config(%s, %s, false)", (PRINCIPAL_SETTING, "u_somebody"))
            seen = conn.execute("SELECT count(*) FROM gate.capability_grant").fetchone()

    assert reach.holds(Capability(value=READ_PRICES), NOW)
    assert seen == (0,)


class Kept:
    """An `EntitlementCache` that never forgets, so a stale entry would be served if it could be."""

    def __init__(self) -> None:
        self.kept: dict[str, EntitlementSet] = {}

    def get(self, key: str) -> EntitlementSet | None:
        return self.kept.get(key)

    def set(self, key: str, value: EntitlementSet, ttl_seconds: int) -> None:
        self.kept[key] = value


def test_a_revocation_reaches_resolve_through_this_store_and_the_bumped_version() -> None:
    """What lifespan will build, less the authority: this store, `gate.grants_version` as `0003`'s
    trigger moves it, and a cache that never forgets. Delete this and the store and the version are
    only ever proved apart, and nothing shows that a revocation retires a cached reach when both
    are real."""
    with resolver("brain_es_resolve") as url:
        a_principal(url, "u_reader")
        a_grant(url, "u_reader", READ_PRICES)
        versions = PostgresVersionSource(lambda: psycopg.connect(url))
        cache = Kept()

        async def work(store: StoredEntitlements) -> tuple[Resolved, Resolved, Resolved]:
            first = await resolve("u_reader", versions=versions, store=store, cache=cache, now=NOW)
            again = await resolve("u_reader", versions=versions, store=store, cache=cache, now=NOW)
            revoke(url, "u_reader", READ_PRICES)
            after = await resolve("u_reader", versions=versions, store=store, cache=cache, now=NOW)
            return first, again, after

        first, again, after = with_store(url, work)

    assert first.entitlements.holds(Capability(value=READ_PRICES), NOW)
    assert again.from_cache is True
    assert after.grants_version > first.grants_version
    assert after.from_cache is False
    assert not after.entitlements.holds(Capability(value=READ_PRICES), NOW)
