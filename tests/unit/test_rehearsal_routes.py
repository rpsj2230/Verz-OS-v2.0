"""Asking the server for a restore rehearsal, and what the Recovery screen then says.

Driven through the real application, with the people, tokens and gate imported from
`tests/unit/test_install_routes.py`, the bucket replaced by a dictionary behind the product's own
reader (`brain.ops.object_store.backup_objects`) so the request a press leaves is read back by the
same code that reads it on an install, and the switch rows held in memory.

**The press is held to what it can truthfully say.** It leaves a request and answers that one was
asked. No test here has a server, so none can say a rehearsal started, and the screen's wording is
held to say the same.

**Every refusal has a sibling that works.** A route tested only by its refusals is satisfied by one
that refuses everybody.

Task ids: M30.3.9
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.core.entitlement import Grant
from brain.ops.drill_service import REQUEST_KEY
from brain.ops.features_declared.backup_drill_requests import BACKUP_DRILL_REQUESTS
from brain.ops.object_store import backup_objects
from brain.ops.storage import StoreUnansweredError
from brain.rehearsal_routes import REHEARSAL_AUTHORITY
from tests.unit.test_api_routes import token_for
from tests.unit.test_install_routes import (
    INSTALL_GRANTS,
    RECOVERY_PATH,
    SECOND_FACTOR,
    WHOLE,
    _app,
    _wiring,
    get,
)

ASK_PATH = f"{API_PREFIX}/install/recovery/rehearsal"
BACKUPS = "backups"


class Bucket:
    """The backup bucket as a dictionary, with the calls it received."""

    def __init__(self, *, refuses_writes: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []
        self.refuses_writes = refuses_writes

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        assert bucket_name == BACKUPS
        if self.refuses_writes:
            msg = "the object store answered 403 (AccessDenied) to PUT in bucket 'backups'"
            raise StoreUnansweredError(msg)
        self.puts.append(key)
        self.objects[key] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.objects[key]

    def delete_object(self, bucket_name: str, key: str) -> None:
        self.objects.pop(key, None)

    def list_objects(self, bucket_name: str, prefix: str) -> Iterator[str]:
        yield from sorted(self.objects)


def switch(on: bool | None) -> Any:
    """Sessions whose `ops.setting` holds this feature's row, or none."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from tests.fixtures import console_http
    from tests.fixtures.setting_rows import SettingRows

    rows = SettingRows()
    if on is not None:
        rows.hold(BACKUP_DRILL_REQUESTS.key, on, value_type="boolean")
    console_http._STUB = console_http.Stub()
    console_http._STUB.answerers.append(rows.answer)
    return async_sessionmaker(class_=console_http.StubSession)


@pytest.fixture
def administrator(monkeypatch: pytest.MonkeyPatch) -> None:
    """`u_admin` also holds the install authority, which no person in the shared table does."""
    monkeypatch.setitem(
        INSTALL_GRANTS,
        "u_admin",
        (*INSTALL_GRANTS["u_admin"], Grant(capability=REHEARSAL_AUTHORITY, scope=WHOLE)),
    )


def post(c: TestClient, pid: str) -> Any:
    token = token_for(pid, claims=SECOND_FACTOR)
    return c.post(ASK_PATH, headers={"authorization": f"Bearer {token}"}, json={})


def wired(c: TestClient, app: Any, *, on: bool | None, bucket: Bucket | None) -> None:
    app.state.gate = _wiring()
    app.state.db_sessions = switch(on)
    if bucket is not None:
        app.state.object_store = SimpleNamespace(backend=bucket)
        app.state.backup_objects = backup_objects(bucket)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------- the ask


def test_a_press_with_the_switch_on_leaves_one_request_in_the_bucket_and_says_only_that(
    administrator: None,
) -> None:
    """The positive case. Delete this and the route can refuse everybody, or answer that a
    rehearsal started, which the product cannot know."""
    bucket = Bucket()
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        wired(c, app, on=True, bucket=bucket)
        answer = post(c, "u_admin")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["already_asked"] is False
    assert "does not say it has started" in body["says"]
    assert bucket.puts == [REQUEST_KEY]
    left = json.loads(bucket.objects[REQUEST_KEY])
    assert left["requested_by"] == "u_admin"
    assert datetime.fromisoformat(left["requested_at"]).tzinfo is not None


def test_a_second_press_while_one_waits_asks_nothing_more(administrator: None) -> None:
    """Delete this and two presses queue two scratch databases, each holding every record."""
    bucket = Bucket()
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        wired(c, app, on=True, bucket=bucket)
        first = post(c, "u_admin").json()
        second = post(c, "u_admin").json()
    assert second["already_asked"] is True
    assert second["requested_at"] == first["requested_at"]
    assert bucket.puts == [REQUEST_KEY]


def test_a_press_with_the_switch_off_or_never_set_leaves_nothing(administrator: None) -> None:
    """The switch is the owner's answer to item 235. Delete this and the request is written on an
    install where nothing reads it."""
    for state in (False, None):
        bucket = Bucket()
        app = _app()
        with TestClient(app, raise_server_exceptions=False) as c:
            wired(c, app, on=state, bucket=bucket)
            answer = post(c, "u_admin")
        assert answer.status_code == 404
        assert "switched off" in answer.text
        assert bucket.puts == []


def test_a_caller_without_the_install_authority_is_refused_as_anyone_the_screen_does_not_answer(
    administrator: None,
) -> None:
    """Holding the recovery screen's read is not enough to cause a rehearsal. Delete this and
    whoever may read the backup page can load every record into a second place. The refusal is the
    one an unknown address gets, so it does not say the control exists."""
    bucket = Bucket()
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        wired(c, app, on=True, bucket=bucket)
        reader = post(c, "u_wide")
        nobody = post(c, "u_none")
    assert reader.status_code == nobody.status_code == 404
    assert reader.json()["message"] == nobody.json()["message"]
    assert "rehearsal" not in reader.text.lower()
    assert bucket.puts == []


def test_a_press_on_a_process_not_connected_to_the_bucket_says_so_and_asks_nothing(
    administrator: None,
) -> None:
    """Delete this and the press reports a request left nowhere."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        wired(c, app, on=True, bucket=None)
        answer = post(c, "u_admin")
    assert answer.status_code == 404
    assert "not connected to the backup bucket" in answer.text


def test_a_bucket_that_refuses_the_write_is_a_failure_that_names_no_store_detail(
    administrator: None,
) -> None:
    """The store's own words name a bucket and a key. Delete this and they reach a page."""
    bucket = Bucket(refuses_writes=True)
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        wired(c, app, on=True, bucket=bucket)
        answer = post(c, "u_admin")
    assert answer.status_code >= 500
    assert "AccessDenied" not in answer.text
    assert "backups" not in answer.text


def test_the_ask_is_a_post_the_recovery_address_stays_a_read_and_both_are_in_the_api_document() -> (
    None
):
    """Delete this and the control can move to a verb a page prefetches, or the address the screen
    reads can start taking writes."""
    paths = _app().openapi()["paths"]
    assert set(paths[ASK_PATH]) == {"post"}
    assert set(paths[RECOVERY_PATH]) == {"get"}


# ------------------------------------------------------------------------ what the screen says


def recovery(c: TestClient, pid: str = "u_admin") -> Mapping[str, Any]:
    return get(c, pid, RECOVERY_PATH).json()  # type: ignore[no-any-return]


def test_the_screen_draws_the_control_only_when_the_switch_is_on(administrator: None) -> None:
    """The card reads the switch from the server. Delete this and a browser guesses, and a button
    appears that the route then refuses."""
    seen: dict[str, bool] = {}
    for label, state in (("on", True), ("off", False), ("unset", None)):
        app = _app()
        with TestClient(app, raise_server_exceptions=False) as c:
            wired(c, app, on=state, bucket=Bucket())
            card = recovery(c)["rehearsal"]
        seen[label] = card["can_request"]
        if state:
            assert "asks and does not say a rehearsal has started" in card["no_control_here"]
        else:
            assert "no control" in card["no_control_here"]
    assert seen == {"on": True, "off": False, "unset": False}


def test_the_screen_says_a_request_is_waiting_after_a_press_and_when_it_was_made(
    administrator: None,
) -> None:
    """Delete this and a person presses, sees nothing change, and presses again."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        wired(c, app, on=True, bucket=Bucket())
        before = recovery(c)["rehearsal"]
        post(c, "u_admin")
        after = recovery(c)["rehearsal"]
    assert before["request_waiting"] is False and before["requested_at"] is None
    assert after["request_waiting"] is True
    assert datetime.fromisoformat(after["requested_at"]) <= datetime.now(UTC)


# --------------------------------------------------------------- where the copies are, declared


def manifest(*, off_host: bool | None, key: str | None) -> tuple[str, str]:
    document: dict[str, object] = {
        "backup_id": "database-20190101T020000Z",
        "coverage": "database",
        "method": "full",
        "destination": "s3://copies",
        "started_at": "2019-01-01T02:00:00+00:00",
        "finished_at": "2019-01-01T02:04:00+00:00",
        "recoverable_to": "2019-01-01T02:04:00+00:00",
        "size_bytes": 4096,
    }
    if off_host is not None:
        document["off_host"] = off_host
    if key is not None:
        document["key_held_by"] = key
    return ("database-20190101T020000Z.manifest.json", json.dumps(document))


def placement_for(*pairs: tuple[str, str]) -> list[str]:
    from tests.unit.test_install_routes import bucket_holding

    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.backup_objects = bucket_holding(*pairs)
        return list(recovery(c, "u_wide")["placement"])


def test_a_copy_on_the_host_and_unencrypted_is_said_so_on_the_screen() -> None:
    """The two facts the taker declares, read back. Delete this and the screen shows a fresh copy
    and says nothing about it being beside the original and readable by anyone."""
    findings = placement_for(manifest(off_host=False, key="nobody"))
    assert any("same host" in one for one in findings)
    assert any("unencrypted" in one for one in findings)


def test_a_copy_on_another_machine_under_the_clients_key_has_no_placement_finding_about_it() -> (
    None
):
    """The sibling: a good declaration is not accused. Delete this and the finding fires on every
    install and is ignored on the one where it matters. What remains is the object store and the
    configuration, which nothing copies yet and the finding says so."""
    findings = placement_for(manifest(off_host=True, key="client"))
    assert not any(
        "same host" in one or "unencrypted" in one or "platform" in one for one in findings
    )
    assert any(one.startswith("object_store:") for one in findings)


def test_a_manifest_that_declares_neither_is_a_finding_of_its_own_and_not_judged_as_unsafe() -> (
    None
):
    """A manifest from before the fields. Delete this and an old install is told its copies are
    unencrypted when the truth is that nothing recorded it."""
    findings = placement_for(manifest(off_host=None, key=None))
    assert len(findings) == 1
    assert "does not say" in findings[0]


def test_no_copies_at_all_has_no_placement_findings() -> None:
    """The panel already says nothing has been copied. Delete this and the screen says it twice
    in different words."""
    assert placement_for() == []
