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

**A drill writes a manifest too, and it records what was asked rather than what it concluded.**
This is the half that was missing on 2026-09-10 and it is why `brain.ops.recovery.Verification`
had no producer. The obvious format carries a `verified` boolean, and then the thing deciding
what counts as a verified restore is a shell script on somebody's server: a runner that never
asked the permission canary writes `"verified": true` and every screen downstream believes it.
So a drill manifest carries the backup it read, when it started, when the last check finished,
that it restored into a scratch target, and one entry per check saying what was asked and what
came back. The verdict is `verification_of`'s and nothing else's, which is the same rule
`Verification` already keeps by being obtainable from one function. A runner that omits the
canary produces a verification whose shortfall says the canary did not run, and it cannot
produce one that says otherwise. See `A_RUNNER_THAT_COULD_WRITE_THE_VERDICT_WOULD_BE_THE_RULE`.

Rejected: a table for drill results. It is the obvious place for a record a console reads, and
`A_RECORD_OF_A_BACKUP_KEPT_ONLY_IN_THE_DATABASE_IS_LOST_WITH_IT` applies to a drill with more
force than to a backup: the drill exists for the morning the database is gone, so a row proving
the copies were readable is unreadable in exactly the hour somebody needs it. The manifest sits
beside the artefact it read, under the same retention, in the bucket a restore reaches anyway.

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
taker is `ops/backup/brain-backup`, which runs on the client's own server, and the drill runner
is its sibling and is not written yet: this is the format it has to write.

Task ids: M30.3.1, M30.3.2
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.ops.recovery import (
    Backup,
    Check,
    CheckRun,
    Coverage,
    Drill,
    Method,
    RecoveryError,
    Verification,
    verification_of,
)

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

#: Why a drill manifest states what was asked and never what it proved.
A_RUNNER_THAT_COULD_WRITE_THE_VERDICT_WOULD_BE_THE_RULE: Final = (
    "A drill manifest carrying a verified flag puts the definition of a verified restore in "
    "a shell script on a client's server, where it is whatever that script's author believed "
    "on the afternoon they wrote it. The failure is not that somebody lies; it is that a "
    "runner which never asked the permission canary has nothing to report and writes true, "
    "and a restored copy missing its policies answers everything to everybody and passes. So "
    "the file carries the questions and the answers, the verdict is verification_of's, and a "
    "check that did not run arrives as a shortfall saying so rather than as an absence."
)

#: The file extension a manifest takes, so a listing can find them without reading every object.
MANIFEST_SUFFIX: Final = ".manifest.json"

#: The file extension a drill's record takes, in the same bucket beside the copy it read.
#:
#: Distinct from `MANIFEST_SUFFIX` and neither is a suffix of the other, which is the property
#: rather than the spelling: a reader selects objects by the end of the name, so one suffix
#: ending in the other would have `read_manifests` hand every drill record to `backup_from` and
#: report a healthy bucket as one unreadable file per drill that ran. A test asserts the
#: relation between the two constants rather than their values.
DRILL_SUFFIX: Final = ".drill.json"

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


#: Every field a drill's manifest must carry. Listed, for the reason `REQUIRED_FIELDS` is.
#:
#: There is no `verified` and no `rto_seconds` here, and their absence is the design. See
#: `A_RUNNER_THAT_COULD_WRITE_THE_VERDICT_WOULD_BE_THE_RULE`.
DRILL_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "backup_id",
    "started_at",
    "finished_at",
    "into_scratch",
    "checks",
)

#: Every field one check entry inside a drill manifest must carry.
CHECK_REQUIRED_FIELDS: Final[tuple[str, ...]] = ("check", "passed", "detail")


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


# ------------------------------------------------------------------------ what a drill wrote
def _flag(value: Any, *, field: str, where: str) -> bool:
    """One boolean from a manifest, refusing everything that is merely truthy.

    **This is the refusal that matters most in this module and it fails in the flattering
    direction.** A shell script writing `"passed": "false"` produces a string, and a string of
    five characters is true to Python, so a check that failed reads as a check that passed and
    the restore verifies. The same value in `into_scratch` turns a drill that ran against the
    live database into one `Drill` accepts, which is the misconfiguration that value class
    exists to refuse.

    `bool` before `int` because `bool` is an `int` in Python, which is the trap
    `backup_from` already carries for `size_bytes`: here `1` would read as a pass and `0` as a
    failure, and a format that quietly accepts either is one a runner can be written against by
    accident.
    """
    if not isinstance(value, bool):
        msg = (
            f"{where}: {field} is {value!r}, and a drill's answers are written as true or "
            "false. Anything else is read for its truthiness, which makes the string false a "
            "pass"
        )
        raise ManifestError(msg)
    return value


def _check_run(entry: Any, *, position: int, where: str) -> CheckRun:
    """One check entry as what was asked and what came back. Never a verdict about the whole."""
    if not isinstance(entry, Mapping):
        msg = f"{where}: check {position} is a {type(entry).__name__} and a check is an object"
        raise ManifestError(msg)
    missing = [name for name in CHECK_REQUIRED_FIELDS if name not in entry]
    if missing:
        msg = f"{where}: check {position} has no {', '.join(missing)}"
        raise ManifestError(msg)
    try:
        asked = Check(entry["check"])
    except ValueError as exc:
        msg = f"{where}: check {position}: {exc}"
        raise ManifestError(msg) from exc
    detail = entry["detail"]
    if not isinstance(detail, str):
        msg = (
            f"{where}: check {position} says what happened as a "
            f"{type(detail).__name__}, and a drill report is read by a person"
        )
        raise ManifestError(msg)
    try:
        return CheckRun(
            check=asked,
            passed=_flag(entry["passed"], field=f"check {position} passed", where=where),
            detail=detail,
        )
    except RecoveryError as exc:
        msg = f"{where}: {exc}"
        raise ManifestError(msg) from exc


def drill_from(document: Mapping[str, Any], *, where: str) -> Drill:
    """One drill manifest as the attempt it records, refusing anything it cannot describe.

    A `Drill` and not a `Verification`, which is the whole point: what the runner may state is
    what it did, and `verification_of` decides what that proved. See
    `A_RUNNER_THAT_COULD_WRITE_THE_VERDICT_WOULD_BE_THE_RULE`.

    `Drill`'s own refusals are kept rather than duplicated, in the same split `backup_from`
    uses: a negative duration, a naive instant, one check run twice and a target that is not
    scratch are all its rules, and the exception is re-raised with the file named because a
    reader looking at a bucket has no other way to find which object complained.
    """
    missing = [name for name in DRILL_REQUIRED_FIELDS if name not in document]
    if missing:
        msg = f"{where}: no {', '.join(missing)}, so the drill cannot be described"
        raise ManifestError(msg)

    backup_id = document["backup_id"]
    if not isinstance(backup_id, str):
        msg = f"{where}: backup_id is {type(backup_id).__name__} and an identifier is a string"
        raise ManifestError(msg)

    entries = document["checks"]
    # A string is a Sequence, and a runner writing one check name rather than a list would
    # otherwise be read one character at a time into as many refusals as the name is long.
    if not isinstance(entries, Sequence) or isinstance(entries, str):
        msg = (
            f"{where}: checks is {type(entries).__name__} and a drill's checks are a list, "
            "even when it asked one question or none"
        )
        raise ManifestError(msg)

    try:
        return Drill(
            backup_id=backup_id,
            started_at=_instant(document["started_at"], field="started_at", where=where),
            finished_at=_instant(document["finished_at"], field="finished_at", where=where),
            into_scratch=_flag(document["into_scratch"], field="into_scratch", where=where),
            checks=tuple(
                _check_run(entry, position=at, where=where) for at, entry in enumerate(entries)
            ),
        )
    except RecoveryError as exc:
        msg = f"{where}: {exc}"
        raise ManifestError(msg) from exc


def read_drills(
    objects: Iterable[tuple[str, str]],
) -> tuple[tuple[Verification, ...], tuple[Unreadable, ...]]:
    """Every drill record in a bucket as what it proved, and every one that could not be read.

    Returns verifications rather than drills, because a caller handed drills would have to run
    `verification_of` itself and a caller that forgot would have the attempt and the proof
    collapsed back into one thing. The conversion is here, once.

    Both halves from one call, the shape
    `AN_UNREADABLE_MANIFEST_IS_THE_ONE_MOST_LIKELY_TO_MATTER` argues for, and it argues harder
    here: the drill whose record is truncated is the drill that fell over, and dropping it
    silently leaves an older success standing as the newest evidence.

    Sorted by the moment each drill began, newest last, matching `read_manifests` so a caller
    reading a bucket does not have to remember which of two functions sorts which way.
    """
    read: list[Verification] = []
    failed: list[Unreadable] = []
    for name, content in objects:
        if not name.endswith(DRILL_SUFFIX):
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
                    why=(
                        f"the top level is a {type(document).__name__} and a drill record is "
                        "an object"
                    ),
                )
            )
            continue
        try:
            read.append(verification_of(drill_from(document, where=name)))
        except ManifestError as exc:
            failed.append(Unreadable(where=name, why=str(exc)))
    return tuple(sorted(read, key=lambda one: (one.attempted_at, one.backup_id))), tuple(failed)


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
