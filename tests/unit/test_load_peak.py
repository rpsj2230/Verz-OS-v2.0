"""The peak-concurrency run: the figures it drives, the verdict it reads, and a small run CI can do.

Nothing here opens a socket. The sender is a function the test writes or an in-memory transport,
and the schedule's sleeps are replaced by a recorder, so a ten-minute schedule runs in no time and
the only thing faked is the waiting. The real run, at two arrivals a second for ten minutes against
an install, is an owner's command (`python -m brain.ops.load_peak`) because it spends model calls.

Task ids: M22.3.3
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from brain.core.lane import Lane
from brain.ops import load_peak
from brain.ops.admission import LOAD_TEST_TARGET
from brain.ops.load_peak import (
    ARRIVALS_PER_SECOND,
    MINIMUM_REQUESTS_FOR_A_P95,
    PEAK_SECONDS,
    LoadError,
    Profile,
    Sample,
    Shape,
    address_refusals,
    arrivals,
    drive,
    http_sender,
    judge,
    main,
    questions_from,
    status_of_reply,
    tokens_from,
)
from brain.ops.reliability import ANSWER_P95_MS, FAST_P95_MS
from brain.ops.telemetry import RequestStatus

QUESTIONS = {Lane.ANSWER: ("a question for the model",), Lane.FAST: ("a record lookup",)}


def profile(**changes: object) -> Profile:
    fields: dict[str, object] = {"questions": QUESTIONS, "people": 3}
    fields.update(changes)
    return Profile(**fields)  # type: ignore[arg-type]


async def no_waiting(_seconds: float) -> None:
    return None


async def sent_once(send: load_peak.Sender, shape: Shape) -> Sample:
    """One send awaited inside a coroutine, which is what `asyncio.run` takes."""
    return await send(shape)


def sample(lane: Lane, seconds: float, status: RequestStatus = RequestStatus.ANSWERED) -> Sample:
    return Sample(lane=lane, status=status, seconds=seconds, shed=status is RequestStatus.DEGRADED)


def test_the_figures_driven_are_the_ones_the_capacity_model_wrote_down() -> None:
    """The drive's rate and length asserted against the target's own sentence, so the two cannot
    drift. Delete this and the target can be raised to a rate this run never generates, leaving a
    capacity claim backed by a run a tenth its size."""
    assert f"{ARRIVALS_PER_SECOND} arrivals a second" in LOAD_TEST_TARGET
    assert "ten minutes" in LOAD_TEST_TARGET
    assert PEAK_SECONDS == 10 * 60
    assert profile().total == 1200


def test_the_arrivals_are_evenly_spaced_seeded_and_mixed_across_lanes_and_people() -> None:
    """Two runs of one file send one population, at the stated rate, over every lane and every
    person. Delete this and a run can send only one lane, so the other lane's objective is
    reported on nothing, or put every request on one person's rate window."""
    first = arrivals(profile())
    assert first == arrivals(profile())
    assert [round(at, 3) for at, _ in first[:3]] == [0.0, 0.5, 1.0]
    assert {shape.lane for _, shape in first} == {Lane.ANSWER, Lane.FAST}
    assert {shape.person for _, shape in first} == {0, 1, 2}
    answers = sum(1 for _, shape in first if shape.lane is Lane.ANSWER)
    assert 0.7 < answers / len(first) < 0.9


def test_the_bound_on_requests_is_applied_before_anything_is_sent() -> None:
    """A real run costs model calls, so the most it will send is a number the run keeps. Delete
    this and a bound is accepted and ignored, which is a spend nobody agreed to."""
    assert profile(max_requests=40).total == 40
    assert len(arrivals(profile(max_requests=40))) == 40


def test_a_small_run_drives_the_whole_schedule_and_holds_when_every_lane_is_fast() -> None:
    """The CI-sized run: two hundred arrivals at the peak rate, sent through the real driver,
    each as its own task, judged against the real objectives. Delete this and the driver, the
    judge and the objectives are only ever run together on an owner's server, once.

    Also the positive case: a judge that reports every run unmet passes every refusal test below.
    """
    sent: list[Shape] = []
    waited: list[float] = []

    async def send(shape: Shape) -> Sample:
        sent.append(shape)
        return sample(shape.lane, 0.05)

    async def record(seconds: float) -> None:
        waited.append(seconds)

    samples = asyncio.run(drive(profile(seconds=100), send, sleep=record))
    report = judge(samples)

    assert len(sent) == len(samples) == 200
    assert sum(waited) == pytest.approx(99.5)
    assert report.held, report.lines()
    assert report.lines()[-1] == "held"


def test_every_arrival_is_sent_without_waiting_for_the_one_before_to_be_answered() -> None:
    """The first send is held open until the last has been sent. Delete this and a driver that
    awaits each reply before the next passes, which measures one person asking one question at a
    time and reports a peak it never generated."""
    gate = asyncio.Event
    in_flight = 0
    highest = 0

    async def run() -> list[Sample]:
        nonlocal in_flight, highest
        release = gate()

        async def send(shape: Shape) -> Sample:
            nonlocal in_flight, highest
            in_flight += 1
            highest = max(highest, in_flight)
            if highest >= 5:
                release.set()
            await release.wait()
            in_flight -= 1
            return sample(shape.lane, 0.01)

        return await drive(profile(max_requests=5), send, sleep=no_waiting)

    asyncio.run(run())
    assert highest == 5


def test_a_slow_answer_lane_is_reported_against_its_own_objective() -> None:
    """The answer lane at ten seconds against eight. Delete this and the judge stops comparing
    a lane's p95 with its objective, so a system that answers in ten seconds is reported held."""
    samples = [sample(Lane.ANSWER, ANSWER_P95_MS / 1000.0 + 2.0) for _ in range(40)] + [
        sample(Lane.FAST, 0.1) for _ in range(40)
    ]
    report = judge(samples)
    assert not report.held
    assert any("answer lane is at" in one for one in report.findings)
    assert not any("fast lane is at" in one for one in report.findings)


def test_a_slow_fast_lane_is_reported_and_the_answer_lane_is_not_blamed() -> None:
    """The fast lane at a second against five hundred milliseconds. Delete this and one lane's
    objective is applied to both, so the fast lane is judged against eight seconds."""
    samples = [sample(Lane.ANSWER, 1.0) for _ in range(40)] + [
        sample(Lane.FAST, FAST_P95_MS / 1000.0 + 0.5) for _ in range(40)
    ]
    report = judge(samples)
    assert not report.held
    assert any("fast lane is at" in one for one in report.findings)


def test_requests_that_were_shed_count_against_the_success_rate_and_are_reported() -> None:
    """Two in forty shed, which is below the success target. Delete this and a controller that
    refuses requests to stay up reports a perfect run, or the shed ones are not reported at
    all and the fall in the rate has no owner."""
    samples = [sample(Lane.ANSWER, 1.0) for _ in range(38)]
    samples += [sample(Lane.ANSWER, 0.1, RequestStatus.DEGRADED) for _ in range(2)]
    samples += [sample(Lane.FAST, 0.1) for _ in range(40)]
    report = judge(samples)
    assert not report.held
    assert report.interactive_shed == 2
    assert next(r for r in report.readings if r.lane is Lane.ANSWER).shed == 2
    assert any("succeeded on" in one for one in report.findings)
    assert "interactive requests shed: 2" in report.lines()


def test_a_lane_sent_a_handful_is_not_measured_and_is_not_held() -> None:
    """Five fast-lane requests, all instant. Delete this and a p95 over five requests is their
    maximum, reported as a measurement, and a run that barely touched a lane reports it green."""
    samples = [sample(Lane.ANSWER, 1.0) for _ in range(40)] + [sample(Lane.FAST, 0.01)] * 5
    report = judge(samples)
    assert MINIMUM_REQUESTS_FOR_A_P95 > 5
    assert not report.held
    assert any("fast lane was sent 5 request" in one for one in report.findings)


def test_a_lane_that_was_sent_nothing_is_unmet_and_an_empty_run_is_refused() -> None:
    """No fast-lane request at all, and no request at all. Delete this and forgetting a lane's
    questions reports its objective as held, or a run that sent nothing is a held objective."""
    report = judge([sample(Lane.ANSWER, 1.0) for _ in range(40)])
    assert not report.held
    assert any("fast lane was sent nothing" in one for one in report.findings)
    with pytest.raises(LoadError):
        judge([])


def test_a_shed_request_cannot_be_recorded_as_a_success() -> None:
    """Constructing one is refused. Delete this and a sample can claim to be both, and the rate
    counts a refusal as an answer."""
    with pytest.raises(LoadError):
        Sample(lane=Lane.ANSWER, status=RequestStatus.ANSWERED, seconds=1.0, shed=True)


def test_a_reply_is_recorded_as_an_answer_a_shed_or_a_fault() -> None:
    """The three readings of an HTTP code. Delete this and a 429 is a fault, which hides that the
    controller shed, or a 500 is an answer."""
    assert status_of_reply(200) == (RequestStatus.ANSWERED, False)
    assert status_of_reply(429) == (RequestStatus.DEGRADED, True)
    assert status_of_reply(503) == (RequestStatus.DEGRADED, True)
    assert status_of_reply(500) == (RequestStatus.FAILED, False)


def test_a_profile_without_a_question_for_a_lane_or_a_person_is_refused() -> None:
    """Delete this and a run is built that cannot measure a lane, which is reported at the end
    rather than before any model call is spent."""
    with pytest.raises(LoadError):
        profile(questions={Lane.ANSWER: ("only this",)})
    with pytest.raises(LoadError):
        profile(people=0)
    with pytest.raises(LoadError):
        profile(max_requests=0)


def test_a_bearer_token_is_never_sent_over_plain_http_beyond_this_machine() -> None:
    """Delete this and the command sends a person's token across a network in the clear."""
    assert not address_refusals("https://install.example")
    assert address_refusals("http://install.example")
    assert not address_refusals("http://localhost:8000")
    assert address_refusals("ftp://install.example")


def test_the_files_are_read_and_a_malformed_line_names_its_number(tmp_path: Path) -> None:
    """Delete this and a bad questions file is read as fewer questions, so the mix is not the
    one that was asked for, with nothing saying so."""
    questions = tmp_path / "questions.tsv"
    questions.write_text("fast\twhat is the price\n\nanswer\tsummarise the policy\n")
    assert questions_from(questions) == {
        Lane.FAST: ("what is the price",),
        Lane.ANSWER: ("summarise the policy",),
    }
    questions.write_text("fast what is the price\n")
    with pytest.raises(LoadError, match="line 1"):
        questions_from(questions)
    questions.write_text("task\tdo a job\n")
    with pytest.raises(LoadError, match="cannot reach"):
        questions_from(questions)
    tokens = tmp_path / "tokens"
    tokens.write_text("a\n\n b \n")
    assert tokens_from(tokens) == ("a", "b")
    tokens.write_text("\n")
    with pytest.raises(LoadError):
        tokens_from(tokens)


def test_the_sender_asks_as_the_person_it_was_given_and_times_a_streamed_reply() -> None:
    """In-memory transport recording who asked. Delete this and the token is sent to the wrong
    person's window, or the reply is not read to its end, so the time is the time to the first
    byte."""
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        return httpx.Response(200, content=b"data: x\n\n")

    send = http_sender(
        "https://install.example", ("one", "two"), transport=httpx.MockTransport(answer)
    )
    got = asyncio.run(sent_once(send, Shape(lane=Lane.ANSWER, question="q", person=1)))
    assert seen == ["Bearer two"]
    assert got.status is RequestStatus.ANSWERED and not got.shed


def test_a_refused_token_ends_the_run_and_a_shed_reply_is_a_sample() -> None:
    """Delete this and a run with a wrong token reports forty failed requests as a measurement."""

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    def shed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    shape = Shape(lane=Lane.ANSWER, question="q", person=0)
    refused = http_sender("https://x.example", ("t",), transport=httpx.MockTransport(refuse))
    with pytest.raises(LoadError):
        asyncio.run(sent_once(refused, shape))
    limited = http_sender("https://x.example", ("t",), transport=httpx.MockTransport(shed))
    assert asyncio.run(sent_once(limited, shape)).shed


def _files(tmp_path: Path) -> list[str]:
    (tmp_path / "t").write_text("token-one\n")
    (tmp_path / "q").write_text("fast\ta lookup\nanswer\ta question\n")
    return [
        "--base-url",
        "https://install.example",
        "--token-file",
        str(tmp_path / "t"),
        "--questions-file",
        str(tmp_path / "q"),
        "--seconds",
        "100",
        "--max-requests",
        "200",
    ]


def test_the_command_exits_zero_when_held_one_when_not_and_two_when_it_cannot_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The three exit codes over a sender the test supplies. Delete this and the command answers
    zero for a run that missed its objective, so a script reading it is told the install is fine."""
    seconds = {"value": 0.05}

    def sender(base_url: str, tokens: object) -> load_peak.Sender:
        async def send(shape: Shape) -> Sample:
            return sample(shape.lane, seconds["value"])

        return send

    monkeypatch.setattr(load_peak, "http_sender", sender)
    arguments = _files(tmp_path)
    assert main(arguments, sleep=no_waiting) == 0
    seconds["value"] = 60.0
    assert main(arguments, sleep=no_waiting) == load_peak.EXIT_UNMET
    assert "unmet" in capsys.readouterr().out
    arguments[1] = "http://install.example"
    assert main(arguments, sleep=no_waiting) == load_peak.EXIT_REFUSED
