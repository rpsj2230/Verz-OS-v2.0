"""A control run carried through the queue: registered, enqueued, fetched, run and recorded.

The unit half is every refusal at the door and the rule that whether a control may act is
decided when it runs. The last test is the leaf: a real knowledge re-verification enqueued on a
scratch PostgreSQL, fetched by the queue driver's own worker, run through the same lock and
record as a scheduled run, and seen in both the queue's row and the control's.

Task ids: M17.1.2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.gate.context import TrafficClass
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops import worker
from brain.ops.queue import (
    Job,
    QueueError,
    Redrive,
    enqueue_job,
    install_queue,
    queue_app,
    queue_name_for,
    register_task,
    tasks_of_ours,
)
from brain.ops.schedule import DESTRUCTIVE
from brain.ops.schedule_runner import RUNNERS, RunnerError
from brain.ops.worker import (
    CONTROL_TASK,
    ControlRunError,
    ControlTick,
    Ticked,
    control_job,
    enqueue_control,
    register_tasks,
    run_control_job,
)
from tests.fixtures.scratch_postgres import run

DIRECT = "postgresql://brain@db:5432/brain"


def an_app() -> Any:
    app = queue_app(DIRECT, pool_max=5)
    register_tasks(app, database_url=DIRECT)
    return app


# ------------------------------------------------------------------ without a server
def test_a_control_job_carries_the_controls_name_and_nothing_that_decides_whether_it_may_act() -> (
    None
):
    """The job row is readable and writable by whoever can reach the queue's tables, so it holds
    the name and no report-only flag. Delete this and a flag can be added to the arguments, and a
    row edited in psql becomes a way to switch a retention sweep from reporting to deleting."""
    job = control_job("retention_sweep")

    assert job.task == CONTROL_TASK
    assert job.args == {"name": "retention_sweep"}
    assert job.traffic_class is TrafficClass.SYSTEM
    assert job.redrive is Redrive.UNSAFE


def test_a_control_nobody_can_run_is_refused_at_the_door() -> None:
    """An unknown name and a known control with nothing wired are both refused before anything is
    enqueued. Delete this and either becomes a job that fails later where nobody asked."""
    unwired = next(one.name for one in RUNNERS if one.run is None)

    with pytest.raises(RunnerError):
        control_job("no_such_control")
    with pytest.raises(RunnerError, match="nothing to run"):
        control_job(unwired)


def test_the_control_task_is_ours_and_is_registered_on_the_queue_its_class_derives() -> None:
    """Delete this and the task can be registered under the driver's own prefix, where
    `tasks_of_ours` hides it, or on a queue the parse worker drains."""
    app = an_app()

    assert tasks_of_ours(app.tasks) == (CONTROL_TASK,)
    assert app.tasks[CONTROL_TASK].queue == queue_name_for(TrafficClass.SYSTEM)


def test_a_task_registered_twice_or_under_the_drivers_own_prefix_is_refused() -> None:
    """The driver lets a second registration replace the first, silently. Delete this and a
    second `register_tasks` call can swap the control run for anything with the same name."""

    async def nothing() -> None:
        return None

    app = an_app()
    with pytest.raises(QueueError, match="already registered"):
        register_task(app, CONTROL_TASK, nothing, traffic_class=TrafficClass.SYSTEM)
    with pytest.raises(QueueError, match="not a name"):
        register_task(app, "procrastinate.mine", nothing, traffic_class=TrafficClass.SYSTEM)


def test_a_job_for_a_task_nobody_registered_is_refused_before_anything_is_written() -> None:
    """The driver defers an unknown task name without complaint and the job then fails where no
    one is looking. The app here was never opened, so a refusal is the only way this returns.

    Delete this and `enqueue_job` can defer any name."""
    with pytest.raises(QueueError, match="no task of ours"):
        run(
            lambda: enqueue_job(
                an_app(), Job(task="brain.nothing", traffic_class=TrafficClass.SYSTEM)
            )
        )


def test_a_job_whose_class_derives_another_queue_than_its_registration_is_refused() -> None:
    """See `A_TASK_RUNS_ON_THE_QUEUE_ITS_CLASS_DERIVES`. Delete this and a job can be deferred
    onto a queue a container not sized for it drains."""
    misrouted = Job(task=CONTROL_TASK, traffic_class=TrafficClass.AUTOMATION, args={"name": "x"})

    with pytest.raises(QueueError, match="registered on"):
        run(lambda: enqueue_job(an_app(), misrouted))


def test_whether_a_queued_control_may_act_is_decided_when_it_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A destructive control runs report-only and any other acts, decided from `brain.ops.schedule`
    at the moment the job runs. Asserted against `DESTRUCTIVE` as a set outside the worker, so the
    rule and the answer cannot move together.

    Delete this and the report-only decision can be dropped or inverted on the queue's path while
    the schedule's path stays right."""
    started: dict[str, bool] = {}

    async def fake(_sessions: Any, name: str, **kwargs: Any) -> ControlTick:
        started[name] = kwargs["report_only"]
        return ControlTick(name, Ticked.REFUSED if kwargs["report_only"] else Ticked.RAN)

    monkeypatch.setattr(worker, "start_owed", fake)
    run(lambda: run_control_job("retention_sweep", database_url=DIRECT))
    run(lambda: run_control_job("knowledge_reverification", database_url=DIRECT))

    assert started == {
        "retention_sweep": "retention_sweep" in DESTRUCTIVE,
        "knowledge_reverification": "knowledge_reverification" in DESTRUCTIVE,
    }
    assert started["retention_sweep"] is True
    assert started["knowledge_reverification"] is False


def test_a_queued_control_whose_runner_raised_fails_its_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control's row already says failed; the queue's must say so too, or the queue reports a
    success for a sweep that broke.

    Delete this and the task can return the failure as a sentence."""

    async def failed(_sessions: Any, name: str, **_: Any) -> ControlTick:
        return ControlTick(name, Ticked.FAILED, "RuntimeError: broke")

    monkeypatch.setattr(worker, "start_owed", failed)

    with pytest.raises(ControlRunError, match="broke"):
        run(lambda: run_control_job("knowledge_reverification", database_url=DIRECT))


# ------------------------------------------------------------------------ with a server
@pytest.mark.needs_db
def test_a_control_enqueued_on_the_queue_is_fetched_run_and_recorded_by_a_worker() -> None:
    """**The leaf.** A knowledge re-verification is enqueued through `enqueue_control` onto a
    queue installed by `install_queue`, fetched by the driver's own worker, and run through
    `start_owed` against the real store: the queue's row says succeeded, `ops.control_run` holds
    one row recording it as ok, and the owner's nag is in the outbox.

    Delete this and every other test of the queue could pass with no job ever having been
    enqueued, fetched or run, which is the state the queue was in until this task existed."""
    from tests.fixtures.knowledge_items import a_person, a_reader, knowledge_items, nags, put
    from tests.fixtures.scratch_postgres import sql

    lapsed = datetime.now(tz=UTC) - timedelta(days=1)
    item = KnowledgeItem(
        item_id="kb.renewals",
        content="What the document says.",
        title="Renewal pricing",
        visibility=KnowledgeVisibility.of_department("web", owner_id="u_owner"),
        owner_id="u_owner",
    ).verified(by="u_verifier", at=lapsed - timedelta(days=365), review_by=lapsed)

    with knowledge_items("brain_ctask_queue") as url:
        a_person(url, "u_owner")
        a_reader(url, "u_owner", "web")
        put(url, item)
        install_queue(url, pool_max=5)

        async def enqueued_and_worked() -> int:
            app = queue_app(url, pool_max=3)
            register_tasks(app, database_url=url)
            job_id = await enqueue_control(app, "knowledge_reverification")
            async with app.open_async():
                await app.run_worker_async(
                    queues=[queue_name_for(TrafficClass.SYSTEM)],
                    wait=False,
                    install_signal_handlers=False,
                )
            return job_id

        job_id = run(enqueued_and_worked)
        status = sql(url, "SELECT status::text FROM ops.procrastinate_jobs WHERE id = %s", job_id)
        runs = sql(url, "SELECT name, outcome, report_only FROM ops.control_run")
        recorded_nags = nags(url)

    assert status == [("succeeded",)]
    assert runs == [("knowledge_reverification", "ok", False)]
    assert [nag[0] for nag in recorded_nags] == ["kb.renewals"]


# ----------------------------------------------------------------- the worker's two doors
def _started_worker(
    monkeypatch: pytest.MonkeyPatch, *, component: str, slot_class: Any, database_url: str
) -> Any:
    """Start `worker.run` with the loop stood in, and answer with the queue app it built."""
    from brain.ops.connections import client_named
    from brain.ops.queue import CONCURRENCY
    from brain.ops.worker import POOL_MAX_ENV, slot_env_name

    budgeted = client_named(component)
    assert budgeted is not None
    env = {
        "QUEUE_URL": "postgresql+psycopg://brain:pw@db:5432/brain",
        POOL_MAX_ENV: str(budgeted.pool_max),
        **{slot_env_name(t): str(v) for t, v in CONCURRENCY.items()},
    }
    if database_url:
        env["DATABASE_URL"] = database_url
    built: dict[str, Any] = {}

    async def serve(app: Any, *_: Any, **__: Any) -> None:
        built["app"] = app

    monkeypatch.setattr(worker, "serve", serve)
    assert worker.run(env, worker_component=component, slot_class=slot_class) == 0
    return built["app"]


def test_the_general_worker_registers_the_control_run_and_the_parse_worker_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control run reads the application's tables, which only the general worker has a
    connection to and memory for. Delete this and either the general worker starts with nothing
    registered, so every enqueued control fails as an unknown task, or the parse worker registers
    one it cannot run."""
    from brain.knowledge.parse_budget import PARSE_WORKER_COMPONENT
    from brain.ops.queue import SlotClass
    from brain.ops.worker import DEFAULT_WORKER_COMPONENT

    general = _started_worker(
        monkeypatch,
        component=DEFAULT_WORKER_COMPONENT,
        slot_class=SlotClass.STANDARD,
        database_url="postgresql+psycopg://brain:pw@pgbouncer:5432/brain",
    )
    parse = _started_worker(
        monkeypatch,
        component=PARSE_WORKER_COMPONENT,
        slot_class=SlotClass.WHOLE_CONTAINER,
        database_url="",
    )

    assert tasks_of_ours(general.tasks) == (CONTROL_TASK,)
    assert tasks_of_ours(parse.tasks) == ()


def test_a_control_is_not_enqueued_from_a_worker_that_cannot_run_one() -> None:
    """Delete this and the parse worker can put a control on a queue whose task it never
    registered, which is a job nothing in that container could describe."""
    from brain.knowledge.parse_budget import PARSE_WORKER_COMPONENT
    from brain.ops.worker import EXIT_MISCONFIGURED, run_control_text

    code, text = run_control_text(
        {"DATABASE_URL": "postgresql+psycopg://brain:pw@pgbouncer:5432/brain"},
        "knowledge_reverification",
        worker_component=PARSE_WORKER_COMPONENT,
    )

    assert code == EXIT_MISCONFIGURED
    assert "general worker" in text


def test_the_checkpointer_is_not_installed_without_a_checkpointer_url() -> None:
    """Delete this and the mode goes on to build a configuration from an empty string, which is
    refused for a different reason in words that do not name the variable to set."""
    from brain.ops.worker import CHECKPOINTER_URL_ENV, EXIT_MISCONFIGURED, install_checkpointer_text

    code, text = install_checkpointer_text({})

    assert code == EXIT_MISCONFIGURED
    assert f"{CHECKPOINTER_URL_ENV} is not set" in text
