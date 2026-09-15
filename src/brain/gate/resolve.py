"""Working out what a caller holds, quickly, without ever being wrong about it.

Entitlement resolution happens on every single request, so it has to be cached, and a cache
in front of a permission decision is the most dangerous cache in any system. Every other
cache serves a stale answer; this one serves somebody else's reach.

Three rules make it safe, and all three are about invalidation rather than speed.

**The key carries the version, so nothing is ever deleted.** A write bumps
`grants_version`, and every key built from the old version is orphaned in the same instant.
Deleting entries on write is the alternative, and it fails in the way that matters: a delete
that does not arrive leaves a stale entry serving a revoked permission, and nothing anywhere
reports it. An orphaned key cannot be read by accident because nobody can construct it.

**A miss loads, and a failure raises.** There is no path here that returns a default. The
tempting default is an empty set, which looks safe and is not: an empty set is a legitimate
value that flows onward, gets cached, gets hashed and produces a confident "I could not find
that" for someone who should have seen the record. A resolution that failed must say so.

**The set is checked against the principal who asked for it.** A store returning the wrong
row is the catastrophic failure, and it is one comparison to rule out.

**The store is awaited, for the reason `brain.knowledge.rows.RowSource` is.** The only pool the
application holds is an `AsyncEngine`, and a synchronous `load` could be implemented against it
only by a second pool or a thread per request. `brain.gate.entitlement_store` is the
implementation, over `gate.resolve_entitlements`.

**The version source and the cache are awaited too, and for a sharper reason.** They are read on
every request, hit or miss, where the store is read only on a miss. A synchronous version read
over psycopg, or a synchronous `GET` against Valkey, holds the event loop for as long as the far
end takes, which is every other request on that worker waiting on one person's cache key. Running
them through `asyncio.to_thread` was the cheaper change and was rejected: it spends a thread from a
default executor of a few dozen per request, so a cache that hangs for its timeout drains the
executor that migrations and readiness also use, and the loop is then blocked by proxy. See
`THE_REQUEST_PATH_AWAITS_WHAT_IT_READS`. `brain.cache` holds both implementations.

**The store is told the caller's instant.** `gate.resolve_entitlements` drops a grant whose own
`not_after` has passed, and the grant type carries no expiry, so that judgement is made when the
set is loaded and nowhere afterwards. See `THE_STORE_IS_ASKED_AT_THE_CALLERS_INSTANT`.

**A cached reach lives no longer than it stays true.** A grant lapsing is not a write, so it moves
no version, and until `0048` a set cached a second before a grant's `not_after` served that grant
for the rest of its sixty seconds: a revocation by time that still authorised, which is the
permissive failure this module exists to prevent. The store now reports the earliest future
lapse on `EntitlementSet.next_grant_lapse`, and the entry's lifetime is capped at it, whole seconds
rounded down, never longer than `CACHE_TTL_SECONDS`. A lapse already reached writes nothing. The
lapse is checked again when a hit is read, at the caller's instant, as the principal's own
`not_after` always has been, so a cache whose clock runs behind ours still cannot serve past it.
The principal's `not_after` does not shorten the entry: the read check refuses it on time, and
`test_an_expired_entitlement_set_is_still_cached` holds that an ended engagement's set is cached.
See `A_CACHED_REACH_LIVES_NO_LONGER_THAN_IT_STAYS_TRUE`.

Rejected: bumping `grants_version` from a scheduled job when a date passes. It keeps the cache
unchanged and puts correctness on a job whose failure is silence, which is the delete-on-write
design the first paragraph rejects, arriving by a different door.

Task ids: M3.3.1, M3.3.2
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

from brain.core.entitlement import EntitlementSet
from brain.core.errors import BrainError, Outcome

#: How long a resolved entitlement may live in the cache. Short enough that a missed
#: version bump is measured in seconds, long enough to matter across a burst of requests
#: from one person. It is a backstop: correctness comes from the version in the key.
CACHE_TTL_SECONDS = 60

#: Why `load` takes a time, and whose.
THE_STORE_IS_ASKED_AT_THE_CALLERS_INSTANT: Final = (
    "A grant's own expiry is decided when the set is loaded, because a Grant carries no date "
    "to decide it by later. Loading at the database's clock or the process's would judge it at "
    "an instant the caller never asked about, so the store is handed the caller's now, the "
    "same instant the cached set's expiry is judged at. Nothing bumps the version when a date "
    "passes, so the store also reports the earliest lapse, and the cache entry is bounded by it: "
    "see A_CACHED_REACH_LIVES_NO_LONGER_THAN_IT_STAYS_TRUE."
)

#: Why a cache entry's lifetime is not simply CACHE_TTL_SECONDS.
A_CACHED_REACH_LIVES_NO_LONGER_THAN_IT_STAYS_TRUE: Final = (
    "A grant's own expiry moves no version, so a cached reach would outlive the grant by up to the "
    "TTL and keep authorising what has lapsed. The entry is written for the whole seconds left "
    "before the earliest lapse, never more than the TTL, and not at all when none are left; a hit "
    "is refused once the lapse has passed at the caller's instant, whatever the cache's own clock "
    "thinks, as it already was for the principal's own not_after."
)

#: Why every seam `resolve` reads is awaitable, and not only the store.
THE_REQUEST_PATH_AWAITS_WHAT_IT_READS: Final = (
    "The grants version and the cache are read on every request, so a blocking read of either "
    "stops every request on the worker for as long as the far end takes. They are awaited on the "
    "application's own event loop rather than pushed to a thread, because a thread per request "
    "drains a small shared executor exactly when the cache is hanging."
)


class ResolutionFailedError(BrainError):
    """Resolution could not complete. Deliberately not an empty entitlement set.

    An empty set is a legitimate value: it flows onward, gets cached, gets hashed, and
    produces a confident "I could not find that" for a person who should have seen the
    record. A failure has to be distinguishable from holding nothing.
    """

    outcome = Outcome.FAILED
    public_message = "I could not work out what you have access to just now."


class VersionSource(Protocol):
    """The current grants version for a principal. Must be cheap; it is read every request.

    Separate from the store because the whole design depends on learning the version
    without loading the grants. If reading the version cost what loading costs, the cache
    would save nothing. Awaitable: see `THE_REQUEST_PATH_AWAITS_WHAT_IT_READS`.
    """

    async def grants_version(self, principal_id: str) -> int: ...


class EntitlementStore(Protocol):
    """The authority. Slow, correct, and consulted only on a miss.

    Awaitable, and handed the instant the caller is asking at. See the module docstring and
    `THE_STORE_IS_ASKED_AT_THE_CALLERS_INSTANT`. A stand-in in a test is `async def load`.
    """

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet: ...


class EntitlementCache(Protocol):
    """A cache that may forget at any time and must never invent.

    `get` returning None is always safe. There is no method to delete, on purpose: version
    bumping is the invalidation mechanism, and offering a delete invites a second one.

    Awaitable, and neither method may raise for an outage: `resolve` guards the version read
    and the store, and nothing around these two. `brain.cache.ValkeyEntitlementCache` turns
    every client failure into None or a dropped write.
    """

    async def get(self, key: str) -> EntitlementSet | None: ...
    async def set(self, key: str, value: EntitlementSet, ttl_seconds: int) -> None: ...


def cache_key(principal_id: str, grants_version: int) -> str:
    """`ent:<principal>:<version>`.

    The version is in the key rather than checked after a read. Checking after means the
    stale value was already in hand, and a later refactor that forgets the check reads as
    a simplification.
    """
    return f"ent:{principal_id}:{grants_version}"


def cache_lifetime(entitlements: EntitlementSet, now: datetime) -> int:
    """Whole seconds a cached copy of this set may live from `now`. Zero means do not cache.

    Bounded by `next_grant_lapse`, rounded down so the entry is gone by the instant rather than up
    to a second after it, and by `CACHE_TTL_SECONDS` above. The principal's `not_after` is not a
    bound here; `_usable` judges it on every hit. See
    `A_CACHED_REACH_LIVES_NO_LONGER_THAN_IT_STAYS_TRUE`.
    """
    if entitlements.next_grant_lapse is None:
        return CACHE_TTL_SECONDS
    remaining = math.floor((entitlements.next_grant_lapse - now).total_seconds())
    return max(0, min(CACHE_TTL_SECONDS, remaining))


@dataclass(frozen=True)
class Resolved:
    """A caller's reach, its hash, and where it came from.

    `from_cache` exists so a trace can show it. A cache hit rate nobody can see is one
    nobody notices collapsing, and the first symptom would be a latency complaint rather
    than a cache problem.
    """

    entitlements: EntitlementSet
    ent_hash: str
    grants_version: int
    from_cache: bool


async def resolve(
    principal_id: str,
    *,
    versions: VersionSource,
    store: EntitlementStore,
    cache: EntitlementCache,
    now: datetime | None = None,
) -> Resolved:
    """M3.3.1 and M3.3.2: resolve the caller's reach and compute its hash.

    The hash is computed here from the set just resolved, never carried alongside it from
    the store. A stored hash is a second copy of a fact, and the two copies disagree the
    first time anyone edits grants without recomputing it, at which point the cache is
    keyed on one reach while the answer uses another.

    The instant is read once, and a caller who has one should pass it: the cached set's
    expiry and the store's load are both judged at it.
    """
    instant = now if now is not None else datetime.now(UTC)
    try:
        version = await versions.grants_version(principal_id)
    except Exception as exc:
        # The same guard as `store.load` below, and it was missing here for the same
        # reason it is easy to miss: this call looks like bookkeeping rather than I/O. It
        # is a database read, and whatever the driver raises would otherwise cross the
        # gate unchanged, connection string and all.
        #
        # Refuses rather than carrying on without a version. Carrying on would mean
        # skipping the cache and loading fresh, which is correct but useless: the version
        # source and the store are the same database, so a failure here means the load is
        # about to fail too, and the only thing the fall-through achieves is a second
        # error and a thundering herd onto a database that is already unwell.
        raise ResolutionFailedError(f"reading grants version for {principal_id}: {exc}") from exc
    key = cache_key(principal_id, version)

    cached = await cache.get(key)
    if cached is not None and _usable(cached, principal_id, instant):
        return Resolved(
            entitlements=cached,
            ent_hash=cached.ent_hash(),
            grants_version=version,
            from_cache=True,
        )

    try:
        loaded = await store.load(principal_id, instant)
    except Exception as exc:
        # Broad on purpose. Whatever the driver raises, a caller of this function must see
        # a failure it can distinguish from holding nothing, not a psycopg error leaking
        # through the gate with a connection string in its message.
        raise ResolutionFailedError(f"loading entitlements for {principal_id}: {exc}") from exc

    if loaded.principal_id != principal_id:
        # The catastrophic failure, and one comparison to rule out. A store returning the
        # wrong row hands one person another person's reach, and every check downstream
        # would pass, because the set is internally consistent.
        raise ResolutionFailedError(
            f"store returned entitlements for {loaded.principal_id} when asked for {principal_id}"
        )

    # Cached even when the principal has expired. Expiry is a property of the set, checked
    # wherever the set is used. Not cached once a grant's lapse has been reached, and never for
    # longer than the lapse leaves: see `A_CACHED_REACH_LIVES_NO_LONGER_THAN_IT_STAYS_TRUE`.
    lifetime = cache_lifetime(loaded, instant)
    if lifetime > 0:
        await cache.set(key, loaded, lifetime)
    return Resolved(
        entitlements=loaded,
        ent_hash=loaded.ent_hash(),
        grants_version=version,
        from_cache=False,
    )


def _usable(cached: EntitlementSet, principal_id: str, now: datetime) -> bool:
    """Whether a cache hit may be served.

    A cache is a shared, mutable store that other processes write to, so a value coming out
    of it is checked as though it arrived from outside, which it did. The principal check
    catches a key collision or a mis-set; the expiry check catches a set cached before an
    expiry that has since passed, which the TTL alone would not, because a sixty-second TTL
    happily outlives a contractor whose access ended thirty seconds ago. The lapse check is the
    same argument for one grant: the entry's lifetime is capped at it, and a cache keeping time
    by its own clock is still not trusted to have honoured that.
    """
    if cached.principal_id != principal_id:
        return False
    if cached.next_grant_lapse is not None and now >= cached.next_grant_lapse:
        return False
    return not cached.is_expired(now)
