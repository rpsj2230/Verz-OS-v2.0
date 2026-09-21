"""Who this product tells what, how, whether anything sends it yet, and the switch that stops it.

An administrator asked "who is told what, and how do I stop it" had no answer anywhere. The
product composes a dozen kinds of notice, each in its own module with its own idea of a recipient,
and a search of the source on 2026-09-17 found that exactly one of them is sent by anything that
runs: the re-verification request, which the worker's schedule records as an event for webhook
subscribers. The rest are composed, tested and called by nothing. This module is the list, in one
place, with the facts a person needs about each, and the one switch a person turns.

**The list is closed and each row names the function that composes the notice.** A row naming a
composer that does not exist is refused by a test that imports it, and a row saying a notice is
sent names the function that sends it, which a test holds to having a caller. So "sent" on the
screen is a claim the source answers rather than a word somebody chose.

**Absent means on.** A notice ships on, because a notice nobody switched on is a notice nobody
receives while the screen says it exists; `brain.ops.features` makes the opposite choice for a
feature, and for the opposite reason. A person switching a notice off writes `false` into
`ops.setting` under `notice.<kind>`, with their name on the row, and switching it on again writes
`true`, so the row says who last decided. See `A_NOTICE_SHIPS_ON`.

**Some notices cannot be switched off, and the screen says why rather than hiding the switch.**
A notice that a safety mechanism has stopped running, that somebody took emergency access, that
an administrator granted themselves something, or that an automation was paused for failing, each
exists to tell somebody about a thing the person at the console may have done or may be trying
not to be told. A switch on the console that silenced it would be a switch for the failure it
reports. `brain.console.reads.StewardNotice` and `brain.console.agent_automations.OwnerNotice`
already say "no field could suppress this" about two of them; this is the same rule, for all of
them, in the place the switch would otherwise be. See
`A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH`.

**Every sender asks `notice_is_on` at the moment it sends, and the one sender that exists does.**
`brain.knowledge.item_store.run_reverification` asks before it records anything, so switching the
request off stops it from the next run. A sender added later for any other row asks the same
function, and `test_notices` holds the rows marked sent to senders that ask.

Rejected: a preference per person. `brain.member.connections` models which channel a person wants
each kind on, and nothing sends anything to a person yet for it to apply to. An install-wide
switch is the one a person can turn today and see change something.

Task ids: M27.8.11, M27.7.12
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons
#: Why a notice is on unless a person switched it off.
A_NOTICE_SHIPS_ON: Final = (
    "A notice exists because somebody should be told something, and one that ships off is told to "
    "nobody while the screen lists it as a thing this product does. So no row means on, and only "
    "a row a person wrote holding false means off."
)

#: Why some notices have no switch.
A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH: Final = (
    "A notice that a safety mechanism stopped running, that somebody took emergency access, that "
    "an administrator granted themselves more, or that an automation was paused for failing, tells "
    "people about something the person at this console may have caused. A switch that silenced it "
    "from here would be a way to do the thing and not be seen doing it, so these have none."
)

#: The namespace a switch is kept under in `ops.setting`.
NOTICE_NAMESPACE: Final = "notice"

#: What a switch row says it is, which `ops.setting` requires of every row.
SWITCH_DESCRIPTION: Final = "Whether this notice is sent. No row, or true, is on; false is off."


class NoticeError(Exception):
    """A notice was named that this product does not declare, or one with no switch was switched."""


class NoticeKind(enum.StrEnum):
    """Every kind of notice this product composes for people. Closed."""

    REVERIFICATION_REQUEST = "reverification_request"
    EVENING_DIGEST = "evening_digest"
    APPROVAL_REQUEST = "approval_request"
    DENIAL_PATTERN = "denial_pattern"
    BUDGET_STOPPED = "budget_stopped"
    ACCESS_REQUEST = "access_request"
    HANDED_TO_A_PERSON = "handed_to_a_person"
    LEARNING_DIGEST = "learning_digest"
    CONTROL_NOT_RUN = "control_not_run"
    BACKUP_EXPOSURE = "backup_exposure"
    EMERGENCY_ACCESS = "emergency_access"
    SELF_GRANT = "self_grant"
    AUTOMATION_PAUSED = "automation_paused"


@dataclass(frozen=True)
class Notice:
    """One kind of notice: who is told, what, how, what composes it and what sends it.

    `sent_by` is the function that delivers it on a running install, and empty when nothing does.
    `fixed_because` is empty exactly when the notice has a switch.
    """

    kind: NoticeKind
    title: str
    told: str
    about: str
    how: str
    composed_by: str
    sent_by: str = ""
    fixed_because: str = ""

    @property
    def switchable(self) -> bool:
        return not self.fixed_because

    def __post_init__(self) -> None:
        for name in ("title", "told", "about", "how", "composed_by"):
            if not str(getattr(self, name)).strip():
                msg = f"{self.kind.value}: a notice says {name}, or a person cannot judge it"
                raise NoticeError(msg)


#: Every notice, in the order the screen lists them: what is sent first, then what is composed and
#: switchable, then what has no switch.
NOTICES: Final[tuple[Notice, ...]] = (
    Notice(
        kind=NoticeKind.REVERIFICATION_REQUEST,
        title="Knowledge due to be checked again",
        told=(
            "The owner of a knowledge item whose review date has come, while the owner can still "
            "read it; otherwise the item's department, or the whole company."
        ),
        about="That the item needs checking, by its identifier and never its title.",
        how=(
            "Recorded as an approval request and sent to every webhook subscriber that takes "
            "approval requests. No person is sent it directly yet."
        ),
        composed_by="brain.knowledge.item_store:nag_event",
        sent_by="brain.knowledge.item_store:run_reverification",
    ),
    Notice(
        kind=NoticeKind.EVENING_DIGEST,
        title="Evening digest",
        told="One staff room named in configuration, never a person.",
        about="What the day's plan closed, opened and is stuck on.",
        how="Posted to the room's chat channel once a day. Nothing posts it yet.",
        composed_by="brain.ops.digest_delivery:deliver_digest",
    ),
    Notice(
        kind=NoticeKind.APPROVAL_REQUEST,
        title="Something waiting for your approval",
        told="Whoever may approve an action an agent is holding.",
        about="That the action is waiting for them, and until when.",
        how=(
            "A card in the approver's chat channel. Nothing sends it yet: an approver opens the "
            "Approvals screen."
        ),
        composed_by="brain.channels.cards:build_approval_card",
    ),
    Notice(
        kind=NoticeKind.DENIAL_PATTERN,
        title="A colleague keeps being refused",
        told="People who can fix a colleague's access, never the colleague.",
        about="The shape of a pattern of refusals, never what was refused.",
        how="No channel is chosen for it yet, so nothing sends it.",
        composed_by="brain.ops.denial_alerts:digest",
    ),
    Notice(
        kind=NoticeKind.BUDGET_STOPPED,
        title="A budget reached its ceiling",
        told="Administrators with authority over the budget, or those above them.",
        about="That work stopped at a budget's ceiling, and which budget.",
        how="No channel is chosen for it yet, so nothing sends it.",
        composed_by="brain.ops.budget_stop:warn",
    ),
    Notice(
        kind=NoticeKind.ACCESS_REQUEST,
        title="Somebody asked to see a field",
        told="The owner of the field.",
        about="That a named person asked for access, never the value they could not see.",
        how=(
            "Listed on the owner's Access requests screen in the console, which is where it is "
            "read; no channel sends it yet."
        ),
        composed_by="brain.core.access_route:route_access_request",
    ),
    Notice(
        kind=NoticeKind.HANDED_TO_A_PERSON,
        title="A question handed to a person",
        told="The human queue a question was handed to.",
        about="That a question needs a person to answer it.",
        how="The queue's channel. Nothing sends it yet.",
        composed_by="brain.gate.abstain:raise_escalation",
    ),
    Notice(
        kind=NoticeKind.LEARNING_DIGEST,
        title="What the system learnt from your work",
        told="Each person, about their own work.",
        about="What was learnt that week, with a way to undo it.",
        how="By email or chat, once a week. Nothing sends it yet.",
        composed_by="brain.memory.digest:weekly_digest",
    ),
    Notice(
        kind=NoticeKind.CONTROL_NOT_RUN,
        title="A safety mechanism has not run",
        told="Whoever holds the operations alert, and for the worst, the incident capability.",
        about="Which mechanism has not run and for how long, never what it covers.",
        how="No channel is chosen for it yet, so nothing sends it.",
        composed_by="brain.ops.controls:overdue",
        fixed_because=A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH,
    ),
    Notice(
        kind=NoticeKind.BACKUP_EXPOSURE,
        title="Work with no copy anywhere",
        told="Whoever is on call.",
        about="How long the install has gone without a backup it could be recovered from.",
        how="No channel is chosen for it yet, so nothing sends it.",
        composed_by="brain.ops.recovery:alerts",
        fixed_because=A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH,
    ),
    Notice(
        kind=NoticeKind.EMERGENCY_ACCESS,
        title="Somebody took emergency access",
        told="Every standing super administrator other than the person and whoever allowed it.",
        about="Who took it, who allowed it and until when.",
        how="No channel is chosen for it yet, so nothing sends it.",
        composed_by="brain.identity.roles:open_break_glass",
        fixed_because=A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH,
    ),
    Notice(
        kind=NoticeKind.SELF_GRANT,
        title="An administrator granted themselves something",
        told="A standing super administrator who is not that administrator.",
        about="What was granted, to whom and by whom.",
        how="No channel is chosen for it yet, so nothing sends it.",
        composed_by="brain.console.global_surfaces:self_grant_notices",
        fixed_because=A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH,
    ),
    Notice(
        kind=NoticeKind.AUTOMATION_PAUSED,
        title="An automation was paused for failing",
        told="The automation's owner.",
        about="Which automation stopped, and why.",
        how=(
            "Shown beside the automation on its agent's Automations tab, with the reason. No "
            "channel sends it to the owner yet."
        ),
        composed_by="brain.console.agent_automations:failure_pause",
        fixed_because=A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH,
    ),
)


def notice(kind: str) -> Notice:
    """One notice by its kind's value, refusing a name this product does not declare."""
    for one in NOTICES:
        if one.kind.value == kind:
            return one
    msg = f"{kind!r} is not a notice this product composes"
    raise NoticeError(msg)


def switched_off_in(states: Mapping[str, SettingState]) -> frozenset[NoticeKind]:
    """The notices a person has switched off: a switchable notice whose row holds JSON `false`.

    `is False` rather than falsiness, for `brain.ops.features.switched_on_in`'s reason turned round:
    a string or a null written at a prompt is not a person switching a notice off, and a notice
    with no switch is on whatever a row says. See `A_NOTICE_SHIPS_ON`.
    """
    return frozenset(
        one.kind
        for one in NOTICES
        if one.switchable
        and (state := states.get(one.kind.value)) is not None
        and state.value_type == SettingType.BOOLEAN.value
        and state.value is False
    )


async def switch_states(session: AsyncSession) -> dict[str, SettingState]:
    """Every live switch row, by notice kind."""
    return values_under(await read_namespace(session, NOTICE_NAMESPACE), NOTICE_NAMESPACE)


async def notice_is_on(session: AsyncSession, kind: NoticeKind) -> bool:
    """Whether this notice may be sent now. The one question every sender asks."""
    return kind not in switched_off_in(await switch_states(session))


async def switch(session: AsyncSession, one: Notice, *, on: bool, by: str) -> None:
    """Switch a notice on or off in the caller's transaction, refusing one that has no switch."""
    if not one.switchable:
        msg = f"{one.kind.value} has no switch. {one.fixed_because}"
        raise NoticeError(msg)
    await put(
        session,
        f"{NOTICE_NAMESPACE}.{one.kind.value}",
        value_type=SettingType.BOOLEAN,
        value=on,
        description=SWITCH_DESCRIPTION,
        updated_by=by,
    )
