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

Scope: arithmetic over what happened, a driver that schedules sends, and one HTTP sender. The only
network reach is the sender, and it is built only by `main`.

Task ids: M22.3.3
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from brain.connectors.throttle import percentile_ms
from brain.core.lane import Lane
from brain.ops.admission import LOAD_TEST_TARGET
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

    def __post_init__(self) -> None:
        if self.people < 1:
            msg = "a run with nobody to ask as sends nothing"
            raise LoadError(msg)
        if self.arrivals_per_second <= 0 or self.seconds <= 0:
            msg = "a rate and a duration are both positive"
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
    lanes = list(MIX)
    weights = [MIX[lane] for lane in lanes]
    gap = 1.0 / profile.arrivals_per_second
    out: list[tuple[float, Shape]] = []
    for n in range(profile.total):
        lane = rng.choices(lanes, weights=weights, k=1)[0]
        question = rng.choice(list(profile.questions[lane]))
        out.append((n * gap, Shape(lane=lane, question=question, person=n % profile.people)))
    return tuple(out)


async def drive(profile: Profile, send: Sender, *, sleep: Sleeper = asyncio.sleep) -> list[Sample]:
    """Send every arrival at its offset and gather what came back.

    Each send is its own task, started at its offset whatever the earlier ones are doing, because
    a load test that waits for a reply before sending the next measures a person who asks one
    question at a time. `sleep` is a parameter so a test can drive a ten-minute schedule in no
    time; nothing else about the schedule is faked.
    """
    started = 0.0
    tasks: list[asyncio.Task[Sample]] = []
    for offset, shape in arrivals(profile):
        if offset > started:
            await sleep(offset - started)
            started = offset
        tasks.append(asyncio.ensure_future(send(shape)))
    return list(await asyncio.gather(*tasks))


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


# ------------------------------------------------------------------------ the command
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description=(
            "Drive an install at its peak arrival rate and read the service levels off the "
            "answers. " + A_REAL_RUN_COSTS_REAL_MODEL_CALLS
        ),
    )
    parser.add_argument("--base-url", required=True, help="the install's address")
    parser.add_argument("--token-file", required=True, type=Path, help="one bearer token a line")
    parser.add_argument("--questions-file", required=True, type=Path, help="lane<TAB>question")
    parser.add_argument("--arrivals-per-second", type=float, default=ARRIVALS_PER_SECOND)
    parser.add_argument("--seconds", type=float, default=PEAK_SECONDS)
    parser.add_argument(
        "--max-requests", type=int, required=True, help="the most this run will send"
    )
    return parser


def main(argv: Sequence[str] | None = None, *, sleep: Sleeper = asyncio.sleep) -> int:
    """Run it. 0 when every lane held, 1 when one did not, 2 when it could not run.

    `sleep` is the schedule's waiting, a parameter so a test does not wait ten minutes.
    """
    args = _parser().parse_args(list(argv) if argv is not None else sys.argv[1:])
    try:
        refusals = address_refusals(args.base_url)
        if refusals:
            raise LoadError(refusals[0])
        tokens = tokens_from(args.token_file)
        profile = Profile(
            questions=questions_from(args.questions_file),
            people=len(tokens),
            arrivals_per_second=args.arrivals_per_second,
            seconds=args.seconds,
            max_requests=args.max_requests,
        )
        samples = asyncio.run(drive(profile, http_sender(args.base_url, tokens), sleep=sleep))
        report = judge(samples)
    except (LoadError, ReliabilityError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    for line in report.lines():
        print(line)
    outcomes = Counter(one.status.value for one in samples)
    print("outcomes: " + ", ".join(f"{name} {count}" for name, count in sorted(outcomes.items())))
    return 0 if report.held else EXIT_UNMET


if __name__ == "__main__":
    raise SystemExit(main())
