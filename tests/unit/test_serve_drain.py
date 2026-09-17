"""A request in flight when the server is told to stop finishes, on a real uvicorn server.

The tracker audit reopened graceful shutdown on 2026-09-17 because nothing had shown an in-flight
request surviving a stop: `test_runtime.py` checks the numbers handed to uvicorn, and
`test_app.py` checks the lifespan's shutdown half through `TestClient`, which never stops a
server. This serves the application `create_app` builds, over a socket, with exactly the options
`brain.serve.server_options` gives uvicorn in a container, starts a slow request, tells the
server to exit the way SIGTERM does, and reads the answer.

What it cannot show is Docker's own stop on an install; that is the proof the audit asks for
(start a slow request, redeploy, see the 200), and it needs the owner's server.

Task ids: M31.1.2.2, M31.1.1.3
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import httpx
import uvicorn

from brain.app import create_app
from brain.runtime import DOCKER_STOP_TIMEOUT, profile_for
from brain.serve import server_options
from brain.settings import Settings

#: Longer than a blink and well inside every graceful timeout `profile_for` can choose.
SLOW_SECONDS = 1.5


def test_a_request_in_flight_when_the_server_is_told_to_stop_finishes_with_a_200() -> None:
    """Delete this and `timeout_graceful_shutdown` can drop out of `server_options`, or fall to
    nought, and every other test stays green while each deploy cuts whoever was mid-question."""
    profile = profile_for(memory_mb=1024, cores=2)
    assert SLOW_SECONDS < profile.graceful_timeout < DOCKER_STOP_TIMEOUT

    app = create_app(Settings(env="development", run_migrations=False))
    arrived = threading.Event()

    @app.get("/_slow")
    async def _slow() -> dict[str, str]:
        arrived.set()
        await asyncio.sleep(SLOW_SECONDS)
        return {"done": "yes"}

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", **server_options(profile)))
    serving = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    serving.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the server never started, so this tests nothing"

    answers: list[httpx.Response] = []
    asking = threading.Thread(
        target=lambda: answers.append(httpx.get(f"http://127.0.0.1:{port}/_slow", timeout=15))
    )
    asking.start()
    assert arrived.wait(10), "the slow request never reached the route"

    stopped_at = time.monotonic()
    server.should_exit = True  # what uvicorn's own SIGTERM handler sets
    asking.join(15)
    serving.join(profile.graceful_timeout + 5)

    assert [answer.status_code for answer in answers] == [200]
    assert answers[0].json() == {"done": "yes"}
    assert not serving.is_alive(), "the server did not stop after the request finished"
    assert time.monotonic() - stopped_at < profile.graceful_timeout + 2
