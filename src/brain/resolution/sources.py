"""Which connector records entity resolution reads, found on the connectors' own declarations.

Each connector says which of its entities are companies, people or projects, which projected field
names each and whether they carry money (`brain.connectors.resolves.ResolvesAs`, on
`ConnectorDeclaration.resolves`). This reads those declarations and nothing else, so adding a
connector edits nothing here, for the reason `brain.knowledge.connector_rows` gives about Ask rows:
`THE_SOURCES_ARE_READ_OFF_THE_DECLARATIONS`.

**Discovery that comes back empty is a fault, not a quiet install.** If discovery stopped finding
declarations, every record would stay unresolved and nothing would say so: the registry job would
report that it had nothing to do. `resolution_source_gaps` names that, anchored on a connector that
must always declare (`ANCHOR`), and a test holds it.

**Every declared entity and field is held against the connector's own manifest.** A declaration
naming an entity the manifest does not project, or a field that entity does not keep, resolves
nothing and reads as though it did. `resolution_source_gaps` builds each connector's manifest from
its own example settings and compares.

Task ids: M14.1.1, M14.7.3
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from brain.connectors.declaration import ConnectorDeclaration, shipped
from brain.connectors.resolves import ResolvesAs

#: Why nothing in this module names a connector.
THE_SOURCES_ARE_READ_OFF_THE_DECLARATIONS: Final = (
    "A connector's records for resolution are declared in its own module and read off the "
    "declarations here, so adding a connector edits no list in this file and a third-party "
    "connector declares its own the same way."
)

#: A connector that must always declare a record for resolution. An accounting system's contact
#: is a client, so if discovery stops finding this one it has stopped finding all of them.
#: Xero's entity names its source since `brain.agents.binding.AN_ENTITY_NAMES_ONE_SOURCE`.
ANCHOR: Final = ("xero", "xero_contact")


def resolved_entities(
    declarations: Mapping[str, ConnectorDeclaration] | None = None,
) -> Mapping[tuple[str, str], ResolvesAs]:
    """Every declared entity, by connector name and entity name, sorted."""
    declared = shipped() if declarations is None else declarations
    found = {
        (name, one.entity): one
        for name, declaration in sorted(declared.items())
        for one in declaration.resolves
    }
    return MappingProxyType(found)


def resolution_source_gaps(
    declarations: Mapping[str, ConnectorDeclaration] | None = None,
) -> tuple[str, ...]:
    """Every way the declarations fail to describe records a connector really keeps."""
    from brain.ops.connectable import manifest_for

    declared = shipped() if declarations is None else declarations
    gaps: list[str] = []
    if ANCHOR not in resolved_entities(declared):
        gaps.append(
            f"{ANCHOR[0]} declares no {ANCHOR[1]} for resolution, so discovery has stopped finding "
            "declarations and every record would stay unresolved with nothing saying so"
        )
    for name, declaration in sorted(declared.items()):
        if not declaration.resolves:
            continue
        example = None if declaration.console is None else declaration.console.example
        if example is None:
            gaps.append(f"{name} declares records for resolution and has no example to check them")
            continue
        manifest = manifest_for(name, example.settings)
        kept = {one.entity: {f.name for f in one.fields} for one in manifest.projections}
        for one in declaration.resolves:
            if one.entity not in kept:
                gaps.append(
                    f"{name} declares {one.entity} for resolution and projects no such entity"
                )
                continue
            missing = sorted(set(one.fields.values()) - kept[one.entity])
            if missing:
                gaps.append(
                    f"{name} reads {missing} of {one.entity} for resolution, which it does not keep"
                )
    return tuple(gaps)
