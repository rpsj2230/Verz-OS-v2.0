"""Checking an install's database against the owner's rule: index fields only, and no canary.

`brain.connectors.minimal_index` proves the rule against the rows a connector's code keeps from its
recordings, which is evidence about this release. This is the same check pointed at an install's
own database, which is evidence about that install: every `proj.record` row is held to the minimal
index its source's declaration names today, and a canary string somebody planted in a source (in
an invoice's reference, say) is looked for in every table this database has. `python -m
brain.ops.index_audit --canary <string>` prints both answers and exits non-zero on either finding.

**It refuses to run as a login that cannot see every row.** Most tables here enable row-level
security, and a login bound by it reads the rows its settings admit, which for a login with no
settings is none. A scan that read nothing would print "found in no table", which is the answer
the check exists to give and the one that must never be given for the wrong reason. So the login
must be a superuser or hold BYPASSRLS, which the schema's owner does, and the command reads the
owner's URL (`brain.settings.Settings.owner_database_url`) for that reason. See
`A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED`.

**A table is searched by its rows' text, and a column of bytes by its hexadecimal form too.**
`row::text` renders every column, JSON and arrays included, so a canary anywhere in a row is found
by one `strpos`; a `bytea` column renders as `\\x` and hex, so the canary's hex is looked for as
well. What cannot be found this way is a value stored encrypted or compressed by the application,
which by construction is not the value any more.

**What it prints is names, never values.** A finding names the table, or the row's source, entity
and id with the field, which are what an index may hold; it never prints the field's value,
because the value is what should not have been kept and the output is read by whoever runs it.

Scope: the SQL and the command. The rule is `brain.connectors.minimal_index`'s and the manifests
are the declarations'; nothing here decides what may be kept.

Task ids: M11.8.2, M11.9.1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.connectors.contract import ConnectorContractError
from brain.connectors.minimal_index import StoredRow, minimal_index_findings
from brain.ops.connectable import NotConnectableError, manifest_for

# ------------------------------------------------------------------ written-down reasons
#: Why the command refuses a login bound by row-level security.
A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED: Final = (
    "A login bound by row-level security reads the rows its settings admit, and with none set "
    "that is no rows at all. A search through tables it cannot read finds nothing and would be "
    "reported as clean, so the command runs only as a login that sees every row."
)

#: The schemas PostgreSQL keeps for itself, which hold nothing a connector wrote.
SYSTEM_SCHEMAS: Final = ("pg_catalog", "information_schema")


class AuditRefusedError(Exception):
    """The audit was asked to run somewhere its answer would mean nothing."""


def _quoted(identifier: str) -> str:
    """An identifier as PostgreSQL reads it, whatever it contains."""
    return '"' + identifier.replace('"', '""') + '"'


async def sees_every_row(session: AsyncSession) -> bool:
    """Whether this login is exempt from row-level security. See the module docstring."""
    found = await session.execute(
        text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
    )
    return bool(found.scalar_one_or_none())


async def every_table(session: AsyncSession) -> tuple[str, ...]:
    """Every ordinary table in this database outside PostgreSQL's own schemas, as schema.table."""
    found = await session.execute(
        text(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema <> ALL(CAST(:system AS text[])) "
            "AND table_schema NOT LIKE 'pg_toast%' ORDER BY table_schema, table_name"
        ),
        {"system": list(SYSTEM_SCHEMAS)},
    )
    return tuple(f"{schema}.{table}" for schema, table in found.all())


async def tables_holding(session: AsyncSession, needle: str) -> tuple[str, ...]:
    """Every table in this database holding `needle` anywhere in a row. Empty when none does.

    The canary half of M11.8.2 on a database: later connector packages call it after driving a
    recorded answer through the worker, and the command calls it on an install. Refused for a
    login that cannot see every row, for `A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED`.
    """
    if not needle.strip():
        msg = "an empty string is in every row; give the canary that was planted"
        raise AuditRefusedError(msg)
    if not await sees_every_row(session):
        raise AuditRefusedError(A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED)
    as_hex = needle.encode("utf-8").hex()
    holding: list[str] = []
    for qualified in await every_table(session):
        schema, table = qualified.split(".", 1)
        statement = text(
            f"SELECT 1 FROM {_quoted(schema)}.{_quoted(table)} AS r "  # noqa: S608
            "WHERE strpos(r::text, :needle) > 0 OR strpos(r::text, :as_hex) > 0 LIMIT 1"
        )
        found = await session.execute(statement, {"needle": needle, "as_hex": as_hex})
        if found.first() is not None:
            holding.append(qualified)
    return tuple(holding)


# ------------------------------------------------------------------ the kept index
async def kept_rows(session: AsyncSession) -> tuple[StoredRow, ...]:
    """Every `proj.record` row still standing, as source, entity, id and fields."""
    found = await session.execute(
        text(
            "SELECT source, entity, source_id, fields FROM proj.record "
            "WHERE deleted_at IS NULL ORDER BY source, entity, source_id"
        )
    )
    return tuple(
        StoredRow(source=source, entity=entity, source_id=source_id, fields=dict(fields or {}))
        for source, entity, source_id, fields in found.all()
    )


async def latest_settings(session: AsyncSession) -> Mapping[str, Mapping[str, str]]:
    """Each connected source's settings from its most recent connection, live or not.

    The most recent rather than the live one, because a disconnected source's rows stay kept
    (`brain.connectors.registry` has no unregister) and are still held to the index it declared.
    """
    found = await session.execute(
        text(
            "SELECT DISTINCT ON (connector) connector, settings FROM ops.connector_connection "
            "ORDER BY connector, connected_at DESC"
        )
    )
    return {
        connector: {str(k): str(v) for k, v in dict(settings or {}).items()}
        for connector, settings in found.all()
    }


def index_findings(
    rows: Sequence[StoredRow], settings: Mapping[str, Mapping[str, str]]
) -> tuple[str, ...]:
    """Every way the kept rows exceed their sources' minimal indexes. Empty when none do.

    Each source's rows are held to the manifest its connection's settings build today, which is
    the declaration the worker writes under. A source whose manifest cannot be built is a finding
    rather than a pass: rows nothing can check are rows nobody agreed to.
    """
    found: list[str] = []
    by_source: dict[str, list[StoredRow]] = {}
    for row in rows:
        by_source.setdefault(row.source, []).append(row)
    for source, kept in sorted(by_source.items()):
        given = settings.get(source)
        if given is None:
            found.append(f"{len(kept)} row(s) are kept for {source}, which was never connected")
            continue
        try:
            manifest = manifest_for(source, given)
        except (NotConnectableError, ConnectorContractError):
            found.append(
                f"{len(kept)} row(s) are kept for {source}, whose declaration this release "
                "cannot build from its settings, so nothing can check them"
            )
            continue
        found.extend(minimal_index_findings(manifest, kept))
    return tuple(found)


@dataclass(frozen=True)
class AuditReport:
    """What one audit found: how many rows it held to an index, and every finding."""

    rows: int
    index: tuple[str, ...]
    #: Every table the canary was looked for in. Empty when no canary was given.
    searched: tuple[str, ...]
    canary: str
    holding: tuple[str, ...]

    def lines(self) -> tuple[str, ...]:
        said = [
            f"proj.record: {self.rows} row(s) checked against their sources' declarations.",
            *(f"  outside the index: {one}" for one in self.index),
        ]
        if not self.index:
            said.append("  every row holds index fields only.")
        if self.canary:
            said.append(f"canary: searched {len(self.searched)} table(s).")
            said.extend(f"  found in {one}" for one in self.holding)
            if not self.holding:
                said.append("  found in no table.")
        return tuple(said)

    @property
    def clean(self) -> bool:
        return not self.index and not self.holding


async def audit(session: AsyncSession, *, canary: str = "") -> AuditReport:
    """The kept index held to its declarations, and the canary looked for in every table."""
    if not await sees_every_row(session):
        raise AuditRefusedError(A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED)
    rows = await kept_rows(session)
    index = index_findings(rows, await latest_settings(session))
    searched = await every_table(session) if canary else ()
    holding = await tables_holding(session, canary) if canary else ()
    return AuditReport(
        rows=len(rows), index=index, searched=searched, canary=canary, holding=holding
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.index_audit [--canary STRING] [database-url]`.

    The database is the schema owner's (`Settings.owner_database_url`) unless one is given, for
    `A_SCAN_THAT_CANNOT_SEE_A_ROW_HAS_NOT_LOOKED`. Exit 0 when clean, 1 on a finding, 2 when the
    audit could not run.
    """
    from brain.session import make_app_engine, make_session_factory
    from brain.settings import Settings

    parser = argparse.ArgumentParser(prog="python -m brain.ops.index_audit")
    parser.add_argument("--canary", default="", help="a string planted in a source to look for")
    parser.add_argument("database_url", nargs="?", default="")
    asked = parser.parse_args(argv)
    url = asked.database_url or Settings().owner_database_url()
    if not url:
        print("no database url: pass one, or set DATABASE_URL", file=sys.stderr)
        return 2

    async def go() -> AuditReport:
        engine = make_app_engine(url)
        try:
            async with make_session_factory(engine)() as session:
                return await audit(session, canary=asked.canary)
        finally:
            await engine.dispose()

    try:
        report = asyncio.run(go())
    except AuditRefusedError as refused:
        print(str(refused), file=sys.stderr)
        return 2
    print("\n".join(report.lines()))
    return 0 if report.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
