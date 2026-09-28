"""The minimal index, proved: what a connector may keep of a source, and a canary for the rest.

The owner's rule is that connectors never bulk-sync (`declaration.CONNECTORS_NEVER_BULK_SYNC`): the
Brain keeps a minimal index of each source and reads every value live at question time. This is the
check that makes the sentence falsifiable, in two halves that fail in different ways.

**`assert_minimal_index` holds kept rows to the manifest that declared them.** A row may carry the
fields its manifest's projection names for that entity, which review already restricted to pointer
shapes, and the fields of the source's visibility predicate with the value that predicate names,
because that is how the row plane evaluates a source's own rule (`brain.ops.connector_sync.
THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS`). Nothing else. Each value is
a scalar no longer than a label, no name is on the permanent denylist, and there are at most twelve.
It is called by the worker before a page is written, so a connector whose projection returns a field
its manifest never declared is refused at the write rather than found later, and by every
connector's tests over the rows its own code keeps from its recordings.

**Why the declared names and not the five pointer shapes alone.** Review already refuses a declared
field that is not an id, a join key, a status, a timestamp or one label (`manifest.projectability`).
What review cannot see is a connector whose code keeps a field it never declared: `amount_due`
arriving beside `status` because a mapping was copied whole. Only the kept rows show that, and only
a comparison with the declaration catches it, which is `A_FIELD_NOBODY_DECLARED_IS_A_COPY`.

**The canary is the other half, and it is the half that finds what a field list cannot.** A value
can leave the source by a route that is not a projected field at all: a log line, an error message
quoting a row, a document handed to a corpus, a run record's detail. So a unique string is planted
in a recorded body where the connector keeps nothing (an amount, a note, a contract value), the
recording is run through the connector's own code, and the string is then looked for everywhere a
copy could be. `plant` and `sightings` are the pure half, used over kept records and captured logs;
`brain.ops.index_audit.tables_holding` is the database half, which looks in every table.

**A canary planted nowhere is refused, not reported clean.** `planted` raises when a body carries no
marker to replace, because a search for a string that was never in the input finds nothing and reads
as a pass. That is the recurring shape of a check that checks nothing, and it has happened in this
repository twice already (`tests/invariants/test_cassettes.py` says where).

Scope: domain logic. Nothing here opens a connection, reads a clock or touches a table.

Task ids: M11.9.1, M11.8.1, M11.8.2, M11.4.5
"""

from __future__ import annotations

import dataclasses
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol

from brain.connectors.manifest import ConnectorManifest, ProjectedEntity
from brain.core.projection import (
    MAX_LABEL_CHARS,
    MAX_PROJECTED_FIELDS,
    ProjectionRefusedError,
    is_forbidden,
)
from brain.core.scope import Op

# ------------------------------------------------------------------ written-down reasons
#: Why a kept field is compared with the declaration and not only with the pointer shapes.
A_FIELD_NOBODY_DECLARED_IS_A_COPY: Final = (
    "Review refuses a declared field that is not a pointer, and the denylist refuses a field by "
    "name. Neither sees a connector whose code keeps a field it never declared, which is what a "
    "mapping copied whole produces: the amount arriving beside the status. The manifest is the "
    "reviewed statement of what is kept, so a kept field it does not name is a copy nobody agreed "
    "to, whatever it is called."
)

#: Why a string longer than a label is refused whatever the field is declared as.
A_VALUE_LONGER_THAN_A_LABEL_IS_A_BODY: Final = (
    "An id, a status and a timestamp are short, and a label is at most 120 characters. A kept "
    "string longer than that is a description, a note or a body, however its field is declared, "
    "and the index is for finding a record rather than for reading it."
)

#: The marker every recorded canary starts with, and every canary this module makes.
CANARY_MARK: Final = "CANARY-"


class MinimalIndexError(ProjectionRefusedError):
    """A kept row holds something outside its connector's minimal index."""


class CanaryError(Exception):
    """A canary was asked to be planted where there was nothing to plant it in."""


class IndexedRow(Protocol):
    """What a kept index entry is, whether it is a `ProjectedRecord` or a row read back."""

    @property
    def source(self) -> str: ...

    @property
    def entity(self) -> str: ...

    @property
    def source_id(self) -> str: ...

    @property
    def fields(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class StoredRow:
    """One `proj.record` row as it was read back: which record, and the fields it holds."""

    source: str
    entity: str
    source_id: str
    fields: Mapping[str, Any]


def predicate_fields(projection: ProjectedEntity) -> Mapping[str, object]:
    """The fields the source's visibility predicate tests, and the value an equality names.

    A clause that is not an equality has no single value a row could hold, so it maps to None and
    only its name is admitted; `brain.ops.connector_sync.storable_predicate` refuses to read such a
    source at all, and this does not second-guess that.
    """
    return {
        clause.field: clause.value if clause.op is Op.EQ else None
        for clause in projection.visibility.clauses
    }


def index_fields(manifest: ConnectorManifest, entity: str) -> frozenset[str]:
    """Every field name a kept row of this entity may carry; empty for one nothing projects."""
    projection = manifest.projection_for(entity)
    if projection is None:
        return frozenset()
    return frozenset(projection.field_names) | frozenset(predicate_fields(projection))


def _scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool | datetime)


def minimal_index_findings(
    manifest: ConnectorManifest, rows: Iterable[IndexedRow]
) -> tuple[str, ...]:
    """Every way these rows exceed the manifest's minimal index, all at once. Empty when none do.

    Each finding names the row and the field and never the value, because the value is the thing
    that should not have been kept, and a finding is read by more people than the row was.
    """
    found: list[str] = []
    for row in rows:
        where = f"{row.source}.{row.entity} {row.source_id}"
        if row.source != manifest.name:
            found.append(f"{where} is checked against {manifest.name}'s manifest")
            continue
        projection = manifest.projection_for(row.entity)
        if projection is None:
            found.append(
                f"{where}: {manifest.name} projects no {row.entity!r}, so nothing of it may be kept"
            )
            continue
        allowed = index_fields(manifest, row.entity)
        predicate = predicate_fields(projection)
        if len(row.fields) > MAX_PROJECTED_FIELDS:
            found.append(f"{where} keeps {len(row.fields)} fields, over {MAX_PROJECTED_FIELDS}")
        for name, value in sorted(row.fields.items()):
            if name not in allowed:
                found.append(
                    f"{where} keeps {name!r}, which its manifest does not declare. "
                    f"{A_FIELD_NOBODY_DECLARED_IS_A_COPY}"
                )
            elif is_forbidden(name):
                found.append(f"{where} keeps {name!r}, which is on the permanent denylist")
            if not _scalar(value):
                found.append(f"{where} keeps {name!r} as a {type(value).__name__}, not a pointer")
            elif isinstance(value, str) and len(value) > MAX_LABEL_CHARS:
                found.append(
                    f"{where} keeps {name!r} at {len(value)} characters. "
                    f"{A_VALUE_LONGER_THAN_A_LABEL_IS_A_BODY}"
                )
            expected = predicate.get(name)
            if isinstance(expected, str) and value != expected:
                found.append(
                    f"{where} keeps {name!r} with a value the source's visibility rule does not "
                    "name, which is two answers to who may read the row"
                )
    return tuple(found)


def assert_minimal_index(manifest: ConnectorManifest, rows: Iterable[IndexedRow]) -> None:
    """Refuse rows that keep anything outside the manifest's minimal index (M11.9.1).

    Later connector packages call this over the records their connector's code keeps from its
    recordings, and the worker calls it before every page it writes.
    """
    findings = minimal_index_findings(manifest, rows)
    if findings:
        listed = "\n".join(f"  - {one}" for one in findings)
        msg = f"kept rows exceed {manifest.name}'s minimal index:\n{listed}"
        raise MinimalIndexError(msg)


# ------------------------------------------------------------------------- the canary
def fresh_canary(label: str = "VALUE") -> str:
    """A string no source, fixture or other test could contain, starting with `CANARY_MARK`."""
    return f"{CANARY_MARK}{label.upper()}-{secrets.token_hex(8).upper()}"


def plant(body: Any, canary: str) -> tuple[Any, int]:
    """A copy of a recorded body with every canary marker replaced by `canary`, and how many.

    The recordings already mark where a canary belongs: a value the connector must never keep, such
    as an invoice's amount or a ticket's note, reads `CANARY-...`. Replacing each with a string
    minted for this run is what makes a sighting mean this run leaked it, rather than that some
    other fixture happened to carry the same word.
    """
    if isinstance(body, str):
        return (canary, 1) if body.startswith(CANARY_MARK) else (body, 0)
    if isinstance(body, Mapping):
        copied: dict[Any, Any] = {}
        total = 0
        for key, value in body.items():
            copied[key], count = plant(value, canary)
            total += count
        return copied, total
    if isinstance(body, list | tuple):
        items = [plant(one, canary) for one in body]
        rebuilt = [one for one, _ in items]
        return (rebuilt if isinstance(body, list) else tuple(rebuilt)), sum(n for _, n in items)
    return body, 0


def planted(body: Any, canary: str) -> Any:
    """`plant`, refusing a body that carries no marker. See the module docstring."""
    replaced, count = plant(body, canary)
    if not count:
        msg = (
            "this body carries no canary marker, so a search for the canary afterwards would find "
            "nothing because nothing was planted, and read as a pass"
        )
        raise CanaryError(msg)
    return replaced


def sightings(canary: str, *places: object) -> tuple[str, ...]:
    """Every path under these values at which the canary appears. Empty when it appears nowhere.

    Walks what a kept record, a reply, a log capture or an exception can be made of: strings,
    bytes, mappings (keys and values), sequences, sets, dataclasses and pydantic models. Anything
    else is read through `str`, so an object whose rendering quotes the canary is a sighting too.
    """
    seen: list[str] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, str):
            if canary in value:
                seen.append(path)
        elif isinstance(value, bytes | bytearray):
            if canary.encode("utf-8") in value:
                seen.append(path)
        elif isinstance(value, Mapping):
            for key, one in value.items():
                walk(key, f"{path}<key>")
                walk(one, f"{path}.{key}")
        elif isinstance(value, list | tuple | set | frozenset):
            for index, one in enumerate(value):
                walk(one, f"{path}[{index}]")
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            for field in dataclasses.fields(value):
                walk(getattr(value, field.name), f"{path}.{field.name}")
        elif hasattr(value, "model_dump"):
            walk(value.model_dump(mode="json"), path)
        elif value is not None and canary in str(value):
            seen.append(path)

    for index, place in enumerate(places):
        walk(place, f"[{index}]")
    return tuple(seen)
