"""A person's ask to run a set-aside job again, and what the worker's minute does about each.

The pure half: which asks are live, what a row must hold to count as an ask or an answer, what the
screen says of each, and the minute itself over a queue held in memory. The routes are
`tests/unit/test_redrive_routes.py`, and the SQL the worker runs is
`tests/unit/test_dead_letter.py`'s database half.

Every refusal here has a sibling proving the same input is carried out when it should be, because a
guard tested only by its refusals is satisfied by a worker that never puts a job back.

Task ids: M27.13.3
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.redrive_control import (
    ANSWERED_NAMESPACE,
    ASKED_NAMESPACE,
    COULD_NOT_PUT_BACK,
    MOST_PER_MINUTE,
    NOT_ANSWERED_YET,
    PUT_BACK,
    PersonAsk,
    RedriveError,
    WorkerAnswer,
    answer_of,
    answered_in,
    asked_in,
    carry_out_asks,
    instant_of,
    is_live,
    job_id_of,
    live_job_ids,
    row_name,
    standing_of,
)
from brain.ops.setting_store import SettingState

#: Far from any wall clock, so no fixture here goes off on a date nobody chose.
NOW = datetime(2999, 1, 1, 12, tzinfo=UTC)
EARLIER = NOW - timedelta(minutes=5)
LATER = NOW + timedelta(minutes=5)


def state(key: str, value: object, *, kind: str = "string", by: str = "u_admin") -> SettingState:
    return SettingState(key=key, value_type=kind, value=value, updated_by=by, updated_at=NOW)


def test_a_job_id_is_the_digits_the_queue_numbers_it_by_and_nothing_else() -> None:
    """The row name is built from text a caller sent, so anything but digits is refused before a
    key exists, and the digits round-trip. Delete this and a path segment becomes part of a
    setting key."""
    assert row_name("41") == "job_41"
    assert job_id_of("job_41") == "41"
    for refused in ("", "4 1", "41.queue", "../41", "job_41", "-1", "4" * 33):
        with pytest.raises(RedriveError):
            row_name(refused)
    assert job_id_of("job_") is None
    assert job_id_of("41") is None


def test_an_ask_is_live_only_while_it_is_later_than_its_answer_and_not_in_the_future() -> None:
    """The four cases the worker's minute turns on. Delete this and an answered ask is carried out
    again every minute, or an unanswered one never is."""
    asked = PersonAsk(at=EARLIER, by="u_admin")
    assert is_live(asked, None, now=NOW) is True
    assert is_live(asked, WorkerAnswer(at=NOW, put_back=True), now=NOW) is False
    assert is_live(asked, WorkerAnswer(at=EARLIER - timedelta(seconds=1), put_back=True), now=NOW)
    # An answer at the very instant of the ask answers it: the worker reads, then writes.
    assert is_live(asked, WorkerAnswer(at=EARLIER, put_back=False), now=NOW) is False
    assert is_live(PersonAsk(at=LATER, by="u_admin"), None, now=NOW) is False


def test_live_asks_come_oldest_first_and_one_minute_carries_out_a_bounded_number() -> None:
    """Delete this and a person pressing a hundred buttons gets a minute that does nothing else."""
    many = {
        str(n): PersonAsk(at=NOW - timedelta(seconds=n), by="u_admin")
        for n in range(1, MOST_PER_MINUTE + 6)
    }
    chosen = live_job_ids(many, {}, now=NOW)

    assert len(chosen) == MOST_PER_MINUTE
    assert chosen[0] == str(MOST_PER_MINUTE + 5)
    assert list(chosen) == sorted(chosen, key=lambda one: -int(one))


def test_a_row_is_an_ask_only_when_it_holds_a_zoned_instant_for_a_job_id() -> None:
    """A row written by hand that holds a naive instant, a number or text that is no instant is
    not an ask, because a naive instant is wrong by the host's offset. Delete this and a stray row
    makes the worker retry a job at the wrong time."""
    good = state(f"{ASKED_NAMESPACE}.job_7", NOW.isoformat())
    found = asked_in(
        {
            "job_7": good,
            "job_8": state("k", "2999-01-01T12:00:00"),
            "job_9": state("k", "not an instant"),
            "job_10": state("k", 5, kind="integer"),
            "job_11": state("k", NOW.isoformat(), kind="json"),
            "other": good,
        }
    )
    assert found == {"7": PersonAsk(at=NOW, by="u_admin")}
    assert instant_of(NOW.isoformat()) == NOW
    assert instant_of(None) is None


def test_a_row_is_an_answer_only_when_it_holds_an_instant_and_a_real_boolean() -> None:
    """Delete this and a row saying `put_back: "yes"` answers an ask, so the ask is never carried
    out and the screen says it was."""
    assert answer_of({"at": NOW.isoformat(), "put_back": True}) == WorkerAnswer(NOW, True)
    assert answer_of({"at": NOW.isoformat(), "put_back": "yes"}) is None
    assert answer_of({"at": "2999-01-01T12:00:00", "put_back": True}) is None
    assert answer_of({"put_back": True}) is None
    assert answer_of("a string") is None
    found = answered_in(
        {
            "job_7": state(
                f"{ANSWERED_NAMESPACE}.job_7", {"at": NOW.isoformat(), "put_back": False}
            ),
            "job_8": state("k", {"at": "nope", "put_back": True}, kind="json"),
        }
    )
    assert found == {"7": WorkerAnswer(NOW, False)}


def test_the_screen_says_what_became_of_an_ask_and_nothing_of_a_job_nobody_asked_about() -> None:
    """Delete this and a job nobody asked about carries a sentence, or an answer older than the
    ask is read as this ask's."""
    asked = PersonAsk(at=NOW, by="u_admin")
    assert standing_of(None, WorkerAnswer(at=NOW, put_back=True)) is None
    assert standing_of(asked, None) == NOT_ANSWERED_YET
    assert standing_of(asked, WorkerAnswer(at=EARLIER, put_back=True)) == NOT_ANSWERED_YET
    assert standing_of(asked, WorkerAnswer(at=NOW, put_back=True)) == PUT_BACK
    assert standing_of(asked, WorkerAnswer(at=LATER, put_back=False)) == COULD_NOT_PUT_BACK


class Queue:
    """A queue in memory: the asks and answers, which jobs the driver would put back, and what the
    minute wrote."""

    def __init__(self, *, failed: set[str]) -> None:
        self.rows: dict[str, tuple[PersonAsk, WorkerAnswer | None]] = {}
        self.failed = failed
        self.retried: list[str] = []
        self.written: list[tuple[str, WorkerAnswer]] = []

    async def asks(self) -> tuple[tuple[str, PersonAsk, WorkerAnswer | None], ...]:
        return tuple((job, ask, answer) for job, (ask, answer) in self.rows.items())

    async def put_back(self, job_id: str, now: datetime) -> bool:
        self.retried.append(job_id)
        return job_id in self.failed

    async def answer(self, job_id: str, answer: WorkerAnswer) -> None:
        self.written.append((job_id, answer))
        self.rows[job_id] = (self.rows[job_id][0], answer)


def test_the_minute_puts_back_every_live_ask_once_and_answers_each() -> None:
    """The positive case, and the property the whole control rests on: a second minute over the
    same rows does nothing, because every ask now has an answer later than itself. Delete this and
    a job is put back every minute for ever, or never."""
    queue = Queue(failed={"7"})
    queue.rows = {
        "7": (PersonAsk(EARLIER, "u_admin"), None),
        "8": (PersonAsk(EARLIER, "u_admin"), None),
        "9": (PersonAsk(EARLIER, "u_admin"), WorkerAnswer(NOW, True)),
    }

    first = asyncio.run(carry_out_asks(queue, now=NOW))
    second = asyncio.run(carry_out_asks(queue, now=NOW + timedelta(minutes=1)))

    assert first.put_back == ("7",)
    assert first.could_not == ("8",)
    assert queue.retried == ["7", "8"]
    assert [job for job, _ in queue.written] == ["7", "8"]
    assert queue.written[1][1].put_back is False
    assert second.put_back == () and second.could_not == ()
    assert queue.retried == ["7", "8"]


def test_a_press_after_an_answer_asks_again() -> None:
    """Delete this and a job that failed a second time can never be run again from the screen."""
    queue = Queue(failed={"7"})
    queue.rows = {"7": (PersonAsk(LATER, "u_admin"), WorkerAnswer(NOW, True))}

    carried = asyncio.run(carry_out_asks(queue, now=LATER + timedelta(minutes=1)))

    assert carried.put_back == ("7",)


def test_the_summary_is_empty_when_nobody_asked_and_names_the_counts_when_somebody_did() -> None:
    """Delete this and every minute's run record carries a sentence about asks nobody made."""
    queue = Queue(failed={"7"})
    nothing = asyncio.run(carry_out_asks(queue, now=NOW))
    assert nothing.summary() == ""
    queue.rows = {"7": (PersonAsk(EARLIER, "u"), None), "8": (PersonAsk(EARLIER, "u"), None)}
    said = asyncio.run(carry_out_asks(queue, now=NOW)).summary()
    assert "1 job(s) put back at a person's asking" in said
    assert "1 no longer waiting for a person" in said


def test_the_sweeps_run_record_says_what_was_put_back_at_a_persons_asking() -> None:
    """The line a person reads on the Scheduled jobs screen for the redrive sweep. Delete this and
    a job put back by a press leaves no trace in the run record, so the one place that says what
    the worker did this minute is silent about the one thing a person asked it to do."""
    from brain.ops.recovery_run import QueueSweep
    from brain.ops.redrive_control import Redriven

    quiet = QueueSweep(decided=(), ran_again=(), set_aside=(), moved_on=(), tasks={})
    asked = QueueSweep(
        decided=(),
        ran_again=(),
        set_aside=(),
        moved_on=(),
        tasks={},
        asked=Redriven(put_back=("7",), could_not=()),
    )

    assert "person's asking" not in quiet.summary()
    assert "1 job(s) put back at a person's asking" in asked.summary()
