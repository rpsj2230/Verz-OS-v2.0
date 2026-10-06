"""The pools per workload class: the URL each process moves to, when it moves, and what is started.

What a real PgBouncer would prove cannot run here: neither CI nor the development machine has one.
So each half is held where it can be. The URL derivation, the rule for when a process moves, and
the configuration the pooler reads (parsed, and every figure held against the file it must agree
with) are units. The compose file is parsed. The preparation runs for real against a stub docker.
The install check runs on a real PostgreSQL, where a login with a connection limit of the batch
share stands in for the batch pool, which is the one property of the pooler the check relies on:
a client past the share does not get a server connection.

**What only an install proves**, and the install check asks: that PgBouncer starts on this
configuration, that the application and the worker reach it by name over the database's network,
and that its batch entry really holds three server connections while its interactive entry hands
out another.

Task ids: M22.2.2
"""

from __future__ import annotations

import asyncio
import configparser
import os
import secrets
import shutil
import stat
import subprocess
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy.engine import make_url

from brain.gate.context import TrafficClass
from brain.ops import acceptance_checks_class_pools as pools_check
from brain.ops import class_pools, worker
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.ops.admission import WorkloadClass
from brain.ops.class_pools import (
    CLASS_DATABASE,
    CLASS_POOLER,
    POOLER_SLOTS,
    POOLS,
    ClassPoolError,
    Follower,
    Routing,
    class_url_of,
    keep_following,
    owner_login_lines,
    queued_class,
    render_ini,
    routed_url,
    runs_here,
)
from brain.ops.overlays import (
    BY_NAME,
    OVERLAYS,
    Host,
    OverlayError,
    Seen,
    observation,
    plan,
    planned,
    switched_on,
)
from brain.ops.schedule_runner import RUNNERS, Runner, RunnerError
from brain.ops.wiring import component
from brain.session import make_app_engine, make_session_factory
from brain.settings import settings_from

REPO = Path(__file__).resolve().parents[2]
STEP = REPO / "ops" / "deploy" / "overlays"
SH = shutil.which("sh")
CLASS_OVERLAY = next(one for one in OVERLAYS if one.name == "class-pools")

THROUGH_THE_POOLER = (
    "postgresql+psycopg://brain_app:p%40ss%3Aw0rd@pgbouncer:5432/brain?sslmode=disable"
)


def _compose(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8"))
    return loaded


def _first_pooler() -> dict[str, Any]:
    service: dict[str, Any] = _compose("docker-compose.yml")["services"]["pgbouncer"]
    return service


def _seen(**body: str) -> dict[str, object]:
    """A report with the class pooler as `body` says, running and healthy by default."""
    entry = {
        "limit_mib": component(CLASS_POOLER).memory_mib,
        "state": "running",
        "health": "healthy",
    }
    entry.update(body)
    return {"commit": "this-release", "services": {CLASS_POOLER: entry}}


# ------------------------------------------------------------------- the URL a class uses
def test_a_url_through_the_transaction_pooler_moves_to_its_class_keeping_the_login() -> None:
    """The host becomes the class pooler and the database its class's entry; the driver, the
    login, a password with characters that need encoding, and the query are kept. Delete this and
    a moved process can lose its password's encoding or its TLS mode and fail only on an install."""
    for workload in WorkloadClass:
        moved = make_url(class_url_of(THROUGH_THE_POOLER, workload) or "")
        assert (moved.host, moved.port, moved.database) == (
            CLASS_POOLER,
            5432,
            f"brain_{workload.value}",
        )
        assert (moved.drivername, moved.username, moved.password) == (
            "postgresql+psycopg",
            "brain_app",
            "p@ss:w0rd",
        )
        assert dict(moved.query) == {"sslmode": "disable"}
    assert len(set(CLASS_DATABASE.values())) == len(WorkloadClass)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://brain:pw@pgbouncer-session:5432/brain",
        "postgresql+psycopg://brain:pw@db:5432/brain",
        "postgresql://brain:pw@localhost:5432/brain_test",
        "",
        "not a url at all",
    ],
    ids=["session-pooler", "direct", "development", "empty", "unparseable"],
)
def test_a_connection_that_needs_session_state_or_goes_round_the_pooler_never_moves(
    url: str,
) -> None:
    """`ONLY_A_CONNECTION_THROUGH_THE_TRANSACTION_POOLER_MOVES`: the queue's LISTEN and the
    checkpointer's prepared statements stay on the session pooler, and a direct URL stays direct,
    even while the class pooler runs. Delete this and a LISTEN can be moved onto a transaction
    pool, where it stops being delivered with no error anywhere."""
    assert class_url_of(url, WorkloadClass.BATCH) is None
    assert routed_url(url, WorkloadClass.BATCH, running=True) == url


def test_a_process_moves_only_while_this_release_reports_the_class_pooler_running() -> None:
    """`A_PROCESS_USES_ITS_CLASS_POOLER_ONLY_WHEN_THIS_RELEASE_SAW_IT_RUNNING`, both directions.
    No report, another release's report, and the pooler absent, stopped or unhealthy all leave a
    process where it was; this release's report of it running and healthy moves it. Delete this
    and a process can depend on a pooler that a server had no room for."""
    commit = "this-release"
    for refused in (
        None,
        {**_seen(), "commit": "an-older-release"},
        {"commit": commit, "services": {}},
        _seen(state="exited"),
        _seen(health="unhealthy"),
        _seen(health="starting"),
        "a value of the wrong shape",
    ):
        assert runs_here(refused, commit=commit) is False, refused
    assert runs_here(_seen(), commit=commit) is True

    assert routed_url(THROUGH_THE_POOLER, WorkloadClass.INTERACTIVE, running=False) == (
        THROUGH_THE_POOLER
    )
    assert make_url(
        routed_url(THROUGH_THE_POOLER, WorkloadClass.INTERACTIVE, running=True)
    ).host == (CLASS_POOLER)


def test_a_queued_job_is_never_classed_onto_the_request_paths_pool() -> None:
    """`A_QUEUED_JOB_IS_TASK_LANE_WORK`, held over every traffic class, and the two queued tasks
    the worker runs land in batch. Delete this and a queued embedding run could be classed
    interactive and hold the connections a person's question is waiting for."""
    from brain.knowledge.embed_queue import EMBED_TRAFFIC_CLASS
    from brain.knowledge.ingest_queue import INGEST_TRAFFIC_CLASS

    assert all(queued_class(one) is not WorkloadClass.INTERACTIVE for one in TrafficClass)
    assert queued_class(EMBED_TRAFFIC_CLASS) is WorkloadClass.BATCH
    assert queued_class(INGEST_TRAFFIC_CLASS) is WorkloadClass.BATCH


def test_every_scheduled_control_is_classed_and_none_is_interactive() -> None:
    """`A_CONTROL_IS_CLASSED_BY_WHAT_IT_IS`: syncs, sweeps and reports are batch, automations and
    checks background, and nothing a control does takes the request path's pool. Delete this and
    the connector sync can be moved onto the interactive pool by a one-word edit."""
    wired = {one.name: one.workload for one in RUNNERS if one.run is not None}
    assert wired and all(value is not None for value in wired.values())
    assert WorkloadClass.INTERACTIVE not in set(wired.values())
    for name in ("connector_sync", "directory_sync", "retention_sweep", "spend_report_refresh"):
        assert wired[name] is WorkloadClass.BATCH, name
    for name in ("automation_run", "acceptance_run", "outbox_dispatch"):
        assert wired[name] is WorkloadClass.BACKGROUND, name


def test_a_control_that_runs_and_names_no_class_is_refused() -> None:
    """A default would put the next sweep somebody writes on whichever pool it named. The positive
    sibling is the table above, every entry of which constructs. Delete this and a control can be
    wired with no class and run on the URL it was given for ever."""
    with pytest.raises(RunnerError, match="names no workload class"):
        Runner(name="sweep", run=lambda _now, _report_only, _url: "done")
    assert Runner(name="sweep", run=lambda *_: "done", workload=WorkloadClass.BATCH).workload


class _Session:
    """Stands in for a session and its transaction: both are async context managers."""

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Session:
        return self


@pytest.mark.parametrize("running", [True, False], ids=["running", "not-running"])
def test_a_scheduled_run_is_handed_its_class_s_url_only_while_the_pooler_runs(
    monkeypatch: pytest.MonkeyPatch, running: bool
) -> None:
    """The lock and the record stay on the schedule's sessions; the run itself is handed the batch
    URL for a sync and the background URL for an automation while the pooler runs, and the URL it
    was given otherwise. Delete this and the schedule can run every control on its own URL with
    every pool built and nothing moved."""
    from datetime import UTC, datetime

    handed: dict[str, str] = {}

    async def lock(_session: object, _name: str) -> bool:
        return True

    async def start(_session: object, _name: str, **_: object) -> int:
        return 1

    async def finish(*_: object, **__: object) -> None:
        return None

    def ran(name: str, _report_only: bool, _now: datetime, url: str) -> str:
        handed[name] = url
        return "done"

    monkeypatch.setattr(worker, "take_the_lock", lock)
    monkeypatch.setattr(worker, "record_start", start)
    monkeypatch.setattr(worker, "record_finish", finish)
    monkeypatch.setattr(worker, "_start", ran)
    at = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
    for name in ("connector_sync", "automation_run"):
        asyncio.run(
            worker.start_owed(
                _Session,  # type: ignore[arg-type]
                name,
                report_only=False,
                now=at,
                database_url=THROUGH_THE_POOLER,
                clock=lambda: at,
                running=running,
            )
        )
    if not running:
        assert handed == dict.fromkeys(handed, THROUGH_THE_POOLER)
        return
    assert make_url(handed["connector_sync"]).database == "brain_batch"
    assert make_url(handed["automation_run"]).database == "brain_background"


# ----------------------------------------------------------------- following the observation
def test_the_sessions_move_to_the_class_pool_when_it_runs_and_home_when_it_stops() -> None:
    """The factory every caller holds is reconfigured in place, once per change, and handed back
    to its own engine when the pooler stops being reported or the loop ends. Delete this and a
    process can stay on a pooler that stopped, or never move at all."""
    home = make_app_engine(THROUGH_THE_POOLER)
    sessions = make_session_factory(home)
    follower = Follower(sessions, url=THROUGH_THE_POOLER, workload=WorkloadClass.INTERACTIVE)

    async def walk() -> list[tuple[bool, str]]:
        seen = []
        for running in (False, True, True, False):
            moved = await follower.follow(running)
            bound = sessions.kw["bind"]
            seen.append((moved, f"{bound.url.host}/{bound.url.database}"))
        await home.dispose()
        return seen

    assert asyncio.run(walk()) == [
        (False, "pgbouncer/brain"),
        (True, f"{CLASS_POOLER}/brain_interactive"),
        (True, f"{CLASS_POOLER}/brain_interactive"),
        (False, "pgbouncer/brain"),
    ]


def test_following_reads_at_once_and_goes_home_when_it_is_stopped() -> None:
    """A process restarted on a release whose pooler runs moves before its first minute, and the
    loop leaves the factory on its own engine however it ends. Delete this and a restarted
    application waits a minute on the old pooler, or shuts down bound to a disposed engine."""
    home = make_app_engine(THROUGH_THE_POOLER)
    sessions = make_session_factory(home)
    bound: list[str] = []

    async def reader(_sessions: object, *, commit: str) -> bool:
        assert commit == "this-release"
        return True

    async def sleep(_: float) -> None:
        bound.append(str(sessions.kw["bind"].url.database))

    asyncio.run(
        keep_following(
            sessions,
            url=THROUGH_THE_POOLER,
            workload=WorkloadClass.INTERACTIVE,
            commit="this-release",
            rounds=2,
            sleep=sleep,
            reader=reader,
        )
    )
    assert bound == ["brain_interactive"]
    assert sessions.kw["bind"] is home
    asyncio.run(home.dispose())


def test_a_reading_the_database_refuses_is_read_as_not_running() -> None:
    """A process on the class pooler that can no longer read through it is moved home by exactly
    this False. Delete this and the read can raise out of the loop and leave it moved for good."""

    class Refusing:
        def __call__(self) -> Refusing:
            return self

        async def __aenter__(self) -> None:
            raise ConnectionRefusedError

        async def __aexit__(self, *_: object) -> None:
            return None

    routing = Routing(commit="this-release", running=True)
    assert asyncio.run(routing.refresh(Refusing())) is False  # type: ignore[arg-type]
    assert routing.url(THROUGH_THE_POOLER, WorkloadClass.BATCH) == THROUGH_THE_POOLER


# ------------------------------------------------------------------ what the pooler reads
def test_the_configuration_is_one_transaction_pool_per_class_summing_to_the_poolers_slots() -> None:
    """Parsed as an ini, and every figure held against the file it has to agree with: the split
    is `pools_for` over the existing pooler's DEFAULT_POOL_SIZE, each entry bounded across logins
    at its own size (`A_CLASS_SHARE_IS_BOUNDED_ACROSS_LOGINS`), the database host, the client
    ceiling, the mode and the login lookup are the existing pooler's. Delete this and the class
    pools can add twenty per class to the database, or admit a login the first pooler refuses."""
    parsed = configparser.ConfigParser(interpolation=None)
    parsed.read_string(render_ini(database="brain", auth_user="brain"))
    first = _first_pooler()["environment"]

    entries = {
        name: dict(part.split("=", 1) for part in value.split())
        for name, value in parsed["databases"].items()
    }
    assert set(entries) == {f"brain_{one.value}" for one in WorkloadClass}
    sizes = []
    for workload in WorkloadClass:
        entry = entries[CLASS_DATABASE[workload]]
        assert entry["pool_size"] == entry["max_db_connections"] == str(POOLS.slots_for(workload))
        assert (entry["host"], entry["port"]) == (first["DB_HOST"], first["DB_PORT"])
        assert (entry["dbname"], entry["auth_user"]) == ("brain", first["DB_USER"])
        sizes.append(int(entry["pool_size"]))
    assert sum(sizes) == POOLER_SLOTS == int(first["DEFAULT_POOL_SIZE"])
    assert POOLS.batch < POOLS.background < POOLS.interactive

    bouncer = parsed["pgbouncer"]
    assert bouncer["pool_mode"] == first["POOL_MODE"] == "transaction"
    assert bouncer["auth_type"] == first["AUTH_TYPE"]
    assert bouncer["auth_query"] == first["AUTH_QUERY"].replace("$$", "$")
    assert bouncer["max_client_conn"] == first["MAX_CLIENT_CONN"]
    assert bouncer["listen_port"] == "5432"


@pytest.mark.parametrize(
    ("database", "auth_user"), [("brain; DROP", "brain"), ("brain", "x y"), ("", "brain")]
)
def test_a_name_the_configuration_cannot_carry_is_refused(database: str, auth_user: str) -> None:
    """A name with a space or a separator in it would be read by PgBouncer as another parameter.
    The positive sibling is the test above. Delete this and a database name can smuggle a setting
    into the pool's entry."""
    with pytest.raises(ClassPoolError):
        render_ini(database=database, auth_user=auth_user)


def test_the_owner_login_is_written_quoted_and_a_password_it_cannot_carry_is_refused() -> None:
    """Single-quoted, so the environment file passes a dollar sign through as it is; a quote, a
    backslash or a line break is refused in words naming no value, which leaves every process on
    its pooler. Delete this and an unusual password reaches the userlist mangled, and the class
    pooler admits nobody while the deploy step reports it healthy."""
    assert owner_login_lines("postgresql+psycopg://brain:s%24cret@pgbouncer:5432/brain") == (
        "BRAIN_CLASS_POOL_OWNER='brain'\nBRAIN_CLASS_POOL_OWNER_PASSWORD='s$cret'\n"
    )
    for password in ("zqx%27v", "zqx%5Cv", "zqx%0Av", "zqx%22v"):
        url = f"postgresql+psycopg://brain:{password}@pgbouncer:5432/brain"
        with pytest.raises(ClassPoolError) as refused:
            owner_login_lines(url)
        assert "zqx" not in str(refused.value)
    with pytest.raises(ClassPoolError):
        owner_login_lines("postgresql+psycopg://brain@pgbouncer:5432/brain")


def test_the_command_writes_the_configuration_and_says_why_when_it_cannot(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the preparation runs inside the application. With no owner login it exits 1 with one
    SAY line, which the preparation shows; with one it writes the configuration. Delete this and
    the preparation can read a usage message as a configuration file."""
    for name in ("DATABASE_URL", "BRAIN_MIGRATION_DATABASE_URL", "BRAIN_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert class_pools.main(["ini", "--database", "brain"]) == 1
    assert capsys.readouterr().out.startswith("SAY the class pools are not prepared: ")

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://brain:pw@pgbouncer:5432/brain")
    assert class_pools.main(["ini", "--database", "brain"]) == 0
    assert "brain_batch = host=db" in capsys.readouterr().out
    assert class_pools.main(["anything"]) == 64


# ------------------------------------------------------------------- what the release starts
def test_the_compose_file_runs_the_first_poolers_image_on_the_servers_network_only() -> None:
    """Parsed: the same image and version as the application's pooler, `expose` and never
    `ports`, the budgeted limit, the configuration mounted read-only, the external network the
    preparation names, and a healthcheck asking for the interactive entry. Delete this and the
    pools can be published on the host, or run a pooler whose entrypoint nobody has read."""
    compose = yaml.safe_load((STEP / "class-pools.yml").read_text(encoding="utf-8"))
    [(name, service)] = compose["services"].items()
    assert name == CLASS_POOLER == CLASS_OVERLAY.components[0]
    assert service["image"] == _first_pooler()["image"]
    assert "ports" not in service
    assert service["expose"] == ["5432"]
    assert service["deploy"]["resources"]["limits"]["memory"] == "32M"
    assert 32 <= component(CLASS_POOLER).memory_mib <= 64
    [mount] = service["volumes"]
    assert mount.endswith(":/etc/pgbouncer/pgbouncer.ini:ro")
    assert service["networks"] == ["default", "brain-app"]
    assert compose["networks"]["brain-app"]["external"] is True
    assert "BRAIN_APP_NETWORK" in compose["networks"]["brain-app"]["name"]
    assert service["healthcheck"]["test"][-1].endswith(
        f"-d {CLASS_DATABASE[WorkloadClass.INTERACTIVE]}"
    )


def test_the_class_pools_are_planned_on_every_deploy_and_cannot_be_named_in_the_setting() -> None:
    """`AN_OVERLAY_THE_PRODUCT_ALWAYS_RUNS_IS_STILL_COSTED`: in every plan, first, whatever the
    setting says, and not a name the setting may carry. Delete this and class isolation becomes
    an option nobody switches on."""
    assert planned(()) == (CLASS_OVERLAY,)
    assert planned(switched_on("presidio")) == (CLASS_OVERLAY, BY_NAME["presidio"])
    assert CLASS_OVERLAY.always and "class-pools" not in BY_NAME
    with pytest.raises(OverlayError):
        switched_on("class-pools")


def test_a_server_without_room_for_the_class_pools_is_told_so_and_one_with_room_starts_them() -> (
    None
):
    """Costed like any overlay, at the boundary. Delete this and the pools can start on a server
    that cannot hold them, or be refused on one that can."""
    cost = CLASS_OVERLAY.cost_mib
    assert cost == component(CLASS_POOLER).memory_mib

    def room(left: int) -> Host:
        from brain.ops.wiring import HOST_RESERVE_MIB

        return Host(total_mib=left + HOST_RESERVE_MIB, reserved_mib=0, unlimited_used_mib=0)

    assert plan(planned(()), room(cost)).start == (CLASS_OVERLAY,)
    short = plan(planned(()), room(cost - 1))
    assert short.start == ()
    [(_, reason)] = short.refused
    assert reason == (
        f"the connection pools for each workload class (class-pools) needs {cost} MiB and this "
        f"server has {cost - 1} MiB left for it, so it is not started"
    )


def test_the_budget_counts_the_two_poolers_once_at_the_larger() -> None:
    """`TWO_POOLERS_FOR_ONE_TRAFFIC_ARE_ONE_BUDGET`: the class pooler's row is the three pools
    together, held against `POOLS` rather than against itself, and it is the same budget as the
    application's pooler, so the database's demand is what it was without it and its memory sizing
    still holds. Delete this and the class pooler can be resized, or counted twice, with nothing
    saying so; counted twice it is seventy connections against memory sized for fifty-six."""
    from brain.deployment.postgres_settings import SETTINGS_FOR
    from brain.ops.connections import (
        CLASS_POOLER_CONNECTIONS,
        CLIENTS,
        client_named,
        connection_breaches,
        database,
        demand_on,
        headroom_on,
    )

    row = client_named(CLASS_POOLER)
    assert row is not None and row.database == "db" and row.shares_with == "pgbouncer"
    assert row.pool_max == CLASS_POOLER_CONNECTIONS == POOLS.total
    first = client_named("pgbouncer")
    assert first is not None and first.pool_max == POOLER_SLOTS
    without = sum(one.demand() for one in CLIENTS if one.database == "db" and one is not row)
    assert demand_on("db") == without
    assert not [one for one in connection_breaches() if "'db'" in one]
    assert headroom_on("db") > 0
    sized = database("db").memory_mib
    assert all(one.worst_case_mib(demand_on("db")) <= sized for one in SETTINGS_FOR.values())


def test_a_shared_budget_counts_the_larger_and_one_naming_nobody_is_a_breach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive half: two rows sharing a budget count once, at the larger. The refusal half: a
    row sharing the budget of a client that does not exist is counted nowhere, and that is named;
    a row sharing its own budget cannot be built. Delete this and a typo in `shares_with` takes
    twenty connections out of the database's budget in silence."""
    from brain.ops import connections

    small = connections.Client(name="a", database="db", pool_max=5, why="w", shares_with="b")
    large = connections.Client(name="b", database="db", pool_max=9, why="w")
    monkeypatch.setattr(connections, "CLIENTS", (small, large))
    assert connections.demand_on("db") == 9
    assert not [one for one in connections.connection_breaches() if "'db'" in one]

    stray = connections.Client(name="a", database="db", pool_max=5, why="w", shares_with="zz")
    monkeypatch.setattr(connections, "CLIENTS", (stray, large))
    assert any("'zz'" in one for one in connections.connection_breaches())
    with pytest.raises(ValueError, match="with itself"):
        connections.Client(name="a", database="db", pool_max=5, why="w", shares_with="a")


# ------------------------------------------------------------------- the preparation, run
PREPARE_STUB = r"""#!/bin/sh
S="$STUB_STATE"
echo "$*" >> "$S/calls"
case "$1" in
  ps) cat "$S/db"; exit 0 ;;
  inspect) echo "u_default"; exit 0 ;;
  exec)
    case "$*" in
      *POSTGRES_DB*) echo brain; exit 0 ;;
      *"class_pools ini"*) echo "[databases]"; echo "brain_batch = host=db"; exit 0 ;;
      *owner-login*) cat "$S/login"; exit "$(cat "$S/login_exit")" ;;
    esac ;;
esac
exit 0
"""

LOGIN = "BRAIN_CLASS_POOL_OWNER='brain'\nBRAIN_CLASS_POOL_OWNER_PASSWORD='kept-secret'\n"


@dataclass
class Prepared:
    code: int
    output: str
    env: str
    calls: list[str]
    settings: Path


def prepare(
    tmp_path: Path, *, login: str = LOGIN, login_exit: int = 0, before: str = ""
) -> Prepared:
    """Run the real `class-pools.prepare.sh` against a stub docker whose application answers."""
    state, bin_dir, settings = tmp_path / "state", tmp_path / "bin", tmp_path / "settings"
    for one in (state, bin_dir, settings):
        one.mkdir(exist_ok=True)
    fake = bin_dir / "docker"
    fake.write_text(PREPARE_STUB, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    for name, text in (
        ("db", "db-u\n"),
        ("calls", ""),
        ("login", login),
        ("login_exit", f"{login_exit}\n"),
    ):
        (state / name).write_text(text, encoding="utf-8", newline="\n")
    env_file = settings / "overlays.env"
    if before:
        env_file.write_text(before, encoding="utf-8", newline="\n")
    assert SH is not None
    done = subprocess.run(
        [SH, (STEP / "class-pools.prepare.sh").as_posix()],
        env={
            **os.environ,
            "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
            "STUB_STATE": state.as_posix(),
            "BRAIN_OVERLAYS_SETTINGS": settings.as_posix(),
            "BRAIN_OVERLAYS_ENV": env_file.as_posix(),
            "BRAIN_APP_PROJECT": "u",
            "BRAIN_APP_CONTAINER": "app-u",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return Prepared(
        code=done.returncode,
        output=done.stdout + done.stderr,
        env=env_file.read_text(encoding="utf-8") if env_file.exists() else "",
        calls=(state / "calls").read_text(encoding="utf-8").splitlines(),
        settings=settings,
    )


pytestmark_sh = pytest.mark.skipif(SH is None, reason="the preparation is a POSIX shell script")


@pytestmark_sh
def test_the_preparation_writes_the_configuration_and_keeps_the_login_where_only_root_reads(
    tmp_path: Path,
) -> None:
    """The configuration comes from the application and is readable by the pooler; the login goes
    into the environment file at 0600, never onto a command line or into the journal, with the
    configuration's path and the database's network; a second run replaces rather than repeats
    them and keeps what other preparations wrote. Delete this and the owner's password can land in
    the deploy journal, or the file can grow a second, stale login."""
    first = prepare(tmp_path, before="LANGFUSE_SALT=abc\nBRAIN_APP_NETWORK=old\n")
    assert first.code == 0, first.output
    ini = first.settings / "class-pools" / "pgbouncer.ini"
    assert ini.read_text(encoding="utf-8").startswith("[databases]\n")
    assert stat.S_IMODE(ini.stat().st_mode) == 0o644
    assert stat.S_IMODE((first.settings / "overlays.env").stat().st_mode) == 0o600
    assert first.env.splitlines() == [
        "LANGFUSE_SALT=abc",
        "BRAIN_CLASS_POOL_OWNER='brain'",
        "BRAIN_CLASS_POOL_OWNER_PASSWORD='kept-secret'",
        f"BRAIN_CLASS_POOLS_INI={ini.as_posix()}",
        "BRAIN_APP_NETWORK=u_default",
    ]
    assert "kept-secret" not in first.output
    assert not [one for one in first.calls if "kept-secret" in one]
    assert "exec app-u python -m brain.ops.class_pools ini --database brain" in first.calls

    second = prepare(tmp_path)
    assert second.code == 0, second.output
    assert second.env == first.env


@pytestmark_sh
def test_a_login_the_application_refuses_fails_the_preparation_and_changes_nothing(
    tmp_path: Path,
) -> None:
    """The application's SAY line is shown and nothing else, the environment file is untouched,
    and the exit is non-zero, which leaves the pooler out of this deploy. Delete this and a refusal
    can be written into the environment file as if it were a login."""
    ran = prepare(
        tmp_path,
        login="SAY the class pools are not prepared: no login\n",
        login_exit=1,
        before="LANGFUSE_SALT=abc\n",
    )
    assert ran.code == 1
    assert "overlays: class-pools: the class pools are not prepared: no login" in ran.output
    assert ran.env == "LANGFUSE_SALT=abc\n"


# ------------------------------------------------------------------- the install check
MODULE = "brain.ops.acceptance_checks_class_pools"
CHECK = "a_batch_job_holding_its_share_cannot_take_a_persons_connection"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_claims_the_leaf_it_proves() -> None:
    """Delete this and the check can drift onto another leaf and close it on this evidence."""
    assert mine()[CHECK].leaves == ("M22.2.2",)


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_acceptance_class_pools") as url:
        yield url


@pytest.fixture
def batch_login(database: str) -> Iterator[str]:
    """A login limited to the batch share, standing in for the batch pool: past the share, a
    client does not get a server connection."""
    import psycopg

    from brain.db import libpq_url

    role = f"class_batch_{secrets.token_hex(4)}"
    password = secrets.token_hex(8)
    with psycopg.connect(libpq_url(database), autocommit=True) as conn:
        conn.execute(
            f"CREATE ROLE {role} LOGIN NOSUPERUSER CONNECTION LIMIT {POOLS.batch} "
            f"PASSWORD '{password}'"
        )
    try:
        yield (
            make_url(database)
            .set(username=role, password=password)
            .render_as_string(hide_password=False)
        )
    finally:
        with psycopg.connect(libpq_url(database), autocommit=True) as conn:
            conn.execute(f"DROP ROLE IF EXISTS {role}")


def _observe(database: str, monkeypatch: pytest.MonkeyPatch, row: dict[str, object]) -> None:
    """Keep `row` as the deploy step does, through the step's own writer."""
    from brain.ops import overlays

    monkeypatch.setenv("BRAIN_MIGRATION_DATABASE_URL", database)
    overlays._record(row)


def _judged(
    database: str, monkeypatch: pytest.MonkeyPatch, urls: Mapping[WorkloadClass, str]
) -> tuple[str, str]:
    from tests.unit.test_acceptance_capacity import run_checks

    monkeypatch.setattr(pools_check, "targets", lambda _h: urls)
    return run_checks(database, (mine()[CHECK],), {})[CHECK]


def _this_release(**body: str) -> dict[str, object]:
    return {**_seen(**body), "commit": settings_from({}).resolved_commit()}


@pytest.mark.needs_db
def test_on_a_real_database_a_held_batch_share_leaves_an_interactive_transaction_running(
    database: str, batch_login: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The check as the worker runs it.** Batch's three connections are held, an interactive
    transaction runs at once, a fourth batch one does not get a connection, and once the three are
    let go batch runs again. Delete this and a check that refuses everything, or one that cannot
    run on the real schema, reaches the owner's server first."""
    _observe(database, monkeypatch, _this_release())
    urls = {WorkloadClass.INTERACTIVE: database, WorkloadClass.BATCH: batch_login}
    assert _judged(database, monkeypatch, urls) == (PASSED, "")


@pytest.mark.needs_db
def test_on_a_real_database_a_batch_share_that_bounds_nothing_fails(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A batch pool with no limit: holding three proves nothing, and the fourth runs. Delete this
    and a pooler whose batch entry was never bounded passes as isolated."""
    _observe(database, monkeypatch, _this_release())
    urls = {WorkloadClass.INTERACTIVE: database, WorkloadClass.BATCH: database}
    assert _judged(database, monkeypatch, urls) == (
        FAILED,
        pools_check.THE_BATCH_SHARE_IS_NOT_BOUNDED,
    )


@pytest.mark.needs_db
def test_on_a_real_database_an_interactive_pool_shared_with_batch_fails(
    database: str, batch_login: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interactive drawing on the same limited login as batch is one pool with two names, and the
    held share leaves it nothing. Delete this and one pool split in name only passes."""
    _observe(database, monkeypatch, _this_release())
    urls = {WorkloadClass.INTERACTIVE: batch_login, WorkloadClass.BATCH: batch_login}
    assert _judged(database, monkeypatch, urls) == (
        FAILED,
        pools_check.BATCH_TOOK_THE_REQUEST_PATHS_CONNECTION,
    )


@pytest.mark.needs_db
@pytest.mark.parametrize("health", ["unhealthy", "absent"])
def test_on_a_real_database_a_pooler_not_running_for_this_release_is_not_run(
    database: str, monkeypatch: pytest.MonkeyPatch, health: str
) -> None:
    """Not running is the design's fallback, not a fault, and the check says so rather than
    passing or failing. Delete this and an install with no room for the pools shows a red row, or
    a green one for isolation it does not have."""
    row: dict[str, object] = _this_release(health="unhealthy")
    if health == "absent":
        row = {"commit": settings_from({}).resolved_commit(), "services": {}}
    _observe(database, monkeypatch, row)
    urls = {WorkloadClass.INTERACTIVE: database, WorkloadClass.BATCH: database}
    assert _judged(database, monkeypatch, urls) == (NOT_RUN, pools_check.NOT_RUNNING_HERE)


def test_a_worker_url_that_does_not_go_through_the_pooler_has_no_targets() -> None:
    """The check derives its URLs as a moved process would, so a worker connected straight to the
    database has nothing to ask. The positive sibling is the derivation test above. Delete this
    and the check can connect to the database directly and report isolation it never tested."""
    from types import SimpleNamespace

    direct = SimpleNamespace(settings=SimpleNamespace(database_url="postgresql://u:p@db:5432/b"))
    through = SimpleNamespace(settings=SimpleNamespace(database_url=THROUGH_THE_POOLER))
    assert pools_check.targets(direct) is None  # type: ignore[arg-type]
    found = pools_check.targets(through)  # type: ignore[arg-type]
    assert found is not None
    assert make_url(found[WorkloadClass.BATCH]).database == "brain_batch"


def test_what_the_step_reports_of_the_pooler_is_what_the_rule_reads() -> None:
    """The producer and the consumer of the report, end to end: the step's own `observation` over
    docker's account is what `runs_here` moves a process on. Delete this and the two can disagree
    on a field name and no process ever moves."""
    seen = (Seen(CLASS_POOLER, 32, "running", "healthy"),)
    assert runs_here(observation(seen, commit="c"), commit="c") is True
    assert runs_here(observation(seen, commit="c"), commit="d") is False
