"""What a connector says Ask answers about its records, declared in its own module.

Until this module a connector's Ask rows were four maps in `brain.knowledge.connector_rows`: its
classifications, the field each source's visibility predicate tests, the field a person names each
entity by, and each row tool's catalogue description. Every connector PR appended to all four, so
every one that landed put every other open one in conflict, six times on 2026-10-05 alone. **Now a
connector states its rows once, as `ask` on its own `ConnectorDeclaration`, and
`connector_rows` assembles the four maps by discovery over `shipped()`.** The public names and
types there are unchanged, so nothing that reads them moved.

**Stated in `brain.core` types, never in `brain.knowledge` ones.** The classification the row plane
reads is a `brain.knowledge.columns.TableClassification`, and a connector cannot build one:
`brain.connectors.declaration` is on the scheduled sync's path, and
`tests/invariants/test_minimal_index.py` holds that path free of any `brain.knowledge` import,
because that import is the door the bulk sync came back through once. So a connector names its
fields as `FieldRule`s, which is what Xero and HubSpot already declare their policy in, and
`connector_rows` compiles them and adds the scope column. Rejected: a callable on the declaration
that returns the classification, which would type-check against `Any` and put the knowledge import
one lazy line inside every connector module, where the invariant cannot read it.

**A source whose records Ask reads as passages says so here too.** The Lark Wiki's pages are read
live for the question's model step rather than classified, and that was a fifth hand-kept set
(`ANSWERED_BY_PASSAGES`). `AskRows.by_passages` is the same fact in the connector's own words.

Scope: domain logic. Nothing here reads a table or opens a connection.

Task ids: M11.6.5, M11.1.6
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from brain.core.entitlement import Capability
from brain.core.field_policy import Classification, FieldRule

# ------------------------------------------------------------------ written-down reasons
#: Why a connector's Ask rows are declared beside the rest of it.
A_CONNECTOR_S_ASK_ROWS_ARE_ITS_OWN: Final = (
    "A connector's classifications, its scope field, the field a record is named by and its "
    "tools' descriptions are facts about that connector, and four maps elsewhere holding them "
    "made every connector change an edit to a file every other connector change also edited. "
    "So each connector declares them in its own module and the maps are assembled from the "
    "declarations, which cannot conflict with one another."
)


class AskRowsError(ValueError):
    """A connector declared its Ask rows in a shape the answer lane cannot use."""


@dataclass(frozen=True)
class AskEntity:
    """One entity a connector's row tool answers: its fields, how a record is named, its words.

    `fields` is every field a reader may be told, each with the capability that reaches it and its
    classification; the scope column is added by `connector_rows` and is not listed here.
    `named_by` is the field a question names a record by, or empty for an entity reached through
    another (HubSpot's contacts through their company). `live_only` are fields a record carries only
    when read live, so a filter on one matches no index row; `unasked` are fields a figure tool
    answers for a range it was given and no question shape may name.
    """

    entity: str
    fields: tuple[FieldRule, ...]
    description: str
    named_by: str = ""
    live_only: tuple[str, ...] = ()
    unasked: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.fields:
            msg = f"{self.entity} declares no field, so its row tool would answer nothing"
            raise AskRowsError(msg)
        others = sorted({one.entity for one in self.fields} - {self.entity})
        if others:
            msg = f"{self.entity} declares fields of {others}, which are other entities' fields"
            raise AskRowsError(msg)
        if not self.description.strip():
            msg = f"{self.entity} has no description, and the catalogue shows it"
            raise AskRowsError(msg)
        names = {one.field for one in self.fields}
        if self.named_by and self.named_by not in names:
            msg = f"{self.entity} is named by {self.named_by!r}, which it does not classify"
            raise AskRowsError(msg)
        loose = sorted((set(self.live_only) | self.unasked) - names)
        if loose:
            msg = f"{self.entity} names {loose} as read live or unasked and classifies none of them"
            raise AskRowsError(msg)


@dataclass(frozen=True)
class AskRows:
    """What Ask answers from one connector: classified entities, or passages read live.

    Exactly one of the two. `scoped_by` is the field the source's visibility predicate tests on
    every row it keeps, which every classified entity carries.
    """

    scoped_by: str = ""
    entities: tuple[AskEntity, ...] = ()
    by_passages: bool = False

    def __post_init__(self) -> None:
        if bool(self.entities) == self.by_passages:
            msg = (
                "Ask rows are either classified entities or passages, and these are both or neither"
            )
            raise AskRowsError(msg)
        if self.entities and not self.scoped_by.strip():
            msg = "classified Ask rows name the field their source's visibility predicate tests"
            raise AskRowsError(msg)
        seen = [one.entity for one in self.entities]
        if len(seen) != len(set(seen)):
            msg = f"an entity is declared twice among {sorted(seen)}"
            raise AskRowsError(msg)


def of_entity(rules: Iterable[FieldRule], entity: str) -> tuple[FieldRule, ...]:
    """One entity's rules out of a connector's field rules for every entity it keeps."""
    return tuple(one for one in rules if one.entity == entity)


def each_behind_its_own(entity: str, names: Iterable[str]) -> tuple[FieldRule, ...]:
    """Each named field behind its own capability (`read:<entity>.<field>`), INTERNAL.

    `brain.demo.row_classifications`' pattern, and what a connector that declares no field rules of
    its own is classified by: reaching the record is one grant and each field a further one.
    """
    return tuple(
        FieldRule(
            entity=entity,
            field=name,
            required_capability=Capability(value=f"read:{entity}.{name}"),
            classification=Classification.INTERNAL,
        )
        for name in dict.fromkeys(names)
    )
