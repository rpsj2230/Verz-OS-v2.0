"""Entry point. Sizes the process against the container, then hands over to uvicorn.

Exists because `uvicorn --workers N` needs N decided before the process starts, and the
only honest source for N is the container's own cgroup limits, which are not knowable
from a Dockerfile.

**The workers are forked from a supervisor that has imported the application, not spawned.**
Uvicorn starts each worker with `multiprocessing`'s spawn context, so every worker imported the
whole application from nothing: measured on 2026-10-06 that is about 200 MiB a worker before any
request, four times over in a 1024M container, and the in-app document read limit is what is
left. Forked workers share the supervisor's imported modules until they write to them.

That is only safe because importing `brain.app` opens nothing: no socket, no database engine or
pool, no thread, no event loop, no cache or vault client. Everything live is built per worker, in
the lifespan, after the fork. See `NOTHING_LIVE_CROSSES_A_FORK`: `live_before_fork` checks it in
the supervisor every time, and a supervisor that finds anything falls back to spawning, which is
slower to start and never wrong. Rejected: gunicorn with `--preload`, which is the same fork with
a second process manager and a dependency, and preloading without the check, which turns the
first import that opens a pool into connections two processes both believe they own.

Task ids: M31.1.2.1, M31.1.2.2, M31.1.2.3
"""

from __future__ import annotations

import asyncio
import gc
import multiprocessing
import os
import socket
import threading
from typing import Any, Final, cast

import structlog
import uvicorn
import uvicorn._subprocess

from brain.config import assert_valid
from brain.runtime import ProcessProfile, detect_profile
from brain.settings import Settings

log = structlog.get_logger()

#: Why the supervisor may fork its workers, and the condition it checks before it does.
NOTHING_LIVE_CROSSES_A_FORK: Final = (
    "Workers are forked from a supervisor that has imported the application and built nothing: "
    "no socket, no database engine, no thread, no event loop, no cache or vault client. Each "
    "worker builds its own in its lifespan. A live object inherited across a fork is one "
    "connection or lock that two processes both believe they own, so a supervisor that finds one "
    "spawns its workers instead."
)


#: Why the supervisor freezes the collector's view of what it imported before forking.
A_COLLECTION_IN_A_WORKER_COPIES_WHAT_IT_WALKS: Final = (
    "A forked worker shares the supervisor's pages until it writes to one, and the cycle "
    "collector writes to every object it examines. Without gc.freeze() before the fork, the first "
    "collections in each worker walk the whole imported application and turn most of the shared "
    "pages back into private copies."
)


def live_before_fork() -> tuple[str, ...]:
    """Everything in this process that must not be inherited by a forked worker, by kind.

    Read from the interpreter itself (threads, and the garbage collector's view of live objects),
    so a new kind of client is caught by its class rather than by somebody remembering to list it.
    """
    import httpx
    from redis import Redis
    from redis.asyncio import Redis as AsyncRedis
    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine

    found = [
        f"thread {one.name!r}"
        for one in threading.enumerate()
        if one is not threading.main_thread()
    ]
    kinds: tuple[tuple[str, tuple[type[Any], ...]], ...] = (
        ("socket", (socket.socket,)),
        ("database engine", (Engine, AsyncEngine)),
        ("event loop", (asyncio.AbstractEventLoop,)),
        ("cache client", (Redis, AsyncRedis)),
        ("HTTP client, which is how the vault is reached", (httpx.Client, httpx.AsyncClient)),
    )
    live = gc.get_objects()
    for name, types in kinds:
        count = sum(1 for one in live if isinstance(one, types))
        if count:
            found.append(f"{count} {name}")
    return tuple(found)


def preload_for_fork() -> bool:
    """Import the application here and say whether workers may be forked from this process.

    True only on a POSIX host whose import of `brain.app` left nothing live. See
    `NOTHING_LIVE_CROSSES_A_FORK`.
    """
    if os.name != "posix":
        return False
    import brain.app  # noqa: F401 - imported here so forked workers share its modules

    found = live_before_fork()
    if found:
        log.warning(
            "workers spawned rather than forked", why=NOTHING_LIVE_CROSSES_A_FORK, found=found
        )
        return False
    # Everything imported so far moves to the collector's permanent generation, so no worker's
    # collection walks it and writes to its pages: a page the collector touches is a page the
    # fork has to copy. See `A_COLLECTION_IN_A_WORKER_COPIES_WHAT_IT_WALKS`.
    gc.freeze()
    return True


def fork_workers() -> None:
    """Have uvicorn start its workers by fork rather than spawn.

    Uvicorn keeps its process context in `uvicorn._subprocess.spawn` and offers no option for it;
    the module attribute is the one place it is read (`get_subprocess`), and the version is
    pinned by the lock file. `tests/unit/test_serve_fork.py` fails if that stops being true.
    """
    # A cast at the library boundary: uvicorn annotates the attribute as the spawn context it
    # sets, and the one thing it does with it, `.Process(...)`, both contexts provide.
    uvicorn._subprocess.spawn = cast(Any, multiprocessing.get_context("fork"))


def server_options(profile: ProcessProfile) -> dict[str, Any]:
    """How uvicorn stops and holds connections: the part a drain test serves an app with.

    Separate from the address and the worker count so `tests/unit/test_serve_drain.py` runs a
    real server with exactly these values rather than a copy of them."""
    return {
        # Uvicorn stops accepting, then waits this long for in-flight requests. Cutting
        # them instead returns 502 to whoever was mid-question on every deploy.
        "timeout_graceful_shutdown": profile.graceful_timeout,
        "timeout_keep_alive": profile.timeout_keep_alive,
        "limit_concurrency": profile.limit_concurrency,
        "access_log": False,  # structlog already emits one line per request, with the trace id
        "server_header": False,
        "date_header": False,
    }


def main() -> None:
    # Before the port is bound. A container that will never work should not be in a load
    # balancer's rotation at all, so this is the one place crashing beats degrading.
    settings = Settings()
    assert_valid(
        settings.env,
        {
            "database_url": settings.database_url,
            "valkey_url": settings.valkey_url,
            "app_role_password": settings.app_role_password,
            "cors_origins": ",".join(settings.cors_origins),
            "widget_origins": ",".join(settings.widget_origins),
        },
    )

    profile = detect_profile()
    forked = profile.workers > 1 and preload_for_fork()
    if forked:
        fork_workers()
    log.info(
        "starting server",
        workers=profile.workers,
        forked=forked,
        graceful_timeout=profile.graceful_timeout,
        limit_concurrency=profile.limit_concurrency,
        reason=profile.reason,
    )
    uvicorn.run(
        "brain.app:app",
        host="0.0.0.0",  # noqa: S104 - the container is the boundary, not the interface
        port=8000,
        workers=profile.workers,
        **server_options(profile),
    )


if __name__ == "__main__":
    main()
