"""The two questions a rehearsal asks a loaded copy beyond its row counts.

`brain.ops.drill_checks` is the code that stood where a paragraph of the drill page asked a person
to do the schema check and the permission canary by hand. The pure parts are tested without a
database. The canary is tested on a database built through every migration that ships, with the
copy damaged in each way the module claims to see inside a transaction that is rolled back, so one
module-scoped database serves every case and a damaged case cannot leak into the next. Each damage
is paired with the undamaged run, because a canary tested only by its refusals is satisfied by a
function that refuses everything.

**The record the checks feed is the one the product's own reader reads.** The last tests build a
drill record from the checks' output and hand it to `read_drills`, so the producer and the consumer
are held to each other and not each to the author's idea of the other.

The role attributes (a superuser or a `BYPASSRLS` application role) are not damaged on the server,
because a role belongs to the whole cluster and a test that altered one would alter it for every
other test database being built at the same time. They are held on the pure function that reads
them.

Task ids: M30.3.7
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import psycopg
import pytest

from brain.db import SCHEMAS
from brain.ops.backup_manifest import DRILL_SUFFIX, read_drills
from brain.ops.drill_checks import (
    APPLICATION_ROLE,
    FAST_LANE_ROLE,
    THE_COPY_WAS_NOT_REACHABLE,
    _role_findings,
    as_entries,
    main,
    permission_canary,
    run_checks,
    schema_complete,
)
from brain.ops.recovery import Check
from tests.fixtures.retirable import has_pgvector, retirable

# ------------------------------------------------------------------------------ the schema check


def test_a_copy_holding_every_schema_passes_the_schema_check() -> None:
    """The positive case, from the product's own list. Delete this and the check can be a function
    that refuses every copy and the weekly rehearsal never verifies."""
    one = schema_complete(set(SCHEMAS))
    assert one.check is Check.SCHEMA_COMPLETE
    assert one.passed


def test_a_copy_missing_a_schema_fails_the_schema_check_and_names_a_count_not_the_schema() -> None:
    """One schema gone, and the sentence counts it. Delete this and a load that stopped early
    verifies, or the report names a schema of a client's data."""
    gone = sorted(SCHEMAS)[0]
    one = schema_complete(set(SCHEMAS) - {gone})
    assert not one.passed
    assert "1 of the" in one.detail
    assert gone not in one.detail


# --------------------------------------------------------------------------------- the role reading


def test_a_role_that_can_bypass_row_level_security_is_a_finding_for_either_role() -> None:
    """The attributes `0001` gives the two roles are read, not assumed. Delete this and a copy
    whose application role came back as a superuser passes the canary."""
    bad = _role_findings([(APPLICATION_ROLE, False, True), (FAST_LANE_ROLE, True, False)])
    assert len(bad) == 2
    assert any("application role" in one for one in bad)
    assert any("fast lane role" in one for one in bad)


def test_a_role_that_does_not_exist_is_a_finding_and_two_good_roles_are_not() -> None:
    """Both directions. Delete this and either an absent role is waved through or every copy is
    refused."""
    assert _role_findings([(APPLICATION_ROLE, False, False), (FAST_LANE_ROLE, False, False)]) == []
    missing = _role_findings([(FAST_LANE_ROLE, False, False)])
    assert missing == ["the application role does not exist in the scratch copy"]


# ------------------------------------------------------------------------------ the entries layout


def test_the_entries_carry_a_bare_boolean_and_a_sentence_and_nothing_else() -> None:
    """The layout `read_drills` requires, with `passed` unquoted. Delete this and the checks can
    emit the string false, which the product refuses the whole record for."""
    entries = as_entries((schema_complete(set(SCHEMAS)),))
    assert entries == [{"check": "schema_complete", "passed": True, "detail": entries[0]["detail"]}]
    assert entries[0]["passed"] is True


def test_an_unreachable_copy_reports_both_checks_as_failed_rather_than_raising() -> None:
    """A drill of a copy that cannot be reached must still leave a record. Delete this and an
    unreachable scratch container raises, the service writes no record, and the panel goes on
    showing the earlier success."""
    ran = run_checks("postgresql://postgres@127.0.0.1:1/none")
    assert {one.check for one in ran} == {Check.SCHEMA_COMPLETE, Check.PERMISSION_CANARY}
    assert all(not one.passed and one.detail == THE_COPY_WAS_NOT_REACHABLE for one in ran)


def test_the_command_prints_the_entries_as_json_and_exits_zero_whatever_they_found(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The service reads the output and writes the record, so the exit status is not the verdict.
    Delete this and a failed canary becomes a crashed script and no record."""
    assert main(["postgresql://postgres@127.0.0.1:1/none"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [one["passed"] for one in printed] == [False, False]


def test_the_command_refuses_a_call_without_exactly_one_database_address(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No default target, so it cannot be pointed at the wrong database by omission. Delete this
    and a missing argument is read as permission to pick one."""
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err


# ------------------------------------------------------------------------------- on a real server


@pytest.fixture(scope="module")
def migrated() -> Iterator[str]:
    """Every migration that ships, in a database of this module's own."""
    with retirable("brain_test_drill_checks") as url:
        if not has_pgvector(url):
            pytest.skip("the migrations to head need pgvector, which CI's server has")
        yield url


@pytest.fixture
def conn(migrated: str) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    with psycopg.connect(migrated) as one:
        yield one


def test_a_migrated_database_passes_the_permission_canary_and_leaves_no_row_behind(
    conn: psycopg.Connection[tuple[object, ...]],
) -> None:
    """The positive case, and the canary's own row rolled back. Delete this and the canary can
    refuse everything, or leave a conversation owned by a made-up person in every copy."""
    ran = permission_canary(conn)
    assert ran.check is Check.PERMISSION_CANARY
    assert ran.passed, ran.detail
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM chat.conversation WHERE principal_id LIKE 'drill-canary%'"
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_table_that_lost_row_level_security_fails_the_canary(
    conn: psycopg.Connection[tuple[object, ...]],
) -> None:
    """Switched off in a transaction the canary then rolls back. Delete this and a copy that
    brought back every row and switched protection off verifies."""
    conn.execute("ALTER TABLE chat.conversation DISABLE ROW LEVEL SECURITY")
    ran = permission_canary(conn)
    assert not ran.passed
    assert "switched off" in ran.detail
    assert "stranger" in ran.detail


def test_a_copy_that_lost_its_policy_fails_the_canary_because_the_owner_is_refused_too(
    conn: psycopg.Connection[tuple[object, ...]],
) -> None:
    """Enabled with no policy refuses everyone. Delete this and the stranger's refusal alone
    passes a copy in which the owner can no longer see their own conversations."""
    conn.execute("DROP POLICY conversation_owner ON chat.conversation")
    ran = permission_canary(conn)
    assert not ran.passed
    assert "their own row" in ran.detail


def test_a_copy_whose_application_role_lost_its_grant_fails_the_canary(
    conn: psycopg.Connection[tuple[object, ...]],
) -> None:
    """The grants are part of what a restore may not bring back. Delete this and a copy loaded
    without its privileges verifies, and the first question anybody asks it fails."""
    conn.execute("REVOKE SELECT ON chat.conversation FROM brain_app")
    ran = permission_canary(conn)
    assert not ran.passed
    assert "InsufficientPrivilege" in ran.detail


def test_a_fast_lane_that_can_write_fails_the_canary(
    conn: psycopg.Connection[tuple[object, ...]],
) -> None:
    """`0008` granted the fast lane SELECT and nothing else. Delete this and a copy in which it can
    write verifies."""
    conn.execute("GRANT INSERT ON chat.conversation TO brain_fastlane")
    ran = permission_canary(conn)
    assert not ran.passed
    assert "fast lane" in ran.detail


def test_a_failed_canary_leaves_the_copy_as_it_found_it(
    conn: psycopg.Connection[tuple[object, ...]],
) -> None:
    """The damage in one test is gone in the next, which is the property the module-scoped
    database rests on. Delete this and a leak between cases makes the order of the tests the
    verdict."""
    conn.execute("ALTER TABLE chat.conversation DISABLE ROW LEVEL SECURITY")
    permission_canary(conn)
    again = permission_canary(conn)
    assert again.passed, again.detail


def test_the_checks_on_a_migrated_database_make_a_record_the_product_reads_as_verified(
    migrated: str,
) -> None:
    """Producer and consumer together: the checks' output, with a smoke check beside it, in a
    record `read_drills` reads. Delete this and the layout can drift from the reader's and every
    drill the service writes is an unreadable record."""
    ran = run_checks(migrated)
    document = {
        "backup_id": "database-29990101T000000Z",
        "started_at": "2999-01-02T09:00:00Z",
        "finished_at": "2999-01-02T09:41:30Z",
        "into_scratch": True,
        "checks": [
            {"check": "smoke_query", "passed": True, "detail": "every count came back"},
            *as_entries(ran),
        ],
    }
    verified, unreadable = read_drills([(f"x{DRILL_SUFFIX}", json.dumps(document))])
    assert not unreadable
    assert [one.verified for one in verified] == [True]
    assert verified[0].rto_seconds == 41 * 60 + 30
