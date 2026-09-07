"""Automations owned by one agent: whose they run as, when they stop, and what says so.

`brain.console.agent_output` is what an agent produced. This is what it does when nobody asks
it to, which is the same surface with the person taken out of it, and every rule here follows
from that one removal.

**An automation that runs on a schedule with nobody watching is the one place a widened reach
goes unnoticed for a week.** A person doing the wrong thing gets an odd answer and says so. A
flow doing the wrong thing at four every morning gets noticed when a client asks why they were
emailed, or never. So the safety leaves in M39.6.2 are not paperwork around a feature: they
are the feature, and the surface leaves in M39.6.1 exist to make them readable.

**What an automation may reach is `flow_reach` and nothing else computes it.** `E(principal)
intersect agent_ceiling`, by `brain.ops.automation.flow_reach`, which calls the one
`EntitlementSet.intersect` there is. It is not the reader's reach, because the reader is not
who it runs as, and it is not the agent's ceiling, because a ceiling belongs to nobody. A
third implementation would be a third place for the platform's central rule to be subtly
wrong, and the wrong copy is the one running unattended. `brain.console.workspace.
intersections_in` is run over this module's own source by its test suite, so the absence is
checked rather than promised.

**An automation runs as a named person or it runs as nobody.** The tempting alternative is to
let it run as the agent, which is one fewer thing to configure and reads as tidy, and it is
the arrangement in which nobody can revoke it: revocation in this system is the deletion of a
grant from a principal, and an agent's ceiling is not a principal's grants. `brain.agents.
model.AN_AGENT_CEILING_IS_NOT_A_PRINCIPAL` says so at the type level and this says so at the
schedule level. See `AN_AUTOMATION_RUNNING_AS_ITSELF_IS_A_GRANT_NOBODY_CAN_REVOKE`.

**Pausing is the scheduler forgetting it, and stopping is `brain.ops.halt`.** Those are two
different acts and this module does both without inventing either. Forgetting is
`next_run_at = None`, because `brain.ops.jobs.SCHEDULING_IS_A_TIMESTAMP_AND_NOT_A_STATE` is
already the rule and a `paused` boolean beside a timestamp is two facts that can disagree.
Stopping what is already running is a `Halt`, which is the system's stop button, and building
a second one here is exactly the fifth lie that module names.

**And the halt this builds does not currently stop anything, which is reported rather than
implied.** `brain.ops.halt.ENFORCED_AXES` holds `EVERYTHING` and `CONNECTOR` only, because
`brain.ops.admission.decide` is handed a connector and nothing else, so a halt scoped to an
agent is in force in the store and refuses no request anywhere. `automation_gaps` runs
`halt_gaps` over the halt a failure pause produces and reports that, because the person
reading a paused automation is not in a position to go and read which call sites exist.

**A schedule change is a gated learning event, and the classification is read rather than
restated.** `brain.memory.tiers` puts `Change.LEASH_INCREASE` at `Tier.GATED` and lists it
among the changes that alter who may see what. Moving when an agent acts unattended, or how
often, is trusting it further in exactly that sense: nothing else about the run changed, and
the amount of unwatched action did. `may_change_schedule` reads `blast_radius` and raises
loudly if that member ever stops being gated, which is `brain.console.reach_view.may_raise`'s
construction and is here for the same reason: a quiet `False` would present as an approver
never being good enough.

**Pausing needs no approval and resuming does**, which is `brain.ops.halt.
THE_GUARDED_ACT_IS_RESUME_AND_NEVER_STOP` at this level and the same asymmetry
`reach_view.may_raise` applies to a rung. A fail-safe direction with paperwork on it is a
fail-safe direction nobody can take during the incident that needs it.

**Names are outcomes because the reader is the owner.** M39.6.1.2 asks for the first person
and against trigger-and-action mechanics, and the reason is who reads the list: the person
answerable for what the agent does, deciding whether an automation should still exist. "When
a form is submitted, POST to the webhook" cannot be judged by that person at all, and "I file
each week's timesheets on Friday" can. See
`A_NAME_THAT_DESCRIBES_THE_WIRING_CANNOT_BE_JUDGED_BY_ITS_OWNER`.

Rejected: a global automations list with an agent filter. It is one query instead of many and
it is the arrangement M39.6.1.1 exists to refuse: the filter is the part that gets omitted,
and the page that results is every scheduled thing in the company under one heading. Every
listing here takes an agent id with no value meaning all of them.

Rejected: a second stop mechanism scoped to one automation. `Halt` has no automation scope and
adding one would mean a switch `brain.ops.admission` does not consult, which is the value class
that reports itself as in force and refuses nothing. The narrower stop is the scheduler
forgetting the automation, which is enforced by the thing that reads `next_run_at`.

Scope: domain logic. Nothing here schedules anything, opens a connection or reads a clock;
`now` and `at` are parameters for the reason `brain.ops.limits` gives about policy that owns a
client. No transaction is opened, which is why M39.6.1.5's "in the same transaction" is
expressed as a value that cannot be half built: `SchedulerChange` carries the automation and
its registry entry together and refuses one without the other.

**Nothing here is a screen.** There is no automations tab in this repository and no route
behind one, exactly as `brain.console.screens` says of its own registry.

**One of the nine leaves in this group is not claimed and it is M39.6.1.3**, the template
gallery with a one-step install. A gallery is a rendered thing, which is reason enough on a
surface with no screens, but the harder half is the content: a set of common automations is a
set of outcomes somebody at a particular company wants, and a list of them written here would
be exactly the company detail `CLAUDE.md` says never goes into the source. `brain.agents.
template` already holds the install-and-overlay mechanism a gallery would use, so what is
missing is a catalogue that is configuration rather than a constant, and deciding where that
catalogue lives is not this module's decision to make.

Task ids: M39.6.1.1, M39.6.1.2, M39.6.1.4, M39.6.1.5
Task ids: M39.6.2.1, M39.6.2.2, M39.6.2.3, M39.6.2.4
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from brain.agents.model import CEILING_PRINCIPAL_PREFIX, AgentRecord, entitlement_ceiling
from brain.console.agent_output import basis_over
from brain.console.screens import screen
from brain.console.workspace import Basis
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Principal
from brain.memory.tiers import Change, Tier, blast_radius
from brain.ops.automation import flow_reach
from brain.ops.halt import (
    MINIMUM_REASON,
    Effect,
    Halt,
    HaltScope,
    halt_gaps,
)
from brain.ops.jobs import TERMINAL, JobState, hidden_count_fields

# ------------------------------------------------------------------ written-down reasons
#: Why an automation may not run as the agent that owns it.
AN_AUTOMATION_RUNNING_AS_ITSELF_IS_A_GRANT_NOBODY_CAN_REVOKE: Final = (
    "Running an automation as the agent is one fewer thing to configure and it reads as "
    "tidy. It is also the one arrangement nobody can undo: revocation in this system is the "
    "deletion of a grant from a principal, and an agent's ceiling is not a principal's "
    "grants, so there is no row anybody could delete to stop it. Worse, the reach would be "
    "the ceiling itself rather than an intersection with somebody's, which is the platform's "
    "central rule inverted by a scheduling convenience. The automation names a person, that "
    "person's grants are what it reaches, and offboarding them stops it."
)

#: Why a schedule change is treated as a gated learning event.
CHANGING_WHEN_SOMETHING_RUNS_UNWATCHED_IS_TRUSTING_IT_FURTHER: Final = (
    "Nothing about a run changes when its schedule moves except how much of it happens with "
    "nobody present, and that is the definition of a leash. Doubling the frequency of an "
    "unattended write, or moving it from an hour somebody is at a desk to one nobody is, "
    "widens the blast radius of every mistake it can make without widening anything a review "
    "would look at. brain.memory.tiers puts a leash increase at the gated tier and lists it "
    "among the changes that alter who may see what; this reads that classification rather "
    "than restating it, so lowering it is one edit in one place with tests on it."
)

#: Why a paused automation has no next time rather than a flag.
A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE: Final = (
    "brain.ops.jobs already decided that scheduling is a timestamp and not a state, because "
    "a second way to be ready means the fetch has to know about both and the day somebody "
    "adds one and forgets the query is the day a schedule silently stops firing. The same "
    "argument inverted applies here: an automation carrying paused=True and a next run time "
    "is a row where the screen and the scheduler read different halves, and the screen is "
    "the half that says it is stopped. Paused is the absence of a next time, and there is no "
    "field it could disagree with."
)

#: Why a name is an outcome in the first person.
A_NAME_THAT_DESCRIBES_THE_WIRING_CANNOT_BE_JUDGED_BY_ITS_OWNER: Final = (
    "The list of an agent's automations is read by the person answerable for what that agent "
    "does, deciding whether each one should still exist. That decision needs the outcome and "
    "nothing else. A name reading when a form is submitted, create a ticket describes the "
    "plumbing to somebody who is not being asked about plumbing, and the honest response to "
    "it is to leave it alone, which is how an automation nobody wants survives three "
    "reviews. First person because the agent is the thing doing it, and an outcome because "
    "that is the only part the owner is qualified to approve or stop."
)

#: Why the pause and the notice are one value.
A_PAUSE_NOBODY_IS_TOLD_ABOUT_IS_AN_AUTOMATION_THAT_QUIETLY_STOPPED: Final = (
    "The failure a threshold protects against is a broken automation writing wrongly for a "
    "week. The failure the notice protects against is the opposite one and is just as "
    "expensive: an automation that stopped, nobody was told, and the work it was doing "
    "simply did not happen. Both halves therefore come back as one value, so there is no "
    "call site at which the pause is written and the notice is dropped, and the notice has "
    "no field that could suppress it, for the reason brain.console.reads.StewardNotice has "
    "none."
)

#: Why an automation and its registry entry are changed together or not at all.
A_SCHEDULE_WITHOUT_A_REGISTRY_ROW_IS_WORK_NOTHING_KNOWS_ABOUT: Final = (
    "M39.6.1.5 asks for the scheduler registry to be updated in the same transaction, and "
    "nothing here opens a transaction. What it can do is remove the shape the requirement "
    "exists to prevent: SchedulerChange carries the automation and its registry entry "
    "together, refuses an entry describing a different automation, and refuses a removal "
    "that leaves either behind. An automation with no registry row is scheduled work nothing "
    "lists; a registry row with no automation is a schedule nothing owns, and it fires."
)


class AutomationSurfaceError(Exception):
    """An automation was described in a shape that would run unwatched or stop unnoticed.

    Outside `brain.core.errors` for the reason `brain.console.workspace.WorkspaceError` is:
    those five outcomes describe an answer given to a person asking a question, and this is a
    refusal to schedule or to assemble. Nobody asking a question ever sees one.
    """


# ------------------------------------------------------------------ naming (M39.6.1.2)
#: How an outcome name opens. First person, because the agent is the thing doing it.
FIRST_PERSON_OPENER: Final = "I "

#: Words that describe the wiring rather than the outcome. Matched on whole words, so
#: "onboarding" is not "on" and "authenticate" is not "auth".
MECHANICS_WORDS: Final[frozenset[str]] = frozenset(
    {
        "action",
        "cron",
        "event",
        "hook",
        "http",
        "poll",
        "post",
        "schedule",
        "trigger",
        "webhook",
        "workflow",
    }
)

#: The shape a trigger-and-action name takes even without one of those words in it. "When x,
#: then y" is the canvas's own grammar and it arrives as a name because it is what the person
#: building the automation was looking at while they named it.
_TRIGGER_GRAMMAR_RE: Final = re.compile(r"\b(when|whenever|if)\b.*\b(then|do|create|send)\b", re.I)

#: Long enough to be an outcome, short enough to be a heading. An outcome in the first person
#: needs a verb and an object, and "I file" is nine characters.
MINIMUM_OUTCOME_NAME: Final = 12


def outcome_name_refusals(name: str) -> tuple[str, ...]:
    """Everything wrong with one automation's name, in words its author can act on (M39.6.1.2).

    Returns findings rather than raising, because a name is edited rather than debugged and a
    person renaming an automation wants all of what is wrong with it at once.
    `Automation.__post_init__` is what refuses, so the rule cannot be got round by not calling
    this. See `A_NAME_THAT_DESCRIBES_THE_WIRING_CANNOT_BE_JUDGED_BY_ITS_OWNER`.
    """
    findings: list[str] = []
    trimmed = name.strip()
    if len(trimmed) < MINIMUM_OUTCOME_NAME:
        findings.append(
            f"{name!r} is too short to be an outcome; the owner reading the list has to be "
            "able to decide whether this should still happen"
        )
    if not trimmed.startswith(FIRST_PERSON_OPENER):
        findings.append(
            f"{name!r} does not open with {FIRST_PERSON_OPENER!r}; the agent is the thing "
            "doing this and a name in the third person reads as a description of a system"
        )
    words = set(re.findall(r"[a-z]+", trimmed.lower()))
    findings.extend(
        f"{name!r} names {word!r}, which is the plumbing rather than the outcome"
        for word in sorted(words & MECHANICS_WORDS)
    )
    if _TRIGGER_GRAMMAR_RE.search(trimmed):
        findings.append(
            f"{name!r} is written as a trigger and an action, which is the canvas's grammar "
            "and not an outcome the owner can approve or stop"
        )
    return tuple(findings)


# -------------------------------------------------------------- the automation (M39.6.1.1)
@dataclass(frozen=True)
class Automation:
    """One thing an agent does without being asked (M39.6.1.1, M39.6.1.2, M39.6.2.1).

    **No `paused` field.** Paused is `next_run_at is None`, which is
    `A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE`, and
    `automation_gaps` reports one if a later edit adds it.

    `runs_as` is a whole `Principal` rather than an identifier, so that the thing an
    automation runs as is the same type the gate computes an entitlement for. An id alone
    would admit a string somebody typed, and the string somebody types is the agent's slug.
    """

    automation_id: str
    agent_id: str
    #: An outcome, in the first person. See `outcome_name_refusals`.
    name: str
    #: The person or service principal whose grants this runs at. Never the agent.
    runs_as: Principal
    #: The registered task it runs, in `brain.ops.queue`'s vocabulary.
    task: str
    #: When it next runs, or `None` when nothing will pick it up.
    next_run_at: datetime | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("automation_id", self.automation_id),
            ("agent_id", self.agent_id),
            ("task", self.task),
        ):
            if not value.strip():
                msg = f"an automation with no {label} cannot be listed, paused or registered"
                raise AutomationSurfaceError(msg)
        refusals = outcome_name_refusals(self.name)
        if refusals:
            msg = f"automation {self.automation_id!r} is named badly: {'; '.join(refusals)}"
            raise AutomationSurfaceError(msg)
        itself = (self.agent_id, f"{CEILING_PRINCIPAL_PREFIX}{self.agent_id}")
        if self.runs_as.id in itself:
            msg = (
                f"automation {self.automation_id!r} runs as {self.runs_as.id!r}, which is "
                "the agent it belongs to. "
                f"{AN_AUTOMATION_RUNNING_AS_ITSELF_IS_A_GRANT_NOBODY_CAN_REVOKE}"
            )
            raise AutomationSurfaceError(msg)
        if self.next_run_at is not None and self.next_run_at.tzinfo is None:
            msg = (
                f"automation {self.automation_id!r} is due at a naive instant, so it fires at "
                "whatever offset the host happens to sit from UTC"
            )
            raise AutomationSurfaceError(msg)

    @property
    def paused(self) -> bool:
        """Whether anything will pick this up. Derived, never stored."""
        return self.next_run_at is None


def automation_reach(runs_as: EntitlementSet, agent: AgentRecord) -> EntitlementSet:
    """What one automation may actually touch (M39.6.2.1).

    `brain.ops.automation.flow_reach`, handed the principal the automation runs as and the
    agent's own ceiling. It is not the reader's reach, because the reader is not who it runs
    as, and it is not the ceiling, because a ceiling confers nothing.

    There is no arithmetic in this function, which is the point: `brain.console.workspace.
    intersections_in` reads this module's source and would report one.
    """
    return flow_reach(runs_as, entitlement_ceiling(agent))


# -------------------------------------------------------- who may see one (M39.6.1.1)
#: The screen whose grant decides whether somebody may see scheduled work that is not theirs.
#:
#: A screen key rather than a capability spelled out here, exactly as
#: `brain.console.workspace.SPEND_OF_OTHERS_SCREEN` is, so the tab cannot drift from the
#: screen an administrator reviews. The queue screen is the one that shows what is scheduled,
#: what failed and what is being retried, for everybody.
SCHEDULE_SCREEN: Final = "queue"

#: What a reader needs to see somebody else's scheduled work, read off the registry.
SCHEDULE_CAPABILITY: Final[Capability] = screen(SCHEDULE_SCREEN).read.requires


def _scope_row(one: Automation) -> dict[str, str]:
    """The fields a schedule grant's scope may be written against.

    Three, all of them closed vocabularies or references, following
    `brain.ops.jobs._scope_row`: a grant scoped on something the row does not carry admits
    nothing, which fails closed, and a wider row would let a grant be written against a field
    this surface cannot evaluate.
    """
    return {
        "agent_id": one.agent_id,
        "task": one.task,
        "principal_id": one.runs_as.id,
    }


def may_see(one: Automation, reader: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may know this automation exists. Two ways in, and no third.

    **It runs as them.** A person may see what is scheduled to happen under their own name,
    and refusing that would mean the only principal whose grants are being spent is the one
    who cannot find out.

    **A grant covers scheduled work, in a scope that matches the row.** The same two branches
    in the same order as `brain.ops.jobs.may_see` and `brain.console.agent_output.may_see`,
    because a second implementation of who may read what is a second place for it to be wrong.
    """
    if one.runs_as.id == reader.principal_id:
        return True
    scope = reader.scope_for(SCHEDULE_CAPABILITY, now)
    if scope is None:
        return False
    return scope.matches(_scope_row(one))


#: Where an automation with no next run sorts. Aware, so it stays comparable with a real
#: instant even though the first element of the sort key means it never has to be.
_NO_NEXT_RUN: Final = datetime.min.replace(tzinfo=UTC)


def automations_for(
    agent_id: str,
    entries: Sequence[Automation],
    reader: EntitlementSet,
    now: datetime | None = None,
) -> tuple[Automation, ...]:
    """The automations of one agent this reader may see (M39.6.1.1).

    `agent_id` is the first parameter and has no value meaning every agent, which is the leaf
    read as a shape rather than as a convention: a listing that could be asked for the estate
    is the global pile with an optional filter on it, and the filter is the part that gets
    omitted. Nothing in this module can produce that list.

    Ordered by the next run and then by id, so the thing about to happen is at the top and two
    readings of an unchanged schedule are the same list. A paused automation has no next time
    and sorts last, which is right: it is the one nothing is about to do.

    One value, and nowhere in it for a count of what was withheld.
    """
    kept = [one for one in entries if one.agent_id == agent_id and may_see(one, reader, now)]

    def order(one: Automation) -> tuple[bool, datetime, str]:
        return (one.next_run_at is None, one.next_run_at or _NO_NEXT_RUN, one.automation_id)

    return tuple(sorted(kept, key=order))


# ------------------------------------------------------ the scheduled job registry (M39.6.2.4)
#: The shortest statement of what an automation guards that says anything. The same length
#: `brain.ops.halt.MINIMUM_REASON` requires of a halt, imported rather than chosen, because
#: both are prose written for whoever has to decide something at three in the morning.
MINIMUM_GUARDS: Final[int] = MINIMUM_REASON


@dataclass(frozen=True)
class RegistryEntry:
    """One row of the scheduled job registry (M39.6.2.4).

    `guards` is required prose, for the reason `brain.ops.retention.Horizon.because` and
    `brain.ops.storage.Bucket.retention_reason` are: a scheduled job nobody can explain is a
    scheduled job that gets disabled during an incident and never restored, or left running
    after the thing it protected has gone. It says what breaks if this does not run.
    """

    automation_id: str
    agent_id: str
    task: str
    #: The principal it runs as, copied so the registry can be read without the automation.
    runs_as_id: str
    next_run_at: datetime | None
    guards: str

    def __post_init__(self) -> None:
        if not self.automation_id.strip() or not self.task.strip():
            msg = (
                "a registry row naming no automation or no task schedules nothing anybody can find"
            )
            raise AutomationSurfaceError(msg)
        if not self.runs_as_id.strip():
            msg = (
                f"registry row {self.automation_id!r} names no principal, so nothing decides "
                "whose grants the run spends"
            )
            raise AutomationSurfaceError(msg)
        if len(self.guards.strip()) < MINIMUM_GUARDS:
            msg = (
                f"registry row {self.automation_id!r} says {self.guards!r} about what it "
                "guards, which tells whoever is deciding whether to disable it nothing at all"
            )
            raise AutomationSurfaceError(msg)


def register(one: Automation, *, guards: str) -> RegistryEntry:
    """The registry row for one automation (M39.6.2.4).

    Derived from the automation rather than assembled beside it, so a row cannot describe a
    schedule the automation does not have. What the caller supplies is the one thing the
    automation does not know, which is what breaks if this stops running.
    """
    return RegistryEntry(
        automation_id=one.automation_id,
        agent_id=one.agent_id,
        task=one.task,
        runs_as_id=one.runs_as.id,
        next_run_at=one.next_run_at,
        guards=guards,
    )


def registry_gaps(
    automations: Sequence[Automation], entries: Sequence[RegistryEntry]
) -> tuple[str, ...]:
    """Every automation the registry does not describe, and every row nothing owns (M39.6.2.4).

    Both directions, and the second is the one that fires. An automation with no row is
    scheduled work nothing lists, which is the failure the leaf names. A row with no
    automation is a schedule nothing owns, and unlike the first it still runs: somebody
    deleted the automation and left the entry, and the task fires on a principal whose reason
    for holding grants has gone.

    The third finding is M39.6.1.5's property checked after the fact: a row whose next run
    disagrees with its automation's is the two halves having been written separately.
    """
    findings: list[str] = []
    by_id = {one.automation_id: one for one in entries}
    known = {one.automation_id for one in automations}
    for one in automations:
        row = by_id.get(one.automation_id)
        if row is None:
            findings.append(
                f"{one.automation_id!r} is scheduled and has no registry row, so nothing "
                "lists it and nobody reviewing scheduled work would see it"
            )
            continue
        if row.next_run_at != one.next_run_at:
            findings.append(
                f"{one.automation_id!r} is due at {one.next_run_at} and its registry row says "
                f"{row.next_run_at}; the two were written separately and one of them fires"
            )
        if row.runs_as_id != one.runs_as.id:
            findings.append(
                f"{one.automation_id!r} runs as {one.runs_as.id!r} and its registry row says "
                f"{row.runs_as_id!r}, so a reviewer reading the registry sees the wrong "
                "principal's grants being spent"
            )
    findings.extend(
        f"{row.automation_id!r} has a registry row and no automation, so it is a schedule "
        "nothing owns and it still fires"
        for row in entries
        if row.automation_id not in known
    )
    return tuple(findings)


# --------------------------------------------- pause, resume and remove (M39.6.1.5)
@dataclass(frozen=True)
class SchedulerChange:
    """One change to an automation and to the registry, as one value (M39.6.1.5).

    See `A_SCHEDULE_WITHOUT_A_REGISTRY_ROW_IS_WORK_NOTHING_KNOWS_ABOUT`. The constructor
    refuses every shape in which one half moved and the other did not, which is what this can
    say about "in the same transaction" without opening one.
    """

    before: Automation
    #: The automation afterwards, or `None` when it was removed.
    after: Automation | None
    #: Its registry row afterwards, or `None` when it was removed.
    entry: RegistryEntry | None

    def __post_init__(self) -> None:
        if (self.after is None) != (self.entry is None):
            msg = (
                f"{self.before.automation_id!r} changed on one side only (automation="
                f"{self.after is not None}, registry={self.entry is not None}). "
                f"{A_SCHEDULE_WITHOUT_A_REGISTRY_ROW_IS_WORK_NOTHING_KNOWS_ABOUT}"
            )
            raise AutomationSurfaceError(msg)
        if self.after is None or self.entry is None:
            return
        if self.after.automation_id != self.before.automation_id:
            msg = (
                f"a change to {self.before.automation_id!r} produced "
                f"{self.after.automation_id!r}, which is a different automation"
            )
            raise AutomationSurfaceError(msg)
        mismatched = registry_gaps([self.after], [self.entry])
        if mismatched:
            msg = f"the registry row does not describe the automation: {'; '.join(mismatched)}"
            raise AutomationSurfaceError(msg)


def _with_next_run(one: Automation, next_run_at: datetime | None) -> Automation:
    return Automation(
        automation_id=one.automation_id,
        agent_id=one.agent_id,
        name=one.name,
        runs_as=one.runs_as,
        task=one.task,
        next_run_at=next_run_at,
    )


def pause(one: Automation, *, guards: str) -> SchedulerChange:
    """Stop the scheduler picking this up, and move the registry row with it (M39.6.1.5).

    No approval and no reason, which is `brain.ops.halt.THE_GUARDED_ACT_IS_RESUME_AND_NEVER_STOP`
    at this level: the fail-safe direction cannot be the one with paperwork on it. Pausing a
    paused automation is allowed and is a no-op, because refusing it would make the safe act
    fail at the moment somebody is pressing it twice.
    """
    after = _with_next_run(one, None)
    return SchedulerChange(before=one, after=after, entry=register(after, guards=guards))


def resume(one: Automation, *, next_run_at: datetime, guards: str) -> SchedulerChange:
    """Put this back on the schedule (M39.6.1.5).

    Takes the next run rather than computing one, because when something resumes is a decision
    and a resumed automation whose next run was derived from its old cadence fires immediately
    for every occurrence it missed. Whether this may happen at all is `may_change_schedule`'s
    question and is deliberately not asked here: a function that both decided and acted would
    be a function whose decision nobody could exercise separately.
    """
    after = _with_next_run(one, next_run_at)
    return SchedulerChange(before=one, after=after, entry=register(after, guards=guards))


def remove(one: Automation) -> SchedulerChange:
    """Delete an automation and its registry row together (M39.6.1.5).

    Both `None`, which the constructor requires: a removal that left the registry row behind
    is the one failure in this group that still fires, because the scheduler reads the
    registry and the console reads the automation.
    """
    return SchedulerChange(before=one, after=None, entry=None)


# --------------------------------------------------------------- run history (M39.6.1.4)
@dataclass(frozen=True)
class AutomationRun:
    """One completed run of one automation (M39.6.1.4).

    Carries no failure text and no arguments, which is `brain.ops.jobs.DeadLetter`'s rule: a
    message from a failing run is somebody's data copied onto an operational surface with a
    different retention on it. The identifiers are enough to fetch what is needed through the
    gate, at the reach whoever is asking holds now.

    Only terminal states, read off `brain.ops.jobs.TERMINAL` rather than listed here. A run
    still in flight is not history, and putting one in a list headed "what this did" is how a
    reader concludes something finished that has not.
    """

    automation_id: str
    at: datetime
    state: JobState
    #: The principal it ran as, so a history can be narrowed to the reader's own.
    principal_id: str

    def __post_init__(self) -> None:
        if self.state not in TERMINAL:
            msg = (
                f"a run of {self.automation_id!r} in state {self.state.value} has not "
                "finished, and a history entry for it says something happened that has not"
            )
            raise AutomationSurfaceError(msg)
        if self.at.tzinfo is None:
            msg = f"a run of {self.automation_id!r} is dated with no timezone"
            raise AutomationSurfaceError(msg)


@dataclass(frozen=True)
class History:
    """What one automation has done and what it will do next (M39.6.1.4).

    `basis` is carried for `brain.console.workspace.Headline`'s reason: a figure whose meaning
    is unstated is read as the total, so a reader shown their own runs with no label reads
    them as the automation's.

    There is no field here for a total or a count of runs withheld; `hidden_count_fields` is
    the check that keeps it that way.
    """

    automation_id: str
    basis: Basis
    #: Newest first.
    runs: tuple[AutomationRun, ...]
    #: The most recent visible run, or `None`.
    last: AutomationRun | None
    #: When it next runs, or `None` when nothing will pick it up.
    next_run_at: datetime | None


def schedule_basis(entitlement: EntitlementSet, now: Any = None) -> Basis:
    """Whose scheduled work this caller may be shown figures over.

    `brain.console.agent_output.basis_over` against the queue screen, which is the screen that
    shows what is scheduled and what failed for everybody. The rule is
    `brain.console.workspace.Basis`': a front-page figure may not be a shortcut past a
    screen's grant, so a reader sees everybody's runs exactly when they could open that screen
    and read them there.
    """
    return basis_over(SCHEDULE_SCREEN, entitlement, now)


def history(
    one: Automation,
    runs: Sequence[AutomationRun],
    reader: EntitlementSet,
    *,
    basis: Basis,
    now: datetime | None = None,
) -> History:
    """This automation's history and its next run, at this reader's basis (M39.6.1.4).

    Two filters and the order matters. Visibility first, through `may_see`, so an automation
    the reader holds nothing for produces no history rather than an empty one attributed to
    it; then the basis, which narrows to the reader's own runs on the narrower one.

    `next_run_at` is the automation's own and is `None` for a paused one, which is the whole
    of `A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE` on a surface: a
    paused automation showing a next time is a screen saying it will run.
    """
    if not may_see(one, reader, now):
        return History(
            automation_id=one.automation_id,
            basis=basis,
            runs=(),
            last=None,
            next_run_at=None,
        )
    mine = tuple(
        entry
        for entry in runs
        if entry.automation_id == one.automation_id
        and (basis is Basis.EVERYONE or entry.principal_id == reader.principal_id)
    )
    ordered = tuple(sorted(mine, key=lambda entry: entry.at, reverse=True))
    return History(
        automation_id=one.automation_id,
        basis=basis,
        runs=ordered,
        last=ordered[0] if ordered else None,
        next_run_at=one.next_run_at,
    )


# ------------------------------------------------------- schedule changes (M39.6.2.2)
#: What kind of learning a schedule change is, in `brain.memory.tiers`' own vocabulary.
#:
#: `LEASH_INCREASE` rather than a member of this module's own, because the tier table is where
#: this system decides how much oversight a change needs and a second table is a second
#: answer. See `CHANGING_WHEN_SOMETHING_RUNS_UNWATCHED_IS_TRUSTING_IT_FURTHER` for why a
#: schedule move is a leash move, and note that the test pins this against
#: `CHANGES_WHAT_ANYBODY_MAY_SEE` as well as against the tier, so repointing it at a tier-one
#: member fails on both counts.
SCHEDULE_CHANGE_IS: Final[Change] = Change.LEASH_INCREASE


def schedule_change_tier() -> Tier:
    """How much oversight a schedule change needs, read from `brain.memory.tiers`."""
    return blast_radius(SCHEDULE_CHANGE_IS)


def may_change_schedule(
    one: Automation,
    *,
    becomes: datetime | None,
    approved_by: str,
) -> bool:
    """Whether this schedule may move, and whether a person has said so (M39.6.2.2).

    **Decides nothing about the change itself.** What this reports is whether the approval in
    front of it meets the bar, which is `brain.console.reach_view.may_raise`'s division and is
    here for the same reason: the classification belongs to `brain.memory.tiers` and a second
    opinion about it would be this module inventing a promotion rule.

    Pausing needs no approver. `becomes is None` is the automation stopping, which is the
    fail-safe direction, and a fail-safe direction with paperwork on it is one nobody can take
    during the incident that needs it.

    The approver may not be the principal the automation runs as. That is not a rule about
    seniority: an automation whose own principal approves its schedule is the automation
    approving itself, and the whole point of a gated change is that somebody outside it looked.
    """
    if becomes is None:
        return True
    if schedule_change_tier() is not Tier.GATED:
        # The premise everything below rests on, checked rather than assumed. Loud rather
        # than a quiet False, because a False here would present as an approver never being
        # good enough and somebody would go looking at the names.
        msg = (
            "a schedule change is no longer a gated change, so the rule that a person must "
            "approve one is not written down anywhere this function can read, and moving "
            "when an agent acts unattended would need nobody's agreement"
        )
        raise AutomationSurfaceError(msg)
    if not approved_by.strip():
        return False
    return approved_by.strip() != one.runs_as.id


# --------------------------------------------------- failure and the pause (M39.6.2.3)
#: How many consecutive failed runs pause an automation.
#:
#: Two, and both bounds are pinned against something outside this figure. It is strictly below
#: `brain.ops.jobs.MAX_ATTEMPTS` because a run that has failed has already exhausted its own
#: retries, so a threshold at or above the retry cap would be more unattended repetitions of a
#: failing side effect than the queue permits for a single job. And it is above one, because
#: one failure is usually something else being down and pausing on it turns every upstream
#: blip into work that silently did not happen.
FAILURES_BEFORE_PAUSE: Final = 2


@dataclass(frozen=True)
class OwnerNotice:
    """What the agent's owner is told when an automation stops (M39.6.2.3).

    **No field could suppress this.** No `enabled`, no `severity`, no `quiet`, which is
    `brain.console.reads.StewardNotice`'s construction: a notification about work that stopped
    happening is the one turned off first when a dashboard is noisy, and it is the one that
    matters most a fortnight later.

    Carries the count of consecutive failures, which is a count of the owner's own
    automation's runs and not a count of anything withheld, and carries no failure text: see
    `AutomationRun`.
    """

    owner_id: str
    automation_id: str
    agent_id: str
    consecutive_failures: int
    at: datetime

    def __post_init__(self) -> None:
        if not self.owner_id.strip():
            msg = "a notice addressed to nobody is not a notice, and the automation is stopped"
            raise AutomationSurfaceError(msg)
        if self.consecutive_failures < FAILURES_BEFORE_PAUSE:
            msg = (
                f"{self.automation_id!r} is reported as paused after "
                f"{self.consecutive_failures} failure(s), below the threshold of "
                f"{FAILURES_BEFORE_PAUSE}; the notice would say something that did not happen"
            )
            raise AutomationSurfaceError(msg)

    def render(self) -> str:
        """The sentence an owner reads. Names what stopped and never why it failed."""
        return (
            f"{self.automation_id} on {self.agent_id} has been paused after "
            f"{self.consecutive_failures} consecutive failed runs. Nothing it does is "
            "happening until somebody resumes it."
        )


@dataclass(frozen=True)
class FailurePause:
    """An automation stopped, the owner told, and what is running signalled (M39.6.2.3).

    Three parts as one value, so there is no call site at which the pause is written and the
    notice is dropped. See `A_PAUSE_NOBODY_IS_TOLD_ABOUT_IS_AN_AUTOMATION_THAT_QUIETLY_STOPPED`.

    The `halt` is `brain.ops.halt`'s own type and is what stops a run already in flight,
    because refusing the next run does not stop the current one, which is that module's first
    lie. Whether it stops anything today is `automation_gaps`' finding rather than this type's
    promise.
    """

    change: SchedulerChange
    notice: OwnerNotice
    halt: Halt


def failure_pause(
    one: Automation,
    *,
    consecutive_failures: int,
    owner_id: str,
    at: datetime,
    guards: str,
    declared_by: str,
) -> FailurePause | None:
    """Pause an automation that keeps failing, and tell its owner (M39.6.2.3).

    `None` below the threshold, which is the positive half: an automation that failed once is
    still scheduled, because one failure is usually something else being down.

    The halt is scoped to the agent and carries both effects, because `brain.ops.halt.
    stop_everything`'s argument applies at every scale: refusing new work while the
    forty-minute run carries on writing is a screen that says stopped over a system that is
    not. Its reason is built here and is long enough for that module's own minimum, so a
    person deciding whether to resume at three in the morning has something to read.
    """
    if consecutive_failures < FAILURES_BEFORE_PAUSE:
        return None
    return FailurePause(
        change=pause(one, guards=guards),
        notice=OwnerNotice(
            owner_id=owner_id,
            automation_id=one.automation_id,
            agent_id=one.agent_id,
            consecutive_failures=consecutive_failures,
            at=at,
        ),
        halt=Halt(
            scope=HaltScope.AGENT,
            target=one.agent_id,
            declared_by=declared_by,
            at=at,
            reason=(
                f"automation {one.automation_id} failed {consecutive_failures} consecutive "
                "runs and was paused automatically"
            ),
            effects=frozenset({Effect.REFUSE_NEW, Effect.SIGNAL_RUNNING}),
        ),
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this surface is handed. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`.
AUTOMATION_SURFACE: Final[tuple[type, ...]] = (Automation, AutomationRun, History, OwnerNotice)

#: Field names that would put the schedule's state in two places at once. See
#: `A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE`.
NAMES_THAT_WOULD_BE_A_SECOND_SCHEDULE_STATE: Final[frozenset[str]] = frozenset(
    {"paused", "enabled", "active", "suspended", "stopped", "running"}
)


def automation_gaps(
    *,
    surface: Sequence[type] = AUTOMATION_SURFACE,
    automation_type: type = Automation,
    listing: Callable[..., object] = automations_for,
    halts: Iterable[Halt] = (),
) -> tuple[str, ...]:
    """Everything about this surface that would run unwatched or stop unnoticed.

    Takes its inputs rather than reading the module's own constants, for the reason
    `brain.ops.starter.starter_gaps` records: a diagnostic that can only be run against the
    healthy tree has nothing to report on today's data, so switching off any of its refusals
    changes nothing observable and every one of them survives.

    The halts are handed to `brain.ops.halt.halt_gaps` rather than examined here, which is the
    whole of the reuse: that module already knows which axes anything consults, and a copy of
    that knowledge here would be a copy that stops being true when a call site is added.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{automation_type.__name__}.{name} is a second place the schedule's state lives. "
        f"{A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE}"
        for name in getattr(automation_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_A_SECOND_SCHEDULE_STATE
    )

    parameters = list(inspect.signature(listing).parameters)
    name = getattr(listing, "__name__", "the listing")
    if not parameters or parameters[0] != "agent_id":
        gaps.append(
            f"{name} does not take an agent id first, so an automations list can be asked "
            "for without naming an agent and the result is the global pile M39.6.1.1 refuses"
        )
    elif inspect.signature(listing).parameters["agent_id"].default is not inspect.Parameter.empty:
        gaps.append(
            f"{name} gives agent_id a default, so the filter that makes this an agent's list "
            "rather than the estate's is the part a caller can omit"
        )

    gaps.extend(halt_gaps(tuple(halts)))
    return tuple(gaps)
