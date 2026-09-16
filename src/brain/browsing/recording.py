"""Everything a browser run said and saw, kept for the recordings window and not a day longer.

A browser run is the widest artefact this system produces: it reads somebody's accounting system
with somebody's session. When the run is disputed, the recording is the evidence of what the page
showed and what the run did, and when it is not, the recording is a copy of a client's records
with no permissions attached. Both facts shape this module.

**Full means every line, both ways.** The recording is the transcript of `brain.browsing.wire`
between the control plane and the runner, in order: the start, every instruction, every tree,
every frame, every record and the end. It is not a summary the control plane chose to keep, and
`recording_gaps` refuses a transcript that does not start with a start, end with an end, number
its trees one by one, and hold a stored picture for every frame it kept. A recording that stopped
early is reported as that rather than as a short run.

**A credential is scrubbed from every line before it is stored, and one found coming back is an
incident.** An instruction to type a password carries the resolved value to the runner; that line
is scrubbed and nothing more is said, because that is where the value is meant to be. A value
found in a line the runner sent is different: the page put it somewhere text can be read, which
`brain.browsing.credentials.scrub_history` calls an incident, and its index is reported. The tree
sequences it was found in are what `brain.browsing.verification.admit_frames` withholds pictures
beside.

**A picture is stored only when a judge could be shown it.** The caller passes the digests
`admit_frames` admitted, and every other picture is recorded by digest alone. A picture a judge may
not see because a credential might be in it is not made safe by putting it in a bucket instead.

**Retention is the recordings bucket's, derived and never restated.** The window is
`brain.ops.retention.RECORDING_RETENTION_DAYS`, which is `brain.ops.storage`'s lifecycle rule for
the `recordings` bucket. Every key begins with the day the run started, so what is due is decided
from the key alone, and the bucket's own rule and `remove_expired` agree without either reading
the other. There is no per-run override, for the reason `brain.ops.retention` gives at length: a
row that can argue with its class keeps itself for ever. A run named by a legal hold is not
removed, and the hold is what the caller resolves, because which runs a hold covers is decided
where holds are read. A key that carries no date is never deleted and never silently kept: it is
counted, so a stray object in the bucket is a finding.

Not built: the worker that holds the transcript while a run is in flight and calls `record` and
`write` at its end, and a scheduled caller of `remove_expired`. Nothing here has written to an
object store; `brain.ops.object_store.S3Backend` implements `StorageBackend` and nothing hands
it to this module yet.

Task ids: M19.6.6
"""

from __future__ import annotations

import base64
import binascii
import enum
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

from brain.browsing.credentials import scrub_outbound
from brain.browsing.wire import Kind, WireError, decode
from brain.ops.retention import RECORDING_RETENTION_DAYS
from brain.ops.storage import ObjectKind, StorageBackend, bucket_for

#: Where every browser recording lives inside the recordings bucket.
PREFIX: Final = "browser-runs"

#: A recording key: the prefix, the day the run started, the run, and what the object is.
KEY_RE: Final = re.compile(r"^browser-runs/(\d{4})/(\d{2})/(\d{2})/([^/]+)/")

#: Why a picture that may hold a credential is not stored.
A_BUCKET_IS_NOT_A_SAFER_PLACE_FOR_A_PICTURE_A_JUDGE_MAY_NOT_SEE: Final = (
    "A frame is withheld from a judge because a credential may be drawn in it. Storing it anyway "
    "moves the credential from a model's context to an object store, outside the vault's custody, "
    "for thirty days. The digest is kept, so the recording still says a picture was taken."
)


class RecordingError(Exception):
    """A recording was asked for in terms that would store something it must not."""


class Direction(enum.StrEnum):
    """Which way a line crossed."""

    TO_RUNNER = "to_runner"
    FROM_RUNNER = "from_runner"


@dataclass(frozen=True)
class Recording:
    """One run's transcript, scrubbed, and the pictures it may keep."""

    run_id: str
    started_at: datetime
    #: Every line in order, scrubbed, with each frame's picture removed from its line.
    entries: tuple[tuple[Direction, str], ...]
    #: Digest to picture, for the frames a judge could be shown and whose picture matched.
    pictures: tuple[tuple[str, bytes], ...] = ()
    #: Entry indices of runner lines in which a bound credential value was found.
    leaked: tuple[int, ...] = ()
    #: Frames whose picture did not hash to the digest they carried.
    mismatched: tuple[str, ...] = ()


def as_written(secrets: Sequence[str]) -> tuple[str, ...]:
    """Each value as it is, and as it appears inside a JSON string, which is how a line holds it.

    A password with a quote, a backslash or any character outside ASCII is escaped when a line is
    encoded, so searching a line for the value alone finds nothing and reports a clean scrub.
    """
    forms: list[str] = []
    for secret in secrets:
        forms.append(secret)
        written = json.dumps(secret)[1:-1]
        if written != secret:
            forms.append(written)
    return tuple(forms)


def secrets_seen(
    exchanged: Sequence[tuple[Direction, bytes]], secrets: Sequence[str]
) -> frozenset[int]:
    """The tree sequences in which a bound credential value appeared in text the runner sent."""
    found: set[int] = set()
    for direction, line in exchanged:
        if direction is not Direction.FROM_RUNNER:
            continue
        try:
            message = decode(line)
        except WireError:
            continue
        if message.kind is not Kind.SNAPSHOT:
            continue
        _, hits = scrub_outbound(line.decode("utf-8", errors="replace"), as_written(secrets))
        if hits:
            found.add(int(message.fields["sequence"]))
    return frozenset(found)


def record(
    run_id: str,
    started_at: datetime,
    exchanged: Sequence[tuple[Direction, bytes]],
    secrets: Sequence[str],
    *,
    keep_pictures: frozenset[str],
) -> Recording:
    """The transcript of one run as it will be stored. `keep_pictures` are admitted digests."""
    entries: list[tuple[Direction, str]] = []
    pictures: dict[str, bytes] = {}
    leaked: list[int] = []
    mismatched: list[str] = []
    for index, (direction, line) in enumerate(exchanged):
        text = line.decode("utf-8", errors="replace")
        try:
            message = decode(line)
        except WireError:
            message = None
        if message is not None and message.kind is Kind.FRAME:
            digest = str(message.fields["digest"])
            picture = _picture(message.fields["picture"])
            if picture is None or hashlib.sha256(picture).hexdigest() != digest:
                mismatched.append(digest)
            elif digest in keep_pictures:
                pictures[digest] = picture
            text = json.dumps(
                {"kind": Kind.FRAME.value, **message.fields, "picture": ""},
                separators=(",", ":"),
                sort_keys=True,
            )
        scrubbed, hits = scrub_outbound(text, as_written(secrets))
        if hits and direction is Direction.FROM_RUNNER:
            leaked.append(index)
        entries.append((direction, scrubbed))
    return Recording(
        run_id=run_id,
        started_at=started_at,
        entries=tuple(entries),
        pictures=tuple(sorted(pictures.items())),
        leaked=tuple(leaked),
        mismatched=tuple(mismatched),
    )


def _picture(value: object) -> bytes | None:
    if not isinstance(value, str):
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None


def recording_gaps(recording: Recording) -> tuple[str, ...]:
    """Every way this recording is less than the whole run. Empty when it is full."""
    gaps: list[str] = []
    kinds: list[tuple[Direction, Kind | None, dict[str, object]]] = []
    for direction, text in recording.entries:
        try:
            message = decode(text.encode("utf-8"))
            kinds.append((direction, message.kind, dict(message.fields)))
        except WireError:
            kinds.append((direction, None, {}))
    if not kinds or kinds[0][:2] != (Direction.TO_RUNNER, Kind.START):
        gaps.append("the recording does not begin with the run's start")
    if not kinds or kinds[-1][:2] != (Direction.FROM_RUNNER, Kind.ENDED):
        gaps.append("the recording does not reach the end of the run")
    sequences = [
        fields["sequence"]
        for direction, kind, fields in kinds
        if direction is Direction.FROM_RUNNER and kind is Kind.SNAPSHOT
    ]
    if sequences != list(range(1, len(sequences) + 1)):
        gaps.append("the trees in the recording are not numbered one by one from the first")
    for digest in recording.mismatched:
        gaps.append(f"a frame's picture did not match its digest {digest[:12]}")
    if any(kind is None for _, kind, _ in kinds):
        gaps.append("the recording holds a line that is not a message of the protocol")
    return tuple(gaps)


def prefix_for(run_id: str, started_at: datetime) -> str:
    """The key prefix for one run: the day it started, then the run."""
    if not run_id or "/" in run_id:
        msg = f"run id {run_id!r} cannot be a single key segment"
        raise RecordingError(msg)
    return f"{PREFIX}/{started_at:%Y/%m/%d}/{run_id}/"


def write(backend: StorageBackend, recording: Recording) -> tuple[str, ...]:
    """Store the transcript and the kept pictures. Returns the keys written."""
    bucket = bucket_for(ObjectKind.BROWSER_RUN_RECORDING).name
    prefix = prefix_for(recording.run_id, recording.started_at)
    transcript = "".join(
        json.dumps({"direction": direction.value, "line": text.rstrip("\n")}) + "\n"
        for direction, text in recording.entries
    ).encode("utf-8")
    keys = [f"{prefix}transcript.jsonl"]
    backend.put_object(bucket, keys[0], transcript, "application/x-ndjson")
    for digest, picture in recording.pictures:
        key = f"{prefix}frames/{digest}.png"
        backend.put_object(bucket, key, picture, "image/png")
        keys.append(key)
    return tuple(keys)


def started_on(key: str) -> date | None:
    """The day a recording's run started, read off its key, or None for a key with no date."""
    found = KEY_RE.match(key)
    if found is None:
        return None
    try:
        return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    except ValueError:
        return None


def expires_on(started: date) -> date:
    """The first day a recording started on this day may no longer be kept."""
    return started + timedelta(days=RECORDING_RETENTION_DAYS)


@dataclass(frozen=True)
class Removal:
    """What a retention pass found in the recordings: removable keys, and counts of the rest."""

    due: tuple[str, ...] = ()
    held: int = 0
    undated: int = 0


def removal(keys: Sequence[str], *, today: date, held_runs: frozenset[str]) -> Removal:
    """Which keys are past the window and not held. Undated keys are counted and never due."""
    due: list[str] = []
    held = 0
    undated = 0
    for key in keys:
        started = started_on(key)
        if started is None:
            undated += 1
            continue
        if expires_on(started) > today:
            continue
        found = KEY_RE.match(key)
        if found is not None and found.group(4) in held_runs:
            held += 1
            continue
        due.append(key)
    return Removal(due=tuple(due), held=held, undated=undated)


def remove_expired(backend: StorageBackend, *, today: date, held_runs: frozenset[str]) -> Removal:
    """Remove every recording object past the window that no hold names. Returns what it found."""
    bucket = bucket_for(ObjectKind.BROWSER_RUN_RECORDING).name
    found = removal(
        tuple(backend.list_objects(bucket, f"{PREFIX}/")), today=today, held_runs=held_runs
    )
    for key in found.due:
        backend.delete_object(bucket, key)
    return found
