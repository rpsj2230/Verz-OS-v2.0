"""Who holds a slot of a capacity budget, and who is waiting for one, counted across processes.

`brain.ops.admission` decides and counts nothing: `decide` is handed a `CapacityState` and trusts
it. Until this module the one caller that asked it anything, the queued upload, built that state
from the job queue's running count and never passed a waiting one, so every position it could
have given was 1, the document read in the request by a person waiting was counted nowhere, and
the three workload classes shared a budget only on paper. This is the count, kept in the install's
own cache so every process reads the same one. It holds no policy: which class a request is in,
what share of a budget that class may use and what the verdict is are `admission`'s, and this
module loads, calls `decide` and writes what it decided, which is the split `brain.ops.limits` and
`brain.ops.limit_store` keep for the same reason.

**A slot is a lease that lapses on its own.** The cheaper design is a counter: add one when work
is taken and subtract one when it is given back. A process killed between the two never
subtracts, and the budget is one slot smaller for ever, which reads on every screen as the machine
being busy and is repaired by nobody because nothing is wrong with the machine. So a slot is a
member of a sorted set whose score is the instant it lapses, a count is the members whose instant
is still to come, and a process that dies mid-work frees its slot when its lease ends without
anybody giving it back. See `A_SLOT_NOBODY_GAVE_BACK_IS_FREED_BY_ITS_LEASE`.

**The slot is taken in the transaction that decided it.** Both sets are watched, read, handed to
`decide` in Python, and written by a transaction that fails if either moved, so two takers who
both saw one slot free cannot both take it: one of them retries and reads the other's lease.
That is `limit_store`'s optimistic transaction and its reason: the rule exists once, in
`admission`, and a server-side script deciding the same thing would be a second copy in a second
language that no test here reads.

**Waiting is counted beside the slots, so a queue position is a position.** `decide` reads the
number already waiting only to say where a new arrival stands, and never to admit or refuse. So a
waiting entry is kept for its expected wait and one lease more, and one that lapses before its
work started makes the positions after it shorter and lets nothing in. See
`A_PLACE_IN_THE_QUEUE_NEVER_ADMITS_ANYTHING`.

**When the cache does not answer, the caller's own count decides and nothing is recorded.** Every
budget this counts is on this machine (a model call is also a vendor's, and the vendor's ceiling
is guarded by `limit_store`'s connector windows, which fail closed and are asked separately), and
each door that asks here has a bound that holds without the cache: the upload read in the request
parses one document at a time in its process, and the queued upload refuses at the job queue's own
depth. So an outage answers with `decide` over the state the caller counted itself, marked
degraded, holding nothing to give back. Refusing every upload because the cache is down would take
a working door away to protect a budget whose other bounds still stand. See
`AN_UNANSWERED_LEDGER_DECIDES_ON_WHAT_THE_CALLER_COUNTED`.

**The keys are namespaced, and the product's are `LIVE`.** A check that proves the classes on an
install takes and queues under a namespace named for its run, so no real upload is ever counted
against it and nothing it leaves outlives its removal. Every segment is percent-encoded, for
`limit_store`'s reason: two keys can never render to the same string.

**A rate budget is refused.** A slot of tokens a minute is free when the minute rolls, whatever
anybody gives back, and a lease cannot say that. Those budgets are sliding windows, which is
`brain.ops.limits`.

Task ids: M22.1.3, M22.1.4, M22.1.5, M22.2.1, M22.2.3
"""

from __future__ import annotations

import enum
import math
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Protocol, cast
from urllib.parse import quote

import structlog
from redis.exceptions import RedisError, WatchError

from brain.ops.admission import (
    AdmissionDecision,
    AdmissionRequest,
    Budget,
    BudgetKey,
    BudgetKind,
    CapacityState,
    Verdict,
    budget_for,
    decide,
)
from brain.ops.halt import NOTHING_HALTED, HaltState
from brain.ops.limit_store import StoreHealth

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a slot is a lease rather than one count.
A_SLOT_NOBODY_GAVE_BACK_IS_FREED_BY_ITS_LEASE: Final = (
    "A counter taken on start and given back on finish loses a slot for ever to every process "
    "killed between the two, and the budget then reads as busy on a machine with nothing wrong "
    "with it. A slot is a member whose score is the instant it lapses, so the count is the "
    "leases still running, and work nobody gave back stops being counted when its lease ends."
)

#: Why a waiting entry that lapses early is harmless.
A_PLACE_IN_THE_QUEUE_NEVER_ADMITS_ANYTHING: Final = (
    "decide reads how many are waiting only to say where a new arrival stands. A waiting entry "
    "that lapses before its work starts makes the positions after it shorter and admits "
    "nothing, so it is kept for its expected wait and one lease more and not for ever."
)

#: What the ledger does when the cache does not answer, and why.
AN_UNANSWERED_LEDGER_DECIDES_ON_WHAT_THE_CALLER_COUNTED: Final = (
    "Every budget counted here is on this machine, and every door asking here has a bound that "
    "holds without the cache: one parse at a time in a process, and the job queue's own depth. "
    "So when the cache does not answer, decide is asked over the state the caller counted "
    "itself, the answer says it was degraded, and nothing is recorded or held. Refusing every "
    "upload while the cache is down would take a working door away to protect a budget whose "
    "other bounds still stand."
)

#: Why a rate budget has no lease.
A_RATE_BUDGET_IS_A_WINDOW_AND_NOT_A_LEASE: Final = (
    "A slot of a rate budget is free when its window rolls, whatever anybody gives back, and a "
    "lease cannot say that. Rate budgets are brain.ops.limits' sliding windows."
)

# ------------------------------------------------------------------------ the figures
#: Namespaces every key this module writes, apart from `limit_store`'s `lim` and `limref`, so
#: its walk of the windows never finds a slot and a slot is never read as a window.
KEY_PREFIX: Final = "cap"

#: The product's own namespace. A check uses one named for its run.
LIVE: Final = "live"

#: How many times a take retries after losing the race, for `limit_store.MAX_ATTEMPTS`' reason.
MAX_ATTEMPTS: Final = 4

#: A lease lasts this many of the budget's mean service times. Ten, because a lease that ends
#: while its work is still running frees a slot early and admits one more than the budget says,
#: and the service time is a mean: a document ten times the usual length is ordinary.
LEASE_SERVICE_TIMES: Final = 10

#: The shortest lease there is, so a budget with a one-second service time does not free a slot
#: under work that took a few seconds longer than usual.
MIN_LEASE_SECONDS: Final = 60.0

#: Added to a key's expiry beyond its latest member, for `limit_store.TTL_SLACK_SECONDS`' reason.
TTL_SLACK_SECONDS: Final = 5


class Kept(enum.StrEnum):
    """The two sets kept per budget: the slots in use, and the places in the queue."""

    HELD = "held"
    WAITING = "waiting"


class LedgerUnreadableError(Exception):
    """The cache did not answer, so what is in use cannot be said.

    Raised rather than answered with an empty state, because an empty state reads as a machine
    with nothing deferred, which is the reassuring answer and the wrong one during an outage.
    """


# ------------------------------------------------------------------------------ the keys
def _segment(value: str) -> str:
    """One key segment with the separator made impossible, as `limit_store._segment` argues."""
    return quote(value, safe="")


def render_key(namespace: str, budget_key: BudgetKey, kept: Kept) -> str:
    """The cache key for one budget's slots or queue. Injective: distinct keys, distinct strings."""
    resource, key = budget_key
    return ":".join(
        (KEY_PREFIX, _segment(namespace), _segment(str(resource)), _segment(key), kept.value)
    )


def keys_for(namespace: str, budget_keys: Iterable[BudgetKey]) -> tuple[str, ...]:
    """Every key a namespace may have written for these budgets, for removing them by name."""
    return tuple(render_key(namespace, one, kept) for one in budget_keys for kept in Kept)


def unit_members(member: str, units: int) -> tuple[str, ...]:
    """One set member per unit held, so work holding three slots is counted as three."""
    return tuple(f"{member}/{n}" for n in range(units))


def lease_seconds(budget: Budget) -> float:
    """How long one slot of this budget is held before it lapses on its own."""
    return max(MIN_LEASE_SECONDS, LEASE_SERVICE_TIMES * budget.mean_service_seconds)


def new_member() -> str:
    """An opaque member for work with no name of its own. Meaningless, for `limit_store._member`'s
    reason: a member carrying a principal id would put an identifier in a store with its own
    retention."""
    return uuid.uuid4().hex


# ------------------------------------------------------------------------------ the shapes
@dataclass(frozen=True)
class Hold:
    """What one take left in the ledger, so exactly that can be given back."""

    budget_key: BudgetKey
    member: str
    units: int = 1
    #: True for slots in use, False for a place among those waiting.
    held: bool = True


@dataclass(frozen=True)
class Taken:
    """A decision, what it left in the ledger, and whether the ledger was read to make it."""

    decision: AdmissionDecision
    #: None when nothing was recorded: a shed, or a decision the cache could not be asked for.
    hold: Hold | None = None
    #: True when the cache did not answer and the caller's own count decided. See
    #: `AN_UNANSWERED_LEDGER_DECIDES_ON_WHAT_THE_CALLER_COUNTED`.
    degraded: bool = False

    @property
    def admitted(self) -> bool:
        return self.decision.admitted


class LedgerPipeline(Protocol):
    """The commands one transaction needs. `redis.client.Pipeline` satisfies it structurally."""

    def __enter__(self) -> LedgerPipeline: ...
    def __exit__(self, *exc: object) -> None: ...
    def watch(self, *names: str) -> object: ...
    def multi(self) -> None: ...
    def execute(self) -> list[Any]: ...
    def zrange(self, name: str, start: int, end: int, *, withscores: bool = False) -> Any: ...
    # Spelled as redis-py spells them; see `limit_store.WindowPipeline`.
    def zremrangebyscore(self, name: str, min: Any, max: Any) -> object: ...  # noqa: A002
    def zadd(self, name: str, mapping: Mapping[str, float]) -> object: ...
    def zrem(self, name: str, *values: str) -> object: ...
    def expire(self, name: str, time: int) -> object: ...


class LedgerClient(Protocol):
    """Whatever hands out pipelines and reads a set. `redis.Redis` and `valkey.Valkey` both do."""

    def pipeline(self) -> LedgerPipeline: ...
    def zrange(self, name: str, start: int, end: int, *, withscores: bool = False) -> Any: ...


def _scores(rows: Any, now: float, *, leaving: Iterable[str] = ()) -> list[float]:
    """The lapse instants still to come, leaving out the members named.

    Leaving out a take's own members is what makes asking twice for one piece of work the same
    as asking once: the same ticket sent again finds its own place and does not count it twice.
    """
    left = set(leaving)
    found: list[float] = []
    for member, score in rows:
        name = member.decode("utf-8") if isinstance(member, bytes) else str(member)
        if name not in left and float(score) > now:
            found.append(float(score))
    return found


def _ttl(latest: float, now: float) -> int:
    """A key's expiry: past its latest member by the slack, and never under a second."""
    return max(1, math.ceil(latest - now) + TTL_SLACK_SECONDS)


# ------------------------------------------------------------------------------ the ledger
@dataclass
class CapacityLedger:
    """The slots and queues of `brain.ops.admission`'s budgets, over the install's cache."""

    client: LedgerClient
    namespace: str = LIVE
    health: StoreHealth = field(default_factory=StoreHealth)

    def admit(
        self,
        request: AdmissionRequest,
        budgets: Sequence[Budget],
        *,
        now: datetime,
        member: str | None = None,
        fallback: CapacityState | None = None,
        halts: HaltState = NOTHING_HALTED,
    ) -> Taken:
        """Decide, and hold what was decided: slots when admitted, a place when queued.

        `member` names the work, so the same work asked for twice is one hold rather than two;
        unnamed work gets an opaque one. `fallback` is what the caller counted itself, used only
        when the cache does not answer.
        """
        budget = budget_for(budgets, request.budget_key)
        if budget is not None and budget.kind is BudgetKind.RATE:
            raise ValueError(A_RATE_BUDGET_IS_A_WINDOW_AND_NOT_A_LEASE)
        name = member or new_member()
        key = request.budget_key
        held_key = render_key(self.namespace, key, Kept.HELD)
        waiting_key = render_key(self.namespace, key, Kept.WAITING)
        mine = unit_members(name, request.units)
        instant = now.timestamp()
        self.health.checks += 1
        for attempt in range(MAX_ATTEMPTS + 1):
            try:
                with self.client.pipeline() as pipe:
                    pipe.watch(held_key, waiting_key)
                    held = _scores(
                        pipe.zrange(held_key, 0, -1, withscores=True), instant, leaving=mine
                    )
                    waiting = _scores(
                        pipe.zrange(waiting_key, 0, -1, withscores=True), instant, leaving=(name,)
                    )
                    state = CapacityState(used={key: len(held)}, queued={key: len(waiting)})
                    decision = decide(request, budgets, state, now=now, halts=halts)
                    pipe.multi()
                    # Pruned inside the transaction rather than before it: a write to a watched
                    # key by the watching connection before MULTI fails the transaction it guards.
                    pipe.zremrangebyscore(held_key, "-inf", instant)
                    pipe.zremrangebyscore(waiting_key, "-inf", instant)
                    hold = self._record(pipe, decision, budget, name, mine, held, waiting, instant)
                    pipe.execute()
                    return Taken(decision=decision, hold=hold)
            except WatchError:
                self.health.contention += 1
                if attempt >= MAX_ATTEMPTS:
                    self.health.spins += 1
                    log.warning("capacity ledger contended out", attempts=attempt + 1)
                    return self._degraded(request, budgets, now, fallback, halts)
                continue
            except (RedisError, OSError) as exc:
                self.health.outages += 1
                # No member is logged: a member may be a ticket, and a ticket names an upload.
                log.warning("capacity ledger unreachable", error=type(exc).__name__)
                return self._degraded(request, budgets, now, fallback, halts)
        # Not reachable: every path in the loop returns or continues, and the last iteration
        # returns. Present so a future edit to the bounds cannot fall through to None.
        msg = "the retry loop fell through"
        raise AssertionError(msg)

    def _record(
        self,
        pipe: LedgerPipeline,
        decision: AdmissionDecision,
        budget: Budget | None,
        name: str,
        mine: tuple[str, ...],
        held: list[float],
        waiting: list[float],
        instant: float,
    ) -> Hold | None:
        """Write what the decision took into the open transaction, and say what that was."""
        key = decision.request.budget_key
        if budget is None or decision.verdict is Verdict.SHED:
            return None
        if decision.verdict is Verdict.ADMITTED:
            lapses = instant + lease_seconds(budget)
            held_key = render_key(self.namespace, key, Kept.HELD)
            pipe.zadd(held_key, dict.fromkeys(mine, lapses))
            pipe.zrem(render_key(self.namespace, key, Kept.WAITING), name)
            pipe.expire(held_key, _ttl(max([lapses, *held]), instant))
            return Hold(budget_key=key, member=name, units=len(mine), held=True)
        # Queued. `decide` gives every queued decision a placement; the fallback is the lease
        # alone, which keeps the place as long as one piece of work could take.
        wait = decision.queue.expected_wait_seconds if decision.queue is not None else 0.0
        lapses = instant + wait + lease_seconds(budget)
        waiting_key = render_key(self.namespace, key, Kept.WAITING)
        pipe.zadd(waiting_key, {name: lapses})
        pipe.expire(waiting_key, _ttl(max([lapses, *waiting]), instant))
        return Hold(budget_key=key, member=name, units=len(mine), held=False)

    def _degraded(
        self,
        request: AdmissionRequest,
        budgets: Sequence[Budget],
        now: datetime,
        fallback: CapacityState | None,
        halts: HaltState,
    ) -> Taken:
        """`AN_UNANSWERED_LEDGER_DECIDES_ON_WHAT_THE_CALLER_COUNTED`: decided, held nowhere."""
        self.health.fail_open += 1
        counted = fallback if fallback is not None else CapacityState()
        return Taken(
            decision=decide(request, budgets, counted, now=now, halts=halts),
            hold=None,
            degraded=True,
        )

    def begin(self, budget: Budget, member: str, *, now: datetime) -> bool:
        """Work that was admitted or queued earlier starts now: its place becomes a slot.

        Records rather than decides. The work was decided when it was asked for, and the worker
        starting it runs one at a time, which is its own bound; deciding again here would refuse
        work already promised a place. Answers whether the cache took it, and a False is the
        caller's to log and carry on from: the work runs uncounted, which is the outage answer.
        """
        key = budget.budget_key
        held_key = render_key(self.namespace, key, Kept.HELD)
        instant = now.timestamp()
        lapses = instant + lease_seconds(budget)
        try:
            # Read outside the transaction and unwatched: all it decides is the key's expiry, and
            # a race there moves that by at most one lease, which is not worth a retry in front
            # of the work itself.
            held = _scores(self.client.zrange(held_key, 0, -1, withscores=True), instant)
            with self.client.pipeline() as pipe:
                pipe.multi()
                pipe.zadd(held_key, dict.fromkeys(unit_members(member, 1), lapses))
                pipe.zrem(render_key(self.namespace, key, Kept.WAITING), member)
                pipe.expire(held_key, _ttl(max([lapses, *held]), instant))
                pipe.execute()
        except (RedisError, OSError) as exc:
            self.health.outages += 1
            log.warning("capacity ledger did not record a start", error=type(exc).__name__)
            return False
        return True

    def give_back(self, hold: Hold) -> bool:
        """Free what a take held. Answers whether the cache took it.

        A False costs nothing but time: the lease lapses on its own. See
        `A_SLOT_NOBODY_GAVE_BACK_IS_FREED_BY_ITS_LEASE`.
        """
        try:
            with self.client.pipeline() as pipe:
                pipe.multi()
                pipe.zrem(
                    render_key(self.namespace, hold.budget_key, Kept.HELD),
                    *unit_members(hold.member, hold.units),
                )
                pipe.zrem(render_key(self.namespace, hold.budget_key, Kept.WAITING), hold.member)
                pipe.execute()
        except (RedisError, OSError) as exc:
            self.health.outages += 1
            log.warning("capacity ledger did not take a slot back", error=type(exc).__name__)
            return False
        return True

    def counts(self, budgets: Sequence[Budget], *, now: datetime) -> CapacityState:
        """What is in use and waiting on every concurrency budget, read and never written.

        Nothing is pruned, for `limit_store.ValkeyWindowStore.live`'s reason: a screen that
        changed the ledger by being opened would read differently depending on who looked last.
        A lapsed lease counts for nothing either way. Raises `LedgerUnreadableError` when the
        cache does not answer.
        """
        instant = now.timestamp()
        used: dict[BudgetKey, int] = {}
        queued: dict[BudgetKey, int] = {}
        try:
            for budget in budgets:
                if budget.kind is not BudgetKind.CONCURRENCY:
                    continue
                key = budget.budget_key
                for kept, into in ((Kept.HELD, used), (Kept.WAITING, queued)):
                    rows = self.client.zrange(
                        render_key(self.namespace, key, kept), 0, -1, withscores=True
                    )
                    into[key] = len(_scores(rows, instant))
        except (RedisError, OSError, UnicodeDecodeError) as exc:
            self.health.outages += 1
            log.warning("capacity ledger could not be read", error=type(exc).__name__)
            msg = "what is in use could not be read"
            raise LedgerUnreadableError(msg) from exc
        return CapacityState(used=used, queued=queued)


def make_ledger(client: object, *, namespace: str = LIVE) -> CapacityLedger:
    """Wrap a `redis.Redis` (or a `valkey.Valkey`) as a ledger.

    A cast for `limit_store.make_store`'s reason: the client satisfies the protocol structurally,
    and asking mypy to prove that about a library's overloaded signatures buys nothing the
    protocol does not already state.
    """
    return CapacityLedger(client=cast(LedgerClient, client), namespace=namespace)
