"""Work with nobody present: the reach resolved at the run, and the ways it stops.

Every rule here is a consequence of one difference. A person doing the wrong thing gets an
odd answer and says so; a schedule doing the wrong thing at four every morning is noticed
when a client asks why they were emailed, or never. So the tests below are about the two
directions that failure takes: a reach that widened and nobody saw, and an automation that
stopped and nobody was told.

Real `EntitlementSet`s and the real `brain.gate.leash` approval maximum throughout, because
the bounds here are only defensible against something outside this module.

Task ids: M17.4.1, M17.4.2, M17.4.3, M17.4.4, M17.4.5, M17.4.6
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.agents.model import CEILING_PRINCIPAL_PREFIX
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.leash import MAX_APPROVAL_WINDOW
from brain.ops.jobs import JobState
from brain.orchestration.unattended import (
    TEMPLATES,
    ApprovalStep,
    CostedRun,
    ExpiredApproval,
    OutcomeTemplate,
    Suspension,
    Trigger,
    TriggerKind,
    UnattendedError,
    UnattendedRun,
    approval_refusals,
    expire,
    from_template,
    history,
    missing_capabilities,
    run_reach,
    suspension_for,
    unattended_gaps,
)

NOW = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
FILE = Capability(value="write:timesheet.status")
READ = Capability(value="read:client.name")
DAILY = timedelta(days=1)


def _reach(
    principal_id: str, *capabilities: Capability, scope: Scope | None = None
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=one, scope=scope or Scope()) for one in capabilities),
    )


def _ceiling(
    agent_id: str, *capabilities: Capability, scope: Scope | None = None
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=f"{CEILING_PRINCIPAL_PREFIX}{agent_id}",
        grants=tuple(Grant(capability=one, scope=scope or Scope()) for one in capabilities),
    )


def _template(**overrides: object) -> OutcomeTemplate:
    fields: dict[str, object] = {
        "template_id": "t-timesheets",
        "outcome": "I file each week's timesheets on Friday",
        "trigger": Trigger(kind=TriggerKind.SCHEDULE, every=DAILY),
        "task": "file_timesheets",
        "requires": (FILE,),
    }
    fields.update(overrides)
    return OutcomeTemplate(**fields)  # type: ignore[arg-type]


def _run(**overrides: object) -> UnattendedRun:
    return from_template(
        _template(**{k: v for k, v in overrides.items() if k in {"trigger", "requires"}}),
        automation_id=str(overrides.get("automation_id", "a-1")),
        principal_id=str(overrides.get("principal_id", "p-ana")),
        agent_id=str(overrides.get("agent_id", "timesheet_helper")),
    )


# ------------------------------------------------------------------ triggers (M17.4.1)
def test_there_are_three_trigger_kinds_and_none_of_them_asks_a_model():
    """The question an auditor asks is what can happen without a person, and the answer has
    to be readable rather than assembled.

    Asserted as the exact set, so a fourth kind added later fails here rather than passing a
    test written against one of the three.

    Delete this and a member deciding for itself when to run could be added, which is a
    second and ungoverned runtime with a schedule in front of it."""
    assert {one.value for one in TriggerKind} == {"schedule", "connector_event", "webhook"}


@pytest.mark.parametrize(
    ("kind", "field", "value"),
    [
        (TriggerKind.SCHEDULE, "every", DAILY),
        (TriggerKind.CONNECTOR_EVENT, "connector", "xero"),
        (TriggerKind.WEBHOOK, "endpoint", "e-9"),
    ],
)
def test_a_trigger_needs_exactly_the_field_its_kind_uses(kind, field, value):
    """Both directions, per kind. Missing, and nothing decides when it fires; spare, and a
    field reads on a screen as applying while nothing evaluates it.

    Delete this and a webhook trigger could carry a cadence, which the approval-window rule
    would then measure against, or a schedule could carry none and never fire."""
    assert Trigger(kind=kind, **{field: value}).kind is kind

    with pytest.raises(UnattendedError, match="and has none"):
        Trigger(kind=kind)

    spare: dict[str, Any] = {"every": DAILY, "connector": "xero", "endpoint": "e-9"}
    spare.pop(field)
    spare[field] = value
    with pytest.raises(UnattendedError, match="which nothing about this kind evaluates"):
        Trigger(kind=kind, **spare)


def test_a_cadence_of_nothing_is_refused():
    """A schedule of zero runs continuously or never, and neither is a cadence.

    Delete this and an approval window would be compared against zero, which refuses every
    approval on that automation with a message about the window."""
    with pytest.raises(UnattendedError, match="neither is a cadence"):
        Trigger(kind=TriggerKind.SCHEDULE, every=timedelta(0))


def test_only_a_schedule_has_a_cadence():
    """An event or a webhook trigger has no interval for an approval to outlive, so the
    check has to say so rather than treat a missing interval as an infinite one.

    Delete this and every approval on a webhook automation would be refused, or every one
    would be admitted, depending on which way the missing value was read."""
    assert Trigger(kind=TriggerKind.SCHEDULE, every=DAILY).cadence == DAILY
    assert Trigger(kind=TriggerKind.WEBHOOK, endpoint="e-9").cadence is None
    assert Trigger(kind=TriggerKind.CONNECTOR_EVENT, connector="xero").cadence is None


# ------------------------------------------------------------------ templates (M17.4.2)
def test_an_automation_is_installed_from_a_named_outcome_and_has_nowhere_to_draw_a_canvas():
    """M17.4.2 read as a shape: what a person configures is which outcome they want, and the
    wiring is not theirs to assemble.

    Delete this and a step list could be added to an automation, which is a second and
    ungoverned way to say what happens, on the surface that runs with nobody watching."""
    run = _run()

    assert run.template_id == "t-timesheets"
    assert "steps" not in UnattendedRun.__dataclass_fields__
    assert unattended_gaps() == ()


def test_the_catalogue_is_empty_and_an_entry_is_still_validated():
    """A set of common automations is a set of outcomes somebody at a particular company
    wants, and a list of them in this source would ship to every company that installs the
    product and read as a recommendation.

    What is here is the shape a catalogue entry has to take, so a catalogue supplied as
    configuration goes through the same constructor.

    Delete this and either the catalogue fills up with one company's outcomes or the shape
    stops being checked."""
    assert TEMPLATES == ()

    with pytest.raises(UnattendedError, match="tells whoever is installing it nothing"):
        _template(outcome="files")
    with pytest.raises(UnattendedError, match="requires nothing"):
        _template(requires=())


def test_installing_copies_the_requirement_rather_than_referring_to_the_template():
    """A reference would be tidier and would mean a change to a shared catalogue silently
    altering the conditions under which twenty schedules stop.

    Delete this and editing a template would change what live automations need without
    anybody reinstalling them."""
    template = _template()
    run = from_template(
        template, automation_id="a-1", principal_id="p-ana", agent_id="timesheet_helper"
    )

    assert run.requires == template.requires
    assert run.requires is not None


# ------------------------------------------------------- the reach at the run (M17.4.3)
def test_the_reach_is_resolved_from_the_live_set_handed_in_at_the_run():
    """`brain.ops.automation.flow_reach`, the one wrapper over the one intersection, with
    the principal's set supplied at the moment of the run.

    Delete this and nothing says what an unattended run reaches, and the next reader has
    only a docstring."""
    principal = _reach("p-ana", FILE, READ)
    ceiling = _ceiling(
        "timesheet_helper",
        FILE,
        scope=Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),)),
    )

    reach = run_reach(principal, ceiling)

    assert {one.capability.value for one in reach.grants} == {FILE.value}
    assert reach.principal_id == "p-ana"


def test_two_runs_of_one_automation_resolve_differently_when_a_grant_is_deleted():
    """Revocation in this system is the deletion of a grant, so an automation carrying a
    stored reach would be the one place a revocation does not take effect.

    Delete this and a cached reach would look correct on every test that resolves it
    once."""
    ceiling = _ceiling("timesheet_helper", FILE, READ)

    monday = run_reach(_reach("p-ana", FILE, READ), ceiling)
    friday = run_reach(_reach("p-ana", READ), ceiling)

    assert monday.holds(FILE)
    assert not friday.holds(FILE)


def test_an_automation_has_no_field_that_could_hold_a_reach_except_its_declared_requirement():
    """The check is `brain.ops.jobs.reach_carrying_fields`, the same one that keeps a queue
    row honest, and the single exemption is named and can be removed.

    A declared requirement is the opposite of a stored reach: it is only ever the left
    operand of a `holds` check against a freshly resolved set, so a stale one can only stop
    a run rather than widen it.

    Delete this and a `reach` field could be added to an automation, cached at configuration
    time, and every run in between two sweeps would use the old answer."""
    assert unattended_gaps() == ()

    unexempted = unattended_gaps(requirement_fields=frozenset())
    assert len(unexempted) == 1
    assert "UnattendedRun.requires" in unexempted[0]


def test_run_reach_cannot_see_the_automation_at_all():
    """**The structural half of the exemption above.** A requirement cannot widen a reach
    because the function that computes the reach has no parameter one could arrive through,
    which is `brain.agents.model.audience_scope`'s construction.

    Delete this and the argument for the exemption becomes a promise about how a field is
    used rather than a property of a signature."""
    parameters = inspect.signature(run_reach).parameters

    assert list(parameters) == ["principal", "agent_ceiling"]
    assert all("EntitlementSet" in str(one.annotation) for one in parameters.values())


def test_an_automation_running_as_its_own_agent_is_refused():
    """Revocation is the deletion of a grant from a principal and an agent has none, so
    there would be no row anybody could delete to stop it.

    Delete this and the tidiest way to configure an automation becomes the one arrangement
    nobody can undo."""
    with pytest.raises(UnattendedError, match="nothing could ever stop it"):
        UnattendedRun(
            automation_id="a-1",
            template_id="t-1",
            principal_id="timesheet_helper",
            agent_id="timesheet_helper",
            trigger=Trigger(kind=TriggerKind.SCHEDULE, every=DAILY),
            requires=(FILE,),
        )


@pytest.mark.parametrize("blank", ["", " "])
def test_an_automation_missing_an_identifier_is_refused(blank):
    """Whitespace as well as the empty string, because a strip-free check admits a space and
    a run with a principal of " " spends nobody's grants.

    Delete this and an automation could be scheduled with nothing to attribute it to."""
    with pytest.raises(UnattendedError, match="cannot be scheduled"):
        UnattendedRun(
            automation_id=blank,
            template_id="t-1",
            principal_id="p-ana",
            agent_id="timesheet_helper",
            trigger=Trigger(kind=TriggerKind.SCHEDULE, every=DAILY),
            requires=(FILE,),
        )


def test_an_automation_requiring_nothing_is_refused():
    """No loss of reach would ever stop it, which is the failure the whole suspension rule
    exists to prevent, arriving by configuration rather than by revocation.

    Delete this and the safest-looking automation to write is the one nothing can stop."""
    with pytest.raises(UnattendedError, match="requires nothing"):
        UnattendedRun(
            automation_id="a-1",
            template_id="t-1",
            principal_id="p-ana",
            agent_id="timesheet_helper",
            trigger=Trigger(kind=TriggerKind.SCHEDULE, every=DAILY),
            requires=(),
        )


# ------------------------------------------------------------------ suspension (M17.4.4)
def test_a_lost_requirement_stops_the_automation_rather_than_narrowing_it():
    """**The rule most likely to be built the other way.** Narrowing fails safe for a person
    and silently for a schedule: the automation goes on running every morning, writing a
    partial version of what it used to write.

    Delete this and an automation whose principal moved department would keep firing at
    whatever reach was left."""
    run = _run()
    ceiling = _ceiling("timesheet_helper", FILE, READ)

    lost = suspension_for(run, run_reach(_reach("p-ana", READ), ceiling), at=NOW)

    assert lost is not None
    assert lost.missing == (FILE,)
    assert lost.automation_id == "a-1"


def test_narrowing_that_does_not_touch_a_requirement_leaves_it_running():
    """The positive half. A rule tested only by its stops is satisfied by one that stops
    everything, and that turns the mechanism into the thing people switch off.

    Delete this and every ordinary narrowing would suspend every automation."""
    run = _run()
    ceiling = _ceiling("timesheet_helper", FILE)

    assert suspension_for(run, run_reach(_reach("p-ana", FILE, READ), ceiling), at=NOW) is None


def test_a_requirement_the_agent_ceiling_removes_stops_it_too():
    """Asked of the reach rather than of the principal's raw grants, because the requirement
    is about what the run can do and the run is the intersection.

    Delete this and an automation would go on firing because a grant was technically still
    there while the agent's ceiling had stopped admitting it, and nothing would stop it."""
    run = _run()
    narrowed = _ceiling("timesheet_helper", READ)

    lost = suspension_for(run, run_reach(_reach("p-ana", FILE, READ), narrowed), at=NOW)

    assert lost is not None
    assert lost.missing == (FILE,)


def test_the_suspension_notice_names_the_automation_and_no_capability():
    """The owner of the agent and the principal it runs as need not be the same person, and
    one person's grants are not the other's business. A count of missing capabilities is a
    count of grants somebody used to hold.

    Delete this and a schedule stopping would tell whoever happens to own the agent what
    somebody else lost."""
    run = _run(automation_id="weekly_filing", requires=(FILE, READ))
    lost = suspension_for(run, run_reach(_reach("p-ana"), _ceiling("h", FILE, READ)), at=NOW)

    assert lost is not None
    assert len(lost.missing) == 2
    rendered = lost.render()

    assert "weekly_filing" in rendered
    assert FILE.value not in rendered
    assert READ.value not in rendered
    # No digit at all, so the count of what somebody lost cannot be read off the sentence.
    assert not any(character.isdigit() for character in rendered)


def test_a_suspension_with_nothing_missing_is_refused():
    """A record of something that did not happen. `missing_capabilities` returns an empty
    tuple in the healthy case, so a caller that built a suspension unconditionally would
    produce one.

    Delete this and a suspension could be recorded for an automation that is running."""
    with pytest.raises(UnattendedError, match="nothing missing"):
        Suspension(automation_id="a-1", principal_id="p-ana", missing=(), at=NOW)
    with pytest.raises(UnattendedError, match="no timezone"):
        Suspension(
            automation_id="a-1",
            principal_id="p-ana",
            missing=(FILE,),
            at=datetime(2026, 9, 8, 4, 0),
        )


def test_missing_capabilities_reports_in_name_order():
    """Two readings of one suspension produce the same list, which is what lets a record be
    compared with the same automation checked again.

    Delete this and the order would follow the declaration, and two identical suspensions
    would look different."""
    run = _run(requires=(FILE, READ))

    missing = missing_capabilities(run, _reach("p-ana"))

    assert missing == (READ, FILE)


# ------------------------------------------------------------------ approvals (M17.4.5)
def test_an_approval_window_over_the_platform_maximum_is_refused():
    """`brain.gate.leash.MAX_APPROVAL_WINDOW` imported rather than chosen again: an approval
    that can stand indefinitely is a standing grant with extra steps, and that does not stop
    being true because the run is on a schedule.

    Delete this and this module would grow its own maximum, and the copy that drifted would
    be the one governing the runs nobody is watching."""
    run = _run(trigger=Trigger(kind=TriggerKind.WEBHOOK, endpoint="e-9"))
    step = ApprovalStep(
        step_id="ap-1", automation_id="a-1", window=MAX_APPROVAL_WINDOW + timedelta(minutes=1)
    )

    refusals = approval_refusals(run, (step,))

    assert len(refusals) == 1
    assert "platform maximum" in refusals[0]


def test_an_approval_window_at_or_over_the_cadence_is_refused():
    """**The bound that only exists because nobody is watching.** Two runs waiting at once
    means approving the older one executes arguments computed from a state that has moved,
    and a person cannot reach that on the request path because they do not ask the same
    question again while the first is still pending.

    Delete this and a daily automation could hold a twenty-four hour approval window, which
    is exactly one stale approval per day."""
    run = _run()
    over = ApprovalStep(step_id="ap-1", automation_id="a-1", window=DAILY)
    under = ApprovalStep(step_id="ap-2", automation_id="a-1", window=DAILY - timedelta(minutes=1))

    assert approval_refusals(run, (under,)) == ()

    refusals = approval_refusals(run, (over,))
    assert len(refusals) == 1
    assert "runs every" in refusals[0]


def test_a_webhook_automation_has_no_cadence_for_an_approval_to_outlive():
    """The positive half of the cadence rule. Treating a missing interval as an infinite one
    would refuse every approval on every webhook automation, and treating it as zero would
    refuse them all the other way.

    Delete this and either reading would pass, because the only test would be about a
    schedule."""
    run = _run(trigger=Trigger(kind=TriggerKind.CONNECTOR_EVENT, connector="xero"))
    step = ApprovalStep(step_id="ap-1", automation_id="a-1", window=MAX_APPROVAL_WINDOW)

    assert approval_refusals(run, (step,)) == ()


def test_a_step_belonging_to_another_automation_is_refused():
    """The cadence bound is computed from this automation's trigger, so a step checked
    against the wrong one is checked against the wrong number.

    Delete this and a weekly automation's step could be validated against a daily
    automation's cadence and admitted."""
    run = _run()
    step = ApprovalStep(step_id="ap-1", automation_id="a-2", window=timedelta(minutes=5))

    refusals = approval_refusals(run, (step,))

    assert len(refusals) == 1
    assert "another automation's cadence" in refusals[0]


def test_a_step_that_gives_nobody_time_to_answer_is_refused():
    """It expires the moment it is raised, so the run stops every time and the automation
    reads as broken rather than as misconfigured.

    Delete this and a zero window would look like a working automation that never
    completes."""
    with pytest.raises(UnattendedError, match="gives nobody any time"):
        ApprovalStep(step_id="ap-1", automation_id="a-1", window=timedelta(0))


def test_an_expired_approval_stops_the_run_and_there_is_no_third_answer():
    """A default action on timeout reads as robustness and is a side effect with nobody's
    name on it; skipping the step produces a run that reports success having done less than
    it says. `expire` returns the stop or nothing, and there is nowhere to express either
    alternative.

    Delete this and somebody adding a timeout action would find nothing in the way."""
    step = ApprovalStep(step_id="ap-1", automation_id="a-1", window=timedelta(hours=1))

    still_open = expire(step, raised_at=NOW, now=NOW + timedelta(minutes=59))
    stopped = expire(step, raised_at=NOW, now=NOW + timedelta(hours=1))

    assert still_open is None
    assert isinstance(stopped, ExpiredApproval)
    assert stopped.expires_at == NOW + timedelta(hours=1)
    assert "Nothing after that step happened." in stopped.render()
    assert set(ExpiredApproval.__dataclass_fields__) == {
        "step_id",
        "automation_id",
        "raised_at",
        "expires_at",
    }


def test_an_expiry_before_it_was_raised_is_refused():
    """Nobody was ever able to answer it, so a record of it expiring says something that did
    not happen.

    Delete this and a clock moving backwards between two hosts would produce a stop nobody
    could have prevented, reported as though somebody had failed to act."""
    with pytest.raises(UnattendedError, match="ever able to answer"):
        ExpiredApproval(
            step_id="ap-1", automation_id="a-1", raised_at=NOW, expires_at=NOW - timedelta(hours=1)
        )
    with pytest.raises(UnattendedError, match="naive"):
        ExpiredApproval(
            step_id="ap-1",
            automation_id="a-1",
            raised_at=datetime(2026, 9, 8, 4, 0),
            expires_at=NOW,
        )


# ------------------------------------------------------------------ history (M17.4.6)
def _costed(automation_id: str, minutes: int, minor: int) -> CostedRun:
    return CostedRun(
        automation_id=automation_id,
        at=NOW + timedelta(minutes=minutes),
        principal_id="p-ana",
        state=JobState.SUCCEEDED,
        minor=minor,
        seconds=4.0,
    )


def test_a_history_is_this_automations_finished_runs_newest_first_with_what_each_cost():
    """Filtered by automation before anything else, so a history can never be assembled from
    another automation's runs, and ordered so two readings of an unchanged history match.

    Delete this and a screen headed "what this did" could show another schedule's runs, and
    the cost line would be somebody else's."""
    runs = (_costed("a-1", 0, 30), _costed("a-2", 5, 999), _costed("a-1", 10, 40))

    found = history("a-1", runs)

    assert [one.minor for one in found.runs] == [40, 30]
    assert found.last is not None
    assert found.last.minor == 40
    assert found.total_minor == 70
    assert found.mean_minor == 35.0


def test_a_run_still_in_flight_is_not_history():
    """Only terminal states, read off `brain.ops.jobs.TERMINAL` rather than listed here.
    Putting a running job in a list headed "what this did" is how a reader concludes
    something finished that has not.

    Delete this and the cost line would report a partial figure as a final one."""
    with pytest.raises(UnattendedError, match="has not finished"):
        CostedRun(
            automation_id="a-1",
            at=NOW,
            principal_id="p-ana",
            state=JobState.RUNNING,
            minor=10,
            seconds=1.0,
        )


def test_a_run_that_cost_nothing_is_still_recorded():
    """A refused or failed run is recorded at what it cost, which may be nothing. Dropping
    the zero rows would make an automation that stopped working look like one that became
    cheap, and a falling cost line is the shape somebody reads as good news.

    Delete this and the history could filter on cost, and the runs worth investigating are
    exactly the ones it would drop."""
    found = history("a-1", (_costed("a-1", 0, 0), _costed("a-1", 5, 20)))

    assert len(found.runs) == 2
    assert found.total_minor == 20
    assert found.mean_minor == 10.0


def test_an_empty_history_reports_zero_rather_than_nothing():
    """A screen showing a dash where a number goes is read as a fault.

    Delete this and the mean would divide by zero on the first day of an automation's
    life."""
    found = history("a-1", ())

    assert found.runs == ()
    assert found.last is None
    assert found.total_minor == 0
    assert found.mean_minor == 0.0


def test_a_negative_or_undated_run_is_refused():
    """A negative figure makes the total smaller than the runs that produced it, and a naive
    timestamp cannot be ordered against one from another host.

    Delete this and a correction posted as a negative row would hide the cost of a run."""
    with pytest.raises(UnattendedError, match="negative figure"):
        CostedRun(
            automation_id="a-1",
            at=NOW,
            principal_id="p-ana",
            state=JobState.SUCCEEDED,
            minor=-1,
            seconds=1.0,
        )
    with pytest.raises(UnattendedError, match="no timezone"):
        CostedRun(
            automation_id="a-1",
            at=datetime(2026, 9, 8, 4, 0),
            principal_id="p-ana",
            state=JobState.SUCCEEDED,
            minor=1,
            seconds=1.0,
        )


# ------------------------------------------------------------------------- the diagnostic
def test_unattended_gaps_reports_a_canvas_a_hidden_count_and_a_stored_reach():
    """All three findings, and the healthy surface beside them, because a diagnostic that
    can only be run against the healthy tree has nothing to report on today's data and every
    one of its refusals survives a mutation.

    Delete this and the checks could each stop reporting anything, which is indistinguishable
    from a clean surface."""

    @dataclass(frozen=True)
    class Drifted:
        automation_id: str
        steps: tuple[str, ...]
        hidden: int
        reach: EntitlementSet

    assert unattended_gaps() == ()

    findings = unattended_gaps(surface=(Drifted,), run_type=Drifted)

    assert any("Drifted.reach" in one for one in findings)
    assert any("Drifted.hidden" in one for one in findings)
    assert any("Drifted.steps is a canvas" in one for one in findings)


def test_a_template_that_requires_nothing_is_refused_once_and_not_twice():
    """The constructor refuses it, so `unattended_gaps` deliberately does not check it again:
    two enforcement points for one rule means the second is unreachable, which is the mistake
    `brain.connectors.projection.ProjectedEntity` records having made and removed.

    Delete this and somebody would add the second check back, and a guard audit would report
    it as an unreachable branch with no explanation of why."""
    with pytest.raises(UnattendedError, match="requires nothing"):
        _template(requires=())

    assert "templates" not in inspect.signature(unattended_gaps).parameters


@pytest.mark.parametrize("blank", ["", " "])
def test_an_approval_step_with_no_id_is_refused(blank):
    """A step nobody can name cannot be raised, found again or expired, so the run waits on
    something no console can show and no timeout can reach.

    Whitespace as well as the empty string, because a strip-free check admits a space and a
    step called " " reads on a screen as a step with a name.

    Delete this and `approval_refusals` would compare an unnamed step against an
    automation's cadence and report findings nobody can act on."""
    with pytest.raises(UnattendedError, match="cannot be raised"):
        ApprovalStep(step_id=blank, automation_id="a-1", window=timedelta(hours=1))


@pytest.mark.parametrize("blank", ["", " "])
def test_a_template_with_no_id_or_no_task_is_refused(blank):
    """A template with no id cannot be installed and one with no task schedules nothing.

    Whitespace as well as the empty string, for the same reason as above: a catalogue
    supplied as configuration is exactly where a field ends up holding a space.

    Delete this and a configuration file with a blank row would install an automation that
    fires and runs nothing, which reads in a history as a run that succeeded."""
    with pytest.raises(UnattendedError, match="cannot be installed or scheduled"):
        _template(template_id=blank)
    with pytest.raises(UnattendedError, match="cannot be installed or scheduled"):
        _template(task=blank)
