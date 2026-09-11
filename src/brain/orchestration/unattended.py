"""Work that runs with nobody present, and the reach it runs at each time.

**An automation is the one place a widened reach goes unnoticed for a week.** A person
doing the wrong thing gets an odd answer and says so within the hour. A schedule doing the
wrong thing at four every morning is noticed when a client asks why they were emailed, or
never. Every rule in this module follows from that single difference, and each one is
written as a shape rather than as a habit, because a habit is what nobody is present to
keep.

**The reach is resolved when the run happens and there is nowhere to store it.**
`brain.ops.checkpoints.ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT` already says this for saved
graph state and `brain.ops.jobs.A_JOB_CARRIES_A_PRINCIPAL_AND_NEVER_A_REACH` says it for a
queue row; this is the same sentence for a schedule, and it is imported rather than
restated. What is added here is the structural half for an automation:
`UnattendedRun` has no field whose type could hold a permission decision, which
`unattended_gaps` asks of the class by way of `brain.ops.jobs.reach_carrying_fields` rather
than of a reviewer, and `run_reach` takes the owner's live set as an argument at the moment
of the run. A configuration written in March and a run in September resolve differently,
and the September answer is the correct one: revocation in this system is the deletion of a
grant, so a stored reach would be the one place a revocation does not take effect.

`brain.console.agent_automations.automation_reach` is the console's one-line call to the
same `brain.ops.automation.flow_reach`, for the same purpose at the other end of the
system. Two callers of one wrapper is not two implementations, and it is worth saying so
plainly because the alternative reads as duplication: what that function answers is what a
reader may be shown about an automation's reach, and what this one answers is what the run
is actually handed. Both call `flow_reach`, neither intersects anything, and
`tests/invariants/test_single_implementation.py` pins every intersection call site in
`src/brain` exactly, so a third way to compute this would fail there rather than here.

**Losing a required capability suspends the automation rather than narrowing it.** This is
the rule most likely to be built the other way, because narrowing is what the platform does
everywhere else and it fails safe. It fails safe for a person, who sees a smaller answer and
asks. It fails silently for a schedule: an automation whose owner moved department goes on
running every morning against whatever is left of its reach, writing a partial version of
what it used to write, and nothing distinguishes that from a quiet week. So a required
capability is declared, checked at each run, and its absence stops the run. See
`A_NARROWED_AUTOMATION_IS_A_SILENT_ONE`.

**An approval step has a window, and the window is bounded by the cadence as well as by the
maximum.** `brain.gate.leash.MAX_APPROVAL_WINDOW` is the platform's ceiling and is imported.
The second bound is this module's and it only exists because nobody is watching: an approval
window longer than the interval between runs means two runs are waiting at once, and
approving the older one executes arguments computed from a state that has since moved. That
is the same failure `SuspendedAction.ent_hash` exists to catch on the request path, arriving
by a route the request path cannot take because a person does not ask the same question
twice while the first is still pending. See `AN_APPROVAL_MAY_NOT_OUTLIVE_THE_CADENCE`.

**An expired approval stops the run and does not skip the step.** There is no member, no
field and no parameter anywhere here that could express "carry on without it", which is the
whole of `AN_EXPIRED_APPROVAL_STOPS_THE_RUN`. The tempting alternative is a default action
on timeout, which reads as robustness and is a side effect with nobody's name on it.

**A trigger is one of three kinds and the set is closed.** Schedule, connector event,
webhook, and nothing that asks a model when to run. The closed set is what makes "nobody
present" enumerable: every way this system starts work unattended is a member of one enum,
so the question "what can run without a person" has an answer somebody can read. A fourth
kind deciding for itself would be a second, ungoverned runtime, which is the argument
`brain.ops.automation.StepKind` makes in the same words about a canvas that could branch on
a model's answer.

**A template is a named outcome, and there is nowhere to draw a canvas.** `UnattendedRun`
has no step list, no graph and no expression field, and `from_template` is the only
producer of one. That is M17.4.2 read as a shape: what a person configures is which outcome
they want, and the wiring is not theirs to assemble. The catalogue of outcomes is
deliberately not here and `TEMPLATES` is empty, for the reason
`brain.console.agent_automations` gives about its own gallery: a set of common automations
is a set of outcomes somebody at a particular company wants, and a list of them in this
source would be exactly the company detail CLAUDE.md says never goes into it.

**Cost per run is the asker's own figure and the total is the sum of what is shown.**
`RunHistory.total_minor` is computed from the rows rather than carried beside them, so it
cannot disagree with them, and there is no field for a count of runs withheld;
`brain.ops.jobs.hidden_count_fields` is the check and it is imported rather than restated.

Rejected: a `reach` field on `UnattendedRun`, cached at configuration time and refreshed by
a sweep. It is the obvious optimisation, it removes a lookup from every run, and it is the
stored permission decision this whole module is built to refuse. The sweep is the part that
sounds like it closes the gap and does not: between two sweeps the automation runs at the
old answer, and the window is exactly as long as whatever interval somebody chose.

Rejected: a default action when an approval expires. See above.

Rejected: expressing the required capabilities as the automation's ceiling. A ceiling and a
requirement are opposite things: a ceiling is the most a run may do and an empty one means
it does nothing, while a requirement is the least it needs and an empty one means it needs
nothing. One field for both would make an empty value mean two opposite things, and the
one it would mean in practice is whichever the first caller assumed.

Scope: domain logic. Nothing here schedules anything, opens a connection or reads a clock;
`now` and `at` are parameters for the reason `brain.ops.limits` gives about policy that owns
a client. No automation described here has ever run, and since 2026-09-11 there is one
reason rather than two: M32.4.1.1 installed a queue driver, so there is something to run an
automation on, and there is still no scheduler in this repository to start one.

Task ids: M17.4.1, M17.4.2, M17.4.3, M17.4.4, M17.4.5, M17.4.6
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.leash import MAX_APPROVAL_WINDOW
from brain.ops.automation import flow_reach
from brain.ops.checkpoints import ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT
from brain.ops.jobs import TERMINAL, JobState, hidden_count_fields, reach_carrying_fields

# ------------------------------------------------------------------ written-down reasons
#: Why a lost capability stops an automation instead of narrowing it.
A_NARROWED_AUTOMATION_IS_A_SILENT_ONE: Final = (
    "Narrowing is what this platform does everywhere else and it fails safe for a person: "
    "they see a smaller answer and ask why. It fails silently for a schedule. An automation "
    "whose principal moved department goes on running every morning against what is left of "
    "its reach, writing a partial version of what it used to write, and a partial version "
    "of a weekly filing is indistinguishable from a quiet week. So an automation declares "
    "what it cannot do without, that requirement is checked against the live reach at each "
    "run, and its absence stops the run rather than shrinking it."
)

#: Why an approval window is bounded by the cadence and not only by the platform maximum.
AN_APPROVAL_MAY_NOT_OUTLIVE_THE_CADENCE: Final = (
    "An approval window longer than the interval between runs puts two runs in the queue at "
    "once, and approving the older one executes arguments computed from a state that has "
    "moved since. brain.gate.leash.SuspendedAction carries an ent_hash to catch exactly "
    "that on the request path, and a person cannot reach it there because nobody asks the "
    "same question again while the first is still pending. A schedule does, every morning, "
    "without being asked. So the window is bounded twice: by the platform maximum, which is "
    "about how long an approval may stand at all, and by the cadence, which is about how "
    "many of them may stand together."
)

#: Why there is no action on timeout.
AN_EXPIRED_APPROVAL_STOPS_THE_RUN: Final = (
    "A default action when nobody answers reads as robustness and is a side effect with "
    "nobody's name on it: the approval existed because somebody had to decide, and a "
    "timeout that decides is the approval not existing. Skipping the step is worse again, "
    "because the run then completes and reports success having done less than it says. So "
    "an expired approval stops the run, and there is no member, field or parameter anywhere "
    "here in which the other two could be expressed."
)

#: Why a declared requirement is not the stored reach `reach_carrying_fields` is looking for.
A_REQUIREMENT_IS_NOT_A_REACH: Final = (
    "brain.ops.jobs.reach_carrying_fields reports any field whose type could hold a "
    "permission decision, and Capability is one of the four names it matches. A declared "
    "requirement is the opposite of a stored reach and the difference is which way it can "
    "move an answer: a stored EntitlementSet is what a run may do, so a stale one widens; a "
    "requirement is what a run must have, it is only ever the left operand of a holds check "
    "against a freshly resolved reach, and a stale one can only stop a run that would "
    "otherwise have gone ahead. The guarantee is structural rather than a promise about how "
    "the field is used: run_reach takes a principal's set and a ceiling and has no "
    "parameter an UnattendedRun could arrive through, so a requirement cannot reach the "
    "computation of the reach at all. brain.agents.model.audience_scope is the same "
    "construction, and the exemption is named here rather than assumed for the reason "
    "tests/invariants/test_single_implementation.py names its known second renderer."
)

#: Why the set of trigger kinds is closed.
EVERY_WAY_WORK_STARTS_UNATTENDED_IS_IN_ONE_ENUM: Final = (
    "The question an auditor asks about a system like this is what can happen without a "
    "person, and the answer has to be readable rather than assembled. Three kinds, in one "
    "closed enum, is that answer: a clock, a change at a source, and a call from outside. "
    "There is no member for a model deciding when to run, and its absence is the mechanism "
    "rather than a policy, which is the construction brain.ops.automation.StepKind uses to "
    "make agent control flow on a canvas unsayable."
)


class UnattendedError(Exception):
    """An automation described in a shape that would run wrongly with nobody watching.

    Outside the `brain.core.errors` taxonomy, like the rest of this package: nobody asking a
    question ever sees one.
    """


# ------------------------------------------------------------------ triggers (M17.4.1)
class TriggerKind(enum.StrEnum):
    """Every way work starts here with nobody present. See
    `EVERY_WAY_WORK_STARTS_UNATTENDED_IS_IN_ONE_ENUM`."""

    #: A clock. The only kind with a cadence, and therefore the only one an approval window
    #: can be measured against.
    SCHEDULE = "schedule"
    #: A change at a source we already hold a connection to.
    CONNECTOR_EVENT = "connector_event"
    #: A call from outside, at an endpoint somebody was given.
    WEBHOOK = "webhook"


@dataclass(frozen=True)
class Trigger:
    """What starts one automation, and the one field its kind needs.

    Three optional fields and a rule that exactly the right one is set, rather than three
    classes: an automation table has one trigger column and a hierarchy would need a
    discriminator anyway. The refusal is what matters and it goes in both directions, which
    is `brain.agents.model.AgentAudience`'s construction for a department that belongs only
    at the department level. A field set on the wrong kind is not harmless: it reads on a
    screen as something that applies and nothing evaluates it.
    """

    kind: TriggerKind
    #: SCHEDULE only. How often it runs.
    every: timedelta | None = None
    #: CONNECTOR_EVENT only. Which source, in `brain.connectors`' own vocabulary.
    connector: str = ""
    #: WEBHOOK only. Which endpoint the call arrives at.
    endpoint: str = ""

    def __post_init__(self) -> None:
        needed = {
            TriggerKind.SCHEDULE: "every",
            TriggerKind.CONNECTOR_EVENT: "connector",
            TriggerKind.WEBHOOK: "endpoint",
        }[self.kind]
        present = {
            "every": self.every is not None,
            "connector": bool(self.connector.strip()),
            "endpoint": bool(self.endpoint.strip()),
        }
        if not present[needed]:
            msg = (
                f"a {self.kind} trigger needs {needed!r} and has none, so nothing decides "
                "when it fires and it either never runs or runs on whatever a default is"
            )
            raise UnattendedError(msg)
        spare = sorted(name for name, given in present.items() if given and name != needed)
        if spare:
            msg = (
                f"a {self.kind} trigger carries {spare}, which nothing about this kind "
                "evaluates; a field that reads on a screen as applying and is never "
                "consulted is worse than an absent one"
            )
            raise UnattendedError(msg)
        if self.every is not None and self.every <= timedelta(0):
            msg = f"a schedule of {self.every} runs continuously or never, and neither is a cadence"
            raise UnattendedError(msg)

    @property
    def cadence(self) -> timedelta | None:
        """The interval between runs, or None when this kind has none.

        Named separately from `every` because the approval-window rule asks a question about
        the *kind* rather than about the field: an event or a webhook trigger has no cadence
        at all, so there is no interval for an approval to outlive, and the check has to say
        so rather than treat a missing interval as an infinite one.

        **No branch on the kind, deliberately.** The constructor above already refuses a
        cadence on any kind but a schedule, so a conditional here would be a second
        enforcement point for one rule and an unreachable one: a mutation switching it off
        changes nothing observable, which is how a branch nobody can reach survives an audit
        looking like a gap in the tests. `brain.connectors.projection.ProjectedEntity`
        records making and removing the same mistake. The property is a name for the
        guarantee, and the guarantee is tested where it is enforced.
        """
        return self.every


# ------------------------------------------------------------------ templates (M17.4.2)
#: How short a named outcome may be. An outcome needs a verb and an object; below this it is
#: a label. Deliberately the same bound `brain.console.agent_automations.MINIMUM_OUTCOME_NAME`
#: applies to the name a reader sees, and the two are separate constants on purpose: that one
#: is about what an owner can judge on a screen, and this is about what a template is.
MINIMUM_OUTCOME: Final = 12


@dataclass(frozen=True)
class OutcomeTemplate:
    """A named outcome somebody may install, and what running it needs (M17.4.2).

    **There is no step list here and nowhere to put one.** That is the leaf read as a shape:
    what a person configures is which outcome they want, and the wiring is not theirs to
    assemble. A canvas is `brain.ops.automation`'s subject, it is deterministic plumbing, and
    it is deliberately a different thing from an agent doing something on a schedule.

    `requires` is the least this outcome needs, never a ceiling. See the rejected note in the
    module docstring: a ceiling and a requirement are opposite, and one field for both would
    make an empty value mean two opposite things.
    """

    template_id: str
    #: What it does, as an outcome rather than as wiring.
    outcome: str
    trigger: Trigger
    #: The registered task it runs, in `brain.ops.queue`'s vocabulary.
    task: str
    #: What the principal must hold at every run, or the run stops.
    requires: tuple[Capability, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("template_id", self.template_id),
            ("task", self.task),
        ):
            if not value.strip():
                msg = f"an outcome template with no {label} cannot be installed or scheduled"
                raise UnattendedError(msg)
        if len(self.outcome.strip()) < MINIMUM_OUTCOME:
            msg = (
                f"template {self.template_id!r} states {self.outcome!r} as its outcome, "
                "which tells whoever is installing it nothing about what it will do"
            )
            raise UnattendedError(msg)
        if not self.requires:
            msg = (
                f"template {self.template_id!r} requires nothing, so no loss of reach ever "
                f"stops it. {A_NARROWED_AUTOMATION_IS_A_SILENT_ONE}"
            )
            raise UnattendedError(msg)


#: The outcomes on offer. Empty, deliberately, and it is not an omission.
#:
#: A set of common automations is a set of outcomes somebody at a particular company wants,
#: and a list of them in this source would be exactly the company detail CLAUDE.md says
#: never goes into it: it would ship to every company that installs this product and read as
#: a recommendation. `brain.console.agent_automations` declined its own gallery leaf on the
#: same grounds. What is here is the shape a catalogue entry has to take, so that a
#: catalogue supplied as configuration is validated by the same constructor.
TEMPLATES: Final[tuple[OutcomeTemplate, ...]] = ()


# ------------------------------------------------------------- the automation (M17.4.3)
@dataclass(frozen=True)
class UnattendedRun:
    """One automation, as the thing that decides what a run may reach sees it.

    **No field here could hold a reach**, and that is asked of the class rather than
    promised: `unattended_gaps` runs `brain.ops.jobs.reach_carrying_fields` over it, which is
    the same check that keeps a queue row honest and is imported rather than written again.
    See `ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT`.

    **No step list either.** See `OutcomeTemplate`: an automation is installed from a named
    outcome, and `from_template` is the only producer.

    `principal_id` is who it runs as. It is a bare identifier rather than a `Principal`,
    because what this module needs is a name to resolve a reach against at run time and
    carrying the object would invite somebody to read grants off it that were current when
    the automation was written.
    """

    automation_id: str
    template_id: str
    #: The person or service principal whose grants each run spends.
    principal_id: str
    #: The agent this belongs to, which is the lens the reach is narrowed by.
    agent_id: str
    trigger: Trigger
    #: What the principal must hold at every run. Copied from the template so a template
    #: edited afterwards does not silently change what a live automation needs.
    requires: tuple[Capability, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("automation_id", self.automation_id),
            ("principal_id", self.principal_id),
            ("agent_id", self.agent_id),
        ):
            if not value.strip():
                msg = (
                    f"an automation with no {label} cannot be scheduled, suspended or "
                    "attributed, and a run with no principal spends nobody's grants"
                )
                raise UnattendedError(msg)
        if self.principal_id.strip() == self.agent_id.strip():
            msg = (
                f"automation {self.automation_id!r} runs as {self.principal_id!r}, which is "
                "the agent it belongs to; revocation here is the deletion of a grant from a "
                "principal and an agent has none, so nothing could ever stop it"
            )
            raise UnattendedError(msg)
        if not self.requires:
            msg = (
                f"automation {self.automation_id!r} requires nothing, so no loss of reach "
                f"ever stops it. {A_NARROWED_AUTOMATION_IS_A_SILENT_ONE}"
            )
            raise UnattendedError(msg)


def from_template(
    template: OutcomeTemplate, *, automation_id: str, principal_id: str, agent_id: str
) -> UnattendedRun:
    """Install a named outcome as an automation (M17.4.2). The only producer of one.

    Copies the requirement rather than referring to the template, so that editing a template
    afterwards cannot change what a live automation needs without somebody reinstalling it.
    A reference would be tidier and would mean a change to a shared catalogue silently
    altering the conditions under which twenty schedules stop.
    """
    return UnattendedRun(
        automation_id=automation_id,
        template_id=template.template_id,
        principal_id=principal_id,
        agent_id=agent_id,
        trigger=template.trigger,
        requires=template.requires,
    )


def run_reach(principal: EntitlementSet, agent_ceiling: EntitlementSet) -> EntitlementSet:
    """What this run may touch, resolved now from the principal's live grants (M17.4.3).

    `brain.ops.automation.flow_reach`, which is the one wrapper over the one
    `EntitlementSet.intersect`. There is no arithmetic in this function and no cache in front
    of it: the argument is the live set, resolved by whoever is starting the run, and the
    answer is good for this run only.

    Two runs of one automation can therefore reach different things, and both answers are
    right at the moment they are given. Narrowing between them is the guarantee, because
    revocation here is the deletion of a grant. Widening is the same rule read the other way
    and is harmless, because the principal is entitled to it now. See
    `ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT`, which says this for a checkpoint and a queue
    row in the same words.
    """
    return flow_reach(principal, agent_ceiling)


# ------------------------------------------------------------------ suspension (M17.4.4)
def missing_capabilities(
    run: UnattendedRun, reach: EntitlementSet, now: datetime | None = None
) -> tuple[Capability, ...]:
    """Which of this automation's requirements the reach no longer covers, in name order.

    Asked of the reach rather than of the principal's raw grants, because the requirement is
    about what the run can do and the run is the intersection: a capability the principal
    still holds and the agent's ceiling no longer admits is just as absent from the run, and
    an automation that went on firing because the grant was technically still there would be
    stopped by nothing at all.
    """
    return tuple(
        sorted(
            (one for one in run.requires if not reach.holds(one, now)),
            key=lambda one: one.value,
        )
    )


@dataclass(frozen=True)
class Suspension:
    """One automation stopped because its run can no longer do what it needs (M17.4.4).

    Carries the capabilities, which is safe and is the point: they are the automation's own
    declared requirements, written down when it was installed and readable by anybody who
    can see the automation. What is *not* here is anything about the principal's other
    grants, what they used to hold, or when it changed, and `render` names none of them
    either: the sentence an agent's owner reads says what stopped and never what somebody
    lost, because the owner of the agent and the principal it runs as need not be the same
    person and one person's grants are not the other's business.
    """

    automation_id: str
    principal_id: str
    #: The declared requirements the run no longer covers.
    missing: tuple[Capability, ...]
    at: datetime

    def __post_init__(self) -> None:
        if not self.missing:
            msg = (
                f"automation {self.automation_id!r} is reported as suspended with nothing "
                "missing, which is a record of something that did not happen"
            )
            raise UnattendedError(msg)
        if self.at.tzinfo is None:
            msg = f"the suspension of {self.automation_id!r} is dated with no timezone"
            raise UnattendedError(msg)

    def render(self) -> str:
        """The sentence an agent's owner reads. Names what stopped and nothing about anybody.

        No count and no capability. A count of missing capabilities is a count of grants
        somebody used to hold, which is a fact about a person offered to whoever happens to
        own the agent.
        """
        return (
            f"{self.automation_id} has stopped: the account it runs as can no longer do "
            "everything it needs. Nothing it does is happening until somebody looks."
        )


def suspension_for(
    run: UnattendedRun, reach: EntitlementSet, *, at: datetime, now: datetime | None = None
) -> Suspension | None:
    """Stop this automation if its run can no longer do what it declared it needs (M17.4.4).

    `None` when everything is held, which is the positive half: an automation whose reach
    narrowed in a way that does not touch its requirements goes on running, because
    narrowing is normal and stopping on every change would make the mechanism the thing
    people switch off.

    Stops rather than narrows. See `A_NARROWED_AUTOMATION_IS_A_SILENT_ONE`.
    """
    missing = missing_capabilities(run, reach, now)
    if not missing:
        return None
    return Suspension(
        automation_id=run.automation_id,
        principal_id=run.principal_id,
        missing=missing,
        at=at,
    )


# ------------------------------------------------------------------ approvals (M17.4.5)
@dataclass(frozen=True)
class ApprovalStep:
    """A point in an unattended run where a person has to say yes (M17.4.5).

    **There is no field here for what happens if nobody does.** See
    `AN_EXPIRED_APPROVAL_STOPS_THE_RUN`: a default action on timeout reads as robustness and
    is a side effect with nobody's name on it, and skipping the step produces a run that
    reports success having done less than it says.

    The window is bounded twice and both bounds are checked by `approval_refusals`, not here,
    because the second bound is a property of the automation rather than of the step: a step
    cannot know the cadence it sits inside.
    """

    step_id: str
    automation_id: str
    #: How long a person has to answer.
    window: timedelta

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            msg = "an approval step with no id cannot be raised, found again or expired"
            raise UnattendedError(msg)
        if self.window <= timedelta(0):
            msg = (
                f"step {self.step_id!r} gives nobody any time to answer, so it expires the "
                "moment it is raised and the run stops every time"
            )
            raise UnattendedError(msg)


def approval_refusals(run: UnattendedRun, steps: Sequence[ApprovalStep]) -> tuple[str, ...]:
    """Every reason these approval steps would go wrong with nobody watching (M17.4.5).

    Three checks and the third is the one that only exists because this is unattended.

    The platform maximum is `brain.gate.leash.MAX_APPROVAL_WINDOW`, imported rather than
    chosen again: an approval that can stand indefinitely is a standing grant with extra
    steps, and that argument does not change because the run is on a schedule.

    A step belonging to another automation is refused because the cadence bound below is
    computed from *this* automation's trigger, so a step checked against the wrong one is
    checked against the wrong number.

    The cadence bound is `AN_APPROVAL_MAY_NOT_OUTLIVE_THE_CADENCE`. It applies only to a
    schedule, because an event or a webhook trigger has no interval for an approval to
    outlive, and treating a missing interval as an infinite one would refuse every approval
    on every webhook automation.
    """
    findings: list[str] = []
    cadence = run.trigger.cadence
    for step in steps:
        if step.automation_id != run.automation_id:
            findings.append(
                f"step {step.step_id!r} belongs to {step.automation_id!r} and is being "
                f"checked against {run.automation_id!r}, so its window is measured against "
                "another automation's cadence"
            )
            continue
        if step.window > MAX_APPROVAL_WINDOW:
            findings.append(
                f"step {step.step_id!r} stands for {step.window} and the platform maximum "
                f"is {MAX_APPROVAL_WINDOW}; an approval that stands indefinitely is a "
                "standing grant with extra steps"
            )
        if cadence is not None and step.window >= cadence:
            findings.append(
                f"step {step.step_id!r} stands for {step.window} on an automation that runs "
                f"every {cadence}. {AN_APPROVAL_MAY_NOT_OUTLIVE_THE_CADENCE}"
            )
    return tuple(findings)


@dataclass(frozen=True)
class ExpiredApproval:
    """An approval nobody answered, and the run it stopped (M17.4.5).

    One outcome and no alternative. The type exists so the stop is a value somebody can
    count, report and act on rather than an absence of a record, which is the shape in which
    an automation that quietly stopped goes unnoticed for the same week a widened one does.
    """

    step_id: str
    automation_id: str
    raised_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for label, value in (("raised_at", self.raised_at), ("expires_at", self.expires_at)):
            if value.tzinfo is None:
                msg = f"step {self.step_id!r} has a naive {label}, which is a silent bug"
                raise UnattendedError(msg)
        if self.expires_at <= self.raised_at:
            msg = (
                f"step {self.step_id!r} expires at or before it was raised, so nobody was "
                "ever able to answer it"
            )
            raise UnattendedError(msg)

    def render(self) -> str:
        """What a person reads. Says the run stopped, because that is what happened."""
        return (
            f"{self.automation_id} stopped at {self.step_id}: nobody approved it in time. "
            "Nothing after that step happened."
        )


def expire(step: ApprovalStep, *, raised_at: datetime, now: datetime) -> ExpiredApproval | None:
    """Stop the run if this approval's window has passed (M17.4.5).

    `None` while there is still time, which is the positive half. There is deliberately no
    third answer: a function that could return "carry on" would be the default action this
    module refuses, and it would be reached by whichever caller wanted the run to finish.
    """
    expires_at = raised_at + step.window
    if now < expires_at:
        return None
    return ExpiredApproval(
        step_id=step.step_id,
        automation_id=step.automation_id,
        raised_at=raised_at,
        expires_at=expires_at,
    )


# ------------------------------------------------------------------ history (M17.4.6)
@dataclass(frozen=True)
class CostedRun:
    """One finished run of one automation, and what it cost (M17.4.6).

    Only terminal states, read off `brain.ops.jobs.TERMINAL` rather than listed here. A run
    still in flight is not history, and putting one in a list headed "what this did" is how
    a reader concludes something finished that has not.

    Carries no failure text and no arguments, which is `brain.ops.jobs.DeadLetter`'s rule: a
    message from a failing run is somebody's data copied onto an operational surface with a
    different retention on it.

    A refused or failed run costs something and is recorded at what it cost, which may be
    nothing. Dropping the zero-cost rows would make an automation that stopped working look
    like one that became cheap, and a falling cost line is the shape somebody reads as good
    news.
    """

    automation_id: str
    at: datetime
    principal_id: str
    state: JobState
    #: Minor currency units, as `brain.ops.spend.Estimate.minor` counts them.
    minor: int
    seconds: float

    def __post_init__(self) -> None:
        if self.state not in TERMINAL:
            msg = (
                f"a run of {self.automation_id!r} in state {self.state.value} has not "
                "finished, and a history entry for it says something happened that has not"
            )
            raise UnattendedError(msg)
        if self.at.tzinfo is None:
            msg = f"a run of {self.automation_id!r} is dated with no timezone"
            raise UnattendedError(msg)
        if self.minor < 0 or self.seconds < 0:
            msg = (
                f"a run of {self.automation_id!r} reports {self.minor} minor units in "
                f"{self.seconds} seconds; a negative figure makes the total smaller than "
                "the runs that produced it"
            )
            raise UnattendedError(msg)


@dataclass(frozen=True)
class RunHistory:
    """What one automation has done, and what it cost (M17.4.6).

    `total_minor` is a property computed from the rows rather than a field beside them, so
    it cannot disagree with what the reader is looking at. There is no field here for a
    total number of runs, a count withheld, or a figure over any other period;
    `unattended_gaps` asks `brain.ops.jobs.hidden_count_fields` of this type rather than
    restating the rule.
    """

    automation_id: str
    #: Newest first.
    runs: tuple[CostedRun, ...]

    @property
    def total_minor(self) -> int:
        return sum(one.minor for one in self.runs)

    @property
    def last(self) -> CostedRun | None:
        return self.runs[0] if self.runs else None

    @property
    def mean_minor(self) -> float:
        """The average cost of a run, over the rows shown and nothing else.

        The figure an owner actually reads: a total rises with the number of runs and says
        nothing, while a mean that doubles is an automation doing more than it used to.
        Zero for an empty history rather than undefined, because a screen showing a dash
        where a number goes is read as a fault.
        """
        return self.total_minor / len(self.runs) if self.runs else 0.0


def history(automation_id: str, runs: Sequence[CostedRun]) -> RunHistory:
    """This automation's finished runs, newest first (M17.4.6).

    Filters by automation before it does anything else, so a history can never be assembled
    from another automation's runs, and orders by time so two readings of an unchanged
    history are the same list.
    """
    mine = tuple(one for one in runs if one.automation_id == automation_id)
    return RunHistory(
        automation_id=automation_id,
        runs=tuple(sorted(mine, key=lambda one: one.at, reverse=True)),
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types anybody is handed about an automation. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`.
UNATTENDED_SURFACE: Final[tuple[type, ...]] = (UnattendedRun, CostedRun, RunHistory, Suspension)

#: Field names that would put a step list back on an automation. See `OutcomeTemplate`: what
#: a person configures is an outcome, and a canvas is a different thing in a different module.
NAMES_THAT_WOULD_BE_A_CANVAS: Final[frozenset[str]] = frozenset(
    {"steps", "graph", "flow", "expression", "script", "nodes"}
)

#: The one field on an automation that names capabilities and is not a stored reach. Named
#: as a constant with a parameter beside it, so removing the exemption is an edit somebody
#: makes deliberately rather than a check nobody has run. See `A_REQUIREMENT_IS_NOT_A_REACH`.
DECLARED_REQUIREMENT_FIELDS: Final[frozenset[str]] = frozenset({"requires"})


def unattended_gaps(
    *,
    surface: Sequence[type] = UNATTENDED_SURFACE,
    run_type: type = UnattendedRun,
    requirement_fields: frozenset[str] = DECLARED_REQUIREMENT_FIELDS,
) -> tuple[str, ...]:
    """Everything about this surface that would run unwatched or stop unnoticed.

    Takes its inputs rather than reading the module's own constants, for the reason
    `brain.ops.starter.starter_gaps` records: a diagnostic that can only be run against the
    healthy tree has nothing to report on today's data, so switching off any of its refusals
    changes nothing observable and every one of them survives a mutation.

    Three checks, all of them delegated where somebody else already owns the rule. The reach
    check is `brain.ops.jobs.reach_carrying_fields` and the count check is
    `hidden_count_fields` from the same module; only the canvas check is this module's own,
    because only this module has an opinion about what an automation is configured from.

    `requirement_fields` is the one exemption and it is a parameter rather than a literal, so
    a test can run this without it and see the finding the exemption suppresses. See
    `A_REQUIREMENT_IS_NOT_A_REACH` for why a declared requirement is not the stored decision
    that check is looking for, and note that the exemption is by field name: a field of type
    `EntitlementSet` called anything else is still reported.

    There is deliberately no check here that a template requires something.
    `OutcomeTemplate.__post_init__` refuses one that does not, so a check here would be a
    second enforcement point for one rule and would be unreachable, which is the mistake
    `brain.connectors.projection.ProjectedEntity` records having made and removed. A
    catalogue supplied as configuration is built through that constructor like any other.
    """
    gaps: list[str] = []
    gaps.extend(
        f"{run_type.__name__}.{found} could hold a permission decision written down at "
        f"configuration time. {ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT}"
        for found in reach_carrying_fields(run_type)
        if found not in requirement_fields
    )
    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    declared: Mapping[str, Any] = getattr(run_type, "__dataclass_fields__", {})
    gaps.extend(
        f"{run_type.__name__}.{name} is a canvas on an automation, which is a second and "
        "ungoverned way to say what happens; an automation is installed from a named outcome"
        for name in declared
        if name in NAMES_THAT_WOULD_BE_A_CANVAS
    )
    return tuple(gaps)
