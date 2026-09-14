"""A thread belongs to the person who started it, whichever app each message was typed into.

`brain.tables.chat` already made the storage decision this module needs, and made it for this
reason: `channel` sits on the message and not on the conversation, so a question asked in the
console and followed up in Lark is one thread rather than two. What was missing was anything
that read it. `brain.member_activity.member_notes` reported the gap from the other side, because
`brain.chat.turns.Turn` carries no thread and no channel, and the answer is not to add them to a
turn: a turn is the unit a follow-up re-checks, and a thread is the unit a person scrolls back
through. This module is the second of those, and it builds turns for the first rather than
widening them.

**The thread is keyed to the person and the channel is a fact about one message.** Nothing
here takes a channel to decide which threads exist, and nothing groups messages by one. A
listing asked for from Lark and a listing asked for from the console are the same listing, and
a thread started on either is continued on the other by its id. See
`A_THREAD_IS_THE_PERSONS_AND_THE_CHANNEL_IS_WHERE_ONE_MESSAGE_WAS_TYPED`.

**What was shown then is not what may be shown now, and the second is decided here.**
`brain.tables.chat` argues that keeping a transcript takes nothing from anybody, because the
person read the answer at the time. That is true of the row and it is not true of showing the
row again: an answer re-rendered after the grant behind it was revoked is the words of a record
the reader no longer reaches, arriving through the one screen where it looks most reasonable,
which is `brain.member_activity.OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_WORDS` about a
transcript instead of a memory. So an answer is shown again only if every reference it drew on
is held by the reader at the instant of reading, and is otherwise absent: not marked, not
counted, and not replaced by a sentence saying something was there. See
`AN_ANSWER_IS_SHOWN_AGAIN_ONLY_AT_THE_REACH_HELD_NOW`.

**Continuing on another app is also a question about the app.** An answer rendered for the
console was rendered for the console's ceiling, and `brain.channels.adapter.ChannelCapabilities`
exists because WhatsApp may not carry what the console may. Replaying the stored body onto a
surface with a lower ceiling would carry it past `assert_can_send` without ever being a
payload, so a body crosses only to a surface whose ceiling is at least the one it was rendered
for. The declared ceiling of the surface it came from is an upper bound on what the body
contains rather than a measurement of it, which is the safe direction. See
`AN_ANSWER_RENDERED_FOR_ONE_SURFACE_IS_NOT_REPLAYED_ONTO_A_LOWER_ONE`.

**The person's own questions are always shown.** They are the words the reader typed, and no
grant was needed to know them. This is what makes a thread continuable when every answer in it
has fallen away: the reader still sees what they asked, and asking again goes through the gate.

**The follow-up context is `brain.chat.turns.context_for` and nothing else.** `as_turns`
converts messages to turns and carries references and never an answer's words, so a
continuation made on a new surface draws on exactly what a continuation on the old one would.

Rejected: storing a reach snapshot on each message and replaying under it. That is the
freezing `brain.chat.turns` exists to prevent, written into a column.

Rejected: showing a withheld answer as "no longer available". It tells the reader which of
their own past answers depended on a grant they have since lost, which is a permission fact
about themselves that changes over time in a way they can probe.

Scope: domain logic. Nothing here opens a connection or reads a clock; `now` is a parameter.
Nothing on a live request path builds a `Thread` yet: no store queries `chat.conversation`, and
no route or channel adapter calls the listing or the continuation.

Task ids: M40.2.1.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from pydantic import ValidationError

from brain.channels.adapter import ChannelCapabilities
from brain.chat.turns import RecordRef, Turn, TurnKind, context_for
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.context import Channel
from brain.tables.chat import MessageRole

# ------------------------------------------------------------------ written-down reasons
#: Why nothing here takes a channel to decide which thread a message belongs to.
A_THREAD_IS_THE_PERSONS_AND_THE_CHANNEL_IS_WHERE_ONE_MESSAGE_WAS_TYPED: Final = (
    "brain.tables.chat puts channel on the message and not on the conversation so that a "
    "question asked in the console and followed up in Lark is one thread. A reader that "
    "grouped by channel, or listed only the threads started where the person is now, would "
    "rebuild the split the schema refused, and the person would lose their own context by "
    "switching app. So a thread is found by its owner and its id, and a channel is read only "
    "to decide whether one stored body may be shown on the surface asking."
)

#: Why an answer's words are re-checked when they are shown again.
AN_ANSWER_IS_SHOWN_AGAIN_ONLY_AT_THE_REACH_HELD_NOW: Final = (
    "Keeping a transcript takes nothing from anybody, because the person read the answer at "
    "the time. Showing it again is a new disclosure made now, and an answer re-rendered after "
    "the grant behind it was revoked is the words of a record the reader no longer reaches. "
    "So every reference the answer drew on is held by the reader at the instant of reading, "
    "or the answer is absent. Absent and not marked: a placeholder tells the reader which of "
    "their answers depended on a grant they have since lost."
)

#: Why a stored body does not cross to a surface with a lower ceiling.
AN_ANSWER_RENDERED_FOR_ONE_SURFACE_IS_NOT_REPLAYED_ONTO_A_LOWER_ONE: Final = (
    "A stored answer was rendered for the ceiling of the surface it was asked on, and "
    "brain.channels.adapter.assert_can_send is what stops a payload reaching a surface that "
    "may not carry it. A body replayed from the transcript is not a payload and never passes "
    "that check. So it crosses only to a surface that may carry the ceiling it was rendered "
    "for, and only to one that can show an opaque label if its origin could. The origin's "
    "declared ceiling overstates what one body contains, which is the direction a guess "
    "should err in."
)

#: Why a reference list that cannot be read counts as reaching nothing.
A_REFERENCE_THAT_CANNOT_BE_READ_IS_A_REFERENCE_THAT_REACHES_NOTHING: Final = (
    "chat.message.refs is jsonb, and a check constraint can prove only that it is an array. "
    "An entry missing its capability cannot be re-checked, and an entry carrying anything "
    "beyond an entity, a record id and a capability is carrying a value, which the column "
    "exists to refuse. Reading either as an empty list would make the answer depend on "
    "nothing and show it to everybody; reading it as unreadable withholds the answer and keeps "
    "the question, which costs a re-ask and discloses nothing."
)

#: The keys one stored reference holds, and no others.
REFERENCE_KEYS: Final[frozenset[str]] = frozenset({"entity", "record_id", "required"})


class ThreadError(Exception):
    """A thread was built that nobody could own, or with nothing in it.

    Outside `brain.core.errors` for the reason `brain.member_activity.MemberError` is: those
    five outcomes answer somebody asking a question, and this is a malformed value built by
    whatever loads a transcript.
    """


@dataclass(frozen=True)
class ThreadMessage:
    """One stored message, and the surface it was typed into or rendered for."""

    role: MessageRole
    at: datetime
    channel: Channel
    body: str = ""
    #: What an answer drew on, or None when the stored list could not be read. None and an
    #: empty tuple are different answers: an empty list is an answer that drew on nothing,
    #: and an unreadable one is an answer whose dependencies are unknown. See
    #: `A_REFERENCE_THAT_CANNOT_BE_READ_IS_A_REFERENCE_THAT_REACHES_NOTHING`.
    refs: tuple[RecordRef, ...] | None = ()

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            msg = "a message instant must be timezone-aware; a naive one orders wrongly"
            raise ThreadError(msg)


@dataclass(frozen=True)
class Thread:
    """One conversation, owned by one person, in the order its messages were written.

    There is no channel field. See
    `A_THREAD_IS_THE_PERSONS_AND_THE_CHANNEL_IS_WHERE_ONE_MESSAGE_WAS_TYPED`.
    """

    thread_id: str
    owner_id: str
    title: str
    messages: tuple[ThreadMessage, ...]
    #: `chat.conversation.deleted_at` is set. Row-level security already hides such a row
    #: from the application role; carried so a loader that bypasses the policy still cannot
    #: offer one.
    retired: bool = False

    def __post_init__(self) -> None:
        for name in ("thread_id", "owner_id"):
            if not getattr(self, name).strip():
                msg = f"a thread with no {name} belongs to nobody, and nobody is everybody"
                raise ThreadError(msg)
        if not self.messages:
            msg = "a thread with nothing in it has no instant to be recent at"
            raise ThreadError(msg)

    @property
    def last(self) -> ThreadMessage:
        """The most recent message, whichever surface it arrived on."""
        return max(self.messages, key=lambda one: one.at)


# ------------------------------------------------------------------ the stored references
def refs_from_json(raw: object) -> tuple[RecordRef, ...] | None:
    """`chat.message.refs` as references, or None when any entry cannot be read.

    One bad entry makes the whole list unreadable rather than being skipped, because an
    answer that drew on three records and is re-checked against two has been re-checked
    against a smaller question than the one it answered.
    """
    if not isinstance(raw, list):
        return None
    found: list[RecordRef] = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != REFERENCE_KEYS:
            return None
        values = (entry["entity"], entry["record_id"], entry["required"])
        if not all(isinstance(one, str) and one.strip() for one in values):
            return None
        try:
            required = Capability(value=entry["required"])
        except ValidationError:
            return None
        found.append(
            RecordRef(entity=entry["entity"], record_id=entry["record_id"], required=required)
        )
    return tuple(found)


def refs_as_json(refs: Sequence[RecordRef]) -> list[dict[str, str]]:
    """The references in the shape `refs_from_json` reads. One shape, written in one place."""
    return [
        {"entity": one.entity, "record_id": one.record_id, "required": one.required.value}
        for one in refs
    ]


# ------------------------------------------------------------------ reading it back
def may_show(
    message: ThreadMessage,
    reader: EntitlementSet,
    *,
    reading: ChannelCapabilities,
    surfaces: Mapping[Channel, ChannelCapabilities],
    now: datetime,
) -> bool:
    """Whether this stored message may be shown to this reader on this surface, now.

    The person's own question always may. Anything else needs three things: references that
    could be read, a surface it came from whose ceiling this one may carry, and every
    reference held by the reader at `now`. A surface missing from `surfaces` is a surface
    whose ceiling is unknown, and an unknown ceiling is not one this surface can be shown to
    carry.
    """
    if message.role is MessageRole.USER:
        return True
    origin = surfaces.get(message.channel)
    if message.refs is None or origin is None:
        return False
    if not reading.may_carry(origin.max_classification):
        return False
    if origin.can_carry_label and not reading.can_carry_label:
        return False
    return all(reader.holds(one.required, now) for one in message.refs)


def shown_on(
    thread: Thread,
    reader: EntitlementSet,
    *,
    reading: ChannelCapabilities,
    surfaces: Mapping[Channel, ChannelCapabilities],
    now: datetime,
) -> tuple[ThreadMessage, ...]:
    """The messages of this thread this reader may see on this surface, in thread order.

    One value and nothing beside it saying how many were left out. See
    `AN_ANSWER_IS_SHOWN_AGAIN_ONLY_AT_THE_REACH_HELD_NOW`.
    """
    return tuple(
        one
        for one in thread.messages
        if may_show(one, reader, reading=reading, surfaces=surfaces, now=now)
    )


def as_turns(thread: Thread) -> tuple[Turn, ...]:
    """The thread as the turns `brain.chat.turns.context_for` re-checks.

    A question keeps its words and an answer keeps only its references, so nothing an answer
    said is carried into a follow-up. A system note is nobody's turn and is not converted. An
    answer whose references could not be read contributes none.
    """
    turns: list[Turn] = []
    for one in thread.messages:
        if one.role is MessageRole.USER:
            turns.append(
                Turn(
                    kind=TurnKind.QUESTION,
                    at=one.at,
                    principal_id=thread.owner_id,
                    text=one.body,
                )
            )
        elif one.role is MessageRole.ASSISTANT:
            turns.append(
                Turn(
                    kind=TurnKind.ANSWER,
                    at=one.at,
                    principal_id=thread.owner_id,
                    refs=one.refs or (),
                )
            )
    return tuple(turns)


def continuation_context(
    thread: Thread, reader: EntitlementSet, *, now: datetime
) -> tuple[RecordRef, ...]:
    """What a follow-up on this thread may draw on, whichever surface it is asked from.

    `context_for` over `as_turns`, and deliberately nothing more: a continuation on another
    app has to draw on exactly what a continuation on the same app would.
    """
    return context_for(as_turns(thread), reader, now=now)
