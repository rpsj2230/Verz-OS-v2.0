"""The object store as the lifespan attaches it, and the recovery screen reading the backup bucket.

`brain.app` connects to the store once at start and builds two things over it: the backup bucket's
reader and the artifact store. These tests replace only `object_store_at_start`, with a store over
`tests.fixtures.fake_s3.FakeS3` and the real client, so everything after it is what an install
runs: the lifespan's attachments, the recovery route reading the bucket once in a thread,
`brain.ops.backup_manifest` parsing what came back, and the panel built from it.

The manifests are written as the JSON `ops/backup/brain-backup` writes, and the drill record as a
runner would write it, because a test handing the route a ready `Backup` would test the consumer
twice. They are dated relative to the wall clock, because the route reads the present from it.

Task ids: M27.7.26
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import brain.app
from brain.app import create_app
from brain.console.installation import Source
from brain.install_routes import (
    NOTHING_HERE_READS_THE_BACKUP_BUCKET,
    THE_BACKUP_BUCKET_DID_NOT_ANSWER,
)
from brain.ops.backup_manifest import DRILL_SUFFIX, MANIFEST_SUFFIX
from brain.ops.object_store import ObjectStore, S3Backend, StoreCredential
from brain.ops.recovery import Check, Coverage
from brain.ops.storage import Backend, ObjectKind, bucket_for, config_for
from brain.settings import Settings
from tests.fixtures.fake_s3 import FakeS3
from tests.fixtures.no_database import as_if_ci_had_a_database
from tests.unit.test_install_routes import RECOVERY_PATH, _app, _wiring, get

KEY = StoreCredential(access_key_id="brain-test-access", secret_access_key="brain-test-secret")
ENDPOINT = "http://objects.example.test:8333"
BACKUPS = bucket_for(ObjectKind.DATABASE_DUMP).name


def _stamp(at: datetime) -> str:
    return at.isoformat()


def manifest(backup_id: str, finished: datetime) -> bytes:
    """A manifest as `ops/backup/brain-backup` writes one."""
    return json.dumps(
        {
            "backup_id": backup_id,
            "coverage": Coverage.DATABASE.value,
            "method": "full",
            "destination": f"s3://{BACKUPS}",
            "started_at": _stamp(finished - timedelta(minutes=3)),
            "finished_at": _stamp(finished),
            "recoverable_to": _stamp(finished),
            "size_bytes": 4096,
        }
    ).encode()


def drill(backup_id: str, started: datetime) -> bytes:
    """A drill record asking every required check, each answered as passed."""
    return json.dumps(
        {
            "backup_id": backup_id,
            "started_at": _stamp(started),
            "finished_at": _stamp(started + timedelta(minutes=20)),
            "into_scratch": True,
            "checks": [
                {"check": one.value, "passed": True, "detail": "answered as expected"}
                for one in Check
            ],
        }
    ).encode()


def a_bucket() -> FakeS3:
    now = datetime.now(UTC)
    copy = "database-copy-one"
    return FakeS3(credential=KEY).holding(
        BACKUPS,
        {
            f"{copy}.dump": b"\x00" * 4096,
            f"{copy}{MANIFEST_SUFFIX}": manifest(copy, now - timedelta(hours=2)),
            f"{copy}-rehearsal{DRILL_SUFFIX}": drill(copy, now - timedelta(hours=1)),
        },
    )


def _at_start(store: FakeS3) -> Callable[[str, str], ObjectStore]:
    """What the lifespan calls instead of reading the vault: a client over `store`."""

    def at_start(_address: str, _token: str) -> ObjectStore:
        backend = S3Backend(
            config_for(Backend.SEAWEEDFS, endpoint_url=ENDPOINT), KEY, transport=store.transport()
        )
        return ObjectStore(backend=backend, prefix="brain")

    return at_start


def connected_to(monkeypatch: pytest.MonkeyPatch, store: FakeS3) -> FastAPI:
    """The real application, whose lifespan connects to `store` instead of reading the vault."""
    monkeypatch.setattr(brain.app, "object_store_at_start", _at_start(store))
    return _app()


@pytest.fixture
def bucket() -> Iterator[FakeS3]:
    yield a_bucket()


def test_the_recovery_screen_measures_the_last_backup_and_the_last_verified_restore_from_the_bucket(
    monkeypatch: pytest.MonkeyPatch, bucket: FakeS3
) -> None:
    """**The gap this closes.** The lifespan attaches a reader over the store it connected to, the
    route reads the manifest and the drill record through the real client, and the field the
    screen is named after is measured rather than unknown. Delete this and the reader can go
    unattached with every route test still green, because those attach a list by hand."""
    app = connected_to(monkeypatch, bucket)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        assert app.state.backup_objects is not None
        body = get(c, "u_wide", RECOVERY_PATH).json()

    assert body["unread"] == ""
    panel = body["panel"]
    assert panel["unreadable"] == []
    assert panel["last_verified"]["source"] == Source.MEASURED.value
    database = next(one for one in panel["copies"] if one["coverage"] == Coverage.DATABASE.value)
    assert Source.MEASURED.value in {fact["source"] for fact in database["facts"]}
    assert panel["measured_rto_seconds"] == 20 * 60


def test_the_recovery_screen_never_fetches_a_copy_to_find_its_description(
    monkeypatch: pytest.MonkeyPatch, bucket: FakeS3
) -> None:
    """Delete this and opening the screen pulls every nightly copy of the database into the web
    process, which is invisible until the copy is large."""
    app = connected_to(monkeypatch, bucket)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        assert get(c, "u_wide", RECOVERY_PATH).status_code == 200

    fetched = [path for method, path, query in bucket.asked if method == "GET" and not query]
    assert len(fetched) == 2
    assert not any(path.endswith(".dump") for path in fetched)


def test_a_backup_bucket_that_does_not_answer_is_said_in_words_and_draws_no_panel(
    monkeypatch: pytest.MonkeyPatch, bucket: FakeS3
) -> None:
    """A store that is down is not an install with no copies. Delete this and the route answers a
    500, or a panel over nothing that says nothing was ever copied."""
    bucket.down = True
    app = connected_to(monkeypatch, bucket)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        response = get(c, "u_wide", RECOVERY_PATH)

    assert response.status_code == 200
    assert response.json()["panel"] is None
    assert response.json()["unread"] == THE_BACKUP_BUCKET_DID_NOT_ANSWER
    assert response.json()["rehearsal"] is not None


def test_a_refused_reader_cannot_make_the_bucket_be_read(
    monkeypatch: pytest.MonkeyPatch, bucket: FakeS3
) -> None:
    """The screen's permission is decided before the store is asked. Delete this and the order can
    be reversed, so anybody holding a token lists the backup bucket on every request."""
    app = connected_to(monkeypatch, bucket)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        assert get(c, "u_elsewhere", RECOVERY_PATH).status_code == 404
        assert bucket.asked == []
        assert get(c, "u_wide", RECOVERY_PATH).status_code == 200
    assert bucket.asked != []


def test_a_process_connected_to_no_store_attaches_no_reader_and_says_nobody_looked() -> None:
    """No vault, so no store, so no reader, and the sentence rather than a panel. Delete this and
    the lifespan could attach a reader over nothing, which raises on the first opening."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        assert app.state.object_store.backend is None
        assert app.state.object_store.unconnected != ""
        assert app.state.backup_objects is None
        assert (
            get(c, "u_wide", RECOVERY_PATH).json()["unread"] == NOTHING_HERE_READS_THE_BACKUP_BUCKET
        )


def test_the_lifespan_builds_no_artifact_store_without_a_database_and_closes_the_client_after(
    monkeypatch: pytest.MonkeyPatch, bucket: FakeS3
) -> None:
    """The records are rows, so no database is no artifact store, and the store's HTTP client is
    closed at shutdown. Delete this and a process with no database lists nothing it can read, or
    leaks a client per restart in a test run."""
    # CI's environment carries a database, so "no database" is pinned rather than assumed; see
    # `tests.fixtures.no_database`.
    as_if_ci_had_a_database(monkeypatch)
    monkeypatch.setattr(brain.app, "object_store_at_start", _at_start(bucket))
    app = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False):
        assert app.state.artifacts is None
        assert app.state.artifact_source is None
        backend = app.state.object_store.backend
        assert isinstance(backend, S3Backend)
    with pytest.raises(RuntimeError):
        backend.get_object(BACKUPS, "anything")
