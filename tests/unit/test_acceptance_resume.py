"""A run of the acceptance checks survives the restart a deploy causes, and the sweep reads only
complete runs.

The decision (`settle`, `remaining`) is pure and tested without a database. The run is tested as
the worker makes it: a check that raises a `BaseException` stands for the process being killed
(`run_one` catches only `Exception`, so nothing after it runs, as after a SIGKILL), and a second
`run_acceptance` stands for the restarted worker. Every instant here is the database's own clock
moved by SQL, never a date in a fixture.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.ops import acceptance_resume, acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, Occasion, Result
from brain.ops.acceptance_resume import (
    ABANDONED,
    COMPLETE,
    RUNNING,
    STALE_AFTER,
    Unfinished,
    remaining,
    settle,
)
from brain.settings import settings_from

# A real-looking abbreviation: hexadecimal, so a run of it may be resumed.
OLD, NEW = "aaaaaaa", "bbbbbbb"
LEAF = "M38.5.1"


def unfinished(
    commit: str,
    *,
    silent: timedelta,
    hours: int = 0,
    run_id: uuid.UUID | None = None,
) -> Unfinished:
    return Unfinished(
        run_id=run_id or uuid.uuid4(),
        commit=commit,
        occasion=Occasion.DEPLOY,
        started_at=datetime(2999, 1, 1, hours, tzinfo=UTC),
        silent_for=silent,
    )


LONG = STALE_AFTER + timedelta(minutes=1)
SHORT = timedelta(seconds=5)


# ---------------------------------------------------------------------------- the decision
def test_the_constant_that_calls_a_worker_dead_is_longer_than_a_check_may_take() -> None:
    """A worker is called dead after `STALE_AFTER` of silence, and the heartbeat moves only between
    checks, so the figure has to be longer than the longest a check may run. Delete this and
    shortening one without the other lets a live worker's run be taken over mid-check, which runs
    the check twice and records it twice."""
    assert timedelta(seconds=acceptance_run.CHECK_TIMEOUT_SECONDS) < STALE_AFTER
    assert STALE_AFTER <= acceptance_run.RUN_EVERY * 2


def test_a_silent_run_of_the_commit_served_is_resumed() -> None:
    """The positive case: a run of this release whose worker has gone is the one to finish. Delete
    this and a guard that refuses to resume anything passes every refusal test below."""
    one = unfinished(OLD, silent=LONG)
    done = settle(OLD, [one])
    assert done.resume == one
    assert done.abandon == ()
    assert done.in_progress is False


def test_a_silent_run_of_another_commit_is_abandoned_and_never_resumed() -> None:
    """A_RUN_OF_ANOTHER_RELEASE_IS_ABANDONED_AND_NEVER_COMPLETED. Delete this and a worker that
    serves a new release finishes the old one's run, and the two releases' results share one run."""
    one = unfinished(OLD, silent=LONG)
    done = settle(NEW, [one])
    assert done.resume is None
    assert done.abandon == (one.run_id,)


def test_a_run_whose_worker_is_still_beating_is_left_alone_and_blocks_a_second() -> None:
    """A fresh heartbeat is a live worker's run: not taken over, not abandoned, and for the commit
    served nothing is started beside it. Delete this and two workers run one commit at once."""
    mine = unfinished(OLD, silent=SHORT)
    theirs = unfinished(NEW, silent=SHORT)
    done = settle(OLD, [mine, theirs])
    assert done == acceptance_resume.Settlement(None, (), True)
    assert settle(NEW, [theirs]).in_progress is True
    other = settle(OLD, [theirs])
    assert (other.resume, other.abandon, other.in_progress) == (None, (), False)


def test_of_several_silent_runs_of_one_commit_the_newest_is_resumed_and_the_rest_abandoned() -> (
    None
):
    """Delete this and two workers' leftovers are both resumed, or the older one is."""
    older = unfinished(OLD, silent=LONG, hours=1)
    newer = unfinished(OLD, silent=LONG, hours=2)
    done = settle(OLD, [older, newer])
    assert done.resume == newer
    assert done.abandon == (older.run_id,)


@pytest.mark.parametrize("word", ["unknown", "wip", "", "ABCDEF1", "abc"])
def test_a_commit_that_names_no_build_is_never_resumed(word: str) -> None:
    """`unknown` and `wip` are what a process with no manifest says, and two builds can both say
    so. Delete this and a run is finished by a different build than began it."""
    one = unfinished(word, silent=LONG)
    done = settle(word, [one])
    assert done.resume is None
    assert done.abandon == (one.run_id,)


def test_the_checks_to_run_are_those_without_a_result_in_suite_order_once_each() -> None:
    """Delete this and a resumed run repeats a recorded check, or runs one twice."""
    at = datetime(2999, 1, 1, tzinfo=UTC)
    done = [Result("check_b", (LEAF,), PASSED, at), Result("check_d", (LEAF,), FAILED, at, "no")]
    assert remaining(["check_a", "check_b", "check_c", "check_d", "check_c"], done) == (
        "check_a",
        "check_c",
    )
    assert remaining(["check_a"], []) == ("check_a",)
    assert remaining(["check_b"], done) == ()


# ---------------------------------------------------------------- the suite, without a database
def named(name: str) -> Check:
    async def body(_: Any) -> None:
        return None

    return Check(name, (LEAF,), "A check made for this test.", body)


def test_a_check_with_a_result_is_not_run_again_and_its_outcome_reaches_the_ones_after() -> None:
    """`prior` is what a resumed run recorded before it was cut short: run_suite skips those, calls
    `before` and `after` only for the rest, hands the roll-up the earlier outcomes, and returns the
    whole run with the earlier results first. Delete this and a resumed run double-counts."""
    seen: list[str] = []
    heard: list[str] = []
    earlier: dict[str, Any] = {}

    async def not_in_use(*_: Any, **__: Any) -> bool:
        return False

    async def one(_: Any, check: Check, **kwargs: Any) -> tuple[str, str]:
        seen.append(check.name)
        earlier[check.name] = dict(kwargs["earlier"])
        return PASSED, ""

    async def before(check: Check) -> None:
        heard.append(f"before {check.name}")

    async def after(result: Result) -> None:
        heard.append(f"after {result.name}")

    at = datetime(2999, 1, 1, tzinfo=UTC)
    prior = [Result("one", (LEAF,), FAILED, at, "it broke")]
    patch = pytest.MonkeyPatch()
    patch.setattr(acceptance_run, "in_use", not_in_use)
    patch.setattr(acceptance_run, "run_one", one)
    try:
        results = asyncio.run(
            acceptance_run.run_suite(
                None,  # type: ignore[arg-type]
                [named("one"), named("two"), named("three")],
                settings=settings_from({}),
                stream=None,  # type: ignore[arg-type]
                prior=prior,
                before=before,
                after=after,
            )
        )
    finally:
        patch.undo()

    assert seen == ["two", "three"]
    assert heard == ["before two", "after two", "before three", "after three"]
    assert [one.name for one in results] == ["one", "two", "three"]
    assert earlier["two"] == {"one": (FAILED, "it broke")}
    assert earlier["three"] == {"one": (FAILED, "it broke"), "two": (PASSED, "")}


# -------------------------------------------------------------------------- against PostgreSQL
class Killed(BaseException):
    """The worker being killed in the middle of a check: nothing after it runs."""


TABLES = ["ops.acceptance_result", "ops.acceptance_run", "ops.setting"]


@contextmanager
def database(name: str) -> Iterator[str]:
    from tests.fixtures.scratch_postgres import database_url, modelled

    if database_url() is None:
        pytest.skip("DATABASE_URL is unset; CI sets it")
    with modelled(name, TABLES) as url:
        yield url


def suite(
    names: list[str],
    calls: Counter[str],
    *,
    kill: str | None = None,
    seen: dict[str, Any] | None = None,
) -> list[Check]:
    """Checks that count their own runs, and one that kills the process when it is reached."""
    checks = []
    for name in names:

        async def body(harness: Any, name: str = name) -> None:
            calls[name] += 1
            if seen is not None:
                seen[name] = dict(harness.earlier)
            if name == kill:
                raise Killed

        checks.append(Check(name, (LEAF,), "A check made for this test.", body))
    return checks


def run(
    url: str,
    checks: list[Check],
    *,
    commit: str = OLD,
    force: bool = False,
    in_use: bool = False,
) -> tuple[Occasion | None, tuple[Result, ...]]:
    from brain.db import normalise_database_url

    async def stub(*_: Any, **__: Any) -> bool:
        return in_use

    patch = pytest.MonkeyPatch()
    patch.setattr(acceptance_run, "in_use", stub)
    try:
        return asyncio.run(
            acceptance_run.run_acceptance(
                normalise_database_url(url),
                settings=settings_from({}),
                commit=commit,
                checks=checks,
                force=force,
            )
        )
    finally:
        patch.undo()


def killed_run(url: str, commit: str = OLD) -> Counter[str]:
    """A run cut off at its third check of four, as a restart cuts one off."""
    calls: Counter[str] = Counter()
    with pytest.raises(Killed):
        run(
            url,
            suite(["check_a", "check_b", "check_c", "check_d"], calls, kill="check_c"),
            commit=commit,
        )
    return calls


def rows(url: str, commit: str | None = None) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    where = "" if commit is None else f" WHERE commit = '{commit}'"
    return sql(
        url,
        "SELECT run_id, commit, check_name, outcome, started_at FROM ops.acceptance_result"  # noqa: S608
        f"{where} ORDER BY checked_at, check_name",
    )


def runs(url: str) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(
        url,
        "SELECT run_id, commit, status, occasion, ended_at IS NULL FROM ops.acceptance_run"
        " ORDER BY started_at",
    )


def silence(url: str, minutes: int = 60) -> None:
    """The killed worker's last word was `minutes` ago, on the database's clock."""
    from tests.fixtures.scratch_postgres import sql

    sql(
        url,
        "UPDATE ops.acceptance_run"
        " SET heartbeat_at = statement_timestamp() - make_interval(mins => %s)",
        minutes,
    )


@pytest.mark.needs_db
def test_a_killed_run_leaves_what_ran_and_a_run_that_is_not_complete() -> None:
    """A_CHECK_IS_RECORDED_WHEN_IT_FINISHES. The worker dies at the third check: the first two have
    rows under the run's id, the third and fourth have none, and the run is still `running`. Delete
    this and rows are written only at the end again, so a restart leaves no record at all."""
    with database("brain_resume_killed") as url:
        calls = killed_run(url)
        recorded = rows(url)
        record = runs(url)

    assert calls == Counter({"check_a": 1, "check_b": 1, "check_c": 1})
    assert [(one[2], one[3]) for one in recorded] == [("check_a", PASSED), ("check_b", PASSED)]
    assert len({one[0] for one in recorded}) == 1
    assert [(one[1], one[2], one[3]) for one in record] == [(OLD, RUNNING, "deploy")]
    assert record[0][0] == recorded[0][0]


@pytest.mark.needs_db
def test_a_restarted_worker_finishes_the_run_of_its_own_release_and_runs_only_the_rest() -> None:
    """A_RESTARTED_WORKER_FINISHES_THE_RUN_OF_ITS_OWN_RELEASE, and a resumed run is one run. After
    the kill the new worker runs only `c` and `d`, under the first run's id and start, and leaves
    four rows (one per check, none twice) with the run marked complete. Delete this and a restart
    either starts over, so a run never finishes, or runs everything again and records it twice."""
    with database("brain_resume_finished") as url:
        killed_run(url)
        silence(url)
        calls: Counter[str] = Counter()
        seen: dict[str, Any] = {}
        occasion, results = run(
            url, suite(["check_a", "check_b", "check_c", "check_d"], calls, seen=seen)
        )
        recorded = rows(url)
        record = runs(url)

    assert occasion == Occasion.DEPLOY
    assert calls == Counter({"check_c": 1, "check_d": 1})
    assert [one.name for one in results] == ["check_a", "check_b", "check_c", "check_d"]
    assert sorted(one[2] for one in recorded) == ["check_a", "check_b", "check_c", "check_d"]
    assert len({one[0] for one in recorded}) == 1
    assert len({one[4] for one in recorded}) == 1
    assert [(one[2]) for one in record] == [COMPLETE]
    assert record[0][4] is False
    assert seen["check_c"] == {"check_a": (PASSED, ""), "check_b": (PASSED, "")}


@pytest.mark.needs_db
def test_a_run_whose_worker_is_still_beating_is_not_resumed_or_duplicated() -> None:
    """The kill leaves a fresh heartbeat, as a restart a second after it would find: the new worker
    starts nothing, because the run may be somebody's. Delete this and a deploy storm runs one
    commit in several workers at once."""
    with database("brain_resume_alive") as url:
        killed_run(url)
        calls: Counter[str] = Counter()
        occasion, results = run(url, suite(["check_a", "check_b", "check_c", "check_d"], calls))
        recorded = rows(url)
        record = runs(url)

    assert (occasion, results) == (None, ())
    assert not calls
    assert len(recorded) == 2
    assert [one[2] for one in record] == [RUNNING]


@pytest.mark.needs_db
def test_an_unfinished_run_of_another_release_is_abandoned_and_a_fresh_run_starts() -> None:
    """A_RUN_OF_ANOTHER_RELEASE_IS_ABANDONED_AND_NEVER_COMPLETED. A run of `OLD` is cut off, the
    worker restarts on `NEW`: the old run is marked abandoned with its two rows left as they were,
    and `NEW` gets its own complete run of four, none of its rows under the old id. Delete this and
    the new release is checked on the old one's results, or the old run is left running for ever."""
    with database("brain_resume_abandoned") as url:
        killed_run(url, OLD)
        silence(url)
        calls: Counter[str] = Counter()
        run(url, suite(["check_a", "check_b", "check_c", "check_d"], calls), commit=NEW)
        old, new = rows(url, OLD), rows(url, NEW)
        record = runs(url)

    assert calls == Counter({"check_a": 1, "check_b": 1, "check_c": 1, "check_d": 1})
    assert [(one[1], one[2]) for one in record] == [(OLD, ABANDONED), (NEW, COMPLETE)]
    assert len(old) == 2 and len(new) == 4
    assert {one[0] for one in old}.isdisjoint({one[0] for one in new})


@pytest.mark.needs_db
def test_a_commit_with_only_a_partial_run_is_still_owed_a_run_and_a_complete_one_is_not() -> None:
    """ONLY_A_COMPLETE_RUN_COUNTS on the owed question. With a half-written run of the commit the
    schedule still owes it a run (so the resume happens), and once it is complete nothing is owed.
    Delete this and the half-written run counts as the commit having been checked, and it is never
    finished."""
    from brain.db import normalise_database_url
    from brain.session import make_app_engine

    async def owed(url: str, commit: str) -> Occasion | None:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await acceptance_run.occasion_now(engine, serving=commit)
        finally:
            await engine.dispose()

    with database("brain_resume_owed") as url:
        before = asyncio.run(owed(url, OLD))
        killed_run(url)
        partial = asyncio.run(owed(url, OLD))
        silence(url)
        run(url, suite(["check_a", "check_b", "check_c", "check_d"], Counter()))
        complete = asyncio.run(owed(url, OLD))

    assert (before, partial, complete) == (Occasion.DEPLOY, Occasion.DEPLOY, None)


@pytest.mark.needs_db
def test_a_run_forced_from_a_shell_starts_afresh_and_leaves_a_silent_run_for_the_schedule() -> None:
    """A person running the checks by hand wants a whole run now, so it takes nothing over. The
    silent run stays `running` for the next tick. Delete this and `python -m
    brain.ops.acceptance_run` quietly finishes a stale run and reports only part of the suite."""
    with database("brain_resume_forced") as url:
        killed_run(url)
        silence(url)
        calls: Counter[str] = Counter()
        occasion, results = run(
            url, suite(["check_a", "check_b", "check_c", "check_d"], calls), force=True
        )
        record = runs(url)

    assert occasion == Occasion.REQUEST
    assert calls == Counter({"check_a": 1, "check_b": 1, "check_c": 1, "check_d": 1})
    assert len(results) == 4
    assert sorted(one[2] for one in record) == [COMPLETE, RUNNING]


@pytest.mark.needs_db
def test_a_run_stopped_by_a_reserved_department_in_use_is_recorded_not_run_and_complete() -> None:
    """The run that may not start still records every check, as not run, and is complete: that is
    the verdict the Install page shows. Delete this and the early return skips the recording, so
    the page reads as though nothing was ever tried."""
    with database("brain_resume_in_use") as url:
        occasion, results = run(url, suite(["check_a", "check_b"], Counter()), in_use=True)
        recorded = rows(url)
        record = runs(url)

    assert occasion == Occasion.DEPLOY
    assert {one.outcome for one in results} == {NOT_RUN}
    assert sorted((one[2], one[3]) for one in recorded) == [
        ("check_a", NOT_RUN),
        ("check_b", NOT_RUN),
    ]
    assert [one[2] for one in record] == [COMPLETE]


@pytest.mark.needs_db
def test_an_unbroken_run_is_recorded_whole_and_marked_complete() -> None:
    """The ordinary day: no restart, and the result is as it was, one complete run of every check.
    Delete this and the new recording is only ever tested through a kill, so a run that is never
    marked complete passes."""
    with database("brain_resume_whole") as url:
        calls: Counter[str] = Counter()
        occasion, results = run(url, suite(["check_a", "check_b", "check_c"], calls))
        second = run(url, suite(["check_a", "check_b", "check_c"], calls))
        recorded = rows(url)
        record = runs(url)

    assert occasion == Occasion.DEPLOY
    assert [one.outcome for one in results] == [PASSED] * 3
    assert second == (None, ())
    assert len(recorded) == 3
    assert [(one[2], one[4]) for one in record] == [(COMPLETE, False)]


# ----------------------------------------------------------------------- the migration at head
@pytest.mark.needs_db
def test_the_application_role_may_move_a_running_run_on_and_nothing_else() -> None:
    """The grants and policies of `0231` as the application role meets them: a running run can be
    moved on and finished; a finished one cannot be edited or deleted; no other column can be
    written. Delete this and the table can be relaxed to editable history without a test noticing,
    which is the one thing `ops.acceptance_result`'s rule forbids."""
    import psycopg

    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url, database_url, sql

    admin_url()
    own = (database_url() or "").rsplit("/", 1)[-1].removeprefix("brain_test_")
    with retirable(f"brain_resume_policy_{own}"[:63]) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to 0231 needs pgvector, which CI has")
        for status, ended in ((RUNNING, "NULL"), (COMPLETE, "statement_timestamp()")):
            sql(
                url,
                "INSERT INTO ops.acceptance_run (run_id, commit, occasion, status, started_at,"  # noqa: S608
                f" ended_at) VALUES (gen_random_uuid(), 'abc1234', 'deploy', '{status}',"
                f" statement_timestamp(), {ended})",
            )
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET ROLE brain_app")
            seen = conn.execute("SELECT count(*) FROM ops.acceptance_run").fetchone()
            moved = conn.execute(
                "UPDATE ops.acceptance_run SET heartbeat_at = statement_timestamp()"
            ).rowcount
            frozen = conn.execute(
                "UPDATE ops.acceptance_run SET status = 'abandoned',"
                " ended_at = statement_timestamp() WHERE status = 'complete'"
            ).rowcount
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("UPDATE ops.acceptance_run SET commit = 'ffffff0'")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("DELETE FROM ops.acceptance_run")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO ops.acceptance_run (run_id, commit, occasion, status, started_at)"
                    " VALUES (gen_random_uuid(), 'abc1234', 'deploy', 'complete',"
                    " statement_timestamp())"
                )
        secured = sql(
            url,
            "SELECT relrowsecurity FROM pg_class WHERE oid = 'ops.acceptance_run'::regclass",
        )

    assert seen == (2,)
    assert moved == 1
    assert frozen == 0
    assert secured == [(True,)]
