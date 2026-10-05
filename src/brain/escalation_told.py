"""An asker whose handed-on question nobody picked up is told so, in the chat they last used.

A skill's escalation hands a question to a person with a deadline, and the worker's
`escalation_expiry` marks it expired once the deadline passes. Until this module nothing else
happened: the asker had been told their question went to a queue, and the only place its expiry
showed was the list of their handoffs in the web application. **The asker is now told, once, on the
channel they last wrote on**, through `brain.tell_later`, which is the one sender for a message a
person is told later.

**The web process tells them, and the worker only marks.** The worker cannot write to a chat: the
channels' bot tokens are read under the application's vault role, and
`ops/openbao/policies/worker.hcl` grants the worker none, deliberately, because a process nobody
watches should not hold what it would need to message anyone as the bot. So a loop in the web
process asks every `TELL_EVERY` which handoffs expired, and tells each asker. See
`THE_WORKER_MARKS_AND_THE_WEB_PROCESS_TELLS`.

**Which handoffs expired is read past the policy, and nothing else is.** `0168`'s policy admits a
handoff to its asker and its named people, so no one reader could list them all.
`gate.expired_handoffs` (`0177`) returns each one's id, asker, queue and expiry in a window the
caller names, and never the question, what was tried or whom it went to. See
`AN_EXPIRED_HANDOFF_IS_READ_FOR_ITS_ASKER_AND_NAMES_NOTHING_ELSE`.

**Once, whatever runs it.** Each message is keyed by the asker and `escalation_expired.<id>` through
the operation ledger, so every web process can run the loop, and a pass that looks back over a day
tells nobody twice. A pass looks back `LOOKBACK`, not only since its own last run, so a process
that was down when a handoff expired still tells its asker when it comes back.

**A switch an administrator can turn off.** `QUESTION_NOT_PICKED_UP` is a row of
`brain.ops.notices` and the sender asks `notice_is_on` before each pass, as every sender does.

Rejected: telling the asker from the worker, by granting it the channels' tokens. It reverses a
written security choice for one message. Rejected too: telling them the next time they write, which
is not in the chat they asked from when it happens.

Task ids: M8.3.4
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

from brain.gate.abstain import EXPIRY_EVERY
from brain.ops.notices import NoticeKind, notice_is_on
from brain.tables.channel import DeliveryOutcome
from brain.tell_later import tell

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the one read past the escalation policy discloses nothing an asker was not already told.
AN_EXPIRED_HANDOFF_IS_READ_FOR_ITS_ASKER_AND_NAMES_NOTHING_ELSE: Final = (
    "gate.expired_handoffs returns, for each handed-on question that expired, which one it was, "
    "who asked, the queue and when it expired, and nothing else: not the question, not what was "
    "tried and not whom it was sent to. The process reads it to tell each asker one sentence "
    "about their own question, naming the queue they were already told it went to."
)

#: Why the web process tells the asker and the worker does not.
THE_WORKER_MARKS_AND_THE_WEB_PROCESS_TELLS: Final = (
    "The worker marks a handoff expired on its schedule and cannot write to a chat, because the "
    "channels' bot tokens are read under the application's vault role and the worker's policy "
    "grants none, on purpose. So the web process, which holds them, tells each asker, once, "
    "keyed through the operation ledger so every process can run the loop."
)

#: What the asker is told, naming the queue they were told their question went to.
A_HANDED_ON_QUESTION_NOBODY_PICKED_UP: Final = (
    "Nobody from {queue} picked up the question you handed on, so it is closed unanswered. You "
    "can ask it again."
)

# ------------------------------------------------------------------------ the figures
#: How often the web process asks which handoffs expired: as often as the worker marks them.
TELL_EVERY: Final = EXPIRY_EVERY

#: How far back each pass looks. A day, so a process down for hours still tells on its return;
#: the operation ledger makes a second pass over the same handoff send nothing.
LOOKBACK: Final = timedelta(days=1)

#: The most handoffs told in one pass, oldest first. A resource bound: the next pass tells the rest.
MOST_TOLD_PER_PASS: Final = 200

#: The key each message is sent once under, per handoff.
INTENT_PREFIX: Final = "escalation_expired"

#: `0177`'s function, written out so no statement here is assembled at run time.
_READ: Final = text(
    "SELECT escalation_id, asker_id, queue, expired_at"
    " FROM gate.expired_handoffs(:after, :until, :most)"
)


@dataclass(frozen=True)
class Expired:
    """One handed-on question that expired: which, who asked, the queue and when. Nothing more."""

    escalation_id: str
    asker_id: str
    queue: str
    expired_at: datetime


def expired_text(queue: str) -> str:
    """What the asker is told. See `A_HANDED_ON_QUESTION_NOBODY_PICKED_UP`."""
    return A_HANDED_ON_QUESTION_NOBODY_PICKED_UP.format(queue=queue)


def intent_ref_for(expired: Expired) -> str:
    """The key the message about this handoff is sent once under."""
    return f"{INTENT_PREFIX}.{expired.escalation_id}"


async def expired_between(
    sessions: async_sessionmaker[AsyncSession],
    *,
    after: datetime,
    until: datetime,
    most: int = MOST_TOLD_PER_PASS,
) -> tuple[Expired, ...]:
    """Every handoff that expired after `after` and by `until`, oldest first, bounded."""
    async with sessions() as session, session.begin():
        rows = (await session.execute(_READ.bindparams(after=after, until=until, most=most))).all()
    return tuple(
        Expired(
            escalation_id=str(one[0]), asker_id=str(one[1]), queue=str(one[2]), expired_at=one[3]
        )
        for one in rows
    )


async def tell_expired_askers(
    request: Request,
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    expired: Sequence[Expired] | None = None,
) -> int:
    """Tell each asker whose handoff expired in the last `LOOKBACK`, once. How many were sent now.

    Nothing while `QUESTION_NOT_PICKED_UP` is switched off. `expired`, when given, is the list to
    tell instead of reading it, which is how an install check tells only its own.
    """
    async with sessions() as session:
        if not await notice_is_on(session, NoticeKind.QUESTION_NOT_PICKED_UP):
            return 0
    due = (
        expired
        if expired is not None
        else await expired_between(sessions, after=now - LOOKBACK, until=now)
    )
    sent = 0
    for one in due:
        delivered = await tell(
            request, one.asker_id, expired_text(one.queue), intent_ref=intent_ref_for(one), now=now
        )
        # A second pass over the same handoff is handed the first's record and issues nothing.
        sent += (
            delivered is not None and delivered.issued and delivered.outcome is DeliveryOutcome.SENT
        )
    return sent


async def keep_telling_expired_askers(app: FastAPI) -> None:
    """Tell expired askers every `TELL_EVERY` for as long as the application runs.

    A failure is logged by its kind and the next pass tries again, as the mailbox loop does.
    """
    # Imported here: the mailbox module imports the events route, which imports this package.
    from brain.mailbox_read import request_for

    while True:
        await asyncio.sleep(TELL_EVERY.total_seconds())
        sessions = getattr(app.state, "db_sessions", None)
        if sessions is None:
            continue
        try:
            sent = await tell_expired_askers(request_for(app), sessions, now=datetime.now(UTC))
        except Exception as exc:
            log.warning("expired askers not told", kind=type(exc).__name__)
            continue
        if sent:
            log.info("expired askers told", sent=sent)
