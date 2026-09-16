"""Saying an answer was wrong from the place it was read, and what that may carry.

`brain.adoption.correction_gaps` states the finding this answers: a correction path that
exists only in the console is a correction path for the people who use the console, and most
answers are read in a chat message. `brain.ops.feedback` holds the decision half, a closed
vocabulary and a reach check, and until this module no channel adapter could reach it.

**Once, at the seam every adapter already shares, rather than six times.** There are two
halves and each sits on a type no adapter can avoid. The offer goes out through
`ChannelAdapter.send`, whose `body` every adapter must accept because the protocol says so,
and the correction comes back as a `ChannelEvent`, which is the one shape every adapter's
`normalise` produces. Nothing here names a vendor, so an adapter added tomorrow carries both
halves by satisfying the protocol, and `tests/unit/test_channel_correction.py` walks the same
discovery `tests/invariants/test_channel_adapter_invariants.py` uses to prove each one does.

**The line holds a reason and a reference and nothing else, and anything more is not a
correction.** A chat reply is free text, which is exactly the field
`brain.ops.feedback.A_FREE_TEXT_NOTE_IS_WHERE_THE_ANSWER_GETS_PASTED` refuses to have. So the
reader accepts a line that is one `FlagReason` value and one reference, and a line with a
sentence after it is not read as a correction at all rather than read with the sentence
dropped. See `A_CORRECTION_LINE_HOLDS_A_REASON_AND_A_REFERENCE_AND_NOTHING_ELSE`.

**Only the first line is read.** An email reply quotes the message it answers, and a line
quoted from an earlier exchange can be a correction somebody else made. Reading the whole body
would file it again, under this sender's name.

**Every outcome is acknowledged with one sentence, and the sentence cannot be told which.** A
correction naming a reference the sender may flag, one naming a reference in a department
they hold nothing in, and one naming a reference that resolves to nothing are three different
events and one reply. The second two differing would let somebody learn which references exist
and which departments they sit in by typing them, which is DENIED and ABSENT told apart one
message at a time. `acknowledge` has no parameter an outcome could arrive through; the outcome
is `file_correction`'s return value, for the audit log. See
`EVERY_CORRECTION_IS_ACKNOWLEDGED_ALIKE`.

**Resolving the reference is not done here.** Which question and which department a trace
reference names is a lookup made by something entitled to open the trace, and a channel module
that opened traces would be a second path to them. `file_correction` takes the result of that
lookup, or None, and decides nothing else.

**What is still missing is stated rather than implied.** Nothing on a live request path calls
this yet: the per-adapter `deliver` functions send plans that carry no trace reference, and no
route receives channel webhooks that could hand an event to `read_correction`. A correction
from somebody who does not hold `write:answer_flag` is acknowledged and filed nowhere, because
`brain.ops.feedback` is a lead's flag rather than a general signal; the general signal is
`brain.chat.turns.Correction`, whose vocabulary does not yet separate wrong sources from a
wrong answer.

Rejected: a `correct` method on each adapter. Six copies of one parser, and the seventh
adapter's author is the one who does not know to write it.

Rejected: buttons on the surfaces that declare `Feature.CARDS`. A press is a second inbound
shape per vendor, and the text line already works on every surface including those.

Scope: nothing here opens a connection or reads a clock. `now` is a parameter.

Task ids: M34.2.2.1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.channels.adapter import ChannelAdapter, send_operation
from brain.channels.cards import render_body
from brain.connectors.throttle import CallOutcome
from brain.core.entitlement import EntitlementSet
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent
from brain.ops.feedback import REFERENCE_MAX_LENGTH, FeedbackError, Flag, FlagReason, flag_answer
from brain.ops.idempotency import Intent, Issued, Operation, OperationLedger, issue_once

# ------------------------------------------------------------------ written-down reasons
#: Why a correction is a reason and a reference, and a longer line is not one.
A_CORRECTION_LINE_HOLDS_A_REASON_AND_A_REFERENCE_AND_NOTHING_ELSE: Final = (
    "A reply in a chat is free text, and the helpful reply pastes the right figure after the "
    "reason. Reading the reason and dropping the rest would tell the person their note was "
    "kept when it was thrown away, and keeping the rest would be the free-text store "
    "brain.ops.feedback refuses to have. So a line that is more than a reason and a reference "
    "is not a correction, and it reaches whatever handles an ordinary message instead."
)

#: Why a person is told the same thing whatever became of their correction.
EVERY_CORRECTION_IS_ACKNOWLEDGED_ALIKE: Final = (
    "Filed, refused because the sender holds nothing in that department, and ignored because "
    "the reference names nothing: a reply that differed between those would let anybody learn "
    "which references exist and where they sit by typing them one at a time. The outcome goes "
    "to the audit log and the person is sent one sentence that is true of all three."
)

#: What a person is sent after any correction. True of every outcome: it was received.
CORRECTION_ACKNOWLEDGEMENT: Final = "Thank you, that has been received."

#: A mention a surface puts in front of what somebody typed: Lark's `@_user_1` placeholder, a
#: Telegram `@name`, Slack's `<@U0ABC>` and Teams' `<at>Brain</at>`. Only leading, and only
#: these shapes, because a group message has to address the bot before it says anything.
_MENTION: Final = r"(?:@\S+|<@[^>\s]+>|<at>[^<]*</at>)"

#: What a trace reference may be spelled with: `secrets.token_urlsafe`'s alphabet, bounded by
#: the cap `brain.ops.feedback` already derives from the reference format.
_REFERENCE: Final = rf"[A-Za-z0-9_-]{{1,{REFERENCE_MAX_LENGTH}}}"

_REFERENCE_RE: Final = re.compile(_REFERENCE)
_LINE_RE: Final = re.compile(
    rf"(?:{_MENTION}\s+)*(?P<reason>[a-z_]+)\s+(?P<reference>{_REFERENCE})"
)


class CorrectionError(Exception):
    """Raised when an answer cannot be offered for correction, which is a wiring fault."""


def correction_line(trace_ref: str) -> str:
    """The line an answer carries so its reader can say it was wrong, from where they read it.

    Names every reason in the vocabulary's own spelling and the reference, and nothing about
    the answer. The reference is quotable and grants nothing, which is
    `brain.gate.compose.ComposedAnswer`'s argument and why it may sit in a room.
    """
    if not _REFERENCE_RE.fullmatch(trace_ref):
        msg = "a correction offered against something that is not a trace reference points nowhere"
        raise CorrectionError(msg)
    reasons = ", ".join(reason.value for reason in FlagReason)
    return f"If this answer is wrong, reply with one of {reasons}, then {trace_ref}"


def send_with_correction(
    adapter: ChannelAdapter,
    payload: ChannelPayload,
    *,
    to: str,
    trace_ref: str,
    ledger: OperationLedger,
    intent: Intent,
) -> Issued:
    """Send an answer with the correction line under it, through any adapter at all, once.

    The body is the payload's own rendering with the line appended, so the label
    `brain.channels.cards.render_body` puts first is still first, and the adapter's own
    `assert_label_survives` check is what confirms it. The send goes through
    `brain.ops.idempotency.issue_once`; see `brain.channels.adapter.send_operation`.
    """
    body = f"{render_body(payload)}\n\n{correction_line(trace_ref)}"

    def send(_: Operation) -> CallOutcome:
        adapter.send(payload, to=to, body=body)
        return CallOutcome.OK

    channel = adapter.capabilities().channel
    return issue_once(ledger, send_operation(intent, channel=channel, to=to), send)


@dataclass(frozen=True)
class CorrectionRequest:
    """One person saying one answer was wrong, as read off a channel event.

    A reason and a reference and the event's own identifiers. No text: see
    `A_CORRECTION_LINE_HOLDS_A_REASON_AND_A_REFERENCE_AND_NOTHING_ELSE`.
    """

    channel: Channel
    external_id: str
    channel_identity: str
    trace_ref: str
    reason: FlagReason
    received_at: datetime


def read_correction(event: ChannelEvent) -> CorrectionRequest | None:
    """The correction this event makes, or None when it is not one.

    The first non-blank line only, and that line whole. None rather than a refusal for
    anything else, because a message that is not a correction is an ordinary message and
    the channel has somewhere to send those.
    """
    first = next((line.strip() for line in event.text.splitlines() if line.strip()), "")
    matched = _LINE_RE.fullmatch(first)
    if matched is None:
        return None
    try:
        reason = FlagReason(matched["reason"])
    except ValueError:
        return None
    return CorrectionRequest(
        channel=event.channel,
        external_id=event.external_id,
        channel_identity=event.channel_identity,
        trace_ref=matched["reference"],
        reason=reason,
        received_at=event.received_at,
    )


@dataclass(frozen=True)
class AnswerOnFile:
    """What an entitled lookup of a trace reference found: which question, in which department."""

    question_id: str
    department: str


def file_correction(
    request: CorrectionRequest,
    *,
    found: AnswerOnFile | None,
    flagger: EntitlementSet,
    now: datetime,
) -> Flag | None:
    """File the correction as a flag, or file nothing, and say which to the audit log only.

    `found` is None when the reference resolved to nothing the lookup could open. `flagger`
    is the sender's entitlement set, resolved by whoever bound their channel identity.
    `brain.ops.feedback.flag_answer` is the whole decision, and its refusal is caught here so
    that it can never become a reply: see `EVERY_CORRECTION_IS_ACKNOWLEDGED_ALIKE`.
    """
    if found is None:
        return None
    try:
        return flag_answer(
            trace_ref=request.trace_ref,
            question_id=found.question_id,
            department=found.department,
            flagger=flagger,
            reason=request.reason,
            now=now,
        )
    except FeedbackError:
        return None


def acknowledge(
    adapter: ChannelAdapter, *, to: str, ledger: OperationLedger, intent: Intent
) -> Issued:
    """Tell the sender their correction arrived, once. No parameter says what became of it.

    The intent is the correction event's, so a correction delivered twice by its channel is
    acknowledged once.
    """

    def send(_: Operation) -> CallOutcome:
        adapter.send(ChannelPayload(), to=to, body=CORRECTION_ACKNOWLEDGEMENT)
        return CallOutcome.OK

    channel = adapter.capabilities().channel
    return issue_once(ledger, send_operation(intent, channel=channel, to=to), send)
