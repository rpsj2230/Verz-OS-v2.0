"""The Valkey clients, the caches over them, and the version source under them.

No Valkey and no PostgreSQL are contacted anywhere in this file. The clients are fakes with
three methods and the session factory is a fake with one statement's worth of behaviour, which
is the whole reason `brain.cache.ValkeyClient` and `brain.cache.AsyncValkeyClient` are narrow
protocols rather than concrete types. The version source against a real database is
`tests/unit/test_version_source.py`.

`make_client` and `make_async_client` are exercised for real, because building either client
opens no socket: the connection pool is lazy, and the assertions are about the arguments it was
configured with.

Task ids: M1.4.5
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.cache import (
    CONNECT_TIMEOUT_SECONDS,
    HEALTH_CHECK_INTERVAL_SECONDS,
    OPERATION_TIMEOUT_SECONDS,
    PRINCIPAL_SQL,
    RETRIES,
    STATEMENT_TIMEOUT_MS,
    STATEMENT_TIMEOUT_SQL,
    VERSION_SQL,
    CacheHealth,
    PostgresVersionSource,
    ValkeyAnswerStore,
    ValkeyEntitlementCache,
    check_reachable,
    check_reachable_async,
    make_async_client,
    make_client,
    version_from,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.answer_cache import STORE_TTL_SECONDS, AnswerStore, lookup, store_answer
from brain.gate.cache_key import CachedAnswer, key_for
from brain.gate.entitlement_store import PRINCIPAL_SETTING
from brain.gate.resolve import (
    CACHE_TTL_SECONDS,
    EntitlementCache,
    ResolutionFailedError,
    Resolved,
    VersionSource,
    cache_key,
)
from brain.gate.resolve import resolve as resolve_awaited

NOW = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)

#: A URL shaped like a real one, so a test can prove the password never reaches a log line.
DEAD_URL = "redis://brain:s3cr3t-valkey-password@cache.internal:6379/0"


# ------------------------------------------------------------------ the fakes
class FakeValkey:
    """An in-memory stand-in for the three commands the client uses. Opens no socket."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.pings = 0

    def get(self, name: str) -> bytes | None:
        return self.data.get(name)

    def setex(self, name: str, time: int, value: bytes) -> object:
        self.data[name] = bytes(value)
        self.ttls[name] = time
        return True

    def ping(self) -> object:
        self.pings += 1
        return True


class DeadValkey:
    """Fails every call the way an unreachable Valkey fails, credentialed message included."""

    def get(self, name: str) -> bytes | None:
        raise RedisConnectionError(f"Error connecting to {DEAD_URL}")

    def setex(self, name: str, time: int, value: bytes) -> object:
        raise RedisConnectionError(f"Error connecting to {DEAD_URL}")

    def ping(self) -> object:
        raise RedisConnectionError(f"Error connecting to {DEAD_URL}")


class Awaited:
    """A synchronous fake behind the awaited protocol, so one fake's data serves both clients."""

    def __init__(self, sync: FakeValkey | DeadValkey) -> None:
        self.sync = sync

    async def get(self, name: str) -> bytes | None:
        return self.sync.get(name)

    async def setex(self, name: str, time: int, value: bytes) -> object:
        return self.sync.setex(name, time, value)

    async def ping(self) -> object:
        return self.sync.ping()


def got(cache: ValkeyEntitlementCache, key: str) -> EntitlementSet | None:
    """`ValkeyEntitlementCache.get`, run to completion."""
    return asyncio.run(cache.get(key))


def put(cache: ValkeyEntitlementCache, key: str, value: EntitlementSet, ttl: int) -> None:
    """`ValkeyEntitlementCache.set`, run to completion."""
    asyncio.run(cache.set(key, value, ttl))


class FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class FakeSession:
    """Answers `VERSION_SQL` from a dict and records every statement, in order, with its binds.

    It is its own transaction as well as its own session: `begin()` hands back the session, so
    `async with sessions() as session, session.begin()` enters it twice and nothing else.
    """

    def __init__(
        self,
        versions: dict[str, int],
        seen: list[tuple[str, dict[str, object]]],
        *,
        broken: bool,
    ) -> None:
        self._versions = versions
        self.seen = seen
        self._broken = broken

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def begin(self) -> FakeSession:
        return self

    async def execute(self, statement: object, params: dict[str, object]) -> FakeResult:
        if self._broken:
            msg = "connection to postgres://brain:s3cr3t@db:5432 failed"
            raise RuntimeError(msg)
        self.seen.append((str(statement), dict(params)))
        if str(statement) == str(VERSION_SQL):
            return FakeResult(self._versions.get(str(params["principal_id"])))
        return FakeResult(None)


def version_source(
    versions: dict[str, int],
    *,
    broken: bool = False,
    statement_timeout_ms: int | None = STATEMENT_TIMEOUT_MS,
) -> tuple[PostgresVersionSource, list[tuple[str, dict[str, object]]]]:
    seen: list[tuple[str, dict[str, object]]] = []

    def sessions() -> FakeSession:
        return FakeSession(versions, seen, broken=broken)

    # A cast at the seam: the fake answers the three calls the source makes and nothing else an
    # `async_sessionmaker` offers, which is the point of a fake.
    factory = cast(async_sessionmaker[AsyncSession], sessions)
    return PostgresVersionSource(factory, statement_timeout_ms=statement_timeout_ms), seen


def version_of(source: PostgresVersionSource, principal_id: str) -> int:
    """`PostgresVersionSource.grants_version`, run to completion."""
    return asyncio.run(source.grants_version(principal_id))


def ents(principal: str, *caps: str, not_after: datetime | None = None) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=c), scope=Scope()) for c in caps),
        not_after=not_after,
    )


def an_answer(key: str = "k", payload: str = "SNM has 12 hours left") -> CachedAnswer:
    return CachedAnswer(key=key, payload=payload, stored_at=NOW, source_epochs={"lark_base": 4})


# ------------------------------------------------------------ the entitlement cache
def test_an_entitlement_set_survives_a_round_trip_through_the_cache() -> None:
    """The base case. Without it the module is a set of failure handlers around a cache that
    was never shown to work."""
    cache = ValkeyEntitlementCache(Awaited(FakeValkey()))
    value = ents("u_weiling", "read:client.name", "read:client.hours_remaining")

    put(cache, cache_key("u_weiling", 3), value, CACHE_TTL_SECONDS)
    assert got(cache, cache_key("u_weiling", 3)) == value


def test_a_grants_lapse_survives_the_round_trip_so_a_hit_can_still_be_refused_by_it() -> None:
    """`resolve` refuses a hit whose `next_grant_lapse` has passed, and it can only read a date
    the cache gave back. Delete this and a payload that drops the date passes the round trip
    above, and every cached reach is trusted past its first lapsing grant for as long as Valkey
    keeps it."""
    cache = ValkeyEntitlementCache(Awaited(FakeValkey()))
    lapse = datetime(2999, 6, 1, 9, 0, 30, tzinfo=UTC)
    value = ents("u_weiling", "read:client.name").model_copy(update={"next_grant_lapse": lapse})

    put(cache, cache_key("u_weiling", 3), value, CACHE_TTL_SECONDS)
    back = got(cache, cache_key("u_weiling", 3))

    assert back is not None
    assert back.next_grant_lapse == lapse


def test_the_stored_bytes_are_the_models_own_json() -> None:
    """A shared cache is read by other tools and other people. A payload that is not JSON is a
    payload nobody can inspect without running our code, which is how a debugging session ends
    up unpickling whatever is in there."""
    client = FakeValkey()
    put(
        ValkeyEntitlementCache(Awaited(client)),
        cache_key("u_weiling", 1),
        ents("u_weiling", "read:client.name"),
        CACHE_TTL_SECONDS,
    )
    stored = json.loads(client.data[cache_key("u_weiling", 1)])
    assert stored["principal_id"] == "u_weiling"
    assert stored["grants"][0]["capability"]["value"] == "read:client.name"


def test_a_key_that_was_never_written_is_a_miss() -> None:
    """None is the protocol's word for "not in hand", and the whole design rests on `resolve`
    treating it as an instruction to ask the authority."""
    cache = ValkeyEntitlementCache(Awaited(FakeValkey()))
    assert got(cache, cache_key("u_weiling", 1)) is None
    assert cache.health.misses == 1


def test_the_ttl_reaches_the_store_on_every_write() -> None:
    """A key written with no expiry outlives the deployment that wrote it, and an orphaned
    entitlement key that never expires is a permission decision nobody can find."""
    client = FakeValkey()
    put(
        ValkeyEntitlementCache(Awaited(client)),
        cache_key("u_weiling", 1),
        ents("u_weiling"),
        CACHE_TTL_SECONDS,
    )
    assert client.ttls[cache_key("u_weiling", 1)] == CACHE_TTL_SECONDS


def test_a_non_positive_ttl_is_refused_rather_than_silently_storing_nothing() -> None:
    """Valkey reports it as a command error, which this module swallows like any other, so
    without the check the cache would appear to work and hold nothing. Both halves are asked,
    because the check is shared and a shared check moved into one half is a check the other
    half lost."""
    client = FakeValkey()
    with pytest.raises(ValueError, match="ttl"):
        put(ValkeyEntitlementCache(Awaited(client)), cache_key("u_weiling", 1), ents("u"), 0)
    with pytest.raises(ValueError, match="ttl"):
        ValkeyAnswerStore(client).set("k", an_answer(), 0)
    assert client.data == {}


def test_resolve_works_end_to_end_over_the_real_cache_class() -> None:
    """M1.4.5 is the wiring, not the class. `resolve` had never run against anything but a
    dict, so this is the first thing that shows the two halves fit, awaited."""
    client = FakeValkey()
    cache = ValkeyEntitlementCache(Awaited(client))
    versions, _ = version_source({"u_weiling": 7})
    store = _Store({"u_weiling": ents("u_weiling", "read:client.name")})

    first = resolve("u_weiling", versions=versions, store=store, cache=cache)
    second = resolve("u_weiling", versions=versions, store=store, cache=cache)

    assert first.from_cache is False
    assert second.from_cache is True
    assert store.loads == 1
    assert cache_key("u_weiling", 7) in client.data


def resolve(principal_id: str, **seams: Any) -> Resolved:
    """`brain.gate.resolve.resolve`, run to completion. It awaits every seam."""
    return asyncio.run(resolve_awaited(principal_id, **seams))


class _Store:
    def __init__(self, sets: dict[str, EntitlementSet]) -> None:
        self.sets = sets
        self.loads = 0

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        self.loads += 1
        return self.sets[principal_id]


# ----------------------------------------------------------------- the answer store
def test_an_answer_survives_a_round_trip_including_its_timezone() -> None:
    """`CachedAnswer.age` subtracts one datetime from another, which raises on a naive/aware
    pair. A store that dropped the timezone would break every hit at the moment it is read,
    not at the moment it is written."""
    client = FakeValkey()
    store = ValkeyAnswerStore(client)
    store.set("k", an_answer(), STORE_TTL_SECONDS)

    found = store.get("k")
    assert found is not None
    assert found == an_answer()
    assert found.stored_at.tzinfo is not None
    assert found.age(NOW + timedelta(minutes=4)) == timedelta(minutes=4)


def test_an_answer_whose_key_field_disagrees_with_its_key_is_refused_on_write() -> None:
    """The only way this happens is code that built the answer with one key and stored it
    under another. Dropping the write would hide it until a read, where the same mismatch
    means one person's answer reaching somebody else."""
    store = ValkeyAnswerStore(FakeValkey())
    with pytest.raises(ValueError, match="key"):
        store.set("k", an_answer(key="a-different-key"), STORE_TTL_SECONDS)


def test_the_answer_cache_works_end_to_end_over_the_real_store_class() -> None:
    """`store_answer` and `lookup` had only ever run against a dict. This is the pair against
    something that serialises, which is where a store goes wrong."""
    client = FakeValkey()
    store: AnswerStore = ValkeyAnswerStore(client)
    key = store_answer(
        "did we invoice acme",
        "yes, on the third",
        ent_hash="e" * 32,
        agent_config_hash="a" * 32,
        policy_epoch=9,
        source_epochs={"lark_base": 4},
        store=store,
        now=NOW,
    )

    assert key == key_for("did we invoice acme", "e" * 32, "a" * 32, 9, {"lark_base": 4})
    assert key is not None
    found = lookup(key, store, NOW + timedelta(minutes=4))
    assert found is not None
    assert found.payload == "yes, on the third"
    assert found.age_label(NOW + timedelta(minutes=4)) == "answered 4 minutes ago"


def test_a_stale_answer_is_still_the_stores_to_return_and_lookups_to_refuse() -> None:
    """The division of labour. Freshness is `answer_cache`'s rule, so a store that filtered on
    age would be deciding the same thing twice, and the two copies would disagree the first
    time `DEFAULT_MAX_AGE` moves."""
    client = FakeValkey()
    store = ValkeyAnswerStore(client)
    store.set("k", an_answer(), STORE_TTL_SECONDS)

    assert store.get("k") is not None
    assert lookup("k", store, NOW + timedelta(hours=1)) is None


# ------------------------------------------------------------------ the version source
def test_the_version_source_reads_the_counter_the_triggers_bump() -> None:
    """M1.4.5. Until this existed the version in the cache key came from nowhere, so a
    revocation bumped a number nobody read."""
    versions, seen = version_source({"u_weiling": 12})
    assert version_of(versions, "u_weiling") == 12
    assert (str(VERSION_SQL), {"principal_id": "u_weiling"}) in seen


def test_a_principal_who_has_never_held_a_grant_reads_as_zero() -> None:
    """`GrantsVersionRow` says the row is created on the first bump, which is what lets `0003`
    create nine tables and write no data. A reader that required a row would fail for
    everybody who has never been granted anything."""
    versions, _ = version_source({})
    assert version_of(versions, "u_new_starter") == 0


def test_a_version_read_is_an_integer_whatever_the_driver_hands_back() -> None:
    """The positive sibling of the zero above, read directly. A driver may hand a BIGINT back as
    something other than `int`, and a key built from its repr would be a different key from the
    one the last request built. Delete this and that drift has no test."""
    assert version_from(None) == 0
    assert version_from(12) == 12
    assert type(version_from(True)) is int


def test_a_failed_version_read_raises_the_gates_own_error() -> None:
    """`resolve` wraps the read, but the detail it logs is this class's to keep clean, and a
    driver error carries the connection string it dialled."""
    versions, _ = version_source({}, broken=True)
    with pytest.raises(ResolutionFailedError) as caught:
        version_of(versions, "u_weiling")
    assert "s3cr3t" not in str(caught.value)
    assert "u_weiling" in str(caught.value)


def test_the_version_read_carries_a_statement_timeout() -> None:
    """A primary key lookup that hangs holds up a request before it has started doing its real
    work, and the request has no way to know it is waiting on a cache key."""
    versions, seen = version_source({"u_weiling": 1})
    version_of(versions, "u_weiling")
    assert seen[0] == (str(STATEMENT_TIMEOUT_SQL), {"bound": f"{STATEMENT_TIMEOUT_MS}ms"})


def test_the_statement_timeout_can_be_left_to_the_connection_string() -> None:
    """A deployment that sets `options=-c statement_timeout=...` should not get two bounds,
    one of which is silently a warning on an autocommit connection."""
    versions, seen = version_source({"u_weiling": 1}, statement_timeout_ms=None)
    version_of(versions, "u_weiling")
    assert [q for q, _ in seen] == [str(PRINCIPAL_SQL), str(VERSION_SQL)]


def test_the_version_read_names_its_principal_to_the_transaction_before_it_selects() -> None:
    """`A_VERSION_READ_NAMES_ITS_PRINCIPAL`, in order. Named after the select it would narrow
    nothing. Delete this and the ordering can drift with the database-backed test still green,
    since a policy reading the setting is checked there only as present or absent."""
    versions, seen = version_source({"u_weiling": 1})
    version_of(versions, "u_weiling")
    statements = [q for q, _ in seen]
    named = statements.index(str(PRINCIPAL_SQL))
    assert named < statements.index(str(VERSION_SQL))
    assert seen[named][1] == {"setting": PRINCIPAL_SETTING, "principal_id": "u_weiling"}


# ------------------------------------------------------------------------- health
def test_readiness_pings_rather_than_only_connecting() -> None:
    """`session.check_reachable` gives the reason: something listening is not something that
    can answer. PgBouncer accepts connections it cannot fulfil, and so does a proxy."""
    client = FakeValkey()
    assert check_reachable(client) is True
    assert client.pings == 1


def test_readiness_reports_a_dead_cache_rather_than_raising() -> None:
    """A probe that raises turns a degraded dependency into a crashed process, and this cache
    is one the system is designed to work without."""
    assert check_reachable(DeadValkey()) is False


def test_readiness_is_asked_of_the_awaited_client_the_requests_use() -> None:
    """The entitlement cache awaits its client, so readiness pings that client natively rather
    than a synchronous one in a thread. Both answers are asserted: a probe that is always True
    and a probe that is always False each pass half of this."""
    alive = FakeValkey()
    assert asyncio.run(check_reachable_async(Awaited(alive))) is True
    assert alive.pings == 1
    assert asyncio.run(check_reachable_async(Awaited(DeadValkey()))) is False


def test_health_counts_hits_misses_and_writes_apart() -> None:
    """A hit rate nobody can see is one nobody notices collapsing, and the first symptom would
    be a latency complaint rather than a cache problem."""
    cache = ValkeyEntitlementCache(Awaited(FakeValkey()))
    got(cache, cache_key("u_weiling", 1))
    put(cache, cache_key("u_weiling", 1), ents("u_weiling"), CACHE_TTL_SECONDS)
    got(cache, cache_key("u_weiling", 1))

    assert (cache.health.misses, cache.health.writes, cache.health.hits) == (1, 1, 1)
    assert cache.health.degraded is False


def test_one_health_record_can_be_shared_by_both_caches() -> None:
    """A deployment reporting one cache figure wants one counter. The default is per instance
    because two counters merged by accident is a milder mistake than one split by accident."""
    shared = CacheHealth()
    entitlements = ValkeyEntitlementCache(Awaited(FakeValkey()), health=shared)
    answers = ValkeyAnswerStore(FakeValkey(), health=shared)
    got(entitlements, "ent:u_weiling:1")
    answers.get("k")
    assert shared.misses == 2


# ------------------------------------------------------------------------- client
def test_the_client_is_built_with_every_timeout_named() -> None:
    """`Redis.from_url` leaves both socket timeouts at None, which is not a large timeout but
    no timeout, and retries ten times with backoff on top. Left alone, one `get` against a
    cache that accepts and then stops answering waits as long as the far end holds the
    connection open."""
    client = cast(Redis, make_client("redis://127.0.0.1:6399/0"))
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == OPERATION_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == CONNECT_TIMEOUT_SECONDS
    assert kwargs["retry"].get_retries() == RETRIES


def test_the_awaited_client_is_built_with_every_bound_the_synchronous_one_has() -> None:
    """The asyncio client's defaults took 5.02 seconds against a socket that never replied.
    Compared against the synchronous client's configuration rather than against the constants
    alone, so a bound added to one builder and not the other fails here. Delete this and the
    client on the request path can be the less bounded of the two."""
    awaited = cast(AsyncRedis, make_async_client("redis://127.0.0.1:6399/0"))
    synchronous = cast(Redis, make_client("redis://127.0.0.1:6399/0"))
    names = (
        "socket_timeout",
        "socket_connect_timeout",
        "health_check_interval",
        "decode_responses",
    )

    ours = awaited.connection_pool.connection_kwargs
    theirs = synchronous.connection_pool.connection_kwargs
    assert {n: ours.get(n) for n in names} == {n: theirs.get(n) for n in names}
    assert ours["retry"].get_retries() == theirs["retry"].get_retries() == RETRIES
    assert ours["health_check_interval"] == HEALTH_CHECK_INTERVAL_SECONDS


def test_the_client_returns_bytes_rather_than_decoded_strings() -> None:
    """pydantic parses JSON from bytes directly. Decoding first is a wasted copy and moves a
    possible UnicodeDecodeError into the client, where this module cannot turn it into a
    miss."""
    client = cast(Redis, make_client("redis://127.0.0.1:6399/0"))
    assert client.connection_pool.connection_kwargs.get("decode_responses") is False


def test_the_classes_satisfy_the_protocols_they_are_written_against() -> None:
    """Checked by mypy rather than at runtime: the protocols are structural and not
    `runtime_checkable`, so a drifted signature is a type error and never an exception. The
    awaitability is checked at runtime as well, because a synchronous method satisfying an
    `async def` protocol member is exactly the mistake a structural check lets through when
    somebody annotates the return as `Any`."""
    cache: EntitlementCache = ValkeyEntitlementCache(Awaited(FakeValkey()))
    answers: AnswerStore = ValkeyAnswerStore(FakeValkey())
    versions: VersionSource = version_source({})[0]

    assert asyncio.run(cache.get("ent:u_weiling:1")) is None
    assert answers.get("k") is None
    assert asyncio.run(versions.grants_version("u_weiling")) == 0
    for method in (cache.get, cache.set, versions.grants_version):
        assert inspect.iscoroutinefunction(method), method
