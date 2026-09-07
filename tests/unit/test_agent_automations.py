"""An agent's automations held to the rules that matter when nobody is watching them run.

Every leaf claimed here is the same leaf as one on the artifacts tab with the person taken
out of it. A person doing the wrong thing gets an odd answer and says so; a flow doing the
wrong thing at four every morning is noticed when a client asks why they were emailed, or
never. So the safety group is not paperwork around a feature: it is the reason the surface
group is shaped the way it is.

Real `Principal`s, real `EntitlementSet`s, the real `Halt` type and the real tier table
throughout, because every rule here is about how two real modules meet. In particular the
tier is read from `brain.memory.tiers` rather than asserted as a number, and the halt is
`brain.ops.halt`'s own rather than a stop button invented for automations, which is the whole
point of both.

Task ids: M39.6.1.1, M39.6.1.2, M39.6.1.4, M39.6.1.5
Task ids: M39.6.2.1, M39.6.2.2, M39.6.2.3, M39.6.2.4
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import (
    CEILING_PRINCIPAL_PREFIX,
    AgentAudience,
    AgentAuthority,
    AgentRecord,
)
from brain.console import agent_automations as automations_module
from brain.console.agent_automations import (
    FAILURES_BEFORE_PAUSE,
    MECHANICS_WORDS,
    MINIMUM_GUARDS,
    SCHEDULE_CAPABILITY,
    SCHEDULE_CHANGE_IS,
    SCHEDULE_SCREEN,
    Automation,
    AutomationRun,
    AutomationSurfaceError,
    OwnerNotice,
    RegistryEntry,
    SchedulerChange,
    automation_gaps,
    automation_reach,
    automations_for,
    failure_pause,
    history,
    may_change_schedule,
    may_see,
    outcome_name_refusals,
    pause,
    register,
    registry_gaps,
    remove,
    resume,
    schedule_basis,
    schedule_change_tier,
)
from brain.console.agent_output import basis_over
from brain.console.screens import screen
from brain.console.workspace import Basis, intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.visibility import Visibility
from brain.memory.tiers import CHANGES_WHAT_ANYBODY_MAY_SEE, Tier
from brain.ops.halt import ENFORCED_AXES, Effect, HaltScope
from brain.ops.jobs import MAX_ATTEMPTS, TERMINAL, JobState, hidden_count_fields

AGENT = "support_triage"
OWNER = "p_owner"
RUNNER = "p_runner"
READER = "p_reader"
NOW = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
NEXT = datetime(2026, 3, 11, 6, 0, tzinfo=UTC)

#: A name that passes every rule in `outcome_name_refusals`, used wherever the name is not
#: what is under test. First person, an outcome, no wiring word and no trigger grammar.
GOOD_NAME = "I file the weekly timesheets"

#: What a registry row says this automation is protecting. Long enough for `MINIMUM_GUARDS`.
GUARDS = "the weekly billing run has nothing to invoice from without it"


def a_principal(principal_id: str, *, kind: PrincipalKind = PrincipalKind.HUMAN) -> Principal:
    """One real principal, named, with an employment that needs no expiry."""
    return Principal(
        id=principal_id,
        kind=kind,
        employment=Employment.STAFF if kind is PrincipalKind.HUMAN else Employment.SERVICE,
        display_name=principal_id,
    )


def holding(*capabilities: str, principal: str = READER) -> EntitlementSet:
    """A caller holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
        ),
    )


def holding_over_agent(agent_id: str, *, principal: str = READER) -> EntitlementSet:
    """A reader whose queue grant is scoped to one agent, and who may open the console."""
    return EntitlementSet(
        principal_id=principal,
        grants=(
            Grant(
                capability=SCHEDULE_CAPABILITY,
                scope=Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value=agent_id),)),
            ),
            Grant(
                capability=Capability(value="read:console.configuration"),
                scope=Scope(clauses=()),
            ),
        ),
    )


def a_record(*capabilities: str) -> AgentRecord:
    """One real agent whose ceiling admits exactly these capabilities."""
    return AgentRecord(
        agent_id=AGENT,
        display_name="Support triage",
        persona="Answers support questions in the house voice.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=OWNER),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by=OWNER,
    )


def an_automation(
    automation_id: str = "auto_1",
    *,
    agent_id: str = AGENT,
    name: str = GOOD_NAME,
    runs_as: str = RUNNER,
    task: str = "file_timesheets",
    next_run_at: datetime | None = NEXT,
) -> Automation:
    """One automation, scheduled unless a test pauses it."""
    return Automation(
        automation_id=automation_id,
        agent_id=agent_id,
        name=name,
        runs_as=a_principal(runs_as),
        task=task,
        next_run_at=next_run_at,
    )


# --- listed under the agent that owns them (M39.6.1.1) ---------------------------------------


def test_an_automation_is_listed_under_the_agent_that_owns_it_and_never_in_a_pile() -> None:
    """**M39.6.1.1.** A global list of scheduled work with an agent filter on it is the pile
    the leaf refuses, because the filter is the part that gets omitted and the page that
    results is every scheduled thing in the company under one heading.

    Ordering is asserted too, because it is what makes the list readable: the thing about to
    happen is at the top, a paused automation sorts last because nothing is about to do it,
    and ties break by id so two readings of an unchanged schedule are the same list.

    Delete this and an agent's tab shows another agent's automations."""
    soon = an_automation("auto_soon", next_run_at=NEXT)
    later = an_automation("auto_later", next_run_at=NEXT + timedelta(days=1))
    paused = an_automation("auto_paused", next_run_at=None)
    elsewhere = an_automation("auto_elsewhere", agent_id="another_agent")
    reader = holding(principal=RUNNER)

    listed = automations_for(AGENT, [later, paused, soon, elsewhere], reader, NOW)

    assert [one.automation_id for one in listed] == ["auto_soon", "auto_later", "auto_paused"]


def test_an_automation_running_as_somebody_else_is_absent_rather_than_hidden() -> None:
    """The strong form: the list a reader gets is byte for byte the list they would get from a
    schedule that never held the others. A placeholder or a gap in an ordering reconstructs
    exactly what was withheld, and what is withheld here is which colleague's name a piece of
    unattended work is spending.

    The positive half is a reader holding the queue grant over this agent, who sees both, so
    this is a narrowing rather than a refusal of everything that is not the reader's.

    Delete this and the tab lists an automation nobody will say whose it is."""
    mine = an_automation("auto_mine", runs_as=RUNNER)
    theirs = an_automation("auto_theirs", runs_as="p_colleague")
    reader = holding(principal=RUNNER)

    with_theirs = automations_for(AGENT, [mine, theirs], reader, NOW)
    without_theirs = automations_for(AGENT, [mine], reader, NOW)
    granted = automations_for(AGENT, [mine, theirs], holding_over_agent(AGENT), NOW)

    assert with_theirs == without_theirs
    assert [one.automation_id for one in with_theirs] == ["auto_mine"]
    assert len(granted) == 2


def test_a_listing_cannot_be_asked_for_without_naming_an_agent() -> None:
    """The shape half of M39.6.1.1, checked through `automation_gaps` against constructed
    signatures as well as against the real one: a scan that can only be pointed at code known
    to be clean is a scan nobody has seen produce a finding.

    Two ways the rule dies and both are covered. An agent id that is not first is a listing
    somebody calls positionally and gets wrong; an agent id with a default is a listing
    somebody calls without one.

    Delete this and `automations_for(entries, reader)` appears as a convenience."""

    def listing_without_an_agent(entries: object, reader: object) -> tuple[()]:
        return ()

    def listing_with_a_default(agent_id: str = "", entries: object = ()) -> tuple[()]:
        return ()

    assert automation_gaps(listing=listing_without_an_agent) != ()
    assert automation_gaps(listing=listing_with_a_default) != ()
    assert any("agent id first" in one for one in automation_gaps(listing=listing_without_an_agent))
    assert any("default" in one for one in automation_gaps(listing=listing_with_a_default))
    assert automation_gaps() == ()


def test_a_reader_with_the_queue_grant_sees_scheduled_work_and_one_without_does_not() -> None:
    """`may_see`'s two branches, each on its own, because a function returning True for the
    principal an automation runs as would pass every test about what it hides.

    The scoped grant is the interesting one: it matches this agent's rows and not another
    agent's, which is what makes a queue grant reviewable rather than total.

    Delete this and the scope stops being evaluated, and a grant over one agent reads the
    whole schedule."""
    here = an_automation("auto_1", runs_as="p_colleague")
    elsewhere = an_automation("auto_2", agent_id="another_agent", runs_as="p_colleague")
    scoped = holding_over_agent(AGENT)

    assert may_see(here, scoped) is True
    assert may_see(elsewhere, scoped) is False
    assert may_see(here, holding(principal="p_colleague")) is True
    assert may_see(here, holding(principal=READER)) is False


# --- named as outcomes in the first person (M39.6.1.2) ---------------------------------------


def test_an_automation_is_named_as_an_outcome_in_the_first_person() -> None:
    """**M39.6.1.2.** The list is read by the person answerable for what the agent does,
    deciding whether each automation should still exist, and that decision needs the outcome
    and nothing else. "When a form is submitted, create a ticket" cannot be judged by them at
    all, so the honest response is to leave it alone, which is how an automation nobody wants
    survives three reviews.

    Four refusals and one acceptance, and the acceptance is what stops this being satisfied by
    a function that refuses everything.

    Delete this and the list fills with the canvas's own vocabulary."""
    assert outcome_name_refusals(GOOD_NAME) == ()
    assert outcome_name_refusals("I chase unpaid invoices every Monday") == ()

    assert outcome_name_refusals("Files the weekly timesheets") != ()
    assert outcome_name_refusals("I do it") != ()
    assert outcome_name_refusals("I call the webhook with the ticket") != ()
    assert outcome_name_refusals("When a form arrives, I then create a ticket") != ()


def test_the_wiring_words_and_the_trigger_grammar_are_both_refused_and_are_different() -> None:
    """Two separate ways a name describes the plumbing, and a check for one misses the other.
    "I notify the client after the run completes" carries no wiring word and is still an
    outcome; "When a ticket arrives, I create a task" carries none either and is pure trigger
    and action.

    The word match is on whole words, so `onboarding` is not `on` and `posted` is not `post`:
    a substring check would refuse half the honest names anybody writes.

    Delete this and one of the two checks is quietly removed as redundant."""
    assert "webhook" in MECHANICS_WORDS
    assert any("webhook" in one for one in outcome_name_refusals("I fire the webhook nightly"))
    assert outcome_name_refusals("I onboard each new client the day they sign") == ()

    trigger = outcome_name_refusals("When a ticket arrives, I create a task for it")
    assert any("trigger and an action" in one for one in trigger)


def test_an_automation_cannot_be_constructed_with_a_name_that_breaks_those_rules() -> None:
    """The refusal is on the type rather than only in a helper, so the rule cannot be got
    round by not calling the helper. A screen that assembled an `Automation` directly would
    otherwise put a trigger-and-action name on the owner's list.

    The positive half is the fixture every other test in this file uses, which is constructed
    the same way.

    Delete this and `outcome_name_refusals` becomes advisory."""
    with pytest.raises(AutomationSurfaceError, match="named badly"):
        an_automation(name="Create a ticket when a form is submitted")

    assert an_automation().name == GOOD_NAME


# --- a named principal, never the agent (M39.6.2.1) ------------------------------------------


def test_an_automation_runs_on_a_named_principal_and_never_on_the_agent_itself() -> None:
    """**M39.6.2.1.** Running as the agent is one fewer thing to configure and it is the one
    arrangement nobody can undo: revocation here is the deletion of a grant from a principal,
    and an agent's ceiling is not a principal's grants, so there is no row anybody could
    delete to stop it.

    Both spellings are refused, and the second is the one somebody writes by accident:
    `brain.agents.model.CEILING_PRINCIPAL_PREFIX` is what an entitlement ceiling calls itself,
    so a ceiling set handed in as the principal arrives with that prefix on it.

    A service principal is accepted, because `brain.core.principal.PrincipalKind.SERVICE`
    exists for scheduled work and is still a named thing with grants somebody can revoke.

    Delete this and an automation outlives the person who set it up, with a reach nobody can
    narrow."""
    with pytest.raises(AutomationSurfaceError, match="the agent it belongs to"):
        an_automation(runs_as=AGENT)
    with pytest.raises(AutomationSurfaceError, match="the agent it belongs to"):
        an_automation(runs_as=f"{CEILING_PRINCIPAL_PREFIX}{AGENT}")

    service = Automation(
        automation_id="auto_1",
        agent_id=AGENT,
        name=GOOD_NAME,
        runs_as=a_principal("svc_billing", kind=PrincipalKind.SERVICE),
        task="file_timesheets",
        next_run_at=NEXT,
    )

    assert service.runs_as.kind is PrincipalKind.SERVICE
    assert an_automation().runs_as.id == RUNNER

    # And a next run with no timezone on it, which is the other way an automation ends up
    # firing at a time nobody chose: `brain.ops.retention.expires_at` refuses a naive instant
    # for the same reason, and a schedule is wrong by the host's offset from UTC either way.
    with pytest.raises(AutomationSurfaceError, match="naive instant"):
        an_automation(next_run_at=datetime(2026, 3, 11, 6, 0))


def test_what_an_automation_reaches_is_its_principals_grants_narrowed_by_the_ceiling() -> None:
    """`E(principal) intersect agent_ceiling`, by `brain.ops.automation.flow_reach`, which is
    the same intersection the gate uses. It is not the reader's reach and it is not the
    ceiling.

    Both directions are asserted, because a reach that took the union rather than the
    intersection would pass a test that only checked the principal narrowed the agent. The
    third case is the one that matters most: a principal holding nothing reaches nothing
    through an agent whose ceiling admits everything, which is the ceiling conferring nothing.

    Delete this and an automation's reach becomes the ceiling, which belongs to nobody."""
    record = a_record("read:client.name", "read:client.contract_value")
    wide = automation_reach(
        holding("read:client.name", "read:client.contract_value", principal=RUNNER), record
    )
    narrow = automation_reach(holding("read:client.name", principal=RUNNER), record)
    nothing = automation_reach(holding(principal=RUNNER), record)
    outside = automation_reach(holding("read:ticket.internal_note", principal=RUNNER), record)

    assert wide.holds(Capability(value="read:client.contract_value"))
    assert not narrow.holds(Capability(value="read:client.contract_value"))
    assert narrow.holds(Capability(value="read:client.name"))
    assert nothing.grants == ()
    assert outside.grants == ()
    assert wide.principal_id == RUNNER


def test_this_surface_intersects_no_entitlement_sets_of_its_own() -> None:
    """The invariant's structural half, the same check `brain.console.workspace` and
    `brain.console.workspace_capabilities` make of themselves. Every reach here comes from
    `flow_reach`, which calls the one `EntitlementSet.intersect` there is.

    Delete this and a helper here starts narrowing a reach, and the copy that is subtly wrong
    is the one running at four in the morning with nobody reading the output."""
    assert intersections_in(inspect.getsource(automations_module)) == ()


# --- the registry (M39.6.2.4) ----------------------------------------------------------------


def test_every_automation_appears_in_the_registry_with_what_it_guards() -> None:
    """**M39.6.2.4.** The registry is what somebody reviewing scheduled work reads, and a row
    with no statement of what it guards is a row that gets disabled during an incident and
    never restored, or left running after the thing it protected has gone.

    The row is derived from the automation rather than assembled beside it, so it cannot
    describe a schedule the automation does not have, and the prose is required to the same
    length `brain.ops.halt` requires of a reason, imported rather than chosen.

    Delete this and `guards=""` is accepted, and the registry becomes a list of task names."""
    one = an_automation()

    row = register(one, guards=GUARDS)

    assert (row.automation_id, row.agent_id, row.task) == (one.automation_id, AGENT, one.task)
    assert (row.runs_as_id, row.next_run_at) == (RUNNER, NEXT)
    assert row.guards == GUARDS
    assert MINIMUM_GUARDS == 12

    with pytest.raises(AutomationSurfaceError, match="what it guards"):
        register(one, guards="too short")


def test_the_registry_reports_work_it_does_not_list_and_schedules_nothing_owns() -> None:
    """Both directions, and the second is the one that still fires. An automation with no row
    is scheduled work nothing lists. A row with no automation is a schedule nothing owns:
    somebody removed the automation and left the entry, and the task keeps running on a
    principal whose reason for holding grants has gone.

    The third and fourth findings are M39.6.1.5's property checked after the fact: a row whose
    next run or whose principal disagrees with the automation's is the two halves having been
    written separately.

    Delete this and the two records drift, and the one that fires is the registry."""
    one = an_automation()
    matching = register(one, guards=GUARDS)

    assert registry_gaps([one], [matching]) == ()
    assert any("no registry row" in gap for gap in registry_gaps([one], []))
    assert any("nothing owns" in gap for gap in registry_gaps([], [matching]))

    stale_time = RegistryEntry(
        automation_id=one.automation_id,
        agent_id=AGENT,
        task=one.task,
        runs_as_id=RUNNER,
        next_run_at=NEXT + timedelta(days=7),
        guards=GUARDS,
    )
    wrong_principal = RegistryEntry(
        automation_id=one.automation_id,
        agent_id=AGENT,
        task=one.task,
        runs_as_id="p_somebody_else",
        next_run_at=NEXT,
        guards=GUARDS,
    )

    assert any("written separately" in gap for gap in registry_gaps([one], [stale_time]))
    assert any("wrong principal" in gap for gap in registry_gaps([one], [wrong_principal]))


# --- pause, resume and remove (M39.6.1.5) ----------------------------------------------------


def test_pausing_resuming_and_removing_move_the_automation_and_the_registry_together() -> None:
    """**M39.6.1.5.** Nothing here opens a transaction, so what "in the same transaction"
    means at this layer is that the shape it exists to prevent cannot be built:
    `SchedulerChange` carries both halves and refuses one without the other.

    Paused is the absence of a next run rather than a flag, which is
    `brain.ops.jobs.SCHEDULING_IS_A_TIMESTAMP_AND_NOT_A_STATE` inverted: a `paused` boolean
    beside a timestamp is a row where the screen and the scheduler read different halves.

    Delete this and a pause writes the automation and leaves the registry row firing."""
    one = an_automation()

    stopped = pause(one, guards=GUARDS)
    started = resume(stopped.after or one, next_run_at=NEXT, guards=GUARDS)
    gone = remove(one)

    assert stopped.after is not None
    assert stopped.entry is not None
    assert stopped.after.next_run_at is None
    assert stopped.after.paused is True
    assert stopped.entry.next_run_at is None

    assert started.after is not None
    assert started.entry is not None
    assert started.after.next_run_at == NEXT
    assert started.after.paused is False
    assert started.entry.next_run_at == NEXT

    assert (gone.after, gone.entry) == (None, None)
    assert gone.before is one


def test_a_change_that_moves_one_half_and_not_the_other_is_refused() -> None:
    """The failure the type exists to prevent, provoked from both sides. An automation removed
    with its registry row left behind is a schedule that keeps firing; a registry row removed
    with the automation left behind is work that runs and appears in no review.

    A row describing a different automation is refused too, because a change assembled by hand
    somewhere else in the console would otherwise pair the two silently.

    Delete this and the constructor accepts a half-written change."""
    one = an_automation()
    row = register(one, guards=GUARDS)

    with pytest.raises(AutomationSurfaceError, match="one side only"):
        SchedulerChange(before=one, after=one, entry=None)
    with pytest.raises(AutomationSurfaceError, match="one side only"):
        SchedulerChange(before=one, after=None, entry=row)

    other = an_automation("auto_2")
    with pytest.raises(AutomationSurfaceError, match="different automation"):
        SchedulerChange(before=one, after=other, entry=register(other, guards=GUARDS))
    with pytest.raises(AutomationSurfaceError, match="does not describe"):
        SchedulerChange(before=one, after=pause(one, guards=GUARDS).after, entry=row)


def test_a_paused_flag_is_not_a_field_an_automation_could_carry() -> None:
    """The state of a schedule lives in one place. A `paused` column beside `next_run_at` is
    two facts that can disagree, and the screen reads the one that says it is stopped.

    Checked through `automation_gaps` with a constructed type as well as against the real one,
    so the refusal has been seen to fire.

    Delete this and `Automation.enabled` arrives with the next screen that wanted a toggle."""

    @dataclass(frozen=True)
    class WithAFlag:
        automation_id: str
        paused: bool

    assert automation_gaps(automation_type=WithAFlag) != ()
    assert any("second place" in one for one in automation_gaps(automation_type=WithAFlag))
    assert automation_gaps() == ()
    assert not {one.name for one in dataclass_fields(Automation)} & {
        "paused",
        "enabled",
        "active",
    }


# --- run history (M39.6.1.4) -----------------------------------------------------------------


def test_a_history_shows_the_last_result_and_the_next_scheduled_time() -> None:
    """**M39.6.1.4.** Both halves, because either alone is unreadable: the last result with no
    next time cannot say whether anything is going to change, and a next time with no last
    result cannot say whether it will work.

    Newest first, and `last` is the newest rather than the newest successful one: a screen
    reporting the last success beside a failing automation is the screen that hides the
    failure.

    Delete this and the history arrives in whatever order the store iterated."""
    one = an_automation()
    older = AutomationRun(
        automation_id="auto_1",
        at=NOW - timedelta(days=2),
        state=JobState.SUCCEEDED,
        principal_id=RUNNER,
    )
    newer = AutomationRun(
        automation_id="auto_1",
        at=NOW - timedelta(days=1),
        state=JobState.FAILED,
        principal_id=RUNNER,
    )
    elsewhere = AutomationRun(
        automation_id="auto_2", at=NOW, state=JobState.SUCCEEDED, principal_id=RUNNER
    )

    told = history(
        one, [older, newer, elsewhere], holding(principal=RUNNER), basis=Basis.OWN, now=NOW
    )

    assert [run.at for run in told.runs] == [newer.at, older.at]
    assert told.last is newer
    assert told.next_run_at == NEXT


def test_a_paused_automation_shows_no_next_time_and_still_shows_what_it_did() -> None:
    """The half of M39.6.1.4 that a flag would break. A paused automation displaying a next
    run is a screen saying it will run, and the history is exactly what the person deciding
    whether to resume it needs.

    Delete this and the tab shows a time for something nothing will pick up."""
    stopped = an_automation(next_run_at=None)
    ran = AutomationRun(
        automation_id="auto_1", at=NOW, state=JobState.DEAD_LETTER, principal_id=RUNNER
    )

    told = history(stopped, [ran], holding(principal=RUNNER), basis=Basis.OWN, now=NOW)

    assert told.next_run_at is None
    assert told.last is ran


def test_a_history_of_somebody_elses_runs_needs_the_grant_the_queue_screen_needs() -> None:
    """The `brain.console.workspace.Basis` rule applied here: a figure that moves when
    somebody else works may not be a shortcut past the screen that shows it. Whose runs are
    counted is decided by whether the reader could open the queue screen and read them there.

    Both bases are asserted over the same rows, so this is a narrowing rather than two
    different queries, and the label is carried alongside because a figure whose meaning is
    unstated is read as the whole.

    Delete this and the wider basis becomes the default, and an automation's history on a
    shared agent is a record of a colleague's week."""
    one = an_automation(runs_as=RUNNER)
    mine = AutomationRun(
        automation_id="auto_1", at=NOW, state=JobState.SUCCEEDED, principal_id=READER
    )
    theirs = AutomationRun(
        automation_id="auto_1",
        at=NOW - timedelta(days=1),
        state=JobState.FAILED,
        principal_id=RUNNER,
    )
    reader = holding_over_agent(AGENT)

    everyone = history(one, [mine, theirs], reader, basis=Basis.EVERYONE, now=NOW)
    own = history(one, [mine, theirs], reader, basis=Basis.OWN, now=NOW)

    assert (len(everyone.runs), everyone.basis) == (2, Basis.EVERYONE)
    assert (len(own.runs), own.basis) == (1, Basis.OWN)
    assert own.runs[0].principal_id == READER


def test_an_automation_the_reader_holds_nothing_for_has_no_history_at_all() -> None:
    """Visibility first, then the basis. A history attributed to an automation the reader may
    not see would confirm the automation exists, whatever it said about the runs.

    The positive half is above, so this is not passing because history is always empty.

    Delete this and the run list becomes a way of asking which automations an agent has."""
    one = an_automation(runs_as="p_colleague")
    ran = AutomationRun(
        automation_id="auto_1", at=NOW, state=JobState.SUCCEEDED, principal_id="p_colleague"
    )

    told = history(one, [ran], holding(principal=READER), basis=Basis.EVERYONE, now=NOW)

    assert told.runs == ()
    assert told.last is None
    assert told.next_run_at is None


def test_a_run_that_has_not_finished_is_not_history() -> None:
    """A list headed "what this did" containing something still running is how a reader
    concludes something finished that has not, and the terminal states are read off
    `brain.ops.jobs.TERMINAL` rather than listed here, so a new edge in that table moves this
    without anybody remembering to.

    The positive half is every other test in this section, all of which build terminal runs.

    Delete this and a queued job appears in a history as a result."""
    assert JobState.RUNNING not in TERMINAL
    assert JobState.DEAD_LETTER in TERMINAL

    with pytest.raises(AutomationSurfaceError, match="has not"):
        AutomationRun(automation_id="auto_1", at=NOW, state=JobState.RUNNING, principal_id=RUNNER)


def test_the_schedule_basis_is_the_same_rule_pointed_at_the_queue_screen() -> None:
    """`schedule_basis` is `brain.console.agent_output.basis_over` with one screen key, and
    the key is the registry's own rather than a capability spelled again here. Two spellings
    stop agreeing the day one moves, and the permissive one wins.

    Asserted over four reaches, including the one holding the capability and not the plane,
    because that is where a check written as one condition rather than two diverges.

    Delete this and this surface grows its own idea of whose figures a reader may see."""
    assert screen(SCHEDULE_SCREEN).read.requires == SCHEDULE_CAPABILITY
    assert SCHEDULE_CAPABILITY.value == "read:queue"

    for reach in (
        holding(),
        holding("read:queue"),
        holding("read:queue", "read:console.configuration"),
        holding("read:console.content"),
    ):
        assert schedule_basis(reach) is basis_over(SCHEDULE_SCREEN, reach)

    assert schedule_basis(holding("read:queue", "read:console.configuration")) is Basis.EVERYONE
    assert schedule_basis(holding("read:queue")) is Basis.OWN


# --- schedule changes are gated (M39.6.2.2) --------------------------------------------------


def test_a_schedule_change_is_a_tier_three_learning_event_and_needs_a_person() -> None:
    """**M39.6.2.2.** Nothing about a run changes when its schedule moves except how much of
    it happens with nobody present, which is what a leash is. The classification is read from
    `brain.memory.tiers` rather than restated, so lowering it is one edit in one place.

    The member is pinned twice: at `Tier.GATED` and inside `CHANGES_WHAT_ANYBODY_MAY_SEE`.
    That second set is deliberately not derived from the tier table in that module, so a
    constant repointed at a tier-one change fails on both counts rather than moving both sides
    of one comparison together.

    Delete this and a schedule moves on nobody's approval."""
    assert schedule_change_tier() is Tier.GATED
    assert SCHEDULE_CHANGE_IS in CHANGES_WHAT_ANYBODY_MAY_SEE

    one = an_automation()

    assert may_change_schedule(one, becomes=NEXT, approved_by=OWNER) is True
    assert may_change_schedule(one, becomes=NEXT, approved_by="") is False
    assert may_change_schedule(one, becomes=NEXT, approved_by="   ") is False
    assert may_change_schedule(one, becomes=NEXT, approved_by=RUNNER) is False


def test_stopping_a_schedule_needs_no_approval_and_starting_one_does() -> None:
    """The asymmetry `brain.ops.halt.THE_GUARDED_ACT_IS_RESUME_AND_NEVER_STOP` states about
    the stop button, at this level. A fail-safe direction with paperwork on it is a direction
    nobody can take during the incident that needs it, and the cost of a wrong stop is work
    that has to be restarted while the cost of a wrong start is the thing carrying on.

    Delete this and pausing a misbehaving automation needs a second person at three in the
    morning."""
    one = an_automation()

    assert may_change_schedule(one, becomes=None, approved_by="") is True
    assert may_change_schedule(one, becomes=NEXT, approved_by="") is False


# --- failure pauses the automation and tells the owner (M39.6.2.3) ---------------------------


def test_an_automation_that_keeps_failing_is_paused_and_its_owner_told() -> None:
    """**M39.6.2.3.** Both halves as one value, so there is no call site at which the pause is
    written and the notice is dropped. A pause nobody was told about is an automation that
    quietly stopped, and the work it was doing simply did not happen.

    Below the threshold nothing happens, which is the positive half: one failure is usually
    something else being down, and pausing on it turns every upstream blip into work that
    silently did not run.

    Delete this and an automation pauses itself in silence."""
    one = an_automation()

    assert (
        failure_pause(
            one,
            consecutive_failures=FAILURES_BEFORE_PAUSE - 1,
            owner_id=OWNER,
            at=NOW,
            guards=GUARDS,
            declared_by=OWNER,
        )
        is None
    )

    stopped = failure_pause(
        one,
        consecutive_failures=FAILURES_BEFORE_PAUSE,
        owner_id=OWNER,
        at=NOW,
        guards=GUARDS,
        declared_by=OWNER,
    )

    assert stopped is not None
    assert stopped.change.after is not None
    assert stopped.change.after.next_run_at is None
    assert stopped.change.entry is not None
    assert stopped.change.entry.next_run_at is None
    assert stopped.notice.owner_id == OWNER
    assert stopped.notice.consecutive_failures == FAILURES_BEFORE_PAUSE
    assert "paused" in stopped.notice.render()


def test_the_pause_threshold_is_below_the_retries_a_single_run_already_gets() -> None:
    """The figure pinned against something outside itself, which is what stops a test
    comparing a constant with itself. A run that has failed has already exhausted its own
    retries, so a threshold at or above `brain.ops.jobs.MAX_ATTEMPTS` would be more unattended
    repetitions of a failing side effect than the queue permits for one job. And it is above
    one, because a single failure is usually something else being down.

    Delete this and the threshold drifts upwards, which is the direction it always drifts:
    somebody is annoyed by a pause and raises it."""
    assert FAILURES_BEFORE_PAUSE < MAX_ATTEMPTS
    assert FAILURES_BEFORE_PAUSE > 1


def test_the_owner_notice_has_no_field_that_could_switch_it_off_and_names_no_failure() -> None:
    """`brain.console.reads.StewardNotice`'s construction applied here. A notification about
    work that stopped happening is the one turned off first when a dashboard is noisy, and it
    is the one that matters most a fortnight later.

    The absence of a failure message is the other half, and it is
    `brain.ops.jobs.DeadLetter`'s rule: text from a failing run is somebody's data copied onto
    an operational surface with a different retention on it.

    Delete this and `OwnerNotice.severity` arrives, and then a filter on it."""
    names = {one.name for one in dataclass_fields(OwnerNotice)}

    assert names == {"owner_id", "automation_id", "agent_id", "consecutive_failures", "at"}
    assert not names & {"enabled", "quiet", "severity", "suppressed", "message", "error"}
    assert not {one.name for one in dataclass_fields(AutomationRun)} & {"error", "message"}

    with pytest.raises(AutomationSurfaceError, match="addressed to nobody"):
        OwnerNotice(
            owner_id="",
            automation_id="auto_1",
            agent_id=AGENT,
            consecutive_failures=FAILURES_BEFORE_PAUSE,
            at=NOW,
        )
    with pytest.raises(AutomationSurfaceError, match="below the threshold"):
        OwnerNotice(
            owner_id=OWNER,
            automation_id="auto_1",
            agent_id=AGENT,
            consecutive_failures=0,
            at=NOW,
        )


def test_the_halt_a_pause_builds_is_the_systems_own_and_stops_nothing_today() -> None:
    """The reuse and the honesty in one test. Stopping what is already running is
    `brain.ops.halt`, not a second switch invented here, and the halt carries both effects
    because refusing new work while a forty-minute run keeps writing is that module's first
    lie.

    And it stops nothing today, which is reported rather than implied.
    `brain.ops.halt.ENFORCED_AXES` holds `EVERYTHING` and `CONNECTOR` only, because
    `brain.ops.admission.decide` is handed a connector and nothing else, so a halt scoped to
    an agent is in force in the store and refuses no request anywhere. `automation_gaps` says
    so by running `halt_gaps`, rather than this module keeping its own copy of which axes are
    consulted.

    Delete this and the console reports an automation as stopped while its current run
    finishes writing, with nothing anywhere saying the halt was inert."""
    stopped = failure_pause(
        an_automation(),
        consecutive_failures=FAILURES_BEFORE_PAUSE,
        owner_id=OWNER,
        at=NOW,
        guards=GUARDS,
        declared_by=OWNER,
    )

    assert stopped is not None
    assert stopped.halt.scope is HaltScope.AGENT
    assert stopped.halt.target == AGENT
    assert stopped.halt.effects == frozenset({Effect.REFUSE_NEW, Effect.SIGNAL_RUNNING})

    assert HaltScope.AGENT not in ENFORCED_AXES
    found = automation_gaps(halts=[stopped.halt])
    assert any("axis nothing consults" in one for one in found)
    assert automation_gaps() == ()


def test_no_figure_on_this_surface_could_be_a_count_of_what_was_withheld() -> None:
    """The field-name check `brain.ops.jobs.hidden_count_fields` exists for, asked of every
    type this surface hands a reader. The failure arrives as a field somebody adds to make a
    screen more useful, and it arrives with one of a small set of names on it.

    **And the check is exercised with a type that has one**, which the first version of this
    test did not do: asking `automation_gaps` about a clean surface passes whether or not it
    asks `hidden_count_fields` anything, and a mutation removing that call survived exactly
    because of it.

    Delete this and `History.total` reads like an improvement."""

    @dataclass(frozen=True)
    class WithATotal:
        runs: int
        total: int

    assert hidden_count_fields(automations_module.AUTOMATION_SURFACE) == ()
    assert not {one.name for one in dataclass_fields(automations_module.History)} & {
        "total",
        "hidden",
        "omitted",
    }
    assert any("not shown" in one for one in automation_gaps(surface=[WithATotal]))
    assert automation_gaps() == ()
