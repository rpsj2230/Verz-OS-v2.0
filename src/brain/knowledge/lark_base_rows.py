"""What a switched-on Lark Base answers on Ask: each table's classification, questions and reader.

A Base table has no field rules written for it in this repository, and cannot have: its tables and
fields are the company's own, discovered from the Base (`brain.ops.lark_base_live.BaseSchema`). So
a table's classification is built from what its schema says, by one rule, and the rule is the
Freshdesk ticket's (`brain.knowledge.connector_rows.freshdesk_classifications`):

- **reaching a record is `read:lark_<table>`**, and the column the row's visibility predicate
  tests (the Base's id, `brain.ops.lark_base_index.A_BASE_ROW_IS_SCOPED_BY_ITS_BASE`) is read under
  it, for `THE_COLUMN_A_SCOPE_TESTS_IS_READ_BY_WHOEVER_REACHES_THE_ROW`'s reason;
- **every field the schema binds is `read:lark_<table>.<field>`, INTERNAL**, so what a person is
  told out of a record is a further grant, and `read:lark_<table>.*` is the one grant for all of
  them. The index registers both words under the table's title
  (`lark_base_index.A_TABLE_S_GRANT_IS_OFFERED_BY_ITS_TITLE`).

Rejected: every field under the row's own capability, which would make finding a record and
reading its values one decision, the opposite of every other source here; and classifying by the
field's Lark type (a number as confidential, say), which would be a rule invented here about a
company's columns that nobody at the company chose. `A_BASE_FIELD_IS_A_GRANT_OF_ITS_OWN`.

A table is asked about by its primary field, the one label the index keeps, in the same words as
an uploaded table or a connected source (`brain.knowledge.classified_rows.questions_over`). A table
whose primary field is not kept (a person, a link, or a name on the permanent denylist) has no
field to name a record by and is asked nothing, though its reader and policy are still filed.

Task ids: M11.6.3, M11.6.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from brain.connectors.lark_base import LARK_BASE, LarkBaseTable
from brain.connectors.manifest import FieldShape
from brain.core.entitlement import Capability
from brain.core.field_policy import Classification, FieldPolicy
from brain.gate.fast_lane import FastPathRule, RowReader
from brain.knowledge.classified_rows import ClassifiedLane, questions_over
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.rows import RowSource, RowTool
from brain.ops.lark_base_index import BASE_ID_FIELD

#: Why each field of a Base table is a grant of its own.
A_BASE_FIELD_IS_A_GRANT_OF_ITS_OWN: Final = (
    "Finding a record in a Base table and being told its values are two grants, as they are for "
    "a ticket or an uploaded table: read:lark_<table> reaches the record by its name, and each "
    "field is read:lark_<table>.<field>, which read:lark_<table>.* grants whole. No rule about a "
    "company's columns is invented here: which of them a person may read is the administrator's "
    "grant."
)

__all__ = ["A_BASE_FIELD_IS_A_GRANT_OF_ITS_OWN"]


def classification_of(table: LarkBaseTable) -> TableClassification:
    """One table's classification from its schema. See `A_BASE_FIELD_IS_A_GRANT_OF_ITS_OWN`."""
    return TableClassification(
        entity=table.entity,
        rules=(
            *(
                ColumnRule(
                    column=binding.target,
                    required_capability=Capability(value=f"read:{table.entity}.{binding.target}"),
                    classification=Classification.INTERNAL,
                )
                for binding in table.bindings
            ),
            ColumnRule(
                column=BASE_ID_FIELD,
                required_capability=Capability(value=f"read:{table.entity}"),
                classification=Classification.INTERNAL,
            ),
        ),
    )


def named_by(table: LarkBaseTable) -> str | None:
    """The field a record of this table is named by: its kept label or identifier, or None."""
    for binding in table.projected_bindings():
        if binding.shape in (FieldShape.LABEL, FieldShape.IDENTIFIER):
            return binding.target
    return None


def description_of(title: str) -> str:
    """What the table's reader is described as, in the catalogue a model reads."""
    return (
        f"Look up records of the Lark Base table {title!r} by their name, with each value read "
        "live from Lark for a reader allowed it"
    )


@dataclass(frozen=True)
class BaseLane(ClassifiedLane):
    """`ClassifiedLane` for the Base's tables, with each one's policy keyed by its source too."""

    source_policies: Mapping[tuple[str, str], FieldPolicy] = field(default_factory=dict)


def lane_for_base(tables: Sequence[tuple[LarkBaseTable, str]], records: RowSource) -> BaseLane:
    """The Base's tables as Ask reads them: question shapes, a row reader and a policy each.

    `tables` is each table with its title. Pure: the reader reads the index through `records`, and
    the live read that fills a record's values is the answer lane's (`brain.ops.lark_base_live`).
    """
    rules: list[FastPathRule] = []
    readers: dict[tuple[str, str], RowReader] = {}
    policies: dict[str, FieldPolicy] = {}
    by_source: dict[tuple[str, str], FieldPolicy] = {}
    for table, title in tables:
        classification = classification_of(table)
        key = named_by(table)
        if key is not None:
            rules.extend(
                questions_over(
                    classification,
                    source=LARK_BASE,
                    key_column=key,
                    unasked=frozenset({BASE_ID_FIELD}),
                )
            )
        tool = RowTool(
            source=LARK_BASE, classification=classification, description=description_of(title)
        )
        readers[(LARK_BASE, table.entity)] = tool.reader(records)
        policies[table.entity] = classification.policy()
        by_source[(LARK_BASE, table.entity)] = policies[table.entity]
    return BaseLane(
        rules=tuple(rules), readers=readers, policies=policies, source_policies=by_source
    )
