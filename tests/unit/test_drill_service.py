"""When a rehearsal is owed and what its record may say, decided in Python and not in shell.

The server's drill service is a shell script and the two judgements it must not make itself are
tested here: the plan, from a listing and a clock, and the record, which is built and then read
back through the reader the product uses. The dates are 2999 for the reason CLAUDE.md records.

**The plan's boundary is tested at the second.** A rehearsal exactly seven days old is owed and one
a second younger is not, because the case that is always wrong is the one on the line.

Task ids: M30.3.6, M30.3.8
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.ops.backup_manifest import DRILL_SUFFIX, MANIFEST_SUFFIX, read_drills
from brain.ops.drill_service import (
    REQUEST_KEY,
    Listed,
    Why,
    main,
    newest_complete_copy,
    parse_listing,
    plan,
    record_document,
)

NOW = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)
OLD = "database-29990601T020000Z"
NEW = "database-29990614T020000Z"


def at(hours_ago: float) -> datetime:
    return NOW - timedelta(hours=hours_ago)


def pair(copy: str, suffix: str = ".dump") -> list[Listed]:
    return [Listed(f"{copy}{suffix}", at(10)), Listed(f"{copy}{MANIFEST_SUFFIX}", at(10))]


# ----------------------------------------------------------------------------------- the listing


def test_a_listing_is_read_as_a_key_a_tab_and_an_instant() -> None:
    """The shape `aws s3api list-objects-v2 --output text` prints. Delete this and the parser can
    drift from the script's query and every plan is a refusal on the server."""
    rows = parse_listing(
        f"{OLD}.dump\t2999-06-01T02:04:10+00:00\n\n{OLD}{MANIFEST_SUFFIX}\t2999-06-01T02:04:11Z\n"
    )
    assert [one.key for one in rows] == [f"{OLD}.dump", f"{OLD}{MANIFEST_SUFFIX}"]
    assert rows[1].modified == datetime(2999, 6, 1, 2, 4, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    "line",
    ["just-a-key", "key\t", "\t2999-06-01T02:00:00Z", "key\tyesterday", "key\t2999-06-01T02:00:00"],
)
def test_a_line_that_is_not_a_key_and_a_time_with_an_offset_is_refused(line: str) -> None:
    """Refused and not skipped. Delete this and a mangled listing reads as a bucket with fewer
    copies, and an older one is rehearsed."""
    with pytest.raises(ValueError):
        parse_listing(line)


# ------------------------------------------------------------------------------------- the copy


def test_the_newest_copy_with_both_its_objects_is_the_one_to_rehearse() -> None:
    """Newest by identifier, complete only. Delete this and the rehearsal reads an older copy than
    the one the panel calls the newest, or a copy whose manifest never arrived."""
    both = [*pair(OLD), *pair(NEW)]
    assert newest_complete_copy(both) == NEW
    manifest_only = [*pair(OLD), Listed(f"{NEW}{MANIFEST_SUFFIX}", at(1))]
    assert newest_complete_copy(manifest_only) == OLD
    artefact_only = [*pair(OLD), Listed(f"{NEW}.dump", at(1))]
    assert newest_complete_copy(artefact_only) == OLD


def test_an_encrypted_copy_counts_as_a_copy_and_so_does_nothing_else() -> None:
    """The client-held key's artefact is `.dump.enc`. Delete this and an install that encrypts its
    copies is never rehearsed, or a drill record or the request is mistaken for a copy."""
    assert newest_complete_copy(pair(NEW, ".dump.enc")) == NEW
    others = [
        Listed(f"{NEW}{DRILL_SUFFIX}", at(1)),
        Listed(REQUEST_KEY, at(1)),
        Listed(f"{NEW}{MANIFEST_SUFFIX}", at(1)),
        Listed("object-store-20990101.snapshot", at(1)),
    ]
    assert newest_complete_copy(others) is None


# --------------------------------------------------------------------------------------- the plan


def test_nothing_is_rehearsed_while_nothing_has_been_copied_even_when_one_is_requested() -> None:
    """No copy, no rehearsal, whoever asks. Delete this and a request on a fresh install starts a
    scratch container with nothing to load."""
    asked = plan([Listed(REQUEST_KEY, at(1))], now=NOW)
    assert (asked.run, asked.why) == (False, Why.NOTHING_COPIED)
    assert plan([], now=NOW).line() == "skip nothing-copied"


def test_a_request_outranks_a_recent_rehearsal() -> None:
    """The button works the day after a drill. Delete this and a person who fixed what a failed
    drill named waits a week to find out."""
    listing = [*pair(NEW), Listed(f"{NEW}{DRILL_SUFFIX}", at(1)), Listed(REQUEST_KEY, at(1))]
    chosen = plan(listing, now=NOW)
    assert chosen.line() == f"run {NEW} requested"


def test_an_install_that_has_never_rehearsed_is_owed_one() -> None:
    """None is due, as `drill_due` says. Delete this and a system whose copies have never been read
    reads as between rehearsals for ever."""
    assert plan(pair(NEW), now=NOW).line() == f"run {NEW} never"


def test_a_rehearsal_exactly_a_week_old_is_owed_and_one_a_second_younger_is_not() -> None:
    """The line itself. Delete this and the comparison can be off by the boundary and the weekly
    rehearsal falls to every eighth day."""
    week = timedelta(days=7)
    on_the_line = [*pair(NEW), Listed(f"{OLD}{DRILL_SUFFIX}", NOW - week)]
    assert plan(on_the_line, now=NOW).why == Why.WEEKLY
    just_inside = [*pair(NEW), Listed(f"{OLD}{DRILL_SUFFIX}", NOW - week + timedelta(seconds=1))]
    held_back = plan(just_inside, now=NOW)
    assert (held_back.run, held_back.why) == (False, Why.NOT_DUE)


def test_due_is_measured_from_the_last_attempt_so_a_failing_drill_is_not_retried_every_poll() -> (
    None
):
    """A failed attempt a minute ago does not start another. Delete this and a copy that cannot be
    read loads the whole database into a scratch container on every poll."""
    listing = [*pair(NEW), Listed(f"{NEW}{DRILL_SUFFIX}", NOW - timedelta(minutes=1))]
    assert not plan(listing, now=NOW).run


def test_the_newest_of_several_attempts_decides() -> None:
    """Not the first listed. Delete this and an old record listed first makes every poll owed."""
    listing = [
        *pair(NEW),
        Listed(f"{OLD}{DRILL_SUFFIX}", NOW - timedelta(days=30)),
        Listed(f"{NEW}{DRILL_SUFFIX}", NOW - timedelta(days=1)),
    ]
    assert not plan(listing, now=NOW).run


def test_a_clock_with_no_offset_is_refused() -> None:
    """Delete this and the schedule is decided at the host's offset, a day early or late."""
    with pytest.raises(ValueError):
        plan(pair(NEW), now=datetime(2999, 6, 15, 12, 0))


# -------------------------------------------------------------------------------------- the record

PASSED = {"check": "schema_complete", "passed": True, "detail": "all schemas are present"}
CANARY = {"check": "permission_canary", "passed": True, "detail": "the stranger was refused"}


def a_record(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "backup_id": NEW,
        "started_at": datetime(2999, 6, 15, 9, 0, tzinfo=UTC),
        "finished_at": datetime(2999, 6, 15, 9, 41, 30, tzinfo=UTC),
        "smoke_passed": True,
        "smoke_detail": "every count came back",
        "checks": [PASSED, CANARY],
    }
    arguments.update(overrides)
    return record_document(**arguments)  # type: ignore[arg-type]


def test_a_record_the_service_writes_is_read_by_the_product_as_verified_with_a_recovery_time() -> (
    None
):
    """Producer and consumer together. Delete this and the layout can drift from the reader's, and
    every rehearsal the server runs is an unreadable file on the Recovery screen."""
    document = a_record()
    verified, unreadable = read_drills([(f"{NEW}{DRILL_SUFFIX}", json.dumps(document))])
    assert not unreadable
    assert [one.verified for one in verified] == [True]
    assert verified[0].rto_seconds == 41 * 60 + 30


def test_a_failed_check_is_written_as_failed_and_the_product_reads_no_recovery_time() -> None:
    """The verdict is the product's. Delete this and a failed canary is recorded as a pass because
    the script wrote the flag."""
    bad = {**CANARY, "passed": False, "detail": "the stranger was shown a row"}
    document = a_record(checks=[PASSED, bad])
    verified, _ = read_drills([(f"{NEW}{DRILL_SUFFIX}", json.dumps(document))])
    assert [one.verified for one in verified] == [False]
    assert verified[0].rto_seconds is None


def test_a_record_with_no_permission_canary_is_written_and_read_as_not_verified() -> None:
    """A check nobody asked is a shortfall, not an absence. Delete this and a service that skipped
    the canary writes a record that verifies."""
    document = a_record(checks=[PASSED])
    verified, _ = read_drills([(f"{NEW}{DRILL_SUFFIX}", json.dumps(document))])
    assert [one.verified for one in verified] == [False]


def test_a_check_written_as_a_string_is_refused_before_it_is_written() -> None:
    """The reader refuses the string false, and so does the writer. Delete this and the refusal
    happens weeks later on a screen instead of now on the server."""
    from brain.ops.backup_manifest import ManifestError

    with pytest.raises(ManifestError):
        a_record(checks=[{**PASSED, "passed": "false"}, CANARY])


def test_the_record_always_says_it_was_loaded_into_a_scratch_database() -> None:
    """The field the drill value class refuses a live target by. Delete this and the record can
    omit it and the reader reports the file as unreadable."""
    assert a_record()["into_scratch"] is True


# ----------------------------------------------------------------------------- the two commands


def test_the_plan_command_reads_a_listing_on_stdin_and_prints_one_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The contract the script depends on. Delete this and a change to the line breaks the script
    on a server nobody is watching."""
    stdin = f"{NEW}.dump\t2999-06-14T02:00:00Z\n{NEW}{MANIFEST_SUFFIX}\t2999-06-14T02:00:00Z\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    assert main(["plan", "--now", "2999-06-15T12:00:00Z"]) == 0
    assert capsys.readouterr().out.strip() == f"run {NEW} never"


def test_the_plan_command_refuses_a_mangled_listing_with_status_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refusal is a distinct status. Delete this and the script cannot tell a refusal from a
    plan."""
    monkeypatch.setattr("sys.stdin", io.StringIO("not a listing"))
    assert main(["plan", "--now", "2999-06-15T12:00:00Z"]) == 2
    assert "refused" in capsys.readouterr().err


def test_the_record_command_prints_json_the_product_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second contract. Delete this and the script's flags drift from the module's."""
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps([PASSED, CANARY]), encoding="utf-8", newline="\n")
    code = main(
        [
            "record",
            "--backup-id",
            NEW,
            "--started",
            "2999-06-15T09:00:00Z",
            "--finished",
            "2999-06-15T09:41:30Z",
            "--smoke",
            "passed",
            "--smoke-detail",
            "every count came back",
            "--checks-file",
            str(checks),
        ]
    )
    assert code == 0
    verified, unreadable = read_drills([(f"{NEW}{DRILL_SUFFIX}", capsys.readouterr().out)])
    assert not unreadable and verified[0].verified


def test_the_record_command_refuses_a_checks_file_that_is_not_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing file is a refusal and no record. Delete this and a crashed canary step writes a
    record with no checks, which the product reads as a drill that skipped them."""
    code = main(
        [
            "record",
            "--backup-id",
            NEW,
            "--started",
            "2999-06-15T09:00:00Z",
            "--finished",
            "2999-06-15T09:41:30Z",
            "--smoke",
            "failed",
            "--smoke-detail",
            "nothing loaded",
            "--checks-file",
            str(tmp_path / "absent.json"),
        ]
    )
    assert code == 2
    assert "refused" in capsys.readouterr().err
