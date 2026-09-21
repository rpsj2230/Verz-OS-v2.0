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

**Probes are replayed beside the attempts, and never as attempts.** The background prober
(`brain.ops.model_probe_run`) cannot write an attempt row, because a probe belongs to no trace and
no request, and it must not: `health.PROBE_OUTCOMES_STAY_OUT_OF_THE_LIVE_RING`. Its outcomes are
kept in `ops.provider_health`'s probe ring, each with its instant, and `replayed` takes them as a
second stream, interleaved by time and handed to `ProviderHealth.record_probe`, which is the only
transition that lets a probe move a breaker: a half-open admission, or two failures on a deployment
with no current live traffic. That is what makes the prober's work reach a person's next question
in every process, by the same replay that makes the attempts agree. See
`A_PROBE_REACHES_THE_BREAKER_ONLY_THROUGH_RECORD_PROBE`.

**`ops.provider_health` keeps both rings, bounded by count and not by age** (M5.4.3). The live ring
is appended by the executor after every attempt that answered or failed on the provider's side,
and the probe ring by the prober. The breaker is still replayed from the attempts inside the
window; what the stored live ring adds is the record that outlives that window, so a rung nothing
has called for an hour still shows its last twenty outcomes and when the newest was. `RingEntry`
and `ring_of` are the rows' shape, read leniently: an entry this release cannot read is left out
rather than failing the plan.

Scope: pure. The attempts are a parameter.

Task ids: M27.8.8, M5.3.4, M5.4.1, M5.4.3, M5.4.7
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from brain.models.driver import DriverFailure
from brain.models.health import PROBE_WINDOW, ProviderHealth
from brain.models.routing import BREAKER_LIVE_WINDOW, FallbackTrigger

# ------------------------------------------------------------------- written-down reasons

#: Why the breaker is computed from the attempt rows rather than held or stored.
HEALTH_IS_REPLAYED_FROM_THE_ATTEMPTS_SO_EVERY_PROCESS_AGREES: Final = (
    "Every try is already written once, by the process that made it, to ops.model_attempt. A "
    "breaker held in memory differs between server processes, so a provider one process saw "
    "fail keeps receiving questions from the others; a breaker stored as a row is rewritten by "
    "every process after every call and they race. Replaying the attempts gives every process "
    "and the screen the same breaker from rows nobody overwrites."
)

#: Why probe outcomes are replayed through `record_probe` and never as attempts.
A_PROBE_REACHES_THE_BREAKER_ONLY_THROUGH_RECORD_PROBE: Final = (
    "A probe is a synthetic request the worker chose to send, so it is not an attempt and never "
    "enters the live ring. Replayed beside the attempts it goes through "
    "ProviderHealth.record_probe, which lets it settle a half-open breaker and open an idle one on "
    "two failures, and nothing else. Written as an attempt it would move the fail ratio and the "
    "prober would vote on its own verdict."
)

#: How many live outcomes `ops.provider_health` keeps per deployment: the breaker's own window.
LIVE_RING_CAP: Final = BREAKER_LIVE_WINDOW

#: How many probe outcomes it keeps: the probe window `ProviderHealth` reads.
PROBE_RING_CAP: Final = PROBE_WINDOW

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


@dataclass(frozen=True)
class Probe:
    """One probe that came back: which deployment, when it was sent, and whether it answered."""

    deployment_id: str
    at: datetime
    ok: bool

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            msg = "a naive probe instant orders probes by the server's offset rather than by time"
            raise EvidenceError(msg)


@dataclass(frozen=True)
class RingEntry:
    """One outcome in a stored ring: whether it answered, and when."""

    ok: bool
    at: datetime

    def stored(self) -> dict[str, object]:
        """The entry as the ring's jsonb holds it."""
        return {"ok": self.ok, "at": self.at.isoformat()}


def ring_of(stored: object) -> tuple[RingEntry, ...]:
    """A stored ring, oldest first, leaving out any entry this release cannot read."""
    if not isinstance(stored, list):
        return ()
    found: list[RingEntry] = []
    for one in stored:
        if not isinstance(one, dict):
            continue
        ok, at = one.get("ok"), one.get("at")
        if not isinstance(ok, bool) or not isinstance(at, str):
            continue
        try:
            when = datetime.fromisoformat(at)
        except ValueError:
            continue
        if when.tzinfo is None:
            continue
        found.append(RingEntry(ok=ok, at=when))
    return tuple(found)


@dataclass(frozen=True)
class StoredRings:
    """One deployment's `ops.provider_health` row: both rings and the two instants."""

    deployment_id: str
    provider: str
    live: tuple[RingEntry, ...] = ()
    probe: tuple[RingEntry, ...] = ()
    last_live_at: datetime | None = None
    last_probe_at: datetime | None = None

    def probes(self, since: datetime) -> tuple[Probe, ...]:
        """The probe outcomes inside the replay window, as the replay takes them."""
        return tuple(
            Probe(deployment_id=self.deployment_id, at=one.at, ok=one.ok)
            for one in self.probe
            if one.at >= since
        )


def outcome_of(failure: DriverFailure | None) -> str:
    """What an attempt is recorded as: `ok`, `refused`, its trigger, or `stopped` with none."""
    if failure is None:
        return OK
    if failure.refused:
        return REFUSED
    trigger = failure.trigger
    return STOPPED if trigger is None else trigger.value


def replayed(
    attempts: Iterable[Attempt], probes: Iterable[Probe] = ()
) -> Mapping[str, ProviderHealth]:
    """Every attempted or probed deployment's health, from its evidence in the order it arrived.

    Ties on the instant are broken by the deployment, then attempts before probes, then by the
    outcome, so two readings of the same rows replay them in the same order and reach the same
    breaker. Probes go through `record_probe` alone: see
    `A_PROBE_REACHES_THE_BREAKER_ONLY_THROUGH_RECORD_PROBE`.
    """
    events: list[tuple[datetime, str, int, str, Attempt | Probe]] = [
        (one.finished_at, one.deployment_id, 0, one.outcome, one) for one in attempts
    ]
    events += [(one.at, one.deployment_id, 1, str(one.ok), one) for one in probes]
    found: dict[str, ProviderHealth] = {}
    for at, deployment, _, _, one in sorted(events, key=lambda e: e[:4]):
        known = found.get(deployment, ProviderHealth.for_deployment(deployment))
        if isinstance(one, Probe):
            found[deployment] = known.record_probe(ok=one.ok, now=at, jitter=0.0)
            continue
        # Advanced to the attempt's instant first, as the executor's own admission does before
        # it sends: an attempt that answered after a cooldown ended is the half-open request
        # coming back clean, and recorded against a breaker still reading open it would be
        # dropped as a stray and the provider would stay out of rotation on the screen.
        health = known.advance(at)
        if one.outcome == OK:
            health = health.record_live_success(at)
        elif one.outcome in ILL_HEALTH:
            health = health.record_live_failure(at, jitter=0.0)
        found[deployment] = health
    return MappingProxyType(found)
