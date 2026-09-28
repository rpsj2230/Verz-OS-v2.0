"""Where an uploaded table's classification and rows are kept, and how Ask reaches them.

`brain.knowledge.columns` decides what a classification is, `brain.knowledge.classified_rows`
decides what a caller may read out of one, and this holds the connection. The split is
`brain.ops.limits` and `brain.ops.limit_store`'s, and for its reason: nothing here decides a
permission, so there is nothing here that needs a database to test the case that is always
wrong.

**A classification is stored whole and read back through the type that refuses a bad one.**
`columns_document` writes the rules as one JSON array and `classification_from` reads them
back through `ColumnRule` and `TableClassification`, so a row edited by hand into a derivation
naming a missing column fails to load rather than loading as a table with a hole in its
policy. It fails loudly: a table that does not load is left out of Ask for every caller alike
and logged, which is `brain.gate.rule_store`'s choice about a rule set that does not validate.

**Every write says who made it, before it makes it.** The routes pass the statements
`brain.attribution.of_request` builds, and they run first in the transaction the write is in,
so the ledger entry `0116`'s trigger appends names the administrator, their reach and the
request rather than `0003`'s placeholders. A write with no attribution is refused here rather
than written anonymously, because an anonymous change to who may read the cost column is the
entry an auditor most needs and would least be able to use.

**Ask reads the live tables on every question.** `classified_lane_of` is the answer route's
one call: the tables as they stand, a reader for each over the application's pool, and each
one's policy for redaction and for the answer cache's epoch. One small query per question,
against the fast lane's rule of reading nothing ahead of the lane, and paid because an upload
or a changed derivation then reaches the next question rather than the next restart.

Task ids: M7.5.1, M7.5.3, M7.7.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol

import structlog
from pydantic import ValidationError
from sqlalchemy import TextClause, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import Capability
from brain.core.field_policy import Classification
from brain.knowledge.classified_rows import ClassifiedLane, StoredTable, lane_for
from brain.knowledge.columns import ColumnClassificationError, ColumnRule, TableClassification
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.rows import RowSource
from brain.tables.classified_table import ClassifiedRecordRow, ClassifiedTableRow

log = structlog.get_logger()

#: Why a write carries its attribution in, rather than the store reading it from anywhere.
A_CLASSIFICATION_CHANGE_NAMES_WHO_MADE_IT: Final = (
    "Every write to a classified table is ledgered by 0116's trigger, and the trigger learns who "
    "is writing only from the three settings brain.attribution builds from the request. The "
    "store takes those statements as an argument and runs them first, and refuses a write that "
    "brings none, because the entry an unattributed change produces names nobody, at no reach, "
    "in no request: a change to who may read a cost column that nobody can be asked about."
)

#: How many rows one statement inserts. A price list is a few hundred rows; the bound keeps a
#: ten-thousand-row upload from becoming one statement with forty thousand parameters.
INSERT_BATCH: Final = 500


class ClassifiedTableStoreError(Exception):
    """A write this store will not make. The routes answer it as a refusal the uploader reads."""


class ClassifiedTables(Protocol):
    """What the Classification routes and Ask need from wherever uploaded tables are kept."""

    async def table(self, entity: str) -> StoredTable | None: ...

    async def live_tables(self) -> tuple[StoredTable, ...]: ...

    async def upload(
        self,
        table: StoredTable,
        rows: Sequence[Mapping[str, str]],
        *,
        actor_id: str,
        attribution: Sequence[TextClause],
    ) -> StoredTable: ...

    async def classify(
        self,
        entity: str,
        classification: TableClassification,
        *,
        actor_id: str,
        attribution: Sequence[TextClause],
    ) -> StoredTable | None: ...

    def records(self) -> RowSource: ...


# ------------------------------------------------------------------ the document


def columns_document(classification: TableClassification) -> list[dict[str, Any]]:
    """The rules as the JSON array `know.classified_table.columns` holds, in declared order."""
    return [
        {
            "column": rule.column,
            "required_capability": rule.required_capability.value,
            "classification": rule.classification.value,
            "derived_from": sorted(rule.derived_from),
        }
        for rule in classification.rules
    ]


def classification_from(entity: str, document: object) -> TableClassification:
    """The rules read back through the types that refuse a bad one. See the module docstring."""
    if not isinstance(document, list):
        msg = f"{entity}'s stored classification is not a list of rules"
        raise ColumnClassificationError(msg)
    rules: list[ColumnRule] = []
    for item in document:
        if not isinstance(item, dict):
            msg = f"{entity}'s stored classification holds something that is not a rule"
            raise ColumnClassificationError(msg)
        try:
            rules.append(
                ColumnRule(
                    column=str(item["column"]),
                    required_capability=Capability(value=str(item["required_capability"])),
                    classification=Classification(str(item["classification"])),
                    derived_from=frozenset(str(name) for name in item.get("derived_from", [])),
                )
            )
        except (KeyError, ValueError, ValidationError) as exc:
            msg = f"{entity}'s stored classification holds a rule that does not load"
            raise ColumnClassificationError(msg) from exc
    classification = TableClassification(entity=entity, rules=tuple(rules))
    # Built here so a rule the field policy refuses (a write capability, say) refuses the load.
    classification.policy()
    return classification


def stored_table_of(row: ClassifiedTableRow) -> StoredTable:
    """One table row as the lane reads it, refused whole if its classification does not load."""
    return StoredTable(
        classification=classification_from(row.entity, row.columns),
        title=row.title,
        key_column=row.key_column,
        version=row.version,
    )


# --------------------------------------------------------------------- the store


class SqlClassifiedTables:
    """The tables in `know.classified_table` and `know.classified_row`, over the app's pool."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    def records(self) -> RowSource:
        return SessionRowSource(self._sessions)

    async def table(self, entity: str) -> StoredTable | None:
        async with self._sessions() as session:
            row = await _live_row(session, entity)
        return None if row is None else stored_table_of(row)

    async def live_tables(self) -> tuple[StoredTable, ...]:
        async with self._sessions() as session:
            result = await session.execute(
                select(ClassifiedTableRow)
                .where(ClassifiedTableRow.deleted_at.is_(None))
                .order_by(ClassifiedTableRow.entity)
            )
            rows = list(result.scalars().all())
        tables: list[StoredTable] = []
        for row in rows:
            try:
                tables.append(stored_table_of(row))
            except ColumnClassificationError:
                # Left out of Ask for everybody alike, and said where an operator reads it.
                log.error("classification_store.table_does_not_load", entity=row.entity)
        return tuple(tables)

    async def upload(
        self,
        table: StoredTable,
        rows: Sequence[Mapping[str, str]],
        *,
        actor_id: str,
        attribution: Sequence[TextClause],
    ) -> StoredTable:
        """Write the table and its rows under the table's version, in one transaction."""
        _require(attribution)
        async with self._sessions() as session:
            for statement in attribution:
                await session.execute(statement)
            current = await _live_row(session, table.entity, lock=True)
            expected = 1 if current is None else current.version + 1
            if table.version != expected:
                msg = "somebody else uploaded this table a moment ago; upload it again"
                raise ClassifiedTableStoreError(msg)
            document = columns_document(table.classification)
            if current is None:
                await session.execute(
                    insert(ClassifiedTableRow).values(
                        entity=table.entity,
                        title=table.title,
                        key_column=table.key_column,
                        columns=document,
                        version=table.version,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            else:
                await session.execute(
                    update(ClassifiedTableRow)
                    .where(ClassifiedTableRow.entity == table.entity)
                    .where(ClassifiedTableRow.deleted_at.is_(None))
                    .values(
                        title=table.title,
                        key_column=table.key_column,
                        columns=document,
                        version=table.version,
                        updated_by=actor_id,
                    )
                )
            values = [
                {
                    "entity": table.entity,
                    "version": table.version,
                    "position": position,
                    "fields": dict(row),
                }
                for position, row in enumerate(rows)
            ]
            for start in range(0, len(values), INSERT_BATCH):
                await session.execute(
                    insert(ClassifiedRecordRow), values[start : start + INSERT_BATCH]
                )
            await session.commit()
        return table

    async def classify(
        self,
        entity: str,
        classification: TableClassification,
        *,
        actor_id: str,
        attribution: Sequence[TextClause],
    ) -> StoredTable | None:
        """Replace one live table's classification whole. None when no live table has the name."""
        _require(attribution)
        async with self._sessions() as session:
            for statement in attribution:
                await session.execute(statement)
            current = await _live_row(session, entity, lock=True)
            if current is None:
                return None
            stored = StoredTable(
                classification=classification,
                title=current.title,
                key_column=current.key_column,
                version=current.version,
            )
            await session.execute(
                update(ClassifiedTableRow)
                .where(ClassifiedTableRow.entity == entity)
                .where(ClassifiedTableRow.deleted_at.is_(None))
                .values(columns=columns_document(classification), updated_by=actor_id)
            )
            await session.commit()
        return stored


def _require(attribution: Sequence[TextClause]) -> None:
    if not attribution:
        raise ClassifiedTableStoreError(A_CLASSIFICATION_CHANGE_NAMES_WHO_MADE_IT)


async def _live_row(
    session: AsyncSession, entity: str, *, lock: bool = False
) -> ClassifiedTableRow | None:
    statement = (
        select(ClassifiedTableRow)
        .where(ClassifiedTableRow.entity == entity)
        .where(ClassifiedTableRow.deleted_at.is_(None))
    )
    if lock:
        # Two uploads of one table at once would both compute the same next version; the lock
        # makes the second wait, see the first one's version, and refuse.
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------- the wiring


def classified_tables_of(state: object) -> ClassifiedTables | None:
    """What this process keeps uploaded tables in: what a test installed, the database, or none."""
    installed = getattr(state, "classified_tables", None)
    if installed is not None:
        return installed  # type: ignore[no-any-return]
    sessions = getattr(state, "db_sessions", None)
    return SqlClassifiedTables(sessions) if isinstance(sessions, async_sessionmaker) else None


async def classified_lane_of(state: object) -> ClassifiedLane:
    """The uploaded tables as Ask reads them on this question. Empty on a process with no store.

    The answer route's one call. It merges `rules`, `readers` and `policies` into what the
    registry provides before the answer cache's key is computed, so a changed derivation moves
    the epoch the cache is keyed on.
    """
    tables = classified_tables_of(state)
    if tables is None:
        return ClassifiedLane()
    return lane_for(await tables.live_tables(), tables.records())
