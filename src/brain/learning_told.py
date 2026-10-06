"""Each person is told, once a week, what the system learnt from their own conversations, and
where to undo each thing, in the chat they last wrote on.

`brain.memory.digest.weekly_digest` builds one person's week at their own reach and has nothing that
sends it; `brain.member_activity.digest_for_channel` decides the form a channel can carry and has no
caller. The Notifications screen said so: "Nothing sends it yet". This is the sender, and it decides
four things and borrows everything else.

**Their own learnings, and only at the reach they hold now.** A learning is put in somebody's week
when it was formed from their own conversation, which is `brain.console.own_things.is_own` over the
formation's `principal_id`, and it is then shown only if `weekly_digest` admits it through
`formation.may_recall` about them as they are this week. Ownership admits the row and recall admits
it to the message, which is `brain.member_activity.OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_
WORDS` unchanged: somebody who formed a memory while holding a grant they have since lost is not
told about it, and a colleague's learning is never in anybody else's week. See
`A_WEEK_IS_THE_PERSONS_OWN_AND_AT_THE_REACH_THEY_HOLD_NOW`.

**The week is a calendar week in the install's zone, and the week is the key.** A run covers the
last complete week, Monday to Sunday, whenever in the current week it happens, and every message is
sent under `learning_digest.<the week covered>` through the operation ledger every send uses, by
`brain.tell_later.tell`. So two runs in one week, two web processes or a restart send each person
one message, and two consecutive weeks cover windows that neither overlap nor leave a gap. See
`ONE_WEEK_IS_ONE_MESSAGE_AND_THE_WEEK_IS_THE_KEY`. Rejected: a rolling seven days ending at the run,
keyed by the week the run falls in. A run late on Sunday and the next early on Monday are then two
weeks with five days in common, and the same learning arrives twice with two undo links.

**The message names a learning and never what it says.** Each item is the kind of change, the day,
the kinds of signal that prompted it, what undoing it does, and the memory's id beside the page its
undo is on. Not the memory's words: `brain.memory.digest.Learning` carries none by design, and a
chat message is a copy of whatever it holds outside the reach check, read wherever the chat is
open. The page shows the words at the reach the person holds when they open it. See
`THE_MESSAGE_NAMES_A_LEARNING_AND_NEVER_WHAT_IT_SAYS`.

**The undo is the person's own Forget, and nothing new.** `POST /me/memory/forget` is the one undo a
person has over a memory formed from their own words: `brain.console.own_things.delete_own_memory`
decides it is theirs, `brain.ops.memory_store.StoredMemoryRecords.undo` writes what
`brain.memory.digest.undo` decides under its lock, and a second press does nothing. Every item says
which memory and links the page whose Forget button posts it. A chat has nothing that could answer a
pressed control on a learning, so the form is the link for every channel, and the link is on every
row rather than missing from some. See `THE_UNDO_IS_THE_PERSONS_OWN_FORGET_ON_THEIR_OWN_PAGE`.

**A week with nothing learnt sends nothing.** The evening digest is sent on a quiet day because a
stall is the thing worth reading there; here an empty week is the system having learnt nothing from
somebody, and telling them so every Monday is a message trained into being ignored before the week
it matters. See `A_WEEK_WITH_NOTHING_LEARNT_SENDS_NOTHING`.

**The web process sends it, as it tells an asker their question expired.** The message goes through
`brain.tell_later.tell`, which plans it to the person's own address on the channel they last wrote
on, holds it to their reach at send time and sends it once; the channels' secrets and the mail relay
are read under the application's role, which the worker does not hold. **It is not a control yet.**
Registering one means widening `ops.control_run`'s name constraint, which is a migration, and no
migration was given to this change; until then the loop is started with the application, like
`brain.escalation_told`'s, and a week no process was running for is not sent. See
`THE_WEB_PROCESS_SENDS_IT_AND_IT_IS_NOT_A_CONTROL_YET`.

**A switch an administrator can turn off.** `LEARNING_DIGEST` is a row of `brain.ops.notices` and
the sender asks `notice_is_on` before each pass, as every sender does.

Task ids: M16.5.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo
from types import MappingProxyType
from typing import Final

import structlog
from fastapi import FastAPI
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from brain.console.own_things import is_own
from brain.core.entitlement import EntitlementSet
from brain.gate.resolve import EntitlementStore
from brain.memory.correction import Correction, corrected
from brain.memory.digest import Learning, MemoryItem, WeeklyDigest, weekly_digest
from brain.memory.signals import Signal
from brain.memory.tiers import Change
from brain.ops.notices import NoticeKind, notice_is_on
from brain.tables.channel import DeliveryOutcome
from brain.tables.learning import LearningRow
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow
from brain.tell_later import tell

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a week holds only the person's own learnings, and only those they may recall now.
A_WEEK_IS_THE_PERSONS_OWN_AND_AT_THE_REACH_THEY_HOLD_NOW: Final = (
    "A learning is put in somebody's week when it was formed from their own conversation, and it "
    "is shown only if recall admits it to them as they are now. Ownership admits the row and "
    "recall admits it to the message: a colleague's learning is in nobody else's week, and a "
    "learning formed under a grant the person has since lost is not named to them."
)

#: Why the week covered is the key, and the week is a calendar week.
ONE_WEEK_IS_ONE_MESSAGE_AND_THE_WEEK_IS_THE_KEY: Final = (
    "A run covers the last complete Monday to Sunday in the install's zone, whenever in the "
    "current week it happens, and each message is sent once under that week through the "
    "operation ledger. Two runs, two processes or a restart in one week send one message, and "
    "consecutive weeks neither overlap nor leave a gap, so no learning arrives twice."
)

#: Why the message carries no memory's words.
THE_MESSAGE_NAMES_A_LEARNING_AND_NEVER_WHAT_IT_SAYS: Final = (
    "A chat message is a copy of what it holds, outside any reach check, read wherever the chat "
    "is open. So each item names the kind of change, the day, the kinds of signal behind it, what "
    "undoing it does and which memory it is, and the words are read on the person's own page, at "
    "the reach they hold when they open it."
)

#: Why the undo is the person's own Forget and a link, on every row.
THE_UNDO_IS_THE_PERSONS_OWN_FORGET_ON_THEIR_OWN_PAGE: Final = (
    "The one undo a person has over a memory formed from their own words is Forget on their own "
    "page, which marks it under a lock and does nothing on a second press. Nothing answers a "
    "control pressed in a chat on a learning, so every item names its memory and links that "
    "page, on every row and every channel, rather than a button on some rows and none on others."
)

#: Why an empty week is not sent.
A_WEEK_WITH_NOTHING_LEARNT_SENDS_NOTHING: Final = (
    "An empty week is the system having learnt nothing from somebody. Telling them so every "
    "Monday is a message trained into being ignored before the week it matters, so a person "
    "with nothing learnt that they may recall is sent nothing at all."
)

#: Why the web process sends it, and why it is not a scheduled control.
THE_WEB_PROCESS_SENDS_IT_AND_IT_IS_NOT_A_CONTROL_YET: Final = (
    "The message is told through brain.tell_later, whose channels' secrets and mail relay are read "
    "under the application's role, which the worker does not hold, so the loop runs in the web "
    "process as the expired-question telling does. A scheduled control needs ops.control_run's "
    "names widened, which is a migration, so until one is written a week no process ran for is "
    "not sent."
)

# ------------------------------------------------------------------------ the figures
#: How often a web process asks whether this week's digests are owed. An hour, so a process started
#: on a Monday sends within the hour; the key makes every later pass in the week send nothing.
SEND_EVERY: Final = timedelta(hours=1)

#: The most learnings one pass reads, newest first. A resource bound: a week holding more is read
#: up to it, and the summary says the load came back full rather than how much was left.
MOST_LEARNINGS_PER_PASS: Final = 5000

#: The key each person's week is sent once under, with the week it covers after the dot.
INTENT_PREFIX: Final = "learning_digest"

#: Where a person's own Forget is: the console's My workspace page, which posts
#: `/me/memory/forget` for the memory a person picks.
UNDO_PAGE: Final = "/me"

#: What the page is called when the install names no public address to link it at.
UNDO_PAGE_UNLINKED: Final = "My workspace in the console"

#: The install setting whose first address is this install's public origin.
PUBLIC_ADDRESS_SETTING: Final = "INSTALL_OIDC_REDIRECT_URIS"

#: The opening line, with the week's first and last day.
OPENING: Final = (
    "What the system learnt from your conversations from {first} to {last}. Undoing one marks it "
    "so it stops being used, and nothing is deleted."
)

#: One item.
ITEM: Final = (
    "- {what}, learnt on {day}{because}. {undoing} Undo: Forget on memory {memory_id}, on {page}."
)

#: What pressing Forget does, by the correction it writes.
UNDOING: Final[Mapping[Correction, str]] = MappingProxyType(
    {
        Correction.SUPERSEDED: "Undoing it puts back what it replaced.",
        Correction.DEMOTED: "Undoing it stops it being used.",
    }
)

#: Each change a week can carry, in the words a person reads it in.
CHANGE_WORDS: Final[Mapping[Change, str]] = MappingProxyType(
    {
        Change.PREFERENCE: "How you like answers shaped",
        Change.RETRIEVAL_BOOST: "A source to rank higher for you",
        Change.RETRIEVAL_DEMOTION: "A source to rank lower for you",
        Change.ENTITY_LINK: "Two records being the same thing",
        Change.NEGATIVE_SIGNAL: "An answer that did not go well",
        Change.FAST_PATH_RULE: "A question it can answer without a model",
        Change.PROCEDURAL_SHORTCUT: "A sequence of steps you repeat",
    }
)

#: Each kind of signal, as the reason a learning was formed.
SIGNAL_WORDS: Final[Mapping[Signal, str]] = MappingProxyType(
    {
        Signal.REASKED: "you asked again in other words",
        Signal.COPIED: "you copied an answer",
        Signal.CONTRADICTED: "a follow-up contradicted an answer",
        Signal.ESCALATED: "the conversation went to a person",
        Signal.TAKEN_OVER: "a person took over an action",
        Signal.REOPENED: "a ticket was reopened",
        Signal.REJECTED: "an approval was refused",
    }
)


# ------------------------------------------------------------------------ the week
@dataclass(frozen=True)
class CoveredWeek:
    """The week one message covers, half open as `(covers_from, covers_to]`, and its key."""

    covers_from: datetime
    covers_to: datetime
    #: The ISO week covered, such as `2026-W40`, which the message is sent once under.
    key: str

    def __post_init__(self) -> None:
        if not self.covers_from < self.covers_to:
            msg = "a week that ends before it starts covers nothing and keys a message all the same"
            raise ValueError(msg)
        if not self.key.strip():
            msg = "a week with no key sends every person's message under one shared key"
            raise ValueError(msg)


def covered_week(now: datetime, zone: tzinfo) -> CoveredWeek:
    """The last complete Monday to Sunday before `now`, in `zone`, keyed by its ISO week.

    The boundaries are midnights in the zone, so a week holding a change of clocks is a week of the
    calendar rather than seven times twenty-four hours. See
    `ONE_WEEK_IS_ONE_MESSAGE_AND_THE_WEEK_IS_THE_KEY`.
    """
    local = now.astimezone(zone)
    this_monday = local.date() - timedelta(days=local.weekday())
    last_monday = this_monday - timedelta(days=7)
    iso = last_monday.isocalendar()
    return CoveredWeek(
        covers_from=datetime.combine(last_monday, time(0), tzinfo=zone).astimezone(UTC),
        covers_to=datetime.combine(this_monday, time(0), tzinfo=zone).astimezone(UTC),
        key=f"{iso.year}-W{iso.week:02d}",
    )


def intent_ref_for(week: CoveredWeek) -> str:
    """The key a person's message for this week is sent once under, beside their own id."""
    return f"{INTENT_PREFIX}.{week.key}"


# ------------------------------------------------------------------------ the digest
def own_digest(
    *,
    reader: EntitlementSet,
    learnings: Sequence[Learning],
    marked: Collection[str],
    week: CoveredWeek,
    now: datetime,
) -> WeeklyDigest:
    """This person's week: their own learnings, not yet undone, that they may recall now.

    `weekly_digest` decides, at `now` and over the window from the week's start, so a reader's grant
    is judged at the instant they are told rather than at the end of the week; what it admits after
    the week's end belongs to next week's message. A memory already marked, either way, is left out,
    because its undo would do nothing. See
    `A_WEEK_IS_THE_PERSONS_OWN_AND_AT_THE_REACH_THEY_HOLD_NOW`.
    """
    theirs = [
        one
        for one in learnings
        if is_own(reader.principal_id, one.formation.principal_id) and one.memory_id not in marked
    ]
    found = weekly_digest(now=now, reader=reader, learnings=theirs, period=now - week.covers_from)
    return WeeklyDigest(
        reader_id=found.reader_id,
        covers_from=week.covers_from,
        covers_to=week.covers_to,
        entries=tuple(one for one in found.entries if one.learned_at <= week.covers_to),
    )


def worth_sending(digest: WeeklyDigest) -> bool:
    """Whether a week is sent at all. See `A_WEEK_WITH_NOTHING_LEARNT_SENDS_NOTHING`."""
    return bool(digest.entries)


def _day(at: datetime, zone: tzinfo) -> str:
    local = at.astimezone(zone)
    return f"{local.day} {local:%B}"


def item_text(item: MemoryItem, *, page: str, zone: tzinfo) -> str:
    """One learning, as its line. See `THE_MESSAGE_NAMES_A_LEARNING_AND_NEVER_WHAT_IT_SAYS`."""
    because = ", ".join(SIGNAL_WORDS.get(one, one.value) for one in item.evidence)
    return ITEM.format(
        what=CHANGE_WORDS.get(item.change, item.change.value),
        day=_day(item.learned_at, zone),
        because=f", because {because}" if because else "",
        undoing=UNDOING[item.control_writes],
        memory_id=item.memory_id,
        page=page,
    )


def digest_text(digest: WeeklyDigest, *, page: str, zone: tzinfo) -> str:
    """The whole message: the week's first and last day, then one line per learning, newest first.

    The last day is the one before the week's end, which is a midnight belonging to the next week.
    """
    opening = OPENING.format(
        first=_day(digest.covers_from, zone),
        last=_day(digest.covers_to - timedelta(microseconds=1), zone),
    )
    return "\n".join((opening, *(item_text(one, page=page, zone=zone) for one in digest.entries)))


def undo_page(redirect_uris: str) -> str:
    """Where a person's Forget is: the install's origin and `UNDO_PAGE`, or the page's name.

    The origin is the one every address this install hands out is built on, its first redirect
    address. With none, the page is named rather than linked by a path a chat could not open.
    """
    from brain.ops.lark_connect import install_origin

    origin = install_origin(redirect_uris)
    return f"{origin}{UNDO_PAGE}" if origin else UNDO_PAGE_UNLINKED


def undo_page_here() -> str:
    """`undo_page` over this install's saved public address, or the page's name with none set."""
    from brain.install import InstallError, value_of

    try:
        return undo_page(value_of(PUBLIC_ADDRESS_SETTING))
    except InstallError:
        return UNDO_PAGE_UNLINKED


# ------------------------------------------------------------------------ the load
@dataclass(frozen=True)
class Loaded:
    """The learnings recorded since a week began, the memories already marked, and whether the
    load came back full."""

    learnings: tuple[Learning, ...]
    marked: frozenset[str]
    full: bool = False


def recorded_since(since: datetime, most: int) -> Select[tuple[LearningRow]]:
    """The learning records written after `since`, newest first, bounded.

    Recorded after rather than formed after, because the record is written when the memory is, so
    nothing formed in the week was recorded before it began; what was recorded in the week and
    formed before it is left out by `weekly_digest`'s own window.
    """
    return (
        select(LearningRow)
        .where(LearningRow.recorded_at > since)
        .order_by(LearningRow.recorded_at.desc(), LearningRow.memory_id)
        .limit(most)
    )


async def learnings_since(
    sessions: async_sessionmaker[AsyncSession],
    since: datetime,
    *,
    most: int = MOST_LEARNINGS_PER_PASS,
) -> Loaded:
    """Every learning recorded since `since` as the domain's `Learning`, with the marked memories.

    Read as the Learning screen reads a learning, by the functions it uses
    (`brain.estate_routes.stored_memory` and `recorded_learning`), so a row the domain refuses is
    skipped here exactly as it is there.
    """
    # Imported here: the route modules import the application's wiring, which starts this loop.
    from brain.estate_routes import recorded_learning, stored_memory
    from brain.ops.memory_store import (
        corrections_naming,
        corrections_of,
        inferred_named,
        stated_named,
    )

    async with sessions() as session:
        rows = (await session.execute(recorded_since(since, most))).scalars().all()
        ids = [one.memory_id for one in rows]
        if not ids:
            return Loaded(learnings=(), marked=frozenset())
        stated = (await session.execute(stated_named(ids))).scalars().all()
        inferred = (await session.execute(inferred_named(ids))).scalars().all()
        marks = (await session.execute(corrections_naming(ids))).scalars().all()
    memory_rows: list[PersistentMemoryRow | AdaptiveMemoryRow] = [*stated, *inferred]
    memories = {
        found[0].memory_id: found[0]
        for found in (stored_memory(row) for row in memory_rows)
        if found is not None
    }
    learnings = tuple(
        learning
        for learning in (
            recorded_learning(row, memories[row.memory_id])
            for row in rows
            if row.memory_id in memories
        )
        if learning is not None
    )
    found = corrections_of(marks)
    return Loaded(
        learnings=learnings,
        marked=corrected(found.supersessions, found.demotions),
        full=len(rows) >= most,
    )


# ------------------------------------------------------------------------ the send
@dataclass(frozen=True)
class Told:
    """What one pass came to. Counts for the caller; `summary` names no person and no number."""

    sent: int = 0
    #: Handed a key a person's week was already sent under, so nothing was sent.
    already: int = 0
    #: Planned and not delivered, or with nowhere to send: no address, a channel off, a reach gone.
    undelivered: int = 0
    switched_off: bool = False
    #: The load reached `MOST_LEARNINGS_PER_PASS`, so the oldest of the week were not read.
    full: bool = False

    def summary(self) -> str:
        """What a log line says. Whether anything happened, never how much or to whom."""
        if self.switched_off:
            return "the learning digest is switched off, so nothing was sent"
        said = [
            "sent" if self.sent else "nothing new sent",
            *(["some were already sent this week"] if self.already else []),
            *(["some could not be delivered"] if self.undelivered else []),
            *(["the week's load came back full"] if self.full else []),
        ]
        return f"the learning digest: {'; '.join(said)}"


async def send_learning_digests(
    request: Request,
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    zone: tzinfo,
    page: str,
    readers: EntitlementStore,
    week: CoveredWeek | None = None,
    only: Collection[str] | None = None,
) -> Told:
    """Tell each person their own week, once. Nothing while `LEARNING_DIGEST` is switched off.

    `week` defaults to the last complete week before `now` in `zone`. `only`, when given, is the
    people to consider instead of everybody a learning was formed from, which is how an install
    check tells only its own. `readers` is where each person's reach is loaded, at `now`; the send
    loads it again when it leaves, through `tell`.
    """
    async with sessions() as session:
        if not await notice_is_on(session, NoticeKind.LEARNING_DIGEST):
            return Told(switched_off=True)
    covered = covered_week(now, zone) if week is None else week
    loaded = await learnings_since(sessions, covered.covers_from)
    people = (
        sorted(set(only))
        if only is not None
        else sorted({one.formation.principal_id for one in loaded.learnings})
    )
    sent = already = undelivered = 0
    for person in people:
        # An ended reach is not skipped here: recall admits nothing to it, so its week is empty,
        # and `tell` refuses it again when the message would leave.
        digest = own_digest(
            reader=await readers.load(person, now),
            learnings=loaded.learnings,
            marked=loaded.marked,
            week=covered,
            now=now,
        )
        if not worth_sending(digest):
            continue
        delivered = await tell(
            request,
            person,
            digest_text(digest, page=page, zone=zone),
            intent_ref=intent_ref_for(covered),
            now=now,
        )
        if delivered is None or delivered.outcome is not DeliveryOutcome.SENT:
            undelivered += 1
        elif delivered.issued:
            sent += 1
        else:
            already += 1
    return Told(sent=sent, already=already, undelivered=undelivered, full=loaded.full)


async def learning_pass(app: FastAPI, *, now: datetime, done: str) -> str:
    """One pass of the loop: the last complete week's digests, unless this process finished that
    week already. Returns the week this process has now finished, which the next pass is handed.

    A pass on a switched-off notice finishes nothing, so switching it on mid-week sends that week's
    on the next pass. A pass another process or an earlier start made is answered by the operation
    ledger with nothing sent, so finishing is this process's saving and never what makes it once.
    """
    # Imported here: these modules import the events route, which imports this package.
    from brain.channel_routes import reach_of
    from brain.locale import time_zone
    from brain.mailbox_read import request_for

    sessions = getattr(app.state, "db_sessions", None)
    if sessions is None:
        return done
    zone = time_zone()
    week = covered_week(now, zone)
    if week.key == done:
        return done
    request = request_for(app)
    told = await send_learning_digests(
        request,
        sessions,
        now=now,
        zone=zone,
        page=undo_page_here(),
        readers=reach_of(request),
        week=week,
    )
    log.info("learning digest pass", said=told.summary())
    return done if told.switched_off else week.key


async def keep_sending_learning_digests(app: FastAPI) -> None:
    """Run `learning_pass` every `SEND_EVERY` for as long as the application runs.

    A failure is logged by its kind and the next pass tries again, as the expired-question loop
    does.
    """
    done = ""
    while True:
        await asyncio.sleep(SEND_EVERY.total_seconds())
        try:
            done = await learning_pass(app, now=datetime.now(UTC), done=done)
        except Exception as exc:
            log.warning("learning digest not sent", kind=type(exc).__name__)
