"""A run of the acceptance checks survives a restart of the worker that serves the same commit.

**Found on the owner's staging install, and the same on every install.** The worker starts a run
after each deploy. A run takes thirty-five minutes and more (364 checks and growing), every merge
to main redeploys, and a redeploy restarts the worker, which killed the run in progress. Rows were
written only when the run ended, so on a day of frequent merges no run was recorded at all, and a
task closes only when the install's newest *complete* run passed every check naming it
(`brain.ops.proof_sweep`; two runs until the owner decided on 2026-10-14 that one complete clean
run is the gate). No leaf could close however many checks were written. The deploy cadence
cannot be much slower than the merge cadence, so the run has to survive the restart instead.

**What that fixed and what it did not, measured on 2026-10-14.** Resuming is keyed on the commit
the restarted worker serves, so it covers a restart that leaves the commit alone (a crash, the
host's memory killer, a reboot, a recreate by hand) and **not a deploy of a new commit**: that
worker serves another release, `A_RUN_OF_ANOTHER_RELEASE_IS_ABANDONED_AND_NEVER_COMPLETED` applies
and the run starts again from nothing. That is the right answer for a deploy that changed what the
worker runs, because the rows already written are about code that is gone, and it is why the
runs were still killed all night after this module existed: the title above used to say a run
survived the restart every deploy causes, and no deploy of a new commit ever resumed anything. The
repair is not to resume across commits but to stop restarting the worker for merges that change
nothing it runs: the server's deploy script leaves a worker alone when the fingerprint of what a
worker runs is unchanged (`brain.ops.restart_scope`). A merge that does change it still ends a run
in progress; narrowing that further would mean holding the worker's replacement back until the
run ends, which needs the timer to retry a worker that lags the app and is not built.

**A worker left running on the previous release still reports that release's commit.** Its runs
are recorded under that commit and the Install page, which asks for the commit the application
serves, shows no run for the newer one until a merge that changes what the worker runs replaces it.
Rejected here: labelling a run with the commit that last changed what the worker runs, which would
let both processes name one release but changes what every run's `commit` means, which is the
owner's to decide and is not decided here.

**Six rules, each with a name and a test.**

`A_CHECK_IS_RECORDED_WHEN_IT_FINISHES`: a run is opened in `ops.acceptance_run` under an id fixed at
its start, and each check's row is appended to `ops.acceptance_result` in the same transaction that
moves the run's heartbeat on, so a killed run leaves a partial record that is exactly what ran.

`A_RESTARTED_WORKER_FINISHES_THE_RUN_OF_ITS_OWN_RELEASE`: a worker that finds a run of the commit it
serves, still `running` with a heartbeat that has stopped, takes it over (one compare-and-set, so
two workers cannot both) and runs only the checks that have no result, under the same run id and
the original start. Its roll-up checks read the earlier checks' results from the rows, so a resumed
run reaches the verdict an uninterrupted one would.

`A_RUN_OF_ANOTHER_RELEASE_IS_ABANDONED_AND_NEVER_COMPLETED`: an unfinished run of any other commit
is marked `abandoned`. Results of two releases are never mixed in one run, because a resumed run
must be of the same commit and the sweep refuses rows of one run that name two.

`ONLY_A_COMPLETE_RUN_COUNTS`: the sweep, the page that says whether this commit is owed a run and
`ROWS_QUERY` read only complete runs. A run is marked `complete` after its last check is recorded
and not before, so a half-written run is never a run that has been seen.

`A_RUN_IS_COMPLETE_ONLY_WHEN_EVERY_REGISTERED_CHECK_RECORDED`: with one run as the whole gate,
"complete" has to mean something a reader can rely on without a second run to catch it. A run is
marked complete only after the store itself is read back and holds a result for every check the
suite registers (`finish_if_whole`), not because the loop that wrote them returned. A run that
ended with a registered check unrecorded stays `running`, so it is taken over and finished or
abandoned like any run a restart cut short, and the sweep never sees it.

`A_REPEAT_RUNS_ONLY_THE_UNSETTLED_AND_SAYS_WHAT_IT_CARRIED`: a run that came back with a failed
or not-run check is repeated for only those checks (`brain.ops.acceptance_run.repeat_unsettled`,
`--repeat-unsettled` on the command). The repeat is a **new run of the same commit** that copies
the earlier run's passes, each marked with where it came from (`CARRIED_FORWARD_FROM`), and runs
the rest, so it is complete only by the rule above and the earlier run stays as the fact it was.
It is never a run of another commit, because a repeat that carried passes across releases would be
the mixture `A_RUN_NAMES_ONE_RELEASE` refuses. Rejected: editing the failed rows in place (the
table is append-only, and the first failure is what somebody reading a regression needs), and
resuming the complete run (it is finished; a finished run is a fact).

**Why a heartbeat and not a lock.** The obvious way to stop two workers running one run is an
advisory lock held for the run's life. The application engine runs through PgBouncer in transaction
mode (`brain.session`), where a session lock belongs to whichever backend the next statement lands
on, which is the trap `brain.migrate` moved off `pg_advisory_lock` to escape. A heartbeat is data:
a run is its worker's while its heartbeat is newer than `STALE_AFTER`, which is longer than the
longest a check may take (`CHECK_TIMEOUT_SECONDS`), so a live worker is never taken over and a dead
one's run is taken at the next tick, at most five minutes (`RUN_EVERY`) after it could be. The price
is that a run is finished no sooner than `STALE_AFTER` after the kill; the run is thirty-five
minutes and this is three.

**What a commit that names no release never resumes.** `unknown` and `wip` are what a process with
no manifest reports, and two different builds can both say so, so a run of such a word could be
finished by a different build and carry two releases' results. Only a commit that is hexadecimal
is resumed.

Rejected: **pausing deploys** while a run is in flight (the cadence of merges is not the run's to
set, and a deploy held back is a fix held back); **running the acceptance outside the worker**
(a second process to deploy, supervise and give the install's settings and vault to, for a problem
that is only that rows were written too late); **a smaller or sampled suite** (it would close fewer
tasks on the same evidence and hide the checks that fail); **marking a run complete from its row
count** (the sweep reads a JSON file as well as a database and knows no registry, so completeness
has to be something the run said, not something a reader infers).

Task ids: M38.5.1, M38.5.4
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from brain.ops.acceptance import CARRIED_FORWARD_FROM, PASSED, Occasion, Result
from brain.tables.acceptance import AcceptanceResultRow, AcceptanceRunRow

# ------------------------------------------------------------------ written-down reasons
#: Why a result is written the moment its check ends.
A_CHECK_IS_RECORDED_WHEN_IT_FINISHES: Final = (
    "Each check's result is appended as the check ends, under the run's id, in the same "
    "transaction that moves the run's heartbeat on. A worker killed in the middle of a run "
    "leaves what ran and nothing that did not, instead of leaving nothing."
)

#: Why a restarted worker takes a run over.
A_RESTARTED_WORKER_FINISHES_THE_RUN_OF_ITS_OWN_RELEASE: Final = (
    "A worker that finds an unfinished run of the commit it serves, whose heartbeat has stopped, "
    "runs only the checks with no result and finishes it under the same run id, because a deploy "
    "restarts the worker more often than a run can finish."
)

#: Why a run of another release is never carried on.
A_RUN_OF_ANOTHER_RELEASE_IS_ABANDONED_AND_NEVER_COMPLETED: Final = (
    "An unfinished run of any commit but the one served is marked abandoned. Finishing it would "
    "put results of two releases in one run, which would then be read as what one release did."
)

#: Why a reader looks at complete runs only.
ONLY_A_COMPLETE_RUN_COUNTS: Final = (
    "A run counts when it was marked complete after its last check was recorded, and not when "
    "some of its rows exist. The sweep, the owed-run question and the sweep's query all read "
    "complete runs only."
)

#: Why a run is marked complete only after its record is read back.
A_RUN_IS_COMPLETE_ONLY_WHEN_EVERY_REGISTERED_CHECK_RECORDED: Final = (
    "A run is marked complete only when the store holds a result for every check the suite "
    "registers, read back after the last one was written. A run that ended short of that stays "
    "running and is settled like any run a restart cut short, so the one complete run the proof "
    "sweep now reads is never a partial one."
)

#: Why a repeat is a new run of the same commit that says what it carried.
A_REPEAT_RUNS_ONLY_THE_UNSETTLED_AND_SAYS_WHAT_IT_CARRIED: Final = (
    "A repeat runs only the checks that failed or came back not run, in a new run of the same "
    "commit that copies the earlier run's passes with the run they came from, so the result is "
    "one complete run and a reader can tell which results were not run again."
)

# ----------------------------------------------------------------------------- the figures
RUNNING: Final = "running"
COMPLETE: Final = "complete"
ABANDONED: Final = "abandoned"

#: Longer than a check may take (`brain.ops.acceptance_run.CHECK_TIMEOUT_SECONDS`, 120 seconds) with
#: a minute over for the run's own set-up between one check's end and the next one's start, so a
#: run whose worker is alive never looks dead. Held above that bound by a test.
STALE_AFTER: Final = timedelta(seconds=180)

#: A commit that names a build: hexadecimal, as a git abbreviation or whole. See the module.
RELEASE_COMMIT: Final = re.compile(r"^[0-9a-f]{7,40}$")


# ------------------------------------------------------------------------- the decision
@dataclass(frozen=True)
class Unfinished:
    """A run recorded as `running`, and how long ago its worker last said it was alive."""

    run_id: uuid.UUID
    commit: str
    occasion: Occasion
    started_at: datetime
    silent_for: timedelta


@dataclass(frozen=True)
class Settlement:
    """What to do about the runs found unfinished: take one over, leave some, abandon the rest."""

    #: The run of the commit served to finish, or none.
    resume: Unfinished | None
    #: Runs to mark abandoned.
    abandon: tuple[uuid.UUID, ...]
    #: Whether a run of the commit served is being run by a worker that is still alive, so a new
    #: one must not be started beside it.
    in_progress: bool


def settle(
    serving: str, found: Sequence[Unfinished], *, stale_after: timedelta = STALE_AFTER
) -> Settlement:
    """Decide what the unfinished runs mean for a worker serving `serving`.

    A run whose heartbeat is fresh is somebody's and is left alone, and if it is of this commit it
    is the reason to start nothing (`in_progress`). A silent run of another commit is abandoned,
    `A_RUN_OF_ANOTHER_RELEASE_IS_ABANDONED_AND_NEVER_COMPLETED`. Of the silent runs of this commit
    the newest is resumed, when the commit names a build, and the others are abandoned.
    """
    in_progress = False
    abandon: list[uuid.UUID] = []
    candidates: list[Unfinished] = []
    for one in found:
        if one.silent_for < stale_after:
            in_progress = in_progress or one.commit == serving
        elif one.commit == serving and RELEASE_COMMIT.match(serving):
            candidates.append(one)
        else:
            abandon.append(one.run_id)
    candidates.sort(key=lambda one: one.started_at, reverse=True)
    resume = None if in_progress or not candidates else candidates[0]
    abandon.extend(one.run_id for one in candidates if one is not resume)
    return Settlement(resume, tuple(abandon), in_progress)


def remaining(names: Sequence[str], recorded: Sequence[Result]) -> tuple[str, ...]:
    """The checks of `names` with no result yet, in suite order, each once."""
    done = {one.name for one in recorded}
    return tuple(dict.fromkeys(one for one in names if one not in done))


def unsettled(names: Sequence[str], recorded: Sequence[Result]) -> tuple[str, ...]:
    """The checks of `names` a repeat must run: no result, or one that is not a pass.

    In suite order, each once. A check with no result is included although the run it came from
    was complete, because a repeat that skipped it would carry nothing for it and the new run
    would be short of a registered check.
    """
    passed = {one.name for one in recorded if one.outcome == PASSED}
    return tuple(dict.fromkeys(one for one in names if one not in passed))


def carried_forward(
    names: Sequence[str], recorded: Sequence[Result], from_run: uuid.UUID
) -> tuple[Result, ...]:
    """The passes of `recorded` a repeat copies, for the checks of `names`, each saying where from.

    A check not in `names` is not carried, so a build that dropped a check does not record a
    result for it, and a failed or not-run result is never carried. See
    `A_REPEAT_RUNS_ONLY_THE_UNSETTLED_AND_SAYS_WHAT_IT_CARRIED`.
    """
    wanted = set(names)
    return tuple(
        Result(
            one.name,
            one.leaves,
            PASSED,
            one.checked_at,
            f"{CARRIED_FORWARD_FROM}{from_run} of this commit, where it passed",
        )
        for one in recorded
        if one.outcome == PASSED and one.name in wanted
    )


# ------------------------------------------------------------------------------ the store
async def open_run(
    engine: AsyncEngine,
    *,
    run_id: uuid.UUID,
    commit: str,
    occasion: Occasion,
    started_at: datetime,
) -> None:
    """Record that a run has begun, before its first check, so a restart finds it."""
    async with engine.begin() as connection:
        await connection.execute(
            insert(AcceptanceRunRow).values(
                run_id=run_id,
                commit=commit,
                occasion=occasion.value,
                status=RUNNING,
                started_at=started_at,
            )
        )


async def unfinished(engine: AsyncEngine) -> tuple[Unfinished, ...]:
    """Every run still `running`, with the time since its heartbeat on the database's own clock."""
    silent = func.extract("epoch", func.statement_timestamp() - AcceptanceRunRow.heartbeat_at)
    async with engine.connect() as connection:
        found = (
            await connection.execute(
                select(
                    AcceptanceRunRow.run_id,
                    AcceptanceRunRow.commit,
                    AcceptanceRunRow.occasion,
                    AcceptanceRunRow.started_at,
                    silent.label("silent"),
                ).where(AcceptanceRunRow.status == RUNNING)
            )
        ).all()
        await connection.rollback()
    return tuple(
        Unfinished(
            run_id=one.run_id,
            commit=one.commit,
            occasion=Occasion(one.occasion),
            started_at=one.started_at,
            silent_for=timedelta(seconds=float(one.silent)),
        )
        for one in found
    )


async def claim(
    engine: AsyncEngine, run_id: uuid.UUID, *, stale_after: timedelta = STALE_AFTER
) -> bool:
    """Take a silent run over: one compare-and-set, so of two workers only one is told yes."""
    async with engine.begin() as connection:
        taken = await connection.execute(
            update(AcceptanceRunRow)
            .where(
                AcceptanceRunRow.run_id == run_id,
                AcceptanceRunRow.status == RUNNING,
                AcceptanceRunRow.heartbeat_at <= func.statement_timestamp() - stale_after,
            )
            .values(heartbeat_at=func.statement_timestamp())
        )
    return taken.rowcount == 1


async def abandon(
    engine: AsyncEngine, run_ids: Sequence[uuid.UUID], *, stale_after: timedelta = STALE_AFTER
) -> int:
    """Mark silent runs abandoned. A run whose heartbeat moved since it was read is left alone."""
    if not run_ids:
        return 0
    async with engine.begin() as connection:
        marked = await connection.execute(
            update(AcceptanceRunRow)
            .where(
                AcceptanceRunRow.run_id.in_(list(run_ids)),
                AcceptanceRunRow.status == RUNNING,
                AcceptanceRunRow.heartbeat_at <= func.statement_timestamp() - stale_after,
            )
            .values(status=ABANDONED, ended_at=func.statement_timestamp())
        )
    return int(marked.rowcount)


async def beat(engine: AsyncEngine, run_id: uuid.UUID) -> None:
    """Say the run's worker is alive, before a check that may take two minutes."""
    async with engine.begin() as connection:
        await connection.execute(
            update(AcceptanceRunRow)
            .where(AcceptanceRunRow.run_id == run_id, AcceptanceRunRow.status == RUNNING)
            .values(heartbeat_at=func.statement_timestamp())
        )


async def record_check(
    engine: AsyncEngine,
    one: Result,
    *,
    run_id: uuid.UUID,
    commit: str,
    occasion: Occasion,
    started_at: datetime,
) -> None:
    """Append one check's row and move the heartbeat on, in one transaction.
    See `A_CHECK_IS_RECORDED_WHEN_IT_FINISHES`."""
    async with engine.begin() as connection:
        await connection.execute(
            insert(AcceptanceResultRow).values(
                run_id=run_id,
                commit=commit,
                occasion=occasion.value,
                check_name=one.name,
                leaves=" ".join(one.leaves),
                outcome=one.outcome,
                reason=one.reason or None,
                started_at=started_at,
                checked_at=max(one.checked_at, started_at),
            )
        )
        await connection.execute(
            update(AcceptanceRunRow)
            .where(AcceptanceRunRow.run_id == run_id, AcceptanceRunRow.status == RUNNING)
            .values(heartbeat_at=func.statement_timestamp())
        )


async def finish(engine: AsyncEngine, run_id: uuid.UUID) -> bool:
    """Mark the run complete, once its last check is recorded. False when it was not running,
    which is a run somebody abandoned while this worker was still going."""
    async with engine.begin() as connection:
        marked = await connection.execute(
            update(AcceptanceRunRow)
            .where(AcceptanceRunRow.run_id == run_id, AcceptanceRunRow.status == RUNNING)
            .values(status=COMPLETE, ended_at=func.statement_timestamp())
        )
    return marked.rowcount == 1


async def recorded(engine: AsyncEngine, run_id: uuid.UUID) -> tuple[Result, ...]:
    """What a run has recorded so far, oldest first. Each check once, the first result standing."""
    async with engine.connect() as connection:
        found = (
            await connection.execute(
                select(
                    AcceptanceResultRow.check_name,
                    AcceptanceResultRow.leaves,
                    AcceptanceResultRow.outcome,
                    AcceptanceResultRow.reason,
                    AcceptanceResultRow.checked_at,
                )
                .where(AcceptanceResultRow.run_id == run_id)
                .order_by(AcceptanceResultRow.checked_at, AcceptanceResultRow.check_name)
            )
        ).all()
        await connection.rollback()
    seen: dict[str, Result] = {}
    for one in found:
        seen.setdefault(
            one.check_name,
            Result(
                one.check_name,
                tuple(str(one.leaves).split()),
                one.outcome,
                one.checked_at,
                one.reason or "",
            ),
        )
    return tuple(seen.values())


async def checked_commits(engine: AsyncEngine, serving: str) -> tuple[str, ...]:
    """`serving` when a complete run of it is recorded, or nothing.

    A complete run is one marked so, or a run with no record in `ops.acceptance_run` at all, which
    is every run written whole before that table existed. `ONLY_A_COMPLETE_RUN_COUNTS`.
    """
    async with engine.connect() as connection:
        found = (
            await connection.execute(
                select(AcceptanceResultRow.commit)
                .outerjoin(AcceptanceRunRow, AcceptanceRunRow.run_id == AcceptanceResultRow.run_id)
                .where(
                    AcceptanceResultRow.commit == serving,
                    (AcceptanceRunRow.run_id.is_(None)) | (AcceptanceRunRow.status == COMPLETE),
                )
                .limit(1)
            )
        ).scalars()
        names = tuple(found)
        await connection.rollback()
    return names


@dataclass(frozen=True)
class CompleteRun:
    """A run recorded as `complete`, which is the only kind a repeat may start from."""

    run_id: uuid.UUID
    commit: str
    occasion: Occasion
    started_at: datetime


async def newest_complete_run(engine: AsyncEngine, commit: str) -> CompleteRun | None:
    """The newest run of `commit` marked complete, or none.

    A run with no record in `ops.acceptance_run` was written whole before that table existed and
    is complete for the sweep (`ONLY_A_COMPLETE_RUN_COUNTS`), but it has no run row to repeat from
    and its commit has long been replaced, so it is not offered here.
    """
    async with engine.connect() as connection:
        found = (
            await connection.execute(
                select(
                    AcceptanceRunRow.run_id,
                    AcceptanceRunRow.commit,
                    AcceptanceRunRow.occasion,
                    AcceptanceRunRow.started_at,
                )
                .where(AcceptanceRunRow.commit == commit, AcceptanceRunRow.status == COMPLETE)
                .order_by(AcceptanceRunRow.started_at.desc())
                .limit(1)
            )
        ).first()
        await connection.rollback()
    if found is None:
        return None
    return CompleteRun(found.run_id, found.commit, Occasion(found.occasion), found.started_at)


async def finish_if_whole(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    names: Sequence[str],
    *,
    read: Callable[[AsyncEngine, uuid.UUID], Awaitable[Sequence[Result]]] | None = None,
    close: Callable[[AsyncEngine, uuid.UUID], Awaitable[bool]] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Mark the run complete only if the store holds a result for every one of `names`.

    Returns whether it was marked (false also when somebody abandoned the run meanwhile) and the
    checks the store lacked, which are empty exactly when the run was whole. The store is read
    back rather than trusted to have been written, for
    `A_RUN_IS_COMPLETE_ONLY_WHEN_EVERY_REGISTERED_CHECK_RECORDED`. `read` and `close` default to
    the store's own `recorded` and `finish`, looked up when called, and are parameters so the
    decision is tested without a database.
    """
    lacking = remaining(names, await (read or recorded)(engine, run_id))
    if lacking:
        return False, lacking
    return await (close or finish)(engine, run_id), ()
