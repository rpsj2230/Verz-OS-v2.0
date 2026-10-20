"""Recordings sit under the install's prefix, are held by a hold, and are removed when due.

The pure half holds the wrapper that puts every key under the install's prefix, the rule that says
which runs a hold keeps, and the sentence a pass reports. The database half builds PostgreSQL at
head and reads the holds and the askers from the tables the schedule reads them from; it skips when
`DATABASE_URL` is unset. The clock is 2999, for the reason CLAUDE.md records about fixtures that go
off, and the window is added to it, so the test is about the window and not about today.

Task ids: M19.6.6, M19.9.11
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from brain.browsing.recording import prefix_for
from brain.browsing.recording_sweep import (
    Holds,
    Under,
    run_recording_sweep_now,
    runs_held,
    runs_in,
    sweep,
)
from brain.ops.retention import RECORDING_RETENTION_DAYS
from brain.ops.storage import ObjectKind, bucket_for

BUCKET = bucket_for(ObjectKind.BROWSER_RUN_RECORDING).name
STARTED = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)
LONG_AFTER = STARTED + timedelta(days=RECORDING_RETENTION_DAYS + 5)
INSIDE_THE_WINDOW = STARTED + timedelta(days=RECORDING_RETENTION_DAYS - 5)


class Bucket:
    """A backend that keeps what it is handed and lists in the order it was given."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self.objects[(bucket, key)] = body

    def get_object(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]

    def delete_object(self, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)

    def list_objects(self, bucket: str, prefix: str) -> Iterator[str]:
        return iter(
            [key for (name, key) in self.objects if name == bucket and key.startswith(prefix)]
        )


def keep(backend: Bucket, run: str, *, started: datetime = STARTED) -> str:
    key = f"{prefix_for(run, started)}transcript.jsonl"
    backend.put_object(BUCKET, key, b"{}", "application/x-ndjson")
    return key


# ------------------------------------------------------------------------------- the prefix
def test_every_key_goes_under_the_prefix_and_is_listed_without_it() -> None:
    """Delete this and recordings land at the bucket's root, where the Storage screen counts
    nothing and a sweep that lists under the prefix finds none of them."""
    inner = Bucket()
    under = Under(inner, "install-a/")

    under.put_object(BUCKET, "browser-runs/2999/03/01/run-1/transcript.jsonl", b"x", "t")

    assert list(inner.objects) == [
        (BUCKET, "install-a/browser-runs/2999/03/01/run-1/transcript.jsonl")
    ]
    assert list(under.list_objects(BUCKET, "browser-runs/")) == [
        "browser-runs/2999/03/01/run-1/transcript.jsonl"
    ]
    assert under.get_object(BUCKET, "browser-runs/2999/03/01/run-1/transcript.jsonl") == b"x"


def test_a_listing_does_not_show_another_installs_objects_or_a_key_outside_the_prefix() -> None:
    """Delete this and a bucket shared by two prefixes lists one install's recordings to the
    other's sweep, which then removes them."""
    inner = Bucket()
    inner.put_object(BUCKET, "install-a/browser-runs/2999/03/01/run-1/transcript.jsonl", b"x", "t")
    inner.put_object(BUCKET, "install-b/browser-runs/2999/03/01/run-2/transcript.jsonl", b"x", "t")

    assert list(Under(inner, "install-a/").list_objects(BUCKET, "browser-runs/")) == [
        "browser-runs/2999/03/01/run-1/transcript.jsonl"
    ]


def test_a_listing_that_ignores_the_prefix_still_shows_only_the_installs_own_keys() -> None:
    """A backend free to over-answer a prefix listing must not make another install's recordings
    this one's. Delete this and the wrapper trusts every store to filter, and a lax one shows the
    sweep a neighbour's objects to remove."""

    class Lax(Bucket):
        def list_objects(self, bucket: str, prefix: str) -> Iterator[str]:
            return iter([key for (name, key) in self.objects if name == bucket])

    inner = Lax()
    inner.put_object(BUCKET, "install-a/browser-runs/2999/03/01/run-1/transcript.jsonl", b"x", "t")
    inner.put_object(BUCKET, "install-b/browser-runs/2999/03/01/run-2/transcript.jsonl", b"x", "t")

    assert list(Under(inner, "install-a/").list_objects(BUCKET, "browser-runs/")) == [
        "browser-runs/2999/03/01/run-1/transcript.jsonl"
    ]


def test_a_delete_through_the_wrapper_reaches_the_object_under_the_prefix() -> None:
    """Delete this and the sweep reports a removal that removed nothing."""
    inner = Bucket()
    under = Under(inner, "install-a/")
    under.put_object(BUCKET, "browser-runs/x", b"x", "t")

    under.delete_object(BUCKET, "browser-runs/x")

    assert inner.objects == {}


# ------------------------------------------------------------------------------- the holds
def test_a_hold_keeps_a_run_named_by_its_session_its_asker_or_everything() -> None:
    """Each of the three ways a hold reaches a run, and a run no hold reaches. Delete this and a
    hold on a person, or on one session, leaves its recording to be removed on schedule."""
    runs = frozenset({"run-1", "run-2", "run-3"})
    askers = {"run-1": "alex", "run-2": "blake", "run-3": "casey"}

    assert runs_held(Holds(subjects=frozenset({"session:run-1"})), askers, runs) == {"run-1"}
    assert runs_held(Holds(actors=frozenset({"blake"})), askers, runs) == {"run-2"}
    assert runs_held(Holds(everything=True), askers, runs) == runs
    assert runs_held(Holds(), askers, runs) == frozenset()
    assert runs_held(Holds(actors=frozenset({"nobody"})), {}, runs) == frozenset()


def test_run_ids_are_read_from_dated_keys_only() -> None:
    """Delete this and an undated key is read as a run and held or removed as one."""
    assert runs_in(
        [
            "browser-runs/2999/03/01/run-1/transcript.jsonl",
            "browser-runs/2999/03/01/run-1/frames/a.png",
            "browser-runs/stray.txt",
        ]
    ) == frozenset({"run-1"})


# ------------------------------------------------------------------------------- the database
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_recording_sweep") as url:
        yield url


def seal(url: str, run: str) -> None:
    from tests.unit.test_browser_session_store import _open

    asyncio.run(_open(url, run, f"trace-{run}"))


def hold(
    url: str, name: str, *, subjects: str = "{}", actors: str = "{}", everything: bool = False
) -> None:
    from tests.fixtures.scratch_postgres import sql

    sql(
        url,
        "INSERT INTO obs.legal_hold (id, reason_code, subjects, actors, all_subjects, placed_at, "
        "placed_by) VALUES (%s, 'dispute', %s::varchar[], %s::varchar[], %s, %s, 'counsel')",
        name,
        subjects,
        actors,
        everything,
        STARTED - timedelta(days=1),
    )


def lift(url: str, name: str) -> None:
    from tests.fixtures.scratch_postgres import sql

    sql(
        url,
        "UPDATE obs.legal_hold SET released_at = %s, released_by = 'counsel' WHERE id = %s",
        STARTED,
        name,
    )


def swept(url: str, backend: Bucket, *, at: datetime, report_only: bool = False) -> str:
    from tests.unit.test_browser_session_store import _sessions

    async def run() -> str:
        result = await sweep(_sessions(url), backend, now=at, report_only=report_only)  # type: ignore[arg-type]
        return result.sentence()

    return asyncio.run(run())


@pytest.mark.needs_db
def test_a_run_inside_its_window_is_kept_and_one_past_it_is_removed(head: str) -> None:
    """The positive case, in both directions. Delete this and a sweep that removes everything, or
    nothing, passes the holds tests, which only look at what was kept."""
    old, young = Bucket(), Bucket()
    old_key = keep(old, "run-old")
    young_key = keep(young, "run-young")

    removed = swept(head, old, at=LONG_AFTER)
    kept = swept(head, young, at=INSIDE_THE_WINDOW)

    assert (BUCKET, old_key) not in old.objects
    assert (BUCKET, young_key) in young.objects
    assert removed == "recordings: removed 1, kept 0 under a hold, 0 with no date in their key"
    assert kept == "recordings: removed 0, kept 0 under a hold, 0 with no date in their key"


@pytest.mark.needs_db
def test_a_hold_on_the_asker_keeps_the_recording_of_a_sealed_run_past_its_window(head: str) -> None:
    """The asker comes from the sealed envelope the install holds, not from the key. Delete this and
    a hold placed on a person does not reach what their browser runs recorded."""
    from tests.unit.test_browser_session_store import ASKER

    seal(head, "run-asked")
    hold(head, "hold-asker", actors="{" + ASKER + "}")
    backend = Bucket()
    key = keep(backend, "run-asked")

    said = swept(head, backend, at=LONG_AFTER)

    assert (BUCKET, key) in backend.objects
    assert said == "recordings: removed 0, kept 1 under a hold, 0 with no date in their key"


@pytest.mark.needs_db
def test_a_hold_on_a_session_keeps_that_run_and_a_lifted_hold_keeps_nothing(head: str) -> None:
    """Delete this and a lifted hold goes on keeping recordings for ever, or a hold on one session
    keeps its neighbours too."""
    hold(head, "hold-session", subjects="{session:run-held}")
    backend = Bucket()
    held = keep(backend, "run-held")
    other = keep(backend, "run-other")

    swept(head, backend, at=LONG_AFTER)
    assert (BUCKET, held) in backend.objects
    assert (BUCKET, other) not in backend.objects

    lift(head, "hold-session")
    swept(head, backend, at=LONG_AFTER)
    assert (BUCKET, held) not in backend.objects


@pytest.mark.needs_db
def test_a_company_wide_hold_removes_nothing_and_an_undated_object_is_counted_not_removed(
    head: str,
) -> None:
    """Delete this and a hold on everything is ignored, or an object the sweep cannot date is
    removed because it looks old."""
    hold(head, "hold-all", everything=True)
    backend = Bucket()
    key = keep(backend, "run-anything")
    backend.put_object(BUCKET, "browser-runs/stray.txt", b"x", "t")

    said = swept(head, backend, at=LONG_AFTER)

    assert (BUCKET, key) in backend.objects and (
        BUCKET,
        "browser-runs/stray.txt",
    ) in backend.objects
    assert said == "recordings: removed 0, kept 1 under a hold, 1 with no date in their key"
    lift(head, "hold-all")


@pytest.mark.needs_db
def test_report_only_decides_the_same_and_removes_nothing(head: str) -> None:
    """Delete this and report-only mode deletes recordings, which is the one thing it exists to
    say it will not."""
    backend = Bucket()
    key = keep(backend, "run-report")

    said = swept(head, backend, at=LONG_AFTER, report_only=True)

    assert (BUCKET, key) in backend.objects
    assert said == "recordings: would remove 1, kept 0 under a hold, 0 with no date in their key"


def test_an_install_with_no_object_store_reports_a_sentence_and_does_not_fail() -> None:
    """With no vault there is no store. Delete this and the retention sweep raises on every install
    that has not connected one, which is most of them."""
    said = run_recording_sweep_now(
        "postgresql://nobody@localhost/none",
        now=STARTED,
        report_only=False,
        vault_address="",
        vault_token="",
    )

    assert said.startswith("recordings: not swept, no object store is connected (")


def test_the_retention_schedule_runs_the_recording_sweep_with_the_workers_vault_and_the_report_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the sweep is a function nothing on the schedule calls, which is what its
    module said of it before it was wired, and recordings stay for ever."""
    from brain.browsing import recording_sweep
    from brain.ops import schedule_runner

    seen: dict[str, object] = {}

    def fake(database_url: str, **kw: object) -> str:
        seen.update(kw, database_url=database_url)
        return "recordings: fake"

    monkeypatch.setattr(recording_sweep, "run_recording_sweep_now", fake)
    monkeypatch.setenv("BRAIN_VAULT_ADDRESS", "http://vault.invalid:8200")

    said = schedule_runner._recording_sweep(STARTED, True, "postgresql://x/y")

    assert said == "recordings: fake"
    assert seen["report_only"] is True and seen["now"] == STARTED
    assert seen["database_url"] == "postgresql://x/y"


@pytest.mark.needs_db
def test_a_hold_placed_after_the_pass_is_not_yet_in_force(head: str) -> None:
    """Delete this and a hold dated in the future keeps recordings now, which is a hold that
    reads as placed before the dispute it was placed for."""
    from tests.fixtures.scratch_postgres import sql

    sql(
        head,
        "INSERT INTO obs.legal_hold (id, reason_code, subjects, actors, all_subjects, placed_at, "
        "placed_by) VALUES ('hold-future', 'dispute', '{}'::varchar[], '{}'::varchar[], true, %s, "
        "'counsel')",
        LONG_AFTER + timedelta(days=1),
    )
    backend = Bucket()
    key = keep(backend, "run-before-the-hold")

    swept(head, backend, at=LONG_AFTER)

    assert (BUCKET, key) not in backend.objects


def test_the_retention_schedule_still_runs_the_sweep_and_the_ledger_partitions_before_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the recording line can be dropped from the retention report, or the sweep it
    sat beside can stop running, with the recordings test still green."""
    from brain.ops import schedule_runner

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class Partitions:
        def summary(self) -> str:
            return "partitions"

    monkeypatch.setattr(schedule_runner.psycopg, "connect", lambda *a, **k: Connection())
    monkeypatch.setattr(schedule_runner, "run_retention_sweep", lambda conn, **k: "swept")
    monkeypatch.setattr(
        schedule_runner, "maintain_ledger_partitions", lambda conn, **k: Partitions()
    )
    monkeypatch.setattr(schedule_runner, "_recording_sweep", lambda *a: "the recordings line")

    said = schedule_runner.retention_sweep(STARTED, False, "postgresql://x/y")

    assert said == "swept\npartitions\nthe recordings line"
