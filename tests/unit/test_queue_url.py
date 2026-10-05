"""The job queue is opened on its own connection everywhere, and never on the application's.

On 2026-09-30 the owner's install had failed `a_full_ingestion_queue_refuses_with_a_retry_hint` on
every one of the 27 runs that ran it: the check opened the queue on `database_url`, which is the
transaction pooler on every install, and `brain.ops.queue.queue_url_refusals` refuses a pooler
before a connection is opened. The upload route, the embedding enqueue after a stored document and
the lifecycle's did the same. The tests stood the driver's count in, so CI never opened one.

These tests hold the class rather than the one check: every construction of the driver under
`src/brain` is handed a queue URL, that URL is derived from the owner's login through the session
pooler and never the application's transaction pooler, and what the application derives is the
worker's own `QUEUE_URL` in the product's compose files, so nothing new has to reach an install.

Task ids: M7.1.5
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops import queue
from brain.ops.queue import (
    SESSION_POOLER_HOST,
    QueueError,
    queue_url_for,
    queue_url_of,
    queue_url_refusals,
)
from brain.settings import settings_from

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "brain"
SESSION_POOLER = "postgresql+psycopg://brain:pw@pgbouncer-session:5432/brain"
TRANSACTION_POOLER = "postgresql+psycopg://brain:pw@pgbouncer:5432/brain"


def driver_constructions() -> list[tuple[str, int, str]]:
    """Every `queue_app(...)` call under `src/brain`, with the source of its first argument."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "queue_app"
                and node.args
            ):
                where = str(path.relative_to(ROOT))
                found.append((where, node.lineno, ast.unparse(node.args[0])))
    return found


def test_every_construction_of_the_driver_is_handed_a_queue_url() -> None:
    """**The class.** Delete this and the next opener written from the pattern beside it takes
    `database_url` again, passes every test that stands the driver in, and is refused on every
    install."""
    found = driver_constructions()
    assert len(found) >= 6, found
    wrong = [one for one in found if "queue" not in one[2].lower()]
    assert wrong == []
    assert not [one for one in found if "database_url" in one[2]]


def test_the_queue_url_is_the_owner_login_through_the_session_pooler() -> None:
    """Derived from the owner's login the process already has: a transaction pooler's host
    becomes the session pooler's, the login and database are kept, a pooler-only marker is
    dropped, and a direct URL is left as it is. Delete this and the derivation can hand back
    the transaction pooler, which a queue refuses, or a different login from the worker's."""
    derived = queue_url_for(TRANSACTION_POOLER + "?prepare_threshold=0&sslmode=disable")
    assert derived == SESSION_POOLER + "?sslmode=disable"
    assert queue_url_refusals(derived, app_url=TRANSACTION_POOLER) == ()
    direct = "postgresql://postgres:pw@localhost:5432/brain"
    assert queue_url_for(direct) == direct
    assert queue_url_for("  ") == ""
    owner = settings_from(
        {
            "DATABASE_URL": "postgresql+psycopg://brain_app:pw@pgbouncer:5432/brain",
            "BRAIN_MIGRATION_DATABASE_URL": TRANSACTION_POOLER,
        }
    )
    assert queue_url_of(owner) == SESSION_POOLER
    assert queue_url_of(settings_from({"DATABASE_URL": TRANSACTION_POOLER})) == SESSION_POOLER
    assert queue_url_of(settings_from({})) == ""
    assert queue_url_of(None) == ""


def compose(name: str) -> dict[str, Any]:
    document = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
    return dict(document["services"])


def test_what_the_application_derives_is_exactly_what_the_product_hands_the_worker() -> None:
    """The application's DATABASE_URL is refused as a queue, which is why the old callers were
    refused on every install; derived, it is the worker's QUEUE_URL to the character, and the
    host it names is a service the worker's overlay composes. Delete this and a compose change
    to either pooler leaves the application's queue pointing somewhere nothing listens."""
    base, worker = compose("docker-compose.yml"), compose("docker-compose.worker.yml")
    app_url = str(base["app"]["environment"]["DATABASE_URL"])
    assert queue_url_refusals(app_url)
    assert queue_url_for(app_url) == str(worker["brain-worker"]["environment"]["QUEUE_URL"])
    assert SESSION_POOLER_HOST in worker and "pgbouncer" in base


def test_the_intake_queue_opens_the_driver_on_the_queue_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opened on the queue's URL, and refused before any driver when a process has none. Delete
    this and the upload route's count can be built from the application's URL again."""
    from brain import knowledge_intake_routes
    from brain.ops import worker

    opened: list[str] = []

    class OpenedError(Exception):
        pass

    def recorded(url: str, **_: Any) -> Any:
        opened.append(url)
        raise OpenedError

    monkeypatch.setattr(queue, "queue_app", recorded)
    monkeypatch.setattr(worker, "register_tasks", lambda *_, **__: None)
    with pytest.raises(OpenedError):
        asyncio.run(
            knowledge_intake_routes.DriverQueue(
                SESSION_POOLER, database_url=TRANSACTION_POOLER
            ).counts()
        )
    assert opened == [SESSION_POOLER]
    with pytest.raises(QueueError, match="no queue connection"):
        asyncio.run(knowledge_intake_routes.DriverQueue("").counts())
    assert opened == [SESSION_POOLER]


def test_the_check_says_it_was_not_run_where_the_process_has_no_queue() -> None:
    """Delete this and a process with no queue reports the install's queue as broken."""
    from brain.ops.acceptance import CheckNotRunError
    from brain.ops.acceptance_ingest import a_full_ingestion_queue_refuses_with_a_retry_hint

    class Harness:
        settings = settings_from({})

    with pytest.raises(CheckNotRunError, match="names no database for the queue"):
        asyncio.run(a_full_ingestion_queue_refuses_with_a_retry_hint(Harness()))  # type: ignore[arg-type]
