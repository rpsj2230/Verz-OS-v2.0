"""What starts an automation besides the clock, decided over values: nothing here opens a database.

`tests/unit/test_automation_event_store.py` holds what the worker does with a real server. This file
holds the decisions it makes: which kinds start anything, what window of changes a pass reads, how
many it may run, how a change is named so it runs once, and what the console confirms when somebody
starts one. Every refusal has a sibling proving the permitted case still works.

Task ids: M17.4.1
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.console.agent_automations import Automation
from brain.console.automation_authoring import (
    Authored,
    AuthoringRefusedError,
    TriggerChoice,
    compose,
)
from brain.console.automation_gallery import Cadence, Every
from brain.console.automation_schedule import (
    ARMED,
    ScheduleControlError,
    ScheduleShown,
    shown_start,
    shown_start_on_change,
    shown_stop,
)
from brain.core.entitlement import Capability
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.knowledge.visibility import Visibility
from brain.ops.automation_event import (
    EVENT_RUNS_PER_HOUR,
    EVENT_RUNS_PER_PASS,
    MAX_AGE,
    SETTLE,
    STARTABLE_KINDS,
    WEBHOOKS_ARE_NOT_OFFERED,
    Change,
    allowance,
    change_key,
    due_changes,
    event_run_id,
    fetch_limit,
    refusal_run_id,
    window,
)
from brain.ops.automation_run import (
    CHANGE_NOT_KEPT,
    AutomationRunError,
    PausedBecause,
    RunOutcome,
    RunRecord,
    afterwards,
    run_id,
)
from brain.orchestration.unattended import TriggerKind
from tests.unit.test_automation_authoring import DAILY, FIELDS

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
ARMED_AT = NOW - timedelta(hours=3)


def a_change(source_id: str = "rec_1", at: datetime = NOW - timedelta(minutes=30)) -> Change:
    return Change(source="invoicing", entity="invoice", source_id=source_id, changed_at=at)


def an_automation(next_run_at: datetime | None = None) -> Automation:
    return Automation(
        automation_id="auto_listener",
        agent_id="quote_helper",
        name="I check each changed invoice as it changes",
        runs_as=Principal(
            id="u_owner",
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name="Owner",
        ),
        task="automation.unanswered_questions",
        next_run_at=next_run_at,
    )


# ------------------------------------------------------------------ which kinds start anything
def test_a_schedule_and_a_change_start_work_and_a_webhook_never_does() -> None:
    """Needs-rupash 223, option B, as a set stated against the enum it is cut from. Delete this and
    the kind the owner closed can be added to the startable set by one word and nothing says so."""
    assert {TriggerKind.SCHEDULE, TriggerKind.CONNECTOR_EVENT} == STARTABLE_KINDS
    assert set(TriggerKind) - STARTABLE_KINDS == {TriggerKind.WEBHOOK}
    assert TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY).fires
    assert TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source="invoicing").fires
    assert not TriggerChoice(kind=TriggerKind.WEBHOOK, source="invoice_paid").fires


def _bound(*connectors: str) -> AgentRecord:
    return AgentRecord(
        agent_id="quote_helper",
        display_name="Quote helper",
        persona="Answers pricing questions.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            capabilities=(Capability(value="read:client.name"),),
            allowed_tools=frozenset({"search_invoices"}),
            connectors=connectors,
        ),
        created_by="u_builder",
    )


def _composed(trigger: TriggerChoice, connectors: tuple[str, ...]) -> Authored:
    return compose(
        agent=_bound(*connectors),
        name="I check each morning whether any invoice is overdue",
        instruction="Look at the invoices and tell me which are overdue by more than a week.",
        guards="Without it an overdue invoice is found when the client chases, not by us.",
        trigger=trigger,
        tools=("search_invoices",),
        condition=None,
        fields=FIELDS,
    )


def test_a_webhook_is_refused_when_it_is_written_and_a_change_and_a_schedule_are_not() -> None:
    """The refusal in words, with its two siblings. Delete this and a webhook can be written again,
    or the refusal is satisfied by one that refuses every trigger."""
    with pytest.raises(AuthoringRefusedError) as refused:
        _composed(TriggerChoice(kind=TriggerKind.WEBHOOK, source="invoice_paid"), ("invoicing",))
    assert WEBHOOKS_ARE_NOT_OFFERED in refused.value.findings

    assert _composed(TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY), ())
    assert _composed(
        TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source="invoicing"), ("invoicing",)
    )


def test_a_change_trigger_on_a_source_its_agent_is_not_bound_to_is_refused() -> None:
    """Delete this and an automation listens to records its agent's ceiling would never let a run
    read, which is a listener that starts runs about nothing."""
    with pytest.raises(AuthoringRefusedError, match="not bound to that source"):
        _composed(TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source="xero"), ("invoicing",))


# ------------------------------------------------------------------ the window
def test_changes_before_the_arming_never_count_and_the_floor_follows_the_newest_run() -> None:
    """Strictly after the arming, and no earlier than the newest change run less the settle. Delete
    this and an automation armed at noon starts runs about the morning's changes, or a pass reads
    the whole of the day again after every run."""
    fresh = window(armed_at=ARMED_AT, newest_run=None, now=NOW)
    later = window(armed_at=ARMED_AT, newest_run=NOW - timedelta(minutes=30), now=NOW)

    assert fresh.after == ARMED_AT
    assert fresh.not_before == ARMED_AT
    assert later.after == ARMED_AT
    assert later.not_before == NOW - timedelta(minutes=30) - SETTLE


def test_a_change_older_than_the_longest_age_is_not_read_even_when_the_arming_is_older() -> None:
    """Delete this and a long-armed automation that was held for days finds every change since the
    arming at once and answers a day nobody remembers."""
    long_ago = NOW - timedelta(days=30)
    reading = window(armed_at=long_ago, newest_run=None, now=NOW)

    assert reading.not_before == NOW - MAX_AGE
    assert reading.after == long_ago


def test_the_settle_is_shorter_than_the_age_and_the_pass_is_inside_the_hour() -> None:
    """Two relations the figures must keep. Delete this and a retuned figure makes the look-back
    wider than the age it looks inside, or a pass bound no hour could hold."""
    assert SETTLE < MAX_AGE
    assert EVENT_RUNS_PER_PASS <= EVENT_RUNS_PER_HOUR


# ------------------------------------------------------------------ the bounds
def test_a_pass_runs_at_most_the_pass_bound_and_less_when_the_hour_is_nearly_used() -> None:
    """Delete this and a source that rewrites a thousand records starts a thousand runs, or an
    hour already full is not respected by the next pass."""
    assert allowance(ran_this_hour=0) == EVENT_RUNS_PER_PASS
    assert allowance(ran_this_hour=EVENT_RUNS_PER_HOUR - 2) == 2
    assert allowance(ran_this_hour=EVENT_RUNS_PER_HOUR) == 0
    assert allowance(ran_this_hour=EVENT_RUNS_PER_HOUR + 7) == 0


def test_the_pass_reads_enough_rows_to_get_past_every_change_it_has_already_run() -> None:
    """Those already run sort first, so a fixed read would stall for good once a window held more
    of them than it. Delete this and the pass looks only at changes it has run and never at a
    new one."""
    assert fetch_limit(recorded_in_window=0) == EVENT_RUNS_PER_PASS
    assert fetch_limit(recorded_in_window=40) == EVENT_RUNS_PER_PASS + 40


# ------------------------------------------------------------------ a change is run once
def test_a_change_is_named_by_its_record_and_its_instant_and_nothing_else_names_it() -> None:
    """The same change is one id and each difference is another. Delete this and two records a
    sync wrote in one transaction share an instant, and the second one's run is refused as the
    first's."""
    one = a_change("rec_1")
    assert event_run_id("auto_listener", one) == event_run_id("auto_listener", a_change("rec_1"))
    assert event_run_id("auto_listener", one) != event_run_id("auto_listener", a_change("rec_2"))
    assert event_run_id("auto_listener", one) != event_run_id(
        "auto_listener", a_change("rec_1", NOW - timedelta(minutes=29))
    )
    assert event_run_id("auto_listener", one) != event_run_id("auto_other", one)
    assert event_run_id("auto_listener", one) != run_id("auto_listener", one.changed_at)


def test_a_scheduled_slots_id_is_the_digest_it_always_was() -> None:
    """Adding a key must not move any slot already recorded. Delete this and the change that made
    a run's id take a key re-ran every automation's last slot, because its id no longer matched."""
    due = datetime(2999, 1, 3, 10, 0, tzinfo=UTC)
    slot = due.isoformat(timespec="microseconds")
    expected = hashlib.sha256(f"auto_one\n{slot}".encode()).hexdigest()[:32]

    assert run_id("auto_one", due) == f"run_{expected}"


def test_a_refusal_at_the_door_is_one_id_per_arming() -> None:
    """Delete this and a pass that repeats a refusal records it twice, or two armings share one."""
    assert refusal_run_id("auto_listener", ARMED_AT) == refusal_run_id("auto_listener", ARMED_AT)
    assert refusal_run_id("auto_listener", ARMED_AT) != refusal_run_id(
        "auto_listener", ARMED_AT + timedelta(seconds=1)
    )


def test_the_oldest_changes_without_a_run_are_due_up_to_the_allowance() -> None:
    """Oldest first, skipping what has a run, no more than allowed. Delete this and a pass runs
    the newest first so the oldest never gets its turn, or runs a change twice."""
    changes = [
        a_change("rec_3", NOW - timedelta(minutes=10)),
        a_change("rec_1", NOW - timedelta(minutes=30)),
        a_change("rec_2", NOW - timedelta(minutes=20)),
    ]
    done = {event_run_id("auto_listener", changes[1])}

    due = due_changes("auto_listener", changes, recorded=done, allowed=5)
    capped = due_changes("auto_listener", changes, recorded=set(), allowed=2)
    none = due_changes("auto_listener", changes, recorded=set(), allowed=0)

    assert [one.source_id for one in due] == ["rec_2", "rec_3"]
    assert [one.source_id for one in capped] == ["rec_1", "rec_2"]
    assert none == ()


def test_changes_sharing_an_instant_are_ordered_by_entity_and_record_so_the_order_is_total() -> (
    None
):
    """Delete this and a pass over a page written in one transaction runs it in an order that
    differs between two reads, so the cap lets different records through each time."""
    same = NOW - timedelta(minutes=5)
    changes = [a_change("b", same), a_change("a", same)]

    due = due_changes("auto_listener", changes, recorded=set(), allowed=1)

    assert [one.source_id for one in due] == ["a"]


def test_a_change_without_a_timezone_is_refused() -> None:
    """Delete this and one host's naive instant is another's, so an id changes with the machine."""
    with pytest.raises(ValueError, match="no timezone"):
        Change(source="s", entity="e", source_id="r", changed_at=datetime(2999, 1, 1))


def test_a_change_key_is_the_record_and_the_instant_in_one_normalised_string() -> None:
    """Delete this and the key depends on the offset a driver returned, so one change read twice
    is two runs."""
    east = a_change("rec_1", datetime(2999, 6, 1, 20, 0, tzinfo=timezone(timedelta(hours=8))))
    utc = a_change("rec_1", datetime(2999, 6, 1, 12, 0, tzinfo=UTC))

    assert change_key(east) == change_key(utc)


# ------------------------------------------------------------------ a run record
def _record(**changes: object) -> RunRecord:
    change = a_change()
    values: dict[str, object] = {
        "run_id": event_run_id("auto_listener", change),
        "automation_id": "auto_listener",
        "agent_id": "quote_helper",
        "principal_id": "u_owner",
        "due_at": change.changed_at,
        "started_at": NOW,
        "finished_at": NOW,
        "outcome": RunOutcome.SUCCEEDED,
        "change_key": change_key(change),
    }
    values.update(changes)
    return RunRecord(**values)  # type: ignore[arg-type]


def test_a_run_a_change_started_carries_the_id_its_change_makes_and_no_other() -> None:
    """The constructor's guard, both ways. Delete this and a writer can record a change's run under
    a scheduled slot's id, which a rerun of the slot would then refuse."""
    assert _record().run_id == event_run_id("auto_listener", a_change())
    with pytest.raises(AutomationRunError, match="is not the id"):
        _record(run_id=run_id("auto_listener", a_change().changed_at))


def test_a_run_read_back_accepts_the_shape_of_an_id_and_refuses_anything_else() -> None:
    """The key is hashed into the id and not stored, so a stored run is held to the shape. Delete
    this and a stored change-started run cannot be read back at all, or a malformed id is."""
    kept = _record(change_key=CHANGE_NOT_KEPT)
    assert kept.run_id == event_run_id("auto_listener", a_change())
    with pytest.raises(AutomationRunError, match="shape of a run id"):
        _record(change_key=CHANGE_NOT_KEPT, run_id="run_zz")


# ------------------------------------------------------------------ what is left after a run
def test_an_armed_automation_keeps_its_arming_after_a_run_and_a_refusal_removes_it() -> None:
    """No cadence moves an armed automation, a run leaves it armed, and only a refusal or the
    failure pause takes the instant away. Delete this and an armed automation either has no next
    run after its first run or one invented from a cadence it does not have."""
    one = an_automation(ARMED_AT)
    kept = afterwards(
        one,
        outcome=RunOutcome.SUCCEEDED,
        refused_because=None,
        failures_before=0,
        cadence=None,
        owner_id="u_steward",
        guards="Without it a changed invoice is found when the client chases us.",
        at=NOW,
        armed_at=ARMED_AT,
    )
    refused = afterwards(
        one,
        outcome=RunOutcome.REFUSED,
        refused_because=PausedBecause.OWNER_GONE,
        failures_before=0,
        cadence=None,
        owner_id="u_steward",
        guards="Without it a changed invoice is found when the client chases us.",
        at=NOW,
        armed_at=ARMED_AT,
    )

    assert kept.next_run_at == ARMED_AT and kept.paused_because is None
    assert refused.next_run_at is None and refused.paused_because is PausedBecause.OWNER_GONE


def test_a_run_with_no_cadence_and_no_arming_is_still_refused_as_a_wiring_fault() -> None:
    """Delete this and a scheduled automation whose template was lost is given a next run from
    nowhere instead of failing loudly."""
    with pytest.raises(AutomationRunError, match="no cadence"):
        afterwards(
            an_automation(ARMED_AT),
            outcome=RunOutcome.SUCCEEDED,
            refused_because=None,
            failures_before=0,
            cadence=None,
            owner_id="u_steward",
            guards="Without it a changed invoice is found when the client chases us.",
            at=NOW,
        )


# ------------------------------------------------------------------ what a person confirms
def test_starting_on_a_change_is_confirmed_without_the_instant_the_write_will_choose() -> None:
    """The digest of a start asked for at one second equals the digest at the next, because the
    instant is the write's and not the request's, and it still differs by source. Delete this and
    every start of an automation a change starts is refused as stale, or one source's start
    confirms another's."""
    one = an_automation()
    first = shown_start_on_change(one, "invoicing", now=NOW)
    later = shown_start_on_change(one, "invoicing", now=NOW + timedelta(seconds=40))
    other = shown_start_on_change(one, "xero", now=NOW)

    assert first.confirmation == later.confirmation
    assert first.confirmation != other.confirmation
    assert first.becomes == NOW
    assert first.trigger_words() == "when something changes in invoicing"
    assert ARMED == "armed"


def test_a_scheduled_start_is_still_confirmed_against_its_next_instant() -> None:
    """Delete this and the change that taught a start to be armed also made a schedule's start
    confirm a stale hour."""
    one = an_automation()
    cadence = Cadence(every=Every.DAY, hour_utc=7)
    a = shown_start(one, cadence, now=NOW)
    b = shown_start(one, cadence, now=NOW + timedelta(days=1))

    assert a.confirmation != b.confirmation


def test_a_stop_confirms_for_either_kind_and_a_start_must_have_exactly_one_trigger() -> None:
    """Delete this and a stop is refused for an automation a change starts, or a shown value can
    name a cadence and a source at once and read as whichever is convenient."""
    one = an_automation(ARMED_AT)
    assert shown_stop(one, listens_to="invoicing").becomes is None
    assert shown_stop(one, Cadence(every=Every.DAY, hour_utc=7)).becomes is None
    with pytest.raises(ScheduleControlError, match="a cadence or by a source"):
        ScheduleShown(
            direction=shown_stop(one, listens_to="x").direction,
            automation=one,
            cadence=Cadence(every=Every.DAY, hour_utc=7),
            becomes=None,
            listens_to="x",
        )
    with pytest.raises(ScheduleControlError, match="a cadence or by a source"):
        shown_stop(one)
