"""Where the autonomy breaker's takeovers are read from: the approvals people took over (M8.3.5).

`brain.gate.abstain.AutonomyBreaker` was written, tested and claimed for M8.3.5, and nothing fed it:
no `TakeoverSignal` was ever built outside a test, so no agent's rung was ever lowered by a person
doing its work instead. This module is the feed. **A takeover is an approval decided with the
verdict `taken_over`**, which `gate.suspension` has recorded since `0083` and the Approvals route
offers since this change, and each one becomes a `TakeoverSignal` recorded into a breaker for that
agent and that target. There is no second breaker and no second rule about when a rung falls: the
threshold, the window and the one-step fall are `AutonomyBreaker`'s, unchanged.

**What is not a takeover, and why it is not fed here.** A question handed to a person by an
escalation step is the authored route working as designed, and an answer has no leash rung to lower.
An abstention a person later corrects is learning evidence (M16.2), and it points the other way: the
agent should have answered. Feeding either would lower the rung of an agent that did nothing wrong
on an action target. And a takeover never reaches the model circuit breaker, for
`brain.gate.abstain.TAKEOVER_IS_NOT_A_PROVIDER_FAULT`'s reason.

**The instants are read past `gate.suspension`'s policy, and nothing else is.** `0042` admits a
reader to a suspension only when it runs as them, when they decided it, or when it is pending and
they may approve it, so under any one person's reach the breaker would count the takeovers that
person happened to see, and the same agent would stand differently depending on who was using it.
`0172`'s `gate.takeover_instants` is the one read past that policy, and it returns instants and
nothing more. See `A_TAKEOVER_INSTANT_SAYS_WHEN_AND_NAMES_NOTHING`.

**The window is read at the instant the caller names, never the clock's.** `standing` takes `now`
and hands both ends of the window to the function, whose body reads no clock, so a leash decision
taken at one instant and asked again at the same instant gets the same rung, and a test can pin
both. See `A_STANDING_IS_READ_AT_THE_INSTANT_A_DECISION_IS_TAKEN`.

Rejected: keeping a counter per agent and target, incremented when a card is taken over. It is a
second copy of what `gate.suspension` already records, it would need its own expiry to forget a
takeover older than the window, and the two would disagree the first time a decision was rolled back
after the counter moved. The rows are the record; the breaker is built from them when it is asked.

Rejected: reading the rows under a session setting that switches the policy off for this one read.
It is a string any application code can write, which is `0040`'s second rejected design.

Task ids: M8.3.5
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from functools import reduce
from typing import Final, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.abstain import (
    TAKEOVER_DEMOTION_THRESHOLD,
    TAKEOVER_WINDOW,
    AutonomyBreaker,
    TakeoverSignal,
)

# ------------------------------------------------------------------ written-down reasons
#: Why the one read past the suspension policy discloses nothing a caller of the agent could not
#: already infer.
A_TAKEOVER_INSTANT_SAYS_WHEN_AND_NAMES_NOTHING: Final = (
    "gate.takeover_instants returns when this agent's action on this target was taken over and "
    "nothing else: no person, no record, no artefact, no reason. The policy on gate.suspension "
    "exists because a suspension carries another person's request and the data it would have "
    "touched, and none of that crosses. What crosses is the fact that people did this agent's work "
    "on this kind of action, which every caller of the agent already meets as the rung its next "
    "action is held to, so the instants add when it happened to a fact the lens already shows."
)

#: Why the window's end is a parameter and not the database's clock.
A_STANDING_IS_READ_AT_THE_INSTANT_A_DECISION_IS_TAKEN: Final = (
    "The leash decides at the instant its caller names, and the breaker's window is measured from "
    "that instant. A read that ended the window at the database's now() would count a takeover "
    "decided after the decision it is feeding, and a decision replayed at the same instant would "
    "stand differently on a second run."
)

# ------------------------------------------------------------------------ the figures
#: The function `0172` creates, which is the only read of takeovers there is.
FUNCTION: Final = "gate.takeover_instants"

#: The most takeovers read for one agent and target, newest first. A resource bound and not a
#: permission one: the breaker needs `TAKEOVER_DEMOTION_THRESHOLD` of them, and the agent's page
#: shows the week; a test holds this above the threshold so a bound can never keep a rung up.
MOST_TAKEOVERS_READ: Final = 50

#: Written out rather than built from `FUNCTION`, so no statement here is assembled at run time; a
#: test holds the two equal.
_READ: Final = text(
    "SELECT taken_over_at FROM gate.takeover_instants(:agent, :target, :after, :until, :most)"
)


# --------------------------------------------------------------------- the standing
def standing_from(agent_id: str, target: str, instants: Iterable[datetime]) -> AutonomyBreaker:
    """The breaker for one agent and target, fed one `TakeoverSignal` per instant, oldest first.

    Through `AutonomyBreaker.record` rather than by constructing the breaker with a tuple, so every
    instant passes the signal's own refusal of a naive timestamp and the breaker's own refusal of a
    signal for another agent, and the window is trimmed by the rule that trims it everywhere else.
    """
    return reduce(
        lambda breaker, at: breaker.record(TakeoverSignal(agent_id=agent_id, target=target, at=at)),
        sorted(instants),
        AutonomyBreaker(agent_id=agent_id, target=target),
    )


@runtime_checkable
class TakeoverStandings(Protocol):
    """Where an agent's standing on one target is read from, at an instant the caller names."""

    async def standing(self, agent_id: str, target: str, now: datetime) -> AutonomyBreaker:
        """The breaker for this agent and target, with the takeovers in the window ending `now`."""
        ...

    async def standings(
        self, agent_id: str, targets: Sequence[str], now: datetime
    ) -> dict[str, AutonomyBreaker]:
        """`standing` for each of these targets of one agent, keyed by target."""
        ...


class StoredTakeovers:
    """`TakeoverStandings` over `gate.suspension`, through `0172`'s function and nothing else."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        window: timedelta = TAKEOVER_WINDOW,
        most: int = MOST_TAKEOVERS_READ,
    ) -> None:
        if most < TAKEOVER_DEMOTION_THRESHOLD:
            msg = (
                f"reading at most {most} takeovers could keep a rung up that "
                f"{TAKEOVER_DEMOTION_THRESHOLD} takeovers lower"
            )
            raise ValueError(msg)
        self.sessions = sessions
        self.window = window
        self.most = most

    async def standing(self, agent_id: str, target: str, now: datetime) -> AutonomyBreaker:
        """See `A_STANDING_IS_READ_AT_THE_INSTANT_A_DECISION_IS_TAKEN`."""
        return (await self.standings(agent_id, (target,), now))[target]

    async def standings(
        self, agent_id: str, targets: Sequence[str], now: datetime
    ) -> dict[str, AutonomyBreaker]:
        """The breaker for each of these targets of one agent, read in one transaction."""
        if now.tzinfo is None:
            msg = "now must be timezone-aware; the window would be measured from nowhere"
            raise ValueError(msg)
        out: dict[str, AutonomyBreaker] = {}
        async with self.sessions() as session:
            for target in dict.fromkeys(targets):
                rows = await session.execute(
                    _READ.bindparams(
                        agent=agent_id,
                        target=target,
                        after=now - self.window,
                        until=now,
                        most=self.most,
                    )
                )
                out[target] = standing_from(agent_id, target, rows.scalars().all())
        return out
