"""The migration routes: refused before the database to anybody without the authority, refused while
the switch is off, every package refusal said in the package's words, and the saved documents read
back with what is outstanding computed and never stored.

The stub holds `ops.setting` in memory and answers the read of `ops.migration_record` by kind; the
writes are proved against PostgreSQL by `brain.ops.acceptance_checks_migration_workspace`.

Task ids: M37.1.1.1, M37.1.1.2, M37.1.1.3, M37.1.3.2, M37.1.3.3
Task ids: M37.1.4.1, M37.1.4.2, M37.1.4.3, M37.1.4.4, M37.7.5
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.migration.checklist import CUTOVER_GATED_ACTS
from brain.migration_routes import (
    MIGRATION_AUTHORITY,
    CutoverAsked,
    cutover_view,
    decommission_of,
    parallel_view,
    register_view,
)
from brain.ops import migration_record_store
from brain.ops.features import MIGRATION_WORKSPACE
from brain.routers import ROUTERS
from brain.tables.migration_record import MigrationRecordRow, RecordKind
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import Result, SettingRows

BASE = f"{API_PREFIX}/migration"
EVERYWHERE = Scope.unrestricted()

#: Far outside any plausible wall clock, on purpose: nothing here is about the present.
LONG_AGO = "2019-01-01T00:00:00+00:00"
STARTED = "2019-03-01T00:00:00+00:00"
ENDS = "2019-04-01T00:00:00+00:00"
CUT = "2019-05-01T00:00:00+00:00"
LATER = "2019-05-02T00:00:00+00:00"

GRANTS = {
    "u_admin": (Grant(capability=MIGRATION_AUTHORITY, scope=EVERYWHERE),),
    "u_narrow": (Grant(capability=MIGRATION_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


def a_register(**more: Any) -> dict[str, Any]:
    return {
        "surveyed": ["knowledge", "prompt"],
        "items": [
            {
                "item_id": "k1",
                "holding": "knowledge",
                "name": "Price list",
                "permissions": ["view"],
            },
            {"item_id": "p1", "holding": "prompt", "name": "Quote prompt"},
        ],
        "decisions": [
            {"item_id": "k1", "disposition": "migrate", "because": "It is the company's data"}
        ],
        "mappings": [
            {"old": "view", "capabilities": ["read:price.list"], "because": "Reading is reading"}
        ],
        **more,
    }


def a_period(**more: Any) -> dict[str, Any]:
    return {
        "started_at": STARTED,
        "ends_at": ENDS,
        "criteria": [
            {
                "measure": "questions asked",
                "direction": "at least",
                "threshold": 2,
                "agreed_at": LONG_AGO,
                "because": "Enough to be a sample",
            }
        ],
        "comparisons": [
            {"question": "q1", "asked_at": STARTED, "verdict": "differed"},
            {"question": "q2", "asked_at": STARTED, "verdict": "only one answered"},
        ],
        **more,
    }


def a_cutover(**more: Any) -> dict[str, Any]:
    return {"cut_over_at": CUT, **more}


def held(kind: RecordKind, body: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind.value,
        body=body,
        recorded_by="u_admin",
        recorded_at=datetime(2019, 6, 1, tzinfo=UTC),
    )


class Records:
    """The read of `ops.migration_record` by kind, answering the versions a test holds."""

    def __init__(self) -> None:
        self.rows: list[SimpleNamespace] = []

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        if statement.column_descriptions[0].get("entity") is not MigrationRecordRow:
            return None
        kind = statement.compile().params["kind_1"]
        return Result([one for one in self.rows if one.kind == kind][:1])


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def records() -> Records:
    return Records()


@pytest.fixture
def served(settings: SettingRows, records: Records) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, records.answer])
        yield client, stub


@pytest.fixture
def switched_on(settings: SettingRows) -> None:
    settings.hold(MIGRATION_WORKSPACE.key, True, value_type="boolean")


def put(client: TestClient, pid: str, path: str, body: Any, *, strong: bool = True) -> Any:
    from tests.fixtures.console_http import headers

    return client.put(f"{BASE}{path}", json=body, headers=headers(pid, strong=strong))


def test_the_router_is_mounted_by_the_application() -> None:
    """Delete this and the routes can be written, tested and never served."""
    assert any(getattr(one, "path", "") == BASE for router in ROUTERS for one in router.routes)


# ------------------------------------------------------------------------------ authority
CALLS = (
    ("GET", "", None),
    ("PUT", "/register", a_register()),
    ("PUT", "/parallel", a_period()),
    ("PUT", "/cutover", a_cutover()),
    ("POST", "/cutover/complete", None),
)


def call(client: TestClient, pid: str, method: str, path: str, body: Any) -> Any:
    if method == "GET":
        return get(client, pid, f"{BASE}{path}")
    if method == "PUT":
        return put(client, pid, path, body)
    return post(client, pid, f"{BASE}{path}", body)


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
@pytest.mark.parametrize(("method", "path", "body"), CALLS)
def test_a_caller_without_the_authority_over_everything_is_refused_before_the_database(
    pid: str, method: str, path: str, body: Any
) -> None:
    """The same refusal with a database and without one, naming no capability, and no statement
    reaches a store.

    Delete this and a department-scoped holder keeps a migration for the whole install, or a
    caller with nothing learns whether this process has a pool."""
    with console_client(GRANTS, database=False) as (client, _):
        without = call(client, pid, method, path, body)
    with console_client(GRANTS) as (client, stub):
        with_pool = call(client, pid, method, path, body)
    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert MIGRATION_AUTHORITY.value not in with_pool.json()["message"]
    assert stub.statements == []


def test_a_password_only_sign_in_holding_the_authority_is_refused(
    served: tuple[TestClient, Stub],
) -> None:
    """`brain.gate.admission` withholds `admin:` from a session with no second factor.

    Delete this and a stolen password alone writes a migration record."""
    client, stub = served
    assert put(client, "u_admin", "/register", a_register(), strong=False).status_code == 404
    assert stub.statements == []


# ------------------------------------------------------------------------------- the switch
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", "/register", a_register()),
        ("PUT", "/parallel", a_period()),
        ("PUT", "/cutover", a_cutover()),
        ("POST", "/cutover/complete", None),
    ],
)
def test_every_write_is_refused_while_the_switch_is_off(
    served: tuple[TestClient, Stub], settings: SettingRows, method: str, path: str, body: Any
) -> None:
    """Delete this and a feature that ships off is on for every install the day it arrives."""
    client, stub = served
    refused = call(client, "u_admin", method, path, body)
    assert refused.status_code == 404
    assert "switched off" in refused.json()["message"]
    assert stub.commits == 0
    assert settings.writes == []


# ---------------------------------------------------------------- the package's own words
def test_an_item_of_a_kind_nobody_surveyed_is_refused_in_the_registers_words(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """Delete this and a register can hold an item from a part of the old system nobody opened."""
    client, stub = served
    body = a_register(surveyed=["prompt"])
    refused = put(client, "u_admin", "/register", body)
    assert refused.status_code == 404
    assert "k1" in refused.json()["message"] or "knowledge" in refused.json()["message"]
    assert stub.commits == 0


def test_a_mapping_that_restates_its_own_name_is_refused(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """Delete this and `admin becomes admin` is a decision in a signed document."""
    client, _ = served
    body = a_register(mappings=[{"old": "view", "capabilities": [], "because": "view"}])
    refused = put(client, "u_admin", "/register", body)
    assert refused.status_code == 404
    assert "restating a name" in refused.json()["message"]


def test_a_threshold_agreed_after_the_period_began_is_refused(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """Delete this and the cutover criteria describe the result they were meant to judge."""
    client, stub = served
    late = a_period()
    late["criteria"][0]["agreed_at"] = "2019-03-15T00:00:00+00:00"
    refused = put(client, "u_admin", "/parallel", late)
    assert refused.status_code == 404
    assert "agreed at" in refused.json()["message"]
    assert stub.commits == 0


def test_a_threshold_dated_after_the_save_is_refused(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """An agreement cannot be agreed ahead of the day it was written down.

    Delete this and a criterion is dated into the past of a period it was written after."""
    client, _ = served
    future = a_period(started_at="2998-01-01T00:00:00+00:00", ends_at="2999-01-01T00:00:00+00:00")
    future["criteria"][0]["agreed_at"] = "2997-01-01T00:00:00+00:00"
    refused = put(client, "u_admin", "/parallel", future)
    assert refused.status_code == 404
    assert "after this save" in refused.json()["message"]


def test_a_naive_time_is_refused_before_it_reaches_a_comparison() -> None:
    """A time with no zone is hours out in whichever direction the server sits. Delete this and a
    naive date crashes a comparison with an aware one, or worse, does not."""
    body = a_period(started_at="2019-03-01T00:00:00")
    with console_client(GRANTS) as (client, _):
        assert put(client, "u_admin", "/parallel", body).status_code == 422


def test_an_archive_before_the_system_was_read_only_is_refused(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """Delete this and the archive is a copy of a system that carried on changing."""
    client, _ = served
    refused = put(client, "u_admin", "/cutover", a_cutover(archived_at=LATER))
    assert refused.status_code == 404
    assert "read-only" in refused.json()["message"]


def test_a_cutover_cannot_be_reported_complete_while_an_act_is_unrecorded(
    served: tuple[TestClient, Stub], switched_on: None, records: Records
) -> None:
    """The refusal is the package's own and names each act.

    Delete this and M37.7.5 is a claim about a type with no route behind it."""
    records.rows.append(held(RecordKind.CUTOVER, a_cutover()))
    client, stub = served
    refused = post(client, "u_admin", f"{BASE}/cutover/complete")
    assert refused.status_code == 404
    message = refused.json()["message"]
    assert all(leaf in message for leaf in CUTOVER_GATED_ACTS)
    assert stub.commits == 0


def test_there_is_nothing_to_report_complete_before_a_cutover_was_saved(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """Delete this and a completion is reported over a record nobody saved."""
    client, _ = served
    refused = post(client, "u_admin", f"{BASE}/cutover/complete")
    assert refused.status_code == 404
    assert "no cutover has been saved" in refused.json()["message"]


def test_a_body_cannot_say_the_cutover_was_reported_complete(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """Only the route that builds `CompletedCutover` writes a completion.

    Delete this and a cutover is completed by naming oneself in a body."""
    client, _ = served
    forged = a_cutover(reported_complete={"by": "u_admin", "at": CUT})
    assert put(client, "u_admin", "/cutover", forged).status_code == 422


# ------------------------------------------------------------------------------ the reads
def test_the_page_computes_what_is_outstanding_from_what_was_saved(
    served: tuple[TestClient, Stub], records: Records, settings: SettingRows
) -> None:
    """Gaps are found on read and never stored, so they cannot be stale.

    Delete this and the page can say a register is agreed that is not, or hide what a cutover
    still lacks."""
    settings.hold(MIGRATION_WORKSPACE.key, True, value_type="boolean")
    records.rows += [
        held(RecordKind.REGISTER, a_register()),
        held(RecordKind.PARALLEL, a_period()),
        held(RecordKind.CUTOVER, a_cutover()),
    ]
    client, _ = served
    page = get(client, "u_admin", BASE).json()
    assert page["workspace_is_on"] is True
    assert page["inventory"]["agreed"] is False
    assert any("p1" in gap and "nothing decided" in gap for gap in page["inventory"]["gaps"])
    assert page["parallel"]["may_cut_over"] is False
    assert page["parallel"]["disagreements"] == ["q1"]
    assert page["parallel"]["unreviewed"] == ["q1"]
    assert page["parallel"]["only_one_answered"] == ["q2"]
    assert sorted(page["cutover"]["acts_outstanding"]) == sorted(
        f"{leaf}: {what}" for leaf, what in CUTOVER_GATED_ACTS.items()
    )
    assert page["cutover"]["may_report_complete"] is False
    assert page["cutover"]["reported_complete"] is None


def test_nothing_saved_reads_as_nothing_and_not_as_agreed() -> None:
    """Delete this and an empty install shows a migration that is agreed."""
    assert register_view(None).agreed is False
    assert parallel_view(None, datetime(2019, 1, 1, tzinfo=UTC)).may_cut_over is False
    assert cutover_view(None).may_report_complete is False


def test_a_complete_register_is_agreed_and_a_complete_cutover_may_be_reported() -> None:
    """The positive halves. Delete this and a register that refuses to agree anything is satisfied
    by every test above."""
    done = a_register(surveyed=["knowledge", "prompt", "tool", "conversation"])
    done["decisions"].append(
        {"item_id": "p1", "disposition": "rebuild", "because": "It was written for no leash"}
    )
    saved = migration_record_store.Saved(
        kind=RecordKind.REGISTER, body=done, by="u_admin", at=datetime(2019, 6, 1, tzinfo=UTC)
    )
    assert register_view(saved).agreed is True
    every = CutoverAsked.model_validate(
        a_cutover(
            acts=[
                {"leaf": leaf, "performed_at": CUT, "recorded_by": "u_admin"}
                for leaf in CUTOVER_GATED_ACTS
            ]
        )
    )
    assert decommission_of(every).acts


def test_a_saved_completion_is_read_back_with_who_and_when() -> None:
    """Delete this and a reported cutover shows as unreported after the next read."""
    body = a_cutover(
        acts=[
            {"leaf": leaf, "performed_at": CUT, "recorded_by": "u_admin"}
            for leaf in CUTOVER_GATED_ACTS
        ]
    )
    body["reported_complete"] = {"by": "u_admin", "at": LATER}
    saved = migration_record_store.Saved(
        kind=RecordKind.CUTOVER, body=body, by="u_admin", at=datetime(2019, 6, 1, tzinfo=UTC)
    )
    view = cutover_view(saved)
    assert view.may_report_complete is True
    assert view.reported_complete is not None and view.reported_complete.by == "u_admin"
