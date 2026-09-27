"""The audit view taken away: the entries one reader may read, as a document, and nothing else.

**What breaks without it.** `brain.audit.export` renders a contiguous run of the chain, and a run
of the chain is only honest for somebody who may read every entry in it. Everybody else was
refused the export outright, which on a fresh install meant the only administrator could read the
audit trail on a screen and could not take a copy of what that screen showed them. A copy of the
screen is a different artefact from a copy of the chain, and this is that artefact.

**It carries exactly what `brain.audit.view.AuditView` shows the exporter, row for row.** The six
fields of `AuditRow` and no seventh: no `seq`, no `prev_hash`, no `entry_hash` and no `ent_hash`.
The view argues each of those away and every argument applies here with more force, because a
document outlives the session it was taken in and is read by whoever holds the file. A sequence
number beside a sequence number is a count of what lies between them, and two digests together say
whether two entries were adjacent.

**The strong property is byte identity.** A window holding an entry the exporter may not read
renders exactly as the same window where that entry was never written: the same manifest, the same
lines, the same digest. That is DENIED and ABSENT made indistinguishable in the one form a copy can
be checked in, and it rules out more than a count. It is why the document does not verify a chain
(a break would be a fact about entries the reader may not see), why it names the window by the
instants the exporter asked for rather than by what it found, and why the rows are ordered below
on their own content and not on the view's.

**The order is the rows' own, not the view's.** `AuditView` breaks a tie between two entries at the
same instant on `entry_hash`, and an entry's digest covers its parent's, which covers every entry
before it, readable or not. Two readable entries written in the same instant could therefore swap
places when an unreadable one is written before them, and the document would differ. Sorted on
the instant and then the row's own canonical line, the order is a function of what is shown.

**The document says what it is, in the same words every time.** `WHAT_THIS_DOCUMENT_CARRIES` is
fixed and pinned by a validator, for the reason `brain.audit.export.LIMITATIONS` is: a sentence that
varied with what was withheld would be the count this module exists not to emit, written in prose.

Rejected: the chain export with the unreadable entries' lines removed and the chain fields left in.
It fails verification by construction, and a document that fails verification reads as a ledger
somebody tampered with. Rejected: a Merkle inclusion proof per entry, which `brain.audit.export`
already names as the right next step for a subject access request and not this leaf; it proves
membership in a chain whose size is itself a count.

Task ids: M27.9.4
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from brain.audit.export import canonical_json
from brain.audit.ledger import DIGEST, FIELD_NAME, IDENTIFIER, TRACE_ID
from brain.audit.view import AuditRow

#: The format label. A different artefact from `brain.audit.export.EXPORT_FORMAT`, with a different
#: name, so nobody opens one expecting the other's recipe.
READABLE_FORMAT: Final = "brain.audit.readable.v1"

#: What every readable document says about itself. Fixed; see the module docstring.
WHAT_THIS_DOCUMENT_CARRIES: Final = (
    "This document carries the entries of the window above that its exporter may read, as the "
    "audit trail showed them to that person, and nothing about any other entry: not how many "
    "there were, where they fell or whether there were any. It is not a hash chain and cannot be "
    "verified as one. entries_digest is the sha256 of the entry lines, so a copy can be matched "
    "to the record of this export."
)


class ReadableManifest(BaseModel):
    """Who took the document, why, over which instants, and what it is.

    `entry_count` is the number of lines below it, which the holder of the file can count for
    themselves. It is never a number about anything the document does not carry.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: str = Field(default=READABLE_FORMAT, pattern=FIELD_NAME)
    exported_at: datetime
    exported_by: str = Field(pattern=IDENTIFIER)
    trace_id: str = Field(pattern=TRACE_ID)
    reason_code: str = Field(pattern=FIELD_NAME, max_length=80)
    #: The window as the exporter asked for it: `since` included, `until` not.
    since: datetime
    until: datetime
    entry_count: int = Field(ge=0)
    entries_digest: str = Field(pattern=DIGEST)
    carries: str = WHAT_THIS_DOCUMENT_CARRIES

    @field_validator("exported_at", "since", "until")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            msg = "a readable export's instants must be timezone-aware; a naive one is a silent bug"
            raise ValueError(msg)
        return v

    @field_validator("carries")
    @classmethod
    def _carries_is_the_sentence(cls, v: str) -> str:
        """Pinned, so no caller can write a sentence that depends on what was withheld."""
        if v != WHAT_THIS_DOCUMENT_CARRIES:
            msg = (
                "what a readable export carries describes the format, not this export; it is fixed"
            )
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.until <= self.since:
            msg = "until must be after since; a window that ends before it starts holds nothing"
            raise ValueError(msg)
        return self


class ReadableExport(BaseModel):
    """The manifest and the rows it describes, kept together until `render`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: ReadableManifest
    rows: tuple[AuditRow, ...]

    def render(self) -> str:
        """One manifest line, then one line per row, in `in_document_order`."""
        return canonical_json(self.manifest.model_dump(mode="json")) + "\n" + _row_block(self.rows)


def row_payload(row: AuditRow) -> dict[str, object]:
    """One row as plain JSON types: exactly `AuditRow`'s fields, with the instant in UTC."""
    return {
        "at": row.at.astimezone(UTC).isoformat(),
        "action": row.action.value,
        "actor_id": row.actor_id,
        "subject_kind": row.subject_kind,
        "subject_id": row.subject_id,
        "details": dict(row.details),
    }


def in_document_order(rows: Iterable[AuditRow]) -> tuple[AuditRow, ...]:
    """The rows by instant, then by their own canonical line. See the module docstring."""
    return tuple(sorted(rows, key=lambda row: (row.at, canonical_json(row_payload(row)))))


def _row_block(rows: Sequence[AuditRow]) -> str:
    return "".join(canonical_json(row_payload(row)) + "\n" for row in rows)


def build_readable_export(
    rows: Iterable[AuditRow],
    *,
    exported_by: str,
    trace_id: str,
    reason_code: str,
    at: datetime,
    since: datetime,
    until: datetime,
) -> ReadableExport:
    """Assemble the document over rows the audit view has already shown this exporter.

    Takes rows rather than entries, so nothing here can be handed a chain position to leak: an
    `AuditRow` has no field for one. Which rows is `brain.ops.data_transfer`'s question, answered
    by the view.
    """
    ordered = in_document_order(rows)
    manifest = ReadableManifest(
        exported_at=at,
        exported_by=exported_by,
        trace_id=trace_id,
        reason_code=reason_code,
        since=since,
        until=until,
        entry_count=len(ordered),
        entries_digest=hashlib.sha256(_row_block(ordered).encode("utf-8")).hexdigest(),
    )
    return ReadableExport(manifest=manifest, rows=ordered)


def verify_readable_document(document: str) -> tuple[bool, str]:
    """Re-read a rendered readable export and check it against its own manifest.

    The sender's check, as `brain.audit.export.verify_document` is for the chain: a truncated write
    or a mangled encoding is caught before the document is handed over.
    """
    lines = document.splitlines(keepends=True)
    if not lines:
        return False, "empty document"
    try:
        manifest = ReadableManifest.model_validate_json(lines[0])
    except ValueError as exc:
        return False, f"manifest line does not parse: {exc}"
    block = "".join(lines[1:])
    if hashlib.sha256(block.encode("utf-8")).hexdigest() != manifest.entries_digest:
        return False, "entries_digest does not match the entry block"
    if len(lines) - 1 != manifest.entry_count:
        return False, f"manifest claims {manifest.entry_count} entries, found {len(lines) - 1}"
    return True, "manifest matches the entry block"
