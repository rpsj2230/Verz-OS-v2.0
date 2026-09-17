"""Engines, sessions, and the PgBouncer constraints that shape them.

Task ids: M0.3.4, M31.2.1.2, M31.2.1.3, M31.2.1.4, M31.2.1.5
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain import session as sess
from brain.db import AuditMixin, SoftDeleteMixin, TimestampMixin
from brain.deployment.requirements import COMPOSE_FILES_FOR

URL = "postgresql://u:p@localhost:5432/d"


def test_the_app_engine_disables_server_side_prepared_statements() -> None:
    """Not a tuning knob. PgBouncer in transaction mode hands a different backend to every
    transaction, so a statement prepared on one and executed on another fails - or worse,
    reuses a plan built for different parameters. Without this the app works in
    development, where there is no pooler, and fails in production under load.
    """
    engine = sess.make_app_engine(URL)
    assert engine.dialect.name == "postgresql"
    # psycopg's own kwarg, passed through connect_args
    assert engine.pool.__class__ is NullPool


def test_the_app_engine_is_built_with_prepared_statements_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The test above is named for this property and never asserts it: its body checks the
    pool class, and a comment says the argument is passed. Setting `prepare_threshold` to 0 in
    `make_app_engine` left this file green.

    Asserted on the arguments the engine is built with, because an async engine offers no
    public view of the connect arguments it will hand psycopg, and `None` specifically: 0 means
    prepare on first use, which is the most aggressive setting rather than the off switch.

    Delete this and the application works on a laptop, where there is no pooler, and fails in
    production under load the first time two transactions land on different backends."""
    seen: dict[str, Any] = {}

    def capture(url: str, **kwargs: Any) -> object:
        del url
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(sess, "create_async_engine", capture)
    sess.make_app_engine(URL)

    assert "prepare_threshold" in seen["connect_args"]
    assert seen["connect_args"]["prepare_threshold"] is None


def test_the_app_engine_is_built_with_exactly_the_arguments_transaction_pooling_allows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole call, compared as one structure, because each argument a transaction pooler
    breaks is an argument somebody adds for a good reason somewhere else:

    - `poolclass=NullPool`: PgBouncer is the pool, and a second pool holds server connections
      the pooler has already handed to somebody else.
    - `prepare_threshold=None` and nothing else in `connect_args`: an `options` startup
      parameter (a `statement_timeout`, a `search_path`) is refused by PgBouncer at connect
      unless it is told to ignore it, and a session `SET` is carried to whichever client gets
      the server connection next. The role is `SET LOCAL` per transaction for that reason.
    - no `pool_size`, `max_overflow`, `pool_pre_ping` or `pool_recycle`: those configure a pool
      this engine does not keep. `engine_kwargs_for_profile` sizes a pool, and nothing may
      hand its figures to this engine.

    Delete this and any of those can be added to `make_app_engine` with every other test here
    green, and it fails only behind the pooler, which development does not run."""
    seen: dict[str, Any] = {}

    def capture(url: str, **kwargs: Any) -> object:
        seen["url"] = url
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(sess, "create_async_engine", capture)
    sess.make_app_engine("postgresql://u:p@pgbouncer:5432/brain")

    assert seen == {
        "url": "postgresql+psycopg://u:p@pgbouncer:5432/brain",
        "echo": False,
        "poolclass": NullPool,
        "connect_args": {"prepare_threshold": None},
    }


def test_the_app_engine_does_not_stack_a_pool_on_the_pooler() -> None:
    """PgBouncer is the pool. Two pools with different ideas about connection lifetime
    produce connections that look idle to one and busy to the other."""
    assert sess.make_app_engine(URL).pool.__class__ is NullPool


def test_the_worker_engine_keeps_a_real_pool() -> None:
    """LISTEN/NOTIFY binds to a backend connection. A listener behind a transaction pooler
    stops receiving notifications with no error anywhere, so the worker holds its own
    long-lived connections."""
    engine = sess.make_worker_engine(URL)
    assert engine.pool.__class__ is not NullPool


def test_a_bare_postgres_url_reaches_psycopg_three() -> None:
    assert sess._async_url("postgresql://u:p@h/d").startswith("postgresql+psycopg://")


# ------------------------------------------------------------------ sizing
@pytest.mark.parametrize(
    ("profile", "size"), [("lite", 5), ("standard", 10), ("full", 20), ("nonsense", 5)]
)
def test_pool_size_per_profile_and_a_safe_default(profile: str, size: int) -> None:
    """An unknown profile gets the smallest pool. The target box runs about thirty
    containers on twelve gigabytes; a pool sized for a machine we do not have is how a
    shared host falls over."""
    assert sess.engine_kwargs_for_profile(profile)["pool_size"] == size


# ------------------------------------------------------------------ mixins
def test_timestamps_come_from_the_database_not_the_application() -> None:
    """One clock. Application time is the clock of whichever container handled the write,
    and on a busy host those drift - which makes a ledger ordered by application time
    wrong exactly when it matters."""
    col = TimestampMixin.__annotations__
    assert "created_at" in col
    assert "updated_at" in col


def test_soft_delete_rather_than_removal() -> None:
    """A hard delete destroys the audit trail for the thing deleted, and the audit trail
    is the product."""
    assert "deleted_at" in SoftDeleteMixin.__annotations__


def test_the_audit_mixin_records_a_hash_not_a_capability_list() -> None:
    """A ledger holding the capabilities themselves becomes a map of who can see what,
    which is a document you do not want to have."""
    fields = AuditMixin.__annotations__
    assert "ent_hash" in fields
    assert "created_by" in fields
    assert "trace_id" in fields
    assert not any("capabilit" in f for f in fields)


# ------------------------------------------------------------------ the poolers per profile
def _profile_services(profile: str) -> dict[str, dict[str, Any]]:
    """Every described service in a profile's compose files, parsed rather than grepped."""
    repo = Path(__file__).resolve().parents[2]
    found: dict[str, dict[str, Any]] = {}
    for name in COMPOSE_FILES_FOR[profile]:
        document = yaml.safe_load((repo / name).read_text(encoding="utf-8")) or {}
        for service, body in (document.get("services") or {}).items():
            if isinstance(body, dict) and body:
                found.setdefault(service, {}).update(body)
    return found


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


@pytest.mark.parametrize("profile", ["lite", "standard", "full"])
def test_in_every_profile_the_application_reaches_a_transaction_pool_and_the_workers_a_session_pool(
    profile: str,
) -> None:
    """The engines above are only correct against the pooler they assume, so the assumption is
    read out of each profile's own compose files: the application's `DATABASE_URL` names a
    service in that profile running `POOL_MODE: transaction`, and every worker's `QUEUE_URL`
    names one running `POOL_MODE: session`.

    Delete this and a profile can point the application straight at `db`, where the missing
    prepared statements cost nothing and the missing pool costs the connection ceiling, or
    point a LISTEN at the transaction pool, where it stops being notified with no error."""
    services = _profile_services(profile)

    def mode(url: str) -> str:
        pooler = services.get(_host(url), {})
        return str((pooler.get("environment") or {}).get("POOL_MODE", "no pooler"))

    assert mode(services["app"]["environment"]["DATABASE_URL"]) == "transaction"
    workers = [name for name in ("brain-worker", "brain-parse-worker") if name in services]
    assert bool(workers) == (profile != "lite"), workers
    for worker in workers:
        assert mode(services[worker]["environment"]["QUEUE_URL"]) == "session", worker


# ------------------------------------------------------------------ a session per request, per job
class _RecordingSession:
    """Stands in for an `AsyncSession`: records what the helper did to it, and nothing else."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def rollback(self) -> None:
        self.calls.append("rollback")

    async def commit(self) -> None:
        self.calls.append("commit")

    async def close(self) -> None:
        self.calls.append("close")


def test_a_request_session_is_rolled_back_on_any_exception_and_always_closed() -> None:
    """One session per request, and a request that raises leaves nothing half written on the
    connection it hands back. Closed on both paths, because behind a transaction pooler an
    unclosed session is a server connection nobody else can have.

    Delete this and `request_session` can swallow the rollback, or close only on success, with
    nothing in the suite noticing: no other test calls it."""
    failed = _RecordingSession()
    # A cast at the fake's boundary: the helper only calls the factory and three methods.

    async def raising() -> None:
        async with sess.request_session(cast("async_sessionmaker[AsyncSession]", lambda: failed)):
            raise RuntimeError("the handler broke")

    with pytest.raises(RuntimeError):
        asyncio.run(raising())
    assert failed.calls == ["rollback", "close"]

    fine = _RecordingSession()

    async def succeeding() -> None:
        factory = cast("async_sessionmaker[AsyncSession]", lambda: fine)
        async with sess.request_session(factory) as session:
            assert cast(object, session) is fine

    asyncio.run(succeeding())
    assert fine.calls == ["close"], "a request that did not commit must not be committed for it"


def test_each_job_gets_its_own_engine_and_sessions_and_disposes_them_even_when_it_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued job is not a request, and the worker runs many: each builds its engine and
    session factory, uses them, and disposes the engine on the way out whether the control
    succeeded or failed. A factory shared between jobs would carry one job's failed
    transaction into the next.

    Delete this and `run_control_job` can hoist the engine out of the job, or drop the `finally`,
    and a failing control leaks its connections until the worker restarts."""
    from sqlalchemy.ext.asyncio import AsyncEngine

    from brain.ops import worker

    built: list[AsyncEngine] = []
    factories: list[object] = []
    disposed: list[AsyncEngine] = []

    def engine(url: str) -> AsyncEngine:
        made = sess.make_app_engine(url)
        built.append(made)
        return made

    async def dispose(self: AsyncEngine, close: bool = True) -> None:
        del close
        disposed.append(self)

    async def released(_session: object, *, now: object) -> frozenset[str]:
        del now
        return frozenset()

    async def owed(sessions: object, name: str, **_: object) -> worker.ControlTick:
        factories.append(sessions)
        if name == "retention_sweep":
            return worker.ControlTick(name, worker.Ticked.FAILED, "RuntimeError: broke")
        return worker.ControlTick(name, worker.Ticked.RAN)

    monkeypatch.setattr(worker, "make_app_engine", engine)
    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    monkeypatch.setattr(worker, "released_controls", released)
    monkeypatch.setattr(worker, "start_owed", owed)

    url = "postgresql://brain@pgbouncer:5432/brain"
    asyncio.run(worker.run_control_job("knowledge_reverification", database_url=url))
    with pytest.raises(worker.ControlRunError):
        asyncio.run(worker.run_control_job("retention_sweep", database_url=url))

    assert len(built) == 2 and built[0] is not built[1]
    assert disposed == built
    assert len(factories) == 2 and factories[0] is not factories[1]
