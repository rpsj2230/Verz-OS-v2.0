"""The retention report over HTTP, and the four writes that decide whether the sweep may act.

Driven through the real application, with the token machinery imported from
`tests/unit/test_api_routes.py` for the reason `tests/unit/test_govern_routes.py` gives: what is
under test is a capability and not an identity. The database is a stub session answering by the
table a statement names, so every refusal, its order against the database and the statements the
routes compile are exercised, and no SQL is run: the store's own statements are
`tests/unit/test_retention_store.py`'s, against a server.

**Every refusal has a sibling that is answered.** A route that refused everybody passes every
refusal below, so each is paired with the person who gets through, and the pair that matters most
is the department reader: they may open the screen and are answered exactly what an install that
has never swept answers.

Task ids: M25.1.5
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.ops.retention import CitedHold, DataClass, Store, StoreCensus, sweep
from brain.ops.retention_store import ReleaseRefusal, report_document
from brain.retention_routes import LEGAL_HOLD_AUTHORITY, RETENTION_AUTHORITY
from brain.tables.retention import RetentionReportRow
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

REPORT_PATH = f"{API_PREFIX}/govern/retention"
RELEASE_PATH = f"{API_PREFIX}/govern/retention/release"
WITHDRAWAL_PATH = f"{API_PREFIX}/govern/retention/withdrawal"
HOLD_PATH = f"{API_PREFIX}/govern/legal-holds"
LIFT_PATH = f"{API_PREFIX}/govern/legal-holds/lift"

#: Far outside any plausible wall clock, and before the request's own instant.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

WHOLE = Scope.unrestricted()
IN_MAINTENANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value="maintenance"),))

#: The Retention screen's capability spelled out rather than read off the registry, so a
#: repointed screen is a failure here rather than both sides moving together.
READ_RETENTION = "read:retention_policy"

SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


def _grant(value: str, scope: Scope) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


def _configuration(scope: Scope = WHOLE) -> Grant:
    return _grant(plane_capability(Plane.CONFIGURATION).value, scope)


#: The six people `test_api_routes` mints tokens for, holding what this file needs.
RETENTION_GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    # The plane and the release authority, and not the screen: refused the report, and refused a
    # release before anything is read.
    "u_prefix": (_configuration(), _grant(RETENTION_AUTHORITY.value, WHOLE)),
    # Both authorities over everything, and the screen in one department: may hold and withdraw,
    # may open the screen and is shown no report, so may not release after reading it.
    "u_narrow": (
        _grant(RETENTION_AUTHORITY.value, WHOLE),
        _grant(LEGAL_HOLD_AUTHORITY.value, WHOLE),
        _grant(READ_RETENTION, IN_MAINTENANCE),
        _configuration(IN_MAINTENANCE),
    ),
    # Reads the report over everything and may write nothing.
    "u_wide": (_grant(READ_RETENTION, WHOLE), _configuration()),
    # Everything, over everything.
    "u_admin": (
        _grant(READ_RETENTION, WHOLE),
        _configuration(),
        _grant(RETENTION_AUTHORITY.value, WHOLE),
        _grant(LEGAL_HOLD_AUTHORITY.value, WHOLE),
    ),
    # Everything, narrowed to one department: may open the screen and is shown no report.
    "u_elsewhere": (
        _grant(READ_RETENTION, IN_MAINTENANCE),
        _configuration(IN_MAINTENANCE),
        _grant(RETENTION_AUTHORITY.value, IN_MAINTENANCE),
        _grant(LEGAL_HOLD_AUTHORITY.value, IN_MAINTENANCE),
    ),
}


class RetentionStore:
    """A `brain.gate.resolve.EntitlementStore` over `RETENTION_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=RETENTION_GRANTS[principal_id])


# ------------------------------------------------------------------------ the report
REPORT_ID = uuid.UUID(int=41)


def report_row(*, report_id: uuid.UUID = REPORT_ID, report_only: bool = True) -> RetentionReportRow:
    """A stored report of a run that removed three traces under one hold."""

    class Scripted:
        def census(self, store: Store, now: datetime) -> StoreCensus:
            if store is Store.TRACE:
                return StoreCensus(store=store, beyond_horizon=4, held=1)
            from brain.ops.retention import RetentionError

            raise RetentionError("not in this test")

        def expire(self, store: Store, now: datetime) -> int:
            return 3

    report = sweep(
        Scripted(),
        now=LONG_AGO,
        report_only=report_only,
        holds=(CitedHold(hold_id="h_dispute", reason_code="litigation", company_wide=False),),
    )
    document = report_document(report)
    return RetentionReportRow(
        id=report_id,
        at=LONG_AGO,
        report_only=report_only,
        complete=report.complete,
        stores=document["stores"],
        holds=document["holds"],
        findings=document["findings"],
        failure=None,
    )


# ------------------------------------------------------------------ the stub session
class StubResult:
    def __init__(self, rows: tuple[Any, ...]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        assert len(self._rows) == 1
        return self._rows[0]


class Executed:
    """What the stub answers each table, and every statement it was asked to run."""

    def __init__(self) -> None:
        self.report: RetentionReportRow | None = report_row()
        self.live_release: uuid.UUID | None = None
        self.lifted: str | None = "h_dispute"
        self.hold_exists = False
        self.release_raced = False
        self.statements: list[str] = []
        self.committed = 0
        self.rolled_back = 0

    def answer(self, sql: str) -> StubResult:
        if sql.startswith("INSERT INTO ops.retention_release"):
            return StubResult((uuid.UUID(int=99),))
        if sql.startswith("UPDATE ops.retention_release"):
            return StubResult(() if self.live_release is None else (self.live_release,))
        if "FROM ops.retention_release" in sql:
            return StubResult(() if self.live_release is None else (self.live_release,))
        if "FROM ops.retention_report" in sql:
            return StubResult(() if self.report is None else (self.report,))
        if sql.startswith("UPDATE obs.legal_hold"):
            return StubResult(() if self.lifted is None else (self.lifted,))
        return StubResult(())


_EXECUTED = Executed()


class StubSession(AsyncSession):
    """An `AsyncSession` that runs nothing and records everything."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(statement)
        _EXECUTED.statements.append(sql)
        if _EXECUTED.hold_exists and sql.startswith("INSERT INTO obs.legal_hold"):
            raise IntegrityError("insert", None, Exception("pk_legal_hold"))
        if _EXECUTED.release_raced and sql.startswith("INSERT INTO ops.retention_release"):
            raise IntegrityError("insert", None, Exception("uq_retention_release_live"))
        return _EXECUTED.answer(sql)

    async def commit(self) -> None:
        _EXECUTED.committed += 1

    async def rollback(self) -> None:
        _EXECUTED.rolled_back += 1

    async def close(self) -> None:
        return None


@pytest.fixture
def executed() -> Iterator[Executed]:
    global _EXECUTED
    _EXECUTED = Executed()
    yield _EXECUTED


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER,
            audience=AUDIENCE,
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=RetentionStore(),
        cache=NoCache(),
    )


@pytest.fixture
def client(executed: Executed) -> Iterator[TestClient]:
    """The real application, with a stub session factory where the pool would be."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.console_reads = None
        yield c


@pytest.fixture
def unwired() -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        app.state.console_reads = None
        yield c


def _headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}


def get(c: TestClient, pid: str) -> Response:
    response: Response = c.get(REPORT_PATH, headers=_headers(pid))
    return response


def post(c: TestClient, path: str, pid: str, body: Mapping[str, object] | None = None) -> Response:
    response: Response = c.post(path, headers=_headers(pid), json=dict(body or {}))
    return response


def _writes(executed: Executed) -> list[str]:
    return [one for one in executed.statements if one.startswith(("INSERT", "UPDATE"))]


HOLD: Mapping[str, object] = {
    "hold_id": "h_dispute",
    "reason_code": "litigation",
    "subjects": ["u_one"],
}


# ------------------------------------------------------------------------ the report
@pytest.mark.parametrize("pid", ["u_none", "u_prefix"])
def test_a_caller_who_may_not_open_the_retention_screen_is_refused_before_the_database(
    client: TestClient, unwired: TestClient, executed: Executed, pid: str
) -> None:
    """The screen's capability and the console plane, both, asked before any statement: the same
    404 with a database and without one, and nothing read.

    Delete this and a caller holding neither could be answered a report, or could tell from a
    500 that the screen would have answered them had the database been up."""
    assert get(client, pid).status_code == 404
    assert get(unwired, pid).status_code == 404
    assert executed.statements == []


def test_a_company_wide_reader_is_shown_the_newest_report_whole(
    client: TestClient, executed: Executed
) -> None:
    """The sibling the refusals need: counts per store and per class, the cited hold, the mode,
    and whether the sweep is released now.

    Delete this and every refusal above is satisfied by a route that answers nobody."""
    response = get(client, "u_wide")

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["report_id"] == str(REPORT_ID)
    assert (report["report_only"], report["released"], report["failure"]) == (True, False, None)
    assert report["removed"] == 0
    assert report["held_by_class"] == [{"data_class": DataClass.TRACE.value, "count": 1}]
    assert report["queued_by_class"] == []
    assert report["holds"] == [
        {"hold_id": "h_dispute", "reason_code": "litigation", "company_wide": False}
    ]
    assert [one["store"] for one in report["stores"]] == [store.value for store in Store]
    trace = next(one for one in report["stores"] if one["store"] == Store.TRACE.value)
    assert (trace["reached"], trace["due"], trace["held"]) == (True, 3, 1)


def test_a_released_run_shows_what_it_removed_by_class_and_that_the_sweep_is_released(
    client: TestClient, executed: Executed
) -> None:
    """A run that acted, with a release live: removals by class and `released` true.

    Delete this and the response could drop the removal counts, which are the half of the report
    that says enforcement happened."""
    executed.report = report_row(report_only=False)
    executed.live_release = uuid.UUID(int=5)

    report = get(client, "u_admin").json()["report"]

    assert report["removed"] == 3
    assert report["removed_by_class"] == [{"data_class": DataClass.TRACE.value, "count": 3}]
    assert report["released"] is True


def test_a_department_reader_is_answered_exactly_as_an_install_that_has_never_swept(
    client: TestClient, executed: Executed
) -> None:
    """`u_elsewhere` may open the screen, and is answered the body `u_admin` gets when no report
    exists. The database was read for both.

    Delete this and a department reader could be shown counts over the whole estate, including how
    much is held about people outside their reach, or be refused in a way that says a report
    exists."""
    withheld = get(client, "u_elsewhere")
    executed.report = None
    never_swept = get(client, "u_admin")

    assert withheld.status_code == never_swept.status_code == 200
    assert withheld.json() == never_swept.json() == {"report": None}
    assert sum("ops.retention_report" in one for one in executed.statements) == 2


# ------------------------------------------------------------------------ releasing
@pytest.mark.parametrize("pid", ["u_wide", "u_prefix", "u_elsewhere", "u_none"])
def test_a_release_needs_the_authority_over_everything_and_the_screen_before_anything_is_read(
    client: TestClient, executed: Executed, pid: str
) -> None:
    """No authority, the authority and no screen, both in one department, and nothing: each
    refused with the ordinary refusal before a statement runs.

    Delete this and somebody who could never open the report, or who holds the authority over one
    department, could approve every deletion in the estate, or learn by the refusal's timing
    whether this process has a database."""
    response = post(client, RELEASE_PATH, pid, {"after_report": str(REPORT_ID)})

    assert response.status_code == 404
    assert response.json()["message"] == Absent.public_message
    assert executed.statements == []


def test_a_release_by_somebody_the_report_is_withheld_from_is_refused_after_it_is_read(
    client: TestClient, executed: Executed
) -> None:
    """`u_narrow` holds the authority over everything and opens the screen in one department, so
    `retention_view` withholds the report from them, and a release they make approves nothing
    they read.

    Delete this and the authority alone would release the sweep, which is
    `A_RELEASE_BY_SOMEBODY_WHO_COULD_NOT_READ_THE_REPORT_APPROVED_NOTHING`."""
    response = post(client, RELEASE_PATH, "u_narrow", {"after_report": str(REPORT_ID)})

    assert response.status_code == 404
    assert response.json()["message"] == Absent.public_message
    assert any("ops.retention_report" in one for one in executed.statements)
    assert _writes(executed) == []


def test_a_release_that_loses_a_race_for_the_one_live_release_is_refused_by_name(
    client: TestClient, executed: Executed
) -> None:
    """The unique index refuses the second of two releases made together; the administrator is
    told it was already released, and nothing is committed.

    Delete this and the integrity error would reach the caller as a fault naming the index."""
    executed.release_raced = True

    response = post(client, RELEASE_PATH, "u_admin", {"after_report": str(REPORT_ID)})

    assert response.status_code == 404
    assert "already_released" in response.json()["message"]
    assert executed.committed == 0


def test_an_administrator_who_read_the_newest_report_releases_the_sweep(
    client: TestClient, executed: Executed
) -> None:
    """Delete this and the refusals above are satisfied by a route nobody can release through,
    which leaves the sweep reporting for ever."""
    response = post(client, RELEASE_PATH, "u_admin", {"after_report": str(REPORT_ID)})

    assert response.status_code == 200
    assert response.json()["after_report"] == str(REPORT_ID)
    assert [one.split(" (")[0] for one in _writes(executed)] == [
        "INSERT INTO ops.retention_release"
    ]
    assert executed.committed == 1


@pytest.mark.parametrize(
    ("setup", "refusal"),
    [
        ("stale", ReleaseRefusal.NOT_THE_NEWEST),
        ("acted", ReleaseRefusal.NOT_A_REPORT_ONLY_RUN),
        ("live", ReleaseRefusal.ALREADY_RELEASED),
    ],
)
def test_a_release_the_store_refuses_is_refused_by_name_to_the_administrator(
    client: TestClient, executed: Executed, setup: str, refusal: ReleaseRefusal
) -> None:
    """The reason reaches a caller who holds the authority, and nothing is written.

    Delete this and a refused release could still commit, or answer the administrator the same
    blank refusal a stranger gets, so nobody could tell that the report had moved on."""
    after = REPORT_ID
    if setup == "stale":
        after = uuid.UUID(int=42)
    elif setup == "acted":
        executed.report = report_row(report_only=False)
    else:
        executed.live_release = uuid.UUID(int=5)

    response = post(client, RELEASE_PATH, "u_admin", {"after_report": str(after)})

    assert response.status_code == 404
    assert refusal.value in response.json()["message"]
    assert _writes(executed) == []
    assert executed.committed == 0


def test_a_release_with_no_report_to_read_is_refused_as_a_stranger_would_be(
    client: TestClient, executed: Executed
) -> None:
    """Delete this and a release could be recorded on an install that has never swept."""
    executed.report = None

    response = post(client, RELEASE_PATH, "u_admin", {"after_report": str(REPORT_ID)})

    assert response.status_code == 404
    assert response.json()["message"] == Absent.public_message
    assert _writes(executed) == []


def test_a_withdrawal_needs_the_authority_and_marks_a_live_release(
    client: TestClient, executed: Executed
) -> None:
    """`u_narrow` holds the authority and not the company-wide read, which withdrawing does not
    need; `u_wide` holds the read and not the authority, and `u_elsewhere` the authority in one
    department. With nothing live the authority is told so.

    Delete this and putting the sweep back to reporting could need the same read releasing does,
    which is the wrong way round for the one control that stops a deletion."""
    executed.live_release = uuid.UUID(int=5)

    assert post(client, WITHDRAWAL_PATH, "u_wide").status_code == 404
    assert post(client, WITHDRAWAL_PATH, "u_elsewhere").status_code == 404
    assert _writes(executed) == []
    assert post(client, WITHDRAWAL_PATH, "u_narrow").status_code == 200
    assert executed.committed == 1

    executed.live_release = None
    refused = post(client, WITHDRAWAL_PATH, "u_narrow")
    assert refused.status_code == 404
    assert "not_released" in refused.json()["message"]


# ------------------------------------------------------------------------ holding
@pytest.mark.parametrize("pid", ["u_wide", "u_elsewhere", "u_none"])
def test_a_legal_hold_needs_the_authority_over_everything(
    client: TestClient, executed: Executed, pid: str
) -> None:
    """Delete this and a hold, which suspends deletion across the estate, could be placed by a
    reader or by somebody holding the authority over one department."""
    assert post(client, HOLD_PATH, pid, HOLD).status_code == 404
    assert post(client, LIFT_PATH, pid, {"hold_id": "h_dispute"}).status_code == 404
    assert _writes(executed) == []


def test_a_legal_hold_is_placed_and_lifted_by_somebody_holding_the_authority(
    client: TestClient, executed: Executed
) -> None:
    """Placed, then lifted, each committed; a lift of a hold that is not live is refused by name.

    Delete this and the refusals above are satisfied by routes nobody can hold data through."""
    placed = post(client, HOLD_PATH, "u_narrow", HOLD)
    lifted = post(client, LIFT_PATH, "u_narrow", {"hold_id": "h_dispute"})

    assert (placed.status_code, lifted.status_code) == (200, 200)
    assert [one.split(" ")[0:3] for one in _writes(executed)] == [
        ["INSERT", "INTO", "obs.legal_hold"],
        ["UPDATE", "obs.legal_hold", "SET"],
    ]
    assert executed.committed == 2

    executed.lifted = None
    again = post(client, LIFT_PATH, "u_narrow", {"hold_id": "h_dispute"})
    assert again.status_code == 404
    assert "not_a_live_hold" in again.json()["message"]


def test_a_hold_naming_nobody_or_placed_twice_is_refused_and_its_instant_is_never_the_bodys(
    client: TestClient, executed: Executed
) -> None:
    """A hold with no subjects, actors or company-wide flag holds nothing; an identifier already
    used is a constraint's refusal; and a body carrying `placed_at` is refused outright, because
    the instant a hold starts is the request's.

    Delete this and a hold could be placed that holds nothing and reads as protection, or be
    back-dated so a deletion that already happened looks as though it was made under a hold."""
    nobody = post(client, HOLD_PATH, "u_admin", {"hold_id": "h_empty", "reason_code": "litigation"})
    assert nobody.status_code == 404
    assert "names_nothing" in nobody.json()["message"]

    backdated = post(client, HOLD_PATH, "u_admin", {**HOLD, "placed_at": LONG_AGO.isoformat()})
    assert backdated.status_code == 422

    executed.hold_exists = True
    twice = post(client, HOLD_PATH, "u_admin", HOLD)
    assert twice.status_code == 404
    assert "not_placed" in twice.json()["message"]
    assert executed.committed == 0


def test_every_write_sets_the_attribution_before_its_row(
    client: TestClient, executed: Executed
) -> None:
    """**M24.3.1 on the Retention screen.** A hold placed and lifted, each preceded by the three
    settings `brain.attribution.attribute` makes, so the ledger entries the triggers write carry
    the administrator's reach and the request's trace rather than `0003`'s placeholders. Delete
    this and the routes can go back to writing holds whose entries say nothing about the reach
    they were placed at."""
    assert post(client, HOLD_PATH, "u_admin", HOLD).status_code == 200
    executed_before_write = executed.statements[
        : next(i for i, one in enumerate(executed.statements) if one.startswith("INSERT"))
    ]
    assert sum("set_config" in one for one in executed_before_write) == 3
