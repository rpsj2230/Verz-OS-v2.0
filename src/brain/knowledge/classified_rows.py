"""Answering from a table somebody uploaded, through the row plane's own decisions.

`brain.knowledge.rows` reads `proj.record`, the bounded copy of a connector's records, and a
price list somebody uploaded is not one: it is the company's own data, held whole in
`know.classified_row` (`brain.tables.classified_table`). So the statement that reads it is
built here. **What decides a permission is not.** The column list is
`rows.compile_projection`, the row grant is `rows.row_scope_for`, both predicates are
`brain.core.scope_sql.compile_where` and the empty case is `rows.NOTHING`, called rather than
copied, so "may this person see the cost" has the one answer it has for every other entity.
What is new is the FROM clause and the pin to one table's live upload, which is the part that
is about where the rows are rather than about who may read them.

**A caller short of a column's grant is never sent the column, and cannot find it by filtering
on it.** The SELECT list is the compiled projection, so the cost is not in the statement a
salesperson's question runs; and a filter naming a column outside the projection compiles the
whole request to nothing, for `rows._compile_filters`'s reason: `cost = 400` returning a row
is a value oracle built out of a WHERE clause. Nothing rather than a refusal, so a person
asking for the cost of a product that exists is answered exactly as one asking about a product
that does not. That is what "absent, not refused" means on Ask, and
`A_RESTRICTED_COLUMN_IS_ABSENT_FOR_A_CALLER_WITHOUT_ITS_GRANT` is the sentence for it.

**Ask reaches a table through question shapes this module writes, not ones a person types.**
The fast lane answers a question that exactly matches a rule's template (`brain.gate.
fast_lane`), and a table's rules are generated from its classification: `what is the sell
price of {name}`, for every column but the one a question names a row by. They are generated
rather than stored because a stored rule naming a column is a second copy of the column list,
and the copy is what goes stale the day a heading is renamed. A rule is generated for a
restricted column too, and that is the point rather than an oversight: the rule matches for
everybody, and whether it answers is decided by the projection for the person asking.

**Two tables with a column of one name are asked in the same words, and each answers for its own
rows.** Until 2026-09-29 the fast lane refused two rules matching one question, so a second price
list with a sell price column made Ask answer nobody about either, which the owner's install
showed the day a second list was uploaded. The same words for two tables are one question asked
of two places, and `brain.gate.fast_lane.respond` now reads each at the asker's reach and answers
from the one holding the name; a table the asker may not read contributes nothing, as a table
never uploaded would. See `brain.gate.fast_lane`'s
`ONE_QUESTION_ASKED_OF_SEVERAL_PLACES_IS_READ_IN_EACH`.

**The lane is built per question, from the tables as they stand.** `lane_for` is pure; the
caller reads the live tables and hands them in. A table classified a moment ago is therefore
answered under its new classification on the next question, and the classification's policy
goes into the answer cache's epoch beside every other entity's, so an answer computed under
the old rule is never served under the new one.

Rejected: registering a `RowTool` per uploaded table at startup. The registry is frozen when
the process starts, so an upload would reach Ask only after a restart, and the tool would read
`proj.record`, which holds none of these rows.

Task ids: M7.5.2, M7.7.3
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

import structlog
from pydantic import ValidationError
from sqlalchemy import String, cast, select, text

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.field_policy import FieldPolicy
from brain.core.scope_sql import ColumnLayout, CompiledPredicate, compile_where
from brain.gate.fast_lane import FastPathRule, RowReader
from brain.knowledge.columns import (
    ColumnAccess,
    ColumnClassificationError,
    ColumnRule,
    TableClassification,
    first_classification,
    marked,
)
from brain.knowledge.rows import (
    ENTITY_KEY,
    FILTER_PREFIX,
    ID_KEY,
    NOTHING,
    SCOPE_PREFIX,
    RowQuery,
    RowRecord,
    RowRequest,
    RowSource,
    compile_projection,
    row_scope_for,
    scope_carried,
)
from brain.tables.classified_table import ClassifiedRecordRow

log = structlog.get_logger()

#: Why a person without a column's grant is told what a person asking about nothing is told.
A_RESTRICTED_COLUMN_IS_ABSENT_FOR_A_CALLER_WITHOUT_ITS_GRANT: Final = (
    "A question about the cost of a product, asked by somebody who does not hold the cost "
    "grant, runs a statement whose SELECT list has no cost in it, so the answer has no cost "
    "to give and the lane abstains in the words it uses for a product that does not exist. "
    "A refusal naming the cost would tell the asker that the column exists, that it has a "
    "value for this product, and that somebody else can read it, which is three facts they "
    "did not have."
)

#: The source every uploaded table is answered under. One name for all of them, because the
#: rows are this installation's own rather than a connected system's, and the fast lane keys
#: its readers on a source and an entity.
TABLES_SOURCE: Final = "tables"

#: The table the rows are read from, and where a field lives on it.
ROWS: Final = ClassifiedRecordRow.__table__
ROW_LAYOUT: Final = ColumnLayout(jsonb_column="fields")

#: The question shapes a column is asked about in. Each is checked by `FastPathRule` itself,
#: so a shape whose literal text is too short for the fast lane's floor is dropped rather than
#: weakened: `cost of {name}` is eight characters of literal and the floor is twelve.
QUESTION_SHAPES: Final[tuple[str, ...]] = (
    "what is the {label} of {slot}",
    "what is the {label} for {slot}",
    "what's the {label} of {slot}",
    "{label} of {slot}",
    "{label} for {slot}",
)


class StoredTable:
    """One uploaded table as the lane reads it: its classification, its title, its key, its upload.

    A plain class with a validating constructor rather than a dataclass, because the one rule it
    holds is about two of its fields at once: the key column has to be a classified column, or
    every question about the table filters on something no rule governs and answers nothing.
    """

    __slots__ = ("classification", "key_column", "title", "version")

    def __init__(
        self, *, classification: TableClassification, title: str, key_column: str, version: int
    ) -> None:
        if classification.rule_for(key_column) is None:
            msg = f"the key column {key_column!r} is not a column of {classification.entity}"
            raise ColumnClassificationError(msg)
        if version < 1:
            msg = f"an upload's version starts at 1, not {version}"
            raise ColumnClassificationError(msg)
        self.classification = classification
        self.title = title
        self.key_column = key_column
        self.version = version

    @property
    def entity(self) -> str:
        return self.classification.entity

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StoredTable):
            return NotImplemented
        return (self.classification, self.title, self.key_column, self.version) == (
            other.classification,
            other.title,
            other.key_column,
            other.version,
        )

    def __hash__(self) -> int:
        return hash((self.classification.entity, self.version))

    def __repr__(self) -> str:
        return f"StoredTable({self.entity!r}, version={self.version})"


def next_upload(
    existing: StoredTable | None,
    *,
    entity: str,
    title: str,
    key_column: str | None,
    columns: Sequence[str],
) -> StoredTable:
    """The table an upload of these columns makes, given the one it replaces if any.

    **An upload never widens anything.** A first upload starts from
    `columns.first_classification`, which opens nothing a price list would not. A second keeps
    the rule of every column that is still there, starts a new column restricted, and drops the
    rule of a column that is gone. If a kept derivation names a dropped column the table would
    not load, and that is refused rather than repaired: repairing it means dropping the
    derivation, which is the one edit that widens who can work out the column it protected.

    The key column is the one named, else the one the table already had if it is still there,
    else the first column.
    """
    if existing is None:
        classification = first_classification(entity, columns)
    else:
        kept: list[ColumnRule] = []
        for column in columns:
            rule = existing.classification.rule_for(column)
            if rule is None:
                kept.append(marked(entity, column, ColumnAccess.RESTRICTED))
            else:
                kept.append(rule)
        classification = TableClassification(entity=entity, rules=tuple(kept))
    if key_column is None:
        still = existing is not None and existing.key_column in columns
        key_column = existing.key_column if still and existing is not None else columns[0]
    return StoredTable(
        classification=classification,
        title=title,
        key_column=key_column,
        version=1 if existing is None else existing.version + 1,
    )


# ------------------------------------------------------------------- the statement


def _filters(table: StoredTable, request: RowRequest, columns: Sequence[str]) -> CompiledPredicate:
    """The asker's narrowing, or nothing when it names a column outside the projection.

    `rows._compile_filters`'s rule, restated here because that function is private to a module
    whose table is a different one. The test beside this module holds the two to the same
    outcome on the same request, so the restatement cannot drift unnoticed.
    """
    unreachable = sorted({clause.field for clause in request.filters.clauses} - set(columns))
    if unreachable:
        log.warning("classified_rows.filter_outside_projection", entity=table.entity)
        return NOTHING
    return compile_where(request.filters, ROW_LAYOUT, param_prefix=FILTER_PREFIX)


def compile_table_query(
    table: StoredTable,
    request: RowRequest,
    *,
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> RowQuery:
    """One caller's question against one uploaded table, as one statement.

    The row plane's order, for its reason: the projection from grants first, because it can be
    decided without a row; the scope and the filters second, into the WHERE clause, because
    they are predicates over rows. A caller holding no grant on the table compiles to `FALSE`
    and the statement is never run.

    The fields the reader's scopes test are selected beside the projection, for
    `brain.knowledge.rows.A_RECORD_CARRIES_WHAT_ITS_READERS_SCOPES_TEST`: an upload that did not
    mark its department column open, read by a department-scoped reader, otherwise reached the
    redactor unable to show that the row was theirs, and every field was withheld.
    """
    rows = row_scope_for(table.entity, entitlement, now)
    columns = compile_projection(table.classification, entitlement=entitlement, rows=rows, now=now)
    carried = scope_carried(rows, columns)
    caller = NOTHING if rows is None else compile_where(rows, ROW_LAYOUT, param_prefix=SCOPE_PREFIX)
    predicate = caller.and_(_filters(table, request, columns))
    statement = (
        select(
            ROWS.c.entity.label(ENTITY_KEY),
            cast(ROWS.c.position, String).label(ID_KEY),
            *(ROWS.c.fields[name].astext.label(name) for name in (*columns, *carried)),
        )
        # The pin to this table's live upload. System narrowing about where the rows are, not
        # a permission: every value in it came from the stored table, none from the asker.
        .where(ROWS.c.entity == table.entity)
        .where(ROWS.c.version == table.version)
        .where(text(predicate.where).bindparams(**predicate.params))
        .order_by(ROWS.c.position)
        .limit(request.limit)
    )
    return RowQuery(
        entity=table.entity,
        source=TABLES_SOURCE,
        columns=columns,
        statement=statement,
        certainly_empty=predicate.certainly_empty,
        carried=carried,
    )


async def read_table_rows(
    table: StoredTable,
    request: RowRequest,
    *,
    entitlement: EntitlementSet,
    records: RowSource,
    now: datetime | None = None,
) -> TypedResult[RowRecord]:
    """Compile, fetch, and build each record out of the projection rather than out of the row.

    `rows.read_rows`'s construction: a key the source hands back that the projection did not
    ask for has no path into a record, and a statement that cannot return a row is not run.
    """
    query = compile_table_query(table, request, entitlement=entitlement, now=now)
    fetched: Sequence[Mapping[str, Any]] = (
        () if query.certainly_empty else await records.rows(query)
    )
    built = tuple(
        RowRecord(
            entity=query.entity,
            id=str(row[ID_KEY]),
            **{
                name: row[name]
                for name in (*query.columns, *query.carried)
                if name in row and row[name] is not None
            },
        )
        for row in fetched
    )
    return TypedResult(
        records=built,
        source=TABLES_SOURCE,
        fetched_at=now.isoformat() if now is not None else "",
        truncated=len(built) == request.limit,
    )


def table_reader(table: StoredTable, records: RowSource) -> RowReader:
    """The fast lane's reader for one table, bound to where its rows are run."""

    async def read(
        request: RowRequest, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[RowRecord]:
        return await read_table_rows(
            table, request, entitlement=entitlement, records=records, now=now
        )

    reader: Callable[..., Awaitable[TypedResult[RowRecord]]] = read
    return reader


# ------------------------------------------------------------------ the questions


def label_of(column: str) -> str:
    """How a column is said in a question: `sell_price` is `sell price`."""
    return column.replace("_", " ")


def rule_name(entity: str, column: str, shape: int | str, *, source: str = TABLES_SOURCE) -> str:
    """A rule's name: readable at the front for a log line, and unique by the digest behind it.

    Truncated names alone could collide between two long entities, and the lane refuses a rule
    set in which one id names two rules. A source other than the uploaded tables is in the digest,
    so a connected source's `invoice.status` and an uploaded table called `invoice` are two names;
    the tables' own digest is unchanged, so no uploaded table's rules are renamed by it.
    """
    named = f"{entity}.{column}" if source == TABLES_SOURCE else f"{source}.{entity}.{column}"
    digest = hashlib.sha256(named.encode()).hexdigest()[:8]
    return f"{entity[:20]}_{column[:20]}_{digest}_{shape}"


def questions_over(
    classification: TableClassification,
    *,
    source: str,
    key_column: str,
    unasked: frozenset[str] = frozenset(),
) -> tuple[FastPathRule, ...]:
    """The question shapes one classified entity answers: a record named by its key, and a column.

    One set per column other than the key and the `unasked`, each in every one of
    `QUESTION_SHAPES` that `FastPathRule` accepts: a shape it refuses is dropped, and only that
    shape. Shared by the uploaded tables and the connected sources
    (`brain.knowledge.connector_rows`), so a question is asked of either in the same words.
    """
    rules: list[FastPathRule] = []
    for column in classification.columns():
        if column == key_column or column in unasked:
            continue
        for shape, template in enumerate(QUESTION_SHAPES):
            try:
                rules.append(
                    FastPathRule(
                        rule_id=rule_name(classification.entity, column, shape, source=source),
                        template=template.format(
                            label=label_of(column), slot="{" + key_column + "}"
                        ),
                        slot=key_column,
                        source=source,
                        entity=classification.entity,
                        match_field=key_column,
                        answer_field=column,
                    )
                )
            except ValidationError:
                continue
    return tuple(rules)


def questions_for(table: StoredTable) -> tuple[FastPathRule, ...]:
    """The question shapes this table answers, one set per column other than the key."""
    return questions_over(table.classification, source=TABLES_SOURCE, key_column=table.key_column)


# ----------------------------------------------------------------------- the lane


@dataclass(frozen=True)
class ClassifiedLane:
    """What Ask needs from the uploaded tables: their question shapes, readers and policies.

    Merged by the answer route into what the registry already provides. The policies are what
    the lane redacts with and what the answer cache's epoch is computed over, so a derivation
    changed on the Classification screen moves the epoch on the next question.
    """

    rules: tuple[FastPathRule, ...] = ()
    readers: Mapping[tuple[str, str], RowReader] = field(default_factory=dict)
    policies: Mapping[str, FieldPolicy] = field(default_factory=dict)


def lane_for(tables: Sequence[StoredTable], records: RowSource) -> ClassifiedLane:
    """The lane for these tables, reading through `records`. Pure: nothing here opens anything.

    A table whose entity another table already claimed is left out rather than merged: the
    store keys tables on the entity, so this happens only when a caller hands in a list it
    built wrongly, and two readers for one pair would make which one answers a question of
    iteration order.
    """
    rules: list[FastPathRule] = []
    readers: dict[tuple[str, str], RowReader] = {}
    policies: dict[str, FieldPolicy] = {}
    for table in tables:
        if table.entity in policies:
            log.warning("classified_rows.entity_twice", entity=table.entity)
            continue
        rules.extend(questions_for(table))
        readers[(TABLES_SOURCE, table.entity)] = table_reader(table, records)
        policies[table.entity] = table.classification.policy()
    return ClassifiedLane(rules=tuple(rules), readers=readers, policies=policies)
