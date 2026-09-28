"""Testing a connection, the rule half: when a test is owed, what its row says, how it reads back.

`brain.ops.connector_probe` and the probe half of `brain.ops.connector_sync` decide from values
handed in, so these hand them values. The worker making the call against a database of its own is
`tests/unit/test_connector_probe_run.py`; the two routes are `tests/unit/test_connector_routes.py`.

Task ids: M27.15.8
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest

from brain.connectors.contract import HealthState
from brain.connectors.throttle import CallOutcome, limits_for
from brain.console.connector_detail import SourceStatus, status_of
from brain.ops.connectable import manifest_for
from brain.ops.connector_probe import (
    NEVER_TESTED,
    PROBE_LOCK,
    PROBE_PRINCIPAL,
    PROBE_SPACING,
    REQUEST_NAMESPACE,
    TEST_WAITING,
    TESTS_COUNTED_OVER,
    ProbeRecord,
    ProbeRequestError,
    ProbeStatus,
    ProbeTarget,
    checked_source,
    in_quota_wait,
    owed_probes,
    probe_limits,
    requests_in,
    windows_after,
)
from brain.ops.connector_sync import (
    DECLARATION_NOT_AGREED,
    KEY_DECLINED,
    NO_KEY,
    NO_VERIFIED_CEILING,
    PROBE_ANSWERED,
    PROBE_NOT_SENT_SHARE_SPENT,
    PROBE_NOT_SENT_WHILE_WAITING,
    PROBE_REFUSED_FOR_NOW,
    READ_TO_THE_END,
    SHAPE_DISAGREED,
    SOURCE_ALLOWANCE_REFUSED,
    SOURCE_UNREACHABLE,
    SYNC_PRINCIPAL,
    TESTED_ON_REQUEST,
    UNHEALTHY_AFTER_FAILURES,
    ProbeVerdict,
    SyncOutcome,
    SyncState,
    after_probe,
    sync_in_words,
    verdict_of,
)
from brain.ops.limits import check
from brain.ops.schedule_runner import RUNNERS
from brain.ops.setting_store import SettingState, checked_key
from brain.tables.connector_sync import OUTCOMES
from brain.tables.identity import one_of
from tests.unit.test_tables import migration_module

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
TENANT: Final = "11111111-2222-3333-4444-555555555555"
HOUR: Final = timedelta(hours=1)

MIGRATION: Final = Path(__file__).parents[2] / "migrations/versions/0142_connector_probe_outcome.py"


def a_state(**changed: Any) -> SyncState:
    base: dict[str, Any] = {
        "connector": "xero",
        "finished_at": NOW - HOUR,
        "outcome": SyncOutcome.SYNCED,
        "health": HealthState.OK,
        "consecutive_failures": 0,
        "next_attempt_at": NOW + HOUR,
        "detail": READ_TO_THE_END,
        "last_synced_at": NOW - HOUR,
    }
    base.update(changed)
    return SyncState(**base)


def a_test(detail: str, previous: SyncState | None, **changed: Any) -> Any:
    return after_probe(
        connector="xero",
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=2),
        detail=detail,
        interval=HOUR,
        previous=previous,
        **changed,
    )


# ------------------------------------------------------------------------ when one is owed


def test_a_request_is_owed_until_a_test_starts_after_it_and_then_it_is_answered() -> None:
    """The request is an instant, answered by the test's own row. Delete this and a request could
    be answered by a test made before it (a person replacing a key and testing sees the old key's
    result), or never answered, so the page waits for ever."""
    asked = {"xero": NOW - timedelta(minutes=5)}
    never = ProbeTarget(connector="xero", last_probe_started=None)
    before = ProbeTarget(connector="xero", last_probe_started=NOW - timedelta(minutes=10))
    after = ProbeTarget(connector="xero", last_probe_started=NOW - timedelta(minutes=5))
    assert owed_probes(asked, [never], now=NOW) == ("xero",)
    assert owed_probes(asked, [before], now=NOW) == ("xero",)
    assert owed_probes(asked, [after], now=NOW) == ()


def test_a_request_inside_the_spacing_waits_and_is_made_once_the_spacing_is_up() -> None:
    """Two tests of one connection are at least `PROBE_SPACING` apart, and a press inside it is kept
    rather than refused. Delete this and pressing the button repeatedly spends a call each time, or
    a press a few seconds after a test is lost."""
    last = NOW - PROBE_SPACING / 2
    asked = {"xero": NOW - timedelta(seconds=1)}
    target = ProbeTarget(connector="xero", last_probe_started=last)
    assert owed_probes(asked, [target], now=NOW) == ()
    assert owed_probes(asked, [target], now=last + PROBE_SPACING) == ("xero",)


def test_nothing_is_owed_on_a_request_in_the_future_or_a_source_with_no_connection() -> None:
    """Delete this and a request from a clock ahead of the worker's fires early, or a request for a
    source nobody connected is made against nothing."""
    target = ProbeTarget(connector="xero", last_probe_started=None)
    assert owed_probes({"xero": NOW + timedelta(seconds=1)}, [target], now=NOW) == ()
    assert owed_probes({"hubspot": NOW}, [target], now=NOW) == ()
    assert owed_probes({}, [target], now=NOW) == ()


def test_a_request_row_is_an_instant_with_its_zone_and_nothing_else() -> None:
    """Delete this and a row somebody typed by hand, or a naive instant, is read as a request that
    fires hours early or late."""

    def row(value: object, value_type: str = "string") -> SettingState:
        return SettingState(
            key="x", value_type=value_type, value=value, updated_by="u_admin", updated_at=NOW
        )

    found = requests_in(
        {
            "xero": row(NOW.isoformat()),
            "hubspot": row("2999-01-01T09:00:00"),
            "freshdesk": row("not a time"),
            "laravel": row(True, "boolean"),
        }
    )
    assert found == {"xero": NOW}


def test_a_request_names_a_source_and_its_key_is_a_setting_key() -> None:
    """The key segment is a source's name. Delete this and a name with a dot or a hyphen in it would
    write under a different key from the one the worker reads, or a path into another namespace."""
    assert checked_key(f"{REQUEST_NAMESPACE}.{checked_source('lark_base')}")
    for bad in ("lark-app", "xero.other", "", "Xero"):
        with pytest.raises(ProbeRequestError):
            checked_source(bad)


# ------------------------------------------------------------------------ what a row says


def test_a_test_that_answered_is_healthy_and_leaves_the_schedule_as_it_found_it() -> None:
    """Delete this and a test that works clears a failing source's backoff, or reads as a read to
    the end, which it is not."""
    failing = a_state(
        outcome=SyncOutcome.FAILED,
        health=HealthState.DOWN,
        consecutive_failures=4,
        next_attempt_at=NOW + 3 * HOUR,
        detail=KEY_DECLINED,
    )
    done = a_test(PROBE_ANSWERED, failing)
    assert done.outcome is SyncOutcome.PROBED
    assert done.health is HealthState.OK
    assert done.records == 0
    assert (done.consecutive_failures, done.next_attempt_at) == (4, NOW + 3 * HOUR)


def test_a_test_that_failed_is_judged_by_the_reads_rule_and_adds_no_failure() -> None:
    """A declined key is down at once, and a third failure in a row is down, as for a read; the
    count itself is not moved. Delete this and a failed test either says healthy or pushes the
    scheduled read further into its backoff for a button somebody pressed."""
    healthy = a_state()
    declined = a_test(KEY_DECLINED, healthy, call=CallOutcome.REJECTED)
    assert declined.health is HealthState.DOWN
    assert declined.consecutive_failures == 0
    assert declined.next_attempt_at == healthy.next_attempt_at

    once = a_test(SOURCE_UNREACHABLE, healthy, call=CallOutcome.UNAVAILABLE)
    assert once.health is HealthState.DEGRADED
    twice = a_state(outcome=SyncOutcome.FAILED, consecutive_failures=UNHEALTHY_AFTER_FAILURES - 1)
    third = a_test(SOURCE_UNREACHABLE, twice, call=CallOutcome.UNAVAILABLE)
    assert third.health is HealthState.DOWN
    assert third.consecutive_failures == UNHEALTHY_AFTER_FAILURES - 1


def test_a_test_the_source_refused_for_volume_waits_as_long_as_the_source_asked() -> None:
    """The one figure a test moves is the source's own wait. Delete this and the next scheduled
    read calls a source that has just said it has no room."""
    previous = a_state(next_attempt_at=NOW + timedelta(minutes=1))
    done = a_test(PROBE_REFUSED_FOR_NOW, previous, retry_after_seconds=3600.0)
    assert done.health is HealthState.DEGRADED
    assert done.next_attempt_at >= NOW + HOUR
    later = a_state(next_attempt_at=NOW + 5 * HOUR)
    assert a_test(PROBE_REFUSED_FOR_NOW, later, retry_after_seconds=1.0).next_attempt_at == (
        NOW + 5 * HOUR
    )


def test_a_test_that_made_no_call_keeps_the_health_it_had() -> None:
    """Nothing was learned, so nothing about the source's health moves; with no attempt before it,
    the only way to make no call is a source nothing can read, which is down. Delete this and a test
    held back for a wait reads as a verdict on the key."""
    degraded = a_state(health=HealthState.DEGRADED, outcome=SyncOutcome.QUOTA)
    assert a_test(PROBE_NOT_SENT_WHILE_WAITING, degraded).health is HealthState.DEGRADED
    assert a_test(PROBE_NOT_SENT_SHARE_SPENT, a_state()).health is HealthState.OK
    assert a_test(NO_VERIFIED_CEILING, None).health is HealthState.DOWN


def test_every_sentence_a_test_can_leave_reads_back_as_what_it_found() -> None:
    """`verdict_of` is how the page and the list know what a test found, from a constant sentence.
    Delete this and a declined key reads back as a test that worked, or a held-back test as a
    failure of the source."""
    assert verdict_of(PROBE_ANSWERED) is ProbeVerdict.ANSWERED
    assert verdict_of(PROBE_REFUSED_FOR_NOW) is ProbeVerdict.WAITING
    for held_back in (
        PROBE_NOT_SENT_WHILE_WAITING,
        PROBE_NOT_SENT_SHARE_SPENT,
        NO_VERIFIED_CEILING,
        DECLARATION_NOT_AGREED,
    ):
        assert verdict_of(held_back) is ProbeVerdict.NOT_SENT, held_back
    for failed in (KEY_DECLINED, NO_KEY, SOURCE_UNREACHABLE, SHAPE_DISAGREED, "a new sentence"):
        assert verdict_of(failed) is ProbeVerdict.FAILED, failed


def test_a_test_is_the_sources_newest_word_on_the_list_and_on_the_page() -> None:
    """A failed test is failing as a failed read is; a held-back test is not; and the page says a
    test was a test. Delete this and the list goes on saying connected after a test found the key
    refused, or a test's sentence reads as a scheduled read."""
    tested = a_state(outcome=SyncOutcome.PROBED, detail=KEY_DECLINED, health=HealthState.DOWN)
    assert status_of(True, tested) is SourceStatus.FAILING
    for fine in (PROBE_ANSWERED, PROBE_REFUSED_FOR_NOW, PROBE_NOT_SENT_WHILE_WAITING):
        assert status_of(True, a_state(outcome=SyncOutcome.PROBED, detail=fine)) is (
            SourceStatus.CONNECTED
        )
    assert sync_in_words(None, tested) == f"{TESTED_ON_REQUEST} {KEY_DECLINED}"


# ------------------------------------------------------------------ what holds a test back


def test_a_source_that_asked_to_wait_is_not_tested_and_a_failing_one_is() -> None:
    """Delete this and a test calls a source inside the wait it asked for, or, worse, a person who
    has just replaced a failing source's key cannot test it until the backoff ends."""
    quota = a_state(outcome=SyncOutcome.QUOTA, detail=SOURCE_ALLOWANCE_REFUSED)
    assert in_quota_wait(quota, now=NOW)
    assert not in_quota_wait(quota, now=quota.next_attempt_at)
    refused = a_state(outcome=SyncOutcome.PROBED, detail=PROBE_REFUSED_FOR_NOW)
    held = a_state(outcome=SyncOutcome.PROBED, detail=PROBE_NOT_SENT_WHILE_WAITING)
    assert in_quota_wait(refused, now=NOW) and in_quota_wait(held, now=NOW)
    failing = a_state(outcome=SyncOutcome.FAILED, detail=KEY_DECLINED, next_attempt_at=NOW + HOUR)
    assert not in_quota_wait(failing, now=NOW)
    assert not in_quota_wait(None, now=NOW)


def test_a_connections_own_tests_count_against_the_sources_verified_windows() -> None:
    """The one call is admitted by the source's verified ceiling at the test's own share, counting
    this connection's tests. Delete this and the limiter is handed an empty window every time,
    which admits every test however many were made."""
    limits = probe_limits(manifest_for("xero", {"tenant_id": TENANT}))
    assert {one.subject for one in limits} >= {"xero", f"{PROBE_PRINCIPAL}:xero"}
    assert check(now=NOW, limits=limits, state=windows_after((), limits)).allowed
    day = max(one.limit for one in limits if one.period == "day")
    spent = tuple(NOW - timedelta(seconds=one) for one in range(1, day + 1))
    assert not check(now=NOW, limits=limits, state=windows_after(spent, limits)).allowed


def test_the_figures_hold_against_what_they_are_for() -> None:
    """Each figure asserted against something outside itself, for CLAUDE.md's rule about a constant
    compared with itself. Delete this and a test could take the read's share of the minute, count
    fewer tests than the longest window holds, or take a lock no read takes."""
    manifest = manifest_for("xero", {"tenant_id": TENANT})
    limits = probe_limits(manifest)
    reads = limits_for(manifest, principal_id=SYNC_PRINCIPAL)
    shares = {one.subject for one in limits} - {one.subject for one in reads}
    assert shares == {f"{PROBE_PRINCIPAL}:xero"}
    assert TESTS_COUNTED_OVER.total_seconds() >= max(one.window_seconds for one in limits)
    assert PROBE_LOCK in {one.name for one in RUNNERS if one.run is not None}
    assert timedelta(seconds=30) <= PROBE_SPACING


# ------------------------------------------------------------------------ what a page reads


def test_a_page_says_waiting_until_a_test_starts_and_then_what_it_found() -> None:
    """Delete this and the page shows the previous test's result as the answer to a new press, or
    says waiting for ever."""
    asked = NOW
    older = ProbeRecord(
        started_at=NOW - HOUR, finished_at=NOW - HOUR, health="down", detail=KEY_DECLINED
    )
    newer = ProbeRecord(started_at=NOW, finished_at=NOW, health="ok", detail=PROBE_ANSWERED)
    waiting = ProbeStatus(requested_at=asked, last=older)
    assert waiting.pending and waiting.said() == TEST_WAITING
    done = ProbeStatus(requested_at=asked, last=newer)
    assert not done.pending
    assert (done.verdict, done.said()) == (ProbeVerdict.ANSWERED, PROBE_ANSWERED)
    never = ProbeStatus(requested_at=None, last=None)
    assert (never.pending, never.verdict, never.said()) == (False, None, NEVER_TESTED)


# ------------------------------------------------------------------------ the migration


def test_the_migration_widens_the_outcome_to_exactly_what_the_model_holds() -> None:
    """`0142`'s list is a copy, held here against the model's and against `0068`'s. Delete this and
    the model and the database can disagree about `probed`, which is refused at the first test on
    an install and nowhere before it."""
    module = migration_module(MIGRATION)
    assert one_of("outcome", OUTCOMES) == module.WIDENED_OUTCOMES
    assert module.SUPERSEDES == {module.NARROWER_OUTCOMES: module.WIDENED_OUTCOMES}
    assert set(OUTCOMES) == {one.value for one in SyncOutcome}
    assert "probed" in module.WIDENED_OUTCOMES and "probed" not in module.NARROWER_OUTCOMES
