"""What a drill's record may say, and the one thing it is not allowed to say.

The runner is a shell script on a client's own server and it is not written yet, so this file
is the format's specification as much as its test. Everything here is about one asymmetry: the
runner states what it asked and what came back, and the verdict is `verification_of`'s. A
format that let the runner write `verified` would put the definition of a verified restore in
whatever that script's author believed on the afternoon they wrote it, and the failure is not
dishonesty, it is a runner that never asked the permission canary having nothing to report.

The dates are 2999 for the reason CLAUDE.md records: a fixture with a plausible date in it is a
clock and it goes off on a morning nobody chose.

Task ids: M30.3.7, M30.3.8
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.ops.backup_manifest import (
    CHECK_REQUIRED_FIELDS,
    DRILL_REQUIRED_FIELDS,
    DRILL_SUFFIX,
    MANIFEST_SUFFIX,
    ManifestError,
    drill_from,
    read_drills,
    read_manifests,
)
from brain.ops.recovery import (
    Check,
    Drill,
    RecoveryError,
    Verification,
    last_attempt,
    last_verified_restore,
)

STARTED = "2999-06-01T03:00:00+00:00"
FINISHED = "2999-06-01T03:12:00+00:00"
NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)


def a_check(name: str, *, passed: bool = True) -> dict[str, Any]:
    """One check entry as the runner writes it: what was asked, and what came back."""
    return {
        "check": name,
        "passed": passed,
        "detail": f"asked {name} of the restored copy and it answered as expected",
    }


def a_drill(**changes: Any) -> dict[str, Any]:
    """A drill record a runner that did everything would write, so each test changes one thing."""
    document: dict[str, Any] = {
        "backup_id": "database-29990601T020000Z",
        "started_at": STARTED,
        "finished_at": FINISHED,
        "into_scratch": True,
        "checks": [a_check(one.value) for one in Check],
    }
    document.update(changes)
    return document


def named(document: dict[str, Any], name: str = "a" + DRILL_SUFFIX) -> list[tuple[str, str]]:
    """One object as the pair a bucket listing hands over."""
    return [(name, json.dumps(document))]


# --- the record a runner writes -----------------------------------------------------------


def test_a_drill_record_reads_back_as_the_attempt_it_describes() -> None:
    """**The positive case, and without it every refusal below is satisfied by a reader that
    refuses everything.**

    The fields are what a restore script actually knows: which copy it read, when it started,
    when the last check finished, that it went into a scratch target, and one entry per check.

    Delete this and a reader rejecting every drill record passes the whole file."""
    attempt = drill_from(a_drill(), where="a" + DRILL_SUFFIX)

    assert attempt.backup_id == "database-29990601T020000Z"
    assert attempt.into_scratch is True
    assert {one.check for one in attempt.checks} == set(Check)
    assert all(one.passed for one in attempt.checks)


def test_a_complete_drill_record_becomes_a_verification_carrying_the_measured_time() -> None:
    """The recovery time is the whole drill, from the restore starting to the last check
    finishing, because that is the interval before the copy could have been used. Twelve
    minutes here, and it arrives as a number rather than as a flag.

    Delete this and the one figure a rehearsal exists to produce is never read out of a
    record."""
    read, unreadable = read_drills(named(a_drill()))

    assert unreadable == ()
    assert len(read) == 1
    assert read[0].verified is True
    assert read[0].rto_seconds == 12 * 60
    assert read[0].shortfalls == ()


def test_a_record_claiming_to_be_verified_is_still_judged_on_what_it_asked() -> None:
    """**This is the whole design of the format.** A runner that writes `verified: true` and
    asked two of the three checks has stated a verdict it is not entitled to state, and the
    reader ignores the claim entirely: the field is not in `DRILL_REQUIRED_FIELDS`, nothing
    reads it, and `verification_of` decides from the checks.

    The pair is the point. The same record with the canary present and passing verifies, so
    the rule is "the checks decide" rather than "records claiming things are refused".

    Delete this and the definition of a verified restore moves into a shell script on somebody
    else's server."""
    lying = a_drill(
        verified=True,
        rto_seconds=1,
        checks=[a_check(Check.SCHEMA_COMPLETE.value), a_check(Check.SMOKE_QUERY.value)],
    )

    read, unreadable = read_drills(named(lying))

    assert unreadable == ()
    assert read[0].verified is False
    assert read[0].rto_seconds is None
    assert any("permission_canary did not run" in one for one in read[0].shortfalls)

    honest, _ = read_drills(named(a_drill(verified=False)))
    assert honest[0].verified is True


def test_a_check_the_runner_did_not_ask_arrives_as_a_shortfall_rather_than_an_absence() -> None:
    """A runner can omit a check from the file. It cannot omit it from the verdict: every
    member of `REQUIRED_CHECKS` that has no entry produces a shortfall saying it did not run,
    and a check nobody asked is not a check that passed.

    The two are reported differently on purpose. A missing canary is a misconfigured runner
    and a failed canary is a restored copy that refuses nothing, and collapsing them sends the
    same person to look at two very different things.

    Delete this and the cheapest way to make a rehearsal pass is to stop asking."""
    read, _ = read_drills(named(a_drill(checks=[])))

    assert read[0].verified is False
    assert len(read[0].shortfalls) == len(Check)
    assert all("did not run" in one for one in read[0].shortfalls)

    failed, _ = read_drills(
        named(
            a_drill(
                checks=[
                    a_check(one.value, passed=one is not Check.PERMISSION_CANARY) for one in Check
                ]
            )
        )
    )
    assert any("ran and did not pass" in one for one in failed[0].shortfalls)


# --- the refusals that catch a record which is not one -------------------------------------


def test_an_answer_written_as_a_string_is_refused_rather_than_read_for_truthiness() -> None:
    """**This is the refusal that fails in the flattering direction and it is the reason
    `_flag` exists.** A shell script writing `"passed": "false"` produces a five-character
    string, and a five-character string is true to Python, so the check that failed reads as
    the check that passed and the restore verifies.

    `into_scratch` carries the same trap with a different cost: the string "false" would make
    a drill that ran against the live database into one `Drill` accepts, and `Drill`'s whole
    reason for having that field is to refuse a runner pointed at production.

    Both directions of the integer trap are covered too, because `bool` is an `int` in Python
    and a format that accepts 1 and 0 is one a runner gets written against by accident.

    Delete this and a rehearsal that failed every check reports as verified."""
    for value in ("false", "true", 0, 1):
        with pytest.raises(ManifestError, match="true or false"):
            drill_from(
                a_drill(checks=[{**a_check("smoke_query"), "passed": value}]),
                where="a" + DRILL_SUFFIX,
            )
        with pytest.raises(ManifestError, match="true or false"):
            drill_from(a_drill(into_scratch=value), where="a" + DRILL_SUFFIX)


def test_a_drill_against_the_live_system_is_refused_and_the_file_is_named() -> None:
    """A weekly automated restore pointed at the production database is a scheduled outage.
    `brain.ops.recovery.Drill` refuses it and this is that refusal arriving with the object
    named, because a reader looking at a bucket has no other way to find which file complained.

    Delete this and a misconfigured runner's record is a row on a screen."""
    with pytest.raises(ManifestError) as caught:
        drill_from(a_drill(into_scratch=False), where="live" + DRILL_SUFFIX)

    assert "live" + DRILL_SUFFIX in str(caught.value)
    assert "scratch" in str(caught.value)


def test_every_field_the_drill_format_needs_is_named_when_it_is_missing() -> None:
    """All of them at once rather than the first, because whoever is writing the runner wants
    the list. Asserted field by field over the constants so a field added to either format
    without a refusal fails here rather than becoming optional by accident.

    Delete this and a record missing three fields reports one."""
    for field in DRILL_REQUIRED_FIELDS:
        document = a_drill()
        del document[field]
        with pytest.raises(ManifestError, match=field):
            drill_from(document, where="a" + DRILL_SUFFIX)

    with pytest.raises(ManifestError) as caught:
        drill_from({}, where="a" + DRILL_SUFFIX)
    for field in DRILL_REQUIRED_FIELDS:
        assert field in str(caught.value)

    for field in CHECK_REQUIRED_FIELDS:
        entry = a_check("smoke_query")
        del entry[field]
        with pytest.raises(ManifestError, match=field):
            drill_from(a_drill(checks=[entry]), where="a" + DRILL_SUFFIX)


def test_a_list_of_checks_written_as_one_string_is_refused() -> None:
    """A string is a `Sequence`, so a runner writing `"checks": "smoke_query"` would otherwise
    be read one character at a time into as many refusals as the name is long, and the reader
    would be told eleven things about a file with one fault.

    Delete this and one typo in a runner produces a wall of findings naming no cause."""
    with pytest.raises(ManifestError, match="checks is str"):
        drill_from(a_drill(checks="smoke_query"), where="a" + DRILL_SUFFIX)


def test_a_check_the_domain_does_not_know_is_refused() -> None:
    """A record naming `row_count` as a check is a runner written against a different
    vocabulary, and accepting it would mean a rehearsal whose verdict rests on a question
    nothing here can reason about.

    Delete this and a typo in the runner produces a drill that verifies nothing and says so
    nowhere."""
    with pytest.raises(ManifestError):
        drill_from(a_drill(checks=[a_check("row_count")]), where="a" + DRILL_SUFFIX)


def test_a_check_that_says_nothing_about_what_it_asked_is_refused_with_the_file_named() -> None:
    """A failure arriving as a red light with no bulb behind it sends somebody to read the
    runner's source. `CheckRun` refuses it and this is that refusal reaching a reader with the
    file named.

    Delete this and the domain type holds a property while the reader cannot say where it
    broke."""
    with pytest.raises(ManifestError) as caught:
        drill_from(
            a_drill(checks=[{**a_check("smoke_query"), "detail": "  "}]),
            where="mute" + DRILL_SUFFIX,
        )

    assert "mute" + DRILL_SUFFIX in str(caught.value)


def test_a_drill_that_asked_one_check_twice_is_refused() -> None:
    """Which result the verdict uses would otherwise depend on the order the entries happen to
    be in, so a runner that retried the canary and recorded both attempts would verify or not
    according to how a bucket listing sorted.

    Delete this and a rehearsal's verdict depends on file order."""
    with pytest.raises(ManifestError, match="same check twice"):
        drill_from(
            a_drill(checks=[a_check("smoke_query"), a_check("smoke_query", passed=False)]),
            where="a" + DRILL_SUFFIX,
        )


def test_a_check_entry_that_is_not_an_object_is_refused() -> None:
    """A runner writing `"checks": ["smoke_query"]` has written the names rather than the
    answers, which is a record with no answers in it at all.

    Delete this and a list of check names reads as a list of checks that were asked."""
    with pytest.raises(ManifestError, match="a check is an object"):
        drill_from(a_drill(checks=["smoke_query"]), where="a" + DRILL_SUFFIX)


# --- reading a bucket ----------------------------------------------------------------------


def test_the_two_readers_do_not_pick_up_each_others_files() -> None:
    """**The property is the relation between the two suffixes, not their spellings.** A
    reader selects objects by the end of the name, so one suffix ending in the other would
    have every drill record handed to `backup_from` and a healthy bucket would report one
    unreadable file per rehearsal that ran.

    Asserted against each other rather than against their values, which is what stops the two
    constants moving together in a way both sides of a comparison agree with.

    Delete this and renaming one suffix silently turns the other reader's findings into
    noise."""
    assert not MANIFEST_SUFFIX.endswith(DRILL_SUFFIX)
    assert not DRILL_SUFFIX.endswith(MANIFEST_SUFFIX)

    copy = {
        "backup_id": "database-29990601T020000Z",
        "coverage": "database",
        "method": "full",
        "destination": "s3://backups",
        "started_at": "2999-06-01T02:00:00+00:00",
        "finished_at": "2999-06-01T02:04:00+00:00",
        "recoverable_to": "2999-06-01T02:04:00+00:00",
        "size_bytes": 4_194_304,
    }
    both = [
        ("one" + MANIFEST_SUFFIX, json.dumps(copy)),
        ("one" + DRILL_SUFFIX, json.dumps(a_drill())),
        ("one.dump", "not json and not meant to be"),
    ]

    copies, copy_complaints = read_manifests(both)
    drills, drill_complaints = read_drills(both)

    assert len(copies) == 1
    assert copy_complaints == ()
    assert len(drills) == 1
    assert drill_complaints == ()


def test_a_drill_record_that_cannot_be_read_is_named_rather_than_skipped() -> None:
    """**The rehearsal that fell over is the one whose record is truncated**, and it is the one
    a panel most needs, because dropping it leaves an older success standing as the newest
    evidence. That is the single direction in which losing a record makes a recovery screen
    look better than the truth.

    Delete this and a bucket holding a broken record of last night's failure reports last
    month's success."""
    objects = [
        ("good" + DRILL_SUFFIX, json.dumps(a_drill())),
        ("truncated" + DRILL_SUFFIX, '{"backup_id": "database-2999'),
        ("wrong-shape" + DRILL_SUFFIX, json.dumps([1, 2, 3])),
        ("empty-copy" + DRILL_SUFFIX, json.dumps(a_drill(into_scratch=False))),
    ]

    read, unreadable = read_drills(objects)

    assert len(read) == 1
    assert {one.where for one in unreadable} == {
        "truncated" + DRILL_SUFFIX,
        "wrong-shape" + DRILL_SUFFIX,
        "empty-copy" + DRILL_SUFFIX,
    }
    assert any("not JSON" in one.why for one in unreadable)
    assert any("a drill record is an object" in one.why for one in unreadable)
    assert any("scratch" in one.why for one in unreadable)


def test_a_bucket_of_drill_records_reads_back_newest_last() -> None:
    """Matching `read_manifests`, so a caller reading a bucket does not have to remember which
    of two functions sorts which way. The identifier breaks ties, so two records written in one
    second cannot swap places between two readings and make a panel change its answer with
    nothing having happened.

    Delete this and the newest rehearsal is whichever name sorted last."""
    older = a_drill(
        backup_id="database-29990525T020000Z",
        started_at="2999-05-25T03:00:00+00:00",
        finished_at="2999-05-25T03:10:00+00:00",
    )
    objects = [
        ("newer" + DRILL_SUFFIX, json.dumps(a_drill())),
        ("older" + DRILL_SUFFIX, json.dumps(older)),
    ]

    read, _ = read_drills(objects)

    assert [one.backup_id for one in read] == [
        "database-29990525T020000Z",
        "database-29990601T020000Z",
    ]


# --- the two questions a console asks ------------------------------------------------------


def _verification(*, started: datetime, passed: bool, backup_id: str = "b1") -> Verification:
    """One rehearsal outcome, built from a drill rather than asserted, so the producer is run."""
    from brain.ops.recovery import CheckRun, verification_of

    return verification_of(
        Drill(
            backup_id=backup_id,
            started_at=started,
            finished_at=started + timedelta(minutes=10),
            into_scratch=True,
            checks=tuple(
                CheckRun(check=one, passed=passed, detail=f"{one.value} was asked") for one in Check
            ),
        )
    )


def test_a_later_failure_leaves_the_earlier_success_where_it_is_and_takes_the_newest_word() -> None:
    """**The two questions a recovery screen has to ask, and reading one as the other is the
    defect.** `last_verified_restore` must not advance because somebody tried and failed, which
    means it goes on saying Monday after Tuesday's rehearsal failed. On Tuesday evening no copy
    this install holds is known to be readable, and a screen built on that function alone
    renders a date and a tick.

    Delete this and the field and the verdict collapse into one, in the reassuring direction,
    on the evening of a failure."""
    monday = _verification(started=NOW - timedelta(days=2), passed=True, backup_id="b1")
    tuesday = _verification(started=NOW - timedelta(days=1), passed=False, backup_id="b2")
    both = [monday, tuesday]

    assert last_verified_restore(both) is monday
    newest = last_attempt(both)
    assert newest is tuesday
    assert newest is not None
    assert newest.verified is False


def test_the_newest_attempt_on_an_install_that_has_never_rehearsed_is_nothing() -> None:
    """`None` rather than raising, because no rehearsal at all is the state this repository is
    actually in and it is an answer a caller has to render rather than an error. The positive
    case sits beside it so the function is not satisfied by one that always answers nothing.

    Delete this and the commonest state of this screen is an exception."""
    assert last_attempt([]) is None

    only = _verification(started=NOW - timedelta(days=1), passed=True)
    assert last_attempt([only]) is only


def test_two_attempts_recorded_at_one_instant_do_not_swap_places() -> None:
    """A bucket listing's order is the object store's business. Both functions break the tie on
    the identifier, so a panel asked twice about the same bucket gives the same answer.

    Delete this and a screen changes its verdict between two refreshes with nothing having
    happened."""
    at = NOW - timedelta(days=1)
    first = _verification(started=at, passed=True, backup_id="aaa")
    second = _verification(started=at, passed=True, backup_id="zzz")

    assert last_attempt([first, second]) is second
    assert last_attempt([second, first]) is second
    assert last_verified_restore([first, second]) is second


def test_a_drill_recorded_at_a_naive_instant_is_refused_with_the_file_named() -> None:
    """A record written by a host in local time makes every interval computed from it wrong by
    whatever that machine's offset is, which on a server in another timezone is hours in the
    direction nobody checks.

    `Drill` is what refuses it, and this is that refusal reaching a reader with the file and
    the field named.

    Delete this and the property is held by a domain type that does not know this module
    exists."""
    with pytest.raises(ManifestError) as caught:
        drill_from(a_drill(started_at="2999-06-01T03:00:00"), where="naive" + DRILL_SUFFIX)

    assert "naive" + DRILL_SUFFIX in str(caught.value)
    assert "started_at" in str(caught.value)


def test_a_drill_that_finished_before_it_started_is_refused() -> None:
    """A negative recovery time is a clock that moved, and a rehearsal reporting one would put
    a figure on a service level statement that no restore has ever taken.

    Delete this and a record written across a clock correction reads as an instant recovery."""
    with pytest.raises(ManifestError, match="finished before it started"):
        drill_from(a_drill(finished_at="2999-06-01T02:00:00+00:00"), where="a" + DRILL_SUFFIX)

    with pytest.raises(RecoveryError):
        Drill(
            backup_id="b1",
            started_at=NOW,
            finished_at=NOW - timedelta(seconds=1),
            into_scratch=True,
            checks=(),
        )
