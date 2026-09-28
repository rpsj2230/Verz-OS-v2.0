"""How many browser sessions one website and one agent may hold at once, beside the global budget.

`brain.browsing.sessions` refuses to keep a second tally of browser sessions, and that refusal
still stands: the global number is `brain.ops.admission`'s and `may_open` asks it first. What
admission cannot express is a limit on an axis it does not carry. An `AdmissionRequest` has one
key, `PER_CONNECTOR` gives that key to source calls, and a browser session is budgeted once
globally, so "no more than one session on this portal" and "no more than one session for this
agent" have nowhere to go there. Those two are M19.6.2 and M19.6.3, and they are here.

**Every limit applies, and the global budget is asked first.** A session opens only if
admission admits it and every per-domain row and the per-agent row have room. Asked in that
order so a halt refuses as a halt, which `admission.decide` already decides before it looks at
a budget, rather than as whichever limit happened to be full. See `EVERY_LIMIT_APPLIES`.

**This module counts nothing.** `SessionCounts` is what somebody else counted, in the shape
`admission.CapacityState` is, and for its reason: a limiter that owned its counters could not
be tested for a decision taken against stale counts, which is the one that goes wrong.

**The domain is each declared origin of the target, and a session holds a slot on all of
them.** A registrable-domain parse needs the public suffix list, which is not a dependency,
and a suffix comparison is how `bank.example.evil.test` matches `bank.example`, which
`brain.browsing.targets.Target.allows_origin` refuses at length. A target declares its origins
already, normalised by `brain.channels.widget.normalise_origin`, and a run may touch any of
them, so a session occupies each. Two targets sharing a login host therefore share that host's
limit, which is the point of the limit: the vendor sees one host being driven twice.

**An axis with no row is refused, never unlimited.** The rule `admission.decide` applies to an
unbudgeted resource: admitting against nothing is the failure the limit exists to prevent. A
row with an empty subject is the default for every subject without its own, which is the shape
`admission.budget_for` gives a connector nobody measured.

Rejected: adding `BROWSER_SESSIONS` to `admission.PER_CONNECTOR`. It would key the one global
budget by domain, so the global count M19.6.1 depends on would become a per-domain default, and
there would still be nowhere for the agent. Rejected too: widening `AdmissionRequest` with an
agent and a domain, which changes the module every request passes through to serve one
subsystem, when the request path's own resources have neither axis.

Not built: the counter that fills `SessionCounts`. There is no runner to hold a session open,
so there is nothing yet whose start and end a counter would record.

Task ids: M19.6.2, M19.6.3
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.browsing.sessions import SessionError, may_start
from brain.browsing.targets import Target
from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.ops.admission import AdmissionDecision, Budget, CapacityState
from brain.ops.halt import NOTHING_HALTED, HaltState

#: Why a session needs room on every axis at once.
EVERY_LIMIT_APPLIES: Final = (
    "The global budget protects this machine, the per-domain limit protects somebody else's "
    "website from being driven twice at once, and the per-agent limit stops one agent taking "
    "every slot the machine has. They answer three different questions, so room on one says "
    "nothing about the other two, and a session that opened on the first that admitted it would "
    "be limited by whichever happened to be asked first."
)

#: Why a missing row refuses.
AN_AXIS_NOBODY_LIMITED_IS_NOT_UNLIMITED: Final = (
    "A domain or an agent with no row and no default is a limit nobody configured, and "
    "admitting against it is exactly the unbounded use the limit exists to prevent. Admission "
    "sheds an unbudgeted resource for the same reason, and the two refuse alike."
)

#: Sessions one origin may hold when nobody has set a row for it. One, because the global
#: seed budget is two, and a default of two would let both of the machine's sessions drive a
#: single vendor's portal at once, which is the lockout this limit is for.
DEFAULT_SESSIONS_PER_DOMAIN: Final = 1

#: Sessions one agent may hold when nobody has set a row for it. One, for the same arithmetic:
#: with two global sessions, an agent allowed two can hold the whole machine and every other
#: agent's browser work waits behind it.
DEFAULT_SESSIONS_PER_AGENT: Final = 1


class Axis(enum.StrEnum):
    """What a session limit is counted per, besides the global budget."""

    DOMAIN = "domain"
    AGENT = "agent"


#: A limit is addressed by its axis and its subject: an origin, or an agent id.
SessionKey = tuple[Axis, str]

_NO_COUNTS: Mapping[SessionKey, int] = MappingProxyType({})


@dataclass(frozen=True)
class SessionLimit:
    """One ceiling on one axis, as a configuration row. An empty subject is the axis default."""

    axis: Axis
    limit: int
    reason: str
    subject: str = ""

    def __post_init__(self) -> None:
        if self.limit < 1:
            # Zero is how somebody switches a website or an agent off by editing a number, and
            # it reads in the console as a configured limit rather than as a suspension; the
            # same refusal `admission.Budget` and `limits.Limit` make.
            msg = f"session limit {self.axis}/{self.subject or '*'} is {self.limit}; minimum is 1"
            raise SessionError(msg)
        if not self.reason.strip():
            msg = (
                f"session limit {self.axis}/{self.subject or '*'} says nothing about why, so "
                "the first person it refuses has no way to argue with it"
            )
            raise SessionError(msg)

    @property
    def key(self) -> SessionKey:
        return (self.axis, self.subject)


def seed_session_limits() -> tuple[SessionLimit, ...]:
    """The two default rows an installation starts from. Configuration, not a runtime truth."""
    return (
        SessionLimit(
            axis=Axis.DOMAIN,
            limit=DEFAULT_SESSIONS_PER_DOMAIN,
            reason=(
                "One session per origin, so the two global sessions never drive one vendor's "
                "portal at once."
            ),
        ),
        SessionLimit(
            axis=Axis.AGENT,
            limit=DEFAULT_SESSIONS_PER_AGENT,
            reason="One session per agent, so no agent holds every session the machine has.",
        ),
    )


def limit_for(limits: Sequence[SessionLimit], key: SessionKey) -> SessionLimit | None:
    """The row governing this key: its own row first, then the axis default, then nothing."""
    for row in limits:
        if row.key == key:
            return row
    for row in limits:
        if row.key == (key[0], ""):
            return row
    return None


@dataclass(frozen=True)
class SessionCounts:
    """Sessions in flight per key, as somebody else counted them."""

    held: Mapping[SessionKey, int] = _NO_COUNTS

    def held_for(self, key: SessionKey) -> int:
        return self.held.get(key, 0)


@dataclass(frozen=True)
class SessionDecision:
    """Whether a session may open, the global decision under it, and every key with no room.

    `over` is every key refused and not only the first, for the reason `limits.LimitDecision`
    carries all of its: a run refused on its agent and its domain at once is a different
    conversation from one refused on either.
    """

    admitted: bool
    admission: AdmissionDecision
    over: tuple[SessionKey, ...]
    reason: str


def keys_for(target: Target, agent_id: str) -> tuple[SessionKey, ...]:
    """Every key one session occupies: each declared origin, and the agent."""
    if not agent_id.strip():
        msg = (
            "a browser session names no agent, so a per-agent limit would count every agent as one"
        )
        raise SessionError(msg)
    domains = tuple((Axis.DOMAIN, origin) for origin in sorted(target.origins))
    return (*domains, (Axis.AGENT, agent_id))


def may_open(
    target: Target,
    *,
    agent_id: str,
    trace_id: str,
    budgets: Sequence[Budget],
    state: CapacityState,
    limits: Sequence[SessionLimit],
    counts: SessionCounts,
    now: datetime,
    traffic: TrafficClass = TrafficClass.AUTOMATION,
    lane: Lane = Lane.TASK,
    halts: HaltState = NOTHING_HALTED,
) -> SessionDecision:
    """Admit one browser session against the global budget, its domains and its agent.

    A halt is admission's answer and nothing below is asked: a stopped system is stopped rather
    than full. Otherwise every key is checked, whatever admission said, so a refusal lists all
    of what was full.
    """
    keys = keys_for(target, agent_id)
    admission = may_start(
        trace_id=trace_id,
        budgets=budgets,
        state=state,
        now=now,
        traffic=traffic,
        lane=lane,
        halts=halts,
    )
    if admission.halted:
        return SessionDecision(
            admitted=False, admission=admission, over=(), reason=admission.reason
        )
    over: list[SessionKey] = []
    for key in keys:
        row = limit_for(limits, key)
        if row is None or counts.held_for(key) + 1 > row.limit:
            over.append(key)
    if over:
        full = ", ".join(f"{axis.value} {subject}" for axis, subject in over)
        return SessionDecision(
            admitted=False,
            admission=admission,
            over=tuple(over),
            reason=f"no room for another browser session on {full}",
        )
    return SessionDecision(
        admitted=admission.admitted,
        admission=admission,
        over=(),
        reason=admission.reason,
    )
