"""Refusing to drive a website for something an API already does, and the one way out.

A browser is the worst way to talk to a system that has an API. It is slower, it breaks when
somebody moves a button, it needs a session and therefore a credential typed into a form, and
it puts a model in front of a document an attacker may have written. Every argument in this
package exists because sometimes there is no API. When there is one, none of that cost buys
anything, and M19.6.7 asks for the loader to say so.

**The refusal is decided from the registry, not from a list kept here.** A target declares
the tool names that do its work without a browser, and this asks a `ToolRegistry` which of
those actually exist. A declared name nothing registers is not a reason to refuse: the API
was planned and is not there, and refusing on it would block the browser route for a
connector nobody has built. A registered one is, because the alternative is present and
callable today.

**An exemption expires and a halt does not, and the two are the same field with opposite
signs.** `brain.ops.halt` argues at length that an expiry is the worst property a halt could
have, because it ends the protection at a time chosen by whoever wrote the default while
everybody still believes the system is stopped. An exemption is the mirror: it is a
permission, and a permission with no end is a decision nobody revisits, granted by somebody
who has probably moved on, still in force long after the API it worked around shipped.
`A_PERMISSION_WITH_NO_EXPIRY_IS_A_DECISION_NOBODY_REVISITS` says so beside the type, so a
reader who has just come from `halt.py` does not conclude that one of the two files is wrong.

**A named approver, not a flag.** The failure this prevents is an exemption that exists
because it was convenient: a boolean somewhere, set during a demo, never removed. Requiring a
person's name and a reason of real length, to the same minimum `brain.ops.halt` requires of a
halt, means the row itself says who decided and why. The reuse is deliberate rather than
tidy: "x" is not a reason in either place and the two limits should not drift apart.

Rejected: refusing at run time instead of at load. A skill refused when it runs has already
been offered to a model, chosen, and started, and the person waiting is told at the end that
it was not allowed. Load is where an author can still be told to use the connector.

Task ids: M19.6.7
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.browsing.targets import Target
from brain.ops.halt import MINIMUM_REASON
from brain.tools.registry import ToolRegistry
from brain.tools.skills import Skill

#: The longest an exemption may run. A quarter, because that is roughly the interval at which
#: somebody will be reviewing the connector backlog anyway, and because a year is long enough
#: for the person who signed it to have left.
MAX_EXEMPTION = timedelta(days=90)

#: Why this field is required here and forbidden on a halt.
A_PERMISSION_WITH_NO_EXPIRY_IS_A_DECISION_NOBODY_REVISITS: Final = (
    "brain.ops.halt refuses an expiry because a halt is a protection, and a protection that "
    "ends on a timer ends while everybody still believes it is on. An exemption is a "
    "permission, and the failure runs the other way: it stays in force after the reason for "
    "it is gone, granted by somebody who has left, working around an API that shipped two "
    "quarters ago. Same field, opposite sign, and both are load bearing."
)

#: Why the check asks a registry rather than reading a list.
AN_API_THAT_IS_PLANNED_IS_NOT_AN_API: Final = (
    "A target may name the tools that would replace it long before any of them exist. "
    "Refusing the browser route on a declared name would block the only working route to a "
    "system because somebody wrote down an intention. The registry is asked instead, so the "
    "refusal starts exactly when the alternative becomes callable."
)


class SkillGateError(Exception):
    """An exemption was written in a way that would not be reviewed."""


@dataclass(frozen=True)
class Exemption:
    """One signed permission to use a browser where an API exists.

    Every field is required and none has a default. A default approver would be whoever the
    default named, a default expiry would be whatever the default was, and both would be
    supplied by the code rather than by the person taking the decision.
    """

    skill: str
    target: str
    approver: str
    expires_at: datetime
    reason: str

    def __post_init__(self) -> None:
        if not self.skill.strip():
            msg = "an exemption naming no skill exempts whichever skill reads it first"
            raise SkillGateError(msg)
        if not self.target.strip():
            msg = (
                f"exemption for {self.skill!r} names no target, so it would permit the "
                "browser route to every system rather than to the one that was argued about"
            )
            raise SkillGateError(msg)
        if not self.approver.strip():
            msg = (
                f"exemption for {self.skill!r} names no approver; an exemption nobody signed "
                "is a flag somebody set, and there is no one to ask when it is reviewed"
            )
            raise SkillGateError(msg)
        if len(self.reason.strip()) < MINIMUM_REASON:
            msg = (
                f"{self.reason!r} is not a reason to drive a website for something an API "
                "already does, and whoever reviews this in three months has nothing else"
            )
            raise SkillGateError(msg)

    def is_live(self, now: datetime) -> bool:
        return now < self.expires_at

    def covers(self, skill: str, target: str, now: datetime) -> bool:
        """Whether this exemption applies. All three, and the clock is one of them."""
        return self.skill == skill and self.target == target and self.is_live(now)


def granted_at(exemption: Exemption, *, granted: datetime) -> timedelta:
    """How long an exemption was written to run. Used to refuse one that runs too long.

    Separate from the type because an `Exemption` carries the end and not the beginning: the
    row is about when it stops, and when it started is a question for whoever is writing it
    rather than a field that would then have to be kept truthful.
    """
    return exemption.expires_at - granted


def available_api_tools(target: Target, registry: ToolRegistry) -> tuple[str, ...]:
    """The declared API alternatives that are actually registered. See
    `AN_API_THAT_IS_PLANNED_IS_NOT_AN_API`."""
    return tuple(sorted(name for name in target.api_tools if registry.has(name)))


def load_gaps(
    skill: Skill,
    target: Target,
    registry: ToolRegistry,
    exemptions: tuple[Exemption, ...] = (),
    *,
    now: datetime,
) -> tuple[str, ...]:
    """Every reason this browser skill should not be loaded against this target.

    Findings rather than a raise, in the shape `brain.ops.halt.halt_gaps` uses, because an
    author fixing one of these wants all of them: being told about the API tool, then about
    the expired exemption, then about the missing approver, one build at a time, is three
    round trips for one edit.

    An expired exemption produces its own finding rather than being silently ignored. The two
    states look identical from the outside and mean different things: nobody asked, or
    somebody asked and the answer has run out.
    """
    alternatives = available_api_tools(target, registry)
    if not alternatives:
        return ()
    live = [one for one in exemptions if one.covers(skill.name, target.name, now)]
    if live:
        return ()
    findings = [
        f"skill {skill.name!r} drives {target.name!r} with a browser and "
        f"{', '.join(alternatives)} already does this without one; a browser route needs an "
        "exemption naming an approver and an expiry"
    ]
    for one in exemptions:
        if one.skill == skill.name and one.target == target.name and not one.is_live(now):
            findings.append(
                f"the exemption {one.approver} signed for {skill.name!r} expired at "
                f"{one.expires_at.isoformat()}; it is reported rather than ignored because "
                "an expired permission and an absent one are different conversations"
            )
        if granted_at(one, granted=now) > MAX_EXEMPTION:
            findings.append(
                f"the exemption for {one.skill!r} runs past {MAX_EXEMPTION.days} days, which "
                "is longer than anybody will remember why it was signed"
            )
    return tuple(findings)


def may_load(
    skill: Skill,
    target: Target,
    registry: ToolRegistry,
    exemptions: tuple[Exemption, ...] = (),
    *,
    now: datetime,
) -> bool:
    """Whether the loader admits this skill. True when `load_gaps` finds nothing.

    Defined in terms of the findings rather than beside them, so there is no way for the
    verdict and the explanation to disagree. Two functions each deciding would eventually
    produce a skill that loads with a finding against it, or one refused with nothing to
    show the author.
    """
    return not load_gaps(skill, target, registry, exemptions, now=now)
