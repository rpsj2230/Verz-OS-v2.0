"""A job set aside for a person is kept where the console reads it, and shown to who may see it.

The pure half holds the reason the sweep gives each job it sets aside and who is shown a row. The
database half runs the driver's own tables and `0228`'s table together, as the worker's schedule
sweeps and writes: the jobs set aside are recorded with the reason the sweep had, the failed jobs
nobody will run again are recorded with theirs, a job still being re-driven is not, and a second
sweep over the same jobs writes nothing.

Task ids: M17.1.5, M17.1.1
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.jobs_routes import dead_letters_shown
from brain.knowledge.embed_queue import EMBED_TASK
from brain.knowledge.ingest_queue import INGEST_TASK
from brain.ops.jobs import DEAD_LETTER_CAPABILITY, DeadLetter, DeadLetterReason
from brain.ops.queue import MAX_REDRIVES, Verdict, queue_app
from brain.ops.recovery_run import REDRIVE_BY_TASK, dead_letter_reason, sweep_queue
from brain.ops.worker import CONTROL_TASK
from tests.unit.test_acceptance import at_head
from tests.unit.test_recovery_run import Queue, a_job

#: A clock nobody's wall clock will reach, so nothing here goes off on a date. See CLAUDE.md.
NOW = datetime(2999, 1, 1, 12, tzinfo=UTC)


def a_dead_letter(job_id: str, *, who: str = "system", task: str = CONTROL_TASK) -> DeadLetter:
    return DeadLetter(
        job_id=job_id,
        task=task,
        principal_id=who,
        traffic_class=TrafficClass.SYSTEM,
        reason=DeadLetterReason.QUARANTINED_AFTER_A_STOP,
        attempts=1,
        at=NOW,
    )


def test_every_verdict_that_sets_a_job_aside_has_a_reason_that_sends_a_person_somewhere() -> None:
    """A job re-driven too often is that, and any other job set aside was left by a stopped worker
    and is not safe to run twice. Delete this and the screen says every set-aside job failed on its
    own terms, which sends a person to read a task that did nothing wrong."""
    assert dead_letter_reason(Verdict.DEAD_LETTER) == DeadLetterReason.RE_DRIVEN_TOO_OFTEN.value
    assert dead_letter_reason(Verdict.QUARANTINE) == DeadLetterReason.QUARANTINED_AFTER_A_STOP.value


def test_the_sweep_names_the_reason_of_each_job_it_sets_aside_and_of_no_other() -> None:
    """Delete this and the writer is handed no reason, or a reason for a job that was put back."""
    from tests.unit.test_recovery_run import swept

    queue = Queue(
        running=(
            a_job("11", CONTROL_TASK),
            a_job("12", EMBED_TASK),
            a_job("13", EMBED_TASK, redrives=MAX_REDRIVES),
        )
    )
    sweep = swept(queue)

    assert sweep.reasons == {
        "11": DeadLetterReason.QUARANTINED_AFTER_A_STOP.value,
        "13": DeadLetterReason.RE_DRIVEN_TOO_OFTEN.value,
    }
    assert set(sweep.reasons) == set(sweep.set_aside)


def test_a_job_is_shown_to_its_owner_and_to_a_covering_grant_and_to_nobody_else() -> None:
    """Three readers over three rows: the owner sees only their own, a holder of the capability
    sees what its scope matches, and a stranger sees nothing and nothing says so. Delete this and a
    reader is shown another person's failed work, or the list answers a stranger differently from
    an install with none."""
    mine, theirs, system = (
        a_dead_letter("1", who="u_me"),
        a_dead_letter("2", who="u_them"),
        a_dead_letter("3"),
    )
    owner = EntitlementSet(principal_id="u_me", grants=())
    holder = EntitlementSet(
        principal_id="u_lead",
        grants=(Grant(capability=DEAD_LETTER_CAPABILITY, scope=Scope.unrestricted()),),
    )
    stranger = EntitlementSet(
        principal_id="u_x",
        grants=(Grant(capability=Capability(value="read:question"), scope=Scope.unrestricted()),),
    )
    entries = [mine, theirs, system]

    assert [one.job_id for one in dead_letters_shown(entries, owner, NOW)] == ["1"]
    assert [one.job_id for one in dead_letters_shown(entries, holder, NOW)] == ["1", "2", "3"]
    assert dead_letters_shown(entries, stranger, NOW) == []
    assert dead_letters_shown([], stranger, NOW) == dead_letters_shown(entries, stranger, NOW)


@pytest.mark.needs_db
def test_the_sweep_writes_what_it_set_aside_and_what_failed_for_good_and_writes_it_once() -> None:
    """**The leaf against the driver's own tables and `0228`'s.** A database at head with the queue
    installed, holding an orphan of an unsafe task, an orphan at the re-drive cap, a failed job of
    an unsafe task, a failed safe job still under the cap and a live job. Swept and written as the
    worker's schedule does: three rows with their reasons, none for the job being re-driven or the
    live one, and a second sweep adds nothing.

    Delete this and the SQL that reads the driver's row could name a column the driver does not
    have, or write a second row for a job it has already recorded."""
    import psycopg

    from brain.ops.queue import DriverQueue, install_queue
    from tests.fixtures.scratch_postgres import run, sql

    with at_head("brain_dead_letter") as url:
        install_queue(url, pool_max=5)
        with psycopg.connect(url, autocommit=True, options="-c search_path=ops") as conn:

            def one(statement: str, *params: object) -> int:
                row = conn.execute(statement, params or None).fetchone()
                assert row is not None
                return int(row[0])

            dead = one(
                "INSERT INTO procrastinate_workers (last_heartbeat) "
                "VALUES (now() - interval '10 minutes') RETURNING id"
            )
            live = one("INSERT INTO procrastinate_workers DEFAULT VALUES RETURNING id")

            def job(task: str, *, failed: bool, worker: int, queue: str = "system") -> int:
                made = one(
                    "INSERT INTO procrastinate_jobs (queue_name, task_name, args) "
                    "VALUES (%s, %s, '{}') RETURNING id",
                    queue,
                    task,
                )
                conn.execute(
                    "UPDATE procrastinate_jobs SET status = 'doing', worker_id = %s WHERE id = %s",
                    (worker, made),
                )
                if failed:
                    conn.execute(
                        "UPDATE procrastinate_jobs SET status = 'failed' WHERE id = %s", (made,)
                    )
                return made

            orphan_unsafe = job(CONTROL_TASK, failed=False, worker=dead)
            running = job(EMBED_TASK, failed=False, worker=live)
            failed_safe = job(INGEST_TASK, failed=True, worker=live)
            failed_unsafe = job(CONTROL_TASK, failed=True, worker=live, queue="automation.large")
            capped = job(INGEST_TASK, failed=True, worker=live)
            for _ in range(MAX_REDRIVES):
                conn.execute(
                    "INSERT INTO procrastinate_events (job_id, type) VALUES (%s, 'retried')",
                    (capped,),
                )

        async def sweep_and_keep() -> None:
            app = queue_app(url, pool_max=2)
            async with app.open_async():
                queue = DriverQueue(app, REDRIVE_BY_TASK)
                swept = await sweep_queue(queue, now=datetime.now(tz=UTC))
                for job_id, reason in swept.reasons.items():
                    await queue.keep_aside(job_id, reason, datetime.now(tz=UTC))
                await queue.keep_failed(datetime.now(tz=UTC))

        def kept() -> dict[str, tuple[str, str]]:
            rows: list[Any] = sql(
                url, "SELECT job_id, reason, traffic_class FROM ops.dead_letter ORDER BY job_id"
            )
            return {str(r[0]): (str(r[1]), str(r[2])) for r in rows}

        run(sweep_and_keep)
        first = kept()
        run(sweep_and_keep)
        second = kept()

    assert first == {
        str(orphan_unsafe): ("quarantined_after_a_stop", "system"),
        str(failed_unsafe): ("attempts_exhausted", "automation"),
        str(capped): ("re_driven_too_often", "system"),
    }
    assert str(running) not in first and str(failed_safe) not in first
    assert second == first


def test_a_reason_the_table_admits_is_a_reason_the_screen_can_say() -> None:
    """The migration's reason list is `DeadLetterReason`'s, on the day it ran. Delete this and a
    reason added to the enum is refused by the table the first time a job has it."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0228_dead_letter.py"
    spec = importlib.util.spec_from_file_location("dead_letter_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.REASONS) == {one.value for one in DeadLetterReason}
    assert set(module.TRAFFIC_CLASSES) == {one.value for one in TrafficClass}


@pytest.mark.needs_db
def test_a_persons_ask_puts_one_job_back_through_the_drivers_retry_and_is_answered_once() -> None:
    """**The control against the driver's own tables and `ops.setting`.** A database at head with
    the queue installed, holding two failed jobs of a task nobody declared safe to run twice and a
    live one. A person asks for one failed job and for the live one; the worker's minute puts the
    failed one back on its queue with the arguments it already had, refuses the live one in an
    answer rather than a run, writes both answers under the worker's name, and a second minute
    over the same rows does nothing.

    Delete this and the SQL that reads the asks could name a column `ops.setting` does not have,
    the driver's retry could be asked for a job it refuses, or the answer's row could be written
    in a shape the screen cannot read back."""
    import json

    import psycopg

    from brain.ops.queue import install_queue
    from brain.ops.recovery_run import run_queue_redrive_now
    from brain.ops.redrive_control import ANSWERED_NAMESPACE, ASKED_NAMESPACE
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_redrive") as url:
        install_queue(url, pool_max=5)
        with psycopg.connect(url, autocommit=True, options="-c search_path=ops") as conn:

            def one(statement: str, *params: object) -> int:
                row = conn.execute(statement, params or None).fetchone()
                assert row is not None
                return int(row[0])

            worker = one("INSERT INTO procrastinate_workers DEFAULT VALUES RETURNING id")

            def job(status: str) -> int:
                made = one(
                    "INSERT INTO procrastinate_jobs (queue_name, task_name, args) "
                    "VALUES ('system', %s, '{\"keep\": 1}') RETURNING id",
                    CONTROL_TASK,
                )
                conn.execute(
                    "UPDATE procrastinate_jobs SET status = 'doing', worker_id = %s WHERE id = %s",
                    (worker, made),
                )
                if status == "failed":
                    conn.execute(
                        "UPDATE procrastinate_jobs SET status = 'failed' WHERE id = %s", (made,)
                    )
                return made

            failed = job("failed")
            also_failed = job("failed")
            live = job("doing")

        def ask(job_id: int, at: datetime) -> None:
            sql(
                url,
                "INSERT INTO ops.setting (key, value_type, value, description, updated_by) "
                "VALUES (%s, 'string', to_jsonb(%s::text), 'when asked', 'u_admin')",
                f"{ASKED_NAMESPACE}.job_{job_id}",
                at.isoformat(),
            )

        ask(failed, datetime.now(tz=UTC) - timedelta(minutes=1))
        ask(live, datetime.now(tz=UTC) - timedelta(minutes=1))

        def minute() -> tuple[tuple[str, ...], tuple[str, ...]]:
            # The worker's own entry point, so the sweep's decisions are made first and the asks
            # carried out after them, as the schedule runs it.
            swept = run_queue_redrive_now(url, now=datetime.now(tz=UTC))
            return swept.asked.put_back, swept.asked.could_not

        first = minute()
        statuses = {
            str(r[0]): (str(r[1]), r[2])
            for r in sql(url, "SELECT id, status, args FROM ops.procrastinate_jobs ORDER BY id")
        }
        answers = {
            str(r[0]): r[1]
            for r in sql(
                url,
                "SELECT key, value FROM ops.setting WHERE starts_with(key, %s) ORDER BY key",
                f"{ANSWERED_NAMESPACE}.",
            )
        }
        written_by = sql(
            url,
            "SELECT DISTINCT updated_by FROM ops.setting WHERE starts_with(key, %s)",
            f"{ANSWERED_NAMESPACE}.",
        )
        second = minute()

    assert first == ((str(failed),), (str(live),))
    assert second == ((), ())
    assert statuses[str(failed)][0] == "todo"
    assert statuses[str(failed)][1] == {"keep": 1}
    assert statuses[str(also_failed)][0] == "failed"
    assert statuses[str(live)][0] == "doing"
    assert {key.rsplit(".", 1)[1]: bool(value["put_back"]) for key, value in answers.items()} == {
        f"job_{failed}": True,
        f"job_{live}": False,
    }
    assert all(json.dumps(value) for value in answers.values())
    assert written_by == [("system",)]
