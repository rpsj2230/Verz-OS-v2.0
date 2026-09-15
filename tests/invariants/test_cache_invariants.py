"""A cache client in front of a permission decision. A failure here blocks deploy.

`test_resolve_invariants` proves `resolve` is right about a cache. These prove the cache is
the thing `resolve` was promised: it forgets, it never invents, and when it is unreachable it
gets out of the way rather than becoming an answer.

Four properties carry the module, and each is a way the system could be wrong rather than
slow.

- A miss and an outage both fall through to the authority, and neither becomes an empty
  entitlement set. An empty set is a legitimate value that flows onward and produces a
  confident "I could not find that" for somebody who should have seen the record.
- Nothing is deleted to invalidate, so there is no method that deletes.
- Nothing is pickled, because a pickle in a shared cache is remote code execution the moment
  anything else can write to that cache.
- Every call is bounded, because a cache that hangs is worse than one that is down: the
  request waits instead of falling through.

No Valkey and no PostgreSQL are contacted anywhere in this file. One test opens a local socket
that accepts and never replies, because the bound on the awaited client is a property of the
library's behaviour and not of the arguments it was given.

Task ids: M1.4.5
"""

from __future__ import annotations

import ast
import asyncio
import pickle
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

import brain.cache
from brain.cache import (
    OPERATION_TIMEOUT_SECONDS,
    STATEMENT_TIMEOUT_MS,
    STATEMENT_TIMEOUT_SQL,
    VERSION_SQL,
    AsyncValkeyClient,
    PostgresVersionSource,
    ValkeyAnswerStore,
    ValkeyClient,
    ValkeyEntitlementCache,
    check_reachable,
    check_reachable_async,
    make_async_client,
    make_client,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.answer_cache import STORE_TTL_SECONDS, lookup, store_answer
from brain.gate.cache_key import CachedAnswer, key_for
from brain.gate.resolve import (
    CACHE_TTL_SECONDS,
    ResolutionFailedError,
    Resolved,
    cache_key,
)
from brain.gate.resolve import resolve as resolve_awaited

pytestmark = pytest.mark.invariant

NOW = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)

#: Shaped like a real connection string, so a log line that leaked one would be caught.
DEAD_URL = "redis://brain:s3cr3t-valkey-password@cache.internal:6379/0"
DB_URL = "postgres://brain:d1fferent-db-password@db.internal:5432/brain"

SOURCE = Path(brain.cache.__file__).read_text(encoding="utf-8")


# ------------------------------------------------------------------ the fakes
class FakeValkey:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, name: str) -> bytes | None:
        return self.data.get(name)

    def setex(self, name: str, time: int, value: bytes) -> object:
        self.data[name] = bytes(value)
        self.ttls[name] = time
        return True

    def ping(self) -> object:
        return True


class DeadValkey:
    """Unreachable, the way redis-py reports it: a connection error naming the URL."""

    def get(self, name: str) -> bytes | None:
        raise RedisConnectionError(f"Error connecting to {DEAD_URL}")

    def setex(self, name: str, time: int, value: bytes) -> object:
        raise RedisConnectionError(f"Error connecting to {DEAD_URL}")

    def ping(self) -> object:
        raise RedisTimeoutError(f"Timeout connecting to {DEAD_URL}")


class RawSocketValkey:
    """Fails with a bare `OSError`, which a client can leak before it wraps anything."""

    def get(self, name: str) -> bytes | None:
        raise OSError(104, "Connection reset by peer")

    def setex(self, name: str, time: int, value: bytes) -> object:
        raise OSError(104, "Connection reset by peer")

    def ping(self) -> object:
        raise OSError(104, "Connection reset by peer")


class Awaited:
    """A synchronous fake behind `AsyncValkeyClient`, so one fake's data serves both clients."""

    def __init__(self, sync: FakeValkey | DeadValkey | RawSocketValkey) -> None:
        self.sync = sync

    async def get(self, name: str) -> bytes | None:
        return self.sync.get(name)

    async def setex(self, name: str, time: int, value: bytes) -> object:
        return self.sync.setex(name, time, value)

    async def ping(self) -> object:
        return self.sync.ping()


def got(cache: ValkeyEntitlementCache, key: str) -> EntitlementSet | None:
    return asyncio.run(cache.get(key))


def put(cache: ValkeyEntitlementCache, key: str, value: EntitlementSet, ttl: int) -> None:
    asyncio.run(cache.set(key, value, ttl))


def resolve(principal_id: str, **seams: Any) -> Resolved:
    """`brain.gate.resolve.resolve`, run to completion. It awaits every seam."""
    return asyncio.run(resolve_awaited(principal_id, **seams))


class GoodStore:
    def __init__(self, sets: dict[str, EntitlementSet]) -> None:
        self.sets = sets
        self.loads = 0

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        self.loads += 1
        return self.sets[principal_id]


class BrokenStore:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        raise RuntimeError(f"database is unreachable, asked for {principal_id}")


class FixedVersions:
    def __init__(self, version: int = 1) -> None:
        self.version = version

    async def grants_version(self, principal_id: str) -> int:
        del principal_id
        return self.version


class FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class FakeSession:
    """Answers `VERSION_SQL` from a dict, or fails as a database that is not there fails."""

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
            raise RuntimeError(f"connection to {DB_URL} failed")
        self.seen.append((str(statement), dict(params)))
        if str(statement) == str(VERSION_SQL):
            return FakeResult(self._versions.get(str(params["principal_id"])))
        return FakeResult(None)


def version_source(
    versions: dict[str, int], *, broken: bool = False
) -> tuple[PostgresVersionSource, list[tuple[str, dict[str, object]]]]:
    seen: list[tuple[str, dict[str, object]]] = []

    def sessions() -> FakeSession:
        return FakeSession(versions, seen, broken=broken)

    # A cast at the seam: the fake answers the calls the source makes and nothing else.
    return PostgresVersionSource(cast(async_sessionmaker[AsyncSession], sessions)), seen


def version_of(source: PostgresVersionSource, principal_id: str) -> int:
    return asyncio.run(source.grants_version(principal_id))


def ents(principal: str, *caps: str, not_after: datetime | None = None) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=c), scope=Scope()) for c in caps),
        not_after=not_after,
    )


# ------------------------------------------------- a miss and an outage are different
def test_a_cache_outage_falls_through_to_the_database() -> None:
    """The property the whole module exists for. An unreachable cache must make the system
    slower and never change what it says, so `get` reports "not in hand" rather than raising:
    `resolve` guards the version read and the store and nothing around the cache, so an
    exception from the cache would leave the gate as an unhandled error on every request."""
    cache = ValkeyEntitlementCache(Awaited(DeadValkey()))
    store = GoodStore({"u_weiling": ents("u_weiling", "read:client.name")})

    resolved = resolve("u_weiling", versions=FixedVersions(1), store=store, cache=cache)

    assert resolved.from_cache is False
    assert resolved.entitlements == ents("u_weiling", "read:client.name")
    assert store.loads == 1
    assert cache.health.degraded is True


def test_a_cache_outage_never_becomes_an_empty_entitlement_set() -> None:
    """The tempting default looks safe and is not. An empty set flows onward, gets hashed, and
    produces a confident "I could not find that" for a person who should have seen the record,
    which is indistinguishable from a correct answer at every point downstream."""
    cache = ValkeyEntitlementCache(Awaited(DeadValkey()))
    resolved = resolve(
        "u_weiling",
        versions=FixedVersions(1),
        store=GoodStore({"u_weiling": ents("u_weiling", "read:client.name")}),
        cache=cache,
    )
    assert resolved.entitlements.grants != ()


def test_a_cache_outage_on_top_of_a_database_outage_raises_rather_than_returning_nothing() -> None:
    """Both halves down is the case where a default would be most tempting and most wrong. A
    resolution that failed has to say so."""
    with pytest.raises(ResolutionFailedError):
        resolve(
            "u_weiling",
            versions=FixedVersions(1),
            store=BrokenStore(),
            cache=ValkeyEntitlementCache(Awaited(DeadValkey())),
        )


def test_a_failed_cache_write_does_not_fail_the_request() -> None:
    """By the time the write happens the answer is already in hand. Raising here would turn a
    degraded cache into a broken system, which is the failure this module is meant to rule
    out."""
    cache = ValkeyEntitlementCache(Awaited(DeadValkey()))
    put(cache, cache_key("u_weiling", 1), ents("u_weiling", "read:client.name"), CACHE_TTL_SECONDS)
    assert cache.health.outages == 1


def test_a_bare_socket_error_is_handled_like_any_other_outage() -> None:
    """redis-py wraps most failures, and not all of them. Catching only `RedisError` leaves a
    reset connection propagating out of the gate on a path nobody tests. Both clients are
    asked, because they share the tuple that decides it."""
    cache = ValkeyEntitlementCache(Awaited(RawSocketValkey()))
    assert got(cache, cache_key("u_weiling", 1)) is None
    put(cache, cache_key("u_weiling", 1), ents("u_weiling"), CACHE_TTL_SECONDS)
    assert cache.health.outages == 2

    answers = ValkeyAnswerStore(RawSocketValkey())
    assert answers.get("k") is None
    assert answers.health.outages == 1


def test_a_miss_and_an_outage_are_counted_apart() -> None:
    """They are the same instruction to `resolve` and a different fact for an operator. Merged
    into one counter, a dead cache reads as a cache that is merely cold, and the difference is
    the one worth paging somebody about."""
    cold = ValkeyEntitlementCache(Awaited(FakeValkey()))
    got(cold, cache_key("u_weiling", 1))
    dead = ValkeyEntitlementCache(Awaited(DeadValkey()))
    got(dead, cache_key("u_weiling", 1))

    assert (cold.health.misses, cold.health.outages, cold.health.degraded) == (1, 0, False)
    assert (dead.health.misses, dead.health.outages, dead.health.degraded) == (0, 1, True)


def test_a_cancelled_request_stays_cancelled_rather_than_becoming_a_miss() -> None:
    """Cancellation is not an outage. Read as one, a request its caller abandoned would fall
    through to the database and do the whole load for nobody, on exactly the occasions a
    server is shedding work. Delete this and `OUTAGES` can be widened to `BaseException` with
    every other test here green."""

    class Cancelled:
        async def get(self, name: str) -> bytes | None:
            raise asyncio.CancelledError

        async def setex(self, name: str, time: int, value: bytes) -> object:
            raise asyncio.CancelledError

        async def ping(self) -> object:
            raise asyncio.CancelledError

    cache = ValkeyEntitlementCache(Cancelled())

    async def ask() -> EntitlementSet | None:
        return await cache.get(cache_key("u_weiling", 1))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ask())
    assert cache.health.outages == 0


# ------------------------------------------------------------- nothing is deleted
def test_neither_cache_offers_a_way_to_delete_an_entry() -> None:
    """The invalidation design in one assertion. The version is in the key and a bump orphans
    the old one; a delete that does not arrive leaves a stale entry serving a revoked
    permission and nothing reports it. A second invalidation path is one that will be relied
    on, so there is not one to reach for."""
    forbidden = ("delete", "remove", "evict", "invalidate", "flush", "purge", "unlink", "expire")
    for cls in (ValkeyEntitlementCache, ValkeyAnswerStore, ValkeyClient, AsyncValkeyClient):
        named = [n for n in dir(cls) if any(word in n.lower() for word in forbidden)]
        assert named == [], f"{cls.__name__} exposes {named}"


def test_every_write_carries_an_expiry() -> None:
    """A key with no expiry outlives the deployment that wrote it. That is the store reclaiming
    space and not invalidation, which is why the TTL is the caller's constant rather than a
    number this module chooses."""
    client = FakeValkey()
    put(
        ValkeyEntitlementCache(Awaited(client)),
        cache_key("u_weiling", 1),
        ents("u_weiling"),
        CACHE_TTL_SECONDS,
    )
    ValkeyAnswerStore(client).set(
        "k", CachedAnswer(key="k", payload="p", stored_at=NOW, source_epochs={}), STORE_TTL_SECONDS
    )
    assert client.ttls == {cache_key("u_weiling", 1): CACHE_TTL_SECONDS, "k": STORE_TTL_SECONDS}


def test_an_expired_entitlement_set_is_still_cached() -> None:
    """`resolve` requires it and says why: refusing to cache an expired set means re-loading it
    on every request from a contractor whose access ended, which is when the load is least
    useful. Expiry is a property of the set, checked where the set is read."""
    client = FakeValkey()
    cache = ValkeyEntitlementCache(Awaited(client))
    expired = ents("u_temp", "read:client.name", not_after=NOW - timedelta(minutes=1))

    resolve(
        "u_temp",
        versions=FixedVersions(1),
        store=GoodStore({"u_temp": expired}),
        cache=cache,
        now=NOW,
    )
    assert cache_key("u_temp", 1) in client.data


# ----------------------------------------------------------------- never pickle
def test_the_cache_client_imports_no_module_that_can_execute_a_stored_value() -> None:
    """A pickle in a shared cache is remote code execution the moment anything else can write
    to that cache, and something else always can: another service, a `redis-cli`, an operator
    with the URL. Checked on the import list rather than on the prose, which says the word
    several times."""
    imported: set[str] = set()
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"pickle", "cloudpickle", "dill", "marshal", "shelve"})


def test_a_pickle_sitting_in_the_cache_is_refused_rather_than_executed() -> None:
    """The attack the rule exists for, carried out. A hostile writer puts a payload in the
    keyspace; unpickling it runs its `__reduce__` inside the gate. JSON cannot execute, so the
    worst outcome is a value that fails validation, which is a miss."""
    client = FakeValkey()
    key = cache_key("u_weiling", 1)
    client.data[key] = pickle.dumps(_HostilePayload())

    assert got(ValkeyEntitlementCache(Awaited(client)), key) is None
    assert _EXECUTED == [], "a stored payload ran code inside the gate"


def test_both_payloads_are_json_that_another_tool_can_read() -> None:
    """The positive half. A cache somebody can inspect with `redis-cli` is one they debug
    without running our deserialiser over whatever is in there."""
    client = FakeValkey()
    put(ValkeyEntitlementCache(Awaited(client)), cache_key("p", 1), ents("p", "read:x.name"), 60)
    ValkeyAnswerStore(client).set(
        "k", CachedAnswer(key="k", payload="p", stored_at=NOW, source_epochs={"x": 1}), 60
    )
    for raw in client.data.values():
        assert raw.startswith(b"{") and raw.endswith(b"}")


# ------------------------------------------- a value out of the cache came from outside
def test_a_value_that_is_not_well_formed_is_a_miss_and_not_a_crash() -> None:
    """The bytes are shared, mutable, and writable by anything holding the URL. Trusting them
    to parse turns somebody else's write into an exception on the permission path."""
    client = FakeValkey()
    key = cache_key("u_weiling", 1)
    cache = ValkeyEntitlementCache(Awaited(client))

    for rubbish in (b"", b"{", b"null", b'{"principal_id": 4}', b"\xff\xfe not utf-8"):
        client.data[key] = rubbish
        assert got(cache, key) is None
    assert cache.health.rejections == 5


def test_a_cache_entry_for_the_wrong_principal_is_left_for_resolve_to_refuse() -> None:
    """The division of labour, and a check that it composes. The cache parses and hands back
    what it found; `resolve._usable` compares the principal. Repeating the comparison here
    would put the same rule in two places, which is how one of them gets relaxed."""
    client = FakeValkey()
    client.data[cache_key("u_weiling", 1)] = (
        ents("u_someone_else", "read:client.contract_value").model_dump_json().encode()
    )
    cache = ValkeyEntitlementCache(Awaited(client))

    assert got(cache, cache_key("u_weiling", 1)) is not None  # the cache is not the judge
    resolved = resolve(
        "u_weiling",
        versions=FixedVersions(1),
        store=GoodStore({"u_weiling": ents("u_weiling", "read:client.name")}),
        cache=cache,
    )
    assert resolved.entitlements.principal_id == "u_weiling"
    assert resolved.from_cache is False


def test_an_answer_found_under_a_key_that_is_not_its_own_is_refused() -> None:
    """Nothing else in the path would notice. The answer is internally consistent and fresh; it
    just belongs to somebody else, and `lookup` checks age rather than identity."""
    elsewhere = CachedAnswer(
        key="somebody-elses-key", payload="margin is 41%", stored_at=NOW, source_epochs={}
    )
    staging = FakeValkey()
    ValkeyAnswerStore(staging).set(elsewhere.key, elsewhere, STORE_TTL_SECONDS)

    client = FakeValkey()
    client.data["k"] = staging.data[elsewhere.key]  # the same bytes, under the wrong key
    store = ValkeyAnswerStore(client)

    assert store.get("k") is None
    assert lookup("k", store, NOW) is None
    # Refused on both reads. Nothing here removes it, because nothing here deletes; the
    # entry sits there until its expiry, unreachable and harmless.
    assert store.health.rejections == 2
    assert "k" in client.data


# ------------------------------------------------------------------- the key is the key
def test_the_key_reaches_the_store_exactly_as_the_gate_built_it() -> None:
    """The key is the invalidation token. A client that prefixes or rewrites it makes "was this
    orphaned by the version bump" a question about two pieces of code instead of one, and the
    answer stops being obvious at exactly the moment somebody needs it to be."""
    client = FakeValkey()
    put(ValkeyEntitlementCache(Awaited(client)), cache_key("u_weiling", 7), ents("u_weiling"), 60)
    assert list(client.data) == ["ent:u_weiling:7"]

    answers = FakeValkey()
    key = store_answer(
        "did we invoice acme",
        "yes",
        ent_hash="e" * 32,
        agent_config_hash="a" * 32,
        policy_epoch=9,
        source_epochs={"lark_base": 4},
        store=ValkeyAnswerStore(answers),
        now=NOW,
    )
    assert list(answers.data) == [key]
    assert key == key_for("did we invoice acme", "e" * 32, "a" * 32, 9, {"lark_base": 4})


# ---------------------------------------------------------------------- timeouts
def test_every_call_the_client_makes_is_bounded() -> None:
    """A cache that hangs is worse than a cache that is down, because the request waits instead
    of falling through. Asserted on the type and not on a value, because the trap is that
    `Redis.from_url` leaves both timeouts at None: a test comparing against redis-py's
    documented five seconds would pass on a client that waits forever. Both builders, since
    the awaited one is the one on the request path."""
    for built in (make_client(DEAD_URL), make_async_client(DEAD_URL)):
        kwargs = cast(Redis, built).connection_pool.connection_kwargs

        for name in ("socket_timeout", "socket_connect_timeout"):
            bound = kwargs.get(name)
            assert isinstance(bound, float), f"{name} is not set to a number"
            assert 0 < bound <= 1, f"{name} is {bound}, which is not a bound worth having"
        assert kwargs["retry"].get_retries() == 0


@contextmanager
def a_cache_that_never_answers() -> Iterator[str]:
    """A local socket that accepts every connection and never writes a byte back."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    held: list[socket.socket] = []

    def accept() -> None:
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            held.append(conn)

    threading.Thread(target=accept, daemon=True).start()
    try:
        yield f"redis://127.0.0.1:{listener.getsockname()[1]}/0"
    finally:
        listener.close()
        for conn in held:
            conn.close()


def test_a_cache_that_accepts_and_never_answers_is_a_miss_within_the_bound() -> None:
    """The hang the module docstring measured, carried out against the real awaited client.
    Unbounded, this `get` waited 5.02 seconds; a request waiting that long on a cache key has
    not failed over, it has stalled. Delete this and the bound is only ever proved on keyword
    arguments, which is the trap `Redis.from_url` already set once.

    The test bounds itself. An unbounded client waits on this socket for ever, so without the
    outer `wait_for` the failure this test exists for would present as a suite that never
    finishes rather than as a red test; a mutation run removing the bound hung for two hours
    that way before this line was added."""
    ceiling = OPERATION_TIMEOUT_SECONDS * 8
    with a_cache_that_never_answers() as url:
        cache = ValkeyEntitlementCache(make_async_client(url))

        async def ask() -> tuple[EntitlementSet | None, float] | None:
            started = time.perf_counter()
            try:
                found = await asyncio.wait_for(cache.get(cache_key("u_weiling", 1)), ceiling)
            except TimeoutError:
                return None
            return found, time.perf_counter() - started

        answered = asyncio.run(ask())

    assert answered is not None, f"a silent cache held the request past {ceiling:.2f}s"
    found, took = answered
    assert found is None
    assert cache.health.outages == 1
    assert took < ceiling, f"a silent cache held the request {took:.2f}s"


def test_the_version_read_is_bounded_too() -> None:
    """It is a network call like the others. A primary key lookup that hangs holds up a request
    before it has begun its real work, and nothing downstream can tell it is waiting."""
    versions, seen = version_source({"u_weiling": 3})
    version_of(versions, "u_weiling")
    assert seen[0] == (str(STATEMENT_TIMEOUT_SQL), {"bound": f"{STATEMENT_TIMEOUT_MS}ms"})
    assert STATEMENT_TIMEOUT_MS <= 1000


# ------------------------------------------------------- the version is never guessed
def test_a_missing_version_row_is_zero_and_a_failed_read_is_never_a_number() -> None:
    """One `if` apart, and the consequences are not comparable. A principal who has never held
    a grant has no row, which is zero. A read that failed must not also be zero: zero is a real
    version, so returning it would mint a key that was already used, under a wider entitlement,
    and whatever is cached there is still readable."""
    present, _ = version_source({"u_weiling": 4})
    assert version_of(present, "u_new_starter") == 0

    broken, _ = version_source({}, broken=True)
    with pytest.raises(ResolutionFailedError):
        version_of(broken, "u_new_starter")


# ---------------------------------------------------------------- nothing leaks
def test_no_credential_and_no_key_reaches_a_log_line() -> None:
    """A log line is read by more people, for longer, than the cache entry it describes. A
    redis-py connection error carries the URL it dialled and the URL carries the password, and
    `ent:<principal>:<version>` names a person."""
    cache = ValkeyEntitlementCache(Awaited(DeadValkey()))
    with capture_logs() as events:
        got(cache, cache_key("u_weiling", 1))
        put(cache, cache_key("u_weiling", 1), ents("u_weiling"), CACHE_TTL_SECONDS)
        check_reachable(DeadValkey())
        asyncio.run(check_reachable_async(Awaited(DeadValkey())))

    blob = repr(events)
    assert len(events) == 4, "an outage was not reported"
    assert "s3cr3t-valkey-password" not in blob
    assert "cache.internal" not in blob
    assert "u_weiling" not in blob
    # Still useful, or somebody puts the message back to debug it.
    assert "ConnectionError" in blob
    assert "TimeoutError" in blob


def test_a_failed_version_read_reports_no_connection_string_either() -> None:
    """`app.py` logs `exc.detail` on every `BrainError`, so the detail is a log line by another
    name, and a driver message names the host, the user and the password it dialled with."""
    versions, _ = version_source({}, broken=True)
    with pytest.raises(ResolutionFailedError) as caught:
        version_of(versions, "u_weiling")

    assert "d1fferent-db-password" not in str(caught.value)
    assert "db.internal" not in str(caught.value)
    assert "u_weiling" in str(caught.value)


# --------------------------------------------------- the payload used by the pickle test
_EXECUTED: list[str] = []


def _mark() -> str:
    """Stands in for the arbitrary code a pickle payload runs. Never called."""
    _EXECUTED.append("a pickle in the cache executed")
    return "owned"


class _HostilePayload:
    """Runs `_mark` if anything unpickles it. Nothing should."""

    def __reduce__(self) -> tuple[Callable[[], str], tuple[()]]:
        return (_mark, ())
