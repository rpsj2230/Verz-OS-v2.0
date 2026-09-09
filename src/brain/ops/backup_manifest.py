"""What a copy that was taken says about itself, written beside it rather than into it.

`brain.ops.recovery` is the domain: what a copy is, how much exposure a schedule leaves, when a
drill is owed, what a service level statement may promise. It takes every observation as a
parameter and its own header says so. Nothing produced those observations, so `latest` had
nothing to be latest of and `alerts` had nothing to alert about. Needs Rupash item 44 chose
option C: take the nightly copy now, and let the drill that verifies it arrive with M30.

**The record of a copy must not live only inside the thing being copied.** A row in the
database saying "the database was backed up at 02:00" is lost with the database, which is the
one moment anybody needs it. So the taker writes a small manifest beside the artefact, in the
same bucket, and this module reads those manifests back into `brain.ops.recovery.Backup`. See
`A_RECORD_OF_A_BACKUP_KEPT_ONLY_IN_THE_DATABASE_IS_LOST_WITH_IT`.

**The manifest is written by the thing that took the copy, which is the only honest author.**
`Backup`'s own docstring says a copy is described "as the thing that took it can honestly
describe it", and the fields are chosen for what a dump command actually knows: when it began,
when it finished, how many bytes it wrote, and the instant the copy is consistent to. Nothing
here infers a field from another one.

**The byte count is the field that catches the commonest silent failure.** A dump command that
exits zero having written nothing is invisible in every listing that shows a timestamp, and
`Backup.__post_init__` already refuses a copy of no bytes for exactly that reason. The manifest
carries the size the taker measured on disk rather than the size the object store reports,
because those disagree precisely when the upload was truncated, and the disagreement is the
finding. See `A_DUMP_THAT_EXITS_ZERO_HAVING_WRITTEN_NOTHING_LOOKS_LIKE_A_BACKUP`.

**A manifest that cannot be read is reported and never skipped.** A bucket holding six good
manifests and one unparseable one must not answer "six copies"; it must answer "six copies and
one file I could not read", because the unreadable one is the one most likely to belong to the
run that went wrong. `read_manifests` returns both halves from one call and
`manifest_gaps` renders them, so a caller cannot take the count without also being handed the
complaint. See
`AN_UNREADABLE_MANIFEST_IS_THE_ONE_MOST_LIKELY_TO_MATTER`.

Rejected: putting the manifest inside the dump file as a header. It makes the size and the
consistency point unreadable without decompressing a multi-gigabyte artefact, so a console
panel showing "last backup" would have to fetch every copy to render a row.

Rejected: naming the manifest after the moment it was written. Two runs in the same second on
two hosts would collide and the second would overwrite the first, which loses the record of a
run rather than the run. The identifier the taker chose is the name, and `Backup` already
refuses an empty one.

Rejected: a `taken_by` field naming the host. It is the obvious provenance field and it is a
client value: this repository is the product every company installs, and a hostname written
into a manifest format is a hostname in the source the day somebody writes a default for it.
What a reader actually needs is which install, and an install is the bucket the manifest is in.

Scope: reading and refusing. Nothing here opens a socket, reads a clock or takes a dump. The
taker is `ops/backup/brain-backup`, which runs on the client's own server.

Task ids: M30.3.1, M30.3.2
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.ops.recovery import Backup, Coverage, Method, RecoveryError

#: Why the manifest sits in the bucket rather than in a table.
A_RECORD_OF_A_BACKUP_KEPT_ONLY_IN_THE_DATABASE_IS_LOST_WITH_IT: Final = (
    "A row recording last night's dump is in the database the dump exists to replace, so the "
    "one morning anybody reads that row is the morning it is gone. The manifest travels with "
    "the artefact it describes, in the same bucket, under the same retention, and a reader "
    "that can reach the copy can always reach its description."
)

#: Why the taker's measured size is on the manifest.
A_DUMP_THAT_EXITS_ZERO_HAVING_WRITTEN_NOTHING_LOOKS_LIKE_A_BACKUP: Final = (
    "The commonest silent backup failure is a command that succeeds and produces an empty "
    "file, and every listing that shows a name and a timestamp shows it as fine. The taker "
    "measures the artefact on disk before uploading it, so a truncated upload disagrees with "
    "the manifest rather than being described by it."
)

#: Why an unreadable manifest is a finding rather than a skipped file.
AN_UNREADABLE_MANIFEST_IS_THE_ONE_MOST_LIKELY_TO_MATTER: Final = (
    "A run that failed halfway is the run whose manifest is truncated, so silently skipping "
    "what cannot be parsed drops exactly the evidence somebody is looking for and reports a "
    "healthy count. Every unreadable file is named, and the count and the complaint come from "
    "the same call so a caller cannot take one without the other."
)

#: The file extension a manifest takes, so a listing can find them without reading every object.
MANIFEST_SUFFIX: Final = ".manifest.json"

#: Every field a manifest must carry, in the order the taker writes them.
#:
#: Listed rather than inferred from `Backup`'s annotations, and the difference is the point:
#: `Backup` is the domain type and this is a file format written by a shell script on somebody
#: else's server. Deriving the format from the type would mean a refactor of the type silently
#: changes what six months of manifests are expected to contain.
REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "backup_id",
    "coverage",
    "method",
    "destination",
    "started_at",
    "finished_at",
    "recoverable_to",
    "size_bytes",
)


class ManifestError(Exception):
    """Raised when a manifest cannot be read as a description of a copy."""


@dataclass(frozen=True)
class Unreadable:
    """One manifest that could not be turned into a copy, and what stopped it.

    A type rather than a string, because two things are done with these: they are counted
    beside the readable ones and they are printed. A string can be printed and cannot be
    grouped by the file it came from without parsing the sentence back apart.
    """

    #: The object name in the bucket, so somebody can go and look at it.
    where: str
    #: What went wrong, in words, for whoever is reading a panel rather than a stack trace.
    why: str

    def __post_init__(self) -> None:
        if not self.where.strip():
            msg = "an unreadable manifest with no name cannot be gone and looked at"
            raise ManifestError(msg)
        if not self.why.strip():
            msg = f"{self.where!r} is unreadable and does not say why, which is a count again"
            raise ManifestError(msg)


def _instant(value: Any, *, field: str, where: str) -> datetime:
    """One ISO-8601 instant from a manifest. Only what `Backup` cannot already refuse.

    **There is deliberately no check for a naive instant here, and a mutation is why.** The
    first version of this refused one, on the argument that a reader needs the file named and
    `Backup`'s message cannot name it: `Backup` is a domain type and does not know it came from
    a file. That argument was wrong about this module. `backup_from` catches `RecoveryError`
    and re-raises it prefixed with the file, so the domain type's refusal already arrives
    naming the field and the file, and removing the check here changed nothing any test could
    see. It was a guard that could not fire, which CLAUDE.md calls this repository's most
    common defect, and it is gone rather than tested around.

    What is left is the pair `Backup` genuinely cannot do: a value that is not a string at all,
    and a string that is not an instant. Both are file-format faults rather than domain ones,
    because the domain type never sees a string.
    """
    if not isinstance(value, str):
        msg = f"{where}: {field} is {type(value).__name__} and an instant is written as a string"
        raise ManifestError(msg)
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"{where}: {field} is {value!r}, which is not an ISO-8601 instant ({exc})"
        raise ManifestError(msg) from exc


def backup_from(document: Mapping[str, Any], *, where: str) -> Backup:
    """One manifest as a copy, refusing anything it cannot describe honestly.

    Every refusal names the file, because a caller reading a bucket has no other way to find
    which of forty objects produced the message. `Backup`'s own refusals are kept rather than
    duplicated: a size of zero, a finish before a start and a snapshot claiming to restore past
    its own end are all its rules and it states them better than a copy here would.
    """
    missing = [name for name in REQUIRED_FIELDS if name not in document]
    if missing:
        msg = f"{where}: no {', '.join(missing)}, so the copy cannot be described"
        raise ManifestError(msg)

    try:
        coverage = Coverage(document["coverage"])
        method = Method(document["method"])
    except ValueError as exc:
        msg = f"{where}: {exc}"
        raise ManifestError(msg) from exc

    size = document["size_bytes"]
    # `bool` is an `int` in Python and `True` would pass an isinstance check and then pass
    # `Backup`'s "at least one byte" rule as the integer 1. A backup of one byte reported as
    # healthy is the failure this whole field exists to catch.
    if isinstance(size, bool) or not isinstance(size, int):
        msg = f"{where}: size_bytes is {size!r}, and a byte count is an integer"
        raise ManifestError(msg)

    destination = document["destination"]
    if not isinstance(destination, str) or not destination.strip():
        msg = f"{where}: destination is {destination!r}, so nothing says where the copy went"
        raise ManifestError(msg)

    backup_id = document["backup_id"]
    if not isinstance(backup_id, str):
        msg = f"{where}: backup_id is {type(backup_id).__name__} and an identifier is a string"
        raise ManifestError(msg)

    try:
        return Backup(
            backup_id=backup_id,
            coverage=coverage,
            method=method,
            destination=destination,
            started_at=_instant(document["started_at"], field="started_at", where=where),
            finished_at=_instant(document["finished_at"], field="finished_at", where=where),
            recoverable_to=_instant(
                document["recoverable_to"], field="recoverable_to", where=where
            ),
            size_bytes=size,
        )
    except RecoveryError as exc:
        msg = f"{where}: {exc}"
        raise ManifestError(msg) from exc


def read_manifests(
    objects: Iterable[tuple[str, str]],
) -> tuple[tuple[Backup, ...], tuple[Unreadable, ...]]:
    """Every manifest in a bucket as copies, and every one that could not be read.

    Takes name and content pairs rather than a bucket, for the reason the whole of
    `brain.ops.recovery` takes its observations: a module that opened the object store could
    not be asked what it does with a truncated file without standing up an object store.

    Both halves are returned from one call, which is the shape
    `AN_UNREADABLE_MANIFEST_IS_THE_ONE_MOST_LIKELY_TO_MATTER` argues for: a caller cannot get
    the count of good copies without also being handed the ones it could not read.

    Sorted by the moment each copy can restore to, newest last, so a caller wanting the newest
    takes the end rather than sorting again with a key it has to get right.
    """
    read: list[Backup] = []
    failed: list[Unreadable] = []
    for name, content in objects:
        if not name.endswith(MANIFEST_SUFFIX):
            continue
        try:
            document = json.loads(content)
        except json.JSONDecodeError as exc:
            failed.append(Unreadable(where=name, why=f"not JSON: {exc}"))
            continue
        if not isinstance(document, dict):
            failed.append(
                Unreadable(
                    where=name,
                    why=f"the top level is a {type(document).__name__} and a manifest is an object",
                )
            )
            continue
        try:
            read.append(backup_from(document, where=name))
        except ManifestError as exc:
            failed.append(Unreadable(where=name, why=str(exc)))
    return tuple(sorted(read, key=lambda one: one.recoverable_to)), tuple(failed)


def manifest_gaps(
    read: Sequence[Backup],
    unreadable: Sequence[Unreadable],
    *,
    expected: Sequence[Coverage] = (),
) -> tuple[str, ...]:
    """Everything about a bucket's manifests that a person should be told.

    Two shapes, and the second is the one a count cannot express. Every file that could not be
    read, because the run that failed halfway is the one whose manifest is truncated. And every
    coverage somebody expected a copy of and has none of: a bucket with forty database dumps
    and no configuration snapshot reports forty copies and is missing a whole coverage, and
    "forty" is the number a panel would show.

    `expected` defaults to nothing rather than to every coverage, so this reports on what a
    caller asked about instead of inventing a policy here. What ought to be copied is
    `brain.ops.recovery.SCHEDULE`'s question and it answers it there, with a reason per line.

    Unreadable files first and in name order, then missing coverages in the order asked for: a
    file somebody can go and look at is more actionable than an absence, and an absence is
    often explained by the file above it.
    """
    found = [f"{one.where}: {one.why}" for one in sorted(unreadable, key=lambda one: one.where)]
    have = {one.coverage for one in read}
    for coverage in expected:
        if coverage not in have:
            found.append(
                f"no readable copy of {coverage.value} at all, so a restore of it would have "
                "nothing to read back and every panel counting copies is counting other things"
            )
    return tuple(found)
