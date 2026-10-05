"""Sync now on Staff sources: the scheduled staff sync asked for at once, and what the page is told.

Driven through the real application with the database's four answers stood in: whether the console
may ask for runs, the run request the Scheduled jobs screen's Run now also writes, when the
scheduled control last started, and when any staff run last started.

Task ids: M1.10.2
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain import staff_source_routes
from brain.api import API_PREFIX
from brain.console.reads import Plane
from brain.identity.staff_adapters import SPREADSHEET
from brain.identity.staff_source import STAFF_SOURCE_SETTING
from brain.identity.staff_sync import SYNC_INTERVAL
from brain.install import hold_saved
from brain.ops.controls import CONTROLS
from brain.staff_source_routes import (
    NOT_READ_BY_THE_WORKER,
    SYNC_CONTROL,
    SYNC_PATH,
    SYNC_SWITCHED_OFF,
    SYNC_WAITING,
)
from tests.fixtures.http_client import Response
from tests.unit.test_staff_connect import GRANTS, LARK_SAVED, headers
from tests.unit.test_staff_connect import app as app  # a fixture
from tests.unit.test_staff_connect import client as client  # a fixture
from tests.unit.test_staff_source_routes import STAFF_SOURCE_CAPABILITY, WHOLE, _grant, _plane

LAST = datetime(2999, 3, 1, 2, 0, tzinfo=UTC)


class Session:
    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> Session:
        return self


@dataclass
class Schedule:
    """The four reads and the one write Sync now makes, recorded."""

    switched_on: bool = True
    last: datetime | None = LAST
    requested: datetime | None = None
    started: datetime | None = None
    done: list[str] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def is_on(session: Session, feature: Any) -> bool:
            return self.switched_on

        async def attribute(session: Session, asked: object) -> None:
            self.done.append("attributed")

        async def request_run(session: Session, name: str, *, at: datetime, by: str) -> None:
            self.done.append(f"{name} asked by {by}")

        async def run_requests(session: Session) -> dict[str, datetime]:
            return {} if self.requested is None else {SYNC_CONTROL: self.requested}

        async def last_attempts(session: Session) -> dict[str, datetime]:
            return {} if self.last is None else {SYNC_CONTROL: self.last}

        async def read_last_started(session: Session) -> datetime | None:
            return self.started

        monkeypatch.setattr(staff_source_routes, "sessions_of", lambda _: Session)
        monkeypatch.setattr(staff_source_routes, "is_on", is_on)
        monkeypatch.setattr(staff_source_routes, "attribute", attribute)
        monkeypatch.setattr(staff_source_routes, "request_run", request_run)
        monkeypatch.setattr(staff_source_routes, "run_requests", run_requests)
        monkeypatch.setattr(staff_source_routes, "last_attempts", last_attempts)
        monkeypatch.setattr(staff_source_routes, "read_last_started", read_last_started)


@pytest.fixture(autouse=True)
def page_readers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everybody here but `u_none` reads the Staff sources page, so a refusal below is about the
    connect authority and not the page."""
    page = (_grant(STAFF_SOURCE_CAPABILITY, WHOLE), _plane(Plane.CONFIGURATION))
    for pid in ("u_admin", "u_wide", "u_narrow"):
        monkeypatch.setitem(GRANTS, pid, (*GRANTS[pid], *page))


@pytest.fixture
def reads_lark() -> Iterator[None]:
    before = hold_saved(LARK_SAVED)
    yield
    hold_saved(before)


def press(c: TestClient, pid: str) -> Response:
    answer: Response = c.post(f"{API_PREFIX}{SYNC_PATH}", headers=headers(pid), json={})
    return answer


def look(c: TestClient, pid: str) -> dict[str, Any]:
    answer: Response = c.get(f"{API_PREFIX}{SYNC_PATH}", headers=headers(pid))
    assert answer.status_code == 200, answer.text
    found: dict[str, Any] = answer.json()
    return found


def test_sync_now_asks_the_scheduled_staff_sync_and_nothing_else() -> None:
    """The control Sync now asks for is the one whose runner is the staff sync. Delete this and
    the name can drift to a control that runs something else, or none, and the button asks for a
    run nothing makes."""
    [control] = [one for one in CONTROLS if one.name == SYNC_CONTROL]

    assert "brain.ops.staff_sync_run:run_staff_sync_now" in control.symbols
    assert control.every == SYNC_INTERVAL


def test_a_press_is_written_attributed_as_the_scheduled_run_and_the_page_is_told_it_waits(
    client: TestClient, reads_lark: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and Sync now can stop asking for the run, ask for another control, or write
    the request without the ledger naming who pressed it."""
    schedule = Schedule()
    schedule.install(monkeypatch)

    answer = press(client, "u_admin")

    assert answer.status_code == 200, answer.text
    assert schedule.done == ["attributed", f"{SYNC_CONTROL} asked by u_admin"]
    assert answer.json()["waiting"] is True
    assert answer.json()["told"] == SYNC_WAITING
    assert answer.json()["next_run_at"] == (LAST + SYNC_INTERVAL).isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("pid", ["u_wide", "u_narrow", "u_none", "u_prefix"])
def test_a_reader_who_may_not_connect_a_source_cannot_press_it_and_is_told_nothing(
    client: TestClient, reads_lark: None, monkeypatch: pytest.MonkeyPatch, pid: str
) -> None:
    """Sync now applies the list, so it asks what Apply the first sync asks: both authorities over
    everything. Delete this and anybody who can read a setting can make the worker apply the
    company's staff list, or learn when it last ran."""
    schedule = Schedule()
    schedule.install(monkeypatch)

    assert press(client, pid).status_code == 404
    assert schedule.done == []
    assert look(client, pid) == {
        "may_sync": False,
        "last_run_at": None,
        "next_run_at": None,
        "requested_at": None,
        "waiting": False,
        "told": "",
    }


def test_a_source_the_worker_cannot_read_or_a_console_that_may_not_ask_is_refused_in_words(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a press waits for a run that cannot happen, or is written on an install
    whose administrator switched console job control off."""
    schedule = Schedule()
    schedule.install(monkeypatch)
    before = hold_saved({STAFF_SOURCE_SETTING: SPREADSHEET})
    try:
        sheet = press(client, "u_admin")
    finally:
        hold_saved(before)
    off = Schedule(switched_on=False)
    off.install(monkeypatch)
    hold_saved(LARK_SAVED)
    try:
        switched = press(client, "u_admin")
    finally:
        hold_saved(before)

    assert (sheet.status_code, sheet.json()["message"]) == (422, NOT_READ_BY_THE_WORKER)
    assert (switched.status_code, switched.json()["message"]) == (422, SYNC_SWITCHED_OFF)
    assert schedule.done == []
    assert off.done == []


def test_the_page_is_told_the_last_and_next_runs_and_waits_until_a_run_starts_after_the_press(
    client: TestClient, reads_lark: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the page cannot say when the scheduled sync runs, or says a press waits
    for ever, or never."""
    pressed = datetime.now(tz=UTC) - timedelta(seconds=5)
    Schedule(requested=pressed).install(monkeypatch)
    waiting = look(client, "u_admin")
    Schedule(requested=pressed, started=pressed + timedelta(seconds=1)).install(monkeypatch)
    ran = look(client, "u_admin")
    Schedule(last=None).install(monkeypatch)
    never = look(client, "u_admin")

    assert waiting["waiting"] is True
    assert waiting["told"] == SYNC_WAITING
    assert ran["waiting"] is False
    assert ran["requested_at"] is None
    assert ran["last_run_at"] is not None
    assert ran["next_run_at"] is not None
    assert (never["last_run_at"], never["next_run_at"]) == (None, None)
