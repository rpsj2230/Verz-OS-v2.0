"""The one place a request the gate accepted is finished with, and what it owes when it is.

A finished request owes more than its answer. Adoption needs to know that somebody asked
(M37.3.2.4), the metadata ledger needs to know when the request ended so that a lane latency
objective has a duration to take a percentile of (M30.5.2), and a spend row names the trace it
paid for (`docs/needs-rupash.md` item 59, M21.3.4). Each of those is written by a different module
with a different table, and the obvious way to get them is a hook per concern, each added where
its author happened to be looking: a line in a route for one, a line in a channel adapter for
the next. **That is the shape this module exists to refuse.** A record written from a route is
missing for every question that arrives some other way, and it is missing silently, because a
table that is short by one channel looks exactly like a channel nobody used.

**So there is one completion point and it is inside the lane, not beside it.**
`brain.gate.answer.answer_lane` is the single function that turns an admitted question into an
outcome, and it takes the recorders as a required argument and calls `finish` on every way out
of it: an answer, an abstention for any reason, a cache hit, and a fault. A channel that wants
to answer a question has to call the lane, and the lane will not run without being told what
to record. A channel cannot forget the record because it never writes one.

**What a recorder is handed is what the gate already decided, and nothing the request
supplied.** `Origin` carries the resolved `Principal`, which the directory produced from a
verified token, the channel `brain.api_routes.channel_for` read off the token's claims, and the
trace id the middleware vouched for or minted. There is no field for a department, a principal
kind or a traffic class, because each of those is derived from the principal or the channel,
and a field for it would be a place for a caller to put a different one. See
`A_RECORD_OF_WHO_ASKED_IS_BUILT_FROM_WHO_THE_GATE_SAID_WAS_ASKING`.

**The origin has to belong to the reach the question was answered at.** A lane handed one
person's entitlements and another person's origin would answer as the first and record the
second, and every figure built from the record would describe a question that person never
asked. `answer_lane` refuses the pair before it reads anything. See
`A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO`.

**A recorder decides what its own failure means, and the order is the order given.** A recorder
that raises fails the request, and the next recorder does not run. That is right for a record
the request must not complete without, and wrong for a measurement, so a recorder whose record
is a measurement catches its own failure and says so in the log:
`brain.ops.question_store.QuestionRecorder` does. Deciding it here, once, for every recorder,
would make one of those two kinds wrong.

Rejected: recording at the route. It is where the principal, the channel and the trace id are
all in scope, and it is one caller of the lane among several: the golden corpus and the lane's
own tests already call it directly, and each chat adapter will. A route-level record is the
per-adapter hook with one adapter written.

Rejected: recording only on the paths that produce frames. A fault is still a question somebody
asked, and a record written on success only would make the count depend on whether a source was
reachable, which a department head would read as their people asking less on the day the
connector was down.

**The metadata ledger's row is the second thing a finished request owes, and it needed three
facts the first did not (M30.5.2).** `brain.ops.telemetry_store.TelemetryRecorder` attaches to
`finish` beside the question recorder, and `Finished` now carries what it reads: the instant the
lane finished, the hash of the reach it answered at, and the lane's declaration of the budget it
ran under. The completion instant comes from a clock the caller hands the lane and the lane reads
once, in its `finally`, before any recorder runs, so every recorder is handed the same instant
and none of them is timed by the recorders before it. A recorder reading its own clock was the
other shape and was rejected for exactly that: the ledger's duration would include the question
recorder's database write.

**A completion instant before the judged one is not refused here.** `Finished` is built inside
the lane's `finally`, so a refusal here would turn an answered question into a fault over a clock
stepping backwards. The telemetry record refuses a negative duration and its recorder logs it,
which is the rule a measurement follows. A naive completion instant is refused here, as a naive
judged instant is: it is a wiring fault identical for every request, and it fails the first test
that runs the lane rather than a report months later.

**The tool count is the fourth fact, and it is counted here rather than in a channel
(M21.3.4).** `docs/needs-rupash.md` item 59 was answered Option B: a spend row carries the trace
id of its request and the question's shape is read from the trace ledger, which had declared
`tool_count` and never set it. The lane is the only place that knows how many readers it called,
because it is the only place that calls them, so `answer_lane` counts each call as it starts it
and hands the count to every recorder on `Finished`. A channel counting calls would be counting a
lane it does not run. See `A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS` for why the count is taken at
the start of a call and not from what it returned.

**A tool call an automation makes finishes here too, and it is not an answer.**
`brain.ops.automation_piece.call_piece` is the second function that turns an admitted request
into an outcome, for a step sent to `brain.automation_routes`, and it takes the recorders as a
required argument and calls `finish` in its `finally` for the reason `answer_lane` does. Until
2026-09-15 it could not: `outcome` was the answer lane's type or None, and
`brain.ops.telemetry.status_of_finished` records None as a fault, so a call that succeeded would
have been written as FAILED or would have needed an `Answered` with invented frames.
`ToolCallOutcome` is what a call ends as, and it holds one fact: whether it was refused. See
`A_REFUSED_TOOL_CALL_IS_RECORDED_WITHOUT_WHAT_WAS_REFUSED`.

Rejected: a field naming the tool, the entity or the kind of refusal. Each is what an operator
reaches for while debugging a flow, and each turns the metadata ledger, which a usage report
reads, into a per-principal list of what was withheld and which tools exist to withhold.

Task ids: M37.3.2.4, M30.5.2, M21.3.4
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import KW_ONLY, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final, Protocol

from brain.audit.ledger import TRACE_ID
from brain.core.lane import Lane
from brain.core.principal import Principal
from brain.gate.context import Channel

if TYPE_CHECKING:
    # Typing only: `brain.gate.answer` imports this module to call `finish`, so importing the
    # outcome type at run time would be a cycle, and the annotation is all that needs it.
    from brain.gate.answer import Answered

#: Why a finished request carries a principal rather than the facts about one.
A_RECORD_OF_WHO_ASKED_IS_BUILT_FROM_WHO_THE_GATE_SAID_WAS_ASKING: Final = (
    "A department, a principal kind and a traffic class are all things a request could "
    "claim, in a header, a body field or a token claim, and every one of them is already "
    "decided by the gate: the directory resolved the principal from a verified token, and "
    "the channel was read from the token rather than from anything the caller set. So a "
    "finished request carries that principal and that channel, and whatever a recorder "
    "needs is derived from them. A field for the department would be a place to put a "
    "different one."
)

#: Why the origin and the reach have to name the same person.
A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO: Final = (
    "The answer is computed at one person's entitlements and the record says who asked. If "
    "the two could name different people, a question would be answered as one person and "
    "counted as another, and no figure built from the records could be traced back to what "
    "anybody actually did. The pair is refused before anything is read."
)

#: What a tool count on a finished request counts, and why it cannot tell a refusal from an
#: absence.
A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS: Final = (
    "A tool call is counted when the lane starts it, before anything comes back, so the count "
    "is a fact about what the lane did and never about what the source held. A record that "
    "exists and is withheld, a record that does not exist, and a name two records answer to "
    "are one read each and one call each. A count taken from what came back would be a count "
    "of rows, which separates those three, and a count of rows per request in a usage report "
    "is a count of things that exist. A question no rule matches makes no call, so its count "
    "is zero: that says whether the installation has a rule for the question's form, and the "
    "readers a rule is matched against are the registry's, the same for every asker, so it "
    "says nothing about the asker's reach or about any record."
)

#: Why a refused tool call is recorded as refused and as nothing more.
A_REFUSED_TOOL_CALL_IS_RECORDED_WITHOUT_WHAT_WAS_REFUSED: Final = (
    "An automation's tool call is refused for a tool its owner does not hold, a tool outside "
    "its declared set, a tool that does not exist, arguments the tool will not take and an "
    "entity with no field policy, and the caller is told one sentence for all of them. The "
    "record keeps that: a refused call is refused and nothing else, with no tool, no entity "
    "and no reason, so the metadata ledger cannot count what one principal's automations were "
    "refused or which tools exist to be refused. Success and refusal are told apart, because an "
    "automation that has stopped working is the operator's to notice."
)

_TRACE_ID_RE: Final = re.compile(TRACE_ID)


class FinishError(ValueError):
    """Raised when a finished request is described in a way no record should be built from."""


@dataclass(frozen=True)
class ToolCallOutcome:
    """How one automation tool call ended, when it ended without a fault.

    **One field, and read the absences.** There is no tool name, no entity, no automation id
    and no reason, and each is a field somebody would reasonably add. See
    `A_REFUSED_TOOL_CALL_IS_RECORDED_WITHOUT_WHAT_WAS_REFUSED`. A fault is not one of these: it
    is `Finished.outcome` being None, as it is for a question.
    """

    refused: bool


@dataclass(frozen=True)
class Origin:
    """Who asked, from where, under which trace, as the gate established each of them.

    The trace id is held to `brain.audit.ledger.TRACE_ID`, imported rather than restated, so a
    record written under it can be joined to the audit entries and the ledger row for the same
    request. `fullmatch` for the reason `brain.ops.telemetry.Ingress` gives: the pattern ends
    in `$`, which `match` would let a trailing newline through.
    """

    trace_id: str
    principal: Principal
    channel: Channel

    def __post_init__(self) -> None:
        if not _TRACE_ID_RE.fullmatch(self.trace_id):
            msg = (
                f"trace id {self.trace_id!r} is not one the audit ledger accepts, so nothing "
                "recorded under it could be joined to the rest of the request"
            )
            raise FinishError(msg)


@dataclass(frozen=True)
class Finished:
    """One admitted request the lane has finished with, however it finished.

    `outcome` is None when the lane raised, which is how a recorder tells a fault from an
    answer without being handed the exception. A recorder that has no business knowing how a
    request ended, such as the question count, simply does not read it.

    An `Answered` is a question the answer lane finished and a `ToolCallOutcome` is a tool call
    an automation made; see the module docstring.
    """

    origin: Origin
    #: The instant the request was judged at, which the lane is given and never reads itself.
    at: datetime
    outcome: Answered | ToolCallOutcome | None
    _: KW_ONLY
    #: The instant the lane finished, read once from the clock the caller handed it (M30.5.2).
    completed_at: datetime
    #: The hash of the reach the question was answered at, which the ledger quotes beside the
    #: trace id. A hash identifies a reach and discloses nothing that is in it.
    entitlement_hash: str
    #: The budget the lane that finished runs under, as that lane declares it.
    lane: Lane
    #: How many tool calls the lane started, counted by the lane as it made them (M21.3.4). A
    #: call that raised is still a call started. See `A_TOOL_CALL_IS_COUNTED_WHEN_IT_STARTS`.
    tool_calls: int

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            msg = "a naive instant files a finished request in the wrong window"
            raise FinishError(msg)
        if self.completed_at.tzinfo is None:
            msg = "a naive completion instant cannot be subtracted from the judged one"
            raise FinishError(msg)


class RequestRecorder(Protocol):
    """Something a finished request owes a record to."""

    async def finished(self, request: Finished) -> None: ...


def attributable(origin: Origin, principal_id: str) -> None:
    """Refuse an origin that names somebody other than the reach it will be answered at.

    See `A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO`.
    """
    if origin.principal.id != principal_id:
        msg = (
            f"a question answered at {principal_id}'s reach cannot be recorded as asked by "
            f"{origin.principal.id}. {A_QUESTION_IS_ATTRIBUTED_TO_WHOEVER_ITS_REACH_BELONGS_TO}"
        )
        raise FinishError(msg)


async def finish(recorders: Sequence[RequestRecorder], request: Finished) -> None:
    """Hand one finished request to every recorder, once each, in the order given."""
    for recorder in recorders:
        await recorder.finished(request)
