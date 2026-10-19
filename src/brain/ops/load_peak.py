"""The peak-concurrency run against a deployed install, and a small version of it CI can run.

`brain.ops.admission.LOAD_TEST_TARGET` states what has to be reproduced: **two arrivals a second
for ten minutes, the service levels held, and no interactive request shed while batch work is
still admitted.** `tests/load/test_admission_at_peak.py` drives the admission controller at that
rate and holds the shedding rule, which is policy and needs no hardware. What nothing could do
until this module is the other half, the one the capacity model itself says "needs a deployed
system to drive": send questions to a running install at that rate and read the service levels off
what came back. See `brain.ops.admission.M36_2_4_IS_ALREADY_M22_3_AND_M30_5` for why this is the
whole of what was missing.

**The judgement is `brain.ops.reliability`'s and is not restated.** The figures are
`LANE_OBJECTIVES`, the comparison is `attainment`, the success classification is
`SUCCESS_STATUSES`, and the percentile is the nearest-rank one `brain.connectors.throttle`
argues for (an interpolated percentile is a number that never happened). This module only turns a
list of what happened into the observed p95 and success rate each lane is compared with. A second
copy of an objective is a second place for it to be subtly wrong.

**A lane with too few requests is not measured, and that is a finding rather than a pass.**
A p95 over three requests is the slowest of them. `MINIMUM_REQUESTS_FOR_A_P95` is twenty, the
fewest for which the 95th percentile is not simply the maximum, and a lane below it is reported
unmet with the sentence `attainment` already uses for "nothing measures one". A run that sent
no fast-lane question therefore cannot report the fast lane's objective as held.

**A shed request is a failure of the objective and is also counted on its own.** An admission
refusal (a 429 or a 503) protects the system and is the right answer under pressure, but it is not
a request that succeeded, so it counts against the success rate and is reported beside it, because
"the rate fell because the controller shed" and "the rate fell because requests failed" are
different findings with different owners.

**What this does not exercise, said before anything is measured.** Batch work cannot be sent over
the door a person asks through, so the live run drives interactive traffic and measures it *while
whatever batch work the install has is running*: the "zero interactive shed while batch is
admitted" half is held by the admission test above, and this run reports how many interactive
requests were shed so a reader can see the number was not zero by accident. The run calls whatever
model the install is configured with, so **a real run costs real calls**; that is why it is a
command an owner runs, bounded by `--max-requests`, and never something a pipeline does.

**Credentials are read from a file and never from the environment**, one bearer token per line,
because a person's own rate window would refuse a single token at two a second long before the
install did, so the run spreads its requests over as many people as it is given. A token is held
in memory and is never printed, logged or put in a report.

**The peak is the profile's, stated, and a smaller run says it was smaller.** `--profile` names
one of `brain.ops.admission.seed_profiles` (lite, full, ha), whose peak arrival rate and
Little's-law concurrency are the figures the run is driven at and held to, so the stated peak is
read from the capacity model and not typed into a command. A run that was given a lower rate, a
shorter length or a bound that cut it short is still reported, and the report and the record both
say `at_stated_peak` is false: a bounded run that held is evidence the machinery works and nothing
more.
The most requests in flight at once is measured and printed beside the concurrency the profile
states, which is the number the task is named for.

**It is safe in six ways, each a refusal made before anything is sent.** Nothing starts it: it is a
command a person runs in the application's container, no schedule, worker or route reaches it, and
`http_sender` is built only by `main`. It refuses while the install's `load_test` switch is off
(`brain.ops.features_declared.load_test`), which ships off. It refuses unless every token it is
given belongs to a person in the reserved `LOAD_TEST_DEPARTMENT`, asked of the install itself
through `/me`, so a run can never be sent as somebody's real account and never sits on a real
person's rate window or history. It refuses unless the operator repeats the number of requests it
will send (`--confirm-requests`), so a spend is a number somebody typed twice. It refuses where it
has no database to keep its result in
(`brain.ops.load_run_store.A_COMMAND_THAT_CANNOT_KEEP_ITS_RESULT_SENDS_NOTHING`). And it respects
the install's admission limits by never changing one and by stopping when they bind: once at least
`MINIMUM_REQUESTS_FOR_A_P95` replies are in and `STOP_WHEN_SHED_SHARE` of them were shed, it sends
nothing further and says how many planned requests it did not send, because hammering an install
that is refusing is a test of the refusal and not of the peak. What a run leaves behind is stated
in `WHAT_A_RUN_LEAVES_BEHIND`.

**Where the result goes.** Printed, and kept as one `ops.setting` row in the install's own database
(`brain.ops.load_run_store`), with the figures and verdicts and no token, person or question.
Rejected: recording through a new route, which would put a write on the public API for something an
operator does once a quarter at a terminal, and a table, which would need a migration for a handful
of rows.

Scope: arithmetic over what happened, a driver that schedules sends, and one HTTP sender. The only
network reach is the sender and the question it asks of `/me`, and both are built only by `main`.

Task ids: M22.3.3
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from brain.connectors.throttle import percentile_ms
from brain.core.lane import Lane
from brain.ops.admission import LOAD_TEST_TARGET, CapacityProfile, seed_profiles
from brain.ops.load_run_store import Keeper, LaneFigures, RunRecord, RunStoreError, database_keeper
from brain.ops.reliability import (
    LANE_OBJECTIVES,
    SUCCESS_STATUSES,
    ReliabilityError,
    attainment,
    success_rate,
)
from brain.ops.telemetry import RequestStatus

if TYPE_CHECKING:
    import httpx

# ------------------------------------------------------------------ written-down reasons
#: Why a lane with few requests is reported unmet.
A_P95_OVER_A_HANDFUL_IS_THE_MAXIMUM: Final = (
    "The 95th percentile of fewer than twenty requests is the slowest of them, so a lane that was "
    "sent a handful is reported as not measured, which is unmet, and never as held. A run that "
    "forgot to send a lane's questions must not be able to report that lane green."
)

#: Why the live run is something a person starts and is bounded.
A_REAL_RUN_COSTS_REAL_MODEL_CALLS: Final = (
    "The questions are answered by the model the install is configured with, so the run is a "
    "spend as well as a measurement: it is started by the owner, names the most it will send, and "
    "is never scheduled."
)

#: Why a run asks as the people set aside for it and nobody else.
A_RUN_ASKS_AS_RESERVED_TEST_PEOPLE_ONLY: Final = (
    "A run sends over a thousand questions, so it is never sent as a real person: it would sit on "
    "their rate window, fill their history and be attributed to them. Every token it is given is "
    "asked of the install, and unless each belongs to a person in the department set aside for "
    "load tests the run refuses before it sends anything."
)

#: Why a run stops when the install refuses most of what it is asked.
A_RUN_STOPS_WHEN_THE_LIMITS_BIND: Final = (
    "The install's admission limits are the install's to set and a run never changes one. Once "
    "most of what it sends is being shed it stops sending and says how much it did not send, "
    "because a test that keeps hammering an install that is refusing measures the refusal and "
    "not the peak."
)

#: Why a run's spend is a number somebody typed twice.
A_SPEND_IS_CONFIRMED_BY_ITS_NUMBER: Final = (
    "The run names the number of requests it will send and the operator repeats it: a bound that "
    "is only a default is a bound nobody read, and a confirmation that is a yes is a yes to "
    "something not seen."
)

#: What a run leaves behind, said where the operator reads it before starting one.
WHAT_A_RUN_LEAVES_BEHIND: Final = (
    "Every request is an ordinary question to the install's answer route, so each is recorded in "
    "the request ledger against the test person who asked it, and the ledger is append-only: those "
    "rows stay, are attributed to people in the load-test department alone, and name no real "
    "person. Nothing else is written except the run's own result row."
)

#: What a run draws on, said so nobody expects a figure it cannot give.
WHAT_A_RUN_DOES_NOT_MEASURE: Final = (
    "It measures the application at the address it is given, from where it is run: not the "
    "network or proxy in front of it unless the address goes through them, and not the host's "
    "memory headroom."
)

#: The department the people a run asks as sit in, reserved for them the way `acceptance_a` and
#: `acceptance_b` are reserved for the install's checks. An administrator makes it and puts test
#: people and a small fixture document in it; the questions the run asks are about that document.
LOAD_TEST_DEPARTMENT: Final = "load_test"

#: The profile a run is driven at unless it is told another: the one whose peak is
#: `LOAD_TEST_TARGET`'s.
DEFAULT_PROFILE: Final = "full"

#: A run stops sending once this share of the replies it has had were shed, after at least
#: `MINIMUM_REQUESTS_FOR_A_P95` of them. See `A_RUN_STOPS_WHEN_THE_LIMITS_BIND`.
STOP_WHEN_SHED_SHARE: Final = 0.5

# ------------------------------------------------------------------------ the figures
#: Two arrivals a second for ten minutes, straight from `LOAD_TEST_TARGET`. Held equal to that
#: sentence by a test, so editing the target without editing the drive fails.
ARRIVALS_PER_SECOND: Final = 2
PEAK_SECONDS: Final = 600

#: The fewest requests in a lane for its 95th percentile to be more than its maximum.
MINIMUM_REQUESTS_FOR_A_P95: Final = 20

#: The share of arrivals each lane a person's question can reach is sent. The fast lane is the
#: row lookups an install answers without a model; the answer lane is everything else. The task
#: lane is not reachable through the door a person asks at, so it has no share.
MIX: Final[Mapping[Lane, float]] = {Lane.ANSWER: 0.8, Lane.FAST: 0.2}

#: What an admission refusal looks like to a client.
SHED_STATUSES: Final[frozenset[int]] = frozenset({429, 503})

#: The seed the arrivals are drawn with, so two runs of one file send one population.
SEED: Final = 20261012

#: A token or a person who is refused outright ends the run: nothing would be measured.
REFUSED_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

EXIT_UNMET: Final = 1
EXIT_REFUSED: Final = 2

COMMAND: Final = "python -m brain.ops.load_peak"


class LoadError(Exception):
    """A run that cannot measure anything: no questions, no people, or every one refused."""


# ------------------------------------------------------------------------ the values
@dataclass(frozen=True)
class Shape:
    """One arrival: which lane it is expected to take, the question, and whose token sends it."""

    lane: Lane
    question: str
    person: int


@dataclass(frozen=True)
class Sample:
    """What happened to one arrival. The status is the telemetry vocabulary, so the success
    classification is `brain.ops.reliability`'s and not this module's."""

    lane: Lane
    status: RequestStatus
    seconds: float
    shed: bool = False

    def __post_init__(self) -> None:
        if self.seconds < 0:
            msg = "a request cannot take a negative time"
            raise LoadError(msg)
        if self.shed and self.status in SUCCESS_STATUSES:
            msg = "a shed request is not a successful one"
            raise LoadError(msg)


Sender = Callable[[Shape], Awaitable[Sample]]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Profile:
    """What is driven: how fast, for how long, and from what."""

    questions: Mapping[Lane, Sequence[str]]
    people: int
    arrivals_per_second: float = ARRIVALS_PER_SECOND
    seconds: float = PEAK_SECONDS
    max_requests: int | None = None
    seed: int = SEED
    #: The share of arrivals each lane is sent. The install's own mix is `MIX`; a short run that
    #: has to give each lane twenty requests in forty says so here rather than sending two hundred.
    mix: Mapping[Lane, float] = field(default_factory=lambda: dict(MIX))

    def __post_init__(self) -> None:
        if self.people < 1:
            msg = "a run with nobody to ask as sends nothing"
            raise LoadError(msg)
        if self.arrivals_per_second <= 0 or self.seconds <= 0:
            msg = "a rate and a duration are both positive"
            raise LoadError(msg)
        if set(self.mix) != set(MIX) or any(weight <= 0 for weight in self.mix.values()):
            msg = "the mix names the answer lane and the fast lane, each with a positive share"
            raise LoadError(msg)
        for lane in MIX:
            if not self.questions.get(lane):
                msg = (
                    f"the {lane.value} lane has no question to send, so its objective would be "
                    "reported unmeasured; give it at least one"
                )
                raise LoadError(msg)
        if self.max_requests is not None and self.max_requests < 1:
            msg = "a bound of no requests sends none"
            raise LoadError(msg)

    @property
    def total(self) -> int:
        """How many arrivals the run sends, after the bound."""
        planned = int(self.arrivals_per_second * self.seconds)
        return planned if self.max_requests is None else min(planned, self.max_requests)


def arrivals(profile: Profile) -> tuple[tuple[float, Shape], ...]:
    """The arrivals, as an offset in seconds from the start and what to send.

    Evenly spaced rather than random in time, because the target is a rate and a Poisson draw
    would make two runs of one file differ by the luck of their bursts; which lane and which
    person are drawn, seeded, because that is the mix.
    """
    rng = random.Random(profile.seed)  # noqa: S311 - a traffic mix, not a secret
    lanes = list(profile.mix)
    weights = [profile.mix[lane] for lane in lanes]
    gap = 1.0 / profile.arrivals_per_second
    out: list[tuple[float, Shape]] = []
    for n in range(profile.total):
        lane = rng.choices(lanes, weights=weights, k=1)[0]
        question = rng.choice(list(profile.questions[lane]))
        out.append((n * gap, Shape(lane=lane, question=question, person=n % profile.people)))
    return tuple(out)


async def drive[T](
    profile: Profile, send: Callable[[Shape], Awaitable[T]], *, sleep: Sleeper = asyncio.sleep
) -> list[T]:
    """Send every arrival at its offset and gather what came back.

    Each send is its own task, started at its offset whatever the earlier ones are doing, because
    a load test that waits for a reply before sending the next measures a person who asks one
    question at a time. `sleep` is a parameter so a test can drive a ten-minute schedule in no
    time; nothing else about the schedule is faked. Generic in what a send returns so that
    `drive_measured` can wrap a sender that sometimes declines to send.
    """
    started = 0.0
    tasks: list[asyncio.Future[T]] = []
    for offset, shape in arrivals(profile):
        if offset > started:
            await sleep(offset - started)
            started = offset
        tasks.append(asyncio.ensure_future(send(shape)))
    return list(await asyncio.gather(*tasks))


@dataclass(frozen=True)
class Measured:
    """What a drive produced beyond the samples: how many were in flight at once, how many
    planned requests were never sent, and how long it took."""

    samples: tuple[Sample, ...]
    most_in_flight: int
    not_sent: int
    seconds_run: float


async def drive_measured(
    profile: Profile,
    send: Sender,
    *,
    sleep: Sleeper = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    stop_when_shed_share: float = STOP_WHEN_SHED_SHARE,
) -> Measured:
    """`drive`, counting the most requests in flight at once and stopping when the limits bind.

    The count is taken around each send, so it is what the install was actually asked to hold at
    once, which is the figure Little's law predicts for the profile. The stop is
    `A_RUN_STOPS_WHEN_THE_LIMITS_BIND`: after at least `MINIMUM_REQUESTS_FOR_A_P95` replies, once
    `stop_when_shed_share` of them were shed, no further request is sent and the schedule's
    waiting is skipped, so a refusing install is not made to sit out the rest of ten minutes.
    """
    in_flight = 0
    most = 0
    replied = 0
    shed = 0
    stopped = False

    async def counted(shape: Shape) -> Sample | None:
        nonlocal in_flight, most, replied, shed, stopped
        if stopped:
            return None
        in_flight += 1
        most = max(most, in_flight)
        try:
            got = await send(shape)
        finally:
            in_flight -= 1
        replied += 1
        shed += 1 if got.shed else 0
        if replied >= MINIMUM_REQUESTS_FOR_A_P95 and shed / replied >= stop_when_shed_share:
            stopped = True
        return got

    async def waiting(seconds: float) -> None:
        if not stopped:
            await sleep(seconds)

    begun = clock()
    results = await drive(profile, counted, sleep=waiting)
    kept = tuple(one for one in results if one is not None)
    return Measured(
        samples=kept,
        most_in_flight=most,
        not_sent=len(results) - len(kept),
        seconds_run=clock() - begun,
    )


# ------------------------------------------------------------------------ the judgement
@dataclass(frozen=True)
class LaneReading:
    """What one lane did over the run."""

    lane: Lane
    requests: int
    p95_ms: float | None
    success_rate: float | None
    shed: int
    findings: tuple[str, ...]


@dataclass(frozen=True)
class Report:
    """A run's readings, and whether every lane it drove held its objective."""

    readings: tuple[LaneReading, ...]
    total: int
    interactive_shed: int = 0
    notes: tuple[str, ...] = field(default=())

    @property
    def findings(self) -> tuple[str, ...]:
        return tuple(one for reading in self.readings for one in reading.findings)

    @property
    def held(self) -> bool:
        return not self.findings and self.total > 0

    def lines(self) -> tuple[str, ...]:
        """The report as lines a person reads. Counts of what was sent and shed are the
        run's own, about the load it generated, and name no person and no question."""
        out = [f"target: {LOAD_TEST_TARGET}", f"sent: {self.total} request(s)"]
        for reading in self.readings:
            p95 = "not measured" if reading.p95_ms is None else f"{reading.p95_ms:.0f}ms"
            rate = "n/a" if reading.success_rate is None else f"{reading.success_rate:.4f}"
            out.append(
                f"{reading.lane.value}: {reading.requests} request(s), p95 {p95}, "
                f"success {rate}, shed {reading.shed}"
            )
        out.append(f"interactive requests shed: {self.interactive_shed}")
        out.extend(f"note: {one}" for one in self.notes)
        out.extend(f"unmet: {one}" for one in self.findings)
        out.append("held" if self.held else "not held")
        return tuple(out)


def judge(samples: Sequence[Sample]) -> Report:
    """Turn what happened into a verdict per lane against `LANE_OBJECTIVES`.

    Every lane that has an objective is read, including one nothing was sent to, which is
    reported unmeasured. Refuses an empty run: no samples is not a held objective.
    """
    if not samples:
        msg = "a run that sent nothing measured nothing, and is not a held objective"
        raise LoadError(msg)
    by_lane: dict[Lane, list[Sample]] = {}
    for one in samples:
        by_lane.setdefault(one.lane, []).append(one)
    readings: list[LaneReading] = []
    for objective in LANE_OBJECTIVES:
        got = by_lane.get(objective.lane, [])
        if not got:
            continue
        if objective.lane not in MIX:
            continue
        rate = success_rate([one.status for one in got])
        measured = len(got) >= MINIMUM_REQUESTS_FOR_A_P95
        p95 = percentile_ms([one.seconds * 1000.0 for one in got], 0.95) if measured else None
        findings = list(attainment(objective, observed_p95_ms=p95, observed_success_rate=rate))
        if objective.p95_ms is not None and not measured:
            findings.append(
                f"the {objective.lane.value} lane was sent {len(got)} request(s): "
                f"{A_P95_OVER_A_HANDFUL_IS_THE_MAXIMUM}"
            )
        readings.append(
            LaneReading(
                lane=objective.lane,
                requests=len(got),
                p95_ms=p95,
                success_rate=rate,
                shed=sum(1 for one in got if one.shed),
                findings=tuple(findings),
            )
        )
    missing = [lane for lane in MIX if lane not in by_lane]
    notes = tuple(f"the {lane.value} lane was sent nothing" for lane in missing)
    readings.extend(
        LaneReading(
            lane=lane,
            requests=0,
            p95_ms=None,
            success_rate=None,
            shed=0,
            findings=(
                f"the {lane.value} lane was sent nothing, so its objective is unmeasured and "
                "therefore unmet",
            ),
        )
        for lane in missing
    )
    shed = sum(1 for one in samples if one.shed)
    return Report(readings=tuple(readings), total=len(samples), interactive_shed=shed, notes=notes)


def status_of_reply(code: int) -> tuple[RequestStatus, bool]:
    """How one HTTP answer is recorded: the status, and whether admission shed it.

    A 200 is an answer; a 429 or a 503 is the controller protecting the system, which is a miss
    against the success rate and is counted as shed beside it; anything else is a fault.
    """
    if 200 <= code < 300:
        return RequestStatus.ANSWERED, False
    if code in SHED_STATUSES:
        return RequestStatus.DEGRADED, True
    return RequestStatus.FAILED, False


# ------------------------------------------------------------------------ the live sender
def tokens_from(path: Path) -> tuple[str, ...]:
    """One bearer token per line, blank lines ignored. Never printed."""
    found = tuple(line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    held = tuple(one for one in found if one)
    if not held:
        msg = "the token file holds no token, so nobody can be asked as"
        raise LoadError(msg)
    return held


def questions_from(path: Path) -> dict[Lane, tuple[str, ...]]:
    """Questions as `lane<TAB>question` lines, the lane being `fast` or `answer`."""
    drawn: dict[Lane, list[str]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        name, separator, question = line.partition("\t")
        if not separator or not question.strip():
            msg = f"line {number} of the questions is not `lane<TAB>question`"
            raise LoadError(msg)
        try:
            lane = Lane(name.strip())
        except ValueError as exc:
            msg = f"line {number} names the lane {name.strip()!r}, which is not one"
            raise LoadError(msg) from exc
        if lane not in MIX:
            msg = (
                f"line {number} names the {lane.value} lane, which a person's question cannot reach"
            )
            raise LoadError(msg)
        drawn.setdefault(lane, []).append(question.strip())
    return {lane: tuple(found) for lane, found in drawn.items()}


def address_refusals(address: str) -> tuple[str, ...]:
    """Why an address may not be driven: a plain-HTTP address that is not this machine, since a
    bearer token over it is a token on the wire in the clear."""
    parts = urlsplit(address)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return (f"{address!r} is not an http or https address",)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme == "http" and not local:
        return ("a bearer token is not sent over plain http to anything but this machine",)
    return ()


def http_sender(
    base_url: str,
    tokens: Sequence[str],
    *,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Sender:
    """A sender that asks `/answer` as a person and times the whole streamed reply.

    `transport` is how a test answers from memory; the command passes none.
    """
    import time

    import httpx

    from brain.api import API_PREFIX

    client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    async def send(shape: Shape) -> Sample:
        begun = time.perf_counter()
        try:
            async with client.stream(
                "POST",
                f"{API_PREFIX}/answer",
                json={"question": shape.question},
                headers={"authorization": f"Bearer {tokens[shape.person % len(tokens)]}"},
            ) as reply:
                code = reply.status_code
                async for _ in reply.aiter_bytes():
                    pass
        except httpx.HTTPError:
            return Sample(lane=shape.lane, status=RequestStatus.FAILED, seconds=timeout)
        if code in REFUSED_STATUSES:
            msg = "a token was refused outright, so nothing it sent would be measured"
            raise LoadError(msg)
        status, shed = status_of_reply(code)
        return Sample(
            lane=shape.lane, status=status, seconds=time.perf_counter() - begun, shed=shed
        )

    return send


# ------------------------------------------------------------------------ the stated peak
@dataclass(frozen=True)
class StatedPeak:
    """What the capacity model states for a profile's busiest minute: the arrival rate, and how many
    requests Little's law says are in flight at once at that rate."""

    profile: str
    arrivals_per_second: float
    in_flight: float


def stated_peak(name: str, profiles: Sequence[CapacityProfile] | None = None) -> StatedPeak:
    """The profile's peak from `brain.ops.admission.seed_profiles`, or a refusal naming the ones
    the capacity model states. Read from there so the run's peak is never a second copy."""
    held = tuple(profiles) if profiles is not None else seed_profiles()
    found = next((one for one in held if one.name == name), None)
    if found is None:
        names = ", ".join(one.name for one in held)
        msg = f"{name!r} is not a profile the capacity model states: {names}"
        raise LoadError(msg)
    return StatedPeak(
        profile=found.name,
        arrivals_per_second=found.peak_arrivals_per_second,
        in_flight=found.concurrency,
    )


def at_stated_peak(profile: Profile, stated: StatedPeak, measured: Measured) -> bool:
    """Whether a run drove the profile's whole stated peak: at least its rate, for the whole
    ten minutes, every planned arrival sent and none held back.

    A run below any of those is still a run and is still reported. It is just not the peak test,
    and the record says so rather than leaving `held` to be read as one.
    """
    planned = int(profile.arrivals_per_second * profile.seconds)
    return (
        profile.arrivals_per_second >= stated.arrivals_per_second
        and profile.seconds >= PEAK_SECONDS
        and profile.total == planned
        and measured.not_sent == 0
    )


#: The three verdicts a run ends on, written once.
HELD_AT_THE_STATED_PEAK: Final = "held at the stated peak"
HELD_BELOW_THE_STATED_PEAK: Final = (
    "held, on a run smaller than the stated peak, so this is not the peak test"
)
NOT_HELD: Final = "not held"


def record_of(
    report: Report,
    measured: Measured,
    profile: Profile,
    stated: StatedPeak,
    *,
    started_at: datetime,
    commit: str,
    run_id: str,
) -> RunRecord:
    """The result as it is kept: figures and verdicts, and nobody and nothing asked.

    A run that stopped because the limits bound is not held whatever its lanes say about the
    requests it did send, and says how many it did not.
    """
    findings = list(report.findings)
    if measured.not_sent:
        findings.append(
            f"the run stopped sending: {measured.not_sent} of {profile.total} planned requests "
            f"were not sent. {A_RUN_STOPS_WHEN_THE_LIMITS_BIND}"
        )
    return RunRecord(
        run_id=run_id,
        commit=commit,
        profile=stated.profile,
        started_at=started_at,
        seconds_run=round(measured.seconds_run, 3),
        stated_arrivals_per_second=stated.arrivals_per_second,
        stated_in_flight=stated.in_flight,
        arrivals_per_second=profile.arrivals_per_second,
        planned=profile.total,
        sent=report.total,
        not_sent=measured.not_sent,
        most_in_flight=measured.most_in_flight,
        people=profile.people,
        at_stated_peak=at_stated_peak(profile, stated, measured),
        held=report.held and not measured.not_sent,
        interactive_shed=report.interactive_shed,
        lanes=tuple(
            LaneFigures(
                lane=one.lane.value,
                requests=one.requests,
                p95_ms=one.p95_ms,
                success_rate=one.success_rate,
                shed=one.shed,
            )
            for one in report.readings
        ),
        findings=tuple(findings),
    )


def lines_of(record: RunRecord) -> tuple[str, ...]:
    """What a person reads about the run beside the lane figures: the stated peak against what was
    driven and held at once, the notes on what it leaves behind, and the verdict."""
    out = [
        f"profile: {record.profile}, stated peak {record.stated_arrivals_per_second:g} arrivals a "
        f"second, {record.stated_in_flight:g} in flight at once (Little's law)",
        f"driven: {record.arrivals_per_second:g} arrivals a second for {record.seconds_run:g}s, "
        f"{record.sent} of {record.planned} planned requests sent, as {record.people} test "
        f"people, the most in flight at once {record.most_in_flight}",
        f"leaves behind: {WHAT_A_RUN_LEAVES_BEHIND}",
        f"does not measure: {WHAT_A_RUN_DOES_NOT_MEASURE}",
    ]
    out.extend(f"unmet: {one}" for one in record.findings if "run stopped sending" in one)
    if not record.held:
        out.append(NOT_HELD)
    elif record.at_stated_peak:
        out.append(HELD_AT_THE_STATED_PEAK)
    else:
        out.append(HELD_BELOW_THE_STATED_PEAK)
    return tuple(out)


# ----------------------------------------------------------------------- the refusals
@dataclass(frozen=True)
class CallerFacts:
    """What the install says of the person a token belongs to: who, and in which department."""

    principal_id: str
    primary_department: str | None


WhoAsks = Callable[[str, Sequence[str]], Awaitable[tuple[CallerFacts, ...]]]


def refusals_before_a_run(
    *,
    switch_is_on: bool,
    callers: Sequence[CallerFacts],
    planned: int,
    confirmed: int,
) -> tuple[str, ...]:
    """Every reason this run may not start, each a sentence naming no person and no token.

    Pure, so every refusal is tested without a database or a socket, and so the install's own
    check holds the same function the command runs. An empty answer is the only way to start.
    """
    out: list[str] = []
    if not switch_is_on:
        out.append(
            "the peak load test is switched off on this install; an administrator turns it on "
            "first, and nothing was sent"
        )
    outside = sum(1 for one in callers if one.primary_department != LOAD_TEST_DEPARTMENT)
    if not callers or outside:
        out.append(
            f"{outside or 'every'} of {len(callers)} tokens is not a person in the "
            f"{LOAD_TEST_DEPARTMENT} department, and nothing was sent. "
            f"{A_RUN_ASKS_AS_RESERVED_TEST_PEOPLE_ONLY}"
        )
    if confirmed != planned:
        out.append(
            f"--confirm-requests is {confirmed} and this run would send {planned}, and nothing "
            f"was sent. {A_SPEND_IS_CONFIRMED_BY_ITS_NUMBER}"
        )
    return tuple(out)


async def who_asks(
    base_url: str,
    tokens: Sequence[str],
    *,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[CallerFacts, ...]:
    """Ask the install who each token belongs to, through the route every signed-in person has.

    A token the install does not accept ends the run here, before a model call is spent.
    """
    import httpx

    from brain.api import API_PREFIX

    found: list[CallerFacts] = []
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
    ) as client:
        for token in tokens:
            try:
                reply = await client.get(
                    f"{API_PREFIX}/me", headers={"authorization": f"Bearer {token}"}
                )
                body = reply.json() if reply.status_code == 200 else None
            except (httpx.HTTPError, ValueError) as exc:
                msg = "the install could not be asked who a token belongs to"
                raise LoadError(msg) from exc
            if not isinstance(body, dict):
                msg = "a token was not accepted by the install, so nobody can be asked as"
                raise LoadError(msg)
            department = body.get("primary_department")
            found.append(
                CallerFacts(
                    principal_id=str(body.get("principal_id", "")),
                    primary_department=department if isinstance(department, str) else None,
                )
            )
    return tuple(found)


# ------------------------------------------------------------------------ the command
EXIT_UNKEPT: Final = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description=(
            "Drive an install at its profile's stated peak and read the service levels off the "
            "answers. " + A_REAL_RUN_COSTS_REAL_MODEL_CALLS + " " + WHAT_A_RUN_LEAVES_BEHIND
        ),
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="the application's address; plain http only for this machine",
    )
    parser.add_argument(
        "--token-file",
        required=True,
        type=Path,
        help=f"one bearer token a line, each a person in the {LOAD_TEST_DEPARTMENT} department",
    )
    parser.add_argument("--questions-file", required=True, type=Path, help="lane<TAB>question")
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="the capacity model's profile whose stated peak is driven (lite, full or ha)",
    )
    parser.add_argument(
        "--arrivals-per-second",
        type=float,
        default=None,
        help="the profile's stated peak unless a lower rate is named, which is not the peak test",
    )
    parser.add_argument("--seconds", type=float, default=PEAK_SECONDS)
    parser.add_argument(
        "--max-requests", type=int, required=True, help="the most this run will send"
    )
    parser.add_argument(
        "--confirm-requests",
        type=int,
        required=True,
        help="the number of requests this run will send, typed again: the spend is confirmed by it",
    )
    return parser


@dataclass(frozen=True)
class Ran:
    """What a run came to: the judgement, the record, whether the install kept it, and the counts
    of what came back."""

    report: Report
    record: RunRecord
    kept: bool
    outcomes: str


async def _run(
    args: argparse.Namespace,
    tokens: Sequence[str],
    profile: Profile,
    stated: StatedPeak,
    keeper: Keeper,
    ask_who: WhoAsks,
    sleep: Sleeper,
) -> Ran:
    """Look, refuse or send, judge and keep, with the keeper's connection let go of at the end.

    Everything that can refuse happens before the first request, so a refusal costs nothing.
    """
    try:
        on = await keeper.switch_is_on()
        callers = await ask_who(args.base_url, tokens)
        refusals = refusals_before_a_run(
            switch_is_on=on,
            callers=callers,
            planned=profile.total,
            confirmed=args.confirm_requests,
        )
        if refusals:
            raise LoadError("; ".join(refusals))
        started_at = datetime.now(UTC)
        measured = await drive_measured(profile, http_sender(args.base_url, tokens), sleep=sleep)
        report = judge(measured.samples)
        record = record_of(
            report,
            measured,
            profile,
            stated,
            started_at=started_at,
            commit=keeper.commit,
            run_id=uuid.uuid4().hex,
        )
        outcomes = ", ".join(
            f"{name} {count}"
            for name, count in sorted(Counter(one.status.value for one in measured.samples).items())
        )
        try:
            await keeper.keep(record)
        except Exception:  # the figures are printed whatever happened to the row
            return Ran(report=report, record=record, kept=False, outcomes=outcomes)
        return Ran(report=report, record=record, kept=True, outcomes=outcomes)
    finally:
        await keeper.close()


def main(
    argv: Sequence[str] | None = None,
    *,
    sleep: Sleeper = asyncio.sleep,
    keeper: Keeper | None = None,
    ask_who: WhoAsks = who_asks,
) -> int:
    """Run it. 0 when every lane held, 1 when one did not, 2 when it could not run (nothing was
    sent, or a token was refused part-way), 3 when it ran and its result could not be kept.

    `sleep` is the schedule's waiting, a parameter so a test does not wait ten minutes; `keeper`
    and `ask_who` are the install's database and its answer to "who is this", which a test hands
    in and the command builds for itself.
    """
    args = _parser().parse_args(list(argv) if argv is not None else sys.argv[1:])
    try:
        refusals = address_refusals(args.base_url)
        if refusals:
            raise LoadError(refusals[0])
        tokens = tokens_from(args.token_file)
        stated = stated_peak(args.profile)
        profile = Profile(
            questions=questions_from(args.questions_file),
            people=len(tokens),
            arrivals_per_second=(
                stated.arrivals_per_second
                if args.arrivals_per_second is None
                else args.arrivals_per_second
            ),
            seconds=args.seconds,
            max_requests=args.max_requests,
        )
        ran = asyncio.run(
            _run(args, tokens, profile, stated, keeper or database_keeper(), ask_who, sleep)
        )
    except (LoadError, ReliabilityError, RunStoreError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    # The report's own last line is its verdict on the lanes, which `lines_of` restates after the
    # run's own conditions, so it is not printed twice.
    for line in ran.report.lines()[:-1]:
        print(line)
    print(f"outcomes: {ran.outcomes}")
    for line in lines_of(ran.record):
        print(line)
    if not ran.kept:
        print("not kept: this result could not be written to the install's database")
        return EXIT_UNKEPT
    print(f"kept: this install holds the result as run {ran.record.run_id}")
    return 0 if ran.record.held else EXIT_UNMET


if __name__ == "__main__":
    raise SystemExit(main())
