"""What a manifest has to say before it counts as a copy, and what happens when it cannot.

The dates are 2999 for the reason CLAUDE.md records: a fixture with a plausible date in it is
a clock and it goes off on a morning nobody chose.

Task ids: M30.3.1, M30.3.2
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from brain.ops.backup_manifest import (
    MANIFEST_SUFFIX,
    REQUIRED_FIELDS,
    ManifestError,
    Unreadable,
    backup_from,
    manifest_gaps,
    read_manifests,
)
from brain.ops.recovery import Coverage, Method

STARTED = "2999-06-01T02:00:00+00:00"
FINISHED = "2999-06-01T02:04:00+00:00"


def a_manifest(**changes: Any) -> dict[str, Any]:
    """A manifest the taker would write, so each refusal below changes exactly one thing."""
    document: dict[str, Any] = {
        "backup_id": "database-29990601T020000Z",
        "coverage": "database",
        "method": "full",
        "destination": "s3://backups",
        "started_at": STARTED,
        "finished_at": FINISHED,
        "recoverable_to": FINISHED,
        "size_bytes": 4_194_304,
    }
    document.update(changes)
    return document


def named(document: dict[str, Any], name: str = "a" + MANIFEST_SUFFIX) -> list[tuple[str, str]]:
    """One object as the pair a bucket listing hands over."""
    return [(name, json.dumps(document))]


# --- a manifest that describes a copy -----------------------------------------------------


def test_a_manifest_the_taker_wrote_reads_back_as_the_copy_it_describes() -> None:
    """**The positive case, and without it every refusal below is satisfied by a reader that
    refuses everything.**

    The fields are the ones a dump command actually knows: when it began, when it finished, how
    many bytes it wrote and where it went. Nothing here is inferred from another field.

    Delete this and a reader that rejects every manifest passes the whole file."""
    copy = backup_from(a_manifest(), where="a.manifest.json")

    assert copy.coverage is Coverage.DATABASE
    assert copy.method is Method.FULL
    assert copy.size_bytes == 4_194_304
    assert copy.recoverable_to == copy.finished_at


def test_every_field_the_format_needs_is_named_when_it_is_missing() -> None:
    """All of them at once rather than the first, because a taker fixing a manifest format
    wants the list rather than four runs of one error each.

    Asserted field by field over `REQUIRED_FIELDS` so a field added to the format without a
    refusal fails here rather than being optional by accident.

    Delete this and a manifest missing three fields reports one."""
    for field in REQUIRED_FIELDS:
        document = a_manifest()
        del document[field]
        with pytest.raises(ManifestError, match=field):
            backup_from(document, where="a.manifest.json")

    bare: dict[str, Any] = {}
    with pytest.raises(ManifestError) as caught:
        backup_from(bare, where="a.manifest.json")
    for field in REQUIRED_FIELDS:
        assert field in str(caught.value)


# --- the refusals that catch a copy that is not one ---------------------------------------


def test_a_dump_that_wrote_nothing_is_refused_rather_than_recorded() -> None:
    """**The commonest silent backup failure there is.** A command that exits zero and produces
    an empty file shows in every listing as a name and a timestamp, which is what a panel
    renders.

    `brain.ops.recovery.Backup` is what refuses it and this test is that its message reaches a
    reader with the file named, because a reader looking at forty objects has no other way to
    find which one produced the complaint.

    Delete this and an empty copy is a healthy row on a screen."""
    with pytest.raises(ManifestError, match="bytes"):
        backup_from(a_manifest(size_bytes=0), where="empty.manifest.json")


def test_a_size_of_true_is_not_a_byte_count() -> None:
    """`bool` is an `int` in Python, so `True` passes an isinstance check and then passes the
    "at least one byte" rule as the integer 1. A backup of one byte reported as healthy is
    precisely the failure the size field exists to catch, arriving through the type system.

    This is the same defect the mutation audit has found repeatedly in this repository: `True`
    passing as a span offset and as a score.

    Delete this and a manifest written by a script that quoted a shell test rather than a
    number reads as a one-byte backup."""
    with pytest.raises(ManifestError, match="byte count is an integer"):
        backup_from(a_manifest(size_bytes=True), where="a.manifest.json")


def test_an_instant_with_no_offset_is_refused_and_the_file_is_named() -> None:
    """A naive timestamp makes the exposure computed from it wrong by whatever the taker's
    clock is set to, which on a server in another timezone is hours in the direction nobody
    checks.

    **This test is why there is no naive check in `_instant` any more.** It was written to
    show that the reader names the file, and the mutation run showed the duplicate check could
    be deleted with nothing failing: `backup_from` catches the domain type's refusal and
    re-raises it prefixed with the file, so `Backup`'s message already arrives naming both.
    The guard could not fire and it is gone; what this pins is the property, which is that a
    manifest from a host in local time is refused and that the reader is told which file and
    which field.

    Delete this and the property is held by a domain type that does not know this module
    exists."""
    with pytest.raises(ManifestError) as caught:
        backup_from(a_manifest(started_at="2999-06-01T02:00:00"), where="naive.manifest.json")

    assert "naive.manifest.json" in str(caught.value), "the reader has to know which file"
    assert "started_at" in str(caught.value), "and which field"

    with pytest.raises(ManifestError) as finished:
        backup_from(
            a_manifest(finished_at="2999-06-01T02:04:00", recoverable_to="2999-06-01T02:04:00"),
            where="also-naive.manifest.json",
        )

    assert "finished_at" in str(finished.value), "every instant, not only the first"


def test_a_full_copy_may_not_claim_to_restore_past_the_moment_it_finished() -> None:
    """Only continuous archiving can restore to a moment after the run that produced it,
    because segments keep arriving. A full copy claiming it is a copy claiming to contain
    writes that happened after it stopped reading.

    The positive case is beside it: the same claim from a continuous copy is accepted, so the
    rule is not "later is always wrong".

    Delete this and a nightly dump can be recorded as having no exposure at all."""
    later = "2999-06-01T03:00:00+00:00"

    with pytest.raises(ManifestError, match="restore past"):
        backup_from(a_manifest(recoverable_to=later), where="a.manifest.json")

    continuous = backup_from(
        a_manifest(method="continuous_wal", recoverable_to=later), where="a.manifest.json"
    )
    assert continuous.recoverable_to > continuous.finished_at


def test_a_coverage_or_method_the_domain_does_not_know_is_refused() -> None:
    """A manifest naming `daily` as a method is a taker written against a different vocabulary,
    and accepting it would mean a copy in the bucket that no schedule check can reason about.

    Delete this and a typo in the taker produces copies that are invisible to every exposure
    calculation."""
    with pytest.raises(ManifestError):
        backup_from(a_manifest(method="nightly"), where="a.manifest.json")
    with pytest.raises(ManifestError):
        backup_from(a_manifest(coverage="everything"), where="a.manifest.json")


def test_a_copy_with_nowhere_to_have_gone_is_refused() -> None:
    """`destination` is what a person reads when they go looking for the artefact. A blank one
    is a manifest describing a copy nobody can find.

    Delete this and a manifest can record that something was copied to nowhere."""
    with pytest.raises(ManifestError, match="destination"):
        backup_from(a_manifest(destination="   "), where="a.manifest.json")


# --- reading a bucket ---------------------------------------------------------------------


def test_a_bucket_of_manifests_reads_back_newest_last() -> None:
    """Sorted by the moment each copy can restore to rather than by name or by finish time,
    which is the same distinction `brain.ops.recovery.latest` exists for: last week's full plus
    this minute's archived segments reaches further than yesterday's incremental.

    Delete this and a caller taking the end of the list gets whichever name sorted last."""
    older = a_manifest(
        backup_id="database-29990530T020000Z",
        started_at="2999-05-30T02:00:00+00:00",
        finished_at="2999-05-30T02:03:00+00:00",
        recoverable_to="2999-05-30T02:03:00+00:00",
    )
    objects = [
        ("newer" + MANIFEST_SUFFIX, json.dumps(a_manifest())),
        ("older" + MANIFEST_SUFFIX, json.dumps(older)),
    ]

    read, unreadable = read_manifests(objects)

    assert unreadable == ()
    assert [one.backup_id for one in read] == [
        "database-29990530T020000Z",
        "database-29990601T020000Z",
    ]


def test_the_artefacts_themselves_are_not_read_as_manifests() -> None:
    """The bucket holds the dumps as well, and a multi-gigabyte dump handed to a JSON parser is
    an unreadable-manifest finding for every copy that worked.

    Delete this and a healthy bucket reports one failure per successful backup."""
    objects = [
        ("database-29990601T020000Z.dump", "not json and not meant to be"),
        ("a" + MANIFEST_SUFFIX, json.dumps(a_manifest())),
    ]

    read, unreadable = read_manifests(objects)

    assert len(read) == 1
    assert unreadable == ()


def test_a_manifest_that_cannot_be_read_is_named_rather_than_skipped() -> None:
    """**The run that failed halfway is the run whose manifest is truncated**, so silently
    skipping what cannot be parsed drops exactly the evidence somebody is looking for and
    reports a healthy count.

    Both halves come from one call, which is what stops a caller taking the count without the
    complaint.

    Delete this and a bucket with six good manifests and one broken one answers "six"."""
    objects = [
        ("good" + MANIFEST_SUFFIX, json.dumps(a_manifest())),
        ("truncated" + MANIFEST_SUFFIX, '{"backup_id": "database-2999'),
        ("wrong-shape" + MANIFEST_SUFFIX, json.dumps([1, 2, 3])),
    ]

    read, unreadable = read_manifests(objects)

    assert len(read) == 1
    assert {one.where for one in unreadable} == {
        "truncated" + MANIFEST_SUFFIX,
        "wrong-shape" + MANIFEST_SUFFIX,
    }
    assert any("not JSON" in one.why for one in unreadable)
    assert any("a manifest is an object" in one.why for one in unreadable)


def test_a_manifest_that_parses_and_describes_no_copy_is_reported_with_the_others() -> None:
    """**A mutation survived here and this is what it found.**

    The test above breaks manifests at the JSON layer, so the branch that catches a file which
    parses cleanly and is then refused as a copy was never executed. Swallowing that one
    silently is the worse of the two failures: a truncated file is obviously broken, and a
    well-formed manifest describing an empty backup is the one a panel would otherwise count.

    Delete this and a bucket of manifests describing zero-byte copies reports a healthy
    count."""
    objects = [
        ("good" + MANIFEST_SUFFIX, json.dumps(a_manifest())),
        ("empty-copy" + MANIFEST_SUFFIX, json.dumps(a_manifest(size_bytes=0))),
        (
            "no-method" + MANIFEST_SUFFIX,
            json.dumps({k: v for k, v in a_manifest().items() if k != "method"}),
        ),
    ]

    read, unreadable = read_manifests(objects)

    assert len(read) == 1
    assert {one.where for one in unreadable} == {
        "empty-copy" + MANIFEST_SUFFIX,
        "no-method" + MANIFEST_SUFFIX,
    }
    assert any("bytes" in one.why for one in unreadable)
    assert any("method" in one.why for one in unreadable)


def test_an_unreadable_manifest_that_does_not_say_why_cannot_be_constructed() -> None:
    """A finding with no reason is a count wearing a type, and this whole module exists because
    a count is what a bucket already gives you.

    Delete this and the complaint half can be filled with blanks."""
    with pytest.raises(ManifestError, match="does not say why"):
        Unreadable(where="a.manifest.json", why="  ")

    with pytest.raises(ManifestError, match="cannot be gone and looked at"):
        Unreadable(where="", why="something")


# --- what a person is told ----------------------------------------------------------------


def test_every_unreadable_file_is_reported_in_name_order() -> None:
    """Name order rather than discovery order, because a bucket listing's order is the object
    store's business and a report that changes order between two runs looks like it changed.

    Delete this and the report reads differently on each call for the same bucket."""
    found = manifest_gaps(
        [],
        [
            Unreadable(where="z.manifest.json", why="b"),
            Unreadable(where="a.manifest.json", why="c"),
        ],
    )

    assert found == ("a.manifest.json: c", "z.manifest.json: b")


def test_a_coverage_with_no_readable_copy_at_all_is_a_finding_a_count_cannot_make() -> None:
    """**Forty database dumps and no configuration snapshot is forty copies and a whole missing
    coverage**, and forty is the number a panel shows.

    Asked about rather than assumed: `expected` defaults to nothing so this reports on what a
    caller asked about instead of inventing a backup policy here, which is
    `brain.ops.recovery.SCHEDULE`'s question.

    Delete this and an install copying only its database reports as fully covered."""
    read, _ = read_manifests(named(a_manifest()))

    assert manifest_gaps(read, [], expected=[Coverage.DATABASE]) == ()

    found = manifest_gaps(read, [], expected=[Coverage.DATABASE, Coverage.CONFIGURATION])

    assert len(found) == 1
    assert "configuration" in found[0]


def test_asking_about_nothing_reports_nothing_rather_than_every_coverage() -> None:
    """The default. A caller that has not said what it expects has not made a claim about what
    ought to exist, and reporting all three coverages as missing would make the default a
    policy this module invented.

    Delete this and every caller gets three findings it did not ask for."""
    assert manifest_gaps([], []) == ()
