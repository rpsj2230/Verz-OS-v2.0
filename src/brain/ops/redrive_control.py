"""A job set aside for a person, put back on its queue because a person asked, and what the worker
does about each ask.

`brain.ops.recovery_run.sweep_queue` decides, every minute, which jobs run again and which are set
aside for a person. Nothing let the person act on what was set aside: the Scheduled jobs screen
listed the jobs and said they were waiting for somebody, and the somebody had a shell. This is the
other half, as rows a person writes and a rule the worker applies, shaped like
`brain.ops.schedule_control` and for the same reasons.

**An ask is an instant per job, `queue.redrive_asked.job_<id>`, and an answer is the worker's own
row, `queue.redrive_answered.job_<id>`.** The application has no connection to the queue, whose
tables are refused to it (`brain.ops.queue`), so the ask cannot be a call. It is a row in
`ops.setting`, which `0059`'s trigger puts in the audit ledger with the person who pressed. The
worker's minute reads every ask whose instant is later than its answer, puts that one job back with
the driver's own retry, and writes the answer: the instant it did so, and whether the job was in
fact put back. A second press moves the instant and asks again, two presses before the minute ask
once, and a worker that dies between the retry and the answer asks the driver to retry a job that is
no longer failed, which the driver refuses and the answer then says in words. See
`AN_ASK_IS_AN_INSTANT_AND_AN_ANSWER_IS_THE_WORKER_S_OWN_ROW`.

**A person may run a set-aside job again and the sweep may not, and that is the whole point.** The
sweep sets a job aside because its task is not declared safe to run twice
(`brain.ops.recovery_run.REDRIVE_BY_TASK`) or because it was put back often enough. Both are
judgements a machine cannot revise and a person looking at what the job was for can. So the control
is the person's decision, recorded under their name, and it does not alter what the sweep decides
for anybody else's job. See `A_PERSON_MAY_RUN_A_SET_ASIDE_JOB_AGAIN_AND_THE_SWEEP_NEVER_MAY`.

**The job is the same job, with the arguments it already had.** The dead letter row holds no
arguments, by design (`brain.tables.dead_letter`), so the control cannot raise a new job from it and
does not try: it asks the driver to retry the one it holds. `brain.ops.jobs` rejects a requeue edge
out of `DEAD_LETTER` for a job a person has cancelled or a worker has aborted, because trying
again is doing what somebody asked not to be done; neither of those is a dead letter's reason
(`DeadLetterReason` has four, all of them a job that was meant to run and did not), and the
driver's retry refuses a job that is not failed. Rejected: a new job built from the dead letter's
task name. It would need the arguments, which would mean keeping them, which is the copy of
somebody's data the dead letter was built not to be.

**Nothing here decides who may press.** The route does, by `admin:schedule` over everything and the
dead letter's own read, and a switch (`brain.ops.features_declared.job_redrive`) ships off. What is
here is the rows and the rule.

Rejected: a queue of asks that the worker consumes. A consumer that dies between taking an ask and
retrying the job loses it silently, and a person has no way to tell. An instant against an answer
loses nothing and says on the screen which has happened.

Task ids: M27.13.3
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.ops.setting_store import SettingState

# ------------------------------------------------------------------ written-down reasons
#: Why an ask is an instant and an answer a row of the worker's own.
AN_ASK_IS_AN_INSTANT_AND_AN_ANSWER_IS_THE_WORKER_S_OWN_ROW: Final = (
    "The application cannot call the queue, so a person's ask is a row it can write, an instant "
    "per job. The worker answers in a row of its own, so the screen can say whether the job was "
    "put back and when, and an ask is live exactly while it is later than its answer. Nothing is "
    "taken, marked or deleted from the ask, so a worker that dies halfway loses nothing and two "
    "presses before its minute ask once."
)

#: Why this is a person's act and not a rule for the sweep.
A_PERSON_MAY_RUN_A_SET_ASIDE_JOB_AGAIN_AND_THE_SWEEP_NEVER_MAY: Final = (
    "The sweep sets a job aside because its task is not declared safe to run twice, or because it "
    "was put back often enough already. A person who knows what the job was for may decide it is "
    "safe this once; a machine that decided the same would be revising its own judgement with "
    "nothing new to go on. So the control is a person's, recorded under their name, and what the "
    "sweep decides for every other job is not changed by it."
)

# ------------------------------------------------------------------------ the figures
#: `queue.redrive_asked.job_<id>`, an ISO 8601 instant with its offset.
ASKED_NAMESPACE: Final = "queue.redrive_asked"

#: `queue.redrive_answered.job_<id>`, the worker's answer as an object.
ANSWERED_NAMESPACE: Final = "queue.redrive_answered"

#: What an ask says about itself in `ops.setting.description`.
ASKED_DESCRIPTION: Final = "When a person last asked for this set-aside job to be run again"

#: What the worker's answer says about itself.
ANSWERED_DESCRIPTION: Final = "When the worker last answered a person's ask to run this job again"

#: Who the worker writes an answer as.
WORKER: Final = "system"

#: The driver's job id as text: digits, and no more than the dead letter table's column holds.
JOB_ID: Final = re.compile(r"^[0-9]{1,32}$")

#: The most asks one minute carries out. A person pressing a hundred buttons gets them over a few
#: minutes rather than a minute that does nothing else.
MOST_PER_MINUTE: Final = 20

#: What the screen says of an ask nobody has answered yet.
NOT_ANSWERED_YET: Final = "PersonAsk; the worker answers within a minute."

#: What the screen says of an answer that put the job back.
PUT_BACK: Final = "The worker put this job back on its queue."

#: What the screen says of an answer that could not.
COULD_NOT_PUT_BACK: Final = (
    "The worker could not put this job back, because it is no longer waiting for a person: it has "
    "run again already, or finished."
)


class RedriveError(Exception):
    """Raised for an id that could not be a job at all, with the reason."""


def row_name(job_id: str) -> str:
    """The name one job's ask and answer rows carry: `job_` and its digits.

    A setting key's segments begin with a letter, and the driver's ids are numbers, so the prefix
    is what makes the key valid. Refuses anything that is not digits, before a key is built from
    text a caller sent.
    """
    if JOB_ID.fullmatch(job_id) is None:
        msg = "a job id is the queue's number for it, digits only"
        raise RedriveError(msg)
    return f"job_{job_id}"


def job_id_of(name: str) -> str | None:
    """The job id a row name carries, or None for a name that is not `job_<digits>`."""
    found = re.fullmatch(r"job_([0-9]{1,32})", name)
    return None if found is None else found.group(1)


def instant_of(value: object) -> datetime | None:
    """A zoned instant out of a stored string, or None for anything else.

    A naive instant is refused for `schedule_control.requested_at`'s reason: compared against the
    worker's clock it is wrong by the host's offset, and an ask that fires hours early or late is
    worse than one that does not fire.
    """
    if not isinstance(value, str):
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


@dataclass(frozen=True)
class PersonAsk:
    """One person's ask: the instant, and who pressed."""

    at: datetime
    by: str


@dataclass(frozen=True)
class WorkerAnswer:
    """The worker's answer to an ask: when, and whether the job was put back."""

    at: datetime
    put_back: bool


def asked_in(states: Mapping[str, SettingState]) -> dict[str, PersonAsk]:
    """Every readable ask, by job id. A row that holds no zoned instant is not an ask."""
    found: dict[str, PersonAsk] = {}
    for name, state in states.items():
        job = job_id_of(name)
        at = instant_of(state.value) if state.value_type == "string" else None
        if job is not None and at is not None:
            found[job] = PersonAsk(at=at, by=state.updated_by)
    return found


def answer_of(value: object) -> WorkerAnswer | None:
    """The worker's answer a stored value holds, or None for anything that is not `{at, put_back}`.

    A zoned instant and a real boolean, both: a row written by hand with `"put_back": "yes"` is
    not an answer, and an ask whose "answer" is not one stays live.
    """
    if not isinstance(value, dict):
        return None
    at = instant_of(value.get("at"))
    put_back = value.get("put_back")
    if at is None or not isinstance(put_back, bool):
        return None
    return WorkerAnswer(at=at, put_back=put_back)


def answered_in(states: Mapping[str, SettingState]) -> dict[str, WorkerAnswer]:
    """Every readable answer, by job id."""
    found: dict[str, WorkerAnswer] = {}
    for name, state in states.items():
        job = job_id_of(name)
        answer = answer_of(state.value)
        if job is not None and answer is not None:
            found[job] = answer
    return found


def is_live(asked: PersonAsk, answered: WorkerAnswer | None, *, now: datetime) -> bool:
    """Whether the worker still owes this ask an answer.

    Later than its answer, and not in the future. The comparison on the answer is strict, so an
    answer written at the very instant of the ask counts as having answered it: the worker reads
    an ask and answers it a moment later, never before.
    """
    if asked.at > now:
        return False
    return answered is None or answered.at < asked.at


def live_job_ids(
    asked: Mapping[str, PersonAsk], answered: Mapping[str, WorkerAnswer], *, now: datetime
) -> tuple[str, ...]:
    """Every job id with a live ask, oldest ask first, bounded to what one minute carries out."""
    owed = sorted(
        (one.at, job) for job, one in asked.items() if is_live(one, answered.get(job), now=now)
    )
    return tuple(job for _, job in owed[:MOST_PER_MINUTE])


def standing_of(asked: PersonAsk | None, answered: WorkerAnswer | None) -> str | None:
    """What the screen says about one job's ask, or None when nobody has asked.

    A sentence, because the question is asked in a row and "True" would not answer it. An answer
    older than the ask is not this ask's answer, so the ask stands unanswered.
    """
    if asked is None:
        return None
    if answered is None or answered.at < asked.at:
        return NOT_ANSWERED_YET
    return PUT_BACK if answered.put_back else COULD_NOT_PUT_BACK


# ------------------------------------------------------------------------ the rows
async def asked_states(session: AsyncSession) -> dict[str, SettingState]:
    """Every live ask row, by row name."""
    from brain.ops.setting_store import read_namespace, values_under

    return values_under(await read_namespace(session, ASKED_NAMESPACE), ASKED_NAMESPACE)


async def answered_states(session: AsyncSession) -> dict[str, SettingState]:
    """Every live answer row, by row name."""
    from brain.ops.setting_store import read_namespace, values_under

    return values_under(await read_namespace(session, ANSWERED_NAMESPACE), ANSWERED_NAMESPACE)


async def ask(session: AsyncSession, job_id: str, *, at: datetime, by: str) -> None:
    """Ask for one set-aside job to be run again, in the caller's transaction.

    The caller commits, and sets who is pressing before this runs, so the entry `0059`'s trigger
    appends names them.
    """
    # Imported here and not at the top: `brain.ops.queue` imports this module for its shapes, and
    # the store reaches the tables, which reach the queue's own importers.
    from brain.ops.setting_store import put
    from brain.tables.config import SettingType

    if at.tzinfo is None:
        msg = "an ask at a naive instant would fire early or late by the host's offset"
        raise RedriveError(msg)
    await put(
        session,
        f"{ASKED_NAMESPACE}.{row_name(job_id)}",
        value_type=SettingType.STRING,
        value=at.isoformat(),
        description=ASKED_DESCRIPTION,
        updated_by=by,
    )


# ------------------------------------------------------------------------ the worker's half
class AskedRedrives(Protocol):
    """What the worker's minute needs of the queue to carry out the asks.

    `brain.ops.queue.DriverQueue` over the driver and `ops.setting`; a test hands another.
    """

    async def asks(self) -> tuple[tuple[str, PersonAsk, WorkerAnswer | None], ...]:
        """Every ask with its answer, whether or not it is live."""
        ...

    async def put_back(self, job_id: str, now: datetime) -> bool:
        """Put this job back on its queue, if and only if it is failed. False when it is not.

        Not `QueueRows.run_again`, which the sweep also uses for a running job whose worker has
        stopped: a person's ask must never move a job that is running or waiting, and the driver's
        retry would accept one.
        """
        ...

    async def answer(self, job_id: str, answer: WorkerAnswer) -> None:
        """Record the worker's answer to the ask for this job."""
        ...


@dataclass(frozen=True)
class Redriven:
    """What one minute did about the asks: the jobs put back, and the ones that could not be."""

    put_back: tuple[str, ...]
    could_not: tuple[str, ...]

    def summary(self) -> str:
        """A sentence for the run record, or the empty string when nobody had asked."""
        if not self.put_back and not self.could_not:
            return ""
        said = f"{len(self.put_back)} job(s) put back at a person's asking"
        if self.could_not:
            said += f", {len(self.could_not)} no longer waiting for a person"
        return said


async def carry_out_asks(rows: AskedRedrives, *, now: datetime) -> Redriven:
    """Put back every job a person asked for and has not been answered, and answer each.

    The answer is written after the retry and not before, so an ask the worker died on is asked
    again, and the driver's refusal of a job that is no longer failed is what turns that second go
    into an answer saying so rather than a second run. One ask failing to be recorded stops the
    minute with the exception, rather than answering the rest and leaving that one to be put back
    twice.
    """
    every = await rows.asks()
    asked = {job: one for job, one, _ in every}
    answered = {job: found for job, _, found in every if found is not None}
    put_back: list[str] = []
    could_not: list[str] = []
    for job in live_job_ids(asked, answered, now=now):
        moved = await rows.put_back(job, now)
        await rows.answer(job, WorkerAnswer(at=now, put_back=moved))
        (put_back if moved else could_not).append(job)
    return Redriven(put_back=tuple(put_back), could_not=tuple(could_not))
