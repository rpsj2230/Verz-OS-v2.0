"""Checking an install's database against the owner's rule, and refusing to check it blind.

`brain.ops.index_audit` is what the owner's install is checked with after a sync: every kept row
held to its source's declaration, and a planted canary looked for in every table. The failure worth
testing first is the one that reads as success: a search that could not see a row, reporting
"found in no table". Then the findings, each beside the clean case.

Task ids: M11.8.2, M11.9.1
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Final

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors import xero
from brain.connectors.manifest import manifest_digest
from brain.connectors.minimal_index import StoredRow, fresh_canary
from brain.ops.connectable import manifest_for
from brain.ops.index_audit import (
    A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED,
    AuditRefusedError,
    AuditReport,
    audit,
    index_findings,
    main,
    tables_holding,
)
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.scratch_postgres import add_modelled, drop, fresh, run, sql

TENANT: Final = "11111111-2222-3333-4444-555555555555"
#: Far from any wall clock; nothing here is about the present.
SEEN: Final = datetime(2019, 6, 1, 12, 0, tzinfo=UTC)
TABLES: Final = ("ops.connector_connection", "proj.record")


def an_invoice(**fields: object) -> StoredRow:
    kept: dict[str, object] = {"tenant_id": TENANT, "status": "AUTHORISED"}
    kept.update(fields)
    return StoredRow(source="xero", entity=xero.ENTITY_INVOICE, source_id="b1f2-0447", fields=kept)


# ------------------------------------------------------------- the findings, without a database


def test_rows_inside_their_declared_index_have_no_finding() -> None:
    """The clean case every finding below needs. Delete this and an audit that flagged every row
    would pass the rest of the file, and every install would read as breaking the rule."""
    assert index_findings([an_invoice()], {"xero": {"tenant_id": TENANT}}) == ()


def test_a_kept_field_outside_the_index_is_named_and_its_value_is_not() -> None:
    """Delete this and a row keeping an amount passes the install's audit."""
    (finding,) = index_findings(
        [an_invoice(amount_due="CANARY-SECRET-1")], {"xero": {"tenant_id": TENANT}}
    )

    assert "'amount_due'" in finding
    assert "CANARY-SECRET-1" not in finding


def test_rows_nothing_can_check_are_a_finding_rather_than_a_pass() -> None:
    """Rows kept for a source never connected, or one whose declaration cannot be built from its
    settings, are rows nobody agreed to. Delete this and they are skipped, and a clean report can
    hold rows no rule was applied to."""
    never = index_findings([an_invoice()], {})
    unbuildable = index_findings([an_invoice()], {"xero": {"tenant_id": "*"}})

    assert len(never) == 1 and "never connected" in never[0]
    assert len(unbuildable) == 1 and "cannot build" in unbuildable[0]


def test_the_report_says_clean_only_when_there_is_nothing_to_say() -> None:
    """Delete this and the command's exit code and its words can disagree."""
    clean = AuditReport(rows=2, index=(), searched=("proj.record",), canary="C", holding=())
    found = AuditReport(rows=2, index=(), searched=("proj.record",), canary="C", holding=("x.y",))

    assert clean.clean and "  found in no table." in clean.lines()
    assert not found.clean and "  found in x.y" in found.lines()
    assert "  every row holds index fields only." in clean.lines()


# ------------------------------------------------------------------ against a database


@contextmanager
def a_database(name: str) -> Iterator[str]:
    url = fresh(name)
    try:
        add_modelled(url, TABLES)
        yield url
    finally:
        drop(name)


def through[T](url: str, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            sessions: async_sessionmaker[AsyncSession] = make_session_factory(engine)
            async with sessions() as session:
                return await work(session)
        finally:
            await engine.dispose()

    return run(go)


def keep(url: str, *, fields: dict[str, object]) -> None:
    settings = {"tenant_id": TENANT}
    sql(
        url,
        "INSERT INTO ops.connector_connection (id, connector, settings, digest, connected_by, "
        "connected_at) VALUES (%s, 'xero', %s, %s, 'u_admin', %s)",
        uuid.uuid4(),
        json.dumps(settings),
        manifest_digest(manifest_for("xero", settings)),
        SEEN,
    )
    sql(
        url,
        "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at) "
        "VALUES ('xero', 'invoice', 'b1f2-0447', %s, %s)",
        json.dumps(fields),
        SEEN,
    )


@pytest.mark.needs_db
def test_a_canary_is_found_in_the_table_that_holds_it_and_in_no_other() -> None:
    """**Both sides of the search.** A string held in a kept row is found in `proj.record` and
    nowhere else, a string held nowhere is found nowhere, and a string held as bytes is found by
    its hexadecimal form. Delete this and a search that read no row, or read every row as a match,
    would pass whichever half was left."""
    held = fresh_canary("held")
    with a_database("brain_index_audit_found") as url:
        keep(url, fields={"tenant_id": TENANT, "status": held})
        sql(url, "CREATE TABLE ops.audit_probe (payload bytea)")
        as_bytes = fresh_canary("bytes")
        sql(url, "INSERT INTO ops.audit_probe VALUES (%s)", as_bytes.encode("utf-8"))
        found = through(url, lambda session: tables_holding(session, held))
        nowhere = through(url, lambda session: tables_holding(session, fresh_canary("absent")))
        in_bytes = through(url, lambda session: tables_holding(session, as_bytes))

    assert found == ("proj.record",)
    assert nowhere == ()
    assert in_bytes == ("ops.audit_probe",)


@pytest.mark.needs_db
def test_a_login_bound_by_row_level_security_is_refused_rather_than_reported_clean() -> None:
    """**The failure that reads as success.** A session running as the application role sees no
    row of a table whose policy it does not satisfy, so its search would find nothing and say so.
    It is refused instead, with the reason. Delete this and the install check can be run as the
    wrong login and report the canary in no table, having looked at no row."""
    with a_database("brain_index_audit_bound") as url:
        keep(url, fields={"tenant_id": TENANT, "status": "AUTHORISED"})

        async def as_the_application(session: AsyncSession) -> tuple[str, ...]:
            await session.execute(text("SET ROLE brain_app"))
            return await tables_holding(session, TENANT)

        with pytest.raises(AuditRefusedError) as refused:
            through(url, as_the_application)
        owner = through(url, lambda session: tables_holding(session, TENANT))

    assert str(refused.value) == A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED
    assert owner == ("ops.connector_connection", "proj.record")


@pytest.mark.needs_db
def test_the_install_check_exits_clean_on_an_index_and_not_on_a_leak(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command the owner's install is checked with: it prints names and never values, exits 0
    when the kept rows are the index and the canary is nowhere, and 1 when either is not. Delete
    this and the command can print a reassuring sentence over a finding."""
    leaked = fresh_canary("leak")
    with a_database("brain_index_audit_command") as url:
        keep(url, fields={"tenant_id": TENANT, "status": "AUTHORISED"})
        clean = main(["--canary", fresh_canary("absent"), url])
        said_clean = capsys.readouterr().out
        sql(
            url,
            "UPDATE proj.record SET fields = fields || jsonb_build_object('amount_due', %s::text)",
            leaked,
        )
        leaking = main(["--canary", leaked, url])
        said_leaking = capsys.readouterr().out
        report = through(url, lambda session: audit(session, canary=leaked))

    assert clean == 0
    assert "found in no table." in said_clean and "every row holds index fields only." in said_clean
    assert leaking == 1
    assert "found in proj.record" in said_leaking and "'amount_due'" in said_leaking
    assert leaked not in said_leaking
    assert report.holding == ("proj.record",)
