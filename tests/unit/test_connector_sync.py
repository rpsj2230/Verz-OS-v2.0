"""Whether a connected source may be read, what is kept from a row, and what an attempt costs.

`brain.ops.connector_sync` holds no connection, so every property here is asserted without one, and
the rows are built from the recorded Xero and HubSpot answers in `tests/fixtures/cassettes.py`
rather than from a hand-written value of what a projection should be: a test that built the record
the function produces would test nothing about the function. What a run writes and who can read it
is `tests/unit/test_connector_sync_run.py`.

**Every refusal has a sibling that reads.** A plan that refused everything would pass every
refusal test here and read nothing on any install, which is the state this module ended.

Task ids: M42.6.5
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

from brain.connectors import hubspot, xero
from brain.connectors.contract import HealthState
from brain.connectors.manifest import ProjectedEntity, manifest_digest
from brain.connectors.projection import MISSED_REFRESHES_BEFORE_STALE, ProjectedRecord
from brain.connectors.throttle import RETRY_AFTER_WHEN_UNSTATED, CallOutcome
from brain.core.projection import MAX_PROJECTED_FIELDS, ProjectionRefusedError
from brain.core.scope import Clause, Op, Scope
from brain.ops import connector_sync
from brain.ops.connectable import READING_ROLE, manifest_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import (
    CONTROL_EVERY,
    DECLARATION_CANNOT_BE_REBUILT,
    DECLARATION_NOT_AGREED,
    FAILED_IN_A_ROW,
    KEY_DECLINED,
    LONGEST_WAIT_AFTER_FAILURES,
    NO_READING,
    NO_VERIFIED_CEILING,
    NOT_READ_YET,
    READ_TO_THE_END,
    READINGS,
    SOURCE_ALLOWANCE_REFUSED,
    SOURCE_TIMED_OUT,
    SOURCE_UNREACHABLE,
    TRIED_AGAIN,
    UNHEALTHY_AFTER_FAILURES,
    VISIBILITY_NOT_STORABLE,
    ConnectorSyncError,
    SyncOutcome,
    SyncPlan,
    SyncState,
    after_attempt,
    failure_detail,
    plan_for,
    storable_predicate,
    stored_fields,
    sync_in_words,
)
from brain.ops.controls import control
from brain.ops.credentials import connector_key_slot
from brain.tables.connector_sync import HEALTH_STATES, OUTCOMES
from tests.fixtures.cassettes import CASSETTES

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
CONNECTED_AT: Final = datetime(2019, 1, 1, tzinfo=UTC)

#: Shaped as the sources' own identifiers are, naming nobody.
TENANT: Final = "11111111-2222-3333-4444-555555555555"
PORTAL: Final = "12345678"

#: A place-holder resolver: every name answers with one public address.
PUBLIC: Final = "93.184.216.34"


class Resolver:
    def resolve(self, host: str) -> list[str]:
        del host
        return [PUBLIC]


def recorded(cid: str) -> Any:
    return next(one for one in CASSETTES if one.cid == cid)


def a_connection(name: str = "xero", *, settings: Mapping[str, str] | None = None) -> Connection:
    """One connection, pinned to the digest its settings build today."""
    given = dict(settings) if settings is not None else _settings(name)
    return Connection(
        connector=name,
        settings=given,
        digest=manifest_digest(manifest_for(name, given)),
        connected_by="u_admin",
        connected_at=CONNECTED_AT,
    )


def _settings(name: str) -> dict[str, str]:
    return {"xero": {"tenant_id": TENANT}, "hubspot": {"portal_id": PORTAL}}[name]


def a_state(**changed: Any) -> SyncState:
    base: dict[str, Any] = {
        "connector": "xero",
        "finished_at": NOW,
        "outcome": SyncOutcome.SYNCED,
        "health": HealthState.OK,
        "consecutive_failures": 0,
        "next_attempt_at": NOW + timedelta(hours=1),
        "detail": READ_TO_THE_END,
        "last_synced_at": NOW,
    }
    base.update(changed)
    return SyncState(**base)


def an_invoice(**overrides: Any) -> ProjectedRecord:
    """The recorded invoice, read through Xero's own mapping and projection."""
    operation = xero.operation_for(xero.ENTITY_INVOICE, resolver=Resolver())
    reply = xero.interpret(
        operation,
        status=200,
        body=recorded("XERO-200-invoices").body,
        fetched_at=NOW.isoformat(),
    )
    assert reply.rows is not None
    (row,) = (one.model_dump() for one in reply.rows.records)
    row.update(overrides)
    made = xero.projected_record(xero.ENTITY_INVOICE, row, last_seen_at=NOW)
    assert made is not None
    return made


def tenant_rule() -> Scope:
    return xero.XeroConnection(tenant_id=TENANT).visibility()


# ------------------------------------------------------------------------- may it be read


def test_an_agreed_xero_connection_under_a_verified_ceiling_is_read_with_the_workers_key() -> None:
    """**The positive case, and the sibling of every refusal below.** A Xero connection whose
    settings build the manifest it was agreed to is read, is due when nothing has tried it, runs
    under the limits `brain.ops.limits` verified for Xero, and names the key the worker reads.

    Delete this and every refusal below is satisfied by a plan that refuses every source, which
    reads nothing on any install and says so in no sentence anybody would question."""
    plan = plan_for(a_connection("xero"), last=None, now=NOW)

    assert plan.refused == ""
    assert plan.due is True
    assert plan.manifest is not None
    assert plan.reading is READINGS["xero"]
    assert {limit.limit for limit in plan.limits} >= {60, 5_000}
    assert plan.manifest.credential.ref.path == connector_key_slot("xero").path
    assert plan.manifest.credential.ref.role is READING_ROLE


def test_hubspot_is_not_read_because_nobody_verified_its_ceiling() -> None:
    """Held against HubSpot's own record of the fact rather than against the sentence alone: the
    connector says its ceiling is unverified, and the plan says the same thing to a person.

    Delete this and HubSpot is read against no ceiling, which `throttle.limits_for` exists to
    refuse, or the refusal stops being said on the screen."""
    assert hubspot.ceiling_is_verified() is False
    plan = plan_for(a_connection("hubspot"), last=None, now=NOW)

    assert plan.refused == NO_VERIFIED_CEILING
    assert (plan.manifest, plan.reading, plan.due) == (None, None, False)


def test_a_connection_whose_declaration_changed_since_it_was_agreed_to_is_not_read() -> None:
    """The pin `brain.connectors.registry.reconnect` fails closed on, applied to a scheduled read.

    Delete this and a release that widened what a connector declares reads every connected source
    under a declaration no administrator accepted."""
    changed = dataclasses.replace(a_connection("xero"), digest="0" * 64)

    assert plan_for(changed, last=None, now=NOW).refused == DECLARATION_NOT_AGREED
    assert plan_for(a_connection("xero"), last=None, now=NOW).refused == ""


def test_settings_this_release_cannot_rebuild_and_a_source_with_no_reading_are_not_read() -> None:
    """A tenant of `*` narrows nothing, and the connection class refuses it; a source this release
    has no reading for is not guessed at. Both are said rather than skipped.

    Delete this and a stored connection whose settings a stricter connector now refuses is read
    with whatever the manifest builder does on the way to refusing it."""
    unbuildable = Connection(
        connector="xero",
        settings={"tenant_id": "*"},
        digest="0" * 64,
        connected_by="u_admin",
        connected_at=CONNECTED_AT,
    )

    assert plan_for(unbuildable, last=None, now=NOW).refused == DECLARATION_CANNOT_BE_REBUILT
    assert plan_for(a_connection("xero"), last=None, now=NOW, readings={}).refused == NO_READING


def test_a_visibility_rule_a_stored_record_cannot_carry_is_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prefix over a field is a predicate over many values and a row holds one. A manifest
    declaring one is not read at all, rather than read into rows no grant can reach.

    Delete this and such a source is read, and every record it leaves is one nobody reaches, which
    reads on every screen as the permission model working."""
    agreed = manifest_for("xero", _settings("xero"))
    widened = dataclasses.replace(
        agreed,
        projections=tuple(
            ProjectedEntity(
                entity=one.entity,
                fields=one.fields,
                change_signal=one.change_signal,
                visibility=Scope(
                    clauses=(Clause(field="tenant_id", op=Op.PREFIX, value=TENANT[:8]),)
                ),
            )
            for one in agreed.projections
        ),
    )
    monkeypatch.setattr(connector_sync, "manifest_for", lambda name, settings: widened)
    connection = dataclasses.replace(a_connection("xero"), digest=manifest_digest(widened))

    assert plan_for(connection, last=None, now=NOW).refused == VISIBILITY_NOT_STORABLE


def test_only_an_equality_over_a_value_is_a_predicate_a_record_can_carry() -> None:
    """Delete this and a set, a prefix or no clause at all reads as storable."""
    assert storable_predicate(tenant_rule()) is True
    assert storable_predicate(Scope()) is False
    assert (
        storable_predicate(Scope(clauses=(Clause(field="tenant_id", op=Op.IN, value=(TENANT,)),)))
        is False
    )
    assert (
        storable_predicate(Scope(clauses=(Clause(field="tenant_id", op=Op.PREFIX, value="1"),)))
        is False
    )


def test_a_source_tried_before_is_due_only_once_its_next_attempt_has_come() -> None:
    """Delete this and a failing source is attempted on every five-minute run, whatever its backoff
    said, which spends a client's allowance on a refusal already known."""
    waiting = a_state(next_attempt_at=NOW + timedelta(minutes=1))
    come = a_state(next_attempt_at=NOW)

    assert plan_for(a_connection("xero"), last=waiting, now=NOW).due is False
    assert plan_for(a_connection("xero"), last=come, now=NOW).due is True


def test_a_plan_cannot_both_refuse_and_carry_what_running_needs() -> None:
    """Delete this and a plan saying why nothing reads a source could still be run, or one with
    nothing to run could be due."""
    manifest = manifest_for("xero", _settings("xero"))
    with pytest.raises(ConnectorSyncError):
        SyncPlan(connector="xero")
    with pytest.raises(ConnectorSyncError):
        SyncPlan(connector="xero", refused=NO_READING, manifest=manifest, reading=READINGS["xero"])
    with pytest.raises(ConnectorSyncError):
        SyncPlan(connector="xero", refused=NO_READING, due=True)
    SyncPlan(connector="xero", refused=NO_READING)
    SyncPlan(connector="xero", manifest=manifest, reading=READINGS["xero"], due=True)


# ------------------------------------------------------------------------- what is kept


def test_a_record_carries_the_field_its_sources_visibility_rule_tests_with_the_value_it_names() -> (
    None
):
    """**The visibility half of the leaf.** The recorded invoice is kept with its declared fields,
    its due date as an instant with its zone, and the tenant its source's rule names, which is the
    field a reader's grant scope is compiled against. The amount owing arrived in the answer and is
    not kept.

    Delete this and a record could be stored without the field every grant tests, which nobody can
    then reach, or with the money the connector refuses to store."""
    kept = stored_fields(an_invoice(), tenant_rule())

    assert kept["tenant_id"] == TENANT
    assert (
        kept["invoice_number"] == recorded("XERO-200-invoices").body["Invoices"][0]["InvoiceNumber"]
    )
    assert kept["status"] == "AUTHORISED"
    assert kept["due_date"] == datetime(2026, 11, 15, tzinfo=UTC).isoformat()
    assert "amount_due" not in kept
    assert "CANARY-INVOICE-Z9KRT" not in repr(kept)


def test_a_projected_field_that_disagrees_with_the_visibility_rule_is_refused_not_overwritten() -> (
    None
):
    """One field with two values is two answers to who may read the row. The sibling holds that
    agreement is not refused.

    Delete this and a projection naming another tenant is quietly overwritten with this one, or a
    visibility field is quietly dropped in favour of whatever the source sent."""
    record = an_invoice()
    other = dataclasses.replace(record, fields={**record.fields, "tenant_id": "another-tenant"})
    same = dataclasses.replace(record, fields={**record.fields, "tenant_id": TENANT})

    with pytest.raises(ConnectorSyncError):
        stored_fields(other, tenant_rule())
    assert stored_fields(same, tenant_rule())["tenant_id"] == TENANT


def test_the_visibility_fields_count_against_the_cap_the_table_enforces() -> None:
    """`proj.record` counts every key in `fields`. A projection at the cap plus the rule's field is
    over it, and is refused where the cap is enforced rather than by the database mid-run.

    Delete this and a source projecting twelve fields is refused by a check constraint on every
    page, which fails the run as a database error rather than as a declaration nobody can store."""
    full = ProjectedRecord(
        source="xero",
        entity="invoice",
        source_id="one",
        last_seen_at=NOW,
        fields={f"field_{n}": "x" for n in range(MAX_PROJECTED_FIELDS)},
    )
    with pytest.raises(ProjectionRefusedError):
        stored_fields(full, tenant_rule())
    stored_fields(
        dataclasses.replace(full, fields=dict(list(full.fields.items())[:-1])), tenant_rule()
    )


def test_a_rule_a_record_cannot_carry_is_refused_by_the_writer_as_well_as_the_plan() -> None:
    """Delete this and a reading handed a prefix rule writes a record carrying no rule at all."""
    with pytest.raises(ConnectorSyncError):
        stored_fields(an_invoice(), Scope())


# ----------------------------------------------------------------------- what it costs


def test_a_read_to_the_end_clears_the_failures_and_waits_one_refresh_interval() -> None:
    """Delete this and a source that recovered keeps its backoff, or a healthy source is read on
    every run."""
    done = after_attempt(
        connector="xero",
        started_at=NOW,
        finished_at=NOW,
        outcome=SyncOutcome.SYNCED,
        detail=READ_TO_THE_END,
        interval=xero.RECONCILIATION_INTERVAL,
        previous=a_state(outcome=SyncOutcome.FAILED, consecutive_failures=4),
        records=1,
    )

    assert (done.consecutive_failures, done.health) == (0, HealthState.OK)
    assert done.next_attempt_at == NOW + xero.RECONCILIATION_INTERVAL


def test_each_failure_in_a_row_doubles_the_wait_and_a_day_is_the_longest() -> None:
    """Held against the interval the source promised, not against a figure typed here.

    Delete this and a source whose key expired is asked on every run, or is never asked again once
    somebody replaces the key, and the arithmetic overflows for a source that failed for a year."""
    interval = xero.RECONCILIATION_INTERVAL
    previous: SyncState | None = None
    waits: list[timedelta] = []
    for _ in range(8):
        done = after_attempt(
            connector="xero",
            started_at=NOW,
            finished_at=NOW,
            outcome=SyncOutcome.FAILED,
            detail=SOURCE_UNREACHABLE,
            interval=interval,
            previous=previous,
            call=CallOutcome.UNAVAILABLE,
        )
        waits.append(done.next_attempt_at - NOW)
        previous = a_state(
            outcome=SyncOutcome.FAILED, consecutive_failures=done.consecutive_failures
        )

    assert waits[:5] == [interval, interval * 2, interval * 4, interval * 8, interval * 16]
    assert waits[5:] == [LONGEST_WAIT_AFTER_FAILURES] * 3
    assert timedelta(days=1) == LONGEST_WAIT_AFTER_FAILURES
    endless = a_state(outcome=SyncOutcome.FAILED, consecutive_failures=10_000)
    late = after_attempt(
        connector="xero",
        started_at=NOW,
        finished_at=NOW,
        outcome=SyncOutcome.FAILED,
        detail=SOURCE_UNREACHABLE,
        interval=interval,
        previous=endless,
    )
    assert late.next_attempt_at == NOW + LONGEST_WAIT_AFTER_FAILURES


def test_the_third_failure_in_a_row_marks_the_source_down_and_the_second_does_not() -> None:
    """Three, because the projection turns stale at the third missed refresh and the two should
    agree. A declined key is down at the first, because retrying reproduces it.

    Delete this and one dropped connection pages somebody, or a source failing all week is shown
    as degraded for ever."""
    assert UNHEALTHY_AFTER_FAILURES == MISSED_REFRESHES_BEFORE_STALE == 3

    def failed(before: int, call: CallOutcome) -> HealthState:
        return after_attempt(
            connector="xero",
            started_at=NOW,
            finished_at=NOW,
            outcome=SyncOutcome.FAILED,
            detail=failure_detail(call),
            interval=xero.RECONCILIATION_INTERVAL,
            previous=a_state(consecutive_failures=before) if before else None,
            call=call,
        ).health

    assert failed(0, CallOutcome.UNAVAILABLE) is HealthState.DEGRADED
    assert failed(1, CallOutcome.UNAVAILABLE) is HealthState.DEGRADED
    assert failed(2, CallOutcome.UNAVAILABLE) is HealthState.DOWN
    assert failed(0, CallOutcome.REJECTED) is HealthState.DOWN


def test_a_quota_refusal_waits_as_long_as_the_source_asked_and_counts_no_failure() -> None:
    """The recorded daily refusal asks for 1847 seconds, longer than the platform's cap. A refusal
    that named no wait gets the platform's longest.

    Delete this and a spent day is retried after five minutes all afternoon, or a busy source is
    marked down for being asked."""
    asked = float(recorded("XERO-429").headers["Retry-After"])
    quota = after_attempt(
        connector="xero",
        started_at=NOW,
        finished_at=NOW,
        outcome=SyncOutcome.QUOTA,
        detail=SOURCE_ALLOWANCE_REFUSED,
        interval=xero.RECONCILIATION_INTERVAL,
        previous=a_state(outcome=SyncOutcome.FAILED, consecutive_failures=2),
        retry_after_seconds=asked,
    )
    unstated = after_attempt(
        connector="xero",
        started_at=NOW,
        finished_at=NOW,
        outcome=SyncOutcome.QUOTA,
        detail=SOURCE_ALLOWANCE_REFUSED,
        interval=xero.RECONCILIATION_INTERVAL,
        previous=None,
    )

    assert quota.next_attempt_at == NOW + timedelta(seconds=asked)
    assert (quota.consecutive_failures, quota.health) == (2, HealthState.DEGRADED)
    assert unstated.next_attempt_at == NOW + timedelta(seconds=RETRY_AFTER_WHEN_UNSTATED)
    assert unstated.consecutive_failures == 0


def test_a_failure_is_described_by_its_kind_and_never_by_what_the_source_said() -> None:
    """Delete this and a timeout reads as an outage and a declined key as a network problem, and
    the person sent to fix it looks in the wrong place."""
    assert failure_detail(CallOutcome.REJECTED) == KEY_DECLINED
    assert failure_detail(CallOutcome.UNAVAILABLE) == SOURCE_UNREACHABLE
    assert failure_detail(CallOutcome.UNAVAILABLE, timed_out=True) == SOURCE_TIMED_OUT


# ------------------------------------------------------------------------ what is said


def test_the_screen_says_why_nothing_reads_a_source_before_it_describes_an_old_attempt() -> None:
    """Delete this and a source whose declaration changed goes on showing its last good read as
    though it were still being read."""
    refused = SyncPlan(connector="xero", refused=DECLARATION_NOT_AGREED)
    failing = a_state(outcome=SyncOutcome.FAILED, consecutive_failures=3, detail=KEY_DECLINED)

    assert sync_in_words(refused, a_state()) == DECLARATION_NOT_AGREED
    assert sync_in_words(None, None) == NOT_READ_YET
    assert sync_in_words(None, a_state()) == READ_TO_THE_END
    said = sync_in_words(None, failing)
    assert said.startswith(KEY_DECLINED)
    assert f"{TRIED_AGAIN} {failing.next_attempt_at.isoformat()}" in said
    assert f"{FAILED_IN_A_ROW} 3" in said
    assert FAILED_IN_A_ROW not in sync_in_words(
        None, a_state(outcome=SyncOutcome.FAILED, consecutive_failures=1)
    )


def test_what_a_row_may_say_is_what_the_table_admits() -> None:
    """Delete this and an outcome or a health word added here is refused by a check constraint on
    the first run that produces it."""
    assert {one.value for one in SyncOutcome} == set(OUTCOMES)
    assert set(HEALTH_STATES) == {one.value for one in HealthState} - {
        HealthState.UNCONFIGURED.value
    }


# ------------------------------------------------------------------------ the readings


def test_the_control_runs_at_a_third_of_the_shortest_interval_any_reading_promises() -> None:
    """Held against the readings' own intervals and against the registry, rather than against the
    constant.

    Delete this and a reading added with a shorter interval is late by more than its own promise,
    or the registry's cadence and the module's drift apart."""
    shortest = min(reading.refresh_interval() for reading in READINGS.values())

    assert shortest == CONTROL_EVERY * 3
    assert control("connector_sync").every == CONTROL_EVERY
    assert shortest == hubspot.CURSOR_POLL_INTERVAL


def test_xeros_reading_asks_for_the_next_page_only_after_a_full_one() -> None:
    """Delete this and a ledger of a hundred and one invoices is read as a hundred, or a reading
    asks for pages after the last for ever."""
    reading = READINGS["xero"]
    first = reading.first_page(xero.ENTITY_INVOICE)

    assert dict(first) == {"page": "1"}
    assert reading.next_page(xero.ENTITY_INVOICE, first, {}, 100) == {"page": "2"}
    assert reading.next_page(xero.ENTITY_INVOICE, first, {}, 99) is None
    assert dict(reading.call_headers({"tenant_id": TENANT})) == {xero.TENANT_HEADER: TENANT}
    assert reading.allowance_spent({"X-DayLimit-Remaining": "0"}) is True
    assert reading.allowance_spent({"X-DayLimit-Remaining": "1"}) is False


def test_hubspots_reading_follows_the_cursor_it_is_given_and_reads_the_recorded_absence() -> None:
    """The one recorded HubSpot answer is a genuine absence, and it is read as an answered call with
    nothing to keep rather than as a failure.

    Delete this and a reading that ignored the cursor reads the first hundred contacts on every run,
    or one that read an empty CRM as a failure marks a healthy source down."""
    reading = READINGS["hubspot"]
    first = reading.first_page(hubspot.ENTITY_CLIENT)
    empty = recorded("HUBSPOT-200-empty")
    operation = reading.operation(hubspot.ENTITY_CLIENT, resolver=Resolver())
    reply = reading.interpret(operation, status=empty.status, body=empty.body, fetched_at="now")

    assert dict(first) == dict(hubspot.default_arguments(hubspot.ENTITY_CLIENT))
    following = reading.next_page(
        hubspot.ENTITY_CLIENT, first, {"paging": {"next": {"after": "cursor-2"}}}, 100
    )
    assert following is not None
    assert following[hubspot.CURSOR_PARAMETER] == "cursor-2"
    assert reading.next_page(hubspot.ENTITY_CLIENT, first, {"results": []}, 0) is None
    assert reply.call is CallOutcome.OK
    assert reply.rows is not None
    assert reply.rows.records == ()
    assert dict(reading.call_headers({"portal_id": PORTAL})) == {}


def test_no_reading_ever_contributes_the_authorisation_header() -> None:
    """The key is added by the worker's run for one request and never by a reading, which a later
    reading could keep. Delete this and a reading could carry a credential header of its own."""
    for name, reading in READINGS.items():
        headers = reading.call_headers(_settings(name))
        assert not {key.lower() for key in headers} & {"authorization", "cookie"}
