"""A routed access request is stored as the application role, and read back by its owner alone.

The shape half runs everywhere. The database half needs a server and runs in CI: `0101` for real
on a fresh database, written and read as `brain_app` so the grant and the row-level security
policies are what is exercised, not the owner's bypass.

Task ids: M4.3.4
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.ops.access_request_store import Request, addressed_to, record
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, run, sql

AT = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)
FIELD = Request(
    asker_id="u_one",
    owner_id="u_steward",
    question="what did Acme sign for",
    requested_capability="read:client.contract_value",
    entity="client",
    field="contract_value",
)
DEPARTMENT = Request(
    asker_id="u_one",
    owner_id="u_steward",
    question="what is the finance leave policy",
    requested_capability="read:knowledge",
    department="finance",
)


@pytest.mark.parametrize(
    "subject",
    [
        {"entity": "client", "field": "name", "department": "web"},
        {"entity": "client"},
        {},
    ],
)
def test_a_request_naming_both_subjects_or_neither_is_refused_before_it_is_stored(
    subject: dict[str, str],
) -> None:
    """Delete this and a request about nothing nameable reaches an owner's list."""
    with pytest.raises(ValueError, match="only one"):
        Request(asker_id="u", owner_id="o", question="q", requested_capability="read:x", **subject)


# ------------------------------------------------------------------ the database
DATABASE = "brain_test_m434_access_request"


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """`0101` run for real on a database stamped at the revision before it."""
    scratch = fresh(DATABASE)
    try:
        migrate(DATABASE, "stamp", "0100")
        migrate(DATABASE, "upgrade", "0101")
        yield scratch
    finally:
        drop(DATABASE)


def test_a_request_is_stored_and_its_owner_reads_it_back_as_the_application_role(
    database: str,
) -> None:
    """M4.3.4 delivery: both subjects are written as `brain_app` and read back by the owner they
    were addressed to, newest first; somebody else's list is empty.

    Delete this and the grant or a policy can be missing, and every request is a 500."""
    sql(database, "TRUNCATE gate.access_request")

    async def go() -> tuple[list[str | None], int]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                await record(session, FIELD, at=AT)
                await record(session, DEPARTMENT, at=AT.replace(hour=10))
                await session.commit()
                mine = await addressed_to(session, "u_steward", limit=10)
                theirs = await addressed_to(session, "u_one", limit=10)
                return [row.department for row in mine], len(theirs)
        finally:
            await bound.dispose()

    assert run(go) == (["finance", None], 0)


def test_the_table_refuses_a_row_naming_no_subject_and_cannot_be_edited(database: str) -> None:
    """The one-subject check holds at the database, and the application role may not update."""
    from psycopg import errors  # Imported here: the driver loads only where a server runs.

    with pytest.raises(errors.CheckViolation):
        sql(
            database,
            "INSERT INTO gate.access_request (asker_id, owner_id, question, requested_capability) "
            "VALUES ('u', 'o', 'q', 'read:x')",
        )
    with pytest.raises(errors.InsufficientPrivilege):
        sql(database, "SET ROLE brain_app; UPDATE gate.access_request SET question = 'changed'")
