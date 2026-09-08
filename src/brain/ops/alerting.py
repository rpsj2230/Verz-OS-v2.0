"""Who hears an operational alert, how loudly, what they do about it, and who they call next.

`brain.ops.controls` decides *what* is wrong with the estate. This decides who is told and
what is in front of them when they are. The split is the one the layout table draws between
`brain.ops.limits` and `brain.ops.limit_store`, and it earns itself here for a sharper
reason than testability: the routing rules are the same whatever raised the alert, and a
severity table written inside the module that raises one becomes a second severity table the
next time something else raises one.

**A severity is what a miss costs, never how it feels.** Three levels, and each is defined
by the consequence rather than by an adjective: something is noticed in a digest, something
is raised for the working day, or somebody is woken. `brain.ops.recovery.Severity` already
makes this argument about its own two levels and says a third invented for tidiness is a
level nobody tunes. That is the reason this one has three rather than five, and the reason
each carries an acknowledgement window: a level nobody has said a number about is a level
that means whatever the reader last felt. See
`A_SEVERITY_IS_WHAT_A_MISS_COSTS_AND_NOT_HOW_IT_FEELS`.

**An alert routes to a capability, never to a person and never to a channel.** A named
recipient is a row that goes stale the week somebody changes job, and the failure is silent:
the alert is delivered, to a mailbox nobody opens. So a route names what a recipient must
hold, and resolving that to people is `brain.core.entitlement`'s, exactly as
`brain.ops.spend.A_REFUSAL_NAMES_A_ROLE_NOT_A_PERSON` argues at the other end of the system.
The channel is not named either: what is named is the highest classification a channel must
be fit for before it may carry this, which is the question `assert_can_send` actually asks.
See `AN_ALERT_ROUTES_TO_A_ROLE_AND_NEVER_TO_A_PERSON`.

**An alert body names a mechanism and never a subject, and this is where that rule is most
likely to be broken by somebody being helpful.** `brain.ops.denial_alerts` keeps it for
denials: the alert names the *shape* of a pattern and never the capability or the object,
because DENIED and ABSENT have to stay indistinguishable. An operational alert is read by
whoever is on call, who is frequently entitled to nothing at all, and it is forwarded, pasted
and read over a shoulder. So the same rule applies unchanged and it is a check rather than a
paragraph: `disclosure_findings` refuses a body carrying a capability, and the capability
grammar it applies is `brain.core.entitlement.CAPABILITY_RE` rather than a copy, so the two
cannot drift apart the way three copies of the tool-name grammar did. A control's own name is
safe to print precisely because a control is a property of the product rather than of any
company's data. See `AN_ALERT_BODY_NAMES_A_MECHANISM_AND_NEVER_A_SUBJECT`.

**The escalation ladder ends outside the installation, and the last rung may see least.**
The client runs this themselves; nobody operates it on their behalf. So the path is the
person on call, then whoever owns the installation, then the supplier of the software, and
the third rung is a support contract rather than an operator: they have no account, no
entitlement and no reach here. What travels to them is what the alert already carried, which
is a mechanism and a runbook step, and `escalation_gaps` refuses a step that claims to carry
more than the rung above it. That is what stops "escalate to the supplier" quietly becoming
"send the supplier a copy of the estate". See `AN_ESCALATION_CARRIES_NO_MORE_THAN_THE_ALERT`.

**The supplier's address is a setting and there is no value for it here.** A support address,
a portal URL or a company name in this file is a client-independence failure of exactly the
kind `brain.ops.independence` sweeps for, and it is the flavour that survives review because
it looks like ours rather than like theirs. `SUPPLIER_CONTACT_SETTING` names the setting and
`supplier_step` takes the value as a parameter, so a module with the address in it cannot be
written without deleting a function signature. See
`THE_SUPPLIER_IS_A_CONTACT_IN_CONFIGURATION_AND_NEVER_A_VALUE_HERE`.

Rejected: delivering anything from here. `brain.ops.denial_alerts` rejects the same thing for
a stronger reason than this module has, which is that importing a channel adapter would put a
refusal on its surface. The reason here is duller and still decides it: a routing table that
held an adapter could not be asked what it would do without something to send to, and the
case worth testing is the one where every channel is refusing.

Rejected: a severity per control. Severities are compared, and a vocabulary with one member
per control is a vocabulary in which nothing compares to anything, so an operator with four
alerts open has no order to work in. The control declares which of three it is.

Rejected: an `escalate: bool` on the route. Escalation is a sequence with a clock on it, and
a flag collapses "who is next" and "how long before they are" into a value that answers
neither. `Runbook.escalate_after` is the clock and `escalation_path` is the sequence.

Scope: domain logic. Nothing here reads a clock, opens a connection or sends anything; every
instant and every configured value arrives as a parameter, for the reason `brain.ops.limits`
gives about a policy module that owns a client.

Task ids: M37.5.2.1, M37.5.2.2, M37.5.2.3
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from itertools import pairwise
from types import MappingProxyType
from typing import Final

from brain.core.entitlement import CAPABILITY_RE, Capability
from brain.core.field_policy import Classification

# ------------------------------------------------------------------ written-down reasons
#: Why a severity is defined by its cost rather than by a word.
A_SEVERITY_IS_WHAT_A_MISS_COSTS_AND_NOT_HOW_IT_FEELS: Final = (
    "critical, major and warning are three words for how the author felt on the afternoon "
    "they wrote the line, and every estate ends up with everything marked critical because "
    "nothing about the word says what happens if it is not. So a level here is a consequence "
    "and a clock: it goes in a digest, it is picked up during the working day, or somebody is "
    "woken. A level with no acknowledgement window attached cannot be missed, because nothing "
    "says what missing it would look like, and an alert that cannot be missed is decoration."
)

#: Why the routing table names a capability rather than a recipient or a channel.
AN_ALERT_ROUTES_TO_A_ROLE_AND_NEVER_TO_A_PERSON: Final = (
    "A named recipient is correct on the day it is written and wrong the week that person "
    "changes job, and the failure is silent: the alert is delivered, to a mailbox nobody "
    "opens, and every dashboard says it was sent. So a route names what somebody must hold, "
    "and who holds it is a question for the entitlement model, which is the one place that "
    "answer is kept current. The channel is left out for the same reason and answered the "
    "same way: what is declared is the sensitivity a channel has to be fit for, which is the "
    "question a channel adapter already asks before it sends anything."
)

#: Why an operational alert obeys the denial alert's rule about naming things.
AN_ALERT_BODY_NAMES_A_MECHANISM_AND_NEVER_A_SUBJECT: Final = (
    "brain.ops.denial_alerts keeps this rule for denials because DENIED and ABSENT have to "
    "stay indistinguishable. It applies here unchanged and for a wider reason: an operational "
    "alert is read by whoever is on call, who is often entitled to nothing in this system at "
    "all, and it is forwarded into a chat window, pasted into a ticket and read over a "
    "shoulder. A control's own name is safe to print because a control is a property of the "
    "product rather than of anybody's data. A capability in the body is not, and neither is a "
    "person, an entity or a field, so the check is applied to the text rather than promised."
)

#: Why the last rung of the ladder is a setting and not a value.
THE_SUPPLIER_IS_A_CONTACT_IN_CONFIGURATION_AND_NEVER_A_VALUE_HERE: Final = (
    "The client owns the installation outright and the supplier is a support contract rather "
    "than an operator, so the supplier's address differs per installation exactly as the "
    "company name and the domain do. A support address written into this module would be the "
    "flavour of client value that survives review, because it reads as ours rather than as "
    "theirs, and it would ship to every company after the first. So the setting is named here "
    "and the value arrives as a parameter, which makes the rule structural: there is nowhere "
    "in this module for an address to be written down."
)

#: Why a later rung of the escalation ladder is never told more than an earlier one.
AN_ESCALATION_CARRIES_NO_MORE_THAN_THE_ALERT: Final = (
    "Escalation is the one moment somebody is willing to widen what an alert says, because "
    "the previous rung could not fix it and the next rung is being asked to. That instinct is "
    "how a supplier with no account and no entitlement ends up holding a description of the "
    "estate. The ladder therefore narrows rather than widens: each rung may see at most what "
    "the rung above it could, and the last rung is outside the installation entirely, so what "
    "reaches it is the mechanism and the runbook step and nothing that came out of a store."
)


class AlertingError(Exception):
    """A route, a runbook or an escalation step was described in a shape nobody can act on.

    Outside `brain.core.errors` for the reason `brain.ops.jobs.JobsError` gives about itself:
    nobody asking a question ever sees one of these. It is a mistake by whoever wired the
    call site up.
    """


# ------------------------------------------------------------------------- severity
class Severity(enum.IntEnum):
    """What a miss costs. An `IntEnum` so that louder is `>` and a test can assert the order.

    Follows `brain.ops.recovery.Severity`, which is an `IntEnum` for the same reason and
    keeps two members because it has two things worth waking somebody for. Three here rather
    than two, and the third is `NOTICED`: this module routes alerts about mechanisms that are
    silently not running, and a great many of those are worth reading tomorrow and worth
    nobody's night.
    """

    #: It goes in a digest. Somebody reads it when they next look at the estate.
    NOTICED = 1
    #: It is picked up during the working day and worked on that day.
    RAISED = 2
    #: Somebody is woken. Reserved for a guarantee that is already not holding.
    WOKEN = 3


#: What a recipient must hold to be told about the estate's own machinery.
#:
#: `admin:halt` is the nearest neighbour and is deliberately not reused:
#: `brain.ops.halt.HALT_CAPABILITY` admits somebody to stop the system, and being told that a
#: sweep has not run is not the same authority as being able to switch it off. A separate
#: noun for the same reason `brain.ops.outbox.MANAGE_SUBSCRIBERS` is separate from it.
OPERATIONS_ALERT: Final[Capability] = Capability(value="admin:operations_alert")

#: What a recipient must hold to be told that a guarantee about the estate has stopped
#: holding. The loudest route, and a wider grant than the one above rather than the same one:
#: waking somebody is an authority somebody delegates deliberately.
OPERATIONS_INCIDENT: Final[Capability] = Capability(value="admin:operations_incident")


@dataclass(frozen=True)
class Route:
    """Where one severity goes, and by when somebody is expected to have looked.

    `audience` is a capability rather than a list of people; see
    `AN_ALERT_ROUTES_TO_A_ROLE_AND_NEVER_TO_A_PERSON`. `carried_by` is the sensitivity a
    channel has to be fit for rather than a channel, for the same reason.
    """

    severity: Severity
    audience: Capability
    #: The highest classification a channel must be able to carry before it may take this.
    carried_by: Classification
    #: How long before nobody having looked is itself a problem.
    acknowledge_within: timedelta
    #: Whether this interrupts somebody outside working hours.
    wakes_somebody: bool

    def __post_init__(self) -> None:
        if self.acknowledge_within <= timedelta(0):
            msg = (
                f"{self.severity.name} is acknowledged within {self.acknowledge_within}, "
                "which is a window that has closed before the alert was raised; every alert "
                "at this severity would be overdue on arrival and the level would be ignored"
            )
            raise AlertingError(msg)


#: Where each severity goes. Exhaustive over `Severity`, and `routing_gaps` keeps it that way.
#:
#: The classification is `INTERNAL` at the quiet end and `CONFIDENTIAL` at the loud one, and
#: the step is deliberate rather than uniform. A digest line saying a sweep is behind is an
#: internal operational fact. An alert saying a guarantee about somebody's data has stopped
#: holding is the sort of sentence that should not land on a consumer messaging application
#: installed on a personal phone, which is the argument
#: `brain.ops.denial_alerts.ALERT_CLASSIFICATION` makes in the same words about its own.
#: Never `RESTRICTED`: nothing routed here carries a field value, and classifying an
#: operational alert alongside salary would make every operator surface claim a ceiling it
#: needs for nothing else.
ROUTES: Final[Mapping[Severity, Route]] = MappingProxyType(
    {
        Severity.NOTICED: Route(
            severity=Severity.NOTICED,
            audience=OPERATIONS_ALERT,
            carried_by=Classification.INTERNAL,
            acknowledge_within=timedelta(days=7),
            wakes_somebody=False,
        ),
        Severity.RAISED: Route(
            severity=Severity.RAISED,
            audience=OPERATIONS_ALERT,
            carried_by=Classification.INTERNAL,
            acknowledge_within=timedelta(days=1),
            wakes_somebody=False,
        ),
        Severity.WOKEN: Route(
            severity=Severity.WOKEN,
            audience=OPERATIONS_INCIDENT,
            carried_by=Classification.CONFIDENTIAL,
            acknowledge_within=timedelta(hours=1),
            wakes_somebody=True,
        ),
    }
)


def route_for(severity: Severity, routes: Mapping[Severity, Route] | None = None) -> Route:
    """Where an alert at this severity goes, refusing a severity nothing routes.

    Raises rather than defaulting to the quiet end. A severity with no route is a level
    somebody added and nobody decided about, and defaulting it to a digest is how the loudest
    thing in the system arrives as the least urgent. The same choice
    `brain.ops.reliability.lane_objective` makes about a lane nothing declares an objective
    for, and for the same reason.
    """
    table = ROUTES if routes is None else routes
    found = table.get(severity)
    if found is None:
        msg = (
            f"{severity.name} has no route, so an alert at this severity reaches nobody. "
            f"{AN_ALERT_ROUTES_TO_A_ROLE_AND_NEVER_TO_A_PERSON}"
        )
        raise AlertingError(msg)
    return found


def routing_gaps(routes: Mapping[Severity, Route] | None = None) -> tuple[str, ...]:
    """Every way this routing table stops being an ordering rather than a list.

    Four findings, and three of them are silent failures rather than loud ones.

    A severity with no row reaches nobody, and `route_for` raises only when somebody asks
    for it, which on a quiet estate is the day of the incident.

    A row filed under the wrong key is the one that reads correctly in review: the table is
    keyed by severity and each row carries its own, so a copy-paste that leaves `WOKEN`'s row
    under `RAISED`'s key routes the loudest alerts to the quietest audience while every
    severity is present and every window is plausible.

    A louder severity acknowledged no faster than a quieter one is a table with three levels
    and one meaning, which is the state every alerting system decays into. Asserted over
    consecutive pairs rather than against a constant, so the property survives a fourth level.

    And a louder severity carried at a lower classification is the direction the leak runs:
    the alert that says a guarantee has stopped holding is the one most likely to be widened
    to reach somebody quickly.

    The table is a parameter defaulting to the declared one, for the reason
    `brain.ops.queue.concurrency_gaps` takes its allocation: a check that can only be run
    against the constant beside it cannot be shown to fail.
    """
    table = ROUTES if routes is None else routes
    findings: list[str] = [
        f"{severity.name} has no route, so an alert at this severity reaches nobody"
        for severity in Severity
        if severity not in table
    ]
    findings.extend(
        f"{key.name} is keyed to a row declaring {row.severity.name}, so alerts at "
        f"{key.name} are routed by {row.severity.name}'s audience and window"
        for key, row in table.items()
        if row.severity is not key
    )
    ordered = [table[one] for one in sorted(Severity) if one in table]
    for quieter, louder in pairwise(ordered):
        if louder.acknowledge_within >= quieter.acknowledge_within:
            findings.append(
                f"{louder.severity.name} is acknowledged within {louder.acknowledge_within} "
                f"and {quieter.severity.name} within {quieter.acknowledge_within}, so being "
                "louder buys no faster response and the levels have one meaning between them"
            )
        if louder.carried_by.rank < quieter.carried_by.rank:
            findings.append(
                f"{louder.severity.name} is carried at {louder.carried_by.value} and "
                f"{quieter.severity.name} at {quieter.carried_by.value}, so the louder alert "
                "may go somewhere the quieter one may not"
            )
    return tuple(findings)


# ------------------------------------------------------------------ what the body may say
#: Words that would turn an operational alert into a statement about somebody's data.
#:
#: Names rather than a rule about meaning, because the failure arrives as a sentence somebody
#: adds to make an alert actionable, and it arrives with one of these words in it. The
#: capability grammar is checked separately and exactly, through
#: `brain.core.entitlement.CAPABILITY_RE`, so this list does not have to guess at that shape.
#:
#: **Every entry is a word that only turns up when somebody is describing a particular
#: thing**, and two were removed on the day this was written because they are not.
#: `department` and `record` are ordinary words in a sentence about a mechanism: "somebody
#: who moves department is judged against the new one" describes what a roster sync is for
#: and discloses nothing. A list that fires on prose like that is a list somebody widens an
#: exemption into, or routes around, and either ends with the check not applying to the
#: sentence it was written for. What is left is structural vocabulary: a body carrying one of
#: these is a body that has started naming what somebody was refused.
WORDS_THAT_WOULD_NAME_A_SUBJECT: Final[frozenset[str]] = frozenset(
    {
        "principal",
        "principal_id",
        "subject_id",
        "capability",
        "grant",
        "entity",
        "field",
        "denied",
        "hidden",
    }
)

#: How a body is split before each piece is asked whether it is a capability. Anything that
#: is not part of the capability grammar ends a token, so a capability inside a sentence, in
#: brackets or in quotes is still seen as one.
_TOKEN_RE: Final = re.compile(r"[A-Za-z0-9_.:*]+")


def disclosure_findings(text: str) -> tuple[str, ...]:
    """Every way this alert body says something about the estate's contents rather than its
    machinery.

    Two checks and they catch different mistakes.

    A capability in the body is the exact failure `brain.ops.denial_alerts` was built to
    avoid: `read:client.contract_value` in a sentence says the field exists to whoever is
    holding the phone. The grammar applied is `CAPABILITY_RE` itself rather than a restatement
    of it, applied token by token, because the compiled pattern is anchored and a sentence is
    not. Three copies of the tool-name grammar disagreed in this repository and CI passed a
    name the registry refused; there is no reason to believe a fourth copy of a different
    grammar would fare better.

    A word from `WORDS_THAT_WOULD_NAME_A_SUBJECT` is softer and is still worth refusing,
    because the sentence that carries one is almost always the helpful one: "the retention
    sweep has not run, so 4 records in finance are past their window" is a count of hidden
    things and a place, added by somebody making the alert useful.

    Reported rather than raised, so a caller can show every problem with a body at once
    rather than fixing them one at a time, which is the choice `brain.config.check` makes.
    """
    findings: list[str] = []
    tokens = _TOKEN_RE.findall(text)
    findings.extend(
        f"the body names the capability {token!r}, which says that what it governs exists"
        for token in tokens
        if CAPABILITY_RE.match(token)
    )
    lowered = {token.lower() for token in tokens}
    findings.extend(
        f"the body uses {word!r}, which is a word about somebody's data rather than about "
        "the mechanism that was supposed to run"
        for word in sorted(WORDS_THAT_WOULD_NAME_A_SUBJECT & lowered)
    )
    return tuple(findings)


# ------------------------------------------------------------------------- runbooks
@dataclass(frozen=True)
class Runbook:
    """What the person who received the alert does, in the order they do it.

    Two lists rather than one, and the split is what makes a runbook usable at three in the
    morning: `first_check` is how to find out whether this is real, and `then_do` is what to
    do once it is. A single numbered list conflates them, and the reader who is half awake
    starts doing step one of a remedy against an alert that turns out to be a deployment.

    `escalate_after` is on the runbook rather than on the route, because how long a fix takes
    is a property of the thing being fixed and how long somebody may take to look is a
    property of how loud it was. A single number would answer neither.
    """

    first_check: tuple[str, ...]
    then_do: tuple[str, ...]
    escalate_after: timedelta

    def __post_init__(self) -> None:
        if not self.first_check:
            msg = (
                "a runbook with nothing to check sends somebody to fix a thing before they "
                "have established that it is happening, which is how an alert about a "
                "deployment becomes an outage"
            )
            raise AlertingError(msg)
        if not self.then_do:
            msg = "a runbook with nothing to do is a notification wearing a runbook's name"
            raise AlertingError(msg)
        for step in (*self.first_check, *self.then_do):
            if not step.strip():
                msg = "a runbook step with no words in it reads as a step somebody skipped"
                raise AlertingError(msg)
        if self.escalate_after <= timedelta(0):
            msg = (
                f"this runbook escalates after {self.escalate_after}, so it is escalated "
                "before anybody has read it and the rung above it becomes the first responder"
            )
            raise AlertingError(msg)


def runbook_gaps(runbook: Runbook, route: Route) -> tuple[str, ...]:
    """Whether this runbook and this route describe the same urgency.

    One finding, and it is the mismatch that makes a ladder useless in both directions. A
    runbook that escalates sooner than its route's acknowledgement window escalates every
    alert automatically, because the first responder is still inside the time they were given
    to look: the rung above becomes the first responder and the rung below learns that
    somebody else picks these up. Equal is refused as well as shorter, because equal means
    escalation fires the instant the window closes, with nobody having been late.
    """
    if runbook.escalate_after <= route.acknowledge_within:
        return (
            f"this runbook escalates after {runbook.escalate_after} and "
            f"{route.severity.name} is acknowledged within {route.acknowledge_within}, so "
            "every alert escalates while the first responder is still inside the time they "
            "were given, and the rung above becomes the one that answers",
        )
    return ()


# ------------------------------------------------------------------------- escalation
class Tier(enum.IntEnum):
    """Who is asked next. An `IntEnum` so that further up is `>` and the order is assertable.

    Three rungs, and the third is outside the installation. There is deliberately no rung
    between the owner and the supplier: an intermediate tier in a single-tenant product a
    client runs themselves would be somebody with an account nobody has agreed to create.
    """

    #: Whoever is on call at the client. Has every reach the installation grants.
    ON_CALL = 1
    #: Whoever owns the installation at the client. Can authorise a change to it.
    INSTALLATION_OWNER = 2
    #: The supplier of the software. No account here, no entitlement and no reach.
    SUPPLIER = 3


#: The setting holding how the supplier is reached. A name, never a value; see
#: `THE_SUPPLIER_IS_A_CONTACT_IN_CONFIGURATION_AND_NEVER_A_VALUE_HERE`. Spelled in
#: `brain.config`'s own lower-case style so a deployment's settings read consistently.
SUPPLIER_CONTACT_SETTING: Final = "support_contact"


@dataclass(frozen=True)
class EscalationStep:
    """One rung: who is asked, what they can do about it, and what they may be told.

    `may_be_told` is prose rather than a classification, and that is deliberate. A
    classification says how sensitive something is; this says what category of fact travels
    to this rung, which is the sentence somebody needs when they are deciding whether to
    paste a log into a support ticket at two in the morning.
    """

    tier: Tier
    #: What this rung can do that the one below could not. Empty is refused: a rung that adds
    #: no authority is a rung that adds delay.
    can_do: str
    may_be_told: str
    #: The setting naming how this rung is reached, empty for a rung inside the installation
    #: whose people the entitlement model already resolves.
    reached_by: str = ""

    def __post_init__(self) -> None:
        if not self.can_do.strip():
            msg = (
                f"the {self.tier.name} rung says nothing it can do that the rung below "
                "could not, so escalating to it adds delay and no authority"
            )
            raise AlertingError(msg)
        if not self.may_be_told.strip():
            msg = (
                f"the {self.tier.name} rung does not say what it may be told, and the rung "
                "that does not say is the rung somebody widens under pressure. "
                f"{AN_ESCALATION_CARRIES_NO_MORE_THAN_THE_ALERT}"
            )
            raise AlertingError(msg)
        for finding in disclosure_findings(f"{self.can_do} {self.may_be_told}"):
            msg = f"the {self.tier.name} rung's own words disclose something: {finding}"
            raise AlertingError(msg)


#: The ladder, in order. Written once here rather than per alert, because an escalation path
#: that differs per alert is a path nobody remembers under pressure, and the thing that
#: differs per alert is how long before it is climbed, which is `Runbook.escalate_after`.
#:
#: The narrowing is the point and it runs the opposite way to authority: the rung that can do
#: most about the installation is told least about what is in it.
ESCALATION: Final[tuple[EscalationStep, ...]] = (
    EscalationStep(
        tier=Tier.ON_CALL,
        can_do=(
            "run the runbook: look at the schedule, start the mechanism by hand, and confirm "
            "from the console that it ran"
        ),
        may_be_told=(
            "everything the installation grants them, because they are inside it and the "
            "console filters what they see the way it filters everything else"
        ),
    ),
    EscalationStep(
        tier=Tier.INSTALLATION_OWNER,
        can_do=(
            "authorise a change to the installation: a setting, a restart, a schedule, or "
            "accepting that a guarantee is not holding until it is fixed"
        ),
        may_be_told=(
            "the same as the rung below, plus the fact that a guarantee about the "
            "installation is not currently holding, which is a fact about the software"
        ),
    ),
    EscalationStep(
        tier=Tier.SUPPLIER,
        can_do=(
            "say whether the mechanism is behaving as designed, and change the software if "
            "it is not"
        ),
        may_be_told=(
            "the name of the mechanism, what it is for, how long it has not run, and the "
            "runbook step that did not work. Nothing that came out of a store, and nothing "
            "about who asked for what"
        ),
        reached_by=SUPPLIER_CONTACT_SETTING,
    ),
)


def escalation_path(
    *, from_tier: Tier = Tier.ON_CALL, ladder: Sequence[EscalationStep] | None = None
) -> tuple[EscalationStep, ...]:
    """The rungs from here upward, in order.

    Takes a starting rung because an alert raised by whoever is on call is already at the
    first rung and offering it to them again is the reason people stop reading escalation
    paths. It never goes downward: a step below the one you are at is not an escalation, and
    a function that returned one would be a way to send an incident back to somebody who has
    already said they cannot fix it.
    """
    steps = ESCALATION if ladder is None else tuple(ladder)
    return tuple(step for step in steps if step.tier >= from_tier)


def escalation_gaps(ladder: Sequence[EscalationStep] | None = None) -> tuple[str, ...]:
    """Every way this ladder stops narrowing as it climbs.

    Three findings.

    A tier missing from the ladder is a rung nobody has decided about, and the one that goes
    missing is the last: a ladder ending at the owner reads as complete right up to the
    incident nobody at the client can fix.

    A ladder out of order climbs to the supplier and back to the person on call, and the
    reader follows it in the order it is written.

    A rung outside the installation with no way to reach it is the finding that matters most,
    because it fails at exactly the moment it is used. `Tier.SUPPLIER` is not somebody the
    entitlement model can resolve; if no setting names how they are reached, then the last
    rung of the ladder is a sentence with no telephone number under it.
    """
    steps = tuple(ESCALATION if ladder is None else ladder)
    present = {step.tier for step in steps}
    findings: list[str] = [
        f"{tier.name} is not on the ladder, so nothing says who is asked after the rung below it"
        for tier in Tier
        if tier not in present
    ]
    findings.extend(
        f"{later.tier.name} is listed after {earlier.tier.name} and is not above it, so the "
        "ladder does not climb in the order it is read in"
        for earlier, later in pairwise(steps)
        if later.tier <= earlier.tier
    )
    findings.extend(
        f"{step.tier.name} is outside the installation and no setting says how they are "
        "reached, so the last rung is a sentence with nothing under it"
        for step in steps
        if step.tier is Tier.SUPPLIER and not step.reached_by.strip()
    )
    return tuple(findings)


def supplier_step(contact: str, ladder: Sequence[EscalationStep] | None = None) -> str:
    """How the supplier is reached, from the value configured for `SUPPLIER_CONTACT_SETTING`.

    A function taking the value rather than a constant holding one, which is the whole of
    `THE_SUPPLIER_IS_A_CONTACT_IN_CONFIGURATION_AND_NEVER_A_VALUE_HERE` made structural:
    there is no expression in this module that evaluates to an address.

    An unset setting raises rather than returning a placeholder. A placeholder is a string
    somebody sends a message to, and the send succeeds; the escalation then reads as done in
    every log, which is the failure mode this whole module exists to make impossible.
    """
    if not contact.strip():
        msg = (
            f"{SUPPLIER_CONTACT_SETTING} is not set, so the last rung of the escalation "
            "ladder cannot be reached. A placeholder here is worse than this refusal: it is "
            "an address a message is sent to, and the escalation then reads as done"
        )
        raise AlertingError(msg)
    outside = escalation_path(from_tier=Tier.SUPPLIER, ladder=ladder)
    if not outside:
        msg = "the escalation ladder has no supplier rung, so there is nobody outside to reach"
        raise AlertingError(msg)
    step = outside[0]
    return f"{step.tier.name}: {contact}, who may be told {step.may_be_told}"
