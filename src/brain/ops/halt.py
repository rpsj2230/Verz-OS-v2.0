"""The stop button, and the five ways a stop button lies.

Nothing in this system could be stopped before this module. There is a rate limiter, an
admission controller, a lease, a budget and a queue, and every one of them is a *policy*: it
decides what is allowed under normal operation. None of them is a switch somebody throws when
operation is no longer normal, and the difference matters at exactly one moment, which is the
moment an administrator is watching something go wrong and needs it to stop now rather than
after they have worked out which policy to edit.

**A stop button that only refuses new work is the first lie.** Press it, the screen says
stopped, and a forty-minute job carries on writing to a connector. Refusing admission and
signalling what is already running are two separate effects, `Effect` names both, and
`stop_everything` sets both because that is what somebody pressing a button labelled "stop
everything" means. Something narrower may set one.

**A stop that lives in memory is the second lie.** The most likely thing to happen after an
administrator halts a misbehaving system is a deploy, and a halt held in a process is undone
by the restart that follows it. `Halt` is a value meant to be persisted and reloaded, it
carries everything needed to reconstruct itself, and `resume` is the only thing that ends one.

**A stop with an expiry is the third lie**, and it is the one that looks like good hygiene.
A halt that clears itself after an hour ends while everybody who mattered still believes the
system is stopped, and it ends quietly, at a time chosen by whoever wrote the default. There
is no TTL here, no scheduled clear and no field either could live on. See
`A_HALT_THAT_EXPIRES_ENDS_WHILE_EVERYBODY_BELIEVES_IT_IS_ON`.

**A stop nobody may press is the fourth lie.** Stopping is unilateral: one capability, no
approval, no second signature, no confirmation step that could itself fail. The guarded act is
*resume*, because restarting a system somebody halted is the decision that needs a reason
attached to it. `admin:halt` stops, `admin:halt` with a stated reason resumes, and the
asymmetry is the whole design: the cost of a wrong stop is an outage somebody can undo, and
the cost of a wrong resume is the incident continuing.

**A stop button nothing consults is the fifth lie, and it is the one this module shipped
with.** Every paragraph above was true of a value class that no code path asked anything:
halts could be declared, validated, stored, reloaded and rendered on a screen, and every
request was admitted anyway. `brain.ops.admission.decide` now asks, before it looks up a
budget row, because that is the one function every piece of work passes through before any
of it starts, and it is where `Effect.REFUSE_NEW` means something. It is handed a connector
and nothing else, so a halt on a department, an agent or a person is still enforced nowhere:
`ENFORCED_AXES` says which axes are real and `halt_gaps` reports a halt declared on one of
the others rather than letting an administrator watch a compromised account keep working.

**Reading fails closed, which is the opposite of everything else here.** Every cache in this
system treats "I could not tell" as "carry on", because a cache that fails closed turns a
Valkey blip into an outage. This one is inverted: `HaltState.unknown()` is halted. If the
store holding the halts cannot be reached, the honest answer is that we do not know whether
somebody stopped this system, and proceeding on that basis is how a halt gets ignored during
precisely the incident that caused it.

**A halt is not a permission decision, so it may say so out loud.** The rule that DENIED and
ABSENT must be indistinguishable governs disclosures about what exists and who may see it. A
halt discloses neither: telling somebody the system is paused reveals nothing about what they
could otherwise have read, and refusing them in silence would send them to a support channel
to report a bug that is not one. `refusal` therefore names the halt and its scope, and never
names the reason, which is written for an administrator and routinely contains the name of a
customer or a defect.

Scope: domain logic. Nothing here opens a connection or reads a clock; `now` is a parameter
and the halts are handed in, for the reason `brain.ops.limits` gives about policy that owns a
client being untestable at the boundary that matters.

Task ids: none
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Final

from brain.core.entitlement import Capability

#: Why stopping needs no approval and resuming does.
THE_GUARDED_ACT_IS_RESUME_AND_NEVER_STOP: Final = (
    "A stop button with a confirmation step is a stop button that can fail at the moment it "
    "is needed, and one requiring a second signature is one that does not work at three in "
    "the morning. Stopping is unilateral. Restarting a system somebody deliberately halted "
    "is the decision that carries risk, so that is the one that takes a stated reason and "
    "names who is overriding whom. A wrong stop is an outage somebody can undo; a wrong "
    "resume is the incident continuing while everybody believes it was handled."
)

#: Why there is no expiry, no TTL and no scheduled clear.
A_HALT_THAT_EXPIRES_ENDS_WHILE_EVERYBODY_BELIEVES_IT_IS_ON: Final = (
    "An automatic expiry looks like hygiene and is the worst property this type could have. "
    "It ends the halt at a time chosen by whoever wrote the default rather than by anybody "
    "watching, it ends it silently, and it ends it while every person who was told the "
    "system was stopped still believes that. A halt ends when somebody resumes it and there "
    "is no other way out, which is why this type has no duration field for one to live on."
)

#: Why refusing new work is not the same as stopping.
REFUSING_ADMISSION_DOES_NOT_STOP_WHAT_IS_ALREADY_RUNNING: Final = (
    "The cheap implementation of a stop button turns away new requests, which leaves every "
    "job already in flight running against the connector somebody is trying to protect. The "
    "screen says stopped and the writes continue. Refusing admission and signalling running "
    "work are two effects, a halt declares which it carries, and the one labelled stop "
    "everything carries both."
)

#: Why this is the one thing in the system that fails closed.
IF_WE_CANNOT_TELL_WHETHER_WE_ARE_HALTED_WE_ARE_HALTED: Final = (
    "Every other cache here treats an unreachable store as permission to carry on, because "
    "failing closed would turn a Valkey blip into an outage. This one is inverted. The "
    "moment the halt store is unreachable is disproportionately likely to be the moment "
    "something is wrong, and carrying on then means ignoring a halt during the incident that "
    "caused it. Unknown is halted, and an administrator who cannot reach the store can still "
    "reach the machine."
)

#: Why a halt may be announced when a denial may not.
A_HALT_DISCLOSES_NOTHING_ABOUT_WHAT_ANYBODY_MAY_SEE: Final = (
    "DENIED and ABSENT must be indistinguishable, and a halt is neither: it says the system "
    "is paused, which reveals nothing about what this person could otherwise have read. "
    "Refusing them in silence would send somebody to a support channel to report a bug that "
    "does not exist. The refusal names the halt and its scope and never the reason, which is "
    "written by an administrator for an administrator and routinely names a customer or a "
    "defect."
)

#: Why a value class describing a switch is not a switch.
A_STOP_BUTTON_NOTHING_CONSULTS_IS_NOT_A_STOP_BUTTON: Final = (
    "The other four lies are special cases of this one. A halt that is declared, validated, "
    "stored, reloaded and shown on a screen, while every request is admitted anyway, is the "
    "most complete version of a screen that says stopped over a system that is not. The "
    "REFUSE_NEW effect lands in `brain.ops.admission.decide`, which is the function every "
    "piece of work passes through before any of it starts, and it is asked before the "
    "budget lookup so that a halted system refuses for the reason somebody halted it rather "
    "than for the arithmetic underneath."
)

#: Why a halted request is turned away rather than handed a position and a time.
A_HALTED_REQUEST_IS_TURNED_AWAY_RATHER_THAN_GIVEN_A_TIME: Final = (
    "Admission hands a queue position and an expected wait to work nobody is waiting for, "
    "and both numbers come out of budget arithmetic: how many units must depart before "
    "there is room. A halt has no arithmetic. It ends when a person resumes it, so any time "
    "offered here would be invented here and believed there, and the client would come back "
    "into the same refusal having been told it would not. A halted request sheds, with no "
    "position and no retry hint."
)

#: The capability that stops and resumes. One, deliberately: see the module docstring.
HALT_CAPABILITY: Final = Capability(value="admin:halt")

#: The shortest reason that says anything. "x" is not a reason and neither is "test".
MINIMUM_REASON = 12


class HaltError(Exception):
    """Raised when a halt is declared or lifted in a way that would not actually work."""


class Effect(enum.StrEnum):
    """What a halt does. Two members, and a halt carries at least one.

    Separate because they are separately implementable and separately forgettable, which is
    `REFUSING_ADMISSION_DOES_NOT_STOP_WHAT_IS_ALREADY_RUNNING`. There is no third member for
    "warn", because a halt that warns is a notification and this type is for the case where
    somebody has decided warning is no longer enough.
    """

    #: Nothing new is admitted. The queue keeps its work; nothing leaves it.
    REFUSE_NEW = "refuse_new"
    #: What is already running is told to stop at its next safe point.
    SIGNAL_RUNNING = "signal_running"


class HaltScope(enum.StrEnum):
    """What a halt covers. Ordered narrow to wide in intent, though nothing here compares them.

    Deliberately not an `IntEnum`. These do not nest the way `console.reads.Plane` does: a
    halt on one connector and a halt on one department overlap without either containing the
    other, and an ordering would invite a comparison that is wrong in both directions.
    """

    #: Every request, every job, every agent, every connector.
    EVERYTHING = "everything"
    #: One department's work, wherever it runs.
    DEPARTMENT = "department"
    #: One agent, everywhere it is invoked.
    AGENT = "agent"
    #: One connector, so nothing reaches a source that is misbehaving or leaking.
    CONNECTOR = "connector"
    #: One person's work, which is what an account compromise needs.
    PERSON = "person"


#: The scopes that name something, and therefore require a target.
#:
#: `EVERYTHING` is the exception and is why this is a set rather than a truthiness check on
#: the target: a halt scoped to everything with a target is a halt somebody thought was
#: narrower than it is, and it is refused rather than silently widened.
TARGETED: Final[frozenset[HaltScope]] = frozenset(
    {HaltScope.DEPARTMENT, HaltScope.AGENT, HaltScope.CONNECTOR, HaltScope.PERSON}
)

#: The scopes something actually consults. Everything else is a halt that refuses nothing.
#:
#: `brain.ops.admission.decide` is the only call site, and an `AdmissionRequest` carries a
#: resource, a lane, a traffic class and the connector the resource belongs to. It carries
#: no principal, no department and no agent, so a halt on one of those axes can be declared
#: and stored and in force and stop nothing at all. `halt_gaps` reports one, because the
#: administrator declaring a halt on a compromised account is not in a position to go and
#: read which call sites exist. Widen this set when a call site that knows the axis asks.
ENFORCED_AXES: Final[frozenset[HaltScope]] = frozenset({HaltScope.EVERYTHING, HaltScope.CONNECTOR})


@dataclass(frozen=True)
class Halt:
    """One halt in force. A value, meant to be written down and read back after a restart.

    **No expiry field, and that is the load-bearing absence.** See
    `A_HALT_THAT_EXPIRES_ENDS_WHILE_EVERYBODY_BELIEVES_IT_IS_ON`. `halt_gaps` fails if one
    appears, because the field would arrive with a plausible default long before anybody
    noticed the property it removed.
    """

    scope: HaltScope
    #: What the halt names, for a targeted scope. Empty for `EVERYTHING`.
    target: str
    #: The principal who stopped it. Present so a resume can name who is being overridden.
    declared_by: str
    at: datetime
    #: Why, in words, for an administrator. Never shown to the person who is refused.
    reason: str
    effects: frozenset[Effect] = frozenset({Effect.REFUSE_NEW, Effect.SIGNAL_RUNNING})

    def __post_init__(self) -> None:
        if self.scope in TARGETED and not self.target.strip():
            msg = (
                f"a {self.scope.value} halt names nothing, so it either covers everything or "
                "covers nothing and there is no way to tell which was meant"
            )
            raise HaltError(msg)
        if self.scope is HaltScope.EVERYTHING and self.target.strip():
            msg = (
                f"a halt on everything also names {self.target!r}, which is somebody "
                "expecting it to be narrower than it is; declare the narrower scope instead"
            )
            raise HaltError(msg)
        if not self.declared_by.strip():
            msg = "a halt nobody declared cannot be resumed, because there is nobody to override"
            raise HaltError(msg)
        if len(self.reason.strip()) < MINIMUM_REASON:
            msg = (
                f"{self.reason!r} is not a reason, and the person deciding whether to resume "
                "this at three in the morning has nothing else to go on"
            )
            raise HaltError(msg)
        if not self.effects:
            msg = (
                "a halt with no effects is a row in a table; it refuses nothing and stops "
                "nothing while reporting itself as in force"
            )
            raise HaltError(msg)

    def covers(
        self, *, department: str = "", agent: str = "", connector: str = "", person: str = ""
    ) -> bool:
        """Whether this halt applies to one piece of work.

        Every axis is optional because a request does not always have all of them: a direct
        question has a person and no agent, a scheduled job has an agent and no person. An
        axis the caller does not supply cannot match a halt on that axis, which is the safe
        direction: it means a narrower halt does not catch work it was not told about, while
        `EVERYTHING` catches everything regardless.
        """
        if self.scope is HaltScope.EVERYTHING:
            return True
        named = {
            HaltScope.DEPARTMENT: department,
            HaltScope.AGENT: agent,
            HaltScope.CONNECTOR: connector,
            HaltScope.PERSON: person,
        }[self.scope]
        return bool(named) and named == self.target

    def refuses_new(self) -> bool:
        return Effect.REFUSE_NEW in self.effects

    def signals_running(self) -> bool:
        return Effect.SIGNAL_RUNNING in self.effects

    def refusal(self) -> str:
        """What the person who is refused reads. Names the scope, never the reason.

        See `A_HALT_DISCLOSES_NOTHING_ABOUT_WHAT_ANYBODY_MAY_SEE` for why this speaks at all,
        and the last sentence of it for why it stops where it does.
        """
        if self.scope is HaltScope.EVERYTHING:
            return "This system has been paused by an administrator. Nothing is being lost."
        return (
            f"Work for this {self.scope.value} has been paused by an administrator. "
            "Nothing is being lost."
        )


@dataclass(frozen=True)
class HaltState:
    """Everything in force, or the admission that we do not know.

    `known` is what makes this fail closed. A caller that could not read the store builds
    `HaltState.unknown()` rather than an empty one, and an empty one is the *only* state that
    admits work.
    """

    halts: tuple[Halt, ...] = ()
    #: False when the store could not be read. See
    #: `IF_WE_CANNOT_TELL_WHETHER_WE_ARE_HALTED_WE_ARE_HALTED`.
    known: bool = True

    @classmethod
    def unknown(cls) -> HaltState:
        """The state to build when the halt store cannot be reached. Halted."""
        return cls(halts=(), known=False)

    def blocking(
        self,
        *,
        department: str = "",
        agent: str = "",
        connector: str = "",
        person: str = "",
    ) -> tuple[Halt, ...]:
        """Every halt in force over this piece of work, widest first.

        Widest first so a caller reporting one reports the most general, which is the one an
        administrator will recognise. Empty when nothing applies, and empty is not the same
        as `known` being False, which is why `admits` checks that separately.
        """
        found = [
            one
            for one in self.halts
            if one.covers(department=department, agent=agent, connector=connector, person=person)
        ]
        return tuple(sorted(found, key=lambda one: (one.scope is not HaltScope.EVERYTHING, one.at)))

    def admits(
        self,
        *,
        department: str = "",
        agent: str = "",
        connector: str = "",
        person: str = "",
    ) -> bool:
        """Whether new work may start. False when we could not tell.

        The unknown case is first and deliberately unconditional: no argument, no scope and
        no combination of them can produce True from a state that was never read.
        """
        if not self.known:
            return False
        return not any(
            one.refuses_new()
            for one in self.blocking(
                department=department, agent=agent, connector=connector, person=person
            )
        )

    def refusal(
        self,
        *,
        department: str = "",
        agent: str = "",
        connector: str = "",
        person: str = "",
    ) -> str:
        """What to tell somebody whose work was refused, including when we do not know.

        The unknown case gets its own sentence rather than borrowing a halt's, because
        claiming an administrator paused the system when nobody did would send whoever is
        on call looking for a halt that does not exist.

        **Only a halt that refuses new work may produce a sentence here**, and the first
        version of this took every covering halt instead. A halt carrying `SIGNAL_RUNNING`
        alone stops what is running and admits more, so `admits` returned True while this
        returned "your work has been paused", and the obvious way to use a function called
        `refusal`, which is to refuse when it is not empty, refused work nothing had
        stopped. Empty here and True from `admits` are now the same answer.
        """
        if not self.known:
            return (
                "This system cannot confirm whether it has been paused, so it is not "
                "starting new work. Nothing is being lost."
            )
        refusing = [
            one
            for one in self.blocking(
                department=department, agent=agent, connector=connector, person=person
            )
            if one.refuses_new()
        ]
        if not refusing:
            return ""
        return refusing[0].refusal()


def stop_everything(*, declared_by: str, at: datetime, reason: str) -> Halt:
    """The button. Both effects, no target, no approval.

    A named constructor rather than a `Halt(...)` at each call site, because the one halt
    that must be impossible to get subtly wrong is this one, and `effects=frozenset({REFUSE_NEW})`
    is a plausible-looking thing for somebody in a hurry to type.
    """
    return Halt(
        scope=HaltScope.EVERYTHING,
        target="",
        declared_by=declared_by,
        at=at,
        reason=reason,
        effects=frozenset({Effect.REFUSE_NEW, Effect.SIGNAL_RUNNING}),
    )


@dataclass(frozen=True)
class Resume:
    """Lifting a halt, which is the act that carries the risk and therefore the paperwork.

    Names the halt being lifted, who is lifting it, and why. The reason is required to the
    same length as a halt's, because "resumed" tells the next reader nothing about whether
    the thing that caused the halt was fixed.
    """

    halt: Halt
    by: str
    at: datetime
    reason: str

    def __post_init__(self) -> None:
        if not self.by.strip():
            msg = "a resume by nobody leaves no one accountable for restarting a halted system"
            raise HaltError(msg)
        if len(self.reason.strip()) < MINIMUM_REASON:
            msg = (
                f"{self.reason!r} is not a reason to restart a system somebody stopped; the "
                "next reader needs to know whether the cause was fixed or overridden"
            )
            raise HaltError(msg)
        if self.at < self.halt.at:
            msg = (
                "this resume predates the halt it lifts, so the halt would be reinstated by "
                "any correct replay of the ledger"
            )
            raise HaltError(msg)

    def overrides_somebody_else(self) -> bool:
        """Whether one person is restarting what another stopped.

        Not refused, because a halt whose declarer is asleep must still be liftable, and a
        rule requiring the same person is a rule that turns an incident into a phone call.
        Reported instead, so the audit row and the console can both say so.
        """
        return self.by != self.halt.declared_by

    def render(self) -> str:
        """The sentence an administrator reads afterwards."""
        who = (
            f"{self.by} restarted work {self.halt.declared_by} had stopped"
            if self.overrides_somebody_else()
            else f"{self.by} restarted work they had stopped"
        )
        target = f" ({self.halt.target})" if self.halt.target else ""
        return f"{who}: {self.halt.scope.value}{target}. {self.reason}"


def halt_gaps(halts: Sequence[Halt] = ()) -> tuple[str, ...]:
    """Everything about a halt arrangement that would make the stop button lie.

    Three checks against the shape of the type and one against a set of halts somebody hands
    in. The shape checks are here rather than in a review comment because the field they
    guard against would arrive with a sensible default and remove a property nobody would
    notice was gone until an incident.
    """
    gaps: list[str] = []

    names = {one.name for one in fields(Halt)}
    for forbidden in ("expires_at", "expires", "ttl", "until", "duration", "clears_at"):
        if forbidden in names:
            gaps.append(
                f"Halt carries {forbidden}, so a halt ends at a time chosen by whoever wrote "
                "its default rather than by anybody watching, and it ends silently while "
                "every person who was told the system is stopped still believes that"
            )
    for forbidden in ("enabled", "active", "suppressed", "muted"):
        if forbidden in names:
            gaps.append(
                f"Halt carries {forbidden}, so a halt can be in the store and doing nothing, "
                "which is the state an administrator reading the list cannot distinguish "
                "from one that is working"
            )
    if "reason" not in names:
        gaps.append(
            "Halt carries no reason, so whoever decides whether to resume it has nothing to "
            "go on but the fact that somebody once pressed a button"
        )

    for one in halts:
        if not one.signals_running():
            gaps.append(
                f"the {one.scope.value} halt {one.target or 'on everything'} refuses new work "
                "and does not signal what is already running, so the screen reads stopped "
                "while in-flight jobs keep writing"
            )
        if not one.refuses_new():
            gaps.append(
                f"the {one.scope.value} halt {one.target or 'on everything'} signals what is "
                "running and admits more of it, so whatever it stops is replaced by the next "
                "request and an operator watching sees churn rather than a stop"
            )
        if one.scope not in ENFORCED_AXES:
            gaps.append(
                f"the {one.scope.value} halt {one.target or 'on everything'} is declared on "
                "an axis nothing consults: admission is handed a connector and nothing else, "
                "so this halt is in force in the store and refuses no request anywhere"
            )

    return tuple(gaps)


def in_force(halts: Iterable[Halt]) -> HaltState:
    """A readable state from whatever the store returned.

    Trivial, and it exists so callers have something to call that is not the constructor:
    the constructor's default for `known` is True, and a caller who wrapped an unreachable
    store's empty list in `HaltState(())` would get a state claiming to know there are none.
    Handing that mistake a name it can be looked for is worth one function.
    """
    return HaltState(halts=tuple(halts), known=True)


#: What a call site that did not ask the store gets. Nothing is halted, and we know it.
#:
#: A default exists at all because `brain.ops.admission.decide` had call sites before this
#: module did, and a required parameter would have stopped those callers rather than the
#: work they admit. The name is the point: omitting the argument is a claim, and this is the
#: claim written down where somebody reading the call can see it being made.
#:
#: Deliberately not `HaltState.unknown()`. Failing every unconverted call site closed reads
#: like the safe choice and is the opposite of one: it would halt the system permanently and
#: from nowhere, which is the state this module exists to make deliberate and reversible.
NOTHING_HALTED: Final = HaltState()
