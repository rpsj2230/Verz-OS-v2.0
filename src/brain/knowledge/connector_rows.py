"""What a connected source's records answer on Ask: their classifications and their questions.

Until this module no question on an install could reach a connected source. The worker kept each
source's minimal index in `proj.record`, the live read was wired to the answer lane, and still the
lane answered nothing about an invoice or a ticket, because the lane answers only entities that have
a row tool, a classification and a question shape, and `brain.tools.startup.SOURCE_ROW_ENTITIES`
filed only the demo's. So a person on an install with Xero connected asked for an invoice's status
and was told nothing was found, which is the answer the product gives for a record that does not
exist.

**The classifications are the connectors' own field rules, compiled here, and none is invented.**
Each connector declares its Ask rows on its own `CONNECTOR` (`brain.connectors.ask`): every field
with the capability that reaches it and its classification, the field its visibility predicate
tests, the field a record is named by and its tool's words. Xero's are `XERO_FIELD_RULES`, with
`amount_due` RESTRICTED; Freshdesk declares no field rules, so its ticket's fields are each behind
their own capability, in the pattern `brain.demo.row_classifications` uses. This module turns them
into the `TableClassification` the row plane and the redactor read, so the capability a person
needs to be told an invoice's amount is the one the connector already names.

**Assembled by discovery over `shipped()`, and nothing here names a connector (M11.1.6).** Until
2026-10-05 the maps below were typed here, one entry per connector in each, and every connector PR
appended to all of them, so every one that landed put every other open one in conflict. The names
and types are unchanged, so no caller moved. The declarations are stated in `brain.core` types
rather than `brain.knowledge` ones because `brain.connectors.declaration` is on the scheduled sync's
path and imports nothing from `brain.knowledge` (`tests/invariants/test_minimal_index.py`); the
compiling happens here, on this side of that line. See `THE_ROWS_ARE_READ_OFF_THE_DECLARATIONS`.

**The Laravel database's clients and staff records are classified by `laravel.LARAVEL_FIELD_RULES`,
and their department is read by whoever reaches the row (M11.6.1).** Its visibility rule is written
per connection over a field its views keep, and the field a reader's grant is tested against is the
department both views keep, so that column is the scope column here and is classified under the
row's own capability rather than the field capability the connector names for it. The contract
value stays behind `read:client.contract_value`, RESTRICTED, and is read live and never kept.

**A connected source's questions are asked in the words an uploaded table's are.**
`brain.knowledge.classified_rows.questions_over` builds both, keyed on the field a person names a
record by: an invoice's number, a contact's name, a ticket's subject. They are built per question
from the connections live at that moment, so a source connected on the Connectors screen answers
from the next question and one disconnected does not, with nothing restarted, and a source nobody
connected contributes no question shape that could tell a person it exists.

**A connected property's or site's figures are classified beside its index fields, and never
kept (M11.7.1, M11.7.2).** Google Analytics keeps the property's name and dates, and Search Console
the site's name and permission; their traffic and search figures for each named range are read
from Google when a question asks (`google_analytics.AnalyticsReport`,
`search_console.SearchConsoleReport`). They are classified here all the same, each behind its own
field capability, because the redactor withholds a field nothing classifies from everybody, and a
figure read live is a field of the record by the time the redactor sees it. So "what is the
sessions last 28 days of <property>" is asked in the words every other question is, and answered
only to a reader granted that figure in the source's department.

**What each answer reads, and what it never keeps.** The fast lane finds the record in the index
at the asker's reach, `brain.ops.live_records.SourceRecords` reads that record from its source
while the asker waits (Xero today; Freshdesk declares no live lookup yet), the redactor removes
every field the asker may not read, and the answer is dated by the oldest row it stands on
(`brain.knowledge.rows.answered_as_of`). Nothing a live read returns is written anywhere.

**Cloudflare's zones and DNS records are asked by name (M11.7.3).** A record's content is read from
Cloudflare while the asker waits, through the connector's own one-record call, and is classified
here beside the fields the index keeps.

**HubSpot answers the same way since 2026-09-30.** Its companies, contacts and deals are compiled
from `hubspot.HUBSPOT_FIELD_RULES`, a company and a deal are asked about by name, and every value
is read from HubSpot's one-record read while the asker waits. Until then HubSpot was offered on the
Connectors screen and read into its index, and no question on Ask could reach it, which is why
`brain.ops.connectable.answers` now refuses to offer a source Ask cannot answer from.

Task ids: M11.6.5, M11.6.2, M11.4.9, M11.7.4, M11.7.3, M11.7.1, M11.7.2, M11.6.1, M11.6.7, M11.1.6
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

from brain.connectors.ask import AskEntity, AskRows
from brain.connectors.declaration import ConnectorDeclaration, shipped
from brain.core.entitlement import Capability
from brain.core.field_policy import Classification
from brain.gate.fast_lane import FastPathRule
from brain.knowledge.classified_rows import questions_over
from brain.knowledge.columns import ColumnRule, TableClassification

#: Why a source's classification is compiled from its own rules.
A_SOURCE_S_FIELDS_ARE_CLASSIFIED_BY_THE_SOURCE_S_OWN_RULES: Final = (
    "A connector that declares its field rules has already said which capability reaches each "
    "field and how sensitive it is. Compiling those rules is the only way the Ask answer and "
    "the connector's own policy cannot disagree; writing a second classification here would be "
    "a second place to decide who may be told an invoice's amount."
)

#: Why only connected sources contribute questions.
A_SOURCE_NOBODY_CONNECTED_ASKS_NOTHING: Final = (
    "A question shape for a source nobody connected would be answered as nothing found, and "
    "the set of shapes an install answers is visible in what it answers. So a source's questions "
    "are built from the connections live when the question is asked, and a source that is not "
    "connected contributes none."
)

#: Why nothing in this module names a connector.
THE_ROWS_ARE_READ_OFF_THE_DECLARATIONS: Final = (
    "A connector's Ask rows are declared in its own module and read off the declarations here, so "
    "adding a connector edits no map in this file, and two connectors added at once cannot "
    "conflict in it. A map typed here would also be a second account of the connector that could "
    "disagree with its first."
)

# ---------------------------------------------------------------- the declarations, read once


def _classified(
    declared: Mapping[str, ConnectorDeclaration],
) -> Mapping[str, tuple[AskRows, tuple[AskEntity, ...]]]:
    """Each connector that declares classified Ask rows, with its rows and its entities."""
    return {
        name: (one.ask, one.ask.entities)
        for name, one in declared.items()
        if one.ask is not None and one.ask.entities
    }


_CLASSIFIED: Final = _classified(shipped())


# ---------------------------------------------------------------- the classifications


#: The field each source's visibility predicate tests on every row it keeps.
SCOPED_BY: Final[Mapping[str, str]] = MappingProxyType(
    {name: rows.scoped_by for name, (rows, _) in _CLASSIFIED.items()}
)


def _scope_column(source: str, entity: str) -> ColumnRule:
    """The column a source's visibility predicate tests, read by whoever reaches the row.

    `brain.demo.THE_COLUMN_A_SCOPE_TESTS_IS_READ_BY_WHOEVER_REACHES_THE_ROW`, measured again here on
    2026-09-30: a ticket granted in one department was dropped whole for its own department's
    reader, because the redactor judges a department-scoped grant against the record and the record
    had no department in it. Under `read:<entity>`, which every reader of the row holds, the column
    tells nobody anything new: every row they reach is in the scope their grant names.
    """
    return ColumnRule(
        column=SCOPED_BY[source],
        required_capability=Capability(value=f"read:{entity}"),
        classification=Classification.INTERNAL,
    )


def compiled(source: str, entity: AskEntity) -> TableClassification:
    """One entity's classification out of its declared field rules, and its scope column.

    A rule the connector wrote for the scope column itself gives way to `_scope_column`, which is
    the whole of `THE_COLUMN_A_SCOPE_TESTS_IS_READ_BY_WHOEVER_REACHES_THE_ROW`: Laravel names a
    field capability for its department, and a reader holding the row and not that field would be
    dropped whole by the redactor.
    """
    return TableClassification(
        entity=entity.entity,
        rules=(
            *(
                ColumnRule(
                    column=rule.field,
                    required_capability=rule.required_capability,
                    classification=rule.classification,
                    derived_from=frozenset(rule.derived_from),
                )
                for rule in entity.fields
                if rule.field != SCOPED_BY[source]
            ),
            _scope_column(source, entity.entity),
        ),
    )


#: Every connected source's classifications, by the source's name.
CONNECTOR_ROW_ENTITIES: Final[Mapping[str, tuple[TableClassification, ...]]] = MappingProxyType(
    {
        name: tuple(compiled(name, one) for one in entities)
        for name, (_, entities) in _CLASSIFIED.items()
    }
)

#: The sources Ask answers through a passage reader rather than a classification: what they hold
#: is read live as passages for the question's model step, as the Lark Wiki's pages are. Each such
#: source says so in its own declaration (`AskRows.by_passages`). See
#: `brain.ops.connectable.answers`. Google Drive's folder is read by `brain.ops.drive_passages`
#: (M11.6.7).
ANSWERED_BY_PASSAGES: Final[frozenset[str]] = frozenset(
    name for name, one in shipped().items() if one.ask is not None and one.ask.by_passages
)

#: The field a person names a record by, per source and entity: the question's slot. An entity a
#: connector reaches through another (HubSpot's contacts, kept with no name) names none.
NAMED_BY: Final[Mapping[tuple[str, str], str]] = MappingProxyType(
    {
        (name, one.entity): one.named_by
        for name, (_, entities) in _CLASSIFIED.items()
        for one in entities
        if one.named_by
    }
)

#: What each source's row tools are described as in the catalogue.
CONNECTOR_ROW_DESCRIPTIONS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        name: MappingProxyType({one.entity: one.description for one in entities})
        for name, (_, entities) in _CLASSIFIED.items()
    }
)


# ------------------------------------------------------------------------ the questions
#: Fields a record carries only when read live, by entity: its figures, which no index row holds,
#: so a filter on one matches nothing whatever it names. The records route's bound on how many
#: columns a filter may name is a bound on the columns a row carries, and these are not among them.
LIVE_ONLY: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        one.entity: one.live_only
        for _, entities in _CLASSIFIED.values()
        for one in entities
        if one.live_only
    }
)

#: Fields a figure tool answers for a range it was asked for, and no question on Ask can name,
#: because a question's range is in its words: see `A_TOOL_S_RANGE_IS_NOT_A_QUESTION_S`.
UNASKED: Final[Mapping[tuple[str, str], frozenset[str]]] = MappingProxyType(
    {
        (name, one.entity): one.unasked
        for name, (_, entities) in _CLASSIFIED.items()
        for one in entities
        if one.unasked
    }
)

#: Why a figure tool's fields are classified and never asked about on Ask.
A_TOOL_S_RANGE_IS_NOT_A_QUESTION_S: Final = (
    "A figure tool answers sessions or clicks for the range it was given, and a question on Ask "
    "names its range in its words from the ranges its fields carry. A question about plain "
    "sessions would name no range, and would be answered from a report that has no such field, "
    "so those fields are classified for the redactor and offered to no question shape."
)


def connected_questions(connected: Iterable[str]) -> tuple[FastPathRule, ...]:
    """The question shapes the connected sources answer. See `A_SOURCE_NOBODY_CONNECTED_...`.

    `connected` is the names of the sources connected on this install now. A name this module
    classifies nothing for contributes nothing.
    """
    rules: list[FastPathRule] = []
    for source in sorted(set(connected)):
        for classification in CONNECTOR_ROW_ENTITIES.get(source, ()):
            key = NAMED_BY.get((source, classification.entity))
            if key is None or classification.rule_for(key) is None:
                continue
            unasked = UNASKED.get((source, classification.entity), frozenset())
            rules.extend(
                questions_over(classification, source=source, key_column=key, unasked=unasked)
            )
    return tuple(rules)
