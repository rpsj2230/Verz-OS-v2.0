"""A browser write runs at Assisted, and one signed exception per surface is the only way past it.

M19.7.3 reads like a new ceiling and most of it is already in place. `brain.tools.registry.
default_rung` puts every WRITE and SEND at ASSISTED, and `brain.browsing.envelope.tier_for`
composes an agent's ceiling with that through `rung_ceiling`, which is `min`. So an agent
configured AUTONOMOUS still gets a browser submit at ASSISTED, and ASSISTED means the envelope
waits for a person (`brain.browsing.approval`). **What this module adds is the exception, and
the exception is the dangerous half**, because it is the one route by which a write on
somebody else's website happens with nobody looking.

**The exception removes the side effect's tightening and never the agent's.** A live exception
on a surface lets a write there run at the agent's own rung instead of at `min(rung,
ASSISTED)`. An agent whose leash says ASSISTED or SHADOW is not lifted by it: the signature is
about the surface and says nothing about how far this agent is trusted, and a surface exception
that could raise an agent would make the person signing it the author of every agent's rung.
See `AN_EXCEPTION_LIFTS_THE_SURFACE_AND_NEVER_THE_AGENT`.

**Per surface, and not per target or per verb.** A target is a whole system and one of its
surfaces is the export button while another files a tax return; an exception on the target
would sign for both. A verb is too narrow in the other direction, because what a click does on
a surface is the page's decision (`brain.browsing.targets.THE_PAGE_DECIDES_WHAT_A_CLICK_DOES`),
so a person signing for the submit and not the click has signed for less than will happen.

**Signed means a named person who could do it themselves, a reason, and an end.** The same shape
as `brain.browsing.skill_gate.Exemption`, reusing its quarter and `brain.ops.halt`'s minimum
reason, so the two permissions in this package cannot drift apart on what counts as a reason or
how long a signature may stand. The signer must hold the surface's own capability at the moment
of signing, for the reason `brain.console.role_surfaces` gives about approvers: somebody who
could not perform a write must not be able to wave an agent through performing it.

**The exception is read when the envelope is compiled and not again.** An exception that
expires mid-run does not stop the run, and that is `brain.browsing.enforcer`'s rule rather than
a gap: the policy is fixed at container start and whatever it was compiled from cannot reach it
afterwards. The envelope's digest covers which writes were compiled to run unattended, so an
approval raised under one set of exceptions does not match an envelope compiled under another.

**Not built:** anywhere to keep an exception. Like `skill_gate.Exemption`, it is configuration
passed to the compiler; the signature is on the value and recording it in the ledger is a leash
change nobody has wired.

Task ids: M19.7.3
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.browsing.skill_gate import MAX_EXEMPTION
from brain.browsing.targets import Target, Verb, is_write
from brain.core.entitlement import EntitlementSet
from brain.gate.injection import AutonomyTier
from brain.ops.halt import MINIMUM_REASON

#: Why the exception cannot raise an agent.
AN_EXCEPTION_LIFTS_THE_SURFACE_AND_NEVER_THE_AGENT: Final = (
    "The Assisted ceiling on a browser write comes from two places: the agent's leash and the "
    "side effect of the verb. A signed surface exception removes the second and leaves the "
    "first, so a write runs unattended only where the agent is already trusted to act alone "
    "and a person has also signed for the surface. Letting it lift the agent too would make "
    "whoever signs for a surface the author of every agent's rung on it."
)

#: Why the default for a browser write is a person.
A_WRITE_ON_SOMEBODY_ELSES_WEBSITE_WAITS_FOR_A_PERSON: Final = (
    "A browser write lands in a system of record that is not ours, through a page whose "
    "behaviour the page decides, and there is no undo on the other side. Assisted is the rung "
    "at which a person reads the envelope before the container starts, and it is the ceiling "
    "for every write until somebody who could perform that write signs for the surface."
)


class AutonomyError(Exception):
    """An exception was signed in a way nobody could review, or by somebody who may not."""


@dataclass(frozen=True)
class SurfaceException:
    """One signed permission for writes on one surface to run without envelope approval.

    Every field is required. A default signer is whoever the default names and a default expiry
    is whatever the code chose, and neither is a person taking a decision.
    """

    target: str
    surface: str
    signed_by: str
    expires_at: datetime
    reason: str

    def __post_init__(self) -> None:
        if not self.target.strip() or not self.surface.strip():
            msg = (
                "a surface exception names no target or no surface, so it would sign for "
                "whichever surface read it first"
            )
            raise AutonomyError(msg)
        if not self.signed_by.strip():
            msg = (
                f"the exception for {self.target}.{self.surface} names no signer; an exception "
                "nobody signed is a flag somebody set"
            )
            raise AutonomyError(msg)
        if len(self.reason.strip()) < MINIMUM_REASON:
            msg = (
                f"{self.reason!r} is not a reason for writes on {self.target}.{self.surface} to "
                "run with nobody looking, and whoever reviews it has nothing else"
            )
            raise AutonomyError(msg)

    def covers(self, target: str, surface: str, now: datetime) -> bool:
        """Whether this exception applies. The target, the surface and the clock, all three."""
        return self.target == target and self.surface == surface and now < self.expires_at


def sign(
    target: Target,
    surface: str,
    *,
    signer: EntitlementSet,
    expires_at: datetime,
    reason: str,
    now: datetime,
) -> SurfaceException:
    """Sign an exception for one declared write surface, or refuse and say why.

    The refusals are the whole of it. A surface the target does not declare, one with no write
    verb to except, a signer who could not perform the write, an end already past and an end
    beyond the quarter are each refused here rather than producing a value that later reads as
    a signature.
    """
    declared = target.surface(surface)
    if declared is None:
        msg = f"target {target.name!r} declares no surface {surface!r}, so there is nothing to sign"
        raise AutonomyError(msg)
    if not declared.writes():
        msg = (
            f"surface {target.name}.{surface} declares no write, so an exception on it signs "
            "for nothing and would read on review as though it had"
        )
        raise AutonomyError(msg)
    if not signer.holds(declared.capability, now):
        msg = (
            f"the signer may not perform writes on {target.name}.{surface} themselves, so they "
            "may not sign for an agent to perform them unattended"
        )
        raise AutonomyError(msg)
    if expires_at <= now:
        msg = "an exception that has already ended signs for nothing"
        raise AutonomyError(msg)
    if expires_at - now > MAX_EXEMPTION:
        msg = (
            f"an exception running past {MAX_EXEMPTION.days} days outlives anybody's memory of "
            "why it was signed"
        )
        raise AutonomyError(msg)
    return SurfaceException(
        target=target.name,
        surface=surface,
        signed_by=signer.principal_id,
        expires_at=expires_at,
        reason=reason,
    )


def runs_unattended(
    target: Target,
    surface: str,
    verb: Verb,
    *,
    ceiling: AutonomyTier,
    exceptions: Sequence[SurfaceException],
    now: datetime,
) -> bool:
    """Whether a write on this surface may run without envelope approval.

    Only a write, only under an agent whose own ceiling is AUTONOMOUS, and only with a live
    exception for exactly this target and surface. A read is never "unattended" because it
    never waited for anybody, and answering True for one would put reads into a set whose
    meaning is "writes nobody approved".
    """
    if not is_write(verb):
        return False
    if ceiling < AutonomyTier.AUTONOMOUS:
        return False
    return any(one.covers(target.name, surface, now) for one in exceptions)
