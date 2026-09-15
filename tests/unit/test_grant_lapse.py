"""A loaded reach says when it stops being true, read off the same rows as the reach itself, and the
resolver's own answer is what it was before `0048`.

The first half reads the SQL `0048` emits and needs no server. The second builds `0002` and `0003`
stamped at `0001` with `0048` over them, as `tests.unit.test_entitlement_store.resolver` does, and
asks the functions both as the superuser, which no policy narrows, and through
`brain.gate.entitlement_store.StoredEntitlements` as the application role. It skips when
DATABASE_URL is unset.

Task ids: none
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from brain.cache import PostgresVersionSource
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.resolve import CACHE_TTL_SECONDS, Resolved, cache_key, resolve
from tests.fixtures.retirable import LAPSE_MIGRATION, predecessor, revision_of
from tests.fixtures.scratch_postgres import drop, fresh, migrate, sql
from tests.unit.test_entitlement_store import (
    READ_NAMES,
    READ_PRICES,
    a_grant,
    a_principal,
    loaded,
    resolver,
    revoke,
    scope_json,
    with_store,
)
from tests.unit.test_resolver import resolver_body
from tests.unit.test_tables import rendered, squash

#: The caller's instant. Far from any plausible wall clock, on purpose: see CLAUDE.md on a fixture
#: with a date in it. Every date below is placed relative to it or further out still.
AT = datetime(2400, 1, 1, tzinfo=UTC)
ALREADY_LAPSED = AT - timedelta(days=1)
RETIRED_GRANT_LAPSE = AT + timedelta(days=1)
RETIRED_PACK_LAPSE = AT + timedelta(days=2)
PACK_LAPSE = datetime(2550, 1, 1, tzinfo=UTC)
GRANT_LAPSE = datetime(2600, 1, 1, tzinfo=UTC)

READ_HOURS = "read:client.hours_remaining"
READ_PHONE = "read:client.phone"
READ_ADDRESS = "read:client.address"
READ_VALUE = "read:client.contract_value"

HELD_GRANTS = "CREATE FUNCTION gate.held_grants"
RESOLVER = "CREATE OR REPLACE FUNCTION gate.resolve_entitlements"
WITH_LAPSE = "CREATE FUNCTION gate.entitlements_with_lapse"


# ------------------------------------------------------------------------ the emitted SQL


def upgrade_sql() -> str:
    return rendered("upgrade", LAPSE_MIGRATION)


def body(emitted: str, head: str) -> str:
    """One function's text from the emitted SQL, up to the next function or grant."""
    start = emitted.index(head)
    rest = start + len(head)
    ends = [
        emitted.index(marker, rest)
        for marker in ("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", "GRANT ")
        if marker in emitted[rest:]
    ]
    return squash(emitted[start : min(ends)] if ends else emitted[start:])


def test_only_the_row_function_reads_a_grant_table() -> None:
    """The one-resolver rule `0003` is built on, kept across the split. Delete this and the lapse or
    the replaced resolver can grow a query of its own over the grant tables, and the two answers
    drift apart exactly where a grant stops counting."""
    emitted = upgrade_sql()
    held = body(emitted, HELD_GRANTS)
    readers = (body(emitted, RESOLVER), body(emitted, WITH_LAPSE))

    assert "gate.capability_grant" in held
    assert "gate.capability_pack_assignment" in held
    for reader in readers:
        assert "gate.held_grants(p_principal_id, p_now)" in reader
        assert "gate.capability_grant" not in reader
        assert "gate.capability_pack_assignment" not in reader
    assert not re.findall(r"CREATE FUNCTION \w+\.resolve\w*", emitted)


def test_the_lapse_is_the_one_field_the_resolvers_own_document_leaves_to_it() -> None:
    """`EntitlementSet` validates the document the store reads, so every field has to be built by
    the resolver or beside it. Delete this and a field can be added to the type that nothing in the
    database builds, and `test_resolver`'s exemption would hide it."""
    from_0003 = {
        field for field in EntitlementSet.model_fields if f"'{field}'," in squash(resolver_body())
    }
    beside = body(upgrade_sql(), WITH_LAPSE)

    assert set(EntitlementSet.model_fields) - from_0003 == {"next_grant_lapse"}
    assert "'next_grant_lapse', (" in beside
    assert "gate.resolve_entitlements(p_principal_id, p_now) ||" in beside


def test_the_row_function_keeps_every_way_a_grant_stops_counting() -> None:
    """The four row-level facts `test_resolver` holds `0003` to, now that they live here. Delete
    this and a predicate can fall out of the lifted body while `test_resolver` still reads the
    superseded one and passes."""
    held = body(upgrade_sql(), HELD_GRANTS)

    assert "g.deleted_at IS NULL" in held
    assert "(g.not_after IS NULL OR g.not_after > p_now)" in held
    assert "k.deleted_at IS NULL" in held
    assert "(a.not_after IS NULL OR a.not_after > p_now)" in held
    assert held.count("pr.disabled_at IS NULL") == 2
    assert held.count("pr.deleted_at IS NULL") == 2


# ------------------------------------------------------------------------ the database


def a_dated_pack(
    url: str, principal_id: str, name: str, capability: str, not_after: datetime, *, retired: bool
) -> None:
    [(pack_id,)] = sql(
        url,
        "INSERT INTO gate.capability_pack (name, description, capabilities)"
        " VALUES (%s, %s, %s) RETURNING id",
        name,
        "a pack a test assigned",
        [capability],
    )
    sql(
        url,
        "INSERT INTO gate.capability_pack_assignment"
        " (principal_id, pack_id, scope, granted_by, reason, not_after)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        principal_id,
        pack_id,
        scope_json(None),
        "u_seed",
        "a test assigned it",
        not_after,
    )
    if retired:
        sql(url, "UPDATE gate.capability_pack SET deleted_at = now() WHERE id = %s", pack_id)


def a_company(url: str) -> None:
    """One reader holding every kind of dated and undated grant, and two who hold nothing dated."""
    a_principal(url, "u_reader")
    a_grant(url, "u_reader", READ_PRICES)
    a_grant(url, "u_reader", READ_NAMES, not_after=GRANT_LAPSE)
    a_grant(url, "u_reader", READ_PHONE, not_after=ALREADY_LAPSED)
    a_grant(url, "u_reader", READ_ADDRESS, not_after=RETIRED_GRANT_LAPSE)
    revoke(url, "u_reader", READ_ADDRESS)
    a_dated_pack(url, "u_reader", "pricing", READ_HOURS, PACK_LAPSE, retired=False)
    a_dated_pack(url, "u_reader", "archive", READ_VALUE, RETIRED_PACK_LAPSE, retired=True)
    a_principal(url, "u_undated")
    a_grant(url, "u_undated", READ_PRICES)
    a_principal(url, "u_contractor", employment="contractor", not_after=RETIRED_GRANT_LAPSE)
    a_grant(url, "u_contractor", READ_PRICES)


def with_lapse(url: str, principal_id: str) -> dict[str, Any]:
    [(answer,)] = sql(url, "SELECT gate.entitlements_with_lapse(%s, %s)", principal_id, AT)
    assert isinstance(answer, dict)
    return answer


def test_the_lapse_is_the_earliest_live_dated_grant_and_ignores_retired_and_lapsed_ones() -> None:
    """The fix's whole content in one principal. The soonest date among the grants the reach holds
    is the pack's, and three sooner dates are not held: a grant already lapsed, a retired grant and
    a retired pack. Asked as the superuser, which no policy narrows, and through the store as the
    application role. Delete this and the function can report the latest date, or count a row the
    reach does not hold, and the cache is capped at a date that says nothing about the reach."""
    with resolver("brain_gl_earliest") as url:
        a_company(url)
        raw = with_lapse(url, "u_reader")
        reach = loaded(url, "u_reader", AT)

    assert EntitlementSet.model_validate(raw).next_grant_lapse == PACK_LAPSE
    assert reach.next_grant_lapse == PACK_LAPSE
    for held in (READ_PRICES, READ_NAMES, READ_HOURS):
        assert reach.holds(Capability(value=held), AT)
    for gone in (READ_PHONE, READ_ADDRESS, READ_VALUE):
        assert not reach.holds(Capability(value=gone), AT)


def test_a_reach_with_no_dated_grant_reports_no_lapse_and_an_engagement_end_stays_apart() -> None:
    """The positive sibling. Undated grants lapse never, and a contractor's own end is carried on
    `not_after` and judged there rather than folded into the lapse. Delete this and a null can
    become a date that caps every entry at nothing, or the two dates can be merged so a set's
    expiry is decided in two places."""
    with resolver("brain_gl_undated") as url:
        a_company(url)
        undated = loaded(url, "u_undated", AT)
        contractor = loaded(url, "u_contractor", AT)

    assert undated.next_grant_lapse is None
    assert undated.holds(Capability(value=READ_PRICES), AT)
    assert contractor.next_grant_lapse is None
    assert contractor.not_after == RETIRED_GRANT_LAPSE


def resolver_answers(url: str) -> list[object]:
    return [
        answer
        for principal_id in ("u_reader", "u_undated", "u_contractor", "u_stranger")
        for instant in (AT, GRANT_LAPSE)
        for (answer,) in sql(url, "SELECT gate.resolve_entitlements(%s, %s)", principal_id, instant)
    ]


@contextmanager
def at_0003(database: str) -> Iterator[str]:
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0001")
        migrate(database, "upgrade", "0003")
        yield scratch
    finally:
        drop(database)


def test_the_resolvers_own_answer_is_unchanged_by_the_upgrade_and_by_the_downgrade() -> None:
    """The previous release calls `gate.resolve_entitlements` and validates its answer with
    `extra="forbid"`, and the audit trigger calls it on every grant write. Delete this and the
    replacement can change that answer, which during a rolling deploy refuses every request, or
    the downgrade can leave the lifted body behind with `gate.held_grants` dropped under it."""
    lapse = LAPSE_MIGRATION
    with at_0003("brain_gl_unchanged") as url:
        a_company(url)
        before = resolver_answers(url)
        migrate("brain_gl_unchanged", "stamp", predecessor(lapse))
        migrate("brain_gl_unchanged", "upgrade", revision_of(lapse))
        after = resolver_answers(url)
        beside = with_lapse(url, "u_reader")
        migrate("brain_gl_unchanged", "downgrade", predecessor(lapse))
        restored = resolver_answers(url)
        gone = sql(
            url,
            "SELECT to_regprocedure('gate.held_grants(text, timestamptz)'),"
            " to_regprocedure('gate.entitlements_with_lapse(text, timestamptz)')",
        )

    assert any(answer["grants"] for answer in before if isinstance(answer, dict))
    assert after == before
    assert restored == before
    assert {k: v for k, v in beside.items() if k != "next_grant_lapse"} == before[0]
    assert gone == [(None, None)]


class Remembered:
    """An `EntitlementCache` that never forgets and records every write, in order."""

    def __init__(self) -> None:
        self.kept: dict[str, EntitlementSet] = {}
        self.writes: list[tuple[str, int]] = []

    async def get(self, key: str) -> EntitlementSet | None:
        return self.kept.get(key)

    async def set(self, key: str, value: EntitlementSet, ttl_seconds: int) -> None:
        self.kept[key] = value
        self.writes.append((key, ttl_seconds))


def test_a_grant_lapsing_inside_the_ttl_stops_authorising_at_its_lapse_through_the_real_store() -> (
    None
):
    """The defect as b53eace recorded it, end to end: this store, the trigger-maintained version and
    a cache that never forgets. The version does not move, the entry is written for the thirty
    seconds the grant has left, and at the lapse the reach is loaded again without it. Delete this
    and the lapse is only ever proved in pieces, with nothing showing the pieces meet."""
    lapse = AT + timedelta(seconds=30)
    cache = Remembered()
    with resolver("brain_gl_resolve") as url:
        a_principal(url, "u_reader")
        a_grant(url, "u_reader", READ_PRICES, not_after=lapse)
        a_grant(url, "u_reader", READ_NAMES)

        async def work(store: StoredEntitlements) -> tuple[Resolved, Resolved]:
            versions = PostgresVersionSource(store.sessions)
            first = await resolve("u_reader", versions=versions, store=store, cache=cache, now=AT)
            later = await resolve(
                "u_reader", versions=versions, store=store, cache=cache, now=lapse
            )
            return first, later

        runner: Callable[[StoredEntitlements], Awaitable[tuple[Resolved, Resolved]]] = work
        first, later = with_store(url, runner)

    assert first.entitlements.holds(Capability(value=READ_PRICES), AT)
    # The write at the lapse is the reload, which holds nothing dated and so keeps the full TTL.
    key = cache_key("u_reader", first.grants_version)
    assert cache.writes == [(key, 30), (key, CACHE_TTL_SECONDS)]
    assert later.grants_version == first.grants_version
    assert later.from_cache is False
    assert not later.entitlements.holds(Capability(value=READ_PRICES), AT)
    assert later.entitlements.holds(Capability(value=READ_NAMES), AT)
