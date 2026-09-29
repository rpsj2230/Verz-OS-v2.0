"""What a connected source's records answer on Ask: their classifications and their questions.

Until this module no question on an install could reach a connected source. The worker kept each
source's minimal index in `proj.record`, the live read was wired to the answer lane, and still the
lane answered nothing about an invoice or a ticket, because the lane answers only entities that have
a row tool, a classification and a question shape, and `brain.tools.startup.SOURCE_ROW_ENTITIES`
filed only the demo's. So a person on an install with Xero connected asked for an invoice's status
and was told nothing was found, which is the answer the product gives for a record that does not
exist.

**The classifications are the connectors' own field rules, compiled here, and none is invented.**
Xero declares `XERO_FIELD_RULES` beside its mapping, each field with the capability that reaches it
and its classification, and `amount_due` RESTRICTED. This module turns those rules into the
`TableClassification` the row plane and the redactor read, so the capability a person needs to be
told an invoice's amount is the one the connector already names. Freshdesk declares no field rules,
so its ticket classification is written here over exactly its projected fields, each behind its own
field capability, in the pattern `brain.demo.row_classifications` uses. Rejected: reading them off
`brain.connectors.declaration`, which is on the scheduled sync's path and imports nothing from
`brain.knowledge` (`tests/invariants/test_minimal_index.py`). The dependency runs the other way.

**A connected source's questions are asked in the words an uploaded table's are.**
`brain.knowledge.classified_rows.questions_over` builds both, keyed on the field a person names a
record by: an invoice's number, a contact's name, a ticket's subject. They are built per question
from the connections live at that moment, so a source connected on the Connectors screen answers
from the next question and one disconnected does not, with nothing restarted, and a source nobody
connected contributes no question shape that could tell a person it exists.

**What each answer reads, and what it never keeps.** The fast lane finds the record in the index
at the asker's reach, `brain.ops.live_records.SourceRecords` reads that record from its source
while the asker waits (Xero today; Freshdesk declares no live lookup yet), the redactor removes
every field the asker may not read, and the answer is dated by the oldest row it stands on
(`brain.knowledge.rows.answered_as_of`). Nothing a live read returns is written anywhere.

Task ids: M11.6.5, M11.6.2, M11.4.9
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

from brain.connectors import freshdesk, xero
from brain.core.entitlement import Capability
from brain.core.field_policy import Classification, FieldRule
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

# ---------------------------------------------------------------- the classifications


#: The field each source's visibility predicate tests on every row it keeps.
SCOPED_BY: Final[Mapping[str, str]] = MappingProxyType(
    {xero.CONNECTOR_NAME: "tenant_id", freshdesk.FRESHDESK: "department"}
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


def _from_rules(source: str, entity: str, rules: Iterable[FieldRule]) -> TableClassification:
    """One entity's classification out of a connector's field rules for it, and its scope column."""
    return TableClassification(
        entity=entity,
        rules=(
            *(
                ColumnRule(
                    column=rule.field,
                    required_capability=rule.required_capability,
                    classification=rule.classification,
                    derived_from=frozenset(rule.derived_from),
                )
                for rule in rules
                if rule.entity == entity
            ),
            _scope_column(source, entity),
        ),
    )


def xero_classifications() -> tuple[TableClassification, ...]:
    """Xero's invoices and contacts, from `xero.XERO_FIELD_RULES`."""
    rules = xero.XERO_FIELD_RULES
    return (
        _from_rules(xero.CONNECTOR_NAME, xero.ENTITY_INVOICE, rules),
        _from_rules(xero.CONNECTOR_NAME, xero.ENTITY_CONTACT, rules),
    )


def freshdesk_classifications() -> tuple[TableClassification, ...]:
    """Freshdesk's tickets, over exactly the fields its index keeps.

    Each field behind its own capability (`read:ticket.status`, ...), INTERNAL, in
    `brain.demo.row_classifications`' pattern: reaching a ticket is `read:ticket` in the department
    the connection names, and each field a person is told is a further grant. The ticket's body is
    not here because it is not kept, and nothing reads it live yet.
    """
    return (
        TableClassification(
            entity=freshdesk.TICKET,
            rules=(
                *(
                    ColumnRule(
                        column=name,
                        required_capability=Capability(value=f"read:{freshdesk.TICKET}.{name}"),
                        classification=Classification.INTERNAL,
                    )
                    for name in freshdesk.projected_field_names()
                ),
                _scope_column(freshdesk.FRESHDESK, freshdesk.TICKET),
            ),
        ),
    )


#: Every connected source's classifications, by the source's name.
CONNECTOR_ROW_ENTITIES: Final[Mapping[str, tuple[TableClassification, ...]]] = MappingProxyType(
    {
        xero.CONNECTOR_NAME: xero_classifications(),
        freshdesk.FRESHDESK: freshdesk_classifications(),
    }
)

#: The field a person names a record by, per source and entity: the question's slot.
NAMED_BY: Final[Mapping[tuple[str, str], str]] = MappingProxyType(
    {
        (xero.CONNECTOR_NAME, xero.ENTITY_INVOICE): "invoice_number",
        (xero.CONNECTOR_NAME, xero.ENTITY_CONTACT): "name",
        (freshdesk.FRESHDESK, freshdesk.TICKET): "subject",
    }
)

#: What each source's row tools are described as in the catalogue.
CONNECTOR_ROW_DESCRIPTIONS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        xero.CONNECTOR_NAME: {
            xero.ENTITY_INVOICE: (
                "Look up Xero invoices by number: status, due date and the contact, and the "
                "amount due read live from Xero for a reader allowed it"
            ),
            xero.ENTITY_CONTACT: "Look up Xero contacts by name: status and when they last changed",
        },
        freshdesk.FRESHDESK: {
            freshdesk.TICKET: (
                "Look up Freshdesk tickets by subject: status, priority, due date and when it "
                "last changed"
            ),
        },
    }
)


# ------------------------------------------------------------------------ the questions
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
            rules.extend(questions_over(classification, source=source, key_column=key))
    return tuple(rules)
