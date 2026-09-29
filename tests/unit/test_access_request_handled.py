"""`0146` against a real database: an access request is marked handled once, by its owner, and a
certification report is recorded as an export with its ledger entry.

Every migration is run to head (`tests.fixtures.retirable`, which needs pgvector, as CI and the
local server have), and every write is made as `brain_app` through `app_engine`, so the grant, the
insert policy and the table's key are what is exercised rather than the owner's bypass. Skipped
where no server answers or pgvector is missing.

Task ids: M4.3.4, M27.15.21, M27.16.1
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from brain.ops.access_request_store import handled_among, mark_handled
from brain.ops.data_export_store import StoredExports
from brain.ops.export import ExportReason
from brain.session import make_session_factory
from brain.tables.data_export import ExportDataSet, ExportForm
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import database_url, run, sql
from tests.unit.test_automation_owner_store import app_engine

DATABASE = "brain_test_access_request_handled"
AT = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)

pytestmark = pytest.mark.skipif(database_url() is None, reason="needs a PostgreSQL server")


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with retirable(DATABASE) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to head needs pgvector")
        yield url


def a_request(url: str) -> uuid.UUID:
    (row,) = sql(
        url,
        "INSERT INTO gate.access_request (asker_id, owner_id, department, question,"
        " requested_capability) VALUES ('u_one', 'u_steward', 'finance', 'why', 'read:knowledge')"
        " RETURNING id",
    )
    return uuid.UUID(str(row[0]))


def marked(url: str, request_id: uuid.UUID, owner: str) -> bool:
    async def go() -> bool:
        engine = app_engine(url)
        try:
            async with make_session_factory(engine)() as session:
                done = await mark_handled(session, request_id, owner_id=owner, at=AT)
                await session.commit()
                return done
        finally:
            await engine.dispose()

    return run(go)


def read_marks(url: str, request_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    async def go() -> dict[uuid.UUID, datetime]:
        engine = app_engine(url)
        try:
            async with make_session_factory(engine)() as session:
                return await handled_among(session, request_ids)
        finally:
            await engine.dispose()

    return run(go)


def test_the_owner_marks_a_request_handled_once_and_nobody_else_may(database: str) -> None:
    """Needs-rupash gap (a), at the database. Delete this and the grant or the policy can be
    missing, so every mark is a 500, or the mark can be put on by a stranger or twice."""
    request_id = a_request(database)
    untouched = a_request(database)

    stranger = marked(database, request_id, "u_one")
    owner = marked(database, request_id, "u_steward")
    again = marked(database, request_id, "u_steward")

    assert (stranger, owner, again) == (False, True, False)
    assert sql(
        database,
        "SELECT handled_by FROM gate.access_request_handled WHERE request_id = %s",
        str(request_id),
    ) == [("u_steward",)]
    assert read_marks(database, [request_id, untouched]) == {request_id: AT}


def test_the_application_may_change_nothing_else_and_mark_nobody_but_the_owner(
    database: str,
) -> None:
    """The grants and the insert policy. Delete this and the application role can rewrite the
    question a person asked, move or clear a mark, or record another person as having handled a
    request, each of which the list would then report as fact."""
    from psycopg import errors  # Imported here: the driver loads only where a server runs.

    request_id = a_request(database)
    marked(database, request_id, "u_steward")
    with pytest.raises(errors.InsufficientPrivilege):
        sql(database, "SET ROLE brain_app; UPDATE gate.access_request SET question = 'changed'")
    with pytest.raises(errors.InsufficientPrivilege):
        sql(
            database,
            "SET ROLE brain_app; UPDATE gate.access_request_handled SET handled_at = now()",
        )
    with pytest.raises(errors.InsufficientPrivilege):
        sql(database, "SET ROLE brain_app; DELETE FROM gate.access_request_handled")
    with pytest.raises(errors.InsufficientPrivilege):
        # The policy's refusal: a mark naming anybody but the request's owner. Every request,
        # this one's second among them: two commands cannot carry a bound parameter.
        sql(
            database,
            "SET ROLE brain_app; INSERT INTO gate.access_request_handled (request_id, handled_by)"
            " SELECT id, 'u_other' FROM gate.access_request",
        )


def test_a_certification_report_is_recorded_as_a_readable_export_with_its_ledger_entry(
    database: str,
) -> None:
    """M27.15.21's record. Delete this and `0146`'s data set can be missing, so every report is
    refused at the insert, or the report can leave with no `publish` entry in the ledger."""

    async def go() -> str:
        engine = app_engine(database)
        try:
            taken = await StoredExports(make_session_factory(engine)).record_report(
                data_set=ExportDataSet.ACCESS_CERTIFICATION,
                actor="u_reviewer",
                ent_hash="0" * 32,
                trace_id="trace-report",
                reason=ExportReason.REGULATORY_REQUEST,
                reason_reference="AUDIT-2026-Q3",
                at=AT,
                entries=3,
                document_digest="a" * 64,
            )
            return taken.export_id
        finally:
            await engine.dispose()

    export_id = run(go)

    assert sql(
        database,
        "SELECT data_set, form, entries, verified, first_seq FROM ops.data_export"
        " WHERE export_id = %s",
        export_id,
    ) == [(ExportDataSet.ACCESS_CERTIFICATION.value, ExportForm.READABLE.value, 3, None, None)]
    assert sql(
        database,
        "SELECT action, actor_id, details->>'fields' FROM obs.audit_entry WHERE subject = %s",
        f"artifact:{export_id}",
    ) == [("publish", "u_reviewer", "access_certification")]
