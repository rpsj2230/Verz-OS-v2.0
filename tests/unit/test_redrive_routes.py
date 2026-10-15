"""Run again, from the Scheduled jobs screen, over HTTP: who may press it, what a press writes, and
what the list says of it.

Driven through the real application with the dead letters and `ops.setting` held in memory. The
press is followed to the row the worker's minute reads (`tests/unit/test_redrive_control.py` follows
that row into the minute, and `tests/unit/test_dead_letter.py` follows the minute into the driver's
tables). Every refusal has a sibling proving the same press works for somebody who may make it.

Task ids: M27.13.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.jobs_routes import (
    REDRIVE_SWITCHED_OFF,
    REFERENCES_HAVE_OUTLIVED_THE_JOB,
    SCHEDULE_AUTHORITY,
)
from brain.ops.redrive_control import (
    ANSWERED_NAMESPACE,
    ASKED_NAMESPACE,
    COULD_NOT_PUT_BACK,
    NOT_ANSWERED_YET,
    PUT_BACK,
)
from brain.tables.dead_letter import DeadLetterRow
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import Result, SettingRows

DEAD = f"{API_PREFIX}/jobs/dead"
EVERYWHERE = Scope.unrestricted()
QUEUE_READ = screen("queue").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)

#: `u_admin` sees and controls every job. `u_wide` sees and does not control. `u_narrow` holds the
#: authority and may see no job, so may not run a dead letter again either. `u_none` holds nothing.
GRANTS = {
    "u_admin": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
        Grant(capability=SCHEDULE_AUTHORITY, scope=EVERYWHERE),
    ),
    "u_wide": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_narrow": (Grant(capability=SCHEDULE_AUTHORITY, scope=EVERYWHERE),),
    "u_none": (),
}

#: A clock nobody's wall clock will reach is not usable here, because the route takes the real
#: time from the request; the rows are dated relative to it instead.
RECENTLY = datetime.now(UTC) - timedelta(hours=1)
LONG_AGO = datetime.now(UTC) - timedelta(days=4000)


def a_dead_letter(job_id: str, *, set_aside_at: datetime = RECENTLY) -> DeadLetterRow:
    return DeadLetterRow(
        job_id=job_id,
        task="brain.controls.run",
        principal_id="system",
        traffic_class="system",
        reason="quarantined_after_a_stop",
        attempts=1,
        set_aside_at=set_aside_at,
    )


class DeadLetters:
    """`ops.dead_letter` held in memory, answering the list and the single-row lookup."""

    def __init__(self) -> None:
        self.rows: list[DeadLetterRow] = [a_dead_letter("41"), a_dead_letter("42")]

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        if [one["name"] for one in statement.column_descriptions] != ["DeadLetterRow"]:
            return None
        asked = statement.compile().params.get("job_id_1")
        return Result(one for one in self.rows if asked is None or one.job_id == asked)


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def dead() -> DeadLetters:
    return DeadLetters()


@pytest.fixture
def served(settings: SettingRows, dead: DeadLetters) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, dead.answer])
        yield client, stub


def switched_on(settings: SettingRows) -> None:
    settings.hold("feature.job_redrive", True, value_type="boolean", by="u_admin")


def test_pressing_run_again_writes_the_instant_the_worker_reads_and_says_who_pressed(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """The positive case: the switch on, the authority over everything, the job visible.

    Delete this and every refusal below is satisfied by a route that refuses everybody."""
    client, stub = served
    switched_on(settings)
    before = datetime.now(UTC)

    answer = post(client, "u_admin", f"{DEAD}/41/redrive")

    assert answer.status_code == 200, answer.text
    assert answer.json()["job_id"] == "41"
    assert answer.json()["asked_by"] == "u_admin"
    assert answer.json()["standing"] == NOT_ANSWERED_YET
    written = settings.writes[-1]
    assert written["key"] == f"{ASKED_NAMESPACE}.job_41"
    assert written["value_type"] == "string"
    assert written["updated_by"] == "u_admin"
    assert before <= datetime.fromisoformat(written["value"]) <= datetime.now(UTC)
    assert stub.commits == 1
    assert ("brain.actor_id", "u_admin") in stub.attributions


def test_the_list_says_what_became_of_each_ask_and_nothing_of_a_job_nobody_asked_about(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and the screen cannot tell a person whether their press did anything."""
    client, _ = served
    switched_on(settings)
    at = datetime.now(UTC).isoformat()
    settings.hold(f"{ASKED_NAMESPACE}.job_41", at, value_type="string", by="u_admin")
    settings.hold(f"{ASKED_NAMESPACE}.job_42", at, value_type="string", by="u_admin")
    settings.hold(
        f"{ANSWERED_NAMESPACE}.job_42",
        {"at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(), "put_back": True},
        value_type="json",
        by="system",
    )

    body = get(client, "u_admin", DEAD).json()

    standing = {one["job_id"]: one["run_again_standing"] for one in body["items"]}
    assert standing == {"41": NOT_ANSWERED_YET, "42": PUT_BACK}
    assert body["run_again_switched_on"] is True
    assert body["may_run_again"] is True

    settings.hold(
        f"{ANSWERED_NAMESPACE}.job_41",
        {"at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(), "put_back": False},
        value_type="json",
        by="system",
    )
    again = get(client, "u_admin", DEAD).json()
    assert {one["job_id"]: one["run_again_standing"] for one in again["items"]}["41"] == (
        COULD_NOT_PUT_BACK
    )


def test_a_job_nobody_asked_about_has_no_ask_on_its_row(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a row says it was asked about when nobody asked."""
    client, _ = served
    body = get(client, "u_admin", DEAD).json()
    assert {one["run_again_asked_at"] for one in body["items"]} == {None}
    assert {one["run_again_standing"] for one in body["items"]} == {None}
    assert body["run_again_switched_on"] is False


def test_pressing_is_refused_by_name_while_the_switch_is_off(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and the `job_redrive` switch reaches nothing: the control works on an install
    that never switched it on."""
    client, stub = served

    answer = post(client, "u_admin", f"{DEAD}/41/redrive")

    assert answer.status_code == 404
    assert REDRIVE_SWITCHED_OFF in answer.json()["message"]
    assert settings.writes == []
    assert stub.commits == 0


def test_an_answered_ask_is_still_shown_while_the_switch_is_off(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """A switch gates the door and never traps what it opened: an ask made while it was on keeps
    its standing on the list. Delete this and turning the switch off hides what the worker did."""
    client, _ = served
    settings.hold(
        f"{ASKED_NAMESPACE}.job_41",
        datetime.now(UTC).isoformat(),
        value_type="string",
        by="u_admin",
    )

    body = get(client, "u_admin", DEAD).json()

    assert {one["job_id"]: one["run_again_standing"] for one in body["items"]}["41"] == (
        NOT_ANSWERED_YET
    )


@pytest.mark.parametrize("pid", ["u_none", "u_wide", "u_narrow"])
def test_a_caller_who_may_not_press_gets_the_refusal_an_unknown_job_gets(
    pid: str, settings: SettingRows
) -> None:
    """No authority, or the authority without the job's read: one refusal, the same words for a job
    that exists as for one that does not, so the refusal says nothing about what is set aside, and
    for a caller without the authority the same with a database and without.

    Delete this and a reader without the authority learns which job ids exist from the difference
    between two refusals, or a caller who guessed an id writes an ask."""
    switched_on(settings)
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, DeadLetters().answer])
        existing = post(client, pid, f"{DEAD}/41/redrive")
        unknown = post(client, pid, f"{DEAD}/9999/redrive")
        assert stub.commits == 0
    assert existing.status_code == unknown.status_code == 404
    assert existing.json()["message"] == unknown.json()["message"]
    if pid != "u_narrow":
        # Without the authority the refusal comes before the database is asked, so it is the same
        # on a process that has none. With it, the job's own read is decided from the row.
        with console_client(GRANTS, database=False) as (client, _):
            without = post(client, pid, f"{DEAD}/41/redrive")
        assert without.status_code == 404
        assert without.json()["message"] == existing.json()["message"]
    assert settings.writes == []


def test_a_job_that_is_not_digits_is_the_same_refusal_as_one_nobody_set_aside(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a path segment that is not a job id reaches the database, or is refused in
    different words from an unknown one."""
    client, _ = served
    switched_on(settings)

    unknown = post(client, "u_admin", f"{DEAD}/9999/redrive")
    odd = post(client, "u_admin", f"{DEAD}/not-a-number/redrive")

    assert unknown.status_code == odd.status_code == 404
    assert unknown.json()["message"] == odd.json()["message"]
    assert settings.writes == []


def test_a_dead_letter_whose_references_are_gone_is_refused_in_words(
    served: tuple[TestClient, Stub], dead: DeadLetters, settings: SettingRows
) -> None:
    """Delete this and a person asks for a run the screen has already said would fail."""
    client, stub = served
    switched_on(settings)
    dead.rows.append(a_dead_letter("77", set_aside_at=LONG_AGO))

    answer = post(client, "u_admin", f"{DEAD}/77/redrive")

    assert answer.status_code == 404
    assert REFERENCES_HAVE_OUTLIVED_THE_JOB in answer.json()["message"]
    assert settings.writes == []
    assert stub.commits == 0


def test_a_password_only_sign_in_cannot_press_run_again(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """The authority is an `admin:` verb, which the gate withholds from a session without a
    second factor. Delete this and a stolen password can make the worker run a job again."""
    client, _ = served
    switched_on(settings)

    answer = post(client, "u_admin", f"{DEAD}/41/redrive", strong=False)

    assert answer.status_code == 404
    assert settings.writes == []
