"""A helpdesk connected from the console, read by the worker, and reached by its department only.

`tests/unit/test_freshdesk.py` holds the connector without a database. This drives the worker's own
run, `brain.ops.connector_sync_run.sync_on`, over a Freshdesk connection written by the store the
Connectors route writes with, answered by the recorded list page `FRESH-200-list`, into a PostgreSQL
database of the test's own, and then reads what the run kept through the row plane and the redactor
as three people. It reuses `tests/unit/test_connector_sync_run.py`'s stand-ins: the key is a
sentinel, the call is a replay, and the address is the one a stand-in resolver hands out. Nothing
here calls Freshdesk.

**Who reaches a kept ticket is a comparison, not a count.** A person granted the ticket in the
department the connection named is handed both tickets. A person granted the same in another
department, and a person holding nothing, are handed after the run exactly what they were handed
before it, when no ticket existed: DENIED and ABSENT are one answer.

**No ticket body is kept, proved with a canary on a fully migrated database.** A string minted for
the run is planted in every recorded ticket's note and body, the worker reads the page, and the
string is then looked for in every table the product has and in every log line the run wrote.

Task ids: M11.6.2, M11.9.6
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from brain.connectors import freshdesk
from brain.connectors.manifest import manifest_digest
from brain.connectors.minimal_index import fresh_canary, planted, sightings
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.redaction import redact
from brain.core.scope import Scope
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.rows import RowRequest, RowTool, read_rows
from brain.ops.connectable import manifest_for
from brain.ops.connector_store import StoredConnections
from brain.ops.connector_sync import READ_TO_THE_END
from brain.ops.connector_sync_run import SourceAnswer, SyncRun
from brain.ops.credentials import connector_key_slot
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_connector_sync_run import (
    KEY,
    NOW,
    PUBLIC,
    Keys,
    Replay,
    a_database,
    attempts,
    audited,
    projected,
    recorded,
    sync,
    through,
)
from tests.unit.test_freshdesk import DEPARTMENT, DOMAIN, console_settings

#: The ids `FRESH-200-list` records, as `proj.record` keys them.
LISTED: Final = ("88401", "88402")

#: The tickets as a row tool reads them: the row under `read:ticket`, and each kept field, the
#: department included, under the same capability, so a reader's scope is the only thing that
#: decides what they are handed. A classification of the tool's own, as the Xero proof writes one:
#: no row tool for a connected source's records ships in this release.
TICKETS: Final = RowTool(
    source=freshdesk.FRESHDESK,
    classification=TableClassification(
        entity=freshdesk.TICKET,
        rules=tuple(
            ColumnRule(name, Capability(value="read:ticket"), Classification.INTERNAL)
            for name in (*freshdesk.projected_field_names(), "department")
        ),
    ),
    description="Tickets this install keeps from a connected helpdesk.",
)


def a_reader(principal: str, scope: Scope) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=(Grant(capability=Capability(value="read:ticket"), scope=scope),),
    )


SUPPORT: Final = a_reader("u_support", Scope.department(DEPARTMENT))
FINANCE: Final = a_reader("u_finance", Scope.department("finance"))
NOBODY: Final = EntitlementSet(principal_id="u_nobody", grants=())


def connect(url: str) -> None:
    """Connect the helpdesk through the store the Connectors route writes with."""
    settings = console_settings()
    digest = manifest_digest(manifest_for(freshdesk.FRESHDESK, settings))

    async def kept() -> datetime | None:
        return None

    through(
        url,
        lambda sessions: StoredConnections(sessions).connect(
            connector=freshdesk.FRESHDESK,
            settings=settings,
            digest=digest,
            actor="u_admin",
            trace_id="t-connect",
            ent_hash="0" * 32,
            keep_key=kept,
        ),
    )


def listed_answer(body: Any = None) -> SourceAnswer:
    """`FRESH-200-list` as the call would have answered with it, or with this body instead."""
    one = recorded("FRESH-200-list")
    return SourceAnswer(
        status=one.status,
        headers={key.lower(): value for key, value in one.headers.items()},
        body=json.dumps(one.body if body is None else body).encode("utf-8"),
    )


def read_as(url: str, who: EntitlementSet) -> Mapping[str, Any]:
    """What this person is handed: the row plane's statement, then the redactor, as a document."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> Mapping[str, Any]:
        result = await read_rows(
            TICKETS, RowRequest(), entitlement=who, records=SessionRowSource(sessions), now=NOW
        )
        answer = redact(result, entitlement=who, policy=TICKETS.classification.policy(), now=NOW)
        return answer.payload.model_dump(mode="json")

    return through(url, work)


@pytest.mark.needs_db
def test_a_connected_helpdesk_is_read_into_its_index_and_reached_by_its_department_only() -> None:
    """**M11.9.6's connect-and-read half, end to end against the recording.** A helpdesk connected
    with the console's two settings is read by the worker's run with the key the vault would hand
    it: one call, to the helpdesk's own address as the address rule checked it, carrying the key as
    the HTTP Basic pair Freshdesk documents. Both recorded tickets are written to `proj.record` with
    their declared fields and the connection's department, and without their note. The attempt is
    recorded as read to the end, healthy, and due again after the reading's interval.

    Then it is read. A person granted tickets in that department is handed both. A person granted
    them in another department, and a person holding nothing, are each handed, byte for byte, what
    they were handed before the sync ran.

    Delete this and a connected helpdesk can be read into rows nobody reaches, or rows every
    department reaches, with every unit test green."""
    with a_database("brain_freshdesk_sync_records") as url:
        connect(url)
        before = {who.principal_id: read_as(url, who) for who in (SUPPORT, FINANCE, NOBODY)}
        caller = Replay([listed_answer()])
        keys = Keys()
        ran = sync(url, caller, keys=keys)
        after = {who.principal_id: read_as(url, who) for who in (SUPPORT, FINANCE, NOBODY)}
        rows = projected(url)
        (attempt,) = attempts(url)
        stored_text = json.dumps([str(one) for one in (*rows, *attempts(url))])
        connected = sql(url, "SELECT settings FROM ops.connector_connection")

    assert ran == SyncRun(read=1, waiting=0, failed=0, not_due=0, cannot_be_read=0)
    assert [ref.path for ref in keys.asked] == [connector_key_slot(freshdesk.FRESHDESK).path]
    (call,) = caller.calls
    assert call.address == PUBLIC
    assert call.url.startswith(f"https://{DOMAIN}/api/v2/tickets?")
    assert "updated_since=" in call.url and "per_page=100" in call.url
    pair = base64.b64encode(f"{KEY}:X".encode()).decode("ascii")
    assert call.headers["Authorization"] == f"Basic {pair}"
    assert connected == [(console_settings(),)]

    assert [(source, entity, source_id) for source, entity, source_id, *_ in rows] == [
        (freshdesk.FRESHDESK, freshdesk.TICKET, one) for one in LISTED
    ]
    for _, _, _, fields, _, deleted_at in rows:
        assert deleted_at is None
        assert fields["department"] == DEPARTMENT
        assert set(fields) <= {*freshdesk.projected_field_names(), "department"}
        assert "custom_fields" not in fields
    assert "CANARY" not in stored_text
    assert KEY not in stored_text

    outcome, health, records, documents, failures, next_at, finished_at, detail = attempt
    assert (outcome, health, records, documents, failures, detail) == (
        "synced",
        "ok",
        2,
        0,
        0,
        READ_TO_THE_END,
    )
    assert next_at == finished_at + freshdesk.READING_INTERVAL

    assert sorted(one["id"] for one in after["u_support"]["records"]) == list(LISTED)
    assert all(one["department"] == DEPARTMENT for one in after["u_support"]["records"])
    assert before["u_support"]["records"] == []
    for principal in ("u_finance", "u_nobody"):
        assert after[principal] == before[principal], principal


@pytest.mark.needs_db
def test_a_synced_helpdesk_keeps_no_ticket_body_and_its_canary_is_in_no_table_or_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """**The owner's rule for Freshdesk, on a database built through every migration.** A canary
    minted for this run is planted in every recorded ticket's note and in a body each ticket
    carries, as the list sends it when a description is included, and the worker reads the page.
    The canary is then in no table this product has, `know.chunk` and `know.item` included, and in
    no log line the run wrote.

    The positive half is in the same database: a ticket id, which is an index field, is found in
    `proj.record` by the same search, so a search that could not read a row fails here rather than
    reporting clean.

    Delete this and the reading can start keeping a ticket's body, or a run can log one, with every
    test over single records green."""
    import brain.tables  # noqa: F401 - registers every table on the metadata
    from brain.db import metadata
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url

    if not has_pgvector(admin_url()):
        pytest.skip("every table needs the full chain, which needs pgvector; CI's image has it")
    canary = fresh_canary("FRESHDESK")
    bodies = [
        {**row, "description": "CANARY-BODY-HTML", "description_text": "CANARY-BODY-TEXT"}
        for row in recorded("FRESH-200-list").body
    ]
    caplog.set_level(logging.DEBUG)
    with retirable("brain_freshdesk_sync_canary") as url, capture_logs() as logged:
        connect(url)
        ran = sync(url, Replay([listed_answer(planted(bodies, canary))]))
        report = audited(url, canary)
        ticket = audited(url, LISTED[0])
        rows = projected(url)

    assert ran.read == 1
    assert len(rows) == len(LISTED)
    assert report.rows == len(rows)
    assert report.index == ()
    assert set(metadata.tables) <= set(report.searched), "a modelled table was not searched"
    assert report.holding == ()
    assert "proj.record" in ticket.holding
    assert sightings(canary, logged, [one.getMessage() for one in caplog.records]) == ()
