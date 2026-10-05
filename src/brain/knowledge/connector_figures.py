"""A connected Google source's figures for any range a workflow or an agent names, as a tool.

A question on Ask names its range in its words, from the few a question shape carries. A workflow
(the monthly SEO report) or an agent's step names it as an argument: last month, since a date, a
first and a last day. So each Google source that declares a report has a figure tool beside its row
tool, `google_analytics.read_traffic`, which takes a `brain.connectors.date_range.RangeRequest`,
finds the connected property through the row plane at the caller's reach, and reads its figures
for that one range from Google (`search_console.read_performance` does the same for a site, with
its top ten queries and pages), through the same live read executor a question's refresh uses.
Nothing it reads is stored: the figures are laid over the index row and handed back.

**Reach is the row plane's, and nothing here decides it.** The tool reads the index through
`brain.knowledge.rows.read_rows` with the caller's own entitlement, so a caller without
`read:analytics_property` in the connected department, and an agent whose ceiling does not bind
the property, finds no row and is handed the same empty result a caller asking about nothing
gets, in the same time: no report is asked for, so nothing is read that could be withheld later.
See `A_FIGURE_TOOL_READS_ONLY_WHAT_ITS_CALLER_REACHES`.

**The range is checked before the index is read.** A period outside the grammar is refused when
the request is built, and a window past Google's sixteen months, ending before it starts or ending
after today is refused by `RangeRequest.window` in one of that module's sentences, before any row
is read or any call made.

**A figure tool is a tool of its own, not the row tool asked differently.** It shares its source
and entity with the row tool, so `brain.knowledge.rows.is_row_tool` is how the fast lane's readers
and the records route tell the two apart; a template naming `analytics_property.read` binds both,
which is what an agent reading a property's traffic needs.

Rejected: a range argument on the row tool. `RowRequest` is the row plane's argument surface and
is compiled into a statement; a range compiles into nothing there, and a row tool that sometimes
read a source would be a row tool whose cost nobody could predict from its name.

Scope: the tool and its handler. The live reads are `LiveFigures`, handed in by whoever builds the
registry (`brain.ops.live_records.SourceRecords` in the application); nothing here opens a
connection.

Task ids: M11.7.1, M11.7.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

from brain.connectors import google_analytics, search_console
from brain.connectors.date_range import DateWindow, RangeRequest
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.errors import Degraded
from brain.core.scope import Clause, Op, Scope
from brain.gate.live_records import Refreshed
from brain.knowledge.columns import TableClassification
from brain.knowledge.rows import (
    ENTITY_KEY,
    RowRecord,
    RowRequest,
    RowSource,
    RowTool,
    entity_capability,
    read_rows,
)

#: Why the tool finds its record at the caller's reach before it reads anything.
A_FIGURE_TOOL_READS_ONLY_WHAT_ITS_CALLER_REACHES: Final = (
    "A figure tool finds the connected record through the row plane at its caller's reach, and "
    "asks the source only for a record it found. A caller or an agent without the record's grant "
    "finds nothing, asks nothing, and is handed what a caller asking about nothing is handed."
)


class LiveFigures(Protocol):
    """Reads each found record's figures for one range from its source. See the module."""

    async def figures(
        self,
        result: TypedResult[RowRecord],
        *,
        source: str,
        entity: str,
        window: DateWindow,
        asker: str,
        trace_id: str = "",
    ) -> Refreshed | None:
        """The records with their figures laid over them, None when the pair is not read live."""
        ...


@dataclass(frozen=True)
class FigureTool:
    """One source's figure tool: its name, what it says to a model, and the row tool it finds by."""

    name: str
    description: str
    rows: RowTool

    @property
    def source(self) -> str:
        return self.rows.source

    @property
    def entity(self) -> str:
        return self.rows.entity

    @property
    def scope(self) -> Scope:
        """The tool's own pin, the row tool's: this source, this entity, nothing else."""
        return Scope(
            clauses=(
                Clause(field="source", op=Op.EQ, value=self.source),
                Clause(field=ENTITY_KEY, op=Op.EQ, value=self.entity),
            )
        )

    def definition(self) -> ToolDefinition:
        """What the catalogue describes: the range request's own schema, and the entity's read."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            entity=self.entity,
            args_schema=RangeRequest.model_json_schema(),
            required_capability=entity_capability(self.entity).value,
            side_effect=SideEffect.NONE,
            identity_mode=IdentityMode.SERVICE,
            source=self.source,
        )

    def reader(
        self, records: RowSource, figures: LiveFigures
    ) -> Callable[..., Awaitable[TypedResult[RowRecord]]]:
        """The handler a registry registers, bound to the index and the live reads."""

        async def read(
            request: RangeRequest,
            *,
            entitlement: EntitlementSet,
            now: datetime | None = None,
        ) -> TypedResult[RowRecord]:
            at = now if now is not None else datetime.now(UTC)
            window = request.window(today=at.date())
            found = await read_rows(
                self.rows, RowRequest(), entitlement=entitlement, records=records, now=at
            )
            if not found.records:
                # See A_FIGURE_TOOL_READS_ONLY_WHAT_ITS_CALLER_REACHES.
                return found
            read = await figures.figures(
                found,
                source=self.source,
                entity=self.entity,
                window=window,
                asker=entitlement.principal_id,
            )
            if read is None:
                return TypedResult[RowRecord](
                    records=(), source=self.source, fetched_at=at.isoformat()
                )
            if read.result is None:
                raise Degraded("a figure tool's source did not answer")
            return read.result

        return read


#: The figure tools, by the source whose report they read. One today, and the tool name is the
#: one its manifest declares.
FIGURE_TOOL_NAMES: Final = {
    google_analytics.GOOGLE_ANALYTICS: "google_analytics.read_traffic",
    search_console.SEARCH_CONSOLE: "search_console.read_performance",
}

#: What each figure tool says to a model. Distinct from the row tool's, which the registry holds
#: to by refusing two tools with one description.
FIGURE_TOOL_DESCRIPTIONS: Final = {
    google_analytics.GOOGLE_ANALYTICS: (
        "Read the connected Google Analytics property's sessions, users and conversions for a "
        "range you name: a first and last day, or yesterday, today, last N days, this month, "
        "last month or since a date, within the last sixteen months. Read live and never stored."
    ),
    search_console.SEARCH_CONSOLE: (
        "Read the connected Search Console site's clicks, impressions, ten most clicked queries "
        "and ten most clicked pages for a range you name, as for Google Analytics, and its "
        "sitemaps' errors and warnings. Read live and never stored."
    ),
}


def figure_tools(
    classified: dict[str, tuple[TableClassification, ...]],
) -> tuple[FigureTool, ...]:
    """Every figure tool for the sources given, found by each source's own classification."""
    tools: list[FigureTool] = []
    for source, name in sorted(FIGURE_TOOL_NAMES.items()):
        for classification in classified.get(source, ()):
            tools.append(
                FigureTool(
                    name=name,
                    description=FIGURE_TOOL_DESCRIPTIONS[source],
                    rows=RowTool(
                        source=source,
                        classification=classification,
                        description=FIGURE_TOOL_DESCRIPTIONS[source],
                    ),
                )
            )
    return tuple(tools)
