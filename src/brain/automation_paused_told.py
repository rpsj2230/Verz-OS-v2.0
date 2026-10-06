"""An automation paused for failing is told to the agent's steward, once, in their own chat.

`brain.ops.automation_run_store.run_one` pauses an automation once its runs fail
`agent_automations.FAILURES_BEFORE_PAUSE` times in a row, and `automation_run.afterwards` composes
the `OwnerNotice` that says so. Until this module the notice was composed and dropped: `run_one`
wrote the pause and returned, and the only place it showed was the Automations tab, which a
steward has no reason to open on the day a weekly report stops arriving. **The steward is now
told, once, on the channel they last wrote on**, through `brain.tell_later`, the one sender for a
message a person is told later (M39.6.2.3).

**The worker marks and the web process tells**, for `brain.escalation_told`'s reason
(`THE_WORKER_MARKS_AND_THE_WEB_PROCESS_TELLS`): the worker cannot write to a chat, because the
channels' bot tokens are read under the application's vault role and the worker's policy grants
none, on purpose. The worker's mark is the row it already writes, an `agent.automation_schedule`
row with the reason `failed_repeatedly` in the runner's name, and the web process reads those rows
every `TELL_EVERY` and tells each steward. So nothing new is stored and no migration is needed:
`0067` lets the application read the schedule, the automation and the agent row, which is where
the steward is. Rejected: telling from the worker by granting it the tokens, which reverses a
written security choice for one message.

**Who is told is the agent's steward, as `run_one` addresses the notice.** `run_one` builds the
notice for `agent.audience.owner_id`, falling back to the automation's own owner when the agent
row is gone; the read here makes the same choice in SQL, so the person the notice was composed for
and the person told are the same person.

**What they are told is `OwnerNotice.render`, and nothing about why it failed.** The sentence
names the automation, the agent and the count, and never a run's failure text, which
`agent_automations.AutomationRun` keeps from the steward's page for the reason that failure text
can carry the data a run read.

**Once, whatever runs it.** Each message is keyed by the steward and the pause row's own id
through the operation ledger, so every web process can run the loop, a pass looking back over a
day tells nobody twice, and an automation paused, resumed and paused again is told twice because
those are two pauses.

**The switch is asked and has no off.** `AUTOMATION_PAUSED` is a row of `brain.ops.notices` with
no switch, by `A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH`; the loop asks `notice_is_on`
before each pass as every sender does, so the day somebody gives it a switch the sender already
honours it.

Task ids: M39.6.2.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import structlog
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from brain.console.agent_automations import FAILURES_BEFORE_PAUSE, OwnerNotice
from brain.ops.automation_run import RUNNER_ACTOR, PausedBecause
from brain.ops.automation_run_store import RUN_EVERY
from brain.ops.notices import NoticeKind, notice_is_on
from brain.tables.channel import DeliveryOutcome
from brain.tell_later import tell

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the pause read names what it does and nothing more.
A_PAUSE_IS_READ_FOR_ITS_STEWARD_AND_NAMES_NOTHING_ELSE: Final = (
    "The read returns, for each automation the runner paused for failing, the pause row's id, the "
    "automation, its agent, the steward and when, and nothing of what the runs did or why they "
    "failed. The process reads it to tell each steward one sentence about their own agent's "
    "automation, which their Automations tab already shows them."
)

# ------------------------------------------------------------------------ the figures
#: How often the web process asks which automations were paused: as often as the worker runs them.
TELL_EVERY: Final = RUN_EVERY

#: How far back each pass looks. A day, so a process down for hours still tells on its return;
#: the operation ledger makes a second pass over the same pause send nothing.
LOOKBACK: Final = timedelta(days=1)

#: The most pauses told in one pass, oldest first. A resource bound: the next pass tells the rest.
MOST_TOLD_PER_PASS: Final = 200

#: The key each message is sent once under, per pause.
INTENT_PREFIX: Final = "automation_paused"

#: The runner's own pauses for failing, with the steward `run_one` addresses the notice to.
#: Written out so no statement here is assembled at run time.
_READ: Final = text(
    "SELECT s.id, s.automation_id, s.agent_id, COALESCE(a.owner_id, m.runs_as_id), s.at"
    " FROM agent.automation_schedule AS s"
    " JOIN agent.automation AS m ON m.automation_id = s.automation_id"
    " LEFT JOIN agent.agent AS a ON a.id = s.agent_id"
    " WHERE s.reason = :reason AND s.changed_by = :runner"
    " AND s.at > :after AND s.at <= :until"
    " ORDER BY s.at, s.id LIMIT :most"
)


@dataclass(frozen=True)
class Paused:
    """One pause for failing: which row, which automation and agent, whose steward, and when."""

    pause_id: str
    automation_id: str
    agent_id: str
    steward_id: str
    paused_at: datetime


def paused_text(one: Paused) -> str:
    """What the steward reads: `OwnerNotice.render`, for the count that paused it."""
    return OwnerNotice(
        owner_id=one.steward_id,
        automation_id=one.automation_id,
        agent_id=one.agent_id,
        consecutive_failures=FAILURES_BEFORE_PAUSE,
        at=one.paused_at,
    ).render()


def intent_ref_for(one: Paused) -> str:
    """The key the steward is told under, once per pause."""
    return f"{INTENT_PREFIX}.{one.pause_id}"


async def paused_between(
    sessions: async_sessionmaker[AsyncSession],
    *,
    after: datetime,
    until: datetime,
    most: int = MOST_TOLD_PER_PASS,
) -> tuple[Paused, ...]:
    """Every pause for failing after `after` and by `until`, oldest first, bounded."""
    async with sessions() as session, session.begin():
        rows = (
            await session.execute(
                _READ.bindparams(
                    reason=PausedBecause.FAILED_REPEATEDLY.value,
                    runner=RUNNER_ACTOR,
                    after=after,
                    until=until,
                    most=most,
                )
            )
        ).all()
    return tuple(
        Paused(
            pause_id=str(one[0]),
            automation_id=str(one[1]),
            agent_id=str(one[2]),
            steward_id=str(one[3]),
            paused_at=one[4],
        )
        for one in rows
    )


async def tell_paused_stewards(
    request: Request,
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    paused: Sequence[Paused] | None = None,
) -> int:
    """Tell each steward whose automation was paused in the last `LOOKBACK`, once. How many now.

    `paused`, when given, is the list to tell instead of reading it, which is how an install check
    tells only its own.
    """
    async with sessions() as session:
        if not await notice_is_on(session, NoticeKind.AUTOMATION_PAUSED):
            return 0
    due = (
        paused
        if paused is not None
        else await paused_between(sessions, after=now - LOOKBACK, until=now)
    )
    sent = 0
    for one in due:
        delivered = await tell(
            request, one.steward_id, paused_text(one), intent_ref=intent_ref_for(one), now=now
        )
        # A second pass over the same pause is handed the first's record and issues nothing.
        sent += (
            delivered is not None and delivered.issued and delivered.outcome is DeliveryOutcome.SENT
        )
    return sent


async def keep_telling_paused_stewards(app: FastAPI) -> None:
    """Tell stewards of paused automations every `TELL_EVERY` for as long as the application runs.

    A failure is logged by its kind and the next pass tries again, as the expired-askers loop does.
    """
    # Imported here: the mailbox module imports the events route, which imports this package.
    from brain.mailbox_read import request_for

    while True:
        await asyncio.sleep(TELL_EVERY.total_seconds())
        sessions = getattr(app.state, "db_sessions", None)
        if sessions is None:
            continue
        try:
            sent = await tell_paused_stewards(request_for(app), sessions, now=datetime.now(UTC))
        except Exception as exc:
            log.warning("paused automations not told", kind=type(exc).__name__)
            continue
        if sent:
            log.info("paused automations told", sent=sent)
