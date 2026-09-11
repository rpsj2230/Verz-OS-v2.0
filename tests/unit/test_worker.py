"""The worker: what it refuses to start with, how it lays its processes out, and its sizing.

Every test here is about a container that would come up, hold a connection, and report
itself healthy while draining nothing.

The queue-side tests for `Shard`, `worker_shards` and `driver_schema_gaps` are here rather
than in `tests/unit/test_queue.py` because those functions exist for this deployment: they
are the translation from a per-class allocation into processes, and the thing that consumes
them is `brain.ops.worker`. Keeping them beside their consumer also means this change touches
one fewer file that other work is in.

No task ids. `brain.ops.worker` and `docker-compose.worker.yml` claim none: the container has
never been started, because the process it runs has no queue driver to fetch with. M32.4.1.4
is served rather than closed, on the same grounds `docker-compose.langfuse.yml` refuses
M32.1.1.1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from brain.db import SCHEMAS
from brain.gate.context import TrafficClass
from brain.ops.checkpoints import connection_refusals
from brain.ops.connections import client_named
from brain.ops.queue import (
    CONCURRENCY,
    DRIVER_SCHEMA,
    FALLBACK_POLL_SECONDS,
    HEARTBEAT_SECONDS,
    MIB_PER_SLOT,
    QueueError,
    Shard,
    driver_schema_gaps,
    queue_name_for,
    queue_url_refusals,
    stale_after,
    worker_shards,
)
from brain.ops.wiring import component
from brain.ops.worker import (
    AN_UNDECLARED_POOL_IS_A_GUESS_AND_A_GUESS_UNDERSTATES,
    EXIT_MISCONFIGURED,
    EXIT_NO_DRIVER,
    EXIT_NOT_READY,
    POOL_MAX_ENV,
    advisories,
    declared_pool_max,
    declared_slots,
    is_ready,
    main,
    plan_for,
    pool_declaration_gaps,
    preflight,
    slot_env_name,
)

REPO = Path(__file__).resolve().parents[2]
COMPOSE = "docker-compose.worker.yml"

NOW = datetime(2026, 9, 6, 14, 0, tzinfo=UTC)


def _compose_service() -> dict[str, object]:
    """The worker service as compose would read it. Parsed, never grepped.

    A regex over the text finds `memory: 384M` inside a comment, which is precisely the state
    a half-finished edit leaves this file in.
    """
    raw = yaml.safe_load((REPO / COMPOSE).read_text(encoding="utf-8"))
    service: dict[str, object] = raw["services"]["brain-worker"]
    return service


def _worker_environment() -> dict[str, str]:
    """The service's environment with the deploy-time password substituted.

    Substituted rather than left as `${POSTGRES_PASSWORD}`, so the URLs below are the URLs
    the container actually gets and the refusal functions are asked the real question.
    """
    raw = _compose_service()["environment"]
    assert isinstance(raw, dict)
    return {key: str(value).replace("${POSTGRES_PASSWORD}", "pw") for key, value in raw.items()}


#: A finding of the kind `advisories` carries and `preflight` must not, put into the advisory
#: source by the tests that check where each list ends up.
#:
#: Arranged rather than live, and that is a change of shape rather than a weakening. Until
#: 2026-09-10 the advisory list was never empty, because the product shipped a corpus column
#: of one width and served a model of another, and three tests here read that live finding.
#: `0027` closed it, and a test whose subject is one install's misconfiguration is a test that
#: goes green or red on somebody else's decision. What each of them is really about is the
#: wiring: that `advisories` reports what `policy_gaps` finds, that `preflight` does not, and
#: that `main` prints it. All three survive the finding being supplied.
A_FINDING_THAT_STARTING_WILL_NOT_FIX = (
    "the served embedding model produces 8 dimensions and know.chunk.embedding holds 16"
)


def _sound_environment(**overrides: str) -> dict[str, str]:
    """An environment a worker would start on, before the override under test."""
    env = {
        "QUEUE_URL": "postgresql+psycopg://brain:pw@db:5432/brain",
        "DATABASE_URL": "postgresql+psycopg://brain:pw@pgbouncer:5432/brain",
        **{slot_env_name(t): str(v) for t, v in CONCURRENCY.items()},
    }
    env.update(overrides)
    return env


# --------------------------------------------------- what the worker refuses to start on
def test_a_worker_with_no_queue_url_refuses_to_start() -> None:
    """A worker with no connection of its own is a worker somebody is about to give
    `DATABASE_URL` to, which points it at the transaction pooler. Delete this and the
    absence is discovered by a queue that reports itself empty for a week."""
    findings = preflight(_sound_environment(QUEUE_URL=""))

    assert any("QUEUE_URL is not set" in f for f in findings)


def test_a_worker_handed_the_applications_own_connection_string_refuses_to_start() -> None:
    """The mistake that is easy to write and impossible to see, checked where it can actually
    stop a container. `queue_url_refusals` has existed and been tested since the queue was
    written, and nothing called it; this is its call site. Delete this and it goes back to
    being a mechanism nobody runs."""
    env = _sound_environment()
    findings = preflight(_sound_environment(QUEUE_URL=env["DATABASE_URL"]))

    assert any("application's own connection string" in f for f in findings)


def test_a_worker_whose_checkpointer_is_behind_the_pooler_refuses_to_start() -> None:
    """A different failure from the queue's and it needs its own check: the saver prepares
    statements server-side, and a pooler hands the next one to a backend that never saw the
    prepare. Delete this and only the queue half of the connection rule is enforced, on a
    process that holds both."""
    findings = preflight(
        _sound_environment(BRAIN_CHECKPOINTER_URL="postgresql+psycopg://brain:pw@pgbouncer:5432/x")
    )

    assert any("transaction pooler" in f for f in findings)


def test_a_worker_with_no_checkpointer_at_all_is_not_a_misconfiguration() -> None:
    """An install with no durable graph has no checkpointer, and refusing that would make
    every worker deployment carry a variable for a component that does not exist. A wrong
    checkpointer is a refusal; an absent one is not. Delete this and the two collapse, which
    blocks the only deployment shape currently possible."""
    assert preflight(_sound_environment()) == ()


def test_the_preflight_surfaces_a_queue_schema_gap_rather_than_swallowing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`driver_schema_gaps` reads a constant, so on today's value it has nothing to say and
    removing the call would change nothing observable. That is exactly the shape of a check
    somebody deletes as dead code, and the day it would have mattered is the day the constant
    moved. Patched to speak so the wiring can be seen rather than assumed.

    Delete this and the preflight can stop asking, with every other test here green."""
    monkeypatch.setattr("brain.ops.worker.driver_schema_gaps", lambda: ("the schema moved",))

    assert "the schema moved" in preflight(_sound_environment())


def test_a_deployment_that_cannot_embed_is_reported_and_still_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The distinction wiring one uncalled check forced into the open.** `policy_gaps` was
    written, argued and never called; its own docstring named `preflight` as where it belonged
    and said wiring it was one line. Wired there, it stopped the worker, because everything in
    `preflight` is fatal and this finding is not.

    A corpus column that disagrees with the served model's width means every embedding job
    fails at the insert and means nothing at all for the rest of the queue. Refusing to boot
    over it takes the whole queue down to protect one leg, and it replaces the operator's real
    diagnosis, "no queue driver is installed", with one they cannot act on.

    **This was asserted against a live disagreement until 2026-09-10 and now has to be
    arranged.** Item 34 was the finding: the product shipped a column of one width for a model
    of another, so `advisories()` was non-empty on every deployment and the assertion was
    `"1024 dimensions" in one`. `0027` closed that, and a test that reads the state of one
    install is a test that reports somebody else's decision. What is worth pinning is the
    wiring, so `policy_gaps` is replaced by one that finds something and the two lists are
    asked what they did with it. The test below is the other half of the same property, and
    the one after it is the case where nothing is wrong.

    Delete this and the check goes back to being uncalled, or worse, goes back into the
    refusals where it stops a worker that could run."""
    monkeypatch.setattr(
        "brain.ops.worker.policy_gaps", lambda: (A_FINDING_THAT_STARTING_WILL_NOT_FIX,)
    )

    assert advisories() == (A_FINDING_THAT_STARTING_WILL_NOT_FIX,)
    assert preflight(_sound_environment()) == ()


def test_an_advisory_is_never_a_reason_the_worker_will_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property that makes the split worth having rather than a second list of the same
    thing. `preflight` answers "must this refuse to start"; `advisories` answers "what is
    wrong that starting will not fix". A finding in both would make the second meaningless and
    the first wrong.

    Asserted by putting a finding into the advisory source and asking whether the refusals
    picked it up, rather than by intersecting two lists. The intersection was the shape while
    item 34 was open and the advisory list was never empty; with nothing wrong on a correctly
    configured install both lists are empty, and two empty sets are disjoint for no reason at
    all. What this asks instead is the real regression: somebody adding `policy_gaps()` to
    `preflight` because a check that matters ought to stop a container.

    Delete this and the next check added to `advisories` can be copied into `preflight` as
    well, which turns an advisory into an outage."""
    monkeypatch.setattr(
        "brain.ops.worker.policy_gaps", lambda: (A_FINDING_THAT_STARTING_WILL_NOT_FIX,)
    )

    assert A_FINDING_THAT_STARTING_WILL_NOT_FIX in advisories()
    assert A_FINDING_THAT_STARTING_WILL_NOT_FIX not in preflight(_sound_environment())


def test_an_install_whose_declared_width_is_its_models_has_nothing_to_report() -> None:
    """The positive sibling, and the one that pins what item 34 decided.

    Every other test on this surface arranges a finding, and a surface tested only that way is
    satisfied by one that reports on every install for ever, which is what an operator learns
    to scroll past. The width the product ships is now the width the model it serves produces,
    so a default install has nothing here at all.

    Delete this and the disagreement between the column and the served model can come back
    with no test noticing, because every other advisory test supplies its own finding."""
    assert advisories() == ()


def test_a_correctly_configured_worker_reports_nothing_to_fix() -> None:
    """The positive sibling of every refusal above. A preflight tested only by what it
    refuses is satisfied by one that refuses everything, and that worker never starts on any
    configuration while every refusal test stays green."""
    env = _sound_environment(BRAIN_CHECKPOINTER_URL="postgresql+psycopg://brain:pw@db:5432/brain")

    assert preflight(env) == ()


def test_a_slot_count_that_is_not_a_number_is_reported_rather_than_ignored() -> None:
    """A typo in one variable would otherwise leave that class out of the mapping entirely,
    which is reported as a class whose jobs are never fetched: the right alarm for the wrong
    reason, and it sends whoever reads it to the wrong file. Delete this and a mistyped slot
    count reads as a missing allocation."""
    findings = preflight(_sound_environment(BRAIN_WORKER_SLOTS_HUMAN_ASYNC="four"))

    assert any("is not a number of slots" in f for f in findings)


def test_a_negative_slot_count_is_refused() -> None:
    """Zero is how a class is declared undrained and it is a decision. A negative number is
    not a smaller version of that, it is a value nothing can act on, and it would make the
    memory arithmetic below understate the total. Delete this and a stray minus sign buys
    slots elsewhere."""
    findings = preflight(_sound_environment(BRAIN_WORKER_SLOTS_SYSTEM="-1"))

    assert any("negative" in f for f in findings)


def test_a_class_missing_from_the_environment_is_reported_as_never_fetched() -> None:
    """A class with no allocation presents as a queue that fills and never drains and takes a
    day to find. The environment is not defaulted back to `CONCURRENCY` when a variable is
    absent, deliberately: substituting the constant would make a deployment that forgot a
    class work here and fail on a version whose constant differs. Delete this and it does."""
    env = _sound_environment()
    del env[slot_env_name(TrafficClass.SYSTEM)]

    assert any("never fetched" in f for f in preflight(env))


def test_an_allocation_over_the_containers_memory_limit_refuses_to_start() -> None:
    """The second cap, doing the only thing it can do. CPython has no heap ceiling, so what
    bounds this container is the number of jobs it will run at once, checked before the first
    fetch. Delete this and a backlog is fixed by raising a slot count, which converts a queue
    depth problem into a neighbour's outage on a shared host."""
    findings = preflight(_sound_environment(BRAIN_WORKER_SLOTS_HUMAN_ASYNC="100"))

    assert any("over the" in f for f in findings), findings


# --------------------------------------------------- the connection bound
def test_a_worker_with_a_queue_driver_and_no_declared_pool_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The refusal `docs/needs-rupash.md` item 41 asks for, and the reason it is a refusal
    rather than a line in the log.** A worker's connections are spent out of a database's
    ceiling rather than out of its own cgroup limit, so an unbounded pool is not this
    container's problem: it is every client of that database, and the first one refused is
    whoever is trying to find out why. That is the 2026-09-07 outage.

    The finding cannot be produced by this repository as it stands, because no queue driver is
    importable, so the driver is patched present. That is the same technique
    `test_the_preflight_surfaces_a_queue_schema_gap_rather_than_swallowing_it` uses and for the
    same reason: a check whose condition is false today is a check that has never been shown to
    fire.

    Delete this and the variable can be dropped from a compose file in a tidy-up, and the day
    a driver is installed the container starts with a pool nobody sized against a budget that
    goes on reporting spare connections."""
    monkeypatch.setattr("brain.ops.worker.driver_is_installed", lambda: True)
    env = _sound_environment()
    assert POOL_MAX_ENV not in env

    findings = preflight(env)

    assert any(POOL_MAX_ENV in f and "is not set" in f for f in findings), findings
    assert any("guessed five and the driver opens twenty" in f for f in findings), findings


def test_a_worker_with_no_queue_driver_is_not_asked_for_a_pool_it_cannot_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate on the refusal above, and it is the half that keeps the check alive. Nothing
    here opens a queue connection today, so refusing every container that omits the variable
    would be a check that is red on arrival, which `brain.ops.sweeps` records at length as how
    a gate comes to be switched off. The day a driver becomes importable is the first day the
    number could be wrong, and it is the day this starts asking.

    Asserted with the driver patched absent as well as present, because the real environment
    has no driver and a test relying on that fact alone would pass for a check that never runs
    at all.

    Delete this and the refusal can be made unconditional, which stops every worker on every
    install that has not yet been told a number for a pool it does not open."""
    monkeypatch.setattr("brain.ops.worker.driver_is_installed", lambda: False)

    assert pool_declaration_gaps(_sound_environment(), worker_component="brain-worker") == ()

    monkeypatch.setattr("brain.ops.worker.driver_is_installed", lambda: True)
    assert pool_declaration_gaps(_sound_environment(), worker_component="brain-worker")


def test_a_declared_pool_that_disagrees_with_the_budget_refuses_to_start() -> None:
    """Two copies of one number, in a compose file and in `brain.ops.connections`, and this is
    what holds them equal from the container's end. The budget's copy is what every headroom
    figure on that database is computed from, so a container deployed with a larger one is a
    database whose spare capacity is a fiction by the difference.

    Asked with no driver installed, deliberately: an agreement between two numbers that both
    exist can be checked today, unlike the absence above, and gating it on the driver would
    leave the copies free to drift for as long as there is no driver.

    Delete this and `BRAIN_WORKER_POOL_MAX` can be raised on the container alone, which is the
    edit that looks like it fixes a backlog."""
    findings = preflight(_sound_environment(**{POOL_MAX_ENV: "40"}))

    assert any("describe different pools" in f for f in findings), findings
    declared = client_named("brain-worker")
    assert declared is not None
    assert any(str(declared.pool_max) in f for f in findings), findings


def test_a_pool_bound_that_is_not_a_number_is_reported_rather_than_ignored() -> None:
    """The same shape as a mistyped slot count, and it has to be its own finding: an unreadable
    value falls back to no declaration at all, so without this it would be reported as an
    absent variable and send whoever reads it to add a line that is already there.

    Delete this and a typo in the bound reads as a missing bound, or worse, as no finding at
    all on a host with no driver."""
    findings = preflight(_sound_environment(**{POOL_MAX_ENV: "fifteen"}))

    assert any("is not a number of connections" in f for f in findings), findings


def test_a_pool_bound_of_zero_is_refused_rather_than_read_as_no_limit() -> None:
    """Zero connections is not a smaller pool, it is a worker that cannot fetch anything, and
    `brain.ops.connections.Client` refuses the same value from the other side because an
    unbounded client runs at its server's ceiling for ever.

    Delete this and zero reads as "no limit configured", which is exactly the sentence that
    describes an unbounded pool."""
    findings = preflight(_sound_environment(**{POOL_MAX_ENV: "0"}))

    assert any("no connections at all" in f for f in findings), findings


def test_a_worker_declaring_the_bound_its_budget_gives_it_starts() -> None:
    """The positive sibling of the four refusals above, and it is the one that says the check
    can be satisfied at all. A preflight tested only by what it refuses is satisfied by one
    that refuses everything.

    Both worker components, because they are budgeted at different numbers and a check reading
    one of them for both would pass every test above.

    Delete this and the bound can become a value nothing accepts, which stops both containers
    on a host where the driver has just been installed."""
    for component_name in ("brain-worker", "brain-parse-worker"):
        declared = client_named(component_name)
        assert declared is not None
        env = _sound_environment(**{POOL_MAX_ENV: str(declared.pool_max)})

        assert pool_declaration_gaps(env, worker_component=component_name) == ()


def test_a_worker_component_the_budget_has_never_heard_of_is_left_alone() -> None:
    """A third worker container is a deployment decision this check has no basis to make, and
    refusing it would put a line nobody can act on into a list whose whole value is that every
    line names a fix. `preflight` has already refused a component `brain.ops.wiring` does not
    budget, which is the case worth refusing.

    Delete this and adding a worker container means editing the connection budget before the
    container can be started even once, which is how the budget becomes something people work
    around rather than with."""
    env = _sound_environment(**{POOL_MAX_ENV: "99"})

    assert client_named("brain-third-worker") is None
    assert pool_declaration_gaps(env, worker_component="brain-third-worker") == ()


def test_an_unreadable_bound_is_not_read_as_a_declaration() -> None:
    """The property that keeps the two findings apart. `declared_pool_max` returns None for an
    unreadable value, so a container with `BRAIN_WORKER_POOL_MAX=fifteen` has not declared
    fifteen and has not declared anything, and the agreement check must not compare against a
    number that was never read.

    Delete this and an unreadable value can be defaulted to the budget's figure, which makes an
    undeclared container look declared: the exact state
    `AN_UNDECLARED_POOL_IS_A_GUESS_AND_A_GUESS_UNDERSTATES` is about."""
    assert declared_pool_max({POOL_MAX_ENV: "fifteen"})[0] is None
    assert declared_pool_max({POOL_MAX_ENV: "  "})[0] is None
    assert declared_pool_max({})[0] is None
    assert declared_pool_max({POOL_MAX_ENV: " 15 "})[0] == 15
    assert "understates" in AN_UNDECLARED_POOL_IS_A_GUESS_AND_A_GUESS_UNDERSTATES


def test_the_deployed_workers_declare_the_bound_the_budget_gives_them() -> None:
    """The artefact rather than the rule: the general worker's compose file carries a bound and
    it is the budgeted one, so this deployment would start on a host where a driver has been
    installed.

    Asserted against `brain.ops.connections` rather than against the number, because the number
    written twice in two files is the thing that drifts.

    Delete this and the compose file can lose the variable, which is invisible until the day
    the driver arrives and every worker refuses at once."""
    declared = client_named("brain-worker")
    assert declared is not None
    assert int(_worker_environment()[POOL_MAX_ENV]) == declared.pool_max


# --------------------------------------------------- the process layout
def test_a_class_allocated_no_slots_gets_no_worker_process() -> None:
    """`HUMAN_INTERACTIVE` is zero on purpose, and the natural loop over the mapping produces
    a worker for it: a process that holds a database connection, drains a queue nothing is
    meant to enqueue onto, and reports itself up. Delete this and the zero becomes an idle
    worker rather than an absent one."""
    shards = worker_shards()

    assert TrafficClass.HUMAN_INTERACTIVE not in {shard.traffic_class for shard in shards}
    assert {shard.traffic_class for shard in shards} == {
        t for t, slots in CONCURRENCY.items() if slots > 0
    }


def test_a_shard_with_no_slots_cannot_be_constructed() -> None:
    """The guard behind the omission above. Delete this and `worker_shards` can be changed to
    emit every class, and the idle process comes back with nothing to report it."""
    with pytest.raises(QueueError, match="still holds a connection"):
        Shard(queue="system", traffic_class=TrafficClass.SYSTEM, concurrency=0)


def test_every_drained_class_gets_a_queue_named_after_it() -> None:
    """A queue name chosen per task would let a task author choose a priority, and the thing
    that decides priority here is whether a person is waiting, which the channel declared at
    ingress with no default. Delete this and a task can promote itself into the interactive
    share by being named well."""
    for shard in worker_shards():
        assert shard.queue == queue_name_for(shard.traffic_class)
        assert shard.queue == shard.traffic_class.value


def test_the_worker_processes_come_out_in_the_same_order_every_time() -> None:
    """Ordered by the enum rather than by the mapping handed in, so two runs of a deploy
    produce the same process list and a diff of the plan is a diff of the decision rather
    than of whatever order an environment happened to be read in.

    Asserted with a mapping built in a different order, because a mapping built in enum
    order agrees with both implementations and a test over it cannot tell them apart.
    Delete this and an unchanged deployment can read as a changed one."""
    scrambled = {
        TrafficClass.SYSTEM: 1,
        TrafficClass.AUTOMATION: 2,
        TrafficClass.HUMAN_ASYNC: 4,
    }

    assert [shard.traffic_class for shard in worker_shards(scrambled)] == [
        TrafficClass.HUMAN_ASYNC,
        TrafficClass.AUTOMATION,
        TrafficClass.SYSTEM,
    ]


def test_the_slot_total_is_the_sum_of_the_shards_and_not_of_the_mapping() -> None:
    """The two differ by whatever the undrained classes were allocated, and the number that
    matters for memory is the one that has processes behind it. Delete this and the plan can
    report a budget for slots that no worker holds."""
    plan = plan_for(CONCURRENCY)

    assert plan.slots == sum(shard.concurrency for shard in plan.shards)
    assert plan.slot_memory_mib == plan.slots * MIB_PER_SLOT
    assert plan.memory_mib == component("brain-worker").memory_mib


def test_the_plan_reports_the_latency_a_lost_notification_costs() -> None:
    """The fallback poll interval is the queue's entire latency once notifications stop being
    delivered, and behind a transaction pooler that day has no error in it. Printing it at
    start means the number is already in the log during the incident rather than being looked
    up while it is happening.

    Delete this and the constant goes back to being a value in a source file that nothing
    reads, which is how it gets raised to a minute as a tidy default."""
    described = plan_for(CONCURRENCY).describe()

    assert f"{FALLBACK_POLL_SECONDS}s" in described
    assert DRIVER_SCHEMA in described


def test_a_worker_never_reports_itself_alive_more_often_than_it_looks_for_work() -> None:
    """The fallback poll interval is what the queue's latency degrades to when notifications
    stop being delivered, which behind a transaction pooler happens with no error at all. A
    poll slower than the heartbeat means the worker writes "I am alive" several times between
    looks at the queue, so a monitor reads a healthy fleet while jobs sit: which is exactly
    the failure this module is about, arrived at from the inside.

    **Added because a mutation raising the interval to a tidy minute survived every other
    test here.** The value itself is a judgement and no test can pin it without restating the
    source; its relation to the heartbeat is not a judgement, and that is what this asserts.

    Delete this and the interval can be raised to whatever makes an idle worker quiet."""
    assert 0 < FALLBACK_POLL_SECONDS <= HEARTBEAT_SECONDS


def test_the_queue_schema_is_one_the_row_level_security_sweep_enumerates() -> None:
    """`brain.ops.sweeps.sweep_rls` reads `brain.db.SCHEMAS` and looks nowhere else. The
    driver installs its own tables with no row-level security on them, so the schema is the
    difference between a red sweep somebody acts on and nothing at all.

    Delete this and `DRIVER_SCHEMA` can be set to a name that reads sensibly and is not
    enumerated, which is the same outcome as leaving it at the driver's default."""
    assert DRIVER_SCHEMA in SCHEMAS
    assert driver_schema_gaps() == ()


def test_a_queue_schema_nobody_declared_is_reported() -> None:
    """The check has to fail when it should. Delete this and `driver_schema_gaps` could
    return an empty tuple unconditionally and the test above would still be green."""
    assert any("sweep_rls" in gap for gap in driver_schema_gaps("public"))


def test_a_queue_with_no_schema_at_all_is_reported_separately() -> None:
    """An empty schema is not an unknown one: the tables land wherever `search_path` points,
    which on a fresh connection is `public`, so the message has to say that rather than
    listing the schemas that exist. Delete this and an unset value is reported as a typo."""
    gaps = driver_schema_gaps("  ")

    assert len(gaps) == 1
    assert "search_path" in gaps[0]


# --------------------------------------------------- readiness
def test_a_container_that_has_never_written_a_heartbeat_is_not_ready(tmp_path: Path) -> None:
    """Which is the true answer today: nothing writes the heartbeat, because there is no
    driver to fetch with. A readiness check that passed anyway would put a container that
    drains nothing into rotation. Delete this and a missing file reads as a fresh one."""
    assert is_ready(tmp_path / "absent", now=NOW) is False


def test_a_fresh_heartbeat_is_ready(tmp_path: Path) -> None:
    """The positive sibling. A readiness check that never passes is a container that is never
    in rotation, and the failure looks identical to the worker being broken. Delete this and
    `is_ready` could return False unconditionally."""
    beat = tmp_path / "heartbeat"
    beat.write_text("", encoding="utf-8")

    assert is_ready(beat, now=datetime.now(tz=UTC)) is True


def test_readiness_uses_the_same_staleness_as_the_re_drive_sweep(tmp_path: Path) -> None:
    """Two thresholds for one condition produce the two states that are both wrong: a
    container reporting ready while the recovery sweep re-drives its jobs, or one taken out
    of rotation while it still holds work nothing will reclaim.

    Asserted by moving the clock rather than by comparing two constants, because a constant
    comparison passes whether or not `is_ready` reads it. Delete this and readiness grows a
    timeout of its own that looks tidier and disagrees."""
    beat = tmp_path / "heartbeat"
    beat.write_text("", encoding="utf-8")
    now = datetime.now(tz=UTC)

    assert is_ready(beat, now=now + stale_after() - timedelta(seconds=1)) is True
    assert is_ready(beat, now=now + stale_after() + timedelta(seconds=5)) is False


# --------------------------------------------------- the process refuses out loud
def test_a_misconfigured_worker_exits_with_a_configuration_code_and_not_with_one() -> None:
    """Exit 1 means everything, so it means nothing. The two ways this process refuses need
    different people: 78 says an operator wrote something wrong, 69 says the build is missing
    a dependency. Delete this and both become 1, and whoever is paged reads the log to find
    out which."""
    assert main([], env=_sound_environment(QUEUE_URL="")) == EXIT_MISCONFIGURED


def test_a_correctly_configured_worker_still_refuses_because_it_has_no_driver() -> None:
    """The honest behaviour, and the reason this leaf is not claimed. A worker that started
    against no driver would poll a queue that does not exist and report itself healthy, and
    an empty queue is indistinguishable from an absent one in every metric there is.

    Delete this and starting anyway becomes a small change with no test against it."""
    assert main([], env=_sound_environment()) == EXIT_NO_DRIVER


def test_the_check_mode_reports_a_sound_configuration_as_sound() -> None:
    """`--check` is an operator asking whether a deployment would start, and it has to be
    able to answer yes on a machine with no driver installed. Delete this and the only way to
    validate a worker's environment is to try to run it, which on this host means editing a
    compose file to find out."""
    assert main(["--check"], env=_sound_environment()) == 0


def test_the_check_mode_prints_an_advisory_rather_than_swallowing_it(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An advisory that is computed and not shown is the state this whole surface was created
    out of: `policy_gaps` was correct, argued and silent for as long as nothing called it, and
    a check nobody sees is indistinguishable from one that was never written.

    stderr rather than stdout, and after the refusals, so it sits in the container log beside
    the plan without changing what a script reading stdout gets.

    The finding is supplied for the reason `A_FINDING_THAT_STARTING_WILL_NOT_FIX` gives: this
    test is about the printing and not about which install is misconfigured, and it read a
    live disagreement only because there was one to read.

    Delete this and `advisories()` can be called and its result dropped, which passes every
    other test here because the exit code does not move."""
    monkeypatch.setattr(
        "brain.ops.worker.policy_gaps", lambda: (A_FINDING_THAT_STARTING_WILL_NOT_FIX,)
    )

    main(["--check"], env=_sound_environment())

    assert A_FINDING_THAT_STARTING_WILL_NOT_FIX in capsys.readouterr().err


def test_the_three_exit_codes_are_three_different_numbers() -> None:
    """The property the codes exist for. Delete this and two of them can be given the same
    value in a tidy-up, which is invisible until an alert routes to the wrong person."""
    assert len({EXIT_MISCONFIGURED, EXIT_NO_DRIVER, EXIT_NOT_READY, 0}) == 4


def test_the_readiness_mode_answers_without_looking_at_the_queue_configuration() -> None:
    """A healthcheck that ran the preflight would report a misconfigured container as
    unhealthy, which is true and useless: it restarts for ever instead of exiting once with
    the reason. Delete this and readiness and configuration are answered by one command, and
    the container loops instead of failing."""
    assert main(["--ready"], env={"BRAIN_WORKER_HEARTBEAT": str(REPO / "absent")}) == EXIT_NOT_READY


# --------------------------------------------------- the deployment
def test_the_worker_container_carries_an_explicit_memory_limit() -> None:
    """The rule the whole of `brain.ops.wiring` exists for. This host runs a second production
    system belonging to the same owner, and an unlimited container is not a sizing mistake on
    a box like that, it is somebody else's outage. Delete this and the limit can be dropped in
    an edit that looks like it removes clutter."""
    limits = _compose_service()["deploy"]

    assert isinstance(limits, dict)
    assert limits["resources"]["limits"]["memory"] == "384M"


def test_the_worker_container_is_sized_as_the_component_it_is_budgeted_as() -> None:
    """The budget is arithmetic over `COMPONENTS` and the compose file is what actually runs.
    Two copies of one number is only safe while something compares them.

    Delete this and the container can be given whatever makes it start while
    `budget_breaches` keeps reporting the old figure."""
    limits = _compose_service()["deploy"]
    assert isinstance(limits, dict)
    declared = component("brain-worker").memory_mib

    assert limits["resources"]["limits"]["memory"] == f"{declared}M"


def test_the_workers_slot_budget_sits_strictly_below_its_cgroup_limit() -> None:
    """The second cap, and the mistake that makes it useless is the tempting one: raise the
    slots until they exactly fill the container so nothing is wasted.

    `MIB_PER_SLOT` counts a job's working set. The cgroup counts that plus the interpreter,
    the imports and the connection pool, so a worker allowed exactly its container's limit
    will exceed it and be killed while believing it is within budget.

    Delete this and the gap gets closed one slot at a time, each edit looking like reclaimed
    waste."""
    limits = _compose_service()["deploy"]
    assert isinstance(limits, dict)
    cgroup = int(str(limits["resources"]["limits"]["memory"]).rstrip("M"))

    assert plan_for(_declared_from_compose()).slot_memory_mib < cgroup


def _declared_from_compose() -> dict[TrafficClass, int]:
    allocation, problems = declared_slots(_worker_environment())
    assert problems == (), problems
    return dict(allocation)


def test_the_compose_file_declares_the_same_allocation_the_queue_decided() -> None:
    """`brain.ops.queue.CONCURRENCY` is where these numbers are argued and the container is
    configured by its environment, so there are two copies and something has to hold them
    equal. Delete this and the deployed allocation drifts from the one every test in
    `test_queue.py` reasons about."""
    assert _declared_from_compose() == dict(CONCURRENCY)


def test_the_compose_file_names_every_traffic_class_including_the_undrained_one() -> None:
    """An omitted class is reported as one whose jobs are never fetched, and a class
    deliberately allocated zero is a decision. The two must not look alike in a file somebody
    reads during an incident. Delete this and adding a traffic class silently strands its
    jobs on the deployed worker."""
    env = _worker_environment()

    assert all(slot_env_name(traffic_class) in env for traffic_class in TrafficClass)
    assert env[slot_env_name(TrafficClass.HUMAN_INTERACTIVE)] == "0"


def test_the_deployed_environment_satisfies_the_preflight_it_will_be_checked_by() -> None:
    """The strongest thing this file asserts: the deployment as written would start. Every
    other test here checks a rule; this one checks the artefact against all of them at once,
    which is the check that catches a rule and a file drifting apart in opposite directions.

    Delete this and the compose file can be edited into a state the worker refuses, which is
    discovered by deploying it."""
    assert preflight(_worker_environment()) == ()


def test_the_worker_is_not_pointed_at_the_pooler_by_its_own_compose_file() -> None:
    """Asserted in both directions, because the first half passes for a file whose refusal
    function does nothing. The queue URL goes straight to the database; the application's URL
    does not, and feeding it to the same check has to produce a refusal.

    Delete this and the two URLs can be made identical, which is one line and is the failure
    with no error message."""
    env = _worker_environment()

    assert queue_url_refusals(env["QUEUE_URL"], app_url=env["DATABASE_URL"]) == ()
    assert connection_refusals(env["BRAIN_CHECKPOINTER_URL"], app_url=env["DATABASE_URL"]) == ()
    assert queue_url_refusals(env["DATABASE_URL"], app_url=env["DATABASE_URL"])


def test_the_worker_runs_only_in_the_profiles_that_budget_it() -> None:
    """`brain.ops.wiring` puts `brain-worker` in `standard` and `full`, and lite is what is
    deployed today. Compose profiles are how that becomes true of the deployment rather than
    of a document. Delete this and the service can acquire a third profile, or lose the key
    entirely, which starts a worker on every install that composes this file."""
    service = _compose_service()
    profiles = service["profiles"]

    assert isinstance(profiles, list)
    assert set(profiles) == set(component("brain-worker").profiles)


def test_the_container_runs_the_module_that_refuses_rather_than_a_shell() -> None:
    """The image has no shell for its user, and the command is the preflight. A command that
    was anything else would start a process that has not been checked, on a host where the
    check is the only thing between a worker and the application's own connection string.
    Delete this and the command can become something that skips it."""
    assert _compose_service()["command"] == ["python", "-m", "brain.ops.worker"]


def test_the_healthcheck_asks_for_readiness_rather_than_liveness() -> None:
    """Liveness is free: the process is up. A worker that is up and draining nothing is the
    state this whole file is about, and a TCP or process check passes for it. Delete this and
    the healthcheck becomes something that always passes."""
    healthcheck = _compose_service()["healthcheck"]

    assert isinstance(healthcheck, dict)
    assert healthcheck["test"] == ["CMD", "python", "-m", "brain.ops.worker", "--ready"]
