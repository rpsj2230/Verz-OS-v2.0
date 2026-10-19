"""The peak run's safety and its result: what it refuses, when it stops and what it keeps.

`tests/unit/test_load_peak.py` holds the arithmetic and the driver. This file holds what makes the
command something an operator can run on an install: the stated peak read from the capacity model,
a run smaller than it saying so, the most requests in flight at once measured, the six refusals
made before anything is sent, the stop when the install's limits bind, and a result kept as
figures only. Nothing opens a socket and nothing needs a database: the install is a keeper and a
"who is this" the test hands in, and the sender is a function.

Task ids: M22.3.3
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from brain.core.lane import Lane
from brain.ops import load_peak
from brain.ops.admission import LOAD_TEST_TARGET, seed_profiles
from brain.ops.load_peak import (
    A_RUN_ASKS_AS_RESERVED_TEST_PEOPLE_ONLY,
    DEFAULT_PROFILE,
    HELD_AT_THE_STATED_PEAK,
    HELD_BELOW_THE_STATED_PEAK,
    LOAD_TEST_DEPARTMENT,
    MINIMUM_REQUESTS_FOR_A_P95,
    NOT_HELD,
    PEAK_SECONDS,
    STOP_WHEN_SHED_SHARE,
    CallerFacts,
    LoadError,
    Measured,
    Profile,
    Sample,
    Shape,
    at_stated_peak,
    drive_measured,
    judge,
    lines_of,
    main,
    record_of,
    refusals_before_a_run,
    stated_peak,
    who_asks,
)
from brain.ops.load_run_store import Keeper, RunRecord
from brain.ops.telemetry import RequestStatus

SRC = Path(__file__).resolve().parents[2] / "src"

QUESTIONS = {Lane.ANSWER: ("QUESTION-FOR-THE-MODEL",), Lane.FAST: ("QUESTION-A-LOOKUP",)}


def profile(**changes: object) -> Profile:
    fields: dict[str, object] = {"questions": QUESTIONS, "people": 2}
    fields.update(changes)
    return Profile(**fields)  # type: ignore[arg-type]


def answered(lane: Lane, seconds: float = 0.05) -> Sample:
    return Sample(lane=lane, status=RequestStatus.ANSWERED, seconds=seconds)


def shed(lane: Lane) -> Sample:
    return Sample(lane=lane, status=RequestStatus.DEGRADED, seconds=0.01, shed=True)


async def no_waiting(_seconds: float) -> None:
    return None


def stated_full() -> load_peak.StatedPeak:
    return stated_peak("full")


def measured(*, not_sent: int = 0, most: int = 8, seconds: float = 600.0) -> Measured:
    return Measured(samples=(), most_in_flight=most, not_sent=not_sent, seconds_run=seconds)


def keeper(
    *,
    on: bool = True,
    kept: list[RunRecord] | None = None,
    fails: bool = False,
    closed: list[str] | None = None,
) -> Keeper:
    async def switch_is_on() -> bool:
        return on

    async def keep(record: RunRecord) -> None:
        if fails:
            raise OSError
        if kept is not None:
            kept.append(record)

    async def close() -> None:
        if closed is not None:
            closed.append("closed")

    return Keeper(switch_is_on=switch_is_on, keep=keep, commit="a-release", close=close)


def people(*departments: str | None):  # type: ignore[no-untyped-def]
    """A "who is this" answering with the departments given, one per token."""

    async def ask(base_url: str, tokens: Sequence[str]) -> tuple[CallerFacts, ...]:
        return tuple(CallerFacts(f"REAL-PERSON-{n}", one) for n, one in enumerate(departments))

    return ask


#: What the command tests send: a hundred seconds at the full profile's two a second, which is
#: enough of each lane for its 95th percentile to be measured.
RUN = 200


def arguments(tmp_path: Path, *, confirm: int = RUN) -> list[str]:
    (tmp_path / "tokens").write_text("TOKEN-ONE\nTOKEN-TWO\n")
    (tmp_path / "questions").write_text("fast\tQUESTION-A-LOOKUP\nanswer\tQUESTION-FOR-THE-MODEL\n")
    return [
        "--base-url",
        "https://install.example",
        "--token-file",
        str(tmp_path / "tokens"),
        "--questions-file",
        str(tmp_path / "questions"),
        "--seconds",
        "100",
        "--max-requests",
        str(RUN),
        "--confirm-requests",
        str(confirm),
    ]


class Sends:
    """A sender that counts what it was asked to send, so a refusal can be shown to send nothing."""

    def __init__(self, reply: Sample | None = None) -> None:
        self.count = 0
        self.reply = reply

    def __call__(self, base_url: str, tokens: object) -> load_peak.Sender:
        async def send(shape: Shape) -> Sample:
            self.count += 1
            return self.reply or answered(shape.lane)

        return send


# ------------------------------------------------------------------------ the stated peak
def test_the_stated_peak_is_read_from_the_capacity_model_and_full_is_the_target_s() -> None:
    """The three profiles' rates and Little's-law concurrency, and the default profile's rate
    against the target's own sentence. Delete this and the run's peak becomes a second copy that
    drifts from `seed_profiles`, so the capacity screen and the test state two different peaks."""
    for one in seed_profiles():
        got = stated_peak(one.name)
        assert got.arrivals_per_second == one.peak_arrivals_per_second
        assert got.in_flight == one.peak_arrivals_per_second * one.mean_service_seconds
    full = stated_peak(DEFAULT_PROFILE)
    assert f"{full.arrivals_per_second:g} arrivals a second" in LOAD_TEST_TARGET
    assert full.in_flight == 8


def test_a_mix_gives_each_lane_its_share_and_names_both_lanes() -> None:
    """A mix of nine fast to one answer, and then two mixes that are not accepted. Delete this and
    the install's mix is applied whatever the profile says, so a short run cannot give each lane
    the twenty requests a percentile needs, or a mix that forgets a lane is accepted."""
    drawn = load_peak.arrivals(
        profile(max_requests=200, mix={Lane.ANSWER: 1.0, Lane.FAST: 9.0}, seconds=1000)
    )
    fast = sum(1 for _, shape in drawn if shape.lane is Lane.FAST)
    assert fast > 150
    with pytest.raises(LoadError):
        profile(mix={Lane.ANSWER: 1.0})
    with pytest.raises(LoadError):
        profile(mix={Lane.ANSWER: 1.0, Lane.FAST: 0.0})


def test_a_profile_the_capacity_model_does_not_state_is_refused_naming_the_ones_it_does() -> None:
    """Delete this and a misspelt profile runs at some default rate and is recorded as the profile
    that was typed."""
    with pytest.raises(LoadError, match="lite, full, ha"):
        stated_peak("enormous")


def test_only_a_run_at_the_whole_stated_peak_is_the_peak_test() -> None:
    """The positive case first (the rate, the ten minutes, every arrival sent), then each way of
    being smaller. Delete this and a bounded run that held is recorded as the peak test, which is
    the one reading of `held` this module exists to prevent."""
    stated = stated_full()
    whole = profile(arrivals_per_second=2.0, seconds=PEAK_SECONDS)
    assert at_stated_peak(whole, stated, measured())
    assert at_stated_peak(
        profile(arrivals_per_second=3.0, seconds=PEAK_SECONDS), stated, measured()
    )
    assert not at_stated_peak(
        profile(arrivals_per_second=1.0, seconds=PEAK_SECONDS), stated, measured()
    )
    assert not at_stated_peak(profile(arrivals_per_second=2.0, seconds=100), stated, measured())
    assert not at_stated_peak(
        profile(arrivals_per_second=2.0, seconds=PEAK_SECONDS, max_requests=1000),
        stated,
        measured(),
    )
    assert not at_stated_peak(whole, stated, measured(not_sent=1))


# ---------------------------------------------------------------------- what is measured
def test_the_most_requests_in_flight_at_once_is_what_the_install_was_asked_to_hold() -> None:
    """Five sends held open together. Delete this and the figure the task is named for, how many
    were in flight at once, is never measured and Little's law is only ever a prediction."""

    async def run() -> Measured:
        gate = asyncio.Event()
        waiting = 0

        async def send(shape: Shape) -> Sample:
            nonlocal waiting
            waiting += 1
            if waiting == 5:
                gate.set()
            await gate.wait()
            return answered(shape.lane)

        return await drive_measured(profile(max_requests=5), send, sleep=no_waiting)

    got = asyncio.run(run())
    assert got.most_in_flight == 5
    assert len(got.samples) == 5
    assert got.not_sent == 0


def test_the_most_in_flight_is_the_peak_and_not_the_last_reading() -> None:
    """Three requests held open together, then two that arrive alone after those finished. Delete
    this and a count that reports the last request's in-flight number passes the test above, where
    the last request is also the highest, and the run reports a peak of one."""

    async def run() -> Measured:
        gate = asyncio.Event()
        entered = 0

        async def send(shape: Shape) -> Sample:
            nonlocal entered
            entered += 1
            if entered <= 3:
                if entered == 3:
                    gate.set()
                await gate.wait()
            return answered(shape.lane)

        async def yielding(_seconds: float) -> None:
            for _ in range(3):
                await asyncio.sleep(0)

        return await drive_measured(profile(max_requests=5), send, sleep=yielding)

    assert asyncio.run(run()).most_in_flight == 3


def test_the_run_s_length_is_the_clock_s_and_the_requests_held_back_are_counted() -> None:
    """A clock that reads ten then forty, over a run that stops. Delete this and the length a
    record states is not the run's, or the number of requests a stopped run did not send is
    reported as the number it sent."""
    readings = iter((10.0, 40.0))

    async def send(shape: Shape) -> Sample:
        return shed(shape.lane)

    got = asyncio.run(
        drive_measured(
            profile(max_requests=50), send, sleep=no_waiting, clock=lambda: next(readings)
        )
    )
    assert got.seconds_run == 30.0
    assert got.not_sent == 50 - MINIMUM_REQUESTS_FOR_A_P95
    assert len(got.samples) == MINIMUM_REQUESTS_FOR_A_P95


def test_a_run_stops_at_exactly_the_share_and_not_only_past_it() -> None:
    """Every second reply shed, which is the share to the digit once twenty are in. Delete this and
    the comparison can drift to strictly greater, so an install refusing exactly half of what it is
    sent is hammered for the rest of the run."""
    count = 0

    async def send(shape: Shape) -> Sample:
        nonlocal count
        count += 1
        return shed(shape.lane) if count % 2 == 0 else answered(shape.lane)

    got = asyncio.run(drive_measured(profile(max_requests=100), send, sleep=no_waiting))
    assert STOP_WHEN_SHED_SHARE == 0.5
    assert len(got.samples) == MINIMUM_REQUESTS_FOR_A_P95
    assert got.not_sent == 100 - MINIMUM_REQUESTS_FOR_A_P95


def test_a_run_stops_sending_once_most_of_what_it_has_sent_was_shed() -> None:
    """Every reply shed: after the twentieth the rest are not sent and are counted. Delete this
    and a run keeps hammering an install that is refusing it, measuring the refusal."""
    sent: list[Shape] = []

    async def send(shape: Shape) -> Sample:
        sent.append(shape)
        return shed(shape.lane)

    got = asyncio.run(drive_measured(profile(max_requests=100), send, sleep=no_waiting))
    assert len(sent) == MINIMUM_REQUESTS_FOR_A_P95
    assert got.not_sent == 100 - MINIMUM_REQUESTS_FOR_A_P95
    assert len(got.samples) == MINIMUM_REQUESTS_FOR_A_P95


def test_a_run_whose_shed_share_stays_under_the_limit_sends_everything() -> None:
    """One reply in five shed, which is under the share that stops a run. Delete this and a run
    that stops on any shed at all passes the test above, and ends every real run early."""
    count = 0

    async def send(shape: Shape) -> Sample:
        nonlocal count
        count += 1
        return shed(shape.lane) if count % 5 == 0 else answered(shape.lane)

    got = asyncio.run(drive_measured(profile(max_requests=100), send, sleep=no_waiting))
    assert got.not_sent == 0
    assert len(got.samples) == 100
    assert STOP_WHEN_SHED_SHARE > 1 / 5


def test_the_waiting_of_a_stopped_run_is_skipped() -> None:
    """A schedule that yields between arrivals, so replies come in while it is still being laid
    out. Delete this and a refusing install is made to sit out the rest of ten minutes of waiting
    after the run has already stopped sending."""
    waited: list[float] = []

    async def record(seconds: float) -> None:
        waited.append(seconds)
        await asyncio.sleep(0)

    async def send(shape: Shape) -> Sample:
        return shed(shape.lane)

    got = asyncio.run(drive_measured(profile(max_requests=100), send, sleep=record))
    assert got.not_sent > 0
    assert len(waited) < 99


# ----------------------------------------------------------------------- the refusals
def refusals(**changes: Any) -> tuple[str, ...]:
    """`refusals_before_a_run` for a run that meets every condition, with `changes` broken."""
    fields: dict[str, Any] = {
        "switch_is_on": True,
        "callers": (CallerFacts("a", LOAD_TEST_DEPARTMENT), CallerFacts("b", LOAD_TEST_DEPARTMENT)),
        "planned": 40,
        "confirmed": 40,
    }
    fields.update(changes)
    return refusals_before_a_run(**fields)


def test_a_run_that_meets_every_condition_is_not_refused() -> None:
    """The positive case: switch on, every token a test person, the number confirmed. Delete this
    and a function that refuses everything passes every refusal test below."""
    assert refusals() == ()


def test_a_switched_off_install_refuses_before_sending_anything() -> None:
    """Delete this and the switch that ships off does not stop the command."""
    got = refusals(switch_is_on=False)
    assert len(got) == 1
    assert "switched off" in got[0]


def test_a_token_that_is_not_a_test_person_refuses_and_names_nobody() -> None:
    """One of two tokens is somebody in another department, or in none. Delete this and a run is
    sent as a real person, on their rate window and into their history."""
    for outside in ("finance", None):
        callers = (CallerFacts("REAL-PERSON", outside), CallerFacts("b", LOAD_TEST_DEPARTMENT))
        got = refusals(callers=callers)
        assert len(got) == 1
        assert A_RUN_ASKS_AS_RESERVED_TEST_PEOPLE_ONLY in got[0]
        assert "REAL-PERSON" not in got[0]
        assert "finance" not in got[0]
    assert refusals(callers=())


def test_the_spend_is_confirmed_by_its_own_number() -> None:
    """A confirmation that differs from what would be sent, either way. Delete this and the bound
    is a default nobody read."""
    for confirmed in (39, 41, 0):
        got = refusals(confirmed=confirmed)
        assert len(got) == 1
        assert "--confirm-requests" in got[0]


def test_every_refusal_is_made_before_the_first_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Through the command: the switch off, a real person's token, a wrong confirmation. Each ends
    with exit 2, nothing sent and nothing kept, and the sentence names no token and no person.
    Delete this and a refusal is only ever tested as a function, never as the thing that stops a
    spend."""
    sends = Sends()
    monkeypatch.setattr(load_peak, "http_sender", sends)
    kept: list[RunRecord] = []
    closed: list[str] = []
    ok = people(LOAD_TEST_DEPARTMENT, LOAD_TEST_DEPARTMENT)
    cases = {
        "switch": (arguments(tmp_path), keeper(on=False, kept=kept, closed=closed), ok),
        "person": (
            arguments(tmp_path),
            keeper(kept=kept, closed=closed),
            people(LOAD_TEST_DEPARTMENT, "finance"),
        ),
        "number": (
            arguments(tmp_path, confirm=RUN + 1),
            keeper(kept=kept, closed=closed),
            ok,
        ),
    }
    for case, (argv, held, ask) in cases.items():
        assert main(argv, sleep=no_waiting, keeper=held, ask_who=ask) == load_peak.EXIT_REFUSED, (
            case
        )
    assert sends.count == 0
    assert kept == []
    assert closed == ["closed"] * 3
    said = capsys.readouterr()
    assert "TOKEN-" not in said.err + said.out
    assert "REAL-PERSON" not in said.err + said.out


def test_a_run_that_meets_every_condition_is_sent_judged_and_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sibling of the test above, through the same command. Delete this and a command that
    refuses everything passes it."""
    sends = Sends()
    monkeypatch.setattr(load_peak, "http_sender", sends)
    kept: list[RunRecord] = []
    closed: list[str] = []
    ok = people(LOAD_TEST_DEPARTMENT, LOAD_TEST_DEPARTMENT)
    held = keeper(kept=kept, closed=closed)
    assert main(arguments(tmp_path), sleep=no_waiting, keeper=held, ask_who=ok) == 0
    assert sends.count == RUN
    assert len(kept) == 1
    assert closed == ["closed"]
    one = kept[0]
    assert (one.planned, one.sent, one.not_sent, one.people) == (RUN, RUN, 0, 2)
    assert (one.profile, one.commit, one.arrivals_per_second) == ("full", "a-release", 2.0)
    assert (one.stated_arrivals_per_second, one.stated_in_flight) == (2.0, 8.0)
    assert not one.at_stated_peak
    out = capsys.readouterr().out
    assert f"kept: this install holds the result as run {kept[0].run_id}" in out
    assert out.splitlines()[-2] == HELD_BELOW_THE_STATED_PEAK


def test_a_lower_rate_is_driven_and_recorded_as_not_the_peak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One arrival a second for a hundred seconds, which is half the full profile's stated peak.
    Delete this and `--arrivals-per-second` is accepted and ignored, so a run named a quarter of the
    peak is driven at the whole of it, or recorded as having been."""
    sends = Sends()
    monkeypatch.setattr(load_peak, "http_sender", sends)
    kept: list[RunRecord] = []
    ok = people(LOAD_TEST_DEPARTMENT, LOAD_TEST_DEPARTMENT)
    argv = [*arguments(tmp_path, confirm=100), "--arrivals-per-second", "1"]
    main(argv, sleep=no_waiting, keeper=keeper(kept=kept), ask_who=ok)
    assert sends.count == 100
    assert kept[0].arrivals_per_second == 1.0
    assert kept[0].stated_arrivals_per_second == 2.0
    assert not kept[0].at_stated_peak


def test_a_run_that_cannot_keep_its_result_prints_it_and_exits_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and a result the install could not store looks kept, or the figures a spend
    bought are thrown away with the failed write."""
    monkeypatch.setattr(load_peak, "http_sender", Sends())
    ok = people(LOAD_TEST_DEPARTMENT, LOAD_TEST_DEPARTMENT)
    got = main(arguments(tmp_path), sleep=no_waiting, keeper=keeper(fails=True), ask_who=ok)
    assert got == load_peak.EXIT_UNKEPT
    out = capsys.readouterr().out
    assert "not kept" in out
    assert "outcomes:" in out


def test_a_run_with_no_database_to_keep_its_result_in_refuses_before_sending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real `database_keeper` with no database named. Delete this and a run spends model calls
    and then has nowhere to put what it measured."""
    for name in ("DATABASE_URL", "BRAIN_DATABASE_URL", "BRAIN_MIGRATION_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    sends = Sends()
    monkeypatch.setattr(load_peak, "http_sender", sends)
    ok = people(LOAD_TEST_DEPARTMENT, LOAD_TEST_DEPARTMENT)
    assert main(arguments(tmp_path), sleep=no_waiting, ask_who=ok) == load_peak.EXIT_REFUSED
    assert sends.count == 0
    assert "refuses" in capsys.readouterr().err


def test_the_command_cannot_be_started_without_the_number_that_confirms_it(tmp_path: Path) -> None:
    """Delete this and `--confirm-requests` becomes optional, which is the bound being a default."""
    without = arguments(tmp_path)[:-2]
    with pytest.raises(SystemExit):
        main(without, sleep=no_waiting, keeper=keeper(), ask_who=people())


# -------------------------------------------------------------------------- who is asking
def test_the_install_is_asked_who_each_token_is_and_a_refused_token_ends_the_run() -> None:
    """In-memory answers: a person in the test department, then a token the install does not
    accept. Delete this and the guard on whose token it is rests on a function nothing exercises
    against an answer."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.headers["authorization"] == "Bearer good":
            return httpx.Response(
                200, json={"principal_id": "p1", "primary_department": LOAD_TEST_DEPARTMENT}
            )
        if request.headers["authorization"] == "Bearer none":
            return httpx.Response(200, json={"principal_id": "p2", "primary_department": None})
        return httpx.Response(401)

    transport = httpx.MockTransport(answer)
    found = asyncio.run(who_asks("https://install.example", ("good", "none"), transport=transport))
    assert found == (CallerFacts("p1", LOAD_TEST_DEPARTMENT), CallerFacts("p2", None))
    with pytest.raises(LoadError):
        asyncio.run(who_asks("https://install.example", ("good", "bad"), transport=transport))


def test_an_answer_that_is_not_json_is_a_refusal_and_not_a_crash() -> None:
    """Delete this and a proxy's error page turns into a traceback in the middle of a refusal."""

    def page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>")

    with pytest.raises(LoadError):
        asyncio.run(
            who_asks("https://install.example", ("t",), transport=httpx.MockTransport(page))
        )


# ----------------------------------------------------------------------- what is kept
def a_run(*, shed_one: bool = False, stated: str = "full") -> tuple[RunRecord, Measured]:
    samples = [answered(Lane.ANSWER, 1.0) for _ in range(40)]
    samples += [answered(Lane.FAST, 0.1) for _ in range(40)]
    if shed_one:
        samples[0] = shed(Lane.ANSWER)
    report = judge(samples)
    got = Measured(samples=tuple(samples), most_in_flight=7, not_sent=0, seconds_run=600.2)
    record = record_of(
        report,
        got,
        profile(arrivals_per_second=2.0, seconds=PEAK_SECONDS),
        stated_peak(stated),
        started_at=datetime(2999, 1, 1, tzinfo=UTC),
        commit="a-release",
        run_id="abc123",
    )
    return record, got


def test_a_run_that_held_at_the_whole_peak_is_kept_as_held_at_the_peak() -> None:
    """The positive record: every lane held, the whole rate and length. Delete this and a record
    that always says `not held`, or never says `at_stated_peak`, passes."""
    record, _ = a_run()
    assert record.held
    assert record.at_stated_peak
    assert record.sent == 80
    assert record.most_in_flight == 7
    assert {one.lane for one in record.lanes} == {"answer", "fast"}
    assert lines_of(record)[-1] == HELD_AT_THE_STATED_PEAK


def test_a_run_the_judge_found_unmet_is_kept_as_not_held_with_its_findings() -> None:
    """Delete this and a failed run is kept without the sentences saying which objective failed."""
    record, _ = a_run(shed_one=True)
    assert not record.held
    assert record.findings
    assert record.interactive_shed == 1
    assert lines_of(record)[-1] == NOT_HELD


def test_a_run_that_stopped_is_not_held_and_says_how_much_it_did_not_send() -> None:
    """Every lane that was measured held, but requests were held back because the limits bound.
    Delete this and a run that stopped early is reported as the peak held."""
    record, got = a_run()
    stopped = record_of(
        judge(list(got.samples)),
        Measured(samples=got.samples, most_in_flight=7, not_sent=1120, seconds_run=30.0),
        profile(arrivals_per_second=2.0, seconds=PEAK_SECONDS),
        stated_peak("full"),
        started_at=datetime(2999, 1, 1, tzinfo=UTC),
        commit="a-release",
        run_id="def456",
    )
    assert not stopped.held
    assert not stopped.at_stated_peak
    assert stopped.not_sent == 1120
    assert any("1120 of 1200" in one for one in stopped.findings)
    assert record.held


def test_a_record_holds_no_token_no_person_and_no_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole value a command keeps, serialised and searched for what it was given. Delete this
    and a later change can put a question or a principal into a row anybody with the setting's
    screen can read."""
    monkeypatch.setattr(load_peak, "http_sender", Sends())
    kept: list[RunRecord] = []
    ok = people(LOAD_TEST_DEPARTMENT, LOAD_TEST_DEPARTMENT)
    assert main(arguments(tmp_path), sleep=no_waiting, keeper=keeper(kept=kept), ask_who=ok) == 0
    text = json.dumps(kept[0].as_value())
    for given in ("TOKEN-ONE", "TOKEN-TWO", "REAL-PERSON", "QUESTION-A-LOOKUP", "QUESTION-FOR"):
        assert given not in text


# --------------------------------------------------------------- nothing starts it by itself
def _python_files() -> list[Path]:
    return sorted((SRC / "brain").rglob("*.py"))


def test_nothing_in_the_product_builds_the_sender_but_the_command() -> None:
    """Every call to `http_sender` under `src`, found by parsing. Delete this and a schedule, a
    route or a check can build the live sender, and a spend starts without a person."""
    callers: set[str] = set()
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                    if name == "http_sender":
                        callers.add(f"{path.relative_to(SRC)}:{function.name}")
    assert callers == {"brain/ops/load_peak.py:_run"}


def test_no_module_imports_the_command_except_the_install_s_own_check() -> None:
    """Every importer of `brain.ops.load_peak` under `src`. Delete this and a scheduled job, the
    worker or a route can import the run and start it on a timer, which this command is built
    never to be."""
    importers: set[str] = set()
    for path in _python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            named = ""
            if isinstance(node, ast.ImportFrom):
                named = node.module or ""
                if named == "brain.ops" and any(a.name == "load_peak" for a in node.names):
                    named = "brain.ops.load_peak"
            elif isinstance(node, ast.Import):
                named = next((a.name for a in node.names if a.name == "brain.ops.load_peak"), "")
            if named == "brain.ops.load_peak":
                importers.add(str(path.relative_to(SRC)))
    assert importers == {"brain/ops/acceptance_checks_load_peak.py"}
