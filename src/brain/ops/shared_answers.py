"""One answer computed once when several people of equal reach ask the same thing at once.

**A shared execution is a cache entry that has not finished yet.** That sentence is the whole
design and it is `brain.ops.scaling.A_SHARED_EXECUTION_IS_A_CACHE_ENTRY_THAT_HAS_NOT_FINISHED_YET`.
The answer cache already says who may be handed an answer: a person whose question, entitlement
hash, agent configuration, policy epoch and source epochs all equal those it was stored under.
Until now nothing used the same rule for an answer being computed, so ten colleagues of one
department asking one question in the same half minute paid for ten model runs, nine of which
produced an answer the first one's store would have served them seconds later.

**What is shared is the wait, never the answer.** A follower does not receive the leader's text
in memory. It waits for the leader to finish and then looks in the answer cache under its own key,
exactly as a later asker would. So the follower can only ever be handed what the cache would have
handed it, and a leader that was refused, abstained, failed or was halted stores nothing and
leaves the follower to answer for itself. The rejected design was handing the leader's `Answered`
to each follower directly: it is quicker by one lookup and it makes this module a second place
that decides who may see an answer, which is the failure `brain.gate.cache_key` opens with. Here
the only decision made is `brain.ops.scaling.share_role`, which compares the cache's own key.

**Equal, never similar.** Two requests with different entitlement hashes are two requests, however
alike their reaches look. `brain.ops.scaling.coalescing_gaps` fails the build on a field that
admits a tolerance and on a key that has lost the hash. A volatile question is not registered
(`brain.ops.scaling.A_QUESTION_TOO_VOLATILE_TO_CACHE_IS_TOO_VOLATILE_TO_SHARE`), so what the
cache refuses to keep is also never waited for.

**Per process, and said so.** The registry lives in one web process. Two replicas each compute a
question their callers share across them, which costs one extra run and is no worse than before.
A table every process wrote to would put a database round trip in front of every answer to save
runs only on the rare simultaneous ones, and would need its own expiry for a process that died
mid-run. That is rejected until a reading from `/install/capacity` shows it is wanted.

**A wait is bounded.** `A_FOLLOWER_WAITS_AT_MOST_THIS_LONG` is the longest a follower holds back:
past it the follower answers for itself, so a leader that hangs costs a follower seconds and not
its question. A woken follower whose lookup finds nothing joins the next run in flight, or leads
one, up to `FOLLOWER_ROUNDS` times, so a leader that failed does not send every follower to the
model at once.

**Off until the owner has seen it work.** See `brain.ops.features_declared.shared_answer_runs`.
Nothing here is reached with the switch off, and with it off a request is answered as it was.

Task ids: M36.2.3.1, M36.2.3.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.federation import FlightRole
from brain.gate.cache_key import CachedAnswer, CacheKeyParts, cache_key
from brain.ops.features import is_on
from brain.ops.features_declared.shared_answer_runs import SHARED_ANSWER_RUNS
from brain.ops.scaling import share_role, volatile

#: The longest a follower waits for the run it joined, in seconds.
#:
#: **Longer than the answer lane's whole wall-clock budget**
#: (`brain.models.routing.ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS`), because a leader that has not
#: finished by then has been stopped by that budget and will release within moments, and a
#: follower that gave up earlier would pay for a second run while the first was still going. Not
#: much longer, because a wait past the budget is a leader that is stuck and not slow.
FOLLOWER_WAIT_SECONDS: Final[float] = 45.0

#: How many runs a follower may join in turn before it answers for itself.
#:
#: Two, so that a leader that stored nothing sends its followers to one new leader and not to the
#: model together; a third waiting is a request that has already been held for most of a minute.
FOLLOWER_ROUNDS: Final = 2

A_FOLLOWER_WAITS_AT_MOST_THIS_LONG: Final = (
    "A follower holds back for the run in flight for a bounded time and then answers for itself, "
    "so a leader that hangs delays a follower by seconds and never leaves a question unanswered."
)

WHAT_A_FOLLOWER_IS_HANDED_IS_WHAT_THE_CACHE_WOULD_HAVE_HANDED_IT: Final = (
    "A follower is given an answer only by looking in the answer cache under its own key after "
    "the leader has finished. It is never handed the leader's answer directly, so sharing a wait "
    "cannot show anyone an answer the cache would not."
)


@dataclass
class _Running:
    """One answer being computed: the parts it was registered under and the signal it is done."""

    parts: CacheKeyParts
    done: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True)
class Flight:
    """The leader's handle on its own registration. Released once, whatever happened."""

    _registry: InFlightAnswers
    _key: str
    _running: _Running

    def release(self) -> None:
        """Remove the registration and wake every follower. Safe to call twice."""
        self._registry.finish(self._key, self._running)


@dataclass(frozen=True)
class Arrival:
    """What a request that has missed the cache is to do about a run in flight.

    `found` is an answer a leader stored, taken from the cache under this request's own key, and
    `flight` is the registration this request must release when it has finished, which is None
    for a follower, for a volatile question and for a request that gave up waiting.
    """

    found: CachedAnswer | None
    flight: Flight | None
    #: Whether this request waited for another's run, whatever came of it.
    waited: bool = False


class InFlightAnswers:
    """The answer executions in flight in this process, keyed by the cache's own key."""

    def __init__(self, *, wait_seconds: float = FOLLOWER_WAIT_SECONDS) -> None:
        self._running: dict[str, _Running] = {}
        self._wait_seconds = wait_seconds

    def in_flight(self) -> int:
        """How many answers are being computed here now."""
        return len(self._running)

    def finish(self, key: str, running: _Running) -> None:
        """Remove `running` if it is still the one registered under `key`, and wake its followers.

        Compared by identity so a leader that releases late cannot remove a newer run that took
        the slot after it.
        """
        if self._running.get(key) is running:
            del self._running[key]
        running.done.set()

    async def arrive(
        self, parts: CacheKeyParts, *, look: Callable[[], CachedAnswer | None]
    ) -> Arrival:
        """Lead this answer or wait for the one in flight.

        `look` is the cache lookup under this request's own key, called after a wait and only
        then. See `WHAT_A_FOLLOWER_IS_HANDED_IS_WHAT_THE_CACHE_WOULD_HAVE_HANDED_IT`.
        """
        if volatile(parts):
            return Arrival(None, None)
        key = cache_key(parts)
        waited = False
        for _ in range(FOLLOWER_ROUNDS + 1):
            running = self._running.get(key)
            if running is None or share_role(parts, running.parts) is FlightRole.LEADER:
                mine = _Running(parts)
                self._running[key] = mine
                return Arrival(None, Flight(self, key, mine), waited)
            waited = True
            try:
                await asyncio.wait_for(running.done.wait(), self._wait_seconds)
            except TimeoutError:
                return Arrival(None, None, waited)
            found = look()
            if found is not None:
                return Arrival(found, None, waited)
        return Arrival(None, None, waited)


async def answers_are_shared(sessions: async_sessionmaker[AsyncSession] | None) -> bool:
    """Whether `shared_answer_runs` is switched on. Off on a process with no database."""
    if sessions is None:
        return False
    async with sessions() as session:
        return await is_on(session, SHARED_ANSWER_RUNS)


def flights_of(state: Any) -> InFlightAnswers:
    """This process's registry, created on first use and kept on the application state."""
    found = getattr(state, "in_flight_answers", None)
    if isinstance(found, InFlightAnswers):
        return found
    made = InFlightAnswers()
    state.in_flight_answers = made
    return made
