"""Three console controls followed past their row to the behaviour they change, with no database.

`docs/admin-console.md` asks for every control to be proved end to end: the write followed to
the row it writes, to the audit entry it leaves, and to the behaviour it changes.
`docs/console-audit.md` measures which writes the console sends have all three, and on
2026-09-17 the Scheduled jobs and Features controls had the first and not the third. Each half
was tested and nothing joined them: `tests/unit/test_jobs_routes.py` watched a pause land in
`ops.setting`, and `tests/unit/test_schedule_control.py` handed the tick a set of paused names
it had built itself, so a pause the route wrote under a key the tick does not read would have
passed both.

**The join is the row, read the way the worker reads it.** Each test presses the control over
HTTP against `ops.setting` held in memory, then reads what was written through the functions the
tick reads it with, `values_under` and `paused_in` or `requested_in`, and asks
`chosen_this_tick` what the next tick starts. The only thing not exercised is the session that
carries the row from the table to those functions, which is a select over one namespace and is
what `tests/fixtures/setting_rows.py` answers.

**What is not here, and why.** The audit entry. `ops.setting` has no audit trigger, which
migration `0004` records as a gap rather than a decision: a switch is attributed only on its own
row, by `updated_by` and `updated_at`, and the ledger has no subject kind for a setting.
`docs/console-audit.md` lists these writes as unproved to the ledger for that reason, rather
than a test here pretending otherwise.

Task ids: M27.8.17
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
from brain.feature_routes import FEATURE_AUTHORITY
from brain.jobs_routes import SCHEDULE_AUTHORITY
from brain.ops.schedule import Owed
from brain.ops.schedule_control import (
    PAUSE_NAMESPACE,
    RUN_NAMESPACE,
    Chosen,
    chosen_this_tick,
    paused_in,
    requested_in,
)
from brain.ops.setting_store import values_under
from tests.fixtures.console_http import console_client, post
from tests.fixtures.setting_rows import Result, SettingRows

JOBS = f"{API_PREFIX}/jobs"
FEATURES = f"{API_PREFIX}/install/features"
#: A wired control that is not destructive, so a run of it is never held to reporting.
REFRESH = "spend_report_refresh"
OTHER = "knowledge_reverification"
EVERYWHERE = Scope.unrestricted()

GRANTS = {
    "u_admin": (
        Grant(capability=screen("queue").read.requires, scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
        Grant(capability=SCHEDULE_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=FEATURE_AUTHORITY, scope=EVERYWHERE),
    ),
}


def no_runs(statement: Any) -> Result | None:
    """No control has run: the run records the jobs routes read, answered empty."""
    if not isinstance(statement, Select):
        return None
    columns = [one["name"] for one in statement.column_descriptions]
    if columns in (
        ["name", "started_at", "finished_at", "outcome", "detail"],
        ["name", "finished_at"],
        ["id"],
    ):
        return Result([])
    return None


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def client(settings: SettingRows) -> Iterator[TestClient]:
    with console_client(GRANTS) as (served, stub):
        stub.answerers.extend([settings.answer, no_runs])
        yield served


def owed(name: str, now: datetime) -> Owed:
    return Owed(name=name, due_since=now, late_by=timedelta(0), first_run=True, report_only=False)


def next_tick(settings: SettingRows, now: datetime) -> tuple[Chosen, ...]:
    """What the next tick starts, from the rows the routes wrote, read as the worker reads them."""
    return chosen_this_tick(
        (owed(REFRESH, now), owed(OTHER, now)),
        now=now,
        paused=paused_in(values_under(settings.rows, PAUSE_NAMESPACE)),
        requested=requested_in(values_under(settings.rows, RUN_NAMESPACE)),
        last_attempt={},
    )


def test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused(
    client: TestClient, settings: SettingRows
) -> None:
    """The Features switch followed to what it changes: the Scheduled jobs screen's pause.

    Delete this and the switch is proved to write its row and to be read back on the Features
    screen, and nothing proves that the row it writes is the row the jobs routes consult, so a
    switch under a key the jobs routes do not read would pass every test that exists."""
    refused = post(client, "u_admin", f"{JOBS}/{REFRESH}/pause")
    assert refused.status_code == 404
    assert settings.writes == []

    switched = post(client, "u_admin", f"{FEATURES}/schedule_control", {"on": True})
    assert switched.status_code == 200, switched.text

    paused = post(client, "u_admin", f"{JOBS}/{REFRESH}/pause")
    assert paused.status_code == 200, paused.text
    assert paused_in(values_under(settings.rows, PAUSE_NAMESPACE)) == {REFRESH}


def test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started(
    client: TestClient, settings: SettingRows
) -> None:
    """Pause and resume followed from the button to what the worker starts.

    Delete this and a pause can be written under a key, or with a value, that the tick reads as
    not paused, and the screen says paused while the job runs on schedule."""
    settings.hold("feature.schedule_control", True, value_type="boolean", by="u_admin")
    now = datetime.now(UTC)
    assert Chosen(REFRESH, False, False) in next_tick(settings, now)

    assert post(client, "u_admin", f"{JOBS}/{REFRESH}/pause").status_code == 200
    assert next_tick(settings, now) == (Chosen(OTHER, False, False),)

    assert post(client, "u_admin", f"{JOBS}/{REFRESH}/resume").status_code == 200
    assert Chosen(REFRESH, False, False) in next_tick(settings, now)


def test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused(
    client: TestClient, settings: SettingRows
) -> None:
    """Run now followed from the button to what the worker starts.

    Delete this and run now can write an instant the tick cannot parse, which is a request the
    screen reports as pending for ever and the worker never answers."""
    settings.hold("feature.schedule_control", True, value_type="boolean", by="u_admin")
    assert post(client, "u_admin", f"{JOBS}/{REFRESH}/pause").status_code == 200

    assert post(client, "u_admin", f"{JOBS}/{REFRESH}/run").status_code == 200
    after = datetime.now(UTC) + timedelta(seconds=1)

    assert Chosen(REFRESH, False, True) in next_tick(settings, after)
