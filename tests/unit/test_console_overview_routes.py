"""The landing screen over HTTP: who may open it, what the health strip says, and that Needs you
counts only what each queue's own screen would show the reader.

Driven through the real application with signed-in people, suspensions held in memory, a skill
library held in memory and a stub where the pool is. Suspensions are built the way the gate
builds them (`tests/unit/test_approval_routes.py`), one in a department the approver may act in
and one in a department they may not, so a count over everything and a count over nothing both
fail.

Task ids: M27.2.1, M27.15.17
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.selectable import Select

from brain import console_overview_routes
from brain.api import API_PREFIX
from brain.approval_routes import APPROVALS_ARE_NOT_KEPT_ON_THIS_PROCESS
from brain.console.elevation import ELEVATION_CONTROL
from brain.console.needs_you import UNRECORDED_HEALTH, Queue, halt_state
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.skill_library import REVIEW_AUTHORITY
from brain.console_overview_routes import (
    A_QUEUE_THAT_COULD_NOT_BE_READ_IS_NAMED,
    OverviewView,
    router,
)
from brain.core.entitlement import Capability, Grant
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.gate.elevation_store import StoredRequest
from brain.gate.review_store import StoredReview
from brain.ops.controls import CONTROLS
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.tables.elevation import ElevationDecision
from tests.fixtures.console_http import Stub, console_client, get
from tests.fixtures.setting_rows import Result, Row
from tests.unit.test_approval_routes import (
    FINANCE,
    MAINTENANCE,
    WRITE_STATUS,
    MemorySource,
    a_suspension,
    in_department,
)
from tests.unit.test_console_stats_routes import Library

OVERVIEW = f"{API_PREFIX}/console/overview"
EVERYWHERE = Scope.unrestricted()
PLANES = tuple(Grant(capability=plane_capability(one), scope=EVERYWHERE) for one in Plane)


def read(key: str) -> Capability:
    return screen(key).read.requires


#: `u_admin` opens the overview, decides approvals in maintenance only, reviews skills, reads the
#: agents screen and the scheduled jobs. `u_narrow` opens the overview and nothing it counts.
#: `u_none` holds nothing, so the landing screen is not theirs to open.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        *PLANES,
        *(
            Grant(capability=read(key), scope=EVERYWHERE)
            for key in ("overview", "approvals", "skills", "agents", "queue")
        ),
        Grant(capability=REVIEW_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=Capability(value=WRITE_STATUS), scope=in_department(MAINTENANCE)),
    ),
    "u_narrow": (*PLANES, Grant(capability=read("overview"), scope=EVERYWHERE)),
    "u_none": (),
}

STARTED = datetime(2027, 5, 4, 9, 0, tzinfo=UTC)
FINISHED = STARTED + timedelta(minutes=2)


#: The latest act per scope and target, as `latest_halt_acts` answers: a halt on everything, a
#: department halt in finance, and a person halt that was resumed.
HALT_ACTS: list[tuple[str, str, str, str, str, datetime]] = [
    ("everything", "", "halt", "u_stopper", "a secret incident reason", STARTED),
    ("department", "finance", "halt", "u_stopper", "a finance incident reason", FINISHED),
    ("person", "u_someone", "resume", "u_stopper", "the account is safe again", FINISHED),
]


class Runs:
    """The newest run of each scheduled control and the halts, answered by the columns asked."""

    def __init__(self) -> None:
        self.halts: list[tuple[str, str, str, str, str, datetime]] | Exception = list(HALT_ACTS)

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        columns = [one["name"] for one in statement.column_descriptions]
        if columns == ["name", "started_at", "finished_at", "outcome", "detail"]:
            first = CONTROLS[0].name
            return Result([Row((first, STARTED, FINISHED, "succeeded", None))])
        if columns == ["scope", "target", "act", "actor_id", "reason", "at"]:
            if isinstance(self.halts, Exception):
                raise self.halts
            return Result(Row(one) for one in self.halts)
        return None


@pytest.fixture
def runs() -> Runs:
    return Runs()


@pytest.fixture
def served(runs: Runs) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(runs.answer)
        state = client.app.state  # type: ignore[attr-defined]
        state.suspensions = MemorySource(
            [
                a_suspension("s_maintenance", department=MAINTENANCE),
                a_suspension("s_finance", department=FINANCE),
            ]
        )
        state.skill_library = Library()
        yield client, stub


def overview_of(client: TestClient, pid: str) -> OverviewView:
    response = get(client, pid, OVERVIEW)
    assert response.status_code == 200, response.text
    return OverviewView.model_validate(response.json())


def test_needs_you_counts_only_the_approvals_and_skill_reviews_the_reader_may_act_on(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case, and its narrowing: one of two suspensions is in a department the
    approver may act in, and both skill versions wait for a reviewer. Delete this and Needs you
    could count every suspension, or none, and nothing would say so."""
    client, _ = served
    body = overview_of(client, "u_admin")

    assert [(one.queue, one.waiting) for one in body.needs_you] == [
        (Queue.APPROVALS.value, 1),
        (Queue.SKILL_REVIEWS.value, 2),
    ]
    assert body.needs_you[0].opens == "/approvals"
    assert [one.figure for one in body.uncounted] == [Queue.PUBLISH_APPROVALS.value]


def test_a_reader_who_may_open_no_queue_is_shown_none_rather_than_a_row_of_noughts(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a reader of the overview alone is shown every queue at nought, which says
    each exists and is being kept from them."""
    client, _ = served
    body = overview_of(client, "u_narrow")

    assert body.needs_you == []
    assert body.uncounted == []


def test_a_reader_without_the_overview_read_gets_the_same_404_as_any_hidden_screen(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the landing screen's figures reach a caller the menu does not offer it to."""
    client, _ = served
    refused = get(client, "u_none", OVERVIEW)

    assert refused.status_code == 404
    assert refused.json()["message"] == Absent.public_message
    assert get(client, "u_narrow", OVERVIEW).status_code == 200


def test_the_health_strip_names_what_nothing_records_and_dates_the_worker_by_visible_runs(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the strip reads "no halts" when nothing can store one, or dates the worker
    for a reader who may see none of its runs."""
    client, _ = served
    admin = overview_of(client, "u_admin")
    narrow = overview_of(client, "u_narrow")

    assert admin.health.worker_last_seen == FINISHED
    assert narrow.health.worker_last_seen is None
    assert {one.figure for one in admin.health.unrecorded} == {
        one.figure for one in UNRECORDED_HEALTH
    }
    assert admin.health.status in {"ok", "degraded"}
    assert [one.name for one in admin.health.parts] == [one.name for one in narrow.health.parts]


def test_a_queue_the_reader_may_act_on_that_cannot_be_read_is_named_not_dropped(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a process with no suspension store, or a store that fails, shows Needs you
    without the queue, which reads as nothing waiting."""
    client, _ = served
    client.app.state.suspensions = None  # type: ignore[attr-defined]
    missing = overview_of(client, "u_admin")
    assert (Queue.APPROVALS.value, APPROVALS_ARE_NOT_KEPT_ON_THIS_PROCESS) in {
        (one.figure, one.why) for one in missing.uncounted
    }

    async def broken(request: Any, asked: Any) -> Any:
        raise Failed("the store is down")

    readers = tuple(
        (queue, broken if queue is Queue.SKILL_REVIEWS else ask)
        for queue, ask in console_overview_routes.QUEUE_READERS
    )
    monkeypatch.setattr(console_overview_routes, "QUEUE_READERS", readers)
    failed = overview_of(client, "u_admin")
    assert (Queue.SKILL_REVIEWS.value, A_QUEUE_THAT_COULD_NOT_BE_READ_IS_NAMED) in {
        (one.figure, one.why) for one in failed.uncounted
    }
    assert Queue.SKILL_REVIEWS.value not in {one.queue for one in failed.needs_you}


def test_no_overview_view_carries_a_field_named_like_a_count_of_what_was_withheld() -> None:
    """Delete this and a queue's total beside the reader's count is one edit away."""
    views = [
        getattr(console_overview_routes, name)
        for name in dir(console_overview_routes)
        if name.endswith("View") and isinstance(getattr(console_overview_routes, name), type)
    ]

    assert len(views) >= 4
    assert [
        f"{one.__name__}.{field}"
        for one in views
        for field in one.model_fields
        if field in NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
    ] == []


# ------------------------------------------------ the queues whose stores these tests fake
class NoHoldings(StoredReview):
    """The access review store with one holding nobody may review and nothing decided."""

    async def holdings(self, *, limit: int) -> Any:
        return (), {}, False


class Elevations:
    """`brain.gate.elevation_store.ElevationRecords` over three requests."""

    def __init__(self) -> None:
        self.held = (
            elevation("u_asker", "web", decided=False),
            elevation("u_asker", "finance", decided=False),
            elevation("u_asker", "web", decided=True),
        )

    async def requests(self, *, limit: int) -> tuple[tuple[StoredRequest, ...], bool]:
        return self.held[:limit], False

    async def file(self, **kwargs: Any) -> None:
        raise AssertionError("the overview wrote")

    async def approve(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("the overview wrote")

    async def deny(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("the overview wrote")


def elevation(principal: str, department: str, *, decided: bool) -> StoredRequest:
    return StoredRequest(
        request_id=uuid.uuid4(),
        principal_id=principal,
        display_name=None,
        department=department,
        capability="read:invoice",
        scope_slug="everything",
        reason="incident",
        explanation="a sentence",
        hours=1,
        requested_at=STARTED,
        decision=ElevationDecision.APPROVED if decided else None,
        decided_by="u_other" if decided else None,
        decided_at=STARTED if decided else None,
        lapses_at=None,
        grant_live=False,
    )


def test_access_review_elevation_and_knowledge_are_counted_by_their_own_screens_decisions(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`u_elsewhere` may authorise elevations in web, open access review, and act on documents.
    One of three elevations is pending in web; one of three documents is past review and theirs
    to act on. Delete this and those three queues are counted by nobody's rule."""
    client, _ = served
    state = client.app.state  # type: ignore[attr-defined]
    state.review_store = NoHoldings(sessions=None)  # type: ignore[arg-type]
    state.elevation_records = Elevations()
    past = datetime.now(UTC) - timedelta(days=1)
    documents = [
        SimpleNamespace(item_id="k_mine", review_by=past),
        SimpleNamespace(item_id="k_hidden", review_by=past),
        SimpleNamespace(item_id="k_fresh", review_by=datetime.now(UTC) + timedelta(days=9)),
    ]

    async def authority(request: Any, asked: Any) -> Any:
        return SimpleNamespace(may_act=lambda item: item.item_id != "k_hidden")

    async def transaction(request: Any, asked: Any, authority: Any, work: Any) -> Any:
        return tuple(documents)

    monkeypatch.setattr(console_overview_routes, "authority_of", authority)
    monkeypatch.setattr(console_overview_routes, "in_transaction", transaction)
    monkeypatch.setitem(
        GRANTS,
        "u_elsewhere",
        (
            *PLANES,
            *(Grant(capability=read(key), scope=EVERYWHERE) for key in ("overview", "library")),
            Grant(capability=ELEVATION_CONTROL, scope=in_department("web")),
        ),
    )
    body = overview_of(client, "u_elsewhere")

    assert [(one.queue, one.waiting) for one in body.needs_you] == [
        (Queue.ACCESS_REVIEW.value, 0),
        (Queue.ELEVATION.value, 1),
        (Queue.KNOWLEDGE_PAST_REVIEW.value, 1),
    ]


# ------------------------------------------------------------------------------- halts
def test_a_halt_on_everything_is_shown_to_everybody_and_a_narrower_one_through_the_halt_grant(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the strip either hides the halt that is refusing a reader's work, or lists a
    department's halt to somebody who may not read halts, or shows why somebody stopped it."""
    client, _ = served
    everybody = overview_of(client, "u_narrow")
    assert [(one.scope, one.target) for one in everybody.health.halts] == [("everything", "")]
    assert everybody.health.halts_known is True
    assert "incident reason" not in get(client, "u_narrow", OVERVIEW).text

    monkeypatch.setitem(
        GRANTS,
        "u_narrow",
        (*GRANTS["u_narrow"], Grant(capability=read("halt"), scope=EVERYWHERE)),
    )
    halt_reader = overview_of(client, "u_narrow")
    assert [(one.scope, one.target) for one in halt_reader.health.halts] == [
        ("everything", ""),
        ("department", "finance"),
    ]
    assert "halts" not in {one.figure for one in halt_reader.health.unrecorded}


def test_halts_that_cannot_be_read_are_unknown_and_never_an_empty_strip(
    served: tuple[TestClient, Stub], runs: Runs
) -> None:
    """Delete this and a halt store that fails reads as nothing stopped while admission, which
    treats unknown as halted, refuses every request."""
    client, _ = served
    runs.halts = OperationalError("SELECT", {}, Exception("the database went away"))

    body = overview_of(client, "u_admin")

    assert (body.health.halts, body.health.halts_known) == ([], False)


def test_the_latest_act_per_target_decides_what_is_in_force_on_postgresql() -> None:
    """Run on PostgreSQL. Delete this and the `DISTINCT ON` read is only ever compiled, so a halt
    lifted by a later resume could still be read as in force, or the other way round."""
    from tests.fixtures.scratch_postgres import engine, modelled, run, sql

    with modelled("brain_test_console_overview_halts", ("ops.halt",)) as url:
        for act, scope, target, minutes in (
            ("halt", "everything", "", 1),
            ("resume", "everything", "", 2),
            ("halt", "department", "finance", 3),
        ):
            sql(
                url,
                "INSERT INTO ops.halt (act, scope, target, actor_id, actor_role, reason, at) "
                "VALUES (%s, %s, %s, 'u_stopper', 'administrator', 'a reason long enough', %s)",
                act,
                scope,
                target,
                STARTED + timedelta(minutes=minutes),
            )

        async def go() -> list[tuple[Any, ...]]:
            built = engine(url)
            try:
                async with built.connect() as conn:
                    result = await conn.execute(console_overview_routes.latest_halt_acts())
                    return [tuple(one) for one in result.all()]
            finally:
                await built.dispose()

        state = halt_state(run(go))

    assert [(one.scope.value, one.target) for one in state.halts] == [("department", "finance")]
    assert state.known is True
