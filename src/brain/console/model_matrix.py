"""The routing matrix with each rung's health beside it, and what has no fallback left.

`brain.models.routing.RoutingChain` is the matrix and `brain.models.health.ProviderHealth` is
the evidence about each rung in it. Both exist and neither knows about the other, which is
right: a breaker that consulted the chain would be a breaker whose verdict depended on where
the deployment happened to be listed. Joining them is a screen's job, and this is the screen.

**Every rung appears, whatever state it is in, and there is no parameter that would remove
one.** A matrix screen with a "hide unhealthy" filter is a screen that can be left in a state
where it says the estate is fine, and the reader who leaves it that way is the reader who set
the filter during the last incident. This is the same defect
`brain.ops.controls.A_MECHANISM_WITH_NO_CALLER_IS_WORSE_THAN_NO_MECHANISM` names one layer
up: a display that can be wrong in the reassuring direction is worse than no display. See
`A_MATRIX_THAT_CAN_HIDE_AN_OPEN_RUNG_IS_A_SCREEN_THAT_SAYS_EVERYTHING_IS_FINE`.

**A deployment with no health record is closed, not unknown.** `ProviderHealth.for_deployment`
already makes that decision and says why: starting unknown-and-blocked would mean a fresh
install serves nothing until something probes every rung. The screen has to make the same
choice or it contradicts the router, and the contradiction runs the reassuring way round: a
fresh install would show a matrix of question marks while answering every question correctly.
See `A_RUNG_NOTHING_HAS_FAILED_AGAINST_IS_HEALTHY_AND_NOT_UNKNOWN`.

**The finding worth waking somebody for is a tier with no rung left, and it is not visible one
row at a time.** Each row can say "open" without anything being wrong, because that is what a
chain is for. A tier whose every rung is open cannot answer at all, and the difference between
those two is a fact about the set rather than about any member of it. `exhausted_tiers` is
that question asked directly, so a screen does not leave it to whoever is counting the amber
rows. See `A_TIER_WITH_EVERY_RUNG_OPEN_IS_AN_OUTAGE_AND_NOT_A_COLOUR`.

**One grant decides the whole screen, and that is a real difference from every other console
module here.** `brain.console.spend_view` filters row by row because a spend row is about a
person and a department. A rung is a fact about the product: which model this software can
route to is the same on every installation, is written in this repository, and is in the
release notes. There is nothing here that a reader could learn about their colleagues or
their company, so the reach question is asked once, about the screen, and the answer is all of
it or none of it. Saying that out loud matters because the row-by-row shape is the house
pattern and departing from it silently would read as an oversight.

What was rejected. A percentage of failed requests per rung, which is what an operator asks
for first: the live ring is capped at a window, so a ratio over it is a ratio over the last
few calls rather than over traffic, and printing it as "12% failing" invites a reader to
multiply it by a request count they do not have. The rings are reported as what they are, a
count of recent outcomes, and `probe_fail_ratio` stays where it is, beside the note saying it
is reported and never fed into the opening rules.

Task ids: M27.2.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.models.health import OpenReason, ProviderHealth
from brain.models.routing import BreakerState, RoutingChain, RungRole, Tier


class ModelMatrixError(Exception):
    """Raised when a matrix view would state something the chain does not support."""


# ------------------------------------------------------------------ written-down reasons
#: Why there is no filter on this screen.
A_MATRIX_THAT_CAN_HIDE_AN_OPEN_RUNG_IS_A_SCREEN_THAT_SAYS_EVERYTHING_IS_FINE: Final = (
    "A hide-unhealthy filter can be left switched on, and the person who leaves it that way "
    "is the person who set it during the last incident. The screen then reports a healthy "
    "estate, which is the failure a display is least able to recover from: nobody checks a "
    "green screen. Every rung in the chain appears, in position order, and no parameter here "
    "removes one."
)

#: Why a rung nobody has evidence about is shown as healthy.
A_RUNG_NOTHING_HAS_FAILED_AGAINST_IS_HEALTHY_AND_NOT_UNKNOWN: Final = (
    "brain.models.health.ProviderHealth.for_deployment starts closed rather than unknown, "
    "because starting unknown-and-blocked means a fresh install serves nothing until "
    "something has probed every rung. A screen that showed the same rung as unknown would "
    "contradict the router, and it would contradict it in the alarming direction: a correct "
    "fresh install rendered as a matrix of question marks."
)

#: Why the set is asked a question the rows cannot answer.
A_TIER_WITH_EVERY_RUNG_OPEN_IS_AN_OUTAGE_AND_NOT_A_COLOUR: Final = (
    "One open rung is a chain doing its job. A tier whose every rung is open cannot answer "
    "at all, and that is a fact about the set rather than about any row in it, so a screen "
    "that renders state per row leaves the reader to notice it by counting. It is asked "
    "directly instead, and it is the one thing on this screen worth an alert."
)

#: Why the reach question is asked once here and row by row everywhere else.
A_RUNG_IS_A_FACT_ABOUT_THE_PRODUCT_AND_NOT_ABOUT_ANYBODY: Final = (
    "Which models this software can route to is the same on every installation, is written "
    "in this repository and is in the release notes. There is nothing in a rung that a "
    "reader could learn about a colleague, a client or a department, so the entitlement is "
    "asked once about the screen rather than once per row. Every other console module here "
    "filters row by row, and departing from that silently would read as an oversight."
)


#: The capability this screen is read behind, taken from the screen that shows it rather
#: than written here, so the screen registry stays the single statement of what a screen
#: needs. `models` is the screen's key; the console's page for it is addressed `/routing`,
#: and the two are allowed to differ because one is a permission and the other is a URL.
MATRIX_AUTHORITY: Final[Capability] = screen("models").read.requires


@dataclass(frozen=True)
class Rung:
    """One rung of the matrix with its health beside it.

    `unhealthy_because` is the router's own reason rather than a word chosen here, so an
    operator reading this screen and an engineer reading a log are looking at one vocabulary.

    The constraint on it runs one way only, and the asymmetry is the interesting part. A rung
    that is not open may not carry a reason: that is incoherent and the constructor refuses
    it. An open rung with no reason is allowed and means something real, which is that the
    breaker opened and the evidence which opened it has since aged out of the ring. Requiring
    a reason there would have turned an ordinary state into an exception on a screen somebody
    opens during an incident.
    """

    tier: Tier
    position: int
    model: str
    deployment_id: str
    provider: str
    role: RungRole
    state: BreakerState
    unhealthy_because: OpenReason | None
    #: How many recent live outcomes are on file, and how many of them failed. Counts rather
    #: than a ratio: the ring is capped, so a percentage over it is a percentage of the last
    #: few calls and reads as a percentage of traffic.
    live_seen: int
    live_failed: int
    last_probe_at: datetime | None

    def __post_init__(self) -> None:
        if self.live_failed > self.live_seen:
            msg = (
                f"rung {self.deployment_id!r} reports {self.live_failed} failures out of "
                f"{self.live_seen} outcomes"
            )
            raise ModelMatrixError(msg)
        if self.unhealthy_because is not None and self.state is not BreakerState.OPEN:
            msg = (
                f"rung {self.deployment_id!r} is {self.state.value} and carries the reason "
                f"{self.unhealthy_because.value!r}; a rung that is not open is one the router "
                "will try, and a reason beside it reads as a warning nobody acted on"
            )
            raise ModelMatrixError(msg)


def _health_of(deployment_id: str, health: Mapping[str, ProviderHealth]) -> ProviderHealth:
    """This deployment's record, or the healthy default the router itself assumes.

    `ProviderHealth.for_deployment` rather than a `None` a renderer turns into a dash. See
    `A_RUNG_NOTHING_HAS_FAILED_AGAINST_IS_HEALTHY_AND_NOT_UNKNOWN`.
    """
    found = health.get(deployment_id)
    return found if found is not None else ProviderHealth.for_deployment(deployment_id)


def matrix(
    chain: RoutingChain,
    health: Mapping[str, ProviderHealth],
    entitlement: EntitlementSet,
    *,
    now: datetime | None = None,
) -> tuple[Rung, ...]:
    """Every rung in the chain with its health, in tier and position order (M27.2.3).

    Empty for a reader who does not hold the routing screen's capability, and empty rather
    than a refusal, for the same reason every other console surface here answers that way.

    The order is the chain's own: tiers in their declared order and rungs by position inside
    each, because position is what the router follows and a screen sorted any other way makes
    a reader work out which rung is tried first.
    """
    if entitlement.scope_for(MATRIX_AUTHORITY, now) is None:
        return ()
    rows: list[Rung] = []
    for tier in Tier:
        for rung in chain.rungs_for(tier):
            state = _health_of(rung.deployment.id, health)
            rows.append(
                Rung(
                    tier=tier,
                    position=rung.position,
                    model=rung.model,
                    deployment_id=rung.deployment.id,
                    provider=rung.deployment.provider,
                    role=chain.role_of(rung),
                    state=state.state,
                    unhealthy_because=(
                        state.would_open(now) if state.state is BreakerState.OPEN else None
                    ),
                    live_seen=len(state.live),
                    live_failed=sum(1 for ok in state.live if not ok),
                    last_probe_at=state.last_probe_at,
                )
            )
    return tuple(rows)


def exhausted_tiers(rows: Sequence[Rung]) -> tuple[Tier, ...]:
    """Tiers whose every rung is open, in the order they appear (M27.2.3).

    A tier with no rungs at all is not exhausted and is not reported: nothing was tried and
    failed, there is nothing configured, and that is a different finding belonging to whoever
    edits the matrix. Reporting it as an outage would put a tier nobody has set up next to a
    tier that has just fallen over, and the two go to different people.

    That property holds by construction rather than by a check. A tier reaches the map below
    only by having a row in it, so `members` is never empty and a guard against it would be a
    guard no test could reach. The first version had one; a mutation removed it and changed no
    answer, which is how it was found. The property is still asserted, because it is a
    property of the answer rather than of the implementation that happens to produce it.

    Asked of the rows rather than of the chain and the health separately, so the answer is
    about what the reader is looking at. A reader holding nothing sees no rows and no
    exhausted tiers, which is the honest answer: they were not shown the estate.
    """
    seen: dict[Tier, list[Rung]] = {}
    for one in rows:
        seen.setdefault(one.tier, []).append(one)
    return tuple(
        tier
        for tier, members in seen.items()
        if all(one.state is BreakerState.OPEN for one in members)
    )


def unhealthy(rows: Sequence[Rung]) -> tuple[Rung, ...]:
    """The open rungs, for a banner. A convenience over `rows`, never a substitute for it.

    Returns the rungs rather than a count, because a count is what a screen prints when it
    has decided not to show the rows, and the rows are the whole point: an operator needs to
    know which provider, not how many.
    """
    return tuple(one for one in rows if one.state is BreakerState.OPEN)
