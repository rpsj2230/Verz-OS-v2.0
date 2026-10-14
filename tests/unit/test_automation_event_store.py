"""An automation a change starts, on a real database: found, scoped to its owner, run once, bounded.

`tests/unit/test_automation_event.py` holds the decisions over values. This file holds what
`brain.ops.automation_event_store` writes through the migrations that ship, and what the index's
upsert now says about when a record changed. It builds one database at head for the whole module and
gives every test its own source, owner, agent and automation, so no test sees another's rows. **It
skips when there is no server**, and CI always has one.

Task ids: M17.4.1
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.connectors.projection import ProjectedRecord
from brain.console.automation_gallery import BUILT_IN
from brain.core.scope import Scope
from brain.ops import automation_run_store as runs
from brain.ops.automation_event import (
    EVENT_RUNS_PER_HOUR,
    EVENT_RUNS_PER_PASS,
    Change,
    event_run_id,
    refusal_run_id,
)
from brain.ops.automation_event_store import event_starts_are_on, run_changes
from brain.ops.automation_run import RUNNER_ACTOR, PausedBecause
from brain.ops.automation_run_store import run_automations
from brain.ops.connector_sync_store import record_upsert
from brain.ops.features import AUTOMATION_EVENTS, switch
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import engine, run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_entitlement_store import a_grant, a_principal, revoke

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)
ARMED = NOW - timedelta(hours=3)

QUESTIONS = next(one for one in BUILT_IN if one.task == "automation.unanswered_questions")


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    with at_head("brain_automation_event_store") as built:
        yield built


@dataclass(frozen=True)
class Armed:
    owner: str
    agent: str
    automation: str
    source: str


def arm(
    url: str, tag: str, *, trigger: str = "connector_event", armed_at: datetime | None = ARMED
) -> Armed:
    """An owner who may read web invoices and the questions report, an agent admitting both, and an
    automation of theirs listening to its own source. Armed at `ARMED`, or paused for None."""
    owner, agent, automation, source = f"u_own_{tag}", f"agent_{tag}", f"auto_{tag}", f"src_{tag}"
    a_principal(url, owner)
    a_grant(url, owner, "read:question")
    a_grant(url, owner, "read:invoice", scope=Scope.department("web"))
    sql(
        url,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
        " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
        " created_by) VALUES (%s, 'Listener', 'Answers briefly.', 'main', 'company',"
        " 'u_steward', NULL, '{\"clauses\": []}', %s, '{}', '{}', 'none', 'u_builder')",
        agent,
        ["read:question", "read:invoice"],
    )
    sql(
        url,
        "INSERT INTO agent.automation (automation_id, agent_id, name, runs_as_id, task,"
        " next_run_at, guards, template_id, template_version, installed_by, trigger_kind,"
        " trigger_source, instruction, tools) VALUES (%s, %s, %s, %s, %s, %s, %s, 'authored', 1,"
        " %s, %s, %s, %s, '{}')",
        automation,
        agent,
        QUESTIONS.name,
        owner,
        QUESTIONS.task,
        armed_at,
        QUESTIONS.guards,
        owner,
        trigger,
        source,
        "Look at what changed and tell me whether it matters to the quote.",
    )
    return Armed(owner=owner, agent=agent, automation=automation, source=source)


def changed(
    url: str,
    source: str,
    source_id: str,
    at: datetime,
    *,
    entity: str = "invoice",
    department: str = "web",
) -> Change:
    """One record in the index whose fields last changed at `at`."""
    sql(
        url,
        "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at, updated_at)"
        " VALUES (%s, %s, %s, %s::jsonb, %s, %s)",
        source,
        entity,
        source_id,
        json.dumps({"department": department}),
        at,
        at,
    )
    return Change(source=source, entity=entity, source_id=source_id, changed_at=at)


def tick(url: str, at: datetime = NOW) -> list[runs.Ran]:
    async def go() -> list[runs.Ran]:
        built = engine(url)
        try:
            return await run_changes(make_session_factory(built), now=at)
        finally:
            await built.dispose()

    return run(go)


def recorded(url: str, automation: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT run_id, outcome, reason, due_at, principal_id FROM agent.automation_run"
        " WHERE automation_id = %s ORDER BY due_at, run_id",
        automation,
    )


def next_run(url: str, automation: str) -> datetime | None:
    [(at,)] = sql(
        url, "SELECT next_run_at FROM agent.automation WHERE automation_id = %s", automation
    )
    return at  # type: ignore[no-any-return]


# ------------------------------------------------------------------ the index's change marker
def _a_record(source: str, fields: dict[str, Any], seen: datetime) -> ProjectedRecord:
    return ProjectedRecord(
        source=source, entity="invoice", source_id="rec_1", last_seen_at=seen, fields=fields
    )


def _upsert(url: str, record: ProjectedRecord) -> None:
    async def go() -> None:
        built = engine(url)
        try:
            async with make_session_factory(built)() as session, session.begin():
                await session.execute(
                    record_upsert(
                        record,
                        {
                            k: v
                            for k, v in record.fields.items()
                            if isinstance(v, str | int | float)
                        },
                    )
                )
        finally:
            await built.dispose()

    run(go)


def _updated_at(url: str, source: str) -> datetime:
    [(at,)] = sql(url, "SELECT updated_at FROM proj.record WHERE source = %s", source)
    return at  # type: ignore[no-any-return]


#: Before the database's own clock by years, so "moved" is `> PAST` whenever the test runs. The
#: upsert stamps `now()` from the server, which is the real time and not this module's `NOW`.
PAST = datetime(2019, 1, 1, tzinfo=UTC)


def test_a_record_the_source_confirms_unchanged_does_not_move_its_change_instant(url: str) -> None:
    """Confirming moves `last_seen_at` and leaves `updated_at` where it was; a real change moves it.
    Delete this and every sync of every source starts a run for every record, the flood the
    owner's decision exists to avoid."""
    source = "src_marker"
    _upsert(url, _a_record(source, {"department": "web"}, PAST))
    sql(url, "UPDATE proj.record SET updated_at = %s WHERE source = %s", PAST, source)

    _upsert(url, _a_record(source, {"department": "web"}, PAST + timedelta(days=1)))
    confirmed = _updated_at(url, source)
    [(seen,)] = sql(url, "SELECT last_seen_at FROM proj.record WHERE source = %s", source)

    _upsert(url, _a_record(source, {"department": "sales"}, PAST + timedelta(days=2)))

    assert confirmed == PAST
    assert seen == PAST + timedelta(days=1)
    assert _updated_at(url, source) > PAST


def test_a_record_a_read_retired_and_the_source_returned_is_a_change_again(url: str) -> None:
    """Delete this and a record that vanished and came back is invisible to every automation
    listening for it, because its fields are the same as the ones it left with."""
    source = "src_returned"
    _upsert(url, _a_record(source, {"department": "web"}, PAST))
    sql(
        url,
        "UPDATE proj.record SET updated_at = %s, deleted_at = now() WHERE source = %s",
        PAST,
        source,
    )
    sql(
        url,
        "INSERT INTO proj.record_retired (source, entity, source_id, fields, last_seen_at,"
        " noticed_at) SELECT source, entity, source_id, fields, last_seen_at, deleted_at"
        " FROM proj.record WHERE source = %s",
        source,
    )

    _upsert(url, _a_record(source, {"department": "web"}, PAST + timedelta(days=1)))

    assert _updated_at(url, source) > PAST
    [(deleted,)] = sql(url, "SELECT deleted_at FROM proj.record WHERE source = %s", source)
    assert deleted is None


# ------------------------------------------------------------------ a change starts a run
def test_a_changed_record_its_owner_may_read_starts_one_run_as_them_and_only_once(
    url: str,
) -> None:
    """The positive case every refusal below is measured against: one changed record in the
    owner's department, one run as the owner under the id its change makes, one outbox event, the
    arming left on the automation, and a second pass over the same change writing nothing. Delete
    this and every refusal test passes against a runner that starts nothing."""
    one = arm(url, "ok")
    change = changed(url, one.source, "rec_1", NOW - timedelta(minutes=30))

    first = tick(url)
    second = tick(url, NOW + timedelta(minutes=1))
    events = sql(
        url,
        "SELECT event_id FROM ops.outbox_event WHERE event_id = %s",
        event_run_id(one.automation, change),
    )

    [(ran_id, outcome, reason, due_at, principal)] = recorded(url, one.automation)
    assert [(r.outcome.value, r.paused) for r in first] == [("succeeded", False)]
    assert second == []
    assert (ran_id, outcome, reason, principal) == (
        event_run_id(one.automation, change),
        "succeeded",
        None,
        one.owner,
    )
    assert due_at == change.changed_at
    assert events == [(ran_id,)]
    assert next_run(url, one.automation) == ARMED


def test_a_record_the_owner_may_not_read_starts_nothing_and_leaves_no_trace(url: str) -> None:
    """A sales invoice and a ticket the owner holds no read on, beside a web invoice they do: one
    run, and nothing recorded for the others, so the automation says nothing of what it may not
    read. Delete this and a run about a record the owner cannot see tells them it exists."""
    one = arm(url, "scoped")
    seen = changed(url, one.source, "rec_web", NOW - timedelta(minutes=30))
    changed(url, one.source, "rec_sales", NOW - timedelta(minutes=29), department="sales")
    changed(url, one.source, "rec_ticket", NOW - timedelta(minutes=28), entity="ticket")

    done = tick(url)

    assert len(done) == 1
    assert [row[0] for row in recorded(url, one.automation)] == [event_run_id(one.automation, seen)]


def test_a_change_from_before_the_arming_starts_nothing_and_one_just_after_it_does(
    url: str,
) -> None:
    """Strictly after the arming. Delete this and an automation armed at noon starts runs about the
    morning, or a change in the first instant after it is missed."""
    one = arm(url, "armed")
    changed(url, one.source, "rec_before", ARMED - timedelta(seconds=1))
    changed(url, one.source, "rec_at", ARMED)
    after = changed(url, one.source, "rec_after", ARMED + timedelta(seconds=1))

    tick(url)

    assert [row[0] for row in recorded(url, one.automation)] == [
        event_run_id(one.automation, after)
    ]


def test_a_paused_automation_is_not_listening_and_a_record_removed_is_not_a_change(
    url: str,
) -> None:
    """No arming, no run; and a retired record is not offered even beside a live one of its kind.
    Delete this and a stopped automation goes on running, or a record a source dropped starts a
    run, which the live record beside it is here to show cannot be explained by there being no
    records at all."""
    paused = arm(url, "paused", armed_at=None)
    changed(url, paused.source, "rec_1", NOW - timedelta(minutes=30))
    listening = arm(url, "retired")
    changed(url, listening.source, "rec_gone", NOW - timedelta(minutes=30))
    sql(
        url,
        "UPDATE proj.record SET deleted_at = now() WHERE source = %s AND source_id = 'rec_gone'",
        listening.source,
    )
    live = changed(url, listening.source, "rec_live", NOW - timedelta(minutes=29))

    done = tick(url)

    assert len(done) == 1
    assert recorded(url, paused.automation) == []
    assert [row[0] for row in recorded(url, listening.automation)] == [
        event_run_id(listening.automation, live)
    ]


def test_a_pass_runs_at_most_five_changes_and_the_rest_wait_for_the_next_pass(url: str) -> None:
    """Eight changes in one transaction share an instant: five run, then the other three, each once.
    Delete this and a rewrite of a source starts one run per record in a single pass, or the three
    that share an instant with the five are never reached."""
    one = arm(url, "tied")
    at = NOW - timedelta(minutes=30)
    made = [changed(url, one.source, f"rec_{n}", at) for n in range(8)]

    first = tick(url)
    second = tick(url, NOW + timedelta(minutes=1))
    third = tick(url, NOW + timedelta(minutes=2))

    assert (len(first), len(second), len(third)) == (EVENT_RUNS_PER_PASS, 3, 0)
    assert {row[0] for row in recorded(url, one.automation)} == {
        event_run_id(one.automation, change) for change in made
    }


def test_an_automation_runs_at_most_twenty_an_hour_and_the_rest_run_when_the_hour_has_gone(
    url: str,
) -> None:
    """Twenty-five changes: twenty in the first hour however many passes, the other five once an
    hour has gone. Delete this and the hourly bound is not applied, or a change over it is lost."""
    one = arm(url, "hour")
    for n in range(25):
        changed(url, one.source, f"rec_{n:02}", NOW - timedelta(minutes=40) + timedelta(seconds=n))

    during = sum(len(tick(url, NOW + timedelta(minutes=n))) for n in range(8))
    later = sum(len(tick(url, NOW + timedelta(minutes=70 + n))) for n in range(3))

    assert during == EVENT_RUNS_PER_HOUR
    assert later == 5
    assert len(recorded(url, one.automation)) == 25


def test_an_owner_who_lost_the_read_is_refused_once_at_the_door_and_stops_listening(
    url: str,
) -> None:
    """The grant the task reads, deleted: one refused run under the arming's own id, no next run, a
    schedule row naming the runner and the reason, and a second pass that finds nothing armed.
    Delete this and a revoked owner's listener goes on listening for ever, or stops with nothing
    saying why."""
    one = arm(url, "revoked")
    changed(url, one.source, "rec_1", NOW - timedelta(minutes=30))
    revoke(url, one.owner, "read:question")

    first = tick(url)
    second = tick(url, NOW + timedelta(minutes=1))
    [(ran_id, outcome, reason, due_at, _)] = recorded(url, one.automation)
    rows = sql(
        url,
        "SELECT reason, changed_by, next_run_at FROM agent.automation_schedule"
        " WHERE automation_id = %s",
        one.automation,
    )

    assert [(r.outcome.value, r.paused) for r in first] == [("refused", True)]
    assert second == []
    assert (ran_id, outcome, reason) == (
        refusal_run_id(one.automation, ARMED),
        "refused",
        PausedBecause.OWNER_LOST_REACH.value,
    )
    assert due_at == ARMED
    assert next_run(url, one.automation) is None
    assert rows == [(PausedBecause.OWNER_LOST_REACH.value, RUNNER_ACTOR, None)]


def test_a_task_that_raises_on_a_change_pauses_at_the_second_failure_and_runs_no_more(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three changes and a task that always raises: two failed runs, the pause, and the third change
    not run. Nothing of the exception is kept. Delete this and a broken task runs against every
    change for ever, or pauses on its first blip."""

    async def broken(*_: object, **__: object) -> tuple[str, ...]:
        msg = "the read quoted somebody's data"
        raise RuntimeError(msg)

    monkeypatch.setattr(runs, "perform", broken)
    one = arm(url, "failing")
    for n in range(3):
        changed(url, one.source, f"rec_{n}", NOW - timedelta(minutes=30) + timedelta(seconds=n))

    done = tick(url)
    rows = recorded(url, one.automation)

    assert [(r.outcome.value, r.paused) for r in done] == [("failed", False), ("failed", True)]
    assert [row[1] for row in rows] == ["failed", "failed"]
    assert next_run(url, one.automation) is None
    assert "somebody's data" not in repr(rows)


def test_a_halt_on_the_owner_holds_the_pass_and_loses_no_change(url: str) -> None:
    """The halt writes nothing and the change is found once it is lifted. Delete this and a stop
    is ignored by the listener, or a halted pass counts as a failure that pauses it."""
    one = arm(url, "halted")
    changed(url, one.source, "rec_1", NOW - timedelta(minutes=30))
    sql(
        url,
        "INSERT INTO ops.halt (act, scope, target, actor_id, actor_role, reason, at)"
        " VALUES ('halt', 'person', %s, 'u_admin', 'install administrator', %s, %s)",
        one.owner,
        "the account was phished on Tuesday",
        NOW - timedelta(minutes=5),
    )
    held = tick(url)
    nothing = recorded(url, one.automation)
    sql(
        url,
        "INSERT INTO ops.halt (act, scope, target, actor_id, actor_role, reason, at)"
        " VALUES ('resume', 'person', %s, 'u_admin', 'install administrator', %s, %s)",
        one.owner,
        "the token was revoked and reset",
        NOW - timedelta(minutes=2),
    )
    after = tick(url, NOW + timedelta(minutes=1))

    assert held == [] and nothing == []
    assert len(after) == 1
    assert next_run(url, one.automation) == ARMED


# ------------------------------------------------------------------ the switch and the clock
def _turn_on(url: str) -> None:
    async def go() -> None:
        built = engine(url)
        try:
            async with make_session_factory(built)() as session, session.begin():
                await switch(session, AUTOMATION_EVENTS, on=True, by="u_owner")
        finally:
            await built.dispose()

    run(go)


def _worker_tick(url: str, at: datetime) -> runs.AutomationTick:
    async def go() -> runs.AutomationTick:
        built = engine(url)
        try:
            return await run_automations(make_session_factory(built), now=at)
        finally:
            await built.dispose()

    return run(go)


def _is_on(url: str) -> bool:
    async def go() -> bool:
        built = engine(url)
        try:
            return await event_starts_are_on(make_session_factory(built))
        finally:
            await built.dispose()

    return run(go)


def test_the_worker_starts_nothing_on_a_change_until_the_switch_is_on_and_the_clock_never_does(
    url: str,
) -> None:
    """The worker's tick with the switch off: an armed row is not due as a schedule and no change
    starts a run; with it on the same tick runs the change. Delete this and the feature ships
    running, or the clock claims a listener as a schedule with no cadence and refuses it."""
    one = arm(url, "switch")
    changed(url, one.source, "rec_1", NOW - timedelta(minutes=30))
    hook = arm(url, "hook", trigger="webhook")

    off = _worker_tick(url, NOW)
    was_off = _is_on(url)
    nothing = (recorded(url, one.automation), recorded(url, hook.automation))
    _turn_on(url)
    on = _worker_tick(url, NOW + timedelta(minutes=1))
    now_on = _is_on(url)

    assert was_off is False and now_on is True
    assert off.summary() == "no automation was due"
    assert nothing == ([], [])
    assert (on.succeeded, on.failed, on.refused) == (1, 0, 0)
    assert len(recorded(url, one.automation)) == 1
    assert recorded(url, hook.automation) == []
    assert next_run(url, hook.automation) == ARMED


def _claimed_by_the_clock(url: str, automation: str) -> object:
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.principal_store import StoredPrincipals

    async def go() -> object:
        built = engine(url)
        try:
            sessions = make_session_factory(built)
            return await runs.run_one(
                sessions,
                automation,
                now=NOW,
                principals=StoredPrincipals(sessions),
                entitlements=StoredEntitlements(sessions),
            )
        finally:
            await built.dispose()

    return run(go)


def test_the_clocks_own_claim_refuses_a_row_a_change_or_a_call_starts_whatever_its_next_run(
    url: str,
) -> None:
    """The claim is the guard and the list of owed ids is only a shortcut, so it is asked of the
    claim directly: an armed listener and a webhook, both due by force, are not claimed and nothing
    is recorded or paused. Delete this and the guard can go from the claim with the worker's tick
    still green, and the first caller that claims by id runs a listener as a schedule with no
    cadence and refuses it."""
    listener = arm(url, "claimed")
    hook = arm(url, "claimed_hook", trigger="webhook")

    assert _claimed_by_the_clock(url, listener.automation) is None
    assert _claimed_by_the_clock(url, hook.automation) is None
    assert recorded(url, listener.automation) == recorded(url, hook.automation) == []
    assert next_run(url, listener.automation) == next_run(url, hook.automation) == ARMED
