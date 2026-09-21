"""A provider's health, read back from the attempts actually made, rather than kept somewhere.

`brain.models.health.ProviderHealth` is the state machine and `ops.model_attempt` is the record
of every try, one row per attempt with its outcome. Until now neither was fed: nothing wrote an
attempt, nothing stored a `ProviderHealth`, and `brain.operate_routes` drew "Not recorded" beside
every provider because `console.model_matrix`'s default, a closed breaker, would have been a
green bar with nobody behind it. This module turns the attempts into the health. **The attempt
rows are the evidence and the breaker is computed from them**, by replaying each finished attempt
through the same transitions `ProviderHealth` applies live.

**Replayed, not stored, and the choice is about agreement between processes.** An install runs
several server processes (`brain.serve` sizes the worker count from the container). A breaker
held in memory is one per process: the process that watched a provider fail three times opens
it, and its siblings go on sending questions there. A breaker stored as a row is one per install
but has to be written after every call by whichever process made it, and two processes writing
it race. The attempts are already written once per try by the process that made the try, so a
breaker replayed from them is the same in every process and on the screen, from rows nobody
overwrites. See `HEALTH_IS_REPLAYED_FROM_THE_ATTEMPTS_SO_EVERY_PROCESS_AGREES`.

What that costs, stated. **The half-open single admission is not shared**: `try_admit` claims in
memory, so after a cooldown each process may send its own first request rather than one process
sending one. At this system's traffic that is a handful of requests where there would have been
one. **Jitter is zero on replay**, so every process computes the same cooldown, which removes the
decorrelation jitter exists for; the same traffic argument applies. And **the window is bounded**:
attempts older than `EVIDENCE_WINDOW` are not replayed, which is longer than the ten-minute
cooldown ceiling, so no breaker the window cuts short could still be open.

**Only a failure that is the provider's is ill health.** A connection that failed, a timeout and a
5xx are. A 429 is the provider asking us to slow down, which `brain.connectors.throttle.
record_outcome` already refuses to count as ill health for a source; a 4xx that stopped the chain
is our request being wrong; a content refusal and a context overflow are properties of the
request. Those rows are evidence that the provider answered, so they make the deployment measured
without moving its breaker either way. See `ONLY_THE_PROVIDERS_OWN_FAILURE_IS_ILL_HEALTH`.

**A deployment with no attempt has no health record at all**, and `measured` in
`brain.console.model_matrix` is how a screen tells that apart from a closed breaker.

Scope: pure. The attempts are a parameter.

Task ids: M27.8.8, M5.3.4, M5.4.1
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from brain.models.driver import DriverFailure
from brain.models.health import ProviderHealth
from brain.models.routing import FallbackTrigger

# ------------------------------------------------------------------- written-down reasons

#: Why the breaker is computed from the attempt rows rather than held or stored.
HEALTH_IS_REPLAYED_FROM_THE_ATTEMPTS_SO_EVERY_PROCESS_AGREES: Final = (
    "Every try is already written once, by the process that made it, to ops.model_attempt. A "
    "breaker held in memory differs between server processes, so a provider one process saw "
    "fail keeps receiving questions from the others; a breaker stored as a row is rewritten by "
    "every process after every call and they race. Replaying the attempts gives every process "
    "and the screen the same breaker from rows nobody overwrites."
)

#: Why only three outcomes open a breaker.
ONLY_THE_PROVIDERS_OWN_FAILURE_IS_ILL_HEALTH: Final = (
    "A refused connection, a timeout and a server error are the provider failing. A rate limit "
    "is the provider working and asking for less; a 4xx that stopped the chain is our request; "
    "a refusal and an overflow are properties of what was asked. Counting those as ill health "
    "would take a working provider out of rotation over a question somebody asked twice."
)

#: The outcome an attempt that answered is recorded under.
OK: Final = "ok"

#: The outcome an attempt that stopped the chain is recorded under: a failure with no trigger.
STOPPED: Final = "stopped"

#: The outcome an attempt the provider declined on content is recorded under (M5.4.1). It stops
#: the chain as `stopped` does and says why, so nobody reads a refusal as our request being wrong.
REFUSED: Final = "refused"

#: Every outcome an attempt can finish with: an answer, a stop, or a member of the closed
#: trigger set. `brain.tables.routing.ATTEMPT_OUTCOMES` is the column's copy and a test holds the
#: two equal; this one is built here so the health layer imports no table.
OUTCOMES: Final[frozenset[str]] = frozenset(
    {OK, REFUSED, STOPPED, *(one.value for one in FallbackTrigger)}
)

#: Outcomes that are the provider's own failure. See the reason constant.
ILL_HEALTH: Final[frozenset[str]] = frozenset(
    {
        FallbackTrigger.CONNECTION_ERROR.value,
        FallbackTrigger.TIMEOUT.value,
        FallbackTrigger.PROVIDER_ERROR.value,
    }
)

#: How far back attempts are replayed. Four times the ten-minute cooldown ceiling in
#: `brain.models.routing.BREAKER_MAX_COOLDOWN_SECONDS`, so a breaker the window starts in the
#: middle of has cooled down long before now, and short enough that a replay per call reads a
#: few hundred rows at this system's traffic rather than a day's.
EVIDENCE_WINDOW: Final = timedelta(minutes=40)


class EvidenceError(ValueError):
    """Raised when an attempt is described in a way the attempt table would refuse."""


@dataclass(frozen=True)
class Attempt:
    """One finished try, as health is replayed from it: which deployment, when, and how."""

    deployment_id: str
    finished_at: datetime
    outcome: str

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            msg = f"{self.outcome!r} is not an outcome ops.model_attempt records"
            raise EvidenceError(msg)
        if self.finished_at.tzinfo is None:
            msg = "a naive finish orders attempts by the server's offset rather than by time"
            raise EvidenceError(msg)


def outcome_of(failure: DriverFailure | None) -> str:
    """What an attempt is recorded as: `ok`, `refused`, its trigger, or `stopped` with none."""
    if failure is None:
        return OK
    if failure.refused:
        return REFUSED
    trigger = failure.trigger
    return STOPPED if trigger is None else trigger.value


def replayed(attempts: Iterable[Attempt]) -> Mapping[str, ProviderHealth]:
    """Every attempted deployment's health, from its attempts in the order they finished.

    Ties on the instant are broken by the deployment and then by the outcome, so two readings of
    the same rows replay them in the same order and reach the same breaker.
    """
    found: dict[str, ProviderHealth] = {}
    for one in sorted(attempts, key=lambda a: (a.finished_at, a.deployment_id, a.outcome)):
        known = found.get(one.deployment_id, ProviderHealth.for_deployment(one.deployment_id))
        # Advanced to the attempt's instant first, as the executor's own admission does before
        # it sends: an attempt that answered after a cooldown ended is the half-open request
        # coming back clean, and recorded against a breaker still reading open it would be
        # dropped as a stray and the provider would stay out of rotation on the screen.
        health = known.advance(one.finished_at)
        if one.outcome == OK:
            health = health.record_live_success(one.finished_at)
        elif one.outcome in ILL_HEALTH:
            health = health.record_live_failure(one.finished_at, jitter=0.0)
        found[one.deployment_id] = health
    return MappingProxyType(found)
