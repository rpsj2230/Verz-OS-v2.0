"""The thirty-day review of a supervised agent's pin, asked on a schedule as well as by a person.

`brain.agents.supervision.review` decides the question and `brain.agent_leash_routes.review_agent`
asks it when a person presses Review. Until this module nothing asked it otherwise, so a pin whose
thirty days had passed sat there, held, until somebody remembered. That is the safe direction and
not the item: M13.5.18 says the pin **is reviewed at thirty days against measured confidence**,
and a review nobody presses is not one that happens at thirty days. This is the second caller, and
a worker control (`supervision_review`) so it runs whether or not anybody is looking.

**The decision is one function and both callers use it.** `answer_review` is what the route used to
do inline: refuse an agent that is not supervised, ask `review` over the pin's own window, and turn
its three outcomes into the two rows a review can store. The route and this run both call it, so a
change to what a review means is a change in one place, and the scheduled run cannot decide
anything the person-pressed one would not. `reviewed_in_window` moved here with it, and the route
imports it from here.

**Nothing is released because a date passed, and this run cannot make that happen.** The run
decides nothing: `answer_review` asks `review`, whose only way to `ELIGIBLE` is a measured
confidence at or over the bar, and below it the pin is `EXTENDED` for another period from now. An
agent nobody reviewed is unmeasured and extends. See `brain.agents.supervision` for the argument,
and `A_SCHEDULED_REVIEW_IS_THE_SAME_QUESTION_AS_A_PRESSED_ONE`. What an eligible pin then waits for
is a person raising a rung, through the two-person gate, exactly as before.

**It ships switched off, and while off it says what it would have done.** CLAUDE.md puts a new
behaviour behind a flag and ships it off for everyone (`brain.ops.features.SUPERVISION_REVIEW`,
needs-rupash 174). Off, the run reads every due pin, decides each one, writes nothing and reports
how many it would have extended and how many it would have marked eligible, so the owner switches
it on knowing what the first run does. **It also writes nothing in report-only mode**, because the
schedule's report-only flag means "decide and do not act" everywhere else and a runner that wrote
anyway would ignore the mode it was given.

**The writer is a named system reviewer, and the row says so.** `agent.supervision_pin` admits an
insert only where `decided_by` is the session's own principal (`0195`), so the run sets
`app.principal_id` to `SYSTEM_REVIEWER` through the same `StoredLeash.write_pin` the route uses,
and a review the worker made is the one row that reads `decided_by = supervision-review`. It is
not a person: the history shows it as the system, and a rung rise still names two people.
**There is no ledger entry for a review**, and that is true of the route as well: `0195` puts a
trigger on `agent.leash_change` and none on `agent.supervision_pin`, so a pin row, its
`decided_by` and its trace are its own record. Rejected: adding the trigger here. It would change
what a person-pressed review writes and widen a migration that is only meant to admit a control
name; it is a decision for the owner and is said in item 174.

**What a run says names no agent and no person.** Its report is read by whoever reads the control
runs, so it says how many pins were due and what each outcome came to, in counts, and never which
agent. An agent whose evidence contradicts itself (`SupervisionError`) is counted as held and left
exactly as it was: the route answers that case with "not due yet", and a worker that guessed would
be deciding which of two reviewers was right.

**Two writers, one agent, one instant.** A person pressing Review in the same second the worker
runs can write two rows. Both are `EXTENDED` with due dates seconds apart, or one is `ELIGIBLE`
and the later `EXTENDED`, which is the newest row and so holds the agent: every outcome is on the
safe side of "released". A lock across the two paths was rejected, because it would be a second
mechanism guarding a window of one second on a table that only ever has rows added to it.

**A cap on one run.** `MAX_PINS_PER_RUN` bounds the read, oldest due first, and the rest wait for
the next day's run, which is when a pin was already going to be reviewed.

Task ids: M13.5.18, M39.8.2
"""

from __future__ import annotations

import asyncio
import enum
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.supervision import (
    ShadowOutcome,
    ShadowPin,
    ShadowReview,
    SupervisionError,
    review,
)
from brain.gate.leash import ActionRecord
from brain.ops.leash_store import LeashState, StoredLeash, simulated_only
from brain.tables.leash import PinOutcome, SupervisionPinRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why the scheduled run has no decision of its own.
A_SCHEDULED_REVIEW_IS_THE_SAME_QUESTION_AS_A_PRESSED_ONE: Final = (
    "The route a person presses and the run the worker starts call one function, so the "
    "worker cannot find an agent eligible that Review would have extended. The only way to "
    "ELIGIBLE is a measured confidence at or over the bar; a date that passes asks the "
    "question and a short or missing answer extends the pin."
)

#: Why the system's review is written under a name of its own.
A_SYSTEM_REVIEW_IS_NOT_A_PERSONS_REVIEW: Final = (
    "A review the worker asked is written as the system reviewer and never as an "
    "administrator, so the history cannot be read as a person having looked at the agent. "
    "Raising a rung is still a person's act, with a second person where it is irreversible."
)

#: Why a run with the switch off writes nothing and still reports.
A_RUN_WITH_THE_SWITCH_OFF_WRITES_NOTHING_AND_SAYS_WHAT_IT_WOULD_HAVE_DONE: Final = (
    "A behaviour that is new on every install is switched off until its owner turns it on. "
    "Off, the run decides each due pin and records only a count of what it would have "
    "extended or marked eligible, so switching it on is a decision made on what the first "
    "run will do."
)

# --------------------------------------------------------------------------- the figures
#: Who a review the worker made is attributed to. Shaped for the principal id grammar
#: `^[A-Za-z0-9_.@-]{1,128}$`, which `0195`'s insert policy compares with the session's own
#: principal.
SYSTEM_REVIEWER: Final = "supervision-review"

#: The reach a review the worker made is recorded at. The ledger's own value for a write with
#: no reach in force (`0003`'s default), because nobody's entitlement was used.
NO_REACH: Final = "0" * 32

#: How often the control is owed, once a day, which is also the finest a thirty-day review needs.
REVIEW_EVERY: Final = timedelta(days=1)

#: The most pins one run reads, oldest due first. A resource bound on the read.
MAX_PINS_PER_RUN: Final = 500

#: The prefix of the trace id one run writes its rows under.
TRACE_PREFIX: Final = "supervision-review"


class SupervisionReviewError(Exception):
    """One or more pins could not be reviewed for a reason that is not their evidence."""


# ------------------------------------------------------------------ the shared decision
def reviewed_in_window(state: LeashState) -> tuple[list[ShadowReview], list[ActionRecord]]:
    """The simulated actions a review counts and the verdicts on them, as the domain takes them.

    A verdict on an action that was not simulated in the pin's window is left out rather than
    handed to `measure`, which refuses one: an action approved at Assisted is evidence for a
    raise, and not about a shadow period.
    """
    if state.pin is None:
        return [], []
    simulated = [one for one in simulated_only(state.actions) if one.at >= state.pin.pin.pinned_at]
    when = {one.action_digest: one.at for one in simulated}
    verdicts = [
        one
        for one in state.verdicts
        if one.action_digest in when and one.at >= when[one.action_digest]
    ]
    return verdicts, simulated


class Refusal(enum.StrEnum):
    """Why a review was not answered. Three words, because the callers tell two of them apart."""

    #: No pin, or one already found eligible: there is nothing to review.
    NOT_SUPERVISED = "not_supervised"
    #: The pin's thirty days are not up. Nothing is decided, however good the figure looks.
    NOT_DUE = "not_due"
    #: The evidence contradicts itself, so no figure can be made of it. Nothing is decided.
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"


@dataclass(frozen=True)
class Answer:
    """What a review found, ready to be stored: the outcome, the pin after it and the counts."""

    outcome: PinOutcome
    pin: ShadowPin
    counts: tuple[int, int, int]


def answer_review(state: LeashState, *, now: datetime) -> Answer | Refusal:
    """Ask the thirty-day question of one agent's stored state and say what to store.

    The route's body and the worker's body, once. `ELIGIBLE` is returned only where `review`
    found a measured confidence at or over the bar; `EXTENDED` for everything else that is due.
    A pin not yet due is `NOT_DUE`. Evidence that contradicts itself is `CONTRADICTORY_EVIDENCE`
    and is logged, because a refusal nobody sees is a pin held for ever with no reason. The route
    answers both as "not due yet", which is what it always did; the run counts the second.
    """
    if state.pin is None or state.pin.outcome is PinOutcome.ELIGIBLE:
        return Refusal.NOT_SUPERVISED
    verdicts, simulated = reviewed_in_window(state)
    try:
        decision = review(state.pin.pin, simulated=simulated, reviews=verdicts, now=now)
    except SupervisionError:
        log.warning("supervision review refused its evidence", agent=state.pin.pin.agent_id)
        return Refusal.CONTRADICTORY_EVIDENCE
    if decision.outcome is ShadowOutcome.NOT_YET_DUE:
        return Refusal.NOT_DUE
    found = decision.confidence
    return Answer(
        outcome=(
            PinOutcome.EXTENDED
            if decision.outcome is ShadowOutcome.EXTENDED
            else PinOutcome.ELIGIBLE
        ),
        pin=decision.pin,
        counts=(found.understood, found.reviewed, found.simulated),
    )


# ------------------------------------------------------------------------- the pass
class ReviewStore(Protocol):
    """What one pass reads and writes. The real one is `StoredReviews`; a test passes a fake."""

    async def switched_on(self) -> bool: ...

    async def due_agents(self, now: datetime, limit: int) -> Sequence[str]: ...

    async def state(self, agent_id: str) -> LeashState: ...

    async def write_pin(
        self,
        pin: ShadowPin,
        outcome: PinOutcome,
        *,
        by: str,
        counts: tuple[int, int, int] | None,
        at: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> None: ...


@dataclass(frozen=True)
class ReviewRun:
    """What one run came to, in counts that name no agent."""

    #: Pins whose review was due and which were answered.
    due: int
    extended: int
    eligible: int
    #: Left as they were because their evidence contradicts itself.
    held: int
    #: Could not be read or written; the run raises after finishing the rest.
    failed: int
    #: Whether anything was written. False with the switch off and in report-only mode.
    wrote: bool

    def summary(self) -> str:
        if self.due == 0 and self.held == 0 and self.failed == 0:
            return "no pin is due for review"
        found = (
            f"{self.due} due, {self.extended} extended, {self.eligible} eligible for a person "
            f"to raise, {self.held} held on contradictory evidence, {self.failed} failed"
        )
        if self.wrote:
            return f"reviewed pins: {found}"
        return (
            f"nothing was written, so this is what a run would have done: {found}. "
            f"{A_RUN_WITH_THE_SWITCH_OFF_WRITES_NOTHING_AND_SAYS_WHAT_IT_WOULD_HAVE_DONE}"
        )


async def run_supervision_review(
    store: ReviewStore, *, now: datetime, report_only: bool = False
) -> ReviewRun:
    """Review every pin whose thirty days have passed, or say what that would do.

    One pin's failure is counted and does not stop the rest, and the run raises at the end if
    any failed, so the control's run is recorded as failed rather than as a success that
    reviewed fewer pins than it found.
    """
    write = (not report_only) and await store.switched_on()
    trace_id = f"{TRACE_PREFIX}.{uuid.uuid4().hex[:16]}"
    due = extended = eligible = held = failed = 0
    for agent_id in await store.due_agents(now, MAX_PINS_PER_RUN):
        try:
            answer = answer_review(await store.state(agent_id), now=now)
            if isinstance(answer, Refusal):
                if answer is Refusal.CONTRADICTORY_EVIDENCE:
                    held += 1
                continue
            if write:
                await store.write_pin(
                    answer.pin,
                    answer.outcome,
                    by=SYSTEM_REVIEWER,
                    counts=answer.counts,
                    at=now,
                    ent_hash=NO_REACH,
                    trace_id=trace_id,
                )
        except Exception as failure:
            # Broad on purpose: one pin that cannot be read or written must not stop the others.
            log.warning("a supervision review could not finish", error=type(failure).__name__)
            failed += 1
            continue
        due += 1
        if answer.outcome is PinOutcome.EXTENDED:
            extended += 1
        else:
            eligible += 1
    done = ReviewRun(
        due=due, extended=extended, eligible=eligible, held=held, failed=failed, wrote=write
    )
    if failed:
        msg = f"{failed} pins could not be reviewed; the others were. {done.summary()}"
        raise SupervisionReviewError(msg)
    return done


# ---------------------------------------------------------------------------- the stores
async def review_switch_is_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether `supervision_review` is switched on now. Off when nobody has said otherwise."""
    from brain.ops.features import SUPERVISION_REVIEW, is_on

    async with sessions() as session:
        return await is_on(session, SUPERVISION_REVIEW)


class StoredReviews:
    """`ReviewStore` over the application's sessions and `StoredLeash`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._leash = StoredLeash(sessions)

    async def switched_on(self) -> bool:
        return await review_switch_is_on(self._sessions)

    async def due_agents(self, now: datetime, limit: int) -> Sequence[str]:
        """Agents whose newest pin row is not eligible and whose review date has come."""
        newest = (
            select(
                SupervisionPinRow.agent_id,
                SupervisionPinRow.outcome,
                SupervisionPinRow.review_due_at,
            )
            .distinct(SupervisionPinRow.agent_id)
            .order_by(SupervisionPinRow.agent_id, SupervisionPinRow.decided_at.desc())
            .subquery()
        )
        async with self._sessions() as session:
            rows = await session.execute(
                select(newest.c.agent_id)
                .where(
                    newest.c.outcome != PinOutcome.ELIGIBLE.value,
                    newest.c.review_due_at <= now,
                )
                .order_by(newest.c.review_due_at)
                .limit(limit)
            )
            return tuple(rows.scalars().all())

    async def state(self, agent_id: str) -> LeashState:
        return await self._leash.state(agent_id)

    async def write_pin(
        self,
        pin: ShadowPin,
        outcome: PinOutcome,
        *,
        by: str,
        counts: tuple[int, int, int] | None,
        at: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> None:
        await self._leash.write_pin(
            pin, outcome, by=by, counts=counts, at=at, ent_hash=ent_hash, trace_id=trace_id
        )


def run_supervision_review_now(
    database_url: str,
    *,
    now: datetime,
    report_only: bool,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> str:
    """`run_supervision_review` from a thread with no event loop of its own, as the worker.

    The shape `brain.ops.denial_digest_run.run_denial_digest_now` takes: the application's own
    engine, so row-level security applies, disposed afterwards.
    """
    from brain.session import make_app_engine, make_session_factory

    async def once() -> str:
        engine = make_app_engine(database_url)
        try:
            ran = await run_supervision_review(
                StoredReviews(make_session_factory(engine)), now=now, report_only=report_only
            )
            return ran.summary()
        finally:
            await engine.dispose()

    return asyncio.run(once(), loop_factory=loop_factory)
