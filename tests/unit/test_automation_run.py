"""An installed automation's run: at whose reach, refused when, scheduled next when, paused when.

`brain.ops.automation_run` holds no connection, so everything here is decided over values. The
database half, where the worker claims a row and writes the run, is
`tests/unit/test_automation_run_store.py`.

Task ids: M39.6.2.1, M39.6.2.3, M38.2.2.5
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.audit.ledger import IDENTIFIER
from brain.console.agent_automations import FAILURES_BEFORE_PAUSE, Automation
from brain.console.automation_gallery import BUILT_IN, Cadence, Every
from brain.console.questions_view import QUESTION_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.visibility import Visibility
from brain.ops import automation_run as run
from brain.ops.automation_run import (
    AutomationRunError,
    PausedBecause,
    RunOutcome,
    RunRecord,
    TaskDeclaration,
    admitted_run,
    afterwards,
    failures_in_a_row,
    next_run_after,
    run_event,
    run_id,
    task_declaration,
    task_gaps,
)
from brain.ops.jobs import MAX_ATTEMPTS
from brain.ops.outbox import EventKind
from brain.tables import automation_run as table

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock. A
#: Thursday, so a weekly cadence on Friday and a weekday cadence both have something to cross.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)
LATER = datetime(3999, 1, 1, tzinfo=UTC)

OWNER = "u_owner"
AGENT = "quote_helper"
QUESTIONS = next(one for one in BUILT_IN if one.task == "automation.unanswered_questions")


def person(pid: str = OWNER, *, not_after: datetime | None = None) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.CONTRACTOR if not_after else Employment.STAFF,
        display_name=f"Person {pid}",
        not_after=not_after,
    )


def an_agent(*capabilities: str, disabled: bool = False, scope: Scope | None = None) -> AgentRecord:
    return AgentRecord(
        agent_id=AGENT,
        display_name="Quote helper",
        persona="Answers briefly.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            capabilities=tuple(Capability(value=one) for one in capabilities),
            scope=scope or Scope.unrestricted(),
        ),
        created_by="u_builder",
        disabled_at=NOW - timedelta(days=1) if disabled else None,
    )


def holding(*capabilities: str, pid: str = OWNER) -> EntitlementSet:
    return EntitlementSet(
        principal_id=pid,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def an_automation(task: str = QUESTIONS.task, owner: Principal | None = None) -> Automation:
    return Automation(
        automation_id="auto_one",
        agent_id=AGENT,
        name=QUESTIONS.name,
        runs_as=owner or person(),
        task=task,
        next_run_at=NOW,
    )


# ------------------------------------------------------------------ the cadence
def test_a_daily_cadence_runs_next_at_its_hour_strictly_after_the_instant() -> None:
    """Before the hour it is today, at or after the hour it is tomorrow.

    Delete this and a run that finished at exactly its hour would be due again at once, or a run
    before the hour would skip today."""
    daily = Cadence(every=Every.DAY, hour_utc=7)
    assert next_run_after(daily, NOW) == datetime(2999, 1, 4, 7, tzinfo=UTC)
    assert next_run_after(daily, NOW.replace(hour=6)) == datetime(2999, 1, 3, 7, tzinfo=UTC)
    exactly = datetime(2999, 1, 3, 7, tzinfo=UTC)
    assert next_run_after(daily, exactly) == exactly + timedelta(days=1)


def test_a_weekday_cadence_skips_the_weekend_and_a_weekly_one_waits_for_its_day() -> None:
    """2999-01-03 is a Thursday, so the Friday after is the fourth and the Monday the seventh.

    Delete this and a weekday report would arrive on Saturday, or a weekly one every day."""
    assert NOW.weekday() == 3
    weekday = Cadence(every=Every.WEEKDAY, hour_utc=9)
    friday = datetime(2999, 1, 4, 9, tzinfo=UTC)
    assert next_run_after(weekday, NOW) == friday
    assert next_run_after(weekday, friday) == datetime(2999, 1, 7, 9, tzinfo=UTC)
    weekly = Cadence(every=Every.WEEK, hour_utc=8, weekday=0)
    assert next_run_after(weekly, NOW) == datetime(2999, 1, 7, 8, tzinfo=UTC)
    assert next_run_after(weekly, datetime(2999, 1, 7, 8, tzinfo=UTC)) == datetime(
        2999, 1, 14, 8, tzinfo=UTC
    )


def test_the_cadence_is_counted_in_utc_whatever_offset_the_instant_carries() -> None:
    """The same instant written at another offset has the same next run.

    Delete this and a worker whose driver hands back local times would schedule at the wrong hour,
    which is the zone `Cadence.words` promises the reader it is not in."""
    daily = Cadence(every=Every.DAY, hour_utc=7)
    elsewhere = NOW.astimezone(timezone(timedelta(hours=8)))
    assert next_run_after(daily, elsewhere) == next_run_after(daily, NOW)
    with pytest.raises(AutomationRunError, match="naive"):
        next_run_after(daily, NOW.replace(tzinfo=None))


# ------------------------------------------------------------------ the reach
def test_a_run_starts_at_the_owners_reach_narrowed_by_the_agent_and_no_wider() -> None:
    """The owner holds the read the task needs and two more; the agent admits the read and one of
    them. The run holds exactly the two both sides hold, and an admin grant both sides name is
    withheld because an automation is admitted at read only.

    Delete this and a run could reach what its owner holds and the agent does not admit, which is
    the central invariant broken with nobody present to notice."""
    owner = holding("read:question", "read:client.name", "read:hr.salary", "admin:question")
    agent = an_agent("read:question", "read:client.name", "admin:question")

    found = admitted_run(
        an_automation(), owner=person(), owner_entitlements=owner, agent=agent, now=NOW
    )

    assert isinstance(found, run.Admitted)
    assert found.reach.principal_id == OWNER
    assert found.reach.holds(QUESTION_AUTHORITY, NOW)
    assert found.reach.holds(Capability(value="read:client.name"), NOW)
    assert not found.reach.holds(Capability(value="read:hr.salary"), NOW)
    assert not found.reach.holds(Capability(value="admin:question"), NOW)
    assert found.declaration.reads == QUESTION_AUTHORITY


def test_the_agents_scope_narrows_the_run_as_well_as_its_capabilities() -> None:
    """An agent scoped to one department gives a run holding the owner's company-wide read only in
    that department.

    Delete this and the ceiling's scope could be dropped by the run, so an agent written for Web
    would report on every department its owner can read."""
    web = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
    found = admitted_run(
        an_automation(),
        owner=person(),
        owner_entitlements=holding("read:question"),
        agent=an_agent("read:question", scope=web),
        now=NOW,
    )
    assert isinstance(found, run.Admitted)
    reached = found.reach.scope_for(QUESTION_AUTHORITY, NOW)
    assert reached is not None
    assert reached.matches({"department": "web"})
    assert not reached.matches({"department": "finance"})


def test_an_owner_who_lost_the_read_runs_nothing_and_is_told_why() -> None:
    """The same automation, the same agent, and an owner who no longer holds the read.

    Delete this and a run would start at a reach holding nothing the task reads and report a quiet
    week, which is the automation that stopped working looking like one that had nothing to say."""
    found = admitted_run(
        an_automation(),
        owner=person(),
        owner_entitlements=holding("read:client.name"),
        agent=an_agent("read:question", "read:client.name"),
        now=NOW,
    )
    assert found is PausedBecause.OWNER_LOST_REACH


def test_an_owner_holding_the_read_through_an_agent_that_does_not_admit_it_runs_nothing() -> None:
    """Asked of the run's reach and not of the owner's own.

    Delete this and a run would be admitted because its owner holds the read, and then read at a
    reach that holds nothing."""
    found = admitted_run(
        an_automation(),
        owner=person(),
        owner_entitlements=holding("read:question"),
        agent=an_agent("read:client.name"),
        now=NOW,
    )
    assert found is PausedBecause.OWNER_LOST_REACH


def test_an_owner_who_has_gone_runs_nothing_whatever_they_still_hold() -> None:
    """A principal the directory no longer holds, and one whose engagement ended before the run.

    Delete this and a leaver's automation would run on grants nobody has revoked yet, which is the
    window `brain.ops.automation_owner` says must not exist."""
    grants = holding("read:question")
    agent = an_agent("read:question")
    assert (
        admitted_run(an_automation(), owner=None, owner_entitlements=grants, agent=agent, now=NOW)
        is PausedBecause.OWNER_GONE
    )
    ended = person(not_after=NOW - timedelta(seconds=1))
    assert (
        admitted_run(
            an_automation(owner=ended), owner=ended, owner_entitlements=grants, agent=agent, now=NOW
        )
        is PausedBecause.OWNER_GONE
    )
    still = person(not_after=LATER)
    assert isinstance(
        admitted_run(
            an_automation(owner=still), owner=still, owner_entitlements=grants, agent=agent, now=NOW
        ),
        run.Admitted,
    )


def test_an_agent_that_is_gone_or_disabled_runs_nothing() -> None:
    """Delete this and an automation would go on running through an agent somebody disabled."""
    grants = holding("read:question")
    for agent in (None, an_agent("read:question", disabled=True)):
        assert (
            admitted_run(
                an_automation(), owner=person(), owner_entitlements=grants, agent=agent, now=NOW
            )
            is PausedBecause.AGENT_UNAVAILABLE
        )


def test_a_task_nothing_performs_runs_nothing() -> None:
    """Delete this and an automation whose task has no performer would be admitted, run nothing
    and be recorded as a success."""
    found = admitted_run(
        an_automation(task="automation.work_summary"),
        owner=person(),
        owner_entitlements=holding("read:question"),
        agent=an_agent("read:question"),
        now=NOW,
    )
    assert found is PausedBecause.TASK_UNBUILT


def test_a_run_handed_somebody_elses_record_or_reach_raises() -> None:
    """Delete this and one person's automation could be admitted at another person's reach."""
    agent = an_agent("read:question")
    with pytest.raises(AutomationRunError, match="entitlements"):
        admitted_run(
            an_automation(),
            owner=person(),
            owner_entitlements=holding("read:question", pid="u_other"),
            agent=agent,
            now=NOW,
        )
    with pytest.raises(AutomationRunError, match="principal record"):
        admitted_run(
            an_automation(),
            owner=person("u_other"),
            owner_entitlements=holding("read:question"),
            agent=agent,
            now=NOW,
        )


# ------------------------------------------------------------------ after a run
def after(outcome: RunOutcome, *, failures_before: int = 0, refused: PausedBecause | None = None):  # type: ignore[no-untyped-def]
    return afterwards(
        an_automation(),
        outcome=outcome,
        refused_because=refused,
        failures_before=failures_before,
        cadence=QUESTIONS.cadence,
        owner_id="u_steward",
        guards=QUESTIONS.guards,
        at=NOW,
    )


def test_a_success_is_scheduled_at_the_cadences_next_instant_after_the_run() -> None:
    """Delete this and a worker down for a week would fire every missed slot one tick apart."""
    found = after(RunOutcome.SUCCEEDED, failures_before=1)
    assert found.paused_because is None
    assert found.next_run_at == next_run_after(QUESTIONS.cadence, NOW)


def test_a_failure_below_the_threshold_is_scheduled_again_and_at_it_pauses_with_a_notice() -> None:
    """One failure is something else being down; the threshold's failure pauses and names it.

    Delete this and one upstream blip would pause every automation, or none would ever pause."""
    first = after(RunOutcome.FAILED, failures_before=FAILURES_BEFORE_PAUSE - 2)
    assert first.paused_because is None
    assert first.next_run_at is not None

    paused = after(RunOutcome.FAILED, failures_before=FAILURES_BEFORE_PAUSE - 1)
    assert paused.next_run_at is None
    assert paused.paused_because is PausedBecause.FAILED_REPEATEDLY
    assert paused.notice is not None
    assert paused.notice.owner_id == "u_steward"
    assert paused.notice.consecutive_failures == FAILURES_BEFORE_PAUSE


def test_a_refused_run_pauses_at_once_with_its_reason() -> None:
    """Delete this and a refused automation would stay scheduled and be refused on every slot."""
    for reason in run.REFUSALS:
        found = after(RunOutcome.REFUSED, refused=reason)
        assert (found.next_run_at, found.paused_because) == (None, reason)
    with pytest.raises(AutomationRunError, match="not a reason"):
        after(RunOutcome.REFUSED, refused=PausedBecause.STOPPED)
    with pytest.raises(AutomationRunError, match="names why"):
        after(RunOutcome.REFUSED)
    with pytest.raises(AutomationRunError, match="names why"):
        after(RunOutcome.SUCCEEDED, refused=PausedBecause.OWNER_GONE)


def test_a_run_with_no_cadence_can_only_be_refused() -> None:
    """Delete this and an automation whose template left the catalogue would be scheduled at an
    instant nothing declared."""
    refused = afterwards(
        an_automation(),
        outcome=RunOutcome.REFUSED,
        refused_because=PausedBecause.TASK_UNBUILT,
        failures_before=0,
        cadence=None,
        owner_id="u_steward",
        guards=QUESTIONS.guards,
        at=NOW,
    )
    assert refused.paused_because is PausedBecause.TASK_UNBUILT
    with pytest.raises(AutomationRunError, match="no cadence"):
        afterwards(
            an_automation(),
            outcome=RunOutcome.SUCCEEDED,
            refused_because=None,
            failures_before=0,
            cadence=None,
            owner_id="u_steward",
            guards=QUESTIONS.guards,
            at=NOW,
        )


def test_the_failure_count_stops_at_the_first_run_that_did_not_fail() -> None:
    """Delete this and a success between two failures would still pause the automation."""
    failed, ok, refused = RunOutcome.FAILED, RunOutcome.SUCCEEDED, RunOutcome.REFUSED
    assert failures_in_a_row([]) == 0
    assert failures_in_a_row([failed, failed, ok, failed]) == 2
    assert failures_in_a_row([ok, failed]) == 0
    assert failures_in_a_row([failed, refused, failed]) == 1


def test_the_threshold_sits_below_the_queues_own_retry_cap_and_the_query_reads_that_far() -> None:
    """Delete this and the count a run reads back could stop short of the threshold, so no
    automation would ever pause."""
    assert run.PAUSE_AFTER >= FAILURES_BEFORE_PAUSE
    assert FAILURES_BEFORE_PAUSE < MAX_ATTEMPTS


# ------------------------------------------------------------------ the record
def test_a_slots_run_id_is_derived_and_the_same_at_any_offset() -> None:
    """Delete this and a slot run twice by two workers would be two rows."""
    one = run_id("auto_one", NOW)
    assert re.fullmatch(table.RUN_ID_PATTERN, one)
    assert run_id("auto_one", NOW.astimezone(timezone(timedelta(hours=-5)))) == one
    assert run_id("auto_one", NOW + timedelta(microseconds=1)) != one
    assert run_id("auto_two", NOW) != one
    with pytest.raises(AutomationRunError, match="naive"):
        run_id("auto_one", NOW.replace(tzinfo=None))


def a_record(**changes: object) -> RunRecord:
    values: dict[str, object] = {
        "run_id": run_id("auto_one", NOW),
        "automation_id": "auto_one",
        "agent_id": AGENT,
        "principal_id": OWNER,
        "due_at": NOW,
        "started_at": NOW,
        "finished_at": NOW,
        "outcome": RunOutcome.SUCCEEDED,
        "result": ("one line",),
    }
    values.update(changes)
    return RunRecord(**values)  # type: ignore[arg-type]


def test_a_run_record_refuses_every_shape_that_says_something_that_did_not_happen() -> None:
    """Delete this and a failed run could carry text, a refused one no reason, or a record another
    slot's id."""
    assert a_record().as_history().principal_id == OWNER
    with pytest.raises(AutomationRunError, match="not the id"):
        a_record(run_id=run_id("auto_one", NOW + timedelta(seconds=1)))
    with pytest.raises(AutomationRunError, match="reason exactly"):
        a_record(outcome=RunOutcome.REFUSED, result=())
    with pytest.raises(AutomationRunError, match="reason exactly"):
        a_record(reason=PausedBecause.OWNER_GONE)
    with pytest.raises(AutomationRunError, match="only a run that succeeded"):
        a_record(outcome=RunOutcome.FAILED)
    with pytest.raises(AutomationRunError, match="before it started"):
        a_record(finished_at=NOW - timedelta(seconds=1))


def test_a_finished_run_is_sent_as_identifiers_and_never_its_result_or_its_person() -> None:
    """Delete this and a webhook subscriber would be handed what the run found, at a reach the
    subscriber never held."""
    event = run_event(a_record())
    assert event.kind is EventKind.AUTOMATION_RUN_FINISHED
    assert event.event_id == event.record_id == a_record().run_id
    assert dict(event.attributes) == {
        "automation_id": "auto_one",
        "agent_id": AGENT,
        "outcome": "succeeded",
    }


# ------------------------------------------------------------------ the tasks
def test_every_template_task_is_declared_once_and_only_those() -> None:
    """Delete this and a template could name a task nothing declares, which no start could refuse
    and every run would pause as unbuilt."""
    assert task_gaps() == ()
    gapped = (*run.TASKS, TaskDeclaration(task="automation.nobody", needs="nothing at all here"))
    assert task_gaps(gapped) == ("'automation.nobody' is declared and no template names it",)
    assert task_gaps(run.TASKS[1:])[0].startswith("'automation.unanswered_questions' is a template")
    assert task_gaps((*run.TASKS, run.TASKS[0]))[0].endswith("is declared twice")


def test_exactly_one_task_reads_and_the_others_say_what_they_need() -> None:
    """Named rather than counted. Delete this and a task could become runnable with no performer
    behind it, or a performer could be quietly unwired."""
    runnable = {one.task for one in run.TASKS if one.runnable}
    assert runnable == {"automation.unanswered_questions"}
    assert task_declaration("automation.unanswered_questions") is not None
    assert task_declaration("automation.nobody") is None
    for one in run.TASKS:
        assert one.runnable or len(one.needs) > 40
    with pytest.raises(AutomationRunError, match="either"):
        TaskDeclaration(task="automation.both", reads=QUESTION_AUTHORITY, needs="something")
    with pytest.raises(AutomationRunError, match="either"):
        TaskDeclaration(task="automation.neither")


def test_the_tables_restated_vocabularies_are_the_domains() -> None:
    """Held against the enums and constants outside the table module. Delete this and the database
    would refuse a reason or an outcome the worker writes, at the moment a run finishes."""
    assert set(table.RUN_OUTCOMES) == {one.value for one in RunOutcome}
    assert (RunOutcome.REFUSED.value, RunOutcome.SUCCEEDED.value) == (
        table.REFUSED,
        table.SUCCEEDED,
    )
    assert set(table.PAUSE_REASONS) == {one.value for one in PausedBecause}
    assert (table.RUN_ID_PREFIX, table.RUN_ID_DIGEST_CHARS) == (
        run.RUN_ID_PREFIX,
        run.RUN_ID_DIGEST_CHARS,
    )
    assert table.STARTED not in table.PAUSE_REASONS
    assert max(len(one) for one in table.SCHEDULE_REASONS) <= table.REASON_CHARS
    assert re.fullmatch(IDENTIFIER, run.RUNNER_ACTOR)
