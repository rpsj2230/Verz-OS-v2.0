"""Workers are forked from a supervisor that imported the application and built nothing live.

`brain.serve` says why: forked workers share the imported modules, which spawned ones import
again, about 200 MiB each. The arrangement is safe only while importing `brain.app` opens nothing,
so these tests hold that in a fresh process, prove the check finds each kind of live object it
names, and prove the supervisor falls back to spawning the moment the check finds one.

Task ids: M31.1.2.1
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import uvicorn
import uvicorn._subprocess

import brain.serve as serve
from brain.runtime import profile_for
from brain.serve import NOTHING_LIVE_CROSSES_A_FORK, live_before_fork


def test_importing_the_application_in_a_fresh_process_leaves_nothing_live() -> None:
    """A child that imports `brain.app` and nothing else holds no socket, engine, thread, loop or
    client.

    Delete this and an import that opens a pool or starts a thread passes every other test here,
    and the supervisor quietly falls back to spawning (or, if the check is also gone, hands the
    same connection to four workers).
    """
    code = (
        "import json, brain.app\n"
        "from brain.serve import live_before_fork\n"
        "print(json.dumps(list(live_before_fork())))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert json.loads(done.stdout.strip().splitlines()[-1]) == []


def _thread() -> Iterator[object]:
    stop = threading.Event()
    worker = threading.Thread(target=stop.wait, name="left-running")
    worker.start()
    yield worker
    stop.set()
    worker.join()


def _socket() -> Iterator[object]:
    with socket.socket() as one:
        yield one


def _loop() -> Iterator[object]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _engine() -> Iterator[object]:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://")
    yield engine
    engine.dispose()


def _cache() -> Iterator[object]:
    from redis import Redis

    client = Redis()
    yield client
    client.close()


def _http() -> Iterator[object]:
    import httpx

    with httpx.Client() as client:
        yield client


@pytest.mark.parametrize(
    ("kind", "make"),
    [
        ("thread", _thread),
        ("socket", _socket),
        ("event loop", _loop),
        ("database engine", _engine),
        ("cache client", _cache),
        ("HTTP client", _http),
    ],
)
def test_each_kind_of_live_object_is_found(kind: str, make: Callable[[], Iterator[object]]) -> None:
    """The check names a thread, socket, loop, engine, cache client or HTTP client when one exists.

    The sibling of the test above, which an empty check would also pass. Delete this and
    `live_before_fork` can stop looking at any one kind, and the first import that builds one is
    forked into every worker.
    """
    made = make()
    held = next(made)
    try:
        found = live_before_fork()
        assert any(kind in one for one in found), found
    finally:
        del held
        for _ in made:
            pass


def test_a_supervisor_that_finds_anything_live_spawns_its_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One live object found, and `preload_for_fork` says no; none, and it says yes.

    Delete this and the fallback can be lost: the check runs, finds a pool, and the supervisor
    forks anyway, which is the failure `NOTHING_LIVE_CROSSES_A_FORK` exists to prevent.
    """
    assert "spawns its workers instead" in NOTHING_LIVE_CROSSES_A_FORK
    monkeypatch.setattr(serve, "live_before_fork", lambda: ("1 database engine",))
    assert serve.preload_for_fork() is False
    monkeypatch.setattr(serve, "live_before_fork", lambda: ())
    assert serve.preload_for_fork() is (os.name == "posix")


def test_forking_changes_the_context_uvicorn_starts_its_workers_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After `fork_workers`, the process uvicorn builds for a worker is a forked one.

    Asked of uvicorn's own `get_subprocess`, so a uvicorn release that stops reading the module
    attribute fails here rather than spawning silently with the saving gone.
    """
    monkeypatch.setattr(uvicorn._subprocess, "spawn", uvicorn._subprocess.spawn)
    serve.fork_workers()
    config = uvicorn.Config(app="brain.app:app")
    process = uvicorn._subprocess.get_subprocess(config, target=lambda **_: None, sockets=[])
    assert isinstance(process, multiprocessing.get_context("fork").Process)


@pytest.mark.parametrize(
    ("workers", "clean", "forked"), [(4, True, True), (4, False, False), (1, True, False)]
)
def test_the_server_forks_only_several_workers_from_a_clean_supervisor(
    monkeypatch: pytest.MonkeyPatch, workers: int, clean: bool, forked: bool
) -> None:
    """`main` forks when there are several workers and nothing live, and spawns otherwise.

    Delete this and `main` can stop calling the check, or call `fork_workers` regardless of it.
    """
    calls: list[str] = []
    profile = profile_for(memory_mb=workers * 230 + 96, cores=8)
    assert profile.workers == workers
    monkeypatch.setattr(serve, "detect_profile", lambda: profile)
    monkeypatch.setattr(serve, "assert_valid", lambda *_: None)
    monkeypatch.setattr(serve, "preload_for_fork", lambda: clean)
    monkeypatch.setattr(serve, "fork_workers", lambda: calls.append("fork"))
    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: seen.update(kwargs))
    serve.main()
    assert calls == (["fork"] if forked else [])
    assert seen["workers"] == workers


def test_a_supervisor_that_may_fork_freezes_what_it_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before forking, the collector's view of the imported application is frozen.

    Delete this and `gc.freeze()` can go, with every other test here green: the workers still
    fork, and their first collections copy back most of what they shared (measured on 2026-10-06:
    a 19 per cent saving without the freeze against 37 per cent with it). See
    `A_COLLECTION_IN_A_WORKER_COPIES_WHAT_IT_WALKS`.
    """
    import gc

    monkeypatch.setattr(serve, "live_before_fork", lambda: ())
    gc.unfreeze()
    assert gc.get_freeze_count() == 0
    try:
        assert serve.preload_for_fork() is (os.name == "posix")
        assert (gc.get_freeze_count() > 0) is (os.name == "posix")
    finally:
        gc.unfreeze()


def test_a_host_without_fork_spawns_its_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Off POSIX there is no fork to take, so the supervisor says no before importing anything.

    Delete this and the guard can go with every test on a POSIX runner green, and a Windows
    development machine asks `multiprocessing` for a start method it does not have.
    """
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(serve, "live_before_fork", lambda: ())
    assert serve.preload_for_fork() is False
