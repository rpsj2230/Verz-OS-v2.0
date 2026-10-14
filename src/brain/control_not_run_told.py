"""The people who hold the operations alert are told when a safety mechanism has not run.

`brain.ops.controls.overdue` has said which controls are late since the registry was written, and
until this module nothing sent it anywhere: `brain.ops.notices` listed `control_not_run` with "no
channel is chosen for it yet, so nothing sends it", and the only place a missed run showed was the
Incidents screen, which nobody has a reason to open on the day a sweep silently stops. The owner
decided (decision 221, option C) who is told and how, and this module is that decision.

**Who is told: whoever holds the operations alert and may open Incidents.** The route for each
severity is `brain.ops.alerting.route_for`, and the audience it names is a capability and never a
person (`AN_ALERT_ROUTES_TO_A_ROLE_AND_NEVER_TO_A_PERSON`). Everybody gets the operations alert; for
a control whose route wakes somebody, the incident capability's holders are told too. A holder must
also be able to open the Incidents screen across the install, asked the way the System health read
asks it, because **a message that points somebody at a screen they would be refused is an alert
they cannot act on**. The reach asked is each person's own, loaded at the instant of the pass.

**How: in the chat tool each last used, through `brain.tell_later`.** The one sender for a message
a person is told later, so the address is their own, a lapsed reach sends nothing and the message
is keyed and recorded as every reply is. It names no `NotificationKind`, so a person's quiet hours
and channel preferences do not hold it back: a safety mechanism that has stopped is not a digest.

**The email fallback: only when none of those holders has used a chat tool in seven days.** Then
the install's own `INSTALL_ALERT_EMAIL` is sent the same sentence through the relay saved on
Notifications, once per episode. It is the install's value, read in the one place installation
values are read, and it is `unset` until somebody sets it on Install, Settings, so nothing here
names an address and an install that never sets one is told nothing by email. A holder who last
used chat eight days ago is still told in chat, because the address is theirs and costs nothing;
the email is for the day nobody is likely to see it. Somebody is only counted as having used chat if
the message reached them there: a channel an administrator switched off, or a refusal, is the same
as no chat at all, and the email goes. How recent a person last wrote is the mark
`brain.ops.binding_store.StoredAddresses.last_used_at` reads, kept to the hour, so no migration
was needed.

**The sentence names the mechanism and how long, and never what it guards.** `Overdue.text` says
what the control guards and what is lost until it runs, which is the sentence an operator reads on
the Incidents screen, and a chat message is forwarded. The text here is built from the control's
name and its cadence alone, and `brain.ops.alerting.disclosure_findings` is asked of it in a test
for every control in the registry (`A_CONTROL_ALERT_NAMES_THE_MECHANISM_AND_NEVER_WHAT_IT_GUARDS`).

**Once per episode.** The key is the control's name and the instant of its last success, or
`never`: a control that runs again and then stops again is a second episode, and a pass every
fifteen minutes in every web process tells nobody twice. Only a control that has run and gone
quiet, or never ran while this process has been watching for longer than its alert window, is
told; a control nothing calls or nothing records is a fact about the software that the Incidents
screen already states on every install, and telling it once per install would be noise
(`WHAT_IS_NOT_A_MISSED_RUN`).

**The web process tells and the worker marks.** The worker writes each run to `ops.control_run`
and cannot hold a channel's bot token or the relay's password, on purpose, so the loop runs in the
web process beside `brain.automation_paused_told`, which is this module's template, and reads the
rows the worker already writes.

**It ships off.** `CONTROL_NOT_RUN_ALERTS` is a feature, so an install turns it on after the owner
has seen it work (`brain.ops.features`). The notice has no switch of its own, by
`A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH`; this switch is on the new path and not on the
notice, and the tension between the two is stated in
`A_SWITCH_ON_THE_NEW_PATH_IS_NOT_A_SWITCH_ON_THE_NOTICE`.

Rejected: telling from the worker by granting it the channel tokens, which reverses a written
security choice for one message (`brain.automation_paused_told`). Rejected: telling a person by
the name of the control's owner, because an alert routes to a role. Rejected: telling every
person who has ever held the capability, which is a list of who held it.

Task ids: M17.7.2, M17.7.6
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from brain.chat_answer import console_link
from brain.console.department_console import held_across_the_install
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.install import value_of
from brain.ops.alerting import OPERATIONS_ALERT, Severity, route_for
from brain.ops.binding_store import ADDRESS_KEPT_ON
from brain.ops.controls import Control, Missed, Overdue, overdue
from brain.ops.features import is_on
from brain.ops.features_declared.control_not_run_alerts import CONTROL_NOT_RUN_ALERTS
from brain.ops.mail import Message, alert_operation, send_alert
from brain.ops.notices import NoticeKind, notice_is_on
from brain.ops.schedule import schedulable
from brain.ops.schedule_store import last_successes
from brain.tables.channel import DeliveryOutcome
from brain.tell_later import tell

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the sentence is built here and `Overdue.text` is not used.
A_CONTROL_ALERT_NAMES_THE_MECHANISM_AND_NEVER_WHAT_IT_GUARDS: Final = (
    "The alert says which mechanism has not run and for how long, and how often it should. What it "
    "guards and what is lost until it runs is on the Incidents screen, which only a person allowed "
    "to open it reads, and a chat message is forwarded, pasted and read over a shoulder."
)

#: Why the notice has no switch and this path has one.
A_SWITCH_ON_THE_NEW_PATH_IS_NOT_A_SWITCH_ON_THE_NOTICE: Final = (
    "The notice that a safety mechanism has not run has no switch, so nobody at the console can "
    "silence it. The feature `control_not_run_alerts` gates a new way of sending it, which ships "
    "off until it has been seen working, and which is to be removed when it has, leaving the "
    "notice with no switch again. Until then switching the feature off stops this delivery and "
    "nothing else: the Incidents screen and the System health check say the same thing."
)

#: Why a control nothing calls, or nothing records, is not told.
WHAT_IS_NOT_A_MISSED_RUN: Final = (
    "A control nothing calls, and one nothing records runs of, is a statement about the software "
    "and is true on every install on every pass. It has no window to have missed, and sending it "
    "would be one message per install per control that nobody can act on. The Incidents screen "
    "states both."
)

# ------------------------------------------------------------------------ the figures
#: How often each web process asks which controls are late. A control's own window is hours at the
#: shortest, so a quarter of an hour is prompt without being a poll.
TELL_EVERY: Final = timedelta(minutes=15)

#: How recently somebody must have used a chat tool to be a person the chat will reach. A week.
CHAT_USE_WINDOW: Final = timedelta(days=7)

#: The most people whose reach one pass loads. A resource bound; an install has hundreds of staff.
MOST_PEOPLE_PER_PASS: Final = 2000

#: The key each message is sent under, per episode.
INTENT_PREFIX: Final = "control_not_run"

#: The words before the link to the Incidents screen.
OPEN_IT: Final = "Open Incidents:"

#: The screen an alert points at and a recipient must be able to open. Held to
#: `brain.system_health_routes.INCIDENTS_SCREEN` by a test.
INCIDENTS_SCREEN: Final = "incidents"

#: The path of that screen on the install's console.
INCIDENTS_PATH: Final = "/incidents"

#: Who an email is recorded as sent by. Not a person: an alert is the system's.
ALERTER_ACTOR: Final = "control-alerter"

#: The subject of the email. Names no mechanism, because a subject is shown on a lock screen.
EMAIL_SUBJECT: Final = "A safety mechanism has not run"

#: The setting holding the fallback address, and the value meaning none.
ALERT_EMAIL_SETTING: Final = "INSTALL_ALERT_EMAIL"
ALERT_EMAIL_UNSET: Final = "unset"

#: Controls the alert does not cover. See `WHAT_IS_NOT_A_MISSED_RUN`.
NOT_TOLD: Final = frozenset({Missed.UNREACHABLE, Missed.NOT_RECORDED})


@dataclass(frozen=True)
class Late:
    """One control that has missed its window, and when it last succeeded."""

    overdue: Overdue
    last_success: datetime | None

    @property
    def name(self) -> str:
        return self.overdue.control.name


@dataclass(frozen=True)
class Told:
    """What one pass did. Counts of messages and of episodes, and never of people.

    `unreachable` is the episodes nobody could be told of: no holder in a chat tool recently and no
    email address or relay to fall back on. Logged by the loop and shown by no screen.
    """

    chat: int = 0
    email: int = 0
    unreachable: int = 0
    late: int = 0
    switched_off: bool = False


# ------------------------------------------------------------------------- the pure half
def how_long(span: timedelta) -> str:
    """A span as an operator reads it: whole days, else whole hours, else whole minutes."""
    seconds = int(span.total_seconds())
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            count = seconds // size
            return f"{count} {unit}{'' if count == 1 else 's'}"
    return "less than a minute"


def late_controls(
    last_success: Mapping[str, datetime],
    *,
    now: datetime,
    since: datetime,
    controls: Sequence[Control] | None = None,
) -> tuple[Late, ...]:
    """The controls that have missed their window, loudest first, and only those worth telling.

    `last_success` is each control's last successful finish, as `schedule_store.last_successes`
    reads it. A control never run counts only once `since`, when this process began watching, is
    longer ago than its own alert window: a freshly started install has run nothing yet and the
    worker's first tick is minutes away, so the first pass would otherwise tell everybody that
    everything is late. See `WHAT_IS_NOT_A_MISSED_RUN` for the two reasons left out.
    """
    watched = schedulable(controls)
    recorded: dict[str, datetime | None] = {one.name: None for one in watched}
    recorded.update(last_success)
    found: list[Late] = []
    for one in overdue(last_run=recorded, now=now, controls=watched):
        if one.missed in NOT_TOLD:
            continue
        if one.missed is Missed.NEVER_RUN and now - since <= one.control.alert_after:
            continue
        found.append(Late(one, last_success.get(one.control.name)))
    return tuple(found)


def control_text(one: Late, *, now: datetime, link: str = "") -> str:
    """The sentence a person is told. The mechanism, how long and how often, and where to look.

    See `A_CONTROL_ALERT_NAMES_THE_MECHANISM_AND_NEVER_WHAT_IT_GUARDS`.
    """
    every = how_long(one.overdue.control.every)
    if one.last_success is None:
        said = f"The safety mechanism {one.name} has not run since this system was started."
    else:
        said = (
            f"The safety mechanism {one.name} has not run for {how_long(now - one.last_success)}."
        )
    said = f"{said} It should run every {every}."
    return f"{said} {OPEN_IT} {link}" if link else said


def intent_ref_for(one: Late) -> str:
    """The key an episode is told under: the control and the last success that began its silence."""
    stamp = "never" if one.last_success is None else one.last_success.astimezone(UTC).isoformat()
    return f"{INTENT_PREFIX}.{one.name}.{stamp}"


def audiences_for(severity: Severity) -> tuple[Capability, ...]:
    """The capabilities whose holders are told at this severity: the operations alert, and for a
    route that wakes somebody the audience that route names too."""
    route = route_for(severity)
    return (OPERATIONS_ALERT, route.audience) if route.wakes_somebody else (OPERATIONS_ALERT,)


def may_be_told(reach: EntitlementSet, severity: Severity, now: datetime) -> bool:
    """Whether this person's own reach holds an audience for this severity and opens Incidents.

    Asked at `now`, so a reach that has lapsed is nobody's: `scope_for` answers None for an expired
    principal, which is why there is no separate expiry test here (a mutation removing one survived,
    and was equivalent). The Incidents screen is asked as the System health read asks it: its own
    read, and held across the whole install.
    """
    if not any(reach.scope_for(one, now) is not None for one in audiences_for(severity)):
        return False
    found = screen(INCIDENTS_SCREEN)
    return permitted(found.read, reach, now) and held_across_the_install(found, reach, now)


def no_chat_lately(holders: Sequence[str], used: Mapping[str, datetime], *, now: datetime) -> bool:
    """Whether none of these people has used a chat tool within `CHAT_USE_WINDOW` of `now`."""
    return not any(
        (at := used.get(one)) is not None and now - at <= CHAT_USE_WINDOW for one in holders
    )


def alert_email() -> str | None:
    """The address the install named for this, or None. Read where every installation value is."""
    written = value_of(ALERT_EMAIL_SETTING).strip()
    return None if not written or written == ALERT_EMAIL_UNSET else written


# ------------------------------------------------------------------------ the sending half
async def control_alerts_are_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether `control_not_run_alerts` is switched on now. Off when nobody has said otherwise."""
    async with sessions() as session:
        return await is_on(session, CONTROL_NOT_RUN_ALERTS)


async def _everyone_addressed(request: Request) -> tuple[str, ...]:
    """Every person with a chat address kept, who are the only people the chat can reach."""
    from brain.channel_routes import addresses_of

    book = addresses_of(request)
    if book is None:
        return ()
    found: set[str] = set()
    for channel in sorted(ADDRESS_KEPT_ON, key=lambda one: one.value):
        found.update(person for person, _ in await book.addressed(channel))
    return tuple(sorted(found))[:MOST_PEOPLE_PER_PASS]


async def _email(request: Request, to: str, one: Late, text: str) -> bool | None:
    """Send the alert to an address once per episode, through the relay saved on Notifications.

    None when there is no relay to send through, in which case nothing was claimed and the next
    pass tries again; otherwise whether the relay accepted it.
    """
    from brain.channel_routes import ledger_of, relay_of

    relay = relay_of(request)
    run = ledger_of(request)
    operation = alert_operation(actor=ALERTER_ACTOR, intent_ref=intent_ref_for(one), to=to)

    def work() -> bool | None:
        transport = relay()
        if transport is None:
            return None
        sent = send_alert(
            run,
            operation,
            transport,
            Message(to=to, subject=EMAIL_SUBJECT, body=text, auto_submitted="auto-generated"),
        )
        return sent.accepted

    return await asyncio.to_thread(work)


async def tell_overdue_controls(
    request: Request,
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    since: datetime,
    last_success: Mapping[str, datetime] | None = None,
    people: Sequence[str] | None = None,
    email: str | None = None,
    controls: Sequence[Control] | None = None,
) -> Told:
    """Tell the holders of the operations alert about each control that has missed its window.

    `last_success`, `people`, `email` and `controls`, when given, replace reading the install's
    own, which is how an install check asks about controls and people of its own and no other.
    `email` is the fallback address; None reads `INSTALL_ALERT_EMAIL`.
    """
    if not await control_alerts_are_on(sessions):
        return Told(switched_off=True)
    async with sessions() as session:
        if not await notice_is_on(session, NoticeKind.CONTROL_NOT_RUN):
            return Told(switched_off=True)
        succeeded = (
            dict(last_success) if last_success is not None else await last_successes(session)
        )
    late = late_controls(succeeded, now=now, since=since, controls=controls)
    if not late:
        return Told()

    from brain.channel_routes import addresses_of, reach_of

    candidates = tuple(people) if people is not None else await _everyone_addressed(request)
    reaches = {one: await reach_of(request).load(one, now) for one in candidates}
    book = addresses_of(request)
    link = console_link(INCIDENTS_PATH)
    address = alert_email() if email is None else email

    chat = by_email = unreachable = 0
    for one in late:
        holders = [
            person
            for person, reach in reaches.items()
            if may_be_told(reach, one.overdue.severity, now)
        ]
        text = control_text(one, now=now, link=link)
        reached: list[str] = []
        for person in holders:
            delivered = await tell(
                request,
                person,
                text,
                intent_ref=intent_ref_for(one),
                now=now,
            )
            landed = delivered is not None and delivered.outcome is DeliveryOutcome.SENT
            if landed:
                reached.append(person)
            # A second pass over the same episode is handed the first's record and issues nothing.
            chat += landed and delivered is not None and delivered.issued
        used = await book.last_used_at(reached) if book is not None and reached else {}
        if not no_chat_lately(reached, used, now=now):
            continue
        accepted = None if address is None else await _email(request, address, one, text)
        by_email += bool(accepted)
        unreachable += not reached and not accepted
    return Told(chat=chat, email=by_email, unreachable=unreachable, late=len(late))


async def keep_telling_overdue_controls(app: FastAPI) -> None:
    """Tell about late controls every `TELL_EVERY` for as long as the application runs.

    A failure is logged by its kind and the next pass tries again. The instant this process began
    is what a control that has never run is measured from; see `late_controls`.
    """
    # Imported here: the mailbox module imports the events route, which imports this package.
    from brain.mailbox_read import request_for

    since = datetime.now(UTC)
    while True:
        await asyncio.sleep(TELL_EVERY.total_seconds())
        sessions = getattr(app.state, "db_sessions", None)
        if sessions is None:
            continue
        try:
            told = await tell_overdue_controls(
                request_for(app), sessions, now=datetime.now(UTC), since=since
            )
        except Exception as exc:
            log.warning("late controls not told", kind=type(exc).__name__)
            continue
        if told.chat or told.email:
            log.info("late controls told", chat=told.chat, email=told.email)
        if told.unreachable:
            log.warning("late controls nobody could be told of", episodes=told.unreachable)
