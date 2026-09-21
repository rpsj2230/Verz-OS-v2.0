"""The data processing record per connector, as the Compliance screen shows it (M24.2.3).

`brain.audit.compliance.ProcessingRecord` is the regulator's form, and every field on it that is a
judgement (the lawful basis, who decided it, the retention a person chose) is a person's to fill.
What the system can say without anybody's judgement is the half this module computes, from the
two things that are true on the install: the manifest each connected source was built from, and
what the worker last read from it.

- **What each connector reads**: every entity its tools fetch live (the federated tier, never
  stored) and every entity it projects, with the field names kept (the projected tier, a pointer
  and never a payload). Read off the manifest the connection builds today, so a register that
  says "reads invoices" is saying what the code will fetch rather than what somebody remembered.
- **Its categories**: the tiers above and the sensitivity classes of the fields those entities
  carry, as this release classifies them (`brain.tools.startup.classification_for`), so a source
  reading a restricted column says so.
- **Its counts**: how many records and documents the worker's last run read, from
  `ops.connector_sync`. Counts of what was read, never of what is held: the owner's rule is a
  minimal index and a live read, and this screen copies nothing from any source to count it.

**Names, never data**, for `ProcessingRecord`'s reason: an entity, a field name and a class are
product vocabulary, and nothing here reads a record.

**A connection whose manifest cannot be built is listed with the reason, not dropped.** A
register is judged by its gaps, and a connector missing from it is the gap nobody sees.

Task ids: M24.2.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.audit.compliance import DataTier
from brain.connectors.contract import ConnectorContractError
from brain.connectors.manifest import ConnectorManifest
from brain.core.envelope import SideEffect
from brain.ops.connectable import CONNECTABLE, NotConnectableError, manifest_for
from brain.ops.connector_store import Connection
from brain.tools.startup import classification_for

#: What a row says when the manifest a connection was made with cannot be built today.
CANNOT_BE_BUILT: Final = (
    "This connection's settings no longer build a connector in this release, so what it reads "
    "cannot be stated. It reads nothing until it is connected again."
)

#: What the counts are, said once on the screen.
THE_COUNTS_ARE_WHAT_WAS_READ: Final = (
    "Records and documents are what the worker's last run read from the source. Nothing is "
    "copied to count them: the system keeps a minimal index and reads the rest live."
)


@dataclass(frozen=True)
class ReadCounts:
    """What the worker's newest run against one source read."""

    records: int
    documents: int
    finished_at: datetime


@dataclass(frozen=True)
class RegisterEntity:
    """One kind of record a connector reads, where it lands, and the classes of its fields."""

    entity: str
    tier: DataTier
    #: The field names kept, for the projected tier. Empty for the federated tier.
    fields: tuple[str, ...]
    #: The sensitivity classes of the entity's classified columns, most sensitive last.
    classes: tuple[str, ...]


@dataclass(frozen=True)
class RegisterRow:
    """One connected source's processing record, as far as the system can state it."""

    connector: str
    label: str
    connected_by: str
    connected_at: datetime
    transport: str | None
    version: str | None
    entities: tuple[RegisterEntity, ...]
    #: Every tier and class across `entities`, sorted.
    categories: tuple[str, ...]
    write_capable: bool
    counts: ReadCounts | None
    #: Empty, or `CANNOT_BE_BUILT` when the manifest could not be built.
    problem: str


def classes_of(entity: str) -> tuple[str, ...]:
    """The classes this release gives `entity`'s columns, in the order of sensitivity."""
    classification = classification_for(entity)
    if classification is None:
        return ()
    found = {rule.classification for rule in classification.rules}
    return tuple(one.value for one in sorted(found, key=lambda c: c.rank))


def entities_of(manifest: ConnectorManifest) -> tuple[RegisterEntity, ...]:
    """Every entity the manifest reads: projected with its field names, else federated."""
    projected = {one.entity: one for one in manifest.projections}
    read = sorted({tool.entity for tool in manifest.tools if tool.entity} | set(projected))
    rows: list[RegisterEntity] = []
    for entity in read:
        projection = projected.get(entity)
        rows.append(
            RegisterEntity(
                entity=entity,
                tier=DataTier.PROJECTED if projection else DataTier.FEDERATED,
                fields=tuple(f.name for f in projection.fields) if projection else (),
                classes=classes_of(entity),
            )
        )
    return tuple(rows)


def register_row(connection: Connection, counts: ReadCounts | None) -> RegisterRow:
    """One connection's row. A manifest that cannot be built is a row with the reason."""
    kind = CONNECTABLE.get(connection.connector)
    label = kind.label if kind is not None else connection.connector
    try:
        manifest = manifest_for(connection.connector, connection.settings)
    except (NotConnectableError, ConnectorContractError):
        return RegisterRow(
            connector=connection.connector,
            label=label,
            connected_by=connection.connected_by,
            connected_at=connection.connected_at,
            transport=None,
            version=None,
            entities=(),
            categories=(),
            write_capable=False,
            counts=counts,
            problem=CANNOT_BE_BUILT,
        )
    entities = entities_of(manifest)
    categories = sorted({e.tier.value for e in entities} | {c for e in entities for c in e.classes})
    return RegisterRow(
        connector=connection.connector,
        label=label,
        connected_by=connection.connected_by,
        connected_at=connection.connected_at,
        transport=manifest.transport.value,
        version=manifest.version,
        entities=entities,
        categories=tuple(categories),
        write_capable=any(tool.side_effect is not SideEffect.NONE for tool in manifest.tools),
        counts=counts,
        problem="",
    )


def register_rows(
    connections: Sequence[Connection], counts: Mapping[str, ReadCounts]
) -> tuple[RegisterRow, ...]:
    """Every live connection's row, in the order of the sources' names."""
    return tuple(
        register_row(one, counts.get(one.connector))
        for one in sorted(connections, key=lambda c: c.connector)
    )
