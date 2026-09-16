"""A run's recording: every line both ways, scrubbed, its pictures kept only where a judge could
see them, and removed on the recordings bucket's own window.

Dates here are pinned far from any plausible wall clock, as CLAUDE.md asks of a fixture that is
not about the present: 2999 and its neighbours.

Task ids: M19.6.6
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pytest

from brain.browsing.recording import (
    Direction,
    Recording,
    RecordingError,
    as_written,
    expires_on,
    prefix_for,
    record,
    recording_gaps,
    removal,
    remove_expired,
    secrets_seen,
    started_on,
    write,
)
from brain.browsing.wire import Kind, encode
from brain.ops.retention import RECORDING_RETENTION_DAYS
from brain.ops.storage import bucket

STARTED = datetime(2999, 3, 4, 10, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery"
PICTURE = b"a masked picture of the invoices page"
DIGEST = hashlib.sha256(PICTURE).hexdigest()


def start() -> bytes:
    return encode(
        Kind.START,
        run_id="run-1",
        asked_by="alex",
        digest="d",
        approved=True,
        origins=["https://books.example"],
        steps=[],
        budget=[],
        tiers=[],
        unattended=[],
        surfaces={},
    )


def act(text: str = "") -> bytes:
    return encode(
        Kind.ACT,
        index=1,
        surface="login",
        verb="type",
        ref="n4",
        sequence=1,
        placeholder="{{secret:books_password}}",
        text=text,
    )


def tree(sequence: int, name: str = "Invoices") -> bytes:
    return encode(
        Kind.SNAPSHOT,
        sequence=sequence,
        origin="https://books.example",
        nodes=[["n4", "textbox", name]],
    )


def picture(sequence: int, data: bytes = PICTURE, digest: str = DIGEST) -> bytes:
    return encode(
        Kind.FRAME,
        sequence=sequence,
        origin="https://books.example",
        digest=digest,
        inputs_masked=True,
        picture=base64.b64encode(data).decode("ascii"),
    )


def run(*middle: tuple[Direction, bytes]) -> list[tuple[Direction, bytes]]:
    return [
        (Direction.TO_RUNNER, start()),
        *middle,
        (Direction.FROM_RUNNER, encode(Kind.ENDED, reason="stopped")),
    ]


# ------------------------------------------------------------------ what is kept
def test_a_whole_run_is_recorded_line_for_line_and_has_no_gap() -> None:
    """The positive case. Delete this and a recorder that keeps nothing satisfies every refusal."""
    exchanged = run(
        (Direction.FROM_RUNNER, tree(1)),
        (Direction.FROM_RUNNER, picture(1)),
        (Direction.TO_RUNNER, act()),
        (Direction.FROM_RUNNER, tree(2)),
    )

    recording = record("run-1", STARTED, exchanged, [PASSWORD], keep_pictures=frozenset({DIGEST}))

    assert len(recording.entries) == len(exchanged)
    assert recording.pictures == ((DIGEST, PICTURE),)
    assert recording_gaps(recording) == ()
    assert '"picture":""' in recording.entries[2][1]


def test_a_credential_sent_to_the_runner_is_scrubbed_and_is_not_an_incident() -> None:
    """The instruction to type a password carries it, which is where it is meant to be.

    Delete this and the resolved password is stored in the recordings bucket for thirty days."""
    recording = record(
        "run-1",
        STARTED,
        run((Direction.TO_RUNNER, act(PASSWORD))),
        [PASSWORD],
        keep_pictures=frozenset(),
    )

    assert all(PASSWORD not in text for _, text in recording.entries)
    assert recording.leaked == ()


def test_a_credential_the_runner_sends_back_is_scrubbed_and_reported_with_its_tree() -> None:
    """The page put the password where text can be read. Delete this and the incident is scrubbed
    quietly, and the pictures beside that tree are not withheld."""
    exchanged = run((Direction.FROM_RUNNER, tree(1, name=f"Welcome back {PASSWORD}")))

    recording = record("run-1", STARTED, exchanged, [PASSWORD], keep_pictures=frozenset())

    assert recording.leaked == (1,)
    assert PASSWORD not in recording.entries[1][1]
    assert secrets_seen(exchanged, [PASSWORD]) == frozenset({1})
    assert secrets_seen(run((Direction.FROM_RUNNER, tree(1))), [PASSWORD]) == frozenset()


def test_a_credential_escaped_by_the_line_encoding_is_still_found() -> None:
    """A quote or an accented letter is escaped in a JSON line, so the value as typed is not in the
    line. Delete this and a password with either is stored as written and reported clean."""
    awkward = 'pa"ss\\wörd-long'
    exchanged = run((Direction.FROM_RUNNER, tree(1, name=awkward)))

    recording = record("run-1", STARTED, exchanged, [awkward], keep_pictures=frozenset())

    assert recording.leaked == (1,)
    assert json.dumps(awkward)[1:-1] not in recording.entries[1][1]
    assert len(as_written([awkward])) == 2


def test_a_picture_a_judge_may_not_see_is_recorded_by_digest_and_not_stored() -> None:
    """Delete this and a frame withheld because a credential may be drawn in it is copied into an
    object store outside the vault's custody instead."""
    recording = record(
        "run-1",
        STARTED,
        run((Direction.FROM_RUNNER, tree(1)), (Direction.FROM_RUNNER, picture(1))),
        [PASSWORD],
        keep_pictures=frozenset(),
    )

    assert recording.pictures == ()
    assert DIGEST in recording.entries[2][1]


# ------------------------------------------------------------------ what is full
@pytest.mark.parametrize(
    ("exchanged", "gap"),
    [
        ([(Direction.FROM_RUNNER, encode(Kind.ENDED, reason="x"))], "begin with the run's start"),
        ([(Direction.TO_RUNNER, start())], "reach the end of the run"),
        (run((Direction.FROM_RUNNER, tree(1)), (Direction.FROM_RUNNER, tree(3))), "one by one"),
        (run((Direction.FROM_RUNNER, picture(1, data=b"other"))), "did not match its digest"),
        (run((Direction.FROM_RUNNER, b"garbage\n")), "not a message of the protocol"),
    ],
    ids=["no start", "no end", "a tree missing", "a picture swapped", "an unreadable line"],
)
def test_a_recording_that_is_less_than_the_whole_run_says_so(
    exchanged: list[tuple[Direction, bytes]], gap: str
) -> None:
    """Delete this and a run cut short, or a picture replaced, is stored as a complete recording."""
    recording = record("run-1", STARTED, exchanged, [], keep_pictures=frozenset({DIGEST}))

    assert any(gap in one for one in recording_gaps(recording))


# ------------------------------------------------------------------ where and how long
@dataclass
class FakeBackend:
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.objects[(bucket_name, key)] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.objects[(bucket_name, key)]

    def delete_object(self, bucket_name: str, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop((bucket_name, key), None)

    def list_objects(self, bucket_name: str, prefix: str) -> Iterator[str]:
        return iter(sorted(key for name, key in self.objects if key.startswith(prefix)))


def test_a_recording_is_written_to_the_recordings_bucket_under_the_day_its_run_started() -> None:
    """Delete this and recordings can land in a bucket with another window, or under keys a
    retention pass cannot date."""
    backend = FakeBackend()
    recording = Recording(
        run_id="run-1",
        started_at=STARTED,
        entries=((Direction.TO_RUNNER, "line"),),
        pictures=((DIGEST, PICTURE),),
    )

    keys = write(backend, recording)

    assert keys == (
        "browser-runs/2999/03/04/run-1/transcript.jsonl",
        f"browser-runs/2999/03/04/run-1/frames/{DIGEST}.png",
    )
    assert {name for name, _ in backend.objects} == {"recordings"}
    assert all(started_on(key) == date(2999, 3, 4) for key in keys)


def test_the_window_is_the_recordings_buckets_own_lifecycle_rule() -> None:
    """Asserted against `brain.ops.storage`, not against the constant this module imports, so a
    retyped window here would fail. Delete this and recordings can be kept on a second number that
    drifts from the bucket's rule in the direction that keeps more."""
    assert bucket("recordings").retention_days == RECORDING_RETENTION_DAYS
    assert expires_on(date(2999, 3, 4)) == date(2999, 3, 4) + timedelta(days=30)


def test_a_recording_is_due_on_the_day_its_window_ends_and_not_the_day_before() -> None:
    """The boundary, both sides. Delete this and a comparison can slip by a day in either direction
    with every other test green."""
    key = prefix_for("run-1", STARTED) + "transcript.jsonl"
    ends = expires_on(STARTED.date())

    assert removal([key], today=ends - timedelta(days=1), held_runs=frozenset()).due == ()
    assert removal([key], today=ends, held_runs=frozenset()).due == (key,)


def test_a_held_run_and_an_undated_key_are_counted_and_never_removed() -> None:
    """Delete this and a run under legal hold is removed on schedule, or a stray object with no
    date in its key is deleted because nothing could say how old it was."""
    old = prefix_for("run-1", STARTED) + "transcript.jsonl"
    held = prefix_for("run-2", STARTED) + "transcript.jsonl"
    backend = FakeBackend(
        objects={
            ("recordings", old): b"",
            ("recordings", held): b"",
            ("recordings", "browser-runs/stray.txt"): b"",
        }
    )

    found = remove_expired(backend, today=date(3000, 1, 1), held_runs=frozenset({"run-2"}))

    assert backend.deleted == [old]
    assert found.held == 1
    assert found.undated == 1


def test_a_run_id_that_is_not_one_key_segment_is_refused() -> None:
    """Delete this and a run id with a slash writes its recording under another run's prefix."""
    with pytest.raises(RecordingError, match="single key segment"):
        prefix_for("run/2", STARTED)
